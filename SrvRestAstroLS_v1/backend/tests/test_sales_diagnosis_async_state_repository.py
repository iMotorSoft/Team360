"""Tests for AsyncStateRepository protocol and implementations.

- AsyncInMemoryStateRepository (in-memory, no DB)
- AsyncPostgresConversationStateRepository (DB-dependent if TEAM360_DB_URL set)

No real LLM. No Milvus. No network (except optional DB pool).
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime.contracts import (
    ConversationState,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    StateRepositoryError,
    StateSerializationError,
)
from modules.sales_diagnosis_runtime.providers import (
    AsyncInMemoryStateRepository,
    AsyncStateRepository,
)
from modules.sales_diagnosis_runtime.state_repository import (
    AsyncPostgresConversationStateRepository,
    ConversationStateSerializer,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_state(**overrides: dict) -> ConversationState:
    defaults = ConversationState(
        session_id=str(uuid4()),
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        slots={"industry": "retail"},
        history_summary="Test session.",
        turn_count=1,
        risk_flags=[],
        last_sources=[],
        pending_questions=[],
    )
    return replace(defaults, **overrides)


# -----------------------------------------------------------------------
# Protocol compliance
# -----------------------------------------------------------------------


class TestAsyncStateRepositoryProtocol:
    def test_asyncinmemory_quacks_like_protocol(self):
        repo: AsyncStateRepository = AsyncInMemoryStateRepository()
        assert hasattr(repo, "load")
        assert hasattr(repo, "save")

    def test_asyncpostgres_quacks_like_protocol(self):
        repo: AsyncStateRepository = AsyncPostgresConversationStateRepository()
        assert hasattr(repo, "load")
        assert hasattr(repo, "save")


# -----------------------------------------------------------------------
# AsyncInMemoryStateRepository
# -----------------------------------------------------------------------


class TestAsyncInMemoryStateRepository:
    @pytest.mark.anyio
    async def test_load_returns_none_for_missing_session(self):
        repo = AsyncInMemoryStateRepository()
        result = await repo.load("nonexistent")
        assert result is None

    @pytest.mark.anyio
    async def test_save_and_load_round_trip(self):
        repo = AsyncInMemoryStateRepository()
        state = make_state()
        await repo.save(state)
        loaded = await repo.load(state.session_id)
        assert loaded is not None
        assert loaded.session_id == state.session_id
        assert loaded.turn_count == state.turn_count
        assert loaded.slots == state.slots

    @pytest.mark.anyio
    async def test_save_overwrites_existing(self):
        repo = AsyncInMemoryStateRepository()
        state = make_state(turn_count=1)
        await repo.save(state)
        updated = make_state(session_id=state.session_id, turn_count=5)
        await repo.save(updated)
        loaded = await repo.load(state.session_id)
        assert loaded is not None
        assert loaded.turn_count == 5

    @pytest.mark.anyio
    async def test_multi_sessions_independent(self):
        repo = AsyncInMemoryStateRepository()
        s1 = make_state()
        s2 = make_state()
        await repo.save(s1)
        await repo.save(s2)
        loaded1 = await repo.load(s1.session_id)
        loaded2 = await repo.load(s2.session_id)
        assert loaded1 is not None
        assert loaded2 is not None
        assert loaded1.session_id != loaded2.session_id

    @pytest.mark.anyio
    async def test_round_trip_preserves_retrieved_chunks(self):
        repo = AsyncInMemoryStateRepository()
        chunk = RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            knowledge_scope_id="ks_test",
            source_uri="/doc.md",
            title="Doc",
            node_path="/root",
            score=0.95,
            content_preview="Preview",
            content="Full content.",
        )
        state = make_state(last_sources=[chunk])
        await repo.save(state)
        loaded = await repo.load(state.session_id)
        assert loaded is not None
        assert len(loaded.last_sources) == 1
        assert loaded.last_sources[0].chunk_id == "c1"
        assert loaded.last_sources[0].score == 0.95


# -----------------------------------------------------------------------
# AsyncPostgresConversationStateRepository (no DB)
# -----------------------------------------------------------------------


class TestAsyncPostgresConversationStateRepositoryNoDB:
    def test_no_pool_raises_on_load(self):
        repo = AsyncPostgresConversationStateRepository()
        with pytest.raises(StateRepositoryError, match="requires an injected pool"):
            import asyncio
            asyncio.run(repo.load("s1"))

    def test_no_pool_raises_on_save(self):
        repo = AsyncPostgresConversationStateRepository()
        state = make_state()
        with pytest.raises(StateRepositoryError, match="requires an injected pool"):
            import asyncio
            asyncio.run(repo.save(state))

    def test_injects_pool(self):
        pool = object()
        repo = AsyncPostgresConversationStateRepository(pool=pool)
        assert repo._pool is pool

    def test_repr_no_secret(self):
        repo = AsyncPostgresConversationStateRepository()
        rep = repr(repo)
        assert "table=" in rep
        assert "pool_configured" in rep
        assert "password" not in rep.lower()

    def test_table_name_is_correct(self):
        repo = AsyncPostgresConversationStateRepository()
        assert repo.TABLE_NAME == "sales_diagnosis_conversation_states"


# -----------------------------------------------------------------------
# AsyncPostgresConversationStateRepository (with real DB)
# -----------------------------------------------------------------------

pytestmark_postgres = pytest.mark.skipif(
    not pytest.importorskip("os").environ.get("TEAM360_DB_URL", "").strip()
    and not pytest.importorskip("os").environ.get("TEAM360_DB_URL_PSQL", "").strip(),
    reason="No TEAM360_DB_URL set. Skipping DB tests.",
)


@pytest.fixture(scope="module")
def db_pool():
    import os

    from psycopg_pool import AsyncConnectionPool

    url = os.environ.get("TEAM360_DB_URL", "").strip()
    if not url:
        url = os.environ.get("TEAM360_DB_URL_PSQL", "").strip()
    if not url:
        pytest.skip("No DB URL available")

    pool = AsyncConnectionPool(
        conninfo=url,
        min_size=1,
        max_size=2,
        timeout=5,
        open=False,
        kwargs={"application_name": "team360-test-async-repo"},
    )
    import asyncio
    asyncio.run(pool.open())

    yield pool

    asyncio.run(pool.close())


@pytest.mark.anyio
class TestAsyncPostgresConversationStateRepositoryWithDB:
    @pytest.fixture(autouse=True)
    async def setup(self, db_pool):
        self.repo = AsyncPostgresConversationStateRepository(pool=db_pool)

    async def _cleanup(self, session_id: str):
        async with self.repo._pool.connection() as conn:
            await conn.execute(
                f"DELETE FROM {self.repo.TABLE_NAME} WHERE session_id = %(sid)s",
                {"sid": session_id},
            )
            await conn.commit()

    async def test_save_and_load_round_trip(self):
        state = make_state()
        try:
            await self.repo.save(state)
            loaded = await self.repo.load(state.session_id)
            assert loaded is not None
            assert loaded.session_id == state.session_id
            assert loaded.turn_count == state.turn_count
            assert loaded.slots == state.slots
            assert loaded.history_summary == state.history_summary
        finally:
            await self._cleanup(state.session_id)

    async def test_load_returns_none_for_missing_session(self):
        result = await self.repo.load("nonexistent_session_id_xyz")
        assert result is None

    async def test_save_updates_existing_state(self):
        state = make_state(turn_count=1)
        try:
            await self.repo.save(state)
            updated = make_state(
                session_id=state.session_id,
                turn_count=5,
                history_summary="Updated summary.",
            )
            await self.repo.save(updated)
            loaded = await self.repo.load(state.session_id)
            assert loaded is not None
            assert loaded.turn_count == 5
            assert loaded.history_summary == "Updated summary."
        finally:
            await self._cleanup(state.session_id)

    async def test_save_and_load_with_chunks(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            knowledge_scope_id="ks_test",
            source_uri="/doc.md",
            title="Doc",
            node_path="/root",
            score=0.95,
            content_preview="Preview",
            content="Full content.",
        )
        state = make_state(last_sources=[chunk])
        try:
            await self.repo.save(state)
            loaded = await self.repo.load(state.session_id)
            assert loaded is not None
            assert len(loaded.last_sources) == 1
            assert loaded.last_sources[0].chunk_id == "c1"
            assert loaded.last_sources[0].score == 0.95
            assert loaded.last_sources[0].title == "Doc"
        finally:
            await self._cleanup(state.session_id)

    async def test_save_with_empty_session_id_raises(self):
        state = make_state(session_id="")
        with pytest.raises(StateSerializationError):
            await self.repo.save(state)

    async def test_multi_session_independence(self):
        s1 = make_state()
        s2 = make_state()
        try:
            await self.repo.save(s1)
            await self.repo.save(s2)
            loaded1 = await self.repo.load(s1.session_id)
            loaded2 = await self.repo.load(s2.session_id)
            assert loaded1 is not None
            assert loaded2 is not None
            assert loaded1.session_id != loaded2.session_id
            assert loaded1.turn_count == 1
            assert loaded2.turn_count == 1
        finally:
            await self._cleanup(s1.session_id)
            await self._cleanup(s2.session_id)

    async def test_jsonb_is_valid_json(self):
        import json

        state = make_state()
        serialized = ConversationStateSerializer.to_dict(state)
        raw_json = json.dumps(serialized)
        reparsed = json.loads(raw_json)
        assert reparsed["session_id"] == state.session_id
        assert reparsed["turn_count"] == state.turn_count

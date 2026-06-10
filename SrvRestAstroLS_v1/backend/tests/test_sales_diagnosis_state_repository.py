"""Tests for ConversationState persistence skeleton.

No DB real. No Milvus. No LLM. No network.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    ConversationStateSerializer,
    InMemoryConversationStateRepository,
    InvalidAssistantRuntimeInputError,
    PostgresConversationStateRepository,
    RetrievedChunk,
    StateRepositoryError,
    StateSerializationError,
)


SAMPLE_CHUNKS = [
    RetrievedChunk(
        chunk_id="c1",
        document_id="d1",
        knowledge_scope_id="ks_test",
        source_uri="/docs/test.md",
        title="Test Document",
        node_path="/test/path",
        score=0.95,
        content_preview="Preview text",
        content="Full content text.",
    ),
    RetrievedChunk(
        chunk_id="c2",
        document_id="d1",
        knowledge_scope_id="ks_test",
        source_uri="/docs/test2.md",
        title=None,
        node_path=None,
        score=0.85,
        content_preview="",
        content="",
    ),
]


def make_full_state() -> ConversationState:
    return ConversationState(
        session_id=str(uuid4()),
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        slots={"industry": "retail", "size": "medium"},
        history_summary="User asked about automation.",
        turn_count=3,
        risk_flags=["pricing_sensitive"],
        last_sources=list(SAMPLE_CHUNKS),
        pending_questions=["What channel do you use?"],
    )


def make_minimal_state() -> ConversationState:
    return ConversationState(
        session_id=str(uuid4()),
        assistant_instance_code="test",
        package_code="test",
        knowledge_scope_code="test",
    )


# ===================================================================
# Serializer
# ===================================================================


class TestConversationStateSerializer:
    def test_round_trip_preserves_core_fields(self):
        original = make_full_state()
        data = ConversationStateSerializer.to_dict(original)
        restored = ConversationStateSerializer.from_dict(data)
        assert restored.session_id == original.session_id
        assert restored.assistant_instance_code == original.assistant_instance_code
        assert restored.package_code == original.package_code
        assert restored.knowledge_scope_code == original.knowledge_scope_code
        assert restored.turn_count == original.turn_count
        assert restored.slots == original.slots
        assert restored.history_summary == original.history_summary

    def test_round_trip_preserves_retrieved_chunks(self):
        original = make_full_state()
        data = ConversationStateSerializer.to_dict(original)
        restored = ConversationStateSerializer.from_dict(data)
        assert len(restored.last_sources) == len(original.last_sources)
        for r, o in zip(restored.last_sources, original.last_sources):
            assert r.chunk_id == o.chunk_id
            assert r.document_id == o.document_id
            assert r.score == o.score
            assert r.title == o.title
            assert r.node_path == o.node_path

    def test_round_trip_without_chunks(self):
        original = make_minimal_state()
        data = ConversationStateSerializer.to_dict(original)
        restored = ConversationStateSerializer.from_dict(data)
        assert restored.last_sources == []

    def test_handles_missing_optional_fields_in_dict(self):
        data = {
            "session_id": "s1",
            "assistant_instance_code": "a1",
            "package_code": "p1",
            "knowledge_scope_code": "k1",
        }
        state = ConversationStateSerializer.from_dict(data)
        assert state.session_id == "s1"
        assert state.turn_count == 0
        assert state.slots == {}
        assert state.last_sources == []
        assert state.pending_questions == []
        assert state.history_summary is None

    def test_rejects_empty_session_id_in_to_dict(self):
        state = ConversationState(
            session_id="",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
        )
        with pytest.raises(
            StateSerializationError, match="empty session_id"
        ):
            ConversationStateSerializer.to_dict(state)

    def test_rejects_empty_session_id_in_from_dict(self):
        with pytest.raises(
            StateSerializationError, match="without session_id"
        ):
            ConversationStateSerializer.from_dict({"session_id": ""})

    def test_serialized_dict_is_json_compatible(self):
        import json

        original = make_full_state()
        data = ConversationStateSerializer.to_dict(original)
        dumped = json.dumps(data)
        loaded = json.loads(dumped)
        restored = ConversationStateSerializer.from_dict(loaded)
        assert restored.session_id == original.session_id
        assert restored.turn_count == original.turn_count

    def test_chunk_with_none_fields_roundtrips(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            knowledge_scope_id="ks1",
            source_uri="/doc.md",
            title=None,
            node_path=None,
        )
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
            last_sources=[chunk],
        )
        data = ConversationStateSerializer.to_dict(state)
        restored = ConversationStateSerializer.from_dict(data)
        assert restored.last_sources[0].title is None
        assert restored.last_sources[0].node_path is None


# ===================================================================
# InMemory repository
# ===================================================================


class TestInMemoryConversationStateRepository:
    def test_save_and_load(self):
        repo = InMemoryConversationStateRepository()
        state = make_full_state()
        repo.save(state)
        loaded = repo.load(state.session_id)
        assert loaded is not None
        assert loaded.session_id == state.session_id
        assert loaded.turn_count == state.turn_count

    def test_returns_none_for_missing_session(self):
        repo = InMemoryConversationStateRepository()
        assert repo.load("nonexistent") is None

    def test_load_returns_independent_copy(self):
        repo = InMemoryConversationStateRepository()
        state = make_full_state()
        repo.save(state)
        loaded = repo.load(state.session_id)
        loaded.turn_count = 99
        loaded_again = repo.load(state.session_id)
        assert loaded_again.turn_count == state.turn_count

    def test_save_overwrites_existing(self):
        repo = InMemoryConversationStateRepository()
        state1 = make_full_state()
        repo.save(state1)
        state2 = make_full_state()
        state2.session_id = state1.session_id
        state2.turn_count = 10
        repo.save(state2)
        loaded = repo.load(state1.session_id)
        assert loaded.turn_count == 10

    def test_multiple_sessions_independent(self):
        repo = InMemoryConversationStateRepository()
        s1 = make_full_state()
        s2 = make_full_state()
        repo.save(s1)
        repo.save(s2)
        assert repo.load(s1.session_id) is not None
        assert repo.load(s2.session_id) is not None
        assert repo.load(s1.session_id).session_id != s2.session_id


# ===================================================================
# Postgres skeleton
# ===================================================================


class TestPostgresConversationStateRepository:
    def test_has_no_secret_in_repr(self):
        repo = PostgresConversationStateRepository()
        rep = repr(repo)
        assert "table=" in rep
        assert "pool_configured" in rep
        assert "password" not in rep.lower()

    def test_uses_injected_pool(self):
        pool = object()
        repo = PostgresConversationStateRepository(pool=pool)
        assert repo._pool is pool

    def test_load_raises_error_without_pool(self):
        repo = PostgresConversationStateRepository()
        with pytest.raises(StateRepositoryError, match="requires an injected pool"):
            repo.load("s1")

    def test_save_raises_error_without_pool(self):
        repo = PostgresConversationStateRepository()
        state = make_minimal_state()
        with pytest.raises(StateRepositoryError, match="requires an injected pool"):
            repo.save(state)

    def test_table_ddl_is_defined(self):
        assert "sales_diagnosis_conversation_states" in PostgresConversationStateRepository.SUGGESTED_DDL
        assert "state_jsonb" in PostgresConversationStateRepository.SUGGESTED_DDL
        assert "session_id" in PostgresConversationStateRepository.SUGGESTED_DDL


# ===================================================================
# Runtime integration
# ===================================================================


@pytest.fixture
def sample_input() -> AssistantTurnInput:
    return AssistantTurnInput(
        session_id=str(uuid4()),
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        user_message="Quiero automatizar mi negocio",
    )


class TestRuntimeStateIntegration:
    def test_runtime_creates_initial_state_when_missing(self, sample_input):
        repo = InMemoryConversationStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)
        output = runtime.handle_turn(sample_input)
        assert output.next_state is not None
        assert output.next_state.session_id == sample_input.session_id

    def test_runtime_increments_turn_count(self, sample_input):
        repo = InMemoryConversationStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)
        runtime.handle_turn(sample_input)
        runtime.handle_turn(sample_input)
        loaded = repo.load(sample_input.session_id)
        assert loaded is not None
        assert loaded.turn_count == 2

    def test_runtime_saves_state_after_turn(self, sample_input):
        repo = InMemoryConversationStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)
        runtime.handle_turn(sample_input)
        loaded = repo.load(sample_input.session_id)
        assert loaded is not None
        assert loaded.session_id == sample_input.session_id

    def test_runtime_preserves_state_across_turns(self, sample_input):
        repo = InMemoryConversationStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)
        runtime.handle_turn(sample_input)
        loaded = repo.load(sample_input.session_id)
        assert loaded.assistant_instance_code == sample_input.assistant_instance_code
        assert loaded.package_code == sample_input.package_code
        assert loaded.knowledge_scope_code == sample_input.knowledge_scope_code

    def test_runtime_loads_existing_state(self, sample_input):
        repo = InMemoryConversationStateRepository()
        initial = ConversationState(
            session_id=sample_input.session_id,
            assistant_instance_code=sample_input.assistant_instance_code,
            package_code=sample_input.package_code,
            knowledge_scope_code=sample_input.knowledge_scope_code,
            slots={"existing": "data"},
            turn_count=5,
        )
        repo.save(initial)
        runtime = AssistantConversationRuntime(state_repository=repo)
        output = runtime.handle_turn(sample_input)
        assert output.next_state.session_id == sample_input.session_id
        assert output.next_state.slots.get("existing") == "data"

    def test_runtime_handles_load_failure_gracefully(self, sample_input):
        class FailingStateRepo:
            def load(self, session_id: str):
                raise StateRepositoryError("DB unavailable")
            def save(self, state: ConversationState):
                pass

        runtime = AssistantConversationRuntime(
            state_repository=FailingStateRepo()
        )
        # Should not crash; should create fresh state instead
        output = runtime.handle_turn(sample_input)
        assert output.next_state is not None
        assert output.next_state.session_id == sample_input.session_id
        assert output.response_type == "skeleton_ack"

    def test_runtime_handles_save_failure_gracefully(self, sample_input):
        class FailingSaveRepo:
            def load(self, session_id: str):
                return None
            def save(self, state: ConversationState):
                raise StateRepositoryError("DB write failed")

        runtime = AssistantConversationRuntime(
            state_repository=FailingSaveRepo()
        )
        # Should not crash; should return response normally
        output = runtime.handle_turn(sample_input)
        assert output.response_type == "skeleton_ack"
        assert output.response_text is not None

    def test_runtime_without_state_repo_works(self, sample_input):
        runtime = AssistantConversationRuntime()
        output = runtime.handle_turn(sample_input)
        assert output.response_type == "skeleton_ack"
        assert output.next_state is not None

    def test_runtime_uses_serializer_compatible_storage(self, sample_input):
        repo = InMemoryConversationStateRepository()
        runtime = AssistantConversationRuntime(state_repository=repo)
        runtime.handle_turn(sample_input)
        raw = repo._store.get(sample_input.session_id)
        assert raw is not None
        assert "session_id" in raw
        assert "turn_count" in raw
        assert "last_sources" in raw

from __future__ import annotations

from dataclasses import replace
from typing import Any

from modules.db.transaction import execute, fetch_one
from modules.sales_diagnosis_runtime.contracts import (
    ConversationState,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    StateRepositoryError,
    StateSerializationError,
)
from modules.sales_diagnosis_runtime.providers import (
    AsyncStateRepository,
    StateRepository,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIGRATION_FILE = "db/migrations/007_sales_diagnosis_conversation_states.sql"

SUGGESTED_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS sales_diagnosis_conversation_states (
    session_id              text        NOT NULL PRIMARY KEY,
    assistant_instance_code text        NOT NULL,
    package_code            text        NOT NULL,
    knowledge_scope_code    text        NOT NULL,
    state_jsonb             jsonb       NOT NULL,
    created_at_utc          timestamptz NOT NULL DEFAULT now(),
    updated_at_utc          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_sd_cs_jsonb_is_object
        CHECK (jsonb_typeof(state_jsonb) = 'object'::text)
);

CREATE INDEX IF NOT EXISTS idx_sd_cs_updated_at
    ON sales_diagnosis_conversation_states (updated_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_sd_cs_assistant_instance
    ON sales_diagnosis_conversation_states (assistant_instance_code);

CREATE INDEX IF NOT EXISTS idx_sd_cs_package
    ON sales_diagnosis_conversation_states (package_code);

CREATE INDEX IF NOT EXISTS idx_sd_cs_knowledge_scope
    ON sales_diagnosis_conversation_states (knowledge_scope_code);
"""


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class ConversationStateSerializer:
    """Converts ConversationState to/from a JSON-compatible dict.

    This is the boundary between runtime objects and any persistence layer.
    The serialized format is designed for jsonb storage in PostgreSQL.
    """

    @staticmethod
    def to_dict(state: ConversationState) -> dict[str, Any]:
        if not state.session_id or not state.session_id.strip():
            raise StateSerializationError(
                "Cannot serialize ConversationState with empty session_id."
            )
        return {
            "session_id": state.session_id,
            "assistant_instance_code": state.assistant_instance_code,
            "package_code": state.package_code,
            "knowledge_scope_code": state.knowledge_scope_code,
            "slots": dict(state.slots) if state.slots else {},
            "history_summary": state.history_summary,
            "turn_count": state.turn_count,
            "risk_flags": list(state.risk_flags),
            "last_sources": [
                ConversationStateSerializer._chunk_to_dict(c)
                for c in (state.last_sources or [])
            ],
            "pending_questions": list(state.pending_questions),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ConversationState:
        session_id = data.get("session_id", "")
        if not session_id:
            raise StateSerializationError(
                "Cannot deserialize ConversationState without session_id."
            )
        return ConversationState(
            session_id=session_id,
            assistant_instance_code=data.get(
                "assistant_instance_code", ""
            ),
            package_code=data.get("package_code", ""),
            knowledge_scope_code=data.get("knowledge_scope_code", ""),
            slots=dict(data.get("slots", {})),
            history_summary=data.get("history_summary"),
            turn_count=int(data.get("turn_count", 0)),
            risk_flags=list(data.get("risk_flags", [])),
            last_sources=[
                ConversationStateSerializer._chunk_from_dict(c)
                for c in (data.get("last_sources") or [])
            ],
            pending_questions=list(data.get("pending_questions", [])),
        )

    # ------------------------------------------------------------------
    # RetrievedChunk serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_to_dict(chunk: RetrievedChunk) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "knowledge_scope_id": chunk.knowledge_scope_id,
            "source_uri": chunk.source_uri,
            "title": chunk.title,
            "node_path": chunk.node_path,
            "score": chunk.score,
            "content_preview": chunk.content_preview,
            "content": chunk.content,
        }

    @staticmethod
    def _chunk_from_dict(data: dict[str, Any]) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=data.get("chunk_id", ""),
            document_id=data.get("document_id", ""),
            knowledge_scope_id=data.get("knowledge_scope_id", ""),
            source_uri=data.get("source_uri", ""),
            title=data.get("title"),
            node_path=data.get("node_path"),
            score=float(data.get("score", 0.0)),
            content_preview=data.get("content_preview", ""),
            content=data.get("content", ""),
        )


# ---------------------------------------------------------------------------
# InMemory repository
# ---------------------------------------------------------------------------


class InMemoryConversationStateRepository:
    """In-memory state repository for testing and development.

    Stores serialized dicts to ensure round-trip fidelity through the
    serializer, matching real persistence semantics.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def load(self, session_id: str) -> ConversationState | None:
        raw = self._store.get(session_id)
        if raw is None:
            return None
        return ConversationStateSerializer.from_dict(raw)

    def save(self, state: ConversationState) -> None:
        raw = ConversationStateSerializer.to_dict(state)
        self._store[state.session_id] = raw


# ---------------------------------------------------------------------------
# Postgres skeleton
# ---------------------------------------------------------------------------


class PostgresConversationStateRepository:
    """PostgreSQL-backed conversation state repository.

    Architecture invariants:
    - PostgreSQL 18 is source of truth for conversation state.
    - state is stored as jsonb for schema flexibility.
    - SQL is written directly with psycopg 3; no ORM.

    NOTE: This class documents the intended SQL patterns but does NOT
    currently wrap async DB calls correctly — the ``StateRepository``
    protocol is sync while ``psycopg_pool.AsyncConnectionPool`` requires
    async. A future async runtime boundary will resolve this.

    It requires an injected pool and will raise StateRepositoryError
    if called without one.

    The actual DDL lives in ``db/migrations/007_sales_diagnosis_conversation_states.sql``.
    Use ``scripts/smoke_sales_diagnosis_state_postgres.py`` to validate
    the table against a live PostgreSQL 18 instance.
    """

    TABLE_NAME = "sales_diagnosis_conversation_states"
    MIGRATION_FILE = MIGRATION_FILE
    SUGGESTED_DDL = SUGGESTED_TABLE_DDL

    def __init__(self, pool: Any = None) -> None:
        self._pool = pool

    def load(self, session_id: str) -> ConversationState | None:
        """Load state from PostgreSQL (sync skeleton — not yet operational).

        Raises ``StateRepositoryError`` if no pool is injected.
        """
        self._ensure_pool()
        raise StateRepositoryError(
            "PostgresConversationStateRepository.load() is a sync skeleton. "
            "Use scripts/smoke_sales_diagnosis_state_postgres.py or the "
            "future async runtime boundary to interact with the DB table. "
            f"Table: {self.TABLE_NAME}"
        )

    def save(self, state: ConversationState) -> None:
        """Save state to PostgreSQL (sync skeleton — not yet operational).

        Raises ``StateRepositoryError`` if no pool is injected.
        """
        self._ensure_pool()
        raise StateRepositoryError(
            "PostgresConversationStateRepository.save() is a sync skeleton. "
            "Use scripts/smoke_sales_diagnosis_state_postgres.py or the "
            "future async runtime boundary to interact with the DB table. "
            f"Table: {self.TABLE_NAME}"
        )

    def _ensure_pool(self) -> None:
        if self._pool is None:
            raise StateRepositoryError(
                "PostgresConversationStateRepository requires an injected pool. "
                "No pool was provided."
            )

    def __repr__(self) -> str:
        return (
            f"PostgresConversationStateRepository(table="
            f"{self.TABLE_NAME!r}, pool_configured={self._pool is not None})"
        )


# ---------------------------------------------------------------------------
# Async Postgres repository
# ---------------------------------------------------------------------------


class AsyncPostgresConversationStateRepository:
    """Async PostgreSQL-backed conversation state repository.

    Production implementation of AsyncStateRepository.
    Uses psycopg 3 async pool directly — no ORM.
    State stored as jsonb in sales_diagnosis_conversation_states table.

    Requires an injected AsyncConnectionPool.
    """

    TABLE_NAME = "sales_diagnosis_conversation_states"

    def __init__(self, pool: Any = None) -> None:
        self._pool = pool

    async def load(self, session_id: str) -> ConversationState | None:
        self._ensure_pool()
        import json

        async with self._pool.connection() as conn:
            row = await fetch_one(
                conn,
                f"SELECT state_jsonb FROM {self.TABLE_NAME} "
                f"WHERE session_id = %(sid)s",
                {"sid": session_id},
            )
        if row is None:
            return None
        raw = row["state_jsonb"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise StateRepositoryError(
                f"Expected jsonb object for session_id={session_id!r}, "
                f"got {type(raw).__name__}"
            )
        return ConversationStateSerializer.from_dict(raw)

    async def save(self, state: ConversationState) -> None:
        self._ensure_pool()
        import json

        serialized = ConversationStateSerializer.to_dict(state)
        async with self._pool.connection() as conn:
            await execute(
                conn,
                f"INSERT INTO {self.TABLE_NAME} "
                f"(session_id, assistant_instance_code, package_code, "
                f"knowledge_scope_code, state_jsonb, "
                f"created_at_utc, updated_at_utc) "
                f"VALUES (%(session_id)s, %(assistant_instance_code)s, "
                f"%(package_code)s, %(knowledge_scope_code)s, "
                f"%(state_jsonb)s::jsonb, now(), now()) "
                f"ON CONFLICT (session_id) DO UPDATE SET "
                f"state_jsonb = EXCLUDED.state_jsonb, "
                f"updated_at_utc = now()",
                {
                    "session_id": serialized["session_id"],
                    "assistant_instance_code": serialized[
                        "assistant_instance_code"
                    ],
                    "package_code": serialized["package_code"],
                    "knowledge_scope_code": serialized[
                        "knowledge_scope_code"
                    ],
                    "state_jsonb": json.dumps(serialized),
                },
            )

    def _ensure_pool(self) -> None:
        if self._pool is None:
            raise StateRepositoryError(
                "AsyncPostgresConversationStateRepository requires "
                "an injected pool. No pool was provided."
            )

    def __repr__(self) -> str:
        return (
            f"AsyncPostgresConversationStateRepository(table="
            f"{self.TABLE_NAME!r}, pool_configured={self._pool is not None})"
        )

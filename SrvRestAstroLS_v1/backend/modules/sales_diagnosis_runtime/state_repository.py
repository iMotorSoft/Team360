from __future__ import annotations

from dataclasses import replace
from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    ConversationState,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    StateRepositoryError,
    StateSerializationError,
)
from modules.sales_diagnosis_runtime.providers import StateRepository


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUGGESTED_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS sales_diagnosis_conversation_states (
    session_id          text        NOT NULL PRIMARY KEY,
    assistant_instance_code text    NOT NULL,
    package_code        text        NOT NULL,
    knowledge_scope_code text       NOT NULL,
    state_jsonb         jsonb       NOT NULL,
    created_at_utc      timestamptz NOT NULL DEFAULT now(),
    updated_at_utc      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_sd_cs_updated_at
    ON sales_diagnosis_conversation_states (updated_at_utc DESC);
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

    NOTE: This skeleton does NOT connect to any database.
    It requires an injected pool and will raise StateRepositoryError
    if called without one.

    The sync protocol matches the StateRepository contract for this phase.
    A full async implementation may be required at the runtime boundary.
    """

    TABLE_NAME = "sales_diagnosis_conversation_states"
    SUGGESTED_DDL = SUGGESTED_TABLE_DDL

    def __init__(self, pool: Any = None) -> None:
        self._pool = pool

    def load(self, session_id: str) -> ConversationState | None:
        self._ensure_pool()
        try:
            from modules.db.transaction import fetch_one

            row = fetch_one(
                self._pool,
                f"SELECT state_jsonb FROM {self.TABLE_NAME} "
                f"WHERE session_id = %s",
                (session_id,),
            )
            if row is None:
                return None
            raw = row["state_jsonb"]
            if isinstance(raw, dict):
                return ConversationStateSerializer.from_dict(raw)
            import json
            return ConversationStateSerializer.from_dict(
                json.loads(raw)
            )
        except Exception as exc:
            raise StateRepositoryError(
                f"Failed to load state for session {session_id}: {exc}"
            ) from exc

    def save(self, state: ConversationState) -> None:
        self._ensure_pool()
        raw = ConversationStateSerializer.to_dict(state)
        try:
            from modules.db.transaction import execute

            import json

            execute(
                self._pool,
                f"INSERT INTO {self.TABLE_NAME} "
                f"(session_id, assistant_instance_code, package_code, "
                f"knowledge_scope_code, state_jsonb, "
                f"created_at_utc, updated_at_utc) "
                f"VALUES (%s, %s, %s, %s, %s::jsonb, now(), now()) "
                f"ON CONFLICT (session_id) DO UPDATE SET "
                f"state_jsonb = EXCLUDED.state_jsonb, "
                f"assistant_instance_code = EXCLUDED.assistant_instance_code, "
                f"package_code = EXCLUDED.package_code, "
                f"knowledge_scope_code = EXCLUDED.knowledge_scope_code, "
                f"updated_at_utc = now()",
                (
                    state.session_id,
                    state.assistant_instance_code,
                    state.package_code,
                    state.knowledge_scope_code,
                    json.dumps(raw),
                ),
            )
        except Exception as exc:
            raise StateRepositoryError(
                f"Failed to save state for session {state.session_id}: {exc}"
            ) from exc

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

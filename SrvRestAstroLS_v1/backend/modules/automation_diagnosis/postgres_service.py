"""PostgreSQL-backed service for automation diagnosis.

Wraps the sync AutomationDiagnosisService and persists session, answers,
lead and events to PostgreSQL after each operation.

This module does not open any DB pool at import time. The pool must be
provided by the caller (typically wired in app.py startup).
"""

from __future__ import annotations

import json
from typing import Any

from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction

from .ai_interpreter import AIInterpreterPort, build_ai_interpreter
from .postgres_repository import AutomationDiagnosisPostgresRepository
from .service import AutomationDiagnosisService
from .schemas import DiagnosisEvent, DiagnosisSession


class AutomationDiagnosisPersistenceError(RuntimeError):
    """Raised when postgres mode cannot persist a critical diagnosis snapshot."""

    def __init__(self, session_id: str, operation: str, cause: Exception) -> None:
        self.session_id = session_id
        self.operation = operation
        self.cause = cause
        super().__init__(
            "PostgreSQL persistence failed for automation diagnosis "
            f"operation={operation!r} session_id={session_id!r}"
        )


class PostgresAutomationDiagnosisService:
    """Async service that delegates business logic to sync AutomationDiagnosisService
    and persists data to PostgreSQL.

    Business logic runs in-memory first, then the result is written to postgres.
    This keeps the deterministic scoring/classification unchanged.
    """

    def __init__(
        self,
        pool: AsyncConnectionPool,
        ai_interpreter: AIInterpreterPort | None = None,
        postgres_repository: AutomationDiagnosisPostgresRepository | None = None,
    ) -> None:
        self._pool = pool
        self._pg_repo = postgres_repository or AutomationDiagnosisPostgresRepository()
        self._persisted_event_keys: set[tuple[str, str, str, str, str]] = set()
        self._memory_service = AutomationDiagnosisService(
            ai_interpreter=ai_interpreter or build_ai_interpreter(),
        )

    async def start_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._memory_service.start_session(payload)
        await self._persist_session(result["id"])
        return result

    async def save_answer(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._memory_service.save_answer(session_id, payload)
        await self._persist_session(session_id)
        return result

    async def classify(self, session_id: str) -> dict[str, Any]:
        result = self._memory_service.classify(session_id)
        await self._persist_session(session_id)
        return result

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._memory_service.get_session(session_id)

    def search_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._memory_service.search_knowledge(payload)

    def debug(self, session_id: str) -> dict[str, Any]:
        return self._memory_service.debug(session_id)

    def capture_contact(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._memory_service.capture_contact(session_id, payload)

    def finalize(self, session_id: str) -> dict[str, Any]:
        return self._memory_service.finalize(session_id)

    async def _persist_session(self, session_id: str) -> None:
        session: DiagnosisSession = self._memory_service.repository.get_session(session_id)
        events: list[DiagnosisEvent] = self._new_events_for_session(session_id)
        try:
            async with transaction(self._pool) as conn:
                await self._pg_repo.persist_session_snapshot(conn, session, events)
        except Exception as exc:
            raise AutomationDiagnosisPersistenceError(session_id, "persist_session_snapshot", exc) from exc

        for event in events:
            self._persisted_event_keys.add(self._event_key(event))

    def _new_events_for_session(self, session_id: str) -> list[DiagnosisEvent]:
        return [
            event
            for event in self._memory_service.event_recorder.events
            if event.session_id == session_id and self._event_key(event) not in self._persisted_event_keys
        ]

    @staticmethod
    def _event_key(event: DiagnosisEvent) -> tuple[str, str, str, str, str]:
        payload_key = json.dumps(event.payload, sort_keys=True, separators=(",", ":"), default=str)
        return (
            event.event_name,
            event.session_id,
            event.correlation_id,
            event.timestamp_utc,
            payload_key,
        )

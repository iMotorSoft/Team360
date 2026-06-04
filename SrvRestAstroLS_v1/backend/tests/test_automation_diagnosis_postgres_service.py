"""Tests for PostgresAutomationDiagnosisService.

Validates that the async postgres wrapper correctly delegates business logic
and persists via the postgres repository.

These tests use fake pool/connection objects to avoid requiring a real database.
The existing postgres_repository tests already validate SQL correctness.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from modules.automation_diagnosis.ai_interpreter import MockAIInterpreter
from modules.automation_diagnosis.postgres_service import (
    AutomationDiagnosisPersistenceError,
    PostgresAutomationDiagnosisService,
)


class _FakeCursor:
    """Fake async cursor that tracks executed statements and returns rows."""

    def __init__(self, rows: list[dict | None] | None = None):
        self.rowcount = 1
        self.statements: list[tuple[str, dict]] = []
        self._rows = list(rows or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql: str, params: dict | None = None):
        self.statements.append((sql, params or {}))

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    async def fetchall(self):
        rows = self._rows
        self._rows = []
        return rows


class _FakeConnection:
    """Fake connection with cursor() returning a fake cursor."""

    def __init__(self, rows: list[dict | None] | None = None):
        self.notices: list[str] = []
        self._rows = rows or []

    def cursor(self):
        return _FakeCursor(list(self._rows))

    @asynccontextmanager
    async def transaction(self):
        yield self


class _FakePool:
    """Minimal fake pool that returns a _FakeConnection via connection()."""

    def __init__(self, rows: list[dict | None] | None = None):
        self._rows = rows or []

    @asynccontextmanager
    async def connection(self):
        yield _FakeConnection(list(self._rows))


class _RecordingPostgresRepository:
    def __init__(self):
        self.snapshots: list[dict] = []

    async def persist_session_snapshot(self, conn, session, events):
        self.snapshots.append(
            {
                "session_id": session.id,
                "answers": sorted(session.answers.keys()),
                "result": dict(session.result) if session.result else None,
                "events": list(events),
            }
        )
        return {"diagnosis_session_id": "diagnosis-session-uuid"}


class _FailingPostgresRepository:
    async def persist_session_snapshot(self, conn, session, events):
        raise RuntimeError("database unavailable")


def _run(coro):
    return asyncio.run(coro)


def _build_service(pg_repo=None):
    return PostgresAutomationDiagnosisService(
        pool=_FakePool(),
        ai_interpreter=MockAIInterpreter(),
        postgres_repository=pg_repo or _RecordingPostgresRepository(),
    )


def _save_full_answers(service: PostgresAutomationDiagnosisService, session_id: str) -> None:
    answers = [
        ("process_to_automate", {"free_text": "Calificar leads desde el sitio web."}),
        ("business_pain", {"free_text": "Las consultas llegan sin diagnostico previo."}),
        ("systems_involved", {"selected": ["email", "whatsapp"]}),
        ("frequency_volume", {"selected": ["daily", "medium_volume"]}),
        ("rules_clarity", {"selected": ["clear"]}),
        ("human_dependency", {"selected": ["medium"]}),
        ("access_security", {"selected": ["role_permissions"]}),
        ("data_sensitivity", {"selected": ["personal_data"]}),
        ("expected_result", {"free_text": "Lead calificado y siguiente paso sugerido."}),
        ("economic_impact", {"selected": ["high"]}),
    ]
    for step_id, answer in answers:
        _run(service.save_answer(session_id, {"step_id": step_id, "answer": answer}))


def test_postgres_service_start_session_delegates_to_memory_and_persists():
    pg_repo = _RecordingPostgresRepository()
    service = _build_service(pg_repo)

    result = _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))

    assert result["organization_id"] == "org_team360"
    assert result["workspace_id"] == "team360_public_site"
    assert result["assistant_instance_id"] == "team360_sales_diagnosis"
    assert result["id"].startswith("diag_")

    session = service._memory_service.repository.get_session(result["id"])
    assert session is not None
    assert session.status == "active"
    assert pg_repo.snapshots[-1]["session_id"] == result["id"]
    assert pg_repo.snapshots[-1]["answers"] == []
    assert [event.event_name for event in pg_repo.snapshots[-1]["events"]] == ["automation_diagnosis.session_started"]


def test_postgres_service_save_answer_delegates_and_persists():
    pg_repo = _RecordingPostgresRepository()
    service = _build_service(pg_repo)

    start = _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))
    result = _run(service.save_answer(start["id"], {"step_id": "process_to_automate", "answer": {"free_text": "test"}}))

    assert result["session_id"] == start["id"]
    assert result["answer"]["step_id"] == "process_to_automate"
    assert pg_repo.snapshots[-1]["answers"] == ["process_to_automate"]
    assert [event.event_name for event in pg_repo.snapshots[-1]["events"]] == ["automation_diagnosis.answer_saved"]


def test_postgres_service_classify_delegates_and_persists():
    pg_repo = _RecordingPostgresRepository()
    service = _build_service(pg_repo)

    start = _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))
    _save_full_answers(service, start["id"])

    result = _run(service.classify(start["id"]))

    assert "classification" in result
    assert result["classification"] in {"standard_package", "operational_automation", "consulting_required", "not_recommended"}
    assert "score_total" in result
    assert pg_repo.snapshots[-1]["result"]["classification"] == result["classification"]
    assert len(pg_repo.snapshots[-1]["answers"]) == 10
    assert [event.event_name for event in pg_repo.snapshots[-1]["events"]] == [
        "automation_diagnosis.knowledge_retrieved",
        "automation_diagnosis.ai_interpretation_started",
        "automation_diagnosis.ai_interpretation_completed",
        "automation_diagnosis.scoring_completed",
        "automation_diagnosis.classified",
    ]


def test_postgres_service_persists_only_new_events_for_repeated_snapshots():
    pg_repo = _RecordingPostgresRepository()
    service = _build_service(pg_repo)

    start = _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))
    _run(service._persist_session(start["id"]))
    _run(service._persist_session(start["id"]))

    assert [event.event_name for event in pg_repo.snapshots[0]["events"]] == ["automation_diagnosis.session_started"]
    assert pg_repo.snapshots[1]["events"] == []
    assert pg_repo.snapshots[2]["events"] == []


def test_postgres_service_persistence_errors_are_not_silenced():
    service = _build_service(_FailingPostgresRepository())

    with pytest.raises(AutomationDiagnosisPersistenceError) as exc_info:
        _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))

    assert exc_info.value.operation == "persist_session_snapshot"
    assert "PostgreSQL persistence failed" in str(exc_info.value)


def test_postgres_service_finalize_and_capture_contact_work():
    service = _build_service()

    start = _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))

    contact = service.capture_contact(start["id"], {"name": "Test", "email": "test@test.com", "consent": True})
    assert contact["contact"]["email"] == "test@test.com"

    finalized = service.finalize(start["id"])
    assert finalized["status"] == "finalized"


def test_postgres_service_sync_methods_return_directly():
    """get_session, debug, search_knowledge are sync passthroughs."""
    service = _build_service()

    start = _run(service.start_session({"source_url": "https://team360.live", "locale": "es"}))
    session = service.get_session(start["id"])
    assert session["id"] == start["id"]

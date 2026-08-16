import asyncio
from datetime import datetime, timezone

from modules.flow.domain import FlowRequestNotFoundError
from modules.flow.executive_ai import _SYSTEM_PROMPT
from modules.flow.executive_query import (
    AUDIT_SNAPSHOT,
    LIVE,
    augment_metrics,
    build_executive_view,
    executive_closure_fact,
    executive_context,
)
from modules.flow.executive_service import FlowExecutiveAuditService


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def connection(self):
        return _AsyncContext(_Connection())


class _Connection:
    def transaction(self):
        return _AsyncContext()


def _snapshot(**overrides):
    snapshot = {
        "request": {
            "request_id": "r-1",
            "conversation_id": "c-1",
            "sector_id": "alumbrado",
            "sector_name": "Alumbrado Público",
            "category": "alumbrado",
            "description": "Luminaria apagada",
            "location": "Esquina",
            "citizen_address": "vecino@example.com",
            "origin_channel": "email",
            "received_at": "2026-08-16T10:00:00+00:00",
            "confirmed_at": "2026-08-16T10:01:00+00:00",
        },
        "routings": [
            {
                "routing_id": "routing-1",
                "routing_key": "initial_n1",
                "level": 1,
                "destination": "alumbrado.n1@alquimiablue.com",
                "assigned_at": "2026-08-16T10:02:00+00:00",
                "routing_status": "ASSIGNED",
                "work_status": "IN_PROGRESS",
                "first_response_at": "2026-08-16T10:05:00+00:00",
                "first_responder": "tech@alquimiablue.com",
            }
        ],
        "slas": [
            {
                "sla_id": "sla-1",
                "sla_type": "FIRST_RESPONSE",
                "routing_id": "routing-1",
                "level": 1,
                "duration_seconds": 30,
                "started_at": "2026-08-16T10:02:00+00:00",
                "due_at": "2026-08-16T10:02:30+00:00",
                "first_response_at": "2026-08-16T10:05:00+00:00",
                "status": "BREACHED",
                "met_at": None,
                "breached_at": "2026-08-16T10:02:30+00:00",
            }
        ],
        "escalations": [],
        "operations": [],
        "resolution": {
            "resolution_id": "res-1",
            "proposed_by": "tech@alquimiablue.com",
            "proposed_at": "2026-08-16T10:06:00+00:00",
            "routing_id": "routing-1",
            "resolution_text": "Reparada",
            "resolution_status": "APPROVED",
        },
        "approval": {
            "approval_id": "appr-1",
            "approver": "mario.rojas@alquimiablue.com",
            "approver_level": 2,
            "decision": "APPROVED",
            "decision_at": "2026-08-16T10:08:00+00:00",
            "decision_reason": "",
            "source_message_id": "gmail-dec-1",
        },
        "result": {"request_status": "RESOLVED", "resolved_at": "2026-08-16T10:08:00+00:00"},
        "metrics": {
            "total_elapsed_seconds": 480,
            "routing_count": 1,
            "escalation_count": 0,
            "sla_total": 1,
            "sla_met_count": 0,
            "sla_breached_count": 1,
            "levels_reached": 1,
        },
        "timeline": [{"timestamp": "2026-08-16T10:08:00+00:00", "event_type": "REQUEST_RESOLVED"}],
    }
    snapshot.update(overrides)
    return snapshot


class _ClosureRepo:
    def __init__(self, status="ACTIVE"):
        self.status = status

    async def get_request_context(self, conn, request_id):
        if request_id == "missing":
            return None
        return {
            "request_id": request_id,
            "conversation_id": "c-1",
            "status": self.status,
            "description": "Luminaria apagada",
            "location_text": "Esquina",
            "tentative_category": "alumbrado",
            "citizen_address": "vecino@example.com",
        }


class _AuditRepo:
    def __init__(self, record=None):
        self.record = record
        self.built = 0

    async def get_record(self, conn, request_id):
        return self.record

    async def build_snapshot(self, conn, request_id):
        self.built += 1
        return _snapshot()


class _Interpreter:
    def __init__(self):
        self.calls = []

    def interpret(self, question, view):
        self.calls.append((question, view["status_fact"]))
        return f"Resumen de {question}"


def _service(repo, audit, interpreter=None):
    return FlowExecutiveAuditService(
        pool=_Pool(),
        closure_repository=repo,
        audit_repository=audit,
        interpreter=interpreter,
    )


def _audit_record(status="RESOLVED"):
    return {
        "audit_record_id": "audit-1",
        "schema_version": 1,
        "generated_at_utc": datetime(2026, 8, 16, 10, 9, tzinfo=timezone.utc),
        "resolved_at_utc": datetime(2026, 8, 16, 10, 8, tzinfo=timezone.utc),
        "snapshot_sha256": "a" * 64,
        "snapshot_jsonb": _snapshot(result={"request_status": status, "resolved_at": "2026-08-16T10:08:00+00:00"}),
    }


def test_executive_closure_fact_mapping():
    assert executive_closure_fact("RESOLVED") == "closed"
    assert executive_closure_fact("RESOLUTION_PENDING_APPROVAL") == "pending_approval"
    assert executive_closure_fact("ACTIVE") == "open"
    assert executive_closure_fact("CONFIRMED") == "open"


def test_resolved_case_prefers_audit_snapshot():
    record = _audit_record()
    view = asyncio.run(
        _service(_ClosureRepo("RESOLVED"), _AuditRepo(record)).query_case("r-1")
    )
    assert view["data_source"] == AUDIT_SNAPSHOT
    assert view["status_fact"] == "closed"
    assert view["audit"]["audit_record_id"] == "audit-1"
    assert view["audit"]["snapshot_sha256"] == "a" * 64
    assert view["resolution"]["resolution_status"] == "APPROVED"
    assert view["closure_approval"]["decision"] == "APPROVED"
    assert "current_age_seconds" not in view["metrics"]


def test_active_case_is_live_without_fabricated_audit():
    audit = _AuditRepo(record=None)
    view = asyncio.run(
        _service(_ClosureRepo("ACTIVE"), audit).query_case("r-1")
    )
    assert view["data_source"] == LIVE
    assert view["status_fact"] == "open"
    assert view["audit"] is None
    assert audit.built == 1


def test_pending_approval_case_explains_pending_fact():
    audit = _AuditRepo(record=None)
    view = asyncio.run(
        _service(_ClosureRepo("RESOLUTION_PENDING_APPROVAL"), audit).query_case("r-1")
    )
    assert view["data_source"] == LIVE
    assert view["status_fact"] == "pending_approval"


def test_metrics_include_first_response_and_current_age_for_open_cases():
    view = build_executive_view(
        _snapshot(), data_source=LIVE, request_status="ACTIVE"
    )
    augment_metrics(view, now=datetime(2026, 8, 16, 11, 0, tzinfo=timezone.utc))
    assert view["metrics"]["first_response_elapsed_seconds"] == 300
    assert view["metrics"]["current_age_seconds"] == 3600


def test_metrics_no_current_age_for_closed_cases():
    view = build_executive_view(
        _snapshot(), data_source=AUDIT_SNAPSHOT, request_status="RESOLVED"
    )
    augment_metrics(view)
    assert "current_age_seconds" not in view["metrics"]
    assert view["metrics"]["first_response_elapsed_seconds"] == 300


def test_executive_context_is_traceable():
    view = build_executive_view(
        _snapshot(), data_source=AUDIT_SNAPSHOT, request_status="RESOLVED"
    )
    context = executive_context(view)
    assert context["status_fact"] == "closed"
    assert context["routing_history"][0]["routing_id"] == "routing-1"
    assert context["sla"][0]["sla_id"] == "sla-1"
    assert context["resolution"]["resolution_id"] == "res-1"
    assert context["closure_approval"]["approval_id"] == "appr-1"


def test_missing_request_raises_not_found():
    import pytest

    with pytest.raises(FlowRequestNotFoundError):
        asyncio.run(_service(_ClosureRepo("ACTIVE"), _AuditRepo()).query_case("missing"))


def test_llm_guardrails_present_in_prompt():
    prompt = _SYSTEM_PROMPT.lower()
    assert "no inventes eventos" in prompt
    assert "personas" in prompt
    assert "status_fact" in prompt
    assert "el caso no está cerrado" in prompt
    assert "trazabilidad" in prompt
    assert "no está disponible" in prompt


def test_llm_receives_status_fact_and_question():
    audit = _AuditRepo(record=None)
    interpreter = _Interpreter()
    view = asyncio.run(
        _service(_ClosureRepo("ACTIVE"), audit, interpreter).query_case(
            "r-1", question="¿Ya está cerrado?"
        )
    )
    assert interpreter.calls[0][0] == "¿Ya está cerrado?"
    assert interpreter.calls[0][1] == "open"
    assert view["executive_summary"] == "Resumen de ¿Ya está cerrado?"


def test_closure_answer_derived_from_facts_not_llm():
    # Operational truth must be decidable from status alone: a pending case is
    # never answered as closed regardless of LLM wording.
    pending = build_executive_view(
        _snapshot(), data_source=LIVE, request_status="RESOLUTION_PENDING_APPROVAL"
    )
    assert pending["status_fact"] == "pending_approval"
    assert pending["status_fact"] != "closed"

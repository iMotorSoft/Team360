"""Integration tests for public diagnosis HTTP endpoints (/api/diagnosis/*).

Tests the thin wrapper contract over the existing automation_diagnosis service.
Does NOT test business logic (already covered in test_automation_diagnosis.py).
"""

from __future__ import annotations

from litestar.testing import TestClient

from app import create_app
from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.postgres_service import AutomationDiagnosisPersistenceError
import routes.automation_diagnosis as auto_routes
import routes.diagnosis as diagnosis_routes

_PRELUDE = "Entendí que querés analizar este proceso:"


def _client():
    return TestClient(create_app())


# ── /api/diagnosis/start ─────────────────────────────────────────────────


def test_public_start_creates_session_with_defaults():
    with _client() as client:
        response = client.post("/api/diagnosis/start", json={})
    assert response.status_code == 201
    data = response.json()
    assert data["session_id"].startswith("diag_")
    assert data["status"] == "active"
    assert data["assistant_instance_code"] == "team360_sales_diagnosis"
    assert data["assistant_display_name"] == "Vera"
    assert data["next_action"] == "send_message"
    assert data["message"] is None
    tm = data["technical_metadata"]
    assert tm["organization_id"] == "org_team360"
    assert tm["workspace_id"] == "team360_public_site"
    assert tm["automation_package_id"] == "pkg_sales_diagnosis"
    assert tm["knowledge_scope_id"] == "ks_team360_sales_diagnosis"
    assert tm["locale"] == "es"
    assert tm["service_code"] == "svc_sales_diagnosis"
    assert tm["package_code"] == "pkg_sales_diagnosis"
    assert tm["knowledge_scope_code"] == "ks_team360_sales_diagnosis"
    assert tm["template_code"] == "team360_sales_automation_diagnosis"


def test_public_start_with_initial_text():
    text = "Quiero automatizar el seguimiento de leads por WhatsApp."
    with _client() as client:
        response = client.post(
            "/api/diagnosis/start",
            json={"initial_text": text},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["message"] is not None
    assert _PRELUDE in data["message"]


def test_public_start_with_custom_metadata():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/start",
            json={
                "assistant_instance_code": "team360_sales_diagnosis",
                "assistant_display_name": "Vera",
                "source_channel": "partner_landing",
                "site_channel": "mamamia360.co.il",
                "source_url": "https://mamamia360.co.il/",
                "locale": "en",
                "lead_owner": "MamaMia360",
                "service_code": "svc_sales_diagnosis",
                "package_code": "pkg_sales_diagnosis",
                "knowledge_scope_code": "ks_team360_sales_diagnosis",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["assistant_instance_code"] == "team360_sales_diagnosis"
    assert data["assistant_display_name"] == "Vera"
    tm = data["technical_metadata"]
    assert tm["locale"] == "en"


def test_public_start_handles_visitor_merge():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/start",
            json={
                "visitor": {"anonymous_id": "test_123", "custom_field": "value"},
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["session_id"].startswith("diag_")


def test_public_start_maps_to_existing_session():
    """Verify the session created via /api/diagnosis/start is also
    retrievable via the existing service internals (same in-memory store)."""
    with _client() as client:
        resp = client.post("/api/diagnosis/start", json={})
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    with _client() as client:
        resp = client.get(f"/api/diagnosis/session/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id


# ── /api/diagnosis/message ────────────────────────────────────────────────


def test_public_message_saves_answer_and_returns_prelude():
    with _client() as client:
        start_resp = client.post("/api/diagnosis/start", json={})
    session_id = start_resp.json()["session_id"]

    with _client() as client:
        response = client.post(
            "/api/diagnosis/message",
            json={"session_id": session_id, "text": "Recibo 40 leads por dia en WhatsApp."},
        )
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "active"
    assert _PRELUDE in data["message"]
    assert data["next_action"] == "continue_conversation"
    assert data["missing_slots"] == []
    assert data["checklist"] == []
    assert data["metadata"]["mode"] == "wrapper_preliminary"


def test_public_message_nonexistent_session_returns_422():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/message",
            json={"session_id": "diag_nonexistent", "text": "test"},
        )
    assert response.status_code == 422


def test_public_message_empty_text_returns_422():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/message",
            json={"session_id": "diag_test", "text": ""},
        )
    assert response.status_code == 422


# ── /api/diagnosis/session/{session_id} ──────────────────────────────────


def test_public_get_session_returns_state():
    with _client() as client:
        start_resp = client.post("/api/diagnosis/start", json={})
    session_id = start_resp.json()["session_id"]

    with _client() as client:
        response = client.get(f"/api/diagnosis/session/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "active"
    assert data["assistant_instance_code"] == "team360_sales_diagnosis"
    assert data["answers"] == {}
    assert data["result"] is None
    assert data["next_action"] == "continue_conversation"


def test_public_get_session_with_answers():
    with _client() as client:
        start_resp = client.post("/api/diagnosis/start", json={"initial_text": "test process"})
    session_id = start_resp.json()["session_id"]

    with _client() as client:
        response = client.get(f"/api/diagnosis/session/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert "process_to_automate" in data["answers"]


def test_public_get_session_nonexistent_returns_404():
    with _client() as client:
        response = client.get("/api/diagnosis/session/diag_no_such_session")
    assert response.status_code == 404


# ── /api/diagnosis/submit-checklist ────────────────────────────────────────


def test_submit_checklist_returns_501():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/submit-checklist",
            json={"session_id": "diag_test", "answers": []},
        )
    assert response.status_code == 501
    data = response.json()
    assert "checklist_real not implemented" in data["error"]


# ── /api/diagnosis/lead ────────────────────────────────────────────────────


def test_lead_returns_501():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/lead",
            json={
                "session_id": "diag_test",
                "cta_type": "schedule_demo",
                "contact": {"name": "Test"},
                "consent": True,
            },
        )
    assert response.status_code == 501
    data = response.json()
    assert "lead_real not implemented" in data["error"]


# ── Error handling ────────────────────────────────────────────────────────


def test_public_start_persistence_error_returns_503(monkeypatch):
    class _FailingService:
        async def start_session(self, payload):
            raise AutomationDiagnosisPersistenceError("diag_test", "persist", RuntimeError("db down"))

    monkeypatch.setattr(auto_routes, "_SERVICE", _FailingService())

    with _client() as client:
        response = client.post("/api/diagnosis/start", json={})
    assert response.status_code == 503


def test_public_start_ai_error_returns_502(monkeypatch):
    class _FailingAIService:
        async def start_session(self, payload):
            raise AIInterpretationError("AI proxy down")

    monkeypatch.setattr(auto_routes, "_SERVICE", _FailingAIService())

    with _client() as client:
        response = client.post("/api/diagnosis/start", json={})
    assert response.status_code == 502


def test_public_message_persistence_error_returns_503(monkeypatch):
    class _FailingService:
        async def save_answer(self, session_id, payload):
            raise AutomationDiagnosisPersistenceError("diag_test", "persist", RuntimeError("db down"))

    monkeypatch.setattr(auto_routes, "_SERVICE", _FailingService())

    with _client() as client:
        response = client.post(
            "/api/diagnosis/message",
            json={"session_id": "diag_test", "text": "test"},
        )
    assert response.status_code == 503

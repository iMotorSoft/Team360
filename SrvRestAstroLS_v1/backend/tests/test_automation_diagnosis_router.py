"""Integration tests for automation_diagnosis HTTP endpoints.

Tests the full HTTP contract via Litestar TestClient.
The service layer is already tested in test_automation_diagnosis.py.
"""

from __future__ import annotations

from litestar.testing import TestClient

from ls_iMotorSoft_Srv01 import create_app
from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.postgres_service import AutomationDiagnosisPersistenceError
import routes.automation_diagnosis as automation_diagnosis_routes


def _client():
    return TestClient(create_app())


def test_health_returns_ok():
    with _client() as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "backend-team360"


def test_health_root_returns_ok():
    with _client() as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_backend_debug_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TEAM360_BACKEND_DEBUG", raising=False)

    assert create_app().debug is False


def test_backend_debug_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("TEAM360_BACKEND_DEBUG", "1")

    assert create_app().debug is True


def test_unknown_scanner_api_paths_return_controlled_404():
    with _client() as client:
        for path in ("/api/env", "/api/config"):
            response = client.get(path)

            assert response.status_code == 404
            assert response.json()["detail"] == "Not Found"


def test_start_session_returns_session_with_default_config():
    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/start",
            json={"source_url": "https://team360.live", "locale": "es"},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["organization_id"] == "org_team360"
    assert data["workspace_id"] == "team360_public_site"
    assert data["assistant_instance_id"] == "team360_sales_diagnosis"
    assert data["automation_package_id"] == "pkg_sales_diagnosis"
    assert data["knowledge_scope_id"] == "ks_team360_sales_diagnosis"
    assert data["site_channel"] == "team360.live"
    assert data["lead_owner"] == "Team360"
    assert data["locale"] == "es"
    assert data["id"].startswith("diag_")
    assert len(data["events"]) == 1


def test_start_session_ignores_unknown_fields():
    """Pydantic boundary strips fields not in the request schema,
    so scope override via knowledge_scope_id is silently dropped.
    The session starts with the default config.
    """
    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/start",
            json={
                "assistant_instance_id": "team360_sales_diagnosis",
                "knowledge_scope_id": "ks_team360_automation_diagnosis",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["assistant_instance_id"] == "team360_sales_diagnosis"
    assert data["knowledge_scope_id"] == "ks_team360_sales_diagnosis"


def test_save_answer_and_classify_full_flow():
    with _client() as client:
        start_resp = client.post(
            "/api/automation-diagnosis/session/start",
            json={"source_url": "https://team360.live", "locale": "es"},
        )
    assert start_resp.status_code == 201
    session_id = start_resp.json()["id"]

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
        with _client() as client:
            resp = client.post(
                f"/api/automation-diagnosis/session/{session_id}/answer",
                json={"step_id": step_id, "answer": answer},
            )
        assert resp.status_code in (200, 201), f"Failed on step {step_id}: {resp.text}"

    with _client() as client:
        classify_resp = client.post(
            f"/api/automation-diagnosis/session/{session_id}/classify",
        )
    assert classify_resp.status_code in (200, 201)
    result = classify_resp.json()
    assert result["classification"] in {
        "standard_package",
        "operational_automation",
        "consulting_required",
        "not_recommended",
    }
    assert "score_total" in result
    assert "internal_card" in result
    assert result["ai_interpretation"]["provider"] == "mock"
    card = result["internal_card"]
    assert card["organization_id"] == "org_team360"
    assert card["workspace_id"] == "team360_public_site"
    assert card["assistant_instance_id"] == "team360_sales_diagnosis"


def test_classify_nonexistent_session_returns_422():
    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/nonexistent/classify",
        )
    assert response.status_code == 422


def test_save_answer_nonexistent_session_returns_422():
    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/nonexistent/answer",
            json={"step_id": "process_to_automate", "answer": {"free_text": "test"}},
        )
    assert response.status_code == 422


def test_classify_without_answers_returns_422():
    with _client() as client:
        start_resp = client.post(
            "/api/automation-diagnosis/session/start",
            json={"source_url": "https://team360.live"},
        )
    session_id = start_resp.json()["id"]

    with _client() as client:
        response = client.post(
            f"/api/automation-diagnosis/session/{session_id}/classify",
        )
    assert response.status_code == 422


def test_start_session_minimal_payload():
    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/start",
            json={},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["assistant_instance_id"] == "team360_sales_diagnosis"
    assert data["locale"] == "es"


def test_postgres_persistence_error_returns_503(monkeypatch):
    class _FailingService:
        async def start_session(self, payload):
            raise AutomationDiagnosisPersistenceError("diag_test", "persist_session_snapshot", RuntimeError("db down"))

    monkeypatch.setattr(automation_diagnosis_routes, "_SERVICE", _FailingService())

    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/start",
            json={"source_url": "https://team360.live"},
        )

    assert response.status_code == 503
    assert "PostgreSQL persistence failed" in response.text


def test_ai_interpretation_error_returns_502(monkeypatch):
    class _FailingAIService:
        async def classify(self, session_id):
            raise AIInterpretationError("LiteLLM interpretation failed: proxy down")

    monkeypatch.setattr(automation_diagnosis_routes, "_SERVICE", _FailingAIService())

    with _client() as client:
        response = client.post(
            "/api/automation-diagnosis/session/diag_test/classify",
        )

    assert response.status_code == 502
    assert "LiteLLM interpretation failed" in response.text

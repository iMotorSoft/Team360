"""Integration tests for public diagnosis HTTP endpoints (/api/diagnosis/*).

Tests the thin wrapper contract over the existing automation_diagnosis service.
Does NOT test business logic (already covered in test_automation_diagnosis.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.testing import TestClient

from ls_iMotorSoft_Srv01 import create_app
from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.postgres_service import AutomationDiagnosisPersistenceError
import routes.automation_diagnosis as auto_routes
import routes.diagnosis as diagnosis_routes

if TYPE_CHECKING:
    from modules.sales_diagnosis_runtime import AssistantConversationRuntime

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


# ── /api/diagnosis/turn ───────────────────────────────────────────────────


def test_public_turn_first_message_creates_session():
    with _client() as client:
        response = client.post("/api/diagnosis/turn", json={"message": "Quiero automatizar mi proceso de ventas."})
    assert response.status_code == 201
    data = response.json()
    assert data["session_id"]
    assert data["is_new"] is True
    assert data["turn_count"] >= 1
    assert len(data["response_text"]) > 0


def test_public_turn_second_message_reuses_session():
    with _client() as client:
        first = client.post("/api/diagnosis/turn", json={"message": "Quiero automatizar mi proceso de ventas."})
    assert first.status_code == 201
    sid = first.json()["session_id"]

    with _client() as client:
        second = client.post("/api/diagnosis/turn", json={"session_id": sid, "message": "El principal problema es el seguimiento de leads."})
    assert second.status_code == 201
    data = second.json()
    assert data["session_id"] == sid
    assert data["is_new"] is False
    assert data["turn_count"] >= 2
    assert len(data["response_text"]) > 0


def test_public_turn_empty_message_returns_422():
    with _client() as client:
        response = client.post("/api/diagnosis/turn", json={"message": ""})
    assert response.status_code == 422


def test_public_turn_unknown_session_creates_new():
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"session_id": "nonexistent_conv_000000000000", "message": "Hola"},
        )
    assert response.status_code == 201
    data = response.json()
    # Non-existent session_id should create new state for that ID
    assert data["session_id"] == "nonexistent_conv_000000000000"
    assert data["is_new"] is False  # session_id was provided
    assert data["turn_count"] >= 1


# ── Point 1: Classifier injection on public route ─────────────────────────


def _make_runtime_with(intent_classifier=None):
    """Build a minimal runtime with a fake LLM provider to avoid skeleton path,
    and optionally a custom intent classifier."""
    from modules.sales_diagnosis_runtime import AssistantConversationRuntime

    class _FakeLLMForTest:
        model_name: str | None = "test-model"
        def generate(self, input, state, context):
            return "I understand your situation. Let me analyze what I have so far."

    return AssistantConversationRuntime(
        llm_provider=_FakeLLMForTest(),
        intent_classifier=intent_classifier,
    )


def test_public_turn_has_classifier_injected(monkeypatch):
    """Verify the public route builds a runtime with an intent_classifier.
    Uses a custom classifier to confirm it is called for ambiguous messages."""
    from modules.sales_diagnosis_runtime.intent_classifier import (
        IntentClassification,
        IntentSource,
        IntentType,
        IntentScope,
    )
    from modules.sales_diagnosis_runtime.intent_classifier import IntentStateSummary

    call_log: list[str] = []

    class CheckClassifier:
        def classify(self, message: str, summary: IntentStateSummary) -> IntentClassification:
            call_log.append(message)
            return IntentClassification(
                intent=IntentType.PROVIDE_INFORMATION,
                scope=IntentScope.NOT_APPLICABLE,
                confidence=0.95,
                source=IntentSource.AI_CLASSIFIER,
            )

    monkeypatch.setattr(
        "routes.diagnosis._build_public_turn_runtime",
        lambda: _make_runtime_with(CheckClassifier()),
    )

    # Use a message that does NOT match any high-confidence rule
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "We receive customer inquiries from many different channels every day"},
        )
    assert response.status_code == 201
    assert len(call_log) > 0, "Intent classifier was never called for ambiguous message"
    assert "customer inquiries" in call_log[0]


# ── Point 2: Public metadata contract ────────────────────────────────────


def test_public_turn_response_includes_turn_decision(monkeypatch):
    """Verify PublicTurnResponse includes turn_decision with metadata."""
    from modules.sales_diagnosis_runtime.intent_classifier import (
        IntentClassification,
        IntentSource,
        IntentType,
        IntentScope,
    )
    from modules.sales_diagnosis_runtime.intent_classifier import IntentStateSummary

    class FixedClassifier:
        def classify(self, message: str, summary: IntentStateSummary) -> IntentClassification:
            return IntentClassification(
                intent=IntentType.REQUEST_DIAGNOSIS,
                scope=IntentScope.GLOBAL,
                confidence=0.94,
                source=IntentSource.AI_CLASSIFIER,
                matched_rule=None,
            )

    monkeypatch.setattr(
        "routes.diagnosis._build_public_turn_runtime",
        lambda: _make_runtime_with(FixedClassifier()),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "We want to centralize our customer support across WhatsApp and email"},
        )
    assert response.status_code == 201
    data = response.json()

    # Presence
    assert "turn_decision" in data, "Response missing turn_decision"
    td = data["turn_decision"]
    assert td is not None, "turn_decision is None"

    # Shape — at minimum these keys must exist
    for key in ("action", "intent", "intent_scope", "intent_confidence",
                "intent_source", "diagnosis_status", "readiness_reason",
                "classifier_called", "matched_rule"):
        assert key in td, f"turn_decision missing key {key}"

    # Values
    assert td["intent"] == "request_diagnosis"
    assert td["intent_scope"] == "global"
    assert td["intent_source"] == "ai_classifier"
    assert td["classifier_called"] is True
    assert td["matched_rule"] is None


def test_public_turn_fast_path_turn_decision():
    """Fast path (high-confidence rule) should show classifier_called=False."""
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "dame el diagnóstico"},
        )
    assert response.status_code == 201
    data = response.json()
    td = data.get("turn_decision")
    assert td is not None, "turn_decision is None"
    assert td.get("intent") == "request_diagnosis"
    assert td.get("intent_source") == "high_confidence_rule"
    assert td.get("classifier_called") is False
    assert td.get("matched_rule") is not None


def test_public_turn_factual_shortcut_turn_decision():
    """Factual answer (e.g. '80 por día') should be provide_information
    without calling AI."""
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "80 por día"},
        )
    assert response.status_code == 201
    data = response.json()
    td = data.get("turn_decision")
    assert td is not None, "turn_decision is None"
    assert td.get("intent") == "provide_information"
    assert td.get("classifier_called") is False


# ── Point 12: Classifier fallback never diagnoses ────────────────────────


def test_public_turn_classifier_fallback_is_never_diagnose(monkeypatch):
    """When classifier returns runtime_fallback, turn_decision action
    should NOT be 'diagnose'."""
    from modules.sales_diagnosis_runtime.intent_classifier import (
        IntentClassification,
        IntentSource,
    )
    from modules.sales_diagnosis_runtime.intent_classifier import IntentStateSummary

    class FallbackClassifier:
        def classify(self, message: str, summary: IntentStateSummary) -> IntentClassification:
            return IntentClassification(source=IntentSource.RUNTIME_FALLBACK)

    monkeypatch.setattr(
        "routes.diagnosis._build_public_turn_runtime",
        lambda: _make_runtime_with(FallbackClassifier()),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "We have 80 inquiries per day from WhatsApp and Gmail. "
                             "The stock is in the system and prices in a spreadsheet."},
        )
    assert response.status_code == 201
    data = response.json()
    td = data.get("turn_decision")
    assert td is not None, "turn_decision is None"
    assert td.get("action") != "diagnose", (
        "Fallback classifier should not trigger diagnose"
    )
    assert td.get("classifier_called") is False


# ── Generation metadata contract ──────────────────────────────────────────


def test_generation_metadata_success(monkeypatch):
    """Successful generation returns status=success, fallback_used=false."""
    import routes.diagnosis as diagnosis_route

    class _OkClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            pass
        def text_completion(self, model, messages, **kwargs):
            from modules.automation_diagnosis.litellm_client import LiteLLMResponse
            return LiteLLMResponse(content="Respuesta real del modelo.", model=model)

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _OkClient)
    with _client() as client:
        resp = client.post("/api/diagnosis/turn", json={"message": "test"})
    assert resp.status_code == 201
    gen = resp.json().get("turn_decision", {}).get("generation", {})
    assert gen.get("status") == "success"
    assert gen.get("fallback_used") is False


def test_generation_metadata_fallback(monkeypatch):
    """Fallback (timeout) returns status=fallback, fallback_used=true."""
    import routes.diagnosis as diagnosis_route

    class _TimeoutClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            pass
        def text_completion(self, model, messages, **kwargs):
            raise TimeoutError("timeout")

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _TimeoutClient)
    with _client() as client:
        resp = client.post("/api/diagnosis/turn", json={"message": "test"})
    assert resp.status_code == 201
    gen = resp.json().get("turn_decision", {}).get("generation", {})
    assert gen.get("status") == "fallback"
    assert gen.get("fallback_used") is True
    assert gen.get("fallback_reason") == "transient_error"


def test_generation_fallback_localized_es():
    """Spanish fallback text must be the honest localized version."""
    from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT
    assert "no pude procesarla" in SAFE_ACK_TEXT
    assert "intentarlo nuevamente" in SAFE_ACK_TEXT


def test_generation_fallback_localized_en():
    """English fallback text must be the honest localized version."""
    from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXTS
    text = SAFE_ACK_TEXTS.get("en", "")
    assert "couldn't fully process" in text
    assert "try again without losing" in text


def test_generation_fallback_localized_he():
    """Hebrew fallback text must be honest localized version."""
    from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXTS
    text = SAFE_ACK_TEXTS.get("he", "")
    assert "קיבלתי" in text
    assert "המידע" in text


# ── Punto 12: Auth/config error never returns placeholder ──────────────────


def test_public_turn_auth_error_no_placeholder(monkeypatch):
    """Auth error (missing key) returns 503, never SAFE_ACK_TEXT."""
    from modules.automation_diagnosis.litellm_client import LiteLLMClientError

    class _AuthFailClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            raise LiteLLMClientError("API key not configured")

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    import routes.diagnosis as diagnosis_route
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _AuthFailClient)
    with _client() as client:
        resp = client.post("/api/diagnosis/turn", json={"message": "test"})
    assert resp.status_code == 503
    # Must NOT return SAFE_ACK_TEXT
    from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXTS
    body = resp.text
    for text in SAFE_ACK_TEXTS.values():
        assert text[:30] not in body, "Auth error must not return placeholder"


# ── Reintento básico (no corrompe sesión) ────────────────────────────────


def test_retry_after_timeout_preserves_session(monkeypatch):
    """After a timeout, same message retry should not corrupt session."""
    import routes.diagnosis as diagnosis_route
    from modules.automation_diagnosis.litellm_client import LiteLLMResponse

    call_count: list[int] = [0]

    class _CycleClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            pass
        def text_completion(self, model, messages, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                raise TimeoutError("first call timeout")
            return LiteLLMResponse(content="Respuesta exitosa tras reintento.", model=model)

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _CycleClient)
    sid = "retry-test"

    # First call — timeout → fallback
    with _client() as client:
        resp1 = client.post("/api/diagnosis/turn", json={"session_id": sid, "message": "Quiero automatizar ventas"})
    assert resp1.status_code == 201
    gen1 = resp1.json().get("turn_decision", {}).get("generation", {})
    assert gen1.get("status") == "fallback", "First call must be fallback"

    # Second call (same session, same message) — success
    with _client() as client:
        resp2 = client.post("/api/diagnosis/turn", json={"session_id": sid, "message": "Quiero automatizar ventas"})
    assert resp2.status_code == 201
    gen2 = resp2.json().get("turn_decision", {}).get("generation", {})
    assert gen2.get("status") == "success", "Retry must succeed after timeout"
    data2 = resp2.json()
    assert data2["turn_count"] == 2, "Turn count must increment correctly"
    # Session must not be corrupted
    assert data2["response_text"] != resp1.json()["response_text"]


# ── _PublicTurnLLMProvider: centralized key, default model, no silent fallback ─


def test_public_turn_default_model_is_gpt5_nano(monkeypatch):
    """Default model should be openai_gpt-5-nano."""
    from routes.diagnosis import _PublicTurnLLMProvider
    provider = _PublicTurnLLMProvider()
    assert provider._model == "openai_gpt-5-nano"


def test_public_turn_model_from_env(monkeypatch):
    """Model should be overridable via TEAM360_LITELLM_MODEL_ALIAS."""
    monkeypatch.setenv("TEAM360_LITELLM_MODEL_ALIAS", "requesty_deepseek_4_flash")
    from routes.diagnosis import _PublicTurnLLMProvider
    provider = _PublicTurnLLMProvider()
    assert provider._model == "requesty_deepseek_4_flash"


def test_public_turn_litellm_client_error_returns_503(monkeypatch):
    """When LiteLLMClient raises (e.g. missing API key), route returns 503."""
    from modules.automation_diagnosis.litellm_client import LiteLLMClientError

    class _FailingClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            raise LiteLLMClientError("API key not configured")

        def text_completion(self, model, messages, **kwargs):
            raise RuntimeError("should not reach")

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    import routes.diagnosis as diagnosis_route
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _FailingClient)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "Quiero automatizar las consultas"},
        )
    assert response.status_code == 503


def test_public_turn_litellm_http_401_returns_503(monkeypatch):
    """When LiteLLM returns 401 (bad key), route returns 503."""
    from modules.automation_diagnosis.litellm_client import LiteLLMClientError

    class _UnauthorizedClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            pass

        def text_completion(self, model, messages, **kwargs):
            raise LiteLLMClientError("LiteLLM HTTP 401: invalid API key")

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    import routes.diagnosis as diagnosis_route
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _UnauthorizedClient)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "Quiero automatizar las consultas"},
        )
    assert response.status_code == 503
    data = response.json()
    # Must not expose internal secrets
    assert "sk-" not in str(data)
    assert "LiteLLM HTTP 401" in str(data)


def test_public_turn_transient_error_falls_back_safely(monkeypatch):
    """Transient errors (timeout, connection) should return SAFE_ACK_TEXT, not 503."""
    from routes.diagnosis_schemas import PublicTurnResponse

    class _TimeoutClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            pass

        def text_completion(self, model, messages, **kwargs):
            raise TimeoutError("Connection timed out")

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    import routes.diagnosis as diagnosis_route
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _TimeoutClient)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "Quiero automatizar las consultas"},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["response_text"] is not None
    assert len(data["response_text"]) > 0


def test_public_turn_successful_litellm_response(monkeypatch):
    """Successful LiteLLM call returns content from the model."""
    import routes.diagnosis as diagnosis_route

    class _SuccessClient:
        def __init__(self, base_url=None, api_key=None, timeout_seconds=None):
            pass

        def text_completion(self, model, messages, **kwargs):
            from modules.automation_diagnosis.litellm_client import LiteLLMResponse
            return LiteLLMResponse(
                content="Este es un diagnóstico real generado por el modelo.",
                model=model,
            )

    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    monkeypatch.setattr(diagnosis_route, "LiteLLMClient", _SuccessClient)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={"message": "Quiero automatizar las consultas de venta por WhatsApp"},
        )
    assert response.status_code == 201
    data = response.json()
    assert "modelo" in data["response_text"] or "diagnóstico" in data["response_text"]
    td = data.get("turn_decision") or {}
    assert td.get("intent") in ("provide_information", "request_diagnosis")
    # generation metadata must indicate success
    gen = td.get("generation") or {}
    assert gen.get("status") == "success"
    assert gen.get("fallback_used") is False
    assert gen.get("fallback_reason") is None

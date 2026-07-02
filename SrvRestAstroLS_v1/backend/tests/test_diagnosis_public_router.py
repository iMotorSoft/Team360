"""Integration tests for public diagnosis HTTP endpoints (/api/diagnosis/*).

Tests the thin wrapper contract over the existing automation_diagnosis service.
Does NOT test business logic (already covered in test_automation_diagnosis.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
from litestar.testing import TestClient

from ls_iMotorSoft_Srv01 import create_app
from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.postgres_service import AutomationDiagnosisPersistenceError
from modules.embed_clients.hmac import build_canonical_string, sign
from modules.embed_clients.models import EmbedClient
from modules.embed_clients.rate_limit import InMemoryRateLimiter
import routes.automation_diagnosis as auto_routes
import routes.diagnosis as diagnosis_routes
from routes.diagnosis_schemas import PublicTurnRequest

if TYPE_CHECKING:
    from modules.sales_diagnosis_runtime import AssistantConversationRuntime

_PRELUDE = "Entendí que querés analizar este proceso:"


def _client():
    return TestClient(create_app())


def _build_embed_client(**overrides) -> EmbedClient:
    payload = {
        "client_id": "public_demo_client",
        "hmac_secret": "test-embed-secret",
        "assistant_instance_code": "team360_sales_diagnosis",
        "organization_code": "team360_live",
        "workspace_code": "team360_public_site",
        "package_code": "pkg_sales_diagnosis",
        "knowledge_scope_code": "ks_team360_sales_diagnosis",
        "allowed_origins": ["https://embed.cliente.test"],
        "is_active": True,
    }
    payload.update(overrides)
    return EmbedClient(**payload)


def _sign_public_turn(
    secret: str,
    *,
    client_id: str,
    timestamp: int,
    session_id: str,
    message: str,
) -> str:
    canonical = build_canonical_string(
        client_id=client_id,
        timestamp=timestamp,
        session_id=session_id,
        message=message.strip(),
    )
    return f"sha256={sign(canonical, secret)}"


class _RecordingRuntime:
    def __init__(self) -> None:
        self.calls = 0
        self.last_input = None

    def handle_turn(self, input_):
        from modules.sales_diagnosis_runtime.contracts import (
            AssistantTurnOutput,
            ConversationState,
        )

        self.calls += 1
        self.last_input = input_
        return AssistantTurnOutput(
            response_text="respuesta controlada",
            next_state=ConversationState(
                session_id=input_.session_id,
                assistant_instance_code=input_.assistant_instance_code,
                package_code=input_.package_code,
                knowledge_scope_code=input_.knowledge_scope_code,
                turn_count=1,
                semantic_memory={"diagnosis_status": "gathering"},
            ),
            language={"current_language": "es", "preferred_response_language": "es"},
            turn_decision={"action": "reflect_and_ask"},
        )


@dataclass
class _FakeClock:
    current: float

    def now(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


class _RecordingEmbedAuthAuditor:
    def __init__(self) -> None:
        self.events = []

    def record(self, event) -> None:
        self.events.append(event)


class _RequestStub:
    def __init__(self, headers: dict[str, str] | None = None, client_host: str = "127.0.0.1") -> None:
        self.headers = headers or {}
        self.scope = {"client": (client_host, 4321)}


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


# ── Context resolution ──────────────────────────────────────────────────────


def test_public_turn_default_context_no_fields():
    """Request without optional context fields uses hardcoded defaults."""
    from routes.diagnosis import _resolve_public_turn_context
    from routes.diagnosis_schemas import PublicTurnRequest

    data = PublicTurnRequest(message="test")
    ctx = _resolve_public_turn_context(data)
    assert ctx["assistant_instance_code"] == "team360_sales_diagnosis"
    assert ctx["organization_code"] == "team360_live"
    assert ctx["workspace_code"] == "team360_public_site"
    assert ctx["package_code"] == "pkg_sales_diagnosis"
    assert ctx["knowledge_scope_code"] == "ks_team360_sales_diagnosis"


def test_public_turn_explicit_context_overrides_defaults():
    """Request with explicit context fields uses provided values."""
    from routes.diagnosis import _resolve_public_turn_context
    from routes.diagnosis_schemas import PublicTurnRequest

    data = PublicTurnRequest(
        message="test",
        assistant_instance_code="test_instance",
        organization_code="test_org",
        workspace_code="test_ws",
        package_code="test_pkg",
        knowledge_scope_code="test_scope",
    )
    ctx = _resolve_public_turn_context(data)
    assert ctx["assistant_instance_code"] == "test_instance"
    assert ctx["organization_code"] == "test_org"
    assert ctx["workspace_code"] == "test_ws"
    assert ctx["package_code"] == "test_pkg"
    assert ctx["knowledge_scope_code"] == "test_scope"


def test_public_turn_partial_context_fills_defaults():
    """Request with only some context fields fills missing ones from defaults."""
    from routes.diagnosis import _resolve_public_turn_context
    from routes.diagnosis_schemas import PublicTurnRequest

    data = PublicTurnRequest(
        message="test",
        assistant_instance_code="custom_instance",
        package_code="custom_pkg",
    )
    ctx = _resolve_public_turn_context(data)
    assert ctx["assistant_instance_code"] == "custom_instance"
    assert ctx["package_code"] == "custom_pkg"
    assert ctx["organization_code"] == "team360_live"
    assert ctx["workspace_code"] == "team360_public_site"
    assert ctx["knowledge_scope_code"] == "ks_team360_sales_diagnosis"


def test_public_turn_default_context_allowed():
    """Request without context fields is allowed (resolves to default, passes allowlist)."""
    from routes.diagnosis import _resolve_public_turn_context, _validate_public_turn_context_allowed
    from routes.diagnosis_schemas import PublicTurnRequest

    data = PublicTurnRequest(message="test")
    ctx = _resolve_public_turn_context(data)
    # Should not raise
    _validate_public_turn_context_allowed(ctx)


def test_public_turn_explicit_default_context_allowed():
    """Request with explicit context equal to default passes allowlist."""
    from routes.diagnosis import _resolve_public_turn_context, _validate_public_turn_context_allowed
    from routes.diagnosis_schemas import PublicTurnRequest

    data = PublicTurnRequest(
        message="test",
        assistant_instance_code="team360_sales_diagnosis",
        organization_code="team360_live",
        workspace_code="team360_public_site",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
    )
    ctx = _resolve_public_turn_context(data)
    # Should not raise
    _validate_public_turn_context_allowed(ctx)


def test_public_turn_partial_context_allowed_when_resolves_to_default():
    """Request with partial context that resolves to default passes allowlist."""
    from routes.diagnosis import _resolve_public_turn_context, _validate_public_turn_context_allowed
    from routes.diagnosis_schemas import PublicTurnRequest

    data = PublicTurnRequest(
        message="test",
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
    )
    ctx = _resolve_public_turn_context(data)
    # Should not raise (partial fields filled from defaults, full tuple matches allowlist)
    _validate_public_turn_context_allowed(ctx)


def test_public_turn_invalid_context_rejected():
    """Request with invalid context (changed knowledge_scope_code) returns 403."""
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "message": "Quiero automatizar ventas",
                "knowledge_scope_code": "ks_some_other_scope",
            },
        )
    assert response.status_code == 403
    data = response.json()
    assert "not allowed" in data.get("detail", "").lower()


def test_public_turn_invalid_context_error_does_not_leak_allowlist():
    """403 error for invalid context must not leak allowlist values."""
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "message": "Quiero automatizar ventas",
                "knowledge_scope_code": "ks_some_other_scope",
            },
        )
    assert response.status_code == 403
    body = str(response.json())
    # Must not contain default values that would reveal the allowlist
    for leak in ("team360_sales_diagnosis", "team360_live", "team360_public_site",
                 "pkg_sales_diagnosis", "ks_team360_sales_diagnosis"):
        assert leak not in body, f"Error response leaks allowlist value: {leak}"


def test_public_turn_invalid_context_rejected_via_workspace():
    """Request with invalid workspace_code also returns 403."""
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "message": "Quiero automatizar ventas",
                "workspace_code": "some_other_workspace",
            },
        )
    assert response.status_code == 403


def test_public_turn_invalid_context_does_not_create_session():
    """Invalid context must not create a session in state."""
    session_id = "phase7a_invalid_should_not_exist"
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "session_id": session_id,
                "message": "Quiero automatizar ventas",
                "knowledge_scope_code": "ks_some_other_scope",
            },
        )
    assert response.status_code == 403
    # Verify session does NOT exist
    with _client() as client:
        get_resp = client.get(f"/api/diagnosis/session/{session_id}")
    assert get_resp.status_code == 404


def test_public_turn_without_client_id_keeps_default_flow(monkeypatch):
    runtime = _RecordingRuntime()

    monkeypatch.setattr(diagnosis_routes, "_build_public_turn_runtime", lambda: runtime)
    monkeypatch.setattr(diagnosis_routes, "_get_public_scope_resolver", lambda: None)

    response = anyio.run(
        diagnosis_routes.public_turn.fn,
        PublicTurnRequest(session_id="legacy_vera_flow", message="Quiero automatizar ventas"),
        None,
    )

    assert runtime.calls == 1
    assert runtime.last_input.assistant_instance_code == "team360_sales_diagnosis"
    assert runtime.last_input.package_code == "pkg_sales_diagnosis"
    assert runtime.last_input.knowledge_scope_code == "ks_team360_sales_diagnosis"
    assert response.session_id == "legacy_vera_flow"


def test_embed_auth_valid_client_returns_signature(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(client_id="auth_ok_client")

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(
        diagnosis_routes,
        "_build_public_turn_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime should not be called by auth endpoint")),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "embed_auth_ok",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "client_id": embed_client.client_id,
        "timestamp": timestamp,
        "signature": _sign_public_turn(
            embed_client.hmac_secret,
            client_id=embed_client.client_id,
            timestamp=timestamp,
            session_id="embed_auth_ok",
            message="Quiero automatizar consultas por WhatsApp",
        ),
    }


def test_embed_auth_signature_can_authorize_public_turn(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    session_id = "embed_auth_then_turn"
    message = "Quiero automatizar consultas por WhatsApp"
    embed_client = _build_embed_client(
        client_id="auth_turn_client",
        assistant_instance_code="db_assistant",
        organization_code="db_org",
        workspace_code="db_workspace",
        package_code="db_package",
        knowledge_scope_code="db_scope",
    )
    runtime = _RecordingRuntime()

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(diagnosis_routes, "_build_public_turn_runtime", lambda: runtime)
    monkeypatch.setattr(diagnosis_routes, "_get_public_scope_resolver", lambda: None)

    with _client() as client:
        auth_response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": session_id,
                "message": message,
            },
        )

        assert auth_response.status_code == 200
        signed = auth_response.json()

        turn_response = anyio.run(
            diagnosis_routes.public_turn.fn,
            PublicTurnRequest(
                client_id=signed["client_id"],
                timestamp=signed["timestamp"],
                session_id=session_id,
                message=message,
                workspace_code="malicious_workspace",
                knowledge_scope_code="malicious_scope",
            ),
            _RequestStub(
                {
                    "Origin": "https://embed.cliente.test",
                    "X-T360-Signature": signed["signature"],
                }
            ),
        )

    assert runtime.calls == 1
    assert runtime.last_input.assistant_instance_code == "db_assistant"
    assert runtime.last_input.package_code == "db_package"
    assert runtime.last_input.knowledge_scope_code == "db_scope"
    assert turn_response.session_id == session_id


def test_embed_auth_unknown_client_rejected(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository(),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": "unknown_client",
                "session_id": "embed_auth_unknown",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Embed client request is not authorized."


def test_embed_auth_inactive_client_rejected(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    embed_client = _build_embed_client(client_id="embed_auth_inactive", is_active=False)
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "embed_auth_inactive",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_embed_auth_invalid_origin_rejected(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    embed_client = _build_embed_client(client_id="embed_auth_origin_denied")
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://evil.example"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "embed_auth_origin_denied",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_embed_auth_response_does_not_leak_secret_or_context(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(
        client_id="embed_auth_no_leak",
        hmac_secret="super-secret-value",
        organization_code="secret_org",
        workspace_code="secret_ws",
        package_code="secret_pkg",
        knowledge_scope_code="secret_scope",
        allowed_origins=["https://embed.secret.test"],
    )

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.secret.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "embed_auth_no_leak",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 200
    body = str(response.json())
    for leak in (
        embed_client.hmac_secret,
        embed_client.organization_code,
        embed_client.workspace_code,
        embed_client.package_code,
        embed_client.knowledge_scope_code,
        "https://embed.secret.test",
    ):
        assert leak not in body


def test_embed_auth_does_not_create_session(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    session_id = "embed_auth_no_state"
    embed_client = _build_embed_client(client_id="embed_auth_no_state")
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": session_id,
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 200
    assert diagnosis_routes._public_turn_state.load(session_id) is None


def test_embed_auth_rate_limit_allows_under_limit(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    clock = _FakeClock(1_710_000_000)
    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=2, time_source=clock.now)
    auditor = _RecordingEmbedAuthAuditor()
    embed_client = _build_embed_client(client_id="rate_limit_under_limit")

    monkeypatch.setattr(embed_auth, "time", lambda: int(clock.now()))
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: limiter)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        first = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_under_limit_1",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )
        second = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_under_limit_2",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert [event.event_type for event in auditor.events] == [
        "embed_auth_allowed",
        "embed_auth_allowed",
    ]


def test_embed_auth_rate_limit_rejects_over_limit(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    clock = _FakeClock(1_710_000_000)
    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=2, time_source=clock.now)
    auditor = _RecordingEmbedAuthAuditor()
    embed_client = _build_embed_client(client_id="rate_limit_over_limit")

    monkeypatch.setattr(embed_auth, "time", lambda: int(clock.now()))
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: limiter)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        for idx in range(2):
            response = client.post(
                "/api/diagnosis/embed/auth",
                headers={"Origin": "https://embed.cliente.test"},
                json={
                    "client_id": embed_client.client_id,
                    "session_id": f"rate_limit_over_limit_{idx}",
                    "message": "Quiero automatizar consultas por WhatsApp",
                },
            )
            assert response.status_code == 200

        limited = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_over_limit_3",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )

    assert limited.status_code == 429
    assert limited.json()["detail"] == "Too many embed authentication requests."
    assert limited.headers["Retry-After"] == "60"
    assert auditor.events[-1].event_type == "embed_auth_rate_limited"
    assert auditor.events[-1].reason_code == "rate_limited"


def test_embed_auth_rate_limit_is_scoped_by_client_and_origin(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    clock = _FakeClock(1_710_000_000)
    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=1, time_source=clock.now)
    auditor = _RecordingEmbedAuthAuditor()
    first_client = _build_embed_client(
        client_id="rate_limit_scope_a",
        allowed_origins=["https://embed.cliente.test"],
    )
    second_client = _build_embed_client(
        client_id="rate_limit_scope_b",
        allowed_origins=["https://alt-origin.test"],
    )

    monkeypatch.setattr(embed_auth, "time", lambda: int(clock.now()))
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository(
            {
                first_client.client_id: first_client,
                second_client.client_id: second_client,
            }
        ),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: limiter)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        first = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": first_client.client_id,
                "session_id": "rate_limit_scope_a",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )
        limited = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": first_client.client_id,
                "session_id": "rate_limit_scope_a_retry",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )
        isolated = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://alt-origin.test"},
            json={
                "client_id": second_client.client_id,
                "session_id": "rate_limit_scope_b",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )

    assert first.status_code == 200
    assert limited.status_code == 429
    assert isolated.status_code == 200


def test_embed_auth_rate_limit_error_is_generic(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=1, time_source=lambda: 1_710_000_000)
    auditor = _RecordingEmbedAuthAuditor()
    embed_client = _build_embed_client(
        client_id="rate_limit_generic",
        hmac_secret="super-secret-value",
        organization_code="secret_org",
        workspace_code="secret_ws",
        package_code="secret_pkg",
        knowledge_scope_code="secret_scope",
        allowed_origins=["https://embed.secret.test"],
    )

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_auth_rate_limiter",
        lambda: limiter,
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        first = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.secret.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_generic_1",
                "message": "Quiero automatizar ventas",
            },
        )
        limited = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.secret.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_generic_2",
                "message": "Quiero automatizar ventas",
            },
        )

    assert first.status_code == 200
    assert limited.status_code == 429
    body = str(limited.json())
    for leak in (
        embed_client.client_id,
        embed_client.hmac_secret,
        embed_client.organization_code,
        embed_client.workspace_code,
        embed_client.package_code,
        embed_client.knowledge_scope_code,
        "https://embed.secret.test",
    ):
        assert leak not in body


def test_embed_auth_rate_limited_does_not_create_session_or_signature(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    session_id = "rate_limit_no_state"
    embed_client = _build_embed_client(client_id="rate_limit_no_state")
    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=1, time_source=lambda: 1_710_000_000)

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_auth_rate_limiter",
        lambda: limiter,
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: _RecordingEmbedAuthAuditor())

    with _client() as client:
        ok = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_no_state_ok",
                "message": "Quiero automatizar ventas",
            },
        )
        limited = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": session_id,
                "message": "Quiero automatizar ventas",
            },
        )

    assert ok.status_code == 200
    assert limited.status_code == 429
    assert "signature" not in limited.json()
    assert diagnosis_routes._public_turn_state.load(session_id) is None


def test_embed_auth_unknown_client_audited_without_leak(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    auditor = _RecordingEmbedAuthAuditor()

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository(),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: InMemoryRateLimiter(window_seconds=60, max_requests=5, time_source=lambda: 1_710_000_000))
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test", "User-Agent": "agent/1.0"},
            json={
                "client_id": "unknown-secret-client",
                "session_id": "embed_auth_unknown_audit",
                "message": "Mensaje sensible que no debe loguearse",
            },
        )

    assert response.status_code == 403
    event = auditor.events[-1]
    assert event.event_type == "embed_auth_rejected"
    assert event.reason_code == "unknown_client"
    event_dump = str(event.as_dict())
    for leak in (
        "unknown-secret-client",
        "Mensaje sensible que no debe loguearse",
        "https://embed.cliente.test",
        "agent/1.0",
    ):
        assert leak not in event_dump


def test_embed_auth_invalid_origin_audited_without_leak(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    auditor = _RecordingEmbedAuthAuditor()
    embed_client = _build_embed_client(
        client_id="invalid_origin_audit",
        hmac_secret="invalid-origin-secret",
        organization_code="secret_org",
        workspace_code="secret_ws",
        package_code="secret_pkg",
        knowledge_scope_code="secret_scope",
        allowed_origins=["https://embed.secret.test"],
    )

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: InMemoryRateLimiter(window_seconds=60, max_requests=5, time_source=lambda: 1_710_000_000))
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://evil.example"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "invalid_origin_audit_session",
                "message": "Mensaje sensible que no debe loguearse",
            },
        )

    assert response.status_code == 403
    event = auditor.events[-1]
    assert event.event_type == "embed_auth_rejected"
    assert event.reason_code == "invalid_origin"
    event_dump = str(event.as_dict())
    for leak in (
        embed_client.client_id,
        embed_client.hmac_secret,
        embed_client.organization_code,
        embed_client.workspace_code,
        embed_client.package_code,
        embed_client.knowledge_scope_code,
        "https://evil.example",
        "Mensaje sensible que no debe loguearse",
    ):
        assert leak not in event_dump


def test_embed_auth_allowed_event_is_safe(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    clock = _FakeClock(1_710_000_000)
    auditor = _RecordingEmbedAuthAuditor()
    embed_client = _build_embed_client(
        client_id="allowed_event_safe",
        hmac_secret="allowed-event-secret",
        organization_code="secret_org",
        workspace_code="secret_ws",
        package_code="secret_pkg",
        knowledge_scope_code="secret_scope",
        allowed_origins=["https://embed.secret.test"],
    )

    monkeypatch.setattr(embed_auth, "time", lambda: int(clock.now()))
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: InMemoryRateLimiter(window_seconds=60, max_requests=5, time_source=clock.now))
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.secret.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "allowed_event_safe_session",
                "message": "Mensaje sensible que no debe loguearse",
            },
        )

    assert response.status_code == 200
    event = auditor.events[-1]
    assert event.event_type == "embed_auth_allowed"
    assert event.reason_code == "allowed"
    event_dump = str(event.as_dict())
    for leak in (
        embed_client.client_id,
        embed_client.hmac_secret,
        embed_client.organization_code,
        embed_client.workspace_code,
        embed_client.package_code,
        embed_client.knowledge_scope_code,
        "https://embed.secret.test",
        "Mensaje sensible que no debe loguearse",
    ):
        assert leak not in event_dump


def test_embed_auth_rate_limit_window_reset_restores_flow(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    clock = _FakeClock(1_710_000_000)
    limiter = InMemoryRateLimiter(window_seconds=60, max_requests=1, time_source=clock.now)
    auditor = _RecordingEmbedAuthAuditor()
    embed_client = _build_embed_client(client_id="rate_limit_window_reset")

    monkeypatch.setattr(embed_auth, "time", lambda: int(clock.now()))
    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_rate_limiter", lambda: limiter)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_auth_auditor", lambda: auditor)

    with _client() as client:
        first = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_window_reset_1",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )
        limited = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_window_reset_2",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )
        clock.advance(61)
        recovered = client.post(
            "/api/diagnosis/embed/auth",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "session_id": "rate_limit_window_reset_3",
                "message": "Quiero automatizar consultas por WhatsApp",
            },
        )

    assert first.status_code == 200
    assert limited.status_code == 429
    assert recovered.status_code == 200


def test_public_turn_valid_client_id_resolves_context_from_db_and_ignores_body(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    session_id = "embed_session_valid"
    message = "Quiero automatizar turnos por WhatsApp"
    embed_client = _build_embed_client(
        client_id="public_demo_client",
        assistant_instance_code="db_assistant",
        organization_code="db_org",
        workspace_code="db_workspace",
        package_code="db_package",
        knowledge_scope_code="db_scope",
    )
    runtime = _RecordingRuntime()
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)
    monkeypatch.setattr(diagnosis_routes, "_build_public_turn_runtime", lambda: runtime)
    monkeypatch.setattr(diagnosis_routes, "_get_public_scope_resolver", lambda: None)

    signature = _sign_public_turn(
        embed_client.hmac_secret,
        client_id=embed_client.client_id,
        timestamp=timestamp,
        session_id=session_id,
        message=message,
    )

    response = anyio.run(
        diagnosis_routes.public_turn.fn,
        PublicTurnRequest(
            client_id=embed_client.client_id,
            timestamp=timestamp,
            session_id=session_id,
            message=message,
            assistant_instance_code="malicious_assistant",
            organization_code="malicious_org",
            workspace_code="malicious_workspace",
            package_code="malicious_package",
            knowledge_scope_code="malicious_scope",
        ),
        _RequestStub(
            {
                "Origin": "https://embed.cliente.test",
                "X-T360-Signature": signature,
            }
        ),
    )

    assert runtime.calls == 1
    assert runtime.last_input.session_id == session_id
    assert runtime.last_input.assistant_instance_code == "db_assistant"
    assert runtime.last_input.package_code == "db_package"
    assert runtime.last_input.knowledge_scope_code == "db_scope"
    assert response.session_id == session_id


def test_public_turn_unknown_client_id_rejected(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository(),
    )
    monkeypatch.setattr(
        diagnosis_routes,
        "_build_public_turn_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime should not be called")),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "client_id": "unknown_client",
                "timestamp": 1_710_000_000,
                "session_id": "embed_unknown",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Embed client request is not authorized."


def test_public_turn_inactive_client_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(client_id="inactive_client", is_active=False)
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={
                "Origin": "https://embed.cliente.test",
                "X-T360-Signature": _sign_public_turn(
                    embed_client.hmac_secret,
                    client_id=embed_client.client_id,
                    timestamp=timestamp,
                    session_id="embed_inactive",
                    message="Quiero automatizar ventas",
                ),
            },
            json={
                "client_id": embed_client.client_id,
                "timestamp": timestamp,
                "session_id": "embed_inactive",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Embed client request is not authorized."


def test_public_turn_origin_not_allowed_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(client_id="origin_denied")
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={
                "Origin": "https://otro-host.test",
                "X-T360-Signature": _sign_public_turn(
                    embed_client.hmac_secret,
                    client_id=embed_client.client_id,
                    timestamp=timestamp,
                    session_id="embed_origin_denied",
                    message="Quiero automatizar ventas",
                ),
            },
            json={
                "client_id": embed_client.client_id,
                "timestamp": timestamp,
                "session_id": "embed_origin_denied",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_public_turn_missing_signature_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(client_id="missing_signature")
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={"Origin": "https://embed.cliente.test"},
            json={
                "client_id": embed_client.client_id,
                "timestamp": timestamp,
                "session_id": "embed_missing_signature",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_public_turn_invalid_signature_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(client_id="bad_signature")
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={
                "Origin": "https://embed.cliente.test",
                "X-T360-Signature": "sha256=deadbeef",
            },
            json={
                "client_id": embed_client.client_id,
                "timestamp": timestamp,
                "session_id": "embed_bad_signature",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_public_turn_signature_for_different_message_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    timestamp = 1_710_000_000
    embed_client = _build_embed_client(client_id="different_message")
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: timestamp)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)
    monkeypatch.setattr(
        diagnosis_routes,
        "_build_public_turn_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("runtime should not be called")),
    )

    signed_for_other_message = _sign_public_turn(
        embed_client.hmac_secret,
        client_id=embed_client.client_id,
        timestamp=timestamp,
        session_id="embed_different_message",
        message="Mensaje firmado original",
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={
                "Origin": "https://embed.cliente.test",
                "X-T360-Signature": signed_for_other_message,
            },
            json={
                "client_id": embed_client.client_id,
                "timestamp": timestamp,
                "session_id": "embed_different_message",
                "message": "Mensaje distinto que no fue firmado",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Embed client request is not authorized."


def test_public_turn_expired_timestamp_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    now_value = 1_710_000_000
    expired_timestamp = now_value - 301
    embed_client = _build_embed_client(client_id="expired_timestamp")
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: now_value)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={
                "Origin": "https://embed.cliente.test",
                "X-T360-Signature": _sign_public_turn(
                    embed_client.hmac_secret,
                    client_id=embed_client.client_id,
                    timestamp=expired_timestamp,
                    session_id="embed_expired",
                    message="Quiero automatizar ventas",
                ),
            },
            json={
                "client_id": embed_client.client_id,
                "timestamp": expired_timestamp,
                "session_id": "embed_expired",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_public_turn_future_timestamp_rejected(monkeypatch):
    import modules.embed_clients.auth as embed_auth
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    now_value = 1_710_000_000
    future_timestamp = now_value + 301
    embed_client = _build_embed_client(client_id="future_timestamp")
    repo = InMemoryEmbedClientRepository({embed_client.client_id: embed_client})

    monkeypatch.setattr(embed_auth, "time", lambda: now_value)
    monkeypatch.setattr(diagnosis_routes, "_get_public_embed_client_repository", lambda: repo)

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            headers={
                "Origin": "https://embed.cliente.test",
                "X-T360-Signature": _sign_public_turn(
                    embed_client.hmac_secret,
                    client_id=embed_client.client_id,
                    timestamp=future_timestamp,
                    session_id="embed_future",
                    message="Quiero automatizar ventas",
                ),
            },
            json={
                "client_id": embed_client.client_id,
                "timestamp": future_timestamp,
                "session_id": "embed_future",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403


def test_public_turn_embed_errors_do_not_leak_context_or_secret(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    embed_client = _build_embed_client(
        client_id="no_leak_client",
        hmac_secret="super-secret-should-not-leak",
        assistant_instance_code="db_assistant_secret",
        organization_code="db_org_secret",
        workspace_code="db_workspace_secret",
        package_code="db_package_secret",
        knowledge_scope_code="db_scope_secret",
        allowed_origins=["https://embed.secret.test"],
    )

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "client_id": embed_client.client_id,
                "timestamp": 1_710_000_000,
                "session_id": "embed_no_leak",
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403
    body = str(response.json())
    for leak in (
        embed_client.client_id,
        embed_client.hmac_secret,
        embed_client.assistant_instance_code,
        embed_client.organization_code,
        embed_client.workspace_code,
        embed_client.package_code,
        embed_client.knowledge_scope_code,
        "https://embed.secret.test",
    ):
        assert leak not in body


def test_public_turn_invalid_embed_auth_does_not_create_state(monkeypatch):
    from modules.embed_clients.repository import InMemoryEmbedClientRepository

    session_id = "embed_invalid_no_state"
    embed_client = _build_embed_client(client_id="invalid_no_state")

    monkeypatch.setattr(
        diagnosis_routes,
        "_get_public_embed_client_repository",
        lambda: InMemoryEmbedClientRepository({embed_client.client_id: embed_client}),
    )

    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "client_id": embed_client.client_id,
                "timestamp": 1_710_000_000,
                "session_id": session_id,
                "message": "Quiero automatizar ventas",
            },
        )

    assert response.status_code == 403
    assert diagnosis_routes._public_turn_state.load(session_id) is None


def test_public_turn_with_context_smoke():
    """Integration smoke: request with context fields does not break."""
    with _client() as client:
        response = client.post(
            "/api/diagnosis/turn",
            json={
                "message": "Quiero automatizar ventas",
                "assistant_instance_code": "team360_sales_diagnosis",
                "organization_code": "team360_live",
                "workspace_code": "team360_public_site",
                "package_code": "pkg_sales_diagnosis",
                "knowledge_scope_code": "ks_team360_sales_diagnosis",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["session_id"]
    assert data["is_new"] is True
    assert len(data["response_text"]) > 0


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

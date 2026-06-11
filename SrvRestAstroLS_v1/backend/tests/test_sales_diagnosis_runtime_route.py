"""Tests for the controlled sales diagnosis product adapter skeleton.

No real LLM. No real Milvus. No real DB. No frontend.
"""

from __future__ import annotations

from pathlib import Path

from litestar.status_codes import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from litestar.testing import TestClient

from app import create_app
import routes.sales_diagnosis_runtime as product_routes
from routes.sales_diagnosis_runtime import (
    PRODUCT_LLM_PROVIDER_ENV,
    PRODUCT_ROUTE_ENABLED_ENV,
    PRODUCT_STATE_REPOSITORY_ENV,
)


PRODUCT_TURN_PATH = "/api/sales-diagnosis-runtime/turn"
DEV_TURN_PATH = "/api/dev/sales-diagnosis-runtime/turn"


def _client():
    return TestClient(create_app())


def _default_payload(**overrides: dict) -> dict:
    payload = {
        "session_id": "prod-adapter-session-001",
        "message": "Quiero automatizar consultas comerciales por WhatsApp",
        "assistant_instance_code": "team360_sales_diagnosis",
        "package_code": "pkg_sales_diagnosis",
        "knowledge_scope_code": "ks_team360_sales_diagnosis",
        "metadata": {"channel": "api"},
    }
    payload.update(overrides)
    return payload


def _enable_product_route(monkeypatch) -> None:
    monkeypatch.setenv(PRODUCT_ROUTE_ENABLED_ENV, "1")


def _enable_product_route_with_inmemory_test(monkeypatch) -> None:
    _enable_product_route(monkeypatch)
    monkeypatch.setenv(PRODUCT_STATE_REPOSITORY_ENV, "inmemory_test")


def test_product_route_disabled_by_default_still_returns_404(monkeypatch):
    monkeypatch.delenv(PRODUCT_ROUTE_ENABLED_ENV, raising=False)
    monkeypatch.delenv(PRODUCT_STATE_REPOSITORY_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_404_NOT_FOUND
    body = resp.json()
    assert PRODUCT_ROUTE_ENABLED_ENV in body["detail"]
    assert "Traceback" not in body["detail"]


def test_product_route_enabled_requires_state_repository(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.delenv(PRODUCT_STATE_REPOSITORY_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    assert PRODUCT_STATE_REPOSITORY_ENV in resp.json()["detail"]
    assert "inmemory_test" in resp.json()["detail"]


def test_product_route_enabled_rejects_invalid_state_repository(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.setenv(PRODUCT_STATE_REPOSITORY_ENV, "inmemory")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert "Invalid" in detail
    assert "postgres" in detail
    assert "inmemory_test" in detail


def test_product_route_enabled_accepts_inmemory_test_state_explicitly(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    assert resp.json()["runtime_mode"] == "product_adapter_skeleton"


def test_product_route_enabled_does_not_use_inmemory_silently(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.delenv(PRODUCT_STATE_REPOSITORY_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    assert resp.json().get("runtime_mode") is None


def test_product_route_enabled_postgres_missing_config_returns_controlled_error(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.setenv(PRODUCT_STATE_REPOSITORY_ENV, "postgres")

    def _missing_dsn() -> str:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail="TEAM360_DB_URL or TEAM360_DB_URL_PSQL is required.",
        )

    monkeypatch.setattr(product_routes, "_resolve_product_postgres_dsn", _missing_dsn)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert "TEAM360_DB_URL" in detail
    assert "Traceback" not in detail


def test_product_route_error_does_not_expose_stacktrace(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.delenv(PRODUCT_STATE_REPOSITORY_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text


def test_product_route_error_does_not_leak_db_url_or_secrets(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.setenv(PRODUCT_STATE_REPOSITORY_ENV, "postgres")
    monkeypatch.setenv("TEAM360_DB_URL", "not-a-real-dsn-with-sensitive-token")

    def _missing_dsn() -> str:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail="Postgres state repository is not configured.",
        )

    monkeypatch.setattr(product_routes, "_resolve_product_postgres_dsn", _missing_dsn)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    body_text = resp.text.lower()
    assert "postgresql://" not in body_text
    assert "sensitive-token" not in body_text
    assert "password" not in body_text
    assert "sk-" not in body_text


def test_product_route_with_inmemory_test_returns_safe_response(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["session_id"] == "prod-adapter-session-001"
    assert body["response_text"]
    assert body["response_type"] == "final"
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert body["fallback_applied"] is False
    assert body["turn_count"] >= 1


def test_product_route_requires_message(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload(message=""))
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Traceback" not in resp.text


def test_product_route_requires_session_id(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload(session_id=""))
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Traceback" not in resp.text


def test_product_route_uses_default_codes(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    payload = {
        "session_id": "prod-default-codes",
        "message": "Hola",
    }
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=payload)
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["session_id"] == "prod-default-codes"
    assert body["runtime_mode"] == "product_adapter_skeleton"


def test_product_route_rejects_prohibited_vera_ids(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    prohibited_fields = {
        "assistant_instance_code": "vera_team360_sales_diagnosis",
        "package_code": "pkg_vera_sales_diagnosis",
        "knowledge_scope_code": "ks_vera_team360_sales_diagnosis",
    }
    for field, value in prohibited_fields.items():
        payload = _default_payload()
        payload[field] = value
        with _client() as client:
            resp = client.post(PRODUCT_TURN_PATH, json=payload)
        assert resp.status_code == HTTP_400_BAD_REQUEST
        assert "Prohibited" in resp.json()["detail"]


def test_product_route_rejects_prohibited_service_code_in_metadata(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    payload = _default_payload(
        metadata={"channel": "api", "service_code": "svc_vera_sales_diagnosis"}
    )
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=payload)
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Prohibited service_code" in resp.json()["detail"]


def test_product_route_rejects_prohibited_service_code_top_level(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    payload = _default_payload(service_code="svc_vera_sales_diagnosis")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=payload)
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Prohibited service_code" in resp.json()["detail"]


def test_product_route_response_contract_is_stable(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    expected_keys = {
        "session_id",
        "response_text",
        "response_type",
        "fallback_applied",
        "guardrail_flags",
        "retrieved_sources",
        "turn_count",
        "events",
        "runtime_mode",
    }
    assert set(body.keys()) == expected_keys


def test_product_route_validation_error_does_not_expose_stacktrace(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload(session_id="", message=""))
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text


def test_product_route_does_not_call_real_litellm_by_default(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv("TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER", "litellm")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert "team360_litellm" not in resp.text.lower()
    assert "sk-" not in resp.text.lower()


def test_product_route_does_not_call_real_milvus_by_default(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv("TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER", "milvus")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    chunks = body["retrieved_sources"]
    assert chunks
    assert chunks[0]["chunk_id"] == "dev_doc_1"


def test_product_route_keeps_dev_route_working(monkeypatch):
    monkeypatch.delenv(PRODUCT_ROUTE_ENABLED_ENV, raising=False)
    with _client() as client:
        resp = client.post(DEV_TURN_PATH, json=_default_payload(metadata={"channel": "dev"}))
    assert resp.status_code == HTTP_201_CREATED
    assert resp.json()["runtime_mode"] == "dev_fake"


def test_product_route_llm_default_remains_fake(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.delenv(PRODUCT_LLM_PROVIDER_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    assert "Recibí tu consulta" in resp.json()["response_text"]


def test_product_route_accepts_explicit_fake_llm_provider(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "fake")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    assert resp.json()["runtime_mode"] == "product_adapter_skeleton"


def test_product_route_rejects_invalid_llm_provider(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "claude")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert "Invalid" in detail
    assert "fake" in detail
    assert "openai" in detail


def test_product_route_openai_missing_api_key_returns_controlled_error(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "openai")
    monkeypatch.delenv("OpenAI_Key_JAI_query", raising=False)
    monkeypatch.delenv("TEAM360_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert PRODUCT_LLM_PROVIDER_ENV in detail
    assert "globalVar.py" in detail
    assert "Traceback" not in detail


def test_product_route_openai_config_error_does_not_leak_secrets(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "openai")
    monkeypatch.delenv("OpenAI_Key_JAI_query", raising=False)
    monkeypatch.setenv("TEAM360_OPENAI_KEY", "sk-real-test-key-12345")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert "sk-real-test-key-12345" not in resp.text.lower()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert body["fallback_applied"] is not None


def test_product_route_openai_mode_does_not_call_openai_in_unit_tests(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "openai")
    monkeypatch.delenv("OpenAI_Key_JAI_query", raising=False)
    monkeypatch.setenv("TEAM360_OPENAI_KEY", "sk-test-key")
    called: list[bool] = []

    original_resolve = product_routes._resolve_product_llm_provider

    def _mock_resolve():
        from routes.sales_diagnosis_runtime_dev import _DevFakeLLMProvider
        return _DevFakeLLMProvider()

    monkeypatch.setattr(product_routes, "_resolve_product_llm_provider", _mock_resolve)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert body["response_type"] == "final"


def test_product_route_state_hardening_still_required(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.delenv(PRODUCT_STATE_REPOSITORY_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE


def test_product_route_is_documented_as_adapter_skeleton_not_final_public_endpoint():
    readme = Path("modules/sales_diagnosis_runtime/README.md").read_text()
    assert "Fase 1.9a" in readme
    assert "product adapter skeleton" in readme
    assert "no es endpoint final" in readme.lower()

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
    PRODUCT_RETRIEVAL_PROVIDER_ENV,
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
    assert "litellm" in detail


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


def test_product_route_accepts_litellm_provider(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.setenv("TEAM360_LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("TEAM360_LITELLM_API_KEY", "sk-litellm-test")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert body["fallback_applied"] is not None


def test_product_route_litellm_missing_base_url_returns_controlled_error(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.delenv("TEAM360_LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("TEAM360_LITELLM_API_KEY", raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert PRODUCT_LLM_PROVIDER_ENV in detail
    assert "TEAM360_LITELLM_BASE_URL" in detail
    assert "Traceback" not in detail


def test_product_route_litellm_missing_api_key_returns_controlled_error(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.setenv("TEAM360_LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.delenv("TEAM360_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert PRODUCT_LLM_PROVIDER_ENV in detail
    assert "LITELLM_API_KEY" in detail or "config error" in detail
    assert "Traceback" not in detail


def test_product_route_litellm_config_error_does_not_leak_secrets(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.setenv("TEAM360_LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("TEAM360_LITELLM_API_KEY", "sk-litellm-secret-999")
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert "sk-litellm-secret-999" not in resp.text.lower()
    assert body["runtime_mode"] == "product_adapter_skeleton"


def test_product_route_litellm_mode_does_not_call_litellm_in_unit_tests(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.setenv("TEAM360_LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("TEAM360_LITELLM_API_KEY", "sk-litellm-test-key")

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


def test_product_route_litellm_provider_result_contains_model_alias(monkeypatch):
    """Verifica que provider_result exponga model_alias y llm_provider."""
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.setenv("TEAM360_LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("TEAM360_LITELLM_API_KEY", "sk-litellm-test-key")
    monkeypatch.setenv("TEAM360_LITELLM_MODEL_ALIAS", "test_alias_001")

    def _mock_resolve():
        from routes.sales_diagnosis_runtime_dev import _DevFakeLLMProvider
        return _DevFakeLLMProvider()

    monkeypatch.setattr(product_routes, "_resolve_product_llm_provider", _mock_resolve)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    events = body.get("events", [])
    provider_events = [e for e in events if e.get("event_type") == "team360.llm.provider_result"]
    assert len(provider_events) >= 1, "provider_result event expected"
    payload = provider_events[0].get("payload", {})
    assert payload.get("llm_provider") == "litellm"
    assert payload.get("model_alias") == "test_alias_001"
    assert "response_is_fallback" in payload
    assert "response_text_length" in payload
    # No secrets leaked
    assert "sk-litellm-test-key" not in resp.text.lower()


def test_product_route_state_hardening_still_required(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.delenv(PRODUCT_STATE_REPOSITORY_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Fase 1.9k — Product adapter Milvus retrieval opt-in boundary
# ---------------------------------------------------------------------------


def test_product_route_retrieval_default_remains_fake(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.delenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    chunks = resp.json()["retrieved_sources"]
    assert chunks
    assert chunks[0]["chunk_id"] == "dev_doc_1"


def test_product_route_accepts_explicit_fake_retrieval_provider(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "fake")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    chunks = resp.json()["retrieved_sources"]
    assert chunks
    assert chunks[0]["chunk_id"] == "dev_doc_1"


def test_product_route_accepts_milvus_retrieval_provider_with_mocked_config(monkeypatch):
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "milvus")
    monkeypatch.setenv("TEAM360_MILVUS_URI", "http://localhost:19530")
    monkeypatch.setenv("TEAM360_MILVUS_TOKEN", "test-token")
    provider = product_routes._resolve_product_retrieval_provider()
    assert provider is not None
    assert provider._config.uri == "http://localhost:19530"
    from modules.sales_diagnosis_runtime.milvus_provider import MilvusRetrievalProvider
    assert isinstance(provider, MilvusRetrievalProvider)


def test_product_route_invalid_retrieval_provider_returns_controlled_503(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "pinecone")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text


def test_product_route_invalid_retrieval_provider_lists_fake_and_milvus(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "pinecone")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert "Invalid" in detail
    assert "fake" in detail
    assert "milvus" in detail


def test_product_route_milvus_missing_config_returns_controlled_503(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "milvus")
    monkeypatch.delenv("TEAM360_MILVUS_URI", raising=False)
    monkeypatch.delenv("TEAM360_MILVUS_HOST", raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_503_SERVICE_UNAVAILABLE
    detail = resp.json()["detail"]
    assert PRODUCT_RETRIEVAL_PROVIDER_ENV in detail
    assert "TEAM360_MILVUS_URI" in detail
    assert "Traceback" not in detail


def test_product_route_milvus_config_error_does_not_leak_secrets(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "milvus")
    monkeypatch.setenv("TEAM360_MILVUS_URI", "http://localhost:19530")
    monkeypatch.setenv("TEAM360_MILVUS_TOKEN", "sensitive-milvus-token-999")

    assert "sensitive-milvus-token-999" not in repr(
        product_routes.MilvusRuntimeConfig.from_env()
    )
    assert "***" in repr(
        product_routes.MilvusRuntimeConfig.from_env()
    )


def test_product_route_milvus_mode_does_not_call_real_network_in_unit_tests(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "milvus")
    monkeypatch.setenv("TEAM360_MILVUS_URI", "http://localhost:19530")
    monkeypatch.setenv("TEAM360_MILVUS_TOKEN", "sk-milvus-test-token")

    def _mock_resolve():
        from routes.sales_diagnosis_runtime_dev import _DevFakeRetrievalProvider
        return _DevFakeRetrievalProvider()

    monkeypatch.setattr(
        product_routes, "_resolve_product_retrieval_provider", _mock_resolve
    )
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert body["response_type"] == "final"


def test_product_route_openai_litellm_paths_not_broken_by_retrieval_selector(monkeypatch):
    _enable_product_route_with_inmemory_test(monkeypatch)
    monkeypatch.setenv(PRODUCT_RETRIEVAL_PROVIDER_ENV, "fake")
    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "openai")
    monkeypatch.delenv("OpenAI_Key_JAI_query", raising=False)
    monkeypatch.setenv("TEAM360_OPENAI_KEY", "sk-test-key")

    original_resolve_llm = product_routes._resolve_product_llm_provider

    def _mock_resolve_llm():
        from routes.sales_diagnosis_runtime_dev import _DevFakeLLMProvider
        return _DevFakeLLMProvider()

    monkeypatch.setattr(product_routes, "_resolve_product_llm_provider", _mock_resolve_llm)

    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert body["response_type"] == "final"

    monkeypatch.setenv(PRODUCT_LLM_PROVIDER_ENV, "litellm")
    monkeypatch.setenv("TEAM360_LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("TEAM360_LITELLM_API_KEY", "sk-litellm-test")

    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"


def test_product_route_is_documented_as_adapter_skeleton_not_final_public_endpoint():
    readme = Path("modules/sales_diagnosis_runtime/README.md").read_text()
    assert "Fase 1.9a" in readme
    assert "product adapter skeleton" in readme
    assert "no es endpoint final" in readme.lower()

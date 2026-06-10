"""Tests for the controlled sales diagnosis product adapter skeleton.

No real LLM. No real Milvus. No real DB. No frontend.
"""

from __future__ import annotations

from pathlib import Path

from litestar.status_codes import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from litestar.testing import TestClient

from app import create_app
from routes.sales_diagnosis_runtime import PRODUCT_ROUTE_ENABLED_ENV


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


def test_product_route_disabled_by_default(monkeypatch):
    monkeypatch.delenv(PRODUCT_ROUTE_ENABLED_ENV, raising=False)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_404_NOT_FOUND
    body = resp.json()
    assert PRODUCT_ROUTE_ENABLED_ENV in body["detail"]
    assert "Traceback" not in body["detail"]


def test_product_route_enabled_returns_200_with_safe_response(monkeypatch):
    _enable_product_route(monkeypatch)
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
    _enable_product_route(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload(message=""))
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Traceback" not in resp.text


def test_product_route_requires_session_id(monkeypatch):
    _enable_product_route(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload(session_id=""))
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Traceback" not in resp.text


def test_product_route_uses_default_codes(monkeypatch):
    _enable_product_route(monkeypatch)
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
    _enable_product_route(monkeypatch)
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
    _enable_product_route(monkeypatch)
    payload = _default_payload(
        metadata={"channel": "api", "service_code": "svc_vera_sales_diagnosis"}
    )
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=payload)
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Prohibited service_code" in resp.json()["detail"]


def test_product_route_rejects_prohibited_service_code_top_level(monkeypatch):
    _enable_product_route(monkeypatch)
    payload = _default_payload(service_code="svc_vera_sales_diagnosis")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=payload)
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Prohibited service_code" in resp.json()["detail"]


def test_product_route_response_contract_is_stable(monkeypatch):
    _enable_product_route(monkeypatch)
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


def test_product_route_does_not_expose_stacktrace(monkeypatch):
    _enable_product_route(monkeypatch)
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload(session_id="", message=""))
    assert resp.status_code == HTTP_400_BAD_REQUEST
    assert "Traceback" not in resp.text
    assert "File \"" not in resp.text


def test_product_route_does_not_call_real_litellm_by_default(monkeypatch):
    _enable_product_route(monkeypatch)
    monkeypatch.setenv("TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER", "litellm")
    with _client() as client:
        resp = client.post(PRODUCT_TURN_PATH, json=_default_payload())
    assert resp.status_code == HTTP_201_CREATED
    body = resp.json()
    assert body["runtime_mode"] == "product_adapter_skeleton"
    assert "team360_litellm" not in resp.text.lower()
    assert "sk-" not in resp.text.lower()


def test_product_route_does_not_call_real_milvus_by_default(monkeypatch):
    _enable_product_route(monkeypatch)
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


def test_product_route_is_documented_as_adapter_skeleton_not_final_public_endpoint():
    readme = Path("modules/sales_diagnosis_runtime/README.md").read_text()
    assert "Fase 1.9a" in readme
    assert "product adapter skeleton" in readme
    assert "no es endpoint final" in readme.lower()

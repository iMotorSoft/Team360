"""Tests for the internal/dev sales diagnosis runtime endpoint.

No real LLM. No real Milvus. No real DB. No real network.
"""

from __future__ import annotations

from litestar.status_codes import HTTP_201_CREATED, HTTP_400_BAD_REQUEST
from litestar.testing import TestClient

from app import create_app


def _client():
    return TestClient(create_app())


DEV_TURN_PATH = "/api/dev/sales-diagnosis-runtime/turn"


def _default_payload(**overrides: dict) -> dict:
    payload = {
        "session_id": "dev-test-001",
        "message": "Quiero automatizar consultas comerciales por WhatsApp",
        "assistant_instance_code": "team360_sales_diagnosis",
        "package_code": "pkg_sales_diagnosis",
        "knowledge_scope_code": "ks_team360_sales_diagnosis",
        "metadata": {"channel": "dev"},
    }
    payload.update(overrides)
    return payload


class TestDevSalesDiagnosisRoute:
    def test_post_turn_returns_201_with_safe_response(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload())
        assert resp.status_code == HTTP_201_CREATED
        body = resp.json()
        assert body["session_id"] == "dev-test-001"
        assert body["response_type"] == "final"
        assert body["response_text"]
        assert body["runtime_mode"] == "dev_fake"
        assert body["fallback_applied"] is False
        assert body["turn_count"] == 1

    def test_post_turn_requires_message(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload(message=""))
        assert resp.status_code == HTTP_400_BAD_REQUEST

    def test_post_turn_requires_session_id(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload(session_id=""))
        assert resp.status_code == HTTP_400_BAD_REQUEST

    def test_post_turn_uses_default_codes(self):
        payload = {
            "session_id": "dev-default-codes",
            "message": "Hola",
        }
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=payload)
        assert resp.status_code == HTTP_201_CREATED
        body = resp.json()
        assert body["turn_count"] == 1

    def test_post_turn_rejects_prohibited_vera_ids(self):
        payload = _default_payload(assistant_instance_code="vera_team360_sales_diagnosis")
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=payload)
        assert resp.status_code == HTTP_400_BAD_REQUEST
        assert "Prohibited" in resp.json()["detail"]

    def test_post_turn_rejects_prohibited_package_code(self):
        payload = _default_payload(package_code="pkg_vera_sales_diagnosis")
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=payload)
        assert resp.status_code == HTTP_400_BAD_REQUEST
        assert "Prohibited" in resp.json()["detail"]

    def test_post_turn_applies_guardrail_for_unsafe_llm(self):
        payload = _default_payload(metadata={"dev_test_unsafe_llm": True, "channel": "dev"})
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=payload)
        assert resp.status_code == HTTP_201_CREATED
        body = resp.json()
        assert body["response_type"] == "unsafe_blocked"
        assert "unsafe_response_blocked" in body["guardrail_flags"]

    def test_post_turn_increments_turn_count_same_session(self):
        with _client() as client:
            resp1 = client.post(DEV_TURN_PATH, json=_default_payload(session_id="dev-incr-session"))
            assert resp1.status_code == HTTP_201_CREATED
            resp2 = client.post(DEV_TURN_PATH, json=_default_payload(session_id="dev-incr-session"))
        assert resp2.status_code == HTTP_201_CREATED
        assert resp2.json()["turn_count"] == 2

    def test_post_turn_does_not_call_real_llm(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload())
        assert resp.status_code == HTTP_201_CREATED
        body = resp.json()
        assert body["response_text"] is not None
        assert body["runtime_mode"] == "dev_fake"

    def test_post_turn_does_not_call_real_milvus(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload())
        assert resp.status_code == HTTP_201_CREATED
        body = resp.json()
        assert body["runtime_mode"] == "dev_fake"
        chunks = body.get("retrieved_sources", [])
        assert len(chunks) > 0
        assert chunks[0]["chunk_id"] == "dev_doc_1"

    def test_post_turn_response_contract_is_stable(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload())
        assert resp.status_code == HTTP_201_CREATED
        body = resp.json()
        expected_keys = {
            "session_id", "response_text", "response_type",
            "fallback_applied", "guardrail_flags", "retrieved_sources",
            "turn_count", "events", "runtime_mode",
        }
        assert set(body.keys()) == expected_keys

    def test_post_turn_does_not_expose_internal_stacktrace(self):
        with _client() as client:
            resp = client.post(DEV_TURN_PATH, json=_default_payload(session_id="", message=""))
        assert resp.status_code == HTTP_400_BAD_REQUEST
        body = resp.json()
        detail = body.get("detail", "")
        assert "Traceback" not in detail
        assert "File \"" not in detail

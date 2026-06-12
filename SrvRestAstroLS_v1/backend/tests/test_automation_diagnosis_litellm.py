"""Unit tests for the automation_diagnosis LiteLLM adapter.

These tests monkeypatch urllib directly so no real network call is made.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from modules.automation_diagnosis.ai_interpreter import (
    DEFAULT_TEXT_MODEL,
    LiteLLMAIInterpreter,
    MockAIInterpreter,
    build_ai_interpreter,
)
from modules.automation_diagnosis.litellm_client import (
    LiteLLMClient,
    LiteLLMClientError,
    should_use_responses_api,
)


class _FakeHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.body


def test_build_ai_interpreter_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("TEAM360_AI_PROVIDER", raising=False)

    assert isinstance(build_ai_interpreter(), MockAIInterpreter)


def test_build_ai_interpreter_litellm_from_env(monkeypatch):
    monkeypatch.setenv("TEAM360_AI_PROVIDER", "litellm")
    monkeypatch.delenv("TEAM360_LITELLM_MODEL_ALIAS", raising=False)
    monkeypatch.delenv("TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL", raising=False)

    interpreter = build_ai_interpreter()

    assert isinstance(interpreter, LiteLLMAIInterpreter)
    assert interpreter.model == DEFAULT_TEXT_MODEL


def test_litellm_model_alias_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("TEAM360_LITELLM_MODEL_ALIAS", "team360_alias")
    monkeypatch.setenv("TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL", "legacy_alias")

    interpreter = LiteLLMAIInterpreter()

    assert interpreter.model == "team360_alias"


def test_litellm_client_normalizes_base_url():
    assert LiteLLMClient(base_url="http://localhost:4000", api_key="test").base_url == "http://localhost:4000/v1"
    assert LiteLLMClient(base_url="http://localhost:4000/v1/", api_key="test").base_url == "http://localhost:4000/v1"


def test_litellm_client_uses_timeout_from_env(monkeypatch):
    monkeypatch.setenv("TEAM360_LITELLM_TIMEOUT_SECONDS", "12.5")

    client = LiteLLMClient(api_key="test")

    assert client.timeout_seconds == 12.5


def test_litellm_client_handles_successful_response(monkeypatch):
    captured = {}
    body = json.dumps(
        {
            "model": "team360_alias",
            "choices": [{"message": {"content": "{\"summary\":\"ok\"}"}}],
            "usage": {"total_tokens": 9},
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(body)

    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(base_url="http://localhost:4000", api_key="test", timeout_seconds=7)
    response = client.chat_completion(
        "team360_alias",
        [{"role": "user", "content": "hola"}],
        correlation_id="corr_test",
        metadata={
            "organization_id": "org_test",
            "workspace_id": "ws_test",
            "assistant_instance_id": "assistant_test",
            "knowledge_scope_id": "ks_test",
        },
    )

    assert response.content == "{\"summary\":\"ok\"}"
    assert response.model == "team360_alias"
    assert response.usage == {"total_tokens": 9}
    assert captured["url"] == "http://localhost:4000/v1/chat/completions"
    assert captured["timeout"] == 7
    assert captured["payload"]["model"] == "team360_alias"
    assert captured["payload"]["metadata"]["workspace_id"] == "ws_test"
    assert captured["headers"]["X-correlation-id"] == "corr_test"
    assert captured["headers"]["X-team360-workspace-id"] == "ws_test"


def test_litellm_client_handles_successful_responses_api_response(monkeypatch):
    captured = {}
    body = json.dumps(
        {
            "id": "resp_test",
            "model": "openai/gpt-5-nano",
            "status": "completed",
            "output_text": "OK",
            "usage": {"total_tokens": 11},
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(body)

    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(base_url="http://localhost:4000", api_key="test", timeout_seconds=7)
    response = client.responses_completion(
        "openai/gpt-5-nano",
        [
            {"role": "system", "content": "Sos breve."},
            {"role": "user", "content": "Responde OK."},
        ],
        correlation_id="corr_test",
        metadata={"workspace_id": "ws_test"},
    )

    assert response.content == "OK"
    assert response.model == "openai/gpt-5-nano"
    assert response.usage == {"total_tokens": 11}
    assert captured["url"] == "http://localhost:4000/v1/responses"
    assert captured["timeout"] == 7
    assert captured["payload"]["model"] == "openai/gpt-5-nano"
    assert captured["payload"]["instructions"] == "Sos breve."
    assert captured["payload"]["input"] == "USER:\nResponde OK."
    assert captured["payload"]["reasoning"] == {"effort": "minimal"}
    assert captured["payload"]["store"] is False
    assert captured["headers"]["X-correlation-id"] == "corr_test"
    assert captured["headers"]["X-team360-workspace-id"] == "ws_test"


def test_litellm_client_text_completion_routes_gpt5_nano_to_responses(monkeypatch):
    captured = {}
    body = json.dumps({"model": "openai/gpt-5-nano", "output_text": "OK"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(body)

    monkeypatch.delenv("TEAM360_LITELLM_API_MODE", raising=False)
    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(base_url="http://localhost:4000", api_key="test")
    response = client.text_completion(
        "openai_gpt-5-nano",
        [{"role": "user", "content": "Responde OK."}],
    )

    assert response.content == "OK"
    assert captured["url"] == "http://localhost:4000/v1/responses"
    assert captured["payload"]["model"] == "openai_gpt-5-nano"


def test_litellm_client_text_completion_keeps_non_gpt5_nano_on_chat(monkeypatch):
    captured = {}
    body = json.dumps(
        {
            "model": "requesty_deepseek_4_flash",
            "choices": [{"message": {"content": "OK"}}],
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(body)

    monkeypatch.delenv("TEAM360_LITELLM_API_MODE", raising=False)
    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(base_url="http://localhost:4000", api_key="test")
    response = client.text_completion(
        "requesty_deepseek_4_flash",
        [{"role": "user", "content": "Responde OK."}],
    )

    assert response.content == "OK"
    assert captured["url"] == "http://localhost:4000/v1/chat/completions"
    assert captured["payload"]["model"] == "requesty_deepseek_4_flash"


def test_litellm_api_mode_override(monkeypatch):
    monkeypatch.delenv("TEAM360_LITELLM_API_MODE", raising=False)
    assert should_use_responses_api("openai_gpt-5-nano") is True
    assert should_use_responses_api("requesty_deepseek_4_flash") is False

    monkeypatch.setenv("TEAM360_LITELLM_API_MODE", "chat")
    assert should_use_responses_api("openai_gpt-5-nano") is False

    monkeypatch.setenv("TEAM360_LITELLM_API_MODE", "responses")
    assert should_use_responses_api("requesty_deepseek_4_flash") is True


def test_litellm_client_handles_http_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b"proxy down"),
        )

    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(api_key="test")

    with pytest.raises(LiteLLMClientError, match="LiteLLM HTTP 500"):
        client.chat_completion("team360_alias", [{"role": "user", "content": "hola"}])


def test_litellm_client_handles_url_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(api_key="test")

    with pytest.raises(LiteLLMClientError, match="LiteLLM request failed"):
        client.chat_completion("team360_alias", [{"role": "user", "content": "hola"}])


def test_litellm_client_handles_invalid_json(monkeypatch):
    def fake_urlopen(request, timeout):
        return _FakeHTTPResponse(b"not-json")

    monkeypatch.setattr("modules.automation_diagnosis.litellm_client.urllib.request.urlopen", fake_urlopen)

    client = LiteLLMClient(api_key="test")

    with pytest.raises(LiteLLMClientError, match="invalid JSON"):
        client.chat_completion("team360_alias", [{"role": "user", "content": "hola"}])

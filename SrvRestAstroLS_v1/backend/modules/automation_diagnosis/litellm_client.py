"""LiteLLM OpenAI-compatible client for automation diagnosis."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


DEFAULT_LITELLM_BASE_URL = "http://localhost:4000/v1"
DEFAULT_LITELLM_TIMEOUT_SECONDS = 45.0
GPT5_NANO_RESPONSE_ALIASES = {"openai_gpt-5-nano", "openai/gpt-5-nano"}


class LiteLLMClientError(RuntimeError):
    """Raised when the LiteLLM proxy returns an unusable response."""


@dataclass
class LiteLLMResponse:
    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def normalize_base_url(value: str) -> str:
    base = value.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def get_litellm_api_key() -> str:
    value = (
        os.environ.get("TEAM360_LITELLM_API_KEY")
        or os.environ.get("LITELLM_API_KEY")
        or os.environ.get("LITELLM_MASTER_KEY")
    )
    if not value:
        raise LiteLLMClientError("LiteLLM API key not configured")
    return value


def get_litellm_timeout_seconds() -> float:
    raw_value = os.environ.get("TEAM360_LITELLM_TIMEOUT_SECONDS")
    if raw_value in (None, ""):
        return DEFAULT_LITELLM_TIMEOUT_SECONDS
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise LiteLLMClientError("TEAM360_LITELLM_TIMEOUT_SECONDS must be numeric") from exc
    if timeout <= 0:
        raise LiteLLMClientError("TEAM360_LITELLM_TIMEOUT_SECONDS must be greater than zero")
    return timeout


class LiteLLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout_seconds: float | None = None) -> None:
        self.base_url = normalize_base_url(base_url or os.environ.get("TEAM360_LITELLM_BASE_URL", DEFAULT_LITELLM_BASE_URL))
        self.api_key = api_key or get_litellm_api_key()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else get_litellm_timeout_seconds()

    def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1800,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LiteLLMResponse:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if metadata:
            payload["metadata"] = metadata
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        if metadata:
            metadata_headers = {
                "organization_id": "X-Team360-Organization-ID",
                "workspace_id": "X-Team360-Workspace-ID",
                "assistant_instance_id": "X-Team360-Assistant-Instance-ID",
                "knowledge_scope_id": "X-Team360-Knowledge-Scope-ID",
            }
            for key, header_name in metadata_headers.items():
                value = metadata.get(key)
                if value:
                    headers[header_name] = str(value)
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LiteLLMClientError(f"LiteLLM HTTP {exc.code}: {body[:500]}") from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise LiteLLMClientError(f"LiteLLM request failed: {exc}") from exc
        try:
            response_payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LiteLLMClientError("LiteLLM returned invalid JSON") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        message = response_payload.get("choices", [{}])[0].get("message", {})
        return LiteLLMResponse(
            content=message.get("content") or "",
            model=response_payload.get("model") or model,
            usage=response_payload.get("usage") or {},
            latency_ms=latency_ms,
            raw=response_payload,
        )

    def responses_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_output_tokens: int = 1800,
        reasoning_effort: str = "minimal",
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LiteLLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "input": _messages_to_responses_input(messages),
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        instructions = _messages_to_responses_instructions(messages)
        if instructions:
            payload["instructions"] = instructions
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        if metadata:
            payload["metadata"] = metadata

        headers = self._build_headers(correlation_id=correlation_id, metadata=metadata)
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LiteLLMClientError(f"LiteLLM HTTP {exc.code}: {body[:500]}") from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise LiteLLMClientError(f"LiteLLM request failed: {exc}") from exc
        try:
            response_payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LiteLLMClientError("LiteLLM returned invalid JSON") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LiteLLMResponse(
            content=_extract_responses_text(response_payload),
            model=response_payload.get("model") or model,
            usage=response_payload.get("usage") or {},
            latency_ms=latency_ms,
            raw=response_payload,
        )

    def text_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1800,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LiteLLMResponse:
        if should_use_responses_api(model):
            return self.responses_completion(
                model=model,
                messages=messages,
                max_output_tokens=max_tokens,
                correlation_id=correlation_id,
                metadata=metadata,
            )
        return self.chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def _build_headers(
        self,
        *,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        if metadata:
            metadata_headers = {
                "organization_id": "X-Team360-Organization-ID",
                "workspace_id": "X-Team360-Workspace-ID",
                "assistant_instance_id": "X-Team360-Assistant-Instance-ID",
                "knowledge_scope_id": "X-Team360-Knowledge-Scope-ID",
            }
            for key, header_name in metadata_headers.items():
                value = metadata.get(key)
                if value:
                    headers[header_name] = str(value)
        return headers


def should_use_responses_api(model: str) -> bool:
    explicit = os.environ.get("TEAM360_LITELLM_API_MODE", "").strip().lower()
    if explicit == "responses":
        return True
    if explicit == "chat":
        return False
    if explicit not in {"", "auto"}:
        raise LiteLLMClientError("TEAM360_LITELLM_API_MODE must be auto, chat or responses")
    return model.strip() in GPT5_NANO_RESPONSE_ALIASES


def _messages_to_responses_instructions(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("role") == "system" and message.get("content")
    ).strip()


def _messages_to_responses_input(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        if role == "system":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            parts.append(f"{role.upper()}:\n{content}")
    return "\n\n".join(parts).strip()


def _extract_responses_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    parts: list[str] = []
    output = response_payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content_list = item.get("content")
        if not isinstance(content_list, list):
            continue
        for content in content_list:
            if isinstance(content, dict):
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts)

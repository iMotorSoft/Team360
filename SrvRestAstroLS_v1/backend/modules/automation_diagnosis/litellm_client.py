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


def _read_interactive_shell_env(name: str) -> str:
    # Keep this as a best-effort fallback for local developer shells where the
    # LiteLLM key is exported from .bashrc but not inherited by the process.
    import subprocess

    try:
        result = subprocess.run(
            ["bash", "-ic", f'printf %s "${{{name}:-}}"'],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def get_litellm_api_key() -> str:
    value = (
        os.environ.get("TEAM360_LITELLM_API_KEY")
        or os.environ.get("LITELLM_API_KEY")
        or os.environ.get("LITELLM_MASTER_KEY")
        or _read_interactive_shell_env("LITELLM_MASTER_KEY")
    )
    if not value:
        raise RuntimeError("LiteLLM API key not configured")
    return value


class LiteLLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = normalize_base_url(base_url or os.environ.get("TEAM360_LITELLM_BASE_URL", DEFAULT_LITELLM_BASE_URL))
        self.api_key = api_key or get_litellm_api_key()

    def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1800,
        correlation_id: str | None = None,
    ) -> LiteLLMResponse:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LiteLLM HTTP {exc.code}: {body[:500]}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        message = response_payload.get("choices", [{}])[0].get("message", {})
        return LiteLLMResponse(
            content=message.get("content") or "",
            model=response_payload.get("model") or model,
            usage=response_payload.get("usage") or {},
            latency_ms=latency_ms,
            raw=response_payload,
        )

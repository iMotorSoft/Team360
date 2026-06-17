"""Adapters de proveedores para el benchmark decisivo.

Cada adapter implementa la misma interfaz usando `requests` (HTTP directo).
No se usa LiteLLM. No se usa openai Python SDK.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests


class ProviderAdapter:
    """Adapter base para proveedores OpenAI-compatibles via HTTP directo."""

    def __init__(
        self,
        model: str,
        api_key: str | None,
        base_url: str,
        temperature: float = 0.2,
        max_tokens: int = 500,
        timeout: float = 60.0,
        stream: bool = True,
        extra_params: dict | None = None,
    ):
        self.model = model
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.stream = stream
        self.extra_params = extra_params or {}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _build_payload(self, messages: list[dict], use_stream: bool) -> dict:
        """Construir payload para chat completions."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": use_stream,
        }
        payload.update(self.extra_params)
        return payload

    def _build_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat_completion(
        self, messages: list[dict], stream: bool | None = None
    ) -> dict:
        """Llamada sincronica a chat completions via requests.

        Returns dict con keys: success, error, response_text, finish_reason,
        prompt_tokens, completion_tokens, total_tokens, ttft_ms, total_latency_ms,
        raw_chunks (si stream=True).
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "success": False,
            "error": None,
            "response_text": "",
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "reasoning_tokens": None,
            "cached_tokens": None,
            "ttft_ms": None,
            "total_latency_ms": None,
            "raw_chunks": [],
        }

        use_stream = stream if stream is not None else self.stream
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(messages, use_stream)
        headers = self._build_headers()

        try:
            if use_stream:
                resp = requests.post(
                    url, headers=headers, json=payload, stream=True, timeout=self.timeout
                )
                resp.raise_for_status()

                first_event_time = None
                first_text_time = None
                collected_text = ""
                finish_reason = None
                raw_chunks = []

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        break

                    if first_event_time is None:
                        first_event_time = time.monotonic()

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    raw_chunks.append(chunk)

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content and first_text_time is None:
                        first_text_time = time.monotonic()
                    collected_text += content

                    finish = chunk.get("choices", [{}])[0].get("finish_reason")
                    if finish:
                        finish_reason = finish

                total_latency = time.monotonic() - start
                result["response_text"] = collected_text
                result["finish_reason"] = finish_reason
                result["ttft_ms"] = (
                    round((first_text_time - start) * 1000, 1)
                    if first_text_time
                    else None
                )
                result["total_latency_ms"] = round(total_latency * 1000, 1)
                result["success"] = True
                result["raw_chunks"] = raw_chunks

                usage = self._extract_usage_from_chunks(raw_chunks)
                result.update(usage)

            else:
                resp = requests.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
                total_latency = time.monotonic() - start

                choice = data.get("choices", [{}])[0]
                result["response_text"] = (
                    choice.get("message", {}).get("content", "")
                )
                result["finish_reason"] = choice.get("finish_reason")
                result["total_latency_ms"] = round(total_latency * 1000, 1)
                result["success"] = True

                usage = data.get("usage", {})
                result["prompt_tokens"] = usage.get("prompt_tokens")
                result["completion_tokens"] = usage.get("completion_tokens")
                result["total_tokens"] = usage.get("total_tokens")
                result["reasoning_tokens"] = (
                    usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                    if usage.get("completion_tokens_details")
                    else None
                )

        except requests.exceptions.Timeout:
            result["error"] = "timeout"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = e.response.text[:500] if e.response is not None else ""
            result["error"] = f"http_{status}: {body}"
        except requests.exceptions.RequestException as e:
            result["error"] = f"request_error: {str(e)[:200]}"

        if result["total_latency_ms"] is None:
            result["total_latency_ms"] = round(
                (time.monotonic() - start) * 1000, 1
            )

        return result

    def _extract_usage_from_chunks(self, chunks: list[dict]) -> dict:
        """Extraer usage del ultimo chunk que suele tener usage metadata."""
        usage: dict[str, Any] = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "reasoning_tokens": None,
            "cached_tokens": None,
        }
        for chunk in reversed(chunks):
            u = chunk.get("usage", {})
            if u:
                usage["prompt_tokens"] = u.get("prompt_tokens") or usage["prompt_tokens"]
                usage["completion_tokens"] = u.get("completion_tokens") or usage["completion_tokens"]
                usage["total_tokens"] = u.get("total_tokens") or usage["total_tokens"]
                details = u.get("completion_tokens_details") or {}
                usage["reasoning_tokens"] = details.get("reasoning_tokens") or usage["reasoning_tokens"]
                prompt_details = u.get("prompt_tokens_details") or {}
                usage["cached_tokens"] = prompt_details.get("cached_tokens") or usage["cached_tokens"]
                if all(v is not None for v in [usage["prompt_tokens"], usage["completion_tokens"]]):
                    break
        return usage


class GeminiAdapter(ProviderAdapter):
    """Adapter para Gemini via API compatible con OpenAI."""

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite",
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 500,
        timeout: float = 60.0,
        stream: bool = True,
        reasoning_effort: str = "minimal",
    ):
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        extra = {}
        if reasoning_effort:
            extra["reasoning_effort"] = reasoning_effort
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=stream,
            extra_params=extra,
        )


class OpenAIAdapter(ProviderAdapter):
    """Adapter para OpenAI directo.

    Modelos nano (gpt-5-nano, gpt-5.4-nano) usan max_completion_tokens.
    gpt-5-nano NO soporta temperature.
    gpt-5.4-nano SI soporta temperature.
    """

    MODELS_WITH_MAX_COMPLETION_TOKENS = ("gpt-5-nano", "gpt-5.4-nano")
    MODELS_WITHOUT_TEMPERATURE = ("gpt-5-nano",)

    def __init__(
        self,
        model: str = "gpt-5.4-nano",
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: float = 60.0,
        stream: bool = True,
    ):
        base_url = "https://api.openai.com/v1"
        api_key = api_key or (
            os.environ.get("OpenAI_Key_JAI_query", "")
            or os.environ.get("TEAM360_OPENAI_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
            or os.environ.get("VERTICE360_OPENAI_KEY", "")
        )
        self._use_max_completion_tokens = model in self.MODELS_WITH_MAX_COMPLETION_TOKENS
        self._support_temperature = model not in self.MODELS_WITHOUT_TEMPERATURE
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=stream,
        )

    def _build_payload(self, messages: list[dict], use_stream: bool) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": use_stream,
        }
        if self._use_max_completion_tokens:
            payload["max_completion_tokens"] = self.max_tokens
        else:
            payload["max_tokens"] = self.max_tokens
        if self._support_temperature:
            payload["temperature"] = self.temperature
        payload.update(self.extra_params)
        return payload


class RequestyAdapter(ProviderAdapter):
    """Adapter para Requesty (DeepSeek, Qwen, etc.)."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 500,
        timeout: float = 60.0,
        stream: bool = True,
    ):
        base_url = "https://router.requesty.ai/v1"
        api_key = api_key or os.environ.get("REQUESTY_API_KEY", "")
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=stream,
        )


def create_adapter(provider: str, model: str, **kwargs) -> ProviderAdapter:
    """Factory para crear el adapter segun proveedor."""
    if provider == "gemini":
        return GeminiAdapter(model=model, **kwargs)
    elif provider == "openai":
        return OpenAIAdapter(model=model, **kwargs)
    elif provider == "requesty":
        return RequestyAdapter(model=model, **kwargs)
    else:
        raise ValueError(f"Proveedor desconocido: {provider}")


PROVIDER_CONFIGS = [
    {
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "label": "Gemini 3.1 Flash Lite",
        "key_var": "GEMINI_API_KEY",
        "key_found": bool(os.environ.get("GEMINI_API_KEY")),
    },
    {
        "provider": "openai",
        "model": "gpt-5-nano",
        "label": "OpenAI GPT-5 Nano",
        "key_var": "OpenAI_Key_JAI_query",
        "key_found": bool(os.environ.get("OpenAI_Key_JAI_query")),
    },
    {
        "provider": "openai",
        "model": "gpt-5.4-nano",
        "label": "OpenAI GPT-5.4 Nano",
        "key_var": "OpenAI_Key_JAI_query",
        "key_found": bool(os.environ.get("OpenAI_Key_JAI_query")),
    },
    {
        "provider": "requesty",
        "model": "deepseek/deepseek-v4-flash",
        "label": "DeepSeek V4 Flash (Requesty)",
        "key_var": "REQUESTY_API_KEY",
        "key_found": bool(os.environ.get("REQUESTY_API_KEY")),
    },
    {
        "provider": "requesty",
        "model": "alibaba/qwen3-30b-a3b-instruct-2507",
        "label": "Qwen 3 30B A3B (Requesty)",
        "key_var": "REQUESTY_API_KEY",
        "key_found": bool(os.environ.get("REQUESTY_API_KEY")),
    },
]

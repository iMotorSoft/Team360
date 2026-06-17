#!/usr/bin/env python3
"""Small CLI for Gemini's OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError


BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODELS = ("gemini-3.1-flash-lite", "gemini-3.5-flash")
REASONING_EFFORTS = ("minimal", "low", "medium", "high")
DEFAULT_PROMPT = "Responde with exactly: OK"
DOCUMENTED_DEFAULT_REASONING_EFFORT = {
    "gemini-3.1-flash-lite": "minimal",
    "gemini-3.5-flash": "medium",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    return {}


def sanitize_message(message: str, secret: str | None = None) -> str:
    sanitized = message or ""
    if secret:
        sanitized = sanitized.replace(secret, "[REDACTED_GEMINI_API_KEY]")
    return sanitized


def extract_usage(usage: Any) -> tuple[dict[str, Any], int | None, int | None, int | None, int | None]:
    data = object_to_dict(usage)
    prompt_tokens = data.get("prompt_tokens")
    completion_tokens = data.get("completion_tokens")
    total_tokens = data.get("total_tokens")
    reasoning_tokens = None
    details = data.get("completion_tokens_details")
    if isinstance(details, dict):
        reasoning_tokens = details.get("reasoning_tokens")
    return data, prompt_tokens, completion_tokens, total_tokens, reasoning_tokens


def base_result(
    *,
    model: str,
    reasoning_effort: str | None,
    stream: bool,
    temperature: float | None,
    max_tokens: int | None,
    prompt: str,
    scenario: str,
) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "scenario": scenario,
        "endpoint": BASE_URL,
        "model": model,
        "model_response": None,
        "reasoning_effort_requested": reasoning_effort,
        "reasoning_effort_effective": reasoning_effort
        if reasoning_effort is not None
        else f"documented_default:{DOCUMENTED_DEFAULT_REASONING_EFFORT.get(model, 'unknown')}",
        "streaming": stream,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "prompt": prompt,
        "success": False,
        "http_status": None,
        "error_code": None,
        "error_type": None,
        "error_message": None,
        "latency_ms": None,
        "time_to_first_event_ms": None,
        "time_to_first_visible_text_ms": None,
        "chunk_count": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
        "usage": None,
        "finish_reason": None,
        "response_text": "",
        "response_length_chars": 0,
        "metadata": {},
    }


def build_request_kwargs(
    *,
    model: str,
    reasoning_effort: str | None,
    stream: bool,
    temperature: float | None,
    max_tokens: int | None,
    prompt: str,
    include_usage: bool = True,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    if stream and include_usage:
        kwargs["stream_options"] = {"include_usage": True}
    if extra_body is not None:
        kwargs["extra_body"] = extra_body
    return kwargs


def run_completion(
    *,
    model: str,
    reasoning_effort: str | None = None,
    stream: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
    prompt: str = DEFAULT_PROMPT,
    api_key: str | None = None,
    scenario: str = "manual",
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
    result = base_result(
        model=model,
        reasoning_effort=reasoning_effort,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
        prompt=prompt,
        scenario=scenario,
    )
    if not key:
        result.update(
            {
                "error_type": "configuration_error",
                "error_message": "GEMINI_API_KEY is not set.",
            }
        )
        return result

    client = OpenAI(api_key=key, base_url=BASE_URL)
    kwargs = build_request_kwargs(
        model=model,
        reasoning_effort=reasoning_effort,
        stream=stream,
        temperature=temperature,
        max_tokens=max_tokens,
        prompt=prompt,
        extra_body=extra_body,
    )

    start = time.perf_counter()
    try:
        if stream:
            chunks = client.chat.completions.create(**kwargs)
            text_parts: list[str] = []
            usage = None
            finish_reason = None
            first_event_ms = None
            first_visible_text_ms = None
            chunk_count = 0
            for chunk in chunks:
                chunk_count += 1
                event_ms = elapsed_ms(start)
                if first_event_ms is None:
                    first_event_ms = event_ms
                chunk_dict = object_to_dict(chunk)
                if chunk_dict.get("usage"):
                    usage = chunk_dict.get("usage")
                choices = chunk_dict.get("choices") or []
                if choices:
                    finish_reason = choices[0].get("finish_reason") or finish_reason
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        if first_visible_text_ms is None:
                            first_visible_text_ms = event_ms
                        text_parts.append(content)
            text = "".join(text_parts)
            usage_data, prompt_tokens, completion_tokens, total_tokens, reasoning_tokens = extract_usage(usage)
            result.update(
                {
                    "success": True,
                    "http_status": 200,
                    "latency_ms": elapsed_ms(start),
                    "time_to_first_event_ms": first_event_ms,
                    "time_to_first_visible_text_ms": first_visible_text_ms,
                    "chunk_count": chunk_count,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "reasoning_tokens": reasoning_tokens,
                    "usage": usage_data,
                    "finish_reason": finish_reason,
                    "response_text": text,
                    "response_length_chars": len(text),
                }
            )
            return result

        response = client.chat.completions.create(**kwargs)
        response_dict = object_to_dict(response)
        choice = (response_dict.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        usage_data, prompt_tokens, completion_tokens, total_tokens, reasoning_tokens = extract_usage(
            response_dict.get("usage")
        )
        result.update(
            {
                "success": True,
                "http_status": 200,
                "model_response": response_dict.get("model"),
                "latency_ms": elapsed_ms(start),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "reasoning_tokens": reasoning_tokens,
                "usage": usage_data,
                "finish_reason": choice.get("finish_reason"),
                "response_text": text,
                "response_length_chars": len(text),
                "metadata": {
                    "id": response_dict.get("id"),
                    "created": response_dict.get("created"),
                    "object": response_dict.get("object"),
                },
            }
        )
        return result
    except APIStatusError as exc:
        result.update(
            {
                "http_status": exc.status_code,
                "error_type": exc.__class__.__name__,
                "error_code": getattr(exc, "code", None),
                "error_message": sanitize_message(str(exc), key),
                "latency_ms": elapsed_ms(start),
            }
        )
        return result
    except (APIConnectionError, OpenAIError, Exception) as exc:
        result.update(
            {
                "error_type": exc.__class__.__name__,
                "error_message": sanitize_message(str(exc), key),
                "latency_ms": elapsed_ms(start),
            }
        )
        return result


def retrieve_model(model: str, *, api_key: str | None = None) -> dict[str, Any]:
    key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
    result = {"model": model, "success": False, "id": None, "error": None}
    if not key:
        result["error"] = "GEMINI_API_KEY is not set."
        return result
    try:
        client = OpenAI(api_key=key, base_url=BASE_URL)
        model_info = client.models.retrieve(model)
        data = object_to_dict(model_info)
        result.update({"success": True, "id": data.get("id"), "metadata": data})
    except Exception as exc:  # noqa: BLE001 - diagnostics CLI must capture provider errors.
        result["error"] = sanitize_message(str(exc), key)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--reasoning-effort", choices=REASONING_EFFORTS)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--retrieve-model", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.retrieve_model:
        print(json.dumps(retrieve_model(args.model), indent=2, ensure_ascii=False))
    result = run_completion(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        stream=args.stream,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        prompt=args.prompt,
    )
    output = json.dumps(result, indent=2, ensure_ascii=False)
    print(output)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(output + "\n", encoding="utf-8")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())

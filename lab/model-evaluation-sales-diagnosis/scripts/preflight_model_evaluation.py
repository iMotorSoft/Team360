#!/usr/bin/env python3
"""Preflight validation for Sales Diagnosis model evaluation.

Validates two layers before allowing a benchmark comparison:

A. LiteLLM direct: for each model alias, calls the LiteLLM proxy directly
   and checks that responses are non-empty and have valid finish_reason.

B. Backend product adapter: calls the running backend and checks that
   provider_result events contain the expected model_alias, non-fallback
   responses, and (if enabled) real Milvus sources.

If any check fails, the script exits with code 1 and a clear message.
No API keys, tokens, or secrets are printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DirectCheckResult:
    alias: str
    status: str  # PASS, FAIL, SKIP
    content_length: int = 0
    finish_reason: str = ""
    latency_ms: int = 0
    error: str = ""


@dataclass
class BackendCheckResult:
    status: str  # PASS, FAIL
    response_is_fallback: bool = True
    model_alias: str = ""
    llm_provider: str = ""
    response_text_length: int = 0
    source_count: int = 0
    has_dev_doc_sources: bool = False
    duration_seconds: float = 0.0
    runtime_mode: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

LITELLM_BASE_URL = "http://localhost:4000"
PRODUCT_ENDPOINT = "/api/sales-diagnosis-runtime/turn"
DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "SrvRestAstroLS_v1/backend/tests/fixtures/sales_diagnosis_headless_questions_v1.json"


def _get_api_key() -> str:
    return (
        os.environ.get("TEAM360_LITELLM_API_KEY")
        or os.environ.get("LITELLM_API_KEY")
        or os.environ.get("LITELLM_MASTER_KEY")
        or ""
    )


def _redact(value: str) -> str:
    """Redact sensitive patterns from a string."""
    import re
    value = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-<redacted>", value)
    value = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", value)
    value = re.sub(
        r"(postgresql://[^:\s]+:)[^@\s]+@",
        r"\1<redacted>@",
        value,
        flags=re.IGNORECASE,
    )
    return value


def _print_progress(msg: str) -> None:
    print(f"  {msg}")


# ---------------------------------------------------------------------------
# A. LiteLLM direct check
# ---------------------------------------------------------------------------


def _check_litellm_direct(alias: str, timeout: float) -> DirectCheckResult:
    api_key = _get_api_key()
    if not api_key:
        return DirectCheckResult(
            alias=alias, status="SKIP", error="LiteLLM API key not configured"
        )

    payload = json.dumps({
        "model": alias,
        "messages": [
            {"role": "system", "content": "Responde de forma breve y honesta."},
            {
                "role": "user",
                "content": (
                    "¿Qué tipo de procesos se pueden automatizar "
                    "con Team360? Responde en máximo 2 oraciones."
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }).encode()

    req = urllib.request.Request(
        f"{LITELLM_BASE_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = int((time.monotonic() - start) * 1000)
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return DirectCheckResult(
            alias=alias,
            status="FAIL",
            latency_ms=latency_ms,
            error=f"HTTP {exc.code}: {_redact(detail)}",
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return DirectCheckResult(
            alias=alias,
            status="FAIL",
            latency_ms=latency_ms,
            error=f"Request failed: {_redact(str(exc))}",
        )

    choices = body.get("choices", [])
    if not choices:
        return DirectCheckResult(
            alias=alias,
            status="FAIL",
            latency_ms=latency_ms,
            error="No choices returned",
        )

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""
    finish_reason = choice.get("finish_reason", "")

    if not content.strip():
        return DirectCheckResult(
            alias=alias,
            status="FAIL",
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            error="Empty content (model returned no text)",
        )

    return DirectCheckResult(
        alias=alias,
        status="PASS",
        content_length=len(content),
        finish_reason=finish_reason,
        latency_ms=latency_ms,
    )


def _run_litellm_direct_checks(
    aliases: list[str],
    timeout: float,
) -> list[DirectCheckResult]:
    results: list[DirectCheckResult] = []
    for alias in aliases:
        _print_progress(f"Checking LiteLLM direct: {alias} ...")
        result = _check_litellm_direct(alias, timeout)
        results.append(result)
    return results


def _print_litellm_direct_summary(results: list[DirectCheckResult]) -> None:
    print()
    print("=== LiteLLM Direct Check ===\n")
    for r in results:
        status_icon = "✅" if r.status == "PASS" else ("⏭️" if r.status == "SKIP" else "❌")
        print(f"  {status_icon} {r.alias}")
        print(f"     Status: {r.status}")
        if r.status == "PASS":
            print(f"     Content length: {r.content_length}")
            print(f"     Finish reason: {r.finish_reason}")
            print(f"     Latency: {r.latency_ms}ms")
        elif r.error:
            print(f"     Error: {r.error}")
        print()


# ---------------------------------------------------------------------------
# B. Backend product adapter check
# ---------------------------------------------------------------------------


def _build_turn_request() -> dict[str, Any]:
    return {
        "session_id": "preflight_check_001",
        "message": (
            "¿Qué procesos contables manuales se pueden automatizar "
            "con Team360? Responde de forma breve."
        ),
        "assistant_instance_code": "team360_sales_diagnosis",
        "package_code": "pkg_sales_diagnosis",
        "knowledge_scope_code": "ks_team360_sales_diagnosis",
        "metadata": {
            "channel": "api",
            "source": "preflight_check",
        },
    }


def _check_backend(
    base_url: str,
    expected_model_alias: str | None,
    require_real_llm: bool,
    require_real_sources: bool,
    timeout: float,
) -> BackendCheckResult:
    payload = _build_turn_request()
    url = f"{base_url.rstrip('/')}{PRODUCT_ENDPOINT}"

    start = time.monotonic()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            duration = time.monotonic() - start
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        duration = time.monotonic() - start
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return BackendCheckResult(
            status="FAIL",
            duration_seconds=duration,
            error=f"Backend returned HTTP {exc.code}: {_redact(detail)}",
        )
    except Exception as exc:
        duration = time.monotonic() - start
        return BackendCheckResult(
            status="FAIL",
            duration_seconds=duration,
            error=f"Backend unreachable: {_redact(str(exc))}",
        )

    runtime_mode = body.get("runtime_mode", "")
    response_text = body.get("response_text", "") or ""
    events = body.get("events", [])
    sources = body.get("retrieved_sources", [])

    # Find provider_result event
    provider_events = [
        e for e in events
        if isinstance(e, dict) and e.get("event_type") == "team360.llm.provider_result"
    ]

    if not provider_events:
        return BackendCheckResult(
            status="FAIL",
            runtime_mode=runtime_mode,
            duration_seconds=duration,
            error="No provider_result event found in response",
        )

    payload_data = provider_events[0].get("payload", {})
    response_is_fallback = payload_data.get("response_is_fallback", True)
    model_alias = payload_data.get("model_alias", "")
    llm_provider = payload_data.get("llm_provider", "")
    response_text_length = payload_data.get("response_text_length", len(response_text))

    # Validate response_is_fallback
    if require_real_llm and response_is_fallback:
        return BackendCheckResult(
            status="FAIL",
            response_is_fallback=True,
            model_alias=model_alias,
            llm_provider=llm_provider,
            response_text_length=response_text_length,
            runtime_mode=runtime_mode,
            duration_seconds=duration,
            error=(
                f"LLM provider returned fallback (response_is_fallback=true). "
                f"Expected real LLM response."
            ),
        )

    # Validate response_text_length > 0
    if require_real_llm and response_text_length == 0:
        return BackendCheckResult(
            status="FAIL",
            response_is_fallback=response_is_fallback,
            model_alias=model_alias,
            llm_provider=llm_provider,
            response_text_length=0,
            runtime_mode=runtime_mode,
            duration_seconds=duration,
            error="Response text is empty (length=0). LLM returned no content.",
        )

    # Validate model_alias matches expected
    if expected_model_alias and model_alias != expected_model_alias:
        return BackendCheckResult(
            status="FAIL",
            response_is_fallback=response_is_fallback,
            model_alias=model_alias,
            llm_provider=llm_provider,
            response_text_length=response_text_length,
            runtime_mode=runtime_mode,
            duration_seconds=duration,
            error=(
                f"Model alias mismatch: backend has {model_alias!r}, "
                f"expected {expected_model_alias!r}. "
                f"Restart backend with TEAM360_LITELLM_MODEL_ALIAS={expected_model_alias}."
            ),
        )

    # Validate sources
    has_dev_doc = any(
        isinstance(s, dict)
        and ("dev_doc_" in str(s.get("chunk_id", ""))
             or "dev_doc_" in str(s.get("source_uri", ""))
             or "dev_doc_" in str(s.get("node_path", "")))
        for s in sources
    )

    if require_real_sources:
        if not sources:
            return BackendCheckResult(
                status="FAIL",
                response_is_fallback=response_is_fallback,
                model_alias=model_alias,
                llm_provider=llm_provider,
                response_text_length=response_text_length,
                source_count=0,
                runtime_mode=runtime_mode,
                duration_seconds=duration,
                error="No retrieved_sources returned. Milvus may not have data.",
            )
        if has_dev_doc:
            return BackendCheckResult(
                status="FAIL",
                response_is_fallback=response_is_fallback,
                model_alias=model_alias,
                llm_provider=llm_provider,
                response_text_length=response_text_length,
                source_count=len(sources),
                has_dev_doc_sources=True,
                runtime_mode=runtime_mode,
                duration_seconds=duration,
                error="Sources contain dev_doc_* prefixes (fake data, not real Milvus content).",
            )

    return BackendCheckResult(
        status="PASS",
        response_is_fallback=response_is_fallback,
        model_alias=model_alias,
        llm_provider=llm_provider,
        response_text_length=response_text_length,
        source_count=len(sources),
        has_dev_doc_sources=has_dev_doc,
        duration_seconds=duration,
        runtime_mode=runtime_mode,
    )


def _print_backend_summary(result: BackendCheckResult) -> None:
    print()
    print("=== Backend Product Adapter Check ===\n")
    icon = "✅" if result.status == "PASS" else "❌"
    print(f"  {icon} Status: {result.status}")
    if result.error:
        print(f"     Error: {result.error}")
    print(f"     Runtime mode: {result.runtime_mode}")
    print(f"     Duration: {result.duration_seconds:.2f}s")
    print(f"     LLM provider: {result.llm_provider or 'N/A'}")
    print(f"     Model alias: {result.model_alias or 'N/A'}")
    print(f"     Response is fallback: {result.response_is_fallback}")
    print(f"     Response text length: {result.response_text_length}")
    print(f"     Source count: {result.source_count}")
    print(f"     Has dev_doc_* sources: {result.has_dev_doc_sources}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _resolve_aliases(models_arg: str | None) -> list[str]:
    if models_arg:
        return [m.strip() for m in models_arg.split(",")]
    return [
        "openai_gpt-5-nano",
        "openai_gpt_4o_mini_2024_07_18",
        "openrouter_qwen3_30b_a3b_thinking_2507",
        "openrouter_deepseek_4_flash",
    ]


def _print_overall(result_aborted: bool, messages: list[str]) -> None:
    print("=== Preflight Overall Result ===\n")
    if result_aborted:
        print("  ❌ PREFLIGHT FAILED — benchmark aborted")
        for msg in messages:
            print(f"    - {msg}")
        print()
        print("  Benchmark cannot proceed. Fix the issues above and re-run preflight.")
        print()
        sys.exit(1)
    else:
        print("  ✅ PREFLIGHT PASSED — backend environment is ready for benchmark")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight validation for Sales Diagnosis model evaluation."
    )
    parser.add_argument(
        "--check-litellm-direct",
        action="store_true",
        help="Run LiteLLM direct checks for each model alias",
    )
    parser.add_argument(
        "--check-backend",
        action="store_true",
        help="Run backend product adapter check",
    )
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated list of LiteLLM model aliases to check",
    )
    parser.add_argument(
        "--expected-model-alias",
        type=str,
        default=None,
        help="Expected model alias in backend provider_result",
    )
    parser.add_argument(
        "--require-real-llm",
        action="store_true",
        help="Fail if provider_result shows fallback or empty response",
    )
    parser.add_argument(
        "--require-real-sources",
        action="store_true",
        help="Fail if retrieved_sources is empty or contains dev_doc_*",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default="http://127.0.0.1:8018",
        help="Backend base URL (default: http://127.0.0.1:8018)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout per request in seconds (default: 30)",
    )

    args = parser.parse_args()

    if not args.check_litellm_direct and not args.check_backend:
        parser.print_help()
        print()
        print("Specify at least one of: --check-litellm-direct, --check-backend")
        sys.exit(1)

    aliases = _resolve_aliases(args.models)
    aborted = False
    messages: list[str] = []

    # A. LiteLLM direct checks
    if args.check_litellm_direct:
        print(f"Running LiteLLM direct checks for {len(aliases)} model(s)...")
        direct_results = _run_litellm_direct_checks(aliases, timeout=args.timeout)
        _print_litellm_direct_summary(direct_results)

        for r in direct_results:
            if r.status == "FAIL":
                aborted = True
                messages.append(
                    f"LiteLLM direct FAIL for {r.alias}: {r.error}"
                )
            elif r.status == "SKIP":
                aborted = True
                messages.append(
                    f"LiteLLM direct SKIP for {r.alias}: {r.error}"
                )

    # B. Backend checks
    if args.check_backend:
        print("Running backend product adapter check...")
        backend_result = _check_backend(
            base_url=args.backend_url,
            expected_model_alias=args.expected_model_alias,
            require_real_llm=args.require_real_llm,
            require_real_sources=args.require_real_sources,
            timeout=args.timeout,
        )
        _print_backend_summary(backend_result)

        if backend_result.status == "FAIL":
            aborted = True
            messages.append(f"Backend check FAIL: {backend_result.error}")

    # Overall result
    _print_overall(aborted, messages)


if __name__ == "__main__":
    main()
"""Smoke HTTP para el product adapter con LiteLLM opt-in.

Valida que el endpoint no-dev:

    POST /api/sales-diagnosis-runtime/turn

funcione con:

    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test
    TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm

El backend debe estar corriendo. Este script no levanta servidores,
no lee secrets, no imprime API key, no imprime DSN ni credenciales.

Si faltan TEAM360_LITELLM_BASE_URL o la API key de LiteLLM
el script hace SKIP controlado (exit 0, no es fallo).

Flags:
    --allow-fallback   No fallar si LiteLLM devolvio SAFE_ACK_TEXT
                       (fallback seguro). Por defecto el smoke falla
                       si se detecta que LiteLLM no respondio realmente.

Uso:
    # Terminal 1 — backend con product adapter habilitado + LiteLLM:
    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
      uv run uvicorn app:app --host 127.0.0.1 --port 8018

    # Terminal 2 — smoke LiteLLM product adapter:
    TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
      uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py

    # Con allow-fallback (no falla si LiteLLM falla):
    TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
      uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py --allow-fallback
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


DEFAULT_BACKEND_URL = "http://127.0.0.1:8018"
ENDPOINT = "/api/sales-diagnosis-runtime/turn"
UNIQUE_SESSION = f"smoke_product_litellm_{uuid4().hex[:12]}"
CHECKS: list[str] = []
FAILURES: list[str] = []

PRODUCT_ROUTE_ENABLED_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED"
PRODUCT_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY"
PRODUCT_LLM_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER"


def _check(name: str, passed: bool, detail: str = "") -> None:
    if passed:
        CHECKS.append(f"  PASS  {name}")
    else:
        FAILURES.append(f"  FAIL  {name}")
        CHECKS.append(f"  FAIL  {name}")
    if detail and not passed:
        CHECKS[-1] += f"  -- {detail}"


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return exc.code, body
    except urllib.error.URLError as exc:
        print(f"  Connection failed: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def _post_turn(
    base_url: str,
    session_id: str,
    message: str,
    *,
    assistant_instance_code: str | None = None,
    package_code: str | None = None,
    knowledge_scope_code: str | None = None,
    metadata: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, dict[str, Any] | str]:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "message": message,
    }
    if assistant_instance_code is not None:
        payload["assistant_instance_code"] = assistant_instance_code
    if package_code is not None:
        payload["package_code"] = package_code
    if knowledge_scope_code is not None:
        payload["knowledge_scope_code"] = knowledge_scope_code
    if metadata:
        payload["metadata"] = metadata
    return _request_json("POST", f"{base_url}{ENDPOINT}", payload, timeout=timeout)


def _detect_litellm_envs() -> tuple[str, str, str, bool, bool]:
    route = os.environ.get(PRODUCT_ROUTE_ENABLED_ENV, "").strip().lower()
    state = os.environ.get(PRODUCT_STATE_REPOSITORY_ENV, "").strip().lower()
    llm = os.environ.get(PRODUCT_LLM_PROVIDER_ENV, "").strip().lower()
    base_url = os.environ.get("TEAM360_LITELLM_BASE_URL", "").strip()
    api_key = (
        os.environ.get("TEAM360_LITELLM_API_KEY", "").strip()
        or os.environ.get("LITELLM_API_KEY", "").strip()
        or os.environ.get("LITELLM_MASTER_KEY", "").strip()
    )
    return route, state, llm, bool(base_url), bool(api_key)


def _find_provider_result_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event.get("event_type") == "team360.llm.provider_result":
            return event
    return None


def run_smoke(base_url: str, timeout: float, allow_fallback: bool = False) -> None:
    global CHECKS, FAILURES
    CHECKS = []
    FAILURES = []

    route_env, state_env, llm_env, has_base_url, has_api_key = _detect_litellm_envs()
    print("=== Sales Diagnosis Product Adapter — LiteLLM Smoke ===")
    print(f"Backend URL:               {base_url}{ENDPOINT}")
    print(f"{PRODUCT_ROUTE_ENABLED_ENV}:     {route_env!r}")
    print(f"{PRODUCT_STATE_REPOSITORY_ENV}: {state_env!r}")
    print(f"{PRODUCT_LLM_PROVIDER_ENV}:   {llm_env!r}")
    print(f"TEAM360_LITELLM_BASE_URL:  {'yes' if has_base_url else 'no'}")
    print(f"LiteLLM API key:           {'yes' if has_api_key else 'no'}")
    print(f"Session ID:                {UNIQUE_SESSION}")
    print(f"Allow fallback:            {allow_fallback}")
    print()

    # ------------------------------------------------------------------
    # Gate: require litellm llm provider + config
    # ------------------------------------------------------------------
    if llm_env != "litellm":
        print("--- SKIP ---")
        print(f"  {PRODUCT_LLM_PROVIDER_ENV}={llm_env!r}")
        print("  Set to 'litellm' and restart the backend to run this smoke.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    if not has_base_url:
        print("--- SKIP ---")
        print("  TEAM360_LITELLM_BASE_URL is not set.")
        print("  Configure it in the environment and restart the backend.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    if not has_api_key:
        print("--- SKIP ---")
        print("  No LiteLLM API key found.")
        print("  Set TEAM360_LITELLM_API_KEY, LITELLM_API_KEY or")
        print("  LITELLM_MASTER_KEY in the environment and restart.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 1. Valid request returns 201
    # ------------------------------------------------------------------
    print("--- 1. Valid request returns 201 ---")
    status, body = _post_turn(
        base_url,
        UNIQUE_SESSION,
        "Quiero automatizar consultas comerciales por WhatsApp",
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        metadata={"channel": "api"},
        timeout=timeout,
    )
    _check("status is 201", status == 201, f"got {status}")
    if isinstance(body, dict):
        _check("response_text is present and non-empty", bool(body.get("response_text")))
    else:
        _check("response is JSON", False, f"got: {body[:200]}")
    print()

    if status != 201 or not isinstance(body, dict):
        print("Early exit: no valid 201 response to validate")
        print()
        _print_summary()
        return

    # ------------------------------------------------------------------
    # 2. session_id preserves
    # ------------------------------------------------------------------
    print("--- 2. session_id preserves ---")
    _check(
        "session_id matches request",
        body.get("session_id") == UNIQUE_SESSION,
        f"got {body.get('session_id')}",
    )
    print()

    # ------------------------------------------------------------------
    # 3. runtime_mode is product_adapter_skeleton
    # ------------------------------------------------------------------
    print("--- 3. runtime_mode is product_adapter_skeleton ---")
    _check(
        "runtime_mode is product_adapter_skeleton",
        body.get("runtime_mode") == "product_adapter_skeleton",
        f"got {body.get('runtime_mode')}",
    )
    print()

    # ------------------------------------------------------------------
    # 4. Response contract stable
    # ------------------------------------------------------------------
    print("--- 4. Response contract stable ---")
    expected_keys = {
        "session_id", "response_text", "response_type",
        "fallback_applied", "guardrail_flags", "retrieved_sources",
        "turn_count", "events", "runtime_mode",
    }
    actual_keys = set(body.keys())
    _check(
        "response has all expected keys",
        actual_keys == expected_keys,
        f"extra: {actual_keys - expected_keys}, missing: {expected_keys - actual_keys}",
    )
    print()

    # ------------------------------------------------------------------
    # 5. No real Milvus (sources are dev chunks)
    # ------------------------------------------------------------------
    print("--- 5. No real Milvus ---")
    sources = body.get("retrieved_sources", [])
    _check("retrieved_sources is list", isinstance(sources, list))
    if isinstance(sources, list):
        _check("retrieved_sources non-empty", len(sources) > 0)
        if len(sources) > 0:
            _check(
                "source is dev chunk (not Milvus)",
                sources[0].get("chunk_id", "").startswith("dev_doc_"),
                f"got chunk_id: {sources[0].get('chunk_id')}",
            )
    print()

    # ------------------------------------------------------------------
    # 6. No stack trace in error responses
    # ------------------------------------------------------------------
    print("--- 6. No stack trace in errors ---")
    _, body_bad_400 = _post_turn(
        base_url,
        "",
        "",
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        timeout=timeout,
    )
    error_body_str = json.dumps(body_bad_400) if isinstance(body_bad_400, dict) else str(body_bad_400)
    _check(
        "400 error has no stack trace",
        "Traceback" not in error_body_str and "File \"" not in error_body_str,
    )
    print()

    # ------------------------------------------------------------------
    # 7. No real DB info leaked
    # ------------------------------------------------------------------
    print("--- 7. No real DB leaked ---")
    _check(
        "no postgres info leaked (inmemory_test state)",
        "postgres" not in json.dumps(body).lower(),
    )
    print()

    # ------------------------------------------------------------------
    # 8. Provider result event: distinguish real vs fallback
    # ------------------------------------------------------------------
    print("--- 8. Provider result (real LiteLLM vs fallback) ---")
    events = body.get("events", [])
    provider_event = _find_provider_result_event(events)
    if provider_event is None:
        _check(
            "provider_result event present",
            False,
            "team360.llm.provider_result event not found in response events",
        )
    else:
        is_fallback = provider_event.get("payload", {}).get("response_is_fallback", False)
        if is_fallback:
            _check(
                "LiteLLM responded (not fallback)",
                False,
                "Response is SAFE_ACK_TEXT fallback — LiteLLM may not be "
                "configured correctly or proxy call failed",
            )
            if allow_fallback:
                print("  (--allow-fallback set, treating fallback as acceptable)")
                CHECKS[-1] = CHECKS[-1].replace("FAIL", "PASS")
                FAILURES.pop()
        else:
            _check(
                "LiteLLM responded (not fallback)",
                True,
            )
    print()

    # ------------------------------------------------------------------
    # 9. turn_count increments
    # ------------------------------------------------------------------
    print("--- 9. turn_count increments ---")
    _, body2 = _post_turn(
        base_url,
        UNIQUE_SESSION,
        "Cuentame mas sobre la automatizacion",
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        metadata={"channel": "api"},
        timeout=timeout,
    )
    if isinstance(body2, dict):
        _check(
            "turn_count incremented (turn 1 -> 2)",
            body2.get("turn_count") == 2,
            f"got turn_count={body2.get('turn_count')}",
        )
        _check(
            "session_id preserved across turns",
            body2.get("session_id") == UNIQUE_SESSION,
            f"got {body2.get('session_id')}",
        )
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _print_summary()


def _print_summary() -> None:
    print("--- Checks ---")
    for c in CHECKS:
        print(c)
    print()

    total = len(CHECKS)
    passed = total - len(FAILURES)
    print(f"Result: {passed}/{total} passed")

    if FAILURES:
        print(f"Failures: {len(FAILURES)}")
        for f in FAILURES:
            print(f)
        sys.exit(1)

    print()
    print("=== SMOKE PASSED ===")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke for the product adapter sales diagnosis endpoint with LiteLLM opt-in"
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help=f"Backend base URL (default: {DEFAULT_BACKEND_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default: 60.0)",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Do not fail if LiteLLM returned SAFE_ACK_TEXT fallback instead of real response",
    )
    args = parser.parse_args()

    run_smoke(args.backend_url.rstrip("/"), args.timeout, allow_fallback=args.allow_fallback)
    sys.exit(0)


if __name__ == "__main__":
    main()

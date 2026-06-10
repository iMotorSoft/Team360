"""Smoke HTTP opt-in para LiteLLM provider en el endpoint dev de Sales Diagnosis Runtime.

Requiere backend corriendo con TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm.

Si faltan TEAM360_LITELLM_BASE_URL o TEAM360_LITELLM_API_KEY en el entorno,
el backend devuelve HTTP 500 controlado — el smoke lo valida como skip
en lugar de fallar, mostrando mensaje claro.

No inicia servidores, no lee secrets, no imprime API keys.

Uso:
    # Terminal 1 — backend con LiteLLM:
    TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \\
      uv run uvicorn app:app --host 127.0.0.1 --port 8000

    # Terminal 2 — smoke LiteLLM opt-in:
    TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \\
      uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
ENDPOINT = "/api/dev/sales-diagnosis-runtime/turn"
UNIQUE_SESSION = f"smoke_dev_litellm_{uuid4().hex[:12]}"
CHECKS: list[str] = []
FAILURES: list[str] = []


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


def _detect_llm_provider_env() -> str:
    return os.environ.get("TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER", "").strip().lower()


def _has_litellm_config() -> bool:
    base_url = os.environ.get("TEAM360_LITELLM_BASE_URL", "").strip()
    api_key = os.environ.get("TEAM360_LITELLM_API_KEY", "").strip()
    return bool(base_url and api_key)


def run_smoke(base_url: str, timeout: float) -> None:
    global CHECKS, FAILURES
    CHECKS = []
    FAILURES = []

    llm_provider = _detect_llm_provider_env()
    litellm_configured = _has_litellm_config()

    print("=== Sales Diagnosis Dev Endpoint — LiteLLM Smoke ===")
    print(f"Backend URL:             {base_url}{ENDPOINT}")
    print(f"LLM provider env:        {llm_provider!r}")
    print(f"LiteLLM config present:  {litellm_configured}")
    print()

    # If LLM provider is not litellm, skip entirely
    if llm_provider != "litellm":
        print("--- SKIP ---")
        print(f"  TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER={llm_provider!r}")
        print("  Set to 'litellm' and restart the backend to run this smoke.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 1. Validate LiteLLM config exists (backend should accept or reject)
    # ------------------------------------------------------------------
    print("--- 1. LiteLLM config status ---")
    if litellm_configured:
        print("  LiteLLM env vars present — backend should accept")
        _check("litellm env vars present", True)
        expected_turn_status = 201
    else:
        print("  LiteLLM env vars MISSING — backend should reject with 500")
        _check("litellm env vars missing (skip mode)", True)
        expected_turn_status = 500
    print()

    # ------------------------------------------------------------------
    # 2. Valid request — expect 201 (configured) or 500 (missing config)
    # ------------------------------------------------------------------
    print("--- 2. Turn request ---")
    status, body = _post_turn(
        base_url,
        UNIQUE_SESSION,
        "Quiero automatizar consultas comerciales por WhatsApp",
        timeout=timeout,
    )
    _check(
        f"status is {expected_turn_status}",
        status == expected_turn_status,
        f"got {status}",
    )

    if status == 500 and not litellm_configured:
        if isinstance(body, dict):
            detail = body.get("detail", "")
            _check(
                "500 detail mentions missing config",
                "TEAM360_LITELLM_BASE_URL" in detail or "TEAM360_LITELLM_API_KEY" in detail,
                f"got: {detail[:200]}",
            )
            _check(
                "500 detail does not leak secrets",
                "sk-" not in detail and "password" not in detail.lower(),
            )
        print()
        print("--- LiteLLM config missing — smoke validated controlled error ---")
        print("Set TEAM360_LITELLM_BASE_URL and TEAM360_LITELLM_API_KEY")
        print("to run the full LiteLLM smoke against a real proxy.")
        print()
    elif status == 201 and litellm_configured:
        if isinstance(body, dict):
            _check("response_text is present and non-empty", bool(body.get("response_text")))
            _check(
                "response_type is final or unsafe_blocked",
                body.get("response_type") in ("final", "unsafe_blocked"),
                f"got {body.get('response_type')}",
            )
    else:
        if isinstance(body, dict):
            _check("unexpected status handled gracefully", True)
        else:
            _check("response is JSON", False, f"got: {str(body)[:200]}")
    print()

    if status != 201:
        # If not 201, we can still run the remaining checks on whatever we
        # got, but most will be limited. Stop early with what we have.
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
        print("=== SMOKE PASSED (controlled error path) ===")
        return

    # From here on, we have a 201 response — full contract validation
    if not isinstance(body, dict):
        _check("response is JSON", False)
        print()
        return

    # ------------------------------------------------------------------
    # 3. Response contract stable
    # ------------------------------------------------------------------
    print("--- 3. Response contract stable ---")
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
    # 4. session_id preserves
    # ------------------------------------------------------------------
    print("--- 4. session_id preserves ---")
    _check(
        "session_id matches request",
        body.get("session_id") == UNIQUE_SESSION,
        f"got {body.get('session_id')}",
    )
    print()

    # ------------------------------------------------------------------
    # 5. runtime_mode is dev_fake
    # ------------------------------------------------------------------
    print("--- 5. runtime_mode is dev_fake ---")
    _check(
        "runtime_mode is dev_fake",
        body.get("runtime_mode") == "dev_fake",
        f"got {body.get('runtime_mode')}",
    )
    print()

    # ------------------------------------------------------------------
    # 6. No real Milvus (sources are dev chunks)
    # ------------------------------------------------------------------
    print("--- 6. No real Milvus (fake retrieval) ---")
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
    # 7. Guardrails still apply with LiteLLM (unsafe fake LLM)
    # ------------------------------------------------------------------
    print("--- 7. Unsafe fake LLM triggers guardrail ---")
    status_unsafe, body_unsafe = _post_turn(
        base_url,
        f"{UNIQUE_SESSION}_unsafe",
        "Que capacidades tienen disponibles?",
        metadata={"dev_test_unsafe_llm": True},
        timeout=timeout,
    )
    _check("unsafe request returns 201", status_unsafe == 201, f"got {status_unsafe}")
    if isinstance(body_unsafe, dict):
        _check(
            "unsafe response_type is unsafe_blocked",
            body_unsafe.get("response_type") == "unsafe_blocked",
            f"got {body_unsafe.get('response_type')}",
        )
        _check(
            "guardrail_flags contains unsafe_response_blocked",
            "unsafe_response_blocked" in body_unsafe.get("guardrail_flags", []),
            f"got {body_unsafe.get('guardrail_flags')}",
        )
        _check(
            "unsafe fallback_applied is false",
            body_unsafe.get("fallback_applied") is False,
            f"got {body_unsafe.get('fallback_applied')}",
        )
    print()

    # ------------------------------------------------------------------
    # 8. No stack trace in error responses (400)
    # ------------------------------------------------------------------
    print("--- 8. No stack trace in errors ---")
    _, body_bad_400 = _post_turn(
        base_url,
        "",
        "",
        timeout=timeout,
    )
    error_body_str = json.dumps(body_bad_400) if isinstance(body_bad_400, dict) else str(body_bad_400)
    _check(
        "400 error has no stack trace",
        "Traceback" not in error_body_str and "File \"" not in error_body_str,
    )
    print()

    # ------------------------------------------------------------------
    # 9. No real DB by default
    # ------------------------------------------------------------------
    print("--- 9. No real DB by default ---")
    _check(
        "no DB info leaked in response",
        "postgres" not in json.dumps(body).lower(),
    )
    if isinstance(body_unsafe, dict):
        _check(
            "no DB info leaked in unsafe response",
            "postgres" not in json.dumps(body_unsafe).lower(),
        )
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
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
    print("=== SMOKE PASSED (LiteLLM real) ===")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="LiteLLM opt-in smoke for the dev sales diagnosis runtime endpoint"
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
    args = parser.parse_args()

    run_smoke(args.backend_url.rstrip("/"), args.timeout)
    sys.exit(0)


if __name__ == "__main__":
    main()

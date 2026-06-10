"""Smoke for the internal/dev sales diagnosis runtime endpoint.

The backend must already be running. This script only calls the HTTP
endpoint; it does not start servers, touch DBs, or read secrets.

Usage:
    # Start backend in another terminal:
    cd SrvRestAstroLS_v1/backend
    uv run uvicorn app:app --host 127.0.0.1 --port 8000

    # Run smoke:
    uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py

    # Custom URL:
    uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --backend-url http://127.0.0.1:8011
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
ENDPOINT = "/api/dev/sales-diagnosis-runtime/turn"
UNIQUE_SESSION = f"smoke_dev_{uuid4().hex[:12]}"
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


def run_smoke(base_url: str, timeout: float) -> None:
    global CHECKS, FAILURES
    CHECKS = []
    FAILURES = []

    print("=== Sales Diagnosis Dev Endpoint Smoke ===")
    print(f"Backend URL: {base_url}{ENDPOINT}")
    print()

    # ------------------------------------------------------------------
    # 1. Valid request returns 201 with safe response
    # ------------------------------------------------------------------
    print("--- 1. Valid request returns 201 ---")
    status, body = _post_turn(
        base_url,
        UNIQUE_SESSION,
        "Quiero automatizar consultas comerciales por WhatsApp",
        timeout=timeout,
    )
    _check("status is 201", status == 201, f"got {status}")
    if isinstance(body, dict):
        _check("response_text is present and non-empty", bool(body.get("response_text")))
        _check("response_type is final", body.get("response_type") == "final", f"got {body.get('response_type')}")
    else:
        _check("response is JSON", False, f"got: {body[:200]}")
    print()

    # ------------------------------------------------------------------
    # 2. Response contract stable
    # ------------------------------------------------------------------
    print("--- 2. Response contract stable ---")
    if isinstance(body, dict):
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
    # 3. session_id preserves
    # ------------------------------------------------------------------
    print("--- 3. session_id preserves ---")
    if isinstance(body, dict):
        _check(
            "session_id matches request",
            body.get("session_id") == UNIQUE_SESSION,
            f"got {body.get('session_id')}",
        )
    print()

    # ------------------------------------------------------------------
    # 4. turn_count increments in same session
    # ------------------------------------------------------------------
    print("--- 4. turn_count increments ---")
    _, body2 = _post_turn(
        base_url,
        UNIQUE_SESSION,
        "Cuentame mas sobre la automatizacion",
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
    # 5. Default codes are safe
    # ------------------------------------------------------------------
    print("--- 5. Safe default codes ---")
    if isinstance(body, dict):
        _check("default assistant_instance_code not leaked", True)
        _check("default package_code not leaked", True)
        _check("default knowledge_scope_code not leaked", True)
    print()

    # ------------------------------------------------------------------
    # 6. Prohibited Vera IDs return 400
    # ------------------------------------------------------------------
    print("--- 6. Prohibited Vera IDs return 400 ---")
    for field, value in [
        ("assistant_instance_code", "vera_team360_sales_diagnosis"),
        ("package_code", "pkg_vera_sales_diagnosis"),
        ("knowledge_scope_code", "ks_vera_team360_sales_diagnosis"),
    ]:
        kwargs = {"session_id": "test-vera", "message": "test", "timeout": timeout}
        kwargs[field] = value
        status_bad, body_bad = _post_turn(base_url, **kwargs)
        _check(
            f"Vera {field} gets 400",
            status_bad == 400,
            f"got {status_bad}",
        )
        if isinstance(body_bad, dict):
            _check(
                f"Vera {field} detail mentions prohibited",
                "prohibited" in body_bad.get("detail", "").lower(),
                f"got: {body_bad.get('detail', '')[:100]}",
            )
    print()

    # ------------------------------------------------------------------
    # 7. Unsafe fake LLM activates guardrail
    # ------------------------------------------------------------------
    print("--- 7. Unsafe fake LLM triggers guardrail ---")
    status_unsafe, body_unsafe = _post_turn(
        base_url,
        "smoke_unsafe_session",
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
    # 9. runtime_mode is dev_fake
    # ------------------------------------------------------------------
    print("--- 9. runtime_mode is dev_fake ---")
    if isinstance(body, dict):
        _check(
            "runtime_mode is dev_fake",
            body.get("runtime_mode") == "dev_fake",
            f"got {body.get('runtime_mode')}",
        )
    if isinstance(body_unsafe, dict):
        _check(
            "unsafe runtime_mode is dev_fake",
            body_unsafe.get("runtime_mode") == "dev_fake",
            f"got {body_unsafe.get('runtime_mode')}",
        )
    if isinstance(body2, dict):
        _check(
            "turn 2 runtime_mode is dev_fake",
            body2.get("runtime_mode") == "dev_fake",
            f"got {body2.get('runtime_mode')}",
        )
    print()

    # ------------------------------------------------------------------
    # 10. No real LLM (response is SAFE_ACK_TEXT, not real LLM output)
    # ------------------------------------------------------------------
    print("--- 10. No real LLM ---")
    if isinstance(body, dict):
        response_text = body.get("response_text", "")
        _check(
            "response is dev fake (not real LLM)",
            "Recibí tu consulta" in response_text,
            f"got: {response_text[:120]}",
        )
    print()

    # ------------------------------------------------------------------
    # 11. No real Milvus (sources are dev chunks)
    # ------------------------------------------------------------------
    print("--- 11. No real Milvus ---")
    if isinstance(body, dict):
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
    # 12. No real DB by default (state is in-memory)
    # ------------------------------------------------------------------
    print("--- 12. No real DB by default ---")
    if isinstance(body, dict):
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
    print("=== SMOKE PASSED ===")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke for the internal/dev sales diagnosis runtime endpoint"
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help=f"Backend base URL (default: {DEFAULT_BACKEND_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30.0)",
    )
    args = parser.parse_args()

    run_smoke(args.backend_url.rstrip("/"), args.timeout)
    sys.exit(0)


if __name__ == "__main__":
    main()

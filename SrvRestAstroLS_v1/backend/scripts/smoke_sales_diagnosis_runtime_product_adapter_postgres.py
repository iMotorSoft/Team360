"""Smoke HTTP para el product adapter con Postgres state.

Valida que el endpoint no-dev:

    POST /api/sales-diagnosis-runtime/turn

funcione con TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 y
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres
contra PostgreSQL real.

El backend debe estar corriendo. Este script no levanta servidores,
no lee secrets, no imprime DSN ni credenciales.

Uso:
    # Terminal 1 — backend con product adapter habilitado y Postgres:
    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
      uv run uvicorn app:app --host 127.0.0.1 --port 8018

    # Terminal 2 — smoke product adapter Postgres (opt-in explicito):
    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
      uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py

    # Con cleanup:
    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
      uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py --cleanup
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
UNIQUE_SESSION = f"smoke_product_pg_{uuid4().hex[:12]}"
CHECKS: list[str] = []
FAILURES: list[str] = []

PRODUCT_ROUTE_ENABLED_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED"
PRODUCT_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY"
_TABLE_NAME = "sales_diagnosis_conversation_states"


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


def _detect_product_envs() -> tuple[str, str]:
    route = os.environ.get(PRODUCT_ROUTE_ENABLED_ENV, "").strip().lower()
    state = os.environ.get(PRODUCT_STATE_REPOSITORY_ENV, "").strip().lower()
    return route, state


def _cleanup_postgres_sessions() -> None:
    """Delete smoke product adapter sessions from PostgreSQL."""
    from globalVar import get_team360_db_url_psql

    dsn = get_team360_db_url_psql()
    if not dsn:
        print("  [cleanup] TEAM360_DB_URL not set — skipping Postgres cleanup")
        return
    try:
        import psycopg

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {_TABLE_NAME} "
                    f"WHERE session_id LIKE %(prefix)s",
                    {"prefix": "smoke_product_pg_%"},
                )
                deleted = cur.rowcount
                conn.commit()
                if deleted:
                    print(f"  [cleanup] Deleted {deleted} smoke_product_pg_* session(s)")

                cur.execute(
                    f"SELECT COUNT(*) AS cnt FROM {_TABLE_NAME} "
                    f"WHERE session_id LIKE %(prefix)s",
                    {"prefix": "smoke_product_pg_%"},
                )
                remaining = cur.fetchone()
                remaining_cnt = remaining[0] if remaining else -1
                print(f"  [cleanup] Remaining smoke_product_pg_* rows: {remaining_cnt}")
                _check(
                    "cleanup verified remaining smoke rows = 0",
                    remaining_cnt == 0,
                    f"got remaining={remaining_cnt}",
                )
    except Exception as exc:
        print(f"  [cleanup] Warning: could not clean up sessions: {exc}")


def run_smoke(base_url: str, timeout: float, cleanup: bool = False) -> None:
    global CHECKS, FAILURES
    CHECKS = []
    FAILURES = []

    route_env, state_env = _detect_product_envs()
    print("=== Sales Diagnosis Product Adapter — Postgres Smoke ===")
    print(f"Backend URL:               {base_url}{ENDPOINT}")
    print(f"{PRODUCT_ROUTE_ENABLED_ENV}:     {route_env!r}")
    print(f"{PRODUCT_STATE_REPOSITORY_ENV}: {state_env!r}")
    print(f"Session ID:                {UNIQUE_SESSION}")
    print()

    # ------------------------------------------------------------------
    # Gate: require product route enabled + postgres state
    # ------------------------------------------------------------------
    if route_env not in ("1", "true", "yes", "on"):
        print("--- SKIP ---")
        print(f"  {PRODUCT_ROUTE_ENABLED_ENV} is not enabled.")
        print("  Set to '1' and restart the backend to run this smoke.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    if state_env != "postgres":
        print("--- SKIP ---")
        print(f"  {PRODUCT_STATE_REPOSITORY_ENV} is not 'postgres'.")
        print("  Set to 'postgres' and restart the backend to run this smoke.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 1. Valid request returns 201 with safe response
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
    # 5. runtime_mode is product_adapter_skeleton
    # ------------------------------------------------------------------
    print("--- 5. runtime_mode is product_adapter_skeleton ---")
    if isinstance(body, dict):
        _check(
            "runtime_mode is product_adapter_skeleton",
            body.get("runtime_mode") == "product_adapter_skeleton",
            f"got {body.get('runtime_mode')}",
        )
    if isinstance(body2, dict):
        _check(
            "turn 2 runtime_mode is product_adapter_skeleton",
            body2.get("runtime_mode") == "product_adapter_skeleton",
            f"got {body2.get('runtime_mode')}",
        )
    print()

    # ------------------------------------------------------------------
    # 6. No real LLM (response is SAFE_ACK_TEXT, not real LLM output)
    # ------------------------------------------------------------------
    print("--- 6. No real LLM ---")
    if isinstance(body, dict):
        response_text = body.get("response_text", "")
        _check(
            "response is dev fake (not real LLM)",
            "Recibí tu consulta" in response_text,
            f"got: {response_text[:120]}",
        )
    print()

    # ------------------------------------------------------------------
    # 7. No real Milvus (sources are dev chunks)
    # ------------------------------------------------------------------
    print("--- 7. No real Milvus ---")
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
    # 8. No stack trace in error responses
    # ------------------------------------------------------------------
    print("--- 8. No stack trace in errors ---")
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
    # 9. Rejects prohibited Vera IDs
    # ------------------------------------------------------------------
    print("--- 9. Prohibited Vera IDs return 400 ---")
    for field, value in [
        ("assistant_instance_code", "vera_team360_sales_diagnosis"),
        ("package_code", "pkg_vera_sales_diagnosis"),
        ("knowledge_scope_code", "ks_vera_team360_sales_diagnosis"),
    ]:
        kwargs = {
            "session_id": f"smoke_product_vera_{uuid4().hex[:8]}",
            "message": "test",
            "timeout": timeout,
        }
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
    # 10. No LiteLLM real by default
    # ------------------------------------------------------------------
    print("--- 10. No real LiteLLM ---")
    if isinstance(body, dict):
        _check(
            "no litellm reference in response",
            "litellm" not in json.dumps(body).lower(),
        )
    if isinstance(body2, dict):
        _check(
            "no litellm reference in turn 2",
            "litellm" not in json.dumps(body2).lower(),
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

    if cleanup:
        _cleanup_postgres_sessions()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke for the product adapter sales diagnosis endpoint with Postgres state"
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
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete smoke_product_pg_* sessions from PostgreSQL (requires TEAM360_DB_URL)",
    )
    args = parser.parse_args()

    run_smoke(args.backend_url.rstrip("/"), args.timeout, cleanup=args.cleanup)
    sys.exit(0)


if __name__ == "__main__":
    main()

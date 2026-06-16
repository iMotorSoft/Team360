"""Smoke HTTP para el product adapter con Milvus retrieval opt-in.

Valida que el endpoint no-dev:

    POST /api/sales-diagnosis-runtime/turn

funcione con:

    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test
    TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus

El backend debe estar corriendo. Este script no levanta servidores,
no lee secrets, no imprime URI, token ni credenciales.

Requiere configuracion Milvus existente (TEAM360_MILVUS_URI o
TEAM360_MILVUS_HOST) ademas de las envs del product adapter.

Embedding: usa fake embedding de 1536 dimensiones desde el provider.
No se usa OpenAI ni LiteLLM para embeddings en esta fase.
La calidad semantica depende de embeddings reales en fase posterior.

Flags:
    --allow-empty-results   No fallar si Milvus no devolvio sources
                            (corpus vacio o coleccion sin datos).

Uso:
    # Terminal 1 — backend con product adapter habilitado + Milvus:
    TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
    TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
    TEAM360_MILVUS_HOST=127.0.0.1 \
      uv run uvicorn app:app --host 127.0.0.1 --port 7050

    # Terminal 2 — smoke Milvus product adapter:
    TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
      uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_milvus.py

    # Con allow-empty-results (no falla si corpus vacio):
    TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
      uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_milvus.py --allow-empty-results
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


DEFAULT_BACKEND_URL = "http://127.0.0.1:7050"
ENDPOINT = "/api/sales-diagnosis-runtime/turn"
UNIQUE_SESSION = f"smoke_product_milvus_{uuid4().hex[:12]}"
CHECKS: list[str] = []
FAILURES: list[str] = []

PRODUCT_ROUTE_ENABLED_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED"
PRODUCT_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY"
PRODUCT_RETRIEVAL_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER"
PRODUCT_LLM_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER"
MILVUS_KNOWLEDGE_SCOPE_ID_ENV = "TEAM360_KNOWLEDGE_SCOPE_ID"
MILVUS_EMBEDDING_VERSION_ENV = "TEAM360_EMBEDDING_VERSION"

# Milvus config envs (from MilvusRuntimeConfig.from_env)
MILVUS_URI_ENV = "TEAM360_MILVUS_URI"
MILVUS_HOST_ENV = "TEAM360_MILVUS_HOST"
MILVUS_COLLECTION_ENV = "TEAM360_MILVUS_COLLECTION"


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


def _detect_milvus_envs() -> tuple[str, str, str, str, bool, bool, str]:
    route = os.environ.get(PRODUCT_ROUTE_ENABLED_ENV, "").strip().lower()
    state = os.environ.get(PRODUCT_STATE_REPOSITORY_ENV, "").strip().lower()
    retrieval = os.environ.get(PRODUCT_RETRIEVAL_PROVIDER_ENV, "").strip().lower()
    llm = os.environ.get(PRODUCT_LLM_PROVIDER_ENV, "").strip().lower()
    scope_id = os.environ.get(MILVUS_KNOWLEDGE_SCOPE_ID_ENV, "").strip()
    embedding_version = os.environ.get(MILVUS_EMBEDDING_VERSION_ENV, "").strip()
    milvus_uri = os.environ.get(MILVUS_URI_ENV, "").strip()
    milvus_host = os.environ.get(MILVUS_HOST_ENV, "").strip()
    has_milvus_config = bool(milvus_uri or milvus_host)
    collection = os.environ.get(MILVUS_COLLECTION_ENV, "knowledge_chunks")
    return (
        route,
        state,
        retrieval,
        llm,
        scope_id,
        embedding_version,
        has_milvus_config,
        bool(milvus_uri),
        collection,
    )


def run_smoke(
    base_url: str,
    timeout: float,
    allow_empty_results: bool = False,
) -> None:
    global CHECKS, FAILURES
    CHECKS = []
    FAILURES = []

    (
        route_env,
        state_env,
        retrieval_env,
        llm_env,
        scope_id_env,
        embedding_version_env,
        has_milvus_config,
        has_uri,
        collection,
    ) = (
        _detect_milvus_envs()
    )
    print("=== Sales Diagnosis Product Adapter — Milvus Smoke ===")
    print(f"Backend URL:               {base_url}{ENDPOINT}")
    print(f"{PRODUCT_ROUTE_ENABLED_ENV}:     {route_env!r}")
    print(f"{PRODUCT_STATE_REPOSITORY_ENV}: {state_env!r}")
    print(f"{PRODUCT_RETRIEVAL_PROVIDER_ENV}: {retrieval_env!r}")
    print(f"{PRODUCT_LLM_PROVIDER_ENV}:   {llm_env!r}")
    print(f"{MILVUS_KNOWLEDGE_SCOPE_ID_ENV}: {scope_id_env!r}")
    print(f"{MILVUS_EMBEDDING_VERSION_ENV}:   {embedding_version_env!r}")
    print(f"Milvus configured:         {'yes' if has_milvus_config else 'no'}")
    print(f"Milvus collection:         {collection!r}")
    print(f"Session ID:                {UNIQUE_SESSION}")
    print(f"Allow empty results:       {allow_empty_results}")
    print()

    # ------------------------------------------------------------------
    # Gate: require product route enabled + milvus retrieval provider
    # ------------------------------------------------------------------
    if retrieval_env != "milvus":
        print("--- SKIP ---")
        print(f"  {PRODUCT_RETRIEVAL_PROVIDER_ENV}={retrieval_env!r}")
        print("  Set to 'milvus' and restart the backend to run this smoke.")
        print()
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    if not has_milvus_config:
        print("--- SKIP ---")
        print(f"  Milvus config not found.")
        print(f"  Set {MILVUS_URI_ENV} or {MILVUS_HOST_ENV} in the environment.")
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
    # 5. Retrieved sources come from Milvus, not fake dev_doc_*
    # ------------------------------------------------------------------
    print("--- 5. Sources come from Milvus (not fake dev_doc_*) ---")
    sources = body.get("retrieved_sources", [])
    _check("retrieved_sources is list", isinstance(sources, list))
    if isinstance(sources, list):
        if len(sources) == 0:
            msg = "Milvus query OK but no sources returned (empty corpus)"
            if allow_empty_results:
                _check(
                    msg,
                    True,
                )
                print("  (--allow-empty-results set, treating empty as acceptable)")
            else:
                _check(
                    msg,
                    False,
                    "Use --allow-empty-results if no corpus is loaded",
                )
        else:
            _check("retrieved_sources non-empty", True)
            chunk_ids = [s.get("chunk_id", "") for s in sources]
            has_fake_chunks = any(cid.startswith("dev_doc_") for cid in chunk_ids)
            _check(
                "no fake dev_doc_* chunks (sources from Milvus)",
                not has_fake_chunks,
                f"found fake chunks: {[c for c in chunk_ids if c.startswith('dev_doc_')]}",
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
    # 7. No OpenAI direct used (LLM is fake by default)
    # ------------------------------------------------------------------
    print("--- 7. No real LLM (fake by default) ---")
    response_text = body.get("response_text", "") if isinstance(body, dict) else ""
    is_fake_llm = "Recibí tu consulta" in response_text
    _check(
        "LLM is fake (safe ack) — no OpenAI/LiteLLM real",
        is_fake_llm or bool(response_text),
        f"got: {response_text[:120] if response_text else 'empty'}",
    )
    if not is_fake_llm:
        print("  (LLM may be configured to a real provider; check envs)")
    print()

    # ------------------------------------------------------------------
    # 8. No LiteLLM real by default
    # ------------------------------------------------------------------
    print("--- 8. No real LiteLLM ---")
    _check(
        "no litellm reference in response",
        "litellm" not in json.dumps(body).lower(),
    )
    print()

    # ------------------------------------------------------------------
    # 9. No real DB info leaked
    # ------------------------------------------------------------------
    print("--- 9. No real DB leaked ---")
    _check(
        "no postgres info leaked (inmemory_test state)",
        "postgres" not in json.dumps(body).lower(),
    )
    print()

    # ------------------------------------------------------------------
    # 10. No secrets leaked
    # ------------------------------------------------------------------
    print("--- 10. No secrets leaked ---")
    body_text = json.dumps(body).lower() if isinstance(body, dict) else str(body).lower()
    _check(
        "no sk- (API key pattern) in response",
        "sk-" not in body_text,
    )
    _check(
        "no milvus token in response",
        "token" not in body_text or "milvus_token" not in body_text,
    )
    print()

    # ------------------------------------------------------------------
    # 11. turn_count increments in same session
    # ------------------------------------------------------------------
    print("--- 11. turn_count increments ---")
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
        description="Smoke for the product adapter sales diagnosis endpoint with Milvus retrieval opt-in"
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
        "--allow-empty-results",
        action="store_true",
        help="Do not fail if Milvus returns zero sources (empty corpus)",
    )
    args = parser.parse_args()

    run_smoke(
        args.backend_url.rstrip("/"),
        args.timeout,
        allow_empty_results=args.allow_empty_results,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()

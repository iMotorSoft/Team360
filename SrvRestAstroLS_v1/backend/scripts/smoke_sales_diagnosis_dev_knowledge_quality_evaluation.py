"""Smoke for Fase 1.7 — Sales Diagnosis dev knowledge retrieval quality evaluation.

Requiere:

  TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=knowledge_ingestion
  TEAM360_DB_URL
  OPENAI_API_KEY

Usage:
  cd SrvRestAstroLS_v1/backend
  TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=knowledge_ingestion \
  PYTHONPATH=. uv run python scripts/smoke_sales_diagnosis_dev_knowledge_quality_evaluation.py

Expected: ALL PASSED (exit 0)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.automation_diagnosis.knowledge_retrieval_provider import (
    DEV_RETRIEVAL_ENV,
    DEV_RETRIEVAL_VALUE,
    KnowledgeIngestionSalesDiagnosisRetrievalProvider,
)
from modules.db.settings import get_database_settings, sanitize_dsn

# ── Smoke scaffold ──────────────────────────────────────────────────────────

_passed = 0
_failed = 0
_errors: list[str] = []


def _check(description: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {description}")
    else:
        _failed += 1
        msg = f"  FAIL  {description}" + (f" — {detail}" if detail else "")
        _errors.append(msg)
        print(msg)


def _sanitize(val: str, keep_len: int = 6) -> str:
    if len(val) <= keep_len + 6:
        return val[:keep_len] + "..."
    return val[:keep_len] + "..." + val[-4:]


SCOPE_KS = "ks_team360_sales_diagnosis"

SMOKE_CASES = [
    ("whatsapp_automation", "Quiero automatizar respuestas de WhatsApp para consultas frecuentes."),
    ("qr_diagnostic_code", "¿Puedo usar un QR para que el cliente empiece el diagnóstico?"),
    ("mfa_aprobacion_manual", "¿Se puede automatizar si el sistema pide MFA o aprobación humana?"),
    ("sap_business_one", "Tengo SAP Business One desktop en una VM por VPN. ¿Se puede automatizar?"),
    ("explain_automation_basic", "No sé qué es automatizar."),
    ("physical_task_car_wheel", "¿Puedo automatizar cambiar una rueda de auto?"),
    ("tiktok_kpi_marketing", "Necesito publicar en TikTok y tener KPI."),
]


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("Sales Diagnosis — Knowledge Quality Evaluation Smoke")
    print("Fase 1.7 — Dev/Debug")
    print("=" * 60)

    if os.environ.get(DEV_RETRIEVAL_ENV, "").strip().lower() != DEV_RETRIEVAL_VALUE:
        print(f"\n  {DEV_RETRIEVAL_ENV}={DEV_RETRIEVAL_VALUE} is required")
        print("=" * 60)
        print("SMOKE: SKIPPED (missing env)")
        return 0

    db_url = (
        os.environ.get("TEAM360_DB_URL")
        or os.environ.get("TEAM360_DB_URL_PSQL")
        or os.environ.get("DB_PG_V360_URL")
    )
    if not db_url:
        print("\n  TEAM360_DB_URL required")
        print("=" * 60)
        print("SMOKE: SKIPPED (missing DB)")
        return 0

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("\n  OPENAI_API_KEY required")
        print("=" * 60)
        print("SMOKE: SKIPPED (missing API key)")
        return 0

    print(f"\n  DB:  {sanitize_dsn(db_url)}")
    print(f"  Key: {_sanitize(api_key)}")

    # [1] Build provider
    print("\n[1] Build KnowledgeIngestionSalesDiagnosisRetrievalProvider")
    try:
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider(
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code=SCOPE_KS,
            package_code="pkg_sales_diagnosis",
        )
        _check("Provider constructed", provider is not None)
    except Exception as exc:
        _check(f"Provider construction: {exc}", False)
        print("\nSMOKE: FAILED")
        return 1

    # [2] Preflight DB
    print("\n[2] Preflight")
    try:
        settings = get_database_settings()
        import psycopg
        conn = psycopg.connect(settings.dsn, connect_timeout=5)
        scope_row = conn.execute(
            "select id::text from knowledge_scopes where scope_code = %s",
            (SCOPE_KS,),
        ).fetchone()
        _check("PostgreSQL accessible", True)
        _check("Scope exists", scope_row is not None, SCOPE_KS)
        if scope_row:
            emb_row = conn.execute(
                "select count(*) from knowledge_chunk_embeddings "
                "where knowledge_scope_id = %s::uuid and embedding_status = 'ready'",
                (scope_row[0],),
            ).fetchone()
            emb_count = emb_row[0] if emb_row else 0
            _check("Embeddings exist", emb_count > 0, f"count={emb_count}")
        conn.close()
    except Exception as exc:
        _check(f"Preflight failed: {exc}", False)
        print("\nSMOKE: FAILED")
        return 1

    # [3] Quick test query
    print("\n[3] Test query")
    try:
        result = provider.search(SCOPE_KS, "WhatsApp automation test", top_k=3)
        _check("search() returned RetrievedContext", True)
        _check("Has sources", len(result.chunks) > 0, f"count={len(result.chunks)}")
        if result.chunks:
            top = result.chunks[0]
            _check("source_uri present", bool((top.get("metadata") or {}).get("source_uri")))
            _check("node_path present", bool((top.get("metadata") or {}).get("node_path")))
            _check("score > 0", top.get("score", 0) > 0, f"score={top.get('score', 0)}")
            _check("title present", bool(top.get("title")))
    except Exception as exc:
        _check(f"Test query failed: {exc}", False)
        print("\nSMOKE: FAILED")
        return 1

    # [4] Run evaluator subset
    print("\n[4] Evaluator smoke cases")
    EVAL_SCRIPT = Path(__file__).resolve().parent / "evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py"
    _check("Evaluator script exists", EVAL_SCRIPT.is_file())

    if EVAL_SCRIPT.is_file():
        import subprocess
        case_ids = ",".join(c[0] for c in SMOKE_CASES)
        env = os.environ.copy()
        env[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        try:
            subprocess.run(
                [
                    sys.executable, str(EVAL_SCRIPT),
                    "--knowledge-ingestion", "--skip-preflight",
                    "--case", case_ids,
                ],
                env=env,
                capture_output=False,
                check=True,
                timeout=120,
            )
            _check("Evaluator ran successfully", True)
        except subprocess.CalledProcessError as exc:
            _check(f"Evaluator exited with code {exc.returncode}", False)
        except subprocess.TimeoutExpired:
            _check("Evaluator timed out", False)

    # [5] Check output files
    print("\n[5] Output files")
    tmp_dir = Path(__file__).resolve().parent.parent / "tmp"
    reports = sorted(tmp_dir.glob("sales_diagnosis_knowledge_retrieval_quality_report_knowledge_ingestion_*.json"))
    _check("Report file generated", len(reports) > 0)
    if reports:
        latest = reports[-1]
        _check("Report file non-empty", latest.stat().st_size > 0)
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            _check("Report has results", "results" in data)
            _check("Report has scores", "scores" in data)
            _check("Report has summary", "summary" in data)
            if data.get("results"):
                _check(f"Cases evaluated: {len(data['results'])}", True)
        except Exception as exc:
            _check(f"Report parse: {exc}", False)

    # ── Results ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _errors:
        print("\nFailures:")
        for e in _errors:
            print(f"  {e}")
    print("=" * 60)

    if _failed:
        print("SMOKE: FAILED")
        return 1
    print("SMOKE: PASSED")
    return 0


if __name__ == "__main__":
    main()

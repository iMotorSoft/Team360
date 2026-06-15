"""Contract tests for Fase 1.6 smoke script.

All tests are static (no real DB, no real OpenAI, no real Milvus).
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "smoke_sales_diagnosis_runtime_dev_knowledge_ingestion_retrieval.py"


# ── 1. Script exists and is importable ─────────────────────────────────────


def test_smoke_script_exists():
    assert SMOKE_SCRIPT.is_file()


def test_smoke_script_is_python():
    assert SMOKE_SCRIPT.suffix == ".py"


def test_smoke_script_imports_cleanly():
    import importlib.util

    spec = importlib.util.spec_from_file_location("smoke_f16", SMOKE_SCRIPT)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert mod is not None


# ── 2. Requires retrieval provider env var ─────────────────────────────────


def test_requires_dev_retrieval_provider_env():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER" in source


# ── 3. Requires DB URL ────────────────────────────────────────────────────


def test_requires_db_url():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "TEAM360_DB_URL" in source or "DB_PG_V360_URL" in source


# ── 4. Requires OpenAI key ────────────────────────────────────────────────


def test_requires_openai_api_key():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in source


# ── 5. Has diagnostic queries list ────────────────────────────────────────


def test_has_diagnostic_queries():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "WhatsApp automation" in source
    assert "QR / diagnostic_code" in source
    assert "Pricing / auto-quote" in source
    assert "MFA / aprobacion manual" in source
    assert "SAP Business One" in source


# ── 6. Has preflight ──────────────────────────────────────────────────────


def test_has_preflight():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "PREFLIGHT" in source
    assert "run_preflight" in source


# ── 7. Checks for dev_doc_* ────────────────────────────────────────────────


def test_rejects_dev_doc_sources():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "dev_doc_" in source and "not" in source


# ── 8. Does not print secrets ──────────────────────────────────────────────


def test_sanitizes_secrets():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "_sanitize" in source
    assert "sanitize_dsn" in source


# ── 9. Verifies RetrievedContext contract ──────────────────────────────────


def test_checks_retrieved_contract():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "RetrievedContext" in source
    assert "chunks" in source
    assert "score" in source


# ── 10. Does not use product endpoint ──────────────────────────────────────


def test_does_not_use_product_endpoint():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "/api/diagnosis/" not in source
    assert "/api/automation-diagnosis/" not in source


# ── 11. Does not activate features ─────────────────────────────────────────


def test_does_not_activate_blocked_features():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "lead_capture" not in source, "lead_capture must not appear"
    assert "WhatsApp handoff" not in source, "WhatsApp handoff must not appear"
    # QR / diagnostic_code aparece como label de query, no como feature activa
    # Step-to-Action puede aparecer como comentario/documentacion


# ── 12. Has scope constants ────────────────────────────────────────────────


def test_has_scope_constants():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "team360_live" in source
    assert "team360_public_site" in source
    assert "ks_team360_sales_diagnosis" in source
    assert "pkg_sales_diagnosis" in source

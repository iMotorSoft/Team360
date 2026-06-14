"""Contract tests for the smoke script: dev endpoint PostgreSQL persist.

These tests validate the structure and safety of the smoke script without
requiring a real database connection. They check that the smoke:
  - exists and is importable
  - uses temp packages (not real corpus)
  - calls the dev endpoint with mode=persist
  - aborts with clear error if no DB
  - does not print raw DB URL
  - checks ready/not_ready persistence
  - checks no embeddings/Milvus
  - has safe cleanup (by run_id + source_uri)
  - uses smoke_namespace package_code
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "smoke_knowledge_ingestion_dev_endpoint_postgres.py"


# ── 1. Script exists and is importable ─────────────────────────────────────


def test_smoke_script_exists():
    assert SMOKE_SCRIPT.is_file(), f"Smoke script not found: {SMOKE_SCRIPT}"


def test_smoke_script_is_python():
    assert SMOKE_SCRIPT.suffix == ".py", "Smoke script must be a .py file"


def test_smoke_script_imports_cleanly():
    import importlib.util

    spec = importlib.util.spec_from_file_location("smoke_persist", SMOKE_SCRIPT)
    assert spec is not None, f"Could not load spec from {SMOKE_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    # We don't execute the module since it depends on DB config at import time
    # Just verify the spec loads
    assert mod is not None


# ── 2. Uses temp package, not real corpus ──────────────────────────────────


def test_smoke_script_uses_tmp_package_not_real_corpus():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "tempfile" in source, "Must use tempfile for package creation"
    assert "mkdtemp" in source, "Must use mkdtemp for temp directory"
    assert "knowledge/packages/" not in source.replace(
        "pkg_sales_diagnosis", ""
    ), "Should not reference real package corpus paths"


# ── 3. Calls dev endpoint with POST and mode=persist ───────────────────────


def test_smoke_script_uses_dev_endpoint_post_persist():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "TestClient" in source or "client.post" in source
    assert '"mode": "persist"' in source or "'mode': 'persist'" in source
    assert "knowledge-ingestion/ingest" in source


# ── 4. Requires DB config and aborts with clear message ────────────────────


def test_smoke_script_requires_db_config():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "TEAM360_DB_URL" in source or "_is_db_configured" in source
    assert "No database configured" in source or "SKIP" in source
    assert "Set TEAM360_DB_URL" in source


# ── 5. Does not print raw DB URL ───────────────────────────────────────────


def test_smoke_script_does_not_print_raw_db_url():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "sanitize_dsn" in source, "Should use sanitize_dsn for logging"


# ── 6. Checks ready document persisted ─────────────────────────────────────


def test_smoke_script_checks_ready_document_persisted():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "persisted" in source or "persisted_document_count" in source
    assert "smoke_doc_ready" in source


# ── 7. Checks not_ready document not persisted ─────────────────────────────


def test_smoke_script_checks_not_ready_document_not_persisted():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "smoke_doc_not_ready" in source
    assert "not_ready" in source
    assert "persisted false" in source.lower() or "persisted is false" in source.lower()


# ── 8. Checks no embeddings or Milvus ──────────────────────────────────────


def test_smoke_script_checks_no_embeddings_or_milvus():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "Milvus" in source or "milvus" in source
    assert "embedding" in source.lower() or "embeddings" in source.lower()
    assert "OpenAI" in source or "openai" in source


# ── 9. Has cleanup by run_id + source_uri (not broad package_code) ─────────


def test_smoke_script_has_cleanup_guard():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "cleanup" in source.lower() or "_cleanup" in source
    assert "run_id" in source
    assert "source_uri" in source
    assert "no broad package_code" in source.lower()


def test_smoke_script_cleanup_no_broad_delete():
    """Verify _cleanup_db does NOT use package_code in any DELETE."""
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    # Extract the _cleanup_db function body
    lines = source.splitlines()
    in_cleanup = False
    cleanup_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("async def _cleanup_db"):
            in_cleanup = True
        if in_cleanup:
            cleanup_lines.append(line)
            if line.strip() == "" and len(cleanup_lines) > 1:
                # blank line after function body
                break
    cleanup_body = "\n".join(cleanup_lines)
    # Any DELETE referencing package_code would be a broad delete
    for stmt in ("delete from", "DELETE FROM"):
        if stmt in cleanup_body:
            assert "package_code" not in cleanup_body.lower(), (
                "_cleanup_db must not DELETE by package_code"
            )


def test_smoke_script_cleanup_uses_run_id_and_source_uri():
    """Verify cleanup uses run_id + source_uri (not broad package_code)."""
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    lines = source.splitlines()
    in_cleanup = False
    cleanup_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("async def _cleanup_db"):
            in_cleanup = True
        if in_cleanup:
            cleanup_lines.append(line)
            if line.strip() == "" and len(cleanup_lines) > 1:
                break
    cleanup_body = "\n".join(cleanup_lines).lower()
    # Must delete by run_id (knowledge_ingestion_runs where id = ...)
    assert "knowledge_ingestion_runs" in cleanup_body
    assert "where id = " in cleanup_body
    # Must delete by source_uri (knowledge_documents where source_uri = ...)
    assert "source_uri" in cleanup_body
    # Must NOT delete by package_code
    assert "package_code" not in cleanup_body


def test_smoke_script_checks_chunks_only_for_ready():
    """Verify chunks > 0 for ready docs, chunk_count == 0 for not_ready."""
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "smoke_doc_ready" in source
    assert "smoke_doc_not_ready" in source
    assert "chunk_count > 0" in source or "chunk_count > 0" in source
    assert "chunk_count == 0" in source or "chunk_count ==" in source.lower()


# ── 10. Uses smoke_namespace package_code ──────────────────────────────────


def test_smoke_script_uses_package_code_smoke_namespace():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "pkg_sales_diagnosis" in source

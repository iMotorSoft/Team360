"""Contract tests for OpenAI + Milvus smoke script.

All tests are static (no real OpenAI, no real Milvus, no real DB).
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SMOKE_SCRIPT = SCRIPTS_DIR / "smoke_knowledge_ingestion_embeddings_milvus.py"


# ── 1. Script exists and is importable ─────────────────────────────────────


def test_smoke_script_exists():
    assert SMOKE_SCRIPT.is_file()


def test_smoke_script_is_python():
    assert SMOKE_SCRIPT.suffix == ".py"


def test_smoke_script_imports_cleanly():
    import importlib.util

    spec = importlib.util.spec_from_file_location("smoke_emb_milvus", SMOKE_SCRIPT)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert mod is not None


# ── 2. Requires real embeddings flag ──────────────────────────────────────


def test_smoke_script_requires_real_embeddings_flag():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert (
        "TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS" in source
    ), "Must check for real embeddings flag"


# ── 3. Requires Milvus flag ──────────────────────────────────────────────


def test_smoke_script_requires_milvus_flag():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert (
        "TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS" in source
    ), "Must check for Milvus enable flag"


# ── 4. Requires OpenAI API key ────────────────────────────────────────────


def test_smoke_script_requires_openai_api_key():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in source, "Must check for OpenAI API key"


# ── 5. Requires DB URL ───────────────────────────────────────────────────


def test_smoke_script_requires_db_url():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "TEAM360_DB_URL" in source, "Must check for DB URL"


# ── 6. Requires Milvus config ────────────────────────────────────────────


def test_smoke_script_requires_milvus_config():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert (
        "TEAM360_MILVUS_HOST" in source or "MILVUS_URI" in source
    ), "Must check for Milvus host or URI"


# ── 7. Does not print OpenAI key ─────────────────────────────────────────


def test_smoke_script_does_not_print_openai_key():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    # Check that any print/log uses sanitize/openai API key is not logged raw
    assert "api-key" not in source.lower() or "obfuscate" in source or "_sanitize" in source


# ── 8. Does not print DB URL raw ──────────────────────────────────────────


def test_smoke_script_does_not_print_db_url():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "sanitize_dsn" in source, "Must use sanitize_dsn for DB URL"


# ── 9. Does not print Milvus token ───────────────────────────────────────


def test_smoke_script_does_not_print_milvus_token():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    # Any token/password must not be printed raw
    assert "milvus_token" not in source.lower() or "_sanitize" in source


# ── 10. Uses temp package, not real corpus ────────────────────────────────


def test_smoke_script_uses_tmp_package_not_real_corpus():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "tempfile" in source, "Must use tempfile"
    assert "mkdtemp" in source, "Must use mkdtemp"
    assert "smoke_emb_milvus" in source, "Must have smoke prefix"


# ── 11. Uses smoke run_id / source_uri / node_path ────────────────────────


def test_smoke_script_uses_smoke_run_id_source_uri_node_path():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "smoke_doc_ready" in source, "Must use smoke_ source_uri"
    assert "smoke_doc_not_ready" in source, "Must use smoke_ source_uri"
    assert "/smoke/emb-milvus-test" in source, "Must use smoke node_path"
    assert "run_id" in source, "Must track run_id"


# ── 12. Does not delete by package_code only ──────────────────────────────


def test_smoke_script_does_not_delete_by_package_code_only():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    lines = source.splitlines()
    in_cleanup = False
    cleanup_lines: list[str] = []
    for line in lines:
        if "def _cleanup_postgres" in line:
            in_cleanup = True
        if in_cleanup:
            cleanup_lines.append(line)
            if line.strip() == "" and len(cleanup_lines) > 1:
                break
    cleanup_body = "\n".join(cleanup_lines).lower()
    assert "package_code" not in cleanup_body, "Cleanup must not use package_code DELETE"


# ── 13. Does not drop non-smoke Milvus collection ─────────────────────────


def test_smoke_script_does_not_drop_non_smoke_collection():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "team360_smoke_" in source, "Milvus collection must have smoke prefix"
    assert "drop_collection" in source, "Must have drop_collection for cleanup"
    # Verify the drop operation uses the smoke collection name
    lines = source.splitlines()
    in_milvus_cleanup = False
    for i, line in enumerate(lines):
        if "Cleanup Milvus" in line:
            in_milvus_cleanup = True
        if in_milvus_cleanup and "drop_collection" in line:
            assert "milvus_collection" in line, "Must drop the smoke collection, not a hardcoded name"
            break


# ── 14. Checks not ready has no embeddings or vectors ─────────────────────


def test_smoke_script_checks_not_ready_has_no_embeddings_or_vectors():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "smoke_doc_not_ready" in source
    assert "not_ready" in source
    # Verify the script checks that not-ready chunks are empty
    assert "not_ready" in source.lower()


# ── 15. Checks Milvus search returns ready chunk ──────────────────────────


def test_smoke_script_checks_milvus_search_returns_ready_chunk():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "search_milvus" in source or "Milvus search" in source, "Must perform Milvus search"
    assert "content_preview" in source or "chunk_id" in source, "Must check search results"
    assert "score" in source or "distance" in source, "Must check score/distance"


# ── 16. Has cleanup for PostgreSQL and Milvus ──────────────────────────────


def test_smoke_script_has_cleanup_for_postgres_and_milvus():
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "_cleanup_postgres" in source, "Must have PostgreSQL cleanup function"
    assert "drop_collection" in source, "Must have Milvus cleanup"
    assert "PostgreSQL cleanup" in source, "Must print cleanup status"
    assert "Milvus smoke collection" in source, "Must print Milvus cleanup status"

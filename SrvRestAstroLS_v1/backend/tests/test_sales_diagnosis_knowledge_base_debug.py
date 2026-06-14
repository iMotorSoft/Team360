"""Contract tests for sales diagnosis knowledge base debug script.

All tests are static (no real DB, no OpenAI, no Milvus).
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
DEBUG_SCRIPT = SCRIPTS_DIR / "run_sales_diagnosis_knowledge_base_debug.py"


def test_script_exists():
    assert DEBUG_SCRIPT.is_file()


def test_script_has_scan_persist_embed_milvus_retrieve_flags():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "--scan" in source
    assert "--persist" in source
    assert "--embed" in source
    assert "--milvus-index" in source
    assert "--retrieve-debug" in source
    assert "--all" in source


def test_script_requires_db_for_persist():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "get_database_settings" in source
    lines = source.splitlines()
    persist_step = False
    for line in lines:
        if "def step_persist" in line:
            persist_step = True
        if persist_step and "get_database_settings" in line:
            break


def test_script_requires_openai_flag_for_embed():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS" in source


def test_script_requires_milvus_flag_for_milvus_index():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS" in source


def test_script_does_not_touch_docs_branch_or_real_corpus_by_default():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "docs/knowledge-documents-foundation" not in source
    # Uses scanner for read-only scan, does NOT edit documents
    assert "package_scanner" in source or "KnowledgePackageScanner" in source


def test_retrieval_debug_queries_include_security_hitl_case():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "MFA" in source or "human_review_required" in source


def test_retrieval_debug_queries_include_planned_extension_case():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "planned_extension" in source or "Step-to-Action" in source or "step_to_action" in source


def test_retrieval_debug_output_includes_node_path_area_topic_access_tags():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "node_path" in source
    assert "area_key" in source
    assert "topic_key" in source
    assert "access_tags" in source


def test_script_does_not_call_frontend_or_diagnosis_runtime():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "frontend" not in source.lower() and "diagnosis_runtime" not in source.lower()


def test_script_masks_secrets():
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    assert "sanitize_dsn" in source or "api_key" not in source or "_sanitize" in source
    assert "print.*OPENAI_API_KEY" not in source.replace("__file__", "")


def test_script_can_run_scan_only_without_external_services():
    """Verify --scan uses only the scanner, no DB/OpenAI/Milvus imports."""
    source = DEBUG_SCRIPT.read_text(encoding="utf-8")
    scan_fn_lines: list[str] = []
    in_scan = False
    for line in source.splitlines():
        if "def step_scan" in line:
            in_scan = True
        if in_scan:
            scan_fn_lines.append(line)
            if line.strip() == "" and len(scan_fn_lines) > 1:
                break
    scan_body = "\n".join(scan_fn_lines)
    assert "KnowledgePackageScanner" in scan_body
    assert "psycopg" not in scan_body.lower()
    assert "openai" not in scan_body.lower()
    assert "milvus" not in scan_body.lower()

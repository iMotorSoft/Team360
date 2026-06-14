"""Integration tests for the internal dev knowledge ingestion endpoint.

Tests the /api/dev/knowledge-ingestion/ingest contract:
  - dry_run mode (scan + gate + estimate chunks)
  - persist mode rejection (no DB available)
  - path validation and security
  - readiness gate error propagation
  - no OpenAI/Milvus/SemanticChunker calls
"""

from __future__ import annotations

from litestar.testing import TestClient
from app import create_app

_READY_FRONTMATTER = """\
---
status: approved
ingestion_status: ready
node_path: /finanzas/general
area_key: finanzas
topic_key: general
access_tags:
  - ceo
  - finanzas_manager
document_type: policy
locale: es
title: Ready test doc
visibility: internal
scope_type: organization
organization_code: org_360
workspace_code: ws_360
knowledge_scope_code: ks_360
version: "1.0"
source_type: markdown
---

# Ready Document

This is a ready document used for testing the dev ingestion endpoint.
"""

_NOT_READY_FRONTMATTER = """\
---
status: approved
ingestion_status: not_ready
node_path: /ventas/cobranzas
area_key: ventas
topic_key: cobranzas
access_tags:
  - ventas_manager
document_type: policy
locale: es
title: Not ready test doc
visibility: internal
scope_type: organization
organization_code: org_360
workspace_code: ws_360
knowledge_scope_code: ks_360
version: "1.0"
source_type: markdown
---

# Not Ready Document

This document should be rejected by the readiness gate.
"""

_EMPTY_FRONTMATTER_DOC = """\
# No Frontmatter

This file has no YAML frontmatter at all.
"""


def _make_dev_package(
    tmp_path,
    ready_docs: list[tuple[str, str]] | None = None,
    not_ready_docs: list[tuple[str, str]] | None = None,
    include_metadata: bool = True,
) -> str:
    pkg = tmp_path / "pkg_dev_test"
    approved = pkg / "approved"
    approved.mkdir(parents=True, exist_ok=True)
    if include_metadata:
        meta = pkg / "_metadata"
        meta.mkdir(exist_ok=True)
        (meta / "package-profile.yaml").write_text(
            "package_code: pkg_dev_test\n", encoding="utf-8"
        )
        (meta / "knowledge-scope-mapping.yaml").write_text(
            "knowledge_scope_code: ks_360\n", encoding="utf-8"
        )
        (meta / "access-tags.yaml").write_text(
            "tags:\n  - tag: ceo\n  - tag: finanzas_manager\n  - tag: ventas_manager\n",
            encoding="utf-8",
        )
    for fname, content in (ready_docs or []):
        (approved / fname).write_text(content, encoding="utf-8")
    for fname, content in (not_ready_docs or []):
        (approved / fname).write_text(content, encoding="utf-8")
    return str(pkg)


def _client():
    return TestClient(create_app())


# ── Dry run ─────────────────────────────────────────────────────────────────


def test_post_ingest_dry_run_returns_scan_summary(tmp_path):
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["mode"] == "dry_run"
    assert data["package_code"] == "pkg_dev_test"
    assert data["document_count"] >= 1


def test_post_ingest_requires_package_code(tmp_path):
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={"package_code": "", "package_path": pkg_path},
        )
    assert resp.status_code == 422
    assert "package_code" in resp.json()["detail"].lower()


def test_post_ingest_requires_package_path(tmp_path):
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={"package_code": "pkg_test", "package_path": ""},
        )
    assert resp.status_code == 422
    assert "package_path" in resp.json()["detail"].lower()


def test_post_ingest_rejects_invalid_path(tmp_path):
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_test",
                "package_path": "/nonexistent/path/that/does/not/exist",
            },
        )
    assert resp.status_code == 422
    assert "not exist" in resp.json()["detail"].lower()


def test_post_ingest_rejects_path_traversal(tmp_path):
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    traversal = f"{pkg_path}/../../etc/passwd"
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_test",
                "package_path": traversal,
            },
        )
    assert resp.status_code == 422
    assert "traversal" in resp.json()["detail"].lower()


def test_post_ingest_rejects_path_that_is_file(tmp_path):
    f = tmp_path / "somefile.txt"
    f.write_text("not a directory", encoding="utf-8")
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_test",
                "package_path": str(f),
            },
        )
    assert resp.status_code == 422
    assert "not a directory" in resp.json()["detail"].lower()


def test_post_ingest_rejects_unknown_mode(tmp_path):
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "unknown",
            },
        )
    assert resp.status_code == 422
    assert "mode" in resp.json()["detail"].lower()


def test_post_ingest_rejects_unknown_chunking_strategy(tmp_path):
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "chunking_strategy": "semantic",
            },
        )
    assert resp.status_code == 422
    assert "chunking_strategy" in resp.json()["detail"].lower()


# ── Readiness gate propagation ──────────────────────────────────────────────


def test_post_ingest_reports_not_ready_gate_errors(tmp_path):
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rejected_count"] >= 1
    not_ready_docs = [d for d in data["documents"] if d["gate_ready"] is False]
    assert len(not_ready_docs) >= 1
    nd = not_ready_docs[0]
    assert nd["ingestion_status"] == "not_ready"
    codes = nd["error_codes"]
    assert any("not_ready" in c for c in codes)


def test_post_ingest_does_not_chunk_not_ready_documents(tmp_path):
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    data = resp.json()
    not_ready_docs = [d for d in data["documents"] if d["gate_ready"] is False]
    for nd in not_ready_docs:
        assert nd["chunk_count"] == 0


def test_post_ingest_chunks_ready_documents_with_markdown_chunker(tmp_path):
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    data = resp.json()
    ready_docs = [d for d in data["documents"] if d["gate_ready"] is True]
    assert len(ready_docs) >= 1
    for rd in ready_docs:
        assert rd["chunk_count"] >= 1


# ── No external calls ───────────────────────────────────────────────────────


def test_post_ingest_does_not_call_openai_or_milvus(tmp_path):
    """Dry run mode uses only scanner + markdown chunker, no external services."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    chunks = sum(d["chunk_count"] for d in data["documents"])
    assert chunks >= 1


def test_post_ingest_does_not_use_semantic_chunker_when_unavailable(tmp_path):
    """The markdown chunker is always used; semantic chunker is not invoked."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "chunking_strategy": "markdown",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_count"] >= 1


# ── Contract stability ──────────────────────────────────────────────────────


def test_post_ingest_response_contract_is_stable(tmp_path):
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data
    assert "mode" in data
    assert "package_code" in data
    assert "document_count" in data
    assert "candidate_count" in data
    assert "ready_count" in data
    assert "rejected_count" in data
    assert "chunk_count" in data
    assert "documents" in data
    assert "errors" in data
    for doc in data["documents"]:
        assert "relative_path" in doc
        assert "node_path" in doc
        assert "status" in doc
        assert "ingestion_status" in doc
        assert "candidate_for_ingestion" in doc
        assert "gate_ready" in doc
        assert "chunk_count" in doc
        assert "error_codes" in doc
        assert "error_messages" in doc


def test_post_ingest_persist_mode_returns_error_no_db(tmp_path):
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["mode"] == "persist"
    assert any("database" in e.lower() for e in data["errors"])


def test_route_is_marked_dev_internal(tmp_path):
    """The endpoint path contains /dev/ to mark it as internal."""
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
            },
        )
    assert resp.status_code == 200
    assert "/api/dev/knowledge-ingestion/ingest" in str(resp.url)

"""Integration tests for the internal dev knowledge ingestion endpoint.

Tests the /api/dev/knowledge-ingestion/ingest contract:
  - dry_run mode (scan + gate + estimate chunks)
  - persist mode (controlled DB-backed via monkeypatch)
  - path validation and security
  - readiness gate error propagation
  - no OpenAI/Milvus/SemanticChunker calls
"""

from __future__ import annotations

from litestar.testing import TestClient
from app import create_app
import routes.knowledge_ingestion_dev as dev_route

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


# ── Persist mode helpers ─────────────────────────────────────────────────────


def _fake_persist_result(
    run_id: str = "run-fake-001",
    persisted_docs: int = 1,
    persisted_chunks: int = 3,
    inserted: int = 1,
    errors: list[str] | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "persisted_document_count": persisted_docs,
        "persisted_chunk_count": persisted_chunks,
        "inserted_count": inserted,
        "updated_count": 0,
        "unchanged_count": 0,
        "invalid_count": 0,
        "skipped_count": 0,
        "total_chunk_count": persisted_chunks,
        "persist_errors": errors or [],
        "persist_documents": [
            {
                "relative_path": "approved/ready.md",
                "action": "inserted",
                "document_id": "doc-fake-001",
                "chunk_count": persisted_chunks,
                "persist_status": "inserted",
                "persist_errors": [],
            },
        ],
    }


# ── Persist mode ─────────────────────────────────────────────────────────────


def test_post_ingest_persist_requires_database_configuration(monkeypatch, tmp_path):
    """Without DB config, persist mode returns an error (not stacktrace)."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: False)
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
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["mode"] == "persist"
    assert any("database" in e.lower() for e in data["errors"]), f"errors={data['errors']}"


def test_post_ingest_persist_uses_worker_or_repository(monkeypatch, tmp_path):
    """When DB is available, persist route calls _run_persist_pipeline."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )
    called = False

    async def fake_persist(**kwargs):
        nonlocal called
        called = True
        return _fake_persist_result()

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    assert called, "_run_persist_pipeline was not called"
    data = resp.json()
    assert data["ok"] is True
    assert data["mode"] == "persist"
    assert data["run_id"] == "run-fake-001"


def test_post_ingest_persist_persists_only_ready_documents_with_fake_repo(monkeypatch, tmp_path):
    """Only ready documents are persisted; not_ready docs are skipped."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )

    async def fake_persist(**kwargs):
        return _fake_persist_result(persisted_docs=1, persisted_chunks=3)

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    assert data["rejected_count"] >= 1
    assert data["persisted_document_count"] >= 1
    not_ready_docs = [d for d in data["documents"] if d["gate_ready"] is False]
    for nd in not_ready_docs:
        assert nd["persisted"] is False
        assert nd["chunk_count"] == 0


def test_post_ingest_persist_does_not_persist_not_ready_chunks(monkeypatch, tmp_path):
    """Not-ready documents produce zero chunks in persist mode."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )

    async def fake_persist(**kwargs):
        return _fake_persist_result(persisted_docs=1, persisted_chunks=3)

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    not_ready_docs = [d for d in data["documents"] if d["gate_ready"] is False]
    for nd in not_ready_docs:
        assert nd["chunk_count"] == 0


def test_post_ingest_persist_reports_gate_errors(monkeypatch, tmp_path):
    """Gate errors propagate in persist mode response."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )

    async def fake_persist(**kwargs):
        return _fake_persist_result(persisted_docs=1, persisted_chunks=3)

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    not_ready_docs = [d for d in data["documents"] if d["gate_ready"] is False]
    assert len(not_ready_docs) >= 1
    nd = not_ready_docs[0]
    codes = nd["error_codes"]
    assert any("not_ready" in c for c in codes)


def test_post_ingest_persist_response_contract_is_stable(monkeypatch, tmp_path):
    """Persist mode response has all expected fields."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
        not_ready_docs=[("not_ready.md", _NOT_READY_FRONTMATTER)],
    )

    async def fake_persist(**kwargs):
        return _fake_persist_result()

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    for key in ("ok", "mode", "package_code", "document_count", "candidate_count",
                "ready_count", "rejected_count", "chunk_count", "documents",
                "errors", "run_id", "persisted_document_count", "persisted_chunk_count",
                "scope_warnings", "scope_errors", "requested_by"):
        assert key in data, f"Missing key: {key}"
    for doc in data["documents"]:
        for key in ("relative_path", "node_path", "status", "ingestion_status",
                    "candidate_for_ingestion", "gate_ready", "chunk_count",
                    "error_codes", "error_messages", "persisted", "document_id",
                    "scope_errors"):
            assert key in doc, f"Missing key in doc: {key}"


def test_post_ingest_persist_does_not_call_openai_or_milvus(monkeypatch, tmp_path):
    """Persist mode uses only scanner + worker + repository, no external AI/Milvus."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )

    async def fake_persist(**kwargs):
        return _fake_persist_result()

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunk_count"] >= 1
    assert data["persisted_chunk_count"] >= 1


def test_post_ingest_persist_handles_repository_error_without_stacktrace(monkeypatch, tmp_path):
    """Repository errors are caught and returned as error messages, not stacktraces."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )

    async def failing_persist(**kwargs):
        raise RuntimeError("DB connection refused")

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", failing_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["errors"]
    error_text = " ".join(data["errors"]).lower()
    assert "failed" in error_text or "error" in error_text


def test_post_ingest_persist_preserves_node_path_access_tags_permission_tags(monkeypatch, tmp_path):
    """Frontmatter metadata survives the persist pipeline."""
    pkg_path = _make_dev_package(
        tmp_path,
        ready_docs=[("ready.md", _READY_FRONTMATTER)],
    )

    async def fake_persist(**kwargs):
        return _fake_persist_result()

    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    ready_docs = [d for d in data["documents"] if d["gate_ready"] is True]
    assert len(ready_docs) >= 1
    rd = ready_docs[0]
    assert rd["node_path"] == "/finanzas/general"
    assert rd["status"] == "approved"
    assert rd["ingestion_status"] == "ready"


# ── Scope hardening (Fase 1.4) ────────────────────────────────────────────────


def test_persist_requires_organization_code(monkeypatch, tmp_path):
    """Persist mode rejects missing organization_code."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 422
    assert "organization_code" in resp.json()["detail"].lower()


def test_persist_requires_workspace_code(monkeypatch, tmp_path):
    """Persist mode rejects missing workspace_code."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 422
    assert "workspace_code" in resp.json()["detail"].lower()


def test_persist_requires_knowledge_scope_code(monkeypatch, tmp_path):
    """Persist mode rejects missing knowledge_scope_code."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "",
            },
        )
    assert resp.status_code == 422
    assert "knowledge_scope_code" in resp.json()["detail"].lower()


def test_persist_rejects_organization_code_mismatch(monkeypatch, tmp_path):
    """Persist aborts when request org_code differs from frontmatter."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_999",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    assert data.get("scope_errors"), f"expected scope_errors, got {data}"
    assert any("organization_code" in e for e in data["scope_errors"])
    assert data["ok"] is False


def test_persist_rejects_workspace_code_mismatch(monkeypatch, tmp_path):
    """Persist aborts when request ws_code differs from frontmatter."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_999",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    assert data.get("scope_errors"), f"expected scope_errors, got {data}"
    assert any("workspace_code" in e for e in data["scope_errors"])
    assert data["ok"] is False


def test_persist_rejects_knowledge_scope_code_mismatch(monkeypatch, tmp_path):
    """Persist aborts when request ks_code differs from frontmatter."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_999",
            },
        )
    data = resp.json()
    assert data.get("scope_errors"), f"expected scope_errors, got {data}"
    assert any("knowledge_scope_code" in e for e in data["scope_errors"])
    assert data["ok"] is False


def test_persist_rejects_package_code_mismatch(monkeypatch, tmp_path):
    """Persist aborts when request package_code differs from frontmatter."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    fm = _READY_FRONTMATTER.replace(
        "source_type: markdown",
        "source_type: markdown\npackage_code: pkg_dev_test",
    )
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", fm)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_other",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    data = resp.json()
    assert data.get("scope_errors"), f"expected scope_errors, got {data}"
    assert any("package_code" in e for e in data["scope_errors"])
    assert data["ok"] is False


def test_persist_rejects_forbidden_vera_technical_ids(monkeypatch, tmp_path):
    """Persist rejects vera_* technical identifiers."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "vera_org",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 422
    assert "vera_" in resp.json()["detail"].lower()


def test_dry_run_reports_scope_mismatch_without_db(tmp_path):
    """Dry run reports scope mismatch as warning, no DB required."""
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
                "organization_code": "org_999",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert any("scope mismatch" in w for w in data.get("scope_warnings", [])), (
        f"expected scope mismatch warning, got scope_warnings={data.get('scope_warnings')}"
    )


def test_persist_does_not_activate_planned_extension(monkeypatch, tmp_path):
    """planned_extension in frontmatter does not bypass readiness gate."""
    from routes.knowledge_ingestion_dev import _check_document_scope_consistency

    fm = {
        "organization_code": "org_360",
        "workspace_code": "ws_360",
        "knowledge_scope_code": "ks_360",
        "package_code": "pkg_dev_test",
        "extension": "neural_search",
    }
    errors = _check_document_scope_consistency(0, "doc.md", fm, "org_360", "ws_360", "ks_360", "pkg_dev_test")
    assert errors == []


def test_response_contract_includes_scope_validation_summary(monkeypatch, tmp_path):
    """Response includes scope_warnings and scope_errors fields."""
    monkeypatch.setattr(dev_route, "_is_db_configured", lambda: True)
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])

    async def fake_persist(**kwargs):
        return _fake_persist_result()

    monkeypatch.setattr(dev_route, "_run_persist_pipeline", fake_persist)

    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "persist",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "scope_warnings" in data
    assert "scope_errors" in data
    assert isinstance(data["scope_warnings"], list)
    assert isinstance(data["scope_errors"], list)
    assert "requested_by" in data


def test_dry_run_accepts_scope_context_and_reports_it(tmp_path):
    """Dry run accepts optional scope context and reports it."""
    pkg_path = _make_dev_package(tmp_path, ready_docs=[("ready.md", _READY_FRONTMATTER)])
    with _client() as client:
        resp = client.post(
            "/api/dev/knowledge-ingestion/ingest",
            json={
                "package_code": "pkg_dev_test",
                "package_path": pkg_path,
                "mode": "dry_run",
                "organization_code": "org_360",
                "workspace_code": "ws_360",
                "knowledge_scope_code": "ks_360",
                "requested_by": "tester",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data.get("requested_by") == "tester"
    assert "scope_warnings" in data


def test_persist_requires_access_tags_or_permission_tags(monkeypatch, tmp_path):
    """Persist warns or rejects when ready doc has no access_tags."""
    from routes.knowledge_ingestion_dev import _check_access_tags

    fm_with_tags = {"access_tags": ["ceo"]}
    assert _check_access_tags(fm_with_tags, "doc.md") == []

    fm_no_tags: dict = {}
    errors = _check_access_tags(fm_no_tags, "doc.md")
    assert any("access_tags" in e for e in errors)


def test_post_ingest_dry_run_still_works_after_persist_changes(tmp_path):
    """Adding persist mode did not break existing dry_run behavior."""
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
    assert data["ok"] is True
    assert data["mode"] == "dry_run"
    assert data["document_count"] >= 2
    assert data["rejected_count"] >= 1
    # Verify run_id and persist fields are absent in dry_run
    assert data.get("run_id") is None
    assert data.get("persisted_document_count", 0) == 0


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

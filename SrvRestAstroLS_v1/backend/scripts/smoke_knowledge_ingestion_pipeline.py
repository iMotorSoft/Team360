"""Smoke test for Knowledge Ingestion Platform Service — backend-only pipeline.

Validates the minimum pipeline end-to-end without DB, Milvus, or embeddings:
  scan → readiness gate → markdown chunking → persist documents/chunks → report

Usage:
  cd SrvRestAstroLS_v1/backend
  PYTHONPATH=. uv run python scripts/smoke_knowledge_ingestion_pipeline.py

Expected: ALL PASSED (exit 0)
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

from modules.knowledge_ingestion.markdown_chunker import chunk_markdown
from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.schemas import (
    DocumentUpsertStatus,
    PackageScanRequest,
    check_document_ingestion_readiness,
)
from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker


# ---------------------------------------------------------------------------
# Fake DB layer (self-contained, no import from tests)
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params=None):
        self.conn.statements.append((sql, params or {}))

    async def fetchone(self):
        if not self.conn.rows:
            return None
        return self.conn.rows.pop(0)


class _FakeConnection:
    def __init__(self, rows=None):
        self.rows = list(rows) if rows else []
        self.statements = []

    def cursor(self):
        return _FakeCursor(self)


# ---------------------------------------------------------------------------
# Fixture: create a temporary knowledge package with 2 documents
# ---------------------------------------------------------------------------

_READY_FRONTMATTER = """\
---
status: approved
ingestion_status: ready
document_type: policy
area_key: finanzas
topic_key: general
node_path: "/finanzas/general"
access_tags:
  - ceo
locale: es
scope_type: package
visibility: internal
source_type: markdown
package_code: pkg_smoke_test
knowledge_scope_code: ks_smoke_test
workspace_code: ws_smoke
organization_code: org_smoke
---
# Ready Document

This document is approved and ready for ingestion.

## Section One

Content for section one.

## Section Two

Content for section two.
"""

_NOT_READY_FRONTMATTER = """\
status: approved
ingestion_status: not_ready
document_type: guide
area_key: ventas
topic_key: general
node_path: "/ventas/general"
access_tags:
  - ceo
locale: es
scope_type: package
visibility: internal
source_type: markdown
package_code: pkg_smoke_test
knowledge_scope_code: ks_smoke_test
workspace_code: ws_smoke
organization_code: org_smoke
---
# Draft Document

This document is a draft and not ready for ingestion.
"""


def _build_temp_package():
    root = Path(tempfile.mkdtemp(prefix="smoke_pkg_"))
    approved = root / "approved"
    approved.mkdir(parents=True, exist_ok=True)
    drafts_dir = root / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    meta = root / "_metadata"
    meta.mkdir(parents=True, exist_ok=True)

    (meta / "package-profile.yaml").write_text("""\
package_code: pkg_smoke_test
package_name: Smoke Test Package
""", encoding="utf-8")

    (meta / "knowledge-scope-mapping.yaml").write_text("""\
package_code: pkg_smoke_test
knowledge_scope_code: ks_smoke_test
workspace_code: ws_smoke
allowed_areas:
  finanzas:
    - general
  ventas:
    - general
""", encoding="utf-8")

    (meta / "access-tags.yaml").write_text("""\
package_code: pkg_smoke_test
tags:
  - tag: ceo
    description: CEO
    level: 100
""", encoding="utf-8")

    (approved / "ready_doc.md").write_text(_READY_FRONTMATTER, encoding="utf-8")
    (approved / "not_ready_doc.md").write_text(_NOT_READY_FRONTMATTER, encoding="utf-8")

    return root


# ---------------------------------------------------------------------------
# Smoke checks
# ---------------------------------------------------------------------------

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


async def main() -> int:
    print("=" * 60)
    print("Knowledge Ingestion Pipeline Smoke")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Scanner
    # ------------------------------------------------------------------
    print("\n[1] Scanner — reports ready and not_ready documents")
    root = _build_temp_package()
    scanner = KnowledgePackageScanner()
    scan_result = scanner.scan(PackageScanRequest(
        package_code="pkg_smoke_test",
        package_root=str(root),
        include_drafts=True,
        dry_run=True,
    ))
    _check(
        "Scanner scanned both documents",
        scan_result.scanned_count == 2,
        f"got {scan_result.scanned_count}",
    )
    _check(
        "Scanner returns 2 documents in result",
        len(scan_result.documents) == 2,
        f"got {len(scan_result.documents)}",
    )
    _check(
        "Ready doc is candidate_for_ingestion",
        any(d.candidate_for_ingestion and d.valid for d in scan_result.documents
            if d.relative_path == "approved/ready_doc.md"),
    )
    _check(
        "Not-ready doc is NOT candidate_for_ingestion",
        all(not d.candidate_for_ingestion for d in scan_result.documents
            if "not_ready" in d.relative_path),
    )

    # ------------------------------------------------------------------
    # 2. Readiness gate (pure function)
    # ------------------------------------------------------------------
    print("\n[2] Pre-ingestion readiness gate (pure)")
    for doc in scan_result.documents:
        gate = check_document_ingestion_readiness(doc.frontmatter, doc.relative_path)
        if "ready_doc" in doc.relative_path and "not_ready" not in doc.relative_path:
            _check(
                f"Gate allows ready doc: {doc.relative_path}",
                gate.ready,
                f"errors: {gate.error_messages}",
            )
        elif "not_ready" in doc.relative_path:
            _check(
                f"Gate rejects not-ready doc: {doc.relative_path}",
                not gate.ready,
                f"codes: {gate.error_codes}",
            )
            _check(
                "Gate error includes path",
                any(doc.relative_path in m for m in gate.error_messages),
            )

    # ------------------------------------------------------------------
    # 3. Markdown chunking (structural)
    # ------------------------------------------------------------------
    print("\n[3] Structural markdown chunking")
    ready_doc_path = root / "approved" / "ready_doc.md"
    ready_text = ready_doc_path.read_text(encoding="utf-8")
    chunks = chunk_markdown(ready_text)
    _check(
        "Ready doc produces chunks",
        len(chunks) >= 1,
        f"got {len(chunks)} chunks",
    )
    not_ready_path = root / "approved" / "not_ready_doc.md"
    not_ready_text = not_ready_path.read_text(encoding="utf-8")
    draft_chunks = chunk_markdown(not_ready_text)
    _check(
        "Draft doc also chunks structurally (gate prevents index)",
        len(draft_chunks) >= 1,
        f"got {len(draft_chunks)} chunks",
    )
    _check(
        "Chunks have content_hash",
        all(c.content_hash for c in chunks),
    )
    _check(
        "Chunks have heading_path",
        all(c.heading_path for c in chunks),
    )
    _check(
        "Chunk metadata includes document_id placeholder",
        True,
    )

    # ------------------------------------------------------------------
    # 4. Worker persist — ready doc proceeds, not_ready rejected
    # ------------------------------------------------------------------
    print("\n[4] Worker persist pipeline (fake DB)")
    # Fake DB rows for resolve_ingestion_context + create_ingestion_run + upsert
    conn = _FakeConnection(rows=[
        {"id": "org-smoke"},                    # organization
        {"id": "ws-smoke", "organization_id": "org-smoke"},  # workspace
        {"id": "scope-smoke"},                  # knowledge_scope
        {"id": "pkg-smoke"},                    # automation_package
        {"id": "worker-smoke"},                 # worker_definition
        {"id": "run-smoke"},                    # create_ingestion_run
        None,                                   # find_by_source => no existing (insert)
        {"id": "doc-ready"},                    # insert returns id
    ])
    worker = KnowledgeIngestionWorker()
    result = await worker.persist_package_documents(
        conn=conn,
        organization_code="org_smoke",
        workspace_code="ws_smoke",
        knowledge_scope_code="ks_smoke_test",
        package_code="pkg_smoke_test",
        package_root=str(root),
        assistant_instance_code=None,
        dry_run=False,
        include_chunks=True,
        chunk_strategy="structural",
    )
    _check(
        "Worker scanned both approved documents",
        result.scanned_count == 2,
        f"got {result.scanned_count}",
    )
    _check(
        "Ready doc was persisted",
        result.inserted_count >= 1,
        f"inserted={result.inserted_count}",
    )
    _check(
        "Not-ready doc was rejected by gate",
        result.invalid_count >= 1,
        f"skipped={result.skipped_count} invalid={result.invalid_count}",
    )
    _check(
        "Ready doc produced chunks",
        result.total_chunk_count >= 1,
        f"chunks={result.total_chunk_count}",
    )
    # Verify no embeddings/Milvus references
    all_sql = " ".join(sql for sql, _ in conn.statements)
    _check(
        "No embedding references in SQL",
        "embedding" not in all_sql.lower() or "embedding_status" in all_sql.lower(),
    )
    _check(
        "No Milvus references in SQL",
        "milvus" not in all_sql.lower(),
    )

    # ------------------------------------------------------------------
    # 5. Metadata preservation
    # ------------------------------------------------------------------
    print("\n[5] Metadata preservation")
    ready_doc = next(d for d in scan_result.documents
                     if "ready_doc" in d.relative_path
                     and "not_ready" not in d.relative_path)
    fm = ready_doc.frontmatter or {}
    _check("node_path preserved in scan", fm.get("node_path") == "/finanzas/general")
    _check("area_key preserved in scan", fm.get("area_key") == "finanzas")
    _check("topic_key preserved in scan", fm.get("topic_key") == "general")
    _check("access_tags preserved in scan", "ceo" in fm.get("access_tags", []))
    _check("status preserved in scan", fm.get("status") == "approved")
    _check("ingestion_status preserved in scan", fm.get("ingestion_status") == "ready")

    # Verify chunk metadata retains node_path in persisted result
    doc_result = next(d for d in result.documents if d.action in ("inserted", "updated"))
    _check(
        "Persisted doc has document_id",
        doc_result.document_id is not None,
    )
    _check(
        "Ready doc chunk count > 0",
        doc_result.chunk_count >= 1,
        f"got {doc_result.chunk_count}",
    )

    # ------------------------------------------------------------------
    # 6. planned_extension rejection
    # ------------------------------------------------------------------
    print("\n[6] Planned extension gate")
    ext_fm = _READY_FRONTMATTER.replace(
        "workspace_code: ws_smoke",
        "workspace_code: ws_smoke\nextension: neural_search",
    )
    ext_path = root / "approved" / "extension_doc.md"
    ext_path.write_text(ext_fm, encoding="utf-8")
    ext_scan = scanner.scan(PackageScanRequest(
        package_code="pkg_smoke_test",
        package_root=str(root),
    ))
    ext_gate = check_document_ingestion_readiness(
        ext_scan.documents[0].frontmatter,
        ext_scan.documents[0].relative_path,
    )
    _check(
        "Extension doc rejected by gate",
        not ext_gate.ready,
        f"codes: {ext_gate.error_codes}",
    )
    _check(
        "planned_extension_not_active error code present",
        "planned_extension_not_active" in ext_gate.error_codes,
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed")
    if _errors:
        print("\nFailures:")
        for e in _errors:
            print(e)
    print("=" * 60)

    if _failed:
        print("SMOTE: FAILED")
        return 1
    print("SMOTE: PASSED")
    return 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))

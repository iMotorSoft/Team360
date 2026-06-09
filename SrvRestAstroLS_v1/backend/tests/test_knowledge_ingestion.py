"""Tests for Knowledge Ingestion Phase 1 — metadata validation and run tracking."""

from __future__ import annotations

import hashlib
import pytest

import tempfile
from pathlib import Path

from modules.knowledge_ingestion.markdown_chunker import chunk_markdown
from modules.knowledge_ingestion.package_scanner import KnowledgePackageScanner
from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
from modules.knowledge_ingestion.schemas import (
    INGESTION_PHASES,
    DOCUMENT_TYPES,
    DocumentUpsertStatus,
    KnowledgeDocumentPersistenceResult,
    ORGANIZATION_MEMBER_ROLE_CODES,
    ORGANIZATION_ROLE_CODES,
    PackagePersistResult,
    PackageScanRequest,
    SCOPE_TYPES,
    SOURCE_TYPES,
    SUPPORTED_LOCALES,
    VISIBILITY_LEVELS,
    IngestionMetadata,
)
from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker


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
# IngestionMetadata validation
# ---------------------------------------------------------------------------


class TestIngestionMetadataValidation:
    def test_valid_metadata_passes(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_team360_sales_diagnosis",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/finanzas/cobranzas",
            area_key="finanzas",
            topic_key="cobranzas",
            document_type="procedure",
            visibility="internal",
            access_tags=["director_finanzas", "gerente_finanzas"],
            locale="es",
            version="1.0",
            title="Procedimiento de cobranzas",
        )
        errors = metadata.validate()
        assert errors == []

    def test_empty_knowledge_scope_code_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert "knowledge_scope_code is required" in errors

    def test_invalid_scope_type_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="invalid_scope",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("scope_type" in e for e in errors)

    def test_empty_organization_code_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert "organization_code is required" in errors

    def test_invalid_node_path_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="no-leading-slash",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("node_path" in e for e in errors)

    def test_empty_access_tags_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=[],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert "access_tags must not be empty" in errors

    def test_invalid_locale_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="fr",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("locale" in e for e in errors)

    def test_invalid_document_type_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="invalid_doc_type",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("document_type" in e for e in errors)

    def test_invalid_visibility_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="secret",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("visibility" in e for e in errors)

    def test_empty_title_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="",
        )
        errors = metadata.validate()
        assert "title is required" in errors

    def test_empty_version_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="",
            title="Test",
        )
        errors = metadata.validate()
        assert "version is required" in errors

    def test_node_path_trailing_slash_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/finanzas/",
            area_key="finanzas",
            topic_key="cobranzas",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("node_path" in e for e in errors)

    def test_root_node_path_allowed(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="global",
            organization_code="team360",
            workspace_code="team360_platform",
            node_path="/",
            area_key="platform",
            topic_key="general",
            document_type="reference",
            visibility="public",
            access_tags=["ceo"],
            locale="en",
            version="1.0",
            title="Global Reference",
        )
        errors = metadata.validate()
        assert errors == []

    def test_access_tags_empty_string_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo", ""],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("empty strings" in e for e in errors)

    def test_area_key_with_slash_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="finanzas/cobranzas",
            topic_key="general",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("area_key" in e for e in errors)

    def test_topic_key_with_slash_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="finanzas",
            topic_key="cobranzas/detalle",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
        )
        errors = metadata.validate()
        assert any("topic_key" in e for e in errors)

    def test_invalid_source_type_fails(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="Test",
            source_type="docx",
        )
        errors = metadata.validate()
        assert any("source_type" in e for e in errors)

    def test_multiple_errors_returned(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="",
            scope_type="bad_type",
            organization_code="",
            workspace_code="",
            node_path="bad",
            area_key="",
            topic_key="",
            document_type="bad",
            visibility="bad",
            access_tags=[],
            locale="xx",
            version="",
            title="",
            source_type="docx",
        )
        errors = metadata.validate()
        assert len(errors) >= 5  # multiple validation errors


# ---------------------------------------------------------------------------
# IngestionMetadata to_metadata_dict
# ---------------------------------------------------------------------------


class TestIngestionMetadataToDict:
    def test_to_metadata_dict_contains_all_keys(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_team360_sales_diagnosis",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/finanzas",
            area_key="finanzas",
            topic_key="general",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo", "director_finanzas"],
            locale="es",
            version="2.1",
            title="Politica financiera",
        )
        d = metadata.to_metadata_dict()
        assert d["knowledge_scope_code"] == "ks_team360_sales_diagnosis"
        assert d["scope_type"] == "assistant_instance"
        assert d["organization_code"] == "team360_live"
        assert d["workspace_code"] == "team360_public_site"
        assert d["node_path"] == "/finanzas"
        assert d["area_key"] == "finanzas"
        assert d["topic_key"] == "general"
        assert d["document_type"] == "policy"
        assert d["visibility"] == "internal"
        assert d["access_tags"] == ["ceo", "director_finanzas"]
        assert d["locale"] == "es"
        assert d["version"] == "2.1"
        assert d["title"] == "Politica financiera"
        assert d["source_type"] == "markdown"
        assert "package_code" in d
        assert "assistant_instance_code" in d
        assert "service_code" in d

    def test_default_fields_in_dict(self):
        metadata = IngestionMetadata(
            knowledge_scope_code="ks_test",
            scope_type="global",
            organization_code="team360",
            workspace_code="team360_platform",
            node_path="/",
            area_key="platform",
            topic_key="general",
            document_type="reference",
            visibility="public",
            access_tags=["ceo"],
            locale="en",
            version="1.0",
            title="Global Reference",
        )
        d = metadata.to_metadata_dict()
        assert d["package_code"] == ""
        assert d["assistant_instance_code"] == ""
        assert d["service_code"] == ""
        assert d["source_type"] == "markdown"


# ---------------------------------------------------------------------------
# IngestionWorker validation_and_register
# ---------------------------------------------------------------------------


class TestKnowledgeIngestionWorker:
    @pytest.mark.anyio
    async def test_validate_and_register_success(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
        ])

        valid_metadata = IngestionMetadata(
            knowledge_scope_code="ks_team360_sales_diagnosis",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/finanzas/cobranzas",
            area_key="finanzas",
            topic_key="cobranzas",
            document_type="procedure",
            visibility="internal",
            access_tags=["gerente_finanzas"],
            locale="es",
            version="1.0",
            title="Cobranzas procedure",
        )
        result = await worker.validate_and_register(
            conn=conn,
            metadata=valid_metadata,
            document_source="documents/cobranzas.md",
        )
        assert "run_id" in result
        assert result["run_id"] == "run-uuid"
        assert "phases" in result
        assert result["phases"]["validate_metadata"] == "completed"
        assert len(conn.statements) >= 1
        insert_params = next(
            params for sql, params in conn.statements
            if "insert into knowledge_ingestion_runs" in sql
        )
        assert insert_params["organization_id"] == "org-uuid"
        assert insert_params["workspace_id"] == "workspace-uuid"
        assert insert_params["knowledge_scope_id"] == "scope-uuid"
        assert insert_params["knowledge_scope_id"] != "ks_team360_sales_diagnosis"
        assert insert_params["triggered_by_user_id"] is None

    @pytest.mark.anyio
    async def test_validate_and_register_uses_triggered_user_id(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "assistant-uuid"},
            {"id": "worker-uuid"},
            {"id": "user-uuid"},
            {"id": "run-uuid"},
        ])

        metadata = IngestionMetadata(
            knowledge_scope_code="ks_team360_sales_diagnosis",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/ventas/general",
            area_key="ventas",
            topic_key="general",
            document_type="guide",
            visibility="internal",
            access_tags=["content_owner"],
            locale="es",
            version="1.0",
            title="Ventas guide",
            package_code="pkg_sales_diagnosis",
            assistant_instance_code="team360_sales_diagnosis",
            service_code="svc_sales_diagnosis",
        )

        result = await worker.validate_and_register(
            conn=conn,
            metadata=metadata,
            document_source="documents/ventas.md",
            triggered_by_email="mario.rojas.marconi@gmail.com",
        )

        assert result["context"].triggered_by_user_id == "user-uuid"
        insert_params = next(
            params for sql, params in conn.statements
            if "insert into knowledge_ingestion_runs" in sql
        )
        assert insert_params["organization_id"] == "org-uuid"
        assert insert_params["workspace_id"] == "workspace-uuid"
        assert insert_params["knowledge_scope_id"] == "scope-uuid"
        assert insert_params["triggered_by_user_id"] == "user-uuid"
        snapshot = insert_params["metadata_snapshot"].obj
        assert snapshot["organization_code"] == "team360_live"
        assert snapshot["workspace_code"] == "team360_public_site"
        assert snapshot["knowledge_scope_code"] == "ks_team360_sales_diagnosis"
        assert snapshot["package_code"] == "pkg_sales_diagnosis"
        assert snapshot["assistant_instance_code"] == "team360_sales_diagnosis"
        assert snapshot["service_code"] == "svc_sales_diagnosis"
        assert snapshot["triggered_by_email"] == "mario.rojas.marconi@gmail.com"

    @pytest.mark.anyio
    async def test_validate_and_register_dry_run_does_not_create_run(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection()

        metadata = IngestionMetadata(
            knowledge_scope_code="ks_team360_sales_diagnosis",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/ventas/general",
            area_key="ventas",
            topic_key="general",
            document_type="guide",
            visibility="internal",
            access_tags=["content_owner"],
            locale="es",
            version="1.0",
            title="Ventas guide",
        )

        result = await worker.validate_and_register(
            conn=conn,
            metadata=metadata,
            document_source="documents/ventas.md",
            dry_run=True,
        )

        assert result["run_id"] is None
        assert result["dry_run"] is True
        assert conn.statements == []

    @pytest.mark.anyio
    async def test_validate_and_register_raises_on_invalid(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection()

        invalid_metadata = IngestionMetadata(
            knowledge_scope_code="",
            scope_type="assistant_instance",
            organization_code="team360_live",
            workspace_code="team360_public_site",
            node_path="/test",
            area_key="test",
            topic_key="test",
            document_type="policy",
            visibility="internal",
            access_tags=["ceo"],
            locale="es",
            version="1.0",
            title="",
        )
        with pytest.raises(ValueError, match="Ingestion metadata validation failed"):
            await worker.validate_and_register(
                conn=conn,
                metadata=invalid_metadata,
                document_source="bad.md",
            )

    @pytest.mark.anyio
    async def test_advance_phase_raises_on_unknown_phase(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection()

        with pytest.raises(ValueError, match="Unknown current phase"):
            await worker.advance_phase(
                conn=conn,
                run_id="test-id",
                current_phase="nonexistent",
                next_phase="convert_to_markdown",
                phases_jsonb={"nonexistent": "completed"},
            )

    @pytest.mark.anyio
    async def test_advance_phase_raises_on_incomplete_current(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection()

        with pytest.raises(ValueError, match="phase not completed"):
            await worker.advance_phase(
                conn=conn,
                run_id="test-id",
                current_phase="validate_metadata",
                next_phase="convert_to_markdown",
                phases_jsonb={"validate_metadata": "failed"},
            )

    @pytest.mark.anyio
    async def test_advance_phase_raises_on_phase_skip(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection()

        with pytest.raises(ValueError, match="Cannot jump"):
            await worker.advance_phase(
                conn=conn,
                run_id="test-id",
                current_phase="validate_metadata",
                next_phase="semantic_chunk",
                phases_jsonb={"validate_metadata": "completed"},
            )


# ---------------------------------------------------------------------------
# Schema constants integrity
# ---------------------------------------------------------------------------


class TestSchemaConstants:
    def test_ingestion_phases_are_non_empty(self):
        assert len(INGESTION_PHASES) >= 5

    def test_document_types_contains_expected(self):
        assert "policy" in DOCUMENT_TYPES
        assert "guide" in DOCUMENT_TYPES
        assert "faq" in DOCUMENT_TYPES

    def test_scope_types_contains_hierarchy_levels(self):
        for level in ("global", "package", "organization", "workspace", "session"):
            assert level in SCOPE_TYPES

    def test_supported_locales_match_team360(self):
        for loc in ("es", "en", "he"):
            assert loc in SUPPORTED_LOCALES

    def test_visibility_levels_includes_restricted(self):
        assert "restricted" in VISIBILITY_LEVELS

    def test_source_types_contains_expected(self):
        assert "markdown" in SOURCE_TYPES
        assert "pdf" in SOURCE_TYPES
        assert "html" in SOURCE_TYPES

    def test_organization_roles_are_distinct_from_member_roles(self):
        assert ORGANIZATION_ROLE_CODES
        assert ORGANIZATION_MEMBER_ROLE_CODES
        assert ORGANIZATION_ROLE_CODES.isdisjoint(ORGANIZATION_MEMBER_ROLE_CODES)
        assert "platform_owner" in ORGANIZATION_ROLE_CODES
        assert "organization_owner" in ORGANIZATION_MEMBER_ROLE_CODES


# ---------------------------------------------------------------------------
# Markdown chunker (Fase 1.4a)
# ---------------------------------------------------------------------------


class TestMarkdownChunker:
    def test_ignores_frontmatter(self):
        md = """\
---
status: approved
ingestion_status: ready
---

# Section One

Body text.
"""
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert "# Section One" in chunks[0].content
        assert "status: approved" not in chunks[0].content

    def test_divides_by_headings(self):
        md = """\
# First

Content A.

## Second

Content B.

### Third

Content C.
"""
        chunks = chunk_markdown(md)
        assert len(chunks) == 3
        assert chunks[0].title == "First"
        assert chunks[1].title == "Second"
        assert chunks[2].title == "Third"
        assert chunks[0].heading_level == 1
        assert chunks[1].heading_level == 2
        assert chunks[2].heading_level == 3
        assert "Content A." in chunks[0].content
        assert "Content B." in chunks[1].content
        assert "Content C." in chunks[2].content
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2

    def test_no_headings_single_chunk(self):
        md = "Just a paragraph.\n\nAnother paragraph.\n"
        chunks = chunk_markdown(md)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert "Just a paragraph." in chunks[0].content
        assert chunks[0].char_count > 0

    def test_no_empty_chunks(self):
        md = """\
# Heading One

## Heading Two

### Heading Three
"""
        chunks = chunk_markdown(md)
        # Each heading has at least itself in content
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c.content) > 0
            assert c.char_count > 0

    def test_heading_path_hierarchy(self):
        md = """\
# L1 A

A body.

## L2 A.1

A.1 body.

# L1 B

B body.
"""
        chunks = chunk_markdown(md)
        assert len(chunks) == 3
        assert chunks[0].heading_path == ["L1 A"]
        assert chunks[1].heading_path == ["L1 A", "L2 A.1"]
        assert chunks[2].heading_path == ["L1 B"]

    def test_base_metadata_propagated_to_chunks(self):
        md = """\
# Section
Body.
"""
        meta = {"locale": "es", "document_type": "guide"}
        chunks = chunk_markdown(md, base_metadata=meta)
        assert len(chunks) == 1
        for k, v in meta.items():
            assert chunks[0].metadata.get(k) == v

    def test_content_hash_stable(self):
        md = "# Stable\nSame content."
        c1 = chunk_markdown(md)
        c2 = chunk_markdown(md)
        assert c1[0].content_hash == c2[0].content_hash

    def test_empty_body_returns_empty(self):
        assert chunk_markdown("") == []
        assert chunk_markdown("---\nkey: val\n---") == []


# ---------------------------------------------------------------------------
# Repository basic contract
# ---------------------------------------------------------------------------


class TestKnowledgeIngestionRepository:
    def test_repository_can_be_instantiated(self):
        repo = KnowledgeIngestionRepository()
        assert repo is not None
        # No DB calls — repository uses injected connection

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_success(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "assistant-uuid"},
            {"id": "worker-uuid"},
            {"id": "user-uuid"},
        ])

        context = await repo.resolve_ingestion_context(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            assistant_instance_code="team360_sales_diagnosis",
            triggered_by_email="mario.rojas.marconi@gmail.com",
        )

        assert context.organization_id == "org-uuid"
        assert context.workspace_id == "workspace-uuid"
        assert context.knowledge_scope_id == "scope-uuid"
        assert context.automation_package_id == "package-uuid"
        assert context.assistant_instance_id == "assistant-uuid"
        assert context.worker_definition_id == "worker-uuid"
        assert context.triggered_by_user_id == "user-uuid"
        assert context.organization_code == "team360_live"
        assert context.knowledge_scope_code == "ks_team360_sales_diagnosis"
        assert context.knowledge_scope_id != context.knowledge_scope_code
        assert context.organization_id != context.organization_code

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_unknown_organization(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection()

        with pytest.raises(ValueError, match="organization_code not found"):
            await repo.resolve_ingestion_context(
                conn=conn,
                organization_code="missing_org",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
            )

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_workspace_wrong_organization(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "other-org-uuid"},
        ])

        with pytest.raises(ValueError, match="workspace_code does not belong"):
            await repo.resolve_ingestion_context(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
            )

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_scope_is_filtered_by_workspace(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            None,
        ])

        with pytest.raises(ValueError, match="knowledge_scope_code not found"):
            await repo.resolve_ingestion_context(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
            )

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_package_optional(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "worker-uuid"},
        ])

        context = await repo.resolve_ingestion_context(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
        )

        assert context.automation_package_id is None
        assert context.assistant_instance_id is None
        assert context.worker_definition_id == "worker-uuid"

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_missing_worker(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            None,
        ])

        with pytest.raises(ValueError, match="worker_code not found"):
            await repo.resolve_ingestion_context(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                worker_code="missing_worker",
            )

    @pytest.mark.anyio
    async def test_resolve_ingestion_context_missing_triggered_user(self):
        repo = KnowledgeIngestionRepository()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "worker-uuid"},
            None,
        ])

        with pytest.raises(ValueError, match="triggered_by_email not found"):
            await repo.resolve_ingestion_context(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                triggered_by_email="missing@example.com",
            )


# ---------------------------------------------------------------------------
# Package scanner (Fase 1.2)
# ---------------------------------------------------------------------------


def _make_package_dir(
    approved_mds: list[tuple[str, str]],
    drafts_mds: list[tuple[str, str]] | None = None,
) -> str:
    root = Path(tempfile.mkdtemp(prefix="pkg_test_"))
    approved = root / "approved"
    approved.mkdir(parents=True, exist_ok=True)
    drafts_dir = root / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    meta = root / "_metadata"
    meta.mkdir(parents=True, exist_ok=True)

    (meta / "package-profile.yaml").write_text("""\
package_code: pkg_sales_diagnosis
package_name: Test Package
""", encoding="utf-8")

    (meta / "knowledge-scope-mapping.yaml").write_text("""\
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
workspace_code: team360_platform
default_runtime_organization_code: team360_live
default_runtime_workspace_code: team360_public_site
allowed_areas:
  finanzas:
    - general
  ventas:
    - general
""", encoding="utf-8")

    (meta / "access-tags.yaml").write_text("""\
package_code: pkg_sales_diagnosis
tags:
  - tag: ceo
    description: CEO
    level: 100
  - tag: director_finanzas
    description: Director
    level: 80
  - tag: public
    description: Public
    level: 0
""", encoding="utf-8")

    for rel_path, content in approved_mds:
        fp = approved / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    if drafts_mds:
        for rel_path, content in drafts_mds:
            fp = drafts_dir / rel_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")

    return str(root)


_VALID_FRONTMATTER = """\
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
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
workspace_code: team360_platform
---

# Test

Content here.
"""


class TestKnowledgePackageScanner:
    def test_approved_empty_returns_valid_scan_with_zero_docs(self):
        root = _make_package_dir([])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.scanned_count == 0
        assert result.valid_count == 0
        assert result.invalid_count == 0
        assert result.candidate_count == 0
        assert not result.errors
        assert any("No .md documents found" in w for w in result.warnings)

    def test_drafts_not_included_by_default(self):
        root = _make_package_dir([], [
            ("draft-test.md", _VALID_FRONTMATTER),
        ])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.scanned_count == 0
        assert result.skipped_count == 1

    def test_include_drafts_without_dry_run_fails(self):
        root = _make_package_dir([])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_drafts=True,
        ))
        assert result.errors
        assert any("include_drafts=True requires dry_run=True" in e for e in result.errors)

    def test_include_drafts_with_dry_run_includes_drafts(self):
        root = _make_package_dir([], [
            ("draft-test.md", _VALID_FRONTMATTER),
        ])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=True,
            include_drafts=True,
        ))
        assert result.scanned_count == 1
        assert result.documents[0].source_section == "drafts"

    def test_document_without_frontmatter_is_invalid(self):
        root = _make_package_dir([
            ("no-fm.md", "Just content without frontmatter"),
        ])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.scanned_count == 1
        assert result.invalid_count == 1
        assert result.valid_count == 0
        assert not result.documents[0].valid
        assert not result.documents[0].candidate_for_ingestion
        assert result.documents[0].has_frontmatter is False

    def test_status_draft_is_not_candidate_for_ingestion(self):
        fm = _VALID_FRONTMATTER.replace("status: approved", "status: draft")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.scanned_count == 1
        assert result.candidate_count == 0
        assert not result.documents[0].candidate_for_ingestion

    def test_ingestion_status_not_ready_is_not_candidate(self):
        fm = _VALID_FRONTMATTER.replace("ingestion_status: ready", "ingestion_status: not_ready")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.scanned_count == 1
        assert result.candidate_count == 0
        assert not result.documents[0].candidate_for_ingestion

    def test_area_key_with_slash_fails(self):
        fm = _VALID_FRONTMATTER.replace("area_key: finanzas", "area_key: finanzas/cobranzas")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("area_key" in i.field for i in result.documents[0].issues)

    def test_topic_key_with_slash_fails(self):
        fm = _VALID_FRONTMATTER.replace("topic_key: general", "topic_key: general/detalle")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("topic_key" in i.field for i in result.documents[0].issues)

    def test_node_path_invalid_fails(self):
        fm = _VALID_FRONTMATTER.replace('node_path: "/finanzas/general"', 'node_path: "no-slash"')
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("node_path" in i.field for i in result.documents[0].issues)

    def test_access_tags_empty_fails(self):
        fm = _VALID_FRONTMATTER.replace("  - ceo", "")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("access_tags" in i.field for i in result.documents[0].issues)

    def test_unknown_access_tag_fails(self):
        fm = _VALID_FRONTMATTER.replace("  - ceo", "  - unknown_tag")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("access_tags" in i.field for i in result.documents[0].issues)

    def test_package_code_mismatch_generates_error(self):
        fm = _VALID_FRONTMATTER.replace(
            "package_code: pkg_sales_diagnosis",
            "package_code: pkg_wrong",
        )
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("package_code" in i.field for i in result.documents[0].issues)

    def test_knowledge_scope_code_mismatch_generates_warning(self):
        fm = _VALID_FRONTMATTER.replace(
            "knowledge_scope_code: ks_team360_sales_diagnosis",
            "knowledge_scope_code: ks_wrong_scope",
        )
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 0
        issues = result.documents[0].issues
        assert any("knowledge_scope_code" in i.field for i in issues)
        assert all(i.severity == "warning" for i in issues if "knowledge_scope_code" in i.field)

    def test_workspace_code_mismatch_generates_warning(self):
        fm = _VALID_FRONTMATTER.replace(
            "workspace_code: team360_platform",
            "workspace_code: team360_public_site",
        )
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 0
        issues = result.documents[0].issues
        assert any("workspace_code" in i.field for i in issues)
        assert all(i.severity == "warning" for i in issues if "workspace_code" in i.field)

    def test_valid_approved_document_is_candidate(self):
        root = _make_package_dir([("finanzas/test.md", _VALID_FRONTMATTER)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.scanned_count == 1
        assert result.valid_count == 1
        assert result.candidate_count == 1
        assert result.documents[0].valid
        assert result.documents[0].candidate_for_ingestion
        assert result.documents[0].has_frontmatter
        assert not result.documents[0].issues
        assert result.documents[0].frontmatter["package_code"] == "pkg_sales_diagnosis"

    def test_real_pkg_sales_diagnosis_has_approved_candidate(self):
        package_root = (
            Path(__file__).resolve().parents[2]
            / "knowledge"
            / "packages"
            / "pkg_sales_diagnosis"
        )
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=str(package_root),
            dry_run=True,
        ))

        approved_doc = (
            "approved/automatizaciones/"
            "team360_sales_diagnosis_package_manual.md"
        )
        approved_results = [
            doc for doc in result.documents if doc.relative_path == approved_doc
        ]

        assert result.errors == []
        assert result.invalid_count == 0
        assert result.candidate_count >= 1
        assert result.skipped_count >= 1
        assert all(doc.source_section == "approved" for doc in result.documents)
        assert len(approved_results) == 1
        assert approved_results[0].valid
        assert approved_results[0].candidate_for_ingestion
        assert approved_results[0].frontmatter["status"] == "approved"
        assert approved_results[0].frontmatter["ingestion_status"] == "ready"
        assert approved_results[0].frontmatter["package_code"] == "pkg_sales_diagnosis"
        assert approved_results[0].frontmatter["organization_code"] == "team360_live"
        assert approved_results[0].frontmatter["workspace_code"] == "team360_public_site"
        assert (
            approved_results[0].frontmatter["knowledge_scope_code"]
            == "ks_team360_sales_diagnosis"
        )

    def test_real_pkg_sales_diagnosis_keeps_original_draft_not_ready(self):
        package_root = (
            Path(__file__).resolve().parents[2]
            / "knowledge"
            / "packages"
            / "pkg_sales_diagnosis"
        )
        draft_doc = package_root / "drafts" / "team360_sales_diagnosis_package_manual.md"
        approved_doc = (
            package_root
            / "approved"
            / "automatizaciones"
            / "team360_sales_diagnosis_package_manual.md"
        )

        assert draft_doc.exists()
        assert approved_doc.exists()

        draft_text = draft_doc.read_text(encoding="utf-8")
        assert "status: draft" in draft_text
        assert "ingestion_status: not_ready" in draft_text
        assert "No debe ingerirse" in draft_text

    def test_scanner_does_not_modify_files(self):
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        original = Path(root) / "approved" / "test.md"
        orig_mtime = original.stat().st_mtime
        orig_content = original.read_text(encoding="utf-8")
        scanner = KnowledgePackageScanner()
        scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert original.stat().st_mtime == orig_mtime
        assert original.read_text(encoding="utf-8") == orig_content

    def test_locale_es_AR_normalizes_to_es(self):
        fm = _VALID_FRONTMATTER.replace("locale: es", "locale: es-AR")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.valid_count == 1

    def test_invalid_scope_type_fails(self):
        fm = _VALID_FRONTMATTER.replace("scope_type: package", "scope_type: invalid_type")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("scope_type" in i.field for i in result.documents[0].issues)

    def test_validate_package_dry_run_on_worker(self):
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        worker = KnowledgeIngestionWorker()
        result = worker.validate_package_dry_run(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        )
        assert result.scanned_count == 1
        assert result.valid_count == 1
        assert result.candidate_count == 1

    def test_invalid_document_type_fails(self):
        fm = _VALID_FRONTMATTER.replace("document_type: policy", "document_type: invalid_type")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("document_type" in i.field for i in result.documents[0].issues)

    def test_invalid_visibility_fails(self):
        fm = _VALID_FRONTMATTER.replace("visibility: internal", "visibility: secret")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("visibility" in i.field for i in result.documents[0].issues)

    def test_invalid_source_type_fails(self):
        fm = _VALID_FRONTMATTER.replace("source_type: markdown", "source_type: docx")
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.invalid_count == 1
        assert any("source_type" in i.field for i in result.documents[0].issues)

    def test_runtime_workspace_matches_no_warning(self):
        fm = _VALID_FRONTMATTER.replace(
            'workspace_code: team360_platform',
            'workspace_code: team360_public_site\norganization_code: team360_live'
        )
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.valid_count == 1
        assert result.candidate_count == 1
        ws_issues = [i for i in result.documents[0].issues if i.field == "workspace_code"]
        assert len(ws_issues) == 0, (
            f"Expected no workspace_code warning for runtime target, got: {ws_issues}"
        )

    def test_undeclared_workspace_still_warns(self):
        fm = _VALID_FRONTMATTER.replace(
            'workspace_code: team360_platform',
            'workspace_code: undeclared_workspace'
        )
        root = _make_package_dir([("test.md", fm)])
        scanner = KnowledgePackageScanner()
        result = scanner.scan(PackageScanRequest(
            package_code="pkg_sales_diagnosis",
            package_root=root,
        ))
        assert result.valid_count == 1
        ws_issues = [i for i in result.documents[0].issues if i.field == "workspace_code"]
        assert len(ws_issues) == 1
        assert ws_issues[0].severity == "warning"


# ---------------------------------------------------------------------------
# Package document persistence (Fase 1.3b)
# ---------------------------------------------------------------------------


class TestKnowledgeIngestionPersistence:
    """Tests for persist_package_documents — Phase 1.3b.

    Persists approved candidates as KnowledgeDocuments.
    No chunks, no embeddings, no ArangoDB, no Milvus.
    """

    @pytest.mark.anyio
    async def test_dry_run_does_not_create_run_or_upsert(self):
        """dry_run=True should not create ingestion run nor upsert documents."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=True,
        )
        assert result.run_id is None
        assert result.inserted_count == 0
        assert result.candidate_count == 1
        assert result.persisted_count == 0
        assert len(conn.statements) == 5  # resolve_ingestion_context queries only

    @pytest.mark.anyio
    async def test_persist_inserts_new_document(self):
        """Valid approved candidate without existing DB row should insert."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,  # find_by_source returns no existing doc
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
        )
        assert result.run_id == "run-uuid"
        assert result.inserted_count == 1
        assert result.persisted_count == 1
        assert result.candidate_count == 1
        assert len(result.documents) == 1
        assert result.documents[0].status == DocumentUpsertStatus.INSERTED
        assert result.documents[0].document_id == "doc-uuid"
        # Verify INSERT was called (find_by_source + INSERT INTO knowledge_documents)
        insert_sqls = [
            sql for sql, _ in conn.statements
            if "insert into knowledge_documents" in sql
        ]
        assert len(insert_sqls) == 1
        # Verify run status updated to completed
        update_run_sqls = [
            sql for sql, _ in conn.statements
            if "update knowledge_ingestion_runs" in sql
        ]
        assert any("completed" in sql for sql in update_run_sqls)

    @pytest.mark.anyio
    async def test_persist_unchanged_same_content_hash(self):
        """Existing doc with same content_hash should return unchanged (no UPDATE)."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        file_path = Path(root) / "approved" / "test.md"
        expected_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            {"id": "doc-uuid", "content_hash": expected_hash},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
        )
        assert result.unchanged_count == 1
        assert result.persisted_count == 0
        assert result.inserted_count == 0
        assert result.updated_count == 0
        assert result.documents[0].status == DocumentUpsertStatus.UNCHANGED
        # No UPDATE knowledge_documents should have been executed
        update_kd_sqls = [
            sql for sql, _ in conn.statements
            if "update knowledge_documents" in sql
        ]
        assert len(update_kd_sqls) == 0

    @pytest.mark.anyio
    async def test_persist_updated_different_hash(self):
        """Existing doc with different content_hash should UPDATE."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            {"id": "doc-uuid", "content_hash": "old-content-hash-that-definitely-differs"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
        )
        assert result.updated_count == 1
        assert result.persisted_count == 1
        assert result.inserted_count == 0
        assert result.unchanged_count == 0
        assert result.documents[0].status == DocumentUpsertStatus.UPDATED
        # Verify UPDATE was executed
        update_kd_sqls = [
            sql for sql, _ in conn.statements
            if "update knowledge_documents" in sql
        ]
        assert len(update_kd_sqls) == 1

    @pytest.mark.anyio
    async def test_persist_invalid_document_not_persisted(self):
        """Document with validation errors should not be persisted."""
        fm = _VALID_FRONTMATTER.replace(
            'document_type: policy', 'document_type: unknown_type'
        )
        root = _make_package_dir([("test.md", fm)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
        )
        assert result.invalid_count >= 1
        assert result.persisted_count == 0
        assert result.inserted_count == 0
        # Scanner sets candidate based only on status/ingestion_status,
        # not on other validation fields — so candidate_count may be >0
        # even when the document is invalid.
        # No INSERT/UPDATE knowledge_documents should have been executed
        kd_sqls = [
            sql for sql, _ in conn.statements
            if "knowledge_documents" in sql and ("insert" in sql or "update" in sql)
        ]
        assert len(kd_sqls) == 0

    @pytest.mark.anyio
    async def test_persist_draft_document_not_persisted(self):
        """Draft documents (candidate_for_ingestion=False) are skipped."""
        draft_fm = _VALID_FRONTMATTER.replace(
            "status: approved", "status: draft"
        ).replace(
            "ingestion_status: ready", "ingestion_status: not_ready"
        )
        root = _make_package_dir([("draft.md", draft_fm)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
        )
        assert result.skipped_count >= 1
        assert result.persisted_count == 0
        assert result.candidate_count == 0
        assert result.run_id == "run-uuid"

    @pytest.mark.anyio
    async def test_persist_no_chunks_created(self):
        """Verify no knowledge_chunks inserts are emitted."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
        )
        assert result.inserted_count == 1
        # Verify no knowledge_chunks touched
        chunk_sqls = [
            sql for sql, _ in conn.statements
            if "knowledge_chunks" in sql
        ]
        assert len(chunk_sqls) == 0
        # Verify no embedding or vector references
        all_sql = " ".join(sql for sql, _ in conn.statements)
        assert "embedding" not in all_sql.lower()
        assert "milvus" not in all_sql.lower()
        assert "arango" not in all_sql.lower()

    @pytest.mark.anyio
    async def test_persist_propagates_triggered_by_email(self):
        """triggered_by_email should be resolved and stored in the run."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "user-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            triggered_by_email="mario.rojas@alquimiablue.com",
            dry_run=False,
        )
        assert result.inserted_count == 1
        # Verify triggered_by_user_id propagated to run
        insert_run = next(
            params for sql, params in conn.statements
            if "insert into knowledge_ingestion_runs" in sql
        )
        assert insert_run["triggered_by_user_id"] == "user-uuid"
        # Verify user was looked up (core_users query present)
        user_sqls = [
            sql for sql, _ in conn.statements
            if "core_users" in sql
        ]
        assert len(user_sqls) == 1

    # ------------------------------------------------------------------
    # include_chunks=True (Fase 1.4a)
    # ------------------------------------------------------------------

    @pytest.mark.anyio
    async def test_include_chunks_true_inserts_chunks(self):
        """include_chunks=True + inserted document should create chunks."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
        )
        assert result.inserted_count == 1
        assert result.documents[0].chunk_count >= 1
        assert result.total_chunk_count >= 1
        # Verify chunks were inserted (DELETE + INSERT into knowledge_chunks)
        chunk_insert_sqls = [
            sql for sql, _ in conn.statements
            if "insert into knowledge_chunks" in sql
        ]
        assert len(chunk_insert_sqls) >= 1
        chunk_delete_sqls = [
            sql for sql, _ in conn.statements
            if "delete from knowledge_chunks" in sql
        ]
        assert len(chunk_delete_sqls) == 1
        # Verify embedding_status kept as pending
        all_sql = " ".join(sql for sql, _ in conn.statements)
        assert "embedding_status = 'completed'" not in all_sql
        # Run should have chunk_count set
        update_run = next(
            params for sql, params in conn.statements
            if "update knowledge_ingestion_runs" in sql and "completed" in sql
        )
        assert update_run["chunk_count"] >= 1

    @pytest.mark.anyio
    async def test_include_chunks_true_unchanged_skips_chunks(self):
        """include_chunks=True + unchanged document should NOT touch chunks."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        file_path = Path(root) / "approved" / "test.md"
        expected_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            {"id": "doc-uuid", "content_hash": expected_hash},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
        )
        assert result.unchanged_count == 1
        assert result.documents[0].chunk_count == 0
        assert result.total_chunk_count == 0
        # No knowledge_chunks should have been touched
        chunk_sqls = [
            sql for sql, _ in conn.statements
            if "knowledge_chunks" in sql
        ]
        assert len(chunk_sqls) == 0

    @pytest.mark.anyio
    async def test_include_chunks_dry_run_no_writes(self):
        """dry_run=True + include_chunks=True should not write chunks."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=True,
            include_chunks=True,
        )
        assert result.run_id is None
        assert result.total_chunk_count >= 1  # estimated
        # No DB writes at all
        knowledge_sqls = [
            sql for sql, _ in conn.statements
            if "knowledge_documents" in sql or "knowledge_chunks" in sql
        ]
        assert len(knowledge_sqls) == 0

    @pytest.mark.anyio
    async def test_include_chunks_no_embeddings_called(self):
        """include_chunks=True should not call embeddings/Milvus/Arango."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
        )
        assert result.inserted_count == 1
        assert result.total_chunk_count >= 1
        all_sql = " ".join(sql for sql, _ in conn.statements)
        assert "generate_embeddings" not in all_sql.lower()
        assert "milvus" not in all_sql.lower()
        assert "arango" not in all_sql.lower()
        # embedding_status should remain 'pending'
        assert "embedding_status = 'completed'" not in all_sql
        assert "embedding_status = 'processing'" not in all_sql


# ---------------------------------------------------------------------------
# Semantic chunker (Fase 1.4b)
# ---------------------------------------------------------------------------


class TestSemanticChunker:
    """Tests for semantic_chunker.py wrapper.

    SemanticChunker from langchain_experimental is NOT installed.
    Tests validate error handling and fallback behavior.
    """

    def test_semantic_chunker_not_available_by_default(self):
        from modules.knowledge_ingestion.semantic_chunker import (
            is_semantic_chunker_available,
        )
        assert is_semantic_chunker_available() is False

    def test_chunk_semantic_raises_when_unavailable(self):
        from modules.knowledge_ingestion.semantic_chunker import chunk_semantic

        with pytest.raises(RuntimeError, match="SemanticChunker is not available"):
            chunk_semantic("# Hello\nWorld.")

    def test_chunk_semantic_empty_body_returns_empty(self):
        from modules.knowledge_ingestion.semantic_chunker import chunk_semantic

        with pytest.raises(RuntimeError):
            chunk_semantic("")
        with pytest.raises(RuntimeError):
            chunk_semantic("---\nkey: val\n---")


class TestChunkStrategyStructural:
    """Tests for chunk_strategy='structural' (default) in persist_package_documents."""

    @pytest.mark.anyio
    async def test_structural_default_strategy(self):
        """Default chunk_strategy should be 'structural'."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
        )
        assert result.inserted_count == 1
        assert result.documents[0].chunk_count >= 1

    @pytest.mark.anyio
    async def test_explicit_structural_strategy(self):
        """Explicit chunk_strategy='structural' should work identically."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
            chunk_strategy="structural",
        )
        assert result.inserted_count == 1
        assert result.documents[0].chunk_count >= 1

    @pytest.mark.anyio
    async def test_structural_dry_run_estimates_chunks(self):
        """dry_run with structural should estimate chunk count."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=True,
            include_chunks=True,
            chunk_strategy="structural",
        )
        assert result.run_id is None
        assert result.total_chunk_count >= 1

    @pytest.mark.anyio
    async def test_structural_no_embeddings_milvus_arango(self):
        """structural chunking should not call embeddings/Milvus/Arango."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
            chunk_strategy="structural",
        )
        assert result.inserted_count == 1
        all_sql = " ".join(sql for sql, _ in conn.statements)
        assert "embedding" not in all_sql.lower()
        assert "milvus" not in all_sql.lower()
        assert "arango" not in all_sql.lower()


class TestChunkStrategySemantic:
    """Tests for chunk_strategy='semantic' — should error if not available."""

    @pytest.mark.anyio
    async def test_semantic_unavailable_reports_invalid(self):
        """SemanticChunker not available should report doc as invalid chunk_failed."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
            chunk_strategy="semantic",
        )
        assert result.invalid_count >= 1
        failing = [d for d in result.documents if d.status == DocumentUpsertStatus.INVALID]
        assert len(failing) >= 1
        assert any("SemanticChunker is not available" in e for e in failing[0].errors)

    @pytest.mark.anyio
    async def test_semantic_unavailable_dry_run_raises(self):
        """dry_run with semantic unavailable should propagate RuntimeError."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        with pytest.raises(RuntimeError, match="SemanticChunker is not available"):
            await worker.persist_package_documents(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                package_root=root,
                dry_run=True,
                include_chunks=True,
                chunk_strategy="semantic",
            )

    @pytest.mark.anyio
    async def test_semantic_unchanged_never_calls_chunking(self):
        """Unchanged document with semantic strategy should not call chunking."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        file_path = Path(root) / "approved" / "test.md"
        expected_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            {"id": "doc-uuid", "content_hash": expected_hash},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
            chunk_strategy="semantic",
        )
        assert result.unchanged_count == 1
        assert result.documents[0].chunk_count == 0


class TestChunkStrategyFallback:
    """Tests for chunk_strategy='semantic_with_structural_fallback'."""

    @pytest.mark.anyio
    async def test_fallback_uses_structural_when_semantic_unavailable(self):
        """Fallback strategy should use structural when SemanticChunker unavailable."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            None,
            {"id": "doc-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
            chunk_strategy="semantic_with_structural_fallback",
        )
        assert result.inserted_count == 1
        # With SemanticChunker unavailable, fallback uses structural
        assert result.documents[0].chunk_count >= 1
        assert any("SemanticChunker unavailable" in w for w in result.warnings)
        chunk_sqls = [
            sql for sql, _ in conn.statements
            if "insert into knowledge_chunks" in sql
        ]
        assert len(chunk_sqls) >= 1
        # Verify no embeddings/Milvus/Arango
        all_sql = " ".join(sql for sql, _ in conn.statements)
        assert "embedding" not in all_sql.lower()
        assert "milvus" not in all_sql.lower()
        assert "arango" not in all_sql.lower()

    @pytest.mark.anyio
    async def test_fallback_dry_run_estimates_with_structural(self):
        """Fallback dry run should estimate chunks via structural."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=True,
            include_chunks=True,
            chunk_strategy="semantic_with_structural_fallback",
        )
        assert result.run_id is None
        assert result.total_chunk_count >= 1

    @pytest.mark.anyio
    async def test_fallback_unchanged_skips_chunks(self):
        """Unchanged with fallback strategy should not touch chunks."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        file_path = Path(root) / "approved" / "test.md"
        expected_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
            {"id": "run-uuid"},
            {"id": "doc-uuid", "content_hash": expected_hash},
        ])
        worker = KnowledgeIngestionWorker()
        result = await worker.persist_package_documents(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            package_root=root,
            dry_run=False,
            include_chunks=True,
            chunk_strategy="semantic_with_structural_fallback",
        )
        assert result.unchanged_count == 1
        assert result.documents[0].chunk_count == 0


class TestChunkStrategyInvalid:
    """Tests for invalid chunk_strategy values."""

    @pytest.mark.anyio
    async def test_unknown_strategy_raises(self):
        """Unknown chunk_strategy should raise ValueError."""
        root = _make_package_dir([("test.md", _VALID_FRONTMATTER)])
        conn = _FakeConnection(rows=[
            {"id": "org-uuid"},
            {"id": "workspace-uuid", "organization_id": "org-uuid"},
            {"id": "scope-uuid"},
            {"id": "package-uuid"},
            {"id": "worker-uuid"},
        ])
        worker = KnowledgeIngestionWorker()
        with pytest.raises(ValueError, match="Unknown chunk_strategy"):
            await worker.persist_package_documents(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                package_root=root,
                dry_run=True,
                include_chunks=True,
                chunk_strategy="invalid_strategy",
            )


# ---------------------------------------------------------------------------
# Embedding provider — unit tests with mocked HTTP
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddingProvider:
    def test_missing_api_key_raises_error(self, monkeypatch):
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EmbeddingProviderError,
        )
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OpenAI_Key_JAI_query", raising=False)
        provider = OpenAIEmbeddingProvider(api_key="")
        with pytest.raises(EmbeddingProviderError, match="OPENAI_API_KEY not found"):
            provider.embed_texts(["test"])

    def test_empty_texts_returns_empty(self):
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
        )
        provider = OpenAIEmbeddingProvider(api_key="sk-test")
        result = provider.embed_texts([])
        assert result == []

    def test_dimension_mismatch_raises_error(self):
        from unittest.mock import Mock
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EmbeddingProviderError,
        )
        mock_response = {
            "data": [
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
            ]
        }
        mock_client = Mock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response

        provider = OpenAIEmbeddingProvider(api_key="sk-test", http_client=mock_client)
        with pytest.raises(EmbeddingProviderError, match="dimension mismatch"):
            provider.embed_texts(["hello"])

    def test_successful_embedding(self):
        from unittest.mock import Mock
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EXPECTED_DIMENSIONS,
        )
        fake_embedding = [0.1] * EXPECTED_DIMENSIONS
        mock_response = {
            "data": [
                {"index": 0, "embedding": fake_embedding},
                {"index": 1, "embedding": fake_embedding},
            ]
        }
        mock_client = Mock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response

        provider = OpenAIEmbeddingProvider(api_key="sk-test", http_client=mock_client)
        result = provider.embed_texts(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == EXPECTED_DIMENSIONS
        assert all(isinstance(x, float) for x in result[0])

    def test_non_float_values_raises_error(self):
        from unittest.mock import Mock
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EmbeddingProviderError,
            EXPECTED_DIMENSIONS,
        )
        bad_embedding = [1] * EXPECTED_DIMENSIONS
        mock_response = {
            "data": [
                {"index": 0, "embedding": bad_embedding},
            ]
        }
        mock_client = Mock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response

        provider = OpenAIEmbeddingProvider(api_key="sk-test", http_client=mock_client)
        with pytest.raises(EmbeddingProviderError, match="not all floats"):
            provider.embed_texts(["hello"])

    def test_http_error_raises(self):
        from unittest.mock import Mock
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EmbeddingProviderError,
        )
        mock_client = Mock()
        mock_client.post.return_value.status_code = 401
        mock_client.post.return_value.text = "Unauthorized"

        provider = OpenAIEmbeddingProvider(api_key="sk-bad", http_client=mock_client)
        with pytest.raises(EmbeddingProviderError, match="401"):
            provider.embed_texts(["hello"])

    def test_missing_data_key_raises(self):
        from unittest.mock import Mock
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EmbeddingProviderError,
        )
        mock_client = Mock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = {"not_data": []}

        provider = OpenAIEmbeddingProvider(api_key="sk-test", http_client=mock_client)
        with pytest.raises(EmbeddingProviderError, match="missing 'data'"):
            provider.embed_texts(["hello"])

    def test_count_mismatch_raises(self):
        from unittest.mock import Mock
        from modules.knowledge_ingestion.embedding_provider import (
            OpenAIEmbeddingProvider,
            EmbeddingProviderError,
        )
        mock_client = Mock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = {
            "data": [{"index": 0, "embedding": [0.1]}],
        }

        provider = OpenAIEmbeddingProvider(api_key="sk-test", http_client=mock_client)
        with pytest.raises(EmbeddingProviderError, match="count mismatch"):
            provider.embed_texts(["hello", "world"])


# ---------------------------------------------------------------------------
# Embedding worker — dry_run and repository integration
# ---------------------------------------------------------------------------


class _FakeEmbeddingConn:
    """Minimal fake connection to capture SQL and return canned rows."""

    def __init__(self):
        self.statements: list[tuple[str, dict]] = []
        self._rows: list[dict | None] = []
        self.autocommit = False

    async def set_autocommit(self, val: bool) -> None:
        self.autocommit = val

    async def execute(self, sql: str, params: dict | None = None):
        self.statements.append((sql, params or {}))
        return self

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    async def fetchall(self):
        return self._rows

    def cursor(self):
        return self

    def __aiter__(self):
        return iter([])

    def __anext__(self):
        raise StopAsyncIteration


class TestEmbedPendingChunks:
    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)

    def test_dry_run_no_writes_no_provider_call(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeEmbeddingConn()
        worker = KnowledgeIngestionWorker()
        repo = worker.repository

        async def fake_resolve(*args, **kwargs):
            return type("Ctx", (), {
                "knowledge_scope_id": "scope-1",
                "organization_id": "org-1",
                "workspace_id": "ws-1",
                "to_metadata_dict": lambda: {},
            })()

        async def fake_find_embedding_model(*args, **kwargs):
            return "model-uuid-1"

        async def fake_list_pending(*args, **kwargs):
            return []

        repo.resolve_ingestion_context = fake_resolve
        repo.find_embedding_model_id = fake_find_embedding_model
        repo.list_pending_chunks_for_embedding = fake_list_pending

        result = self._run(worker.embed_pending_chunks(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            dry_run=True,
        ))

        assert result["dry_run"] is True
        assert result["pending_count"] == 0
        assert len(conn.statements) == 0

    def test_dry_run_reports_pending_chunks(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeEmbeddingConn()
        worker = KnowledgeIngestionWorker()
        repo = worker.repository

        async def fake_resolve(*args, **kwargs):
            return type("Ctx", (), {
                "knowledge_scope_id": "scope-1",
                "organization_id": "org-1",
                "workspace_id": "ws-1",
                "to_metadata_dict": lambda: {},
            })()

        async def fake_find_embedding_model(*args, **kwargs):
            return "model-uuid-1"

        async def fake_list_pending(*args, **kwargs):
            return [
                {"chunk_id": "c1", "chunk_index": 0, "title": "Test",
                 "content": "hello world", "content_hash": "abc123",
                 "knowledge_scope_id": "scope-1", "metadata_jsonb": {}},
            ]

        repo.resolve_ingestion_context = fake_resolve
        repo.find_embedding_model_id = fake_find_embedding_model
        repo.list_pending_chunks_for_embedding = fake_list_pending

        result = self._run(worker.embed_pending_chunks(
            conn=conn,
            organization_code="team360_live",
            workspace_code="team360_public_site",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            dry_run=True,
        ))

        assert result["dry_run"] is True
        assert result["pending_count"] == 1
        assert result["chunks"][0]["chunk_id"] == "c1"

    def test_embedding_model_not_found_raises(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeEmbeddingConn()
        worker = KnowledgeIngestionWorker()
        repo = worker.repository

        async def fake_resolve(*args, **kwargs):
            return type("Ctx", (), {
                "knowledge_scope_id": "scope-1",
                "organization_id": "org-1",
                "workspace_id": "ws-1",
                "to_metadata_dict": lambda: {},
            })()

        async def fake_find_embedding_model(*args, **kwargs):
            return None

        repo.resolve_ingestion_context = fake_resolve
        repo.find_embedding_model_id = fake_find_embedding_model

        with pytest.raises(ValueError, match="No active embedding model"):
            self._run(worker.embed_pending_chunks(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                dry_run=True,
            ))

    def test_missing_api_key_reported(self):
        from unittest.mock import patch
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        from modules.knowledge_ingestion.embedding_provider import (
            EmbeddingProviderError,
            OpenAIEmbeddingProvider,
        )

        conn = _FakeEmbeddingConn()
        worker = KnowledgeIngestionWorker()
        repo = worker.repository

        async def fake_resolve(*args, **kwargs):
            return type("Ctx", (), {
                "knowledge_scope_id": "scope-1",
                "organization_id": "org-1",
                "workspace_id": "ws-1",
                "to_metadata_dict": lambda: {},
            })()

        async def fake_find_embedding_model(*args, **kwargs):
            return "model-uuid-1"

        async def fake_list_pending(*args, **kwargs):
            return [
                {"chunk_id": "c1", "chunk_index": 0, "title": "Test",
                 "content": "hello", "content_hash": "abc",
                 "knowledge_scope_id": "scope-1", "metadata_jsonb": {}},
            ]

        async def fake_find_existing(*args, **kwargs):
            return None

        async def fake_update_status(*args, **kwargs):
            conn.statements.append(("update_status", kwargs))

        repo.resolve_ingestion_context = fake_resolve
        repo.find_embedding_model_id = fake_find_embedding_model
        repo.list_pending_chunks_for_embedding = fake_list_pending
        repo.find_existing_chunk_embedding = fake_find_existing
        repo.update_chunk_embedding_status = fake_update_status
        repo.mark_chunk_embedding_failed = fake_update_status

        with patch.object(
            OpenAIEmbeddingProvider, "embed_texts",
            side_effect=EmbeddingProviderError("No API key"),
        ):
            result = self._run(worker.embed_pending_chunks(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                dry_run=False,
            ))

        assert result["error_count"] == 1
        assert any("No API key" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Fase 1.6a — Retrieval via pgvector
# ---------------------------------------------------------------------------


class _FakeRetrievalConn:
    """Minimal fake connection for retrieval tests."""

    def __init__(self, rows: list[dict] | None = None):
        self.statements: list[tuple[str, dict]] = []
        self._rows: list[dict] = list(rows) if rows else []
        self.autocommit = False

    async def set_autocommit(self, val: bool) -> None:
        self.autocommit = val

    async def execute(self, sql: str, params: dict | None = None):
        self.statements.append((sql, params or {}))
        return self

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    async def fetchall(self):
        return self._rows

    def cursor(self):
        return self

    def __aiter__(self):
        return iter([])

    def __anext__(self):
        raise StopAsyncIteration


class TestKnowledgeRetrieval:
    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)

    def _make_context(self, scope_id="scope-1"):
        return type("Ctx", (), {
            "knowledge_scope_id": scope_id,
            "organization_id": "org-1",
            "workspace_id": "ws-1",
            "to_metadata_dict": lambda: {},
        })()

    def test_empty_query_raises(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeRetrievalConn()
        worker = KnowledgeIngestionWorker()
        with pytest.raises(ValueError, match="query is required"):
            self._run(worker.retrieve_knowledge_chunks(
                conn=conn, organization_code="o", workspace_code="w",
                knowledge_scope_code="ks", query="",
            ))

    def test_limit_below_1_raises(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeRetrievalConn()
        worker = KnowledgeIngestionWorker()
        with pytest.raises(ValueError, match="limit must be between 1 and 50"):
            self._run(worker.retrieve_knowledge_chunks(
                conn=conn, organization_code="o", workspace_code="w",
                knowledge_scope_code="ks", query="test", limit=0,
            ))

    def test_limit_above_50_raises(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeRetrievalConn()
        worker = KnowledgeIngestionWorker()
        with pytest.raises(ValueError, match="limit must be between 1 and 50"):
            self._run(worker.retrieve_knowledge_chunks(
                conn=conn, organization_code="o", workspace_code="w",
                knowledge_scope_code="ks", query="test", limit=51,
            ))

    def test_embedding_version_required(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeRetrievalConn()
        worker = KnowledgeIngestionWorker()
        with pytest.raises(ValueError, match="embedding_version is required"):
            self._run(worker.retrieve_knowledge_chunks(
                conn=conn, organization_code="o", workspace_code="w",
                knowledge_scope_code="ks", query="test", embedding_version="",
            ))

    def test_repository_validates_limit(self):
        from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
        repo = KnowledgeIngestionRepository()
        conn = _FakeRetrievalConn()
        with pytest.raises(ValueError, match="limit must be between 1 and 50"):
            self._run(repo.search_chunks_by_embedding(
                conn, knowledge_scope_id="s", query_embedding=[0.1]*1536,
                embedding_version="v1", limit=-1,
            ))

    def test_repository_validates_embedding_version(self):
        from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
        repo = KnowledgeIngestionRepository()
        conn = _FakeRetrievalConn()
        with pytest.raises(ValueError, match="embedding_version is required"):
            self._run(repo.search_chunks_by_embedding(
                conn, knowledge_scope_id="s", query_embedding=[0.1]*1536,
                embedding_version="", limit=5,
            ))

    def test_retrieval_no_llm_no_milvus_no_arango(self):
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        conn = _FakeRetrievalConn()
        worker = KnowledgeIngestionWorker()
        repo = worker.repository

        repo.resolve_ingestion_context = lambda *a, **kw: self._run(
            self._make_context().__class__.__call__()
        )
        # Actually build a simple synchronous mock
        async def fake_resolve(*args, **kwargs):
            return self._make_context()
        repo.resolve_ingestion_context = fake_resolve

        async def fake_search(*args, **kwargs):
            return [
                {
                    "chunk_embedding_id": "emb-1",
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "source_uri": "doc.md",
                    "scope_id": "scope-1",
                    "chunk_index": 0,
                    "title": "Test",
                    "content": "This is a test chunk content " * 20,
                    "node_path": "/test",
                    "chunk_metadata": {"heading_path": "Test"},
                    "embedding_metadata": {"embedding_version": "v1"},
                    "score": 0.95,
                },
            ]
        repo.search_chunks_by_embedding = fake_search

        from unittest.mock import patch
        from modules.knowledge_ingestion.embedding_provider import OpenAIEmbeddingProvider

        with patch.object(OpenAIEmbeddingProvider, "embed_texts", return_value=[[0.1]*1536]):
            result = self._run(worker.retrieve_knowledge_chunks(
                conn=conn,
                organization_code="team360_live",
                workspace_code="team360_public_site",
                knowledge_scope_code="ks_team360_sales_diagnosis",
                query="test query",
                embedding_version="v1",
                limit=5,
            ))

        assert result["result_count"] == 1
        assert result["results"][0]["score"] == 0.95
        assert result["results"][0]["chunk_id"] == "c1"
        assert result["results"][0]["document_id"] == "d1"
        assert result["results"][0]["source_uri"] == "doc.md"
        assert result["results"][0]["chunk_metadata"] == {"heading_path": "Test"}
        assert "Milvus" not in str(result)
        assert "ArangoDB" not in str(result)
        assert "completion" not in str(result).lower()
        assert "llm" not in str(result).lower() or "embedding" in str(result).lower()

    def test_empty_results_when_no_embeddings_ready(self):
        from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
        repo = KnowledgeIngestionRepository()
        conn = _FakeRetrievalConn([])

        result = self._run(repo.search_chunks_by_embedding(
            conn, knowledge_scope_id="s", query_embedding=[0.1]*1536,
            embedding_version="v1", limit=5,
        ))
        assert result == []

    def test_search_includes_metadata_fields(self):
        from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
        repo = KnowledgeIngestionRepository()
        conn = _FakeRetrievalConn([
            {
                "chunk_embedding_id": "emb-1",
                "chunk_id": "c1",
                "document_id": "d1",
                "source_uri": "doc.md",
                "scope_id": "scope-1",
                "chunk_index": 0,
                "title": "Test",
                "content": "content here",
                "node_path": "/test",
                "chunk_metadata": {"heading_path": "H1", "chunk_strategy": "structural"},
                "embedding_metadata": {"embedding_version": "v1"},
                "score": 0.92,
            },
        ])
        result = self._run(repo.search_chunks_by_embedding(
            conn, knowledge_scope_id="s", query_embedding=[0.1]*1536,
            embedding_version="v1", limit=5,
        ))
        assert len(result) == 1
        r = result[0]
        assert r["chunk_metadata"]["heading_path"] == "H1"
        assert r["chunk_metadata"]["chunk_strategy"] == "structural"
        assert r["embedding_metadata"]["embedding_version"] == "v1"
        assert r["score"] == 0.92

    def test_search_respects_knowledge_scope(self):
        """Verify the SQL includes scope_id filter by inspecting the statement."""
        from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
        repo = KnowledgeIngestionRepository()
        conn = _FakeRetrievalConn()

        self._run(repo.search_chunks_by_embedding(
            conn, knowledge_scope_id="scope-specific", query_embedding=[0.1]*1536,
            embedding_version="v1", limit=5,
        ))
        assert len(conn.statements) >= 1
        sql = conn.statements[0][0]
        params = conn.statements[0][1]
        assert params.get("knowledge_scope_id") == "scope-specific"
        assert "embedding_version" in sql or "v1" in str(conn.statements)

    def test_search_respects_min_score(self):
        from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
        repo = KnowledgeIngestionRepository()
        conn = _FakeRetrievalConn()

        self._run(repo.search_chunks_by_embedding(
            conn, knowledge_scope_id="s", query_embedding=[0.1]*1536,
            embedding_version="v1", limit=5, min_score=0.7,
        ))
        sql = conn.statements[0][0]
        assert "min_score" in sql or ">= %(min_score)s" in sql

    def test_retrieval_no_chat_completion(self):
        """Verify the method signature and return contract has no chat completion."""
        import inspect
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        sig = inspect.signature(
            KnowledgeIngestionWorker.retrieve_knowledge_chunks
        )
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "embedding_version" in params
        assert "limit" in params
        assert "min_score" in params
        # Verify the method does NOT have chat/llm params
        assert "messages" not in params
        assert "completion" not in params
        assert "model" not in params or "embedding_model" in params

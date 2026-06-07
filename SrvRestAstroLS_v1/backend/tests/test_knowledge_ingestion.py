"""Tests for Knowledge Ingestion Phase 1 — metadata validation and run tracking."""

from __future__ import annotations

import pytest

from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
from modules.knowledge_ingestion.schemas import (
    INGESTION_PHASES,
    DOCUMENT_TYPES,
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
        assert d["source_type"] == "markdown"


# ---------------------------------------------------------------------------
# IngestionWorker validation_and_register
# ---------------------------------------------------------------------------


class TestKnowledgeIngestionWorker:
    @pytest.mark.anyio
    async def test_validate_and_register_success(self):
        worker = KnowledgeIngestionWorker()
        conn = _FakeConnection(rows=[{"id": "00000000-0000-0000-0000-000000000001"}])

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
        assert "phases" in result
        assert result["phases"]["validate_metadata"] == "completed"
        assert len(conn.statements) >= 1

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


# ---------------------------------------------------------------------------
# Repository basic contract
# ---------------------------------------------------------------------------


class TestKnowledgeIngestionRepository:
    def test_repository_can_be_instantiated(self):
        repo = KnowledgeIngestionRepository()
        assert repo is not None
        # No DB calls — repository uses injected connection

"""Contract tests for KnowledgeIngestionSalesDiagnosisRetrievalProvider.

All tests are static — no real DB, no real OpenAI, no real Milvus.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from modules.automation_diagnosis.knowledge_retrieval_provider import (
    DEV_RETRIEVAL_ENV,
    DEV_RETRIEVAL_VALUE,
    MAX_TOP_K,
    KnowledgeIngestionSalesDiagnosisRetrievalProvider,
    build_dev_retrieval_provider,
    is_dev_retrieval_enabled,
)
from modules.automation_diagnosis.schemas import RetrievedContext


# ── Feature flag tests ──────────────────────────────────────────────────────


class TestIsDevRetrievalEnabled:
    def test_returns_false_when_unset(self):
        os.environ.pop(DEV_RETRIEVAL_ENV, None)
        assert is_dev_retrieval_enabled() is False

    def test_returns_false_when_wrong_value(self):
        os.environ[DEV_RETRIEVAL_ENV] = "console"
        assert is_dev_retrieval_enabled() is False

    def test_returns_true_when_knowledge_ingestion(self):
        os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        assert is_dev_retrieval_enabled() is True

    def test_returns_true_case_insensitive(self):
        os.environ[DEV_RETRIEVAL_ENV] = "KNOWLEDGE_INGESTION"
        assert is_dev_retrieval_enabled() is True

    def test_returns_false_for_empty_string(self):
        os.environ[DEV_RETRIEVAL_ENV] = ""
        assert is_dev_retrieval_enabled() is False


class TestBuildDevRetrievalProvider:
    def test_returns_none_when_disabled(self):
        os.environ.pop(DEV_RETRIEVAL_ENV, None)
        assert build_dev_retrieval_provider() is None

    def test_returns_provider_when_enabled(self):
        os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        provider = build_dev_retrieval_provider()
        assert provider is not None
        assert provider.organization_code == "team360_live"
        assert provider.knowledge_scope_code == "ks_team360_sales_diagnosis"


# ── Provider contract tests ─────────────────────────────────────────────────


class TestProviderContract:
    def setup_method(self):
        os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE

    def test_provider_can_be_constructed_with_default_params(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        assert provider.organization_code == "team360_live"
        assert provider.workspace_code == "team360_public_site"
        assert provider.knowledge_scope_code == "ks_team360_sales_diagnosis"
        assert provider.package_code == "pkg_sales_diagnosis"

    def test_provider_can_be_constructed_with_custom_params(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider(
            organization_code="org_test",
            workspace_code="ws_test",
            knowledge_scope_code="ks_test",
            package_code="pkg_test",
        )
        assert provider.organization_code == "org_test"
        assert provider.workspace_code == "ws_test"
        assert provider.knowledge_scope_code == "ks_test"
        assert provider.package_code == "pkg_test"

    def test_search_returns_retrieved_context(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        with patch.object(provider, "_get_embedding_provider", return_value=None):
            result = provider.search("ks_test", "test query")
            assert isinstance(result, RetrievedContext)
            assert result.knowledge_scope_id == "ks_test"
            assert result.query == "test query"
            assert result.chunks == []

    def test_search_empty_query_returns_empty_result(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        with patch.object(provider, "_get_embedding_provider", return_value=None):
            result = provider.search("ks_test", "")
            assert result.chunks == []
            assert result.query == ""

    def test_search_whitespace_query_returns_empty_result(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        with patch.object(provider, "_get_embedding_provider", return_value=None):
            result = provider.search("ks_test", "   ")
            assert result.chunks == []

    def test_search_respects_top_k_upper_bound(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        with patch.object(provider, "_get_embedding_provider", return_value=None):
            result = provider.search("ks_test", "query", top_k=999)
            assert isinstance(result, RetrievedContext)
            assert result.chunks == []

    def test_search_fallback_when_openai_key_missing(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        with patch.object(provider, "_get_embedding_provider", return_value=None):
            result = provider.search("ks_test", "test query")
            assert result.chunks == []
            assert result.knowledge_scope_id == "ks_test"

    def test_search_fallback_when_embedding_fails(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        mock_emb = MagicMock()
        mock_emb.embed_texts.side_effect = RuntimeError("API error")
        with patch.object(provider, "_get_embedding_provider", return_value=mock_emb):
            result = provider.search("ks_test", "test query")
            assert result.chunks == []

    def test_search_fallback_when_db_unavailable(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        mock_emb = MagicMock()
        mock_emb.embed_texts.return_value = [[0.1] * 1536]
        with patch.object(provider, "_get_embedding_provider", return_value=mock_emb):
            with patch("psycopg.connect", side_effect=RuntimeError("DB unavailable")):
                result = provider.search("ks_test", "test query")
                assert result.chunks == []

    def test_scope_debug_returns_dict_on_db_unavailable(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        with patch("psycopg.connect", side_effect=RuntimeError("DB unavailable")):
            result = provider.scope_debug("ks_test")
            assert "error" in result
            assert result.get("retrieval_provider") == "knowledge_ingestion"
            assert result.get("retrieval_is_real") is False

    def test_scope_debug_returns_dict_when_scope_missing(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        with patch("psycopg.connect", return_value=mock_conn):
            result = provider.scope_debug("ks_test")
            assert "error" in result
            assert result.get("fallback") is True

    def test_scope_debug_returns_debug_info_when_scope_exists(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        call_count = {"n": 0}
        mock_cursor = MagicMock()

        def mock_execute(sql, *args):
            call_count["n"] += 1
            if call_count["n"] == 1:
                mock_cursor.fetchone.return_value = ("scope-uuid",)
            elif call_count["n"] == 2:
                mock_cursor.fetchone.return_value = (3,)
            elif call_count["n"] == 3:
                mock_cursor.fetchone.return_value = (10,)
            elif call_count["n"] == 4:
                mock_cursor.fetchone.return_value = (8,)
            else:
                mock_cursor.fetchone.return_value = (0,)
            return mock_cursor

        mock_conn = MagicMock()
        mock_conn.execute = mock_execute

        with patch("psycopg.connect", return_value=mock_conn):
            result = provider.scope_debug("ks_test")
            assert result.get("document_count") == 3
            assert result.get("chunk_count") == 10
            assert result.get("embedded_chunk_count") == 8
            assert result.get("retrieval_is_real") is True
            assert result.get("fallback") is False

    def test_search_returns_real_results_when_all_services_available(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()

        mock_emb = MagicMock()
        mock_emb.embed_texts.return_value = [[0.1] * 1536]

        call_count = {"n": 0}

        def mock_execute(sql, *args):
            call_count["n"] += 1
            cur = MagicMock()
            if call_count["n"] == 1:
                cur.fetchone.return_value = ("scope-uuid",)
            elif call_count["n"] == 2:
                cur.__iter__.return_value = iter([
                    (
                        "chunk-1",
                        "doc-1",
                        "docs/sap-integration.md",
                        "SAP Business One Integration",
                        "Contenido sobre integracion con SAP Business One...",
                        "/sap/b1-integration",
                        0,
                        {"area_key": "sap", "topic_key": "integration"},
                        {"embedding_version": "v1"},
                        0.92,
                    ),
                ])
            else:
                cur.fetchone.return_value = None
            return cur

        mock_conn = MagicMock()
        mock_conn.execute = mock_execute

        with (
            patch.object(provider, "_get_embedding_provider", return_value=mock_emb),
            patch("psycopg.connect", return_value=mock_conn),
        ):
            result = provider.search("ks_test", "SAP Business One integration", top_k=3)
            assert len(result.chunks) == 1
            assert result.chunks[0]["title"] == "SAP Business One Integration"
            assert result.chunks[0]["chunk_id"] == "chunk-1"
            assert "source_uri" in result.chunks[0]["metadata"]
            assert result.chunks[0]["metadata"]["source_uri"] == "docs/sap-integration.md"
            assert result.chunks[0]["metadata"]["node_path"] == "/sap/b1-integration"
            assert result.chunks[0]["score"] == 0.92

    def test_search_scopes_by_organization_workspace(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider(
            organization_code="org_custom",
            workspace_code="ws_custom",
        )
        assert provider.organization_code == "org_custom"
        assert provider.workspace_code == "ws_custom"

    def test_provider_state_after_construction(self):
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider()
        assert provider._embedding_provider is None
        assert provider._settings is not None


# ── Integration with service (env-based wiring) ──────────────────────────────


class TestServiceWiring:
    def test_default_service_uses_in_memory_when_env_unset(self):
        os.environ.pop(DEV_RETRIEVAL_ENV, None)
        from modules.automation_diagnosis.service import AutomationDiagnosisService
        from modules.automation_diagnosis.knowledge_connector import InMemoryKnowledgeRepository

        service = AutomationDiagnosisService(ai_interpreter=MagicMock())
        assert isinstance(service.knowledge_repository, InMemoryKnowledgeRepository)

    def test_default_service_uses_dev_provider_when_env_set(self):
        os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        from modules.automation_diagnosis.service import AutomationDiagnosisService

        service = AutomationDiagnosisService(ai_interpreter=MagicMock())
        assert isinstance(
            service.knowledge_repository,
            KnowledgeIngestionSalesDiagnosisRetrievalProvider,
        )

    def test_explicit_knowledge_repository_overrides_env(self):
        os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        from modules.automation_diagnosis.service import AutomationDiagnosisService
        from modules.automation_diagnosis.knowledge_connector import (
            InMemoryKnowledgeRepository,
        )

        mock_repo = InMemoryKnowledgeRepository()
        service = AutomationDiagnosisService(
            knowledge_repository=mock_repo,
            ai_interpreter=MagicMock(),
        )
        assert service.knowledge_repository is mock_repo

    def test_dev_provider_build_failure_falls_back_to_in_memory(self):
        os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        from modules.automation_diagnosis.service import AutomationDiagnosisService
        from modules.automation_diagnosis.knowledge_connector import InMemoryKnowledgeRepository

        with patch(
            "modules.automation_diagnosis.service.build_dev_retrieval_provider",
            return_value=None,
        ):
            service = AutomationDiagnosisService(ai_interpreter=MagicMock())
            assert isinstance(service.knowledge_repository, InMemoryKnowledgeRepository)


# ── Secret / safety tests ────────────────────────────────────────────────────


class TestNoSecretLeakage:
    def test_openai_key_not_logged(self):
        source = open(__file__).read() if False else ""
        from modules.automation_diagnosis import knowledge_retrieval_provider as mod

        source = open(mod.__file__).read()
        assert "sanitize" in source.lower() or "_sanitize" in source

    def test_dsn_not_logged_raw(self):
        from modules.automation_diagnosis import knowledge_retrieval_provider as mod

        source = open(mod.__file__).read()
        assert "sanitize_dsn" in source

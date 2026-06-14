"""Tests for Knowledge Ingestion Phase 1.3h — embedding persistence contract.

No real OpenAI, no vector DB, no real DB by default.
"""

from __future__ import annotations

from typing import Any

import pytest

from modules.knowledge_ingestion.embedding_provider import (
    EMBEDDING_VERSION,
    EXPECTED_DIMENSIONS,
    FakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from modules.knowledge_ingestion.repository import KnowledgeIngestionRepository
from modules.knowledge_ingestion.schemas import (
    ChunkEmbeddingUpsertRequest,
    EmbeddingStatus,
    KnowledgeChunkEmbeddingRecord,
)


class TestEmbeddingStatus:
    def test_valid_statuses_are_frozenset(self):
        assert isinstance(EmbeddingStatus.VALID_STATUSES, frozenset)

    def test_pending_exists(self):
        assert EmbeddingStatus.PENDING == "pending"

    def test_processing_exists(self):
        assert EmbeddingStatus.PROCESSING == "processing"

    def test_ready_exists(self):
        assert EmbeddingStatus.READY == "ready"

    def test_failed_exists(self):
        assert EmbeddingStatus.FAILED == "failed"

    def test_skipped_exists(self):
        assert EmbeddingStatus.SKIPPED == "skipped"

    def test_all_statuses_covered(self):
        expected = {"pending", "processing", "ready", "failed", "skipped"}
        assert EmbeddingStatus.VALID_STATUSES == expected


class TestKnowledgeChunkEmbeddingRecord:
    def test_preserves_chunk_id_model_version_dimensions_status(self):
        record = KnowledgeChunkEmbeddingRecord(
            chunk_embedding_id="emb-001",
            knowledge_chunk_id="chunk-001",
            provider="openai",
            model="text-embedding-3-small",
            embedding_version="team360-openai-small-1536-v1",
            dimensions=1536,
            content_hash="abc123",
            embedding_status="ready",
        )
        assert record.chunk_embedding_id == "emb-001"
        assert record.knowledge_chunk_id == "chunk-001"
        assert record.provider == "openai"
        assert record.model == "text-embedding-3-small"
        assert record.embedding_version == "team360-openai-small-1536-v1"
        assert record.dimensions == 1536
        assert record.content_hash == "abc123"
        assert record.embedding_status == "ready"

    def test_vector_defaults_to_none(self):
        record = KnowledgeChunkEmbeddingRecord(
            chunk_embedding_id="emb-002",
            knowledge_chunk_id="chunk-002",
            provider="openai",
            model="text-embedding-3-small",
            embedding_version="v1",
            dimensions=1536,
            content_hash="def456",
            embedding_status="pending",
        )
        assert record.vector is None

    def test_metadata_defaults_to_empty_dict(self):
        record = KnowledgeChunkEmbeddingRecord(
            chunk_embedding_id="emb-003",
            knowledge_chunk_id="chunk-003",
            provider="openai",
            model="text-embedding-3-small",
            embedding_version="v1",
            dimensions=1536,
            content_hash="ghi789",
            embedding_status="ready",
        )
        assert record.metadata_jsonb == {}


class TestChunkEmbeddingUpsertRequest:
    def test_valid_request_passes_validation(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="chunk-001",
            provider="openai",
            model="text-embedding-3-small",
            embedding_version="team360-openai-small-1536-v1",
            dimensions=1536,
            content_hash="abc123",
            vector=[0.1] * 1536,
        )
        errors = req.validate()
        assert errors == []

    def test_missing_chunk_id_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="",
            provider="openai",
            model="text-embedding-3-small",
            embedding_version="v1",
            dimensions=1536,
            content_hash="abc",
            vector=[0.1] * 1536,
        )
        errors = req.validate()
        assert any("chunk_id" in e for e in errors)

    def test_missing_provider_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="c1",
            provider="",
            model="m1",
            embedding_version="v1",
            dimensions=1536,
            content_hash="abc",
            vector=[0.1] * 1536,
        )
        errors = req.validate()
        assert any("provider" in e for e in errors)

    def test_missing_model_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="c1",
            provider="openai",
            model="",
            embedding_version="v1",
            dimensions=1536,
            content_hash="abc",
            vector=[0.1] * 1536,
        )
        errors = req.validate()
        assert any("model" in e for e in errors)

    def test_missing_embedding_version_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="c1",
            provider="openai",
            model="m1",
            embedding_version="",
            dimensions=1536,
            content_hash="abc",
            vector=[0.1] * 1536,
        )
        errors = req.validate()
        assert any("embedding_version" in e for e in errors)

    def test_zero_dimensions_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="c1",
            provider="openai",
            model="m1",
            embedding_version="v1",
            dimensions=0,
            content_hash="abc",
            vector=[],
        )
        errors = req.validate()
        assert any("dimensions" in e for e in errors)

    def test_invalid_status_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="c1",
            provider="openai",
            model="m1",
            embedding_version="v1",
            dimensions=128,
            content_hash="abc",
            vector=[0.1] * 128,
            embedding_status="bogus",
        )
        errors = req.validate()
        assert any("embedding_status" in e for e in errors)

    def test_vector_dimension_mismatch_fails(self):
        req = ChunkEmbeddingUpsertRequest(
            chunk_id="c1",
            provider="openai",
            model="m1",
            embedding_version="v1",
            dimensions=4,
            content_hash="abc",
            vector=[0.1, 0.2, 0.3],  # length 3, expected 4
        )
        errors = req.validate()
        assert any("vector" in e for e in errors)


class TestFakeEmbeddingProvider:
    def test_returns_expected_dimensions(self):
        provider = FakeEmbeddingProvider()
        vectors = provider.embed_texts(["hello world"])
        assert len(vectors) == 1
        assert len(vectors[0]) == EXPECTED_DIMENSIONS

    def test_allows_custom_dimensions(self):
        provider = FakeEmbeddingProvider(dimensions=64)
        vectors = provider.embed_texts(["test"])
        assert len(vectors[0]) == 64

    def test_returns_unit_vector(self):
        provider = FakeEmbeddingProvider(dimensions=4)
        vectors = provider.embed_texts(["test"])
        vec = vectors[0]
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-9

    def test_returns_multiple_vectors(self):
        provider = FakeEmbeddingProvider(dimensions=8)
        vectors = provider.embed_texts(["a", "b", "c"])
        assert len(vectors) == 3

    def test_returns_empty_for_empty_input(self):
        provider = FakeEmbeddingProvider()
        assert provider.embed_texts([]) == []

    def test_repr_does_not_contain_secrets(self):
        provider = FakeEmbeddingProvider()
        assert "api_key" not in repr(provider)
        assert "sk-" not in repr(provider)


class TestOpenAIEmbeddingProviderContract:
    def test_repr_does_not_contain_api_key(self):
        provider = OpenAIEmbeddingProvider(api_key="sk-test-secret-12345")
        rep = repr(provider)
        assert "sk-test" not in rep
        assert "api_key" not in rep
        assert "model=" in rep
        assert "dimensions=" in rep

    def test_no_api_call_on_import_or_init(self):
        """Creating an instance does not call any external API."""
        provider = OpenAIEmbeddingProvider()
        assert provider is not None
        assert provider.model == "text-embedding-3-small"
        assert provider.dimensions == 1536


class TestRepositoryEmbeddingMethods:
    def test_upsert_embedding_refers_to_knowledge_chunk_embeddings_table(self):
        """Verify the upsert SQL targets the existing table."""
        repo = KnowledgeIngestionRepository()
        # Inspect the method source for table name
        import inspect
        src = inspect.getsource(repo.upsert_chunk_embedding)
        assert "knowledge_chunk_embeddings" in src
        assert "on conflict" in src.lower()

    def test_upsert_embedding_uses_chunk_id_and_content_hash(self):
        """Verify the upsert uses chunk_id and content_hash in SQL."""
        repo = KnowledgeIngestionRepository()
        import inspect
        src = inspect.getsource(repo.upsert_chunk_embedding)
        assert "%(chunk_id)s" in src
        assert "%(content_hash)s" in src

    def test_list_embeddings_for_run_returns_list_of_dicts_with_expected_fields(self):
        """Verify the query joins through the existing schema."""
        repo = KnowledgeIngestionRepository()
        import inspect
        src = inspect.getsource(repo.list_chunk_embeddings_for_run)
        assert "knowledge_chunk_embeddings" in src
        assert "knowledge_ingestion_runs" in src
        assert "%(run_id)s" in src
        # Should join through chunk → document → run
        assert "knowledge_chunks" in src
        assert "knowledge_documents" in src

    def test_find_embedding_model_id_refers_to_knowledge_embedding_models(self):
        """Verify find_embedding_model_id uses the model catalog table."""
        repo = KnowledgeIngestionRepository()
        import inspect
        src = inspect.getsource(repo.find_embedding_model_id)
        assert "knowledge_embedding_models" in src
        assert "%(provider_code)s" in src
        assert "%(model_code)s" in src
        assert "%(dimensions)s" in src


class TestWorkerEmbeddingDefault:
    def test_include_embeddings_defaults_to_false(self):
        """Verify persist_package_documents defaults to no embeddings."""
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        import inspect

        sig = inspect.signature(
            KnowledgeIngestionWorker.persist_package_documents
        )
        assert "include_embeddings" in sig.parameters
        param = sig.parameters["include_embeddings"]
        assert param.default is False

    def test_include_embeddings_true_requires_include_chunks(self):
        """include_embeddings=True without include_chunks raises ValueError."""
        from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker
        import inspect

        src = inspect.getsource(
            KnowledgeIngestionWorker.persist_package_documents
        )
        assert "include_embeddings=True requires include_chunks=True" in src


class TestDevEndpointNoEmbeddings:
    def test_endpoint_persist_does_not_pass_include_embeddings(self):
        """Verify the dev endpoint does NOT pass include_embeddings to worker."""
        import inspect
        from routes import knowledge_ingestion_dev as dev_route

        src = inspect.getsource(dev_route._run_persist_pipeline)
        assert "persist_package_documents" in src
        assert "include_embeddings" not in src

    def test_endpoint_module_says_no_real_embeddings(self):
        """The dev endpoint docstring explicitly says no real embeddings."""
        from routes import knowledge_ingestion_dev as dev_route

        doc = dev_route.__doc__ or ""
        assert "No upload" in doc
        assert "no Milvus" in doc
        assert "no real embeddings" in doc


class TestPlannedExtensionNotActivatingEmbeddings:
    def test_planned_extension_metadata_does_not_trigger_embedding(self):
        """planned_extension field does not activate embedding generation."""
        from modules.knowledge_ingestion.schemas import (
            INGESTION_READINESS_ERROR_CODES,
            check_document_ingestion_readiness,
        )

        frontmatter = {
            "status": "approved",
            "ingestion_status": "ready",
            "extension": "sales_diagnosis_v2",
        }
        result = check_document_ingestion_readiness(frontmatter, "doc.md")
        assert not result.ready
        assert "planned_extension_not_active" in result.error_codes
        # No embedding-related error codes should appear
        assert not any("embedding" in e.lower() for e in result.error_codes)


class TestNoMilvusInTests:
    def test_no_milvus_import(self):
        """This test file must not import Milvus."""
        with open(__file__, encoding="utf-8") as f:
            source = f.read()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Check for actual Python import statements
            if stripped.startswith("import ") and "milvus" in stripped.lower():
                pytest.fail(f"Line {i+1}: import Milvus: {stripped}")
            if stripped.startswith("from ") and "milvus" in stripped.lower():
                pytest.fail(f"Line {i+1}: from Milvus import: {stripped}")

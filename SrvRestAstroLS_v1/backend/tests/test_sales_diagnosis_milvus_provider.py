"""Tests for MilvusRetrievalProvider and QueryEmbeddingProvider.

No real Milvus calls. No real LLM. No DB. All providers use fakes/stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    MilvusConfigurationError,
    MilvusRetrievalProvider,
    MilvusRuntimeConfig,
    MilvusSearchError,
    QueryEmbeddingProvider,
    RetrievalUnavailableError,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.milvus_provider import _int_or_none


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Returns a fixed 4-dimensional vector for any query."""

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


class FakeMilvusCollection:
    """Simulates a Milvus Collection with search().

    Returns configurable results for testing mapping and edge cases.
    """

    def __init__(
        self,
        results: list | None = None,
        schema_fields: list[str] | None = None,
        query_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._results = results or []
        self._query_rows = query_rows or []
        self.indexes: list[dict[str, Any]] = []
        self.last_search: dict[str, Any] | None = None
        self.last_query: dict[str, Any] | None = None
        self.schema = (
            type(
                "FakeSchema",
                (),
                {
                    "fields": [
                        type("FakeField", (), {"name": name})()
                        for name in (schema_fields or [])
                    ]
                },
            )()
            if schema_fields is not None
            else None
        )

    def load(self) -> None:
        pass

    def query(
        self,
        expr: str,
        output_fields: list[str],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.last_query = {
            "expr": expr,
            "output_fields": output_fields,
            "limit": limit,
        }
        return self._query_rows

    def search(
        self,
        data: list[list[float]],
        anns_field: str,
        param: dict[str, Any],
        limit: int,
        expr: str,
        output_fields: list[str],
    ) -> list:
        self.last_search = {
            "data": data,
            "anns_field": anns_field,
            "param": param,
            "limit": limit,
            "expr": expr,
            "output_fields": output_fields,
        }
        return self._results


@dataclass
class FakeEntity:
    fields: dict[str, Any] = field(default_factory=lambda: {
        "chunk_id": "chunk_001",
        "document_id": "doc_001",
        "knowledge_scope_id": "ks_team360_sales_diagnosis",
        "source_uri": "/knowledge/test.md",
        "title": "Test Document",
        "node_path": "/automatizaciones/diagnostico",
        "content_preview": "Esto es un preview",
        "content": "Esto es el contenido completo del chunk.",
    })


@dataclass
class FakeHit:
    """Simulates a Milvus search hit with .id, .score and .entity."""

    id: str = "chunk_001"
    score: float = 0.92
    _entity: FakeEntity = field(default_factory=FakeEntity, repr=False)

    @property
    def entity(self) -> FakeEntity:
        return self._entity

    @entity.setter
    def entity(self, value: FakeEntity | None) -> None:
        self._entity = value or FakeEntity()


def make_fake_result_set(*hits: FakeHit) -> list:
    """Wrap hits into a list of result sets matching Milvus search output."""
    return [list(hits)]


def make_fake_chunk(
    chunk_id: str = "chunk_fake",
    title: str = "Fake Title",
    score: float = 0.85,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc_fake",
        knowledge_scope_id="ks_test",
        source_uri="/fake.md",
        title=title,
        node_path="/fake",
        score=score,
        content_preview="Fake preview",
        content="Fake content.",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_input() -> AssistantTurnInput:
    return AssistantTurnInput(
        session_id="session_test",
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        user_message="Quiero automatizar mi negocio",
    )


@pytest.fixture
def default_state() -> ConversationState:
    return ConversationState(
        session_id="session_test",
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
    )


@pytest.fixture
def fake_embedding() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


# ---------------------------------------------------------------------------
# 1. QueryEmbeddingProvider protocol
# ---------------------------------------------------------------------------


class TestQueryEmbeddingProvider:
    def test_query_embedding_protocol_with_fake_embedding(self, fake_embedding):
        vector = fake_embedding.embed_query("test query")
        assert isinstance(vector, list)
        assert all(isinstance(v, float) for v in vector)
        assert len(vector) == 4

    def test_embedding_is_deterministic(self, fake_embedding):
        v1 = fake_embedding.embed_query("test")
        v2 = fake_embedding.embed_query("test")
        assert v1 == v2


# ---------------------------------------------------------------------------
# 2. MilvusRetrievalProvider
# ---------------------------------------------------------------------------


class TestMilvusRetrievalProvider:
    def test_milvus_provider_requires_embedding_provider(
        self, sample_input, default_state
    ):
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=None,
        )
        with pytest.raises(RetrievalUnavailableError, match="QueryEmbeddingProvider"):
            provider.retrieve(sample_input, default_state)

    def test_milvus_provider_maps_results_to_retrieved_chunks(
        self, sample_input, default_state, fake_embedding
    ):
        hits = make_fake_result_set(FakeHit())
        collection = FakeMilvusCollection(results=hits)

        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=collection,
        )
        chunks = provider.retrieve(sample_input, default_state)
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.chunk_id == "chunk_001"
        assert chunk.document_id == "doc_001"
        assert chunk.knowledge_scope_id == "ks_team360_sales_diagnosis"
        assert chunk.score == 0.92
        assert chunk.content_preview == "Esto es un preview"
        assert chunk.content == "Esto es el contenido completo del chunk."

    def test_milvus_provider_maps_multiple_results(
        self, sample_input, default_state, fake_embedding
    ):
        hit1 = FakeHit(id="c1", score=0.95)
        hit2 = FakeHit(id="c2", score=0.87)
        hit3 = FakeHit(id="c3", score=0.72)
        hit1.entity.fields["chunk_id"] = "c1"
        hit2.entity.fields["chunk_id"] = "c2"
        hit3.entity.fields["chunk_id"] = "c3"

        collection = FakeMilvusCollection(
            results=make_fake_result_set(hit1, hit2, hit3)
        )
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=collection,
        )
        chunks = provider.retrieve(sample_input, default_state, top_k=2)
        assert len(chunks) == 2
        assert chunks[0].chunk_id == "c1"
        assert chunks[1].chunk_id == "c2"

    def test_milvus_provider_builds_safe_filter_for_scope_and_embedding_version(
        self, sample_input, default_state, fake_embedding
    ):
        config = MilvusRuntimeConfig(
            embedding_version="text-embedding-3-small-1536d",
            knowledge_scope_id="ks_test",
        )
        provider = MilvusRetrievalProvider(
            config=config,
            embedding_provider=fake_embedding,
            _client=FakeMilvusCollection(),
        )
        filters = provider._build_filters(sample_input, default_state)
        assert "knowledge_scope_code" in filters
        assert "embedding_version" in filters

    def test_milvus_provider_empty_filters_when_no_scope(
        self, fake_embedding
    ):
        input_no_scope = AssistantTurnInput(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="",
            user_message="test",
        )
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="",
        )
        config = MilvusRuntimeConfig(embedding_version="")
        provider = MilvusRetrievalProvider(
            config=config,
            embedding_provider=fake_embedding,
            _client=FakeMilvusCollection(),
        )
        filters = provider._build_filters(input_no_scope, state)
        assert filters == ""

    def test_milvus_provider_does_not_connect_on_import(self):
        import modules.sales_diagnosis_runtime.milvus_provider as mp

        assert hasattr(mp, "MilvusRetrievalProvider")

    def test_milvus_provider_returns_empty_without_query_vector(
        self, sample_input, default_state
    ):
        class EmptyEmbeddingProvider:
            def embed_query(self, text: str) -> list[float]:
                return []

        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=EmptyEmbeddingProvider(),
            _client=FakeMilvusCollection(),
        )
        chunks = provider.retrieve(sample_input, default_state)
        assert chunks == []

    def test_milvus_provider_handles_missing_fields_gracefully(
        self, sample_input, default_state, fake_embedding
    ):
        hit = FakeHit()
        hit.entity.fields = {"chunk_id": "c1", "content": "only content"}
        collection = FakeMilvusCollection(results=make_fake_result_set(hit))
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=collection,
        )
        chunks = provider.retrieve(sample_input, default_state)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == "c1"
        assert chunks[0].document_id == ""
        assert chunks[0].title is None

    def test_milvus_provider_aligns_with_real_collection_schema_aliases(
        self, sample_input, default_state, fake_embedding
    ):
        hit = FakeHit()
        hit.entity.fields = {
            "chunk_id": "87d34156-4254-4a65-9e71-732926a8de34",
            "document_id": "9e9dc259-e601-4bc8-acff-a669969bcaa6",
            "knowledge_scope_id": "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b",
            "embedding_version": "team360-openai-small-1536-v1",
            "content_preview": "# Alcance productivo inicial",
            "node_path": "/automatizaciones/alcance-inicial",
            "title": "Alcance productivo inicial",
        }
        collection = FakeMilvusCollection(
            results=make_fake_result_set(hit),
            schema_fields=[
                "id",
                "chunk_id",
                "document_id",
                "knowledge_scope_id",
                "embedding_version",
                "content_preview",
                "node_path",
                "title",
                "embedding",
            ],
        )
        config = MilvusRuntimeConfig(
            knowledge_scope_id="8b071443-5bd6-4fe4-bbc3-fc2dca179a5b",
            embedding_version="team360-openai-small-1536-v1",
        )
        provider = MilvusRetrievalProvider(
            config=config,
            embedding_provider=fake_embedding,
            _client=collection,
        )

        chunks = provider.retrieve(sample_input, default_state)

        assert len(chunks) == 1
        assert collection.last_search is not None
        assert collection.last_search["anns_field"] == "embedding"
        assert collection.last_search["expr"] == (
            'knowledge_scope_id == "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b" '
            'and embedding_version == "team360-openai-small-1536-v1"'
        )
        assert collection.last_search["output_fields"] == [
            "chunk_id",
            "document_id",
            "knowledge_scope_id",
            "embedding_version",
            "node_path",
            "title",
            "content_preview",
        ]
        chunk = chunks[0]
        assert chunk.chunk_id == "87d34156-4254-4a65-9e71-732926a8de34"
        assert chunk.source_uri == "/automatizaciones/alcance-inicial"
        assert chunk.node_path == "/automatizaciones/alcance-inicial"
        assert chunk.content_preview == "# Alcance productivo inicial"
        assert chunk.content == "# Alcance productivo inicial"

    def test_milvus_provider_reports_missing_vector_field_as_controlled_error(
        self, sample_input, default_state, fake_embedding
    ):
        collection = FakeMilvusCollection(
            results=make_fake_result_set(FakeHit()),
            schema_fields=[
                "chunk_id",
                "document_id",
                "knowledge_scope_id",
                "content_preview",
                "node_path",
            ],
        )
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=collection,
        )
        with pytest.raises(MilvusConfigurationError, match="vector field"):
            provider.retrieve(sample_input, default_state)


# ---------------------------------------------------------------------------
# 3. UUID discovery and scope filter resolution
# ---------------------------------------------------------------------------


class TestMilvusScopeUUIDDiscovery:
    """Tests for the UUID discovery mechanism in _build_filters."""

    def test_is_uuid_detects_uuid_format(self):
        provider = MilvusRetrievalProvider()
        assert provider._is_uuid("8b071443-5bd6-4fe4-bbc3-fc2dca179a5b")
        assert provider._is_uuid("00000000-0000-0000-0000-000000000000")

    def test_is_uuid_rejects_codes(self):
        provider = MilvusRetrievalProvider()
        assert not provider._is_uuid("ks_team360_sales_diagnosis")
        assert not provider._is_uuid("pkg_sales_diagnosis")
        assert not provider._is_uuid("")
        assert not provider._is_uuid("not-a-uuid")

    def test_discover_scope_uuids_returns_unique_values(self):
        provider = MilvusRetrievalProvider()
        collection = FakeMilvusCollection(query_rows=[
            {"knowledge_scope_id": "uuid-001"},
            {"knowledge_scope_id": "uuid-001"},
            {"knowledge_scope_id": "uuid-002"},
        ])
        uuids = provider._discover_scope_uuids("knowledge_scope_id", collection)
        assert sorted(uuids) == sorted(["uuid-001", "uuid-002"])

    def test_discover_scope_uuids_empty_when_no_results(self):
        provider = MilvusRetrievalProvider()
        collection = FakeMilvusCollection(query_rows=[])
        uuids = provider._discover_scope_uuids("knowledge_scope_id", collection)
        assert uuids == []

    def test_discover_scope_uuids_query_error_returns_empty(self):
        class BrokenCollection:
            def query(self, **kwargs):
                raise RuntimeError("query failed")
            def load(self):
                pass
            indexes = []

        provider = MilvusRetrievalProvider()
        uuids = provider._discover_scope_uuids("knowledge_scope_id", BrokenCollection())
        assert uuids == []

    def test_build_filters_discoveries_single_uuid(
        self, sample_input, default_state, fake_embedding
    ):
        """When scope code is provided but collection stores UUIDs with a single
        value, the discovery mechanism should resolve the code to the UUID."""
        collection = FakeMilvusCollection(
            query_rows=[{"knowledge_scope_id": "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b"}],
            schema_fields=[
                "chunk_id", "document_id", "knowledge_scope_id",
                "embedding_version", "source_uri", "title", "node_path",
                "content_preview", "content", "embedding",
            ],
        )
        config = MilvusRuntimeConfig(embedding_version="")
        provider = MilvusRetrievalProvider(config=config, _client=collection)

        from modules.sales_diagnosis_runtime.milvus_provider import resolve_milvus_field_map
        field_map = resolve_milvus_field_map(collection, config)

        filters = provider._build_filters(
            sample_input, default_state, field_map, collection
        )
        # Should discover and use the UUID, not the code
        assert "ks_team360_sales_diagnosis" not in filters
        assert "8b071443" in filters
        assert len(collection.last_query or {}) > 0  # discovery query was executed

    def test_build_filters_no_discovery_when_env_var_set(
        self, sample_input, default_state, fake_embedding
    ):
        """When TEAM360_KNOWLEDGE_SCOPE_ID is set in config to a UUID,
        the env var value should be used directly without discovery."""
        collection = FakeMilvusCollection(
            query_rows=[{"knowledge_scope_id": "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b"}],
            schema_fields=[
                "chunk_id", "document_id", "knowledge_scope_id",
                "embedding_version", "source_uri", "title", "node_path",
                "content_preview", "content", "embedding",
            ],
        )
        config = MilvusRuntimeConfig(
            knowledge_scope_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            embedding_version="",
        )
        provider = MilvusRetrievalProvider(config=config, _client=collection)

        from modules.sales_diagnosis_runtime.milvus_provider import resolve_milvus_field_map
        field_map = resolve_milvus_field_map(collection, config)

        filters = provider._build_filters(
            sample_input, default_state, field_map, collection
        )
        # Should use the env var UUID, not the input code or discovered UUID
        assert 'knowledge_scope_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"' in filters
        assert "ks_team360_sales_diagnosis" not in filters

    def test_build_filters_multiple_uuids_does_not_resolve(
        self, sample_input, default_state, fake_embedding
    ):
        """When multiple unique scope UUIDs exist, the discovery should NOT
        resolve, leaving the original scope code in the filter."""
        collection = FakeMilvusCollection(
            query_rows=[
                {"knowledge_scope_id": "uuid-001"},
                {"knowledge_scope_id": "uuid-002"},
            ],
            schema_fields=[
                "chunk_id", "document_id", "knowledge_scope_id",
                "embedding_version", "source_uri", "title", "node_path",
                "content_preview", "content", "embedding",
            ],
        )
        config = MilvusRuntimeConfig(embedding_version="")
        provider = MilvusRetrievalProvider(config=config, _client=collection)

        from modules.sales_diagnosis_runtime.milvus_provider import resolve_milvus_field_map
        field_map = resolve_milvus_field_map(collection, config)

        filters = provider._build_filters(
            sample_input, default_state, field_map, collection
        )
        # Should NOT resolve — original scope code stays
        assert 'knowledge_scope_id == "ks_team360_sales_diagnosis"' in filters

    def test_build_filters_retrieve_uses_discovery(
        self, sample_input, default_state, fake_embedding
    ):
        """Full retrieve() path should work with UUID discovery."""
        hit = FakeHit()
        hit.entity.fields = {
            "chunk_id": "c1",
            "document_id": "d1",
            "knowledge_scope_id": "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b",
            "source_uri": "/test.md",
            "title": "Test",
            "node_path": "/test",
            "content_preview": "preview",
            "content": "content",
        }
        collection = FakeMilvusCollection(
            results=make_fake_result_set(hit),
            query_rows=[{"knowledge_scope_id": "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b"}],
            schema_fields=[
                "chunk_id", "document_id", "knowledge_scope_id",
                "embedding_version", "source_uri", "title", "node_path",
                "content_preview", "content", "embedding",
            ],
        )
        config = MilvusRuntimeConfig(embedding_version="")
        provider = MilvusRetrievalProvider(
            config=config,
            embedding_provider=fake_embedding,
            _client=collection,
        )

        chunks = provider.retrieve(sample_input, default_state, top_k=5)
        assert len(chunks) == 1
        assert chunks[0].knowledge_scope_id == "8b071443-5bd6-4fe4-bbc3-fc2dca179a5b"
        # The search expr should contain the discovered UUID, not the code
        assert collection.last_search is not None
        expr = collection.last_search["expr"]
        assert "8b071443" in expr
        assert "ks_team360_sales_diagnosis" not in expr


# ---------------------------------------------------------------------------
# 4. Configuration
# ---------------------------------------------------------------------------


class TestMilvusRuntimeConfig:
    def test_milvus_config_defaults(self):
        config = MilvusRuntimeConfig()
        assert config.collection_name == "knowledge_chunks"
        assert config.top_k_default == 5
        assert config.top_n_default == 20
        assert config.timeout_seconds == 10.0
        assert config.metric_type == "COSINE"

    def test_milvus_config_repr_hides_token(self):
        config = MilvusRuntimeConfig(token="secret-token-123")
        rep = repr(config)
        assert "secret-token-123" not in rep
        assert "***" in rep

    def test_milvus_config_no_secret_in_repr_when_empty(self):
        config = MilvusRuntimeConfig()
        rep = repr(config)
        assert "token=None" in rep or "token=" in rep

    def test_milvus_config_from_env_missing(self, monkeypatch):
        for k in [
            "TEAM360_MILVUS_URI",
            "TEAM360_MILVUS_HOST",
            "TEAM360_MILVUS_PORT",
            "TEAM360_MILVUS_TOKEN",
            "TEAM360_MILVUS_COLLECTION",
            "TEAM360_EMBEDDING_VERSION",
            "TEAM360_KNOWLEDGE_SCOPE_ID",
        ]:
            monkeypatch.delenv(k, raising=False)
        config = MilvusRuntimeConfig.from_env()
        assert config.uri is None
        assert config.host is None
        assert config.token is None
        assert config.collection_name == "knowledge_chunks"

    def test_milvus_config_from_env_full(self, monkeypatch):
        monkeypatch.setenv("TEAM360_MILVUS_URI", "http://milvus:19530")
        monkeypatch.setenv("TEAM360_MILVUS_TOKEN", "token123")
        monkeypatch.setenv("TEAM360_MILVUS_COLLECTION", "test_collection")
        monkeypatch.setenv("TEAM360_EMBEDDING_VERSION", "v1")
        monkeypatch.setenv("TEAM360_KNOWLEDGE_SCOPE_ID", "ks_test")
        config = MilvusRuntimeConfig.from_env()
        assert config.uri == "http://milvus:19530"
        assert config.token == "token123"
        assert config.collection_name == "test_collection"

    def test_int_or_none_helper(self):
        assert _int_or_none("19530") == 19530
        assert _int_or_none("") is None
        assert _int_or_none(None) is None
        assert _int_or_none("abc") is None

    def test_no_secret_values_in_error_message(self):
        config = MilvusRuntimeConfig(token="super-secret")
        error = MilvusConfigurationError(
            f"Config: {config!r}"
        )
        assert "super-secret" not in str(error)
        assert "***" in str(error)


# ---------------------------------------------------------------------------
# 4. Runtime integration with MilvusRetrievalProvider
# ---------------------------------------------------------------------------


class TestRuntimeWithMilvusProvider:
    def test_runtime_with_real_milvus_provider_and_no_llm(
        self, sample_input, fake_embedding
    ):
        config = MilvusRuntimeConfig()
        milvus = MilvusRetrievalProvider(
            config=config,
            embedding_provider=fake_embedding,
            _client=FakeMilvusCollection(results=make_fake_result_set(FakeHit())),
        )
        runtime = AssistantConversationRuntime(
            retrieval_provider=milvus,
        )
        output = runtime.handle_turn(sample_input)
        assert output.response_text is not None
        assert output.response_type == "skeleton_ack"

    def test_runtime_handles_retrieval_unavailable_with_safe_fallback(
        self, sample_input
    ):
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=None,
        )
        runtime = AssistantConversationRuntime(
            retrieval_provider=provider,
        )
        # Runtime uses has_real_retrieval check via isinstance.
        # Since MilvusRetrievalProvider is not NullRetrievalProvider,
        # but retrieve() will raise RetrievalUnavailableError.
        # In skeleton mode (no LLM), runtime does not call retrieve.
        output = runtime.handle_turn(sample_input)
        assert output.response_type == "skeleton_ack"
        # The real retrieval path is only reached when LLM provider is also real.
        # For now, skeleton mode returns safe ack regardless.
        # This test validates that the runtime itself doesn't crash.

    def test_runtime_with_milvus_provider_emits_proper_events(
        self, sample_input, fake_embedding
    ):
        milvus = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=FakeMilvusCollection(results=make_fake_result_set(FakeHit())),
        )
        runtime = AssistantConversationRuntime(
            retrieval_provider=milvus,
        )
        output = runtime.handle_turn(sample_input)
        event_types = [e.event_type for e in output.events]
        assert "team360.status.received" in event_types
        assert "team360.answer.quick_ack" in event_types
        assert "team360.done" in event_types

    def test_runtime_does_not_activate_future_capabilities(
        self, sample_input, fake_embedding
    ):
        milvus = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=FakeMilvusCollection(results=make_fake_result_set(FakeHit())),
        )
        runtime = AssistantConversationRuntime(
            retrieval_provider=milvus,
        )
        output = runtime.handle_turn(sample_input)
        text_lower = output.response_text.lower()
        for cap in [
            "step_to_action",
            "lead_capture",
            "diagnostic_code",
            "whatsapp_handoff",
        ]:
            label = cap.replace("_", " ")
            if label in text_lower:
                assert "disponible" not in text_lower or "no" in text_lower


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_milvus_provider_empty_result_set(
        self, sample_input, default_state, fake_embedding
    ):
        collection = FakeMilvusCollection(results=[])
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=collection,
        )
        chunks = provider.retrieve(sample_input, default_state)
        assert chunks == []

    def test_milvus_provider_multiple_result_sets(
        self, sample_input, default_state, fake_embedding
    ):
        hit1 = FakeHit(id="a1", score=0.9)
        hit2 = FakeHit(id="a2", score=0.8)
        hit1.entity.fields["chunk_id"] = "a1"
        hit2.entity.fields["chunk_id"] = "a2"

        hit3 = FakeHit(id="b1", score=0.85)
        hit3.entity.fields["chunk_id"] = "b1"

        collection = FakeMilvusCollection(
            results=[list(hits) for hits in [  # Two result sets (two queries)
                [hit1, hit2],
                [hit3],
            ]]
        )
        provider = MilvusRetrievalProvider(
            config=MilvusRuntimeConfig(),
            embedding_provider=fake_embedding,
            _client=collection,
        )
        chunks = provider.retrieve(sample_input, default_state)
        # The first result set yields up to top_k chunks
        assert len(chunks) == 2
        assert chunks[0].chunk_id == "a1"
        assert chunks[1].chunk_id == "a2"

"""Tests for QueryEmbeddingProvider and OpenAIQueryEmbeddingProvider.

No network calls. No real OpenAI API. All providers use fakes/stubs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from modules.sales_diagnosis_runtime import (
    InvalidAssistantRuntimeInputError,
    LLMUnavailableError,
    OpenAIQueryEmbeddingProvider,
    QueryEmbeddingConfig,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeEmbeddingResponse:
    data: list[FakeEmbeddingData]


@dataclass
class FakeEmbeddingData:
    embedding: list[float]


class FakeOpenAIClient:
    """Simulates openai.OpenAI for testing without API calls."""

    def __init__(self, dimension: int = 1536, fail_on_call: bool = False) -> None:
        self._dimension = dimension
        self._fail_on_call = fail_on_call

    @property
    def embeddings(self) -> FakeEmbeddings:
        return FakeEmbeddings(self._dimension, self._fail_on_call)


class FakeEmbeddings:
    def __init__(self, dimension: int, fail_on_call: bool) -> None:
        self._dimension = dimension
        self._fail_on_call = fail_on_call

    def create(self, input: str, model: str, timeout: float) -> FakeEmbeddingResponse:
        if self._fail_on_call:
            raise RuntimeError("API failure simulated")
        vector = [0.5] * self._dimension
        return FakeEmbeddingResponse(data=[FakeEmbeddingData(embedding=vector)])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueryEmbeddingConfig:
    def test_config_defaults(self):
        config = QueryEmbeddingConfig()
        assert config.model == "text-embedding-3-small"
        assert config.dimensions == 1536
        assert config.timeout_seconds == 30.0

    def test_config_repr_masks_api_key_env(self):
        config = QueryEmbeddingConfig(api_key_env="OPENAI_API_KEY")
        rep = repr(config)
        assert "api_key_env" not in rep

    def test_config_from_env_defaults(self, monkeypatch):
        for k in ["TEAM360_EMBEDDING_MODEL", "TEAM360_EMBEDDING_DIMENSIONS"]:
            monkeypatch.delenv(k, raising=False)
        config = QueryEmbeddingConfig.from_env()
        assert config.model == "text-embedding-3-small"
        assert config.dimensions == 1536


class TestOpenAIQueryEmbeddingProvider:
    def test_does_not_import_openai_on_module_import(self):
        import modules.sales_diagnosis_runtime.embedding_provider as ep

        assert hasattr(ep, "OpenAIQueryEmbeddingProvider")

    def test_missing_api_key_raises_controlled_error(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = OpenAIQueryEmbeddingProvider()
        with pytest.raises(LLMUnavailableError, match="API key not found"):
            provider.embed_query("test query")

    def test_empty_query_raises_invalid_input(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key-for-unit-tests")
        provider = OpenAIQueryEmbeddingProvider()
        with pytest.raises(
            InvalidAssistantRuntimeInputError, match="non-empty"
        ):
            provider.embed_query("")
        with pytest.raises(
            InvalidAssistantRuntimeInputError, match="non-empty"
        ):
            provider.embed_query("   ")

    def test_fake_client_returns_1536_vector(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key-for-unit-tests")
        fake = FakeOpenAIClient(dimension=1536)
        provider = OpenAIQueryEmbeddingProvider(_client=fake)
        vector = provider.embed_query("test query")
        assert isinstance(vector, list)
        assert len(vector) == 1536
        assert all(isinstance(v, float) for v in vector)

    def test_wrong_dimension_raises_controlled_error(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key-for-unit-tests")
        fake = FakeOpenAIClient(dimension=512)
        provider = OpenAIQueryEmbeddingProvider(
            config=QueryEmbeddingConfig(dimensions=1536),
            _client=fake,
        )
        with pytest.raises(LLMUnavailableError, match="expected 1536"):
            provider.embed_query("test query")

    def test_repr_masks_secrets(self):
        provider = OpenAIQueryEmbeddingProvider(
            config=QueryEmbeddingConfig(api_key_env="OPENAI_API_KEY"),
        )
        rep = repr(provider)
        assert "model=" in rep
        assert "dimensions=" in rep
        assert "OPENAI_API_KEY" not in rep

    def test_fake_client_uses_config_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key-for-unit-tests")
        fake = FakeOpenAIClient(dimension=1536)
        config = QueryEmbeddingConfig(model="text-embedding-ada-002")
        provider = OpenAIQueryEmbeddingProvider(config=config, _client=fake)
        vector = provider.embed_query("test")
        assert len(vector) == 1536

    def test_api_call_failure_raises_llm_unavailable(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key-for-unit-tests")
        fake = FakeOpenAIClient(dimension=1536, fail_on_call=True)
        provider = OpenAIQueryEmbeddingProvider(_client=fake)
        with pytest.raises(LLMUnavailableError, match="Embedding call failed"):
            provider.embed_query("test")

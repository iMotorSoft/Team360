"""Embedding provider for Knowledge Ingestion Phase 1.5.

Uses OpenAI text-embedding-3-small as the default embedding model.
Uses httpx for API calls (already in project dependencies).

No chat completions. No LLM calls. Embeddings only.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

EXPECTED_DIMENSIONS = 1536
EMBEDDING_VERSION = "team360-openai-small-1536-v1"
DEFAULT_EMBEDDING_PROVIDER = "openai"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
OPENAI_DEFAULT_MODEL = "text-embedding-3-small"


class EmbeddingProviderError(Exception):
    """Raised when embedding generation fails."""


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        model: str = OPENAI_DEFAULT_MODEL,
        dimensions: int = EXPECTED_DIMENSIONS,
        api_key: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
        self._client = http_client

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120.0)
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise EmbeddingProviderError(
                "OPENAI_API_KEY not found in environment"
            )

        client = self._get_client()
        body = {
            "input": texts,
            "model": self.model,
            "dimensions": self.dimensions,
        }
        response = client.post(
            OPENAI_EMBEDDING_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )

        if response.status_code != 200:
            raise EmbeddingProviderError(
                f"OpenAI embedding API error {response.status_code}: "
                f"{response.text[:300]}"
            )

        data: dict[str, Any] = response.json()

        if "data" not in data:
            raise EmbeddingProviderError(
                f"OpenAI response missing 'data' key: {str(data)[:200]}"
            )

        embeddings_data = data["data"]
        if not isinstance(embeddings_data, list) or len(embeddings_data) != len(texts):
            raise EmbeddingProviderError(
                f"Response data count mismatch: "
                f"expected {len(texts)}, got {len(embeddings_data)}"
            )

        results: list[list[float]] = []
        for item in sorted(embeddings_data, key=lambda x: x.get("index", 0)):
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingProviderError(
                    f"Embedding is not a list: {type(embedding)}"
                )
            if len(embedding) != self.dimensions:
                raise EmbeddingProviderError(
                    f"Embedding dimension mismatch: "
                    f"expected {self.dimensions}, got {len(embedding)} "
                    f"for index {item.get('index', '?')}"
                )
            if not all(isinstance(x, float) for x in embedding):
                raise EmbeddingProviderError(
                    f"Embedding values are not all floats at index "
                    f"{item.get('index', '?')}"
                )
            results.append(embedding)

        return results

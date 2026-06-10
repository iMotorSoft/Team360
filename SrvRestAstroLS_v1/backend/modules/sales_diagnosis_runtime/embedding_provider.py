from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from modules.sales_diagnosis_runtime.errors import (
    InvalidAssistantRuntimeInputError,
    LLMUnavailableError,
)
from modules.sales_diagnosis_runtime.providers import QueryEmbeddingProvider


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class QueryEmbeddingConfig:
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    timeout_seconds: float = 30.0
    api_key_env: str = "OPENAI_API_KEY"
    base_url_env: str | None = "OPENAI_BASE_URL"
    provider_name: str = "openai"

    @classmethod
    def from_env(
        cls,
        model_env: str = "TEAM360_EMBEDDING_MODEL",
        dimensions_env: str = "TEAM360_EMBEDDING_DIMENSIONS",
    ) -> QueryEmbeddingConfig:
        return cls(
            model=os.environ.get(model_env, "text-embedding-3-small"),
            dimensions=_int_or_none(os.environ.get(dimensions_env)) or 1536,
        )

    def __repr__(self) -> str:
        d = self.__dict__.copy()
        d.pop("api_key_env", None)
        fields = ", ".join(f"{k}={v!r}" for k, v in d.items())
        return f"QueryEmbeddingConfig({fields})"


def _int_or_none(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class OpenAIQueryEmbeddingProvider:
    """Query embedding provider backed by OpenAI-compatible API.

    Architecture invariants:
    - OpenAI is not source of truth; embeddings may be cached.
    - This provider is a derived vector producer for Milvus retrieval.
    - API key is read from environment at runtime, not at import.

    Requires:
    - openai >= 1.0.0 (lazy imported, error if missing).
    - A valid API key in the configured environment variable.
    """

    def __init__(
        self,
        config: QueryEmbeddingConfig | None = None,
        _client: Any = None,
    ) -> None:
        self._config = config or QueryEmbeddingConfig.from_env()
        self._client = _client  # Injected for tests; None means lazy init.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise InvalidAssistantRuntimeInputError(
                "Query text must be non-empty for embedding."
            )

        client = self._get_client()
        vector = self._call_embedding(client, text)
        expected = self._config.dimensions

        if len(vector) != expected:
            raise LLMUnavailableError(
                f"Embedding returned {len(vector)} dimensions, "
                f"expected {expected}. Check model or config."
            )
        return vector

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError:
            raise LLMUnavailableError(
                "openai package is not installed. "
                "Install it with 'pip install openai>=1.0.0'."
            ) from None

        api_key = os.environ.get(self._config.api_key_env)
        if not api_key:
            raise LLMUnavailableError(
                f"OpenAI API key not found in env var "
                f"'{self._config.api_key_env}'."
            )

        kwargs: dict[str, Any] = {"api_key": api_key}
        base_url_env_val = self._config.base_url_env
        if base_url_env_val:
            base_url = os.environ.get(base_url_env_val)
            if base_url:
                kwargs["base_url"] = base_url

        self._client = OpenAI(**kwargs)
        return self._client

    def _call_embedding(self, client: Any, text: str) -> list[float]:
        try:
            resp = client.embeddings.create(
                input=text,
                model=self._config.model,
                timeout=self._config.timeout_seconds,
            )
            return resp.data[0].embedding
        except Exception as exc:
            raise LLMUnavailableError(
                f"Embedding call failed: {exc}"
            ) from exc

    def __repr__(self) -> str:
        return (
            f"OpenAIQueryEmbeddingProvider(model={self._config.model!r}, "
            f"dimensions={self._config.dimensions})"
        )

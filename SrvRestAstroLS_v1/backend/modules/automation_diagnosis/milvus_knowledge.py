"""Milvus 2.6 knowledge repository for AutomationDiagnosisService.

Uses the existing knowledge_chunks collection in Milvus as a
vector index, with PostgreSQL as source of truth.

Activated by env var:
  TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus

Fallback: in-memory keyword matching (default).
"""

from __future__ import annotations

import os
import time
from typing import Any

from modules.automation_diagnosis.schemas import RetrievedContext

MILVUS_COLLECTION = "team360_sales_diagnosis_knowledge_v1"
SCOPE_CODE = "ks_team360_sales_diagnosis"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
DEFAULT_TOP_K = 5
MAX_TOP_K = 20


def is_milvus_retrieval_enabled() -> bool:
    return os.environ.get("TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER", "").strip().lower() == "milvus"


def _openai_embed(text: str) -> list[float]:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
    )
    return resp.data[0].embedding


class MilvusKnowledgeRepository:
    """Knowledge repository backed by Milvus 2.6 vector search.

    Implements the same interface as InMemoryKnowledgeRepository
    so it can be used interchangeably by AutomationDiagnosisService.
    """

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from pymilvus import MilvusClient
        uri = (
            os.environ.get("TEAM360_MILVUS_URI")
            or f"http://{os.environ.get('TEAM360_MILVUS_HOST', 'localhost')}:{os.environ.get('TEAM360_MILVUS_PORT', '19530')}"
        )
        kwargs: dict = {"uri": uri}
        token = os.environ.get("TEAM360_MILVUS_TOKEN") or ""
        if token:
            kwargs["token"] = token
        self._client = MilvusClient(**kwargs)
        return self._client

    def search(
        self,
        scope_id: str,
        query: str,
        retrieval_mode: str | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> RetrievedContext:
        if not query or not query.strip():
            return RetrievedContext(
                knowledge_scope_id=scope_id,
                retrieval_mode=retrieval_mode or "rag",
                query=query or "",
                chunks=[],
            )

        top_k = min(max(1, top_k), MAX_TOP_K)

        try:
            query_vec = _openai_embed(query)
        except Exception:
            return RetrievedContext(
                knowledge_scope_id=scope_id,
                retrieval_mode=retrieval_mode or "rag",
                query=query,
                chunks=[],
            )

        try:
            client = self._get_client()
            collection = os.environ.get(
                "TEAM360_MILVUS_COLLECTION", MILVUS_COLLECTION
            )
            results = client.search(
                collection_name=collection,
                data=[query_vec],
                limit=top_k,
                output_fields=[
                    "chunk_id", "document_id", "source_uri", "title",
                    "node_path", "content_preview", "content",
                    "knowledge_scope_id",
                ],
                search_params={"metric_type": "COSINE", "params": {"ef": 100}},
            )
        except Exception:
            return RetrievedContext(
                knowledge_scope_id=scope_id,
                retrieval_mode=retrieval_mode or "rag",
                query=query,
                chunks=[],
            )

        chunks: list[dict[str, Any]] = []
        if results:
            for hit in results[0][:top_k]:
                entity = hit.get("entity") or {}
                source_uri = entity.get("source_uri") or ""
                node_path = entity.get("node_path") or ""
                content = entity.get("content") or entity.get("content_preview") or ""

                meta = {
                    "source_uri": source_uri,
                    "node_path": node_path,
                }
                chunks.append({
                    "chunk_id": entity.get("chunk_id") or str(hit.get("id", "")),
                    "document_id": entity.get("document_id") or "",
                    "title": entity.get("title") or "",
                    "content": content,
                    "score": round(float(hit.get("distance", 0)), 6),
                    "metadata": meta,
                })

        return RetrievedContext(
            knowledge_scope_id=scope_id,
            retrieval_mode=retrieval_mode or "rag",
            query=query,
            chunks=chunks,
        )

    def scope_debug(self, scope_id: str) -> dict[str, Any]:
        try:
            client = self._get_client()
            collection = os.environ.get(
                "TEAM360_MILVUS_COLLECTION", MILVUS_COLLECTION
            )
            stats = client.get_collection_stats(collection)
            return {
                "scope_id": scope_id,
                "collection": collection,
                "row_count": stats.get("row_count", 0),
                "retrieval_provider": "milvus",
            }
        except Exception as exc:
            return {
                "scope_id": scope_id,
                "error": str(exc),
                "retrieval_provider": "milvus",
            }

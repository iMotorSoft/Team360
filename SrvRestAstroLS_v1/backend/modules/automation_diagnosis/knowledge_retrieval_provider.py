"""Dev/debug retrieval provider connecting Sales Diagnosis Runtime
to real Knowledge Ingestion data (PostgreSQL + pgvector).

Activated by env var:

    TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=knowledge_ingestion

When unset or set to any other value, the default in-memory fake is used.
"""

from __future__ import annotations

import os
import time
from typing import Any

import psycopg

from modules.db.settings import get_database_settings, sanitize_dsn
from modules.knowledge_ingestion.embedding_provider import (
    EMBEDDING_VERSION,
    EXPECTED_DIMENSIONS,
    OPENAI_DEFAULT_MODEL,
    OpenAIEmbeddingProvider,
)

from .schemas import KnowledgeChunk, KnowledgeDocument, KnowledgeScope, RetrievedContext

DEV_RETRIEVAL_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER"
DEV_RETRIEVAL_VALUE = "knowledge_ingestion"

SCOPE_ORG_CODE = "team360_live"
SCOPE_WS_CODE = "team360_public_site"
SCOPE_KS_CODE = "ks_team360_sales_diagnosis"
SCOPE_PKG_CODE = "pkg_sales_diagnosis"

PG_CONNECT_TIMEOUT = 5
DEFAULT_TOP_K = 5
MAX_TOP_K = 20


def _sanitize_for_log(val: str, keep: int = 6) -> str:
    if len(val) <= keep + 4:
        return val
    return val[:keep] + "..."


def _has_openai_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", ""))


def is_dev_retrieval_enabled() -> bool:
    return os.environ.get(DEV_RETRIEVAL_ENV, "").strip().lower() == DEV_RETRIEVAL_VALUE


def build_dev_retrieval_provider(
    organization_code: str = SCOPE_ORG_CODE,
    workspace_code: str = SCOPE_WS_CODE,
    knowledge_scope_code: str = SCOPE_KS_CODE,
    package_code: str = SCOPE_PKG_CODE,
) -> KnowledgeIngestionSalesDiagnosisRetrievalProvider | None:
    if not is_dev_retrieval_enabled():
        return None
    try:
        return KnowledgeIngestionSalesDiagnosisRetrievalProvider(
            organization_code=organization_code,
            workspace_code=workspace_code,
            knowledge_scope_code=knowledge_scope_code,
            package_code=package_code,
        )
    except Exception as exc:
        import warnings
        warnings.warn(
            f"Failed to build KnowledgeIngestionSalesDiagnosisRetrievalProvider "
            f"(falling back to in-memory): {exc}"
        )
        return None


class KnowledgeIngestionSalesDiagnosisRetrievalProvider:
    """Dev/debug retrieval provider backed by real Knowledge Ingestion data.

    Connects to PostgreSQL, queries pgvector via the same embedding provider
    used by the ingestion pipeline. Returns RetrievedContext compatible with
    the Sales Diagnosis Runtime contract.

    Fallback behavior:
    - If DB is unavailable → returns empty RetrievedContext (does not crash).
    - If OpenAI key is missing → returns empty RetrievedContext.
    - If scope_code not found → returns empty RetrievedContext.
    - If no chunks found → returns empty RetrievedContext.
    """

    def __init__(
        self,
        organization_code: str = SCOPE_ORG_CODE,
        workspace_code: str = SCOPE_WS_CODE,
        knowledge_scope_code: str = SCOPE_KS_CODE,
        package_code: str = SCOPE_PKG_CODE,
    ) -> None:
        self.organization_code = organization_code
        self.workspace_code = workspace_code
        self.knowledge_scope_code = knowledge_scope_code
        self.package_code = package_code

        self._embedding_provider: OpenAIEmbeddingProvider | None = None
        self._settings = get_database_settings()

    def _get_embedding_provider(self) -> OpenAIEmbeddingProvider | None:
        if self._embedding_provider is not None:
            return self._embedding_provider
        if not _has_openai_key():
            return None
        try:
            self._embedding_provider = OpenAIEmbeddingProvider(
                model=OPENAI_DEFAULT_MODEL,
                dimensions=EXPECTED_DIMENSIONS,
            )
            return self._embedding_provider
        except Exception:
            return None

    def _resolve_scope_id(self, conn: psycopg.Connection) -> str | None:
        row = conn.execute(
            "select id::text from knowledge_scopes where scope_code = %s",
            (self.knowledge_scope_code,),
        ).fetchone()
        return row[0] if row else None

    def _search_pgvector(
        self,
        conn: psycopg.Connection,
        scope_id: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            select
                kc.id::text as chunk_id,
                kc.knowledge_document_id::text as document_id,
                kd.source_uri,
                kc.title,
                kc.content,
                kc.node_path,
                kc.chunk_index,
                kc.metadata_jsonb as chunk_metadata,
                kce.metadata_jsonb as emb_metadata,
                1 - (kce.embedding <=> %s::vector) as score
            from knowledge_chunk_embeddings kce
            join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
            join knowledge_documents kd on kd.id = kc.knowledge_document_id
            where kce.embedding_status = 'ready'
              and kce.knowledge_scope_id = %s::uuid
              and kce.embedding is not null
              and kd.knowledge_scope_id = %s::uuid
            order by kce.embedding <=> %s::vector
            limit %s
            """,
            (query_embedding, scope_id, scope_id, query_embedding, top_k),
        )
        results: list[dict[str, Any]] = []
        for r in rows:
            results.append({
                "chunk_id": r[0],
                "document_id": r[1],
                "source_uri": r[2] or "",
                "title": r[3] or "",
                "content": r[4] or "",
                "node_path": r[5] or "",
                "chunk_index": r[6] or 0,
                "chunk_metadata": r[7] or {},
                "emb_metadata": r[8] or {},
                "score": round(float(r[9]), 6) if r[9] is not None else 0.0,
            })
        return results

    def search(
        self,
        scope_id: str,
        query: str,
        retrieval_mode: str | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> RetrievedContext:
        start_ms = time.time()
        top_k = min(max(1, top_k), MAX_TOP_K)
        retrieval_is_real = False
        fallback_reason: str | None = None
        collection_name = "pgvector"

        if not query or not query.strip():
            return RetrievedContext(
                knowledge_scope_id=scope_id,
                retrieval_mode=retrieval_mode or "rag",
                query=query or "",
                chunks=[],
            )

        embedding_provider = self._get_embedding_provider()
        if embedding_provider is None:
            fallback_reason = "openai_key_missing"
            elapsed_ms = int((time.time() - start_ms) * 1000)
            return self._build_empty_result(scope_id, query, retrieval_mode, collection_name, retrieval_is_real, fallback_reason, elapsed_ms)

        try:
            query_vec = embedding_provider.embed_texts([query])[0]
        except Exception as exc:
            fallback_reason = f"embedding_failed:{exc}"
            elapsed_ms = int((time.time() - start_ms) * 1000)
            return self._build_empty_result(scope_id, query, retrieval_mode, collection_name, retrieval_is_real, fallback_reason, elapsed_ms)

        try:
            conn = psycopg.connect(
                self._settings.dsn,
                connect_timeout=PG_CONNECT_TIMEOUT,
            )
        except Exception as exc:
            fallback_reason = f"db_connect_failed:{exc}"
            elapsed_ms = int((time.time() - start_ms) * 1000)
            return self._build_empty_result(scope_id, query, retrieval_mode, collection_name, retrieval_is_real, fallback_reason, elapsed_ms)

        try:
            db_scope_id = self._resolve_scope_id(conn)
            if db_scope_id is None:
                fallback_reason = f"scope_not_found:{self.knowledge_scope_code}"
                elapsed_ms = int((time.time() - start_ms) * 1000)
                return self._build_empty_result(scope_id, query, retrieval_mode, collection_name, retrieval_is_real, fallback_reason, elapsed_ms)

            results = self._search_pgvector(conn, db_scope_id, query_vec, top_k)
            retrieval_is_real = True

            chunks = []
            for r in results:
                meta = dict(r.get("chunk_metadata") or {})
                meta["source_uri"] = r.get("source_uri", "")
                meta["node_path"] = r.get("node_path", "")
                meta["score"] = r["score"]
                meta["emb_metadata"] = r.get("emb_metadata", {})
                chunks.append({
                    "chunk_id": r["chunk_id"],
                    "document_id": r["document_id"],
                    "title": r["title"],
                    "content": r["content"],
                    "score": r["score"],
                    "metadata": meta,
                })

            elapsed_ms = int((time.time() - start_ms) * 1000)

            return RetrievedContext(
                knowledge_scope_id=scope_id,
                retrieval_mode=retrieval_mode or "rag",
                query=query,
                chunks=chunks,
            )
        except Exception as exc:
            fallback_reason = f"search_failed:{exc}"
            elapsed_ms = int((time.time() - start_ms) * 1000)
            return self._build_empty_result(scope_id, query, retrieval_mode, collection_name, retrieval_is_real, fallback_reason, elapsed_ms)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def scope_debug(self, scope_id: str) -> dict[str, Any]:
        try:
            conn = psycopg.connect(
                self._settings.dsn,
                connect_timeout=PG_CONNECT_TIMEOUT,
            )
        except Exception as exc:
            return {
                "scope_id": scope_id,
                "error": f"db_connect_failed:{exc}",
                "retrieval_provider": "knowledge_ingestion",
                "retrieval_is_real": False,
                "fallback": True,
            }

        try:
            db_scope_id = self._resolve_scope_id(conn)
            if db_scope_id is None:
                return {
                    "scope_id": scope_id,
                    "knowledge_scope_code": self.knowledge_scope_code,
                    "error": "scope_not_found",
                    "retrieval_provider": "knowledge_ingestion",
                    "retrieval_is_real": False,
                    "fallback": True,
                }

            doc_row = conn.execute(
                "select count(*) from knowledge_documents "
                "where knowledge_scope_id = %s::uuid",
                (db_scope_id,),
            ).fetchone()
            doc_count = doc_row[0] if doc_row else 0

            chunk_row = conn.execute(
                "select count(*) from knowledge_chunks kc "
                "join knowledge_documents kd on kd.id = kc.knowledge_document_id "
                "where kd.knowledge_scope_id = %s::uuid",
                (db_scope_id,),
            ).fetchone()
            chunk_count = chunk_row[0] if chunk_row else 0

            emb_row = conn.execute(
                "select count(*) from knowledge_chunk_embeddings kce "
                "where kce.knowledge_scope_id = %s::uuid "
                "and kce.embedding_status = 'ready'",
                (db_scope_id,),
            ).fetchone()
            emb_count = emb_row[0] if emb_row else 0

            return {
                "scope_id": scope_id,
                "knowledge_scope_code": self.knowledge_scope_code,
                "organization_code": self.organization_code,
                "workspace_code": self.workspace_code,
                "package_code": self.package_code,
                "document_count": doc_count,
                "chunk_count": chunk_count,
                "embedded_chunk_count": emb_count,
                "retrieval_provider": "knowledge_ingestion",
                "retrieval_is_real": True,
                "fallback": False,
            }
        except Exception as exc:
            return {
                "scope_id": scope_id,
                "error": f"debug_query_failed:{exc}",
                "retrieval_provider": "knowledge_ingestion",
                "retrieval_is_real": False,
                "fallback": True,
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _build_empty_result(
        self,
        scope_id: str,
        query: str,
        retrieval_mode: str | None,
        collection_name: str,
        retrieval_is_real: bool,
        fallback_reason: str | None,
        elapsed_ms: int,
    ) -> RetrievedContext:
        return RetrievedContext(
            knowledge_scope_id=scope_id,
            retrieval_mode=retrieval_mode or "rag",
            query=query,
            chunks=[],
        )

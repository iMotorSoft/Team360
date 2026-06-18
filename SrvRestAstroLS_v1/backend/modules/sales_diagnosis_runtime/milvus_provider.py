from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    MilvusConfigurationError,
    MilvusSearchError,
    RetrievalUnavailableError,
)
from modules.sales_diagnosis_runtime.providers import (
    QueryEmbeddingProvider,
    RetrievalProvider,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class MilvusRuntimeConfig:
    uri: str | None = None
    host: str | None = None
    port: int | None = None
    token: str | None = None
    collection_name: str = "knowledge_chunks"
    embedding_version: str = ""
    knowledge_scope_id: str | None = None
    timeout_seconds: float = 10.0
    top_n_default: int = 20
    top_k_default: int = 5
    vector_field: str = "embedding"
    output_fields: tuple[str, ...] = (
        "chunk_id",
        "document_id",
        "knowledge_scope_id",
        "source_uri",
        "title",
        "node_path",
        "content_preview",
        "content",
    )
    metric_type: str = "COSINE"

    @classmethod
    def from_env(cls) -> MilvusRuntimeConfig:
        return cls(
            uri=os.environ.get("TEAM360_MILVUS_URI"),
            host=os.environ.get("TEAM360_MILVUS_HOST"),
            port=_int_or_none(os.environ.get("TEAM360_MILVUS_PORT")),
            token=os.environ.get("TEAM360_MILVUS_TOKEN"),
            collection_name=os.environ.get(
                "TEAM360_MILVUS_COLLECTION", "knowledge_chunks"
            ),
            embedding_version=os.environ.get(
                "TEAM360_EMBEDDING_VERSION", ""
            ),
            knowledge_scope_id=os.environ.get("TEAM360_KNOWLEDGE_SCOPE_ID"),
        )

    def __repr__(self) -> str:
        d = self.__dict__.copy()
        if d.get("token"):
            d["token"] = "***"
        fields = ", ".join(f"{k}={v!r}" for k, v in d.items())
        return f"MilvusRuntimeConfig({fields})"


def _int_or_none(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class MilvusFieldMap:
    """Resolved Milvus field names for the active collection schema."""

    vector_field: str
    chunk_id_field: str
    document_id_field: str | None
    knowledge_scope_field: str | None
    embedding_version_field: str | None
    source_uri_field: str | None
    title_field: str | None
    node_path_field: str | None
    content_preview_field: str | None
    content_field: str | None
    available_fields: tuple[str, ...]

    @property
    def output_fields(self) -> tuple[str, ...]:
        fields = [
            self.chunk_id_field,
            self.document_id_field,
            self.knowledge_scope_field,
            self.embedding_version_field,
            self.source_uri_field,
            self.title_field,
            self.node_path_field,
            self.content_preview_field,
            self.content_field,
        ]
        return tuple(_dedupe_preserve_order(field for field in fields if field))


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _schema_field_names(collection: Any) -> set[str]:
    schema = getattr(collection, "schema", None)
    if schema is None or not hasattr(schema, "fields"):
        return set()
    names: set[str] = set()
    for field_obj in getattr(schema, "fields", []):
        name = getattr(field_obj, "name", None)
        if name:
            names.add(str(name))
    return names


def _first_existing_field(
    available_fields: set[str],
    *candidates: str | None,
) -> str | None:
    for candidate in candidates:
        if candidate and candidate in available_fields:
            return candidate
    return None


def resolve_milvus_field_map(
    collection: Any,
    config: MilvusRuntimeConfig | None = None,
) -> MilvusFieldMap:
    """Resolve the collection schema to the field names used by the provider."""

    cfg = config or MilvusRuntimeConfig()
    available_fields = _schema_field_names(collection)

    if not available_fields:
        # Fake collections used in unit tests often omit schema metadata.
        available_fields = {
            cfg.vector_field,
            "chunk_id",
            "document_id",
            "knowledge_scope_id",
            "knowledge_scope_code",
            "embedding_version",
            "source_uri",
            "title",
            "node_path",
            "content_preview",
            "content",
        }

    vector_field = _first_existing_field(
        available_fields,
        cfg.vector_field,
        "embedding",
        "vector",
    )
    if not vector_field:
        raise MilvusConfigurationError(
            "Milvus collection schema does not expose a vector field. "
            "Check TEAM360_MILVUS_VECTOR_FIELD or the active collection schema."
        )

    chunk_id_field = _first_existing_field(
        available_fields,
        "chunk_id",
        "source_id",
        "id",
    ) or "chunk_id"
    document_id_field = _first_existing_field(
        available_fields,
        "document_id",
        "source_id",
        "id",
    )
    knowledge_scope_field = _first_existing_field(
        available_fields,
        "knowledge_scope_id",
        "knowledge_scope_code",
    )
    embedding_version_field = _first_existing_field(
        available_fields,
        "embedding_version",
    )
    title_field = _first_existing_field(
        available_fields,
        "title",
    )
    node_path_field = _first_existing_field(
        available_fields,
        "node_path",
    )
    content_preview_field = _first_existing_field(
        available_fields,
        "content_preview",
        "text",
        "content",
    )
    content_field = _first_existing_field(
        available_fields,
        "content",
        "text",
        "content_preview",
    )
    source_uri_field = _first_existing_field(
        available_fields,
        "source_uri",
        "node_path",
        "document_id",
        "chunk_id",
    ) or node_path_field or document_id_field or chunk_id_field

    return MilvusFieldMap(
        vector_field=vector_field,
        chunk_id_field=chunk_id_field,
        document_id_field=document_id_field,
        knowledge_scope_field=knowledge_scope_field,
        embedding_version_field=embedding_version_field,
        source_uri_field=source_uri_field,
        title_field=title_field,
        node_path_field=node_path_field,
        content_preview_field=content_preview_field,
        content_field=content_field,
        available_fields=tuple(sorted(available_fields)),
    )
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class MilvusRetrievalProvider:
    """Retrieval provider backed by Milvus 2.6.

    Architecture invariants:
    - Milvus is a derived vector index, not source of truth.
    - PostgreSQL 18 remains source of truth.
    - This provider reads from Milvus only.
    - Index is reconstructible from PostgreSQL at any time.

    Requires:
    - A QueryEmbeddingProvider to convert user text to query vectors.
    - pymilvus >= 3.0.0 (lazy imported, error if missing).
    """

    def __init__(
        self,
        config: MilvusRuntimeConfig | None = None,
        embedding_provider: QueryEmbeddingProvider | None = None,
        _client: Any = None,
    ) -> None:
        self._config = config or MilvusRuntimeConfig.from_env()
        self._embedding_provider = embedding_provider
        self._client = _client  # Injected for tests; None means lazy connect.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        input: Any,
        state: Any,
        top_k: int | None = None,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if self._embedding_provider is None:
            raise RetrievalUnavailableError(
                "MilvusRetrievalProvider requires a QueryEmbeddingProvider. "
                "Configure one or use NullRetrievalProvider for development."
            )

        query_vector = self._embedding_provider.embed_query(
            getattr(input, "user_message", "") or ""
        )
        if not query_vector:
            return []

        collection = self._connect()
        field_map = resolve_milvus_field_map(collection, self._config)
        search_params = self._build_search_params(collection)
        filters = self._build_filters(input, state, field_map, collection)
        k = top_k or self._config.top_k_default
        n = top_n or self._config.top_n_default

        try:
            results = collection.search(
                data=[query_vector],
                anns_field=field_map.vector_field,
                param=search_params,
                limit=n,
                expr=filters,
                output_fields=list(field_map.output_fields),
            )
        except Exception as exc:
            raise MilvusSearchError(
                f"Milvus search failed: {exc}"
            ) from exc

        return self._map_results(results, k, field_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from pymilvus import Collection, connections
        except ImportError:
            raise MilvusConfigurationError(
                "pymilvus is not installed. "
                "Install it with 'uv add pymilvus>=3.0.0'."
            ) from None

        cfg = self._config
        if cfg.uri:
            conn_alias = "team360_runtime"
            connections.connect(
                alias=conn_alias,
                uri=cfg.uri,
                token=cfg.token or "",
                timeout=cfg.timeout_seconds,
            )
        elif cfg.host:
            conn_alias = "team360_runtime"
            connections.connect(
                alias=conn_alias,
                host=cfg.host,
                port=cfg.port or 19530,
                token=cfg.token or "",
                timeout=cfg.timeout_seconds,
            )
        else:
            raise MilvusConfigurationError(
                "Milvus connection not configured. "
                "Set TEAM360_MILVUS_URI or TEAM360_MILVUS_HOST."
            )

        collection = Collection(name=cfg.collection_name, using=conn_alias)
        collection.load()
        return collection

    def _build_search_params(self, collection: Any) -> dict[str, Any]:
        idx_type = "IVF_FLAT"
        try:
            for idx in collection.indexes:
                idx_type = idx.params.get("index_type", idx_type) or idx_type
        except Exception:
            pass
        nprobe = min(self._config.top_n_default, 16)
        return {
            "metric_type": self._config.metric_type,
            "params": {"nprobe": nprobe},
        }

    _UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )

    @staticmethod
    def _is_uuid(value: str) -> bool:
        return bool(MilvusRetrievalProvider._UUID_RE.match(value))

    def _discover_scope_uuids(
        self, field_name: str, collection: Any
    ) -> list[str]:
        """Query the collection for unique scope values in the given field.

        Returns a deduplicated list of values found in the collection.
        Returns empty list on any query error.
        """
        try:
            results = collection.query(
                expr=f'{field_name} != ""',
                output_fields=[field_name],
                limit=500,
            )
            seen: set[str] = set()
            for row in results:
                val = str(row.get(field_name, "")).strip()
                if val:
                    seen.add(val)
            return list(seen)
        except Exception:
            return []

    # Debug gate env — when set to "true", mono-scope collection discovery is
    # permitted as a fallback for development/diagnostic use only.
    _MONOSCOPE_DISCOVERY_ENV = "TEAM360_MILVUS_ALLOW_MONOSCOPE_DISCOVERY"

    def _build_filters(
        self,
        input: Any,
        state: Any,
        field_map: MilvusFieldMap | None = None,
        collection: Any = None,
    ) -> str:
        filters: list[str] = []

        # Priority 1: explicit config UUID (env var TEAM360_KNOWLEDGE_SCOPE_ID).
        # Used for debugging, infra tests, and administrative scripts only.
        scope_value = self._config.knowledge_scope_id or ""
        if not scope_value:
            # Priority 2: pre-resolved UUID from PostgreSQL resolver.
            scope_value = getattr(input, "knowledge_scope_id", None) or ""
        if not scope_value:
            # Priority 3: human-readable scope code.
            # Without a resolver this will fail closed (0 hits) when the
            # collection stores UUIDs in knowledge_scope_id.
            scope_value = getattr(input, "knowledge_scope_code", None) or ""

        if scope_value:
            field_name = (
                field_map.knowledge_scope_field
                if field_map is not None and field_map.knowledge_scope_field
                else "knowledge_scope_code"
            )

            # Mono-scope collection discovery — DEBUG/DIAGNOSTIC ONLY.
            # Gated behind TEAM360_MILVUS_ALLOW_MONOSCOPE_DISCOVERY=true.
            # Not used in production. Kept for inspector, tests, and migration.
            allow_discovery = os.environ.get(
                self._MONOSCOPE_DISCOVERY_ENV, ""
            ).strip().lower() == "true"
            if (
                allow_discovery
                and field_name == "knowledge_scope_id"
                and not self._is_uuid(scope_value)
                and collection is not None
            ):
                discovered = self._discover_scope_uuids(field_name, collection)
                if len(discovered) == 1:
                    scope_value = discovered[0]
                elif len(discovered) > 1:
                    import warnings
                    warnings.warn(
                        f"Multiple scope UUIDs ({len(discovered)}) found in "
                        f"field {field_name!r}; cannot resolve code "
                        f"{scope_value!r} to a single UUID. Filter may "
                        "return 0 results."
                    )

            filters.append(f'{field_name} == "{scope_value}"')

        if self._config.embedding_version:
            field_name = (
                field_map.embedding_version_field
                if field_map is not None and field_map.embedding_version_field
                else "embedding_version"
            )
            filters.append(
                f'{field_name} == "{self._config.embedding_version}"'
            )

        return " and ".join(filters) if filters else ""

    def _map_results(
        self,
        raw_results: Any,
        top_k: int,
        field_map: MilvusFieldMap | None = None,
    ) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        for result_set in raw_results:
            for i in range(min(len(result_set), top_k)):
                hit = result_set[i]
                fields: dict[str, Any] = {}
                if hasattr(hit, "entity") and hit.entity is not None:
                    ent = hit.entity
                    if hasattr(ent, "fields"):
                        fields = ent.fields
                if not fields and hasattr(hit, "fields"):
                    fields = hit.fields

                chunk_field = (
                    field_map.chunk_id_field
                    if field_map is not None
                    else "chunk_id"
                )
                document_field = (
                    field_map.document_id_field
                    if field_map is not None and field_map.document_id_field
                    else "document_id"
                )
                scope_field = (
                    field_map.knowledge_scope_field
                    if field_map is not None and field_map.knowledge_scope_field
                    else "knowledge_scope_id"
                )
                source_field = (
                    field_map.source_uri_field
                    if field_map is not None and field_map.source_uri_field
                    else "source_uri"
                )
                title_field = (
                    field_map.title_field
                    if field_map is not None and field_map.title_field
                    else "title"
                )
                node_path_field = (
                    field_map.node_path_field
                    if field_map is not None and field_map.node_path_field
                    else "node_path"
                )
                preview_field = (
                    field_map.content_preview_field
                    if field_map is not None and field_map.content_preview_field
                    else "content_preview"
                )
                content_field = (
                    field_map.content_field
                    if field_map is not None and field_map.content_field
                    else "content"
                )

                chunk_id = self._safe_str(fields, chunk_field, hit.id)
                document_id = self._safe_str(fields, document_field, "")
                knowledge_scope_id = self._safe_str(fields, scope_field, "")
                source_uri = self._safe_str(fields, source_field, "")
                title = self._safe_str(fields, title_field)
                node_path = self._safe_str(fields, node_path_field)
                content_preview = self._safe_str(fields, preview_field, "")
                content = self._safe_str(fields, content_field, "")

                if not source_uri:
                    source_uri = node_path or document_id or chunk_id
                if not content:
                    content = content_preview or ""

                chunks.append(RetrievedChunk(
                    chunk_id=str(chunk_id),
                    document_id=str(document_id),
                    knowledge_scope_id=str(knowledge_scope_id),
                    source_uri=str(source_uri),
                    title=str(title) if title else None,
                    node_path=str(node_path) if node_path else None,
                    score=float(hit.score),
                    content_preview=str(content_preview),
                    content=str(content),
                ))
            break  # Only process first result set (single query vector)
        return chunks

    @staticmethod
    def _safe_str(
        fields: dict[str, Any],
        key: str,
        default: str | None = None,
    ) -> str | None:
        val = fields.get(key)
        if val is None:
            return default
        return str(val)

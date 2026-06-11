"""Inspect Milvus schema/corpus alignment for Sales Diagnosis.

This script is a controlled diagnostic tool for the Milvus-backed retrieval
path used by the sales diagnosis product adapter.

It does not print secrets, DSNs or tokens. It skips cleanly when Milvus is not
configured. When Milvus is configured, it inspects the live collection schema,
field aliases, available corpus values and a minimal retrieval search.

Usage:

    cd backend
    uv run python scripts/inspect_sales_diagnosis_milvus_schema.py

Optional runtime alignment envs:

    TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus
    TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536
    TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b
    TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from textwrap import shorten
from typing import Any


MILVUS_URI_ENV = "TEAM360_MILVUS_URI"
MILVUS_HOST_ENV = "TEAM360_MILVUS_HOST"
MILVUS_PORT_ENV = "TEAM360_MILVUS_PORT"
MILVUS_TOKEN_ENV = "TEAM360_MILVUS_TOKEN"
MILVUS_COLLECTION_ENV = "TEAM360_MILVUS_COLLECTION"
MILVUS_KNOWLEDGE_SCOPE_ID_ENV = "TEAM360_KNOWLEDGE_SCOPE_ID"
MILVUS_EMBEDDING_VERSION_ENV = "TEAM360_EMBEDDING_VERSION"
PRODUCT_RETRIEVAL_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER"

ZERO_VECTOR_DIM = 1536
TOP_K = 3
QUERY_FILTER_LIMIT = 200


def _sanitize_text(value: Any, limit: int = 88) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ")
    return shorten(text, width=limit, placeholder="...")


def _print_field_row(name: str, dtype_name: str, is_primary: bool, dim: Any) -> None:
    dim_part = f", dim={dim}" if dim is not None else ""
    print(
        f"  - {name}: dtype={dtype_name}, primary={'yes' if is_primary else 'no'}{dim_part}"
    )


def _unique_counts(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    return Counter(
        str(row.get(field))
        for row in rows
        if row.get(field) is not None and str(row.get(field)).strip() != ""
    )


def main() -> None:
    route_provider = os.environ.get(PRODUCT_RETRIEVAL_PROVIDER_ENV, "").strip().lower()
    collection_name = os.environ.get(MILVUS_COLLECTION_ENV, "knowledge_chunks").strip()
    milvus_uri = os.environ.get(MILVUS_URI_ENV, "").strip()
    milvus_host = os.environ.get(MILVUS_HOST_ENV, "").strip()
    milvus_port = os.environ.get(MILVUS_PORT_ENV, "").strip() or "19530"
    knowledge_scope_id = os.environ.get(MILVUS_KNOWLEDGE_SCOPE_ID_ENV, "").strip()
    embedding_version = os.environ.get(MILVUS_EMBEDDING_VERSION_ENV, "").strip()

    print("=== Sales Diagnosis Milvus Schema Inspector ===")
    print(f"{PRODUCT_RETRIEVAL_PROVIDER_ENV}: {route_provider!r}")
    print(f"{MILVUS_COLLECTION_ENV}: {collection_name!r}")
    print(f"{MILVUS_KNOWLEDGE_SCOPE_ID_ENV}: {knowledge_scope_id!r}")
    print(f"{MILVUS_EMBEDDING_VERSION_ENV}: {embedding_version!r}")
    print()

    if not milvus_uri and not milvus_host:
        print("--- SKIP ---")
        print(
            f"Missing Milvus config. Set {MILVUS_URI_ENV} or {MILVUS_HOST_ENV} to inspect the live schema."
        )
        print("Result: SKIPPED (not a failure)")
        sys.exit(0)

    try:
        from pymilvus import Collection, DataType, MilvusClient, connections
    except ImportError:
        print(
            "ERROR: pymilvus is not installed in this runtime. "
            "Run the command with an environment that has pymilvus available, "
            "or use `uv run --with pymilvus ...` for the diagnostic."
        )
        sys.exit(1)

    connection_uri = milvus_uri or f"http://{milvus_host}:{milvus_port}"

    try:
        from modules.sales_diagnosis_runtime.milvus_provider import (
            MilvusRuntimeConfig,
            resolve_milvus_field_map,
        )
    except Exception as exc:
        print(f"ERROR: could not import Milvus provider helpers: {exc}")
        sys.exit(1)

    cfg = MilvusRuntimeConfig.from_env()

    print(f"Milvus configured: yes")
    print(f"Target collection: {collection_name!r}")
    print(f"Zero-vector dim:   {ZERO_VECTOR_DIM}")
    print()

    try:
        client = MilvusClient(uri=connection_uri)
        connections.connect(alias="team360_milvus_diag", uri=connection_uri)
    except Exception as exc:
        print(f"ERROR: could not connect to Milvus: {type(exc).__name__}: {exc}")
        sys.exit(1)

    try:
        collections = client.list_collections()
    except Exception as exc:
        print(f"ERROR: could not list Milvus collections: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print("--- Collections ---")
    print(", ".join(collections) if collections else "(none)")
    if collection_name not in collections:
        print()
        print("MISMATCH: target collection is not present in this Milvus instance.")
        print(f"Expected collection: {collection_name!r}")
        print(f"Available collections: {collections!r}")
        sys.exit(1)

    collection = Collection(collection_name, using="team360_milvus_diag")
    try:
        collection.load()
    except Exception as exc:
        print(f"ERROR: could not load collection: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print()
    print("--- Schema ---")
    try:
        for field in collection.schema.fields:
            dtype_name = DataType(field.dtype).name
            dim = getattr(field, "params", {}).get("dim") if hasattr(field, "params") else None
            _print_field_row(
                name=str(getattr(field, "name", "")),
                dtype_name=dtype_name,
                is_primary=bool(getattr(field, "is_primary", False)),
                dim=dim,
            )
    except Exception as exc:
        print(f"ERROR: could not inspect schema: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print()
    print("--- Indexes ---")
    try:
        indexes = getattr(collection, "indexes", [])
        if not indexes:
            print("  (no indexes reported)")
        for index in indexes:
            print(
                "  - "
                f"name={getattr(index, 'index_name', getattr(index, 'name', ''))!r}, "
                f"field={getattr(index, 'field_name', '')!r}, "
                f"params={getattr(index, 'params', {})!r}"
            )
    except Exception as exc:
        print(f"  ERROR: could not inspect indexes: {type(exc).__name__}: {exc}")

    print()
    print("--- Provider Field Map ---")
    try:
        field_map = resolve_milvus_field_map(collection, cfg)
    except Exception as exc:
        print(f"ERROR: could not resolve provider field map: {type(exc).__name__}: {exc}")
        sys.exit(1)

    resolved_fields = {
        "vector": field_map.vector_field,
        "chunk_id": field_map.chunk_id_field,
        "document_id": field_map.document_id_field,
        "knowledge_scope": field_map.knowledge_scope_field,
        "embedding_version": field_map.embedding_version_field,
        "source_uri": field_map.source_uri_field,
        "title": field_map.title_field,
        "node_path": field_map.node_path_field,
        "content_preview": field_map.content_preview_field,
        "content": field_map.content_field,
    }
    for logical_name, resolved_name in resolved_fields.items():
        print(f"  - {logical_name}: {resolved_name!r}")

    print()
    print("--- Corpus Snapshot ---")
    row_count = 0
    try:
        stats = client.get_collection_stats(collection_name)
        row_count = int(stats.get("row_count", 0) or 0)
        print(f"  rows: {row_count}")
    except Exception as exc:
        print(f"  WARN: could not read row count: {type(exc).__name__}: {exc}")

    sample_rows: list[dict[str, Any]] = []
    try:
        sample_rows = client.query(
            collection_name=collection_name,
            filter="id >= 0",
            output_fields=[
                resolved_fields["chunk_id"] or "chunk_id",
                resolved_fields["document_id"] or "document_id",
                resolved_fields["knowledge_scope"] or "knowledge_scope_id",
                resolved_fields["embedding_version"] or "embedding_version",
                resolved_fields["source_uri"] or "node_path",
                resolved_fields["title"] or "title",
                resolved_fields["node_path"] or "node_path",
                resolved_fields["content_preview"] or "content_preview",
            ],
            limit=QUERY_FILTER_LIMIT,
        )
    except Exception as exc:
        print(f"  WARN: could not fetch sample rows: {type(exc).__name__}: {exc}")

    if sample_rows:
        for row in sample_rows[:3]:
            print(
                "  - "
                f"chunk_id={_sanitize_text(row.get(resolved_fields['chunk_id'] or 'chunk_id'))}, "
                f"scope={_sanitize_text(row.get(resolved_fields['knowledge_scope'] or 'knowledge_scope_id'))}, "
                f"version={_sanitize_text(row.get(resolved_fields['embedding_version'] or 'embedding_version'))}, "
                f"title={_sanitize_text(row.get(resolved_fields['title'] or 'title'))}, "
                f"node_path={_sanitize_text(row.get(resolved_fields['node_path'] or 'node_path'))}, "
                f"preview={_sanitize_text(row.get(resolved_fields['content_preview'] or 'content_preview'))}"
            )
    else:
        print("  (no sample rows returned)")

    print()
    print("--- Field Coverage ---")
    actual_field_names = {str(field.name) for field in collection.schema.fields}
    canonical_roles = [
        ("vector", "embedding", field_map.vector_field),
        ("chunk_id/source_id", "chunk_id", field_map.chunk_id_field),
        ("document_id", "document_id", field_map.document_id_field),
        ("knowledge_scope", "knowledge_scope_code", field_map.knowledge_scope_field),
        ("embedding_version", "embedding_version", field_map.embedding_version_field),
        ("source_uri", "source_uri", field_map.source_uri_field),
        ("title", "title", field_map.title_field),
        ("node_path", "node_path", field_map.node_path_field),
        ("content_preview/text", "content_preview", field_map.content_preview_field),
        ("content", "content", field_map.content_field),
    ]
    for role_name, canonical_name, resolved_name in canonical_roles:
        if resolved_name is None:
            print(f"  - {role_name}: MISSING")
        elif resolved_name == canonical_name or canonical_name in actual_field_names:
            print(f"  - {role_name}: exact match on {resolved_name!r}")
        else:
            print(f"  - {role_name}: alias resolved to {resolved_name!r} (canonical {canonical_name!r} not present)")

    metadata_present = any(
        name in actual_field_names for name in ("metadata", "metadata_jsonb", "metadata_json")
    )
    print(
        "  - metadata: "
        + ("present" if metadata_present else "absent; not surfaced by current runtime contract")
    )

    print()
    print("--- Filter Coverage ---")
    target_scope_for_runtime = knowledge_scope_id or "ks_team360_sales_diagnosis"
    target_version_for_runtime = embedding_version
    print(f"  runtime knowledge_scope filter value: {target_scope_for_runtime!r}")
    print(f"  runtime embedding_version filter value: {target_version_for_runtime!r}")

    discovered_scope_counts = _unique_counts(sample_rows, resolved_fields["knowledge_scope"] or "knowledge_scope_id")
    discovered_version_counts = _unique_counts(sample_rows, resolved_fields["embedding_version"] or "embedding_version")
    print(f"  discovered scope counts: {dict(discovered_scope_counts)!r}")
    print(f"  discovered version counts: {dict(discovered_version_counts)!r}")

    runtime_filters: list[str] = []
    if target_scope_for_runtime and field_map.knowledge_scope_field:
        runtime_filters.append(
            f'{field_map.knowledge_scope_field} == "{target_scope_for_runtime}"'
        )
    if target_version_for_runtime and field_map.embedding_version_field:
        runtime_filters.append(
            f'{field_map.embedding_version_field} == "{target_version_for_runtime}"'
        )
    runtime_expr = " and ".join(runtime_filters)

    control_scope_value = discovered_scope_counts.most_common(1)[0][0] if discovered_scope_counts else ""
    control_version_value = (
        discovered_version_counts.most_common(1)[0][0]
        if discovered_version_counts
        else ""
    )
    control_filters: list[str] = []
    if control_scope_value and field_map.knowledge_scope_field:
        control_filters.append(
            f'{field_map.knowledge_scope_field} == "{control_scope_value}"'
        )
    if control_version_value and field_map.embedding_version_field:
        control_filters.append(
            f'{field_map.embedding_version_field} == "{control_version_value}"'
        )
    control_expr = " and ".join(control_filters)

    print(f"  runtime expr: {runtime_expr!r}")
    print(f"  control expr: {control_expr!r}")

    def _search(expr: str) -> list[Any]:
        return client.search(
            collection_name=collection_name,
            data=[[0.0] * ZERO_VECTOR_DIM],
            filter=expr,
            limit=TOP_K,
            output_fields=list(field_map.output_fields),
            anns_field=field_map.vector_field,
        )

    runtime_hits: list[Any] = []
    control_hits: list[Any] = []
    try:
        runtime_hits = _search(runtime_expr)
    except Exception as exc:
        print(f"  WARN: runtime search failed: {type(exc).__name__}: {exc}")
    try:
        control_hits = _search(control_expr)
    except Exception as exc:
        print(f"  WARN: control search failed: {type(exc).__name__}: {exc}")

    runtime_count = len(runtime_hits[0]) if runtime_hits else 0
    control_count = len(control_hits[0]) if control_hits else 0
    print(f"  runtime search hits: {runtime_count}")
    print(f"  control search hits: {control_count}")

    if runtime_hits:
        print("  runtime sample hits:")
        for hit in runtime_hits[0][:TOP_K]:
            fields = {}
            if hasattr(hit, "entity") and getattr(hit, "entity") is not None:
                entity = hit.entity
                if hasattr(entity, "fields"):
                    fields = entity.fields
            print(
                "    - "
                f"chunk_id={_sanitize_text(fields.get(field_map.chunk_id_field or 'chunk_id', hit.id))}, "
                f"source_uri={_sanitize_text(fields.get(field_map.source_uri_field or 'node_path', ''))}, "
                f"title={_sanitize_text(fields.get(field_map.title_field or 'title', ''))}, "
                f"preview={_sanitize_text(fields.get(field_map.content_preview_field or 'content_preview', ''))}"
            )

    print()
    print("--- Diagnosis ---")
    issues: list[str] = []
    if field_map.knowledge_scope_field == "knowledge_scope_id":
        print("  scope field aligned via knowledge_scope_id.")
    elif field_map.knowledge_scope_field is None:
        issues.append("knowledge_scope field is missing in the current collection schema.")
    else:
        issues.append(
            f"knowledge_scope field resolved to {field_map.knowledge_scope_field!r}, not knowledge_scope_id."
        )

    if field_map.source_uri_field == "node_path":
        print("  source_uri is derived from node_path.")
    elif field_map.source_uri_field is None:
        issues.append("source_uri source is missing and no fallback field was resolved.")

    if field_map.content_field == "content_preview":
        print("  content is derived from content_preview.")
    elif field_map.content_field is None:
        issues.append("content source is missing and no fallback field was resolved.")

    if row_count == 0:
        issues.append("collection is empty.")

    if not discovered_scope_counts:
        issues.append("no rows expose knowledge_scope values.")
    elif target_scope_for_runtime and target_scope_for_runtime not in discovered_scope_counts:
        issues.append(
            f"runtime knowledge_scope filter {target_scope_for_runtime!r} has no matches in the collection."
        )

    if target_version_for_runtime and target_version_for_runtime not in discovered_version_counts:
        issues.append(
            f"runtime embedding_version filter {target_version_for_runtime!r} has no matches in the collection."
        )

    if runtime_count == 0:
        issues.append(
            "runtime search returned zero results; this is expected only when filters do not match the live corpus."
        )

    if control_count == 0:
        issues.append(
            "control search returned zero results; live corpus was not found or the schema cannot be queried correctly."
        )

    if issues:
        print("  Problems found:")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("Result: MISALIGNED")
        sys.exit(1)

    print("  No blocking mismatch detected.")
    print()
    print("Result: OK")


if __name__ == "__main__":
    main()

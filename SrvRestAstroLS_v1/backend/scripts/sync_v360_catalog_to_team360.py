"""Future optional sync from v360 into a Team360 catalog/pgvector database.

This script is preserved for later experiments and is not integrated into the
current Team360 runtime path. The active project priority remains:
- real channels
- conversational flow
- seller questions / inbox reading
- normalization into the orchestrator
- operational telemetry

Do not treat this script as part of the current core product path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from openai import OpenAI
from psycopg.rows import dict_row

try:
    from backend import globalVar
except ImportError:  # pragma: no cover - fallback when run from backend/
    import globalVar  # type: ignore[no-redef]

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "team360_pgvector_catalog.sql"


@dataclass
class CatalogDocument:
    source_system: str
    source_entity_type: str
    source_entity_key: str
    source_workspace_id: str | None
    source_project_code: str | None
    source_channel: str | None
    target_channel: str
    target_entity_type: str
    title: str
    subtitle: str | None
    body_text: str
    metadata: dict[str, Any]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body_text.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync product knowledge from v360 into Team360 pgvector catalog.")
    parser.add_argument("--source-dsn", default=globalVar.get_future_optional_v360_source_db_url_psql(), help="Source v360 Postgres DSN.")
    parser.add_argument("--target-dsn", default=globalVar.get_future_optional_team360_db_url_psql(), help="Target Team360 Postgres DSN.")
    parser.add_argument("--target-channel", default=globalVar.FUTURE_OPTIONAL_TARGET_CHANNEL, help="Primary channel label for Team360 knowledge.")
    parser.add_argument("--apply-schema", action="store_true", help="Apply the Team360 pgvector schema before syncing.")
    parser.add_argument("--embed", action="store_true", help="Generate embeddings when an OpenAI key is available.")
    parser.add_argument("--embedding-model", default=globalVar.FUTURE_OPTIONAL_EMBEDDING_MODEL, help="Embedding model name.")
    parser.add_argument("--max-chars", type=int, default=900, help="Approximate max characters per chunk.")
    parser.add_argument("--overlap", type=int, default=120, help="Character overlap between chunks.")
    return parser.parse_args()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _optional_line(label: str, value: Any) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return f"{label}: {cleaned}"


def _optional_json_line(label: str, value: Any) -> str | None:
    if value in (None, {}, [], ""):
        return None
    return f"{label}: {_json_dumps(value)}"


def _build_project_body(row: dict[str, Any]) -> str:
    lines = [
        f"Proyecto: {_clean_text(row['project_name'])}",
        _optional_line("Codigo", row["project_code"]),
        _optional_line("Estado", row.get("project_status")),
        _optional_line("Descripcion", row.get("project_description")),
        _optional_json_line("Ubicacion", row.get("location_jsonb")),
        _optional_json_line("Tags", row.get("project_tags")),
        _optional_line("Desarrolladora", row.get("developer_name")),
        _optional_json_line("Amenidades", row.get("amenities_jsonb")),
        _optional_json_line("Construccion", row.get("construction_jsonb")),
        _optional_json_line("Financiacion", row.get("financing_jsonb")),
        _optional_line("Inventario", row.get("inventory_scope_label")),
        _optional_line("Inventario completo", row.get("inventory_is_complete")),
        _optional_json_line("Resumen inventario", row.get("raw_status_breakdown_jsonb")),
        _optional_json_line("Advertencias de uso", row.get("usage_warnings_jsonb")),
        _optional_json_line("Advertencias familia", row.get("child_safety_warnings_jsonb")),
        _optional_json_line("Perfiles recomendados", row.get("recommended_profiles_jsonb")),
        _optional_json_line("Assets marketing", row.get("marketing_assets_jsonb")),
        _optional_json_line("Fuentes", row.get("source_urls_jsonb")),
    ]
    return "\n".join(line for line in lines if line)


def _build_unit_body(row: dict[str, Any]) -> str:
    lines = [
        f"Unidad: {_clean_text(row.get('project_name'))} {row.get('unit_code') or row.get('unit_id')}",
        _optional_line("Proyecto", row.get("project_code")),
        _optional_line("Tipologia", row.get("typology")),
        _optional_line("Ambientes", row.get("rooms_label")),
        _optional_line("Dormitorios", row.get("bedrooms")),
        _optional_line("Banios", row.get("bathrooms")),
        _optional_line("Superficie total m2", row.get("surface_total_m2")),
        _optional_line("Superficie cubierta m2", row.get("surface_covered_m2")),
        _optional_line("Precio", f"{row.get('currency') or ''} {row.get('list_price') or ''}"),
        _optional_line("Disponibilidad", row.get("availability_status")),
        _optional_json_line("Features", row.get("features_jsonb")),
        _optional_line("Orientacion", row.get("orientation")),
        _optional_line("Exposicion", row.get("exposure")),
        _optional_line("Vista", row.get("view_text")),
        _optional_line("Luz natural", row.get("natural_light")),
        _optional_line("Ventilacion cruzada", row.get("cross_ventilation")),
        _optional_line("Apto chicos", row.get("children_suitable")),
        _optional_line("Mascotas", row.get("pets_allowed")),
        _optional_line("Restricciones mascotas", row.get("pets_restrictions_text")),
        _optional_line("Patio", row.get("has_patio")),
        _optional_line("Jardin", row.get("has_garden")),
        _optional_json_line("Advertencias de uso", row.get("usage_warnings_jsonb")),
        _optional_json_line("Advertencias familia", row.get("child_safety_warnings_jsonb")),
        _optional_json_line("Features comerciales", row.get("commercial_features_jsonb")),
        _optional_json_line("Perfiles recomendados", row.get("recommended_profiles_jsonb")),
        _optional_json_line("Fuentes", row.get("source_urls_jsonb")),
    ]
    return "\n".join(line for line in lines if line)


def _build_marketing_body(row: dict[str, Any]) -> str:
    lines = [
        f"Campania marketing: {_clean_text(row.get('title'))}",
        _optional_line("Proyecto", row.get("project_code")),
        _optional_line("Canal origen", row.get("channel")),
        _optional_line("Copy", row.get("short_copy")),
        _optional_json_line("Chips", row.get("chips")),
        _optional_line("WhatsApp prefill", row.get("whatsapp_prefill")),
        _optional_line("Activa", row.get("is_active")),
    ]
    return "\n".join(line for line in lines if line)


def _paragraph_chunks(text: str, max_chars: int, overlap: int) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n{paragraph}"
        if current and len(candidate) > max_chars:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else ""
            current = f"{tail}\n{paragraph}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _embedding_literal(embedding: list[float] | None) -> str | None:
    if embedding is None:
        return None
    return "[" + ",".join(f"{value:.10f}" for value in embedding) + "]"


def _target_database_name(dsn: str) -> str:
    parsed = urlparse(dsn)
    return parsed.path.lstrip("/") or "unknown"


def _apply_schema(target_conn: psycopg.Connection[Any]) -> None:
    target_conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    target_conn.commit()


def _fetch_project_documents(source_conn: psycopg.Connection[Any], target_channel: str) -> list[CatalogDocument]:
    query = """
    select
        p.code as project_code,
        p.name as project_name,
        p.status as project_status,
        p.description as project_description,
        p.location_jsonb,
        to_jsonb(p.tags) as project_tags,
        d.name as developer_name,
        pf.workspace_id,
        pf.amenities_jsonb,
        pf.construction_jsonb,
        pf.financing_jsonb,
        pp.inventory_scope_label,
        pp.inventory_is_complete,
        pp.raw_status_breakdown_jsonb,
        pp.usage_warnings_jsonb,
        pp.child_safety_warnings_jsonb,
        pp.recommended_profiles_jsonb,
        coalesce(pf.source_urls, pp.source_urls, '[]'::jsonb) as source_urls_jsonb,
        coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'channel', m.channel,
                    'title', m.title,
                    'short_copy', m.short_copy,
                    'chips', m.chips
                )
                order by m.sort_order
            ) filter (where m.id is not null),
            '[]'::jsonb
        ) as marketing_assets_jsonb
    from projects p
    left join developers d on d.id = p.developer_id
    left join demo_project_facts pf on pf.project_code = p.code
    left join demo_project_profile pp on pp.project_code = p.code
    left join marketing_assets m on m.project_id = p.id
    group by
        p.code,
        p.name,
        p.status,
        p.description,
        p.location_jsonb,
        p.tags,
        d.name,
        pf.workspace_id,
        pf.amenities_jsonb,
        pf.construction_jsonb,
        pf.financing_jsonb,
        pp.inventory_scope_label,
        pp.inventory_is_complete,
        pp.raw_status_breakdown_jsonb,
        pp.usage_warnings_jsonb,
        pp.child_safety_warnings_jsonb,
        pp.recommended_profiles_jsonb,
        pf.source_urls,
        pp.source_urls
    order by p.code;
    """
    rows = source_conn.execute(query).fetchall()
    documents: list[CatalogDocument] = []
    for row in rows:
        row = dict(row)
        metadata = {
            "project_code": row["project_code"],
            "project_status": row.get("project_status"),
            "location": row.get("location_jsonb"),
            "tags": _json_list(row.get("project_tags")),
            "developer_name": row.get("developer_name"),
            "amenities": _json_list(row.get("amenities_jsonb")),
            "construction": _json_object(row.get("construction_jsonb")),
            "financing": _json_object(row.get("financing_jsonb")),
            "marketing_assets": _json_list(row.get("marketing_assets_jsonb")),
        }
        documents.append(
            CatalogDocument(
                source_system="v360",
                source_entity_type="project",
                source_entity_key=row["project_code"],
                source_workspace_id=row.get("workspace_id"),
                source_project_code=row["project_code"],
                source_channel="v360",
                target_channel=target_channel,
                target_entity_type="catalog",
                title=row["project_name"],
                subtitle=row.get("project_description"),
                body_text=_build_project_body(row),
                metadata=metadata,
            )
        )
    return documents


def _fetch_unit_documents(source_conn: psycopg.Connection[Any], target_channel: str) -> list[CatalogDocument]:
    query = """
    select
        u.workspace_id,
        u.project_code,
        p.name as project_name,
        u.unit_id,
        u.unit_code,
        u.typology,
        u.rooms_label,
        u.rooms_count,
        u.bedrooms,
        u.bathrooms,
        u.surface_total_m2,
        u.surface_covered_m2,
        u.currency,
        u.list_price,
        u.availability_status,
        u.features_jsonb,
        up.orientation,
        up.exposure,
        up.view_text,
        up.natural_light,
        up.cross_ventilation,
        up.children_suitable,
        up.pets_allowed,
        up.pets_restrictions_text,
        up.has_patio,
        up.has_garden,
        up.usage_warnings_jsonb,
        up.child_safety_warnings_jsonb,
        up.commercial_features_jsonb,
        up.recommended_profiles_jsonb,
        up.source_urls as source_urls_jsonb
    from demo_units u
    join projects p on p.code = u.project_code
    left join demo_unit_profile up
        on up.workspace_id = u.workspace_id
       and up.project_code = u.project_code
       and up.unit_id = u.unit_id
    order by u.project_code, u.unit_id;
    """
    rows = source_conn.execute(query).fetchall()
    documents: list[CatalogDocument] = []
    for row in rows:
        row = dict(row)
        metadata = {
            "project_code": row["project_code"],
            "unit_id": row["unit_id"],
            "unit_code": row.get("unit_code"),
            "availability_status": row.get("availability_status"),
            "price": row.get("list_price"),
            "currency": row.get("currency"),
            "features": _json_list(row.get("features_jsonb")),
            "commercial_features": _json_object(row.get("commercial_features_jsonb")),
        }
        documents.append(
            CatalogDocument(
                source_system="v360",
                source_entity_type="unit",
                source_entity_key=f"{row['project_code']}:{row['unit_id']}",
                source_workspace_id=row.get("workspace_id"),
                source_project_code=row["project_code"],
                source_channel="v360",
                target_channel=target_channel,
                target_entity_type="offer",
                title=f"{row['project_name']} {row.get('unit_code') or row['unit_id']}",
                subtitle=row.get("rooms_label"),
                body_text=_build_unit_body(row),
                metadata=metadata,
            )
        )
    return documents


def _fetch_marketing_documents(source_conn: psycopg.Connection[Any], target_channel: str) -> list[CatalogDocument]:
    query = """
    select
        m.id::text as marketing_asset_id,
        p.code as project_code,
        pf.workspace_id,
        m.channel::text as channel,
        m.title,
        m.short_copy,
        m.chips,
        m.whatsapp_prefill,
        m.is_active
    from marketing_assets m
    join projects p on p.id = m.project_id
    left join demo_project_facts pf on pf.project_code = p.code
    order by p.code, m.sort_order;
    """
    rows = source_conn.execute(query).fetchall()
    documents: list[CatalogDocument] = []
    for row in rows:
        row = dict(row)
        metadata = {
            "project_code": row["project_code"],
            "origin_channel": row.get("channel"),
            "chips": _json_list(row.get("chips")),
            "is_active": row.get("is_active"),
        }
        documents.append(
            CatalogDocument(
                source_system="v360",
                source_entity_type="marketing_asset",
                source_entity_key=row["marketing_asset_id"],
                source_workspace_id=row.get("workspace_id"),
                source_project_code=row["project_code"],
                source_channel=row.get("channel"),
                target_channel=target_channel,
                target_entity_type="campaign",
                title=f"{row['project_code']} {row['title']}",
                subtitle=row.get("short_copy"),
                body_text=_build_marketing_body(row),
                metadata=metadata,
            )
        )
    return documents


def _build_documents(source_conn: psycopg.Connection[Any], target_channel: str) -> list[CatalogDocument]:
    return [
        *_fetch_project_documents(source_conn, target_channel),
        *_fetch_unit_documents(source_conn, target_channel),
        *_fetch_marketing_documents(source_conn, target_channel),
    ]


def _embed_chunks(chunks: list[str], model: str) -> list[list[float] | None]:
    if not chunks:
        return []
    if not globalVar.FUTURE_OPTIONAL_OPENAI_API_KEY:
        return [None for _ in chunks]
    client = OpenAI(api_key=globalVar.FUTURE_OPTIONAL_OPENAI_API_KEY)
    response = client.embeddings.create(model=model, input=chunks)
    return [item.embedding for item in response.data]


def _upsert_source(target_conn: psycopg.Connection[Any], document: CatalogDocument) -> int:
    row = target_conn.execute(
        """
        insert into team360_catalog_source (
            source_system,
            source_entity_type,
            source_entity_key,
            source_workspace_id,
            source_project_code,
            source_channel,
            target_channel,
            target_entity_type,
            title,
            subtitle,
            body_text,
            metadata_jsonb,
            content_hash,
            synced_at,
            updated_at
        )
        values (
            %(source_system)s,
            %(source_entity_type)s,
            %(source_entity_key)s,
            %(source_workspace_id)s,
            %(source_project_code)s,
            %(source_channel)s,
            %(target_channel)s,
            %(target_entity_type)s,
            %(title)s,
            %(subtitle)s,
            %(body_text)s,
            %(metadata_jsonb)s,
            %(content_hash)s,
            now(),
            now()
        )
        on conflict (source_system, source_entity_type, source_entity_key, target_channel)
        do update set
            source_workspace_id = excluded.source_workspace_id,
            source_project_code = excluded.source_project_code,
            source_channel = excluded.source_channel,
            target_entity_type = excluded.target_entity_type,
            title = excluded.title,
            subtitle = excluded.subtitle,
            body_text = excluded.body_text,
            metadata_jsonb = excluded.metadata_jsonb,
            content_hash = excluded.content_hash,
            synced_at = now(),
            updated_at = now()
        returning id;
        """,
        {
            "source_system": document.source_system,
            "source_entity_type": document.source_entity_type,
            "source_entity_key": document.source_entity_key,
            "source_workspace_id": document.source_workspace_id,
            "source_project_code": document.source_project_code,
            "source_channel": document.source_channel,
            "target_channel": document.target_channel,
            "target_entity_type": document.target_entity_type,
            "title": document.title,
            "subtitle": document.subtitle,
            "body_text": document.body_text,
            "metadata_jsonb": _json_dumps(document.metadata),
            "content_hash": document.content_hash,
        },
    ).fetchone()
    assert row is not None
    return int(row["id"])


def _replace_chunks(
    target_conn: psycopg.Connection[Any],
    source_id: int,
    document: CatalogDocument,
    *,
    max_chars: int,
    overlap: int,
    embed: bool,
    embedding_model: str,
) -> tuple[int, int, int]:
    chunks = _paragraph_chunks(document.body_text, max_chars=max_chars, overlap=overlap)
    embeddings = _embed_chunks(chunks, embedding_model) if embed else [None for _ in chunks]
    target_conn.execute("delete from team360_catalog_chunk where source_id = %s", (source_id,))
    embedded_count = 0
    skipped_count = 0
    for index, chunk_text in enumerate(chunks):
        embedding = embeddings[index]
        if embedding is None:
            skipped_count += 1
        else:
            embedded_count += 1
        target_conn.execute(
            """
            insert into team360_catalog_chunk (
                source_id,
                chunk_index,
                chunk_kind,
                chunk_text,
                token_estimate,
                metadata_jsonb,
                content_hash,
                embedding_model,
                embedding,
                updated_at
            )
            values (
                %(source_id)s,
                %(chunk_index)s,
                'semantic',
                %(chunk_text)s,
                %(token_estimate)s,
                %(metadata_jsonb)s,
                %(content_hash)s,
                %(embedding_model)s,
                cast(%(embedding)s as vector),
                now()
            )
            """,
            {
                "source_id": source_id,
                "chunk_index": index,
                "chunk_text": chunk_text,
                "token_estimate": max(1, len(chunk_text) // 4),
                "metadata_jsonb": _json_dumps(document.metadata),
                "content_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                "embedding_model": embedding_model if embedding is not None else None,
                "embedding": _embedding_literal(embedding),
            },
        )
    return len(chunks), embedded_count, skipped_count


def _start_sync_run(
    target_conn: psycopg.Connection[Any],
    source_dsn: str,
    target_dsn: str,
    target_channel: str,
) -> tuple[int, uuid.UUID]:
    run_id = uuid.uuid4()
    row = target_conn.execute(
        """
        insert into team360_telemetry_sync_run (
            run_id,
            source_system,
            source_database,
            target_database,
            target_channel,
            status,
            meta_jsonb
        )
        values (%s, 'v360', %s, %s, %s, 'running', '{}'::jsonb)
        returning id;
        """,
        (
            run_id,
            _target_database_name(source_dsn),
            _target_database_name(target_dsn),
            target_channel,
        ),
    ).fetchone()
    assert row is not None
    return int(row["id"]), run_id


def _finish_sync_run(
    target_conn: psycopg.Connection[Any],
    sync_run_id: int,
    *,
    status: str,
    documents_seen: int,
    documents_upserted: int,
    chunks_upserted: int,
    chunks_embedded: int,
    embeddings_skipped: int,
    error_text: str | None = None,
) -> None:
    target_conn.execute(
        """
        update team360_telemetry_sync_run
        set
            status = %(status)s,
            finished_at = now(),
            documents_seen = %(documents_seen)s,
            documents_upserted = %(documents_upserted)s,
            chunks_upserted = %(chunks_upserted)s,
            chunks_embedded = %(chunks_embedded)s,
            embeddings_skipped = %(embeddings_skipped)s,
            error_text = %(error_text)s
        where id = %(id)s;
        """,
        {
            "id": sync_run_id,
            "status": status,
            "documents_seen": documents_seen,
            "documents_upserted": documents_upserted,
            "chunks_upserted": chunks_upserted,
            "chunks_embedded": chunks_embedded,
            "embeddings_skipped": embeddings_skipped,
            "error_text": error_text,
        },
    )


def run(args: argparse.Namespace) -> None:
    source_dsn = args.source_dsn
    target_dsn = args.target_dsn
    if not source_dsn:
        raise ValueError("Missing source DSN. Set DB_PG_V360_URL or pass --source-dsn.")
    if not target_dsn:
        raise ValueError("Missing target DSN. Set TEAM360_DB_URL or pass --target-dsn.")

    with (
        psycopg.connect(source_dsn, row_factory=dict_row, autocommit=False) as source_conn,
        psycopg.connect(target_dsn, row_factory=dict_row, autocommit=False) as target_conn,
    ):
        if args.apply_schema:
            _apply_schema(target_conn)

        sync_run_id, run_id = _start_sync_run(target_conn, source_dsn, target_dsn, args.target_channel)
        target_conn.commit()
        documents_seen = documents_upserted = chunks_upserted = chunks_embedded = embeddings_skipped = 0
        try:
            documents = _build_documents(source_conn, args.target_channel)
            documents_seen = len(documents)
            for document in documents:
                source_id = _upsert_source(target_conn, document)
                documents_upserted += 1
                chunk_count, embedded_count, skipped_count = _replace_chunks(
                    target_conn,
                    source_id,
                    document,
                    max_chars=args.max_chars,
                    overlap=args.overlap,
                    embed=args.embed,
                    embedding_model=args.embedding_model,
                )
                chunks_upserted += chunk_count
                chunks_embedded += embedded_count
                embeddings_skipped += skipped_count

            _finish_sync_run(
                target_conn,
                sync_run_id,
                status="completed",
                documents_seen=documents_seen,
                documents_upserted=documents_upserted,
                chunks_upserted=chunks_upserted,
                chunks_embedded=chunks_embedded,
                embeddings_skipped=embeddings_skipped,
            )
            target_conn.commit()
            print(
                json.dumps(
                    {
                        "run_id": str(run_id),
                        "status": "completed",
                        "documents_seen": documents_seen,
                        "documents_upserted": documents_upserted,
                        "chunks_upserted": chunks_upserted,
                        "chunks_embedded": chunks_embedded,
                        "embeddings_skipped": embeddings_skipped,
                        "target_database": _target_database_name(target_dsn),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as exc:
            target_conn.rollback()
            _finish_sync_run(
                target_conn,
                sync_run_id,
                status="failed",
                documents_seen=documents_seen,
                documents_upserted=documents_upserted,
                chunks_upserted=chunks_upserted,
                chunks_embedded=chunks_embedded,
                embeddings_skipped=embeddings_skipped,
                error_text=str(exc),
            )
            target_conn.commit()
            raise


def main() -> int:
    args = parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

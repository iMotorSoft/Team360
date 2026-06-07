"""PostgreSQL repository for Knowledge Ingestion Phase 1.

SQL stays here. Service/worker layers should not assemble SQL.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from modules.db.errors import DatabaseExecutionError
from modules.db.transaction import execute, fetch_one


class KnowledgeIngestionRepository:
    """Write-side repository for ingestion run tracking and document metadata.

    Follows existing Team360 pattern: receives connection from caller,
    uses named-parameter SQL, returns dicts.
    """

    async def create_ingestion_run(
        self,
        conn: AsyncConnection,
        knowledge_scope_id: str,
        document_source: str,
        metadata_snapshot: dict[str, Any],
        workspace_id: str | None = None,
    ) -> dict[str, str]:
        row = await fetch_one(
            conn,
            """
            insert into knowledge_ingestion_runs (
                knowledge_scope_id,
                workspace_id,
                document_source,
                metadata_snapshot,
                status,
                phases_jsonb,
                chunk_count,
                token_count,
                created_at_utc
            ) values (
                %(knowledge_scope_id)s,
                %(workspace_id)s,
                %(document_source)s,
                %(metadata_snapshot)s,
                'pending',
                '{}'::jsonb,
                0,
                0,
                now()
            )
            returning id::text
            """,
            {
                "knowledge_scope_id": knowledge_scope_id,
                "workspace_id": workspace_id,
                "document_source": document_source,
                "metadata_snapshot": Jsonb(metadata_snapshot),
            },
        )
        if row is None:
            raise DatabaseExecutionError(
                "create_ingestion_run returned no row"
            )
        return {"run_id": row["id"]}

    async def update_ingestion_run_status(
        self,
        conn: AsyncConnection,
        run_id: str,
        status: str,
        phases_jsonb: dict[str, Any] | None = None,
        chunk_count: int | None = None,
        token_count: int | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        parts = ["status = %(status)s", "updated_at_utc = now()"]
        params: dict[str, Any] = {"run_id": run_id, "status": status}

        if phases_jsonb is not None:
            parts.append("phases_jsonb = %(phases_jsonb)s")
            params["phases_jsonb"] = Jsonb(phases_jsonb)
        if chunk_count is not None:
            parts.append("chunk_count = %(chunk_count)s")
            params["chunk_count"] = chunk_count
        if token_count is not None:
            parts.append("token_count = %(token_count)s")
            params["token_count"] = token_count
        if error_code is not None:
            parts.append("error_code = %(error_code)s")
            params["error_code"] = error_code
        if error_detail is not None:
            parts.append("error_detail = %(error_detail)s")
            params["error_detail"] = error_detail

        if status == "running":
            parts.append("started_at_utc = coalesce(started_at_utc, now())")
        elif status == "completed":
            parts.append("completed_at_utc = now()")

        sql = (
            "update knowledge_ingestion_runs set "
            + ", ".join(parts)
            + " where id = %(run_id)s"
        )
        await execute(conn, sql, params)

    async def update_document_node_path(
        self,
        conn: AsyncConnection,
        document_id: str,
        node_path: str,
    ) -> None:
        """Set node_path on an existing knowledge document."""
        await execute(
            conn,
            """
            update knowledge_documents
            set node_path = %(node_path)s,
                updated_at_utc = now()
            where id = %(document_id)s
            """,
            {"document_id": document_id, "node_path": node_path},
        )

    async def update_chunk_node_path_and_tags(
        self,
        conn: AsyncConnection,
        chunk_id: str,
        node_path: str,
        permission_tags: list[str],
    ) -> None:
        """Set node_path and permission_tags on an existing knowledge chunk."""
        await execute(
            conn,
            """
            update knowledge_chunks
            set node_path = %(node_path)s,
                permission_tags = %(permission_tags)s,
                updated_at_utc = now()
            where id = %(chunk_id)s
            """,
            {
                "chunk_id": chunk_id,
                "node_path": node_path,
                "permission_tags": permission_tags,
            },
        )

    async def get_ingestion_run(
        self,
        conn: AsyncConnection,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Get a single ingestion run by id."""
        return await fetch_one(
            conn,
            """
            select
                id::text,
                knowledge_scope_id::text,
                workspace_id::text,
                document_source,
                metadata_snapshot,
                status,
                phases_jsonb,
                chunk_count,
                token_count,
                error_code,
                error_detail,
                started_at_utc,
                completed_at_utc,
                created_at_utc,
                updated_at_utc
            from knowledge_ingestion_runs
            where id = %(run_id)s
            """,
            {"run_id": run_id},
        )

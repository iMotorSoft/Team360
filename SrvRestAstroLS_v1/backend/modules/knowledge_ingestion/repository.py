"""PostgreSQL repository for Knowledge Ingestion Phase 1.

SQL stays here. Service/worker layers should not assemble SQL.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from modules.db.errors import DatabaseExecutionError
from modules.db.transaction import execute, fetch_one
from modules.knowledge_ingestion.schemas import (
    IngestionContext,
    IngestionContextRequest,
)


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
        organization_id: str | None = None,
        workspace_id: str | None = None,
        triggered_by_user_id: str | None = None,
    ) -> dict[str, str]:
        row = await fetch_one(
            conn,
            """
            insert into knowledge_ingestion_runs (
                knowledge_scope_id,
                organization_id,
                workspace_id,
                triggered_by_user_id,
                document_source,
                metadata_snapshot,
                status,
                phases_jsonb,
                chunk_count,
                token_count,
                created_at_utc
            ) values (
                %(knowledge_scope_id)s,
                %(organization_id)s,
                %(workspace_id)s,
                %(triggered_by_user_id)s,
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
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "triggered_by_user_id": triggered_by_user_id,
                "document_source": document_source,
                "metadata_snapshot": Jsonb(metadata_snapshot),
            },
        )
        if row is None:
            raise DatabaseExecutionError(
                "create_ingestion_run returned no row"
        )
        return {"run_id": row["id"]}

    async def find_knowledge_document_by_source(
        self,
        conn: AsyncConnection,
        knowledge_scope_id: str,
        source_uri: str,
    ) -> dict[str, Any] | None:
        return await fetch_one(
            conn,
            """
            select id::text, content_hash
            from knowledge_documents
            where knowledge_scope_id = %(knowledge_scope_id)s
              and source_uri = %(source_uri)s
            """,
            {
                "knowledge_scope_id": knowledge_scope_id,
                "source_uri": source_uri,
            },
        )

    async def insert_knowledge_document(
        self,
        conn: AsyncConnection,
        *,
        knowledge_scope_id: str,
        source_type: str,
        source_uri: str,
        title: str,
        content_hash: str,
        metadata_jsonb: dict[str, Any],
        node_path: str | None = None,
    ) -> str:
        row = await fetch_one(
            conn,
            """
            insert into knowledge_documents (
                knowledge_scope_id,
                source_type,
                source_uri,
                title,
                content_hash,
                metadata_jsonb,
                node_path
            ) values (
                %(knowledge_scope_id)s,
                %(source_type)s,
                %(source_uri)s,
                %(title)s,
                %(content_hash)s,
                %(metadata_jsonb)s,
                %(node_path)s
            )
            returning id::text
            """,
            {
                "knowledge_scope_id": knowledge_scope_id,
                "source_type": source_type,
                "source_uri": source_uri,
                "title": title,
                "content_hash": content_hash,
                "metadata_jsonb": Jsonb(metadata_jsonb),
                "node_path": node_path,
            },
        )
        if row is None:
            raise DatabaseExecutionError("insert_knowledge_document returned no row")
        return row["id"]

    async def update_knowledge_document(
        self,
        conn: AsyncConnection,
        *,
        document_id: str,
        source_type: str,
        title: str,
        content_hash: str,
        metadata_jsonb: dict[str, Any],
        node_path: str | None = None,
    ) -> None:
        await execute(
            conn,
            """
            update knowledge_documents
            set source_type = %(source_type)s,
                title = %(title)s,
                content_hash = %(content_hash)s,
                metadata_jsonb = %(metadata_jsonb)s,
                node_path = %(node_path)s,
                updated_at_utc = now()
            where id = %(document_id)s
            """,
            {
                "document_id": document_id,
                "source_type": source_type,
                "title": title,
                "content_hash": content_hash,
                "metadata_jsonb": Jsonb(metadata_jsonb),
                "node_path": node_path,
            },
        )

    async def upsert_knowledge_document(
        self,
        conn: AsyncConnection,
        *,
        knowledge_scope_id: str,
        source_type: str,
        source_uri: str,
        title: str,
        content_hash: str,
        metadata_jsonb: dict[str, Any],
        node_path: str | None = None,
    ) -> tuple[str, str]:
        existing = await self.find_knowledge_document_by_source(
            conn, knowledge_scope_id, source_uri,
        )
        if existing is None:
            doc_id = await self.insert_knowledge_document(
                conn=conn,
                knowledge_scope_id=knowledge_scope_id,
                source_type=source_type,
                source_uri=source_uri,
                title=title,
                content_hash=content_hash,
                metadata_jsonb=metadata_jsonb,
                node_path=node_path,
            )
            return doc_id, "inserted"
        if existing["content_hash"] == content_hash:
            return existing["id"], "unchanged"
        await self.update_knowledge_document(
            conn=conn,
            document_id=existing["id"],
            source_type=source_type,
            title=title,
            content_hash=content_hash,
            metadata_jsonb=metadata_jsonb,
            node_path=node_path,
        )
        return existing["id"], "updated"

    async def resolve_ingestion_context(
        self,
        conn: AsyncConnection,
        organization_code: str,
        workspace_code: str,
        knowledge_scope_code: str,
        package_code: str | None = None,
        assistant_instance_code: str | None = None,
        worker_code: str = "knowledge_ingestion_worker",
        triggered_by_email: str | None = None,
    ) -> IngestionContext:
        """Resolve public ingestion codes to database ids.

        Codes remain metadata. IDs returned by this method are the only values
        used for FK columns such as knowledge_ingestion_runs.knowledge_scope_id.
        """
        request = IngestionContextRequest(
            organization_code=organization_code,
            workspace_code=workspace_code,
            knowledge_scope_code=knowledge_scope_code,
            package_code=package_code,
            assistant_instance_code=assistant_instance_code,
            worker_code=worker_code,
            triggered_by_email=triggered_by_email,
        )
        errors = request.validate()
        if errors:
            raise ValueError(
                f"Ingestion context validation failed: {'; '.join(errors)}"
            )

        organization = await fetch_one(
            conn,
            """
            select id::text
            from core_organizations
            where organization_code = %(organization_code)s
              and status = 'active'
            """,
            {"organization_code": organization_code},
        )
        if organization is None:
            raise ValueError(f"organization_code not found: {organization_code}")

        workspace = await fetch_one(
            conn,
            """
            select id::text, organization_id::text
            from core_workspaces
            where slug = %(workspace_code)s
              and status in ('active', 'testing')
            """,
            {"workspace_code": workspace_code},
        )
        if workspace is None:
            raise ValueError(f"workspace_code not found: {workspace_code}")
        if workspace["organization_id"] != organization["id"]:
            raise ValueError(
                "workspace_code does not belong to organization_code: "
                f"{workspace_code} -> {organization_code}"
            )

        knowledge_scope = await fetch_one(
            conn,
            """
            select id::text
            from knowledge_scopes
            where workspace_id = %(workspace_id)s::uuid
              and scope_code = %(knowledge_scope_code)s
              and status in ('active', 'testing')
            """,
            {
                "workspace_id": workspace["id"],
                "knowledge_scope_code": knowledge_scope_code,
            },
        )
        if knowledge_scope is None:
            raise ValueError(
                "knowledge_scope_code not found for workspace_code: "
                f"{knowledge_scope_code} -> {workspace_code}"
            )

        automation_package_id: str | None = None
        if package_code:
            package = await fetch_one(
                conn,
                """
                select id::text
                from automation_packages
                where workspace_id = %(workspace_id)s::uuid
                  and package_code = %(package_code)s
                  and status in ('active', 'testing', 'paused')
                """,
                {"workspace_id": workspace["id"], "package_code": package_code},
            )
            if package is None:
                raise ValueError(
                    "package_code not found for workspace_code: "
                    f"{package_code} -> {workspace_code}"
                )
            automation_package_id = package["id"]

        assistant_instance_id: str | None = None
        if assistant_instance_code:
            assistant = await fetch_one(
                conn,
                """
                select id::text
                from assistant_instances
                where workspace_id = %(workspace_id)s::uuid
                  and assistant_code = %(assistant_instance_code)s
                  and status in ('active', 'testing')
                """,
                {
                    "workspace_id": workspace["id"],
                    "assistant_instance_code": assistant_instance_code,
                },
            )
            if assistant is None:
                raise ValueError(
                    "assistant_instance_code not found for workspace_code: "
                    f"{assistant_instance_code} -> {workspace_code}"
                )
            assistant_instance_id = assistant["id"]

        worker = await fetch_one(
            conn,
            """
            select id::text
            from worker_definitions
            where worker_code = %(worker_code)s
              and status in ('active', 'testing')
            """,
            {"worker_code": worker_code},
        )
        if worker is None:
            raise ValueError(f"worker_code not found: {worker_code}")

        triggered_by_user_id: str | None = None
        if triggered_by_email:
            user = await fetch_one(
                conn,
                """
                select id::text
                from core_users
                where lower(email) = lower(%(triggered_by_email)s)
                  and status in ('invited', 'active')
                """,
                {"triggered_by_email": triggered_by_email},
            )
            if user is None:
                raise ValueError(
                    f"triggered_by_email not found: {triggered_by_email}"
                )
            triggered_by_user_id = user["id"]

        return IngestionContext(
            organization_code=organization_code,
            organization_id=organization["id"],
            workspace_code=workspace_code,
            workspace_id=workspace["id"],
            knowledge_scope_code=knowledge_scope_code,
            knowledge_scope_id=knowledge_scope["id"],
            package_code=package_code,
            automation_package_id=automation_package_id,
            assistant_instance_code=assistant_instance_code,
            assistant_instance_id=assistant_instance_id,
            worker_code=worker_code,
            worker_definition_id=worker["id"],
            triggered_by_email=triggered_by_email,
            triggered_by_user_id=triggered_by_user_id,
            warnings=[],
        )

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
                organization_id::text,
                workspace_id::text,
                triggered_by_user_id::text,
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

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

    async def delete_chunks_for_document(
        self,
        conn: AsyncConnection,
        document_id: str,
    ) -> int:
        return await execute(
            conn,
            "delete from knowledge_chunks where knowledge_document_id = %(document_id)s",
            {"document_id": document_id},
        ) or 0

    async def insert_knowledge_chunk(
        self,
        conn: AsyncConnection,
        *,
        document_id: str,
        chunk_index: int,
        title: str,
        content: str,
        metadata_jsonb: dict[str, Any],
        token_count: int | None = None,
        node_path: str | None = None,
        permission_tags: list[str] | None = None,
    ) -> None:
        await execute(
            conn,
            """
            insert into knowledge_chunks (
                knowledge_document_id,
                chunk_index,
                title,
                content,
                metadata_jsonb,
                token_count,
                node_path,
                permission_tags
            ) values (
                %(document_id)s,
                %(chunk_index)s,
                %(title)s,
                %(content)s,
                %(metadata_jsonb)s,
                %(token_count)s,
                %(node_path)s,
                %(permission_tags)s
            )
            """,
            {
                "document_id": document_id,
                "chunk_index": chunk_index,
                "title": title,
                "content": content,
                "metadata_jsonb": Jsonb(metadata_jsonb),
                "token_count": token_count,
                "node_path": node_path,
                "permission_tags": permission_tags,
            },
        )

    async def replace_chunks_for_document(
        self,
        conn: AsyncConnection,
        *,
        document_id: str,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Delete old chunks and insert new ones in a single operation.

        Each chunk dict must have: chunk_index, title, content, metadata_jsonb.
        Optional: token_count, node_path, permission_tags.
        Returns the number of chunks inserted.
        """
        await self.delete_chunks_for_document(conn, document_id)
        count = 0
        for chunk in chunks:
            await self.insert_knowledge_chunk(
                conn=conn,
                document_id=document_id,
                chunk_index=chunk["chunk_index"],
                title=chunk.get("title", ""),
                content=chunk["content"],
                metadata_jsonb=chunk.get("metadata_jsonb", {}),
                token_count=chunk.get("token_count"),
                node_path=chunk.get("node_path"),
                permission_tags=chunk.get("permission_tags"),
            )
            count += 1
        return count

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

    async def find_embedding_model_id(
        self,
        conn: AsyncConnection,
        provider_code: str = "openai",
        model_code: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ) -> str | None:
        row = await fetch_one(
            conn,
            """
            select embedding_model_id::text
            from knowledge_embedding_models
            where provider_code = %(provider_code)s
              and model_code = %(model_code)s
              and dimension = %(dimensions)s
              and status = 'active'
            """,
            {
                "provider_code": provider_code,
                "model_code": model_code,
                "dimensions": dimensions,
            },
        )
        return row["embedding_model_id"] if row else None

    async def list_pending_chunks_for_embedding(
        self,
        conn: AsyncConnection,
        knowledge_scope_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = ["kc.embedding_status = 'pending'"]
        params: dict[str, Any] = {"limit": limit}
        if knowledge_scope_id is not None:
            where.append("kd.knowledge_scope_id = %(knowledge_scope_id)s")
            params["knowledge_scope_id"] = knowledge_scope_id
        sql = f"""
            select
                kc.id::text as chunk_id,
                kc.knowledge_document_id::text as document_id,
                kd.knowledge_scope_id::text as knowledge_scope_id,
                kc.chunk_index,
                kc.title,
                kc.content,
                kc.metadata_jsonb ->> 'content_hash' as content_hash,
                kc.metadata_jsonb
            from knowledge_chunks kc
            join knowledge_documents kd on kd.id = kc.knowledge_document_id
            where {' and '.join(where)}
            order by kc.chunk_index
            limit %(limit)s
        """
        rows = await conn.execute(sql, params)
        return await rows.fetchall() or []

    async def find_existing_chunk_embedding(
        self,
        conn: AsyncConnection,
        chunk_id: str,
        embedding_model_id: str,
        content_hash: str | None = None,
    ) -> dict[str, Any] | None:
        if content_hash is not None:
            row = await fetch_one(
                conn,
                """
                select chunk_embedding_id::text, embedding_status, content_hash
                from knowledge_chunk_embeddings
                where knowledge_chunk_id = %(chunk_id)s
                  and embedding_model_id = %(embedding_model_id)s
                  and content_hash = %(content_hash)s
                """,
                {
                    "chunk_id": chunk_id,
                    "embedding_model_id": embedding_model_id,
                    "content_hash": content_hash,
                },
            )
        else:
            row = await fetch_one(
                conn,
                """
                select chunk_embedding_id::text, embedding_status, content_hash
                from knowledge_chunk_embeddings
                where knowledge_chunk_id = %(chunk_id)s
                  and embedding_model_id = %(embedding_model_id)s
                """,
                {
                    "chunk_id": chunk_id,
                    "embedding_model_id": embedding_model_id,
                },
            )
        return row

    async def insert_chunk_embedding(
        self,
        conn: AsyncConnection,
        *,
        chunk_id: str,
        knowledge_scope_id: str,
        embedding_model_id: str,
        embedding: list[float],
        content_hash: str,
        metadata_jsonb: dict[str, Any] | None = None,
    ) -> str:
        row = await fetch_one(
            conn,
            """
            insert into knowledge_chunk_embeddings (
                knowledge_chunk_id,
                knowledge_scope_id,
                embedding_model_id,
                embedding,
                embedding_status,
                content_hash,
                metadata_jsonb,
                embedded_at_utc
            ) values (
                %(chunk_id)s,
                %(knowledge_scope_id)s,
                %(embedding_model_id)s,
                %(embedding)s,
                'ready',
                %(content_hash)s,
                %(metadata_jsonb)s,
                now()
            )
            returning chunk_embedding_id::text
            """,
            {
                "chunk_id": chunk_id,
                "knowledge_scope_id": knowledge_scope_id,
                "embedding_model_id": embedding_model_id,
                "embedding": embedding,
                "content_hash": content_hash,
                "metadata_jsonb": Jsonb(metadata_jsonb or {}),
            },
        )
        if row is None:
            raise DatabaseExecutionError("insert_chunk_embedding returned no row")
        return row["chunk_embedding_id"]

    async def update_chunk_embedding_status(
        self,
        conn: AsyncConnection,
        chunk_id: str,
        status: str,
    ) -> None:
        await execute(
            conn,
            """
            update knowledge_chunks
            set embedding_status = %(status)s,
                updated_at_utc = now()
            where id = %(chunk_id)s
            """,
            {"chunk_id": chunk_id, "status": status},
        )

    async def mark_chunk_embedding_ready(
        self,
        conn: AsyncConnection,
        chunk_embedding_id: str,
    ) -> None:
        await execute(
            conn,
            """
            update knowledge_chunk_embeddings
            set embedding_status = 'ready',
                embedded_at_utc = now(),
                updated_at_utc = now()
            where chunk_embedding_id = %(chunk_embedding_id)s
            """,
            {"chunk_embedding_id": chunk_embedding_id},
        )

    async def search_chunks_by_embedding(
        self,
        conn: AsyncConnection,
        *,
        knowledge_scope_id: str,
        query_embedding: list[float],
        embedding_version: str,
        limit: int = 5,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 50:
            raise ValueError(f"limit must be between 1 and 50, got {limit}")
        if not embedding_version:
            raise ValueError("embedding_version is required for retrieval")
        sql = """
            select
                kce.chunk_embedding_id::text,
                kc.id::text as chunk_id,
                kc.knowledge_document_id::text as document_id,
                kd.source_uri,
                kd.knowledge_scope_id::text as scope_id,
                kc.chunk_index,
                kc.title,
                kc.content,
                kc.node_path,
                kc.metadata_jsonb as chunk_metadata,
                kce.metadata_jsonb as embedding_metadata,
                1 - (kce.embedding <=> %(query_embedding)s::vector) as score
            from knowledge_chunk_embeddings kce
            join knowledge_chunks kc on kc.id = kce.knowledge_chunk_id
            join knowledge_documents kd on kd.id = kc.knowledge_document_id
            where kce.embedding_status = 'ready'
              and kce.knowledge_scope_id = %(knowledge_scope_id)s
              and kce.embedding is not null
              and kce.metadata_jsonb->>'embedding_version' = %(embedding_version)s
        """
        params: dict[str, Any] = {
            "query_embedding": query_embedding,
            "knowledge_scope_id": knowledge_scope_id,
            "embedding_version": embedding_version,
            "limit": limit,
        }
        if min_score is not None:
            sql += " and (1 - (kce.embedding <=> %(query_embedding)s::vector)) >= %(min_score)s"
            params["min_score"] = min_score
        sql += """
            order by kce.embedding <=> %(query_embedding)s::vector
            limit %(limit)s
        """
        rows = await conn.execute(sql, params)
        return await rows.fetchall() or []

    async def mark_chunk_embedding_failed(
        self,
        conn: AsyncConnection,
        chunk_embedding_id: str,
    ) -> None:
        await execute(
            conn,
            """
            update knowledge_chunk_embeddings
            set embedding_status = 'failed',
                updated_at_utc = now()
            where chunk_embedding_id = %(chunk_embedding_id)s
            """,
            {"chunk_embedding_id": chunk_embedding_id},
        )

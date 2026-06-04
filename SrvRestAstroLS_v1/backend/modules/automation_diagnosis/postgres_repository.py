"""PostgreSQL write repository for automation diagnosis."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from modules.db.transaction import execute, fetch_all, fetch_one

from .assistant_instances import AssistantInstanceConfig
from .schemas import DiagnosisEvent, DiagnosisSession, to_dict


class AutomationDiagnosisPostgresRepository:
    """Write-side repository for diagnosis package installations and sessions.

    Repositories receive an existing connection/transaction from the caller.
    SQL stays here; service and route layers should not assemble SQL.
    """

    async def upsert_package_installation(
        self,
        conn: AsyncConnection,
        config: AssistantInstanceConfig,
    ) -> dict[str, str]:
        workspace = await self._upsert_workspace(conn, config)
        knowledge_scope = await self._upsert_knowledge_scope(conn, config, workspace["id"])
        assistant = await self._upsert_assistant_instance(conn, config, workspace["id"], knowledge_scope["id"])
        package = await self._upsert_automation_package(conn, config, workspace["id"], assistant["id"])
        await self._upsert_knowledge_scope_binding(
            conn,
            knowledge_scope_id=knowledge_scope["id"],
            workspace_id=workspace["id"],
            binding_type="assistant_instance",
            bound_entity_id=assistant["id"],
            metadata={"assistant_instance_id": config.assistant_instance_id},
        )
        await self._upsert_knowledge_scope_binding(
            conn,
            knowledge_scope_id=knowledge_scope["id"],
            workspace_id=workspace["id"],
            binding_type="automation_package",
            bound_entity_id=package["id"],
            metadata={"automation_package_id": config.automation_package_id},
        )

        package_worker_ids: dict[str, str] = {}
        for worker in config.package_workers:
            worker_definition = await self._get_worker_definition(conn, worker.worker_definition_id)
            package_worker = await self._upsert_package_worker(
                conn,
                config=config,
                workspace_id=workspace["id"],
                package_id=package["id"],
                worker_definition_id=worker_definition["id"],
                knowledge_scope_id=knowledge_scope["id"],
                package_worker_code=worker.id,
                mode=str(worker.config.get("mode") or "assisted"),
            )
            await self._upsert_package_worker_config(conn, package_worker["id"], worker.config)
            await self._upsert_knowledge_scope_binding(
                conn,
                knowledge_scope_id=knowledge_scope["id"],
                workspace_id=workspace["id"],
                binding_type="package_worker",
                bound_entity_id=package_worker["id"],
                metadata={"package_worker_code": worker.id, "worker_definition_id": worker.worker_definition_id},
                is_default=False,
            )
            package_worker_ids[worker.id] = package_worker["id"]

        return {
            "workspace_id": workspace["id"],
            "assistant_instance_id": assistant["id"],
            "automation_package_id": package["id"],
            "knowledge_scope_id": knowledge_scope["id"],
            "package_worker_ids": package_worker_ids,
        }

    async def upsert_session(self, conn: AsyncConnection, session: DiagnosisSession) -> dict[str, str]:
        refs = await self.get_installation_refs(conn, session)
        row = await fetch_one(
            conn,
            """
            insert into automation_diagnosis_sessions (
                public_session_id,
                workspace_id,
                assistant_instance_id,
                automation_package_id,
                knowledge_scope_id,
                organization_code,
                workspace_slug,
                assistant_instance_code,
                automation_package_code,
                knowledge_scope_code,
                source_url,
                site_channel,
                lead_owner,
                locale,
                market,
                status,
                correlation_id,
                visitor_jsonb,
                package_worker_codes_jsonb,
                cost_attribution_jsonb,
                metadata_jsonb,
                result_jsonb,
                contact_jsonb,
                updated_at_utc
            ) values (
                %(public_session_id)s,
                %(workspace_id)s,
                %(assistant_instance_id)s,
                %(automation_package_id)s,
                %(knowledge_scope_id)s,
                %(organization_code)s,
                %(workspace_slug)s,
                %(assistant_instance_code)s,
                %(automation_package_code)s,
                %(knowledge_scope_code)s,
                %(source_url)s,
                %(site_channel)s,
                %(lead_owner)s,
                %(locale)s,
                %(market)s,
                %(status)s,
                %(correlation_id)s,
                %(visitor_jsonb)s,
                %(package_worker_codes_jsonb)s,
                %(cost_attribution_jsonb)s,
                %(metadata_jsonb)s,
                %(result_jsonb)s,
                %(contact_jsonb)s,
                now()
            )
            on conflict (public_session_id) do update set
                status = excluded.status,
                source_url = excluded.source_url,
                visitor_jsonb = excluded.visitor_jsonb,
                package_worker_codes_jsonb = excluded.package_worker_codes_jsonb,
                cost_attribution_jsonb = excluded.cost_attribution_jsonb,
                metadata_jsonb = excluded.metadata_jsonb,
                result_jsonb = excluded.result_jsonb,
                contact_jsonb = excluded.contact_jsonb,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "public_session_id": session.id,
                "workspace_id": refs["workspace_id"],
                "assistant_instance_id": refs["assistant_instance_id"],
                "automation_package_id": refs["automation_package_id"],
                "knowledge_scope_id": refs["knowledge_scope_id"],
                "organization_code": session.organization_id,
                "workspace_slug": session.workspace_id,
                "assistant_instance_code": session.assistant_instance_id,
                "automation_package_code": session.automation_package_id,
                "knowledge_scope_code": session.knowledge_scope_id,
                "source_url": session.source_url,
                "site_channel": session.site_channel,
                "lead_owner": session.lead_owner,
                "locale": session.locale,
                "market": session.market,
                "status": session.status if session.status != "active" or session.result is None else "classified",
                "correlation_id": session.correlation_id,
                "visitor_jsonb": Jsonb(session.visitor),
                "package_worker_codes_jsonb": Jsonb(session.package_worker_ids),
                "cost_attribution_jsonb": Jsonb(session.cost_attribution),
                "metadata_jsonb": Jsonb(session.metadata),
                "result_jsonb": Jsonb(session.result) if session.result is not None else None,
                "contact_jsonb": Jsonb(session.contact) if session.contact is not None else None,
            },
        )
        return {**refs, "diagnosis_session_id": row["id"]}

    async def upsert_answers(self, conn: AsyncConnection, session: DiagnosisSession, diagnosis_session_id: str) -> None:
        for answer in session.answers.values():
            await execute(
                conn,
                """
                insert into automation_diagnosis_answers (
                    session_id,
                    step_id,
                    selected_jsonb,
                    free_text,
                    normalized_text,
                    metadata_jsonb,
                    updated_at_utc
                ) values (
                    %(session_id)s,
                    %(step_id)s,
                    %(selected_jsonb)s,
                    %(free_text)s,
                    %(normalized_text)s,
                    %(metadata_jsonb)s,
                    now()
                )
                on conflict (session_id, step_id) do update set
                    selected_jsonb = excluded.selected_jsonb,
                    free_text = excluded.free_text,
                    normalized_text = excluded.normalized_text,
                    metadata_jsonb = excluded.metadata_jsonb,
                    updated_at_utc = now()
                """,
                {
                    "session_id": diagnosis_session_id,
                    "step_id": answer.step_id,
                    "selected_jsonb": Jsonb(answer.selected),
                    "free_text": answer.free_text,
                    "normalized_text": answer.normalized_text,
                    "metadata_jsonb": Jsonb(answer.metadata),
                },
            )

    async def upsert_lead_from_session(
        self,
        conn: AsyncConnection,
        session: DiagnosisSession,
        refs: dict[str, str],
    ) -> dict[str, str] | None:
        if session.result is None:
            return None
        card = session.result.get("internal_card") or {}
        row = await fetch_one(
            conn,
            """
            insert into automation_diagnosis_leads (
                session_id,
                workspace_id,
                assistant_instance_id,
                automation_package_id,
                knowledge_scope_id,
                lead_type,
                lead_owner,
                site_channel,
                locale,
                status,
                classification,
                automation_mode,
                recommended_package_type,
                score_total,
                next_step,
                internal_card_jsonb,
                contact_jsonb,
                updated_at_utc
            ) values (
                %(session_id)s,
                %(workspace_id)s,
                %(assistant_instance_id)s,
                %(automation_package_id)s,
                %(knowledge_scope_id)s,
                %(lead_type)s,
                %(lead_owner)s,
                %(site_channel)s,
                %(locale)s,
                %(status)s,
                %(classification)s,
                %(automation_mode)s,
                %(recommended_package_type)s,
                %(score_total)s,
                %(next_step)s,
                %(internal_card_jsonb)s,
                %(contact_jsonb)s,
                now()
            )
            on conflict (session_id) do update set
                status = excluded.status,
                classification = excluded.classification,
                automation_mode = excluded.automation_mode,
                recommended_package_type = excluded.recommended_package_type,
                score_total = excluded.score_total,
                next_step = excluded.next_step,
                internal_card_jsonb = excluded.internal_card_jsonb,
                contact_jsonb = excluded.contact_jsonb,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "session_id": refs["diagnosis_session_id"],
                "workspace_id": refs["workspace_id"],
                "assistant_instance_id": refs["assistant_instance_id"],
                "automation_package_id": refs["automation_package_id"],
                "knowledge_scope_id": refs["knowledge_scope_id"],
                "lead_type": card.get("lead_type") or "automation_opportunity",
                "lead_owner": session.lead_owner,
                "site_channel": session.site_channel,
                "locale": session.locale,
                "status": self._lead_status(str(session.result.get("classification") or "")),
                "classification": session.result.get("classification"),
                "automation_mode": session.result.get("automation_mode"),
                "recommended_package_type": session.result.get("recommended_package_type"),
                "score_total": session.result.get("score_total"),
                "next_step": card.get("next_step"),
                "internal_card_jsonb": Jsonb(card),
                "contact_jsonb": Jsonb(session.contact or {}),
            },
        )
        return {"lead_id": row["id"]}

    async def insert_event(self, conn: AsyncConnection, event: DiagnosisEvent, diagnosis_session_id: str | None = None) -> bool:
        workspace_id = await self._workspace_uuid(conn, event.workspace_id)
        payload = {
            **event.payload,
            "organization_id": event.organization_id,
            "assistant_instance_id": event.assistant_instance_id,
            "automation_package_id": event.automation_package_id,
            "knowledge_scope_id": event.knowledge_scope_id,
            "site_channel": event.site_channel,
            "lead_owner": event.lead_owner,
            "locale": event.locale,
            "session_id": event.session_id,
        }
        rowcount = await execute(
            conn,
            """
            insert into core_events (
                workspace_id,
                event_name,
                entity_type,
                entity_id,
                correlation_id,
                payload_jsonb,
                occurred_at_utc
            )
            select
                %(workspace_id)s,
                %(event_name)s,
                'automation_diagnosis_session',
                %(entity_id)s,
                %(correlation_id)s,
                %(payload_jsonb)s,
                %(occurred_at_utc)s
            where not exists (
                select 1
                from core_events
                where workspace_id is not distinct from %(workspace_id)s
                  and event_name = %(event_name)s
                  and entity_type = 'automation_diagnosis_session'
                  and entity_id is not distinct from %(entity_id)s
                  and correlation_id is not distinct from %(correlation_id)s
                  and occurred_at_utc = %(occurred_at_utc)s
                  and payload_jsonb = %(payload_jsonb)s
            )
            """,
            {
                "workspace_id": workspace_id,
                "event_name": event.event_name,
                "entity_id": diagnosis_session_id,
                "correlation_id": event.correlation_id,
                "payload_jsonb": Jsonb(payload),
                "occurred_at_utc": event.timestamp_utc,
            },
        )
        return bool(rowcount)

    async def persist_session_snapshot(
        self,
        conn: AsyncConnection,
        session: DiagnosisSession,
        events: list[DiagnosisEvent] | None = None,
    ) -> dict[str, str]:
        refs = await self.upsert_session(conn, session)
        await self.upsert_answers(conn, session, refs["diagnosis_session_id"])
        lead = await self.upsert_lead_from_session(conn, session, refs)
        for event in events or []:
            await self.insert_event(conn, event, refs["diagnosis_session_id"])
        if lead:
            refs.update(lead)
        return refs

    async def get_installation_refs(self, conn: AsyncConnection, session: DiagnosisSession) -> dict[str, str]:
        row = await fetch_one(
            conn,
            """
            select
                w.id::text as workspace_id,
                ai.id::text as assistant_instance_id,
                ap.id::text as automation_package_id,
                ks.id::text as knowledge_scope_id
            from core_workspaces w
            join assistant_instances ai
              on ai.workspace_id = w.id
             and ai.assistant_code = %(assistant_instance_code)s
            join automation_packages ap
              on ap.workspace_id = w.id
             and ap.package_code = %(automation_package_code)s
            join knowledge_scopes ks
              on ks.workspace_id = w.id
             and ks.scope_code = %(knowledge_scope_code)s
            where w.slug = %(workspace_slug)s
            """,
            {
                "workspace_slug": session.workspace_id,
                "assistant_instance_code": session.assistant_instance_id,
                "automation_package_code": session.automation_package_id,
                "knowledge_scope_code": session.knowledge_scope_id,
            },
        )
        if row is None:
            raise ValueError(
                "Package installation not found for "
                f"assistant_instance_id={session.assistant_instance_id!r} "
                f"workspace_id={session.workspace_id!r}"
            )
        return row

    async def _upsert_workspace(self, conn: AsyncConnection, config: AssistantInstanceConfig) -> dict[str, str]:
        return await self._required_row(
            conn,
            """
            insert into core_workspaces (slug, display_name, timezone, status, metadata_jsonb, updated_at_utc)
            values (%(slug)s, %(display_name)s, 'UTC', 'active', %(metadata_jsonb)s, now())
            on conflict (slug) do update set
                display_name = excluded.display_name,
                metadata_jsonb = core_workspaces.metadata_jsonb || excluded.metadata_jsonb,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "slug": config.workspace_id,
                "display_name": config.workspace_name,
                "metadata_jsonb": Jsonb({"organization_id": config.organization_id, "organization_name": config.organization_name}),
            },
        )

    async def _upsert_knowledge_scope(self, conn: AsyncConnection, config: AssistantInstanceConfig, workspace_id: str) -> dict[str, str]:
        return await self._required_row(
            conn,
            """
            insert into knowledge_scopes (workspace_id, scope_code, name, retrieval_mode, graph_enabled, settings_jsonb, status, updated_at_utc)
            values (%(workspace_id)s, %(scope_code)s, %(name)s, 'rag', false, %(settings_jsonb)s, 'active', now())
            on conflict (workspace_id, scope_code) where workspace_id is not null do update set
                name = excluded.name,
                retrieval_mode = excluded.retrieval_mode,
                settings_jsonb = excluded.settings_jsonb,
                status = excluded.status,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "workspace_id": workspace_id,
                "scope_code": config.knowledge_scope_id,
                "name": f"{config.assistant_instance_name} Knowledge",
                "settings_jsonb": Jsonb({"arangodb_scope": config.arangodb_scope, "milvus_scope": config.milvus_scope}),
            },
        )

    async def _upsert_assistant_instance(
        self,
        conn: AsyncConnection,
        config: AssistantInstanceConfig,
        workspace_id: str,
        knowledge_scope_id: str,
    ) -> dict[str, str]:
        return await self._required_row(
            conn,
            """
            insert into assistant_instances (
                workspace_id,
                assistant_code,
                assistant_type,
                name,
                status,
                public_config_jsonb,
                default_knowledge_scope_id,
                settings_jsonb,
                updated_at_utc
            ) values (
                %(workspace_id)s,
                %(assistant_code)s,
                'sales_diagnosis',
                %(name)s,
                'active',
                %(public_config_jsonb)s,
                %(default_knowledge_scope_id)s,
                %(settings_jsonb)s,
                now()
            )
            on conflict (workspace_id, assistant_code) where assistant_code is not null do update set
                name = excluded.name,
                status = excluded.status,
                public_config_jsonb = excluded.public_config_jsonb,
                default_knowledge_scope_id = excluded.default_knowledge_scope_id,
                settings_jsonb = excluded.settings_jsonb,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "workspace_id": workspace_id,
                "assistant_code": config.assistant_instance_id,
                "name": config.assistant_instance_name,
                "public_config_jsonb": Jsonb({
                    "site_channel": config.site_channel,
                    "default_locale": config.default_locale,
                    "supported_locales": list(config.supported_locales),
                }),
                "default_knowledge_scope_id": knowledge_scope_id,
                "settings_jsonb": Jsonb(config.to_session_metadata()),
            },
        )

    async def _upsert_automation_package(
        self,
        conn: AsyncConnection,
        config: AssistantInstanceConfig,
        workspace_id: str,
        assistant_instance_id: str,
    ) -> dict[str, str]:
        return await self._required_row(
            conn,
            """
            insert into automation_packages (
                workspace_id,
                assistant_instance_id,
                package_code,
                package_name,
                plan_code,
                status,
                enabled_features_jsonb,
                settings_jsonb,
                updated_at_utc
            ) values (
                %(workspace_id)s,
                %(assistant_instance_id)s,
                %(package_code)s,
                %(package_name)s,
                'starter',
                'active',
                %(enabled_features_jsonb)s,
                %(settings_jsonb)s,
                now()
            )
            on conflict (workspace_id, package_code) do update set
                assistant_instance_id = excluded.assistant_instance_id,
                package_name = excluded.package_name,
                status = excluded.status,
                enabled_features_jsonb = excluded.enabled_features_jsonb,
                settings_jsonb = excluded.settings_jsonb,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "workspace_id": workspace_id,
                "assistant_instance_id": assistant_instance_id,
                "package_code": config.automation_package_id,
                "package_name": config.automation_package_name,
                "enabled_features_jsonb": Jsonb(["diagnosis.basic", "rag.simple", "events.basic"]),
                "settings_jsonb": Jsonb({"lead_owner": config.lead_owner, "site_channel": config.site_channel}),
            },
        )

    async def _get_worker_definition(self, conn: AsyncConnection, worker_code: str) -> dict[str, str]:
        row = await fetch_one(
            conn,
            "select id::text from worker_definitions where worker_code = %(worker_code)s",
            {"worker_code": worker_code},
        )
        if row is None:
            raise ValueError(f"Missing worker_definition seed: {worker_code}")
        return row

    async def _upsert_package_worker(
        self,
        conn: AsyncConnection,
        config: AssistantInstanceConfig,
        workspace_id: str,
        package_id: str,
        worker_definition_id: str,
        knowledge_scope_id: str,
        package_worker_code: str,
        mode: str,
    ) -> dict[str, str]:
        return await self._required_row(
            conn,
            """
            insert into package_workers (
                workspace_id,
                automation_package_id,
                worker_definition_id,
                package_worker_code,
                status,
                mode,
                knowledge_scope_id,
                updated_at_utc
            ) values (
                %(workspace_id)s,
                %(automation_package_id)s,
                %(worker_definition_id)s,
                %(package_worker_code)s,
                'active',
                %(mode)s,
                %(knowledge_scope_id)s,
                now()
            )
            on conflict (automation_package_id, package_worker_code) do update set
                worker_definition_id = excluded.worker_definition_id,
                status = excluded.status,
                mode = excluded.mode,
                knowledge_scope_id = excluded.knowledge_scope_id,
                updated_at_utc = now()
            returning id::text
            """,
            {
                "workspace_id": workspace_id,
                "automation_package_id": package_id,
                "worker_definition_id": worker_definition_id,
                "package_worker_code": package_worker_code,
                "mode": mode if mode in {"read_only", "assisted", "approval_required", "execution", "blocked"} else "assisted",
                "knowledge_scope_id": knowledge_scope_id,
            },
        )

    async def _upsert_package_worker_config(self, conn: AsyncConnection, package_worker_id: str, config: dict[str, Any]) -> None:
        await execute(
            conn,
            """
            insert into package_worker_configs (
                package_worker_id,
                config_jsonb,
                allowed_actions_jsonb,
                blocked_actions_jsonb,
                requires_human_approval,
                updated_at_utc
            ) values (
                %(package_worker_id)s,
                %(config_jsonb)s,
                %(allowed_actions_jsonb)s,
                %(blocked_actions_jsonb)s,
                %(requires_human_approval)s,
                now()
            )
            on conflict (package_worker_id) do update set
                config_jsonb = excluded.config_jsonb,
                allowed_actions_jsonb = excluded.allowed_actions_jsonb,
                blocked_actions_jsonb = excluded.blocked_actions_jsonb,
                requires_human_approval = excluded.requires_human_approval,
                updated_at_utc = now()
            """,
            {
                "package_worker_id": package_worker_id,
                "config_jsonb": Jsonb(config),
                "allowed_actions_jsonb": Jsonb(config.get("allowed_actions", [])),
                "blocked_actions_jsonb": Jsonb(config.get("blocked_actions", [])),
                "requires_human_approval": bool(config.get("requires_human_approval", False)),
            },
        )

    async def _upsert_knowledge_scope_binding(
        self,
        conn: AsyncConnection,
        knowledge_scope_id: str,
        workspace_id: str,
        binding_type: str,
        bound_entity_id: str,
        metadata: dict[str, Any],
        is_default: bool = True,
    ) -> None:
        await execute(
            conn,
            """
            insert into knowledge_scope_bindings (
                knowledge_scope_id,
                workspace_id,
                binding_type,
                bound_entity_id,
                is_default,
                metadata_jsonb
            ) values (
                %(knowledge_scope_id)s,
                %(workspace_id)s,
                %(binding_type)s,
                %(bound_entity_id)s,
                %(is_default)s,
                %(metadata_jsonb)s
            )
            on conflict do nothing
            """,
            {
                "knowledge_scope_id": knowledge_scope_id,
                "workspace_id": workspace_id,
                "binding_type": binding_type,
                "bound_entity_id": bound_entity_id,
                "is_default": is_default,
                "metadata_jsonb": Jsonb(metadata),
            },
        )

    async def _workspace_uuid(self, conn: AsyncConnection, workspace_slug: str) -> str:
        row = await fetch_one(conn, "select id::text from core_workspaces where slug = %(slug)s", {"slug": workspace_slug})
        if row is None:
            raise ValueError(f"Unknown workspace slug: {workspace_slug}")
        return row["id"]

    async def _required_row(self, conn: AsyncConnection, sql: str, params: dict[str, Any]) -> dict[str, str]:
        row = await fetch_one(conn, sql, params)
        if row is None:
            raise ValueError("Expected query to return a row")
        return row

    @staticmethod
    def _lead_status(classification: str) -> str:
        if classification == "not_recommended":
            return "not_recommended"
        if classification == "consulting_required":
            return "consulting_required"
        return "qualified"

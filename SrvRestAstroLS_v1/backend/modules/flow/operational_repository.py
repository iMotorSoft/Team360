"""PostgreSQL repository for correlated operational replies."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from modules.db.transaction import fetch_one
from modules.messaging.domain import InboundMessage

from .domain import (
    OperationalInterpretation,
    OperationalRoutingContext,
    OperationalStatus,
    OperationalWorkState,
)


_CONTEXT_COLUMNS = """
    frr.id::text as routing_id, frr.request_id::text,
    fr.conversation_id::text, frr.routing_key, frr.level,
    frr.status as routing_status,
    frr.destination, frr.outbound_external_message_id,
    frr.outbound_rfc_message_id,
    frr.outbound_observed_rfc_message_id
"""


def _context(row: dict | None) -> OperationalRoutingContext | None:
    return OperationalRoutingContext(**row) if row else None


def _work_state(row: dict | None) -> OperationalWorkState | None:
    if row is None:
        return None
    return OperationalWorkState(
        request_id=row["request_id"],
        routing_id=row["routing_id"],
        status=OperationalStatus(row["operational_status"]),
        first_response_at=row["first_response_at_utc"],
        first_responder=row["first_responder"],
    )


class FlowOperationalPostgresRepository:
    async def find_by_rfc_reference(
        self, conn: AsyncConnection, references: tuple[str, ...]
    ) -> OperationalRoutingContext | None:
        if not references:
            return None
        return _context(
            await fetch_one(
                conn,
                f"""
                select {_CONTEXT_COLUMNS}
                from flow_request_routings frr
                join flow_requests fr on fr.id = frr.request_id
                where frr.status = 'ASSIGNED'
                  and (
                    frr.outbound_observed_rfc_message_id = any(%(references)s)
                    or frr.outbound_rfc_message_id = any(%(references)s)
                  )
                order by (
                    frr.outbound_observed_rfc_message_id = any(%(references)s)
                ) desc
                limit 1
                """,
                {"references": list(references)},
            )
        )

    async def find_unambiguous_by_request_id(
        self, conn: AsyncConnection, request_id: str
    ) -> OperationalRoutingContext | None:
        return _context(
            await fetch_one(
                conn,
                f"""
                select {_CONTEXT_COLUMNS}
                from flow_request_routings frr
                join flow_requests fr on fr.id = frr.request_id
                where frr.request_id = %(request_id)s
                  and frr.status = 'ASSIGNED'
                  and not exists (
                      select 1 from flow_request_routings other
                      where other.request_id = frr.request_id
                        and other.status = 'ASSIGNED'
                        and other.id <> frr.id
                  )
                """,
                {"request_id": request_id},
            )
        )

    async def find_by_request_routing_key(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        routing_key: str,
    ) -> OperationalRoutingContext | None:
        return _context(
            await fetch_one(
                conn,
                f"""
                select {_CONTEXT_COLUMNS}
                from flow_request_routings frr
                join flow_requests fr on fr.id = frr.request_id
                where frr.request_id = %(request_id)s
                  and frr.routing_key = %(routing_key)s
                  and frr.status = 'ASSIGNED'
                """,
                {"request_id": request_id, "routing_key": routing_key},
            )
        )

    async def claim_message(
        self,
        conn: AsyncConnection,
        *,
        context: OperationalRoutingContext,
        message: InboundMessage,
    ) -> str | None:
        row = await fetch_one(
            conn,
            """
            insert into flow_messages (
                conversation_id, provider, external_message_id, direction,
                sender_address, recipients_jsonb, subject, text_body,
                occurred_at_utc, metadata_jsonb, processed_at_utc
            ) values (
                %(conversation_id)s, %(provider)s, %(external_message_id)s,
                'inbound', %(sender)s, %(recipients)s, %(subject)s,
                %(text_body)s, %(occurred_at)s, %(metadata)s, now()
            )
            on conflict (provider, external_message_id) do nothing
            returning id::text
            """,
            {
                "conversation_id": context.conversation_id,
                "provider": message.provider,
                "external_message_id": message.external_message_id,
                "sender": message.sender,
                "recipients": Jsonb(list(message.recipients)),
                "subject": message.subject,
                "text_body": message.text_body,
                "occurred_at": message.received_at,
                "metadata": Jsonb(dict(message.metadata)),
            },
        )
        return row["id"] if row else None

    async def ensure_work_state(
        self, conn: AsyncConnection, context: OperationalRoutingContext
    ) -> OperationalWorkState:
        row = await fetch_one(
            conn,
            """
            insert into flow_request_work_states (request_id, routing_id)
            values (%(request_id)s, %(routing_id)s)
            on conflict (routing_id) do update set
                request_id = flow_request_work_states.request_id
            returning request_id::text, routing_id::text, operational_status,
                      first_response_at_utc, first_responder
            """,
            {"request_id": context.request_id, "routing_id": context.routing_id},
        )
        state = _work_state(row)
        if state is None:
            raise RuntimeError("Flow operational work state upsert returned no row.")
        return state

    async def record_event(
        self,
        conn: AsyncConnection,
        *,
        context: OperationalRoutingContext,
        source_message_id: str,
        message: InboundMessage,
        correlation_method: str,
        interpretation: OperationalInterpretation,
    ) -> str:
        row = await fetch_one(
            conn,
            """
            insert into flow_request_operational_events (
                request_id, routing_id, source_message_id, provider,
                inbound_external_message_id, responder_address,
                response_received_at_utc, correlation_method,
                interpretation_action, interpretation_jsonb,
                ai_provider, ai_model, usage_jsonb, latency_ms
            ) values (
                %(request_id)s, %(routing_id)s, %(source_message_id)s,
                %(provider)s, %(external_message_id)s, %(responder)s,
                %(received_at)s, %(correlation_method)s, %(action)s,
                %(interpretation)s, %(ai_provider)s, %(ai_model)s,
                %(usage)s, %(latency_ms)s
            )
            returning id::text
            """,
            {
                "request_id": context.request_id,
                "routing_id": context.routing_id,
                "source_message_id": source_message_id,
                "provider": message.provider,
                "external_message_id": message.external_message_id,
                "responder": message.sender,
                "received_at": message.received_at,
                "correlation_method": correlation_method,
                "action": interpretation.action.value,
                "interpretation": Jsonb({"summary": interpretation.summary}),
                "ai_provider": interpretation.provider,
                "ai_model": interpretation.model,
                "usage": Jsonb(interpretation.usage),
                "latency_ms": interpretation.latency_ms,
            },
        )
        if row is None:
            raise RuntimeError("Flow operational event insert returned no row.")
        return row["id"]

    async def mark_in_progress(
        self,
        conn: AsyncConnection,
        *,
        context: OperationalRoutingContext,
        message: InboundMessage,
    ) -> OperationalWorkState:
        row = await fetch_one(
            conn,
            """
            update flow_request_work_states
            set operational_status = 'IN_PROGRESS',
                first_response_at_utc = coalesce(
                    first_response_at_utc, %(received_at)s
                ),
                first_responder = coalesce(first_responder, %(responder)s),
                updated_at_utc = now()
            where routing_id = %(routing_id)s
            returning request_id::text, routing_id::text, operational_status,
                      first_response_at_utc, first_responder
            """,
            {
                "routing_id": context.routing_id,
                "received_at": message.received_at,
                "responder": message.sender,
            },
        )
        state = _work_state(row)
        if state is None:
            raise RuntimeError("Flow IN_PROGRESS transition returned no row.")
        return state

    async def event_for_message(
        self, conn: AsyncConnection, provider: str, external_message_id: str
    ) -> dict[str, Any] | None:
        return await fetch_one(
            conn,
            """
            select id::text as event_id, request_id::text, routing_id::text,
                   interpretation_action, correlation_method,
                   response_received_at_utc
            from flow_request_operational_events
            where provider = %(provider)s
              and inbound_external_message_id = %(external_message_id)s
            """,
            {"provider": provider, "external_message_id": external_message_id},
        )

    async def evidence(
        self, conn: AsyncConnection, request_id: str, routing_id: str | None = None
    ) -> dict | None:
        return await fetch_one(
            conn,
            """
            select fws.request_id::text, fws.routing_id::text,
                   fws.operational_status, fws.first_response_at_utc,
                   fws.first_responder,
                   count(foe.id) as operational_events
            from flow_request_work_states fws
            left join flow_request_operational_events foe
              on foe.routing_id = fws.routing_id
            where fws.request_id = %(request_id)s
              and (%(routing_id)s::uuid is null
                   or fws.routing_id = %(routing_id)s::uuid)
            group by fws.request_id, fws.routing_id, fws.operational_status,
                     fws.first_response_at_utc, fws.first_responder
            """,
            {"request_id": request_id, "routing_id": routing_id},
        )

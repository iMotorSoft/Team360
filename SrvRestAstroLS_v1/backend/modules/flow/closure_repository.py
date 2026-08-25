"""PostgreSQL persistence for supervisor closure approvals and resolutions."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from modules.db.transaction import execute, fetch_all, fetch_one
from modules.messaging.domain import InboundMessage

from .domain import (
    ClosureApproval,
    ClosureApprovalStatus,
    ResolutionProposal,
    ResolutionStatus,
)


def _resolution(row: dict | None) -> ResolutionProposal | None:
    if row is None:
        return None
    return ResolutionProposal(
        id=row["id"],
        request_id=row["request_id"],
        routing_id=row["routing_id"],
        status=ResolutionStatus(row["status"]),
        proposed_by=row["proposed_by"],
        proposed_at=row["proposed_at_utc"],
        source_provider=row["source_provider"],
        source_external_message_id=row["source_external_message_id"],
        resolution_text=row["resolution_text"],
    )


def _approval(row: dict | None) -> ClosureApproval | None:
    if row is None:
        return None
    return ClosureApproval(
        id=row["id"],
        request_id=row["request_id"],
        resolution_id=row["resolution_id"],
        approver_level=int(row["approver_level"]),
        approver_destination=row["approver_destination"],
        approval_token=row["approval_token"],
        status=ClosureApprovalStatus(row["status"]),
        outbound_rfc_message_id=row["outbound_rfc_message_id"],
        outbound_external_message_id=row["outbound_external_message_id"],
        outbound_observed_rfc_message_id=row["outbound_observed_rfc_message_id"],
        decision_source_external_message_id=row["decision_source_external_message_id"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at_utc"],
        decision_reason=row["decision_reason"],
        created_at=row["created_at_utc"],
    )


_RESOLUTION_COLUMNS = """
    id::text, request_id::text, routing_id::text, status, proposed_by,
    proposed_at_utc, source_provider, source_external_message_id, resolution_text
"""

_APPROVAL_COLUMNS = """
    id::text, request_id::text, resolution_id::text, approver_level,
    approver_destination, approval_token, status, outbound_rfc_message_id,
    outbound_external_message_id, outbound_observed_rfc_message_id,
    decision_source_external_message_id, decided_by, decided_at_utc,
    decision_reason, created_at_utc
"""


class FlowClosurePostgresRepository:
    async def get_request_lifecycle_for_update(
        self, conn: AsyncConnection, request_id: str
    ) -> dict[str, Any] | None:
        return await fetch_one(
            conn,
            """
            select status
            from flow_requests
            where id = %(request_id)s
            for update
            """,
            {"request_id": request_id},
        )

    async def get_closure_policy(
        self, conn: AsyncConnection, routing_id: str
    ) -> dict[str, Any] | None:
        return await fetch_one(
            conn,
            """
            select fsl.level::int as approver_level,
                   fsl.destination as approver_destination
            from flow_request_routings frr
            join flow_sectors fs on fs.sector_id = frr.sector_id
            join flow_sector_levels fsl
              on fsl.sector_id = fs.sector_id
             and fsl.level = fs.closure_approval_level
             and fsl.active = true
            where frr.id = %(routing_id)s
            """,
            {"routing_id": routing_id},
        )

    async def upsert_resolution(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        routing_id: str,
        proposed_by: str,
        proposed_at,
        source_provider: str,
        source_external_message_id: str,
        resolution_text: str,
    ) -> ResolutionProposal:
        row = await fetch_one(
            conn,
            f"""
            insert into flow_request_resolutions (
                request_id, routing_id, status, proposed_by, proposed_at_utc,
                source_provider, source_external_message_id, resolution_text
            ) values (
                %(request_id)s, %(routing_id)s, 'PROPOSED', %(proposed_by)s,
                %(proposed_at)s, %(source_provider)s, %(source_external_message_id)s,
                %(resolution_text)s
            )
            on conflict (source_provider, source_external_message_id) do nothing
            returning {_RESOLUTION_COLUMNS}
            """,
            {
                "request_id": request_id,
                "routing_id": routing_id,
                "proposed_by": proposed_by,
                "proposed_at": proposed_at,
                "source_provider": source_provider,
                "source_external_message_id": source_external_message_id,
                "resolution_text": resolution_text,
            },
        )
        created = _resolution(row)
        if created is not None:
            return created
        existing = await self.find_resolution_by_source(
            conn, source_provider, source_external_message_id
        )
        if existing is None:
            raise RuntimeError("Flow resolution conflict returned no row.")
        return existing

    async def find_resolution_by_source(
        self,
        conn: AsyncConnection,
        provider: str,
        external_message_id: str,
    ) -> ResolutionProposal | None:
        return _resolution(
            await fetch_one(
                conn,
                f"""
                select {_RESOLUTION_COLUMNS}
                from flow_request_resolutions
                where source_provider = %(provider)s
                  and source_external_message_id = %(external_message_id)s
                """,
                {"provider": provider, "external_message_id": external_message_id},
            )
        )

    async def upsert_approval(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        resolution_id: str,
        approver_level: int,
        approver_destination: str,
        approval_token: str,
    ) -> ClosureApproval:
        row = await fetch_one(
            conn,
            f"""
            insert into flow_closure_approvals (
                request_id, resolution_id, approver_level, approver_destination,
                approval_token, status
            ) values (
                %(request_id)s, %(resolution_id)s, %(approver_level)s,
                %(approver_destination)s, %(approval_token)s, 'PENDING'
            )
            on conflict (resolution_id) do nothing
            returning {_APPROVAL_COLUMNS}
            """,
            {
                "request_id": request_id,
                "resolution_id": resolution_id,
                "approver_level": approver_level,
                "approver_destination": approver_destination,
                "approval_token": approval_token,
            },
        )
        created = _approval(row)
        if created is not None:
            return created
        existing = await self.find_approval_by_resolution(conn, resolution_id)
        if existing is None:
            raise RuntimeError("Flow approval conflict returned no row.")
        return existing

    async def find_approval_by_resolution(
        self, conn: AsyncConnection, resolution_id: str
    ) -> ClosureApproval | None:
        return _approval(
            await fetch_one(
                conn,
                f"""
                select {_APPROVAL_COLUMNS}
                from flow_closure_approvals
                where resolution_id = %(resolution_id)s
                """,
                {"resolution_id": resolution_id},
            )
        )

    async def get_approval_by_request_for_update(
        self, conn: AsyncConnection, request_id: str
    ) -> ClosureApproval | None:
        return _approval(
            await fetch_one(
                conn,
                f"""
                select {_APPROVAL_COLUMNS}
                from flow_closure_approvals
                where request_id = %(request_id)s
                order by created_at_utc desc
                limit 1
                for update
                """,
                {"request_id": request_id},
            )
        )

    async def get_resolution(
        self, conn: AsyncConnection, resolution_id: str
    ) -> ResolutionProposal | None:
        return _resolution(
            await fetch_one(
                conn,
                f"""
                select {_RESOLUTION_COLUMNS}
                from flow_request_resolutions
                where id = %(resolution_id)s
                """,
                {"resolution_id": resolution_id},
            )
        )

    async def find_approval_by_token(
        self, conn: AsyncConnection, token: str
    ) -> ClosureApproval | None:
        return _approval(
            await fetch_one(
                conn,
                f"""
                select {_APPROVAL_COLUMNS}
                from flow_closure_approvals
                where approval_token = %(token)s
                """,
                {"token": token},
            )
        )

    async def find_approval_by_rfc_reference(
        self, conn: AsyncConnection, references: tuple[str, ...]
    ) -> ClosureApproval | None:
        if not references:
            return None
        return _approval(
            await fetch_one(
                conn,
                f"""
                select {_APPROVAL_COLUMNS}
                from flow_closure_approvals
                where outbound_observed_rfc_message_id = any(%(references)s)
                   or outbound_rfc_message_id = any(%(references)s)
                order by (
                    outbound_observed_rfc_message_id = any(%(references)s)
                ) desc
                limit 1
                """,
                {"references": list(references)},
            )
        )

    async def get_approval_for_decision(
        self, conn: AsyncConnection, approval_id: str
    ) -> ClosureApproval | None:
        return _approval(
            await fetch_one(
                conn,
                f"""
                select {_APPROVAL_COLUMNS}
                from flow_closure_approvals
                where id = %(approval_id)s
                for update
                """,
                {"approval_id": approval_id},
            )
        )

    async def mark_approval_sent(
        self,
        conn: AsyncConnection,
        approval_id: str,
        external_message_id: str,
        observed_rfc: str | None,
        outbound_rfc_message_id: str | None = None,
    ) -> ClosureApproval:
        row = await fetch_one(
            conn,
            f"""
            update flow_closure_approvals
            set outbound_rfc_message_id = coalesce(
                    %(outbound_rfc_message_id)s, outbound_rfc_message_id
                ),
                outbound_external_message_id = %(external_message_id)s,
                outbound_observed_rfc_message_id = coalesce(
                    %(observed_rfc)s, outbound_observed_rfc_message_id
                ),
                status = case
                    when status = 'DELIVERY_UNCERTAIN' then 'PENDING'
                    else status
                end,
                updated_at_utc = now()
            where id = %(approval_id)s
            returning {_APPROVAL_COLUMNS}
            """,
            {
                "approval_id": approval_id,
                "external_message_id": external_message_id,
                "observed_rfc": observed_rfc,
                "outbound_rfc_message_id": outbound_rfc_message_id,
            },
        )
        result = _approval(row)
        if result is None:
            raise RuntimeError("Flow approval send update returned no row.")
        return result

    async def record_approval_resend(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        conversation_id: str,
        approval_id: str,
        approver_level: int,
        recipient: str,
        external_message_id: str,
        subject: str,
        body: str,
        sender_address: str,
    ) -> None:
        await execute(
            conn,
            """
            insert into flow_messages (
                conversation_id, provider, external_message_id, direction,
                sender_address, recipients_jsonb, subject, text_body,
                occurred_at_utc, metadata_jsonb, processed_at_utc
            ) values (
                %(conversation_id)s, 'gmail', %(external_message_id)s,
                'outbound', %(sender_address)s, %(recipients)s, %(subject)s,
                %(body)s, now(), %(metadata)s, now()
            )
            on conflict (provider, external_message_id) do nothing
            """,
            {
                "conversation_id": conversation_id,
                "external_message_id": external_message_id,
                "sender_address": sender_address,
                "recipients": Jsonb([recipient]),
                "subject": subject,
                "body": body,
                "metadata": Jsonb(
                    {
                        "flow_event": "APPROVAL_NOTIFICATION_RESENT",
                        "request_id": request_id,
                        "approval_id": approval_id,
                        "approver_level": approver_level,
                        "recipient": recipient,
                    }
                ),
            },
        )

    async def mark_approval_delivery_uncertain(
        self, conn: AsyncConnection, approval_id: str
    ) -> ClosureApproval:
        row = await fetch_one(
            conn,
            f"""
            update flow_closure_approvals
            set status = 'DELIVERY_UNCERTAIN', updated_at_utc = now()
            where id = %(approval_id)s
            returning {_APPROVAL_COLUMNS}
            """,
            {"approval_id": approval_id},
        )
        result = _approval(row)
        if result is None:
            raise RuntimeError("Flow approval delivery update returned no row.")
        return result

    async def mark_request_resolution_pending(
        self, conn: AsyncConnection, request_id: str
    ) -> None:
        await execute(
            conn,
            """
            update flow_requests
            set status = 'RESOLUTION_PENDING_APPROVAL'
            where id = %(request_id)s
              and status in ('CONFIRMED', 'ACTIVE')
            """,
            {"request_id": request_id},
        )

    async def mark_request_active(
        self, conn: AsyncConnection, request_id: str
    ) -> None:
        await execute(
            conn,
            """
            update flow_requests
            set status = 'ACTIVE'
            where id = %(request_id)s
              and status = 'RESOLUTION_PENDING_APPROVAL'
            """,
            {"request_id": request_id},
        )

    async def get_request_context(
        self, conn: AsyncConnection, request_id: str
    ) -> dict[str, Any] | None:
        return await fetch_one(
            conn,
            """
            select fr.id::text as request_id, fr.conversation_id::text,
                   fr.status, fr.description, fr.location_text,
                   fr.tentative_category, fc.citizen_address
            from flow_requests fr
            join flow_conversations fc on fc.id = fr.conversation_id
            where fr.id = %(request_id)s
            """,
            {"request_id": request_id},
        )

    async def claim_approval_reply(
        self,
        conn: AsyncConnection,
        conversation_id: str,
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
                "conversation_id": conversation_id,
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

    async def apply_approve(
        self,
        conn: AsyncConnection,
        approval: ClosureApproval,
        *,
        decision_source_external_message_id: str,
        decided_by: str,
        decided_at,
        reason: str,
    ) -> None:
        await execute(
            conn,
            """
            update flow_closure_approvals
            set status = 'APPROVED',
                decision_source_external_message_id = %(source_message_id)s,
                decided_by = %(decided_by)s,
                decided_at_utc = %(decided_at)s,
                decision_reason = %(reason)s,
                updated_at_utc = now()
            where id = %(approval_id)s
            """,
            {
                "approval_id": approval.id,
                "source_message_id": decision_source_external_message_id,
                "decided_by": decided_by,
                "decided_at": decided_at,
                "reason": reason,
            },
        )
        await execute(
            conn,
            """
            update flow_request_resolutions
            set status = 'APPROVED', updated_at_utc = now()
            where id = %(resolution_id)s
            """,
            {"resolution_id": approval.resolution_id},
        )
        await execute(
            conn,
            """
            update flow_requests
            set status = 'RESOLVED',
                resolved_at_utc = %(decided_at)s,
                authorized_by = %(decided_by)s,
                authorized_approval_id = %(approval_id)s
            where id = %(request_id)s
            """,
            {
                "request_id": approval.request_id,
                "decided_at": decided_at,
                "decided_by": decided_by,
                "approval_id": approval.id,
            },
        )

    async def apply_reject(
        self,
        conn: AsyncConnection,
        approval: ClosureApproval,
        *,
        decision_source_external_message_id: str,
        decided_by: str,
        decided_at,
        reason: str,
    ) -> None:
        await execute(
            conn,
            """
            update flow_closure_approvals
            set status = 'REJECTED',
                decision_source_external_message_id = %(source_message_id)s,
                decided_by = %(decided_by)s,
                decided_at_utc = %(decided_at)s,
                decision_reason = %(reason)s,
                updated_at_utc = now()
            where id = %(approval_id)s
            """,
            {
                "approval_id": approval.id,
                "source_message_id": decision_source_external_message_id,
                "decided_by": decided_by,
                "decided_at": decided_at,
                "reason": reason,
            },
        )
        await execute(
            conn,
            """
            update flow_request_resolutions
            set status = 'REJECTED', updated_at_utc = now()
            where id = %(resolution_id)s
            """,
            {"resolution_id": approval.resolution_id},
        )
        await self.mark_request_active(conn, approval.request_id)

    async def get_case_brief(
        self, conn: AsyncConnection, request_id: str
    ) -> dict[str, Any]:
        request = await fetch_one(
            conn,
            """
            select fr.description, fr.location_text, fsec.display_name as sector_name
            from flow_requests fr
            join flow_request_routings frr on frr.request_id = fr.id
            join flow_sectors fsec on fsec.sector_id = frr.sector_id
            where fr.id = %(request_id)s
            order by frr.level
            limit 1
            """,
            {"request_id": request_id},
        )
        chain = await fetch_all(
            conn,
            """
            select frr.level::int, frr.destination,
                   frr.assigned_at_utc, fws.operational_status as work_status
            from flow_request_routings frr
            left join flow_request_work_states fws on fws.routing_id = frr.id
            where frr.request_id = %(request_id)s
              and frr.status = 'ASSIGNED'
            order by frr.level, frr.assigned_at_utc
            """,
            {"request_id": request_id},
        )
        slas = await fetch_all(
            conn,
            """
            select frr.level::int, fs.status as sla_status
            from flow_request_slas fs
            join flow_request_routings frr on frr.id = fs.routing_id
            where fs.request_id = %(request_id)s
            order by frr.level
            """,
            {"request_id": request_id},
        )
        return {
            "description": request["description"] if request else "",
            "location_text": request["location_text"] if request else None,
            "sector_name": request["sector_name"] if request else "",
            "chain": list(chain),
            "slas": list(slas),
        }

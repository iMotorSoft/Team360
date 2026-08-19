"""PostgreSQL persistence for the traceable citizen communication policy."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from modules.db.transaction import execute, fetch_all, fetch_one

from .domain import CitizenNotificationType


_TRACE_COLUMNS = """
    id::text, request_id::text, notification_type, channel, recipient,
    public_reference, subject, body, dedupe_key, status,
    provider_message_id, provider_thread_id, outbound_rfc_message_id,
    outbound_observed_rfc_message_id, attempt_count, last_error_code,
    last_error_detail, sent_at_utc, created_at_utc, updated_at_utc
"""


class CitizenNotificationPostgresRepository:
    """All citizen-notification SQL lives here; connections are caller-owned."""

    async def find(
        self,
        conn: AsyncConnection,
        request_id: str,
        notification_type: CitizenNotificationType,
    ) -> dict[str, Any] | None:
        return await fetch_one(
            conn,
            f"""
            select {_TRACE_COLUMNS}
            from flow_citizen_notifications
            where request_id = %(request_id)s
              and notification_type = %(notification_type)s
            """,
            {
                "request_id": request_id,
                "notification_type": notification_type.value,
            },
        )

    async def get_request_projection(
        self, conn: AsyncConnection, request_id: str
    ) -> dict[str, Any] | None:
        """Allow-listed public fields only; internal routing/SLA/approval data
        is never selected here and cannot leak into citizen messages."""
        return await fetch_one(
            conn,
            """
            select fr.id::text as public_reference,
                   fr.status as request_status,
                   fr.description as public_description,
                   fr.location_text as public_location,
                   fr.resolved_at_utc,
                   fc.citizen_address,
                   fc.subject
            from flow_requests fr
            join flow_conversations fc on fc.id = fr.conversation_id
            where fr.id = %(request_id)s
            """,
            {"request_id": request_id},
        )

    async def find_confirmed_request_ids(
        self, conn: AsyncConnection, conversation_id: str
    ) -> list[str]:
        rows = await fetch_all(
            conn,
            """
            select id::text as request_id
            from flow_requests
            where conversation_id = %(conversation_id)s
              and status = 'CONFIRMED'
            order by confirmed_at_utc
            """,
            {"conversation_id": conversation_id},
        )
        return [row["request_id"] for row in rows]

    async def insert_or_claim(
        self,
        conn: AsyncConnection,
        *,
        request_id: str,
        notification_type: CitizenNotificationType,
        channel: str,
        recipient: str,
        public_reference: str,
        subject: str,
        body: str,
        dedupe_key: str,
        outbound_rfc_message_id: str,
    ) -> str | None:
        """Insert the notification intent with an atomic request+type claim.

        A concurrent caller loses the race and gets ``None``: the unique
        request/type constraint guarantees exactly one trace and one eventual
        public send regardless of retries.
        """
        row = await fetch_one(
            conn,
            f"""
            insert into flow_citizen_notifications (
                request_id, notification_type, channel, recipient,
                public_reference, subject, body, dedupe_key, status,
                outbound_rfc_message_id
            ) values (
                %(request_id)s, %(notification_type)s, %(channel)s,
                %(recipient)s, %(public_reference)s, %(subject)s, %(body)s,
                %(dedupe_key)s, 'PENDING', %(outbound_rfc_message_id)s
            )
            on conflict (request_id, notification_type) do nothing
            returning id::text
            """,
            {
                "request_id": request_id,
                "notification_type": notification_type.value,
                "channel": channel,
                "recipient": recipient,
                "public_reference": public_reference,
                "subject": subject,
                "body": body,
                "dedupe_key": dedupe_key,
                "outbound_rfc_message_id": outbound_rfc_message_id,
            },
        )
        return row["id"] if row else None

    async def mark_sent(
        self,
        conn: AsyncConnection,
        trace_id: str,
        *,
        provider_message_id: str,
        provider_thread_id: str | None,
        observed_rfc_message_id: str | None,
    ) -> None:
        await execute(
            conn,
            """
            update flow_citizen_notifications
            set status = 'SENT',
                provider_message_id = %(provider_message_id)s,
                provider_thread_id = coalesce(
                    %(provider_thread_id)s, provider_thread_id
                ),
                outbound_observed_rfc_message_id = coalesce(
                    %(observed_rfc_message_id)s,
                    outbound_observed_rfc_message_id
                ),
                attempt_count = attempt_count + 1,
                last_error_code = null,
                last_error_detail = null,
                sent_at_utc = coalesce(sent_at_utc, now()),
                updated_at_utc = now()
            where id = %(trace_id)s
            """,
            {
                "trace_id": trace_id,
                "provider_message_id": provider_message_id,
                "provider_thread_id": provider_thread_id,
                "observed_rfc_message_id": observed_rfc_message_id,
            },
        )

    async def mark_failed(
        self,
        conn: AsyncConnection,
        trace_id: str,
        *,
        error_code: str,
        error_detail: str | None,
        uncertain: bool,
    ) -> None:
        await execute(
            conn,
            """
            update flow_citizen_notifications
            set status = %(status)s,
                attempt_count = attempt_count + 1,
                last_error_code = %(error_code)s,
                last_error_detail = %(error_detail)s,
                updated_at_utc = now()
            where id = %(trace_id)s
            """,
            {
                "trace_id": trace_id,
                "status": (
                    "DELIVERY_UNCERTAIN" if uncertain else "DELIVERY_FAILED"
                ),
                "error_code": error_code,
                "error_detail": (error_detail or "")[:500],
            },
        )

    async def list_traces(
        self, conn: AsyncConnection, request_id: str
    ) -> list[dict[str, Any]]:
        return await fetch_all(
            conn,
            f"""
            select {_TRACE_COLUMNS}
            from flow_citizen_notifications
            where request_id = %(request_id)s
            order by created_at_utc
            """,
            {"request_id": request_id},
        )

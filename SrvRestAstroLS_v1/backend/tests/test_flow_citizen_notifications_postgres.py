"""Real-PostgreSQL integration coverage for citizen notifications.

Exercises the notification trace, request+type dedupe, delivery failure and
idempotent reconciliation, the RESOLVED closure guard and the separation
between the citizen recipient and the operational destinations. Gated behind
``TEAM360_FLOW_CITIZEN_NOTIFICATIONS_POSTGRES_TEST=1`` (migration 022 applied).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.citizen_notifications import (
    CitizenNotificationPostgresRepository,
    FlowCitizenNotificationService,
)
from modules.flow.closure_repository import FlowClosurePostgresRepository
from modules.flow.domain import approval_token_for


CITIZEN = "citizen@example.com"
N1_DESTINATION = "alumbrado.n1@alquimiablue.com"


class _Sender:
    def __init__(self):
        self.prefix = uuid4().hex[:8]
        self.sent: list[dict] = []
        self.recovered: str | None = None
        self.fail_with: Exception | None = None

    @property
    def sender_address(self):
        return "mesaentrada@alquimiablue.com"

    def find_sent_message_by_rfc_message_id(self, rfc_message_id):
        return self.recovered

    def find_sent_message_by_reference(self, reference, *, to=None):
        return None

    def get_message_rfc_id(self, message_id):
        return f"<observed-{message_id}@mail.gmail.com>"

    def send_message(self, *, to, subject, body, rfc_message_id):
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append({"to": to, "subject": subject, "body": body})
        return f"{self.prefix}-gmail-{len(self.sent)}"


async def _seed_request(conn, suffix):
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into flow_conversations (
                provider, channel, external_thread_id, citizen_address, subject, state
            ) values ('gmail', 'email', %(thread)s, %(citizen)s,
                      'Solicitud de alumbrado publico', 'CONFIRMED') returning id
            """,
            {"thread": f"citizen-{suffix}", "citizen": CITIZEN},
        )
        conversation_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_request_candidates (
                conversation_id, revision, ordinal, description,
                tentative_category, status
            ) values (%(conversation)s, 1, 1, 'Luminaria apagada', 'alumbrado',
                      'CONFIRMED') returning id
            """,
            {"conversation": conversation_id},
        )
        candidate_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_requests (
                conversation_id, source_candidate_id, description,
                tentative_category, location_text, confirmed_at_utc
            ) values (%(conversation)s, %(candidate)s, 'Luminaria apagada',
                      'alumbrado', 'Av. Eucaliptos 980', now()) returning id
            """,
            {"conversation": conversation_id, "candidate": candidate_id},
        )
        request_id = str((await cur.fetchone())["id"])
        await cur.execute(
            """
            select id from flow_sector_levels
            where sector_id = 'alumbrado' and level = 1
            """
        )
        level_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_request_routings (
                request_id, sector_id, sector_level_id, level, channel,
                destination, status, outbound_rfc_message_id,
                outbound_observed_rfc_message_id, outbound_external_message_id,
                assigned_at_utc
            ) values (%(request)s, 'alumbrado', %(level_id)s, 1, 'email',
                      %(destination)s, 'ASSIGNED',
                      %(intended)s, %(observed)s, %(external)s, now())
            returning id
            """,
            {
                "request": request_id,
                "level_id": level_id,
                "destination": N1_DESTINATION,
                "intended": f"<intended-{suffix}@example.com>",
                "observed": f"<observed-{suffix}@mail.gmail.com>",
                "external": f"gmail-out-{suffix}",
            },
        )
        routing_id = str((await cur.fetchone())["id"])
    return request_id, routing_id, conversation_id


def _now():
    return datetime.now(timezone.utc)


async def _cleanup(settings, request_id: str):
    """Remove only the seeded citizen test case in dependency order."""
    async with await psycopg.AsyncConnection.connect(
        settings.dsn, row_factory=dict_row
    ) as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "alter table flow_requests "
                    "disable trigger trg_flow_request_resolution_guard"
                )
                await cur.execute(
                    "update flow_requests set status = 'CONFIRMED', "
                    "authorized_approval_id = null where id = %s::uuid",
                    (request_id,),
                )
                await cur.execute(
                    "select conversation_id from flow_requests where id = %s::uuid",
                    (request_id,),
                )
                row = await cur.fetchone()
                conversation_id = row["conversation_id"] if row else None
                for table in (
                    "flow_citizen_notifications",
                    "flow_case_audit_records",
                    "flow_closure_approvals",
                    "flow_request_resolutions",
                    "flow_request_routings",
                    "flow_request_work_states",
                    "flow_request_escalations",
                    "flow_request_operational_events",
                    "flow_request_slas",
                ):
                    await cur.execute(
                        f"delete from {table} where request_id = %s::uuid",
                        (request_id,),
                    )
                await cur.execute(
                    "delete from flow_request_sla_events where sla_id in ("
                    "select id from flow_request_slas where request_id = %s::uuid"
                    ")",
                    (request_id,),
                )
                await cur.execute(
                    "delete from flow_requests where id = %s::uuid",
                    (request_id,),
                )
                if conversation_id is not None:
                    for table in (
                        "flow_request_candidates",
                        "flow_interpretations",
                        "flow_messages",
                    ):
                        await cur.execute(
                            f"delete from {table} where conversation_id = %s::uuid",
                            (conversation_id,),
                        )
                    await cur.execute(
                        "delete from flow_conversations where id = %s::uuid",
                        (conversation_id,),
                    )
                await cur.execute(
                    "alter table flow_requests "
                    "enable trigger trg_flow_request_resolution_guard"
                )


def _service(pool, sender):
    return FlowCitizenNotificationService(
        pool=pool,
        repository=CitizenNotificationPostgresRepository(),
        sender=sender,
    )


def _setup_pool(settings):
    pool = create_pool(settings)
    return pool


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CITIZEN_NOTIFICATIONS_POSTGRES_TEST") != "1",
    reason="requires migration 022 on the configured Team360 PostgreSQL",
)
def test_real_postgres_received_dedupe_and_trace_persisted():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=2)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, _routing_id, _conversation_id = await _seed_request(
                conn, suffix
            )
            await conn.commit()

        pool = _setup_pool(settings)
        await open_pool(pool)
        try:
            sender = _Sender()
            service = _service(pool, sender)

            first = await service.notify_received(request_id)
            assert first.outcome == "SENT"
            assert first.provider_message_id

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select notification_type, status, recipient,
                               public_reference, dedupe_key, provider_message_id
                        from flow_citizen_notifications
                        where request_id = %(request_id)s
                        """,
                        {"request_id": request_id},
                    )
                    rows = await cur.fetchall()
            assert len(rows) == 1
            row = rows[0]
            assert row["notification_type"] == "CITIZEN_RECEIVED"
            assert row["status"] == "SENT"
            assert row["recipient"] == CITIZEN
            assert row["public_reference"] == request_id
            assert row["dedupe_key"] == f"{request_id}:CITIZEN_RECEIVED"
            assert row["provider_message_id"] == first.provider_message_id

            second = await service.notify_received(request_id)
            assert second.outcome == "ALREADY_SENT"
            assert len(sender.sent) == 1
            await service.notify_received(request_id)
            assert len(sender.sent) == 1  # repeated processing, one email
        finally:
            await _cleanup(settings, request_id)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CITIZEN_NOTIFICATIONS_POSTGRES_TEST") != "1",
    reason="requires migration 022 on the configured Team360 PostgreSQL",
)
def test_real_postgres_delivery_failure_preserves_case_and_retry_is_idempotent():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=2)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, _routing_id, _conversation_id = await _seed_request(
                conn, suffix
            )
            await conn.commit()

        pool = _setup_pool(settings)
        await open_pool(pool)
        try:
            sender = _Sender()
            sender.fail_with = RuntimeError("provider down")
            service = _service(pool, sender)

            failed = await service.notify_received(request_id)
            assert failed.outcome == "DELIVERY_FAILED"

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select status, last_error_code, attempt_count,
                               provider_message_id
                        from flow_citizen_notifications
                        where request_id = %(request_id)s
                        """,
                        {"request_id": request_id},
                    )
                    trace = await cur.fetchone()
                    await cur.execute(
                        "select status from flow_requests where id = %(request_id)s",
                        {"request_id": request_id},
                    )
                    case_status = (await cur.fetchone())["status"]
            assert trace["status"] == "DELIVERY_FAILED"
            assert trace["last_error_code"] == "RuntimeError"
            assert trace["attempt_count"] == 1
            assert trace["provider_message_id"] is None
            assert case_status == "CONFIRMED"  # business state unaffected

            # Retry reconciles against the provider: no duplicate email.
            sender.fail_with = None
            sender.recovered = "gmail-recovered-1"
            retried = await service.notify_received(request_id)
            assert retried.outcome == "SENT_RECONCILED"
            assert retried.provider_message_id == "gmail-recovered-1"
            assert sender.sent == []  # reconciled, never re-sent

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select status, provider_message_id
                        from flow_citizen_notifications
                        where request_id = %(request_id)s
                        """,
                        {"request_id": request_id},
                    )
                    trace = await cur.fetchone()
            assert trace["status"] == "SENT"
            assert trace["provider_message_id"] == "gmail-recovered-1"
        finally:
            await _cleanup(settings, request_id)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CITIZEN_NOTIFICATIONS_POSTGRES_TEST") != "1",
    reason="requires migration 022 on the configured Team360 PostgreSQL",
)
def test_real_postgres_resolved_only_after_real_closure():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=2)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, routing_id, _conversation_id = await _seed_request(
                conn, suffix
            )
            await conn.commit()

        pool = _setup_pool(settings)
        await open_pool(pool)
        try:
            sender = _Sender()
            service = _service(pool, sender)
            closure_repo = FlowClosurePostgresRepository()

            # Before closure: RESOLVED is never emitted.
            early = await service.notify_resolved(request_id)
            assert early.outcome == "STATUS_MISMATCH"
            assert sender.sent == []

            # Drive a real approved closure through the real repositories.
            async with pool.connection() as conn:
                async with conn.transaction():
                    resolution = await closure_repo.upsert_resolution(
                        conn,
                        request_id=request_id,
                        routing_id=routing_id,
                        proposed_by="tech@alquimiablue.com",
                        proposed_at=_now(),
                        source_provider="gmail",
                        source_external_message_id=f"proposal-{suffix}",
                        resolution_text="Luminaria reparada.",
                    )
                    approval = await closure_repo.upsert_approval(
                        conn,
                        request_id=request_id,
                        resolution_id=resolution.id,
                        approver_level=2,
                        approver_destination="alumbrado.n2@alquimiablue.com",
                        approval_token=approval_token_for("gmail", f"proposal-{suffix}"),
                    )
                    await closure_repo.apply_approve(
                        conn,
                        approval,
                        decision_source_external_message_id=f"decision-{suffix}",
                        decided_by="alumbrado.n2@alquimiablue.com",
                        decided_at=_now(),
                        reason="ok",
                    )
            # RESOLVED is terminal (DB trigger) and the citizen is notified.
            resolved = await service.notify_resolved(request_id)
            assert resolved.outcome == "SENT"
            assert sender.sent and "fue atendida" in sender.sent[0]["body"]

            again = await service.notify_resolved(request_id)
            assert again.outcome == "ALREADY_SENT"
            assert len(sender.sent) == 1
        finally:
            await _cleanup(settings, request_id)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CITIZEN_NOTIFICATIONS_POSTGRES_TEST") != "1",
    reason="requires migration 022 on the configured Team360 PostgreSQL",
)
def test_real_postgres_citizen_recipient_differs_from_operational_destinations():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=2)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, routing_id, _conversation_id = await _seed_request(
                conn, suffix
            )
            await conn.commit()

        pool = _setup_pool(settings)
        await open_pool(pool)
        try:
            sender = _Sender()
            service = _service(pool, sender)
            result = await service.notify_received(request_id)
            assert result.outcome == "SENT"
            assert sender.sent[0]["to"] == CITIZEN
            # Strong separation: the citizen recipient is never an operational
            # destination and no operational destination is ever used as the
            # citizen recipient.
            assert CITIZEN != N1_DESTINATION
            assert sender.sent[0]["to"] != N1_DESTINATION
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select destination from flow_request_routings
                        where id = %(routing_id)s
                        """,
                        {"routing_id": routing_id},
                    )
                    destination = (await cur.fetchone())["destination"]
            assert sender.sent[0]["to"] != destination
        finally:
            await _cleanup(settings, request_id)
            await close_pool(pool)

    asyncio.run(exercise())

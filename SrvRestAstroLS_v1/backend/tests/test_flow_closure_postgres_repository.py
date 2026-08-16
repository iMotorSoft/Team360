import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.audit_repository import FlowAuditRepository
from modules.flow.closure_repository import FlowClosurePostgresRepository
from modules.flow.closure_service import FlowClosureService
from modules.flow.domain import (
    ApprovalDecision,
    ApprovalDecisionResult,
    OperationalAction,
    OperationalInterpretation,
    OperationalRoutingContext,
)
from modules.messaging.domain import InboundMessage


APPROVER = "alumbrado.n2@alquimiablue.com"


class _Sender:
    def __init__(self):
        self.prefix = uuid4().hex[:8]
        self.sent = []

    def find_sent_message_by_rfc_message_id(self, rfc_message_id):
        return None

    def find_sent_message_by_reference(self, reference, *, to=None):
        return None

    def get_message_rfc_id(self, message_id):
        return f"<observed-{message_id}@mail.gmail.com>"

    def send_message(self, *, to, subject, body, rfc_message_id):
        self.sent.append({"to": to, "subject": subject, "rfc": rfc_message_id})
        return f"{self.prefix}-gmail-sent-{len(self.sent)}"


class _ApproveInterpreter:
    def interpret(self, text, *, correlation_id=None):
        return ApprovalDecisionResult(ApprovalDecision.APPROVE, "")


def _interpretation():
    return OperationalInterpretation(
        OperationalAction.RESOLUTION_PROPOSED, "resuelto", "mock", "mock", {}, 1
    )


def _dt(seconds=0):
    return datetime(2026, 8, 13, 12, 0, seconds, tzinfo=timezone.utc)


async def _seed_request(conn, suffix):
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into flow_conversations (
                provider, channel, external_thread_id, citizen_address, subject, state
            ) values ('gmail', 'email', %(thread)s, 'citizen@example.com',
                      'Closure test', 'CONFIRMED') returning id
            """,
            {"thread": f"closure-{suffix}"},
        )
        conversation_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_request_candidates (
                conversation_id, revision, ordinal, description,
                tentative_category, status
            ) values (%(conversation)s, 1, 1, 'Reparar poste', 'alumbrado',
                      'CONFIRMED') returning id
            """,
            {"conversation": conversation_id},
        )
        candidate_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_requests (
                conversation_id, source_candidate_id, description,
                tentative_category, confirmed_at_utc
            ) values (%(conversation)s, %(candidate)s, 'Reparar poste',
                      'alumbrado', now()) returning id
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
        observed_rfc = f"<{suffix}@mail.gmail.com>"
        await cur.execute(
            """
            insert into flow_request_routings (
                request_id, sector_id, sector_level_id, level, channel,
                destination, status, outbound_rfc_message_id,
                outbound_observed_rfc_message_id, outbound_external_message_id,
                assigned_at_utc
            ) values (%(request)s, 'alumbrado', %(level_id)s, 1, 'email',
                      'alumbrado.n1@alquimiablue.com', 'ASSIGNED',
                      %(intended)s, %(observed)s, %(external)s, now())
            returning id
            """,
            {
                "request": request_id,
                "level_id": level_id,
                "intended": f"<intended-{suffix}@example.com>",
                "observed": observed_rfc,
                "external": f"gmail-out-{suffix}",
            },
        )
        routing_id = str((await cur.fetchone())["id"])
    return request_id, routing_id, conversation_id, observed_rfc


def _context(request_id, routing_id, conversation_id, *, request_status="CONFIRMED"):
    return OperationalRoutingContext(
        routing_id=routing_id,
        request_id=request_id,
        conversation_id=conversation_id,
        routing_key="initial_n1",
        level=1,
        routing_status="ASSIGNED",
        destination="alumbrado.n1@alquimiablue.com",
        outbound_external_message_id="gmail-out-1",
        outbound_rfc_message_id="<intended@example.com>",
        outbound_observed_rfc_message_id=None,
        request_status=request_status,
    )


def _proposal_message(suffix, in_reply_to):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=f"proposal-{suffix}",
        external_thread_id="other-thread",
        sender="tech@alquimiablue.com",
        recipients=("mesa@alquimiablue.com",),
        subject=f"Re: request {suffix}",
        text_body="La luminaria quedó reparada.",
        received_at=_dt(),
        metadata={"in_reply_to": in_reply_to, "references": ""},
    )


def _approval_reply_message(suffix, token, observed_rfc):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=f"decision-{suffix}",
        external_thread_id="supervisor-thread",
        sender=APPROVER,
        recipients=("mesa@alquimiablue.com",),
        subject=f"Re: [CIERRE][R:{token}][{suffix}] Aprobación de cierre",
        text_body="APROBAR",
        received_at=_dt(5),
        metadata={"in_reply_to": observed_rfc, "references": ""},
    )


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CLOSURE_POSTGRES_TEST") != "1",
    reason="requires migration 019 on Team360 PostgreSQL",
)
def test_real_postgres_closure_approve_and_audit_are_atomic_and_idempotent():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=3)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, routing_id, conversation_id, observed_rfc = await _seed_request(
                conn, suffix
            )
            await conn.commit()

        pool = create_pool(settings)
        await open_pool(pool)
        try:
            closure_repo = FlowClosurePostgresRepository()
            audit_repo = FlowAuditRepository()
            sender = _Sender()
            service = FlowClosureService(
                pool=pool,
                repository=closure_repo,
                audit_repository=audit_repo,
                interpreter=_ApproveInterpreter(),
                sender=sender,
            )

            context = _context(request_id, routing_id, conversation_id)
            message = _proposal_message(suffix, observed_rfc)

            async with pool.connection() as conn:
                async with conn.transaction():
                    proposal = await service.propose_resolution(
                        conn,
                        context=context,
                        message=message,
                        interpretation=_interpretation(),
                    )
            assert proposal.request_status == "RESOLUTION_PENDING_APPROVAL"
            assert proposal.approval_id is not None
            assert len(sender.sent) == 1
            assert sender.sent[0]["to"] == APPROVER

            # Re-proposing the same message is a no-op (lifecycle guard).
            async with pool.connection() as conn:
                async with conn.transaction():
                    second = await service.propose_resolution(
                        conn,
                        context=context,
                        message=message,
                        interpretation=_interpretation(),
                    )
            assert second.request_status == "ALREADY_PENDING_APPROVAL"

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select approval_token, outbound_observed_rfc_message_id
                        from flow_closure_approvals where id = %(id)s
                        """,
                        {"id": proposal.approval_id},
                    )
                    row = await cur.fetchone()

            reply = _approval_reply_message(
                suffix, row["approval_token"], row["outbound_observed_rfc_message_id"]
            )
            result = await service.process_approval_reply(reply)
            assert result.decision == ApprovalDecision.APPROVE
            assert result.processed is True

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select status, resolved_at_utc, authorized_by from flow_requests where id = %(id)s",
                        {"id": request_id},
                    )
                    request_row = await cur.fetchone()
                    assert request_row["status"] == "RESOLVED"
                    assert request_row["authorized_by"] == APPROVER
                    await cur.execute(
                        "select id, snapshot_sha256, snapshot_jsonb from flow_case_audit_records where request_id = %(id)s",
                        {"id": request_id},
                    )
                    audit_rows = await cur.fetchall()
                    assert len(audit_rows) == 1
                    sha = audit_rows[0]["snapshot_sha256"]
                    assert len(sha) == 64
                    snapshot = audit_rows[0]["snapshot_jsonb"]
                    assert snapshot["result"]["request_status"] == "RESOLVED"
                    assert len(snapshot["routings"]) == 1
                    assert snapshot["approval"]["decision"] == "APPROVED"

            # Re-processing the same approval reply is idempotent.
            again = await service.process_approval_reply(reply)
            assert again.idempotent is True
            assert again.processed is False

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select count(*) from flow_case_audit_records where request_id = %(id)s",
                        {"id": request_id},
                    )
                    assert (await cur.fetchone())["count"] == 1
                    await cur.execute(
                        "select resolved_at_utc from flow_requests where id = %(id)s",
                        {"id": request_id},
                    )
                    assert (await cur.fetchone())["resolved_at_utc"] == request_row["resolved_at_utc"]
        finally:
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CLOSURE_POSTGRES_TEST") != "1",
    reason="requires migration 019 on Team360 PostgreSQL",
)
def test_real_postgres_closure_transaction_rolls_back_when_audit_fails(monkeypatch):
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=3)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, routing_id, conversation_id, observed_rfc = await _seed_request(
                conn, suffix
            )
            await conn.commit()

        pool = create_pool(settings)
        await open_pool(pool)
        try:
            closure_repo = FlowClosurePostgresRepository()
            audit_repo = FlowAuditRepository()
            sender = _Sender()
            service = FlowClosureService(
                pool=pool,
                repository=closure_repo,
                audit_repository=audit_repo,
                interpreter=_ApproveInterpreter(),
                sender=sender,
            )

            context = _context(request_id, routing_id, conversation_id)
            message = _proposal_message(suffix, observed_rfc)
            async with pool.connection() as conn:
                async with conn.transaction():
                    proposal = await service.propose_resolution(
                        conn, context=context, message=message, interpretation=_interpretation()
                    )
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select approval_token, outbound_observed_rfc_message_id from flow_closure_approvals where id = %(id)s",
                        {"id": proposal.approval_id},
                    )
                    row = await cur.fetchone()

            def _fail(*args, **kwargs):
                raise RuntimeError("forced audit failure")

            monkeypatch.setattr(FlowAuditRepository, "create_record", _fail)

            reply = _approval_reply_message(
                suffix, row["approval_token"], row["outbound_observed_rfc_message_id"]
            )
            with pytest.raises(RuntimeError, match="forced audit failure"):
                await service.process_approval_reply(reply)

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select status from flow_requests where id = %(id)s",
                        {"id": request_id},
                    )
                    assert (await cur.fetchone())["status"] == "RESOLUTION_PENDING_APPROVAL"
                    await cur.execute(
                        "select status from flow_closure_approvals where id = %(id)s",
                        {"id": proposal.approval_id},
                    )
                    assert (await cur.fetchone())["status"] == "PENDING"
                    await cur.execute(
                        "select count(*) from flow_case_audit_records where request_id = %(id)s",
                        {"id": request_id},
                    )
                    assert (await cur.fetchone())["count"] == 0
        finally:
            await close_pool(pool)

    asyncio.run(exercise())

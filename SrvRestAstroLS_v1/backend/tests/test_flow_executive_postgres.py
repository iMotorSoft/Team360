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
from modules.flow.executive_query import AUDIT_SNAPSHOT, LIVE
from modules.flow.executive_service import FlowExecutiveAuditService
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
        self.sent.append({"to": to})
        return f"{self.prefix}-gmail-sent-{len(self.sent)}"


class _ApproveInterpreter:
    def interpret(self, text, *, correlation_id=None):
        return ApprovalDecisionResult(ApprovalDecision.APPROVE, "")


async def _seed_active_request(conn, suffix):
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into flow_conversations (provider, channel, external_thread_id,
                citizen_address, subject, state)
            values ('gmail','email', %(thread)s, 'vecino@example.com',
                    'Executive test', 'CONFIRMED') returning id
            """,
            {"thread": f"exec-{suffix}"},
        )
        conversation_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_request_candidates (conversation_id, revision, ordinal,
                description, tentative_category, status)
            values (%(c)s, 1, 1, 'Luminaria apagada', 'alumbrado', 'CONFIRMED')
            returning id
            """,
            {"c": conversation_id},
        )
        candidate_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_requests (conversation_id, source_candidate_id, description,
                tentative_category, confirmed_at_utc)
            values (%(c)s, %(k)s, 'Luminaria apagada', 'alumbrado', now())
            returning id
            """,
            {"c": conversation_id, "k": candidate_id},
        )
        request_id = str((await cur.fetchone())["id"])
        await cur.execute(
            "select id from flow_sector_levels where sector_id='alumbrado' and level=1"
        )
        level_id = (await cur.fetchone())["id"]
        observed = f"<{suffix}@mail.gmail.com>"
        await cur.execute(
            """
            insert into flow_request_routings (request_id, sector_id, sector_level_id,
                level, channel, destination, status, outbound_rfc_message_id,
                outbound_observed_rfc_message_id, outbound_external_message_id,
                assigned_at_utc)
            values (%(r)s, 'alumbrado', %(l)s, 1, 'email',
                    'alumbrado.n1@alquimiablue.com', 'ASSIGNED', %(i)s, %(o)s,
                    %(ext)s, now()) returning id
            """,
            {"r": request_id, "l": level_id, "i": f"<intended-{suffix}@x.com>", "o": observed, "ext": f"gmail-out-{suffix}"},
        )
        routing_id = str((await cur.fetchone())["id"])
        await cur.execute(
            """
            insert into flow_messages (conversation_id, provider,
                external_message_id, direction, sender_address, recipients_jsonb,
                subject, text_body, occurred_at_utc, metadata_jsonb, processed_at_utc)
            values (%(c)s, 'gmail', %(mid)s, 'inbound', 'vecino@example.com',
                    '[]'::jsonb, 'Luminaria apagada', 'Quiero que reparen la luminaria',
                    now(), '{}'::jsonb, now())
            """,
            {"c": conversation_id, "mid": f"inbound-{suffix}"},
        )
    return request_id, routing_id, conversation_id, observed


def _context(request_id, routing_id, conversation_id):
    return OperationalRoutingContext(
        routing_id=routing_id,
        request_id=request_id,
        conversation_id=conversation_id,
        routing_key="initial_n1",
        level=1,
        routing_status="ASSIGNED",
        destination="alumbrado.n1@alquimiablue.com",
        outbound_external_message_id="gmail-out",
        outbound_rfc_message_id="<intended@x.com>",
        outbound_observed_rfc_message_id=None,
        request_status="CONFIRMED",
    )


def _proposal_message(suffix, observed):
    return InboundMessage(
        provider="gmail", channel="email", external_message_id=f"p-{suffix}",
        external_thread_id="t", sender="tech@alquimiablue.com",
        recipients=("mesa@example.com",), subject="Re: caso",
        text_body="La luminaria fue reparada.", received_at=datetime.now(timezone.utc),
        metadata={"in_reply_to": observed, "references": ""},
    )


def _approval_message(suffix, token, observed):
    return InboundMessage(
        provider="gmail", channel="email", external_message_id=f"d-{suffix}",
        external_thread_id="t2", sender=APPROVER,
        recipients=("mesa@example.com",), subject=f"Re: [CIERRE][R:{token}]",
        text_body="APROBAR", received_at=datetime.now(timezone.utc),
        metadata={"in_reply_to": observed, "references": ""},
    )


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_EXECUTIVE_POSTGRES_TEST") != "1",
    reason="requires migration 019 on Team360 PostgreSQL",
)
def test_real_postgres_executive_live_then_audit_snapshot():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=3)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            request_id, routing_id, conversation_id, observed = await _seed_active_request(
                conn, suffix
            )
            await conn.commit()

        pool = create_pool(settings)
        await open_pool(pool)
        try:
            closure_repo = FlowClosurePostgresRepository()
            audit_repo = FlowAuditRepository()
            service = FlowExecutiveAuditService(
                pool=pool,
                closure_repository=closure_repo,
                audit_repository=audit_repo,
            )

            # ACTIVE case -> LIVE view, no fabricated audit.
            live = await service.query_case(request_id)
            assert live["data_source"] == LIVE
            assert live["status_fact"] == "open"
            assert live["audit"] is None
            assert live["routing_history"][0]["routing_id"] == routing_id
            assert "current_age_seconds" in live["metrics"]
            assert "first_response_elapsed_seconds" not in live["metrics"]

            # Close the case for real (proposal -> supervisor APPROVE -> audit).
            sender = _Sender()
            closure = FlowClosureService(
                pool=pool,
                repository=closure_repo,
                audit_repository=audit_repo,
                interpreter=_ApproveInterpreter(),
                sender=sender,
            )
            context = _context(request_id, routing_id, conversation_id)
            message = _proposal_message(suffix, observed)
            async with pool.connection() as conn:
                async with conn.transaction():
                    proposal = await closure.propose_resolution(
                        conn, context=context, message=message,
                        interpretation=OperationalInterpretation(
                            OperationalAction.RESOLUTION_PROPOSED, "x", "m", "m", {}, 1
                        ),
                    )
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select approval_token, outbound_observed_rfc_message_id from flow_closure_approvals where id = %(id)s",
                        {"id": proposal.approval_id},
                    )
                    row = await cur.fetchone()
            reply = _approval_message(suffix, row["approval_token"], row["outbound_observed_rfc_message_id"])
            decision = await closure.process_approval_reply(reply)
            assert decision.decision == ApprovalDecision.APPROVE

            # RESOLVED case -> AUDIT_SNAPSHOT with the immutable record.
            resolved = await service.query_case(request_id)
            assert resolved["data_source"] == AUDIT_SNAPSHOT
            assert resolved["status_fact"] == "closed"
            assert resolved["audit"]["snapshot_sha256"]
            assert resolved["audit"]["schema_version"] == 1
            assert resolved["resolution"]["resolution_status"] == "APPROVED"
            assert resolved["closure_approval"]["decision"] == "APPROVED"
            assert resolved["result"]["request_status"] == "RESOLVED"
            assert resolved["timeline"]
            assert "current_age_seconds" not in resolved["metrics"]

            # Read-only idempotency: repeated query produces identical view and
            # zero new workflow rows.
            again = await service.query_case(request_id)
            assert again["executive_summary"] == resolved["executive_summary"]
            assert again["audit"]["snapshot_sha256"] == resolved["audit"]["snapshot_sha256"]
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select count(*) from flow_closure_approvals where request_id = %(id)s",
                        {"id": request_id},
                    )
                    assert (await cur.fetchone())["count"] == 1
                    await cur.execute(
                        "select count(*) from flow_case_audit_records where request_id = %(id)s",
                        {"id": request_id},
                    )
                    assert (await cur.fetchone())["count"] == 1
        finally:
            await close_pool(pool)

    asyncio.run(exercise())

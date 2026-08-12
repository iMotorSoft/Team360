import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.flow.domain import (
    OperationalAction,
    OperationalInterpretation,
)
from modules.flow.operational_repository import FlowOperationalPostgresRepository
from modules.messaging.domain import InboundMessage


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_OPERATIONAL_POSTGRES_TEST") != "1",
    reason="requires migrations 011-013 on Team360 PostgreSQL",
)
def test_real_postgres_operational_repository_idempotency_and_first_response():
    async def exercise():
        suffix = uuid4().hex
        repo = FlowOperationalPostgresRepository()
        settings = get_database_settings(min_size=1, max_size=1)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_conversations (
                            provider, channel, external_thread_id,
                            citizen_address, subject, state
                        ) values ('gmail', 'email', %(thread)s,
                                  'citizen@example.com', 'Operational test',
                                  'CONFIRMED') returning id
                        """,
                        {"thread": f"operational-{suffix}"},
                    )
                    conversation_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_candidates (
                            conversation_id, revision, ordinal, description,
                            tentative_category, status
                        ) values (%(conversation)s, 1, 1, 'Reparar poste',
                                  'alumbrado', 'CONFIRMED') returning id
                        """,
                        {"conversation": conversation_id},
                    )
                    candidate_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_requests (
                            conversation_id, source_candidate_id, description,
                            tentative_category, confirmed_at_utc
                        ) values (%(conversation)s, %(candidate)s,
                                  'Reparar poste', 'alumbrado', now())
                        returning id
                        """,
                        {"conversation": conversation_id, "candidate": candidate_id},
                    )
                    request_id = str((await cur.fetchone())["id"])
                    await cur.execute(
                        """
                        select id from flow_sector_levels
                        where sector_id='alumbrado' and level=1
                        """
                    )
                    level_id = (await cur.fetchone())["id"]
                    observed_rfc = f"<{suffix}@mail.gmail.com>"
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id, sector_id, sector_level_id, level,
                            channel, destination, status,
                            outbound_rfc_message_id,
                            outbound_observed_rfc_message_id,
                            outbound_external_message_id, assigned_at_utc
                        ) values (%(request)s, 'alumbrado', %(level_id)s, 1,
                                  'email', 'alumbrado.n1@alquimiablue.com',
                                  'ASSIGNED', %(intended)s, %(observed)s,
                                  %(external)s, now()) returning id
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

                context = await repo.find_by_rfc_reference(conn, (observed_rfc,))
                assert context is not None
                assert context.request_id == request_id
                first_at = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
                first = InboundMessage(
                    "gmail", "email", f"reply-{suffix}", "other-thread",
                    "tech@example.com", ("mesa@example.com",),
                    f"Re: request {request_id}", "Recibido", first_at,
                    {"in_reply_to": observed_rfc},
                )
                source_id = await repo.claim_message(
                    conn, context=context, message=first
                )
                duplicate = await repo.claim_message(
                    conn, context=context, message=first
                )
                assert source_id is not None
                assert duplicate is None
                state = await repo.ensure_work_state(conn, context)
                assert state.status.value == "ASSIGNED"
                interpretation = OperationalInterpretation(
                    OperationalAction.ACK_OR_PROGRESS,
                    "Recibido y en revisión",
                    "mock", "mock", {}, 1,
                )
                await repo.record_event(
                    conn,
                    context=context,
                    source_message_id=source_id,
                    message=first,
                    correlation_method="in_reply_to_rfc",
                    interpretation=interpretation,
                )
                progressed = await repo.mark_in_progress(
                    conn, context=context, message=first
                )
                assert progressed.first_response_at == first_at

                later = InboundMessage(
                    "gmail", "email", f"reply-later-{suffix}", "third-thread",
                    "another-tech@example.com", ("mesa@example.com",),
                    f"Re: request {request_id}", "Seguimos trabajando",
                    first_at + timedelta(hours=2), {"references": observed_rfc},
                )
                unchanged = await repo.mark_in_progress(
                    conn, context=context, message=later
                )
                assert unchanged.first_response_at == first_at
                assert unchanged.first_responder == "tech@example.com"
                evidence = await repo.evidence(conn, request_id)
                assert evidence["operational_status"] == "IN_PROGRESS"
                assert evidence["operational_events"] == 1
                assert evidence["routing_id"] == routing_id
            finally:
                await conn.rollback()

    asyncio.run(exercise())

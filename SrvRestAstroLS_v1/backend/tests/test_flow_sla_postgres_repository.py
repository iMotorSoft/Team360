import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import CheckViolation
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.flow.domain import FirstResponseSLAStatus
from modules.flow.routing_repository import FlowRoutingPostgresRepository
from modules.flow.sla_repository import FlowSLARepository


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_SLA_POSTGRES_TEST") != "1",
    reason="requires migrations 011-014 on Team360 PostgreSQL",
)
def test_real_postgres_sla_snapshot_constraints_reconciliation_and_idempotency():
    async def exercise():
        suffix = uuid4().hex
        t0 = datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)
        settings = get_database_settings(min_size=1, max_size=1)
        routing_repo = FlowRoutingPostgresRepository()
        sla_repo = FlowSLARepository()
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
                        ) values ('gmail','email',%(thread)s,'citizen@example.com',
                                  'SLA test','CONFIRMED') returning id
                        """,
                        {"thread": f"sla-{suffix}"},
                    )
                    conversation_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_candidates (
                            conversation_id, revision, ordinal, description,
                            tentative_category, status
                        ) values (%(conversation)s,1,1,'Reparar poste','alumbrado',
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
                        ) values (%(conversation)s,%(candidate)s,'Reparar poste',
                                  'alumbrado',now()) returning id
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
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id, sector_id, sector_level_id, level, channel,
                            destination, status, outbound_rfc_message_id,
                            outbound_external_message_id, assigned_at_utc
                        ) values (%(request)s,'alumbrado',%(level)s,1,'email',
                                  'alumbrado.n1@alquimiablue.com','ASSIGNED',
                                  %(rfc)s,%(external)s,%(assigned)s)
                        returning id::text
                        """,
                        {
                            "request": request_id,
                            "level": level_id,
                            "rfc": f"<{suffix}@example.com>",
                            "external": f"gmail-{suffix}",
                            "assigned": t0,
                        },
                    )
                    routing_id = (await cur.fetchone())["id"]

                assignment = await routing_repo.get_assignment(conn, request_id)
                await routing_repo.ensure_first_response_sla(conn, assignment)
                await routing_repo.ensure_first_response_sla(conn, assignment)
                evidence = await sla_repo.evidence(conn, routing_id)
                assert evidence["duration_seconds"] == 30
                assert evidence["started_at_utc"] == t0
                assert evidence["due_at_utc"] == t0 + timedelta(seconds=30)
                assert evidence["event_count"] == 1

                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=60
                           where id=%(id)s""",
                        {"id": level_id},
                    )
                unchanged = await sla_repo.evidence(conn, routing_id)
                assert unchanged["duration_seconds"] == 30
                assert unchanged["due_at_utc"] == t0 + timedelta(seconds=30)

                pending = next(s for s in await sla_repo.list_evaluable(conn) if s.routing_id == routing_id)
                breached = await sla_repo.persist_evaluation(
                    conn,
                    sla=pending,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=t0 + timedelta(seconds=40),
                    reconciled=False,
                )
                breached_at = breached.breached_at
                again = await sla_repo.persist_evaluation(
                    conn,
                    sla=breached,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=t0 + timedelta(seconds=50),
                    reconciled=False,
                )
                assert again.breached_at == breached_at

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_request_work_states (
                            request_id, routing_id, operational_status,
                            first_response_at_utc, first_responder
                        ) values (%(request)s,%(routing)s,'IN_PROGRESS',
                                  %(response)s,'tech@example.com')
                        """,
                        {
                            "request": request_id,
                            "routing": routing_id,
                            "response": t0 + timedelta(seconds=20),
                        },
                    )
                loaded = next(s for s in await sla_repo.list_evaluable(conn) if s.routing_id == routing_id)
                met = await sla_repo.persist_evaluation(
                    conn,
                    sla=loaded,
                    status=FirstResponseSLAStatus.MET,
                    now=t0 + timedelta(seconds=60),
                    reconciled=True,
                )
                assert met.met_at == t0 + timedelta(seconds=20)
                assert met.breached_at is None
                final = await sla_repo.evidence(conn, routing_id)
                assert final["status"] == "MET"
                assert final["event_count"] == 3

                with pytest.raises(CheckViolation):
                    async with conn.transaction():
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """update flow_sector_levels
                                   set first_response_sla_seconds=0
                                   where id=%(id)s""",
                                {"id": level_id},
                            )
            finally:
                await conn.rollback()

    asyncio.run(exercise())

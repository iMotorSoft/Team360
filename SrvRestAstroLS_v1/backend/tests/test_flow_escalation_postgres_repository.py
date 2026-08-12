import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.flow.escalation_repository import FlowEscalationPostgresRepository
from modules.flow.operational_repository import FlowOperationalPostgresRepository


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_ESCALATION_POSTGRES_TEST") != "1",
    reason="requires migrations 011-015 on Team360 PostgreSQL",
)
def test_real_postgres_multilevel_state_escalation_constraints_and_idempotency():
    async def exercise():
        suffix = uuid4().hex
        t0 = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)
        repo = FlowEscalationPostgresRepository()
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
                        ) values ('gmail','email',%(thread)s,'citizen@example.com',
                                  'Escalation test','CONFIRMED') returning id
                        """,
                        {"thread": f"escalation-{suffix}"},
                    )
                    conversation_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_candidates (
                            conversation_id, revision, ordinal, description,
                            tentative_category, location_text, status
                        ) values (%(conversation)s,1,1,'Reparar poste','alumbrado',
                                  'Olleros y Ciudad de la Paz','CONFIRMED') returning id
                        """,
                        {"conversation": conversation_id},
                    )
                    candidate_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_requests (
                            conversation_id, source_candidate_id, description,
                            tentative_category, location_text, confirmed_at_utc
                        ) values (%(conversation)s,%(candidate)s,'Reparar poste',
                                  'alumbrado','Olleros y Ciudad de la Paz',now())
                        returning id
                        """,
                        {"conversation": conversation_id, "candidate": candidate_id},
                    )
                    request_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """select level, id from flow_sector_levels
                           where sector_id='alumbrado' and level in (1,2)"""
                    )
                    levels = {row["level"]: row["id"] for row in await cur.fetchall()}
                    assert set(levels) == {1, 2}
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id, routing_key, sector_id, sector_level_id,
                            level, channel, destination, status,
                            outbound_rfc_message_id, outbound_external_message_id,
                            assigned_at_utc
                        ) values (%(request)s,'initial_n1','alumbrado',%(level)s,1,
                                  'email','alumbrado.n1@alquimiablue.com','ASSIGNED',
                                  %(rfc)s,%(external)s,%(assigned)s) returning id
                        """,
                        {"request": request_id, "level": levels[1],
                         "rfc": f"<n1-{suffix}@example.com>",
                         "external": f"gmail-n1-{suffix}", "assigned": t0},
                    )
                    n1 = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_work_states (request_id,routing_id)
                        values (%(request)s,%(routing)s)
                        """,
                        {"request": request_id, "routing": n1},
                    )
                    await cur.execute(
                        """
                        insert into flow_request_slas (
                            routing_id,request_id,duration_seconds,started_at_utc,
                            due_at_utc,status,breached_at_utc,evaluated_at_utc
                        ) values (%(routing)s,%(request)s,30,%(start)s,%(due)s,
                                  'BREACHED',%(breached)s,%(breached)s) returning id
                        """,
                        {"routing": n1, "request": request_id, "start": t0,
                         "due": t0 + timedelta(seconds=30),
                         "breached": t0 + timedelta(seconds=31)},
                    )
                    sla_id = (await cur.fetchone())["id"]

                # A provisional breach with newly discovered on-time evidence is
                # not eligible even before the checker persists MET.
                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_request_work_states
                           set operational_status='IN_PROGRESS',
                               first_response_at_utc=%(response)s,
                               first_responder='tech@example.com'
                           where routing_id=%(routing)s""",
                        {"routing": n1, "response": t0 + timedelta(seconds=20)},
                    )
                assert await repo.get_eligible(conn, str(sla_id)) is None
                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_request_work_states
                           set operational_status='ASSIGNED',
                               first_response_at_utc=null, first_responder=null
                           where routing_id=%(routing)s""",
                        {"routing": n1},
                    )

                eligible = next(
                    row for row in await repo.list_eligible(conn)
                    if row.trigger_sla_id == str(sla_id)
                )
                escalation = await repo.create_pending(conn, eligible)
                duplicate = await repo.create_pending(conn, eligible)
                assert duplicate.id == escalation.id

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id,routing_key,sector_id,sector_level_id,level,
                            channel,destination,status,outbound_rfc_message_id,
                            outbound_external_message_id,assigned_at_utc
                        ) values (%(request)s,'alumbrado_level_2','alumbrado',
                                  %(level)s,2,'email','alumbrado.n2@alquimiablue.com',
                                  'ASSIGNED',%(rfc)s,%(external)s,%(assigned)s)
                        returning id
                        """,
                        {"request": request_id, "level": levels[2],
                         "rfc": f"<n2-{suffix}@example.com>",
                         "external": f"gmail-n2-{suffix}",
                         "assigned": t0 + timedelta(seconds=32)},
                    )
                    n2 = (await cur.fetchone())["id"]
                    await cur.execute(
                        """insert into flow_request_work_states (request_id,routing_id)
                           values (%(request)s,%(routing)s)""",
                        {"request": request_id, "routing": n2},
                    )
                n2_context = await FlowOperationalPostgresRepository().find_by_rfc_reference(
                    conn, (f"<n2-{suffix}@example.com>",)
                )
                assert n2_context is not None
                assert n2_context.routing_id == str(n2)
                completed = await repo.mark_completed(
                    conn, escalation_id=escalation.id, to_routing_id=str(n2)
                )
                assert completed.status.value == "COMPLETED"

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select frr.level, frr.status, fws.operational_status,
                               fs.status as sla_status
                        from flow_request_routings frr
                        join flow_request_work_states fws on fws.routing_id=frr.id
                        left join flow_request_slas fs on fs.routing_id=frr.id
                        where frr.request_id=%(request)s order by frr.level
                        """,
                        {"request": request_id},
                    )
                    history = await cur.fetchall()
                assert history == [
                    {"level": 1, "status": "ASSIGNED", "operational_status": "ASSIGNED", "sla_status": "BREACHED"},
                    {"level": 2, "status": "ASSIGNED", "operational_status": "ASSIGNED", "sla_status": None},
                ]

                # A late N1 response changes only N1 work state. N2 remains an
                # independent ASSIGNED routing and the N1 SLA remains breached.
                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_request_work_states
                           set operational_status='IN_PROGRESS',
                               first_response_at_utc=%(response)s,
                               first_responder='late-tech@example.com'
                           where routing_id=%(routing)s""",
                        {"routing": n1, "response": t0 + timedelta(seconds=35)},
                    )
                    await cur.execute(
                        """select frr.level,fws.operational_status,fs.status sla_status
                           from flow_request_routings frr
                           join flow_request_work_states fws on fws.routing_id=frr.id
                           left join flow_request_slas fs on fs.routing_id=frr.id
                           where frr.request_id=%(request)s order by frr.level""",
                        {"request": request_id},
                    )
                    late_history = await cur.fetchall()
                assert late_history == [
                    {"level": 1, "operational_status": "IN_PROGRESS", "sla_status": "BREACHED"},
                    {"level": 2, "operational_status": "ASSIGNED", "sla_status": None},
                ]

                with pytest.raises(UniqueViolation):
                    async with conn.transaction():
                        async with conn.cursor() as cur:
                            await cur.execute(
                                """
                                insert into flow_request_escalations (
                                    request_id,sector_id,from_routing_id,from_level,
                                    trigger_type,trigger_sla_id,to_level
                                ) values (%(request)s,'alumbrado',%(routing)s,1,
                                          'FIRST_RESPONSE_SLA_BREACHED',%(sla)s,2)
                                """,
                                {"request": request_id, "routing": n1, "sla": sla_id},
                            )
            finally:
                await conn.rollback()

    asyncio.run(exercise())

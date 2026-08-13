import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.db.pool import close_pool, create_pool, open_pool
from modules.flow.escalation_repository import FlowEscalationPostgresRepository
from modules.flow.escalation_service import FlowEscalationService
from modules.flow.operational_repository import FlowOperationalPostgresRepository
from modules.flow.routing_repository import FlowRoutingPostgresRepository


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_ESCALATION_POSTGRES_TEST") != "1",
    reason="requires migrations 011-017 on Team360 PostgreSQL",
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
                           where sector_id='alumbrado' and level in (1,2,3)"""
                    )
                    levels = {row["level"]: row["id"] for row in await cur.fetchall()}
                    assert set(levels) == {1, 2, 3}
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
                escalation = await repo.create_pending(conn, eligible, to_level=2)
                duplicate = await repo.create_pending(conn, eligible, to_level=2)
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
                routing_repo = FlowRoutingPostgresRepository()
                n2_assignment = await routing_repo.get_assignment_for_key(
                    conn,
                    request_id=str(request_id),
                    routing_key="alumbrado_level_2",
                )
                await routing_repo.ensure_first_response_sla(conn, n2_assignment)
                await routing_repo.ensure_first_response_sla(conn, n2_assignment)
                n2_context = await FlowOperationalPostgresRepository().find_by_rfc_reference(
                    conn, (f"<n2-{suffix}@example.com>",)
                )
                assert n2_context is not None
                assert n2_context.routing_id == str(n2)
                completed = await repo.mark_completed(
                    conn, escalation_id=escalation.id, to_routing_id=str(n2)
                )
                assert completed.status.value == "COMPLETED"

                assert (
                    await routing_repo.get_next_active_sector_level(
                        conn, "alumbrado", 1
                    )
                ).level == 2
                assert (
                    await routing_repo.get_next_active_sector_level(
                        conn, "alumbrado", 2
                    )
                ).level == 3
                assert await routing_repo.get_next_active_sector_level(
                    conn, "alumbrado", 3
                ) is None

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        update flow_request_slas
                        set status='BREACHED', breached_at_utc=%(breached)s,
                            evaluated_at_utc=%(breached)s
                        where routing_id=%(routing)s
                        returning id
                        """,
                        {
                            "routing": n2,
                            "breached": t0 + timedelta(seconds=63),
                        },
                    )
                    n2_sla = (await cur.fetchone())["id"]
                n2_eligible = next(
                    row for row in await repo.list_eligible(conn)
                    if row.trigger_sla_id == str(n2_sla)
                )
                assert n2_eligible.from_level == 2
                n2_escalation = await repo.create_pending(
                    conn, n2_eligible, to_level=3
                )
                n2_duplicate = await repo.create_pending(
                    conn, n2_eligible, to_level=3
                )
                assert n2_duplicate.id == n2_escalation.id

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select r.id::text,r.assigned_at_utc,w.operational_status,
                               s.id::text sla_id,s.status sla_status,s.due_at_utc,
                               w.first_response_at_utc,
                               (select count(*) from flow_request_sla_events e
                                where e.sla_id=s.id) event_count
                        from flow_request_routings r
                        join flow_request_work_states w on w.routing_id=r.id
                        join flow_request_slas s on s.routing_id=r.id
                        where r.id in (%(n1)s,%(n2)s) order by r.level
                        """,
                        {"n1": n1, "n2": n2},
                    )
                    history_before_n3 = await cur.fetchall()
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id,routing_key,sector_id,sector_level_id,level,
                            channel,destination,status,outbound_rfc_message_id,
                            outbound_external_message_id,assigned_at_utc
                        ) values (%(request)s,'alumbrado_level_3','alumbrado',
                                  %(level)s,3,'email','alumbrado.n3@alquimiablue.com',
                                  'ASSIGNED',%(rfc)s,%(external)s,%(assigned)s)
                        returning id
                        """,
                        {
                            "request": request_id,
                            "level": levels[3],
                            "rfc": f"<n3-{suffix}@example.com>",
                            "external": f"gmail-n3-{suffix}",
                            "assigned": t0 + timedelta(seconds=64),
                        },
                    )
                    n3 = (await cur.fetchone())["id"]
                    await cur.execute(
                        """insert into flow_request_work_states (request_id,routing_id)
                           values (%(request)s,%(routing)s)""",
                        {"request": request_id, "routing": n3},
                    )
                n3_assignment = await routing_repo.get_assignment_for_key(
                    conn,
                    request_id=str(request_id),
                    routing_key="alumbrado_level_3",
                )
                await routing_repo.ensure_first_response_sla(conn, n3_assignment)
                n3_completed = await repo.mark_completed(
                    conn,
                    escalation_id=n2_escalation.id,
                    to_routing_id=str(n3),
                )
                assert n3_completed.status.value == "COMPLETED"

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
                    {"level": 2, "status": "ASSIGNED", "operational_status": "ASSIGNED", "sla_status": "BREACHED"},
                    {"level": 3, "status": "ASSIGNED", "operational_status": "ASSIGNED", "sla_status": "PENDING"},
                ]

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select r.id::text,r.assigned_at_utc,w.operational_status,
                               s.id::text sla_id,s.status sla_status,s.due_at_utc,
                               w.first_response_at_utc,
                               (select count(*) from flow_request_sla_events e
                                where e.sla_id=s.id) event_count
                        from flow_request_routings r
                        join flow_request_work_states w on w.routing_id=r.id
                        join flow_request_slas s on s.routing_id=r.id
                        where r.id in (%(n1)s,%(n2)s) order by r.level
                        """,
                        {"n1": n1, "n2": n2},
                    )
                    assert await cur.fetchall() == history_before_n3
                    await cur.execute(
                        """select max(level) current_level
                           from flow_request_routings
                           where request_id=%(request)s and status='ASSIGNED'""",
                        {"request": request_id},
                    )
                    assert (await cur.fetchone())["current_level"] == 3
                    await cur.execute(
                        """select from_level,to_level,status
                           from flow_request_escalations
                           where request_id=%(request)s order by from_level""",
                        {"request": request_id},
                    )
                    assert await cur.fetchall() == [
                        {"from_level": 1, "to_level": 2, "status": "COMPLETED"},
                        {"from_level": 2, "to_level": 3, "status": "COMPLETED"},
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
                    {"level": 2, "operational_status": "ASSIGNED", "sla_status": "BREACHED"},
                    {"level": 3, "operational_status": "ASSIGNED", "sla_status": "PENDING"},
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


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_ESCALATION_POSTGRES_TEST") != "1",
    reason="requires migrations 011-017 on Team360 PostgreSQL",
)
def test_real_postgres_concurrent_escalation_sends_once_for_one_n2_sla():
    class ScopedRepository(FlowEscalationPostgresRepository):
        def __init__(self, trigger_sla_id):
            self.trigger_sla_id = str(trigger_sla_id)

        async def list_eligible(self, conn):
            candidate = await self.get_eligible(conn, self.trigger_sla_id)
            return (candidate,) if candidate is not None else ()

    class Sender:
        sender_address = "mesaentrada@alquimiablue.com"

        def __init__(self):
            self.send_calls = []

        def find_sent_message_by_rfc_message_id(self, value):
            return None

        def find_sent_message_by_reference(self, value, *, to=None):
            return None

        def send_message(self, **kwargs):
            self.send_calls.append(kwargs)
            return "gmail-concurrency-n3"

        def get_message_rfc_id(self, message_id):
            return "<gmail-concurrency-n3@example.com>"

    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        sender = Sender()
        request_id = candidate_id = conversation_id = None
        try:
            async with pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            insert into flow_conversations (
                                provider, channel, external_thread_id,
                                citizen_address, subject, state
                            ) values ('gmail','email',%(thread)s,'citizen@example.com',
                                      'Concurrency escalation','CONFIRMED') returning id
                            """,
                            {"thread": f"escalation-concurrency-{suffix}"},
                        )
                        conversation_id = (await cur.fetchone())["id"]
                        await cur.execute(
                            """
                            insert into flow_request_candidates (
                                conversation_id, revision, ordinal, description,
                                tentative_category, location_text, status
                            ) values (%(conversation)s,1,1,'Poste sin luz','alumbrado',
                                      'Olleros 100','CONFIRMED') returning id
                            """,
                            {"conversation": conversation_id},
                        )
                        candidate_id = (await cur.fetchone())["id"]
                        await cur.execute(
                            """
                            insert into flow_requests (
                                conversation_id, source_candidate_id, description,
                                tentative_category, location_text, confirmed_at_utc
                            ) values (%(conversation)s,%(candidate)s,'Poste sin luz',
                                      'alumbrado','Olleros 100',now()) returning id
                            """,
                            {"conversation": conversation_id, "candidate": candidate_id},
                        )
                        request_id = (await cur.fetchone())["id"]
                        await cur.execute(
                            """
                            insert into flow_request_routings (
                                request_id,routing_key,sector_id,sector_level_id,level,
                                channel,destination,status,outbound_rfc_message_id,
                                outbound_external_message_id,assigned_at_utc
                            ) select %(request)s,'alumbrado_level_2','alumbrado',id,2,
                                     channel,destination,'ASSIGNED',%(rfc)s,%(external)s,now()
                              from flow_sector_levels
                             where sector_id='alumbrado' and level=2
                            returning id
                            """,
                            {
                                "request": request_id,
                                "rfc": f"<n2-concurrency-{suffix}@example.com>",
                                "external": f"gmail-n2-concurrency-{suffix}",
                            },
                        )
                        n2_routing_id = (await cur.fetchone())["id"]
                        await cur.execute(
                            """insert into flow_request_work_states (request_id,routing_id)
                               values (%(request)s,%(routing)s)""",
                            {"request": request_id, "routing": n2_routing_id},
                        )
                        await cur.execute(
                            """
                            insert into flow_request_slas (
                                routing_id,request_id,duration_seconds,started_at_utc,
                                due_at_utc,status,breached_at_utc,evaluated_at_utc
                            ) values (%(routing)s,%(request)s,30,now()-interval '40 seconds',
                                      now()-interval '10 seconds','BREACHED',now(),now())
                            returning id
                            """,
                            {"request": request_id, "routing": n2_routing_id},
                        )
                        trigger_sla_id = (await cur.fetchone())["id"]

            services = [
                FlowEscalationService(
                    pool=pool,
                    repository=ScopedRepository(trigger_sla_id),
                    routing_repository=FlowRoutingPostgresRepository(),
                    sender=sender,
                )
                for _ in range(2)
            ]
            results = await asyncio.gather(
                *(service.escalate_once(confirm_send=True) for service in services)
            )
            assert sum(result.sent for result in results) == 1
            assert len(sender.send_calls) == 1
            assert sender.send_calls[0]["to"] == "alumbrado.n3@alquimiablue.com"

            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """select count(*) as count
                           from flow_request_escalations
                           where trigger_sla_id=%(sla)s""",
                        {"sla": trigger_sla_id},
                    )
                    assert (await cur.fetchone())["count"] == 1
                    await cur.execute(
                        """select count(*) as count
                           from flow_request_routings
                           where request_id=%(request)s and routing_key='alumbrado_level_3'""",
                        {"request": request_id},
                    )
                    assert (await cur.fetchone())["count"] == 1
        finally:
            if request_id is not None:
                async with pool.connection() as conn:
                    async with conn.transaction():
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "delete from flow_request_escalations where request_id=%s",
                                (request_id,),
                            )
                            await cur.execute(
                                """delete from flow_request_sla_events
                                   where sla_id in (
                                       select id from flow_request_slas where request_id=%s
                                   )""",
                                (request_id,),
                            )
                            await cur.execute(
                                "delete from flow_request_slas where request_id=%s",
                                (request_id,),
                            )
                            await cur.execute(
                                "delete from flow_request_work_states where request_id=%s",
                                (request_id,),
                            )
                            await cur.execute(
                                "delete from flow_request_routings where request_id=%s",
                                (request_id,),
                            )
                            await cur.execute("delete from flow_requests where id=%s", (request_id,))
                            await cur.execute(
                                "delete from flow_request_candidates where id=%s",
                                (candidate_id,),
                            )
                            await cur.execute(
                                "delete from flow_conversations where id=%s",
                                (conversation_id,),
                            )
            await close_pool(pool)

    asyncio.run(exercise())

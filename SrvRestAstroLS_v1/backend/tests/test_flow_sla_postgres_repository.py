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
from modules.flow.escalation_repository import FlowEscalationPostgresRepository
from modules.flow.routing_repository import FlowRoutingPostgresRepository
from modules.flow.sla_repository import FlowSLARepository


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_SLA_POSTGRES_TEST") != "1",
    reason="requires migrations 011-018 on Team360 PostgreSQL",
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

                    await cur.execute(
                        """
                        select id from flow_sector_levels
                        where sector_id='alumbrado' and level=2
                        """
                    )
                    n2_level_id = (await cur.fetchone())["id"]
                    n2_t0 = t0 + timedelta(minutes=1)
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id, routing_key, sector_id, sector_level_id,
                            level, channel, destination, status,
                            outbound_rfc_message_id,
                            outbound_external_message_id, assigned_at_utc
                        ) values (
                            %(request)s,'alumbrado_level_2','alumbrado',%(level)s,
                            2,'email','alumbrado.n2@alquimiablue.com','ASSIGNED',
                            %(rfc)s,%(external)s,%(assigned)s
                        ) returning id::text
                        """,
                        {
                            "request": request_id,
                            "level": n2_level_id,
                            "rfc": f"<n2-{suffix}@example.com>",
                            "external": f"gmail-n2-{suffix}",
                            "assigned": n2_t0,
                        },
                    )
                    n2_routing_id = (await cur.fetchone())["id"]

                assignment = await routing_repo.get_assignment(conn, request_id)
                n2_assignment = await routing_repo.get_assignment_for_key(
                    conn,
                    request_id=request_id,
                    routing_key="alumbrado_level_2",
                )
                await routing_repo.ensure_first_response_sla(conn, assignment)
                await routing_repo.ensure_first_response_sla(conn, assignment)
                await routing_repo.ensure_first_response_sla(conn, n2_assignment)
                await routing_repo.ensure_first_response_sla(conn, n2_assignment)
                evidence = await sla_repo.evidence(conn, routing_id)
                n2_evidence = await sla_repo.evidence(conn, n2_routing_id)
                assert evidence["duration_seconds"] == 30
                assert evidence["started_at_utc"] == t0
                assert evidence["due_at_utc"] == t0 + timedelta(seconds=30)
                assert evidence["event_count"] == 1
                assert n2_evidence["request_id"] == evidence["request_id"]
                assert n2_evidence["duration_seconds"] == 30
                assert n2_evidence["started_at_utc"] == n2_t0
                assert n2_evidence["due_at_utc"] == n2_t0 + timedelta(seconds=30)
                assert n2_evidence["event_count"] == 1

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

                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=60
                           where id=%(id)s""",
                        {"id": n2_level_id},
                    )
                unchanged_n2 = await sla_repo.evidence(conn, n2_routing_id)
                assert unchanged_n2["duration_seconds"] == 30
                assert unchanged_n2["due_at_utc"] == n2_t0 + timedelta(seconds=30)

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

                n1_before_n2 = await sla_repo.evidence(conn, routing_id)
                pending_n2 = next(
                    s for s in await sla_repo.list_evaluable(conn)
                    if s.routing_id == n2_routing_id
                )
                n2_breached = await sla_repo.persist_evaluation(
                    conn,
                    sla=pending_n2,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=n2_t0 + timedelta(seconds=31),
                    reconciled=False,
                )
                n2_breached_at = n2_breached.breached_at
                n2_breached_again = await sla_repo.persist_evaluation(
                    conn,
                    sla=n2_breached,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=n2_t0 + timedelta(seconds=40),
                    reconciled=False,
                )
                assert n2_breached_again.breached_at == n2_breached_at
                assert await sla_repo.evidence(conn, routing_id) == n1_before_n2
                eligible_sla_ids = {
                    candidate.trigger_sla_id
                    for candidate in await FlowEscalationPostgresRepository().list_eligible(conn)
                }
                assert n2_breached.id in eligible_sla_ids

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_request_work_states (
                            request_id, routing_id, operational_status,
                            first_response_at_utc, first_responder
                        ) values (%(request)s,%(routing)s,'IN_PROGRESS',
                                  %(response)s,'n2-tech@example.com')
                        """,
                        {
                            "request": request_id,
                            "routing": n2_routing_id,
                            "response": n2_t0 + timedelta(seconds=20),
                        },
                    )
                loaded_n2 = next(
                    s for s in await sla_repo.list_evaluable(conn)
                    if s.routing_id == n2_routing_id
                )
                reconciled_n2 = await sla_repo.persist_evaluation(
                    conn,
                    sla=loaded_n2,
                    status=FirstResponseSLAStatus.MET,
                    now=n2_t0 + timedelta(seconds=50),
                    reconciled=True,
                )
                assert reconciled_n2.met_at == n2_t0 + timedelta(seconds=20)
                assert reconciled_n2.breached_at is None
                assert await sla_repo.evidence(conn, routing_id) == n1_before_n2
                final_n2 = await sla_repo.evidence(conn, n2_routing_id)
                assert final_n2["status"] == "MET"
                assert final_n2["operational_status"] == "IN_PROGRESS"
                assert final_n2["event_count"] == 3
                eligible_after_reconciliation = {
                    candidate.trigger_sla_id
                    for candidate in await FlowEscalationPostgresRepository().list_eligible(conn)
                }
                assert n2_breached.id not in eligible_after_reconciliation

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

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id, routing_key, sector_id, sector_level_id,
                            level, channel, destination, status,
                            outbound_rfc_message_id,
                            outbound_external_message_id, assigned_at_utc
                        ) values (
                            %(request)s,'test_n2_policy_60','alumbrado',%(level)s,
                            2,'email','alumbrado.n2@alquimiablue.com','ASSIGNED',
                            %(rfc)s,%(external)s,%(assigned)s
                        ) returning id::text
                        """,
                        {
                            "request": request_id,
                            "level": n2_level_id,
                            "rfc": f"<n2-60-{suffix}@example.com>",
                            "external": f"gmail-n2-60-{suffix}",
                            "assigned": n2_t0 + timedelta(minutes=1),
                        },
                    )
                    n2_60_routing_id = (await cur.fetchone())["id"]
                n2_60_assignment = await routing_repo.get_assignment_for_key(
                    conn, request_id=request_id, routing_key="test_n2_policy_60"
                )
                await routing_repo.ensure_first_response_sla(conn, n2_60_assignment)
                n2_60 = await sla_repo.evidence(conn, n2_60_routing_id)
                assert n2_60["duration_seconds"] == 60

                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=null
                           where id=%(id)s""",
                        {"id": n2_level_id},
                    )
                    await cur.execute(
                        """
                        insert into flow_request_routings (
                            request_id, routing_key, sector_id, sector_level_id,
                            level, channel, destination, status,
                            outbound_rfc_message_id,
                            outbound_external_message_id, assigned_at_utc
                        ) values (
                            %(request)s,'test_n2_policy_null','alumbrado',%(level)s,
                            2,'email','alumbrado.n2@alquimiablue.com','ASSIGNED',
                            %(rfc)s,%(external)s,%(assigned)s
                        ) returning id::text
                        """,
                        {
                            "request": request_id,
                            "level": n2_level_id,
                            "rfc": f"<n2-null-{suffix}@example.com>",
                            "external": f"gmail-n2-null-{suffix}",
                            "assigned": n2_t0 + timedelta(minutes=2),
                        },
                    )
                    n2_null_routing_id = (await cur.fetchone())["id"]
                n2_null_assignment = await routing_repo.get_assignment_for_key(
                    conn, request_id=request_id, routing_key="test_n2_policy_null"
                )
                await routing_repo.ensure_first_response_sla(conn, n2_null_assignment)
                assert await sla_repo.evidence(conn, n2_null_routing_id) is None

                for invalid_seconds in (0, -1):
                    with pytest.raises(CheckViolation):
                        async with conn.transaction():
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    """update flow_sector_levels
                                       set first_response_sla_seconds=%(seconds)s
                                       where id=%(id)s""",
                                    {"id": n2_level_id, "seconds": invalid_seconds},
                                )
            finally:
                await conn.rollback()

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_SLA_POSTGRES_TEST") != "1",
    reason="requires migrations 011-018 on Team360 PostgreSQL",
)
def test_real_postgres_n3_policy_snapshots_results_reconciliation_and_no_n4():
    async def exercise():
        suffix = uuid4().hex
        t0 = datetime(2026, 8, 13, 14, 0, tzinfo=timezone.utc)
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
                                  'N3 SLA test','CONFIRMED') returning id
                        """,
                        {"thread": f"n3-sla-{suffix}"},
                    )
                    conversation_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_candidates (
                            conversation_id, revision, ordinal, description,
                            tentative_category, status
                        ) values (%(conversation)s,1,1,'Reparar luminaria',
                                  'alumbrado','CONFIRMED') returning id
                        """,
                        {"conversation": conversation_id},
                    )
                    candidate_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_requests (
                            conversation_id, source_candidate_id, description,
                            tentative_category, confirmed_at_utc
                        ) values (%(conversation)s,%(candidate)s,
                                  'Reparar luminaria','alumbrado',now()) returning id
                        """,
                        {"conversation": conversation_id, "candidate": candidate_id},
                    )
                    request_id = str((await cur.fetchone())["id"])
                    await cur.execute(
                        """select level,id from flow_sector_levels
                           where sector_id='alumbrado' and level in (1,2,3)"""
                    )
                    levels = {row["level"]: row["id"] for row in await cur.fetchall()}
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=null where id=%s""",
                        (levels[3],),
                    )

                async def add_routing(key, level, assigned):
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            insert into flow_request_routings (
                                request_id,routing_key,sector_id,sector_level_id,
                                level,channel,destination,status,
                                outbound_rfc_message_id,
                                outbound_external_message_id,assigned_at_utc
                            ) values (%(request)s,%(key)s,'alumbrado',%(level_id)s,
                                      %(level)s,'email',%(destination)s,'ASSIGNED',
                                      %(rfc)s,%(external)s,%(assigned)s)
                            returning id::text
                            """,
                            {
                                "request": request_id,
                                "key": key,
                                "level_id": levels[level],
                                "level": level,
                                "destination": f"alumbrado.n{level}@alquimiablue.com",
                                "rfc": f"<{key}-{suffix}@example.com>",
                                "external": f"gmail-{key}-{suffix}",
                                "assigned": assigned,
                            },
                        )
                        routing_id = (await cur.fetchone())["id"]
                    assignment = await routing_repo.get_assignment_for_key(
                        conn, request_id=request_id, routing_key=key
                    )
                    await routing_repo.ensure_work_state(conn, assignment)
                    await routing_repo.ensure_first_response_sla(conn, assignment)
                    return routing_id, assignment

                n1, _ = await add_routing("n3-test-n1", 1, t0)
                n2, _ = await add_routing(
                    "n3-test-n2", 2, t0 + timedelta(minutes=1)
                )
                historical_n3, _ = await add_routing(
                    "n3-test-historical-null", 3, t0 + timedelta(minutes=2)
                )
                assert await sla_repo.evidence(conn, historical_n3) is None

                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=30 where id=%s""",
                        (levels[3],),
                    )
                assert await sla_repo.evidence(conn, historical_n3) is None
                # Re-running ensure on a historical routing is deliberately not
                # part of migration/application behavior and would synthesize a
                # snapshot, so it is not invoked after the policy change.

                n3_start = t0 + timedelta(minutes=3)
                n3, n3_assignment = await add_routing(
                    "n3-test-policy-30", 3, n3_start
                )
                await routing_repo.ensure_first_response_sla(conn, n3_assignment)
                n3_pending = await sla_repo.evidence(conn, n3)
                assert n3_pending["duration_seconds"] == 30
                assert n3_pending["started_at_utc"] == n3_start
                assert n3_pending["due_at_utc"] == n3_start + timedelta(seconds=30)
                assert n3_pending["status"] == "PENDING"
                assert n3_pending["event_count"] == 1

                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=60 where id=%s""",
                        (levels[3],),
                    )
                unchanged = await sla_repo.evidence(conn, n3)
                assert unchanged["duration_seconds"] == 30
                assert unchanged["due_at_utc"] == n3_start + timedelta(seconds=30)
                n3_60, _ = await add_routing(
                    "n3-test-policy-60", 3, n3_start + timedelta(minutes=1)
                )
                assert (await sla_repo.evidence(conn, n3_60))["duration_seconds"] == 60

                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_sector_levels
                           set first_response_sla_seconds=30 where id=%s""",
                        (levels[3],),
                    )
                    for routing in (n1, n2):
                        await cur.execute(
                            """update flow_request_slas
                               set status='BREACHED', breached_at_utc=due_at_utc,
                                   evaluated_at_utc=due_at_utc
                               where routing_id=%s""",
                            (routing,),
                        )
                    await cur.execute(
                        """update flow_request_work_states
                           set operational_status='IN_PROGRESS',
                               first_response_at_utc=%s,
                               first_responder='n3-tech@example.com'
                           where routing_id=%s""",
                        (n3_start + timedelta(seconds=10), n3),
                    )
                n1_before = await sla_repo.evidence(conn, n1)
                n2_before = await sla_repo.evidence(conn, n2)
                loaded_n3 = next(
                    sla for sla in await sla_repo.list_evaluable(conn)
                    if sla.routing_id == n3
                )
                met_n3 = await sla_repo.persist_evaluation(
                    conn,
                    sla=loaded_n3,
                    status=FirstResponseSLAStatus.MET,
                    now=n3_start + timedelta(seconds=20),
                    reconciled=False,
                )
                assert met_n3.met_at == n3_start + timedelta(seconds=10)
                assert (await sla_repo.evidence(conn, n3))["event_count"] == 2
                assert await sla_repo.evidence(conn, n1) == n1_before
                assert await sla_repo.evidence(conn, n2) == n2_before

                breach_start = n3_start + timedelta(minutes=2)
                n3_breach, _ = await add_routing(
                    "n3-test-breach", 3, breach_start
                )
                breach_sla = next(
                    sla for sla in await sla_repo.list_evaluable(conn)
                    if sla.routing_id == n3_breach
                )
                breached = await sla_repo.persist_evaluation(
                    conn,
                    sla=breach_sla,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=breach_start + timedelta(seconds=31),
                    reconciled=False,
                )
                breached_at = breached.breached_at
                breached_again = await sla_repo.persist_evaluation(
                    conn,
                    sla=breached,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=breach_start + timedelta(seconds=40),
                    reconciled=False,
                )
                assert breached_again.breached_at == breached_at
                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_request_work_states
                           set operational_status='IN_PROGRESS',
                               first_response_at_utc=%s,
                               first_responder='late@example.com'
                           where routing_id=%s""",
                        (breach_start + timedelta(seconds=40), n3_breach),
                    )
                assert all(
                    sla.routing_id != n3_breach
                    for sla in await sla_repo.list_evaluable(conn)
                )
                assert (
                    await sla_repo.evidence(conn, n3_breach)
                )["operational_status"] == "IN_PROGRESS"

                reconcile_start = n3_start + timedelta(minutes=3)
                n3_reconcile, _ = await add_routing(
                    "n3-test-reconcile", 3, reconcile_start
                )
                provisional = next(
                    sla for sla in await sla_repo.list_evaluable(conn)
                    if sla.routing_id == n3_reconcile
                )
                provisional = await sla_repo.persist_evaluation(
                    conn,
                    sla=provisional,
                    status=FirstResponseSLAStatus.BREACHED,
                    now=reconcile_start + timedelta(seconds=31),
                    reconciled=False,
                )
                async with conn.cursor() as cur:
                    await cur.execute(
                        """update flow_request_work_states
                           set operational_status='IN_PROGRESS',
                               first_response_at_utc=%s,
                               first_responder='timely@example.com'
                           where routing_id=%s""",
                        (reconcile_start + timedelta(seconds=20), n3_reconcile),
                    )
                reload_reconcile = next(
                    sla for sla in await sla_repo.list_evaluable(conn)
                    if sla.routing_id == n3_reconcile
                )
                reconciled = await sla_repo.persist_evaluation(
                    conn,
                    sla=reload_reconcile,
                    status=FirstResponseSLAStatus.MET,
                    now=reconcile_start + timedelta(seconds=40),
                    reconciled=True,
                )
                assert reconciled.met_at == reconcile_start + timedelta(seconds=20)
                assert (await sla_repo.evidence(conn, n3_reconcile))["event_count"] == 3

                eligible = await FlowEscalationPostgresRepository().list_eligible(conn)
                assert all(item.from_level < 3 for item in eligible)
                assert await routing_repo.get_next_active_sector_level(
                    conn, "alumbrado", 3
                ) is None
                async with conn.cursor() as cur:
                    await cur.execute(
                        """select count(*) as count from flow_request_slas
                           where request_id=%s""",
                        (request_id,),
                    )
                    assert (await cur.fetchone())["count"] >= 3
                    await cur.execute(
                        """select count(*) as count from flow_request_routings
                           where request_id=%s and level >= 4""",
                        (request_id,),
                    )
                    assert (await cur.fetchone())["count"] == 0
                    await cur.execute(
                        """select count(*) as count from flow_request_escalations
                           where request_id=%s and from_level >= 3""",
                        (request_id,),
                    )
                    assert (await cur.fetchone())["count"] == 0
                for invalid_seconds in (0, -1):
                    with pytest.raises(CheckViolation):
                        async with conn.transaction():
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    """update flow_sector_levels
                                       set first_response_sla_seconds=%s
                                       where id=%s""",
                                    (invalid_seconds, levels[3]),
                                )
            finally:
                await conn.rollback()

    asyncio.run(exercise())

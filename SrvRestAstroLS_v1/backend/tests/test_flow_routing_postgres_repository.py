import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.flow.domain import RoutingStatus, routing_rfc_message_id
from modules.flow.routing_repository import FlowRoutingPostgresRepository


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_ROUTING_POSTGRES_TEST") != "1",
    reason="requires migrations 011/012 on the configured Team360 PostgreSQL",
)
def test_real_postgres_routing_repository_catalog_and_idempotency():
    async def exercise():
        suffix = uuid4().hex
        repo = FlowRoutingPostgresRepository()
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
                        ) values (
                            'gmail', 'email', %(thread_id)s,
                            'integration@example.com', 'Routing repository',
                            'CONFIRMED'
                        ) returning id
                        """,
                        {"thread_id": f"routing-integration-{suffix}"},
                    )
                    conversation_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_candidates (
                            conversation_id, revision, ordinal, description,
                            tentative_category, location_text, status
                        ) values (
                            %(conversation_id)s, 1, 1, 'Reparar poste',
                            'alumbrado', 'Olleros y Ciudad de la Paz',
                            'CONFIRMED'
                        ) returning id
                        """,
                        {"conversation_id": conversation_id},
                    )
                    candidate_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_requests (
                            conversation_id, source_candidate_id, description,
                            tentative_category, location_text, confirmed_at_utc
                        ) values (
                            %(conversation_id)s, %(candidate_id)s,
                            'Reparar poste', 'alumbrado',
                            'Olleros y Ciudad de la Paz', now()
                        ) returning id
                        """,
                        {
                            "conversation_id": conversation_id,
                            "candidate_id": candidate_id,
                        },
                    )
                    request_id = str((await cur.fetchone())["id"])

                request = await repo.get_request(conn, request_id)
                sector = await repo.get_sector(conn, "alumbrado")
                level = await repo.get_sector_level(conn, "alumbrado", 1)
                assert request is not None and request.status == "CONFIRMED"
                assert sector is not None and sector.active is True
                assert level is not None
                assert level.destination == "alumbrado.n1@alquimiablue.com"

                first = await repo.create_pending_assignment(
                    conn,
                    request_id=request_id,
                    sector=sector,
                    sector_level=level,
                    outbound_rfc_message_id=routing_rfc_message_id(request_id),
                )
                duplicate = await repo.create_pending_assignment(
                    conn,
                    request_id=request_id,
                    sector=sector,
                    sector_level=level,
                    outbound_rfc_message_id=routing_rfc_message_id(request_id),
                )
                assert duplicate.id == first.id

                attempted = await repo.mark_attempt(conn, first.id)
                assigned = await repo.mark_assigned(
                    conn,
                    assignment_id=first.id,
                    external_message_id=f"gmail-integration-{suffix}",
                )
                evidence = await repo.routing_evidence(conn, request_id)
                assert attempted.attempt_count == 1
                assert assigned.status == RoutingStatus.ASSIGNED
                assert evidence["routing_id"] == first.id
                assert evidence["status"] == "ASSIGNED"
                assert evidence["attempt_count"] == 1

                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select count(*) as count
                        from flow_request_routings
                        where request_id = %(request_id)s
                          and routing_key = 'initial_n1'
                        """,
                        {"request_id": request_id},
                    )
                    assert (await cur.fetchone())["count"] == 1
            finally:
                await conn.rollback()

    asyncio.run(exercise())

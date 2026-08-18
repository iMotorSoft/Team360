"""Real PostgreSQL coverage for the read-only executive case list."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.executive_list_service import FlowExecutiveListService


REQUIRE = "requires TEAM360_FLOW_EXECUTIVE_LIST_POSTGRES_TEST=1"


async def _counts(conn) -> dict[str, int]:
    result = {}
    async with conn.cursor() as cur:
        for table in (
            "flow_messages",
            "flow_request_routings",
            "flow_request_slas",
            "flow_request_sla_events",
            "flow_request_escalations",
            "flow_request_resolutions",
            "flow_closure_approvals",
            "flow_case_audit_records",
        ):
            await cur.execute(f"select count(*) from {table}")
            result[table] = (await cur.fetchone())["count"]
    return result


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_EXECUTIVE_LIST_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_executive_list_filters_pagination_and_read_only():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=2)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            service = FlowExecutiveListService(pool=pool)
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                before = await _counts(conn)

            first = await service.list_cases(page=1, page_size=3)
            assert len(first["items"]) == 3
            assert first["pagination"] == {
                "page": 1,
                "page_size": 3,
                "total": 24,
                "has_next": True,
            }
            assert first["items"][0]["request_id"] == "9285797d-4939-4732-a28a-68c50df6bb77"
            assert first["items"][0]["updated_at"] is not None

            resolved = await service.list_cases(status="resolved", page_size=100)
            assert resolved["items"]
            assert all(item["status_fact"] == "closed" for item in resolved["items"])
            assert all(item["data_source"] == "AUDIT_SNAPSHOT" for item in resolved["items"])

            pending = await service.list_cases(status="pending_approval", page_size=100)
            assert [item["request_id"] for item in pending["items"]] == [
                "d16a0a08-315b-47a8-9790-aaece91bde5f"
            ]

            searched = await service.list_cases(
                status="open",
                sector_id="alumbrado",
                search="Olleros",
                page_size=100,
            )
            assert searched["items"]
            assert all(item["status_fact"] == "open" for item in searched["items"])
            assert all(item["sector_id"] == "alumbrado" for item in searched["items"])

            escalated = await service.list_cases(escalated=True, page_size=100)
            escalated_item = next(
                item
                for item in escalated["items"]
                if item["request_id"] == "333a15d0-b3cd-4ec1-ba01-b0a9593f087f"
            )
            assert escalated_item["current_level"] == 3
            assert escalated_item["escalation_count"] == 2
            assert escalated_item["has_breached_sla"] is True

            second = await service.list_cases(page=1, page_size=3)
            assert second["items"] == first["items"]
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                assert await _counts(conn) == before
        finally:
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_EXECUTIVE_LIST_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_new_request_appears_without_frontend_registry():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=2)
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = None
        conversation_id = None
        candidate_id = None
        suffix = uuid4().hex
        try:
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_conversations (
                            provider, channel, external_thread_id,
                            citizen_address, subject, state
                        ) values ('test','email',%(thread)s,'citizen@example.com',
                                  'List auto-discovery','CONFIRMED') returning id
                        """,
                        {"thread": f"executive-list-{suffix}"},
                    )
                    conversation_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_request_candidates (
                            conversation_id, revision, ordinal, description,
                            tentative_category, location_text, status
                        ) values (%(conversation)s,1,1,%(description)s,'alumbrado',
                                  'List auto-discovery location','CONFIRMED') returning id
                        """,
                        {
                            "conversation": conversation_id,
                            "description": f"Auto list fixture {suffix}",
                        },
                    )
                    candidate_id = (await cur.fetchone())["id"]
                    await cur.execute(
                        """
                        insert into flow_requests (
                            conversation_id, source_candidate_id, description,
                            tentative_category, location_text, confirmed_at_utc
                        ) values (%(conversation)s,%(candidate)s,%(description)s,
                                  'alumbrado','List auto-discovery location',now())
                        returning id
                        """,
                        {
                            "conversation": conversation_id,
                            "candidate": candidate_id,
                            "description": f"Auto list fixture {suffix}",
                        },
                    )
                    request_id = str((await cur.fetchone())["id"])
                    await conn.commit()

            result = await FlowExecutiveListService(pool=pool).list_cases(
                search=f"Auto list fixture {suffix}",
                page_size=20,
            )
            assert [item["request_id"] for item in result["items"]] == [request_id]
            assert result["items"][0]["status_fact"] == "open"
        finally:
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    if request_id:
                        await cur.execute(
                            "delete from flow_requests where id = %s::uuid",
                            (request_id,),
                        )
                    if candidate_id:
                        await cur.execute(
                            "delete from flow_request_candidates where id = %s::uuid",
                            (candidate_id,),
                        )
                    if conversation_id:
                        await cur.execute(
                            "delete from flow_conversations where id = %s::uuid",
                            (conversation_id,),
                        )
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())

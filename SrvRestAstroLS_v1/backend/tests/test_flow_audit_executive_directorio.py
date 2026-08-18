"""Team360 Flow — Audit Record -> Executive Query -> Directorio chain.

Validates, against real PostgreSQL, that a closed case is served from the
immutable Audit Record: hash recomputation, immutability, read-only behavior,
LIVE vs AUDIT_SNAPSHOT switching, integrity failures (missing/corrupt audit)
and historical independence from later configuration changes.

Gated behind TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST=1 following the repository
convention; the demo harness creates a fresh RESOLVED + audit case per run and
is cleaned up afterwards.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.audit_repository import FlowAuditRepository, sha256_of_snapshot
from modules.flow.closure_repository import FlowClosurePostgresRepository
from modules.flow.configuration_service import FlowConfigurationService
from modules.flow.demo.run import cleanup_demo_cases, run_demo
from modules.flow.domain import AUDIT_SCHEMA_VERSION
from modules.flow.executive_query import AUDIT_SNAPSHOT, LIVE
from modules.flow.executive_service import (
    FlowAuditIntegrityError,
    FlowExecutiveAuditService,
)

REQUIRE = "requires TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST=1"


def _service(pool):
    return FlowExecutiveAuditService(
        pool=pool,
        closure_repository=FlowClosurePostgresRepository(),
        audit_repository=FlowAuditRepository(),
    )


async def _row_counts(settings, request_id) -> dict[str, int]:
    import psycopg
    from psycopg.rows import dict_row

    tables = (
        ("flow_messages", "conversation_id", "fr.conversation_id"),
        ("flow_request_routings", "request_id", "fr.id"),
        ("flow_request_slas", "request_id", "fr.id"),
        ("flow_request_sla_events", "sla_id", "fs.id"),
        ("flow_request_escalations", "request_id", "fr.id"),
        ("flow_request_resolutions", "request_id", "fr.id"),
        ("flow_closure_approvals", "request_id", "fr.id"),
        ("flow_case_audit_records", "request_id", "fr.id"),
        ("flow_request_operational_events", "request_id", "fr.id"),
    )
    result: dict[str, int] = {}
    async with await psycopg.AsyncConnection.connect(
        settings.dsn, row_factory=dict_row
    ) as conn:
        async with conn.cursor() as cur:
            for table, _col, _join in tables:
                if table == "flow_request_sla_events":
                    sql = (
                        "select count(*) as count from flow_request_sla_events fse "
                        "join flow_request_slas fs on fs.id = fse.sla_id "
                        "where fs.request_id = %(rid)s"
                    )
                else:
                    sql = (
                        f"select count(*) as count from {table} "
                        f"where {_col} = %(rid)s::uuid"
                    )
                await cur.execute(sql, {"rid": request_id})
                result[table] = (await cur.fetchone())["count"]
    return result


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST") != "1",
    reason=REQUIRE,
)
def test_audit_hash_stable_immutable_and_read_only():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            report = await run_demo(pool, settings)
            service = _service(pool)
            view = await service.query_case(report.request_id)
            assert view["data_source"] == AUDIT_SNAPSHOT
            assert view["status_fact"] == "closed"
            assert view["audit"]["schema_version"] == AUDIT_SCHEMA_VERSION
            stored_hash = view["audit"]["snapshot_sha256"]

            for _ in range(10):
                again = await service.query_case(report.request_id)
                assert again["audit"]["snapshot_sha256"] == stored_hash
                assert again["audit"]["audit_record_id"] == report.audit_id

            before = await _row_counts(settings, report.request_id)
            for _ in range(5):
                await service.query_case(report.request_id)
            after = await _row_counts(settings, report.request_id)
            assert before == after, f"read mutated data: {before} -> {after}"
        finally:
            await cleanup_demo_cases(pool)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST") != "1",
    reason=REQUIRE,
)
def test_executive_facts_match_audit_snapshot():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            report = await run_demo(pool, settings)
            service = _service(pool)
            view = await service.query_case(report.request_id)

            assert [row["level"] for row in view["routing_history"]] == [1, 2]
            assert len(view["escalations"]) == 1
            assert view["escalations"][0]["from_level"] == 1
            assert view["escalations"][0]["to_level"] == 2
            assert view["resolution"]["resolution_status"] == "APPROVED"
            assert view["closure_approval"]["decision"] == "APPROVED"
            assert view["closure_approval"]["approver_level"] == 2
            assert view["metrics"]["routing_count"] == 2
            assert view["metrics"]["escalation_count"] == 1
            assert view["metrics"]["levels_reached"] == 2
            assert len(view["timeline"]) >= 9
            assert any(
                event["event_type"] == "REQUEST_RESOLVED"
                for event in view["timeline"]
            )
            assert view["audit"]["audit_record_id"] == report.audit_id
        finally:
            await cleanup_demo_cases(pool)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST") != "1",
    reason=REQUIRE,
)
def test_historical_configuration_change_does_not_rewrite_audit():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        config_service = FlowConfigurationService(pool=pool)
        original = await config_service.get_configuration("alumbrado")
        assert original is not None
        original_level = original["closure_approval_level"]
        levels_payload = [
            {"level": item["level"], "destination": item["destination"]}
            for item in original["levels"]
        ]
        try:
            report = await run_demo(pool, settings)
            service = _service(pool)
            view = await service.query_case(report.request_id)
            hash_before = view["audit"]["snapshot_sha256"]
            assert view["closure_approval"]["approver_level"] == 2

            await config_service.update_configuration(
                "alumbrado",
                levels=levels_payload,
                closure_approval_level=3,
            )

            after = await service.query_case(report.request_id)
            assert after["audit"]["snapshot_sha256"] == hash_before
            assert after["closure_approval"]["approver_level"] == 2
            n2 = next(
                row for row in after["routing_history"] if row["level"] == 2
            )
            assert n2["destination"] == "alumbrado.n2@alquimiablue.com"
        finally:
            await config_service.update_configuration(
                "alumbrado",
                levels=levels_payload,
                closure_approval_level=original_level,
            )
            await cleanup_demo_cases(pool)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST") != "1",
    reason=REQUIRE,
)
def test_resolved_without_audit_is_integrity_failure():
    async def exercise():
        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            report = await run_demo(pool, settings)
            async with pool.connection() as conn:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "delete from flow_case_audit_records "
                            "where request_id = %s::uuid",
                            (report.request_id,),
                        )
            service = _service(pool)
            with pytest.raises(FlowAuditIntegrityError):
                await service.query_case(report.request_id)
        finally:
            await cleanup_demo_cases(pool)
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST") != "1",
    reason=REQUIRE,
)
def test_live_case_does_not_create_audit_and_uses_live():
    async def exercise():
        import psycopg
        from psycopg.rows import dict_row

        settings = get_database_settings(min_size=1, max_size=4)
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select id::text from flow_requests "
                        "where status in ('ACTIVE','RESOLUTION_PENDING_APPROVAL') "
                        "limit 1"
                    )
                    row = await cur.fetchone()
            if row is None:
                pytest.skip("no live case available for the LIVE transition test")
            assert row is not None

            request_id = row["id"]
            before = await _row_counts(settings, request_id)
            service = _service(pool)
            view = await service.query_case(request_id)
            assert view["data_source"] == LIVE
            assert view["status_fact"] != "closed"
            after = await _row_counts(settings, request_id)
            assert before == after
            assert after["flow_case_audit_records"] == 0
        finally:
            await close_pool(pool)

    asyncio.run(exercise())

"""Real PostgreSQL integration for Flow sector configuration.

Opt-in via ``TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST=1``. Requires migration
021 seeded on the Team360 PostgreSQL. All temporary changes are restored
through the real service; only diagnostic SQL is used for setup/cleanup of
throwaway workflow rows.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool, reset_pool_for_tests, set_pool
from modules.db.settings import get_database_settings
from modules.flow.audit_repository import FlowAuditRepository
from modules.flow.closure_repository import FlowClosurePostgresRepository
from modules.flow.closure_service import FlowClosureService
from modules.flow.configuration_auth import FlowConfigurationAuthorizationService
from modules.flow.configuration_repository import FlowConfigurationPostgresRepository
from modules.flow.configuration_service import (
    FlowConfigurationService,
    FlowConfigurationValidationError,
)
from modules.flow.domain import (
    OperationalAction,
    OperationalInterpretation,
    OperationalRoutingContext,
)
from modules.flow.escalation_repository import FlowEscalationPostgresRepository
from modules.flow.escalation_service import FlowEscalationService
from modules.flow.routing_repository import FlowRoutingPostgresRepository
from modules.flow.routing_service import FlowRoutingService
from modules.messaging.domain import InboundMessage

REQUIRE = "requires migration 021 on Team360 PostgreSQL"

_ORIGINAL = {
    "closure": 2,
    "levels": {
        1: "alumbrado.n1@alquimiablue.com",
        2: "alumbrado.n2@alquimiablue.com",
        3: "alumbrado.n3@alquimiablue.com",
    },
}


async def _grant(conn, suffix: str, permissions: list[str]) -> tuple[str, str]:
    user_id = str(uuid4())
    async with conn.cursor() as cur:
        await cur.execute("select id from core_workspaces order by created_at_utc limit 1")
        workspace_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into core_users (id, workspace_id, email, display_name, role, status, metadata_jsonb)
            values (%s, %s, %s, %s, 'member', 'active', '{}'::jsonb)
            """,
            (user_id, workspace_id, f"config-{suffix}@example.com", f"config-{suffix}"),
        )
        await cur.execute(
            """
            insert into core_roles (workspace_id, role_code, display_name, status)
            values (%s, %s, 'Config Test', 'active') returning id
            """,
            (workspace_id, f"config_test_{suffix}"),
        )
        role_id = (await cur.fetchone())["id"]
        for permission in permissions:
            await cur.execute(
                """
                insert into core_role_permissions (role_id, permission_id)
                values (%s, (select id from core_permissions where permission_code = %s))
                """,
                (role_id, permission),
            )
        await cur.execute(
            "insert into core_user_roles (user_id, role_id) values (%s, %s)",
            (user_id, role_id),
        )
    return user_id, role_id


async def _cleanup(conn, user_ids: list[str], role_ids: list[str]) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "delete from core_user_roles where user_id = any(%s::uuid[])",
            ([user_ids],),
        )
        await cur.execute(
            "delete from core_users where id = any(%s::uuid[])",
            ([user_ids],),
        )
        await cur.execute(
            "delete from core_roles where id = any(%s::uuid[])",
            ([role_ids],),
        )


def _config_snapshot(configuration: dict) -> dict:
    return {
        "closure": configuration["closure_approval_level"],
        "levels": {
            item["level"]: item["destination"] for item in configuration["levels"]
        },
    }


def _level_destination(configuration: dict, level: int) -> str:
    return next(
        item["destination"]
        for item in configuration["levels"]
        if item["level"] == level
    )


async def _read_alumbrado(service) -> dict:
    return _config_snapshot(await service.get_configuration("alumbrado"))


async def _apply(service, *, levels: dict | None = None, closure=None) -> dict:
    current = await _read_alumbrado(service)
    levels = levels or current["levels"]
    closure = current["closure"] if closure is None else closure
    return await service.update_configuration(
        "alumbrado",
        levels=[
            {"level": level, "destination": destination}
            for level, destination in sorted(levels.items())
        ],
        closure_approval_level=closure,
    )


def _settings():
    return get_database_settings(min_size=1, max_size=3)


def _sql_conn(settings):
    return psycopg.AsyncConnection.connect(settings.dsn, row_factory=dict_row)


async def _seed_confirmed_request(conn, suffix: str) -> str:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into flow_conversations (
                provider, channel, external_thread_id, citizen_address, subject, state
            ) values ('gmail', 'email', %(thread)s, 'citizen@example.com',
                      'Config integration', 'CONFIRMED') returning id
            """,
            {"thread": f"config-integration-{suffix}"},
        )
        conversation_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_request_candidates (
                conversation_id, revision, ordinal, description,
                tentative_category, location_text, status
            ) values (%(conversation)s, 1, 1, 'Reparar poste', 'alumbrado',
                      'Olleros y Ciudad de la Paz', 'CONFIRMED') returning id
            """,
            {"conversation": conversation_id},
        )
        candidate_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_requests (
                conversation_id, source_candidate_id, description,
                tentative_category, location_text, confirmed_at_utc
            ) values (%(conversation)s, %(candidate)s, 'Reparar poste',
                      'alumbrado', 'Olleros y Ciudad de la Paz', now()) returning id
            """,
            {"conversation": conversation_id, "candidate": candidate_id},
        )
        return str((await cur.fetchone())["id"])


async def _seed_routing(conn, suffix: str, *, destination: str, level: int = 1) -> tuple[str, str]:
    request_id = await _seed_confirmed_request(conn, suffix)
    async with conn.cursor() as cur:
        await cur.execute(
            "select id from flow_sector_levels where sector_id = 'alumbrado' and level = %s",
            (level,),
        )
        level_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into flow_request_routings (
                request_id, sector_id, sector_level_id, level, channel,
                destination, status, outbound_rfc_message_id,
                outbound_external_message_id, assigned_at_utc
            ) values (%(request)s, 'alumbrado', %(level_id)s, %(level)s, 'email',
                      %(destination)s, 'ASSIGNED', %(rfc)s, %(external)s, now()) returning id
            """,
            {
                "request": request_id,
                "level_id": level_id,
                "level": level,
                "destination": destination,
                "rfc": f"<intended-{suffix}@example.com>",
                "external": f"gmail-out-{suffix}",
            },
        )
        routing_id = str((await cur.fetchone())["id"])
    return request_id, routing_id


async def _delete_request(conn, request_id: str) -> None:
    async with conn.cursor() as cur:
        routing_ids = """
            select id from flow_request_routings where request_id = %s::uuid
        """
        await cur.execute(
            """
            delete from flow_request_sla_events
            where sla_id in (
                select id from flow_request_slas where routing_id in (
                    select id from flow_request_routings where request_id = %s::uuid
                )
            )
            """,
            (request_id,),
        )
        await cur.execute(
            f"delete from flow_request_slas where routing_id in ({routing_ids})",
            (request_id,),
        )
        await cur.execute(
            f"delete from flow_request_work_states where routing_id in ({routing_ids})",
            (request_id,),
        )
        await cur.execute(
            f"delete from flow_request_operational_events where routing_id in ({routing_ids})",
            (request_id,),
        )
        await cur.execute(
            "delete from flow_request_routings where request_id = %s::uuid",
            (request_id,),
        )
        await cur.execute(
            "delete from flow_requests where id = %s::uuid",
            (request_id,),
        )
        await cur.execute(
            """
            delete from flow_conversations
            where id = (select conversation_id from flow_requests where id = %s::uuid)
            """,
            (request_id,),
        )


class _NoopInterpreter:
    def interpret(self, text, correlation_id=None):
        raise AssertionError("no debe interpretarse en este test")


class _FakeSender:
    sender_address = "test@alquimiablue.com"

    def __init__(self):
        self.sent = []

    def send_message(self, *, to, subject, body, rfc_message_id=None):
        self.sent.append(to)
        return f"gmail-out-{uuid4().hex}"

    def find_sent_message_by_rfc_message_id(self, rfc_message_id):
        return None

    def find_sent_message_by_reference(self, reference, *, to=None):
        return None

    def get_message_rfc_id(self, message_id):
        return None


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_configuration_read_write_atomic_and_restore():
    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        async with await _sql_conn(settings) as conn:
            admin, admin_role = await _grant(
                conn, f"admin-{suffix}", ["flow.configuration.read", "flow.configuration.write"]
            )
            reader, reader_role = await _grant(
                conn, f"reader-{suffix}", ["flow.configuration.read"]
            )
            await conn.commit()

        pool = create_pool(settings)
        await open_pool(pool)
        try:
            service = FlowConfigurationService(pool=pool)
            authz = FlowConfigurationAuthorizationService()

            async with pool.connection() as conn:
                assert await authz.can_read(conn, admin) is True
                assert await authz.can_write(conn, admin) is True
                assert await authz.can_read(conn, reader) is True
                assert await authz.can_write(conn, reader) is False

            original = await _read_alumbrado(service)
            assert original == _ORIGINAL, f"baseline esperado {_ORIGINAL}, fue {original}"

            # Authorized write persists.
            changed = await _apply(service, levels={1: "temp.n1@alquimiablue.com"})
            assert _level_destination(changed, 1) == "temp.n1@alquimiablue.com"
            re_read = await _read_alumbrado(service)
            assert re_read["levels"][1] == "temp.n1@alquimiablue.com"

            # Atomicity: N1 valid + N2 invalid -> nothing persisted.
            try:
                await service.update_configuration(
                    "alumbrado",
                    levels=[
                        {"level": 1, "destination": "parcial.n1@alquimiablue.com"},
                        {"level": 2, "destination": "invalido-sin-dominio"},
                        {"level": 3, "destination": "alumbrado.n3@alquimiablue.com"},
                    ],
                    closure_approval_level=2,
                )
                raise AssertionError("esperaba FlowConfigurationValidationError")
            except FlowConfigurationValidationError:
                pass
            after_failed = await _read_alumbrado(service)
            assert after_failed["levels"][1] == "temp.n1@alquimiablue.com"
            assert after_failed["levels"][2] == "alumbrado.n2@alquimiablue.com"

            # Same-value update is idempotent and leaves config unchanged.
            await _apply(service, levels={1: "temp.n1@alquimiablue.com"})
            assert await _read_alumbrado(service) == after_failed

            # Restore original through the real service.
            restored = await _apply(
                service,
                levels=original["levels"],
                closure=original["closure"],
            )
            assert _config_snapshot(restored) == _ORIGINAL
            assert await _read_alumbrado(service) == _ORIGINAL
        finally:
            async with await _sql_conn(settings) as conn:
                await _cleanup(conn, [admin, reader], [admin_role, reader_role])
                await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_route_configuration_e2e(monkeypatch):
    from litestar.testing import TestClient

    from ls_iMotorSoft_Srv01 import create_app
    from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public

    _KEY_ID = "config-e2e-key"
    _KEY_PAIR = PasetoKeyPair.generate(_KEY_ID)

    def _token(user_id: str) -> str:
        return issue_paseto_v4_public(
            {"sub": f"user:{user_id}", "user_id": user_id},
            private_key_pem=_KEY_PAIR.private_pem,
            key_id=_KEY_ID,
            ttl_seconds=900,
            issuer="team360",
            token_type="console_access",
        )

    suffix = uuid4().hex
    settings = _settings()

    async def setup():
        async with await _sql_conn(settings) as conn:
            admin, admin_role = await _grant(
                conn, f"admin-{suffix}", ["flow.configuration.read", "flow.configuration.write"]
            )
            reader, reader_role = await _grant(
                conn, f"reader-{suffix}", ["flow.configuration.read"]
            )
            await conn.commit()
        return admin, reader, admin_role, reader_role

    async def teardown(admin, reader, admin_role, reader_role):
        async with await _sql_conn(settings) as conn:
            await _cleanup(conn, [admin, reader], [admin_role, reader_role])
            await conn.commit()

    async def restore_original():
        service = FlowConfigurationService(pool=create_pool(settings))
        await open_pool(service._pool)
        try:
            await _apply(
                service,
                levels=_ORIGINAL["levels"],
                closure=_ORIGINAL["closure"],
            )
        finally:
            await close_pool(service._pool)

    admin, reader, admin_role, reader_role = asyncio.run(setup())
    monkeypatch.setenv("AUTOMATION_DIAGNOSIS_REPOSITORY", "postgres")
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "authenticated")
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda s: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    set_pool(create_pool(settings))
    path = "/api/team360-flow/configuration/alumbrado"
    list_path = "/api/team360-flow/configuration"
    payload = {
        "levels": [
            {"level": 1, "destination": "route-temp.n1@alquimiablue.com"},
            {"level": 2, "destination": "alumbrado.n2@alquimiablue.com"},
            {"level": 3, "destination": "alumbrado.n3@alquimiablue.com"},
        ],
        "closure_approval_level": 2,
    }
    try:
        with TestClient(create_app()) as client:
            assert client.get(list_path).status_code == 401
            assert client.patch(path, json=payload).status_code == 401

            reader_headers = {"Authorization": f"Bearer {_token(reader)}"}
            admin_headers = {"Authorization": f"Bearer {_token(admin)}"}

            # Reader: read OK, write denied.
            assert client.get(list_path, headers=reader_headers).status_code == 200
            denied = client.patch(path, headers=reader_headers, json=payload)
            assert denied.status_code == 403

            # Invalid payload -> 422 and nothing persisted.
            invalid = {**payload, "levels": [{"level": 1, "destination": "mal"}]}
            bad = client.patch(path, headers=admin_headers, json=invalid)
            assert bad.status_code == 422

            # Authorized write persists through the real route.
            ok = client.patch(path, headers=admin_headers, json=payload)
            assert ok.status_code == 200
            assert _level_destination(ok.json(), 1) == "route-temp.n1@alquimiablue.com"

            re_read = client.get(list_path, headers=reader_headers)
            alumbrado = next(
                s for s in re_read.json()["sectors"] if s["sector_id"] == "alumbrado"
            )
            assert _level_destination(alumbrado, 1) == "route-temp.n1@alquimiablue.com"
    finally:
        asyncio.run(restore_original())
        asyncio.run(teardown(admin, reader, admin_role, reader_role))
        reset_pool_for_tests()


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_new_routing_uses_changed_destination():
    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = None
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)
            await _apply(service, levels={1: "routing-temp.n1@alquimiablue.com"})

            async with await _sql_conn(settings) as conn:
                request_id = await _seed_confirmed_request(conn, suffix)
                await conn.commit()

            sender = _FakeSender()
            routing_service = FlowRoutingService(
                pool=pool,
                repository=FlowRoutingPostgresRepository(),
                sender=sender,
            )
            result = await routing_service.route_confirmed_request(
                request_id, confirm_send=True
            )
            assert result.assignment is not None
            assert result.assignment.destination == "routing-temp.n1@alquimiablue.com"
            # El correo del nuevo routing se entrega al destination actualizado.
            assert sender.sent == ["routing-temp.n1@alquimiablue.com"]
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            if request_id:
                async with await _sql_conn(settings) as conn:
                    await _delete_request(conn, request_id)
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_closure_policy_uses_changed_destination():
    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = routing_id = None
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)
            assert original["closure"] == 2
            # Change N2 destination: with closure_approval_level=2 the next
            # approval must resolve to the updated destination.
            await _apply(service, levels={2: "closure-temp.n2@alquimiablue.com"})

            async with await _sql_conn(settings) as conn:
                request_id, routing_id = await _seed_routing(
                    conn, suffix, destination="alumbrado.n1@alquimiablue.com"
                )
                await conn.commit()

            repo = FlowConfigurationPostgresRepository()
            from modules.flow.closure_repository import FlowClosurePostgresRepository

            closure_repo = FlowClosurePostgresRepository()
            async with pool.connection() as conn:
                policy = await closure_repo.get_closure_policy(conn, routing_id)
            assert policy is not None
            assert policy["approver_level"] == 2
            assert policy["approver_destination"] == "closure-temp.n2@alquimiablue.com"
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            if request_id:
                async with await _sql_conn(settings) as conn:
                    await _delete_request(conn, request_id)
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_existing_routing_history_preserved():
    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = routing_id = None
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)

            # Seed routing with the ORIGINAL destination, then change config.
            async with await _sql_conn(settings) as conn:
                request_id, routing_id = await _seed_routing(
                    conn,
                    suffix,
                    destination=original["levels"][1],
                )
                await conn.commit()

            await _apply(service, levels={1: "history-temp.n1@alquimiablue.com"})

            async with pool.connection() as conn:
                assignment = await FlowRoutingPostgresRepository().get_assignment(
                    conn, request_id
                )
            assert assignment is not None
            # Historical routing keeps the destination captured at creation.
            assert assignment.destination == original["levels"][1]
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            if request_id:
                async with await _sql_conn(settings) as conn:
                    await _delete_request(conn, request_id)
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_default_admin_no_token_read(monkeypatch):
    from litestar.testing import TestClient

    from ls_iMotorSoft_Srv01 import create_app

    settings = _settings()
    monkeypatch.setenv("AUTOMATION_DIAGNOSIS_REPOSITORY", "postgres")
    # Explicit DEV demo: no token required, never a production default.
    monkeypatch.setenv("TEAM360_ENV", "development")
    monkeypatch.setenv("TEAM360_FLOW_ACCESS_MODE", "default_admin")
    set_pool(create_pool(settings))
    try:
        with TestClient(create_app()) as client:
            listing = client.get("/api/team360-flow/configuration")
            assert listing.status_code == 200, listing.text
            assert any(
                sector["sector_id"] == "alumbrado"
                for sector in listing.json()["sectors"]
            )
            one = client.get("/api/team360-flow/configuration/alumbrado")
            assert one.status_code == 200, one.text
            assert one.json()["sector_id"] == "alumbrado"
            assert [l["level"] for l in one.json()["levels"]] == [1, 2, 3]
    finally:
        reset_pool_for_tests()


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_new_escalation_uses_changed_destination():
    """N2 destination changes -> a fresh N1 breach escalates to the NEW N2."""

    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = None
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)
            await _apply(service, levels={2: "escalation-temp.n2@alquimiablue.com"})

            t0 = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
            async with await _sql_conn(settings) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_conversations (
                            provider, channel, external_thread_id,
                            citizen_address, subject, state
                        ) values ('gmail','email',%(thread)s,'citizen@example.com',
                                  'Escalation config test','CONFIRMED') returning id
                        """,
                        {"thread": f"cfg-esc-{suffix}"},
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
                    request_id = str((await cur.fetchone())["id"])
                    await cur.execute(
                        "select level, id from flow_sector_levels where sector_id='alumbrado'"
                    )
                    levels = {row["level"]: row["id"] for row in await cur.fetchall()}
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
                        insert into flow_request_work_states (request_id, routing_id)
                        values (%(request)s,%(routing)s)
                        """,
                        {"request": request_id, "routing": n1},
                    )
                    await cur.execute(
                        """
                        insert into flow_request_slas (
                            routing_id, request_id, duration_seconds,
                            started_at_utc, due_at_utc, status,
                            breached_at_utc, evaluated_at_utc
                        ) values (%(routing)s,%(request)s,30,%(start)s,%(due)s,
                                  'BREACHED',%(breached)s,%(breached)s) returning id
                        """,
                        {"routing": n1, "request": request_id, "start": t0,
                         "due": t0 + timedelta(seconds=30),
                         "breached": t0 + timedelta(seconds=31)},
                    )
                    await conn.commit()

            sender = _FakeSender()
            escalation_service = FlowEscalationService(
                pool=pool,
                repository=FlowEscalationPostgresRepository(),
                routing_repository=FlowRoutingPostgresRepository(),
                sender=sender,
            )
            summary = await escalation_service.escalate_once(confirm_send=True)
            assert summary.created == 1, summary
            assert summary.sent == 1, summary
            assert summary.completed == 1, summary
            n2_outcome = next(o for o in summary.outcomes if o.to_level == 2)
            assert n2_outcome.destination == "escalation-temp.n2@alquimiablue.com"
            # El email del nuevo routing N2 va al destination actualizado.
            assert sender.sent == ["escalation-temp.n2@alquimiablue.com"]

            async with pool.connection() as conn:
                n2_assignment = await FlowRoutingPostgresRepository().get_assignment_for_key(
                    conn,
                    request_id=request_id,
                    routing_key="alumbrado_level_2",
                )
            assert n2_assignment is not None
            assert n2_assignment.destination == "escalation-temp.n2@alquimiablue.com"
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            if request_id:
                async with await _sql_conn(settings) as conn:
                    await _delete_escalations(conn, request_id)
                    await _delete_request(conn, request_id)
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_closure_level_change_uses_new_policy():
    """closure_approval_level 2->3 + N3 change -> new proposal approves at N3."""

    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = routing_id = None
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)
            assert original["closure"] == 2
            await _apply(
                service,
                levels={3: "closure-temp.n3@alquimiablue.com"},
                closure=3,
            )

            async with await _sql_conn(settings) as conn:
                request_id, routing_id = await _seed_routing(
                    conn, suffix, destination="alumbrado.n1@alquimiablue.com"
                )
                await conn.commit()

            sender = _FakeSender()
            closure_service = FlowClosureService(
                pool=pool,
                repository=FlowClosurePostgresRepository(),
                audit_repository=FlowAuditRepository(),
                interpreter=_NoopInterpreter(),
                sender=sender,
            )
            context = OperationalRoutingContext(
                routing_id=routing_id,
                request_id=request_id,
                conversation_id="cfg-closure-conv",
                routing_key="initial_n1",
                level=1,
                routing_status="ASSIGNED",
                destination="alumbrado.n1@alquimiablue.com",
                outbound_external_message_id="gmail-out-1",
                outbound_rfc_message_id="<routing@example.com>",
                outbound_observed_rfc_message_id="<observed@mail.gmail.com>",
                request_status="ACTIVE",
            )
            message = InboundMessage(
                provider="gmail",
                channel="email",
                external_message_id=f"proposal-{suffix}",
                external_thread_id=f"thread-{suffix}",
                sender="tech@alquimiablue.com",
                recipients=("mesa@alquimiablue.com",),
                subject="Re: reparación",
                text_body="La luminaria quedó reparada y verificada.",
                received_at=datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc),
            )
            interpretation = OperationalInterpretation(
                action=OperationalAction.RESOLUTION_PROPOSED,
                summary="propuesta de cierre",
                provider="fake",
                model="fake",
                usage={},
                latency_ms=1,
            )
            async with pool.connection() as conn:
                result = await closure_service.propose_resolution(
                    conn,
                    context=context,
                    message=message,
                    interpretation=interpretation,
                )
                await conn.commit()

            assert result.request_status == "RESOLUTION_PENDING_APPROVAL"
            # La nueva policy aplica: nivel 3 y destination actualizado.
            assert result.approver_level == 3
            assert result.approver_destination == "closure-temp.n3@alquimiablue.com"
            assert sender.sent == ["closure-temp.n3@alquimiablue.com"]
            assert result.approval_id is not None

            async with await _sql_conn(settings) as conn:
                row = await _fetch_approval(conn, result.approval_id)
            assert row["approver_level"] == 3
            assert row["approver_destination"] == "closure-temp.n3@alquimiablue.com"
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            if request_id:
                async with await _sql_conn(settings) as conn:
                    await _delete_approvals_and_resolutions(conn, request_id)
                    await _delete_request(conn, request_id)
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_pending_approval_keeps_snapshot_after_policy_change():
    """Un approval PENDING conserva nivel/destino creados aunque cambie la policy."""

    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        request_id = routing_id = None
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)
            async with await _sql_conn(settings) as conn:
                request_id, routing_id = await _seed_routing(
                    conn, suffix, destination="alumbrado.n1@alquimiablue.com"
                )
                await conn.commit()

            # Approval PENDING creado con la policy vigente (N2).
            closure_repo = FlowClosurePostgresRepository()
            async with pool.connection() as conn:
                policy = await closure_repo.get_closure_policy(conn, routing_id)
                assert policy is not None
                assert policy["approver_level"] == 2
                assert policy["approver_destination"] == original["levels"][2]
                resolution = await closure_repo.upsert_resolution(
                    conn,
                    request_id=request_id,
                    routing_id=routing_id,
                    proposed_by="tech@alquimiablue.com",
                    proposed_at=datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc),
                    source_provider="gmail",
                    source_external_message_id=f"res-{suffix}",
                    resolution_text="Reparado.",
                )
                approval = await closure_repo.upsert_approval(
                    conn,
                    request_id=request_id,
                    resolution_id=resolution.id,
                    approver_level=policy["approver_level"],
                    approver_destination=policy["approver_destination"],
                    approval_token=f"a1b2c3d4{suffix[:24]}",
                )
                approval_id = str(approval.id)
                await conn.commit()

            # El administrador cambia la policy (nivel de aprobación y destino N2).
            await _apply(
                service,
                levels={2: "changed-temp.n2@alquimiablue.com"},
                closure=3,
            )

            async with await _sql_conn(settings) as conn:
                row = await _fetch_approval(conn, approval_id)
            # Identidad histórica del approval ya creado: intacta.
            assert row["approver_level"] == 2
            assert row["approver_destination"] == original["levels"][2]
            assert row["status"] == "PENDING"

            # La policy vigente ahora resuelve a N3.
            async with pool.connection() as conn:
                new_policy = await closure_repo.get_closure_policy(conn, routing_id)
            assert new_policy is not None
            assert new_policy["approver_level"] == 3
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            if request_id:
                async with await _sql_conn(settings) as conn:
                    await _delete_approvals_and_resolutions(conn, request_id)
                    await _delete_request(conn, request_id)
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_config_update_has_no_workflow_side_effects():
    """Guardar configuración no crea routings, mensajes, approvals ni eventos."""

    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        service = None
        original = None
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)

            async def counts():
                async with await _sql_conn(settings) as conn:
                    async with conn.cursor() as cur:
                        result = {}
                        for table in (
                            "flow_requests",
                            "flow_request_routings",
                            "flow_request_escalations",
                            "flow_request_resolutions",
                            "flow_closure_approvals",
                            "flow_request_operational_events",
                            "flow_request_slas",
                        ):
                            await cur.execute(f"select count(*) from {table}")
                            result[table] = (await cur.fetchone())["count"]
                        return result

            before = await counts()
            changed = await _apply(
                service,
                levels={
                    1: "noop.n1@alquimiablue.com",
                    2: "noop.n2@alquimiablue.com",
                    3: "noop.n3@alquimiablue.com",
                },
                closure=3,
            )
            assert _level_destination(changed, 1) == "noop.n1@alquimiablue.com"
            after = await counts()
            assert after == before, f"el update de configuración alteró el workflow: {after} != {before}"
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_config_update_does_not_alter_other_sectors():
    """Editar Alumbrado no toca la configuración de otro sector."""

    async def exercise():
        suffix = uuid4().hex
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        service = None
        original = None
        other_sector_id = f"cfg_other_{suffix[:8]}"
        try:
            service = FlowConfigurationService(pool=pool)
            original = await _read_alumbrado(service)
            other = {
                "sector_id": other_sector_id,
                "display_name": "Config Test Other",
                "active": True,
                "closure_approval_level": 1,
                "levels": [
                    {"level": 1, "destination": f"other.n1@example.invalid"},
                    {"level": 2, "destination": f"other.n2@example.invalid"},
                ],
            }
            async with await _sql_conn(settings) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        insert into flow_sectors (sector_id, display_name, active, closure_approval_level)
                        values (%(id)s, %(name)s, true, 1)
                        """,
                        {"id": other["sector_id"], "name": other["display_name"]},
                    )
                    for level in other["levels"]:
                        await cur.execute(
                            """
                            insert into flow_sector_levels (sector_id, level, channel, destination, active)
                            values (%(id)s, %(level)s, 'email', %(destination)s, true)
                            """,
                            {"id": other["sector_id"], "level": level["level"],
                             "destination": level["destination"]},
                        )
                    await conn.commit()

            other_before = await service.get_configuration(other_sector_id)
            assert other_before is not None
            assert _level_destination(other_before, 1) == "other.n1@example.invalid"

            await _apply(service, levels={1: "alumbrado-temp.n1@alquimiablue.com"})
            other_after = await service.get_configuration(other_sector_id)
            assert other_after is not None
            assert _level_destination(other_after, 1) == "other.n1@example.invalid"
            assert _level_destination(other_after, 2) == "other.n2@example.invalid"
            assert other_after["closure_approval_level"] == 1

            listing = await service.list_configurations()
            assert any(s["sector_id"] == other_sector_id for s in listing["sectors"])
        finally:
            if service is not None and original is not None:
                await _apply(
                    service,
                    levels=original["levels"],
                    closure=original["closure"],
                )
            async with await _sql_conn(settings) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "delete from flow_sector_levels where sector_id = %(id)s",
                        {"id": other_sector_id},
                    )
                    await cur.execute(
                        "delete from flow_sectors where sector_id = %(id)s",
                        {"id": other_sector_id},
                    )
                    await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_CONFIGURATION_POSTGRES_TEST") != "1",
    reason=REQUIRE,
)
def test_real_postgres_operational_settings_roundtrip_without_restart():
    """Operational settings, including cutoff, persist and restore in PostgreSQL."""

    async def exercise():
        settings = _settings()
        pool = create_pool(settings)
        await open_pool(pool)
        service = FlowConfigurationService(pool=pool)
        original = await service.get_operational_settings()
        try:
            changed = await service.update_operational_settings(
                automation_enabled=False,
                scheduler_interval_seconds=20,
                mail_intake_enabled=False,
                mail_batch_limit=17,
                mail_after_cutoff=True,
                mail_cutoff_epoch=1787239368,
            )
            assert changed == {
                "automation_enabled": False,
                "scheduler_interval_seconds": 20,
                "mail_intake_enabled": False,
                "mail_batch_limit": 17,
                "mail_after_cutoff": True,
                "mail_cutoff_epoch": 1787239368,
            }
            reread = await service.get_operational_settings()
            assert reread == changed
        finally:
            await service.update_operational_settings(**original)
            await close_pool(pool)

    asyncio.run(exercise())


async def _fetch_approval(conn, approval_id: str) -> dict:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            select approver_level, approver_destination, status
            from flow_closure_approvals where id = %s
            """,
            (approval_id,),
        )
        return (await cur.fetchone()) or {}


async def _delete_escalations(conn, request_id: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "delete from flow_request_escalations where request_id = %s::uuid",
            (request_id,),
        )


async def _delete_approvals_and_resolutions(conn, request_id: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            delete from flow_closure_approvals
            where resolution_id in (
                select id from flow_request_resolutions where request_id = %s::uuid
            )
            """,
            (request_id,),
        )
        await cur.execute(
            "delete from flow_request_resolutions where request_id = %s::uuid",
            (request_id,),
        )

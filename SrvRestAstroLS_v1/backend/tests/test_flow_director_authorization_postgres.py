import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.audit_repository import FlowAuditRepository
from modules.flow.closure_repository import FlowClosurePostgresRepository
from modules.flow.executive_auth import FlowExecutiveAuthorizationService
from modules.flow.executive_query import AUDIT_SNAPSHOT, LIVE
from modules.flow.executive_service import FlowExecutiveAuditService


async def _grant_director(conn, suffix: str) -> tuple[str, str, str]:
    user_a = str(uuid4())
    user_b = str(uuid4())
    async with conn.cursor() as cur:
        await cur.execute("select id from core_workspaces order by created_at_utc limit 1")
        workspace_id = (await cur.fetchone())["id"]
        for user_id, email in (
            (user_a, f"director-a-{suffix}@example.com"),
            (user_b, f"director-b-{suffix}@example.com"),
        ):
            await cur.execute(
                """
                insert into core_users (id, workspace_id, email, display_name, role, status, metadata_jsonb)
                values (%s, %s, %s, %s, 'member', 'active', '{}'::jsonb)
                """,
                (user_id, workspace_id, email, email),
            )
        await cur.execute(
            """
            insert into core_roles (workspace_id, role_code, display_name, status)
            values (%s, %s, 'Director Test', 'active') returning id
            """,
            (workspace_id, f"director_test_{suffix}"),
        )
        role_id = (await cur.fetchone())["id"]
        await cur.execute(
            """
            insert into core_role_permissions (role_id, permission_id)
            values (%s, (select id from core_permissions where permission_code = 'flow.executive.read'))
            """,
            (role_id,),
        )
        await cur.execute(
            "insert into core_user_roles (user_id, role_id) values (%s, %s)",
            (user_a, role_id),
        )
    return user_a, user_b, role_id


async def _revoke_director(conn, user_a: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute("delete from core_user_roles where user_id = %s::uuid", (user_a,))


async def _cleanup(conn, user_a: str, user_b: str, role_id: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "delete from core_user_roles where user_id = any(%s::uuid[])", ([user_a, user_b],)
        )
        await cur.execute("delete from core_users where id = any(%s::uuid[])", ([user_a, user_b],))
        await cur.execute("delete from core_roles where id = %s::uuid", (role_id,))


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_DIRECTOR_POSTGRES_TEST") != "1",
    reason="requires migration 020 on Team360 PostgreSQL",
)
def test_real_postgres_director_grant_then_revoke():
    async def exercise():
        suffix = uuid4().hex
        settings = get_database_settings(min_size=1, max_size=3)

        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            user_a, user_b, role_id = await _grant_director(conn, suffix)
            await conn.commit()

        pool = create_pool(settings)
        await open_pool(pool)
        try:
            authz = FlowExecutiveAuthorizationService()
            async with pool.connection() as conn:
                assert await authz.has_flow_executive_read(conn, user_a) is True
                assert await authz.has_flow_executive_read(conn, user_b) is False

            executive = FlowExecutiveAuditService(
                pool=pool,
                closure_repository=FlowClosurePostgresRepository(),
                audit_repository=FlowAuditRepository(),
            )
            # Authorized access to a RESOLVED case -> AUDIT_SNAPSHOT.
            resolved = await executive.query_case(
                "814f38ce-9509-4cd6-a355-fa176e63edb2"
            )
            assert resolved["data_source"] == AUDIT_SNAPSHOT
            assert resolved["status_fact"] == "closed"
            assert resolved["audit"]["snapshot_sha256"]
            # Authorized access to an open case -> LIVE.
            live = await executive.query_case("c92d739c-4e6e-4b84-a65d-99a6a90ef712")
            assert live["data_source"] == LIVE
            assert live["status_fact"] == "open"

            # Revoke the grant -> same user denied, fail closed.
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                await _revoke_director(conn, user_a)
                await conn.commit()
            async with pool.connection() as conn:
                assert await authz.has_flow_executive_read(conn, user_a) is False

            # Read-only: repeated authorized queries do not mutate workflow.
            again = await executive.query_case("814f38ce-9509-4cd6-a355-fa176e63edb2")
            assert again["audit"]["snapshot_sha256"] == resolved["audit"]["snapshot_sha256"]
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select count(*) from flow_case_audit_records where request_id = '814f38ce-9509-4cd6-a355-fa176e63edb2'"
                    )
                    assert (await cur.fetchone())["count"] == 1
        finally:
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                await _cleanup(conn, user_a, user_b, role_id)
                await conn.commit()
            await close_pool(pool)

    asyncio.run(exercise())


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_DIRECTOR_POSTGRES_TEST") != "1",
    reason="requires migration 020 on Team360 PostgreSQL",
)
def test_real_route_director_e2e(monkeypatch):
    from litestar.testing import TestClient

    from ls_iMotorSoft_Srv01 import create_app
    from modules.db.pool import reset_pool_for_tests, set_pool
    from modules.security.paseto_tokens import PasetoKeyPair, issue_paseto_v4_public

    _KEY_ID = "director-e2e-key"
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
    settings = get_database_settings(min_size=1, max_size=1)

    async def setup() -> tuple[str, str, str]:
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            user_a, user_b, role_id = await _grant_director(conn, suffix)
            await conn.commit()
        return user_a, user_b, role_id

    async def teardown(user_a, user_b, role_id) -> None:
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            await _cleanup(conn, user_a, user_b, role_id)
            await conn.commit()

    user_a, user_b, role_id = asyncio.run(setup())
    monkeypatch.setenv("AUTOMATION_DIAGNOSIS_REPOSITORY", "postgres")
    monkeypatch.setattr(
        "modules.flow.routes._resolve_public_keys",
        lambda s: {_KEY_ID: _KEY_PAIR.public_pem},
    )
    set_pool(create_pool(settings))
    path = "/api/team360-flow/executive/814f38ce-9509-4cd6-a355-fa176e63edb2"
    try:
        with TestClient(create_app()) as client:
            assert client.get(path).status_code == 401
            denied = client.get(path, headers={"Authorization": f"Bearer {_token(user_b)}"})
            assert denied.status_code == 403
            allowed = client.get(path, headers={"Authorization": f"Bearer {_token(user_a)}"})
            assert allowed.status_code == 200
            data = allowed.json()
            assert data["data_source"] == AUDIT_SNAPSHOT
            assert data["status_fact"] == "closed"
            assert data["audit"]["snapshot_sha256"]
    finally:
        asyncio.run(teardown(user_a, user_b, role_id))
        reset_pool_for_tests()

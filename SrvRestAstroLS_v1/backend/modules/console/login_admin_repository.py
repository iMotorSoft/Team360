"""Explicit DEV operator provisioning; never called by login/runtime."""
from pathlib import Path
from psycopg import sql
from psycopg.rows import dict_row

RUNTIME_ROLE = 'team360_business_semantics_dev_runtime'


class ConsoleLoginAdminRepository:
    async def prepare(self, conn, *, role_password):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute('SELECT rolname FROM pg_roles WHERE rolname=%s', (RUNTIME_ROLE,))
            if await cur.fetchone():
                raise PermissionError('runtime_role_exists_review_required')
            await cur.execute("SELECT to_regclass('public.console_password_credentials') AS existing")
            if (await cur.fetchone())['existing']:
                raise PermissionError('credential_schema_exists_review_required')
        migration = Path(__file__).resolve().parents[2] / 'db/migrations/030_team360_console_password_credentials.sql'
        await conn.execute(migration.read_text())
        role = sql.Identifier(RUNTIME_ROLE)
        await conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}').format(role,sql.Literal(role_password)))
        await conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(conn.info.dbname),role))
        await conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        tables = ['core_organizations','core_workspaces','core_users','core_organization_members','core_organization_member_roles','console_password_credentials']
        for table in tables:
            await conn.execute(sql.SQL('GRANT SELECT ON TABLE {} TO {}').format(sql.Identifier(table),role))
        await conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON TABLE console_login_attempts TO {}').format(role))
        await conn.execute(sql.SQL('GRANT INSERT ON TABLE core_events TO {}').format(role))
        # System identifier is non-secret; grant only this read-only control function.
        await conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION pg_control_system() TO {}').format(role))
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'business_concept%' ORDER BY tablename")
            for row in await cur.fetchall():
                await conn.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON TABLE {} TO {}').format(sql.Identifier(row['tablename']),role))

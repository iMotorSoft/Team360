"""Real resolver SQL against session-local tables; never edits operational rows."""
import asyncio
import os
from uuid import uuid4
import pytest
import psycopg
from psycopg.rows import dict_row
from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings


@pytest.mark.skipif(os.getenv('TEAM360_FULL_ACCESS_POSTGRES_TEST') != '1', reason='PG opt-in required')
def test_dynamic_scoped_full_access():
    async def run():
        async with await psycopg.AsyncConnection.connect(get_database_settings().dsn, row_factory=dict_row) as conn:
            definitions = {
                'core_users': 'id uuid,workspace_id uuid,status text',
                'core_workspaces': 'id uuid,organization_id uuid,status text',
                'core_organizations': 'id uuid,status text',
                'core_roles': 'id uuid,workspace_id uuid,status text',
                'core_user_roles': 'user_id uuid,role_id uuid',
                'core_role_permissions': 'role_id uuid,permission_id uuid',
                'core_permissions': 'id uuid,permission_code text',
                'core_user_profiles': 'user_id uuid,profile_id uuid',
                'core_permission_profiles': 'id uuid,workspace_id uuid,status text',
                'core_profile_permissions': 'profile_id uuid,permission_id uuid',
                'core_module_full_access_grants': 'id uuid,organization_id uuid,workspace_id uuid,module text,user_id uuid,revoked_at_utc timestamptz',
                'core_workspace_capabilities': 'workspace_id uuid,module text,capability_code text,permission_id uuid,enabled boolean',
            }
            for table, fields in definitions.items():
                await conn.execute(f'CREATE TEMP TABLE {table} ({fields}) ON COMMIT DROP')
            tenant, other_tenant, workspace, other_workspace, pilot, other_user, normal_role, grant = [str(uuid4()) for _ in range(8)]
            await conn.execute("INSERT INTO core_organizations VALUES (%s,'active'),(%s,'active')", (tenant,other_tenant))
            await conn.execute("INSERT INTO core_workspaces VALUES (%s,%s,'testing'),(%s,%s,'active')", (workspace,tenant,other_workspace,other_tenant))
            await conn.execute("INSERT INTO core_users VALUES (%s,%s,'active'),(%s,%s,'active')", (pilot,workspace,other_user,workspace))
            normal = str(uuid4())
            await conn.execute("INSERT INTO core_permissions VALUES (%s,'normal.read')", (normal,))
            await conn.execute("INSERT INTO core_roles VALUES (%s,%s,'active')", (normal_role,workspace))
            await conn.execute('INSERT INTO core_user_roles VALUES (%s,%s)', (pilot,normal_role))
            await conn.execute('INSERT INTO core_role_permissions VALUES (%s,%s)', (normal_role,normal))
            await conn.execute("INSERT INTO core_module_full_access_grants VALUES (%s,%s,%s,'telchi',%s,NULL)", (grant,tenant,workspace,pilot))
            resolver = PermissionConsoleRepository()
            async def effective(w=workspace,u=pilot):
                return set(await resolver.list_effective_permissions(conn,w,u))
            assert await effective() == {'normal.read'}
            # Newly registered enabled capability is effective WITHOUT touching grant.
            new, disabled, foreign_module, foreign_workspace = [str(uuid4()) for _ in range(4)]
            for ident, code, w, module, enabled in [
                (new,'telchi.future.read',workspace,'telchi',True),
                (disabled,'telchi.disabled.read',workspace,'telchi',False),
                (foreign_module,'flow.read',workspace,'flow',True),
                (foreign_workspace,'other.read',other_workspace,'telchi',True),
            ]:
                await conn.execute('INSERT INTO core_permissions VALUES (%s,%s)', (ident,code))
                await conn.execute('INSERT INTO core_workspace_capabilities VALUES (%s,%s,%s,%s,%s)', (w,module,code,ident,enabled))
            # Even a misregistered foreign permission cannot cross the module boundary.
            await conn.execute("INSERT INTO core_workspace_capabilities VALUES (%s,'telchi','misregistered',%s,true)", (workspace,foreign_module))
            assert await effective() == {'normal.read','telchi.future.read'}
            assert await effective(u=other_user) == set()
            assert await effective(w=other_workspace) == set()
            await conn.execute('UPDATE core_module_full_access_grants SET organization_id=%s', (other_tenant,))
            assert await effective() == {'normal.read'}
            await conn.execute('UPDATE core_module_full_access_grants SET organization_id=%s', (tenant,))
            await conn.execute("UPDATE core_users SET status='inactive' WHERE id=%s", (pilot,))
            assert await effective() == set()
            await conn.execute("UPDATE core_users SET status='active' WHERE id=%s", (pilot,))
            await conn.execute("UPDATE core_workspaces SET status='inactive' WHERE id=%s", (workspace,))
            assert 'telchi.future.read' not in await effective()
            await conn.execute("UPDATE core_workspaces SET status='testing' WHERE id=%s", (workspace,))
            await conn.execute('UPDATE core_workspace_capabilities SET enabled=false WHERE permission_id=%s', (new,))
            assert await effective() == {'normal.read'}
            await conn.execute('UPDATE core_workspace_capabilities SET enabled=true WHERE permission_id=%s', (new,))
            await conn.execute("UPDATE core_organizations SET status='inactive' WHERE id=%s", (tenant,))
            assert await effective() == {'normal.read'}
            await conn.execute("UPDATE core_organizations SET status='active' WHERE id=%s", (tenant,))
            await conn.execute('UPDATE core_module_full_access_grants SET revoked_at_utc=now()')
            assert await effective() == {'normal.read'}
            await conn.rollback()
    asyncio.run(run())

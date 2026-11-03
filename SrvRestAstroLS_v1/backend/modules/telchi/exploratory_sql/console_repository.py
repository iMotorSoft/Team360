"""Telchi's read-only identity binding and existing core_events audit adapter.

No role expansion: PermissionConsoleRepository remains the sole RBAC resolver.
Caller owns the existing async pool, connection and transaction.
"""
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ResearchConsoleRepository:
    async def identity(self, conn, user_id):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""SELECT u.id::text AS user_id,
                w.id::text AS workspace, o.id::text AS organization
                FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id
                JOIN core_organizations o ON o.id=w.organization_id
                JOIN core_organization_members m ON m.organization_id=o.id AND m.user_id=u.id
                WHERE u.id=%s AND u.status='active'
                AND w.status IN ('active','testing') AND o.status='active' AND m.status='active'""", (user_id,))
            rows = await cur.fetchall()
            return dict(rows[0]) if len(rows) == 1 else None

    async def enabled_permissions(self, conn, workspace):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""SELECT p.permission_code FROM core_workspace_capabilities c
                JOIN core_permissions p ON p.id=c.permission_id
                WHERE c.workspace_id=%s AND c.module='telchi' AND c.enabled
                AND split_part(p.permission_code,'.',1)='telchi'""", (workspace,))
            return frozenset(row['permission_code'] for row in await cur.fetchall())

    async def audit(self, conn, scope, investigation_id, state):
        # No token, prompt, names, SQL, observations or commercial values in PG.
        await conn.execute("""INSERT INTO core_events(workspace_id,actor_user_id,
            event_name,entity_type,correlation_id,payload_jsonb)
            VALUES(%s,%s,'telchi.research.authorization','telchi_research',%s,%s)""",
            (scope.workspace, scope.user_id, investigation_id,
             Jsonb({'state': state, 'environment': 'dev', 'organization': scope.organization})))

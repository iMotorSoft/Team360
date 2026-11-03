"""B3 administrative READ_ONLY evidence; no login, grants or business execution."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import time

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from modules.console.repositories import PermissionConsoleRepository, WorkspaceConsoleRepository
from modules.telchi.exploratory_sql.console_repository import ResearchConsoleRepository
from modules.telchi.exploratory_sql.foundation import host_read_preflight

OUT = Path('../../data/reports/telchi/authorized-research-b3-v1')

class ReadOnlyProbeRepository:
    async def rows(self, conn, sql, params=()):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            return [dict(r) for r in await cur.fetchall()]

    async def inspect(self, conn):
        users = await self.rows(conn, """SELECT u.id::text AS user_id,u.display_name,u.status AS user_status,
            u.workspace_id::text AS workspace_id,w.slug AS workspace_slug,w.status AS workspace_status,
            o.id::text AS organization_id,o.display_name AS organization_name,o.status AS organization_status,
            m.status AS membership_status FROM core_users u
            JOIN core_workspaces w ON w.id=u.workspace_id
            LEFT JOIN core_organizations o ON o.id=w.organization_id
            LEFT JOIN core_organization_members m ON m.user_id=u.id AND m.organization_id=o.id
            WHERE lower(w.slug) LIKE '%%telchi%%' OR lower(u.display_name) LIKE ANY(%s)
            ORDER BY w.slug,u.display_name""", (['%mario%', '%abraham%'],))
        for u in users:
            uid, wid = u['user_id'], u['workspace_id']
            u['bridge_identity'] = await ResearchConsoleRepository().identity(conn, uid)
            u['roles'] = await self.rows(conn, """SELECT r.role_code,r.status,r.workspace_id::text
                FROM core_user_roles ur JOIN core_roles r ON r.id=ur.role_id WHERE ur.user_id=%s""", (uid,))
            u['profiles'] = await PermissionConsoleRepository().list_permission_profiles(conn, wid, uid)
            u['effective_permissions'] = await PermissionConsoleRepository().list_effective_permissions(conn,wid,uid)
            u['enabled_telchi_permissions'] = sorted(await ResearchConsoleRepository().enabled_permissions(conn,wid))
            u['bridge_permissions'] = sorted(set(u['effective_permissions']) & set(u['enabled_telchi_permissions']))
            u['scoped_full_access'] = await self.rows(conn, """SELECT module,organization_id::text,workspace_id::text,
                revoked_at_utc IS NOT NULL AS revoked FROM core_module_full_access_grants WHERE user_id=%s""", (uid,))
            u['password_state'] = await self.rows(conn, """SELECT disabled FROM console_password_credentials WHERE user_id=%s""", (uid,))
        return users

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), host=host_read_preflight())
    started=time.monotonic()
    dsn=get_database_settings().dsn
    cfg=conninfo_to_dict(dsn)
    if cfg.get('host') not in {'localhost','127.0.0.1','::1'} or cfg.get('dbname')!='team360':
        raise RuntimeError('nonlocal_or_nondev_target_refused')
    conn=await psycopg.AsyncConnection.connect(dsn,connect_timeout=5,application_name='telchi-b3-readonly',
        options='-c default_transaction_read_only=on -c statement_timeout=10000 -c lock_timeout=1000 -c max_parallel_workers_per_gather=0')
    async with conn:
        async with conn.transaction():
            repo=ReadOnlyProbeRepository()
            report['database']=await repo.rows(conn,"SELECT current_database() AS database,current_setting('transaction_read_only') AS read_only,version() AS version")
            report['concurrent_queries']=await repo.rows(conn,"""SELECT datname,state,wait_event_type,wait_event,
                EXTRACT(epoch FROM clock_timestamp()-query_start)::int AS elapsed_seconds
                FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND state='active'
                ORDER BY query_start LIMIT 15""")
            report['identities']=await repo.inspect(conn)
    report['elapsed_seconds']=round(time.monotonic()-started,3)
    with (OUT/'identity.json').open('x') as f: json.dump(report,f,indent=2,default=str)
    print(json.dumps(report,indent=2,default=str))

if __name__=='__main__': asyncio.run(main())

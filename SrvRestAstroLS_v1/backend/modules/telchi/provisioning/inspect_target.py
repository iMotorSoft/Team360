"""Focused read-only inspection; no credentials or human PII in output."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values


async def main():
    from modules.db.settings import get_database_settings
    base = get_database_settings().dsn
    for key, value in dotenv_values('../.env.backend-dev.local').items():
        if value is not None:
            os.environ[key] = value
    dev = get_database_settings().dsn
    def target(dsn):
        p = urlparse(dsn)
        return dict(host=p.hostname, port=p.port, database=p.path.lstrip('/'))
    result = dict(base_target=target(base), dev_override_target=target(dev), read_only=True)
    async with await psycopg.AsyncConnection.connect(dev, connect_timeout=5,
            options='-c default_transaction_read_only=on -c statement_timeout=5000',
            application_name='telchi-provisioning-readonly', row_factory=dict_row) as conn:
        async def query(sql):
            return await (await conn.execute(sql)).fetchall()
        result['server'] = await query("SELECT current_database() AS database, current_user AS role, current_setting('server_version') AS version, current_setting('transaction_read_only') AS read_only")
        result['roles'] = await query('SELECT rolname, rolsuper, rolcanlogin, rolcreatedb FROM pg_roles WHERE rolcanlogin ORDER BY rolname')
        result['sessions'] = await query("SELECT usename, application_name, client_addr::text, state, count(*) FROM pg_stat_activity WHERE datname=current_database() GROUP BY 1,2,3,4")
        result['columns'] = await query("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND (table_name LIKE 'core_organization%' OR table_name IN ('core_workspaces','core_users')) ORDER BY table_name,ordinal_position")
        result['constraints'] = await query("SELECT conrelid::regclass::text AS table_name,conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE connamespace='public'::regnamespace AND (conrelid::regclass::text LIKE 'core_organization%' OR conrelid::regclass::text IN ('core_workspaces','core_users')) ORDER BY 1,2")
        result['orgs'] = await query('SELECT organization_code,status FROM core_organizations ORDER BY organization_code')
        result['org_roles'] = await query('SELECT role_code FROM core_organization_roles ORDER BY role_code')
        result['workspaces'] = await query('SELECT slug,status,metadata_jsonb FROM core_workspaces ORDER BY slug')
        result['permission_candidates'] = await query("SELECT permission_code,description FROM core_permissions WHERE permission_code LIKE '%telchi%' OR permission_code LIKE '%sales%' ORDER BY permission_code")
        result['user_inventory'] = await query("SELECT w.slug,u.role,u.status,count(*) AS n FROM core_users u LEFT JOIN core_workspaces w ON w.id=u.workspace_id GROUP BY 1,2,3 ORDER BY 1,2,3")
        result['organizational_admin_inventory'] = await query("SELECT o.organization_code,r.role_code,r.status,count(*) AS n FROM core_organization_member_roles r JOIN core_organization_members m ON m.id=r.organization_member_id JOIN core_organizations o ON o.id=m.organization_id GROUP BY 1,2,3 ORDER BY 1,2,3")
        result['write_roles'] = await query("SELECT rolname,has_table_privilege(rolname,'core_workspaces','INSERT') AS workspace_insert,has_table_privilege(rolname,'core_users','UPDATE') AS user_update FROM pg_roles WHERE rolcanlogin ORDER BY rolname")
        result['phone_schema'] = await query("SELECT to_regclass('public.messaging_phone_bindings')::text AS table_name")
    out = Path('../../data/reports/telchi/whatsapp-assistant-dev-live-v1/tenant-target-inspection-r2.json')
    if out.exists():
        raise RuntimeError('evidence already exists')
    out.write_text(json.dumps(result, indent=2, default=str) + '\n')
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(main())

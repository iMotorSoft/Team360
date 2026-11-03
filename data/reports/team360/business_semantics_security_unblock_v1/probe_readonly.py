"""Run from backend with uv run --no-sync python <this file>. No application import/startup.
Only allowlisted connection metadata and aggregate identity inventory are emitted.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from dotenv import dotenv_values
from modules.db.settings import get_database_settings, _is_postgresql_scheme

OUT = Path(__file__).resolve().parent


def target(dsn):
    p = conninfo_to_dict(dsn)
    return {k: p.get(k) for k in ('host', 'port', 'dbname', 'user')}


def source():
    for k in ('TEAM360_DB_URL', 'TEAM360_DB_URL_PSQL', 'DB_PG_V360_URL'):
        v = os.getenv(k, '').strip()
        if v and _is_postgresql_scheme(v):
            return k
    return 'globalVar.get_team360_db_url_psql'


QUERIES = {
    'server': "SELECT current_database() AS database,current_schema() AS schema,current_schemas(true) AS schemas,current_user AS role,session_user,inet_server_addr()::text AS address,inet_server_port() AS port,current_setting('server_version') AS version,current_setting('search_path') AS search_path,current_setting('row_security') AS row_security,current_setting('transaction_read_only') AS read_only,pg_is_in_recovery() AS recovery,(pg_control_system()).system_identifier::text AS system_identifier",
    'role': "SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolinherit,rolcanlogin FROM pg_roles WHERE rolname=current_user",
    'membership': "SELECT r.rolname,r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,pg_has_role(current_user,r.oid,'USAGE') AS effective_inherited FROM pg_roles r WHERE r.rolname<>current_user AND pg_has_role(current_user,r.oid,'MEMBER') ORDER BY r.rolname",
    'direct_role_grants': "SELECT r.rolname,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member WHERE u.rolname=current_user ORDER BY r.rolname",
    'databases': "SELECT datname,pg_get_userbyid(datdba) AS owner,datallowconn FROM pg_database ORDER BY datname",
    'extensions': "SELECT extname,extversion FROM pg_extension WHERE extname IN ('vector','pgcrypto') ORDER BY extname",
    'tables': "SELECT n.nspname AS schema,c.relname AS table_name,pg_get_userbyid(c.relowner) AS owner,c.relrowsecurity,c.relforcerowsecurity,has_table_privilege(current_user,c.oid,'SELECT') AS can_select,has_table_privilege(current_user,c.oid,'INSERT') AS can_insert,has_table_privilege(current_user,c.oid,'UPDATE') AS can_update,has_table_privilege(current_user,c.oid,'DELETE') AS can_delete FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND c.relname LIKE 'business_concept%' ORDER BY n.nspname,c.relname",
    'runtime_role_candidates': "SELECT r.rolname,r.rolsuper,r.rolbypassrls,has_table_privilege(r.oid,'public.business_concepts','SELECT') AS concept_select,has_table_privilege(r.oid,'public.business_concepts','INSERT') AS concept_insert FROM pg_roles r WHERE r.rolcanlogin ORDER BY r.rolname",
    'policies': "SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE tablename LIKE 'business_concept%' ORDER BY tablename,policyname",
    'sessions': "SELECT datname,usename,application_name,client_addr::text,state,count(*) AS n FROM pg_stat_activity WHERE backend_type='client backend' GROUP BY 1,2,3,4,5 ORDER BY 1,2,3",
    'identity_inventory': "SELECT o.organization_code,w.slug,u.status,count(u.id) AS n FROM core_organizations o JOIN core_workspaces w ON w.organization_id=o.id LEFT JOIN core_users u ON u.workspace_id=w.id GROUP BY 1,2,3 ORDER BY 1,2,3",
    'admin_inventory': "SELECT o.organization_code,r.role_code,m.status AS member_status,r.status AS assignment_status,count(*) AS n FROM core_organization_members m JOIN core_organization_member_roles r ON r.organization_member_id=m.id JOIN core_organizations o ON o.id=m.organization_id GROUP BY 1,2,3,4 ORDER BY 1,2",
    'auth_column_names': "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name LIKE 'core_%' AND (column_name ILIKE '%password%' OR column_name ILIKE '%auth%' OR column_name ILIKE '%login%') ORDER BY 1,2",
}


async def main():
    original = dict(os.environ)
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'writes': 0,
              'queries': QUERIES, 'contexts': {}, 'errors': {}}
    contexts = [('inherited_shell', None), ('backend_dev_launcher_override', Path('../.env.backend-dev.local'))]
    for label, file in contexts:
        os.environ.clear()
        os.environ.update(original)
        if file:
            if not file.is_file():
                report['contexts'][label] = {'file_present': False}
                continue
            for k, v in dotenv_values(file).items():
                if v is not None:
                    os.environ[k] = v
        dsn = get_database_settings().dsn
        item = {'source': source(), 'target': target(dsn),
                'TEAM360_ENV': os.getenv('TEAM360_ENV'),
                'approved_marker_present': bool(os.getenv('TEAM360_SEMANTICS_DEV_SYSTEM_IDENTIFIER')),
                'paseto_enabled_setting': os.getenv('TEAM360_PASETO_ENABLED'),
                'public_key_present': bool(os.getenv('TEAM360_PASETO_PUBLIC_KEY_B64')),
                'operator_trust_present': bool(os.getenv('TELCHI_ADMIN_TRUST_CONFIG')),
                'explicit_provisioning_dsn_present': bool(os.getenv('TELCHI_PROVISIONING_DSN')),
                'results': {}}
        report['contexts'][label] = item
        try:
            async with await psycopg.AsyncConnection.connect(
                dsn, row_factory=dict_row, connect_timeout=5,
                options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000',
                application_name='bs-security-unblock-readonly') as conn:
                for name, sql in QUERIES.items():
                    try:
                        async with conn.transaction():
                            item['results'][name] = await (await conn.execute(sql)).fetchall()
                    except Exception as exc:
                        report['errors'][label + ':' + name] = type(exc).__name__
                await conn.rollback()
        except Exception as exc:
            report['errors'][label] = type(exc).__name__
    os.environ.clear()
    os.environ.update(original)
    (OUT / 'database_probe.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
    print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(main())

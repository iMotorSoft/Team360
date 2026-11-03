"""Bounded DEV RBAC audit. PostgreSQL transactions are READ ONLY from connect.

Run from backend: .venv/bin/python -m modules.telchi.investigation.validation.full_access_rbac_v1.readonly_audit
Prints no DSN, telephone, credentials or message content. No services started.
"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row

from modules.console.repositories import PermissionConsoleRepository, WorkspaceConsoleRepository
from modules.db.settings import get_database_settings
from modules.telchi.assistant.whatsapp_dev import PRIVATE_ROOT, approval_digest, read_approval


async def main():
    for key, value in dotenv_values('../.env.backend-dev.local').items():
        if value is not None:
            os.environ[key] = value
    dsn = get_database_settings().dsn
    target = urlparse(dsn)
    if target.hostname not in {'localhost', '127.0.0.1'} or target.path != '/team360':
        raise RuntimeError('unexpected DEV target; audit not executed')
    output = dict(observed_at=datetime.now(timezone.utc).isoformat(),
                  database_writes=0, branch='feature/console-backend-core')
    async with await psycopg.AsyncConnection.connect(
        dsn, connect_timeout=5, row_factory=dict_row,
        options='-c default_transaction_read_only=on -c statement_timeout=5000',
        application_name='telchi-full-access-readonly-audit',
    ) as conn:
        async def query(sql, params=None):
            return await (await conn.execute(sql, params)).fetchall()

        output['server'] = await query("SELECT current_database() AS database, current_setting('transaction_read_only') AS read_only, inet_server_port() AS port")
        output['pilot'] = await query("""
            SELECT u.id::text AS user_id, u.email, u.role, u.status,
                   u.workspace_id::text, w.slug, w.status AS workspace_status,
                   w.organization_id::text, o.organization_code, o.status AS organization_status
            FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id
            JOIN core_organizations o ON o.id=w.organization_id
            WHERE lower(trim(u.email))='devfull@telchiai.com'
        """)
        if len(output['pilot']) != 1:
            raise RuntimeError('ambiguous or absent pilot')
        pilot = output['pilot'][0]
        uid, wid = pilot['user_id'], pilot['workspace_id']
        if pilot['slug'] != 'telchi_dev' or pilot['organization_code'] != 'telchi':
            raise RuntimeError('pilot outside expected DEV scope')
        resolver = PermissionConsoleRepository()
        output['effective_permissions'] = await resolver.list_effective_permissions(conn, wid, uid)
        output['roles'] = await query(WorkspaceConsoleRepository.LIST_USER_ROLES_SQL,
                                      dict(user_id=uid, workspace_id=wid))
        output['profiles'] = await resolver.list_permission_profiles(conn, wid, uid)
        output['full_access_permissions'] = await query("SELECT permission_code FROM core_permissions WHERE lower(permission_code) LIKE '%full%access%' OR permission_code IN ('*','telchi.*')")
        output['full_access_roles'] = await query("SELECT role_code,workspace_id::text,status FROM core_roles WHERE lower(role_code) LIKE '%full%access%'")
        output['phone_bindings'] = await query("""
            SELECT environment, provider, tenant_id, workspace_id::text, verification_status,
                   verified_at_utc IS NOT NULL AS has_verified_at,
                   verification_ref IS NOT NULL AS has_verification_ref, revoked_at_utc
            FROM messaging_phone_bindings WHERE user_id=%s
        """, (uid,))
        output['channels'] = await query("""
            SELECT c.channel_alias, c.status, p.code AS provider,
                   c.metadata_jsonb->>'environment' AS environment,
                   c.metadata_jsonb->>'module' AS module,
                   c.metadata_jsonb->>'tenant_id' AS tenant_id,
                   c.metadata_jsonb->>'dispatcher' AS dispatcher
            FROM communication_channels c
            JOIN communication_providers p ON p.id=c.provider_id
            WHERE c.workspace_id=%s AND c.channel_type='whatsapp'
        """, (wid,))
        output['commercial_authorizations'] = await query("""
            SELECT event_name,occurred_at_utc,payload_jsonb->'after' AS after
            FROM core_events WHERE workspace_id=%s
              AND event_name LIKE 'telchi.admin.%%authorize'
            ORDER BY occurred_at_utc DESC LIMIT 10
        """, (wid,))
        output['wrong_workspace_effective'] = await resolver.list_effective_permissions(
            conn, '00000000-0000-0000-0000-000000000000', uid)
    # Read/validate only the existing pilot admission, never mutate it or its gates.
    approval = read_approval(PRIVATE_ROOT / 'whatsapp-dev-session-approval.json')
    output['pilot_admission'] = {key: approval[key] for key in (
        'environment', 'tenant_id', 'workspace_id', 'user_id', 'access', 'revoked',
        'module_enabled', 'whole_workspace_scope_verified')}
    output['pilot_admission']['scope_matches_database'] = (
        approval['user_id'] == uid and approval['workspace_id'] == wid)
    output['pilot_admission']['sha256'] = approval_digest(approval)
    output['limits'] = ['No live transport or runtime availability certified.',
                        'No FULL_ACCESS role exists to revoke; specific-grant revocation tested offline.',
                        'Organization/tenant binding is separate from Console permission resolution.']
    print(json.dumps(output, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(main())

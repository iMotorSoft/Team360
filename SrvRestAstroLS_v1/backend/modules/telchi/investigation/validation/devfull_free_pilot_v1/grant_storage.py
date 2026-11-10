"""Bounded owner-authorized DEV grants; ACL backup and rollback-only UPSERT probe."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.whatsapp_dev_quick import operation_lock
from modules.telchi.research_repository import ResearchRecoveryRepository
from .activate import check_runtime_storage
from .prepare import ORG, WORKSPACE, write_new

COLUMNS = ('id', 'workspace_id', 'actor_user_id', 'event_name', 'entity_type',
           'correlation_id', 'payload_jsonb')
ROLE = 't360devv1_runtime'
GRANTS = '''GRANT INSERT (id, workspace_id, actor_user_id, event_name,
    entity_type, correlation_id, payload_jsonb)
    ON TABLE public.core_events TO t360devv1_runtime;
GRANT UPDATE (payload_jsonb) ON TABLE public.core_events TO t360devv1_runtime;'''
ACL = '''SELECT a.attname, a.attacl::text AS acl
    FROM pg_attribute a WHERE a.attrelid='public.core_events'::regclass
    AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum'''


async def run():
    import globalVar
    from modules.db.settings import get_database_settings
    control = lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval = dev.read_approval(Path(control['approval']))
    assert approval['environment'] == 'dev' and approval['workspace_id'] == WORKSPACE
    runtime = get_database_settings().dsn
    backup = dev.PRIVATE_ROOT / ('devfull-column-grants-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(mode=0o700)
    async with await psycopg.AsyncConnection.connect(globalVar.get_team360_db_url_psql(),
            row_factory=dict_row, connect_timeout=5,
            options='-c statement_timeout=5000 -c lock_timeout=3000') as admin:
        identity = await (await admin.execute('SELECT current_database() AS db, current_user AS role')).fetchone()
        assert identity['db'] == 'team360'
        before = await (await admin.execute(ACL)).fetchall()
        table_acl = await (await admin.execute("SELECT relacl::text AS acl FROM pg_class WHERE oid='public.core_events'::regclass")).fetchone()
        direct = await (await admin.execute('''SELECT a.attname, x.privilege_type
            FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) x
            JOIN pg_roles r ON r.oid=x.grantee
            WHERE a.attrelid='public.core_events'::regclass AND r.rolname=%s''', (ROLE,))).fetchall()
        existing = {(r['attname'], r['privilege_type']) for r in direct}
        rollback = []
        for privilege, columns in [('INSERT', COLUMNS), ('UPDATE', ('payload_jsonb',))]:
            added = [c for c in columns if (c, privilege) not in existing]
            if added:
                rollback.append(f"REVOKE {privilege} ({', '.join(added)}) ON TABLE public.core_events FROM {ROLE};")
        write_new(backup / 'acl-before.json', dict(database='team360', role=ROLE, columns=before, table=table_acl, direct=direct))
        with open(backup / 'rollback.sql', 'x', opener=lambda p, f: __import__('os').open(p, f, 0o600)) as stream:
            stream.write('BEGIN;\n' + '\n'.join(rollback) + '\nCOMMIT;\n')
        await admin.execute(GRANTS)
        after = await (await admin.execute(ACL)).fetchall()
        assert table_acl == await (await admin.execute("SELECT relacl::text AS acl FROM pg_class WHERE oid='public.core_events'::regclass")).fetchone()
        write_new(backup / 'acl-after.json', after)
        await admin.commit()
    await check_runtime_storage()
    repo = ResearchRecoveryRepository()
    scope = SimpleNamespace(user_id=approval['user_id'], organization=ORG, workspace=WORKSPACE)
    context = SimpleNamespace(correlation_id=str(uuid4()))
    async with await psycopg.AsyncConnection.connect(runtime, row_factory=dict_row, connect_timeout=5) as conn:
        identity = await (await conn.execute('SELECT current_database() AS db, current_user AS role')).fetchone()
        assert identity == dict(db='team360', role=ROLE)
        assert await repo.load(conn, scope, context) is None
        await repo.save(conn, scope, context, {'probe': 'insert', 'isolated': True})
        assert await repo.load(conn, scope, context) == {'probe': 'insert', 'isolated': True}
        await repo.save(conn, scope, context, {'probe': 'conflict-update', 'isolated': True})
        assert await repo.load(conn, scope, context) == {'probe': 'conflict-update', 'isolated': True}
        await conn.rollback()
        assert await repo.load(conn, scope, context) is None
    result = dict(DB_GRANTS='PASS', database='team360', role=ROLE, grants=GRANTS,
                  upsert_insert='PASS', upsert_conflict_update='PASS', probe_rollback='PASS',
                  table_acl_unchanged=True, backup=str(backup),
                  rollback='Use administrative globalVar connection to team360; execute backup/rollback.sql after verifying no later ACL writer.',
                  row_restriction=False, risk_accepted='DEV ONLY; column grants do not restrict rows')
    write_new(backup / 'result.json', result)
    print('DB_GRANTS=PASS')
    print('GRANTS_RECEIPT=' + str(backup / 'result.json'))
    return result


def main():
    with operation_lock():
        asyncio.run(run())


if __name__ == '__main__':
    main()

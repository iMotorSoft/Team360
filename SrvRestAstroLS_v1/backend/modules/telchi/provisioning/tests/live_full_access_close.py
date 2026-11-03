"""Real DEV grant/revocation rehearsal. Revocation and its audit are rolled back.

Requires explicit --backup from the actual closeout. Does not create identities,
change individual pilot grants, issue tokens, or interact with a transport.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings
from modules.telchi.provisioning.business_close_repository import BusinessCloseRepository, AUTHORIZATION, REGISTRY
from modules.telchi.provisioning.repository import canonical


async def run(backup):
    from modules.telchi.assistant.whatsapp_dev import private_file
    backup = private_file(backup)
    before = json.loads(backup.read_text())
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    dsn = get_database_settings().dsn
    parsed = urlparse(dsn)
    assert parsed.hostname in {'127.0.0.1','localhost'} and parsed.port == 5432 and parsed.path == '/team360'
    async with await psycopg.AsyncConnection.connect(dsn,row_factory=dict_row,autocommit=True) as conn:
        repo = BusinessCloseRepository()
        async with conn.transaction():
            await repo.guard(conn)
            identities = await repo.identities(conn)
            assert identities == before['identities']
            workspace, pilot = identities['workspace']['id'],identities['pilot']['id']
            resolver = PermissionConsoleRepository()
            effective = await resolver.list_effective_permissions(conn,workspace,pilot)
            assert set(effective) == set(before['effective']) | set(REGISTRY.values())
            active = await (await conn.execute('SELECT user_id::text,workspace_id::text,module,organization_id::text FROM core_module_full_access_grants WHERE revoked_at_utc IS NULL')).fetchall()
            assert active == [dict(user_id=pilot,workspace_id=workspace,module='telchi',organization_id=identities['workspace']['organization_id'])]
            user_roles = canonical(await (await conn.execute('''SELECT ur.* FROM core_user_roles ur
                JOIN core_users u ON u.id=ur.user_id WHERE u.workspace_id=%s''',(workspace,))).fetchall())
            assert sorted(user_roles,key=lambda r:r['id']) == sorted(before['records']['user_roles'],key=lambda r:r['id'])
            audit_before = (await (await conn.execute('SELECT count(*) n FROM core_events')).fetchone())['n']
            # Reapplying changes nothing and does not append another grant audit.
            result = await repo.activate(conn,authorization=AUTHORIZATION,backup_sha256=digest)
            assert result['changed'] is False and result['individual_pilot_assignments_created'] == 0
            assert (await (await conn.execute('SELECT count(*) n FROM core_events')).fetchone())['n'] == audit_before
        async with conn.transaction(force_rollback=True):
            result = await repo.revoke(conn,authorization=AUTHORIZATION,backup_sha256=digest)
            assert result['changed'] is True
            assert set(result['effective']) == set(before['effective'])
            assert 'telchi.sales.invoice_amount.read.v1' not in result['effective']
            event = await (await conn.execute("SELECT payload_jsonb FROM core_events WHERE event_name='telchi.admin.full-access-revoke' AND workspace_id=%s ORDER BY occurred_at_utc DESC LIMIT 1",(workspace,))).fetchone()
            assert event['payload_jsonb']['result'] == 'revoked'
            assert event['payload_jsonb']['user_id'] == pilot
            assert event['payload_jsonb']['before'] == effective
        restored = await resolver.list_effective_permissions(conn,workspace,pilot)
        assert restored == effective
        return dict(status='PASS', actual_pilot=True, active_full_access_assignments=1,
            dynamic_effective=effective, individual_user_roles_unchanged=True,
            idempotent_activation=True,revocation='real repository and resolver inside rollback transaction',
            revocation_audit_verified=True,revocation_rollback_restored=True,
            new_amount_only_via_full_access=True,backup_sha256=digest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    result=asyncio.run(run(args.backup))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()

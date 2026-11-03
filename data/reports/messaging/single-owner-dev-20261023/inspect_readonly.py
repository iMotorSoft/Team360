"""Bounded DEV inventory only. No key generation, writes, delivery or Graph calls."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'SrvRestAstroLS_v1/backend'))
from modules.db.settings import get_database_settings

OUT = Path(__file__).resolve().parent
PREVIOUS = OUT.parent / 'dev-v1-intervention-20261023'
PRIVATE = ROOT.parents[1] / 'private/telchi'
LAB = ROOT.parents[1] / 'lab/evolution-api'
CHANNELS = ['489e6f2c-8bac-4805-99ba-7dbe4d48c10e', '3cc01e11-da1c-4630-a9c6-ecc2f79220d4']


def main():
    prior = json.loads((PREVIOUS / 'result.json').read_text())
    backup = Path(json.loads((PREVIOUS / 'backup-verification.json').read_text())['backup_directory'])
    report = dict(observed_at=datetime.now(timezone.utc).isoformat(),
                  branch='feature/console-backend-core', target_writes=0, real_messages_sent=0,
                  production_modified=False, meta_calls=0, services_started=0,
                  keys_generated=0, credentials_provisioned=False)
    with psycopg.connect(get_database_settings().dsn, row_factory=dict_row, connect_timeout=3,
                        application_name='single-owner-dev-readonly',
                        options='-c default_transaction_read_only=on -c statement_timeout=5000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        assert conn.execute('SELECT current_database() AS db').fetchone()['db'] == 'team360'
        report['bindings'] = conn.execute('''SELECT w.slug,c.channel_alias,c.status,
            c.metadata_jsonb->>'provider_instance' AS provider_instance,
            c.metadata_jsonb->>'environment' AS environment
            FROM communication_channels c JOIN core_workspaces w ON w.id=c.workspace_id
            WHERE c.id=ANY(%s::uuid[]) ORDER BY w.slug''', (CHANNELS,)).fetchall()
        report['event_counts'] = conn.execute('''SELECT channel_id::text,count(*) AS n
            FROM message_events WHERE channel_id=ANY(%s::uuid[]) GROUP BY 1 ORDER BY 1''', (CHANNELS,)).fetchall()
        ids = [str(row['id']) for row in prior['protected_events']]
        protected = conn.execute('''SELECT id::text,status,transport_status FROM message_events
            WHERE id=ANY(%s::uuid[]) ORDER BY id''', (ids,)).fetchall()
        report['protected_events_unchanged'] = protected == prior['protected_events']
        report['protected_event_count'] = len(protected)
        report['ot_inventory_count'] = conn.execute('SELECT count(*) AS n FROM ot_inventory').fetchone()['n']
        conn.rollback()
    report['counts_match_prior'] = {r['channel_id']: r['n'] for r in report['event_counts']} == {
        str(r['channel_id']): r['n'] for r in prior['message_event_counts']}
    report['configuration_matches_verified_backup'] = {}
    for path, name in [(LAB / '.env', 'evolution.env'), (LAB / 'image.ref', 'image.ref'),
                       (ROOT / 'SrvRestAstroLS_v1/.env.backend-dev.local', 'backend.env'),
                       (PRIVATE / 'whatsapp-dev-control.json', 'telchi-control.json')]:
        report['configuration_matches_verified_backup'][name] = path.read_bytes() == (backup / 'private' / name).read_bytes()
    state = subprocess.run(['podman', 'inspect', 'evolution-api', '--format', '{{.State.Status}}'],
                           capture_output=True, check=True, timeout=10).stdout.decode().strip()
    report['evolution_state'] = state
    report['blocker'] = ('Existing instance still has two persisted workspace bindings; testing is not '
                         'evidence of retirement. Exclusive V1 inventory is empty. No authority inferred '
                         'to alter the other workspace or claim exclusive routing.')
    report['source_sha256'] = {}
    files = list((ROOT / 'SrvRestAstroLS_v1/backend/modules/messaging/administration').glob('*.py'))
    files.append(ROOT / 'SrvRestAstroLS_v1/backend/tests/test_messaging_single_owner_dev.py')
    for path in sorted(files):
        report['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / 'inspection.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('counts_match_prior', 'protected_events_unchanged',
                                          'ot_inventory_count', 'evolution_state', 'configuration_matches_verified_backup')}))


if __name__ == '__main__':
    main()

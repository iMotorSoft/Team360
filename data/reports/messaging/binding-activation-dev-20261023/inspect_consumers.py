"""Bounded observation of the previously identified DEV transport; no writes to services."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'SrvRestAstroLS_v1/backend'))
import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
OUT = Path(__file__).parent
PRIVATE = ROOT.parents[1] / 'private/telchi'
LAB = ROOT.parents[1] / 'lab/evolution-api'
CHANNELS = ['3cc01e11-da1c-4630-a9c6-ecc2f79220d4', '489e6f2c-8bac-4805-99ba-7dbe4d48c10e']

def observe():
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'process_consumers': []}
    keys = ['TEAM360_MESSAGING_DEV_ENABLED', 'TEAM360_MESSAGING_WORKSPACE_SLUG',
            'TEAM360_MESSAGING_CHANNEL_ALIAS', 'TEAM360_MESSAGING_EVOLUTION_INSTANCE',
            'TEAM360_MESSAGING_DEV_WORKSPACE_SLUG', 'TEAM360_MESSAGING_DEV_CHANNEL_ALIAS']
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            cmd = (proc/'cmdline').read_bytes().replace(b'\x00', b' ')
            if not any(s in cmd for s in (b'uvicorn', b'ls_iMotorSoft', b'dev_runtime_http', b'messaging.dev_app', b'dev_session', b'gate_session')): continue
            if int(proc.name) == os.getpid(): continue
            env = dict(v.split(b'=', 1) for v in (proc/'environ').read_bytes().split(b'\x00') if b'=' in v)
            report['process_consumers'].append({'pid': int(proc.name), 'comm': (proc/'comm').read_text().strip(),
                'cwd': str((proc/'cwd').resolve()),
                'routing': {k: env[k.encode()].decode() for k in keys if k.encode() in env}})
        except (FileNotFoundError, PermissionError, ProcessLookupError): continue
    raw = subprocess.run(['podman','inspect','evolution-api'], check=True, capture_output=True, timeout=10)
    c = json.loads(raw.stdout)[0]
    report['evolution'] = {'state': c['State']['Status'], 'image': c['Image'], 'pid': c['State']['Pid']}
    listeners = subprocess.run(['ss','-ltn'], check=True, capture_output=True, timeout=5).stdout.decode()
    report['transport_listeners'] = [l for l in listeners.splitlines() if any(':'+p in l for p in ('18180','18181'))]
    report['config_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (LAB/'.env',LAB/'image.ref', ROOT/'SrvRestAstroLS_v1/.env.backend-dev.local', PRIVATE/'whatsapp-dev-control.json')}
    # Publish only selected routing values, never tokens/DSNs.
    control = json.loads((PRIVATE/'whatsapp-dev-control.json').read_text())['env']
    report['control_routing'] = {k: control[k] for k in keys + ['TEAM360_EVOLUTION_INSTANCE'] if k in control}
    with psycopg.connect(get_database_settings().dsn, row_factory=dict_row, connect_timeout=3,
            options='-c default_transaction_read_only=on -c statement_timeout=5000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        assert conn.execute('SELECT current_database() AS db').fetchone()['db'] == 'team360'
        report['bindings'] = conn.execute('''SELECT c.id::text,c.workspace_id::text,w.slug,c.channel_alias,c.status,
            c.metadata_jsonb->>'provider_instance' AS instance FROM communication_channels c
            JOIN core_workspaces w ON w.id=c.workspace_id WHERE c.id=ANY(%s::uuid[]) ORDER BY c.id''', (CHANNELS,)).fetchall()
        report['history'] = conn.execute('''SELECT channel_id::text,count(*) AS n,max(occurred_at_utc)::text AS last_event,
            md5(string_agg(md5(row_to_json(e)::text),'' ORDER BY id)) AS digest
            FROM message_events e WHERE channel_id=ANY(%s::uuid[]) GROUP BY 1 ORDER BY 1''',(CHANNELS,)).fetchall()
        report['historical_pending'] = conn.execute('''SELECT status,transport_status,count(*) AS n FROM message_events
            WHERE channel_id=%s AND (status IN ('pending','running') OR transport_status IN ('pending','unknown'))
            GROUP BY 1,2''',(CHANNELS[0],)).fetchall()
        report['ot_inventory'] = conn.execute('SELECT side,binding_id::text,scope FROM ot_inventory').fetchall()
        conn.rollback()
    return report

if __name__ == '__main__':
    report = observe()
    (OUT/'consumer-observation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='config_sha256'}, indent=2))

"""Read-only post-intervention evidence and source-artifact validation."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import backup_verify as b

proof=json.loads((b.OUT/'backup-verification.json').read_text())
private=Path(proof['backup_directory'])
assert proof['restore_verified'] and proof['restore_container_removed']
result={'branch':'feature/console-backend-core','observed_at':datetime.now(timezone.utc).isoformat(),
        'V1_INSTALLED_IN_DEV':'NO','installation_detail':'Srv05/Messaging source and all three schemas installed; existing Evolution container NOT replaced/started until authenticated DEV configuration is provisioned',
        'THREE_MIGRATIONS':'PASS','V1_CREDENTIALS':'FAIL','PRIVATE_CALLBACK':'FAIL','SRV05_PROVIDER_V1':'FAIL','BACKUP_RECOVERY':'PASS',
        'blocked_not_functional_failures':{'V1_CREDENTIALS':'Missing distinct accredited requester/approver identities, public key references and independent approvals; none fabricated',
          'PRIVATE_CALLBACK':'UDS mount/UID proof PASS; actual signed callback cannot be configured before V1 trust/identities',
          'SRV05_PROVIDER_V1':'Source composition/no-fallback tests PASS; operational startup blocked by missing authenticated configuration'},
        'META_UNCHANGED':'YES','HISTORY_PRESERVED':'YES','REAL_MESSAGES_SENT':0,'READY_FOR_WHATSAPP_TEST':'NO',
        'source_files':[],'databases':{},'existing_private_configuration_unchanged':{},'production_modified':False,
        'focused_tests':{'passed':161,'skipped':16,'warning':'Existing Diagnosis default in-memory warning; no Diagnosis request','scope':'modified Messaging and Srv05 tests only; no 427 rerun'},
        'recovery':'Keep additive tables, audit and UNKNOWN. Admission remains closed; do not start legacy image/launcher or restore live DB. Archives and pre-change source retained privately.',
        'next_owner_input':'Two distinct authorized requester/approver actor IDs with public Ed25519 key references and independently signed approvals for existing Telchi DEV scope; no private keys in chat',
        'own_processes_left_running':0,'real_history_replayed':False}
for x in json.loads((b.OUT/'source-plan.json').read_text()):
    p=b.BACKEND/x['path'];actual=hashlib.sha256(p.read_bytes()).hexdigest();assert actual==x['after'],x['path']
    result['source_files'].append({'path':str(p.relative_to(b.ROOT)),'sha256':actual})
for p in ['db/migrations/032_team360_transport_evidence_v1.sql','tests/durable_egress_worker.py']:
    candidate=b.LAB/'data/dev-promotion-v1/team360/backend'/p
    assert (b.BACKEND/p).read_bytes()==candidate.read_bytes()
    result['source_files'].append({'path':str((b.BACKEND/p).relative_to(b.ROOT)),'sha256':b.digest(candidate)})
base=conninfo_to_dict(b.get_database_settings().dsn)
for db,schema in [('team360','public'),('evolution_api','evolution_api')]:
    with psycopg.connect(make_conninfo(**{**base,'dbname':db}),row_factory=dict_row,connect_timeout=3,
                         options='-c default_transaction_read_only=on -c statement_timeout=30000') as c:
        c.execute(b.sql.SQL('SET LOCAL search_path TO {},public').format(b.sql.Identifier(schema)))
        before=json.loads((private/(db+'-premigration.json')).read_text())
        after=b.inventory(c)
        for table,entry in before['tables'].items():
            if table.endswith('._prisma_migrations'):
                assert after['tables'][table]['count']==entry['count']+2
            else:
                assert after['tables'][table]==entry,table
        result['databases'][db]={'all_original_tables_preserved':'PASS',
            'new_ot_tables':[t for t in after['tables'] if t not in before['tables']],
            'ot_row_counts':{t:e['count'] for t,e in after['tables'].items() if t.split('.',1)[1].startswith('ot_')}}
        if db=='team360':
            result['message_event_counts']=c.execute('SELECT channel_id,count(*) AS n FROM message_events WHERE channel_id=ANY(%s::uuid[]) GROUP BY 1',(b.CHANNELS,)).fetchall()
            counts={str(x['channel_id']):x['n'] for x in result['message_event_counts']}
            assert counts==dict(zip(b.CHANNELS,[1335,164]))
            ids=['42b57718-2956-421a-9bc1-20e5918f02b5','62c88461-2502-4ab4-8705-ef8395e15dff','9c16bd91-0972-4273-8015-2f54c52d40be','aedf9f66-0a34-4d3a-91d1-60a567d358bc','f8cee1ab-f0f2-4186-bf9d-c45ce574d0ab']
            protected=c.execute('SELECT id,status,transport_status FROM message_events WHERE id=ANY(%s::uuid[]) ORDER BY id',(ids,)).fetchall()
            assert len(protected)==5
            result['protected_events']=protected
            roles=c.execute("SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolinherit,rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname IN ('t360devv1_ddl','evodevv1_ddl') ORDER BY 1").fetchall()
            assert len(roles)==2 and all(not any(v for k,v in row.items() if k!='rolname') for row in roles)
            result['ddl_roles']=roles
        c.rollback()
for src,name in [(b.LAB/'.env','evolution.env'),(b.LAB/'image.ref','image.ref'),
                 (b.ROOT/'SrvRestAstroLS_v1/.env.backend-dev.local','backend.env'),
                 (b.PRIVATE/'whatsapp-dev-control.json','telchi-control.json')]:
    same=src.read_bytes()==(private/'private'/name).read_bytes()
    result['existing_private_configuration_unchanged'][name]=same
    assert same,name
state=subprocess.run(['podman','inspect','evolution-api','--format','{{.State.Status}} {{.Image}}'],capture_output=True,check=True).stdout.decode().strip()
result['evolution_existing_container']=state
assert state.startswith('created ')
# Fail closed with no credentials, before DB/network or legacy provider construction.
from modules.messaging.transport_runtime import TransportRuntime
assert not os.environ.get('TEAM360_TRANSPORT_V1_CONFIG')
try:
    TransportRuntime.from_env(None)
except ValueError as e:
    assert 'legacy fallback forbidden' in str(e)
    result['missing_configuration_fail_closed']='PASS'
else:
    raise AssertionError('Missing V1 configuration did not fail closed')
(b.OUT/'result.json').write_text(json.dumps(result,default=str,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['THREE_MIGRATIONS','BACKUP_RECOVERY','META_UNCHANGED','HISTORY_PRESERVED','REAL_MESSAGES_SENT','missing_configuration_fail_closed']}))

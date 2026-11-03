"""Owner-authorized scoped DEV status change. No history deletion or replay."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from inspect_consumers import observe, ROOT, OUT, PRIVATE, CHANNELS
import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from modules.messaging.administration.bindings import BindingAdministration


def main():
    before = observe()
    assert before['evolution']['state'] == 'created' and before['evolution']['pid'] == 0
    assert not before['transport_listeners'] and not before['historical_pending']
    assert all(not p['cwd'].startswith(str(ROOT)) for p in before['process_consumers'])
    assert before['control_routing']['TEAM360_MESSAGING_WORKSPACE_SLUG'] == 'telchi_dev'
    assert before['control_routing']['TEAM360_MESSAGING_CHANNEL_ALIAS'] == 'telchi_whatsapp_dev'
    assert [r['n'] for r in before['history']] == [164,1335]
    assert not before['ot_inventory']
    evidence = OUT/'consumer-observation.json'
    evidence.write_text(json.dumps(before,indent=2)+'\n')
    private = PRIVATE/'evolution-dev-v1'
    assert private.stat().st_mode & 0o777 == 0o700
    backup_path = private/'historical-binding-before.json'
    assert not backup_path.exists()
    admin = BindingAdministration()
    with psycopg.connect(get_database_settings().dsn,row_factory=dict_row,connect_timeout=3,
            options='-c statement_timeout=5000') as conn:
        assert conn.execute('SELECT current_database() AS db').fetchone()['db'] == 'team360'
        old = admin.deactivate_historical(conn, channel_id=CHANNELS[0], workspace_slug='team360_public_site',
            alias='evolution-meta-dev', instance='team360-meta-dev', expected_status='testing', expected_events=164,
            evidence_ref=str(evidence))
        exclusive = admin.require_exclusive(conn,'team360-meta-dev',CHANNELS[1])
        fd = os.open(backup_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream: json.dump({'row':old,'evidence':str(evidence),
            'rollback':'Restore only this channel status from inactive to testing after rechecking owner authorization and routing.'},stream,default=str,indent=2)
        conn.commit()
    after = observe()
    assert before['history'] == after['history']
    assert before['config_sha256'] == after['config_sha256']
    assert after['bindings'][0]['status'] == 'inactive'
    result = dict(historical_binding_inactive=True,all_events_byte_equivalent=True,
        counts=[164,1335],telchi_operative_exclusive=True,exclusive_binding=exclusive,
        before=before,after=after,rollback_record=str(backup_path),real_messages_sent=0,meta_calls=0)
    (OUT/'deactivation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('HISTORICAL_BINDING_INACTIVE=YES HISTORY_DIGESTS_UNCHANGED=YES TELCHI_OPERATIVE_EXCLUSIVE=YES')

if __name__ == '__main__': main()

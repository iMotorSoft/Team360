"""Offline measured trace/schema/baseline consistency gate; no external calls."""
import json
from .run_profile import OUT, save


def validate():
    baseline=json.loads((OUT.parent/'telchi-datalake-sql-v1/latency-20261008-122518/final-verification.json').read_text())
    assert baseline['status']=='PASS' and baseline['n']==10
    first=baseline['samples'][0]['result']
    required={'foundation_resolution','attachment_open_including_catalog_session','duckdb_connect',
              'duckdb_sql_execute','query_preparation','fetch','materialization','attachment_connection_close'}
    samples=[]
    for name in ['direct','messaging-local']:
        group=json.loads((OUT/(name+'.json')).read_text())
        assert len(group)==10
        samples+=group
        for result in group:
            assert result['read_only'] and not result['sap_accessed']
            for key in ['result_hash','query_hash','executed_sql_hash','foundation_publication_id','ducklake_snapshot_id']:
                assert result[key]==first[key],key
            profile=result['profile']
            assert profile['schema']=='telchi-pre-sql-profile-v1'
            spans=profile['spans']
            assert required <= {s['label'] for s in spans}
            for s in spans:
                assert 0 <= s['start_ms'] <= s['end_ms'] <= profile['total_ms']
                assert abs(s['end_ms']-s['start_ms']-s['duration_ms']) < .00001
            assert profile['parent']['spawn_ms'] > 0
            assert profile['parent']['worker_entry_ms'] >= profile['parent']['spawn_ms']
            if name=='messaging-local':
                m=result['messaging_profile']
                assert m['pre_send_ms'] >= max(s['end_ms'] for s in m['spans'])
    plan=json.loads((OUT/'explain-analyze.json').read_text())
    assert plan['foundation']==first['foundation_publication_id'] and plan['snapshot']==first['ducklake_snapshot_id']
    assert plan['engine']=='DuckDB / DuckLake' and not plan['postgres_business_sql']
    save('offline-verification.json',{'status':'PASS','samples':len(samples),
         'monotonic_spans':True,'same_query_pins_and_result_as_real_whatsapp_baseline':True,
         'new_whatsapp_validation':False})
    print('OFFLINE_EVIDENCE=PASS')


if __name__=='__main__':
    validate()

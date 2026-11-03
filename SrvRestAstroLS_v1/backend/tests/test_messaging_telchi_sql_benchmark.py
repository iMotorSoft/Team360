from copy import deepcopy

import pytest

from modules.messaging.telchi_sql_benchmark import report


def row(offset=0):
    return {'id':'out-secret-id','thread_id':'thread-secret-id','correlation_id':'in-secret-id',
            'provider_message_id':'provider-secret-id','direction':'outbound','event_type':'message',
            'transport_status':'read','payload_jsonb':{
                'initial_result':'accepted','text':'Telchi result','t6_ms':offset+800,
                'timings':{'sql_gate':{'tenant':'telchi','capability':'test','query_hash':'hash',
                    'capability_started_ms':offset+200,'status':'succeeded','result':{'rows':[]},
                    'timings':{f't{i}_ms':offset+(i+1)*100 for i in range(7)}}}}}


def test_metrics_exact_sql_timestamps_delivery_and_sequential():
    result = report([row(),row(1000)],since_ms=0)
    assert result['n']==2 and result['sequential']
    assert result['metrics_ms']['sql_datalake']['p50']==100
    assert result['metrics_ms']['pre_sql']['p50']==200
    assert result['metrics_ms']['total_observable']['p95']==700
    assert 'provider-secret-id' not in str(result)
    assert result['samples'][0]['timings']['t7_ms']==800
    assert not report([row(),row(300)],since_ms=0)['sequential']


def test_missing_delivery_and_errors_not_fabricated():
    missing = row()
    missing['payload_jsonb']['t6_ms']=None
    failed = deepcopy(missing)
    failed['payload_jsonb']['timings']['sql_gate']['status']='failed'
    result = report([missing,failed],since_ms=0)
    assert result['n']==0 and result['incomplete']==1 and result['excluded_failed']==1
    assert result['metrics_ms']['sql_datalake']=={'n':0}


def test_invalid_timestamps_rejected():
    invalid = row()
    invalid['payload_jsonb']['t6_ms']=0
    with pytest.raises(ValueError):
        report([invalid],since_ms=0)

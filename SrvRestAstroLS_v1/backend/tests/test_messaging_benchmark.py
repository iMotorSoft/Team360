"""Benchmark scope preserves non-test traffic and rejects real sequence faults."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from modules.messaging.benchmark import report
from modules.messaging.providers.evolution.probes.gate_session import replay_candidate

SINCE = datetime(2026, 10, 6, tzinfo=timezone.utc)


def fixture_rows():
    rows=[]
    for n in range(1,21):
        inbound={'id':f'in-{n}', 'direction':'inbound','event_type':'message',
                 'occurred_at_utc':SINCE+timedelta(seconds=n),'provider_message_id':f'fixture-in-{n}',
                 'payload_jsonb':{'text':f'team360 ping {n:02}'}}
        timings={'t0_ms':n*10000,'t1_ms':n*10000+1,'t2_ms':n*10000+2,
                 't3_ms':n*10000+3,'t4_ms':n*10000+10,'t5_ms':n*10000+500}
        outbound={'id':f'out-{n}','direction':'outbound','event_type':'message',
                  'correlation_id':inbound['id'],'transport_status':'read',
                  'payload_jsonb':{'text':f'TEAM360 PONG {n:02}','initial_result':'accepted',
                                   'timings':timings,'t6_ms':n*10000+1000}}
        rows.extend([inbound,outbound])
    for n,text in enumerate(['hello','not a ping','team360 ping 21']):
        rows.append({'id':f'extra-{n}','direction':'inbound','event_type':'message',
                     'provider_message_id':f'fixture-extra-{n}',
                     'occurred_at_utc':SINCE+timedelta(seconds=100+n),'payload_jsonb':{'text':text}})
    return rows


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Benchmark traffic isolation tests]]
def test_non_test_texts_retained_without_hiding_duplicates_or_bad_routing():
    rows=fixture_rows()
    result=report(rows,SINCE)
    assert result['complete_20_sequential_pairs'] is True
    assert result['observed_inbound']==23 and result['inbound']==20 and result['outbound']==20
    assert result['non_test_inbound']==3 and result['non_test_outbound']==0
    assert len(result['non_test_records'])==3
    assert all('text' not in record for record in result['non_test_records'])
    assert all(metric['n']==20 for metric in result['metrics'].values())

    duplicate=deepcopy(rows[0]); duplicate['id']='another-inbound-id'; duplicate['provider_message_id']='another-provider-id'
    assert report(rows+[duplicate],SINCE)['complete_20_sequential_pairs'] is False

    reordered=deepcopy(rows)
    reordered[1]['payload_jsonb']['timings']['t0_ms']=25000
    assert report(reordered,SINCE)['complete_20_sequential_pairs'] is False

    missing_delivery=deepcopy(rows)
    missing_delivery[39]['payload_jsonb']['t6_ms']=None  # last pair has no next inbound to expose the gap
    incomplete=report(missing_delivery,SINCE)
    assert incomplete['metrics']['Team360 observable total T0→T6']['n']==19
    assert incomplete['complete_20_sequential_pairs'] is False

    misrouted=deepcopy(rows[1]); misrouted['correlation_id']='extra-0'
    invalid=report(rows+[misrouted],SINCE)
    assert invalid['complete_20_sequential_pairs'] is False
    assert invalid['non_test_outbound']==1
    assert 'non-test text unexpectedly received a reply' in invalid['violations']


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Replay candidate tests]]
def test_probe_chooses_message_with_accepted_reply_not_earlier_greeting():
    rows=fixture_rows()
    greeting=rows[-3]
    assert replay_candidate([greeting]+rows,SINCE)['id']=='in-1'
    assert replay_candidate([greeting],SINCE) is None
    assert replay_candidate(rows,SINCE+timedelta(days=1)) is None

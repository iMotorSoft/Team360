"""Separate SQL-gate evidence; never reinterpret historic Evolution timestamps."""
from __future__ import annotations

import hashlib
from modules.messaging.benchmark import stats

GATE = 'TEAM360_MESSAGING_TELCHI_DATALAKE_SQL_V1'


def _hash(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def report(rows, *, since_ms):
    samples, excluded, incomplete = [], 0, 0
    for row in rows:
        if row['direction'] != 'outbound' or row['event_type'] != 'message':
            continue
        payload = row['payload_jsonb']
        audit = payload.get('timings', {}).get('sql_gate')
        if not audit or audit.get('capability_started_ms', 0) < since_ms:
            continue
        if audit.get('status') != 'succeeded' or payload.get('initial_result') != 'accepted':
            excluded += 1
            continue
        timings = dict(audit['timings'])
        if payload.get('t6_ms') is not None:
            timings['t7_ms'] = payload['t6_ms']  # existing delivered callback, NOT phone time
        if any(timings.get(f't{i}_ms') is None for i in range(8)):
            incomplete += 1
            continue
        values = [timings[f't{i}_ms'] for i in range(8)]
        if values != sorted(values):
            raise ValueError('Non-monotonic observable SQL gate timestamps')
        durations = {name: timings[f't{end}_ms']-timings[f't{start}_ms']
            for name, start, end in [('pre_sql',0,2),('sql_datalake',2,3),('formatting_until_send',3,5),
                                    ('team360_until_send',0,5),('evolution_accept',5,6),('total_observable',0,7)]}
        result = audit['result']
        samples.append({'inbound_id_hash':_hash(row['correlation_id']), 'outbound_id_hash':_hash(row['id']),
            'thread_id_hash':_hash(row['thread_id']), 'provider_message_id_hash':_hash(row['provider_message_id']),
            'tenant':audit['tenant'], 'capability':audit['capability'], 'query_hash':audit['query_hash'],
            'timings':timings, 'durations_ms':durations, 'transport_status':row['transport_status'],
            'result':result, 'response_text':payload['text'],
            'capability_started_ms':audit['capability_started_ms']})
        profile = payload.get('timings', {}).get('pre_sql_profile')
        if profile is not None:
            samples[-1]['messaging_profile'] = profile
    samples.sort(key=lambda sample:sample['timings']['t0_ms'])
    sequential = all(previous['timings']['t7_ms'] <= current['timings']['t0_ms']
                     for previous,current in zip(samples,samples[1:]))
    metrics = {name:stats([sample['durations_ms'][name] for sample in samples])
        for name in ['pre_sql','sql_datalake','formatting_until_send','team360_until_send','evolution_accept','total_observable']}
    return {'gate':GATE, 'status':'EVIDENCE_ONLY', 'n':len(samples), 'sequential':sequential,
            'incomplete':incomplete, 'excluded_failed':excluded, 'metrics_ms':metrics, 'samples':samples,
            'notes':['T2/T3 are worker wall-clock timestamps around the fixed SELECT.',
                     'Pre-SQL includes worker startup, attachment and Foundation resolution.',
                     'T3→T5 includes worker cleanup, formatting and durable outbound intent.',
                     'T7 is local delivered callback reception, not a timestamp on the phone.',
                     'Baseline fixed p50/p95: Team360 56.37/146.04 ms; total 2516.86/2972.98 ms.',
                     'Do not subtract unmatched baseline samples to infer SQL overhead.']}

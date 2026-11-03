"""Separate Team360-only latency report from persisted receipt timestamps."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import hashlib
import math
from pathlib import Path
import statistics

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from .providers.evolution.config import EvolutionConfig
from .repository import MessagingRepository
from .settings import MessagingDevSettings
from .service import fixed_response


def stats(values):
    if not values:
        return {'n': 0}
    values = sorted(values)
    def percentile(p):
        index = (len(values)-1)*p
        low, high = math.floor(index), math.ceil(index)
        return values[low]+(values[high]-values[low])*(index-low)
    return {'n':len(values),'min':min(values),'mean':statistics.mean(values),
            'p50':percentile(.5),'p90':percentile(.9),'p95':percentile(.95),'max':max(values)}


def report(rows, since: datetime):
    observed = {str(r['id']):r for r in rows if r['event_type']=='message'
                and r['direction']=='inbound' and r['occurred_at_utc'] >= since}
    inbound = {key:row for key,row in observed.items()
               if fixed_response(row['payload_jsonb']['text']) is not None}
    other = {key:row for key,row in observed.items() if key not in inbound}
    outbound = [r for r in rows if r['event_type']=='message' and r['direction']=='outbound'
                and r['correlation_id'] in inbound]
    other_outbound = [r for r in rows if r['event_type']=='message' and r['direction']=='outbound'
                      and r['correlation_id'] in other]
    definitions = {'Team360 processing T0→T4':('t0_ms','t4_ms'),
                   'Evolution acceptance T4→T5':('t4_ms','t5_ms'),
                   'Team360 observable total T0→T6':('t0_ms','t6_ms')}
    samples = {name:[] for name in definitions}
    violations=[]
    exchanges=[]
    for row in outbound:
        payload=row['payload_jsonb']
        timings={**payload.get('timings',{}),'t6_ms':payload.get('t6_ms')}
        source=inbound[row['correlation_id']]
        text=source['payload_jsonb']['text']
        exchanges.append({'text':text,'reply':payload['text'],'status':row['transport_status'],
                          'initial_result':payload.get('initial_result'),'timings':timings})
        for name,(a,b) in definitions.items():
            if timings.get(a) is None or timings.get(b) is None:
                continue
            delta=timings[b]-timings[a]
            if delta < 0:
                violations.append('negative timestamp interval: '+name)
            else:
                samples[name].append(delta)
    exchanges.sort(key=lambda x:x['timings'].get('t0_ms',0))
    expected=[f'team360 ping {n:02}' for n in range(1,21)]
    sequence=[x['text'] for x in exchanges]
    if sequence != expected:
        violations.append('twenty exact sequential exchanges not complete')
    for previous,current in zip(exchanges,exchanges[1:]):
        delivery=previous['timings'].get('t6_ms')
        if delivery is None or current['timings']['t0_ms'] < delivery:
            violations.append('next inbound precedes previous delivery, or delivery missing')
    if len(inbound)!=20 or len(outbound)!=20:
        violations.append('benchmark ping/reply counts are not 20/20')
    if other_outbound:
        violations.append('non-test text unexpectedly received a reply')
    if any(x['reply'] != x['text'].replace('team360 ping ','TEAM360 PONG ') or
           x['initial_result']!='accepted' or x['status'] not in {'delivered','read'} for x in exchanges):
        violations.append('reply, acceptance or delivery mismatch')
    metrics={name:stats(values) for name,values in samples.items()}
    for name in ('Team360 processing T0→T4', 'Team360 observable total T0→T6'):
        if metrics[name]['n'] != 20:
            violations.append('required timing samples are not 20/20: '+name)
    return {'unit':'ms','percentiles':'linear interpolation at (N-1)*p',
            'scope':'exact fixed-response commands team360 ping 01..20; valid repeated/out-of-order commands remain violations',
            'observed_inbound':len(observed),'non_test_inbound':len(other),
            'non_test_outbound':len(other_outbound),
            'non_test_records':[{'provider_message_id_hash':hashlib.sha256(row['provider_message_id'].encode()).hexdigest(),
                                 'text_hash':hashlib.sha256(row['payload_jsonb']['text'].encode()).hexdigest(),
                                 'text_length':len(row['payload_jsonb']['text']),
                                 'received_at':row['occurred_at_utc'].isoformat()} for row in other.values()],
            'inbound':len(inbound),'outbound':len(outbound),'metrics':metrics,
            'complete_20_sequential_pairs':not violations,'violations':violations,'exchanges':exchanges,
            'baseline_evolution_ms':{'p50':2567.4,'p95':3091.8},
            'limits':['Receipt timestamps are Team360 wall-clock milliseconds; negative intervals are rejected.',
                      'T2 is after inbound commit; T4 is inside the thread immediately before sender.send_text.',
                      'T5 is local Evolution HTTP acceptance, not device delivery or Meta Graph acceptance.',
                      'T6 is local delivered callback receipt, not the device timestamp.',
                      'This report alone does not attest human WhatsApp traffic or close the adapter gate.']}


async def _run(args):
    since=datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        raise ValueError('--since must include timezone')
    settings=MessagingDevSettings.from_env()
    config=EvolutionConfig.from_env()
    repository=MessagingRepository()
    pool=create_pool(get_database_settings(min_size=1,max_size=2))
    await open_pool(pool)
    try:
        async with transaction(pool) as conn:
            binding=await repository.binding(conn,workspace_slug=settings.workspace_slug,
                channel_alias=settings.channel_alias,provider='evolution',instance=config.instance)
            rows=await repository.evidence(conn,binding)
        evidence=report(rows,since)
        target=Path(args.output)
        target.mkdir(parents=True,exist_ok=True)
        (target/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        table=['| Métrica (ms) | N | Min | Mean | p50 | p90 | p95 | Max |',
               '|---|---:|---:|---:|---:|---:|---:|---:|']
        for name,metric in evidence['metrics'].items():
            cells=[name,str(metric['n'])]+[f'{metric[k]:.2f}' if k in metric else '—'
                                        for k in ['min','mean','p50','p90','p95','max']]
            table.append('| '+' | '.join(cells)+' |')
        text='\n'.join(table)+'\n'
        (target/'report.md').write_text(text)
        print(text)
    finally:
        await close_pool(pool)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since',required=True,help='ISO receipt time with timezone; isolates the real session')
    parser.add_argument('--output',required=True,help='Separate Team360 evidence directory')
    asyncio.run(_run(parser.parse_args()))

"""Independent PostgreSQL read and final statistics, no sends or SQL workload."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
BACKEND=ROOT/'SrvRestAstroLS_v1/backend'
os.chdir(BACKEND)
sys.path.insert(0,str(BACKEND))
from dotenv import load_dotenv
load_dotenv(BACKEND.parent/'.env.backend-dev.local',override=True)
os.environ['TEAM360_MESSAGING_DEV_SQL_TENANT']='telchi'
from modules.db.pool import create_pool,open_pool,close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.repository import MessagingRepository
from modules.messaging.settings import MessagingDevSettings
from modules.messaging.providers.evolution.config import EvolutionConfig
from modules.messaging.telchi_sql_benchmark import report
from modules.messaging.benchmark import stats
from modules.telchi.datalake.messaging_sales_query import CAPABILITY,QUERY_HASH
from modules.messaging.telchi_sql import format_sales

async def main():
    session=json.loads((OUT/'session/session.json').read_text())
    since=datetime.fromisoformat(session['since']).timestamp()*1000
    pool=create_pool(get_database_settings(min_size=1,max_size=2))
    try:
        await open_pool(pool)
        repo=MessagingRepository()
        settings=MessagingDevSettings.from_env()
        config=EvolutionConfig.from_env()
        async with transaction(pool) as conn:
            binding=await repo.binding(conn,workspace_slug=settings.workspace_slug,channel_alias=settings.channel_alias,provider='evolution',instance=config.instance)
            rows=await repo.evidence(conn,binding)
    finally:
        await close_pool(pool)
    evidence=report(rows,since_ms=since)
    ins=[r for r in rows if r['direction']=='inbound' and r['event_type']=='message'
         and r['payload_jsonb'].get('sql_gate',{}).get('capability_started_ms',0)>=since]
    outs=[r for r in rows if r['direction']=='outbound' and r['event_type']=='message'
          and r['payload_jsonb'].get('timings',{}).get('sql_gate',{}).get('capability_started_ms',0)>=since]
    samples=evidence['samples']
    checks={
        'ten_inbounds':len(ins)==10,'ten_outbounds':len(outs)==10,'ten_delivered':evidence['n']==10,
        'ten_read':all(r['transport_status']=='read' for r in outs),
        'all_hola_authorized':all(r['payload_jsonb']['text'].strip().lower()=='hola' and r['payload_jsonb']['sender']==settings.authorized_sender for r in ins),
        'unique_inbound_provider_ids':len({r['provider_message_id'] for r in ins})==10,
        'unique_outbound_provider_ids':len({r['provider_message_id'] for r in outs})==10,
        'one_persistent_thread':len({str(r['thread_id']) for r in ins+outs})==1,
        'same_thread_as_n1':bool(samples) and samples[0]['thread_id_hash']==json.loads((OUT.parent/'runtime-20261008-121608/session/evidence.json').read_text())['samples'][0]['thread_id_hash'],
        'one_reply_per_inbound':{str(r['id']) for r in ins}=={str(r['correlation_id']) for r in outs},
        'sequential':evidence['sequential'],'no_failed_or_incomplete':evidence['excluded_failed']==0 and evidence['incomplete']==0,
        'real_sql_fixed_capability':all(s['capability']==CAPABILITY and s['query_hash']==QUERY_HASH and s['result']['sql_duration_ms']>0 and bool(s['result']['executed_sql_hash']) for s in samples),
        'telchi_foundation_read_only':all(s['tenant']=='telchi' and s['result']['read_only'] is True and s['result']['sap_accessed'] is False and s['result']['foundation_publication_id']=='foundation_afd08d9eca6a725be53cdc3f9d5709c9' for s in samples),
        'responses_formatted_from_sql_results':all(format_sales(s['result'])==s['response_text'] for s in samples),
        'distinct_sql_executions':len({s['result']['sql_started_ms'] for s in samples})==10,
        'duplicate_replay_no_new_events':session['duplicate_replay_no_new_events'] and session['duplicate_replays']==10,
        'backend_closed_only_after_ten':session['n_delivered']==10 and not session['runtime_active'] and session['own_processes_left_running']==0,
        'historical_evidence_preserved':hashlib.sha256((OUT.parent/'runtime-20261008-121608/final-verification.json').read_bytes()).hexdigest()=='db82fdb71cf6dcedc4bd4919dfa1a5febd00d54828735acccab07991e13ed5b7',
    }
    assert all(checks.values()),checks
    result={'gate':'TEAM360_MESSAGING_TELCHI_DATALAKE_SQL_LATENCY_V1','status':'PASS',
            'branch':'feature/console-backend-core','verified_at':datetime.now(timezone.utc).isoformat(),
            'verification':'Independent post-session PostgreSQL read using existing repository; no new messages/queries to Data Lake',
            'checks':checks,'no_ia':'Unchanged deterministic adapter and fixed SELECT; no LLM imports/calls in executed path',
            'n':10,'all_metrics_ms':evidence['metrics_ms'],
            'warm_n':9,'warm_metrics_ms':{k:stats([s['durations_ms'][k] for s in samples[1:]]) for k in evidence['metrics_ms']},
            'samples':samples,'percentiles':'linear interpolation (N-1)*p',
            'limitations':['Preflight executed fixed SQL before message 1: not a pure cold Data Lake/cache sample.',
                           'New subprocess and read-only DuckLake attachment on every call: module load/SQL connection initialization recur.',
                           'T7 is local delivered callback, not handset timestamp.',
                           'Pre-SQL cannot be split into imports, attachment and Foundation resolution with current timestamps.',
                           'Shared host load not controlled; small N does not prove capacity or production readiness.']}
    (OUT/'final-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'latency.json').write_text(json.dumps({k:result[k] for k in ['gate','status','n','all_metrics_ms','warm_n','warm_metrics_ms','samples','percentiles','limitations']},indent=2)+'\n')
    text=[]
    for label,metrics in [('N=10',result['all_metrics_ms']),('warm N=9',result['warm_metrics_ms'])]:
        text.append(label+' (seconds)')
        for k,m in metrics.items(): text.append(k+' '+ ' '.join(f'{v}={m[v]/1000:.3f}' for v in ['min','mean','p50','p90','p95','max']))
    for i,s in enumerate(samples,1): text.append(str(i)+' '+ ' '.join(f'{k}={v/1000:.3f}' for k,v in s['durations_ms'].items()))
    (OUT/'report.txt').write_text('\n'.join(text)+'\n')
    print('\n'.join(text))
    print('INDEPENDENT_VERIFICATION=PASS')

asyncio.run(main())

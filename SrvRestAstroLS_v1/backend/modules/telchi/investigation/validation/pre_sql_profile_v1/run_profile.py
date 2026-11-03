"""Sequential read-only Foundation N=10 and isolated PG/ASGI Messaging N=10.
Run from backend with uv run --no-sync python -m modules.telchi.investigation.validation.pre_sql_profile_v1.run_profile
No external sender, service startup, SAP access or Foundation writes.
"""
import asyncio
import json
import os
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[5]
ROOT = BACKEND.parent.parent
OUT = ROOT/'data/reports/messaging/telchi-datalake-pre-sql-profile-v1'


def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, default=str)+'\n')


def stats(values):
    ordered = sorted(values)
    def q(p):
        x = (len(ordered)-1)*p
        low = int(x)
        return ordered[low]+(ordered[min(low+1,len(ordered)-1)]-ordered[low])*(x-low)
    return dict(n=len(values), min=min(values), mean=statistics.mean(values),
                p50=q(.5), p90=q(.9), p95=q(.95), max=max(values))


def summary(samples):
    groups = {}
    for sample in samples:
        per_sample = {}
        for s in sample['profile']['spans']:
            per_sample[s['label']] = per_sample.get(s['label'],0)+s['duration_ms']
        per_sample['worker_entry'] = sample['profile']['parent']['worker_entry_ms']
        per_sample['spawn'] = sample['profile']['parent']['spawn_ms']
        per_sample['worker_total'] = sample['profile']['parent']['total_ms']
        per_sample['ipc_exit_decode_residual'] = sample['profile']['parent']['ipc_exit_decode_residual_ms']
        if 'messaging_profile' in sample:
            for s in sample['messaging_profile']['spans']:
                per_sample[s['label']] = per_sample.get(s['label'],0)+s['duration_ms']
            per_sample['pre_send'] = sample['messaging_profile']['pre_send_ms']
        for k,v in per_sample.items():
            groups.setdefault(k,[]).append(v)
    return {k:stats(v) for k,v in groups.items()}


async def main():
    from modules.telchi.datalake.messaging_sales_query import query_fixed_sales, SQL_TEMPLATE, PERIOD_FROM, PERIOD_TO_EXCLUSIVE
    from modules.telchi.datalake.ducklake import DuckLakeConnector
    from modules.telchi.datalake.foundation_reader import FoundationReader
    from modules.telchi.datalake.query_profile import Trace
    # Preflight does NOT execute the analytical capability before sample #1.
    from modules.db.pool import create_pool, open_pool, close_pool, set_pool
    from modules.db.settings import get_database_settings
    from modules.db.transaction import transaction
    from modules.messaging.repository import MessagingRepository
    pool = create_pool(get_database_settings(min_size=1,max_size=2,connect_timeout=5))
    await open_pool(pool)
    set_pool(pool)
    binding = None
    repo = MessagingRepository()
    try:
        async with transaction(pool) as conn:
            row = await (await conn.execute('SELECT 1 AS ok')).fetchone()
            assert row['ok']==1
        save('preflight.json', {'postgres': 'PASS','llm_used':False,'sap_used':False,
             'foundation_before_sample_1':'not queried by this runner; prior host use/cache unknown',
             'modules_loaded_in_parent':True,'worker_modules':'new process every sample',
             'n':10,'concurrency':1,'threads':2})
        direct=[]
        for i in range(10):
            result=await query_fixed_sales()
            assert result['read_only'] and not result['sap_accessed']
            direct.append(result)
            save('direct.json',direct)
            print('DIRECT',i+1,round(result['profile']['parent']['total_ms'],2),flush=True)
        assert len({r['result_hash'] for r in direct})==1
        save('direct-summary.json',summary(direct))
        # Exact engine/query/parameters/pins. EXPLAIN is extra work, not a timed sample.
        trace=Trace()
        with trace.activate():
            connector=DuckLakeConnector()
            with connector.session(read_only=True) as con:
                con.execute('SET threads=2')
                con.execute("SET memory_limit='512MB'")
                con.execute("SET max_temp_directory_size='0B'")
                access=FoundationReader(connector).resolve_on(con)
                sql=SQL_TEMPLATE.format(documents=access.sales('sales_document'),lines=access.sales('sales_line'))
                plan=con.execute('EXPLAIN (ANALYZE, FORMAT JSON) '+sql,[PERIOD_FROM,PERIOD_TO_EXCLUSIVE]).fetchall()
                save('explain-analyze.json',{'engine':'DuckDB / DuckLake','postgres_business_sql':False,
                    'sql':sql,'parameters':[PERIOD_FROM,PERIOD_TO_EXCLUSIVE],
                    'foundation':access.foundation_publication_id,'snapshot':access.ducklake_snapshot_id,
                    'plan':[{ 'key':r[0],'value':json.loads(r[1])} for r in plan]})
                con.execute("SET profiling_mode='detailed'")
                detailed=con.execute('EXPLAIN (ANALYZE, FORMAT JSON) '+sql,[PERIOD_FROM,PERIOD_TO_EXCLUSIVE]).fetchall()
                save('explain-detailed.json',json.loads(detailed[0][1]))
        save('explain-setup-profile.json',trace.export())
        # Real HTTP/controller/repository/pool; isolated workspace, fake output port only.
        import httpx
        from modules.messaging.dev_app import create_app
        from modules.messaging.webhooks import evolution_whatsapp as webhook
        workspace='profile-'+uuid4().hex
        from modules.messaging.providers.evolution.config import EvolutionConfig
        config=EvolutionConfig.from_env()
        async with transaction(pool) as conn:
            await conn.execute("INSERT INTO core_workspaces(slug,display_name,status) VALUES (%s,'Profile fixture','testing')",(workspace,))
            binding=await repo.provision_dev_channel(conn,workspace_slug=workspace,channel_alias='profile',provider='evolution',instance=config.instance)
        class Sender:
            count=0
            def send_text(self,**kwargs):
                self.count+=1
                return SimpleNamespace(external_message_id='profile-out-'+str(self.count))
        sender=Sender()
        env={'TEAM360_MESSAGING_WORKSPACE_SLUG':workspace,'TEAM360_MESSAGING_CHANNEL_ALIAS':'profile',
             'TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER':'15550000001','TEAM360_MESSAGING_DEV_SQL_TENANT':'telchi'}
        local=[]
        with patch.dict(os.environ,env), patch.object(webhook,'EvolutionProvider',lambda config:sender):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://profile.local') as client:
                for i in range(10):
                    payload={'event':'messages.upsert','instance':config.instance,
                      'data':{'key':{'id':'profile-in-'+str(i),'remoteJid':'15550000001@s.whatsapp.net','fromMe':False},
                              'message':{'conversation':'hola'}}}
                    response=await client.post('/webhooks/messaging/evolution/whatsapp',json=payload,
                        headers={'x-team360-webhook-token':os.environ['TEAM360_MESSAGING_WEBHOOK_TOKEN']})
                    assert response.status_code==200 and response.json()['results']=={'accepted':1}
                    async with transaction(pool) as conn:
                        rows=await repo.evidence(conn,binding)
                    outbound=next(r for r in rows if r['provider_message_id']=='profile-out-'+str(i+1))
                    timings=outbound['payload_jsonb']['timings']
                    result=timings['sql_gate']['result']
                    result['messaging_profile']=timings['pre_sql_profile']
                    local.append(result)
                    save('messaging-local.json',local)
                    print('LOCAL',i+1,round(result['messaging_profile']['pre_send_ms'],2),flush=True)
        assert sender.count==10 and len({r['result_hash'] for r in local+direct})==1
        save('messaging-local-summary.json',summary(local))
    finally:
        if binding:
            async with transaction(pool) as conn:
                for table in ['message_events','message_threads','communication_channels']:
                    await conn.execute('DELETE FROM '+table+' WHERE workspace_id=%s',(binding.workspace_id,))
                await conn.execute('DELETE FROM core_workspaces WHERE id=%s',(binding.workspace_id,))
        await close_pool(pool)
        save('runner-cleanup.json',{'pool_closed':True,'fixture_deleted':binding is not None,
             'external_sends':0,'services_started':0,'workers':'communicate/reaped per sample',
             'unrelated_processes_terminated':0})


if __name__=='__main__':
    load_dotenv(BACKEND.parent/'.env.backend-dev.local',override=True)
    os.environ['TEAM360_TELCHI_PRE_SQL_PROFILE']='1'
    try:
        asyncio.run(main())
    except Exception as exc:
        save('runner-error.json',{'class':type(exc).__name__,'layer':'see last completed evidence; no exception text saved'})
        print('BLOCKED',type(exc).__name__,flush=True)
        raise SystemExit(2)

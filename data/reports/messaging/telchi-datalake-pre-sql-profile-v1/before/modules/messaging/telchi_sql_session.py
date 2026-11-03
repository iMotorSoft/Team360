"""Bounded SQL gate real-human session, only own backend + temporary local webhook.

From backend, private env loaded:
TEAM360_MESSAGING_DEV_SQL_TENANT=telchi uv run --no-sync python -m \
modules.messaging.telchi_sql_session --host <Podman-host-IP> --output <new-report-dir>

Evolution and its Meta ingress must already be operational. No proactive sends,
no infrastructure restart/subscription changes, no historical benchmark writes.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

import httpx

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.repository import MessagingRepository
from modules.messaging.settings import MessagingDevSettings
from modules.messaging.providers.evolution.config import EvolutionConfig
from modules.messaging.telchi_sql_benchmark import GATE, report

BACKEND = Path(__file__).resolve().parents[2]
WEBHOOK = '/webhooks/messaging/evolution/whatsapp'


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, default=str)+'\n')
    temp.replace(path)


async def run(args):
    settings, config = MessagingDevSettings.from_env(), EvolutionConfig.from_env()
    if settings.telchi_tenant != 'telchi':
        raise ValueError('Explicit authorized DEV sender→telchi mapping required')
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    since_ms = time.time_ns()/1_000_000
    deadline = time.monotonic()+args.duration
    state = {'gate':GATE, 'status':'BLOCKED', 'since':datetime.now(timezone.utc).isoformat(),
             'layer':'preflight', 'n_target':args.count, 'backend_owned':False,
             'own_processes_left_running':0}
    pool, process, previous, configured = None, None, None, False
    repo = MessagingRepository()
    api = httpx.Client(base_url=config.base_url, headers={'apikey':config.api_key}, timeout=15, trust_env=False)
    local = httpx.Client(base_url=f'http://{args.host}:{args.port}', timeout=40, trust_env=False)
    log = (directory/'backend.log').open('a')
    def call(method, path, body=None):
        response = api.request(method,path,json=body)
        response.raise_for_status()
        return response.json()
    def post(payload):
        response = local.post(WEBHOOK,json=payload,headers={'x-team360-webhook-token':settings.webhook_token})
        response.raise_for_status()
        return response.json()['results']
    def inbound(id, text, sender):
        return {'event':'messages.upsert','instance':config.instance,
                'data':{'key':{'id':id,'remoteJid':sender+'@s.whatsapp.net','fromMe':False},
                        'message':{'conversation':text}}}
    async def rows():
        async with transaction(pool) as conn:
            return await repo.evidence(conn,binding)
    try:
        state['layer'] = 'Evolution transport'
        connection = call('GET','/instance/connectionState/'+config.instance)
        if connection.get('instance',{}).get('state') != 'open':
            raise RuntimeError('Evolution instance not open')
        previous = call('GET','/webhook/find/'+config.instance)
        if previous and previous.get('enabled'):
            raise RuntimeError('Refuse to overwrite an active local webhook')
        state['layer'] = 'Team360 PostgreSQL'
        pool = create_pool(get_database_settings(min_size=1,max_size=2))
        await open_pool(pool)
        async with transaction(pool) as conn:
            binding = await repo.binding(conn,workspace_slug=settings.workspace_slug,
                channel_alias=settings.channel_alias,provider='evolution',instance=config.instance)
        state['layer'] = 'Telchi Data Lake'
        from modules.telchi.datalake.messaging_sales_query import query_fixed_sales
        preflight = await query_fixed_sales()
        save(directory/'datalake-preflight.json',preflight)
        state['layer'] = 'Messaging runtime'
        env = dict(os.environ,TEAM360_DEV_PROFILE='messaging-only',TEAM360_BACKEND_HOST=args.host,
                   TEAM360_BACKEND_PORT=str(args.port))
        process = subprocess.Popen([str(BACKEND.parent/'backend-dev.sh')],env=env,
            stdout=log,stderr=subprocess.STDOUT)
        state['backend_owned'] = True
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Own backend exited')
            try:
                response = local.get('/health')
                if response.status_code==200 and response.json().get('profile')=='messaging-only':
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('Messaging health timeout')
        configured = True  # restore even if the set operation returns uncertain
        call('POST','/webhook/set/'+config.instance,{'webhook':{
            'enabled':True,'url':f'http://host.containers.internal:{args.port}{WEBHOOK}',
            'events':['MESSAGES_UPSERT','MESSAGES_UPDATE'],
            'headers':{'x-team360-webhook-token':settings.webhook_token},'byEvents':False,'base64':False}})
        # Container reachability without SQL or sending WhatsApp.
        code = "const http=require('http');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const c=JSON.parse(s),b=JSON.stringify({event:'connection.update',instance:c.instance});const r=http.request(c.url,{method:'POST',headers:{'content-type':'application/json','x-team360-webhook-token':c.token,'content-length':Buffer.byteLength(b)}},x=>{x.resume();x.on('end',()=>{if(x.statusCode!==200)process.exitCode=1})});r.on('error',()=>process.exitCode=1);r.end(b)})"
        reach = subprocess.run(['podman','exec','-i','evolution-api','node','-e',code],
            input=json.dumps({'instance':config.instance,'token':settings.webhook_token,
                             'url':f'http://host.containers.internal:{args.port}{WEBHOOK}'}),
            text=True,capture_output=True,timeout=15)
        if reach.returncode:
            raise RuntimeError('Container webhook reachability failed')
        before = await rows()
        unauthorized = settings.authorized_sender[:-1]+str((int(settings.authorized_sender[-1])+1)%10)
        assert post(inbound('sql-gate-unauthorized-'+str(int(since_ms)),'hola',unauthorized))=={'unauthorized':1}
        assert len(await rows())==len(before)
        state.update(status='WAITING_HUMAN',layer=None,unauthorized_no_persistence=True,
                     container_reachability=True,backend_pid=process.pid,
                     runtime_active=True,own_processes_left_running=1)
        save(directory/'session.json',state)
        print('Enviá "hola" desde el WhatsApp autorizado.',flush=True)
        while time.monotonic()<deadline:
            observed = await rows()
            evidence = report(observed,since_ms=since_ms)
            save(directory/'evidence.json',evidence)
            state['n_delivered'] = evidence['n']
            save(directory/'session.json',state)
            if evidence['n']>=args.count:
                if (evidence['n'] != args.count or not evidence['sequential']
                        or evidence['excluded_failed'] or evidence['incomplete']):
                    raise RuntimeError('Session not sequential/complete/successful')
                from modules.telchi.datalake.messaging_sales_query import CAPABILITY, QUERY_HASH
                for sample in evidence['samples']:
                    result = sample['result']
                    if (sample['tenant'] != 'telchi' or sample['capability'] != CAPABILITY
                            or sample['query_hash'] != QUERY_HASH or result.get('read_only') is not True
                            or result.get('sap_accessed') is not False):
                        raise RuntimeError('SQL gate capability/tenant/read-only evidence mismatch')
                accepted = {str(r['correlation_id']) for r in observed if r['direction']=='outbound'
                    and r['event_type']=='message' and r['payload_jsonb'].get('timings',{}).get('sql_gate')}
                candidates = [r for r in observed if r['direction']=='inbound' and str(r['id']) in accepted
                    and r['payload_jsonb'].get('sql_gate',{}).get('capability_started_ms',0)>=since_ms]
                for row in candidates:
                    assert post(inbound(row['provider_message_id'],row['payload_jsonb']['text'],settings.authorized_sender))=={'duplicate':1}
                assert len(await rows())==len(observed)
                state.update(status='PASS',duplicate_replay_no_new_events=True,
                             duplicate_replays=len(candidates),layer=None)
                save(directory/'session.json',state)
                break
            await asyncio.sleep(2)
    except Exception as exc:
        # Never save exception repr/tracebacks: HTTP/driver errors may contain secrets.
        state.update(status='BLOCKED',error_class=type(exc).__name__)
    finally:
        if configured:
            try:
                call('POST','/webhook/set/'+config.instance,{'webhook':{
                    'enabled':bool((previous or {}).get('enabled')),
                    'url':(previous or {}).get('url') or f'http://host.containers.internal:{args.port}{WEBHOOK}',
                    'events':(previous or {}).get('events') or ['MESSAGES_UPSERT','MESSAGES_UPDATE'],
                    'headers':(previous or {}).get('headers') or {},'byEvents':False,'base64':False}})
                state['webhook_restored'] = True
            except Exception:
                state.update(status='BLOCKED',layer='Evolution webhook restoration',webhook_restored=False)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        state['own_processes_left_running'] = 0 if process is None or process.poll() is not None else 1
        state['runtime_active'] = False
        if state['status'] == 'WAITING_HUMAN':
            state.update(status='BLOCKED',layer='real human traffic not completed before session expiry')
        if pool is not None:
            await close_pool(pool)
        api.close(); local.close(); log.close()
        save(directory/'session.json',state)
    print(json.dumps(state,indent=2))
    return 0 if state['status']=='PASS' else 2


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--port',type=int,default=18181)
    parser.add_argument('--duration',type=int,default=900)
    parser.add_argument('--count',type=int,choices=[1,10],default=1)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    if not 1<=args.duration<=1800 or not 1<=args.port<=65535:
        parser.error('Bounded duration/valid port required')
    raise SystemExit(asyncio.run(run(args)))

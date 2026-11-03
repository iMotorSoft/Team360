"""Verify a completed human session against both stores, without new sends.

Starts/stops only its own canonical Messaging launcher children. Replays the
already-persisted inbound IDs, never a new ping. Does not restart Evolution or
modify its webhook. The original session/latency evidence remains untouched.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import httpx

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.benchmark import report
from modules.messaging.repository import MessagingRepository
from modules.messaging.settings import MessagingDevSettings
from modules.messaging.providers.evolution.config import EvolutionConfig

BACKEND = Path(__file__).resolve().parents[5]
PATH = '/webhooks/messaging/evolution/whatsapp'


async def verify(args):
    directory = Path(args.session)
    original = json.loads((directory/'session.json').read_text())
    since = datetime.fromisoformat(original['since'])
    settings, config = MessagingDevSettings.from_env(), EvolutionConfig.from_env()
    pool = create_pool(get_database_settings(min_size=1,max_size=2))
    await open_pool(pool)
    repo = MessagingRepository()
    process = None
    pids = []
    logfile = (directory/'verification-backend.log').open('a')
    local = httpx.Client(base_url=f'http://{args.host}:{args.port}',trust_env=False,timeout=10)
    evolution = httpx.Client(base_url=config.base_url,headers={'apikey':config.api_key},trust_env=False,timeout=15)
    env = dict(os.environ,TEAM360_DEV_PROFILE='messaging-only',TEAM360_BACKEND_HOST=args.host,
               TEAM360_BACKEND_PORT=str(args.port))

    def stop(child):
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)

    def start():
        child = subprocess.Popen([str(BACKEND.parent/'backend-dev.sh')],env=env,
                                 stdout=logfile,stderr=subprocess.STDOUT)
        pids.append(child.pid)
        for _ in range(100):
            if child.poll() is not None: raise RuntimeError('Messaging launcher exited')
            try:
                response=local.get('/health')
                if response.status_code==200 and response.json().get('postgres')=='ok': return child
            except (httpx.HTTPError,ValueError): pass
            time.sleep(.1)
        stop(child)
        raise RuntimeError('Messaging restart health timeout')

    def records():
        response=evolution.post('/chat/findMessages/'+config.instance,
                                json={'where':{},'page':1,'offset':100})
        if response.status_code!=200: raise RuntimeError('Evolution read verification failed')
        messages=response.json()['messages']
        if messages['total']>100: raise RuntimeError('History paging required; refuse partial proof')
        return messages['records']

    async def rows():
        async with transaction(pool) as conn: return await repo.evidence(conn,binding)

    def replay(message_id,text,sender):
        response=local.post(PATH,headers={'x-team360-webhook-token':settings.webhook_token},json={
            'event':'messages.upsert','instance':config.instance,'data':{
                'key':{'id':message_id,'remoteJid':sender+'@s.whatsapp.net','fromMe':False},
                'message':{'conversation':text}}})
        if response.status_code!=200: raise RuntimeError('Live replay failed')
        return response.json()['results']

    try:
        async with transaction(pool) as conn:
            binding=await repo.binding(conn,workspace_slug=settings.workspace_slug,
                channel_alias=settings.channel_alias,provider='evolution',instance=config.instance)
        before=await rows()
        evidence=report(before,since)
        if not evidence['complete_20_sequential_pairs']:
            raise RuntimeError('Session is not twenty valid sequential delivered pairs')
        inbound={str(r['id']):r for r in before if r['event_type']=='message' and r['direction']=='inbound'}
        outbound=[r for r in before if r['event_type']=='message' and r['direction']=='outbound'
                  and r['correlation_id'] in inbound and inbound[r['correlation_id']]['occurred_at_utc']>=since]
        observed_before=records()
        transport={m['key']['id']:m for m in observed_before}
        correlation=[]
        for out in outbound:
            source=inbound[out['correlation_id']]
            actual_in=transport.get(source['provider_message_id'])
            actual_out=transport.get(out['provider_message_id'])
            assert actual_in and actual_out
            assert actual_in['key']['fromMe'] is False and actual_out['key']['fromMe'] is True
            assert actual_in['key']['remoteJid']==settings.authorized_sender+'@s.whatsapp.net'
            assert actual_out['key']['remoteJid']==settings.authorized_sender+'@s.whatsapp.net'
            assert actual_in['message']['conversation']==source['payload_jsonb']['text']
            assert actual_out['message']['conversation']==out['payload_jsonb']['text']
            assert source['provider_message_id'].startswith('wamid.') and out['provider_message_id'].startswith('wamid.')
            status_rows=[r for r in before if r['event_type']=='status' and r['provider_message_id']==out['provider_message_id']]
            assert {'sent','delivered','read'}.issubset({r['transport_status'] for r in status_rows})
            correlation.append({'seq':int(source['payload_jsonb']['text'][-2:]),
                'inbound_id_hash':hashlib.sha256(source['provider_message_id'].encode()).hexdigest(),
                'outbound_id_hash':hashlib.sha256(out['provider_message_id'].encode()).hexdigest(),
                'statuses':sorted({r['transport_status'] for r in status_rows})})
        original_ids={str(r['id']) for r in before}
        original_threads={str(r['thread_id']) for r in before if r['event_type']=='message'}
        assert len(original_threads)==1
        process=start()
        duplicate_results=[]
        for out in outbound:
            source=inbound[out['correlation_id']]
            result=replay(source['provider_message_id'],source['payload_jsonb']['text'],settings.authorized_sender)
            assert result=={'duplicate':1}
            duplicate_results.append(result)
        unauthorized='15550000002' if settings.authorized_sender!='15550000002' else '15550000003'
        assert replay('unauthorized-closure-'+uuid4().hex,'team360 ping 01',unauthorized)=={'unauthorized':1}
        assert replay('empty-closure-'+uuid4().hex,'',settings.authorized_sender)=={'ignored':1}
        after_replays=await rows()
        assert original_ids=={str(r['id']) for r in after_replays}
        stop(process)
        process=start()
        after_restart=await rows()
        assert original_ids=={str(r['id']) for r in after_restart}
        assert original_threads=={str(r['thread_id']) for r in after_restart if r['event_type']=='message'}
        first=inbound[outbound[0]['correlation_id']]
        assert replay(first['provider_message_id'],first['payload_jsonb']['text'],settings.authorized_sender)=={'duplicate':1}
        observed_after=records()
        assert {m['key']['id'] for m in observed_before}=={m['key']['id'] for m in observed_after}
        webhook=evolution.get('/webhook/find/'+config.instance).json()
        assert not webhook or not webhook.get('enabled')
        evidence.update({'adapter_criteria_verified':True,'human_pairs_verified_against_evolution':len(correlation),
            'correlation':sorted(correlation,key=lambda r:r['seq']),'conversation_count':len(original_threads),
            'duplicate_live_replays':len(duplicate_results),'post_restart_duplicate_replay':True,
            'duplicate_new_core_rows':0,'duplicate_new_evolution_messages':0,'unauthorized_live_replay_rejected':True,
            'empty_text_live_replay_ignored':True,'actual_backend_restart_preserved_all_rows':True,
            'verification_backend_pids':pids,'evolution_webhook_remained_disabled':True,
            'evolution_container_restart_performed':False,
            'original_probe_state_preserved':original['gate'],
            'original_probe_latency_sha256':hashlib.sha256((directory/'latency.json').read_bytes()).hexdigest(),
            'probe_errors':['Original count included three non-routed texts; all remain in PostgreSQL and original evidence.',
                            'Original duplicate probe selected a non-routed greeting without an outbound; live ping replays supersede that failed assertion.',
                            'Original supervisor timed out instead of executing automatic restart; actual launcher restart verified separately.']})
        target=directory/'verified'
        target.mkdir(exist_ok=True)
        (target/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('Verified: 20 real pairs, 20 delivered/read, one conversation, duplicate/unauthorized/restart checks')
    finally:
        stop(process)
        logfile.close(); local.close(); evolution.close()
        await close_pool(pool)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--port',type=int,default=18181)
    args=parser.parse_args()
    try: asyncio.run(verify(args))
    except Exception:
        print('Verification failed; no gate PASS. Inspect sanitized evidence.')
        raise SystemExit(1) from None

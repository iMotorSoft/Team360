"""Bounded DEV real-traffic gate session; owns only its launcher child and webhook.

Run from backend with existing private environment loaded. No active webhook is
replaced. Duration expiry restores a disabled/prior local webhook and stops only
the backend process created here. This probe never generates a new ping/reply.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import signal
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


def replay_candidate(rows, since):
    """Only a routed, accepted benchmark message is eligible for reply dedup proof."""
    accepted = {r['correlation_id'] for r in rows if r['event_type']=='message'
                and r['direction']=='outbound' and r['payload_jsonb'].get('initial_result')=='accepted'}
    return next((r for r in rows if r['event_type']=='message' and r['direction']=='inbound'
                 and r['occurred_at_utc'] >= since and str(r['id']) in accepted), None)


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


async def run(args):
    settings, config = MessagingDevSettings.from_env(), EvolutionConfig.from_env()
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    since = datetime.now(timezone.utc)
    deadline = since + timedelta(seconds=args.duration)
    state = {'gate':'WAITING_HUMAN','since':since.isoformat(),'expires_at':deadline.isoformat(),
             'profile':'messaging-only','real_inbound':0,'accepted_outbound':0,'delivered_outbound':0,
             'duplicate_replay':None,'unauthorized_replay':None,'backend_restart':None}
    info = directory / 'session.json'
    repo = MessagingRepository()
    pool = create_pool(get_database_settings(min_size=1, max_size=2))
    await open_pool(pool)
    process = None
    previous = None
    configured = False
    log = (directory / 'backend.log').open('a')
    client = httpx.Client(base_url=config.base_url, headers={'apikey':config.api_key}, trust_env=False, timeout=15)
    local = httpx.Client(base_url=f'http://{args.host}:{args.port}', trust_env=False, timeout=15)
    callback_url = f'http://host.containers.internal:{args.port}{PATH}'
    env = dict(os.environ, TEAM360_DEV_PROFILE='messaging-only', TEAM360_BACKEND_HOST=args.host,
               TEAM360_BACKEND_PORT=str(args.port))

    def api(method, path, body=None):
        response = client.request(method, path, json=body)
        if response.status_code not in {200, 201}:
            raise RuntimeError('Evolution API preflight/configuration failed')
        return response.json()

    def stop(child):
        if child is None or child.poll() is not None:
            return
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()  # only the exact child process created by this session
            child.wait(timeout=5)

    def start():
        child = subprocess.Popen([str(BACKEND.parent/'backend-dev.sh')], env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        for _ in range(100):
            if child.poll() is not None:
                raise RuntimeError('Messaging launcher exited')
            try:
                response = local.get('/health')
                if response.status_code == 200 and response.json().get('profile') == 'messaging-only':
                    return child
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(.1)
        stop(child)
        raise RuntimeError('Messaging health timeout')

    async def rows():
        async with transaction(pool) as conn:
            return await repo.evidence(conn, binding)

    def replay(payload):
        response = local.post(PATH, json=payload, headers={'x-team360-webhook-token':settings.webhook_token})
        if response.status_code != 200:
            raise RuntimeError('Webhook replay failed')
        return response.json()['results']

    try:
        async with transaction(pool) as conn:
            binding = await repo.binding(conn, workspace_slug=settings.workspace_slug,
                channel_alias=settings.channel_alias, provider='evolution', instance=config.instance)
        instance = api('GET', '/instance/connectionState/'+config.instance)
        if instance.get('instance',{}).get('state') != 'open':
            raise RuntimeError('Evolution instance not open')
        previous = api('GET', '/webhook/find/'+config.instance)
        if previous and previous.get('enabled'):
            raise RuntimeError('Refuse to overwrite an active local webhook')
        process = start()
        state['backend_pid'] = process.pid
        configured = True  # restore even if the configuration HTTP result is uncertain
        api('POST', '/webhook/set/'+config.instance, {'webhook':{
            'enabled':True,'url':callback_url,'events':['MESSAGES_UPSERT','MESSAGES_UPDATE'],
            'headers':{'x-team360-webhook-token':settings.webhook_token},'byEvents':False,'base64':False}})
        # Real container→Team360 HTTP reachability, without sending WhatsApp.
        code = "const http=require('http');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const c=JSON.parse(s);const b=JSON.stringify({event:'connection.update',instance:c.instance});const r=http.request(c.url,{method:'POST',headers:{'content-type':'application/json','x-team360-webhook-token':c.token,'content-length':Buffer.byteLength(b)}},x=>{let d='';x.on('data',v=>d+=v);x.on('end',()=>{if(x.statusCode!==200||JSON.parse(d).results.ignored!==1)process.exitCode=1})});r.on('error',()=>process.exitCode=1);r.end(b)})"
        reach = subprocess.run(['podman','exec','-i','evolution-api','node','-e',code],
            input=json.dumps({'url':callback_url,'instance':config.instance,'token':settings.webhook_token}),
            text=True,capture_output=True,timeout=15)
        if reach.returncode:
            raise RuntimeError('Evolution container cannot reach Messaging webhook')
        state['container_webhook_reachability'] = True
        state['ready'] = True
        # Synthetic unauthorized sender through the live authenticated webhook;
        # the service must reject it before persistence or any provider call.
        unauthorized = '15550000002' if settings.authorized_sender != '15550000002' else '15550000003'
        before = await rows()
        result = replay({'event':'messages.upsert','instance':config.instance,'data':{
            'key':{'id':'unauthorized-probe-'+uuid4().hex,'remoteJid':unauthorized+'@s.whatsapp.net','fromMe':False},
            'message':{'conversation':'team360 ping 01'}}})
        after = await rows()
        before_messages = {str(r['id']) for r in before if r['event_type']=='message'}
        after_messages = {str(r['id']) for r in after if r['event_type']=='message'}
        state['unauthorized_replay'] = result == {'unauthorized':1} and before_messages == after_messages
        if not state['unauthorized_replay']:
            raise RuntimeError('Unauthorized identity was not rejected')
        atomic_json(info,state)
        print('READY: send team360 ping 01..20 sequentially; session is time-bounded',flush=True)

        while datetime.now(timezone.utc) < deadline:
            if process.poll() is not None:
                raise RuntimeError('Messaging backend exited during session')
            evidence_rows = await rows()
            evidence = report(evidence_rows, since)
            state.update(real_inbound=evidence['inbound'], accepted_outbound=evidence['outbound'],
                delivered_outbound=sum(x['timings'].get('t6_ms') is not None for x in evidence['exchanges']))
            if evidence['exchanges'] and state['duplicate_replay'] is None:
                inbound = replay_candidate(evidence_rows, since)
                if inbound is None:
                    await asyncio.sleep(1)
                    continue
                same = {'event':'messages.upsert','instance':config.instance,'data':{
                    'key':{'id':inbound['provider_message_id'],'remoteJid':settings.authorized_sender+'@s.whatsapp.net','fromMe':False},
                    'message':{'conversation':inbound['payload_jsonb']['text']}}}
                duplicate = replay(same)
                current = await rows()
                inbound_count = sum(r['event_type']=='message' and r['direction']=='inbound'
                                    and r['provider_message_id']==inbound['provider_message_id'] for r in current)
                reply_count = sum(r['event_type']=='message' and r['direction']=='outbound'
                                  and r['correlation_id']==str(inbound['id']) for r in current)
                state['duplicate_replay'] = duplicate == {'duplicate':1} and inbound_count == 1 and reply_count == 1
                # Replayed IDs stay private to PostgreSQL; evidence uses hash only.
                state['duplicate_inbound_id_hash'] = hashlib.sha256(inbound['provider_message_id'].encode()).hexdigest()
            atomic_json(directory/'latency.json', evidence)
            atomic_json(info, state)
            if evidence['complete_20_sequential_pairs']:
                original_ids = {str(r['id']) for r in evidence_rows}
                stop(process)
                process = start()
                state['backend_pid'] = process.pid
                restart_rows = await rows()
                state['backend_restart'] = original_ids.issubset({str(r['id']) for r in restart_rows}) and replay(same) == {'duplicate':1}
                state['gate'] = 'REAL_SESSION_COMPLETE_REVIEW_REQUIRED'
                atomic_json(info, state)
                print('Real twenty-pair session complete; inspect evidence before declaring gates',flush=True)
                break
            await asyncio.sleep(1)
        else:
            state['gate'] = 'WAITING_HUMAN_EXPIRED'
    except Exception:
        state['gate'] = 'BLOCKED'
        state['error'] = 'Runtime gate failed; inspect sanitized preflight/session evidence'
        raise RuntimeError(state['error']) from None
    finally:
        if configured:
            backup = previous or {}
            restore = {'enabled':False,'url':backup.get('url') or callback_url,'events':backup.get('events') or [],
                       'headers':backup.get('headers') or {},'byEvents':bool(backup.get('webhookByEvents')),
                       'base64':bool(backup.get('webhookBase64'))}
            try:
                api('POST','/webhook/set/'+config.instance,{'webhook':restore})
                state['local_webhook_restored_disabled'] = True
            except Exception:
                state['local_webhook_restored_disabled'] = False
        stop(process)
        state['backend_stopped'] = True
        state['ready'] = False
        atomic_json(info,state)
        log.close(); client.close(); local.close()
        await close_pool(pool)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,help='Host address resolved by host.containers.internal')
    parser.add_argument('--port',type=int,default=18181)
    parser.add_argument('--duration',type=int,default=1800)
    parser.add_argument('--output',required=True,help='New session directory, not the Evolution baseline')
    args=parser.parse_args()
    if not 60 <= args.duration <= 7200:
        parser.error('duration must be 60..7200 seconds')
    def stop_owned_session(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_owned_session)
    try:
        asyncio.run(run(args))
    except (Exception, KeyboardInterrupt):
        print('Gate session failed/interrupted; inspect sanitized session evidence', flush=True)
        raise SystemExit(1) from None

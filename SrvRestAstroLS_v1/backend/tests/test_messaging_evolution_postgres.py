"""Opt-in real Team360 PostgreSQL + loopback HTTP integration; no WhatsApp send."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
from uuid import uuid4

from litestar import Litestar
from litestar.testing import AsyncTestClient
import pytest

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.providers.evolution.mapper import normalize_events
from modules.messaging.repository import MessagingRepository
from modules.messaging.service import epoch_ms
from modules.messaging.webhooks.evolution_whatsapp import EvolutionWhatsAppWebhookController
import modules.messaging.webhooks.evolution_whatsapp as webhook

pytestmark = pytest.mark.skipif(os.getenv('TEAM360_MESSAGING_POSTGRES_TEST') != '1',
                              reason='requires Team360 PostgreSQL migration 026')
SENDER='15550000001'
TOKEN='synthetic-webhook-token-0000000000000000'


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Adapter local integration specifications]]
def test_real_postgres_http_idempotency_errors_early_status_and_recovery(monkeypatch):
    async def exercise():
        suffix=uuid4().hex
        instance='test-'+suffix
        workspace='messaging-test-'+suffix
        calls=[]
        mode={'value':'ok'}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert self.path == '/message/sendText/'+instance
                assert self.headers['apikey']=='synthetic-key'
                calls.append(body)
                message_id='synthetic-outbound-'+str(len(calls))
                behavior=mode['value']
                if behavior=='timeout': time.sleep(.2)
                code=500 if behavior=='error' else 201
                response=(b'not-json' if behavior=='invalid' else json.dumps(
                    {'key':{'id':message_id,'remoteJid':body['number']+'@s.whatsapp.net','fromMe':True}}
                ).encode())
                try:
                    self.send_response(code)
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                except (BrokenPipeError,ConnectionResetError): pass

        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        pool=create_pool(get_database_settings(min_size=1,max_size=4))
        repo=MessagingRepository()
        await open_pool(pool)
        try:
            async with transaction(pool) as conn:
                await conn.execute("INSERT INTO core_workspaces(slug,display_name,status) VALUES (%s,'Messaging integration','testing')",(workspace,))
                binding=await repo.provision_dev_channel(conn,workspace_slug=workspace,channel_alias='test-channel',
                                                        provider='evolution',instance=instance)
            values={'TEAM360_ENV':'development','TEAM360_MESSAGING_DEV_ENABLED':'1',
                    'TEAM360_EVOLUTION_BASE_URL':f'http://127.0.0.1:{server.server_port}',
                    'TEAM360_EVOLUTION_INSTANCE':instance,'TEAM360_EVOLUTION_API_KEY':'synthetic-key',
                    'TEAM360_EVOLUTION_TIMEOUT_SECONDS':'2',
                    'TEAM360_MESSAGING_WORKSPACE_SLUG':workspace,'TEAM360_MESSAGING_CHANNEL_ALIAS':'test-channel',
                    'TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER':SENDER,'TEAM360_MESSAGING_WEBHOOK_TOKEN':TOKEN}
            for key,value in values.items(): monkeypatch.setenv(key,value)
            monkeypatch.setattr(webhook,'get_pool',lambda:pool)
            app=Litestar(route_handlers=[EvolutionWhatsAppWebhookController])
            path='/webhooks/messaging/evolution/whatsapp'
            headers={'x-team360-webhook-token':TOKEN}

            def inbound(message_id,text='team360 ping 01',sender=SENDER):
                return {'event':'messages.upsert','instance':instance,
                        'data':{'key':{'id':message_id,'remoteJid':sender+'@s.whatsapp.net','fromMe':False},
                                'message':{'conversation':text}}}
            def status(message_id,state):
                return {'event':'messages.update','instance':instance,'data':{'keyId':message_id,'status':state,'fromMe':False}}
            async def rows():
                async with transaction(pool) as conn: return await repo.evidence(conn,binding)

            async with AsyncTestClient(app) as client:
                async def post(data):
                    response=await client.post(path,json=data,headers=headers)
                    assert response.status_code==200
                    return response.json()['results']
                first=inbound('in-1')
                assert await post(first)=={'accepted':1}
                assert await post(first)=={'duplicate':1}
                assert len(calls)==1
                evidence=await rows()
                assert len(evidence)==2
                assert len({r['thread_id'] for r in evidence})==1
                assert await post(inbound('unauthorized',sender='15550000002'))=={'unauthorized':1}
                assert len(await rows())==2 and len(calls)==1
                assert await post(inbound('empty',text=''))=={'ignored':1}
                assert await post(inbound('other-text',text='hello'))=={'received':1}
                assert len(calls)==1
                for state in ['DELIVERED','READ','SENT','DELIVERED']:
                    assert await post(status('synthetic-outbound-1',state))=={'status':1}
                evidence=await rows()
                out=next(r for r in evidence if r['direction']=='outbound' and r['event_type']=='message')
                assert out['transport_status']=='read' and out['payload_jsonb']['t6_ms'] is not None
                assert len([r for r in evidence if r['event_type']=='status'])==3
                times=out['payload_jsonb']['timings']
                assert [times[f't{i}_ms'] for i in range(6)] == sorted(times.values())

                # Concurrent duplicates across separate connections still send once.
                results=await asyncio.gather(post(inbound('in-concurrent')),post(inbound('in-concurrent')))
                assert sorted(results,key=str)==sorted([{'accepted':1},{'duplicate':1}],key=str)
                assert len(calls)==2
                for state in ['SENT','FAILED','SENT']:
                    assert await post(status('synthetic-outbound-2',state))=={'status':1}
                failed=next(r for r in await rows() if r['provider_message_id']=='synthetic-outbound-2' and r['event_type']=='message')
                assert failed['transport_status']=='failed'
                assert await post(status('synthetic-outbound-2','DELIVERED'))=={'status':1}
                delivered=next(r for r in await rows() if r['provider_message_id']=='synthetic-outbound-2' and r['event_type']=='message')
                assert delivered['transport_status']=='delivered'
                for behavior,expected in [('error','unknown'),('invalid','unknown'),('timeout','unknown')]:
                    mode['value']=behavior
                    monkeypatch.setenv('TEAM360_EVOLUTION_TIMEOUT_SECONDS','.05' if behavior=='timeout' else '2')
                    before=len(calls)
                    value=inbound('in-'+behavior)
                    assert await post(value)=={'send_failed':1}
                    assert await post(value)=={'duplicate':1}
                    assert len(calls)==before+1
                    latest=next(r for r in await rows() if r['event_type']=='message' and
                        r['direction']=='outbound' and r['payload_jsonb']['text']=='TEAM360 PONG 01' and
                        r['payload_jsonb'].get('initial_result')=={'error':'provider_http_error',
                            'invalid':'provider_invalid_response','timeout':'provider_timeout'}[behavior])
                    assert latest['transport_status']==expected
                mode['value']='early-status'
                # Persist callback before outbound acceptance: it must reconcile later.
                monkeypatch.setenv('TEAM360_EVOLUTION_TIMEOUT_SECONDS','2')
                assert await post(status('synthetic-outbound-6','DELIVERED'))=={'status':1}
                assert await post(inbound('in-early'))=={'accepted':1}
                early=next(r for r in await rows() if r['provider_message_id']=='synthetic-outbound-6' and r['event_type']=='message')
                assert early['transport_status']=='delivered' and early['payload_jsonb']['t6_ms'] is not None

            # Simulate a process cut after durable intent but before transport I/O.
            interrupted=normalize_events(inbound('in-interrupted'),instance=instance,
                recipient='synthetic-recipient',received_at=datetime.now(timezone.utc))[0]
            async with transaction(pool) as conn:
                claimed=await repo.claim(conn,binding,interrupted,{'t0_ms':epoch_ms(),'t1_ms':epoch_ms()})
                pending_id=await repo.intent(conn,binding,claimed,interrupted,'TEAM360 PONG 01',{})
            # Close/reopen the pool and reconstruct HTTP app + service: no process-memory dedup.
            await close_pool(pool)
            pool=create_pool(get_database_settings(min_size=1,max_size=4))
            await open_pool(pool)
            await pool.wait()
            async with AsyncTestClient(Litestar(route_handlers=[EvolutionWhatsAppWebhookController])) as client:
                result=await client.post(path,json=first,headers=headers)
                assert result.json()['results']=={'duplicate':1}
                assert len(calls)==6
                interrupted_result=await client.post(path,json=inbound('in-interrupted'),headers=headers)
                assert interrupted_result.json()['results']=={'duplicate':1}
                pending=next(r for r in await rows() if str(r['id'])==pending_id)
                assert pending['status']=='pending' and pending['provider_message_id'] is None
                assert len(calls)==6
                assert len({r['thread_id'] for r in await rows() if r['thread_id']})==1
                # Closed listener represents Evolution off without touching actual infrastructure.
                server.shutdown(); server.server_close(); thread.join(timeout=2)
                response=await client.post(path,json=inbound('in-offline'),headers=headers)
                assert response.json()['results']=={'send_failed':1}
                offline=next(r for r in await rows() if r['payload_jsonb'].get('initial_result')=='provider_unavailable')
                assert offline['transport_status']=='failed'
        finally:
            async with transaction(pool) as conn:
                await conn.execute('DELETE FROM message_events WHERE workspace_id=%s',(binding.workspace_id,))
                await conn.execute('DELETE FROM message_threads WHERE workspace_id=%s',(binding.workspace_id,))
                await conn.execute('DELETE FROM communication_channels WHERE workspace_id=%s',(binding.workspace_id,))
                await conn.execute('DELETE FROM core_workspaces WHERE id=%s',(binding.workspace_id,))
            await close_pool(pool)
            if thread.is_alive():
                server.shutdown(); server.server_close(); thread.join(timeout=2)
    asyncio.run(exercise())

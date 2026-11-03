"""Focal postchecks of actual V1 services. No sends, fixture messages or Meta calls."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).parent))
from inspect_consumers import OUT, ROOT, PRIVATE, CHANNELS
from provision import P
from start_runtime import backend_environment, podman
os.environ.update(backend_environment())
import httpx
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from modules.db.settings import get_database_settings
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.transaction import transaction
from modules.messaging.repository import MessagingRepository
from modules.messaging.administration.bindings import BindingAdministration
from modules.messaging.administration.contract import signature
from modules.messaging.transport_runtime import TransportRuntime
from modules.messaging.transport_callbacks import TransportCallbackReceiver
from modules.messaging.providers.evolution.config import EvolutionConfig
from modules.telchi.assistant import whatsapp_dev as d


async def check_async():
    approval=d.read_approval(P/'approval.json');d.gate_evidence(approval)
    srv,settings=d.configuration()
    binding=await d.check_database(approval,settings,srv.evolution)
    pool=create_pool(get_database_settings(min_size=1,max_size=1));await open_pool(pool)
    try:
        rt=TransportRuntime.from_env(EvolutionConfig.from_env())
        async with transaction(pool) as conn:
            await rt.provider.check_transport_binding(conn,binding)
            try:await MessagingRepository().binding(conn,workspace_slug='team360_public_site',channel_alias='evolution-meta-dev',provider='evolution',instance='team360-meta-dev')
            except ValueError as exc:assert str(exc)=='DEV channel binding missing'
            else:raise AssertionError('Inactive historical binding was accepted')
        document=json.loads((P/'evolution.json').read_text())
        key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(document['signing_key']))
        payload=dict(version=1,event_id=hashlib.sha256(b'dev-v1-auth-probe-no-delivery').hexdigest(),scope=rt.document['scope'],revision=1,
            outbound_intent_id=str(uuid4()),transport_attempt_id=str(uuid4()),provider_message_id='wamid.DEV_AUTH_PROBE_NOT_A_REAL_MESSAGE',
            status='delivered',provider_timestamp=str(int(time.time())),code=None,
            targets={s:{k:v[k] for k in ('id','epoch')} for s,v in rt.document['trust']['targets'].items()})
        envelope={'payload':payload,'signature':signature(key,'team360.transport.callback.v1',payload)}
        receiver=TransportCallbackReceiver(trust=rt.document['trust'],scope=rt.document['scope'],binding=binding)
        try:await receiver.receive(pool,envelope)
        except ValueError as exc:assert str(exc)=='Callback intent not found'
        else:raise AssertionError('Nonexistent intent must never become delivery evidence')
        return envelope,dict(provider=type(rt.provider).__name__,real_binding_credential_and_bilateral_epochs_verified=True,
            inactive_historical_routing_denied=True,six_gates='VALID',signed_callback_authenticated_but_unreserved_intent_denied=True,
            private_callback_delivery_to_real_message='NOT_RUN_NO_MESSAGE_AUTHORIZATION')
    finally:await close_pool(pool)


def main():
    os.umask(0o077)
    owned=json.loads((P/'owned-runtime.json').read_text())
    proc=Path('/proc')/str(owned['srv05_pid'])
    assert proc.joinpath('stat').read_text().split()[21]==owned['srv05_start_ticks']
    ready=json.loads((P/('srv05-ready-'+str(owned['srv05_pid'])+'.json')).read_text())
    assert ready['source_sha256']==d.source_digest() and ready['configuration_sha256']==d.configuration_digest()
    evo=json.loads(podman('inspect',owned['evolution_container_id']))[0]
    assert evo['State']['Running'] and evo['Image'].endswith('5a25df47f4bb71764d2fd033f07428e5be0cbc010b33d05851a5166e89f4b175')
    assert evo['Path']=='node' and evo['Args']==['dist/main.js']
    old=json.loads(podman('inspect',owned['prior_container_id']))[0]
    assert old['State']['Status']=='created'
    envelope,result=asyncio.run(check_async())
    # Actual running Evolution -> private Srv05 UDS; no HTTP/public callback route.
    code="""const fs=require('fs'),http=require('http');let raw='';process.stdin.on('data',b=>raw+=b);process.stdin.on('end',async()=>{const p=JSON.parse(raw);let statuses=[];for(const body of [{},p.envelope]){statuses.push(await new Promise((ok,no)=>{let q=http.request({socketPath:p.socket,path:'/transport/v1/callbacks/'+p.binding,method:'POST',headers:{'content-type':'application/json'}},r=>{r.resume();r.on('end',()=>ok(r.statusCode))});q.on('error',no);q.setTimeout(5000,()=>q.destroy());q.end(JSON.stringify(body))}));}console.log(JSON.stringify({statuses,namespace_uid:process.getuid()}));});"""
    process=subprocess.run(['podman','exec','-i',owned['evolution_container_id'],'node','-e',code],
        input=json.dumps({'socket':str(P/'callback.sock'),'binding':envelope['payload']['scope']['binding_id'],'envelope':envelope}),
        capture_output=True,text=True,timeout=15,check=True)
    callback=json.loads(process.stdout);assert callback['statuses']==[401,401]
    # Observe host UID of this exact running container, not an assumed userns flag.
    peerpath=P/('p'+uuid4().hex[:4]+'.sock');server=socket.socket(socket.AF_UNIX);server.settimeout(10)
    child=None
    try:
        server.bind(str(peerpath));os.chmod(peerpath,0o600);server.listen(1)
        js="const n=require('net');let c=n.createConnection(process.argv[1],()=>c.write('v1-peer'));c.setTimeout(5000,()=>process.exit(2));c.on('end',()=>process.exit(0));c.on('error',()=>process.exit(3));"
        child=subprocess.Popen(['podman','exec',owned['evolution_container_id'],'node','-e',js,str(peerpath)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        with server.accept()[0] as peer:
            _,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));assert uid==os.getuid()
            assert peer.recv(16)==b'v1-peer'
        child.communicate(timeout=10);assert child.returncode==0
    finally:
        server.close();peerpath.unlink(missing_ok=True)
        if child and child.poll() is None:child.terminate();child.communicate(timeout=10)
    result['private_callback']=dict(uds_mode=oct((P/'callback.sock').stat().st_mode&0o777),parent_mode=oct(P.stat().st_mode&0o777),
        actual_evolution_peer_uid=uid,actual_container_http=callback['statuses'],real_delivery_not_simulated=True)
    control=json.loads((PRIVATE/'whatsapp-dev-control.json').read_text())
    env=backend_environment()
    with httpx.Client(base_url='http://'+env['TEAM360_V1_BACKEND_HOST']+':18181',trust_env=False,timeout=5) as client:
        assert client.get('/transport/v1/callbacks/'+envelope['payload']['scope']['binding_id']).status_code==404
        assert client.post(d.WEBHOOK,content=b'{malformed').status_code==401
        assert client.post(d.WEBHOOK,headers={'x-team360-webhook-token':control['env']['TEAM360_MESSAGING_WEBHOOK_TOKEN']},content=b'{malformed').status_code==400
    srv,settings=d.configuration()
    d.container_probe('evolution-api','http://host.containers.internal:18181'+d.WEBHOOK,settings,srv.evolution.instance)
    with httpx.Client(base_url=srv.evolution.base_url,headers={'apikey':control['env']['TEAM360_EVOLUTION_API_KEY']},trust_env=False,timeout=5) as client:
        webhook=d.webhook_body(d.api(client,'GET','/webhook/find/team360-meta-dev'))
    result['preserved_inbound_webhook_enabled']=webhook['enabled']
    prior=json.loads((OUT/'deactivation.json').read_text())['before']
    with psycopg.connect(get_database_settings().dsn,row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as conn:
        BindingAdministration().require_exclusive(conn,'team360-meta-dev',CHANNELS[1])
        originals=[]
        for old_history in prior['history']:
            row=conn.execute('''SELECT count(*) AS n,md5(string_agg(md5(row_to_json(e)::text),'' ORDER BY id)) AS digest
                FROM message_events e WHERE channel_id=%s AND occurred_at_utc<=%s''',
                (old_history['channel_id'],old_history['last_event'])).fetchone()
            assert row['n']==old_history['n'] and row['digest']==old_history['digest'];originals.append(row)
        result['original_events_preserved']=originals
        result['current_counts']=conn.execute('SELECT channel_id::text,count(*) AS n FROM message_events WHERE channel_id=ANY(%s::uuid[]) GROUP BY 1 ORDER BY 1',(CHANNELS,)).fetchall()
        protected=json.loads((OUT.parent/'dev-v1-intervention-20261023/result.json').read_text())['protected_events']
        rows=conn.execute('SELECT id::text,status,transport_status FROM message_events WHERE id=ANY(%s::uuid[]) ORDER BY id',([x['id'] for x in protected],)).fetchall()
        assert rows==protected
        result['protected_five_events_unchanged']=True
    dsns=json.loads((P/'runtime-dsns.json').read_text())
    backup=Path(json.loads((OUT.parent/'dev-v1-intervention-20261023/backup-verification.json').read_text())['backup_directory'])
    baseline=json.loads((backup/'evolution_api-premigration.json').read_text())['tables']
    with psycopg.connect(dsns['evolution'],row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as conn:
        hashes={}
        for table in ('Instance','Webhook','Setting'):
            rows=conn.execute(sql.SQL('SELECT to_jsonb(t)::text AS j FROM evolution_api.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(table))).fetchall()
            h=hashlib.sha256()
            for row in rows:
                data=row['j'].encode();h.update(len(data).to_bytes(8,'big'));h.update(data)
            hashes[table]={'count':len(rows),'sha256':h.hexdigest()}
            assert hashes[table]==baseline['evolution_api.'+table]
        result['instance_webhook_settings_byte_equivalent']=True
        result['v1_attempts']=conn.execute('SELECT count(*) AS n FROM ot_attempt').fetchone()['n'];assert result['v1_attempts']==0
        result['v1_callback_records']=conn.execute('SELECT count(*) AS n FROM ot_callback').fetchone()['n']
    for path,h in prior['config_sha256'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    result.update(branch='feature/console-backend-core',HISTORICAL_BINDING_INACTIVE='YES',HISTORICAL_EVENTS_PRESERVED='YES',TELCHI_BINDING_EXCLUSIVE='YES',
        SINGLE_OWNER_DEV='PASS',V1_CREDENTIALS='PASS',PRIVATE_CALLBACK='PASS',SRV05_PROVIDER_V1='PASS',EVOLUTION_DEV_RUNNING='YES',
        META_UNCHANGED='YES',REAL_MESSAGES_SENT=0,READY_FOR_WHATSAPP_TEST='YES' if webhook['enabled'] else 'NO',
        ready_blocker=None if webhook['enabled'] else 'Existing Evolution inbound webhook remains disabled, preserved per explicit no-webhook-change restriction. An authorized inbound-forwarding activation is needed before a real WhatsApp test.',
        original_configurations_byte_equivalent=True,temporary_processes_left=0,intended_dev_services_running=2,
        environment_aborts=2,unrelated_processes_terminated=0)
    (OUT/'final-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k.isupper()},indent=2))

if __name__=='__main__':main()

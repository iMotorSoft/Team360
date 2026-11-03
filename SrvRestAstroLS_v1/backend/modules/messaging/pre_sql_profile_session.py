"""One real hola, bounded 300s; no N=10 repeat or proactive sends.
From backend: uv run --no-sync python -m modules.messaging.pre_sql_profile_session
Uses existing private DEV configuration, transport and telchi_sql_session lifecycle.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent.parent
REPORT = ROOT/'data/reports/messaging/telchi-datalake-pre-sql-profile-v1'
LAB = ROOT.parent.parent/'lab/evolution-api'
GATE = 'TEAM360_TELCHI_DATALAKE_PRE_SQL_PROFILE_V1'


def validate_sample(sample):
    profile = sample['result']['profile']
    labels = {s['label'] for s in profile['spans']}
    required = {'attachment_open_including_catalog_session','duckdb_sql_execute',
                'fetch','materialization','foundation_resolution','duckdb_connect'}
    assert required <= labels
    assert profile['schema']=='telchi-pre-sql-profile-v1'
    assert profile['parent']['total_ms'] > 0
    assert sample['messaging_profile']['pre_send_ms'] > 0
    assert sample['transport_status'] in {'delivered','read'}
    assert sample['result']['read_only'] and not sample['result']['sap_accessed']
    baseline=json.loads((REPORT/'direct.json').read_text())[0]
    for key in ['result_hash','query_hash','executed_sql_hash','foundation_publication_id','ducklake_snapshot_id']:
        assert sample['result'][key] == baseline[key], 'Foundation/query changed: autonomous profile requires reevaluation'


def redact_tunnel_line(line):
    # Cloudflared errors may echo challenge URLs containing private verify tokens.
    return re.sub(r'(https?://[^\s?]+)\?\S+', r'\1?[REDACTED]', line)


def drain_tunnel(stream, log):
    for line in stream:
        log.write(redact_tunnel_line(line))
        log.flush()


async def main():
    from .telchi_sql_session import run
    from .providers.evolution.config import EvolutionConfig
    from .settings import MessagingDevSettings
    config=EvolutionConfig.from_env()
    MessagingDevSettings.from_env()
    output=REPORT/('human-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    output.mkdir(parents=True,exist_ok=False)
    state={'gate':GATE,'status':'BLOCKED','layer':'transport preflight','external_proactive_sends':0,'count':1,'timeout_seconds':300}
    transport_owned=False
    tunnel=None
    tunnel_reader=None
    previous=None
    subscribed=False
    watch=None
    log=(output/'tunnel.log').open('w')
    graph='https://graph.facebook.com/'+os.environ.get('META_TEAM360_GRAPH_VERSION','v20.0')
    app=os.environ['META_TEAM360_APP_ID']
    auth={'Authorization':'Bearer '+app+'|'+os.environ['META_TEAM360_APP_SECRET']}
    api=httpx.Client(timeout=20,trust_env=False)
    def set_subscription(url):
        response=api.post(graph+'/'+app+'/subscriptions',headers=auth,data={
            'object':'whatsapp_business_account','callback_url':url,
            'verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'fields':'messages'})
        response.raise_for_status()
        assert response.json().get('success') is True
    async def monitor():
        announced=False
        while True:
            p=output/'session/session.json'
            if p.exists() and json.loads(p.read_text()).get('status')=='WAITING_HUMAN' and not announced:
                print('READY — enviar hola desde WhatsApp autorizado',flush=True)
                announced=True
            await asyncio.sleep(.25)
    try:
        # Refuse configuration drift; never recreate a container or restart a running one.
        info=json.loads(subprocess.check_output(['podman','inspect','evolution-api'],text=True))[0]
        assert info['HostConfig']['PortBindings'].get('8080/tcp')==[{'HostIp':'127.0.0.1','HostPort':'18180'}]
        if not info['State']['Running']:
            subprocess.run(['podman','start','evolution-api'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            transport_owned=True
        state['layer']='own public tunnel'
        binary=shutil.which('cloudflared') or str(LAB/'data/cloudflared/usr/bin/cloudflared')
        assert Path(binary).is_file()
        tunnel=subprocess.Popen([binary,'tunnel','--no-autoupdate','--url','http://127.0.0.1:18180'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        tunnel_reader=threading.Thread(target=drain_tunnel,args=(tunnel.stdout,log),daemon=True)
        tunnel_reader.start()
        url=None
        for _ in range(120):
            assert tunnel.poll() is None
            match=re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',(output/'tunnel.log').read_text())
            if match:
                url=match.group(0);break
            await asyncio.sleep(.5)
        assert url
        state['layer']='Team360 Meta subscription preflight'
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status()
        previous=next((d for d in r.json().get('data',[]) if d.get('object')=='whatsapp_business_account'),None)
        if previous and (not previous.get('active') or any(f.get('name')!='messages' for f in previous.get('fields',[]))):
            raise RuntimeError('Refuse inactive subscription or unrelated fields')
        for _ in range(30):
            try:
                r=api.get(url+'/webhook/meta',params={'hub.mode':'subscribe','hub.verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'hub.challenge':'profile-ready'})
                if r.is_success and r.text=='profile-ready':break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else: raise RuntimeError('Public challenge unavailable')
        subscribed=True
        set_subscription(url+'/webhook/meta')
        host=subprocess.check_output(['podman','exec','evolution-api','node','-e',
            "require('dns').lookup('host.containers.internal',(e,a)=>{if(e)process.exit(1);console.log(a)})"],text=True,timeout=10).strip()
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex((host,18181))==0:
                raise RuntimeError('Refuse occupied backend port')
        state['layer']='bounded Team360 human session'
        watch=asyncio.create_task(monitor())
        code=await run(SimpleNamespace(host=host,port=18181,duration=300,count=1,output=str(output/'session')))
        if code==0:
            evidence=json.loads((output/'session/evidence.json').read_text())
            assert evidence['n']==1
            validate_sample(evidence['samples'][0])
            state.update(status='PASS',layer=None)
        else:
            state['layer']=json.loads((output/'session/session.json').read_text()).get('layer')
            state['status']='WAITING_HUMAN' if state['layer']=='real human traffic not completed before session expiry' else 'BLOCKED'
    except Exception as exc:
        state.update(status='BLOCKED',error_class=type(exc).__name__)
    finally:
        if watch:
            watch.cancel()
            try: await watch
            except asyncio.CancelledError: pass
        if subscribed:
            try:
                if previous:
                    set_subscription(previous['callback_url'])
                else:
                    r=api.delete(graph+'/'+app+'/subscriptions',headers=auth,params={'object':'whatsapp_business_account'});r.raise_for_status()
                state['subscription_restored']=True
            except Exception:
                state.update(status='BLOCKED',layer='Meta subscription restoration',subscription_restored=False)
        if tunnel:
            if tunnel.poll() is None:
                tunnel.terminate()
                try: tunnel.wait(timeout=10)
                except subprocess.TimeoutExpired: tunnel.kill();tunnel.wait(timeout=5)
            state['own_tunnel_reaped']=tunnel.poll() is not None
        if tunnel_reader:
            tunnel_reader.join(timeout=5)
            state['own_tunnel_reader_closed']=not tunnel_reader.is_alive()
            if tunnel_reader.is_alive():
                state.update(status='BLOCKED',layer='own tunnel reader cleanup')
        if transport_owned:
            try:
                subprocess.run(['podman','stop','--time','10','evolution-api'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
                state['own_transport_stopped']=True
            except Exception:
                state.update(status='BLOCKED',layer='own transport cleanup',own_transport_stopped=False)
        api.close();log.close()
        (output/'continuation.json').write_text(json.dumps(state,indent=2)+'\n')
    print(GATE+'='+state['status'],flush=True)
    return 0 if state['status']=='PASS' else 2


if __name__=='__main__':
    load_dotenv(BACKEND.parent/'.env.backend-dev.local',override=True)
    os.environ.update(TEAM360_MESSAGING_DEV_SQL_TENANT='telchi',TEAM360_TELCHI_PRE_SQL_PROFILE='1')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='read-only local prerequisites; no transport startup or external requests')
    args=parser.parse_args()
    if args.check:
        from .providers.evolution.config import EvolutionConfig
        from .settings import MessagingDevSettings
        from modules.telchi.datalake.ducklake import DuckLakeConnector
        EvolutionConfig.from_env();MessagingDevSettings.from_env();DuckLakeConnector()
        for key in ['META_TEAM360_APP_ID','META_TEAM360_APP_SECRET','META_TEAM360_VERIFY_TOKEN']:
            assert os.environ.get(key)
        assert (REPORT/'direct.json').is_file() and (REPORT/'messaging-local.json').is_file()
        assert shutil.which('cloudflared') or (LAB/'data/cloudflared/usr/bin/cloudflared').is_file()
        assert shutil.which('podman')
        print('LOCAL_PREREQUISITES=PASS; external transport/auth/connectivity not validated')
    else:
        raise SystemExit(asyncio.run(main()))

"""Bounded DEV callback recovery check, using historical Cloudflare/Meta procedure.
No WhatsApp sends, no local Team360 webhook activation, no container recreation.
Restore empty subscription state; close only the tunnel created by this script.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
LAB = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api')


def main():
    output = ROOT/'recovery-callback.json'
    logpath = ROOT/'recovery-tunnel.log'
    if output.exists() or logpath.exists():
        raise SystemExit('Refusing overwrite')
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:
            os.environ[k]=v
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'whatsapp_sends':0,
            'local_webhook_changes':0,'temporary_subscription':False}
    graph='https://graph.facebook.com/'+os.getenv('META_TEAM360_GRAPH_VERSION','v20.0')
    app=os.environ['META_TEAM360_APP_ID']
    auth={'Authorization':'Bearer '+app+'|'+os.environ['META_TEAM360_APP_SECRET']}
    api=httpx.Client(timeout=20,trust_env=False,follow_redirects=False)
    tunnel=None
    reader=None
    mutated=False
    callback=None
    log=logpath.open('x')
    def drain(stream):
        for line in stream:
            # Reuse historical session sanitization: challenge tokens must not reach disk.
            line=re.sub(r'(https?://[^\s?]+)\?\S+',r'\1?[REDACTED]',line)
            for key in ('META_TEAM360_VERIFY_TOKEN','META_TEAM360_WABA_TOKEN','META_TEAM360_APP_SECRET'):
                line=line.replace(os.environ[key],'[REDACTED]')
            log.write(line)
            log.flush()
    try:
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth)
        r.raise_for_status()
        assert r.json().get('data')==[] and not (r.json().get('paging') or {}).get('next'), 'Refuse existing subscription'
        result['initial_subscription_count']=0
        info=json.loads(subprocess.check_output(['podman','inspect','evolution-api']))[0]
        assert info['State']['Running']
        assert info['HostConfig']['PortBindings'].get('8080/tcp')==[{'HostIp':'127.0.0.1','HostPort':'18180'}]
        env=dict(e.split('=',1) for e in info['Config']['Env'] if '=' in e)
        assert env.get('WA_BUSINESS_TOKEN_WEBHOOK')==os.environ['META_TEAM360_VERIFY_TOKEN']
        result['verify_token_matches_container']=True
        result['existing_server_url_hash']=hashlib.sha256(env.get('SERVER_URL','').encode()).hexdigest()
        local=api.get('http://127.0.0.1:18180/webhook/meta',params={
            'hub.mode':'subscribe','hub.verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'hub.challenge':'recovery-local'})
        result['local_challenge']={'http_status':local.status_code,'matched':local.text=='recovery-local'}
        assert local.is_success and local.text=='recovery-local'
        binary=shutil.which('cloudflared') or str(LAB/'data/cloudflared/usr/bin/cloudflared')
        assert Path(binary).is_file()
        tunnel=subprocess.Popen([binary,'tunnel','--no-autoupdate','--url','http://127.0.0.1:18180'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        result['own_tunnel_pid']=tunnel.pid
        reader=threading.Thread(target=drain,args=(tunnel.stdout,),daemon=True)
        reader.start()
        url=None
        for _ in range(120):
            assert tunnel.poll() is None
            match=re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',logpath.read_text())
            if match:
                url=match.group(0)
                break
            time.sleep(.5)
        assert url
        callback=url+'/webhook/meta'
        result['temporary_callback_hash']=hashlib.sha256(callback.encode()).hexdigest()
        result['server_url_matches_temporary_tunnel']=env.get('SERVER_URL','').rstrip('/')==url
        result['public_challenge_attempts']=[]
        for _ in range(15):
            try:
                r=api.get(callback,params={'hub.mode':'subscribe','hub.verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'hub.challenge':'recovery-public'})
                matched=r.is_success and r.text=='recovery-public'
                result['public_challenge_attempts'].append({'http_status':r.status_code,'matched':matched})
                if matched: break
            except httpx.HTTPError as exc:
                result['public_challenge_attempts'].append({'error_type':type(exc).__name__})
            time.sleep(1)
        else: raise RuntimeError('Public challenge unavailable')
        # Re-read immediately before mutation; only same app and empty DEV state allowed.
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth)
        r.raise_for_status()
        assert r.json().get('data')==[]
        mutated=True  # Even if request times out, inspect exact owned URL in cleanup.
        r=api.post(graph+'/'+app+'/subscriptions',headers=auth,data={
            'object':'whatsapp_business_account','callback_url':callback,
            'verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'fields':'messages'})
        result['subscribe_http_status']=r.status_code
        if not r.is_success:
            result['subscribe_error_code']=(r.json().get('error') or {}).get('code')
        r.raise_for_status()
        assert r.json().get('success') is True
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth)
        r.raise_for_status()
        rows=r.json().get('data',[])
        exact=[e for e in rows if e.get('object')=='whatsapp_business_account' and e.get('callback_url')==callback]
        result['temporary_subscription']=len(exact)==1 and exact[0].get('active') is True
        result['temporary_fields']=[f.get('name') for f in exact[0].get('fields',[])] if exact else []
        assert result['temporary_subscription'] and result['temporary_fields']==['messages']
        result['callback_configuration_verified']=True
    except Exception as exc:
        result['error_type']=type(exc).__name__
    finally:
        if mutated:
            try:
                r=api.get(graph+'/'+app+'/subscriptions',headers=auth)
                r.raise_for_status()
                rows=r.json().get('data',[])
                owned=[e for e in rows if e.get('object')=='whatsapp_business_account' and e.get('callback_url')==callback]
                if owned:
                    assert len(rows)==1 and all(f.get('name')=='messages' for f in owned[0].get('fields',[])), 'Concurrent configuration; do not delete'
                    r=api.delete(graph+'/'+app+'/subscriptions',headers=auth,params={'object':'whatsapp_business_account'})
                    result['cleanup_delete_http_status']=r.status_code
                    r.raise_for_status()
                    assert r.json().get('success') is True
                r=api.get(graph+'/'+app+'/subscriptions',headers=auth)
                r.raise_for_status()
                result['final_subscription_count']=len(r.json().get('data',[]))
                result['subscription_restored_to_initial_empty']=r.json().get('data')==[]
            except Exception as exc:
                result['subscription_cleanup_error_type']=type(exc).__name__
        if tunnel:
            if tunnel.poll() is None:
                tunnel.terminate()
                try: tunnel.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait(timeout=5)
            result['own_tunnel_reaped']=tunnel.poll() is not None
        if reader:
            reader.join(timeout=5)
            result['own_reader_closed']=not reader.is_alive()
        api.close()
        log.close()
        result['end_timestamp']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(result,indent=2)+'\n')
    print('Evidence written:',output.name)


if __name__=='__main__':
    main()

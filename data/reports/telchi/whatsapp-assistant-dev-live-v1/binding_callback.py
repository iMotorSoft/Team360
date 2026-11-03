"""Bounded DEV possession-evidence window. Never binds or sends; cleanup owned callback/tunnel."""
import hashlib,json,os,re,shutil,subprocess,threading,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlparse,urlencode,parse_qsl
import httpx,psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from psycopg.rows import dict_row
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parent
LAB=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api')
PROOF_TEXT='TELCHI DEV: soy devfull@telchiai.com y autorizo vincular esta linea para la prueba.'
def main():
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:os.environ[k]=v
    run=os.getenv('TELCHI_BINDING_CALLBACK_RUN','binding')
    assert re.fullmatch(r'binding(?:-[a-z0-9-]+)?',run)
    seconds=int(os.getenv('TELCHI_BINDING_WINDOW_SECONDS','180'))
    assert 30 <= seconds <= 900
    out=ROOT/(run+'-callback.json');logpath=ROOT/(run+'-tunnel.log')
    statuspath=ROOT/(run+'-status.json')
    assert not out.exists() and not logpath.exists() and not statuspath.exists()
    sender=os.environ['TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER'];assert sender.endswith('6950')
    info=json.loads(subprocess.check_output(['podman','inspect','evolution-api']))[0]
    assert info['State']['Running'] and info['HostConfig']['PortBindings']['8080/tcp']==[{'HostIp':'127.0.0.1','HostPort':'18180'}]
    env=dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)
    assert env['WA_BUSINESS_TOKEN_WEBHOOK']==os.environ['META_TEAM360_VERIFY_TOKEN']
    u=urlparse(env['DATABASE_CONNECTION_URI']);u=u._replace(query=urlencode([(k,v) for k,v in parse_qsl(u.query) if k!='schema']))
    settings=conninfo_to_dict(u.geturl());settings['host']='127.0.0.1'
    graph='https://graph.facebook.com/'+os.getenv('META_TEAM360_GRAPH_VERSION','v20.0');app=os.environ['META_TEAM360_APP_ID']
    auth={'Authorization':'Bearer '+app+'|'+os.environ['META_TEAM360_APP_SECRET']}
    api=httpx.Client(timeout=20,trust_env=False)
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'phone_binding_created':False,'outbound_sends':0,'proof_observed':False,'operator_confirmation_required':True}
    tunnel=None;reader=None;mutated=False;callback=None
    log=logpath.open('x')
    def drain(stream):
        for line in stream:
            line=re.sub(r'(https?://[^\s?]+)\?\S+',r'\1?[REDACTED]',line)
            for key in ('META_TEAM360_VERIFY_TOKEN','META_TEAM360_WABA_TOKEN','META_TEAM360_APP_SECRET'):line=line.replace(os.environ[key],'[REDACTED]')
            log.write(line);log.flush()
    try:
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();assert r.json().get('data')==[] and not r.json().get('paging',{}).get('next')
        binary=shutil.which('cloudflared') or str(LAB/'data/cloudflared/usr/bin/cloudflared')
        tunnel=subprocess.Popen([binary,'tunnel','--no-autoupdate','--url','http://127.0.0.1:18180'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        result['own_pid']=tunnel.pid;reader=threading.Thread(target=drain,args=(tunnel.stdout,),daemon=True);reader.start()
        for _ in range(120):
            assert tunnel.poll() is None
            match=re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',logpath.read_text())
            if match:callback=match.group(0)+'/webhook/meta';break
            time.sleep(.5)
        assert callback
        for _ in range(15):
            r=api.get(callback,params={'hub.mode':'subscribe','hub.verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'hub.challenge':'telchi-dev-binding'})
            if r.is_success and r.text=='telchi-dev-binding':break
            time.sleep(1)
        else:raise RuntimeError('public challenge unavailable')
        result['challenge']='PASS'
        mutated=True
        r=api.post(graph+'/'+app+'/subscriptions',headers=auth,data={'object':'whatsapp_business_account','callback_url':callback,'verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'fields':'messages'});r.raise_for_status();assert r.json().get('success') is True
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status()
        rows=r.json()['data'];assert len(rows)==1 and rows[0]['callback_url']==callback and rows[0]['active'] is True
        result['subscription_verified']=True;result['callback_hash']=hashlib.sha256(callback.encode()).hexdigest()
        start=int(time.time());result['window_start']=datetime.now(timezone.utc).isoformat()
        result['window_expires_at']=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
        result['session_pid']=os.getpid()
        statuspath.write_text(json.dumps(dict(result,status='READY'),indent=2)+'\n')
        print(f'VENTANA DEV ABIERTA: {seconds} segundos; esperando mensaje consentido desde la linea piloto.',flush=True)
        with psycopg.connect(make_conninfo(**settings),autocommit=True,row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=5000') as c:
            for _ in range((seconds+1)//2):
                rows=c.execute('''SELECT m.id,m.key,m.message,m."messageTimestamp" FROM evolution_api."Message" m JOIN evolution_api."Instance" i ON i.id=m."instanceId" WHERE i.name='team360-meta-dev' AND m."messageTimestamp">=%s AND m.key->>'remoteJid'=%s AND m.key->>'fromMe'='false' ORDER BY m."messageTimestamp" DESC LIMIT 5''',(start,sender+'@s.whatsapp.net')).fetchall()
                for row in rows:
                    text=row['message'].get('conversation') or row['message'].get('extendedTextMessage',{}).get('text')
                    if text==PROOF_TEXT:
                        result['proof_observed']=True;result['proof_message_id_hash']=hashlib.sha256(str(row['key'].get('id',row['id'])).encode()).hexdigest();result['proof_timestamp']=row['messageTimestamp']
                        private=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-live-v1/proof.json')
                        fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                        with os.fdopen(fd,'w') as f:json.dump(row,f,default=str)
                        break
                if result['proof_observed']:break
                time.sleep(2)
        result['window_result']='PROOF_PENDING_OPERATOR_CONFIRMATION' if result['proof_observed'] else 'NO_FRESH_PILOT_MESSAGE'
    except Exception as exc:result['error_type']=type(exc).__name__
    finally:
        if mutated:
            try:
                r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();rows=r.json()['data']
                if any(x.get('callback_url')==callback for x in rows):
                    assert len(rows)==1 and all(f.get('name')=='messages' for f in rows[0].get('fields',[]))
                    r=api.delete(graph+'/'+app+'/subscriptions',headers=auth,params={'object':'whatsapp_business_account'});r.raise_for_status();assert r.json().get('success') is True
                r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();result['subscription_restored_empty']=r.json().get('data')==[]
            except Exception as exc:result['cleanup_error_type']=type(exc).__name__
        if tunnel:
            if tunnel.poll() is None:
                tunnel.terminate()
                try:tunnel.wait(timeout=10)
                except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait(timeout=5)
            result['own_tunnel_reaped']=tunnel.poll() is not None
        if reader:reader.join(timeout=5);result['own_reader_closed']=not reader.is_alive()
        log.close();api.close();result['completed_at']=datetime.now(timezone.utc).isoformat()
        out.write_text(json.dumps(result,indent=2)+'\n')
        statuspath.write_text(json.dumps(dict(result,status='CLOSED'),indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

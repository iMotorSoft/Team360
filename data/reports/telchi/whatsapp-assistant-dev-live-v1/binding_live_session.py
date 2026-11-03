"""Bounded operational DEV session of the existing Srv05 Telchi factory.
No migrations/grants/simulated messages; restores only owned callback/webhook.
"""
import asyncio,hashlib,ipaddress,json,os,re,shutil,signal,socket,subprocess,sys,threading,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parent
BACKEND=Path.cwd()
sys.path.insert(0,str(BACKEND))  # Explicit source deployment; do not pick an older installed Srv05 wheel.
WEBHOOK='/webhooks/messaging/evolution/whatsapp'
LAB=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api')
def configure():
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:os.environ[k]=v
    os.environ.update(TEAM360_ENV='dev',TEAM360_SRV05_EVOLUTION_ENABLED='1',TEAM360_MESSAGING_DEV_ENABLED='1',TEAM360_MESSAGING_DISPATCH_MODE='horizontal_v1',TEAM360_MESSAGING_DEV_SQL_TENANT='',TEAM360_MESSAGING_WORKSPACE_SLUG='telchi_dev',TEAM360_MESSAGING_CHANNEL_ALIAS='telchi_whatsapp_dev',AUTOMATION_DIAGNOSIS_REPOSITORY='postgres',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
    applied=json.loads((ROOT/'binding-phone-applied.json').read_text());assert applied['phone_binding']=='PASS'
    return applied
class MessagingBoundary:
    """Restrict this LAN listener to authenticated Messaging and safe health only."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']=='http' and not ((scope['path']==WEBHOOK and scope['method']=='POST') or (scope['path']=='/health' and scope['method']=='GET')):
            await send({'type':'http.response.start','status':404,'headers':[]})
            await send({'type':'http.response.body','body':b''});return
        await self.app(scope,receive,send)
def serve(host,port):
    applied=configure()
    from modules.telchi.assistant.composition import create_telchi_app
    from modules.telchi.assistant.handler import BusinessPolicy
    import uvicorn
    app=create_telchi_app(policy=BusinessPolicy('telchi',applied['workspace_id'],'telchi.sales.source_quantity.read.v1',True,True))
    # Operational selection, not edits/mocks of Flow. Keep real DB + Srv05 validation hooks.
    assert [h.__name__ for h in app.on_startup]==['_open_db_pool','_validate_evolution_binding','_start_flow_scheduler']
    app.on_startup=[h for h in app.on_startup if h.__name__!='_start_flow_scheduler']
    app.on_shutdown=[h for h in app.on_shutdown if h.__name__!='_stop_flow_scheduler']
    uvicorn.run(MessagingBoundary(app),host=host,port=port,workers=1,access_log=False,log_level='warning')
def main():
    configure()
    from modules.messaging.providers.evolution.config import EvolutionConfig
    from modules.messaging.settings import MessagingDevSettings
    c=EvolutionConfig.from_env();m=MessagingDevSettings.from_env()
    run='binding-live-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    output=ROOT/(run+'-session.json')
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'run':run,'supervisor_pid':os.getpid(),'status':'STARTING','environment':'dev','instance':c.instance,'routing':'horizontal_v1','handler':'TelchiHandler','flow_scheduler_started':False,'other_routes_exposed':False,'whatsapp_end_to_end':'NOT_OBSERVED'}
    (ROOT/'binding-live-active.json').write_text(json.dumps({'run':run,'pid':os.getpid()},indent=2)+'\n')
    def save():output.write_text(json.dumps(result,indent=2)+'\n')
    save()
    graph='https://graph.facebook.com/'+os.getenv('META_TEAM360_GRAPH_VERSION','v20.0');app=os.environ['META_TEAM360_APP_ID'];auth={'Authorization':'Bearer '+app+'|'+os.environ['META_TEAM360_APP_SECRET']}
    api=httpx.Client(timeout=20,trust_env=False)
    provider=httpx.Client(base_url=c.base_url,headers={'apikey':c.api_key},timeout=20,trust_env=False)
    process=None;tunnel=None;threads=[];logs=[];callback=None;mutated=False;webhook_changed=False;previous=None;stopping=threading.Event()
    def request_stop(*_):stopping.set()
    signal.signal(signal.SIGTERM,request_stop);signal.signal(signal.SIGINT,request_stop)
    def call(method,path,body=None):
        r=provider.request(method,path,json=body);r.raise_for_status();return r.json()
    def spawn(command,path):
        log=path.open('x');logs.append(log)
        p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        def drain():
            for line in p.stdout:
                line=re.sub(r'(https?://[^\s?]+)\?\S+',r'\1?[REDACTED]',line)
                for key in ('META_TEAM360_VERIFY_TOKEN','META_TEAM360_WABA_TOKEN','META_TEAM360_APP_SECRET','TEAM360_MESSAGING_WEBHOOK_TOKEN','TEAM360_EVOLUTION_API_KEY','TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER'):
                    value=os.getenv(key)
                    if value:line=line.replace(value,'[REDACTED]')
                log.write(line);log.flush()
        reader=threading.Thread(target=drain,daemon=True);reader.start();threads.append(reader);return p
    try:
        assert call('GET','/instance/connectionState/'+c.instance).get('instance',{}).get('state')=='open'
        previous=call('GET','/webhook/find/'+c.instance);previous=previous.get('webhook',previous);assert not previous.get('enabled')
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();assert r.json().get('data')==[]
        host=subprocess.check_output(['podman','exec','evolution-api','node','-e',"require('dns').lookup('host.containers.internal',(e,a)=>{if(e)process.exit(1);console.log(a)})"],text=True).strip()
        assert ipaddress.ip_address(host).is_private
        port=18181
        with socket.socket() as probe:probe.bind((host,port))
        process=spawn([str(BACKEND/'.venv/bin/python'),str(Path(__file__).resolve()),'--serve',host,str(port)],ROOT/(run+'-backend.log'));result['backend_pid']=process.pid
        with httpx.Client(base_url=f'http://{host}:{port}',timeout=10,trust_env=False) as local:
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError('Srv05 startup failed')
                try:
                    if local.get('/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:raise RuntimeError('Srv05 health deadline')
            assert local.get('/api/console/me').status_code==404
            assert local.post(WEBHOOK,json={}).status_code==401
            result['listener_health']='PASS';result['missing_token_rejected']=True;result['other_routes_blocked']=True
        # Ignored non-message event checks the real container->Srv05 path, not a WhatsApp simulation.
        code="const http=require('http');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{const c=JSON.parse(s),b=JSON.stringify({event:'connection.update',instance:c.instance});const r=http.request(c.url,{method:'POST',headers:{'content-type':'application/json','x-team360-webhook-token':c.token,'content-length':Buffer.byteLength(b)}},x=>{x.resume();x.on('end',()=>{if(x.statusCode!==200)process.exitCode=1})});r.on('error',()=>process.exitCode=1);r.end(b)})"
        reach=subprocess.run(['podman','exec','-i','evolution-api','node','-e',code],input=json.dumps({'instance':c.instance,'token':m.webhook_token,'url':f'http://host.containers.internal:{port}{WEBHOOK}'}),text=True,capture_output=True,timeout=15)
        assert reach.returncode==0;result['container_reachability']='PASS'
        binary=shutil.which('cloudflared') or str(LAB/'data/cloudflared/usr/bin/cloudflared')
        logpath=ROOT/(run+'-tunnel.log');tunnel=spawn([binary,'tunnel','--no-autoupdate','--url','http://127.0.0.1:18180'],logpath);result['tunnel_pid']=tunnel.pid
        for _ in range(120):
            assert tunnel.poll() is None
            match=re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',logpath.read_text())
            if match:callback=match.group(0)+'/webhook/meta';break
            time.sleep(.5)
        assert callback
        for _ in range(15):
            r=api.get(callback,params={'hub.mode':'subscribe','hub.verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'hub.challenge':'telchi-live'})
            if r.is_success and r.text=='telchi-live':break
            time.sleep(1)
        else:raise RuntimeError('public challenge deadline')
        webhook_changed=True
        call('POST','/webhook/set/'+c.instance,{'webhook':{'enabled':True,'url':f'http://host.containers.internal:{port}{WEBHOOK}','events':['MESSAGES_UPSERT','MESSAGES_UPDATE'],'headers':{'x-team360-webhook-token':m.webhook_token},'byEvents':False,'base64':False}})
        actual=call('GET','/webhook/find/'+c.instance);actual=actual.get('webhook',actual)
        assert actual['enabled'] and actual['url']==f'http://host.containers.internal:{port}{WEBHOOK}' and actual.get('headers',{}).get('x-team360-webhook-token')==m.webhook_token
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();assert r.json().get('data')==[]
        mutated=True
        r=api.post(graph+'/'+app+'/subscriptions',headers=auth,data={'object':'whatsapp_business_account','callback_url':callback,'verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'fields':'messages'});r.raise_for_status();assert r.json().get('success') is True
        r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();entries=r.json()['data'];assert len(entries)==1 and entries[0]['callback_url']==callback and entries[0]['active'] is True
        result.update(status='READY',local_webhook_verified=True,public_challenge='PASS',meta_subscription_verified=True,callback_hash=hashlib.sha256(callback.encode()).hexdigest(),ready_at=datetime.now(timezone.utc).isoformat(),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat())
        save();print('TELCHI LIVE READY',flush=True)
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline and not stopping.wait(2):
            if process.poll() is not None or tunnel.poll() is not None:raise RuntimeError('owned process exited')
    except Exception as exc:result['error_type']=type(exc).__name__;result['status']='BLOCKED'
    finally:
        if mutated:
            try:
                r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();entries=r.json()['data']
                if any(e.get('callback_url')==callback for e in entries):
                    assert len(entries)==1 and all(f.get('name')=='messages' for f in entries[0].get('fields',[]))
                    r=api.delete(graph+'/'+app+'/subscriptions',headers=auth,params={'object':'whatsapp_business_account'});r.raise_for_status();assert r.json().get('success') is True
                r=api.get(graph+'/'+app+'/subscriptions',headers=auth);r.raise_for_status();result['meta_restored_empty']=r.json().get('data')==[]
            except Exception as exc:result['meta_cleanup_error_type']=type(exc).__name__
        if webhook_changed:
            try:
                actual=call('GET','/webhook/find/'+c.instance);actual=actual.get('webhook',actual)
                assert actual['url']==f'http://host.containers.internal:{port}{WEBHOOK}' and actual.get('headers',{}).get('x-team360-webhook-token')==m.webhook_token
                call('POST','/webhook/set/'+c.instance,{'webhook':{'enabled':bool(previous.get('enabled')),'url':previous['url'],'events':previous.get('events') or [],'headers':previous.get('headers') or {},'byEvents':bool(previous.get('webhookByEvents')),'base64':bool(previous.get('webhookBase64'))}})
                result['local_webhook_restored']=True
            except Exception as exc:result['webhook_cleanup_error_type']=type(exc).__name__
        for label,p in [('backend',process),('tunnel',tunnel)]:
            if p:
                if p.poll() is None:
                    p.terminate()
                    try:p.wait(timeout=15)
                    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
                result[label+'_reaped']=p.poll() is not None
        for thread in threads:thread.join(timeout=5)
        for log in logs:log.close()
        api.close();provider.close();result['closed_at']=datetime.now(timezone.utc).isoformat()
        if result['status']=='READY':result['status']='CLOSED'
        save();print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':
    if sys.argv[1:2]==['--serve']:serve(sys.argv[2],int(sys.argv[3]))
    else:main()

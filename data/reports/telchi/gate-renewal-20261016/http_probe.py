"""Bounded real HTTP ingress certification; never launches a WhatsApp session.
Actual composition and PilotBoundary, lifespan off, no webhook/API writes.
Configured container is inspected, never started. No doubles or patched guards.
"""
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from urllib.parse import urlparse

B=Path(__file__).resolve().parents[4]/'SrvRestAstroLS_v1/backend'
sys.path.insert(0,str(B));os.chdir(B);os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
sha=lambda value:hashlib.sha256(value).hexdigest()
cpath=d.PRIVATE_ROOT/'whatsapp-dev-control.json'
c=l.load_config(cpath)
apath=c.get('approval',d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json')
a=d.read_approval(apath);srv,settings=d.configuration()
output=d.PRIVATE_ROOT/('gate-renewal-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
output.mkdir(mode=0o700)
manifest_path=d.private_file(a['gates_file']);historical_bytes=manifest_path.read_bytes()
with open(output/'historical-manifest.json','xb',opener=lambda p,f:os.open(p,f,0o600)) as f:f.write(historical_bytes)
r=dict(generated_at=datetime.now(timezone.utc).isoformat(),source_sha256=d.source_digest(),approval_sha256=d.approval_digest(a),config_sha256=sha(cpath.read_bytes()),runner_sha256=sha(Path(__file__).read_bytes()),historical_manifest_sha256=sha(historical_bytes),approval_expires_at=a['expires_at'],observations=[],listeners=[],restrictions=dict(whatsapp_sends=0,webhook_mutations=0,model_calls=0,business_queries=0,services_started=0),scope='Real HTTP Srv05 composition and PilotBoundary; lifespan disabled for ingress-only certification. Existing read-only DB session/schema validation; no general startup, Flow scheduler, business execution, gate bypass or normal session start.',host_preflight='BUSY_BUT_SAFE: 8 CPUs; load 1.88/2.26/2.44; available 5686 MiB; swap 380 MiB, no observed current swap IO. One process/listener, sequential requests, no scans/browser/model.')
counts=Counter()
watched={('evolution_whatsapp.py','_receive'):'real_ingress',('evolution_whatsapp.py','build_service'):'build_service',('request.py','body'):'body_read',('mapper.py','normalize_events'):'normalize_events',('service.py','process'):'messaging_process',('handler.py','handle'):'handler',('capabilities.py','execute'):'capability',('capabilities.py','execute_products'):'product_capability',('luna.py','interpret'):'luna',('provider.py','send_text'):'outbound',('transaction.py','transaction'):'transaction',('messaging_sales_query.py','query_fixed_sales'):'foundation',('whatsapp_dev.py','__call__'):'pilot_boundary'}
def observe(frame,event,arg):
 if event=='call':
  key=(Path(frame.f_code.co_filename).name,frame.f_code.co_name)
  if key in watched:counts[watched[key]]+=1

async def main():
 import httpx,uvicorn
 from modules.telchi.assistant.composition import create_telchi_app
 from modules.telchi.assistant.handler import BusinessPolicy
 binding=await d.check_database(a,settings,srv.evolution)
 r['database']='PASS: approved pilot, receiver, workspace, tenant, effective permission, transport and identity schema; read-only transaction'
 p=subprocess.run(['podman','inspect','--format','{{.State.Status}}',c.get('container','evolution-api')],capture_output=True,text=True,timeout=10)
 r['container_state']=p.stdout.strip() if p.returncode==0 else 'UNAVAILABLE'
 r['container_probe']='BLOCKED: container not running; no service start authorized'
 app=create_telchi_app(policy=BusinessPolicy(a['tenant_id'],a['workspace_id'],a['permission'],a['module_enabled'],a['whole_workspace_scope_verified']))
 nonce=secrets.token_hex(32);os.environ['TEAM360_TELCHI_WHATSAPP_NONCE']=nonce
 for surface,asgi in [('srv05_ingress',app),('session_pilot_boundary',d.PilotBoundary(app,settings,srv.evolution,srv.recipient))]:
  sock=socket.socket();sock.bind((c['host'],c.get('port',18181)));sock.listen(8);sock.setblocking(False)
  server=uvicorn.Server(uvicorn.Config(asgi,lifespan='off',log_config=None,access_log=False,timeout_keep_alive=1,workers=1))
  task=asyncio.create_task(server.serve(sockets=[sock]))
  try:
   for _ in range(100):
    if server.started:break
    if task.done():await task
    await asyncio.sleep(.05)
   if not server.started:raise TimeoutError('owned_listener_not_started')
   async with httpx.AsyncClient(base_url=f"http://{c['host']}:{c.get('port',18181)}",trust_env=False,timeout=5) as client:
    if surface=='session_pilot_boundary':
     health=await client.get('/health');r['owned_health_nonce_verified']=health.status_code==200 and secrets.compare_digest(health.headers.get('x-team360-session',''),nonce)
     assert r['owned_health_nonce_verified']
     if r['container_state']=='running':
      await asyncio.to_thread(d.container_probe,c.get('container','evolution-api'),f"http://{c['host']}:{c.get('port',18181)}"+d.WEBHOOK,settings,srv.evolution.instance)
      r['container_probe']='PASS: non-message connection event and invalid token only'
    for label,token,body,expected in [('missing_token',None,b'{malformed',401),('wrong_token',secrets.token_hex(32),b'{malformed',401),('valid_token_invalid_json',settings.webhook_token,b'{malformed',400),('valid_token_inert_event',settings.webhook_token,json.dumps(dict(event='connection.update',instance=srv.evolution.instance)).encode(),200)]:
     counts.clear();old=sys.getprofile();sys.setprofile(observe)
     try:
      headers={'content-type':'application/json'}
      if token is not None:headers['x-team360-webhook-token']=token
      response=await client.post(d.WEBHOOK,content=body,headers=headers)
     finally:sys.setprofile(old)
     calls=dict(counts)
     no_effects=all(calls.get(k,0)==0 for k in ('build_service','messaging_process','handler','capability','product_capability','luna','outbound','transaction','foundation'))
     before_body=label not in {'missing_token','wrong_token'} or (calls.get('body_read',0)==0 and calls.get('normalize_events',0)==0)
     ignored=label!='valid_token_inert_event' or response.json()=={'ok':True,'results':{'ignored':1}}
     r['observations'].append(dict(surface=surface,case=label,status=response.status_code,expected=expected,calls=calls,input_sha256=sha(body),no_persistence_execution_or_outbound_entry=no_effects,authentication_before_decode=before_body,inert_event_ignored=ignored,passed=response.status_code==expected and no_effects and before_body and ignored))
  finally:
   server.should_exit=True
   try:await asyncio.wait_for(task,10)
   finally:sock.close()
   r['listeners'].append(dict(surface=surface,host=c['host'],port=c.get('port',18181),task_finished=task.done(),socket_closed=sock.fileno()==-1))

try:
 asyncio.run(main())
except Exception as exc:
 r['error_class']=type(exc).__name__
finally:
 r['source_sha256_after']=d.source_digest();r['approval_sha256_after']=d.approval_digest(d.read_approval(apath));r['config_sha256_after']=sha(cpath.read_bytes())
 r['fingerprints_stable']=all(r[k]==r[k+'_after'] for k in ('source_sha256','approval_sha256','config_sha256'))
 r['historical_manifest_unchanged']=manifest_path.read_bytes()==historical_bytes
 r['http_auth_local']='PASS' if len(r['observations'])==8 and all(o['passed'] for o in r['observations']) and r.get('owned_health_nonce_verified') and r['fingerprints_stable'] and not r.get('error_class') else 'BLOCKED'
 r['own_processes_left_running']=0 if len(r['listeners'])==2 and all(v['task_finished'] and v['socket_closed'] for v in r['listeners']) else 'UNKNOWN'
 r['status']='BLOCKED' # No container reachability / final operational preflight certified.
 d.save_private(output/'http-auth.json',r)
 public=dict(artifact=str(output/'http-auth.json'),sha256=sha((output/'http-auth.json').read_bytes()),http_auth_local=r['http_auth_local'],container_state=r.get('container_state'),container_probe=r.get('container_probe'),error_class=r.get('error_class'),fingerprints_stable=r['fingerprints_stable'],own_processes_left_running=r['own_processes_left_running'])
 (Path(__file__).parent/'http-result.json').write_text(json.dumps(public,indent=2)+'\n')
 print(json.dumps(public,indent=2))

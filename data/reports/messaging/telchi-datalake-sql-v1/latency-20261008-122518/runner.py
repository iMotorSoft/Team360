"""Operational wrapper only: unchanged count=10 SQL session, no expiry while awaiting human."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
LAB = ROOT.parent.parent / 'lab/evolution-api'
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from dotenv import load_dotenv
load_dotenv(BACKEND.parent / '.env.backend-dev.local', override=True)
os.environ['TEAM360_MESSAGING_DEV_SQL_TENANT'] = 'telchi'
import httpx
from modules.messaging.telchi_sql_session import run
from modules.messaging.benchmark import stats

GATE = 'TEAM360_MESSAGING_TELCHI_DATALAKE_SQL_LATENCY_V1'
state = {'gate': GATE, 'status': 'PREFLIGHT', 'branch': 'feature/console-backend-core',
         'target': 10, 'supervisor_pid': os.getpid(), 'runtime_expiry': None,
         'no_restart_during_measurement': True, 'no_llm': True,
         'host_preflight': 'SAFE', 'sql_threads': 2, 'human_concurrency': 1,
         'prior_verification_sha256': hashlib.sha256((OUT.parent/'runtime-20261008-121608/final-verification.json').read_bytes()).hexdigest(),
         'limits': ['SQL session preflight executes the same query before traffic; message 1 is potential runtime cold start, not untouched Data Lake/cache.',
                    'Each SQL call creates a fresh bounded worker and read-only attachment; SQL connection/modules are not retained between messages.',
                    'Milvus/LiteLLM already run on shared host; neither is started, stopped or used by this session.']}

def save(name, value):
    p = OUT/name
    t = p.with_suffix('.tmp')
    t.write_text(json.dumps(value, indent=2, default=str)+'\n')
    t.replace(p)

async def monitor():
    seen = 0
    while True:
        await asyncio.sleep(1)
        p = OUT/'session/session.json'
        if p.exists():
            s = json.loads(p.read_text())
            state['session_status'] = s['status']
            state['backend_pid'] = s.get('backend_pid')
            state['runtime_active'] = s.get('runtime_active', False)
            if s['status']=='WAITING_HUMAN': state['status']='WAITING_HUMAN'
        e = OUT/'session/evidence.json'
        if e.exists():
            evidence = json.loads(e.read_text())
            n = evidence['n']
            state['n_delivered'] = n
            warm = evidence['samples'][1:]
            save('latency.json', {'gate':GATE, 'status':'WAITING_HUMAN',
                 'n':n, 'all_metrics_ms': evidence['metrics_ms'],
                 'warm_metrics_ms': {k:stats([s['durations_ms'][k] for s in warm]) for k in evidence['metrics_ms']},
                 'samples':evidence['samples'], 'sequential':evidence['sequential'],
                 'incomplete':evidence['incomplete'], 'excluded_failed':evidence['excluded_failed']})
            if n > seen:
                print(f'DELIVERED {n:02}/10'+(f' — enviá hola #{n+1}' if n<10 else ''), flush=True)
                seen = n
        save('supervisor.json', state)

async def main():
    watch = None
    try:
        # No existing service is stopped/recreated. Start the previously stopped transport.
        bindings = json.loads(subprocess.check_output(['podman','inspect','--format','{{json .HostConfig.PortBindings}}','evolution-api'],text=True))
        if bindings.get('8080/tcp') != [{'HostIp':'127.0.0.1','HostPort':'18180'}]:
            raise RuntimeError('Unexpected Evolution configured port binding')
        # start.sh checks podman port, empty on a stopped container on this host.
        # Verified configured binding permits starting the existing container, no recreate.
        subprocess.run(['podman','start','evolution-api'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state['evolution_started_by_this_run'] = True
        subprocess.run([str(LAB/'cloudflare-start.sh')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state['tunnel_pid'] = int((LAB/'data/cloudflared.pid').read_text())
        url = (LAB/'data/cloudflared.url').read_text().strip()
        graph = 'https://graph.facebook.com/'+os.environ.get('META_TEAM360_GRAPH_VERSION','v20.0')
        with httpx.Client(timeout=30, trust_env=False) as c:
            for _ in range(60):
                try:
                    r = c.get('http://127.0.0.1:18180/')
                    if r.is_success: break
                except httpx.HTTPError: pass
                await asyncio.sleep(1)
            else: raise RuntimeError('Evolution unavailable')
            r = c.get(url+'/webhook/meta', params={'hub.mode':'subscribe', 'hub.verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'], 'hub.challenge':'team360-latency-v1'})
            if not r.is_success or r.text != 'team360-latency-v1': raise RuntimeError('Public tunnel challenge failed')
            auth = {'Authorization':'Bearer '+os.environ['META_TEAM360_APP_ID']+'|'+os.environ['META_TEAM360_APP_SECRET']}
            r = c.post(graph+'/'+os.environ['META_TEAM360_APP_ID']+'/subscriptions', headers=auth,
                       data={'object':'whatsapp_business_account','callback_url':url+'/webhook/meta',
                             'verify_token':os.environ['META_TEAM360_VERIFY_TOKEN'],'fields':'messages'})
            r.raise_for_status()
            if r.json().get('success') is not True: raise RuntimeError('Subscription rejected')
            r = c.get(graph+'/'+os.environ['META_TEAM360_APP_ID']+'/subscriptions',headers=auth)
            r.raise_for_status()
            if not any(d.get('callback_url')==url+'/webhook/meta' and d.get('active') for d in r.json().get('data',[])):
                raise RuntimeError('Subscription not active')
        state['transport_preflight'] = 'PASS'
        host = subprocess.check_output(['podman','exec','evolution-api','node','-e',
            "require('dns').lookup('host.containers.internal',(e,a)=>{if(e)process.exit(1);console.log(a)})"],text=True).strip()
        state['host'] = host
        save('supervisor.json', state)
        watch = asyncio.create_task(monitor())
        # Infinite deadline deliberately prevents count=1 or timeout cleanup while traffic remains incomplete.
        code = await run(SimpleNamespace(host=host,port=18181,duration=float('inf'),count=10,output=str(OUT/'session')))
        state['session_exit_code'] = code
        state['status'] = 'PASS' if code==0 else 'BLOCKED'
        if code==0:
            evidence = json.loads((OUT/'session/evidence.json').read_text())
            latency = json.loads((OUT/'latency.json').read_text())
            latency.update(status='PASS' if evidence['n']==10 and evidence['sequential'] else 'BLOCKED')
            save('latency.json',latency)
    except Exception as exc:
        state.update(status='BLOCKED',error_class=type(exc).__name__)
    finally:
        if watch:
            watch.cancel()
            try: await watch
            except asyncio.CancelledError: pass
        # Leave transport alive for explicit post-run inspection/owned cleanup; do not touch unrelated services.
        save('supervisor.json',state)

if __name__=='__main__':
    asyncio.run(main())

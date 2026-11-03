"""Managed owner-authorized closed DEV launch; no webhook or Meta setup calls.

Keep the old stopped container as rollback. Only terminate a child created here
on failure. No automigration launcher, fallback, replay, business turn or send.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).parent))
from inspect_consumers import ROOT, PRIVATE, OUT, LAB
from provision import P, save
import httpx

IMAGE='5a25df47f4bb71764d2fd033f07428e5be0cbc010b33d05851a5166e89f4b175'
BACKUP='evolution-api-pre-v1-20261023'
BACKEND=ROOT/'SrvRestAstroLS_v1/backend'


def podman(*args,**kwargs):
    return subprocess.run(['podman',*args],check=True,capture_output=True,timeout=120,**kwargs).stdout.decode().strip()


def free_port(port):
    with socket.socket() as s: s.bind(('127.0.0.1',port))


def backend_environment():
    control=json.loads((PRIVATE/'whatsapp-dev-control.json').read_text())
    env={**os.environ,**control['env'], 'TEAM360_DB_URL':json.loads((P/'runtime-dsns.json').read_text())['team360'],
        'TEAM360_EVOLUTION_API_KEY':json.loads((P/'credential.json').read_text())['credential'],
        'TEAM360_TRANSPORT_V1_CONFIG':str(P/'team360.json'),
        'TEAM360_TELCHI_WHATSAPP_APPROVAL':str(P/'approval.json') if (P/'approval.json').exists() else str(PRIVATE/'whatsapp-dev-session-approval.json'),
        'TEAM360_TRANSPORT_V1_RUNTIME_ROLE':'t360devv1_runtime',
        'TEAM360_V1_BACKEND_HOST':control['host'],
        'PYTHONPATH':str(BACKEND),'PYTHONDONTWRITEBYTECODE':'1', 'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
    assert env['TEAM360_ENV'] in ('dev','development')
    assert env['TEAM360_DB_URL'].startswith('postgresql://')
    return env


def main():
    os.umask(0o077)
    assert not (P/'owned-runtime.json').exists()
    for port in (18180,18181): free_port(port)
    old=json.loads(podman('inspect','evolution-api'))[0]
    assert old['State']['Status']=='created' and not old['State']['Running']
    assert list(old['NetworkSettings']['Networks'])==['evolution-api-net']
    assert len(old['Mounts'])==1 and old['Mounts'][0]['Destination']=='/evolution/store'
    podman('image','exists',IMAGE)
    runtime=json.loads((P/'team360.json').read_text());evo=json.loads((P/'evolution.json').read_text())
    assert runtime['admission_open'] is False and evo['admission_open'] is False
    assert not Path(runtime['socket']).exists()
    if (P/'pre-v1-container-inspect.json').exists():
        assert json.loads((P/'pre-v1-container-inspect.json').read_text())['Id']==old['Id']
    else:
        save('pre-v1-container-inspect.json',old)
    env=backend_environment()
    attempt=str(time.time_ns())
    log=open(P/('srv05-'+attempt+'.log'),'xb')
    child=subprocess.Popen([str(BACKEND/'.venv/bin/python'),'-m','uvicorn',
        'modules.telchi.assistant.transport_dev:create_app','--factory','--host',env['TEAM360_V1_BACKEND_HOST'],'--port','18181',
        '--no-access-log','--log-level','warning','--workers','1'],cwd=BACKEND,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    owned={'srv05_pid':child.pid,'srv05_start_ticks':Path('/proc/'+str(child.pid)+'/stat').read_text().split()[21],
        'evolution_container_id':None,'prior_container_id':old['Id'],'prior_container_name':BACKUP,
        'admission_open':False,'intentional_dev_service':True}
    renamed=False;container=None
    try:
        with httpx.Client(trust_env=False,timeout=1) as client:
            for _ in range(150):
                assert child.poll() is None,'Owned Srv05 startup failed; inspect PRIVATE_ROOT log'
                try:
                    if client.get('http://'+env['TEAM360_V1_BACKEND_HOST']+':18181/health').status_code==200 and Path(runtime['socket']).is_socket(): break
                except httpx.HTTPError: pass
                time.sleep(.2)
            else: raise RuntimeError('Owned Srv05 startup timeout')
        overlay=dict(v.split('=',1) for v in old['Config']['Env'])
        overlay.update(TRANSPORT_V1_DEV_CONFIG=str(P/'evolution.json'),
            TRANSPORT_V1_DEV_CONFIG_SHA256=hashlib.sha256((P/'evolution.json').read_bytes()).hexdigest(),
            DATABASE_CONNECTION_URI=json.loads((P/'evolution-runtime-dsn.json').read_text())['url'],
            NODE_OPTIONS='--max-old-space-size=512')
        assert not overlay.get('TRANSPORT_V1_LAB_CONFIG')
        assert all('\n' not in k+v and '\r' not in k+v for k,v in overlay.items())
        env_data=''.join(k+'='+v+'\n' for k,v in overlay.items())
        if (P/'evolution.env').exists():
            assert (P/'evolution.env').read_text()==env_data
        else:
            fd=os.open(P/'evolution.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write(env_data)
        podman('rename','evolution-api',BACKUP);renamed=True
        container=podman('run','-d','--pull=never','--name','evolution-api',
            '--cidfile',str(P/('container-'+attempt+'.cid')),'--label','io.team360.dev-v1-run='+attempt,
            # Reuse the previously accredited default rootless mapping: host UID
            # 1000 is container root; SO_PEERCRED still observes host UID 1000.
            # keep-id needlessly requests an alternate whole-image UID mapping.
            '--network','evolution-api-net','--memory','768m','--cpus','1','--pids-limit','128',
            '--read-only','--tmpfs','/tmp:rw,size=64m','--stop-timeout','10',
            '-p','127.0.0.1:18180:8080','--env-file',str(P/'evolution.env'),
            '-v',old['Mounts'][0]['Source']+':/evolution/store:rw', '-v',str(P)+':'+str(P)+':rw',
            '--entrypoint','node',IMAGE,'dist/main.js')
        owned['evolution_container_id']=container
        with httpx.Client(trust_env=False,timeout=1) as client:
            for _ in range(100):
                try:
                    r=client.post('http://127.0.0.1:18180/transport/v1/instances/'+runtime['scope']['instance_id']+'/sendText',
                        headers={'apikey':env['TEAM360_EVOLUTION_API_KEY']},json={})
                    if r.status_code==403: break
                except httpx.HTTPError: pass
                assert json.loads(podman('inspect',container))[0]['State']['Running'],'Owned Evolution failed; private logs only'
                time.sleep(.3)
            else: raise RuntimeError('Evolution V1 closed admission preflight failed')
        save('owned-runtime.json',owned)
        result={'srv05_pid':child.pid,'evolution_container_id':container,'v1_closed_admission_http':403,
            'callback_socket':str(P/'callback.sock'),'callback_mode':oct((P/'callback.sock').stat().st_mode&0o777),
            'automigrations':False,'meta_setup_calls':0,'real_messages_sent':0,'admission_open':False,
            'prior_container_preserved':True,'host_preflight':'SAFE','owned_processes_intentionally_running':2}
        (OUT/'runtime-start.json').write_text(json.dumps(result,indent=2)+'\n')
        print('SRV05_STARTED=YES EVOLUTION_DEV_RUNNING=YES CALLBACK_SOCKET=0600 V1_SEND_ADMISSION=CLOSED')
    except BaseException:
        cidfile=P/('container-'+attempt+'.cid')
        if container is None and cidfile.exists():
            candidate=cidfile.read_text().strip()
            inspect=json.loads(podman('inspect',candidate))[0]
            assert inspect['Config']['Labels']['io.team360.dev-v1-run']==attempt
            container=candidate
        if container:
            podman('stop','--time','10',container);podman('rm',container)
        if renamed: podman('rename',BACKUP,'evolution-api')
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill();child.wait(timeout=5)
        raise
    finally: log.close()

if __name__=='__main__': main()

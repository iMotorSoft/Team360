"""Restart only this task's recorded Srv05 child; never another backend/container."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).parent))
from start_runtime import P, OUT, BACKEND, backend_environment
from modules.telchi.assistant.whatsapp_dev_lifecycle import atomic
import httpx

os.umask(0o077)
owned=json.loads((P/'owned-runtime.json').read_text());pid=owned['srv05_pid'];proc=Path('/proc')/str(pid)
assert proc.exists() and proc.joinpath('stat').read_text().split()[21]==owned['srv05_start_ticks']
assert b'modules.telchi.assistant.transport_dev:create_app' in proc.joinpath('cmdline').read_bytes()
os.kill(pid,signal.SIGTERM)
for _ in range(100):
    if not (P/'callback.sock').exists():break
    time.sleep(.1)
else:raise RuntimeError('Owned Srv05 callback did not shut down; do not force unlink')
env=backend_environment()
log=open(P/('srv05-restart-'+str(time.time_ns())+'.log'),'xb')
child=subprocess.Popen([str(BACKEND/'.venv/bin/python'),'-m','uvicorn','modules.telchi.assistant.transport_dev:create_app',
    '--factory','--host',env['TEAM360_V1_BACKEND_HOST'],'--port','18181','--no-access-log','--log-level','warning','--workers','1'],
    cwd=BACKEND,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
try:
    with httpx.Client(trust_env=False,timeout=1) as client:
        for _ in range(150):
            assert child.poll() is None,'Owned Srv05 failed; inspect private restart log'
            proof=P/('srv05-ready-'+str(child.pid)+'.json')
            try:
                if proof.exists() and client.get('http://'+env['TEAM360_V1_BACKEND_HOST']+':18181/health').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        else:raise RuntimeError('Owned Srv05 readiness timeout')
    ready=json.loads(proof.read_text())
    assert ready['database_role']=='t360devv1_runtime' and ready['provider']=='BoundEvolutionProvider'
    assert ready['callback_started'] and ready['telchi_handler_registered'] and ready['admission_open'] is False
    owned.update(srv05_pid=child.pid,srv05_start_ticks=Path('/proc/'+str(child.pid)+'/stat').read_text().split()[21])
    atomic(P/'owned-runtime.json',owned)
    (OUT/'srv05-live-attestation.json').write_text(json.dumps(ready,indent=2)+'\n')
    print('SRV05_PROVIDER_V1=PASS DEDICATED_RUNTIME_ROLE=PASS CALLBACK_STARTED=YES ADMISSION=CLOSED')
except BaseException:
    if child.poll() is None:
        child.terminate();child.wait(timeout=15)
    raise
finally:log.close()

"""Reuse the existing six-guarantee runner, not a new business inventory/battery.

One real model/readonly Foundation turn with recording egress and a fresh isolated
receiver_context; original 1335/164 events are never replayed, altered or removed.
The only adaptation is V1's management/runtime credential separation and a private
V1 gate registry. No old registry/approval/control is overwritten. No Meta calls.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).parent))
from inspect_consumers import ROOT, PRIVATE, OUT
from provision import P, save

SOURCE=ROOT/'data/reports/telchi/six-gates-reaccreditation-20261021/reaccredit.py'
spec=importlib.util.spec_from_file_location('existing_six_gate_runner',SOURCE)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
# The imported runner only loads the old configuration and creates its own private
# evidence directory. Replace trusted deployment inputs BEFORE any probe.
# The existing controller is the sole launch configuration authority.
# Legacy manual reproduction remains available when no V1 controller is selected.
if r.config['env'].get('TEAM360_TRANSPORT_V1_CONFIG'):
    os.environ.update(r.config['env'])
else:
    from start_runtime import backend_environment
    os.environ.update(backend_environment())
approval=dict(r.a);approval['gates_file']=str(P/'gates.json')
if (P/'approval.json').exists():
    assert json.loads((P/'approval.json').read_text())==approval
else:save('approval.json',approval)
if not (P/'gates.json').exists():save('gates.json',json.loads(r.old_bytes))
r.ap=P/'approval.json';r.a=r.d.read_approval(r.ap);r.mp=P/'gates.json';r.old_bytes=r.mp.read_bytes()
r.source=r.d.source_digest();r.configuration=r.d.configuration_digest()
r.config=dict(r.config,port=18182)
r.r.update(source_sha256=r.source,configuration_sha256=r.configuration,approval_sha256=r.d.approval_digest(r.a),
    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    reused_runner_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    host_preflight='SAFE: 8 CPUs, ~6 GiB MemAvailable, stable swap; one runner, PG max3, DuckDB threads2')
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
original_preflight=r.d.preflight


def v1_preflight(path, *, require_gates=True):
    # The V1 credential is intentionally NOT a management credential. Existing
    # instance/configuration are verified with the original read-only management
    # key, never sent in a runtime send/callback request.
    import httpx
    a=r.d.read_approval(path);srv,settings=r.d.configuration()
    assert hashlib.sha256(settings.authorized_sender.encode()).hexdigest()==a['sender_sha256']
    binding=asyncio.run(r.d.check_database(a,settings,srv.evolution))
    with r.d.client_for(srv.evolution) as client:
        state=r.d.api(client,'GET','/instance/connectionState/'+srv.evolution.instance)
        assert state.get('instance',{}).get('state')=='open'
        r.d.webhook_body(r.d.api(client,'GET','/webhook/find/'+srv.evolution.instance))
    if require_gates:r.d.gate_evidence(a)
    return a,srv,settings,binding


def focused():
    paths=['tests/test_messaging_binding_administration.py','tests/test_messaging_single_owner_dev.py',
        'tests/test_srv05_evolution_isolation.py','tests/test_telchi_transport_dev.py',
        'modules/telchi/assistant/tests/test_dev_gate_policy.py',
        'modules/telchi/assistant/tests/test_whatsapp_operational_contract.py']
    # Unit fixtures must never inherit real binding/trust/dispatcher/DB inputs.
    # The earlier four failures were fixture pollution by this harness, not a
    # demonstrated runtime defect; initial clean-shell 71 contracts already pass.
    unit_env={k:v for k,v in os.environ.items() if not k.startswith(('TEAM360_','META_TEAM360_'))}
    unit_env['AUTOMATION_DIAGNOSIS_REPOSITORY']='memory'
    process=subprocess.run([sys.executable,'-m','pytest',*paths,'-q'],cwd=r.BACKEND,
        env=unit_env,capture_output=True,text=True,timeout=90,umask=0o022)
    p=r.out/'focused-tests.txt';r.d.save_private(p,{'stdout':process.stdout,'stderr':process.stderr})
    return {'command':'pytest '+' '.join(paths)+' -q','exit_code':process.returncode,
        'result':process.stdout.strip().splitlines()[-1:] ,'artifact':str(p),'sha256':r.sha(p)}


if __name__=='__main__':
    r.d.preflight=v1_preflight
    try:
        if '--resume-observations' in sys.argv:
            previous=r.d.private_file(sys.argv[sys.argv.index('--resume-observations')+1])
            prior=json.loads(previous.read_text())
            assert prior['source_sha256']==r.source and prior['configuration_sha256']==r.configuration
            assert prior['approval_sha256']==r.d.approval_digest(r.a)
            assert set(prior['gates'])==r.d.GATES and set(prior['observations'])==r.d.GATES
            assert all(g['status']=='PASS' for g in prior['observations'].values())
            assert prior['pool_closed'] and prior['whatsapp_sends']==0
            prior['resumed_observations']={'artifact':str(previous),'sha256':r.sha(previous),
                'reason':'All six real observations passed; rerun only the unit harness with clean fixture environment.'}
            r.r=prior
        else:
            report=asyncio.run(r.http_gate());r.d.save_private(r.out/'http-container.json',report)
            r.gate('http_auth','Fresh current PilotBoundary/Srv05 inert authentication and container reachability, lifespan off, no message/Meta calls.')
            r.observe('http_auth',cases=[o['case'] for o in report['observations']],
                container_auth_reachability=report['container_auth_reachability'],listener_closed=report['listener_closed'],whatsapp_sends=0)
            asyncio.run(r.run())
        assert r.source==r.d.source_digest() and r.configuration==r.d.configuration_digest()
        assert set(r.r['gates'])==r.d.GATES
        r.focused_tests=focused
        summary=r.publish()
        summary['renewal_scope']='V1 private registry; one reused six-guarantee probe, not a broad business suite'
        summary['legacy_control_unchanged']=True
        summary['v1_source_manifest_sha256']=r.source
        (OUT/'v1-six-gates.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({k:summary[k] for k in ('SIX_GATES','CURRENT_CODE_FINGERPRINT','REAL_SECURITY_BOUNDARIES','whatsapp_sends','validations')}))
    except BaseException as exc:
        r.r.update(status='BLOCKED',error_class=type(exc).__name__)
        r.d.save_private(r.out/'v1-accreditation-failure.json',r.r)
        print(json.dumps({'SIX_GATES':'BLOCKED','error_class':type(exc).__name__,'evidence':str(r.out)}))
        raise
    finally:r.d.preflight=original_preflight

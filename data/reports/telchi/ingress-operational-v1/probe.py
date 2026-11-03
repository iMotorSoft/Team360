"""Focused local HTTP probe. No runtime startup hooks, outbound or webhook changes."""
import asyncio
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
config_path = d.PRIVATE_ROOT / 'whatsapp-dev-control.json'
config = l.load_config(config_path)
apath = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(apath)
srv, settings = d.configuration()
manifest = d.private_file(a['gates_file'])
before = {str(p): sha(p) for p in (config_path, apath, manifest)}
source = d.source_digest()
output = d.PRIVATE_ROOT / ('ingress-operational-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(mode=0o700)
report = dict(generated_at=datetime.now(timezone.utc).isoformat(), branch='feature/console-backend-core',
    source_sha256=source, approval_sha256=d.approval_digest(a), runner_sha256=sha(__file__),
    configuration_sha256=sha(config_path), observations=[],
    host_preflight='BUSY_BUT_SAFE: 8 CPUs, load 2.45/1.84/1.65, MemAvailable 6080 MiB, swap 5 MiB, vmstat 88% idle and no swap IO; one listener, requests sequential, PG pool max 2',
    scope='Production Srv05 composition + PilotBoundary over real loopback HTTP. Lifespan disabled; owned PG pool only. No normal TelchiAI launch, model, Foundation, Meta, Evolution or Cloudflare calls.',
    affected_gate='http_auth: positive messages.upsert admission invalidated by removal of base pilot permission',
    gates_published=False, unrelated_processes_terminated=0)
old_manifest = json.loads(manifest.read_text())
report['historical_evidence'] = {name: dict(status=g.get('status'), kind=g.get('kind'),
    artifact_sha256=g.get('sha256'), artifact_integrity=sha(d.private_file(g['artifact'])) == g['sha256'],
    applicability='Supporting evidence preserved; not reaccredited by this blocked probe')
    for name, g in old_manifest.get('gates', {}).items()}
report['manifest_source_matches'] = old_manifest.get('source_sha256') == source
report['manifest_approval_matches'] = old_manifest.get('approval_sha256') == d.approval_digest(a)
report['previous_attempts'] = ['First harness timed out (ENVIRONMENTAL_ABORT, no conclusion); process absence checked',
    'Second harness exposed construction ValueError before listener; process exited; final harness moves composition before resource allocation']
counts = Counter()
errors = set()
watched = {('evolution_whatsapp.py', 'build_service'): 'build_service',
    ('evolution_whatsapp.py', '_receive'): 'real_ingress',
    ('service.py', 'process'): 'messaging_process', ('identity.py', 'resolve'): 'identity_resolution',
    ('handler.py', 'handle'): 'handler', ('luna.py', 'interpret'): 'model',
    ('capabilities.py', 'execute'): 'capability', ('provider.py', 'send_text'): 'outbound'}

def observe(frame, event, arg):
    if event not in {'call', 'exception'}:
        return observe
    name = (Path(frame.f_code.co_filename).name, frame.f_code.co_name)
    if event == 'call' and name in watched:
        counts[watched[name]] += 1
    if event == 'exception' and name == ('evolution_whatsapp.py', 'build_service'):
        # Whitelist a source literal; never record arbitrary DB/provider error text.
        if str(arg[1]) == 'Approved module permission gate/handler required':
            errors.add('Approved module permission gate/handler required')
    return observe

async def run():
    import httpx
    import uvicorn
    from modules.db.pool import create_pool, open_pool, close_pool, set_pool
    from modules.db.settings import get_database_settings
    from modules.telchi.assistant.composition import create_telchi_app
    from modules.telchi.assistant.handler import BusinessPolicy
    report['session_before'] = l.read_json(l.root() / 'current.json')['state']
    binding = await d.check_database(a, settings, srv.evolution)
    report['database_scope'] = dict(status='PASS', tenant_matches=binding.tenant_id == a['tenant_id'],
        workspace_matches=binding.workspace_id == a['workspace_id'])
    report['own_processes_left_running'] = 0
    print('READ_ONLY_DB_PREFLIGHT=PASS', flush=True)
    access = {'revoked': False}
    def access_check():
        d.unchanged_approval(apath, a)
        if access['revoked']:
            raise PermissionError('probe_revoked')
    policy = BusinessPolicy(a['tenant_id'], a['workspace_id'], None, a['module_enabled'],
        a['whole_workspace_scope_verified'], pilot_access_check=access_check,
        pilot_user_id=a['user_id'], pilot_approval_sha256=d.approval_digest(a))
    # Construct the unmodified runtime before allocating a listener or pool.
    app = d.PilotBoundary(create_telchi_app(policy=policy), settings,
        srv.evolution, srv.recipient, access_check)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=2))
    await open_pool(pool)
    set_pool(pool)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(8)
    sock.setblocking(False)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_config=None,
        access_log=False, timeout_keep_alive=1, workers=1))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    report['listener'] = dict(host='127.0.0.1', port=port, process=l.identity(os.getpid()))
    def payload(sender):
        return dict(event='messages.upsert', instance=srv.evolution.instance,
            data=dict(key=dict(id='ingress-local-' + uuid.uuid4().hex,
                remoteJid=sender + '@s.whatsapp.net', fromMe=False),
                message=dict(conversation='Mostrame las últimas 5 facturas de venta de Telchi.')))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.05)
        assert server.started
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=10) as client:
            foreign = '19999999999' if settings.authorized_sender != '19999999999' else '18888888888'
            cases = [('missing_token', settings.authorized_sender, False, False, 401),
                ('unauthorized_sender', foreign, True, False, 403),
                ('revoked_access', settings.authorized_sender, True, True, 403),
                ('authorized_pilot', settings.authorized_sender, True, False, 200)]
            for label, sender, token, revoked, expected in cases:
                access['revoked'] = revoked
                counts.clear()
                errors.clear()
                headers = {'x-team360-webhook-token': settings.webhook_token} if token else {}
                sys.setprofile(observe)
                sys.settrace(observe)
                try:
                    response = await client.post(d.WEBHOOK, json=payload(sender), headers=headers)
                finally:
                    sys.setprofile(None)
                    sys.settrace(None)
                report['observations'].append(dict(case=label, status=response.status_code,
                    expected=expected, passed=response.status_code == expected,
                    entries=dict(counts), known_source_errors=sorted(errors)))
                print(f'{label}: HTTP {response.status_code}', flush=True)
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 10)
        finally:
            sock.close()
            await close_pool(pool)
        report['listener_closed'] = task.done() and sock.fileno() == -1
        report['pool_closed'] = pool.closed
        report['session_after'] = l.read_json(l.root() / 'current.json')['state']

try:
    asyncio.run(asyncio.wait_for(run(), timeout=45))
except Exception as exc:
    report['error_class'] = type(exc).__name__
    if str(exc) == 'Approved DEV horizontal handler registry required':
        report['blocker'] = str(exc)
        report['classification'] = 'FUNCTIONAL_FAILURE: production Srv05 refuses permissionless pilot registration before listener construction; no guard bypass authorized'
    report['session_after'] = l.read_json(l.root() / 'current.json')['state']
finally:
    report['source_unchanged'] = source == d.source_digest()
    report['private_inputs_unchanged'] = all(sha(p) == value for p, value in before.items())
    if report.get('listener_closed') and report.get('pool_closed'):
        report['own_processes_left_running'] = 0
    elif 'listener' in report:
        report['own_processes_left_running'] = 'UNKNOWN'
    report['status'] = 'PASS' if len(report['observations']) == 4 and all(x['passed'] for x in report['observations']) else 'BLOCKED'
    d.save_private(output / 'result.json', report)
    report['private_artifact'] = str(output / 'result.json')
    report['private_artifact_sha256'] = sha(output / 'result.json')
    Path(__file__).with_name('result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

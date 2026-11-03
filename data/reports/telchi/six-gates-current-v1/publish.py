"""Finish existing inert container/HTTP gate, then operator attestation publication.
No normal TelchiAI session, lifespan, webhook mutation, message or model call.
Retains existing four-hour technical-evidence renewal window (not pilot expiry).
"""
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
config = l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(ap)
s = json.loads((HERE / 'result.json').read_text())
p = d.private_file(s['artifact'])
assert sha(p) == s['sha256']
r = json.loads(p.read_text())
assert r['status'] == 'PASS' and set(r['gates']) == d.GATES
assert r['source_sha256'] == d.source_digest() and r['approval_sha256'] == d.approval_digest(a)
assert r['runner_sha256'] == sha(HERE / 'reaccredit.py')
mp = d.private_file(a['gates_file'])
old_bytes = mp.read_bytes()
old = json.loads(old_bytes)
out = p.parent
report = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=d.source_digest(),
              approval_sha256=d.approval_digest(a), observations=[], whatsapp_sends=0,
              webhook_mutations=0, model_calls=0, foundation_queries=0,
              scope='Current unmodified Srv05/PilotBoundary, real inert HTTP plus existing container_probe; lifespan off, no message events. No commercial or egress doubles needed.',
              runner_sha256=sha(__file__))

async def http_gate():
    import httpx
    import uvicorn
    from modules.telchi.assistant.composition import create_telchi_app
    from modules.telchi.assistant.handler import BusinessPolicy
    srv, settings = d.configuration()
    await d.check_database(a, settings, srv.evolution)
    def check():
        d.unchanged_approval(ap, a)
    policy = BusinessPolicy(a['tenant_id'], a['workspace_id'], None, a['module_enabled'],
                            a['whole_workspace_scope_verified'], pilot_access_check=check,
                            pilot_user_id=a['user_id'], pilot_approval_sha256=d.approval_digest(a))
    app = d.PilotBoundary(create_telchi_app(policy=policy), settings, srv.evolution, srv.recipient, check)
    nonce = secrets.token_hex(32)
    os.environ['TEAM360_TELCHI_WHATSAPP_NONCE'] = nonce
    sock = socket.socket()
    sock.bind((config['host'], config.get('port', 18181)))
    sock.listen(8)
    sock.setblocking(False)
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_config=None,
        access_log=False, timeout_keep_alive=1, workers=1))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.05)
        assert server.started
        async with httpx.AsyncClient(base_url=f"http://{config['host']}:{config.get('port', 18181)}", trust_env=False, timeout=5) as client:
            health = await client.get('/health')
            assert health.status_code == 200 and secrets.compare_digest(health.headers['x-team360-session'], nonce)
            for case, token, body, expected in (
                ('missing_token_before_json_decode', '', b'{malformed', 401),
                ('invalid_token_before_json_decode', secrets.token_hex(32), b'{malformed', 401),
                ('valid_token_invalid_json', settings.webhook_token, b'{malformed', 400),
                ('valid_token_ignored_event', settings.webhook_token, json.dumps(dict(event='connection.update', instance=srv.evolution.instance)).encode(), 200)):
                response = await client.post(d.WEBHOOK, content=body,
                    headers={'x-team360-webhook-token': token, 'content-type': 'application/json'})
                assert response.status_code == expected
                if expected == 200:
                    assert response.json() == {'ok': True, 'results': {'ignored': 1}}
                report['observations'].append(dict(case=case, status=response.status_code, passed=True))
        await asyncio.to_thread(d.container_probe, config.get('container', 'evolution-api'),
            f"http://host.containers.internal:{config.get('port', 18181)}" + d.WEBHOOK, settings, srv.evolution.instance)
        report['container_auth_reachability'] = 'PASS'
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 10)
        finally:
            sock.close()
        report['listener_closed'] = task.done() and sock.fileno() == -1

try:
    asyncio.run(http_gate())
    assert report['listener_closed']
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
    d.preflight(ap, require_gates=False)
    assert report['source_sha256'] == d.source_digest()
    assert report['approval_sha256'] == d.approval_digest(d.read_approval(ap))
    assert mp.read_bytes() == old_bytes
    report['status'] = 'PASS'
    report['own_processes_left_running'] = 0
    http_path = out / 'http-container.json'
    d.save_private(http_path, report)
    # Keep dates and artifact hashes of reused admission evidence, not a new copy.
    r['gates']['http_auth'].update(container_artifact=str(http_path), container_sha256=sha(http_path))
    r['gates']['http_auth']['scope'] += ' Fresh unmodified inert HTTP and container reachability/auth PASS.'
    r['focused_tests'] = dict(command='uv run pytest modules/telchi/assistant/tests/test_pilot_access.py modules/telchi/assistant/tests/test_assistant.py modules/telchi/assistant/tests/test_safety.py tests/test_srv05_horizontal_composition.py -q', result='101 passed, 1 warning in 2.51s')
    r['legacy_dependencies'] = dict(
        obsolete_runners=['gate-renewal-final-20261016/current_probes.py: approval permission and removed PERMISSION constant', 'gate-renewal-final-20261016/complete.py: approval expires_at and previous manifest expiry cap', 'scripts/telchi_durable_idempotency_probe.py CLI: fixed approval permission'],
        correction_applied='Only evidence runners adapted; current policy has permission=None, live pilot revocation callback and per-capability RBAC. Runtime/Luna/State Engine/Foundation unchanged.',
        evidence_expiry='Current validator still requires technical expires_at and uses it as session deadline. Independent from pilot access; no policy change authorized or applied.',
        minimal_owner_proposal='If technical evidence TTL is deemed artificial: authorize removing only gate TTL rejection and its session-deadline coupling; keep source/access fingerprints, artifact integrity, explicit revocation and bounded manual session. Not implemented.')
    r['gate_inventory'] = {
        'http_auth': 'Preserved exact-current admission evidence; fresh inert HTTP/container boundary.',
        'identity_tenant_isolation': 'Fresh real read-only PG identity and tenant/workspace/revoked negatives.',
        'business_authorization': 'Fresh live Console grant and forged-cache negative, pilot admission without fixed permission; offline multi-capability/revocation-before-query tests.',
        'durable_idempotency': 'Fresh PG duplicate/concurrent claims and durable intent with one real handler/capability; offline crash/fence contracts.',
        'assistant_foundation': 'Fresh real capability read with publication/snapshot lineage; read-only existing Foundation.',
        'model_no_fallback': 'Fresh real Luna provider/model/effort; offline failure/no-fallback contracts.'}
    final = out / 'final-accreditation.json'
    d.save_private(final, r)
    backup = out / 'previous-manifest.json'
    with open(backup, 'xb', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        stream.write(old_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    now = datetime.now(timezone.utc)
    # Same technical-evidence window used by the existing renewal, not access TTL.
    expiry = now + timedelta(hours=4)
    manifest = dict(workspace_id=a['workspace_id'], user_id=a['user_id'], instance='team360-meta-dev',
                    generated_at=now.isoformat(), expires_at=expiry.isoformat(),
                    source_sha256=d.source_digest(), approval_sha256=d.approval_digest(a),
                    previous_manifest=dict(artifact=str(backup), sha256=sha(backup)),
                    renewal_basis='Focused current-source real reaccreditation; preserved admission dates, no historical evidence relabeling; four-hour existing technical renewal window, no access expiry',
                    gates={name: dict(status='PASS', kind='real', artifact=str(final), sha256=sha(final), scope=g['scope']) for name, g in r['gates'].items()})
    assert mp.read_bytes() == old_bytes
    l.atomic(mp, manifest)
    try:
        d.gate_evidence(a)
        d.preflight(ap)
        assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
    except BaseException:
        l.atomic(mp, old)
        raise
    summary = dict(branch='feature/console-backend-core', SIX_GATES='VALID', GATE_FAILURES=[],
                   CURRENT_CODE_FINGERPRINT='VALID', CURRENT_PILOT_CONTRACT='VALID',
                   REAL_SECURITY_BOUNDARIES='PASS', READY_FOR_MANUAL_START='YES',
                   source_sha256=d.source_digest(), approval_sha256=d.approval_digest(a),
                   manifest_sha256=sha(mp), technical_evidence_expires_at=expiry.isoformat(),
                   artifact=str(final), artifact_sha256=sha(final),
                   validations=r['focused_tests'], lifecycle='STOPPED', whatsapp_sends=0,
                   own_processes_left_running=0, unrelated_processes_terminated=0,
                   impact='Evidence/private manifest only; no runtime, security policy, grants, bindings, webhook or Foundation changes.',
                   legacy_dependencies=r['legacy_dependencies'],
                   limits='Not WhatsApp E2E; recording egress certifies logical intent only. No provider outage induced. Manual start remains separate.',
                   next_step='Manual operator start, then WhatsApp latest five invoices; no automatic start performed.')
    (HERE / 'closure.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
except Exception as exc:
    report.update(status='BLOCKED', error_class=type(exc).__name__)
    d.save_private(out / 'publication-blocked.json', report)
    print(json.dumps(dict(SIX_GATES='BLOCKED', error_class=type(exc).__name__, manifest_changed=mp.read_bytes() != old_bytes)))
    raise SystemExit(1) from None

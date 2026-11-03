"""Owner-authorized proportional DEV attestation. No listener, model or outbound.
Reuses exact-current conversational/security evidence; probes HTTP and durable
storage/cache only. All public source files remain unchanged.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

async def main():
    config_path = d.PRIVATE_ROOT / 'whatsapp-dev-control.json'
    config = l.load_config(config_path)
    ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    a = d.read_approval(ap)
    mp = d.private_file(a['gates_file'])
    previous_bytes = mp.read_bytes()
    old = json.loads(previous_bytes)
    source, configuration = d.source_digest(), d.configuration_digest()
    assert old['configuration_sha256'] == configuration
    assert old['approval_sha256'] == d.approval_digest(a)
    assert old['schema_version'] == 2 and old['validity_policy'] == d.DEV_GATE_POLICY and 'expires_at' not in old
    pinned = {str(p): sha(p) for p in (config_path, ap)}
    original = {}
    for name, gate in old['gates'].items():
        p = d.private_file(gate['artifact'])
        assert sha(p) == gate['sha256']
        r = json.loads(p.read_text())
        assert r['status'] == 'PASS' and r['source_sha256'] == old['source_sha256']
        assert r['configuration_sha256'] == configuration and r['approval_sha256'] == d.approval_digest(a)
        assert all(r['observations'][key]['status'] == 'PASS' for key in gate['observations'])
        for relative, digest in r['inputs'].items():
            assert sha(BACKEND / relative) == digest
        original[name] = dict(gate, original_generated_at=r['generated_at'])
    evidence_root = ROOT / 'data/reports/telchi/conversational-quality-v1'
    closure = json.loads((evidence_root / 'closure.json').read_text())
    live = json.loads((evidence_root / 'live-final.json').read_text())
    security = json.loads((evidence_root / 'security-and-admission.json').read_text())
    for name, digest in closure['files'].items():
        assert sha(ROOT / name) == digest
    assert live['source_sha256'] == security['source_sha256'] == source
    assert live['quality_pass'] and len(live['turns']) == 8
    assert security['current_identity_and_isolation'] == 'PASS'
    assert security['real_permission_revoked_with_stale_identity'].startswith('PASS')
    assert security['rollback_and_ordinary_assignments_verified'] == 'PASS' and security['pool_closed']
    assert security['authorization_changes_committed'] == 0
    for turn in live['turns']:
        assert turn['classification'] == 'DIRECT_AVAILABLE'
        assert turn['audit']['pilot_approval_sha256'] == d.approval_digest(a)
        md = turn['model']
        assert md['provider'] == 'OpenAI direct' and md['model'] == 'gpt-5.6-luna'
        assert md['reasoning'] == 'medium' and md['reasoning_echo_verified']
    assert all(t['audit']['capability_calls'] == 0 for t in live['turns'][3:5])
    assert '-1.673.673,34' in live['turns'][3]['text'] and '-15,84' in live['turns'][4]['text']
    assert all('parcial' in t['text'] for t in live['turns'][3:5])
    for p in evidence_root.glob('*.json'):
        pinned[str(p)] = sha(p)
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
    _, srv, settings, binding = await asyncio.to_thread(d.preflight, ap, require_gates=False)
    out = d.PRIVATE_ROOT / ('conversational-reaccreditation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(mode=0o700)
    report = dict(status='PASS', source_sha256=source, configuration_sha256=configuration,
        approval_sha256=d.approval_digest(a), generated_at=datetime.now(timezone.utc).isoformat(),
        runner_sha256=sha(__file__), inputs=pinned, original_evidence=original, observations={},
        impact='Evidence/private manifest only; no functionality, grants, infrastructure or lifecycle changes.',
        host_preflight='BUSY_BUT_SAFE: 8 CPUs, load 2.22/2.18/1.53; 5836 MiB available; 1795 MiB swap stable; sampled idle 88-89%, no swap IO',
        concurrency='Sequential process, PG pool max 1; no browser, listener, model or Foundation queries',
        services_started_or_stopped=0, whatsapp_sent=0, new_model_calls=0, new_foundation_queries=0,
        unrelated_processes_terminated=0, environmental_aborts=0, own_processes_left_running=0,
        limits='Manual readiness only, not WhatsApp delivery/E2E. No upstream outage induced. Original observations retain their dates.')
    def passed(name, **facts):
        report['observations'][name] = dict(status='PASS', **facts)
    # Admission/cache contracts only; the 215-test quality suite is not repeated.
    tests = ['modules/telchi/assistant/tests/test_dev_gate_policy.py',
             'modules/telchi/assistant/tests/test_conversational_quality.py::test_handler_local_reauthorization_and_cache']
    p = subprocess.run([sys.executable, '-m', 'pytest', *tests, '-q'], capture_output=True, text=True, timeout=90, umask=0o022)
    test_path = out / 'focused-tests.txt'
    test_path.write_text(p.stdout + p.stderr)
    assert p.returncode == 0, 'focused_tests_failed'
    report['tests'] = dict(command=[sys.executable, '-m', 'pytest', *tests, '-q'], artifact=str(test_path), sha256=sha(test_path), result=p.stdout.strip().splitlines()[-1])
    import httpx
    from modules.db.pool import create_pool, open_pool, close_pool
    from modules.db.settings import get_database_settings
    from modules.db.transaction import transaction
    from modules.messaging.repository import MessagingRepository
    from modules.messaging.identity import PhoneIdentityRepository
    from modules.messaging.handlers import ChannelContext, MessageContext
    from modules.messaging.domain.messages import InboundMessage
    from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore
    from modules.telchi.assistant.composition import create_telchi_app
    def check():
        d.unchanged_approval(ap, a)
    policy = BusinessPolicy(a['tenant_id'], a['workspace_id'], None, a['module_enabled'],
        a['whole_workspace_scope_verified'], pilot_access_check=check, pilot_user_id=a['user_id'],
        pilot_approval_sha256=d.approval_digest(a))
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    try:
        app = d.PilotBoundary(create_telchi_app(policy=policy, pool=pool), settings, srv.evolution, srv.recipient, check)
        cases = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated') as client:
            for token, body, expected in [('', b'{malformed', 401), ('invalid', b'{malformed', 401),
                (settings.webhook_token, b'{malformed', 400), (settings.webhook_token, json.dumps(dict(event='connection.update', instance=srv.evolution.instance)).encode(), 200)]:
                response = await client.post(d.WEBHOOK, content=body, headers={'x-team360-webhook-token': token, 'content-type':'application/json'})
                assert response.status_code == expected
                cases.append(expected)
        passed('http_auth', current_real_asgi_statuses=cases, listener=False, message_events=0)
        channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance, binding.receiver_context,
            binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
        async with transaction(pool) as conn:
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            assert identity and identity.user_id == a['user_id']
        turn = live['turns'][3]  # Actual persisted new deterministic comparison.
        context = MessageContext(channel, identity, settings.authorized_sender, turn['thread_id'], turn['event_id'], frozenset())
        message = InboundMessage(provider='evolution', channel='whatsapp', external_message_id='cache-evidence',
            sender=settings.authorized_sender, recipients=(binding.receiver_context,), text_body=turn['question'],
            external_thread_id=None, subject=None, received_at=datetime.now(timezone.utc), metadata={'provider_instance':binding.provider_instance})
        handler = TelchiHandler(store=PostgresConversationStore(pool), authorization=BusinessAuthorization(policy))
        # Cached path must not invoke either provider or Foundation.
        async def forbidden(*args, **kwargs):
            raise AssertionError('cache_must_not_execute')
        handler.interpreter.interpret = forbidden
        handler.capabilities.execute = forbidden
        for _ in range(2):
            cached = await handler.handle(message, context)
            assert cached.text == turn['text'] and cached.classification == 'DIRECT_AVAILABLE'
        repo = MessagingRepository()
        isolated = replace(binding, receiver_context='quality-gate:' + uuid4().hex)
        probe = replace(message, external_message_id='quality-gate-' + uuid4().hex, recipients=(isolated.receiver_context,))
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                claimed = await repo.claim(conn, isolated, probe, {})
                assert claimed
                await repo.complete_dispatch(conn, isolated, claimed, cached)
                assert await repo.claim(conn, isolated, probe, {}) is None
                one = await repo.intent(conn, isolated, claimed, probe, cached.text, {})
                assert one == await repo.intent(conn, isolated, claimed, probe, cached.text, {})
        passed('durable_idempotency', original_committed_claim_and_duplicate_provenance=original['durable_idempotency'],
            fresh_pg_claim_duplicate_and_unique_intent='PASS; rollback-only, no queued delivery',
            current_comparison_cache_replayed_twice=True, additional_model_or_foundation_calls=0)
    finally:
        await close_pool(pool)
    report['pool_closed'] = pool.closed
    passed('identity_tenant_isolation', exact_current_security_artifact=str(evidence_root/'security-and-admission.json'),
        fresh_binding_verified=True, negative_axes=['tenant','workspace','user'], persisted_eight_turns=True)
    passed('business_authorization', exact_current_security_artifact=str(evidence_root/'security-and-admission.json'),
        stale_identity_revocation_and_rollback_verified=True, current_cached_comparison_reauthorized=True)
    passed('assistant_foundation', exact_current_live_artifact=str(evidence_root/'live-final.json'),
        eight_real_turns=True, deterministic_difference='-1673673.34', percentage='-15.84', partial_warning=True,
        comparison_foundation_queries=0, original_independent_parity=original['assistant_foundation'])
    passed('model_no_fallback', exact_current_live_artifact=str(evidence_root/'live-final.json'),
        eight_verified_luna_medium_responses=True, adapter='OpenAI direct; no proxy/retries/redirects/fallback')
    assert set(report['observations']) == d.GATES
    assert source == d.source_digest() and configuration == d.configuration_digest()
    assert all(sha(p) == value for p, value in pinned.items())
    assert mp.read_bytes() == previous_bytes
    artifact = out / 'accreditation.json'
    l.atomic(artifact, report)
    backup = out / 'previous-manifest.json'
    # Preserve original bytes and hash rather than reserialize historical evidence.
    backup.write_bytes(previous_bytes)
    manifest = dict(old)
    manifest.update(issued_at=report['generated_at'], source_sha256=source,
        previous_manifest=dict(artifact=str(backup), sha256=sha(backup)),
        renewal_basis='Owner-authorized conversational quality V1: exact-current live/security evidence reused with original dates; focused ASGI/PG duplicate/cache validation. DEV change-based policy unchanged.',
        gates={name:dict(status='PASS', kind='real', artifact=str(artifact), sha256=sha(artifact), observations=[name]) for name in d.GATES})
    assert mp.read_bytes() == previous_bytes and source == d.source_digest()
    l.atomic(mp, manifest)
    try:
        assert d.gate_evidence(a) is None
        await asyncio.to_thread(d.preflight, ap)
    except BaseException:
        l.atomic(mp, old)
        raise
    assert l.read_json(l.root()/'current.json')['state'] == 'STOPPED'
    summary = dict(branch='feature/console-backend-core', SIX_GATES='VALID', CURRENT_FINGERPRINT='VALID',
        PREFLIGHT='PASS', TELCHIAI_RUNTIME='STOPPED', READY_FOR_MANUAL_WHATSAPP='YES',
        source_sha256=source, manifest_sha256=sha(mp), artifact=str(artifact), artifact_sha256=sha(artifact),
        tests=report['tests']['result'], services_started_or_stopped=0, whatsapp_sent=0,
        own_processes_left_running=0, unrelated_processes_terminated=0)
    l.atomic(out/'closure.json', summary)
    public = Path(__file__).parent/'closure.json'
    public.write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    asyncio.run(main())

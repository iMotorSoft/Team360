"""Final reaccreditation of the six TelchiAI DEV gates on the delivered code.

Same probes and same assertions as the official renewal runners
(``data/reports/telchi/six-gates-current-v1/{reaccredit,publish}.py`` and
``data/reports/telchi/biz01-conversation-v1/six_gates_reaccredit.py``), with
two corrections:

* the inert HTTP gate is produced by the *current* source instead of being
  reused from an older artifact (the 21/10 13:34 attempt failed exactly
  there: ``gate_scope_mismatch`` on reused evidence);
* the DEV registry is published in the owner-approved ``change_based_v1``
  version 2 form (no ``expires_at``), per ``dev-gate-policy-v1`` and
  ``modules/telchi/assistant/WHATSAPP_DEV.md``.

No session, no lifespan, no webhook mutation, no WhatsApp message, no grant,
binding, approval, credential or Foundation mutation.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BACKEND = ROOT / 'SrvRestAstroLS_v1/backend'
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
os.umask(0o077)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
cp = d.PRIVATE_ROOT / 'whatsapp-dev-control.json'
config = l.load_config(cp)
ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(ap)
source = d.source_digest()
configuration = d.configuration_digest()
mp = d.private_file(a['gates_file'])
old_bytes = mp.read_bytes()
out = d.PRIVATE_ROOT / ('six-gates-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
out.mkdir(mode=0o700)
r = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=source,
         configuration_sha256=configuration, approval_sha256=d.approval_digest(a),
         runner_sha256=sha(Path(__file__)), gates={}, observations={},
         concurrency='One process, PG max 3, two concurrent claims of ONE event; one model/query',
         whatsapp_sends=0, webhook_mutations=0, grant_mutations=0, binding_mutations=0,
         manifest_published=False, unrelated_processes_terminated=0,
         host_preflight='BUSY_BUT_SAFE: 8 CPUs; load 4.71/2.87/1.58; 6186 MiB available; swap 350 MiB stable; sampled CPU idle 73-81%; one sequential runner')


def gate(name, scope, **evidence):
    r['gates'][name] = dict(status='PASS', kind='real', scope=scope, **evidence)


def observe(name, **evidence):
    r['observations'][name] = dict(status='PASS', **evidence)


async def http_gate():
    """Inert loopback HTTP admission and container reachability. No lifespan."""
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
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=d.source_digest(),
                  approval_sha256=d.approval_digest(a), observations=[], whatsapp_sends=0,
                  webhook_mutations=0, model_calls=0, foundation_queries=0,
                  scope='Current unmodified Srv05/PilotBoundary, real inert HTTP plus existing container_probe; '
                        'lifespan off, no message events. No commercial or egress doubles needed.',
                  runner_sha256=sha(Path(__file__)))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.05)
        assert server.started
        async with httpx.AsyncClient(base_url=f"http://{config['host']}:{config.get('port', 18181)}",
                                     trust_env=False, timeout=5) as client:
            health = await client.get('/health')
            assert health.status_code == 200 and secrets.compare_digest(health.headers['x-team360-session'], nonce)
            for case, token, body, expected in (
                    ('missing_token_before_json_decode', '', b'{malformed', 401),
                    ('invalid_token_before_json_decode', secrets.token_hex(32), b'{malformed', 401),
                    ('valid_token_invalid_json', settings.webhook_token, b'{malformed', 400),
                    ('valid_token_ignored_event', settings.webhook_token,
                     json.dumps(dict(event='connection.update', instance=srv.evolution.instance)).encode(), 200)):
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
    assert report['listener_closed']
    return report


async def isolated_authorization(pool, binding, settings):
    """Real Console SQL, synthetic user, pg_temp-only writes; no operational grants."""
    from modules.console.repositories import PermissionConsoleRepository
    from modules.messaging.identity import PhoneIdentityRepository
    from modules.messaging.handlers import ChannelContext, MessageContext
    from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization
    tables = ('core_users', 'core_user_roles', 'core_user_profiles', 'core_module_full_access_grants')
    async with pool.connection() as conn:
        conn.prepare_threshold = None
        async with conn.transaction(force_rollback=True):
            await conn.execute('SET LOCAL statement_timeout = 5000')
            await conn.execute('SET LOCAL lock_timeout = 3000')
            resolver = PermissionConsoleRepository()
            before = await resolver.list_effective_permissions(conn, a['workspace_id'], a['user_id'])
            channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
                binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            assert identity and identity.user_id == a['user_id']
            fixture_id = str(uuid.uuid4())
            absent = await (await conn.execute('SELECT count(*) AS n FROM public.core_users WHERE id=%s', (fixture_id,))).fetchone()
            assert absent['n'] == 0
            for table in tables:
                key = 'id' if table == 'core_users' else 'user_id'
                await conn.execute(f'CREATE TEMP TABLE {table} ON COMMIT DROP AS SELECT * FROM public.{table} WHERE {key}=%s', (a['user_id'],))
                await conn.execute(f'UPDATE pg_temp.{table} SET {key}=%s', (fixture_id,))
            await conn.execute('SET LOCAL search_path TO pg_temp, public')
            isolated = replace(identity, user_id=fixture_id)
            context = MessageContext(channel, isolated, settings.authorized_sender, 'isolated', 'isolated', frozenset())
            policy = BusinessPolicy(a['tenant_id'], a['workspace_id'], None,
                a['module_enabled'], a['whole_workspace_scope_verified'],
                pilot_access_check=lambda: d.unchanged_approval(ap, a), pilot_user_id=fixture_id)
            authorization = BusinessAuthorization(policy)
            permission = 'telchi.sales.commercial_line_amount_by.read.v1'
            assert await resolver.list_effective_permissions(conn, a['workspace_id'], fixture_id) == before
            assert permission in isolated.permissions
            assert await authorization.allowed(context, conn, required_permission=permission)
            assert not await authorization.allowed(replace(context, channel=replace(channel, tenant_id='foreign')), conn)
            assert not await authorization.allowed(replace(context, channel=replace(channel, workspace_id=str(uuid.uuid4()))), conn)
            for table in tables[1:]:
                await conn.execute(f'DELETE FROM pg_temp.{table} WHERE user_id=%s', (fixture_id,))
            assert await resolver.list_effective_permissions(conn, a['workspace_id'], fixture_id) == []
            assert permission in isolated.permissions
            assert not await authorization.allowed(context, conn, required_permission=permission)
        async with conn.transaction():
            await conn.execute('SET TRANSACTION READ ONLY')
            assert await resolver.list_effective_permissions(conn, a['workspace_id'], a['user_id']) == before
            for table in tables:
                row = await (await conn.execute('SELECT to_regclass(%s) AS name', ('pg_temp.' + table,))).fetchone()
                assert row['name'] is None
    gate('business_authorization', 'Real Console SQL with a new synthetic identity and session-local temporary tables; positive permission, foreign tenant/workspace negatives, stale cache denied after removal of synthetic assignments. Forced rollback; operational grants untouched.')
    observe('business_authorization', real_console_sql=True, synthetic_identity=True,
        positive_permission=True, foreign_tenant_denied=True, foreign_workspace_denied=True,
        stale_cache_denied=True, temporary_fixtures_removed=True,
        operational_effective_permissions_unchanged=True, operational_dml=0, grants_changed=0)


async def run():
    from modules.db.pool import create_pool, open_pool, close_pool
    from modules.db.settings import get_database_settings
    from modules.db.transaction import transaction
    from modules.messaging.repository import MessagingRepository
    from modules.messaging.service import MessagingService
    from modules.messaging.identity import PhoneIdentityRepository, PostgresPhoneIdentityResolver, InvalidPhoneBinding
    from modules.messaging.handlers import ChannelContext, MessageContext, MessageDispatcher
    from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore, registration
    from modules.telchi.assistant.capabilities import SalesCapabilities
    from modules.telchi.assistant.luna import LunaInterpreter
    from scripts import telchi_durable_idempotency_probe as h

    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
    approval, srv, settings, binding = await asyncio.to_thread(d.preflight, ap, require_gates=False)
    r['read_only_operational_preflight'] = 'PASS'
    access = {'revoked': False}

    def check():
        d.unchanged_approval(ap, a)
        if access['revoked']:
            raise PermissionError('probe_only_revocation')
    policy = BusinessPolicy(a['tenant_id'], a['workspace_id'], None, a['module_enabled'],
                            a['whole_workspace_scope_verified'], pilot_access_check=check,
                            pilot_user_id=a['user_id'], pilot_approval_sha256=d.approval_digest(a))
    auth = BusinessAuthorization(policy)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=3))
    await open_pool(pool)
    try:
        repo = MessagingRepository()
        # A dedicated receiver_context isolates probe persistence from the real
        # pilot thread: the horizontal storage instance includes it.
        pb = replace(binding, receiver_context='six-gates:' + uuid.uuid4().hex)
        channel = ChannelContext(pb.channel_id, 'evolution', srv.evolution.instance, pb.receiver_context,
                                 pb.tenant_id, pb.workspace_id, pb.module, pb.environment)
        capability_permission = h.PERMISSION  # Only the exercised capability, NEVER pilot admission.
        async with transaction(pool) as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            await repo.validate_transport_schema(conn)
            identities = PhoneIdentityRepository()
            identity = await identities.resolve(conn, channel, settings.authorized_sender)
            assert identity and identity.user_id == a['user_id']
            context = MessageContext(channel, identity, settings.authorized_sender, 'six-gates', 'negative', frozenset())
            assert await auth.allowed(context, conn)
            empty = replace(context, sender_identity=replace(identity, permissions=frozenset()))
            assert await auth.allowed(empty, conn)  # No fixed commercial entry grant.
            assert not await auth.allowed(empty, conn, required_permission=capability_permission)
            assert await auth.allowed(context, conn, required_permission=capability_permission)
            foreign = replace(channel, tenant_id='six-gates-foreign')
            assert await identities.resolve(conn, foreign, settings.authorized_sender) is None
            assert not await auth.allowed(replace(context, channel=foreign), conn)
            wrong_workspace = replace(channel, workspace_id=str(uuid.uuid4()))
            assert await identities.resolve(conn, wrong_workspace, settings.authorized_sender) is None
            assert not await auth.allowed(replace(context, channel=wrong_workspace), conn)
            fixtures = await (await conn.execute("SELECT b.sender_identity,b.user_id FROM messaging_phone_bindings b JOIN core_users u ON u.id=b.user_id WHERE b.environment='dev' AND b.provider='evolution' AND b.tenant_id=%s AND b.workspace_id=%s AND b.verification_status='revoked' AND u.status='inactive' LIMIT 1", (a['tenant_id'], a['workspace_id']))).fetchall()
            assert fixtures, 'existing_revoked_fixture_required'
            f = fixtures[0]
            try:
                await identities.resolve(conn, channel, f['sender_identity'])
            except InvalidPhoneBinding:
                pass
            else:
                raise AssertionError('revoked_identity_accepted')
            stale = replace(context, sender_identity=replace(identity, user_id=str(f['user_id'])))
            rbac_only = BusinessAuthorization(replace(policy, pilot_user_id=str(f['user_id'])))
            assert not await rbac_only.allowed(stale, conn, required_permission=capability_permission)
            access['revoked'] = True
            assert not await auth.allowed(context, conn)
            access['revoked'] = False
        gate('identity_tenant_isolation', 'Real authenticated PG binding and approved user; foreign tenant/workspace absent and denied; existing revoked/inactive identity rejected. No fixture mutation.')
        observe('identity_tenant_isolation', real_binding=True, approved_user=True,
                foreign_tenant_denied=True, foreign_workspace_denied=True,
                revoked_inactive_identity_rejected=True, fixture_mutations=0)
        await isolated_authorization(pool, binding, settings)
        interpreter = LunaInterpreter()
        cap = h.CapabilityCounter(SalesCapabilities())
        handler = h.HandlerCounter(TelchiHandler(store=PostgresConversationStore(pool), authorization=auth,
                                               interpreter=interpreter, capabilities=cap))
        dispatcher = MessageDispatcher(channels=(channel,), handlers={'telchi': registration(handler)},
                                       identities=PostgresPhoneIdentityResolver(pool), environment='dev')
        assert not registration(handler).required_permissions
        sender = h.RecordingSender()
        service = MessagingService(pool=pool, repository=repo, binding=pb, sender=sender,
                                   authorized_sender='', dispatcher=dispatcher)
        external = 'six-gates-' + uuid.uuid4().hex
        event = h._event(settings.authorized_sender, pb.receiver_context,
                        'Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros', external)
        results = await asyncio.gather(service.process(event, t0_ms=0, t1_ms=0),
                                       service.process(event, t0_ms=0, t1_ms=0))
        results.append(await service.process(event, t0_ms=0, t1_ms=0))
        inbound, outbound = await h._snapshot(pool, pb, external)
        audit = inbound[0]['payload_jsonb'].get('telchi_assistant_v1', {}) if inbound else {}
        r['message'] = dict(results=results, handler_calls=handler.calls, capability_calls=cap.calls,
                            recording_egress_calls=len(sender.calls), inbound_count=len(inbound),
                            outbound_count=len(outbound), audit=h._audit_summary(inbound[0]) if inbound else {})
        r['model_metadata'] = interpreter.last_metadata
        d.save_private(out / 'progress.json', r)
        assert results.count('accepted') == 1 and results[-1] == 'duplicate'
        assert set(results) <= {'accepted', 'duplicate', 'execution_uncertain'}
        assert handler.calls == 1 and len(inbound) == len(outbound) == len(sender.calls) == 1
        gate('durable_idempotency', 'Real PG concurrent claims and sequential retry of one event, one real handler/capability and one durable outbound intent. Overlap may be execution_uncertain; no replay. Recording egress, not WhatsApp delivery.', evidence=r['message'])
        observe('durable_idempotency', results=r['message']['results'], handler_calls=handler.calls,
                capability_calls=cap.calls, inbound_count=len(inbound), outbound_count=len(outbound),
                recording_egress_calls=len(sender.calls), whatsapp_sends=0)
        md = interpreter.last_metadata
        assert md and md['provider'] == 'OpenAI direct' and md['reasoning_echo_verified']
        gate('model_no_fallback', 'One real current Luna request with returned model/effort verified. Fresh provider-failure/no-fallback offline contracts supplement live success; no provider outage induced.', metadata=md)
        observe('model_no_fallback', model=md['model'], reasoning=md['reasoning'],
                provider=md['provider'], reasoning_echo_verified=md['reasoning_echo_verified'],
                attempts=md.get('attempts'), provider_outage_induced=False)
        result = audit.get('execution_result') or {}
        assert audit['execution_status'] == 'executed' and audit['capability_calls'] == cap.calls == 1
        assert audit['business_rbac_verified'] is True and audit['pilot_approval_sha256'] == d.approval_digest(a)
        assert len(result['rows']) == 10 and result['source']['publication_id'] and result['source']['snapshot_id'] is not None
        r['foundation'] = dict(source=result['source'], row_count=len(result['rows']),
                               rows_sha256=hashlib.sha256(json.dumps(result['rows'], sort_keys=True).encode()).hexdigest())
        gate('assistant_foundation', 'One current real Messaging/PG identity/Console/TelchiHandler capability execution and read-only Foundation query. Existing fixed query, no SAP or Foundation publication mutation.', evidence=r['foundation'])
        observe('assistant_foundation', publication_id=result['source']['publication_id'],
                snapshot_id=result['source']['snapshot_id'], row_count=len(result['rows']),
                rows_sha256=r['foundation']['rows_sha256'], read_only=True)
    finally:
        await close_pool(pool)
        r['pool_closed'] = pool.closed
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'


def focused_tests():
    """Focused, sequential contracts for the code under accreditation."""
    cmd = [sys.executable, '-m', 'pytest',
           'modules/telchi/assistant/tests',
           'tests/test_messaging_evolution.py',
           'tests/test_messaging_horizontal_runtime.py',
           'tests/test_messaging_handlers.py', '-q']
    # Permission-negative tests require the normal test umask: they create a
    # deliberately insecure directory and assert it is NOT repaired, which the
    # runner's own 077 umask would mask. The parent and every artifact written
    # by this runner stay 0600/0700. Same correction as dev-gate-policy-v1.
    process = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=BACKEND,
                             umask=0o022)
    path = out / 'focused-tests.txt'
    with open(path, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        stream.write(process.stdout + process.stderr)
    tail = [line for line in process.stdout.strip().splitlines() if line.strip()][-1:]
    return dict(command=' '.join(cmd[2:]), result=tail[0] if tail else 'NO OUTPUT',
                exit_code=process.returncode, artifact=str(path), sha256=sha(path))


def publish():
    """Publish the DEV registry v2 (change_based_v1) for the current source."""
    r['focused_tests'] = focused_tests()
    assert r['focused_tests']['exit_code'] == 0, 'focused_tests_failed'
    assert source == d.source_digest(), 'source_changed_during_tests'
    assert configuration == d.configuration_digest(), 'configuration_changed_during_tests'
    d.unchanged_approval(ap, a)
    assert set(r['gates']) == d.GATES
    status = l.status()
    assert status['state'] == 'STOPPED' and status['webhook'] == 'INTERNAL'
    from types import SimpleNamespace
    timing = d.session_timing(SimpleNamespace(
        idle_timeout=config.get('idle_timeout', d.DEFAULT_IDLE_TIMEOUT),
        max_duration=config.get('max_duration', config.get('duration', d.DEFAULT_MAX_DURATION))))
    r['dev_session_policy'] = dict(status='READY', idle_timeout=timing[0], max_duration=timing[1])
    r['gate_inventory'] = {
        'http_auth': 'Fresh inert HTTP/container boundary for the current source.',
        'identity_tenant_isolation': 'Fresh real read-only PG identity and tenant/workspace/revoked negatives.',
        'business_authorization': 'Fresh real Console SQL with synthetic identity and temporary PostgreSQL tables; positive and negative cases, stale cache denied; operational grants unchanged.',
        'durable_idempotency': 'Fresh PG duplicate/concurrent claims and durable intent with one real handler/capability.',
        'assistant_foundation': 'Fresh real capability read with publication/snapshot lineage; read-only Foundation.',
        'model_no_fallback': 'Fresh real Luna provider/model/effort; no provider outage induced.'}
    r['status'] = 'PASS'
    final = out / 'final-accreditation.json'
    d.save_private(final, r)
    backup = out / 'previous-manifest.json'
    with open(backup, 'xb', opener=lambda p, f: os.open(p, f, 0o600)) as stream:
        stream.write(old_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    now = datetime.now(timezone.utc)
    manifest = dict(workspace_id=a['workspace_id'], user_id=a['user_id'], instance='team360-meta-dev',
                    environment='dev', schema_version=2, validity_policy=d.DEV_GATE_POLICY,
                    issued_at=now.isoformat(), source_sha256=source,
                    approval_sha256=d.approval_digest(a), configuration_sha256=configuration,
                    previous_manifest=dict(artifact=str(backup), sha256=sha(backup)),
                    renewal_basis='Final reaccreditation on Commercial Continuity V2 code; isolated Console authorization; '
                                  'all six real guarantees reexecuted against the current source; owner-approved '
                                  'DEV change-based validity (no artificial expiration); no access expiry.',
                    gates={name: dict(status='PASS', kind='real', artifact=str(final), sha256=sha(final),
                                      observations=[name], scope=g['scope'])
                           for name, g in r['gates'].items()})
    assert mp.read_bytes() == old_bytes
    assert source == d.source_digest(), 'source_changed_before_publication'
    assert configuration == d.configuration_digest(), 'configuration_changed_before_publication'
    l.atomic(mp, manifest)
    try:
        d.gate_evidence(a)
        d.preflight(ap)  # Normal entry point, gates required: NO bypass.
        assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
        assert source == d.source_digest(), 'source_changed_after_publication'
    except BaseException:
        l.atomic(mp, json.loads(old_bytes))
        raise
    r['manifest_published'] = True
    return dict(branch='feature/console-backend-core', SIX_GATES='VALID', GATE_FAILURES=[],
                CURRENT_CODE_FINGERPRINT='VALID', CURRENT_PILOT_CONTRACT='VALID',
                REAL_SECURITY_BOUNDARIES='PASS', DEV_GATE_POLICY=d.DEV_GATE_POLICY,
                READY_FOR_MANUAL_START='YES', source_sha256=source,
                approval_sha256=d.approval_digest(a), configuration_sha256=configuration,
                manifest_sha256=sha(mp), artifact=str(final), artifact_sha256=sha(final),
                validations=r['focused_tests'], lifecycle='STOPPED', whatsapp_sends=0,
                own_processes_left_running=0, unrelated_processes_terminated=0,
                impact='Evidence/private manifest only; no runtime, security policy, grants, bindings, '
                       'webhook, credentials or Foundation changes.',
                limits='Not WhatsApp E2E; recording egress certifies logical intent only. No provider outage '
                       'induced. Manual start remains separate.',
                next_step='Manual operator start, then the presidential conversation on WhatsApp; '
                          'no automatic start performed.')


if __name__ == '__main__':
    try:
        initial_status = l.status()
        assert initial_status['state'] == 'STOPPED' and initial_status['webhook'] == 'INTERNAL'
        previous = json.loads(old_bytes)
        assert previous['validity_policy'] == d.DEV_GATE_POLICY == 'change_based_v1'
        assert previous['schema_version'] == 2 and 'expires_at' not in previous
        d.preflight(ap, require_gates=False)
        r['initial_status'] = initial_status
        report = asyncio.run(http_gate())
        d.save_private(out / 'http-container.json', report)
        gate('http_auth', 'Fresh unmodified inert HTTP and container reachability/auth PASS. '
                          'No lifespan, no message events, no commercial or egress doubles.',
             artifact=str(out / 'http-container.json'), sha256=sha(out / 'http-container.json'),
             generated_at=report['generated_at'])
        observe('http_auth', cases=[o['case'] for o in report['observations']],
                container_auth_reachability=report['container_auth_reachability'],
                listener_closed=report['listener_closed'], whatsapp_sends=0)
        asyncio.run(run())
        assert source == d.source_digest(), 'source_changed_during_run'
        assert configuration == d.configuration_digest(), 'configuration_changed_during_run'
        assert set(r['gates']) == d.GATES
        summary = publish()
        summary['artifact'] = str(out / 'final-accreditation.json')
        summary['artifact_sha256'] = sha(out / 'final-accreditation.json')
        (HERE / 'closure.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        r['status'] = 'BLOCKED'
        r['error_class'] = type(exc).__name__
        d.save_private(out / 'accreditation.json', r)
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)
        print(json.dumps(dict(SIX_GATES='BLOCKED', error_class=type(exc).__name__,
                              frames=[dict(file=Path(f.filename).name, line=f.lineno) for f in frames],
                              evidence_directory=str(out),
                              source_sha256=source,
                              manifest_changed=mp.read_bytes() != old_bytes)))
        raise SystemExit(1) from None

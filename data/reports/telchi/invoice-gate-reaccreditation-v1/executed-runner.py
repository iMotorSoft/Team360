"""Isolated operational accreditation; no listener, service lifecycle or WhatsApp.

Run from repo root with backend/.venv Python. Uses existing private control config.
Real Evolution normalization -> MessagingService/fence -> identity -> Console ->
TelchiHandler -> persisted audit -> Foundation/Luna. Only egress is recording.
Revocation uses session-local copies of actual RBAC join rows, never public grants.
Each turn is committed and gets a fresh handler/store/interpreter (no memory reuse).
Writes new private evidence only; publication is a separate reviewed operation.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
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
config_path = d.PRIVATE_ROOT / 'whatsapp-dev-control.json'
config = l.load_config(config_path)
os.environ.update(OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(ap)
mp = d.private_file(a['gates_file'])
old_bytes = mp.read_bytes()
old = json.loads(old_bytes)
source = d.source_digest()
out = d.PRIVATE_ROOT / ('invoice-gate-reaccreditation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
out.mkdir(mode=0o700)
r = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=source,
         approval_sha256=d.approval_digest(a), runner_sha256=sha(__file__),
         configuration_sha256=sha(config_path), previous_manifest_sha256=sha(mp),
         observations={}, model_metadata=[], turns=[], status='BLOCKED',
         services_started_or_stopped=0, listeners_created=0, whatsapp_sent=0,
         public_permission_mutations=0, pilot_access_mutations=0, webhook_mutations=0,
         host_preflight='BUSY_BUT_SAFE: 8 CPUs, load 1.31/1.61/1.49; 5422 MiB available; swap 2652 MiB stable; sampled idle 84-90%, no swap IO',
         concurrency='One sequential process, one PG connection; numeric threads 2; no browser',
         command='SrvRestAstroLS_v1/backend/.venv/bin/python data/reports/telchi/invoice-gate-reaccreditation-v1/run.py')


def passed(name, **evidence):
    r['observations'][name] = dict(status='PASS', **evidence)
    l.atomic(out / 'progress.json', r)


class ObservedLuna:
    def __init__(self):
        from modules.telchi.assistant.luna import LunaInterpreter
        self.inner = LunaInterpreter()
        self.calls = []

    async def interpret(self, **kw):
        # Descriptors contain no business row values. Store only descriptors/metadata.
        self.calls.append(kw.get('result_context'))
        proposal = await self.inner.interpret(**kw)
        md = self.inner.last_metadata
        assert md and md['provider'] == 'OpenAI direct' and md['reasoning_echo_verified']
        r['model_metadata'].append(md)
        return proposal


async def run():
    from modules.db.pool import create_pool, open_pool, close_pool
    from modules.db.settings import get_database_settings
    from modules.db.transaction import transaction
    from modules.messaging.repository import MessagingRepository
    from modules.messaging.service import MessagingService
    from modules.messaging.identity import PhoneIdentityRepository, PostgresPhoneIdentityResolver
    from modules.messaging.handlers import ChannelContext, MessageContext, MessageDispatcher
    from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, TelchiHandler, PostgresConversationStore, registration
    from modules.telchi.assistant.repository import ConversationRepository
    from modules.telchi.assistant.capabilities import SalesCapabilities
    from modules.console.repositories import PermissionConsoleRepository
    from scripts import telchi_durable_idempotency_probe as h
    import httpx

    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
    assert old['approval_sha256'] == d.approval_digest(a)
    # Expired technical evidence is provenance only, not current admission.
    for gate in d.GATES:
        g = old['gates'][gate]
        assert g['status'] == 'PASS' and g['kind'] == 'real'
        assert sha(d.private_file(g['artifact'])) == g['sha256']
    passed('previous_artifact_integrity', reuse='Original artifacts/dates retained, NOT relabeled current')
    evidence_root = ROOT / 'data/reports/telchi/document-continuity-invoice-lines-v1'
    validation = json.loads((evidence_root / 'source-manifest-final.json').read_text())
    for name, value in validation['files'].items():
        assert sha(ROOT / name) == value, name
    summary = json.loads((evidence_root / 'validation-summary.json').read_text())
    assert summary['pytest'] == dict(passed=422, skipped=2, warnings=1, evidence='pytest-final-r3.txt')
    passed('focused_evidence_reuse', tests='422 PASS / 2 SKIP; exact source manifest verified; not rerun',
           source_manifest_sha256=sha(evidence_root / 'source-manifest-final.json'),
           test_artifact_sha256=sha(evidence_root / 'pytest-final-r3.txt'),
           luna_artifact_sha256=sha(evidence_root / 'luna-full-conversation.json'))
    _, srv, settings, binding = await asyncio.to_thread(d.preflight, ap, require_gates=False)
    passed('operational_preflight', postgresql='READY', evolution='READY', runtime='STOPPED',
           bootstrap='Only harness skips manifest admission; normal launcher remains unchanged')
    def check():
        d.unchanged_approval(ap, a)
    policy = BusinessPolicy(a['tenant_id'], a['workspace_id'], None, a['module_enabled'],
                            a['whole_workspace_scope_verified'], pilot_access_check=check,
                            pilot_user_id=a['user_id'], pilot_approval_sha256=d.approval_digest(a))
    auth = BusinessAuthorization(policy)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    try:
        # Exercise real HTTP parsing/auth with ASGI transport, no server/listener.
        from modules.telchi.assistant.composition import create_telchi_app
        app = d.PilotBoundary(create_telchi_app(policy=policy, pool=pool), settings, srv.evolution, srv.recipient, check)
        cases = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://isolated', timeout=5) as client:
            for name, token, body, expected in (
                ('missing_token', '', b'{malformed', 401),
                ('invalid_token', 'invalid-probe-token', b'{malformed', 401),
                ('valid_token_invalid_json', settings.webhook_token, b'{malformed', 400),
                ('valid_ignored_event', settings.webhook_token, json.dumps(dict(event='connection.update', instance=srv.evolution.instance)).encode(), 200)):
                response = await client.post(d.WEBHOOK, content=body, headers={'x-team360-webhook-token': token, 'content-type': 'application/json'})
                assert response.status_code == expected, (name, response.status_code)
                cases.append(dict(case=name, status=expected))
        passed('http_auth', transport='In-process real ASGI/PilotBoundary/Srv05, no network listener', cases=cases,
               previous_network_evidence=old['gates']['http_auth'])
        repo = MessagingRepository()
        pb = replace(binding, receiver_context='result-reference-probe:' + uuid.uuid4().hex)
        channel = ChannelContext(pb.channel_id, 'evolution', srv.evolution.instance, pb.receiver_context,
                                 pb.tenant_id, pb.workspace_id, pb.module, pb.environment)
        async with transaction(pool) as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            identities = PhoneIdentityRepository()
            identity = await identities.resolve(conn, channel, settings.authorized_sender)
            assert identity and identity.user_id == a['user_id']
            base = MessageContext(channel, identity, settings.authorized_sender, 'pending', 'pending', frozenset())
            assert await auth.allowed(base, conn)
            for key, foreign in (('tenant', replace(channel, tenant_id='probe-foreign')),
                                 ('workspace', replace(channel, workspace_id=str(uuid.uuid4())))):
                assert await identities.resolve(conn, foreign, settings.authorized_sender) is None
                assert not await auth.allowed(replace(base, channel=foreign), conn)
        class CountedCapabilities(SalesCapabilities):
            invoice_calls = 0
            async def invoice_lines(self, parameters):
                self.invoice_calls += 1
                return await super().invoice_lines(parameters)
        cap = h.CapabilityCounter(CountedCapabilities())
        sender = h.RecordingSender()
        latest_handler = None
        latest_context = None
        async def turn(text, label, concurrent=False):
            nonlocal latest_handler, latest_context
            llm = ObservedLuna()
            latest_handler = TelchiHandler(store=PostgresConversationStore(pool), authorization=auth, interpreter=llm, capabilities=cap)
            counted = h.HandlerCounter(latest_handler)
            dispatcher = MessageDispatcher(channels=(channel,), handlers={'telchi': registration(counted)},
                identities=PostgresPhoneIdentityResolver(pool), environment='dev')
            service = MessagingService(pool=pool, repository=repo, binding=pb, sender=sender,
                authorized_sender='', dispatcher=dispatcher)
            external = 'rr-' + label + '-' + uuid.uuid4().hex
            ev = h._event(settings.authorized_sender, pb.receiver_context, text, external)
            before = cap.calls
            before_send = len(sender.calls)
            result = await service.process(ev, t0_ms=0, t1_ms=0)
            if concurrent:
                retries = await asyncio.gather(service.process(ev, t0_ms=0, t1_ms=0), service.process(ev, t0_ms=0, t1_ms=0))
            else:
                retries = [await service.process(ev, t0_ms=0, t1_ms=0)]
            inbound, outbound = await h._snapshot(pool, pb, external)
            assert result == 'accepted' and all(x == 'duplicate' for x in retries), (result, retries)
            assert len(inbound) == len(outbound) == counted.calls == len(sender.calls) - before_send == 1
            row = inbound[0]
            audit = row['payload_jsonb'].get('telchi_assistant_v1') or {}
            dispatch = row['payload_jsonb']['dispatch_result']
            latest_context = replace(base, conversation_id=str(row['thread_id']), correlation_id=str(row['id']))
            record = dict(label=label, event_id=str(row['id']), thread_id=str(row['thread_id']),
                classification=dispatch['classification'], decision=audit.get('decision'),
                capability_delta=cap.calls-before, result_context=llm.calls,
                duplicate_results=retries, one_audit_one_outbound=True,
                audit_sha256=hashlib.sha256(json.dumps(audit, sort_keys=True).encode()).hexdigest())
            r['turns'].append(record)
            l.atomic(out / 'progress.json', r)
            return audit, dispatch, row, ev

        five, _, _, _ = await turn('Mostrame las últimas 5 facturas de venta, sin filtrar sucursal ni canal.', 'five')
        assert five['execution_status'] == 'executed' and len(five['execution_result']['rows']) == 5
        three, _, three_row, _ = await turn('Mostrame solamente las últimas 3 facturas de esa consulta.', 'three')
        assert three['execution_status'] == 'executed' and len(three['execution_result']['rows']) == 3
        assert cap.calls == 2
        permission = three['required_permission']
        assert three['business_rbac_verified'] is True
        assert three['owner'] == ['dev', a['tenant_id'], a['workspace_id'], pb.channel_id, a['user_id']]
        passed('assistant_foundation', queries=2, capability=three['execution_result']['capability'],
               source=three['execution_result']['source'], row_count=3,
               rows_sha256=hashlib.sha256(json.dumps(three['execution_result']['rows'], sort_keys=True).encode()).hexdigest())
        selected, dispatch, selection_row, selection_ev = await turn('¿Cuál es el número de factura de la segunda de esas tres?', 'second', concurrent=True)
        assert selected['decision'] == 'SELECT_RESULT' and selected['capability_calls'] == 0 and cap.calls == 2
        assert selected['result_reference'] == dict(result_id=str(three_row['id']), selected_ordinal=2)
        target = str(three['execution_result']['rows'][1]['doc_num'])
        assert target in dispatch['text'] and selected['selected_document']['doc_num'] == three['execution_result']['rows'][1]['doc_num']
        selected_context = latest_context
        cached = await latest_handler.handle(selection_ev, selected_context)
        assert cached.classification == 'DIRECT_AVAILABLE' and cached.text == dispatch['text'] and cap.calls == 2
        passed('persisted_result_recovery', sequence='5 -> 3 -> second', fresh_handler_each_turn=True,
               selected_result_id=str(three_row['id']), selected_ordinal=2, foundation_calls_on_selection=0,
               cached_selection_identical=True)
        # SQL owner checks: bounded reads/row locks only, no data mutation.
        # Repository uses SELECT FOR UPDATE, which PostgreSQL disallows in READ ONLY.
        async with transaction(pool) as conn:
            cr = ConversationRepository()
            loaded = await cr.load(conn, selected_context)
            view = await cr.load_result(conn, selected_context, loaded)
            assert view and view['result_id'] == str(three_row['id'])
            for case, ctx in (
                ('user', replace(selected_context, sender_identity=replace(identity, user_id=str(uuid.uuid4())))),
                ('tenant', replace(selected_context, channel=replace(channel, tenant_id='probe-foreign'))),
                ('workspace', replace(selected_context, channel=replace(channel, workspace_id=str(uuid.uuid4())))),
                ('conversation', replace(selected_context, conversation_id=str(uuid.uuid4()))),
                ('channel', replace(selected_context, channel=replace(channel, channel_id=str(uuid.uuid4()))))):
                try:
                    await cr.load(conn, ctx)
                except ValueError:
                    pass
                else:
                    raise AssertionError('owner_leak_' + case)
        passed('identity_tenant_isolation', scope=['user', 'tenant', 'workspace', 'conversation', 'channel'],
               real_phone_binding=True, real_persisted_list=True)
        # Pin a snapshot of ACTUAL joins on this one connection. Public RBAC stays intact.
        async with transaction(pool) as conn:
            await conn.execute('''CREATE TEMP TABLE core_role_permissions AS SELECT rp.* FROM public.core_role_permissions rp
                JOIN public.core_user_roles ur ON ur.role_id=rp.role_id WHERE ur.user_id=%s''', (a['user_id'],))
            await conn.execute('''CREATE TEMP TABLE core_profile_permissions AS SELECT pp.* FROM public.core_profile_permissions pp
                JOIN public.core_user_profiles up ON up.profile_id=pp.profile_id WHERE up.user_id=%s''', (a['user_id'],))
            resolver = PermissionConsoleRepository()
            assert permission in await resolver.list_effective_permissions(conn, a['workspace_id'], a['user_id'])
            assert await auth.allowed(selected_context, conn, required_permission=permission)
            await conn.execute('''DELETE FROM pg_temp.core_role_permissions WHERE permission_id IN
                (SELECT id FROM public.core_permissions WHERE permission_code=%s)''', (permission,))
            await conn.execute('''DELETE FROM pg_temp.core_profile_permissions WHERE permission_id IN
                (SELECT id FROM public.core_permissions WHERE permission_code=%s)''', (permission,))
        # New committed turn: same identity still contains cached permission.
        assert permission in identity.permissions
        async with transaction(pool) as conn:
            assert permission not in await PermissionConsoleRepository().list_effective_permissions(conn, a['workspace_id'], a['user_id'])
            assert not await auth.allowed(selected_context, conn, required_permission=permission)
        denied_cached = await latest_handler.handle(selection_ev, selected_context)
        assert denied_cached.classification == 'DENIED' and target not in denied_cached.text
        revoked, revoked_dispatch, _, _ = await turn('¿Cuál es el número de factura de la segunda de esas tres?', 'revoked')
        assert revoked_dispatch['classification'] != 'DIRECT_AVAILABLE' and target not in revoked_dispatch['text']
        assert cap.calls == 2 and revoked.get('decision') != 'SELECT_RESULT'
        assert all(x is None for x in r['turns'][-1]['result_context'])
        passed('revocation_between_turns', real_console_resolver=True, committed_between_turns=True,
               stale_identity_permission=True, descriptors_withheld=True, cached_selection='DENIED',
               new_selection=revoked_dispatch['classification'], foundation_calls_after_revocation=0,
               scope='Actual RBAC join rows copied to pg_temp; permission removed only from session copies. No pilot/public grants revoked.')
        # Explicit qualification proves operational grants were untouched by the probe.
        async with transaction(pool) as conn:
            await conn.execute('DROP TABLE pg_temp.core_role_permissions, pg_temp.core_profile_permissions')
            assert permission in await PermissionConsoleRepository().list_effective_permissions(conn, a['workspace_id'], a['user_id'])
        passed('public_rbac_preserved', actual_permission_still_effective=True)
        # Scope restoration above is verified against the real public grants.
        # Rebuild handlers each turn: recover a document, then read actual lines.
        first, first_dispatch, _, _ = await turn('Mostrame el número de la primera factura de esas tres últimas facturas.', 'first-document')
        assert first['decision'] in {'SELECT_RESULT', 'SELECT_DOCUMENT'} and first['capability_calls'] == 0
        assert first['selected_document']['doc_entry'] == three['execution_result']['rows'][0]['doc_entry']
        invoice, invoice_dispatch, invoice_row, invoice_ev = await turn('Mostrame los productos de esta factura.', 'invoice-lines', concurrent=True)
        assert invoice_dispatch['classification'] == 'DIRECT_AVAILABLE'
        assert invoice['execution_status'] == 'executed' and invoice['capability_calls'] == 1
        result = invoice['execution_result']
        from modules.telchi.datalake.invoice_lines_query import PERMISSION as LINE_PERMISSION
        assert result['capability'] == 'sales.invoice_lines.v1' and result['rows']
        assert invoice['required_permission'] == LINE_PERMISSION and invoice['business_rbac_verified'] is True
        assert result['document']['doc_entry'] == first['selected_document']['doc_entry']
        assert cap.inner.invoice_calls == 1 and cap.calls == 2
        passed('invoice_lines_authorized_execution', capability=result['capability'], permission=LINE_PERMISSION,
               source=result['source'], rows=len(result['rows']), fresh_handler=True,
               rows_sha256=hashlib.sha256(json.dumps(result['rows'], sort_keys=True).encode()).hexdigest(),
               concurrent_retries='Both duplicate; one invoice query; one logical outbound')
        invoice_context = latest_context
        async with transaction(pool) as conn:
            loaded = await ConversationRepository().load(conn, invoice_context)
            assert loaded['document_reference']['result_id'] == str(three_row['id'])
            assert loaded['document_reference']['selected_ordinal'] == 1
            assert loaded['result_reference']['result_id'] == str(invoice_row['id'])
            view = await ConversationRepository().load_result(conn, invoice_context, loaded)
            assert view and view['capability'] == 'sales.invoice_lines.v1'
            assert await auth.allowed(invoice_context, conn, required_permission=LINE_PERMISSION)
            await conn.execute('''CREATE TEMP TABLE core_role_permissions AS SELECT rp.* FROM public.core_role_permissions rp
                JOIN public.core_user_roles ur ON ur.role_id=rp.role_id WHERE ur.user_id=%s''', (a['user_id'],))
            await conn.execute('''CREATE TEMP TABLE core_profile_permissions AS SELECT pp.* FROM public.core_profile_permissions pp
                JOIN public.core_user_profiles up ON up.profile_id=pp.profile_id WHERE up.user_id=%s''', (a['user_id'],))
            # Force re-resolution after recreating same-named temporary tables:
            # prior prepared queries may otherwise remain bound to public joins.
            await conn.execute('SET search_path TO pg_temp, public')
            for table in ('core_role_permissions', 'core_profile_permissions'):
                await conn.execute('DELETE FROM pg_temp.' + table + ' WHERE permission_id IN (SELECT id FROM public.core_permissions WHERE permission_code=%s)', (LINE_PERMISSION,))
        async with transaction(pool) as conn:
            assert not await auth.allowed(invoice_context, conn, required_permission=LINE_PERMISSION)
        denied_invoice = await latest_handler.handle(invoice_ev, invoice_context)
        assert denied_invoice.classification == 'DENIED'
        assert cap.inner.invoice_calls == 1
        async with transaction(pool) as conn:
            await conn.execute('DROP TABLE pg_temp.core_role_permissions, pg_temp.core_profile_permissions')
            assert await auth.allowed(invoice_context, conn, required_permission=LINE_PERMISSION)
        passed('invoice_lines_revocation_and_recovery', persisted_parent_and_line_pointers=True,
               cached_result_after_revocation='DENIED', additional_invoice_queries=0,
               live_console_resolver=True, public_grants_preserved=True,
               scope='Only session-local copies of actual joins modified; no public grants changed')
        passed('durable_idempotency', real_pg=True, new_turns=len(r['turns']),
               one_audit_and_one_logical_outbound_per_inbound=True, selection_retries='Two concurrent duplicate requests; zero handler reruns',
               scope='Logical intent only; recording egress, no WhatsApp delivery claim')
        passed('model_no_fallback', provider='OpenAI direct', metadata_count=len(r['model_metadata']),
               scope='Every live request model/effort echo checked; no fallback code or adapter replacement')
    finally:
        await close_pool(pool)
        r['pool_closed'] = pool.closed
    assert d.source_digest() == source
    assert sha(config_path) == r['configuration_sha256'] and d.approval_digest(d.read_approval(ap)) == r['approval_sha256']
    assert mp.read_bytes() == old_bytes
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'
    r['status'] = 'PASS'

try:
    asyncio.run(run())
except Exception as exc:
    r.update(error_class=type(exc).__name__, error=str(exc)[:160] if isinstance(exc, AssertionError) else 'See private runner stage', traceback=__import__('traceback').format_exc())
finally:
    r['own_processes_left_running'] = 0  # No child processes/listeners; asyncio loop and pool closed.
    r['manifest_published'] = False
    d.save_private(out / 'accreditation.json', r)
    summary = dict(status=r['status'], observations=list(r['observations']), source_sha256=source,
        artifact=str(out / 'accreditation.json'), sha256=sha(out / 'accreditation.json'),
        error_class=r.get('error_class'), error=r.get('error'), pool_closed=r.get('pool_closed'))
    (HERE / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    if r['status'] != 'PASS':
        raise SystemExit(1)

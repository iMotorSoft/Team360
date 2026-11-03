"""Focused reuse of existing gate probes, current pilot contract; never starts session.
Real PG identity/RBAC/fence and Foundation; one Luna request; recording egress only.
No grant, binding, approval, webhook or Foundation mutations. No manifest publication.
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
cp = d.PRIVATE_ROOT / 'whatsapp-dev-control.json'
config = l.load_config(cp)
ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
a = d.read_approval(ap)
source = d.source_digest()
mp = d.private_file(a['gates_file'])
inputs = {str(p): sha(p) for p in (cp, ap, mp)}
out = d.PRIVATE_ROOT / ('six-gates-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
out.mkdir(mode=0o700)
r = dict(generated_at=datetime.now(timezone.utc).isoformat(), source_sha256=source,
         approval_sha256=d.approval_digest(a), runner_sha256=sha(__file__), gates={},
         host_preflight='BUSY_BUT_SAFE: 8 CPUs; ~5 GiB available; swap 103 MiB stable, sampled CPU idle 75-77%, no swap IO',
         concurrency='One process, PG max 3, two concurrent claims of ONE event; one model/query',
         whatsapp_sends=0, webhook_mutations=0, grant_mutations=0, binding_mutations=0,
         manifest_published=False, unrelated_processes_terminated=0)

def gate(name, scope, **evidence):
    r['gates'][name] = dict(status='PASS', kind='real', scope=scope, **evidence)

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
    # Reuse intact evidence only after checking its exact current code/access/config.
    prior = json.loads((HERE.parent / 'ingress-contract-fix-v1/result.json').read_text())
    artifact = d.private_file(prior['private_artifact'])
    assert sha(artifact) == prior['private_artifact_sha256']
    http = json.loads(artifact.read_text())
    assert http['status'] == 'PASS' and http['source_sha256'] == source
    assert http['approval_sha256'] == d.approval_digest(a) and http['configuration_sha256'] == sha(cp)
    assert len(http['observations']) == 4 and all(v['passed'] for v in http['observations'])
    gate('http_auth', 'Preserved current-code real loopback HTTP auth/sender/revocation/admission. Commercial handler and egress doubles do not accredit business or delivery. Prior date retained.', artifact=str(artifact), sha256=sha(artifact), generated_at=http['generated_at'])

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
            # Remove only the pilot user restriction in a negative test: live RBAC,
            # not the admission restriction, must reject this forged cached grant.
            rbac_only = BusinessAuthorization(replace(policy, pilot_user_id=str(f['user_id'])))
            assert not await rbac_only.allowed(stale, conn, required_permission=capability_permission)
            access['revoked'] = True
            assert not await auth.allowed(context, conn)
            access['revoked'] = False
        gate('identity_tenant_isolation', 'Real authenticated PG binding and approved user; foreign tenant/workspace absent and denied; existing revoked/inactive identity rejected. No fixture mutation.')
        gate('business_authorization', 'Real Console effective grant required only for executed capability. Empty cache admits pilot but denies operation; forged cache for revoked fixture denied by live Console. Pilot revocation callback denied. No grants changed.')
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
        md = interpreter.last_metadata
        assert md and md['provider'] == 'OpenAI direct' and md['reasoning_echo_verified']
        gate('model_no_fallback', 'One real current Luna request with returned model/effort verified. Fresh provider-failure/no-fallback offline contracts supplement live success; no provider outage induced.', metadata=md)
        result = audit.get('execution_result') or {}
        assert audit['execution_status'] == 'executed' and audit['capability_calls'] == cap.calls == 1
        assert audit['business_rbac_verified'] is True and audit['pilot_approval_sha256'] == d.approval_digest(a)
        assert len(result['rows']) == 10 and result['source']['publication_id'] and result['source']['snapshot_id'] is not None
        r['foundation'] = dict(source=result['source'], row_count=len(result['rows']),
                               rows_sha256=hashlib.sha256(json.dumps(result['rows'], sort_keys=True).encode()).hexdigest())
        gate('assistant_foundation', 'One current real Messaging/PG identity/Console/TelchiHandler capability execution and read-only Foundation query. Existing fixed query, no SAP or Foundation publication mutation.', evidence=r['foundation'])
    finally:
        await close_pool(pool)
        r['pool_closed'] = pool.closed
    assert l.read_json(l.root() / 'current.json')['state'] == 'STOPPED'

try:
    asyncio.run(run())
    assert source == d.source_digest()
    assert all(sha(p) == value for p, value in inputs.items())
    assert set(r['gates']) == d.GATES
    r['status'] = 'PASS'
except Exception as exc:
    r['status'] = 'BLOCKED'
    r['error_class'] = type(exc).__name__
finally:
    r['own_processes_left_running'] = 0  # No subprocess or listener created; asyncio.run closes loop.
    d.save_private(out / 'accreditation.json', r)
    summary = dict(status=r['status'], gates=list(r['gates']), error_class=r.get('error_class'),
                   source_sha256=source, approval_sha256=d.approval_digest(a),
                   artifact=str(out / 'accreditation.json'), sha256=sha(out / 'accreditation.json'),
                   pool_closed=r.get('pool_closed'), own_processes_left_running=0)
    (HERE / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))

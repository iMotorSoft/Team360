"""Actual DEV catalog, authorization and authenticated ASGI conversation probe.

No listener, service lifecycle, human impersonation or outbound transport. Uses
existing owner-approved pilot phone binding; writes only DEV conversation audits.
Revocation is capability disablement inside rollback, never a FULL_ACCESS change.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import secrets
from uuid import uuid4

import httpx
import psycopg
from psycopg.rows import dict_row
from modules.console.repositories import PermissionConsoleRepository
from modules.db.pool import create_pool, set_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.messaging.handlers import ChannelContext, MessageContext, SenderIdentity
from modules.messaging.identity import PhoneIdentityRepository
from modules.messaging.domain.messages import InboundMessage
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization
from modules.telchi.assistant.composition import create_telchi_app
from modules.telchi.assistant.dev_runtime_http import DevAssistantController, DEV_PATH
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.provisioning.category_repository import (
    CategoryRegistrationRepository, AUTHORIZATION, CAPABILITY, PERMISSION, PILOT, WORKSPACE)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def run(args):
    l.load_config(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
    config = l.load_config(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
    ap = Path(config.get('approval', d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
    approval = d.read_approval(ap)
    _, srv, settings, binding = await asyncio.to_thread(d.preflight, ap, require_gates=False)
    assert l.read_json(l.root()/'current.json')['state'] == 'STOPPED'
    source = d.source_digest()
    registration = json.loads(args.registration.read_text())
    backup = d.private_file(registration['backup'])
    assert sha(backup) == registration['backup_sha256']
    before = json.loads(backup.read_text())
    report = dict(status='IN_PROGRESS', generated_at=datetime.now(timezone.utc).isoformat(),
        source_sha256=source, approval_sha256=d.approval_digest(approval),
        configuration_sha256=d.configuration_digest(), observations={}, turns=[],
        registration_sha256=sha(args.registration), backup_sha256=sha(backup),
        services_started_or_stopped=0, listeners=0, whatsapp_sent=0,
        authentication='Real token-authenticated DEV HTTP route over in-process ASGI; existing approved phone/Console identity. Not human login or WhatsApp ingress.',
        limits='Manual DEV readiness, not WhatsApp delivery or complete month certification.')
    def passed(name, **facts):
        report['observations'][name] = dict(status='PASS', **facts)
    def check():
        d.unchanged_approval(ap, approval)
    policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
        approval['module_enabled'], approval['whole_workspace_scope_verified'],
        pilot_access_check=check, pilot_user_id=approval['user_id'],
        pilot_approval_sha256=d.approval_digest(approval))
    auth = BusinessAuthorization(policy)
    channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
        binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
    repo = CategoryRegistrationRepository()
    resolver = PermissionConsoleRepository()
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn, row_factory=dict_row,
            autocommit=True, application_name='telchi-category-real-verification') as conn:
        async with conn.transaction():
            await repo.guard(conn)
            current = await repo.security_state(conn)
            # All previous grants, profiles, roles and foreign registry entries unchanged.
            for table, rows in before['security']['records'].items():
                extra = [c['row'] for c in registration['created'] if c['table'] == table]
                assert sorted(rows+extra, key=lambda r:json.dumps(r,sort_keys=True)) == current['records'][table], table
            for user, codes in before['security']['effective'].items():
                assert set(current['effective'][user]) == set(codes) | ({PERMISSION} if user == PILOT else set())
            audit = await (await conn.execute('SELECT payload_jsonb FROM core_events WHERE correlation_id=%s',
                                              (registration['run_id'],))).fetchone()
            assert audit['payload_jsonb']['result'] == 'registered'
            assert audit['payload_jsonb']['backup_sha256'] == sha(backup)
            count = (await (await conn.execute('SELECT count(*) n FROM core_events')).fetchone())['n']
            repeated = await repo.activate(conn, authorization=AUTHORIZATION, backup_sha256=sha(backup))
            assert not repeated['changed']
            assert (await (await conn.execute('SELECT count(*) n FROM core_events')).fetchone())['n'] == count
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            assert identity.user_id == PILOT and PERMISSION in identity.permissions
            context = MessageContext(channel, identity, settings.authorized_sender, 'probe', 'probe', frozenset())
            assert await auth.allowed(context, conn, required_permission=PERMISSION)
            normal = before['identities']['admin']['id']
            normal_codes = await resolver.list_effective_permissions(conn, WORKSPACE, normal)
            assert PERMISSION not in normal_codes and not normal_codes
            normal_identity = SenderIdentity(normal, 'telchi', WORKSPACE, 'dev', frozenset(normal_codes))
            assert not await auth.allowed(replace(context, sender_identity=normal_identity), conn, required_permission=PERMISSION)
            foreign_user = before['identities']['global']
            assert PERMISSION not in await resolver.list_effective_permissions(conn, foreign_user['workspace_id'], foreign_user['id'])
            assert PERMISSION not in await resolver.list_effective_permissions(conn, foreign_user['workspace_id'], PILOT)
            for foreign in (replace(channel, tenant_id='team360_platform'), replace(channel, workspace_id=foreign_user['workspace_id']),
                            replace(channel, module='flow')):
                assert not await auth.allowed(replace(context, channel=foreign), conn, required_permission=PERMISSION)
                if foreign.module == 'telchi':
                    assert await PhoneIdentityRepository().resolve(conn, foreign, settings.authorized_sender) is None
            passed('identity_tenant_isolation', actual_pilot_binding=True, actual_nonprivileged_user=normal,
                actual_foreign_user=foreign_user['id'], negative_axes=['tenant','workspace','module','user'])
        async with conn.transaction(force_rollback=True):
            await conn.execute("UPDATE core_workspace_capabilities SET enabled=false WHERE workspace_id=%s AND module='telchi' AND capability_code=%s", (WORKSPACE,CAPABILITY))
            assert PERMISSION not in await resolver.list_effective_permissions(conn, WORKSPACE, PILOT)
            assert not await auth.allowed(context, conn, required_permission=PERMISSION)
            assert await auth.allowed(context, conn, required_permission='telchi.sales.invoice_amount.read.v1')
        assert await auth.allowed(context, conn, required_permission=PERMISSION)
        assert await repo.security_state(conn) == current
        passed('business_authorization', actual_catalog=True, pilot_full_access=True,
            ordinary_and_foreign_effective_permissions_unchanged=True, full_access_records_unchanged=True,
            individual_assignments_created=0, registration_idempotent=True, registration_audit_verified=True,
            revocation='Actual capability disablement in rollback; stale identity denied; restored; FULL_ACCESS untouched')
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    try:
        interpreter = LunaInterpreter()
        preflight = await interpreter.interpret(text='¿Cuánto facturamos?', state=EMPTY, history={}, turn_id='preflight')
        assert preflight['action'] == 'ASK'
        report['model_preflight'] = interpreter.last_metadata
        app = create_telchi_app(policy=policy, pool=pool)
        # Legacy route imports configure their unopened pool. Bind the probe's
        # opened native pool AFTER composition, without starting shared lifecycles.
        set_pool(pool)
        from modules.db.pool import get_pool
        assert get_pool() is pool and not pool.closed
        app.register(DevAssistantController)
        token = secrets.token_urlsafe(48)
        app.state.dev_assistant_config = dict(token=token, phone=settings.authorized_sender, binding=binding,
            instance=binding.provider_instance, receiver_context=binding.receiver_context)
        assert app.state.messaging_handlers['telchi'].handler.concept_resolver is None
        # No lifespan entered: unrelated scheduler/hooks/services never start.
        http_cases = []
        conversation = 'category-'+uuid4().hex
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
            for label, headers, content, status in [
                ('absent', {}, b'{bad', 401), ('invalid', {'x-team360-dev-token':'invalid'}, b'{bad',401),
                ('authenticated_bad_json', {'x-team360-dev-token':token}, b'{bad',400)]:
                response = await client.post(DEV_PATH+'/turn', content=content, headers=headers)
                assert response.status_code == status
                http_cases.append(dict(case=label,status=status))
            passed('http_auth', actual_asgi_route=DEV_PATH+'/turn', cases=http_cases, token_logged=False, listener=False)
            questions = ['¿Cuánto vendimos de materia prima en septiembre?', '¿Y de productos terminados?',
                         '¿Cuál de esas categorías vendió más?', 'Mostrame las últimas cinco facturas.']
            handler = app.state.messaging_handlers['telchi'].handler
            for n, question in enumerate(questions):
                response = await client.post(DEV_PATH+'/turn', json=dict(text=question,conversation=conversation),
                    headers={'x-team360-dev-token':token})
                assert response.status_code == 200, response.status_code
                turn = response.json()
                turn.update(question=question, model=handler.interpreter.last_metadata)
                report['turns'].append(turn)
                assert turn['classification'] == 'DIRECT_AVAILABLE', turn
                audit = turn['audit']
                if n < 2:
                    result = audit['execution_result']
                    expected = ('839582.63', '2679208.66')[n]
                    assert Decimal(result['rows'][0]['amount']) == Decimal(expected)
                    assert audit['required_permission'] == PERMISSION and audit['business_rbac_verified']
                    assert result['coverage']['complete'] is False and result['coverage']['last_date'].startswith('2026-09-24')
                    assert 'notas de crédito' in turn['text'] and 'líneas comerciales' in turn['text']
                    if n == 0:
                        assert [result['rows'][0][k] for k in ('product_count','line_count','document_count')] == [34,526,495]
                elif n == 2:
                    assert audit['monetary_calculation'] and audit['capability_calls'] == 0
                else:
                    assert audit['execution_result']['capability'] == 'sales.latest_documents.v1'
            # Replay actual persisted first result, then revoke only its operation.
            first = report['turns'][0]
            replay_context = replace(context, conversation_id=first['conversation_id'], correlation_id=first['correlation_id'])
            message = InboundMessage(provider='evolution', channel='whatsapp', external_message_id='replay',
                sender=settings.authorized_sender, recipients=(binding.receiver_context,), text_body=questions[0],
                external_thread_id=None, subject=None, received_at=datetime.now(timezone.utc), metadata={})
            replay = await handler.handle(message,replay_context)
            assert replay.text == first['text'] and replay.classification == 'DIRECT_AVAILABLE'
            async with pool.connection() as conn:
                async with conn.transaction(force_rollback=True):
                    # Check stale identity against the live resolver in the cached authorization path.
                    await conn.execute("UPDATE core_workspace_capabilities SET enabled=false WHERE workspace_id=%s AND module='telchi' AND capability_code=%s", (WORKSPACE,CAPABILITY))
                    assert not await auth.allowed(replay_context,conn,required_permission=PERMISSION)
        passed('assistant_foundation', real_authenticated_turns=4, raw_material='839582.63', second_category='2679208.66',
            counts=[34,526,495], contextual_comparison=True, previous_operation='sales.latest_documents.v1',
            partial_through='2026-09-24', credit_notes_excluded=True)
        # The durable fence/claim implementation is unchanged; retain dated real evidence,
        # supplementing it with the new operation's committed result/cache replay above.
        manifest = json.loads(d.private_file(approval['gates_file']).read_text())
        old = manifest['gates']['durable_idempotency']
        old_path = d.private_file(old['artifact'])
        assert sha(old_path) == old['sha256']
        old_report = json.loads(old_path.read_text())
        assert old_report['status'] == 'PASS' and old_report['observations']['durable_idempotency']['status'] == 'PASS'
        passed('durable_idempotency', previous_real_evidence=old, previous_generated_at=old_report['generated_at'],
            reuse_reason='No changes to Messaging claim/fence, PG conversation storage or dispatch; category registry increment only.',
            current_category_committed_cache_replay=True, current_stale_identity_reauthorization=True)
        metadata = [report['model_preflight']]+[t['model'] for t in report['turns']]
        assert all(md['provider'] == 'OpenAI direct' and md['reasoning_echo_verified'] for md in metadata)
        passed('model_no_fallback', metadata=metadata, adapter='OpenAI direct; no proxy/retry/redirect/fallback')
        assert source == d.source_digest(), 'Runtime source changed concurrently'
        assert report['configuration_sha256'] == d.configuration_digest()
        report['status'] = 'PASS'
    finally:
        await close_pool(pool)
        report['pool_closed'] = True
        with args.output.open('x') as f:
            json.dump(report,f,indent=2,ensure_ascii=False,default=str)
    return dict(status=report['status'], output=str(args.output), turns=[dict(
        question=t['question'], classification=t['classification'], text=t['text']) for t in report['turns']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    print(json.dumps(asyncio.run(run(args)),ensure_ascii=False))


if __name__ == '__main__':
    main()

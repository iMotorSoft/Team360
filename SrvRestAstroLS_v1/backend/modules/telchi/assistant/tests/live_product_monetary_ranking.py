"""Real DEV HTTP/dispatcher/Console/PG/Luna/Foundation. No listener, WhatsApp or runtime lifecycle.

Copies only the incident's audited state into a NEW probe thread; verifies original
thread and event unchanged. Private output is required. Does not publish gate attestations.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb
from modules.db.pool import create_pool, set_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.messaging.handlers import ChannelContext, MessageContext
from modules.messaging.identity import PhoneIdentityRepository, PostgresPhoneIdentityResolver
from modules.messaging.handlers import MessageDispatcher
from modules.messaging.domain.messages import InboundMessage
from modules.messaging.repository import MessagingRepository
from modules.db.transaction import transaction
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.composition import create_telchi_app
from modules.telchi.assistant.dev_runtime_http import DevAssistantController, DEV_PATH
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, PostgresConversationStore, TelchiHandler, registration
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY, process
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.provisioning.ranking_repository import RankingRegistrationRepository
from modules.telchi.datalake.product_line_amount_ranking_query import METRIC, CAPABILITY, PERMISSION, validate_result

FIXTURE = Path(__file__).parent / 'fixtures/product_monetary_ranking_incident.json'


async def run(output):
    config = lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval_path = Path(config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    assert hashlib.sha256(settings.authorized_sender.encode()).hexdigest() == approval['sender_sha256']
    binding = await dev.check_database(approval, settings, srv.evolution)
    source = dev.source_digest()
    report = dict(status='IN_PROGRESS', source_sha256=source, configuration_sha256=dev.configuration_digest(),
        approval_sha256=dev.approval_digest(approval), observations={}, turns=[],
        authentication='Token-authenticated in-process DEV HTTP with existing approved phone identity and real Console resolver; not human login or WhatsApp ingress.',
        listeners=0, whatsapp_sent=0, runtime_started_or_stopped=0, committed_security_writes=0)
    def check():
        dev.unchanged_approval(approval_path, approval)
    policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
        approval['module_enabled'], approval['whole_workspace_scope_verified'], pilot_access_check=check,
        pilot_user_id=approval['user_id'], pilot_approval_sha256=dev.approval_digest(approval))
    auth = BusinessAuthorization(policy)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=2))
    await open_pool(pool)
    try:
        app = create_telchi_app(policy=policy, pool=pool)
        set_pool(pool)
        app.register(DevAssistantController)
        token = secrets.token_urlsafe(48)
        app.state.dev_assistant_config = dict(token=token, phone=settings.authorized_sender, binding=binding,
            instance=binding.provider_instance, receiver_context=binding.receiver_context)
        handler = app.state.messaging_handlers['telchi'].handler
        assert handler.concept_resolver is None
        channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
            binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
        fixture = json.loads(FIXTURE.read_text())
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            security = await RankingRegistrationRepository().security_state(conn)
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            ctx = MessageContext(channel, identity, settings.authorized_sender, 'probe', 'probe', frozenset())
            assert identity.user_id == approval['user_id'] and await auth.allowed(ctx, conn, required_permission=PERMISSION)
            assert any(r['user_id'] == identity.user_id for r in security['records']['core_module_full_access_grants'])
            for foreign in (replace(channel, tenant_id='foreign'), replace(channel, workspace_id=str(uuid4())), replace(channel, module='other')):
                assert not await auth.allowed(replace(ctx, channel=foreign), conn, required_permission=PERMISSION)
            normal = next(u for u, codes in security['effective'].items() if u != identity.user_id and PERMISSION not in codes)
            assert PERMISSION not in await PermissionConsoleRepository().list_effective_permissions(conn, policy.workspace_id, normal)
            assert not await BusinessAuthorization(replace(policy, pilot_user_id=normal)).allowed(
                replace(ctx, sender_identity=replace(identity, user_id=normal)), conn, required_permission=PERMISSION)
            assert not await auth.allowed(ctx, conn, required_permission='telchi.unregistered.probe.read.v1')
            original = await (await conn.execute('SELECT payload_jsonb FROM message_events WHERE id=%s AND thread_id=%s',
                (fixture['source_event_id'], fixture['source_thread_id']))).fetchone()
            original_thread = await (await conn.execute('SELECT metadata_jsonb FROM message_threads WHERE id=%s',
                (fixture['source_thread_id'],))).fetchone()
            audited = original['payload_jsonb']['telchi_assistant_v1']
            assert audited['previous_state'] == fixture['previous_state'] and audited['interpretation_proposed'] == fixture['proposal']
        legacy = process(fixture['previous_state'], fixture['proposal'], {}, 'audited-replay')
        assert legacy['committed'] and not SalesCapabilities().availability(legacy['state_after']).allowed
        report['audited_replay'] = dict(exact_state_and_proposal_verified_in_postgres=True,
            historical_proposal_still_not_ranking=True, original_not_modified=True)
        # Revocation test is transaction-local and rolled back. Never changes FULL_ACCESS.
        async with pool.connection() as conn:
            await conn.execute('SAVEPOINT ranking_revocation')
            await conn.execute("UPDATE core_workspace_capabilities SET enabled=false WHERE workspace_id=%s AND module='telchi' AND capability_code=%s",
                (policy.workspace_id, CAPABILITY))
            assert not await auth.allowed(ctx, conn, required_permission=PERMISSION)
            await conn.execute('ROLLBACK TO SAVEPOINT ranking_revocation')
            assert await auth.allowed(ctx, conn, required_permission=PERMISSION)
        report['observations']['business_authorization'] = dict(status='PASS', full_access=True,
            ordinary_without_grant_denied=True, foreign_scope_denied=True, unregistered_denied=True,
            registry_revocation_denied_with_stale_identity=True, revocation_rolled_back=True)
        report['observations']['identity_tenant_isolation'] = dict(status='PASS', existing_phone_binding=True,
            negative_axes=['tenant', 'workspace', 'module', 'ordinary_user'])
        model = LunaInterpreter()
        preflight = await model.interpret(text='¿Cuánto facturamos?', state=deepcopy(EMPTY), history={}, turn_id='preflight')
        assert preflight['action'] == 'ASK' and model.last_metadata['reasoning_echo_verified']
        report['model_preflight'] = model.last_metadata
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
            for headers in ({}, {'x-team360-dev-token': 'invalid'}):
                assert (await client.post(DEV_PATH + '/turn', content=b'{bad', headers=headers)).status_code == 401
            async def turn(question, conversation, expected='DIRECT_AVAILABLE'):
                handler.interpreter = LunaInterpreter()
                handler.store = PostgresConversationStore(pool)
                response = await client.post(DEV_PATH + '/turn', json=dict(text=question, conversation=conversation),
                    headers={'x-team360-dev-token': token})
                assert response.status_code == 200, response.status_code
                value = response.json()
                value.update(question=question, model=handler.interpreter.last_metadata)
                report['turns'].append(value)
                assert value['classification'] == expected, {'question': question, 'classification': value['classification'], 'text': value['text'], 'audit':value['audit']}
                return value
            conversation = 'monetary-ranking-' + uuid4().hex
            seeded = await turn('¿Cuánto vendimos de productos terminados en septiembre?', conversation)
            # Only this newly-created thread can be seeded. Original is never written.
            assert seeded['conversation_id'] != fixture['source_thread_id']
            async with pool.connection() as conn:
                await conn.execute("UPDATE message_threads SET metadata_jsonb=jsonb_set(metadata_jsonb, '{telchi_assistant_v1,state}', %s) WHERE id=%s",
                    (Jsonb(fixture['previous_state']), seeded['conversation_id']))
            a = await turn('¿Cuánto vendimos de productos terminados en septiembre?', conversation)
            assert a['audit']['previous_state'] == fixture['previous_state']
            assert Decimal(a['audit']['execution_result']['rows'][0]['amount']) == Decimal('2679208.66')
            b = await turn('Dame los 5 más vendidos por precio de venta', conversation)
            verify_ranking(b, 'LAB_FINISHED_PRODUCT', 5)
            assert b['audit']['previous_state'] == a['audit']['confirmed_state']
            c = await turn('¿Y los 10 primeros?', conversation)
            verify_ranking(c, 'LAB_FINISHED_PRODUCT', 10)
            assert c['audit']['previous_state'] == b['audit']['confirmed_state']
            assert c['audit']['execution_result']['rows'][:5] == b['audit']['execution_result']['rows']
            d = await turn('¿Y de materias primas?', conversation)
            verify_ranking(d, 'RAW_MATERIAL', 10)
            assert d['audit']['previous_state'] == c['audit']['confirmed_state']
            e = await turn('¿Cuánto vendió el primero?', conversation)
            assert e['audit']['decision'] == 'SELECT_RESULT' and e['audit']['capability_calls'] == 0
            assert e['audit']['selected_field'] == 'amount'
            assert e['audit']['selected_document']['item_code'] == d['audit']['execution_result']['rows'][0]['item_code']
            assert e['audit']['confirmed_state'] == d['audit']['confirmed_state']
            assert 'Bs ' in e['text'] and 'Sin IVA' in e['text']
            # Exact original wording, seeded directly from the actual persisted incident, not EMPTY.
            exact_thread = 'ranking-exact-' + uuid4().hex
            exact_seed = await turn('¿Cuánto vendimos de productos terminados en septiembre?', exact_thread)
            async with pool.connection() as conn:
                await conn.execute("UPDATE message_threads SET metadata_jsonb=jsonb_set(metadata_jsonb, '{telchi_assistant_v1,state}', %s) WHERE id=%s",
                    (Jsonb(fixture['previous_state']), exact_seed['conversation_id']))
            exact = await turn(fixture['question'], exact_thread)
            assert exact['audit']['previous_state'] == fixture['previous_state']
            verify_ranking(exact, 'LAB_FINISHED_PRODUCT', 5)
            # Explicit unit price and physical quantity must not become monetary rankings.
            unit = await turn('Ahora quiero los de mayor precio unitario, no el importe acumulado', conversation, 'DIRECT_UNAVAILABLE')
            assert unit['audit']['capability_calls'] == 0 and unit['audit']['confirmed_state']['metric'] != METRIC
            qty = await turn('Dame los cinco productos terminados más vendidos por cantidad en septiembre de 2026', conversation, 'DIRECT_UNAVAILABLE')
            assert qty['audit']['capability_calls'] == 0 and qty['audit']['confirmed_state']['metric'] == 'sales.source_top_items'
            ambiguous = await turn('Dame los cinco más vendidos por precio de venta de productos terminados en septiembre de 2026',
                'ranking-ambiguous-' + uuid4().hex, 'NEEDS_CLARIFICATION')
            assert ambiguous['audit']['capability_calls'] == 0
            report['observations']['assistant_foundation'] = dict(status='PASS', reload_every_turn=True,
                incident_exact_state=True, original_question=True, sequence='A → B → C → D → E', ordinal_projection=True)
            report['unit_price_distinction'] = dict(status='PASS', explicit_unit_price_not_ranked=True,
                quantities_not_monetary=True, missing_monetary_context_clarified=True)
            report['observations']['http_auth'] = dict(status='PASS', missing_and_invalid_token_denied=True)
        # Current-code durable claim/cache/intent evidence, not inherited solely from a fingerprint.
        isolated = replace(binding, receiver_context='ranking-gate:' + uuid4().hex)
        isolated_channel = replace(channel, receiver_context=isolated.receiver_context)
        message = InboundMessage(provider='evolution', channel='whatsapp', external_message_id='ranking-gate-' + uuid4().hex,
            sender=settings.authorized_sender, recipients=(isolated.receiver_context,),
            text_body='Dame los cinco productos terminados con mayor importe acumulado vendido en septiembre de 2026',
            external_thread_id=None, subject=None, received_at=datetime.now(timezone.utc),
            metadata={'provider_instance': binding.provider_instance, 'local_gate_probe': True})
        repo = MessagingRepository()
        async with transaction(pool) as conn:
            claimed = await repo.claim(conn, isolated, message, {})
            assert claimed
        class MeasuredCapabilities(SalesCapabilities):
            calls = 0
            async def execute(self, state):
                self.calls += 1
                return await super().execute(state)
        measured = MeasuredCapabilities()
        durable_model = LunaInterpreter()
        durable_handler = TelchiHandler(store=PostgresConversationStore(pool), authorization=auth,
            interpreter=durable_model, capabilities=measured)
        dispatcher = MessageDispatcher(channels=(isolated_channel,), handlers={'telchi': registration(durable_handler)},
            identities=PostgresPhoneIdentityResolver(pool), environment='dev')
        result = await dispatcher.dispatch(message, channel_id=isolated.channel_id,
            conversation_id=claimed['thread_id'], correlation_id=claimed['id'])
        assert result.classification == 'DIRECT_AVAILABLE' and 'Bs 259.922,61' in result.text
        async with transaction(pool) as conn:
            await repo.complete_dispatch(conn, isolated, claimed, result)
        async def duplicate():
            async with transaction(pool) as conn:
                return await repo.claim(conn, isolated, message, {})
        assert await duplicate() is None
        assert await asyncio.gather(duplicate(), duplicate()) == [None, None]
        cached = await TelchiHandler(store=PostgresConversationStore(pool), authorization=auth,
            interpreter=durable_model, capabilities=measured).handle(message, replace(ctx, channel=isolated_channel,
                conversation_id=claimed['thread_id'], correlation_id=claimed['id']))
        assert cached.text == result.text and cached.classification == result.classification and measured.calls == 1
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                one = await repo.intent(conn, isolated, claimed, message, result.text, {})
                two = await repo.intent(conn, isolated, claimed, message, result.text, {})
                assert one == two
        report['observations']['durable_idempotency'] = dict(status='PASS', committed_pg_claim=True,
            sequential_duplicate_denied=True, concurrent_duplicate_claims_denied=2, capability_executions=measured.calls,
            new_handler_committed_cache_replay=True, actual_outbound_intent_uniqueness=True,
            outbound_intent_rolled_back=True, delivery_queued=False)
        report['durable_model'] = durable_model.last_metadata
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            assert security == await RankingRegistrationRepository().security_state(conn)
            assert original == await (await conn.execute('SELECT payload_jsonb FROM message_events WHERE id=%s AND thread_id=%s',
                (fixture['source_event_id'], fixture['source_thread_id']))).fetchone()
            assert original_thread == await (await conn.execute('SELECT metadata_jsonb FROM message_threads WHERE id=%s',
                (fixture['source_thread_id'],))).fetchone()
        report['observations']['model_no_fallback'] = dict(status='PASS', metadata=[report['model_preflight'], report['durable_model']]+[t['model'] for t in report['turns']])
        assert all(m['model'] == 'gpt-5.6-luna' and m['reasoning'] == 'medium' and m['provider'] == 'OpenAI direct'
                   and m['reasoning_echo_verified'] for m in report['observations']['model_no_fallback']['metadata'])
        assert set(report['observations']) == dev.GATES
        report['generated_at'] = datetime.now(timezone.utc).isoformat()
        report['ending_source_sha256'] = dev.source_digest()
        assert report['ending_source_sha256'] == source, 'Concurrent source change; cannot accredit current fingerprint'
        report['status'] = 'PASS'
    except BaseException as exc:
        report['failure'] = dict(type=type(exc).__name__, reason=str(exc))
        raise
    finally:
        await close_pool(pool)
        report['pool_closed'] = True
        with os.fdopen(os.open(output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
    return dict(status=report['status'], turns=len(report['turns']), pool_closed=True, whatsapp_sent=0)


def verify_ranking(turn, category, limit):
    audit = turn['audit']
    result = audit['execution_result']
    assert audit['committed'] and audit['business_rbac_verified'] and audit['required_permission'] == PERMISSION
    assert audit['capability_calls'] == 1 and result['capability'] == CAPABILITY
    state = audit['confirmed_state']
    assert state['metric'] == METRIC and state['requested_metrics'] == [METRIC]
    assert state['entity_mention']['text'] == category and state['limit'] == limit
    assert state['period'] == dict(start='2026-09-01', end_exclusive='2026-10-01')
    assert len(result['rows']) == limit and Decimal(result['reconciliation']['difference']) == 0
    validate_result(result['parameters'], result)
    assert 'Importes sin IVA, antes de notas de crédito.' in turn['text']
    assert result['coverage']['last_date'].startswith('2026-09-24')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.resolve().is_relative_to(dev.PRIVATE_ROOT.resolve()):
        raise SystemExit('new private evidence output required')
    print(json.dumps(asyncio.run(run(args.output))))


if __name__ == '__main__':
    main()

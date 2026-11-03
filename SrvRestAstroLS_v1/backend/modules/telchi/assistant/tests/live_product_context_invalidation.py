"""Authenticated DEV ASGI/PG/Luna/Foundation regression; never sends WhatsApp.

Run with --output NEW_PRIVATE_JSON. Uses existing owner-approved identity, no
lifespan/listener or RBAC writes. Deterministic audited replay and real Luna are
reported separately. Produces private evidence, not an automatic gate approval.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import secrets
from uuid import uuid4

import httpx

from modules.db.pool import create_pool, set_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.messaging.handlers import ChannelContext, MessageContext
from modules.messaging.identity import PhoneIdentityRepository
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.composition import create_telchi_app
from modules.telchi.assistant.dev_runtime_http import DevAssistantController, DEV_PATH
from modules.telchi.assistant.handler import BusinessPolicy, BusinessAuthorization, PostgresConversationStore
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.provisioning.category_repository import CategoryRegistrationRepository, PERMISSION

FIXTURE = Path(__file__).parent / 'fixtures/product_context_invalidation_audited.json'


class AuditedReplay:
    """No model call: replay only the audited category proposal, not its result."""
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = 0

    async def interpret(self, **kwargs):
        self.calls += 1
        return deepcopy(self.proposal)


async def run(output):
    config = lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval_path = Path(config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    approval = dev.read_approval(approval_path)
    _, _, settings, binding = await asyncio.to_thread(dev.preflight, approval_path, require_gates=False)
    assert lifecycle.read_json(lifecycle.root() / 'current.json')['state'] == 'STOPPED'
    source = dev.source_digest()
    report = dict(status='IN_PROGRESS', source_sha256=source, observations={}, turns=[],
        authentication='Token-authenticated DEV HTTP over in-process ASGI; actual approved phone binding and Console permissions, not human login or WhatsApp ingress.',
        services_started_or_stopped=0, listeners=0, whatsapp_sent=0, rbac_writes=0)
    def check():
        dev.unchanged_approval(approval_path, approval)
    policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
        approval['module_enabled'], approval['whole_workspace_scope_verified'],
        pilot_access_check=check, pilot_user_id=approval['user_id'],
        pilot_approval_sha256=dev.approval_digest(approval))
    auth = BusinessAuthorization(policy)
    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    try:
        app = create_telchi_app(policy=policy, pool=pool)
        set_pool(pool)  # legacy composition imports must not replace our opened pool
        app.register(DevAssistantController)
        token = secrets.token_urlsafe(48)
        app.state.dev_assistant_config = dict(token=token, phone=settings.authorized_sender, binding=binding,
            instance=binding.provider_instance, receiver_context=binding.receiver_context)
        handler = app.state.messaging_handlers['telchi'].handler
        assert handler.concept_resolver is None
        channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
            binding.receiver_context, binding.tenant_id, binding.workspace_id, binding.module, binding.environment)
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            security = await CategoryRegistrationRepository().security_state(conn)
            identity = await PhoneIdentityRepository().resolve(conn, channel, settings.authorized_sender)
            ctx = MessageContext(channel, identity, settings.authorized_sender, 'probe', 'probe', frozenset())
            assert identity.user_id == approval['user_id'] and await auth.allowed(ctx, conn, required_permission=PERMISSION)
            assert any(r['user_id'] == identity.user_id for r in security['records']['core_module_full_access_grants'])
            for foreign in (replace(channel, tenant_id='foreign'), replace(channel, workspace_id=str(uuid4()))):
                assert await PhoneIdentityRepository().resolve(conn, foreign, settings.authorized_sender) is None
                assert not await auth.allowed(replace(ctx, channel=foreign), conn, required_permission=PERMISSION)
            normal = next(u for u, codes in security['effective'].items() if u != identity.user_id and PERMISSION not in codes)
            assert PERMISSION not in await PermissionConsoleRepository().list_effective_permissions(conn, policy.workspace_id, normal)
            assert not await BusinessAuthorization(replace(policy, pilot_user_id=normal)).allowed(
                replace(ctx, sender_identity=replace(identity, user_id=normal)), conn, required_permission=PERMISSION)
            assert not await auth.allowed(ctx, conn, required_permission='telchi.unregistered.probe.read.v1')
        report['observations']['authorization'] = dict(status='PASS', full_access=True, specific_permission=PERMISSION,
            ordinary_identity_denied=True, foreign_tenant_workspace_denied=True, unregistered_permission_denied=True)
        model = LunaInterpreter()
        preflight = await model.interpret(text='¿Cuánto facturamos?', state=deepcopy(EMPTY), history={}, turn_id='preflight')
        assert preflight['action'] == 'ASK' and model.last_metadata['reasoning_echo_verified']
        report['model_preflight'] = model.last_metadata
        fixture = json.loads(FIXTURE.read_text())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
            denied = await client.post(DEV_PATH + '/turn', content=b'{bad')
            assert denied.status_code == 401
            async def turn(question, conversation, interpreter):
                handler.interpreter = interpreter
                handler.store = PostgresConversationStore(pool)  # reload committed state each turn
                response = await client.post(DEV_PATH + '/turn', json=dict(text=question, conversation=conversation),
                    headers={'x-team360-dev-token': token})
                assert response.status_code == 200, response.status_code
                value = response.json()
                value.update(question=question, model=getattr(interpreter, 'last_metadata', None))
                report['turns'].append(value)
                assert value['classification'] == 'DIRECT_AVAILABLE', value
                return value
            # Seed a NEW isolated DEV thread with the exact audited pre-state.
            # Do not modify the real user's existing conversation.
            deterministic = 'context-replay-' + uuid4().hex
            seeded = await turn('Buscá productos que digan materia prima', deterministic, LunaInterpreter())
            from psycopg.types.json import Jsonb
            async with pool.connection() as conn:
                await conn.execute("UPDATE message_threads SET metadata_jsonb=jsonb_set(metadata_jsonb, '{telchi_assistant_v1,state}', %s) WHERE id=%s",
                    (Jsonb(fixture['previous_state']), seeded['conversation_id']))
            replay = AuditedReplay(fixture['proposal'])
            raw = await turn('Cuánto vendimos de materia prima en septiembre?', deterministic, replay)
            audit = raw['audit']
            assert audit['previous_state'] == fixture['previous_state'] and replay.calls == 1
            assert audit['interpretation_proposed'] == fixture['proposal']
            assert audit['confirmed_state'] == dict(fixture['obsolete_state'], product_context=None)
            verify_category(raw, '839582.63')
            # Independent genuine model sequence, retaining the persisted search state.
            conversation = 'context-luna-' + uuid4().hex
            search = await turn('Buscá productos que digan materia prima', conversation, LunaInterpreter())
            assert search['audit']['confirmed_state']['product_context']
            assert search['audit']['execution_result']['capability'] == 'products.search.v1'
            raw = await turn('Cuánto vendimos de materia prima en septiembre?', conversation, LunaInterpreter())
            assert raw['audit']['previous_state'] == search['audit']['confirmed_state']
            verify_category(raw, '839582.63')
            finished = await turn('¿Y de productos terminados?', conversation, LunaInterpreter())
            verify_category(finished, '2679208.66')
            assert raw['conversation_id'] == finished['conversation_id'] != seeded['conversation_id']
            assert finished['audit']['confirmed_state']['entity_mention']['text'] == 'LAB_FINISHED_PRODUCT'
            report['observations']['persisted_replay'] = dict(status='PASS', exact_audited_state_and_delta=True)
            report['observations']['real_luna'] = dict(status='PASS', sequence='persisted search → RAW_MATERIAL → LAB_FINISHED_PRODUCT')
        metadata = [report['model_preflight']] + [t['model'] for t in report['turns'] if t['model']]
        assert all(m['provider'] == 'OpenAI direct' and m['reasoning_echo_verified'] and m['model'] == 'gpt-5.6-luna' for m in metadata)
        async with pool.connection() as conn:
            await conn.execute('SET TRANSACTION READ ONLY')
            assert security == await CategoryRegistrationRepository().security_state(conn)
        assert dev.source_digest() == source, 'Source changed concurrently; evidence cannot accredit current fingerprint'
        report['status'] = 'PASS'
    finally:
        await close_pool(pool)
        report['pool_closed'] = True
        with output.open('x') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
    return dict(status=report['status'], turns=len(report['turns']), raw_material='839582.63', pool_closed=True)


def verify_category(turn, amount):
    audit = turn['audit']
    result = audit['execution_result']
    assert audit['committed'] and audit['business_rbac_verified'] and audit['required_permission'] == PERMISSION
    assert audit['capability_calls'] == 1 and result['capability'] == 'sales.category_line_amount.v1'
    assert Decimal(result['rows'][0]['amount']) == Decimal(amount)
    assert audit['confirmed_state']['product_context'] is None
    assert audit['confirmed_state']['product_search_text'] is None
    assert result['coverage']['complete'] is False and result['coverage']['last_date'].startswith('2026-09-24')
    assert 'líneas comerciales' in turn['text'] and 'No incluye IVA' in turn['text'] and 'notas de crédito' in turn['text']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        raise SystemExit('Output must be new with existing parent; use PRIVATE_ROOT for full audit')
    print(json.dumps(asyncio.run(run(args.output))))


if __name__ == '__main__':
    main()

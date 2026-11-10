"""Real PG + real investigator/readonly SQL, synthetic Luna/data/transport.

Explicit isolated-schema opt-in. No operational identities, policies, Foundation,
Luna provider or WhatsApp are changed. Interruptions discard the whole service
and handler (including in-memory conversation) before recovery.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
from time import perf_counter
import json
from uuid import uuid4

import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.domain.messages import InboundMessage, OutboundMessageReceipt
from modules.messaging.handlers import ChannelContext, MessageContext, SenderIdentity, MessageDispatcher
from modules.messaging.repository import MessagingRepository
from modules.messaging.service import MessagingService
from modules.messaging.durable import DurableWorker
from modules.messaging.durable_repository import DurableInboxRepository
from modules.telchi.assistant.handler import PostgresConversationStore, registration
from modules.telchi.assistant.tests.test_research_fallback import build, GAP
from modules.telchi.exploratory_sql.authorized_foundation import AuthorizedFoundationExecutor
from modules.telchi.exploratory_sql.console_bridge import ConsoleResearchService
from modules.telchi.exploratory_sql.test_authorized_foundation import setup
from modules.telchi.exploratory_sql import ask, adaptive_research
from modules.telchi.research_port import WhatsAppResearchPort
from modules.telchi.research_repository import ResearchRecoveryRepository

pytestmark = pytest.mark.skipif(os.getenv('TEAM360_DURABLE_RESEARCH_POSTGRES_TEST') != '1',
                               reason='Isolated PostgreSQL schema opt-in required')


class Interrupted(BaseException):
    pass


@pytest.mark.parametrize('point', ['before_sql', 'after_sql', 'multistep',
                                  'after_research', 'after_result', 'revoked', 'identity_revoked',
                                  'policy_changed', 'publication_changed', 'uncertain'])
def test_recovery(setup, monkeypatch, point):
    async def exercise():
        schema = 'research_recovery_' + uuid4().hex
        settings = get_database_settings(min_size=1, max_size=5)
        admin = create_pool(settings)
        await open_pool(admin)
        pool = None
        try:
            async with transaction(admin) as conn:
                assert (await (await conn.execute('SELECT 1 AS ready')).fetchone())['ready'] == 1
                await conn.execute('CREATE SCHEMA ' + schema)
            pool = AsyncConnectionPool(settings.dsn, min_size=1, max_size=5, open=False,
                kwargs={'row_factory': dict_row, 'options': '-csearch_path=' + schema})
            await open_pool(pool)
            repo, recovery = MessagingRepository(), ResearchRecoveryRepository()
            user, org = str(uuid4()), str(uuid4())
            async with transaction(pool) as conn:
                backend = Path(__file__).resolve().parents[2]
                for name in ['001_team360_core_schema.sql', '026_team360_messaging_transport_v1.sql']:
                    await conn.execute((backend / 'db/migrations' / name).read_text())
                await conn.execute("INSERT INTO core_workspaces(slug,display_name) VALUES('fixture','Fixture')")
                base = await repo.provision_dev_channel(conn, workspace_slug='fixture',
                    channel_alias='fixture', provider='evolution', instance='fixture')
                await conn.execute('INSERT INTO core_users(id,workspace_id) VALUES(%s,%s)',
                                   (user, base.workspace_id))
                await conn.execute('CREATE TABLE fixture_grants(permission text PRIMARY KEY)')
                await conn.execute("INSERT INTO fixture_grants VALUES('existing.sales.read')")
            binding = replace(base, environment='dev', module='telchi', tenant_id='telchi',
                              receiver_context='receiver')
            setup.policies = [replace(p, organization=org, workspace=binding.workspace_id)
                              for p in setup.policies]

            class Identity:
                async def identity(self, conn, ident):
                    row = await (await conn.execute("SELECT id::text AS user_id FROM core_users WHERE id=%s AND status='active'", (ident,))).fetchone()
                    return dict(row, organization=org, workspace=binding.workspace_id) if row else None
                async def enabled_permissions(self, conn, workspace):
                    return frozenset({'existing.sales.read'})
                async def list_effective_permissions(self, conn, workspace, ident):
                    rows = await (await conn.execute('SELECT permission FROM fixture_grants')).fetchall()
                    return frozenset(r['permission'] for r in rows)
                async def resolve(self, channel, phone):
                    return SenderIdentity(user, 'telchi', binding.workspace_id,
                                          permissions=frozenset({'fixture.business.read'}))

            model_calls, sql_calls, writes = [], [], []
            interrupt = [point]
            original_execute = AuthorizedFoundationExecutor.execute
            def execute(executor, proposal, context, **kwargs):
                if interrupt[0] == 'before_sql':
                    interrupt[0] = None
                    raise Interrupted()
                result = original_execute(executor, proposal, context, **kwargs)
                assert result[1].status == 'COMPLETED'
                sql_calls.append(result[1].rows)
                if interrupt[0] == 'after_sql' or (interrupt[0] == 'multistep' and len(sql_calls) == 2):
                    interrupt[0] = None
                    raise Interrupted()
                return result
            monkeypatch.setattr(AuthorizedFoundationExecutor, 'execute', execute)

            class Probe:
                calls = []
                async def next(self, *args, **kwargs): return {'ready': True}
            class Model:
                def __init__(self): self.calls = []
                async def next(self, payload, **kwargs):
                    model_calls.append(1)
                    self.calls.append({'elapsed_seconds': 0})
                    manifests = [o['evidence_manifest'] for o in payload['observations']
                                 if o.get('evidence_manifest')]
                    if len(manifests) >= 3:
                        m = manifests[-1]
                        claim = dict(kind='executed_cell', result_id=m['result_id'],
                            row_id=m['row_ids'][0], column_id=m['columns'][0]['column_id'])
                        return dict(action='final', answer='Fixture verified total: 30',
                                    claims=[claim], coverage='COMPLETE')
                    predicates = ['', ' WHERE amount > 0', ' WHERE amount < 100']
                    sql = 'SELECT sum(amount) AS total FROM sales_line' + predicates[len(manifests)]
                    return dict(action='query', sql=sql,
                        objective='Fixture analysis', justification='Read fixture source',
                        requested_sources=['sales_line'], expected_grain='aggregate',
                        expected_result='sum', candidate_relations=[], hypothesis='Fixture',
                        prior_observation_interpretation='', hypothesis_state='OPEN', evidence_turns=[])
            monkeypatch.setattr(adaptive_research, 'LunaSQL', lambda **kw: Probe())
            monkeypatch.setattr(ask, 'CancellableLuna', lambda cancel, **kw: Model())

            class Sender:
                calls = 0
                def send_text(self, **kwargs):
                    self.calls += 1
                    if point == 'uncertain':
                        from modules.messaging.domain.delivery import MessagingSendError
                        raise MessagingSendError('fixture_unknown', uncertain=True)
                    return OutboundMessageReceipt('fixture-' + str(self.calls), '')
            sender = Sender()
            revoked_cases = {'revoked', 'identity_revoked', 'policy_changed', 'publication_changed'}
            seen_conversations = []
            original_model_next = Model.next
            async def capture_conversation(self, payload, **kwargs):
                seen_conversations.append(payload.get('conversation', []))
                return await original_model_next(self, payload, **kwargs)
            monkeypatch.setattr(Model, 'next', capture_conversation)
            original_save = recovery.save
            async def measured_save(*args):
                started = perf_counter()
                await original_save(*args)
                writes.append((perf_counter() - started) * 1000)
            monkeypatch.setattr(recovery, 'save', measured_save)

            def compose():
                identities = Identity()
                research = ConsoleResearchService(pool=pool, public_keys_by_id={},
                    organization=org, workspace=binding.workspace_id, policies=setup.policies,
                    reader=setup.reader, enabled=True, environment='dev')
                port = WhatsAppResearchPort(service=research, organization=org,
                    workspace=binding.workspace_id, policies=setup.policies,
                    evidence_sink_factory=lambda: (lambda _: None), identities=identities,
                    permissions=identities, recovery_repository=recovery)
                handler = build([GAP] * 10, port)
                handler.store = PostgresConversationStore(pool)
                async def allowed(*args, **kw): return True
                handler.authorization.allowed = allowed
                channel = ChannelContext(binding.channel_id, 'evolution', 'fixture', 'receiver',
                                         'telchi', binding.workspace_id, 'telchi')
                dispatcher = MessageDispatcher(channels=(channel,),
                    handlers={'telchi': registration(handler)}, identities=identities)
                composed = MessagingService(pool=pool, repository=repo, binding=binding,
                    sender=sender, authorized_sender='', dispatcher=dispatcher, durable=True)
                composed.fixture_port = port
                composed.fixture_handler = handler
                return composed

            service = compose()
            def message(ident):
                return InboundMessage('evolution', 'whatsapp', ident, '', '15550000001',
                    ('receiver',), '', 'Relaciona ventas autorizadas', datetime.now(timezone.utc),
                    {'provider_instance': 'fixture'})
            assert await service.process(message('one'), t0_ms=0, t1_ms=0) == 'queued'
            # Admission must remain independent of the active investigator.
            original_next = Model.next
            ingress = []
            async def next_with_ingress(self, *args, **kwargs):
                future = asyncio.run_coroutine_threadsafe(service.process(message('two'),
                    t0_ms=0, t1_ms=0), loop)
                ingress.append(future.result(timeout=2))
                return await original_next(self, *args, **kwargs)
            loop = asyncio.get_running_loop()
            monkeypatch.setattr(Model, 'next', next_with_ingress)
            original_intent = repo.intent
            async def before_outbound(*args, **kwargs):
                raise Interrupted()
            if point == 'after_result':
                monkeypatch.setattr(repo, 'intent', before_outbound)
            if point in revoked_cases:
                monkeypatch.setattr(service, '_send_horizontal', before_outbound)
            original_store_save = PostgresConversationStore.save
            if point == 'after_research':
                monkeypatch.setattr(PostgresConversationStore, 'save', before_outbound)
            if point != 'uncertain':
                with pytest.raises(Interrupted):
                    await DurableWorker(service).tick()
                assert sender.calls == 0
            else:
                assert await DurableWorker(service).tick()
            before = (len(model_calls), len(sql_calls))
            monkeypatch.setattr(repo, 'intent', original_intent)
            monkeypatch.setattr(PostgresConversationStore, 'save', original_store_save)
            monkeypatch.setattr(Model, 'next', original_next)
            if point == 'revoked':
                async with transaction(pool) as conn:
                    await conn.execute('DELETE FROM fixture_grants')
            if point == 'identity_revoked':
                async with transaction(pool) as conn:
                    await conn.execute("UPDATE core_users SET status='inactive' WHERE id=%s", (user,))
            if point == 'policy_changed':
                setup.policies = [replace(p, columns=('doc_entry',)) for p in setup.policies]
            if point == 'publication_changed':
                with setup.reader.connector.session() as db:
                    setup.reader.resolve_on(db).foundation_publication_id = 'fixture_new_publication'
            recovered = compose()  # no original investigator/session/handler memory
            started = perf_counter()
            if point == 'uncertain':
                # Reconciliation only, never automatic or explicit uncertain retry.
                assert await recovered.recover_delivery(message('one'), retry=True) == 'retry_reviewed'
                assert sender.calls == 1
            else:
                assert await DurableWorker(recovered).tick()
                assert sender.calls == (0 if point in revoked_cases else 1)
            recovery_ms = (perf_counter() - started) * 1000
            if point in {'after_research', 'after_result', 'uncertain'} | revoked_cases:
                assert before == (len(model_calls), len(sql_calls))
            async with transaction(pool) as conn:
                evidence = await repo.evidence(conn, binding)
                first = next(r for r in evidence if r['direction']=='inbound' and r['provider_message_id']=='one')
                state = first['payload_jsonb']['durable_job']['state']
                if point in revoked_cases:
                    assert state == 'CANCELED'
                elif point == 'uncertain':
                    assert state == 'FAILED_FINAL'
                    candidates = await DurableInboxRepository().candidates(conn, binding)
                    assert all(str(c['id']) != str(first['id']) for c in candidates)
                elif point != 'uncertain':
                    assert state == 'OUTBOUND_ACCEPTED'
                out = [r for r in evidence if r['direction']=='outbound' and r['correlation_id']==str(first['id'])]
                assert len(out) <= 1
                if point not in revoked_cases | {'uncertain'}:
                    assert sql_calls and all(rows == ((30,),) for rows in sql_calls)
            assert await recovered.process(message('one'), t0_ms=0, t1_ms=0) == 'duplicate'
            assert sender.calls <= 1
            assert ingress and ingress[0] == 'queued'
            measurement = dict(point=point, llm_calls=len(model_calls), sql_calls=len(sql_calls),
                recovery_llm_calls=len(model_calls)-before[0], recovery_sql_calls=len(sql_calls)-before[1],
                recovery_ms=round(recovery_ms, 3), persistence_statement_ms=round(sum(writes), 3),
                ingress=ingress, outbound_calls=sender.calls, fixture_only=True)
            if point == 'after_result':
                paired = []
                for _ in range(3):
                    pair = {}
                    for durable in (False, True):
                        instance = compose()
                        if not durable:
                            instance.fixture_port.recovery_repository = None
                        channel = ChannelContext(binding.channel_id, 'evolution', 'fixture',
                            'receiver', 'telchi', binding.workspace_id, 'telchi')
                        identity = await Identity().resolve(channel, '15550000001')
                        ctx = MessageContext(channel, identity, '15550000001', str(uuid4()),
                                             str(uuid4()), frozenset())
                        start = perf_counter()
                        report = await instance.fixture_port('Relaciona ventas autorizadas',
                                                            ctx.conversation_id, ctx)
                        assert '30' in report['business_answer']
                        pair['durable_ms' if durable else 'baseline_ms'] = (perf_counter()-start)*1000
                    pair['delta_ms'] = pair['durable_ms']-pair['baseline_ms']
                    paired.append({k: round(v, 3) for k, v in pair.items()})
                measurement['paired_port_latency_fixture'] = paired
                measurement['live_43006ms_comparison'] = 'NOT_MEASURED; synthetic Luna and fixture Foundation'
            if point == 'after_research':
                assert not recovered.fixture_handler.interpreter.calls
                seen_conversations.clear()
                assert await DurableWorker(compose()).tick()  # queued follow-up, fresh service
                assert sender.calls == 2
                assert seen_conversations and seen_conversations[0]
                assert any(h['role'] == 'assistant' for h in seen_conversations[0])
                measurement['conversation_survives_restart'] = True
            print(json.dumps(measurement, sort_keys=True))
        finally:
            if pool: await close_pool(pool)
            async with transaction(admin) as conn:
                await conn.execute('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE')
            await close_pool(admin)
    asyncio.run(exercise())

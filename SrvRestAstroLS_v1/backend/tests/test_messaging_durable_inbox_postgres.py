"""Opt-in PG contract in a unique disposable schema, never operational rows."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

import pytest

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.domain.messages import InboundMessage, OutboundMessageReceipt
from modules.messaging.handlers import MessageResult
from modules.messaging.repository import MessagingRepository
from modules.messaging.durable import DurableWorker
from modules.messaging.durable_repository import DurableInboxRepository
from modules.messaging.service import MessagingService

pytestmark = pytest.mark.skipif(os.getenv('TEAM360_DURABLE_INBOX_POSTGRES_TEST') != '1',
                              reason='Explicit isolated schema PostgreSQL opt-in required')


def test_real_pg_durable_duplicates_order_recovery_and_nonblocking_ingress(monkeypatch):
    async def exercise():
        schema = 'durable_inbox_' + uuid4().hex
        settings = get_database_settings(min_size=1, max_size=5)
        admin = create_pool(settings)
        await open_pool(admin)
        pool = None
        try:
            async with transaction(admin) as conn:
                await conn.execute('CREATE SCHEMA ' + schema)
            # This pool can only see fixture tables; no operational table fallback.
            from psycopg_pool import AsyncConnectionPool
            from psycopg.rows import dict_row
            pool = AsyncConnectionPool(settings.dsn, min_size=1, max_size=5, open=False,
                kwargs={'row_factory': dict_row, 'options': '-csearch_path=' + schema})
            await open_pool(pool)
            repo = MessagingRepository()
            async with transaction(pool) as conn:
                backend = Path(__file__).resolve().parents[1]
                for name in ['001_team360_core_schema.sql', '026_team360_messaging_transport_v1.sql']:
                    await conn.execute((backend / 'db/migrations' / name).read_text())
                await conn.execute("INSERT INTO core_workspaces(slug,display_name) VALUES ('fixture','Fixture')")
                base = await repo.provision_dev_channel(conn, workspace_slug='fixture', channel_alias='fixture',
                    provider='evolution', instance='fixture')
            binding = replace(base, environment='dev', module='telchi', tenant_id='telchi', receiver_context='receiver')
            from modules.messaging.handlers import ChannelContext, SenderIdentity, MessageDispatcher
            from modules.telchi.assistant.handler import PostgresConversationStore, registration
            from modules.telchi.assistant.tests.test_assistant import setup, proposal, plan
            handler, _, interpreter, analytical_calls = setup([
                proposal({'/metric':'sales.source_top_items','/period':plan()['period']}, intent='NEW_QUERY'),
                proposal({'/metric':'sales.source_top_items','/period':plan()['period']}, intent='NEW_QUERY'),
                proposal({'/metric':'sales.source_top_items','/period':plan()['period']}, intent='NEW_QUERY'),
                proposal({'/metric':'sales.source_top_items','/period':plan()['period']}, intent='NEW_QUERY')])
            handler.store = PostgresConversationStore(pool)
            # Authorization and Foundation fixtures are explicit here; this test
            # accredits real PG atomicity, not real grants/model/business results.
            async def allowed(*args, **kwargs): return True
            monkeypatch.setattr(handler.authorization, 'allowed', allowed)
            class Identities:
                async def resolve(self, channel, phone):
                    return SenderIdentity('fixture-user','telchi',binding.workspace_id,
                        permissions=frozenset({'fixture.business.read','telchi.sales.source_quantity.read.v1'}))
            channel = ChannelContext(binding.channel_id,'evolution','fixture','receiver',
                'telchi',binding.workspace_id,'telchi')
            dispatcher = MessageDispatcher(channels=(channel,), handlers={'telchi':registration(handler)},
                                           identities=Identities())
            class Sender:
                calls = 0
                fail = False
                def send_text(self, **kw):
                    from modules.messaging.domain.delivery import MessagingSendError
                    self.calls += 1
                    if self.fail:
                        raise MessagingSendError('fixture_confirmed_failure', uncertain=False)
                    return OutboundMessageReceipt('out-' + str(self.calls), '')
            sender = Sender()
            service = MessagingService(pool=pool, repository=repo, binding=binding,
                sender=sender, authorized_sender='', dispatcher=dispatcher, durable=True)
            def message(ident):
                return InboundMessage('evolution','whatsapp',ident,'','15550000001',('receiver',),'',
                    'fixture query',datetime.now(timezone.utc),{'provider_instance':'fixture'})
            async def receive(ident):
                return await service.process(message(ident),t0_ms=0,t1_ms=0)
            # Real authenticated HTTP boundary/normalizer and PG, no external
            # provider. Ten concurrent retries acknowledge only durable inbox.
            from types import SimpleNamespace
            from unittest.mock import AsyncMock
            from litestar import Litestar
            from litestar.testing import AsyncTestClient
            import modules.messaging.webhooks.evolution_whatsapp as webhook
            app = Litestar(route_handlers=[webhook.EvolutionWhatsAppWebhookController])
            app.state.srv05_settings = SimpleNamespace(evolution_enabled=True,
                messaging=SimpleNamespace(webhook_token='synthetic-webhook-token'),
                evolution=SimpleNamespace(instance='fixture'), recipient='receiver')
            app.state.transport_v1 = object()
            app.state.durable_messaging = True
            monkeypatch.setenv('TEAM360_ENV','dev')
            monkeypatch.setenv('TEAM360_MESSAGING_DEV_ENABLED','1')
            monkeypatch.setattr(webhook,'build_service',AsyncMock(return_value=service))
            payload = {'event':'messages.upsert','instance':'fixture','data':{
                'key':{'id':'one','remoteJid':'15550000001@s.whatsapp.net','fromMe':False},
                'message':{'conversation':'fixture query'}}}
            async with AsyncTestClient(app) as client:
                async def post():
                    response = await client.post('/webhooks/messaging/evolution/whatsapp',
                        headers={'x-team360-webhook-token':'synthetic-webhook-token'},json=payload)
                    assert response.status_code == 200
                    return next(iter(response.json()['results']))
                outcomes = await asyncio.gather(*(post() for _ in range(10)))
            assert outcomes.count('queued') == 1 and outcomes.count('duplicate') == 9
            assert len(analytical_calls) == sender.calls == 0
            async with transaction(pool) as conn:
                rows = await DurableInboxRepository().candidates(conn,binding)
            first = rows[0]
            # Simulate the lock held throughout Luna. Both a duplicate and the
            # next message must commit without waiting for the analysis lock.
            async with transaction(pool) as locked:
                await locked.execute('SELECT id FROM message_threads WHERE id=%s FOR NO KEY UPDATE',
                                     (first['thread_id'],))
                assert await asyncio.wait_for(receive('one'),2) == 'duplicate'
                assert await asyncio.wait_for(receive('two'),2) == 'queued'
            # Recreate the worker after durable receive; no HTTP request remains.
            worker = DurableWorker(service)
            original_intent = repo.intent
            async def crash_after_result(*args, **kwargs):
                raise RuntimeError('crash after committed Telchi result before outbound intent')
            monkeypatch.setattr(repo, 'intent', crash_after_result)
            with pytest.raises(RuntimeError):
                await worker.tick()
            assert len(analytical_calls) == 1 and sender.calls == 0
            monkeypatch.setattr(repo, 'intent', original_intent)
            assert await DurableWorker(service).tick()
            assert await DurableWorker(service).tick()
            assert len(analytical_calls) == len(interpreter.calls) == 2
            assert not await worker.tick()
            assert sender.calls == 2
            async with transaction(pool) as conn:
                evidence = await repo.evidence(conn,binding)
            inbound = [r for r in evidence if r['direction']=='inbound']
            outbound = [r for r in evidence if r['direction']=='outbound']
            assert len(inbound) == len(outbound) == 2
            assert all(r['payload_jsonb']['durable_job']['state']=='OUTBOUND_ACCEPTED' for r in inbound)
            assert not any(r['transport_status']=='delivered' for r in outbound)
            assert await receive('one') == 'duplicate'
            assert sender.calls == 2
            # Explicit known-failure retry revalidates the cached result, never
            # recalculates it, and reuses one logical outbound row.
            assert await receive('three') == 'queued'
            sender.fail = True
            assert await worker.tick()
            assert len(analytical_calls) == 3 and sender.calls == 3
            sender.fail = False
            assert await service.recover_delivery(message('three'), retry=True) == 'retry_reviewed'
            assert len(analytical_calls) == 3 and sender.calls == 4
            # Permission revoked after committed preparation: no protected send.
            assert await receive('four') == 'queued'
            original_send = service._send_horizontal
            async def stop_before_send(*args, **kwargs):
                raise RuntimeError('worker stopped before send')
            monkeypatch.setattr(service, '_send_horizontal', stop_before_send)
            with pytest.raises(RuntimeError): await worker.tick()
            async def revoked(*args, required_permission=None, **kwargs):
                return required_permission is None
            monkeypatch.setattr(handler.authorization, 'allowed', revoked)
            monkeypatch.setattr(service, '_send_horizontal', original_send)
            assert await DurableWorker(service).tick()
            assert sender.calls == 4 and len(analytical_calls) == 4
            async with transaction(pool) as conn:
                foreign = replace(binding, workspace_id=str(uuid4()))
                assert await DurableInboxRepository().candidates(conn,foreign) == []
                evidence = await repo.evidence(conn,binding)
            last = next(r for r in evidence if r['provider_message_id']=='four')
            assert last['payload_jsonb']['durable_job']['state'] == 'CANCELED'
            # Persistence failure after INSERT rolls back and NEVER acknowledges
            # success; the provider's subsequent retry can durably enqueue it.
            original_claim = repo.claim
            async def fail_commit(*args, **kwargs):
                await original_claim(*args, **kwargs)
                raise RuntimeError('fixture persistence failure')
            monkeypatch.setattr(repo, 'claim', fail_commit)
            from copy import deepcopy
            failed_payload = deepcopy(payload)
            failed_payload['data']['key']['id'] = 'persist-failure'
            async with AsyncTestClient(app) as client:
                response = await client.post('/webhooks/messaging/evolution/whatsapp',
                    headers={'x-team360-webhook-token':'synthetic-webhook-token'}, json=failed_payload)
                assert response.status_code == 503
                async with transaction(pool) as conn:
                    assert await DurableInboxRepository().find_id(conn,binding,'persist-failure') is None
                monkeypatch.setattr(repo, 'claim', original_claim)
                response = await client.post('/webhooks/messaging/evolution/whatsapp',
                    headers={'x-team360-webhook-token':'synthetic-webhook-token'}, json=failed_payload)
                assert response.json()['results'] == {'queued':1}
            monkeypatch.setattr(dispatcher, 'dispatch', AsyncMock(return_value=
                MessageResult('temporary access system failure','fixture','ERROR')))
            assert await worker.tick()
            assert await receive('later') == 'queued'
            async with transaction(pool) as conn:
                pending_id = await DurableInboxRepository().find_id(conn,binding,'persist-failure')
                pending = await DurableInboxRepository().load(conn,binding,pending_id)
                assert pending['payload_jsonb']['durable_job']['state'] == 'FAILED_RETRYABLE'
                assert pending['payload_jsonb']['durable_job']['attempts'] == 1
                # The delayed oldest turn still fences the later turn.
                assert await DurableInboxRepository().candidates(conn,binding) == []
        finally:
            if pool: await close_pool(pool)
            async with transaction(admin) as conn:
                await conn.execute('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE')
            await close_pool(admin)
    asyncio.run(exercise())

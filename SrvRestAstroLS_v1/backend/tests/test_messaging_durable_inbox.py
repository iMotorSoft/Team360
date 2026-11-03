"""Durable worker fault injection. Doubles are NOT external WhatsApp evidence."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from modules.messaging.durable import DurableWorker
from modules.messaging.handlers import MessageResult
from modules.messaging.repository import ChannelBinding


@pytest.fixture
def harness(monkeypatch):
    rows, intents, results, sends = {}, {}, {}, []
    binding = ChannelBinding('w', 'c', 'p', 'instance', 'dev', 'telchi', 'telchi', 'receiver')
    @asynccontextmanager
    async def transaction(pool):
        yield None
    monkeypatch.setattr('modules.messaging.durable.transaction', transaction)
    class Inbox:
        async def candidates(self, conn, binding):
            return [dict(id=k, thread_id=v['thread_id']) for k, v in rows.items()
                    if v['payload_jsonb']['durable_job']['state'] not in
                    {'OUTBOUND_ACCEPTED', 'FAILED_FINAL', 'CANCELED'}][:1]
        async def lock(self, *args): return True
        async def load(self, conn, binding, event_id): return rows[event_id]
        async def state(self, conn, binding, event_id, state, **kw):
            rows[event_id]['payload_jsonb']['durable_job']['state'] = state
        async def cancel_outbound(self, conn, binding, event_id):
            intents[event_id]['payload_jsonb']['initial_result'] = 'authorization_revoked'
    class Repo:
        async def recoverable_intent(self, conn, binding, message):
            return intents.get(message.external_message_id)
        async def complete_dispatch(self, *args): pass
        async def intent(self, conn, binding, claimed, message, text, timings):
            ident = claimed['id']
            intents[ident] = dict(id=ident, status='pending', payload_jsonb={
                'text': text, 'initial_result': 'dispatch_intent'})
            return ident
    class Dispatcher:
        calls = 0
        authorized = True
        async def dispatch(self, message, **kw):
            ident = kw['correlation_id']
            if not self.authorized:
                return MessageResult('denied', ident, 'DENIED')
            if ident not in results:
                self.calls += 1
                results[ident] = MessageResult('real result fixture', ident, 'DIRECT_AVAILABLE')
            return results[ident]
    async def send(ident, sender, text, timings):
        sends.append(ident)
        intents[ident]['status'] = 'completed'
        return 'accepted'
    service = SimpleNamespace(pool=None, durable=True, binding=binding, repository=Repo(),
        dispatcher=Dispatcher(), _send_horizontal=send)
    def enqueue(ident):
        rows[ident] = dict(id=ident, thread_id='thread', provider_message_id=ident,
            occurred_at_utc=datetime.now(timezone.utc), payload_jsonb=dict(
                provider='evolution', channel='whatsapp', sender='15550000001',
                recipients=['receiver'], text='query', metadata={'provider_instance': 'instance'},
                timings={}, durable_job={'state': 'QUEUED'}))
    return SimpleNamespace(service=service, inbox=Inbox(), enqueue=enqueue, rows=rows,
        intents=intents, results=results, sends=sends,
        worker=lambda: DurableWorker(service, repository=Inbox()))


def test_restart_with_committed_result_does_not_recalculate(harness):
    async def run():
        h = harness
        h.enqueue('a')
        h.results['a'] = MessageResult('real result fixture', 'a', 'DIRECT_AVAILABLE')
        h.rows['a']['payload_jsonb']['durable_job']['state'] = 'RUNNING'
        assert await h.worker().tick()
        assert h.service.dispatcher.calls == 0 and h.sends == ['a']
        assert not await h.worker().tick()
    asyncio.run(run())


def test_order_and_restart_before_outbound(harness):
    async def run():
        h = harness
        h.enqueue('a'); h.enqueue('b')
        send = h.service._send_horizontal
        async def crash(*args): raise RuntimeError('worker stopped before transport fence')
        h.service._send_horizontal = crash
        with pytest.raises(RuntimeError): await h.worker().tick()
        assert not h.sends and h.service.dispatcher.calls == 1
        h.service._send_horizontal = send
        assert await h.worker().tick()
        assert await h.worker().tick()
        assert h.sends == ['a', 'b'] and h.service.dispatcher.calls == 2
    asyncio.run(run())


def test_revocation_after_result_never_sends_protected_text(harness):
    async def run():
        h = harness
        h.enqueue('a')
        h.intents['a'] = dict(id='a', status='pending', payload_jsonb={
            'text': 'protected', 'initial_result': 'dispatch_intent'})
        h.service.dispatcher.authorized = False
        await h.worker().tick()
        assert not h.sends and h.rows['a']['payload_jsonb']['durable_job']['state'] == 'CANCELED'
    asyncio.run(run())


def test_uncertain_outbound_never_automatically_resends(harness):
    async def run():
        h = harness
        h.enqueue('a')
        h.intents['a'] = dict(id='a', status='pending', payload_jsonb={'initial_result': 'sending'})
        await h.worker().tick()
        assert not h.sends and h.service.dispatcher.calls == 0
        assert not await h.worker().tick()
    asyncio.run(run())


def test_acceptance_persisted_before_worker_crash_is_not_delivery_or_resend(harness):
    async def run():
        h = harness
        h.enqueue('a')
        h.intents['a'] = dict(id='a', status='completed', payload_jsonb={'initial_result': 'accepted'})
        await h.worker().tick()
        assert not h.sends and h.service.dispatcher.calls == 0
        assert h.rows['a']['payload_jsonb']['durable_job']['state'] == 'OUTBOUND_ACCEPTED'
    asyncio.run(run())

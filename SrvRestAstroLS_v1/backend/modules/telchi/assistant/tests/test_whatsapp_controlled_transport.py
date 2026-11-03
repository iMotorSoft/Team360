"""Controlled Evolution wire -> real Messaging/Telchi -> Evolution wire.

DB, identities, interpreter and Evolution HTTP are explicit doubles. No real
WhatsApp delivery, human identity, Foundation read or commercial data is used.
"""
import asyncio
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest

from modules.messaging.handlers import MessageDispatcher
from modules.messaging.providers.evolution.config import EvolutionConfig
from modules.messaging.providers.evolution.provider import EvolutionProvider
from modules.messaging.repository import ChannelBinding
from modules.messaging.service import MessagingService
from modules.messaging.domain.egress import OutboundIdentity
from modules.telchi.assistant.handler import registration
from .test_assistant import TransportStore, context, setup, proposal, run, plan
from modules.messaging.providers.evolution.mapper import normalize_events
from datetime import datetime, timezone


class WireTransportStore(TransportStore):
    """Map symbolic test IDs to canonical wire IDs at the send fence."""

    async def begin_send(self, conn, binding, outbound_id, retry=False):
        started = await super().begin_send(conn, binding, outbound_id, retry=retry)
        if started:
            canonical = lambda value: str(uuid5(NAMESPACE_URL, value))
            self.intents[outbound_id]['identity'] = OutboundIdentity(
                canonical(outbound_id), str(uuid4()), canonical(binding.workspace_id),
                canonical(binding.channel_id), binding.provider_instance)
        return started

    async def send_identity(self, conn, binding, outbound_id):
        identity = self.intents[outbound_id]['identity']
        assert identity.provider_instance == binding.provider_instance
        return identity


@pytest.mark.parametrize('scenario', ['ASK', 'BLOCK_INVALID_PLAN', 'BLOCK_IDENTITY', 'EXECUTE'])
@run
async def test_controlled_response_idempotent_through_evolution_wire(monkeypatch, scenario):
    @asynccontextmanager
    async def tx(pool):
        yield object()
    monkeypatch.setattr('modules.messaging.service.transaction', tx)
    raw = (proposal({'/metric': 'sales.source_top_items'}, action='ASK', intent='NEW_QUERY',
                    clarification={'slot': 'period', 'question': '¿Qué período querés consultar?'})
           if scenario == 'ASK' else proposal({'/metric': plan()['metric'], '/period': plan()['period']})
           if scenario == 'EXECUTE' else proposal({'/unknown': 'must never execute'}))
    handler, store, interpreter, capability_calls = setup([raw])
    c = context()
    class Identities:
        async def resolve(self, channel, phone):
            return None if scenario == 'BLOCK_IDENTITY' else c.sender_identity
    dispatcher = MessageDispatcher(channels=(c.channel,), identities=Identities(),
                                    handlers={'telchi': registration(handler)})
    requests = []
    def wire(request):
        import json
        body = json.loads(request.content)
        assert request.url.path == '/message/sendText/instance'
        assert body['number'] == '123456789'
        requests.append(body)
        assert body['team360_egress'] == repository.intents['synthetic-controlled']['identity'].wire()
        return httpx.Response(201, json={'egress': {
            **body['team360_egress'], 'acceptance': 'ACCEPTED',
            'provider_message_id': 'wamid.synthetic-receipt',
            'automatic_retry': False, 'durable': True}})
    sender = EvolutionProvider(EvolutionConfig('http://test', 'instance', 'synthetic-key'),
                               transport=httpx.MockTransport(wire))
    repository = WireTransportStore()
    service = MessagingService(pool=object(), repository=repository,
        binding=ChannelBinding('workspace', 'channel', 'provider', 'instance', 'dev', 'telchi', 'tenant', 'receiver'),
        sender=sender, authorized_sender='', dispatcher=dispatcher)
    payload = {'event': 'messages.upsert', 'instance': 'instance', 'data': {
        'key': {'id': 'synthetic-controlled', 'remoteJid': '123456789@s.whatsapp.net', 'fromMe': False},
        'message': {'conversation': 'Consulta sintética controlada'}}}
    event, = normalize_events(payload, instance='instance', recipient='receiver', received_at=datetime.now(timezone.utc))
    results = await asyncio.gather(*(service.process(event, t0_ms=0, t1_ms=1) for _ in range(2)))
    assert sorted(results) == ['accepted', 'duplicate']
    assert await service.process(event, t0_ms=0, t1_ms=1) == 'duplicate'
    assert len(requests) == len(repository.intents) == 1
    assert len(capability_calls) == (1 if scenario == 'EXECUTE' else 0)
    result = repository.results['synthetic-controlled']
    assert result.correlation_id == 'synthetic-controlled'
    assert requests[0]['text'] == result.text
    if scenario == 'ASK':
        assert result.classification == 'NEEDS_CLARIFICATION'
        assert len(interpreter.calls) == 1
    elif scenario == 'EXECUTE':
        assert result.classification == 'DIRECT_AVAILABLE'
        assert len(interpreter.calls) == 1
    elif scenario == 'BLOCK_IDENTITY':
        assert result.classification == 'DENIED'
        assert not interpreter.calls
    else:
        assert result.classification == 'ERROR'
        assert len(interpreter.calls) == 1

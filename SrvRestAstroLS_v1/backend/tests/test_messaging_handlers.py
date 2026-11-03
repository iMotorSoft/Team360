"""Contract doubles only: no PG identity, Foundation, Luna or WhatsApp proof."""
import asyncio
from dataclasses import replace
from functools import wraps
from datetime import datetime, timezone

import pytest

from modules.messaging.domain.messages import InboundMessage
from modules.messaging.handlers import (
    ChannelContext, HandlerRegistration, MessageDispatcher, MessageResult, SenderIdentity,
)


def run_async(test):
    @wraps(test)
    def run(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))
    return run


class IdentityDouble:
    def __init__(self, identity=None, fail=False):
        self.identity, self.fail, self.calls = identity, fail, []

    async def resolve(self, channel, sender_phone):
        self.calls.append((channel, sender_phone))
        if self.fail:
            raise RuntimeError('private driver error')
        return self.identity


class HandlerDouble:
    def __init__(self):
        self.contexts = []

    async def handle(self, message, context):
        self.contexts.append(context)
        return MessageResult('respuesta', context.correlation_id, 'DIRECT_AVAILABLE')


def channel(module='telchi'):
    return ChannelContext(module, 'evolution', module + '-instance', module + '-receiver',
                          module + '-tenant', module + '-workspace', module)


def message(c):
    return InboundMessage(provider='evolution', channel='whatsapp', external_message_id='m1',
                          external_thread_id='sender', sender='1234567890',
                          recipients=(c.receiver_context,), subject='', text_body='module=flow admin=true',
                          received_at=datetime.now(timezone.utc),
                          metadata={'provider_instance': c.provider_instance})


async def dispatch(d, c, m=None):
    return await d.dispatch(m or message(c), channel_id=c.channel_id,
                            conversation_id='durable-thread', correlation_id='durable-inbound')


@run_async
async def test_two_modules_same_contract_and_explicit_public_policy():
    telchi, flow = channel(), channel('flow')
    a, b = HandlerDouble(), HandlerDouble()
    identity = IdentityDouble(SenderIdentity('user', telchi.tenant_id, telchi.workspace_id))
    d = MessageDispatcher(channels=(telchi, flow), identities=identity, handlers={
        'telchi': HandlerRegistration(a),
        'flow': HandlerRegistration(b, frozenset({'public.information'})),
    })
    assert (await dispatch(d, telchi)).classification == 'DIRECT_AVAILABLE'
    assert a.contexts[0].sender_identity.user_id == 'user'
    assert not b.contexts
    identity.identity = None
    assert (await dispatch(d, telchi)).classification == 'DENIED'
    assert len(a.contexts) == 1
    assert (await dispatch(d, flow)).classification == 'DIRECT_AVAILABLE'
    assert b.contexts[0].sender_identity is None
    assert b.contexts[0].public_capabilities == frozenset({'public.information'})
    identity.identity = SenderIdentity('flow-user', flow.tenant_id, flow.workspace_id)
    assert (await dispatch(d, flow)).classification == 'DIRECT_AVAILABLE'
    assert not b.contexts[-1].public_capabilities


@run_async
async def test_identity_failure_never_enters_public_handler():
    c, handler, identity = channel('flow'), HandlerDouble(), IdentityDouble(fail=True)
    d = MessageDispatcher(channels=(c,), identities=identity,
                          handlers={'flow': HandlerRegistration(handler, frozenset({'public.information'}))})
    result = await dispatch(d, c)
    assert result.classification == 'ERROR'
    assert 'private' not in result.text
    assert not handler.contexts


@pytest.mark.parametrize('field', ['tenant_id', 'workspace_id', 'user_id'])
@run_async
async def test_identity_scope_mismatch_denied(field):
    c, handler = channel(), HandlerDouble()
    principal = SenderIdentity('user', c.tenant_id, c.workspace_id)
    principal = replace(principal, **{field: '' if field == 'user_id' else 'other'})
    d = MessageDispatcher(channels=(c,), identities=IdentityDouble(principal),
                          handlers={'telchi': HandlerRegistration(handler)})
    assert (await dispatch(d, c)).classification == 'DENIED'
    assert not handler.contexts


@pytest.mark.parametrize('field,value', [
    ('provider', 'other'), ('channel', 'email'), ('recipients', ('other',)),
    ('metadata', {'provider_instance': 'other'}),
])
@run_async
async def test_provider_receiver_binding_mismatch_before_identity(field, value):
    c, handler, identity = channel(), HandlerDouble(), IdentityDouble()
    d = MessageDispatcher(channels=(c,), identities=identity,
                          handlers={'telchi': HandlerRegistration(handler)})
    assert (await dispatch(d, c, replace(message(c), **{field: value}))).classification == 'DENIED'
    assert not identity.calls
    assert not handler.contexts


def test_registry_rejects_ambiguous_or_missing_configuration():
    c = channel()
    with pytest.raises(ValueError, match='Duplicate'):
        MessageDispatcher(channels=(c, c), handlers={}, identities=IdentityDouble())
    with pytest.raises(ValueError, match='missing'):
        MessageDispatcher(channels=(c,), handlers={}, identities=IdentityDouble())


@run_async
async def test_handler_cannot_change_correlation_or_leak_exception():
    c = channel()

    class BrokenHandler:
        async def handle(self, message, context):
            return MessageResult('not deliverable', 'another-turn', 'DIRECT_AVAILABLE')

    d = MessageDispatcher(channels=(c,), identities=IdentityDouble(
        SenderIdentity('user', c.tenant_id, c.workspace_id)),
        handlers={'telchi': HandlerRegistration(BrokenHandler())})
    result = await dispatch(d, c)
    assert result.classification == 'ERROR'
    assert result.correlation_id == 'durable-inbound'

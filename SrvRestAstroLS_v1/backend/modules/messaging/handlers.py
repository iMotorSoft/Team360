"""Minimal module dispatch contract; composition supplies trusted DB resolvers.

Not a webhook or an authorization engine. The caller owns durable claim,
conversation recovery, response intent and delivery. Business operations must
recheck effective permissions in the module, including on subsequent turns.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .domain.messages import InboundMessage


@dataclass(frozen=True)
class ChannelContext:
    channel_id: str
    provider: str
    provider_instance: str
    receiver_context: str
    tenant_id: str
    workspace_id: str
    module: str
    environment: str = 'dev'


@dataclass(frozen=True)
class SenderIdentity:
    user_id: str
    tenant_id: str
    workspace_id: str
    environment: str = 'dev'
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MessageContext:
    channel: ChannelContext
    sender_identity: SenderIdentity | None
    sender_phone: str
    conversation_id: str
    correlation_id: str
    public_capabilities: frozenset[str]


@dataclass(frozen=True)
class MessageResult:
    text: str
    correlation_id: str
    classification: Literal[
        'DIRECT_AVAILABLE', 'NEEDS_CLARIFICATION', 'DIRECT_UNAVAILABLE',
        'ANALYSIS_UNAVAILABLE', 'DENIED', 'ERROR',
    ]


class MessageHandler(Protocol):
    async def handle(self, message: InboundMessage, context: MessageContext) -> MessageResult: ...


class InvalidIdentityBinding(ValueError):
    """A known binding is revoked, ambiguous, corrupt or out of scope."""


class IdentityResolver(Protocol):
    async def resolve(self, channel: ChannelContext, sender_phone: str) -> SenderIdentity | None:
        """None means verified absence; DB/unverifiable identity must raise.

        Implementations must use a previously authorized telephone link and
        active Team360 identity, not message content or a transport allowlist.
        """
        ...


@dataclass(frozen=True)
class HandlerRegistration:
    handler: MessageHandler
    public_capabilities: frozenset[str] = frozenset()
    anonymous_denial: str = 'Este canal requiere un usuario autorizado.'
    required_permissions: frozenset[str] = frozenset()
    environment: str = 'dev'


class MessageDispatcher:
    """A simple explicit registry, independent of any business module or LLM.

    Channels come from trusted configuration/PG bindings, never payload-selected
    modules. Public capability names are limits, not grants to private data.
    A module handler must enforce them and authorize each sensitive operation.
    """

    def __init__(self, *, channels: tuple[ChannelContext, ...],
                 handlers: dict[str, HandlerRegistration], identities: IdentityResolver,
                 environment: str = 'dev'):
        if environment not in {'dev', 'pro', 'laboratory'}:
            raise ValueError('Invalid runtime environment')
        self.environment = environment
        self._channels = {c.channel_id: c for c in channels}
        if len(self._channels) != len(channels):
            raise ValueError('Duplicate channel registration')
        if any(c.module not in handlers for c in channels):
            raise ValueError('Channel handler missing')
        if any(not all((c.channel_id, c.provider, c.provider_instance,
                        c.receiver_context, c.tenant_id, c.workspace_id, c.module)) for c in channels):
            raise ValueError('Incomplete channel context')
        self._handlers = dict(handlers)
        self._identities = identities

    async def dispatch(self, message: InboundMessage, *, channel_id: str,
                       conversation_id: str, correlation_id: str) -> MessageResult:
        """IDs and channel_id must be supplied by the durable caller, not text."""
        denied = MessageResult('No se pudo autorizar esta solicitud.', correlation_id, 'DENIED')
        channel = self._channels.get(channel_id)
        if (channel is None or channel.environment != self.environment
                or not conversation_id or not correlation_id):
            return denied
        # V1 is direct text only. Group and LID messages need separate verified
        # participant/receiver normalization before this contract can accept them.
        if (message.provider != channel.provider or message.channel != 'whatsapp'
                or message.metadata.get('provider_instance') != channel.provider_instance
                or message.recipients != (channel.receiver_context,)):
            return denied
        registration = self._handlers[channel.module]
        if registration.environment != channel.environment:
            return denied
        try:
            identity = await self._identities.resolve(channel, message.sender)
        except InvalidIdentityBinding:
            return denied
        except Exception:
            # Never downgrade identity-system failures to anonymous/public access.
            return MessageResult('No se pudo verificar el acceso. Intentá nuevamente.',
                                 correlation_id, 'ERROR')
        if identity is not None and (not identity.user_id
                or identity.workspace_id != channel.workspace_id
                or identity.tenant_id != channel.tenant_id
                or identity.environment != channel.environment):
            return denied
        if (identity is not None
                and not registration.required_permissions <= identity.permissions):
            return denied
        public = registration.public_capabilities if identity is None else frozenset()
        if identity is None and not public:
            return MessageResult(registration.anonymous_denial, correlation_id, 'DENIED')
        context = MessageContext(channel, identity, message.sender, conversation_id,
                                 correlation_id, public)
        try:
            result = await registration.handler.handle(message, context)
        except Exception:
            return MessageResult('No se pudo completar la solicitud.', correlation_id, 'ERROR')
        if not isinstance(result, MessageResult) or result.correlation_id != correlation_id:
            return MessageResult('No se pudo completar la solicitud.', correlation_id, 'ERROR')
        return result

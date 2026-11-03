"""Authenticated Evolution HTTP boundary; provider payloads stop here."""
from __future__ import annotations

from datetime import datetime, timezone
import hmac
import json
import os
from collections import Counter

from litestar import Controller, Request, post
from litestar.exceptions import HTTPException
from modules.db.pool import get_pool
from modules.db.transaction import transaction
from modules.messaging.providers.evolution.config import EvolutionConfig, EvolutionConfigurationError
from modules.messaging.providers.evolution.mapper import normalize_events
from modules.messaging.providers.evolution.provider import EvolutionProvider
from modules.messaging.repository import MessagingRepository
from modules.messaging.service import MessagingService, epoch_ms
from modules.messaging.settings import MessagingDevSettings
from modules.messaging.profile_trace import enabled, span, aspan


async def build_service(settings, config, *, handlers=None, transport_runtime=None, durable=False):
    repository = MessagingRepository()
    pool = get_pool()
    async with aspan('messaging_binding_lookup'), transaction(pool) as conn:
        binding = await repository.binding(conn, workspace_slug=settings.workspace_slug,
                                           channel_alias=settings.channel_alias,
                                           provider='evolution', instance=config.instance)
    if binding is None:
        raise ValueError('Messaging binding unavailable')
    # Srv05 supplies its already-accredited lifecycle runtime. Standalone legacy
    # fixtures remain separate; an enabled Srv05 can never reach that branch.
    sender = transport_runtime.sender() if transport_runtime is not None else EvolutionProvider(config)
    horizontal = getattr(settings, 'dispatch_mode', 'legacy') == 'horizontal_v1'
    if horizontal != (binding.environment is not None):
        raise ValueError('Runtime/channel dispatcher mismatch')
    if horizontal:
        from modules.messaging.handlers import ChannelContext, MessageDispatcher
        from modules.messaging.identity import PostgresPhoneIdentityResolver
        # Registrations are supplied by trusted composition, never webhook JSON
        # or dynamic imports selected by channel metadata. Missing means closed.
        registrations = handlers or {}
        registration = registrations.get(binding.module)
        if registration is None:
            raise ValueError('Approved module handler required')
        if durable and not getattr(registration.handler, 'durable_replay_safe', False):
            raise ValueError('Durable dispatch requires a transactional replay-safe handler')
        dispatcher = MessageDispatcher(
            channels=(ChannelContext(binding.channel_id, 'evolution', config.instance,
                                     binding.receiver_context, binding.tenant_id,
                                     binding.workspace_id, binding.module, binding.environment),),
            handlers=registrations, identities=PostgresPhoneIdentityResolver(pool),
            environment=(transport_runtime.document['scope']['environment'] if transport_runtime else 'dev'))
        return MessagingService(pool=pool, repository=repository, binding=binding,
                                sender=sender, authorized_sender='', dispatcher=dispatcher, durable=durable)
    capability = None
    if settings.telchi_tenant == 'telchi':
        from modules.messaging.telchi_sql import TelchiSqlAdapter
        with span('messaging_capability_resolution'):
            capability = TelchiSqlAdapter()
    return MessagingService(pool=pool, repository=repository, binding=binding,
                            sender=sender, authorized_sender=settings.authorized_sender,
                            telchi_capability=capability, tenant=settings.telchi_tenant)


class EvolutionWhatsAppWebhookController(Controller):
    path = '/webhooks/messaging/evolution/whatsapp'
    tags = ['Messaging Webhooks']

    @post(status_code=200, request_max_body_size=1_048_576)
    async def receive(self, request: Request) -> dict[str, object]:
        if enabled():
            from modules.telchi.datalake.query_profile import Trace
            with Trace().activate():
                return await self._receive(request)
        return await self._receive(request)

    async def _receive(self, request: Request) -> dict[str, object]:
        t0 = epoch_ms()
        received_at = datetime.now(timezone.utc)
        try:
            with span('messaging_config'):
                composition = getattr(request.app.state, 'srv05_settings', None)
                if composition is not None:
                    if (not composition.evolution_enabled
                            or os.getenv('TEAM360_ENV', '').strip().lower() not in {'dev', 'development'}
                            or os.getenv('TEAM360_MESSAGING_DEV_ENABLED') != '1'):
                        raise ValueError('DEV messaging disabled')
                    settings, config = composition.messaging, composition.evolution
                else:
                    # Standalone messaging-only test/lab composition.
                    settings = MessagingDevSettings.from_env()
                    config = EvolutionConfig.from_env()
        except (ValueError, EvolutionConfigurationError):
            raise HTTPException(status_code=503, detail='DEV messaging not configured') from None
        token = request.headers.get('x-team360-webhook-token', '')
        with span('messaging_auth'):
            if not hmac.compare_digest(token.encode(), settings.webhook_token.encode()):
                raise HTTPException(status_code=401, detail='Invalid webhook credentials')
        try:
            async with aspan('messaging_body_decode'):
                payload = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail='Invalid JSON') from None
        with span('messaging_normalization'):
            events = normalize_events(payload, instance=config.instance,
                                      recipient=(composition.recipient if composition is not None else
                                                 os.getenv('META_TEAM360_PHONE_NUMBER_ID', '').strip()),
                                      received_at=received_at)
        t1 = epoch_ms()
        if not events:
            return {'ok': True, 'results': {'ignored': 1}}
        try:
            handlers = getattr(request.app.state, 'messaging_handlers', None)
            if composition is not None:
                runtime = getattr(request.app.state, 'transport_v1', None)
                if runtime is None:
                    raise ValueError('Srv05 V1 runtime unavailable')
                service = await build_service(settings, config, handlers=handlers, transport_runtime=runtime,
                                              durable=getattr(request.app.state, 'durable_messaging', False))
            else:
                service = (await build_service(settings, config) if handlers is None else
                           await build_service(settings, config, handlers=handlers))
            results = Counter()
            for event in events:
                results[await service.process(event, t0_ms=t0, t1_ms=t1)] += 1
        except Exception:
            # No provider payload, phone, API key or exception text in logs/response.
            raise HTTPException(status_code=503, detail='Messaging persistence unavailable') from None
        return {'ok': True, 'results': dict(results)}

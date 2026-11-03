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


async def build_service(settings, config):
    repository = MessagingRepository()
    pool = get_pool()
    async with transaction(pool) as conn:
        binding = await repository.binding(conn, workspace_slug=settings.workspace_slug,
                                           channel_alias=settings.channel_alias,
                                           provider='evolution', instance=config.instance)
    capability = None
    if settings.telchi_tenant == 'telchi':
        from modules.messaging.telchi_sql import TelchiSqlAdapter
        capability = TelchiSqlAdapter()
    return MessagingService(pool=pool, repository=repository, binding=binding,
                            sender=EvolutionProvider(config), authorized_sender=settings.authorized_sender,
                            telchi_capability=capability, tenant=settings.telchi_tenant)


class EvolutionWhatsAppWebhookController(Controller):
    path = '/webhooks/messaging/evolution/whatsapp'
    tags = ['Messaging Webhooks']

    @post(status_code=200, request_max_body_size=1_048_576)
    async def receive(self, request: Request) -> dict[str, object]:
        t0 = epoch_ms()
        received_at = datetime.now(timezone.utc)
        try:
            settings = MessagingDevSettings.from_env()
            config = EvolutionConfig.from_env()
        except (ValueError, EvolutionConfigurationError):
            raise HTTPException(status_code=503, detail='DEV messaging not configured') from None
        token = request.headers.get('x-team360-webhook-token', '')
        if not hmac.compare_digest(token.encode(), settings.webhook_token.encode()):
            raise HTTPException(status_code=401, detail='Invalid webhook credentials')
        try:
            payload = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail='Invalid JSON') from None
        events = normalize_events(payload, instance=config.instance,
                                  recipient=os.getenv('META_TEAM360_PHONE_NUMBER_ID', '').strip(),
                                  received_at=received_at)
        t1 = epoch_ms()
        if not events:
            return {'ok': True, 'results': {'ignored': 1}}
        try:
            service = await build_service(settings, config)
            results = Counter()
            for event in events:
                results[await service.process(event, t0_ms=t0, t1_ms=t1)] += 1
        except Exception:
            # No provider payload, phone, API key or exception text in logs/response.
            raise HTTPException(status_code=503, detail='Messaging persistence unavailable') from None
        return {'ok': True, 'results': dict(results)}

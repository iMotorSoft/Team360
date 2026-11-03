"""DEV-only HTTP adapter for the real Telchi conversational pipeline.

This module is NOT an alternative implementation of the assistant. It mounts a
single token-gated, loopback-only endpoint that feeds the same
``MessageDispatcher`` -> ``TelchiHandler`` -> State Engine -> capabilities route
used by the Evolution/WhatsApp webhook, then reads the audit the handler already
persisted in PostgreSQL. No WhatsApp message is ever sent: there is no outbound
transport here, only the durable conversation rows that Messaging owns.

Security posture (all required, fail closed):
  * ``TEAM360_ENV`` in {dev, development};
  * ``TEAM360_TELCHI_ASSISTANT_DEV_HTTP=1`` (disabled by default);
  * ``TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN`` (>= 32 chars, hmac compared);
  * loopback-only bind;
  * identity is resolved from the approved PostgreSQL phone binding, never from
    a client-supplied user/tenant/permission;
  * the pilot phone comes from ``TEAM360_TELCHI_ASSISTANT_DEV_PHONE``, not from
    the request body.

It reuses the existing Srv05/Telchi composition (``create_telchi_app``) so the
handler registration, DB pool lifecycle and Evolution binding validation are the
productive ones. Only the Flow scheduler hooks are dropped: they are an
unrelated shared module and are not needed to converse.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hmac
import os
from time import perf_counter
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from litestar import Controller, Request, post
from litestar.exceptions import HTTPException

from modules.messaging.domain.messages import InboundMessage
from modules.messaging.handlers import ChannelContext, MessageDispatcher
from modules.messaging.identity import PostgresPhoneIdentityResolver
from modules.messaging.repository import MessagingRepository
from modules.db.transaction import transaction

HEALTH_PATH = '/health'
DEV_PATH = '/api/telchi/assistant/dev'
_TOKEN_HEADER = 'x-team360-dev-token'


def _env(name: str, default: str = '') -> str:
    return os.getenv(name, default).strip()


def guard_environment() -> dict:
    """Return the validated DEV configuration or raise before serving."""
    if _env('TEAM360_ENV').lower() not in {'dev', 'development'}:
        raise RuntimeError('DEV HTTP assistant requires TEAM360_ENV=dev')
    if _env('TEAM360_TELCHI_ASSISTANT_DEV_HTTP') != '1':
        raise RuntimeError('DEV HTTP assistant disabled (set TEAM360_TELCHI_ASSISTANT_DEV_HTTP=1)')
    token = _env('TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN')
    if len(token) < 32:
        raise RuntimeError('DEV HTTP assistant token too short')
    phone = _env('TEAM360_TELCHI_ASSISTANT_DEV_PHONE')
    if not phone:
        raise RuntimeError('DEV HTTP assistant pilot phone required')
    if _env('TEAM360_MESSAGING_DISPATCH_MODE') != 'horizontal_v1':
        raise RuntimeError('DEV HTTP assistant requires horizontal_v1 dispatch')
    return dict(token=token, phone=phone,
                workspace_slug=_env('TEAM360_MESSAGING_WORKSPACE_SLUG'),
                channel_alias=_env('TEAM360_MESSAGING_CHANNEL_ALIAS'),
                instance=_env('TEAM360_EVOLUTION_INSTANCE'))


def _resolve_binding(workspace_slug: str, channel_alias: str, instance: str):
    from modules.db.settings import get_database_settings

    async def run():
        async with await psycopg.AsyncConnection.connect(
                get_database_settings().dsn, row_factory=dict_row) as conn:
            return await MessagingRepository().binding(
                conn, workspace_slug=workspace_slug, channel_alias=channel_alias,
                provider='evolution', instance=instance)

    return asyncio.run(run())


class _SessionBoundPhoneIdentity:
    """Same DB identity resolver, additionally bound to the authenticated subject."""
    def __init__(self, identities, user_id):
        self.identities, self.user_id = identities, user_id

    async def resolve(self, channel, sender_phone):
        identity = await self.identities.resolve(channel, sender_phone)
        if identity is None or identity.user_id != self.user_id:
            raise PermissionError('authenticated_subject_phone_mismatch')
        return identity


async def _human_subject(request, config):
    """Reuse Console's existing password session verifier, never issue tokens here."""
    if not config.get('requires_human_session'):
        return None
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 16384:
        raise HTTPException(status_code=401, detail='Console password session required')
    from modules.console.auth import ConsoleAuthError
    handler = request.app.state.messaging_handlers['telchi'].handler
    if handler.semantics_connection is None:
        raise HTTPException(status_code=503, detail='Restricted semantics connection required')
    try:
        async with handler.semantics_connection() as conn:
            principal = await request.app.state.dev_assistant_login_service.verify_session(
                conn, header[7:], workspace_id=config['binding'].workspace_id)
        return principal.user_id
    except (ConsoleAuthError, PermissionError):
        raise HTTPException(status_code=401, detail='Console session denied') from None
    except Exception:
        raise HTTPException(status_code=503, detail='Console session verification unavailable') from None


async def _run_turn(*, pool, registrations, binding, message, conversation_key, authenticated_user_id=None):
    """Feed one turn through the real dispatcher; return (result, ids, elapsed)."""
    channel = ChannelContext(binding.channel_id, 'evolution', binding.provider_instance,
                             binding.receiver_context, binding.tenant_id, binding.workspace_id,
                             binding.module, binding.environment)
    identities = PostgresPhoneIdentityResolver(pool)
    if authenticated_user_id is not None:
        identities = _SessionBoundPhoneIdentity(identities, authenticated_user_id)
        # Check before persisting an event, and check again at dispatch to prevent
        # rebinding between HTTP authentication and handler entry.
        await identities.resolve(channel, message.sender)
    dispatcher = MessageDispatcher(channels=(channel,), handlers=registrations,
                                   identities=identities, environment='dev')
    contact_identity = f'{message.sender}#dev:{conversation_key}'
    instance = binding.storage_instance
    started = perf_counter()
    async with transaction(pool) as conn:
        thread = await (await conn.execute("""
            INSERT INTO message_threads(workspace_id,channel_id,provider_instance,contact_identity,last_message_at_utc)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (channel_id,provider_instance,contact_identity) WHERE provider_instance IS NOT NULL
            DO UPDATE SET last_message_at_utc=GREATEST(message_threads.last_message_at_utc,EXCLUDED.last_message_at_utc),
                          updated_at_utc=now()
            RETURNING id
            """, (binding.workspace_id, binding.channel_id, instance, contact_identity,
                  message.received_at))).fetchone()
        event = await (await conn.execute("""
            INSERT INTO message_events(workspace_id,thread_id,channel_id,provider_id,provider_instance,
                provider_message_id,direction,event_type,status,transport_status,contact_identity,payload_jsonb,occurred_at_utc)
            VALUES (%s,%s,%s,%s,%s,%s,'inbound','message','running','received',%s,%s,%s)
            RETURNING id,thread_id
            """, (binding.workspace_id, thread['id'], binding.channel_id, binding.provider_id, instance,
                  message.external_message_id, contact_identity,
                  Jsonb({'text': message.text_body, 'sender': message.sender,
                         'recipients': list(message.recipients), 'channel': message.channel,
                         'provider': message.provider, 'metadata': dict(message.metadata),
                         'environment': binding.environment, 'processing_state': 'running',
                         'dev_adapter': {'conversation_key': conversation_key}}),
                  message.received_at))).fetchone()
    result = await dispatcher.dispatch(message, channel_id=binding.channel_id,
                                       conversation_id=str(event['thread_id']),
                                       correlation_id=str(event['id']))
    elapsed_ms = (perf_counter() - started) * 1000
    async with transaction(pool) as conn:
        row = await (await conn.execute(
            'SELECT payload_jsonb FROM message_events WHERE id=%s', (event['id'],))).fetchone()
        await conn.execute("""
            UPDATE message_events SET status='completed', payload_jsonb=payload_jsonb || %s
            WHERE id=%s AND channel_id=%s AND provider_instance=%s
            """, (Jsonb({'processing_state': 'result_persisted',
                         'dispatch_result': {'text': result.text, 'classification': result.classification,
                                             'correlation_id': result.correlation_id}}),
                  event['id'], binding.channel_id, instance))
    return result, dict(conversation_id=str(event['thread_id']),
                        correlation_id=str(event['id']),
                        payload=(row or {}).get('payload_jsonb') or {}), elapsed_ms


class DevAssistantController(Controller):
    path = DEV_PATH

    @post('/turn', status_code=200)
    async def turn(self, request: Request) -> dict:
        config = request.app.state.dev_assistant_config
        if not hmac.compare_digest(request.headers.get(_TOKEN_HEADER, ''), config['token']):
            raise HTTPException(status_code=401, detail='Invalid DEV assistant token')
        authenticated_user_id = await _human_subject(request, config)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail='Invalid JSON body') from None
        if not isinstance(body, dict) or set(body) - {'text', 'conversation'}:
            raise HTTPException(status_code=400, detail='Allowed fields: text, conversation')
        text = body.get('text')
        conversation = body.get('conversation', 'default')
        if not isinstance(text, str) or not 0 < len(text) <= 4000:
            raise HTTPException(status_code=400, detail='text is required (1..4000 chars)')
        if not isinstance(conversation, str) or not 0 < len(conversation) <= 64:
            raise HTTPException(status_code=400, detail='conversation must be 1..64 chars')
        from modules.db.pool import get_pool
        message = InboundMessage(
            provider='evolution', channel='whatsapp',
            external_message_id=f'dev-{uuid4()}', sender=config['phone'],
            recipients=(config['receiver_context'],), text_body=text,
            external_thread_id=None, subject=None, received_at=datetime.now(timezone.utc),
            metadata={'provider_instance': config['instance']})
        try:
            result, ids, elapsed_ms = await _run_turn(
                pool=get_pool(), registrations=request.app.state.messaging_handlers,
                binding=config['binding'], message=message, conversation_key=conversation,
                authenticated_user_id=authenticated_user_id)
        except PermissionError:
            raise HTTPException(status_code=403, detail='Authenticated identity not bound to channel') from None
        except Exception:
            raise HTTPException(status_code=503, detail='Conversation pipeline unavailable') from None
        audit = ids['payload'].get('telchi_assistant_v1') if isinstance(ids['payload'], dict) else None
        return dict(ok=True, text=result.text, classification=result.classification,
                    conversation_key=conversation, conversation_id=ids['conversation_id'],
                    correlation_id=ids['correlation_id'], elapsed_ms=round(elapsed_ms, 2),
                    audit=audit)


class _LoopbackBoundary:
    """Expose only health and the DEV assistant over loopback; block the rest."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path, method = scope['path'], scope['method']
            allowed = (path == HEALTH_PATH and method in {'GET', 'HEAD'}) or (
                path.startswith(DEV_PATH + '/') and method == 'POST')
            if not allowed:
                await send({'type': 'http.response.start', 'status': 404,
                            'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"detail":"Not Found"}'})
                return
        await self.app(scope, receive, send)


def create_dev_app():
    """Build the real Telchi composition plus the DEV assistant route."""
    config = guard_environment()
    from modules.telchi.assistant.composition import create_telchi_app
    from modules.telchi.assistant.handler import BusinessPolicy

    binding = _resolve_binding(config['workspace_slug'], config['channel_alias'], config['instance'])
    policy = BusinessPolicy(binding.tenant_id, binding.workspace_id,
                            'telchi.sales.source_quantity.read.v1', True, True)
    app = create_telchi_app(policy=policy)
    app.on_startup = [h for h in app.on_startup if getattr(h, '__name__', '') != '_start_flow_scheduler']
    app.on_shutdown = [h for h in app.on_shutdown if getattr(h, '__name__', '') != '_stop_flow_scheduler']
    app.register(DevAssistantController)
    handler = app.state.messaging_handlers['telchi'].handler
    requires_human_session = handler.concept_resolver is not None
    if requires_human_session:
        from modules.console.login_cli import read_config, issuer_settings
        from modules.console.login_service import ConsoleLoginService
        cfg = read_config(_env('TEAM360_SEMANTICS_AUTH_CONFIG'))
        app.state.dev_assistant_login_service = ConsoleLoginService(issuer_settings(cfg))
    app.state.dev_assistant_config = dict(config, binding=binding,
                                          requires_human_session=requires_human_session,
                                          receiver_context=binding.receiver_context)
    return _LoopbackBoundary(app)


def main():
    import uvicorn
    host = _env('TEAM360_TELCHI_ASSISTANT_DEV_HTTP_HOST', '127.0.0.1')
    if host not in {'127.0.0.1', 'localhost', '::1'}:
        raise RuntimeError('DEV HTTP assistant is loopback-only')
    port = int(_env('TEAM360_TELCHI_ASSISTANT_DEV_HTTP_PORT', '7090'))
    uvicorn.run(create_dev_app(), host=host, port=port, workers=1,
                access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
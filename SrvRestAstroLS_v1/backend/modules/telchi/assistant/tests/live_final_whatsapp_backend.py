"""Owner-authorized local Messaging/Luna/PG probe; NO external WhatsApp.

Uses the approved identity and binding, isolating storage by a unique synthetic
receiver. Only the outbound sender is simulated. Never publishes startup gates.
Run sequentially after the live Foundation integrity gate.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.domain.delivery import MessagingSendError
from modules.messaging.domain.messages import InboundMessage, OutboundMessageReceipt
from modules.messaging.handlers import ChannelContext, MessageDispatcher
from modules.messaging.identity import PostgresPhoneIdentityResolver
from modules.messaging.repository import MessagingRepository
from modules.messaging.service import MessagingService
from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import (
    BusinessPolicy, BusinessAuthorization, PostgresConversationStore, TelchiHandler, registration,
)
from modules.telchi.assistant.luna import LunaInterpreter
from modules.telchi.assistant.state_engine import EMPTY
from .live_operational_authorized import QUESTIONS


async def run(output):
    if output.exists():
        raise ValueError('refusing to overwrite evidence')
    config = lifecycle.load_config(dev.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    approval_path = Path(config.get('approval', dev.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    approval = dev.read_approval(approval_path)
    srv, settings = dev.configuration()
    binding = await dev.check_database(approval, settings, srv.evolution)
    assert hashlib.sha256(settings.authorized_sender.encode()).hexdigest() == approval['sender_sha256']
    # Different storage instance, existing channel/workspace/user. No DB binding mutation.
    isolated = replace(binding, receiver_context='local-closure-' + uuid4().hex)
    channel = ChannelContext(isolated.channel_id, isolated.provider, isolated.provider_instance,
                             isolated.receiver_context, isolated.tenant_id, isolated.workspace_id,
                             isolated.module, isolated.environment)
    policy = BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
        approval['module_enabled'], approval['whole_workspace_scope_verified'],
        pilot_access_check=lambda: dev.unchanged_approval(approval_path, approval),
        pilot_user_id=approval['user_id'], pilot_approval_sha256=dev.approval_digest(approval))
    report = dict(status='RUNNING', scope='local backend probe; NOT WhatsApp ingress/delivery',
        workspace_id=binding.workspace_id, user_id=approval['user_id'], instance=binding.provider_instance,
        provider=binding.provider, synthetic_receiver_isolation=True, outbound_transport='simulated',
        real_identity=True, real_rbac=True, real_luna=True, real_foundation=True, real_postgresql=True,
        whatsapp_sent=0, grants_changed=0, source_sha256=dev.source_digest(), turns=[],
        budgets=dict(worker_seconds=300, turn_seconds=360, model_seconds=45,
                     production_defaults_changed=False), started_at=datetime.now(timezone.utc).isoformat())

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.pending.json')
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n')
        temporary.replace(output)

    class MeasuredCapabilities(SalesCapabilities):
        calls = 0

        async def execute(self, state):
            self.calls += 1
            return await super().execute(state)

    class ControlledSender:
        def __init__(self):
            self.calls = 0
            self.fail = False

        def send_text(self, *, destination, text):
            assert destination == settings.authorized_sender
            assert text and len(text) <= 4096
            assert 'SELECT ' not in text and 'read_parquet(' not in text
            self.calls += 1
            if self.fail:
                raise MessagingSendError('local_probe_confirmed_failure', uncertain=False)
            return OutboundMessageReceipt('local-probe-' + uuid4().hex, '')

    pool = create_pool(replace(get_database_settings(), min_size=1, max_size=1))
    await open_pool(pool)
    save()
    try:
        repository = MessagingRepository()
        for index, question in enumerate(QUESTIONS):
            interpreter = LunaInterpreter()
            if index == 0:
                await interpreter.interpret(text='¿Cuánto facturamos?', state=EMPTY,
                    history={}, turn_id='local-closure-preflight',
                    enterprise_context=dict(own_company={'name': 'Telchi', 'aliases': []},
                        tenant_id=approval['tenant_id'], workspace_id=approval['workspace_id']))
                report['model_preflight'] = interpreter.last_metadata
                save()
            capabilities = MeasuredCapabilities(timeout_seconds=300)
            handler = TelchiHandler(store=PostgresConversationStore(pool),
                authorization=BusinessAuthorization(policy), interpreter=interpreter,
                capabilities=capabilities, turn_timeout_seconds=360)
            dispatcher = MessageDispatcher(channels=(channel,), handlers={'telchi': registration(handler)},
                identities=PostgresPhoneIdentityResolver(pool), environment='dev')
            sender = ControlledSender()
            service = MessagingService(pool=pool, repository=repository, binding=isolated,
                sender=sender, authorized_sender='', dispatcher=dispatcher)
            message = InboundMessage(provider='evolution', channel='whatsapp',
                external_message_id='local-closure-' + uuid4().hex,
                sender=settings.authorized_sender, recipients=(isolated.receiver_context,),
                text_body=question, external_thread_id=None, subject=None,
                received_at=datetime.now(timezone.utc), metadata={'provider_instance': isolated.provider_instance,
                    'local_probe': True, 'external_whatsapp': False})
            sender.fail = index == 4
            start = monotonic()
            result = await service.process(message, t0_ms=0, t1_ms=0)
            elapsed = monotonic() - start
            assert result == ('send_failed' if sender.fail else 'accepted'), result
            calls = capabilities.calls
            assert calls == 1, f'expected one analytical call, got {calls}'
            if sender.fail:
                # Recreate service before operator-controlled retry, without a new handler call.
                sender.fail = False
                service = MessagingService(pool=pool, repository=repository, binding=isolated,
                    sender=sender, authorized_sender='', dispatcher=dispatcher)
                assert await service.recover_delivery(message, retry=True) == 'accepted'
            assert await service.process(message, t0_ms=0, t1_ms=0) == 'duplicate'
            assert await service.process(message, t0_ms=0, t1_ms=0) == 'duplicate'
            assert capabilities.calls == calls
            assert sender.calls == (2 if index == 4 else 1)
            async with transaction(pool) as conn:
                rows = await repository.evidence(conn, isolated)
            inbound = next(r for r in rows if r['direction'] == 'inbound'
                           and r['provider_message_id'] == message.external_message_id)
            outbound = [r for r in rows if r['direction'] == 'outbound'
                        and r['event_type'] == 'message' and r['correlation_id'] == str(inbound['id'])]
            assert len(outbound) == 1
            audit = inbound['payload_jsonb'].get('telchi_assistant_v1') or {}
            assert inbound['status'] == 'completed'
            assert audit, 'missing committed analytical audit'
            report['turns'].append(dict(question=question, event_id=str(inbound['id']),
                thread_id=str(inbound['thread_id']), outbound_id=str(outbound[0]['id']),
                elapsed_seconds=elapsed, analytical_calls=calls, duplicate_replays=2,
                outbound_attempts=sender.calls, classification=inbound['payload_jsonb']['dispatch_result']['classification'],
                response=outbound[0]['payload_jsonb']['text'], audit=audit,
                model=interpreter.last_metadata, provider_acceptance='SIMULATED',
                delivered=False, read=False, controlled_retry=index == 4))
            assert report['turns'][-1]['classification'] == 'DIRECT_AVAILABLE'
            print(json.dumps(dict(turn=index + 1, seconds=elapsed, status='PASS')), flush=True)
            save()
        report['status'] = 'LOCAL_BACKEND_FUNCTIONAL_PASS'
        report['not_accredited'] = ['external inbound/outbound', 'durable asynchronous admission',
            'automatic recovery of interrupted execution', 'transport admission six gates']
    except Exception as exc:
        report['status'] = 'FAIL'
        report['error'] = dict(type=type(exc).__name__, reason=str(exc))
        raise
    finally:
        await close_pool(pool)
        report['pool_closed'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))

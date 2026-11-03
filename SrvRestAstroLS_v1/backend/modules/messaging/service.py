"""Horizontal conversation/delivery ownership plus explicit legacy DEV compatibility."""
from __future__ import annotations

import asyncio
import logging
import re
import time

from modules.db.transaction import transaction
from .delivery_guard import guard_outbound
from .domain.delivery import DeliveryEvent, MessagingSendError
from .domain.messages import InboundMessage
from .domain.whatsapp import WhatsAppMessageSenderPort
from .repository import MessagingRepository, ChannelBinding
from .profile_trace import active_trace, span, aspan

logger = logging.getLogger(__name__)


def epoch_ms():
    return time.time_ns() / 1_000_000


def fixed_response(text: str) -> str | None:
    match = re.fullmatch(r'team360 ping (0[1-9]|1[0-9]|20)', text)
    return f'TEAM360 PONG {match[1]}' if match else None


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Fixed response conversation ownership]]
class MessagingService:
    def __init__(self, *, pool, repository: MessagingRepository, binding: ChannelBinding,
                 sender: WhatsAppMessageSenderPort, authorized_sender: str,
                 telchi_capability=None, tenant=None, dispatcher=None, durable=False):
        self.pool, self.repository, self.binding = pool, repository, binding
        self.sender, self.authorized_sender = sender, authorized_sender
        self.telchi_capability, self.tenant = telchi_capability, tenant
        self.dispatcher = dispatcher
        self.durable = durable
        if binding.environment is not None and (dispatcher is None
                or dispatcher.environment != binding.environment):
            raise ValueError('Horizontal dispatcher missing or environment mismatch')

    async def process(self, event: InboundMessage | DeliveryEvent, *, t0_ms, t1_ms):
        instance = (event.provider_instance if isinstance(event, DeliveryEvent)
                    else event.metadata.get('provider_instance'))
        if instance != self.binding.provider_instance:
            return 'ignored'
        if self.binding.environment is not None and event.provider != self.binding.provider:
            return 'ignored'
        if isinstance(event, DeliveryEvent):
            async with transaction(self.pool) as conn:
                await self.repository.delivery(conn, self.binding, event)
            return 'status'
        if self.binding.environment is not None:
            return await self._process_horizontal(event, t0_ms=t0_ms, t1_ms=t1_ms)
        with span('messaging_allowlist'):
            if event.sender != self.authorized_sender:
                return 'unauthorized'
        timings = {'t0_ms': t0_ms, 't1_ms': t1_ms}
        trace = (active_trace() if self.tenant == 'telchi'
                 and event.text_body.strip().lower() == 'hola' else None)
        if trace is not None:
            timings['pre_sql_profile'] = {'schema': 'telchi-pre-sql-profile-v1', 'spans': trace.events}
        async with aspan('messaging_claim_conversation_commit'), transaction(self.pool) as conn:
            claimed = await self.repository.claim(conn, self.binding, event, timings)
        if not claimed:
            return 'duplicate'
        timings['t2_ms'] = epoch_ms()  # after the inbound commit, not after execute
        reply = fixed_response(event.text_body)
        audit = None
        if self.telchi_capability is not None and self.tenant == 'telchi':
            from .telchi_sql import is_telchi_trigger
            with span('messaging_trigger_tenant_resolution'):
                triggered = is_telchi_trigger(event.text_body)
            if triggered:
                audit = {'tenant': self.tenant, 'dev_only': True, 'trigger': 'hola',
                         'capability': self.telchi_capability.capability,
                         'query_hash': self.telchi_capability.query_hash, 'status': 'started',
                         'timings': {'t0_ms': t0_ms, 't1_ms': timings['t2_ms']}}
                # Persist execution intent after durable inbound claim and before SQL.
                async with aspan('messaging_sql_intent_persistence'), transaction(self.pool) as conn:
                    await self.repository.record_sql_gate(conn, self.binding, claimed, audit)
                audit['capability_started_ms'] = epoch_ms()
                async with aspan('messaging_capability_execute_including_format'):
                    reply, result = await self.telchi_capability.execute()
                # Adapter includes formatting. Exact inner SQL timestamps live in result.
                audit['timings']['t4_ms'] = epoch_ms()
                audit.update(result)
                if result.get('result'):
                    audit['timings']['t2_ms'] = result['result']['sql_started_ms']
                    audit['timings']['t3_ms'] = result['result']['sql_finished_ms']
                async with aspan('messaging_sql_result_persistence'), transaction(self.pool) as conn:
                    await self.repository.record_sql_gate(conn, self.binding, claimed, audit)
                timings['sql_gate'] = audit
        timings['t3_ms'] = epoch_ms()
        if reply is None:
            return 'received'
        # The provider rejects a body longer than its limit: the guard keeps the
        # answer deliverable and records what was accredited but not delivered.
        decision = guard_outbound(reply)
        async with aspan('messaging_outbound_intent_persistence'), transaction(self.pool) as conn:
            outbound_id = await self.repository.intent(conn, self.binding, claimed, event, decision.text, timings)
        # Legacy and horizontal paths share the same durable pre-I/O fence.
        async with transaction(self.pool) as conn:
            await self._check_transport_binding(conn)
            started = await self.repository.begin_send(conn, self.binding, outbound_id)
        if not started:
            return 'duplicate'
        send, identity_args = await self._sender_for_intent(outbound_id, event.sender, decision.text)
        def dispatch():
            timings['t4_ms'] = epoch_ms()
            if trace is not None:
                timings['pre_sql_profile']['pre_send_ms'] = (time.perf_counter_ns()-trace.origin)/1e6
            if audit is not None:
                audit['timings']['t5_ms'] = timings['t4_ms']
            return send(destination=event.sender, text=decision.text, **identity_args)
        receipt, error = None, None
        try:
            receipt = await asyncio.to_thread(dispatch)
        except MessagingSendError as exc:
            error = exc
        except Exception:
            error = MessagingSendError('provider_unexpected_error', uncertain=True)
        timings['t5_ms'] = epoch_ms()
        if audit is not None:
            audit['timings']['t6_ms'] = timings['t5_ms']
        async with transaction(self.pool) as conn:
            if receipt:
                await self.repository.lock_receipt(conn, self.binding.provider_id,
                                                   self.binding.storage_instance, receipt.external_message_id)
            await self.repository.finish(conn, outbound_id, receipt=receipt, error=error, timings=timings)
            if audit is not None:
                await self.repository.record_sql_gate(conn, self.binding, claimed, audit)
        if error is not None:
            # A failed delivery is never silent: the durable intent already
            # records the reason, and the operator sees it in the log.
            logger.warning('outbound_send_failed code=%s uncertain=%s correlation=%s',
                           error.code, error.uncertain, claimed['id'])
        return 'accepted' if receipt else 'send_failed'

    async def _process_horizontal(self, event, *, t0_ms, t1_ms):
        # Reject wrong receivers before persistence/identity, including groups.
        if (event.provider != self.binding.provider or event.channel != 'whatsapp'
                or event.recipients != (self.binding.receiver_context,)):
            return 'ignored'
        timings = {'t0_ms': t0_ms, 't1_ms': t1_ms}
        async with transaction(self.pool) as conn:
            claimed = await self.repository.claim(conn, self.binding, event, timings, **({'durable': True} if self.durable else {}))
        if self.durable:
            return 'queued' if claimed else 'duplicate'
        if not claimed:
            return await self.recover_delivery(event)
        # The durable claim is an execution fence. Crash before result commit
        # leaves execution_uncertain; never replay a possibly mutating handler.
        result = await self.dispatcher.dispatch(
            event, channel_id=self.binding.channel_id,
            conversation_id=claimed['thread_id'], correlation_id=claimed['id'])
        # The provider rejects a body longer than its limit: the guard keeps the
        # answer deliverable and records what was accredited but not delivered.
        decision = guard_outbound(result.text)
        async with transaction(self.pool) as conn:
            await self.repository.complete_dispatch(conn, self.binding, claimed, result)
            outbound_id = await self.repository.intent(
                conn, self.binding, claimed, event, decision.text, timings)
        return await self._send_horizontal(outbound_id, event.sender, decision.text, timings)

    async def recover_delivery(self, event, *, retry=False):
        """Resume durable intents only; known failed sends require operator retry.

        No intent means duplicate/execution uncertain, not permission to execute.
        Sending/unknown outcomes require provider reconciliation, not replay.
        """
        if (self.binding.environment is None or event.provider != self.binding.provider
                or event.metadata.get('provider_instance') != self.binding.provider_instance
                or event.recipients != (self.binding.receiver_context,)):
            return 'ignored'
        if self.durable:
            if not retry:
                return 'duplicate'  # recovery belongs to the ordered worker
            from .durable import DurableWorker
            worker = DurableWorker(self)
            async with transaction(self.pool) as conn:
                event_id = await worker.repository.find_id(conn, self.binding, event.external_message_id)
            if event_id is None:
                return 'execution_uncertain'
            return 'retry_reviewed' if await worker.retry(event_id) else 'duplicate'
        async with transaction(self.pool) as conn:
            intent = await self.repository.recoverable_intent(conn, self.binding, event)
        if intent is None:
            return 'execution_uncertain'
        if intent['contact_identity'] != event.sender:
            return 'ignored'
        return await self._send_horizontal(str(intent['id']), intent['contact_identity'],
                                          intent['payload_jsonb']['text'],
                                          intent['payload_jsonb']['timings'], retry=retry)

    async def _check_transport_binding(self, conn):
        check = getattr(self.sender, 'check_transport_binding', None)
        if callable(check):
            await check(conn, self.binding)

    async def _sender_for_intent(self, outbound_id, destination, text):
        # Preserve existing sender port consumers. Evolution explicitly opts in;
        # a V1 rejection/missing response never falls back to send_text.
        send_intent = getattr(self.sender, 'send_intent', None)
        if not callable(send_intent):
            return self.sender.send_text, {}
        async with transaction(self.pool) as conn:
            identity = await self.repository.send_identity(conn, self.binding, outbound_id)
        extra = {}
        prepare = getattr(self.sender, 'prepare_transport', None)
        if callable(prepare):
            extra = await prepare(pool=self.pool, binding=self.binding, identity=identity,
                                  destination=destination, text=text)
        return send_intent, {'identity': identity, **extra}

    async def _send_horizontal(self, outbound_id, destination, text, timings, *, retry=False):
        async with transaction(self.pool) as conn:
            await self._check_transport_binding(conn)
            started = await self.repository.begin_send(conn, self.binding, outbound_id, retry=retry)
        if not started:
            return 'duplicate'
        send, identity_args = await self._sender_for_intent(outbound_id, destination, text)
        receipt, error = None, None
        timings['t4_ms'] = epoch_ms()
        try:
            receipt = await asyncio.to_thread(send, destination=destination, text=text, **identity_args)
            if receipt is None:
                error = MessagingSendError('provider_empty_receipt', uncertain=True)
        except MessagingSendError as exc:
            error = exc
        except Exception:
            error = MessagingSendError('provider_unexpected_error', uncertain=True)
        timings['t5_ms'] = epoch_ms()
        async with transaction(self.pool) as conn:
            if receipt:
                await self.repository.lock_receipt(conn, self.binding.provider_id,
                                                   self.binding.storage_instance, receipt.external_message_id)
            await self.repository.finish(conn, outbound_id, receipt=receipt, error=error, timings=timings)
        if error is not None:
            # A failed delivery is never silent: the durable intent already
            # records the reason, and the operator sees it in the log.
            logger.warning('outbound_send_failed code=%s uncertain=%s correlation=%s',
                           error.code, error.uncertain, outbound_id)
        return 'accepted' if receipt else 'send_failed'

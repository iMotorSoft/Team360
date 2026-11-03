"""Team360 owns conversation, DEV authorization and the fixed responder."""
from __future__ import annotations

import asyncio
import re
import time

from modules.db.transaction import transaction
from .domain.delivery import DeliveryEvent, MessagingSendError
from .domain.messages import InboundMessage
from .domain.whatsapp import WhatsAppMessageSenderPort
from .repository import MessagingRepository, ChannelBinding


def epoch_ms():
    return time.time_ns() / 1_000_000


def fixed_response(text: str) -> str | None:
    match = re.fullmatch(r'team360 ping (0[1-9]|1[0-9]|20)', text)
    return f'TEAM360 PONG {match[1]}' if match else None


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Fixed response conversation ownership]]
class MessagingService:
    def __init__(self, *, pool, repository: MessagingRepository, binding: ChannelBinding,
                 sender: WhatsAppMessageSenderPort, authorized_sender: str,
                 telchi_capability=None, tenant=None):
        self.pool, self.repository, self.binding = pool, repository, binding
        self.sender, self.authorized_sender = sender, authorized_sender
        self.telchi_capability, self.tenant = telchi_capability, tenant

    async def process(self, event: InboundMessage | DeliveryEvent, *, t0_ms, t1_ms):
        instance = (event.provider_instance if isinstance(event, DeliveryEvent)
                    else event.metadata.get('provider_instance'))
        if instance != self.binding.provider_instance:
            return 'ignored'
        if isinstance(event, DeliveryEvent):
            async with transaction(self.pool) as conn:
                await self.repository.delivery(conn, self.binding, event)
            return 'status'
        if event.sender != self.authorized_sender:
            return 'unauthorized'
        timings = {'t0_ms': t0_ms, 't1_ms': t1_ms}
        async with transaction(self.pool) as conn:
            claimed = await self.repository.claim(conn, self.binding, event, timings)
        if not claimed:
            return 'duplicate'
        timings['t2_ms'] = epoch_ms()  # after the inbound commit, not after execute
        reply = fixed_response(event.text_body)
        audit = None
        if self.telchi_capability is not None and self.tenant == 'telchi':
            from .telchi_sql import is_telchi_trigger
            if is_telchi_trigger(event.text_body):
                audit = {'tenant': self.tenant, 'dev_only': True, 'trigger': 'hola',
                         'capability': self.telchi_capability.capability,
                         'query_hash': self.telchi_capability.query_hash, 'status': 'started',
                         'timings': {'t0_ms': t0_ms, 't1_ms': timings['t2_ms']}}
                # Persist execution intent after durable inbound claim and before SQL.
                async with transaction(self.pool) as conn:
                    await self.repository.record_sql_gate(conn, self.binding, claimed, audit)
                audit['capability_started_ms'] = epoch_ms()
                reply, result = await self.telchi_capability.execute()
                # Adapter includes formatting. Exact inner SQL timestamps live in result.
                audit['timings']['t4_ms'] = epoch_ms()
                audit.update(result)
                if result.get('result'):
                    audit['timings']['t2_ms'] = result['result']['sql_started_ms']
                    audit['timings']['t3_ms'] = result['result']['sql_finished_ms']
                async with transaction(self.pool) as conn:
                    await self.repository.record_sql_gate(conn, self.binding, claimed, audit)
                timings['sql_gate'] = audit
        timings['t3_ms'] = epoch_ms()
        if reply is None:
            return 'received'
        async with transaction(self.pool) as conn:
            outbound_id = await self.repository.intent(conn, self.binding, claimed, event, reply, timings)
        # Durable intent precedes I/O. Never retry it on duplicates or restart.
        def dispatch():
            timings['t4_ms'] = epoch_ms()
            if audit is not None:
                audit['timings']['t5_ms'] = timings['t4_ms']
            return self.sender.send_text(destination=event.sender, text=reply)
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
                                                   self.binding.provider_instance, receipt.external_message_id)
            await self.repository.finish(conn, outbound_id, receipt=receipt, error=error, timings=timings)
            if audit is not None:
                await self.repository.record_sql_gate(conn, self.binding, claimed, audit)
        return 'accepted' if receipt else 'send_failed'

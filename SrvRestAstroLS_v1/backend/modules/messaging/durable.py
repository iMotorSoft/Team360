"""Opt-in worker for replay-safe transactional handlers, backed by PG inbox.

A supervisor may die at any point: a transaction-scoped advisory lock is released
by PG; the persisted inbox/result/intent remain. No HTTP task owns the work.
Unknown provider acceptance is NEVER automatically retried.
"""
import asyncio
import logging

from modules.db.transaction import transaction
from .domain.messages import InboundMessage
from .delivery_guard import guard_outbound
from .durable_repository import DurableInboxRepository

log = logging.getLogger(__name__)


class DurableWorker:
    def __init__(self, service, *, repository=None, poll_seconds=2):
        if not service.durable or service.binding.environment is None:
            raise ValueError('Durable horizontal service required')
        self.service = service
        self.repository = repository or DurableInboxRepository()
        self.poll_seconds = max(1, poll_seconds)
        self.stopped = asyncio.Event()

    async def run(self):
        while not self.stopped.is_set():
            try:
                worked = await self.tick()
            except Exception:
                # No payload, identity or exception text in the log. Durable
                # rows remain eligible; back off on persistence/transport errors.
                log.warning('durable_worker_iteration_failed')
                worked = False
            if not worked:
                try:
                    await asyncio.wait_for(self.stopped.wait(), self.poll_seconds)
                except TimeoutError:
                    pass

    async def tick(self):
        s, repo = self.service, self.repository
        async with transaction(s.pool) as conn:
            candidates = await repo.candidates(conn, s.binding)
        for candidate in candidates:
            # This connection holds ONLY the advisory lock, never a row lock.
            # Handler transactions can commit independently. The connection must
            # remain live until the handler finishes; cancellation rolls it back.
            async with transaction(s.pool) as lock_conn:
                if not await repo.lock(lock_conn, s.binding, candidate['thread_id']):
                    continue
                # Re-read the oldest job after the lock: another worker may have
                # completed it after our initial selection.
                current = await repo.candidates(lock_conn, s.binding)
                if candidate not in current:
                    continue
                await self.process(candidate['id'])
                return True
        return False

    async def state(self, event_id, state, **kwargs):
        async with transaction(self.service.pool) as conn:
            await self.repository.state(conn, self.service.binding, event_id, state, **kwargs)

    async def retry(self, event_id):
        """Explicit operator retry of a confirmed failure, with current RBAC.

        Unknown acceptance is not retryable here; preserve it for reconciliation.
        """
        s = self.service
        async with transaction(s.pool) as conn:
            row = await self.repository.load(conn, s.binding, event_id)
            if row is None or not await self.repository.lock(conn, s.binding, row['thread_id']):
                return False
            await self.process(event_id, retry=True)
            return True

    async def process(self, event_id, *, retry=False):
        s, repo = self.service, self.repository
        async with transaction(s.pool) as conn:
            row = await repo.load(conn, s.binding, event_id)
        p = row['payload_jsonb']
        message = InboundMessage(provider=p['provider'], channel=p['channel'], sender=p['sender'],
            recipients=tuple(p['recipients']), external_message_id=row['provider_message_id'],
            external_thread_id=row['thread_id'], subject='',
            text_body=p['text'], received_at=row['occurred_at_utc'], metadata=p['metadata'])
        async with transaction(s.pool) as conn:
            intent = await s.repository.recoverable_intent(conn, s.binding, message)
        if intent and intent['status'] == 'completed':
            await self.state(event_id, 'OUTBOUND_ACCEPTED')
            return
        confirmed_retry = bool(retry and intent and intent['status'] == 'failed'
                               and intent['transport_status'] == 'failed')
        if intent and intent['payload_jsonb']['initial_result'] != 'dispatch_intent' and not confirmed_retry:
            # Includes sending/unknown: operator/provider reconciliation is needed.
            await self.state(event_id, 'FAILED_FINAL', error='outbound_reconciliation_required')
            return
        await self.state(event_id, 'RUNNING', attempt=True)
        # Telchi's transaction commits result+audit+context together. On replay,
        # its cached path revalidates identity and operation-specific live grants.
        result = await s.dispatcher.dispatch(message, channel_id=s.binding.channel_id,
            conversation_id=row['thread_id'], correlation_id=event_id)
        if result.classification == 'ERROR' and intent is None:
            async with transaction(s.pool) as conn:
                saved = await repo.load(conn, s.binding, event_id)
            if (not saved['payload_jsonb'].get('telchi_assistant_v1')
                    and p['durable_job'].get('attempts', 0) < 2):
                # No committed business result: retry the durable question, not
                # an in-memory task. Later turns stay behind this turn's fence.
                await self.state(event_id, 'FAILED_RETRYABLE', error='dispatch_uncommitted')
                return
        if intent and result.classification in {'DENIED', 'ERROR'}:
            async with transaction(s.pool) as conn:
                await repo.cancel_outbound(conn, s.binding, str(intent['id']))
            await self.state(event_id, 'CANCELED', error='delivery_authorization_unverified')
            return
        text = guard_outbound(result.text).text
        if intent and text != intent['payload_jsonb']['text']:
            await self.state(event_id, 'CANCELED', error='prepared_result_changed')
            return
        if intent is None:
            claimed = {'id': event_id, 'thread_id': row['thread_id']}
            async with transaction(s.pool) as conn:
                await s.repository.complete_dispatch(conn, s.binding, claimed, result)
                outbound_id = await s.repository.intent(conn, s.binding, claimed, message, text, p['timings'])
                await repo.state(conn, s.binding, event_id, 'OUTBOUND_PENDING')
        else:
            outbound_id = str(intent['id'])
        # Re-enter the replay-safe cached handler after preparation, immediately
        # before external I/O, to revalidate revoked business grants/identity.
        checked = result
        if result.classification not in {'DENIED', 'ERROR'}:
            checked = await s.dispatcher.dispatch(message, channel_id=s.binding.channel_id,
                conversation_id=row['thread_id'], correlation_id=event_id)
        if checked != result:
            async with transaction(s.pool) as conn:
                await repo.cancel_outbound(conn, s.binding, outbound_id)
            await self.state(event_id, 'CANCELED', error='delivery_authorization_changed')
            return
        outcome = await s._send_horizontal(outbound_id, message.sender, text, p['timings'],
                                           **({'retry': True} if confirmed_retry else {}))
        await self.state(event_id, 'OUTBOUND_ACCEPTED' if outcome == 'accepted' else 'FAILED_FINAL',
                         error=None if outcome == 'accepted' else 'outbound_reconciliation_required')

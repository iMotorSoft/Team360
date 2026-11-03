"""Disposable process worker. Synthetic Evolution wire fixture, NOT Evolution proof."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import httpx
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from modules.db.transaction import transaction
from modules.messaging.domain.delivery import DeliveryEvent
from modules.messaging.providers.evolution.config import EvolutionConfig
from modules.messaging.providers.evolution.provider import EvolutionProvider
from modules.messaging.repository import ChannelBinding, MessagingRepository
from modules.messaging.service import MessagingService


async def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    mode = sys.argv[2]
    binding = ChannelBinding(**config['binding'])
    async with AsyncConnectionPool(config['dsn'], min_size=1, max_size=3,
                                   kwargs={'row_factory': dict_row}, open=False) as pool:
        await pool.wait()
        loop = asyncio.get_running_loop()
        async def callback(message_id):
            async with transaction(pool) as conn:
                await MessagingRepository().delivery(conn, binding, DeliveryEvent(
                    'evolution', binding.provider_instance, message_id, 'delivered',
                    datetime.now(timezone.utc)))

        def wire(request):
            # An fsynced fixture counter survives child termination.
            with open(config['calls'], 'a') as handle:
                handle.write(json.dumps(json.loads(request.content)['team360_egress']) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            if mode == 'during_io':
                os._exit(72)
            if mode == 'timeout':
                raise httpx.ReadTimeout('synthetic fixture', request=request)
            body = json.loads(request.content)
            evidence = {**body['team360_egress'], 'acceptance': 'ACCEPTED',
                        'provider_message_id': config['meta_id'], 'automatic_retry': False,
                        'durable': True, 'discard_secret': 'must-not-persist'}
            if mode == 'rejected':
                evidence.update(acceptance='REJECTED', provider_message_id=None, graph_code=131030)
            elif mode == 'unknown':
                evidence.update(acceptance='UNKNOWN', provider_message_id=None)
            elif mode == 'no_id':
                evidence['provider_message_id'] = None
            if mode == 'early_callback':
                asyncio.run_coroutine_threadsafe(callback(config['meta_id']), loop).result(timeout=5)
            return httpx.Response(500 if mode == 'accepted_http500' else 201,
                                  json={'egress': evidence})

        class Repository(MessagingRepository):
            async def begin_send(self, conn, *args, **kwargs):
                if mode == 'pre_fence_persist_fail':
                    await conn.execute('SELECT 1/0')
                return await super().begin_send(conn, *args, **kwargs)

            async def finish(self, *args, **kwargs):
                if mode == 'after_acceptance':
                    os._exit(73)
                if mode == 'persist_fail':
                    # Real PostgreSQL transaction failure BEFORE finish commits.
                    await args[0].execute('SELECT 1/0')
                return await super().finish(*args, **kwargs)

        class Service(MessagingService):
            async def _sender_for_intent(self, *args):
                value = await super()._sender_for_intent(*args)
                if mode == 'before_io':
                    os._exit(71)
                return value

        service = Service(pool=pool, repository=Repository(), binding=binding,
                          sender=EvolutionProvider(EvolutionConfig('http://fixture.invalid',
                              binding.provider_instance, 'synthetic-key'),
                              transport=httpx.MockTransport(wire)), authorized_sender='15550000001')
        result = await service._send_horizontal(config['outbound_id'], '15550000001', 'synthetic', {})
        print(result, flush=True)


if __name__ == '__main__':
    asyncio.run(main())

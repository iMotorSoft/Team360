"""Opt-in real PG persistence and Messaging→Foundation SQL (no WhatsApp send)."""
import asyncio
from datetime import datetime, timezone
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from modules.messaging.domain.delivery import DeliveryEvent
from modules.messaging.providers.evolution.mapper import normalize_events
from modules.messaging.repository import MessagingRepository
from modules.messaging.service import MessagingService, epoch_ms
from modules.messaging.telchi_sql import TelchiSqlAdapter, ERROR_TEXT
from modules.telchi.datalake.messaging_sales_query import query_fixed_sales, TelchiQueryError

pytestmark = pytest.mark.skipif(os.getenv('TEAM360_MESSAGING_POSTGRES_TEST') != '1', reason='PG opt-in required')


@pytest.mark.parametrize('live_lake', [False, True])
def test_gate_postgres_persistence_dedup_errors_and_foundation(live_lake):
    if live_lake and os.getenv('TEAM360_MESSAGING_TELCHI_SQL_TEST') != '1':
        pytest.skip('real Data Lake opt-in required')
    async def exercise():
        pool = create_pool(get_database_settings(min_size=1, max_size=3))
        await open_pool(pool)
        repo = MessagingRepository()
        suffix = uuid4().hex
        instance, workspace = 'sql-test-'+suffix, 'sql-test-'+suffix
        binding = None
        sent, queries = [], []
        class Sender:
            def send_text(self, **kwargs):
                sent.append(kwargs['text'])
                return SimpleNamespace(external_message_id='test-out-'+str(len(sent)))
        mode = {'value': 'ok'}
        async def query(**kwargs):
            queries.append(mode['value'])
            if mode['value'] not in {'ok','empty'}:
                raise TelchiQueryError(mode['value'])
            if live_lake and mode['value'] == 'ok':
                return await query_fixed_sales(**kwargs)
            return {'rows': [] if mode['value']=='empty' else [{'item_code':'L001','quantity':'123'}],
                    'sql_started_ms':epoch_ms(), 'sql_finished_ms':epoch_ms()}
        try:
            async with transaction(pool) as conn:
                await conn.execute("INSERT INTO core_workspaces(slug,display_name,status) VALUES (%s,'SQL gate test','testing')",(workspace,))
                binding = await repo.provision_dev_channel(conn, workspace_slug=workspace, channel_alias='test',
                    provider='evolution', instance=instance)
            svc = MessagingService(pool=pool, repository=repo, binding=binding, sender=Sender(),
                authorized_sender='15550000001', tenant='telchi', telchi_capability=TelchiSqlAdapter(query))
            def inbound(id, text='hola', sender='15550000001'):
                return normalize_events({'event':'messages.upsert','instance':instance,
                    'data':{'key':{'id':id,'remoteJid':sender+'@s.whatsapp.net','fromMe':False},
                            'message':{'conversation':text}}}, instance=instance, recipient='test',
                    received_at=datetime.now(timezone.utc))[0]
            async def process(event):
                return await svc.process(event,t0_ms=epoch_ms(),t1_ms=epoch_ms())
            assert await process(inbound('unauthorized',sender='15550000002')) == 'unauthorized'
            assert not queries and not sent
            assert await process(inbound('other','hola ventas')) == 'received'
            results = await asyncio.gather(process(inbound('one')),process(inbound('one')))
            assert sorted(results) == ['accepted','duplicate']
            assert len(queries) == len(sent) == 1
            assert await process(inbound('one')) == 'duplicate'
            assert len(queries) == 1
            await process(DeliveryEvent('evolution',instance,'test-out-1','delivered',datetime.now(timezone.utc)))
            await process(DeliveryEvent('evolution',instance,'test-out-1','read',datetime.now(timezone.utc)))
            async with transaction(pool) as conn:
                rows = await repo.evidence(conn,binding)
                metadata = await (await conn.execute('SELECT metadata_jsonb FROM message_threads WHERE channel_id=%s',(binding.channel_id,))).fetchone()
            assert metadata['metadata_jsonb']['dev_sql_tenant'] == 'telchi'
            inbound_row = next(r for r in rows if r['provider_message_id']=='one')
            audit = inbound_row['payload_jsonb']['sql_gate']
            assert audit['tenant']=='telchi' and audit['status']=='succeeded'
            assert audit['timings']['t6_ms'] >= audit['timings']['t5_ms']
            if live_lake:
                assert audit['result']['read_only'] and not audit['result']['sap_accessed']
                assert audit['result']['foundation_publication_id'].startswith('foundation_')
            out = next(r for r in rows if r['provider_message_id']=='test-out-1' and r['event_type']=='message')
            assert out['transport_status']=='read' and out['payload_jsonb']['t6_ms'] is not None
            assert str(out['correlation_id']) == str(inbound_row['id'])
            assert all(r['thread_id']==inbound_row['thread_id'] for r in rows)
            for value in ['empty','datalake_timeout','datalake_connection_error','datalake_query_error']:
                mode['value'] = value
                assert await process(inbound(value))=='accepted'
                assert await process(inbound(value))=='duplicate'
                if value=='empty': assert 'Sin resultados' in sent[-1]
                else: assert sent[-1]==ERROR_TEXT
            assert len(queries)==len(sent)==5
        finally:
            if binding:
                async with transaction(pool) as conn:
                    await conn.execute('DELETE FROM message_events WHERE workspace_id=%s',(binding.workspace_id,))
                    await conn.execute('DELETE FROM message_threads WHERE workspace_id=%s',(binding.workspace_id,))
                    await conn.execute('DELETE FROM communication_channels WHERE workspace_id=%s',(binding.workspace_id,))
                    await conn.execute('DELETE FROM core_workspaces WHERE id=%s',(binding.workspace_id,))
            await close_pool(pool)
    asyncio.run(exercise())

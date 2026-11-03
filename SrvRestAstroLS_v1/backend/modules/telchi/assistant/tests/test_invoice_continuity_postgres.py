"""Committed JSONB document and line pointers on temporary PG tables only."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import os
import pytest
from psycopg.types.json import Jsonb
from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.telchi.assistant.handler import PostgresConversationStore
from .test_assistant import event, proposal
from .test_result_references import select
from .test_invoice_continuity import prepare, document


@pytest.mark.skipif(os.getenv('TEAM360_RESULT_REFERENCE_POSTGRES_TEST') != '1', reason='PG opt-in required')
def test_document_and_line_survive_committed_turns(monkeypatch):
    async def exercise():
        pool = create_pool(get_database_settings(min_size=1, max_size=1))
        await open_pool(pool)
        try:
            async with pool.connection() as conn:
                await conn.execute('CREATE TEMP TABLE message_threads(id text,channel_id text,workspace_id text,metadata_jsonb jsonb)')
                await conn.execute('CREATE TEMP TABLE message_events(id text,thread_id text,channel_id text,workspace_id text,direction text,event_type text,payload_jsonb jsonb)')
                await conn.execute("INSERT INTO pg_temp.message_threads VALUES ('conversation','channel','workspace','{}')")
            h, _, llm, calls, _, c, line_calls = prepare(monkeypatch, [
                proposal({'/metric':'sales.latest_documents'}, intent='NEW_QUERY'), select(1, result_id='turn-1'),
                document(), select(2, None, 'turn-3'), document('SELECT_DOCUMENT'),
                select(None, 'quantity', 'turn-3')])
            @asynccontextmanager
            async def tx(_):
                async with pool.connection() as conn:
                    yield conn
            monkeypatch.setattr('modules.telchi.assistant.handler.transaction', tx)
            for n in range(1, 7):
                ident = f'turn-{n}'
                async with pool.connection() as conn:
                    await conn.execute("INSERT INTO pg_temp.message_events VALUES (%s,'conversation','channel','workspace','inbound','message',%s)", (ident, Jsonb({'environment':'dev'})))
                h.store = PostgresConversationStore(pool)
                response = await h.handle(event(), replace(c, correlation_id=ident))
                assert response.classification == 'DIRECT_AVAILABLE', response.text
            assert '11' in response.text and len(calls) == len(line_calls) == 1
            async with pool.connection() as conn:
                row = await (await conn.execute('SELECT metadata_jsonb FROM pg_temp.message_threads')).fetchone()
                saved = row['metadata_jsonb']['telchi_assistant_v1']
                assert saved['document_reference'] == dict(result_id='turn-1', selected_ordinal=1)
                assert saved['result_reference'] == dict(result_id='turn-3', selected_ordinal=2)
                # A separate conversation must not retrieve this document audit.
                ctx = replace(c, conversation_id='different')
                turn = dict(owner=saved['owner'], history={}, result_reference=saved['document_reference'])
                assert await h.store.repository.load_result(conn, ctx, turn) is None
        finally:
            await close_pool(pool)
    asyncio.run(exercise())

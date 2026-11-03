"""Real repository commits on session-local PG tables; no operational rows touched."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import os

import pytest
from psycopg.types.json import Jsonb

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from modules.telchi.assistant.handler import PostgresConversationStore
from .test_result_references import persistent_handler, select
from .test_assistant import event, proposal


@pytest.mark.skipif(os.getenv('TEAM360_RESULT_REFERENCE_POSTGRES_TEST') != '1', reason='PG opt-in required')
def test_real_pg_repository_multiturn(monkeypatch):
    async def exercise():
        pool = create_pool(get_database_settings(min_size=1, max_size=1))
        await open_pool(pool)
        try:
            # One session, temp relations shadow public names, survive each commit.
            async with pool.connection() as conn:
                await conn.execute('''CREATE TEMP TABLE message_threads
                    (id text, channel_id text, workspace_id text, metadata_jsonb jsonb)''')
                await conn.execute('''CREATE TEMP TABLE message_events
                    (id text, thread_id text, channel_id text, workspace_id text,
                     direction text, event_type text, payload_jsonb jsonb)''')
                await conn.execute("INSERT INTO pg_temp.message_threads VALUES ('conversation','channel','workspace','{}')")
            handler, _, llm, calls, checks, c = persistent_handler(monkeypatch, [
                proposal({'/metric': 'sales.latest_documents', '/limit': 5}, intent='NEW_QUERY'),
                proposal({'/limit': 3}), select(), select(None)])
            # Use the pinned session, but independent committed transactions per turn.
            @asynccontextmanager
            async def tx(_):
                async with pool.connection() as conn:
                    yield conn
            monkeypatch.setattr('modules.telchi.assistant.handler.transaction', tx)
            for n in range(1, 5):
                ident = f'turn-{n}'
                async with pool.connection() as conn:
                    await conn.execute('''INSERT INTO pg_temp.message_events VALUES
                        (%s,'conversation','channel','workspace','inbound','message',%s)''',
                        (ident, Jsonb({'environment': 'dev'})))
                handler.store = PostgresConversationStore(pool)
                response = await handler.handle(event(), replace(c, correlation_id=ident))
                assert response.classification == 'DIRECT_AVAILABLE', response.text
                if n >= 3:
                    assert '260192727' in response.text
            assert len(calls) == 2
            async with pool.connection() as conn:
                row = await (await conn.execute("SELECT metadata_jsonb FROM pg_temp.message_threads")).fetchone()
                assert row['metadata_jsonb']['telchi_assistant_v1']['result_reference'] == dict(
                    result_id='turn-2', selected_ordinal=2)
                rows = await (await conn.execute('''SELECT payload_jsonb FROM pg_temp.message_events
                    WHERE id IN ('turn-3','turn-4')''')).fetchall()
                assert all(r['payload_jsonb']['telchi_assistant_v1']['capability_calls'] == 0 for r in rows)
                # Oversized newest result must NOT silently fall back to the older
                # five-row list when importing legacy state without a pointer.
                await conn.execute('''UPDATE pg_temp.message_events SET payload_jsonb=jsonb_set(
                    payload_jsonb,'{telchi_assistant_v1,padding}',to_jsonb(repeat('x',70000))) WHERE id='turn-2' ''')
                await conn.execute('''UPDATE pg_temp.message_threads SET metadata_jsonb=
                    metadata_jsonb #- '{telchi_assistant_v1,result_reference}' ''')
                await conn.execute('''INSERT INTO pg_temp.message_events VALUES
                    ('turn-5','conversation','channel','workspace','inbound','message',%s)''',
                    (Jsonb({'environment': 'dev'}),))
            llm.proposals = iter([select()])
            response = await handler.handle(event(), replace(c, correlation_id='turn-5'))
            assert response.classification == 'NEEDS_CLARIFICATION'
            assert 'result_context' not in llm.calls[-1] and len(calls) == 2
        finally:
            # Closing the only session drops its temporary data automatically.
            await close_pool(pool)
    asyncio.run(exercise())

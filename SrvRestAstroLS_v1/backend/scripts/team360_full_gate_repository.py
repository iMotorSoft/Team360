"""Read-only, bounded SQL probes owned by the Full Gate (no migrations/writes)."""
from __future__ import annotations


async def inspect_database(conn):
    async with conn.cursor() as cur:
        await cur.execute("select current_database() as database, current_setting('server_version') as version, current_setting('transaction_read_only') as read_only")
        identity = await cur.fetchone()
        assert identity['database'] == 'team360' and identity['read_only'] == 'on'
        tables = ('flow_requests', 'flow_operational_settings', 'flow_scheduler_state',
                  'sales_diagnosis_conversation_states', 'embed_clients', 'core_permissions',
                  'message_threads', 'message_events')
        missing = []
        for table in tables:
            await cur.execute('select to_regclass(%s) as name', (table,))
            if not (await cur.fetchone())['name']:
                missing.append(table)
        assert not missing, f'Missing tables: {missing}'
        await cur.execute('select automation_enabled from flow_operational_settings where id=1')
        settings = await cur.fetchone()
        assert settings is not None, 'Missing Flow settings row'
        indexes = ('uq_messaging_transport_thread', 'uq_messaging_transport_message',
                   'uq_messaging_transport_reply', 'uq_messaging_transport_status')
        for index in indexes:
            await cur.execute('select to_regclass(%s) as name', (index,))
            assert (await cur.fetchone())['name'], f'Missing index: {index}'
        return {**identity, 'tables_present': list(tables), 'automation_enabled': settings['automation_enabled']}


async def cleanup_test_sessions(dsn, sessions):
    """Delete ONLY this invocation's UUID sessions, following the official state smoke.

    Never prefix-delete other runs; no DDL, corpus or tenant mutation.
    """
    import re
    from psycopg import AsyncConnection
    assert sessions and all(re.fullmatch(r'full_gate_[0-9a-f]{32}', sid) for sid in sessions)
    try:
        async with await AsyncConnection.connect(dsn, connect_timeout=5) as conn:
            async with conn.cursor() as cur:
                await cur.execute('DELETE FROM sales_diagnosis_conversation_states WHERE session_id = ANY(%s)', (sessions,))
                deleted = cur.rowcount
                await cur.execute('SELECT count(*) FROM sales_diagnosis_conversation_states WHERE session_id = ANY(%s)', (sessions,))
                remaining = (await cur.fetchone())[0]
        return {'status': 'PASS' if remaining == 0 else 'FAIL', 'deleted': deleted, 'remaining': remaining, 'sessions': sessions}
    except Exception as exc:
        return {'status': 'FAIL', 'error_class': type(exc).__name__, 'sessions_requiring_cleanup': sessions}

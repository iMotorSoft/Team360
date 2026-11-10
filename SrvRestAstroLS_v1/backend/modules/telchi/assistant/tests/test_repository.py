"""Real repository SQL against a controlled PG port; no DDL or operational writes."""
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant.repository import ConversationRepository
from modules.telchi.assistant.handler import PostgresConversationStore
from .test_assistant import context, run, setup, event, proposal, plan


class Connection:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.calls = []
    async def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self
    async def fetchone(self):
        return next(self.rows)


@run
async def test_sql_load_save_namespace_and_scope():
    c = context()
    conn = Connection([{'metadata_jsonb': {'other_module': 'untouched'}}, {'payload_jsonb': {'environment': 'dev'}}])
    repo = ConversationRepository()
    turn = await repo.load(conn, c)
    assert turn['state']['metric'] is None and not turn['history']
    # Serialize conversation state without blocking inbound FK KEY SHARE locks.
    assert 'message_threads' in conn.calls[2][0] and 'FOR NO KEY UPDATE' in conn.calls[2][0]
    assert 'message_events' in conn.calls[3][0] and 'FOR UPDATE' in conn.calls[3][0]
    assert conn.calls[2][1] == ('conversation', 'channel', 'workspace')
    assert conn.calls[3][1] == ('turn-1', 'conversation', 'channel', 'workspace')
    audit = dict(confirmed_state=plan(), owner=turn['owner'], response_prepared={'text': 'fixture', 'classification': 'DIRECT_AVAILABLE'})
    await repo.save(conn, c, turn, audit)
    assert len(conn.calls) == 6
    for sql, params in conn.calls[-2:]:
        assert ' || %s' in sql and 'telchi_assistant_v1' in params[0].obj
        assert 'CREATE' not in sql and 'ALTER' not in sql
    saved = conn.calls[-2][1][0].obj['telchi_assistant_v1']
    assert saved['history_order'] == ['turn-1'] and saved['state'] == plan()
    next_conn = Connection([{'metadata_jsonb': {'telchi_assistant_v1': saved}},
                            {'payload_jsonb': {'environment': 'dev', 'telchi_assistant_v1': audit}}])
    reloaded = await repo.load(next_conn, c)
    assert reloaded['state'] == plan() and reloaded['cached'] == audit


@pytest.mark.parametrize('case', ['missing_thread', 'missing_event', 'environment', 'user', 'tenant', 'workspace'])
@run
async def test_repository_rejects_unowned_state(case):
    c = context()
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    if case in {'user', 'tenant', 'workspace'}:
        owner[{'user': 4, 'tenant': 1, 'workspace': 2}[case]] = 'other'
    saved = dict(owner=owner, state=plan(), history={}, history_order=[])
    thread = None if case == 'missing_thread' else {'metadata_jsonb': {'telchi_assistant_v1': saved}}
    row = None if case == 'missing_event' else {'payload_jsonb': {'environment': 'pro' if case == 'environment' else 'dev'}}
    with pytest.raises(ValueError):
        await ConversationRepository().load(Connection([thread, row]), c)


@run
async def test_state_history_has_explicit_order_not_jsonb_key_order():
    c = context()
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    saved = dict(owner=owner, state=plan(), history={'a': plan(), 'z': plan()}, history_order=['z', 'a'])
    turn = await ConversationRepository().load(Connection([{'metadata_jsonb': {'telchi_assistant_v1': saved}},
                                                           {'payload_jsonb': {'environment': 'dev'}}]), c)
    assert list(turn['history']) == ['z', 'a']


@run
async def test_pg_store_commit_precedes_return(monkeypatch):
    from contextlib import asynccontextmanager
    log = []
    @asynccontextmanager
    async def tx(pool):
        log.append('begin')
        try:
            yield object()
        except Exception:
            log.append('rollback')
            raise
        else:
            log.append('commit')
    class Repository:
        async def load(self, conn, c):
            return dict(state=deepcopy(plan()), history={}, owner=[], cached=None, conn=conn)
        async def save(self, conn, c, turn, audit):
            log.append('save')
    monkeypatch.setattr('modules.telchi.assistant.handler.transaction', tx)
    handler, _, _, calls = setup([proposal()])
    async def allowed(*args, **kwargs): return True
    handler.authorization.allowed = allowed
    sentinel = object()
    def pool_provider():
        log.append('resolve_existing_pool')
        return sentinel
    handler.store = PostgresConversationStore(pool_provider, Repository())
    result = await handler.handle(event(), context())
    log.append('returned')
    assert result.classification == 'DIRECT_AVAILABLE'
    assert log == ['resolve_existing_pool', 'begin', 'save', 'commit', 'returned'] and len(calls) == 1

"""Reference contracts and actual repository serialization (no provider/transport)."""
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import result_references as refs
from modules.telchi.assistant.handler import PostgresConversationStore, TelchiHandler
from modules.telchi.assistant.repository import ConversationRepository
from modules.telchi.assistant.state_engine import EMPTY
from .test_assistant import context, event, run, setup, proposal

PERMISSION = 'telchi.sales.latest_documents.read.v1'


def document_result(count=3):
    return dict(capability='sales.latest_documents.v1',
        source=dict(publication_id='accredited-publication', snapshot_id=7, updated_at='2026-10-18T00:00:00Z'),
        rows=[dict(doc_date='2026-10-17', doc_entry=str(900-i), doc_num=num)
              for i, num in enumerate(['260192728', '260192727', '260192726', '260192725', '260192724'][:count])])


def select(ordinal=2, field='doc_num', result_id='turn-2'):
    return dict(intent='RESULT_REFERENCE', action='SELECT_RESULT',
                result_reference=dict(result_id=result_id, ordinal=ordinal, field=field), clarification=None)


class DatabasePort:
    """SQL port preserving only actual Jsonb writes from ConversationRepository."""
    def __init__(self):
        self.thread = {}
        self.events = {}
        self.calls = []
        self.row = None

    async def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if 'SELECT metadata_jsonb' in sql:
            self.row = dict(metadata_jsonb=deepcopy(self.thread))
        elif 'SELECT payload_jsonb' in sql:
            self.row = dict(payload_jsonb=deepcopy(self.events.get(params[0], {'environment': 'dev'})))
        elif 'AS result_id' in sql:
            ids = params[4]
            candidates = [(ident, self.events.get(ident, {}).get('telchi_assistant_v1')) for ident in reversed(ids)]
            self.row = next((dict(result_id=ident, audit=deepcopy(audit)) for ident, audit in candidates
                             if audit and audit.get('execution_status') == 'executed'), None)
        elif 'UPDATE message_threads' in sql:
            self.thread.update(deepcopy(params[0].obj))
        elif 'UPDATE message_events' in sql:
            self.events.setdefault(params[1], {'environment': 'dev'}).update(deepcopy(params[0].obj))
        return self

    async def fetchone(self):
        return self.row


def persistent_handler(monkeypatch, proposals):
    db = DatabasePort()
    @asynccontextmanager
    async def tx(pool):
        yield db
    monkeypatch.setattr('modules.telchi.assistant.handler.transaction', tx)
    handler, _, llm, _ = setup(proposals)
    handler.store = PostgresConversationStore(object())
    c = context()
    c = replace(c, sender_identity=replace(c.sender_identity,
                permissions=c.sender_identity.permissions | {PERMISSION}))
    # Authorization fixture: live method is exercised, no real Console grants implied.
    checks = []
    async def allowed(ctx, conn=None, *, required_permission=None):
        checks.append(required_permission)
        return required_permission is None or required_permission in c.sender_identity.permissions
    handler.authorization.allowed = allowed
    calls = []
    async def execute(state):
        calls.append(deepcopy(state))
        return document_result(state.get('limit', 10))
    handler.capabilities.execute = execute
    return handler, db, llm, calls, checks, c


@run
async def test_5_3_second_number_repository_continuity(monkeypatch):
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents', '/limit': 5}, intent='NEW_QUERY'),
        proposal({'/limit': 3}), select(), select(None), select(None, None)])
    texts = ['Mostrame las últimas 5 facturas de venta de Telchi.',
             'De esas cinco facturas, mostrame solamente las tres más recientes.',
             '¿Cuál es el número de factura de la segunda de esas tres?',
             '¿Cuál es su número?', 'Mostrame solamente esa factura']
    for n, text in enumerate(texts, 1):
        # Reconstruct handler/store every turn: no handler-local result memory.
        handler.store = PostgresConversationStore(object(), ConversationRepository())
        response = await handler.handle(event(text), replace(c, correlation_id=f'turn-{n}'))
        assert response.classification == 'DIRECT_AVAILABLE', response.text
        if n >= 3:
            assert '260192727' in response.text and '260192728' not in response.text
            assert 'datos al' in response.text
            audit = db.events[f'turn-{n}']['telchi_assistant_v1']
            assert audit['capability_calls'] == 0 and audit['execution_result'] is None
            assert audit['confirmed_state']['limit'] == 3
            assert audit['result_provenance']['snapshot_id'] == 7
    assert len(calls) == 2 and [s['limit'] for s in calls] == [5, 3]
    assert checks.count(PERMISSION) >= 8
    assert llm.calls[2]['result_context']['row_count'] == 3
    assert llm.calls[3]['result_context']['selected_ordinal'] == 2
    assert '260192727' not in str(llm.calls)  # zero commercial values sent to Luna
    assert db.thread['telchi_assistant_v1']['result_reference'] == dict(result_id='turn-2', selected_ordinal=2)
    assert 'cabecera' in response.text


@pytest.mark.parametrize('ref', [select(0), select(4), select(True), select(2, 'total'),
    select(2, result_id='another-conversation'), select(None),
    dict(select(), state_delta={'set': {'/limit': 2}, 'unset': []}),
    dict(intent='RESULT_REFERENCE', action='ASK', result_reference=None, clarification={'question': '¿Cuál?'})])
@run
async def test_invalid_or_ambiguous_never_calls_foundation(monkeypatch, ref):
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents', '/limit': 3}, intent='NEW_QUERY'), ref])
    await handler.handle(event(), replace(c, correlation_id='turn-2'))
    result = await handler.handle(event(), replace(c, correlation_id='turn-3'))
    assert result.classification == 'NEEDS_CLARIFICATION'
    assert len(calls) == 1


@run
async def test_revoked_operation_not_exposed_or_selected(monkeypatch):
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents', '/limit': 3}, intent='NEW_QUERY'), select()])
    await handler.handle(event(), replace(c, correlation_id='turn-2'))
    async def revoked(ctx, conn=None, *, required_permission=None):
        return required_permission is None
    handler.authorization.allowed = revoked
    result = await handler.handle(event(), replace(c, correlation_id='turn-3'))
    assert result.classification != 'DIRECT_AVAILABLE' and 'result_context' not in llm.calls[-1]
    assert len(calls) == 1


@run
async def test_revocation_during_interpretation_and_cached_selection(monkeypatch):
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents', '/limit': 3}, intent='NEW_QUERY'), select()])
    await handler.handle(event(), replace(c, correlation_id='turn-2'))
    selected = await handler.handle(event(), replace(c, correlation_id='turn-3'))
    assert selected.classification == 'DIRECT_AVAILABLE'
    async def revoked(ctx, conn=None, *, required_permission=None):
        return required_permission is None
    handler.authorization.allowed = revoked
    cached = await handler.handle(event(), replace(c, correlation_id='turn-3'))
    assert cached.classification == 'DENIED' and '260192727' not in cached.text
    # Authorization may be revoked while the LLM request is in flight.
    async def active(*args, **kwargs):
        return True
    handler.authorization.allowed = active
    async def interpret(**kwargs):
        handler.authorization.allowed = revoked
        return select()
    handler.interpreter.interpret = interpret
    result = await handler.handle(event(), replace(c, correlation_id='turn-4'))
    assert result.classification == 'DENIED' and '260192727' not in result.text
    assert len(calls) == 1


@run
async def test_legacy_audit_and_query_bounds(monkeypatch):
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents', '/limit': 3}, intent='NEW_QUERY'), select()])
    await handler.handle(event(), replace(c, correlation_id='turn-2'))
    del db.thread['telchi_assistant_v1']['result_reference']
    response = await handler.handle(event(), replace(c, correlation_id='turn-3'))
    assert '260192727' in response.text and len(calls) == 1
    sql, params = next((s, p) for s, p in db.calls if 'AS result_id' in s)
    assert 'LIMIT 1' in sql and 'octet_length' in sql and 'direction=\'inbound\'' in sql
    assert params[1:4] == ('conversation', 'channel', 'workspace')
    assert params[0] == refs.MAX_BYTES


def test_horizontal_contract_and_exact_presentation_order():
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    audit = dict(owner=owner, execution_status='executed', business_rbac_verified=True,
        response_prepared={'classification': 'DIRECT_AVAILABLE'}, required_permission=PERMISSION,
        confirmed_state=dict(EMPTY, metric='sales.latest_documents'), execution_result=document_result())
    # An arbitrary already-presented order must not be re-sorted by dates/IDs.
    audit['execution_result']['rows'].reverse()
    view = refs.presentation(audit, 'turn-2', owner, 'conversation')
    _, text = refs.resolve(select(1), view, None, owner, 'conversation')
    assert '260192726' in text and '260192728' not in text
    audit['confirmed_state'] = dict(EMPTY, metric='products.search')
    audit['execution_result']['capability'] = 'products.search.v1'
    audit['execution_result']['rows'] = [dict(item_code='SKU-002', description='Producto B', status='active'),
                                         dict(item_code='SKU-001', description='Producto A', status='active')]
    view = refs.presentation(audit, 'turn-2', owner, 'conversation')
    _, text = refs.resolve(select(2, 'item_code'), view, None, owner, 'conversation')
    assert 'SKU-001' in text and 'SKU-002' not in text
    # Capability/state mismatch cannot turn an unrelated audit into a list.
    audit['confirmed_state']['metric'] = 'sales.net_amount'
    assert refs.presentation(audit, 'turn-2', owner, 'conversation') is None


@pytest.mark.parametrize('case', ['user', 'tenant', 'workspace', 'conversation', 'no_result', 'invalid', 'field'])
def test_reference_scope_and_integrity(case):
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    audit = dict(owner=owner, execution_status='executed', business_rbac_verified=True,
                 response_prepared={'classification': 'DIRECT_AVAILABLE'}, required_permission=PERMISSION,
                 confirmed_state=dict(EMPTY, metric='sales.latest_documents', limit=3), execution_result=document_result())
    view = refs.presentation(audit, 'turn-2', owner, 'conversation')
    conversation = 'conversation'
    if case in {'user', 'tenant', 'workspace'}:
        owner = list(owner)
        owner[{'user': 4, 'tenant': 1, 'workspace': 2}[case]] = 'other'
    elif case == 'conversation':
        conversation = 'other'
    elif case == 'no_result':
        view = None
    elif case == 'invalid':
        audit['execution_result']['source'] = {}
        view = refs.presentation(audit, 'turn-2', owner, 'conversation')
        assert view is None
    elif case == 'field':
        view['rows'][1]['doc_num'] = None
    with pytest.raises(ValueError):
        refs.resolve(select(), view, None, owner, conversation)

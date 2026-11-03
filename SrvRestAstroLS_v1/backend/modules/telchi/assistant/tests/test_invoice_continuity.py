"""Document/line focus through the actual repository JSON contract."""
from copy import deepcopy
from dataclasses import replace
import pytest

from modules.telchi.assistant import result_references as refs
from modules.telchi.assistant.capabilities import format_result
from modules.telchi.assistant.state_engine import EMPTY
from modules.telchi.datalake.invoice_lines_query import (
    CAPABILITY, PERMISSION, PUBLICATION, SNAPSHOT, parameters, validate_result)
from .test_assistant import run, event, proposal
from .test_result_references import persistent_handler, document_result, select


def options():
    return dict(source_system='SAP_B1_HANA', document_type='OINV', doc_entry='900',
                doc_num='260192728', doc_date='2026-10-17', publication_id=PUBLICATION, snapshot_id=SNAPSHOT)


def lines(opts=None, count=2):
    opts = opts or options()
    return dict(capability=CAPABILITY, parameters=deepcopy(opts),
        document={k: opts[k] for k in ('source_system', 'document_type', 'doc_entry', 'doc_num', 'doc_date')},
        rows=[dict(line_num=i, item_code=f'fixture-{i}', description=f'Producto {i}', quantity=str(i+10),
                   unit=None, description_source='Foundation reference.products SAP_HANA', source_as_of='2026-09-24')
              for i in range(count)], source=dict(publication_id=PUBLICATION, snapshot_id=SNAPSHOT, updated_at='2026-09-28'),
        read_only=True, sap_accessed=False)


def document(action='READ_LINES', ordinal=None, field=None, result_id='turn-1'):
    return dict(intent='DOCUMENT_REFERENCE', action=action, result_reference=dict(result_id=result_id,
                ordinal=ordinal, field=field), clarification=None)


def prepare(monkeypatch, proposals):
    handler, db, llm, calls, checks, c = persistent_handler(monkeypatch, proposals)
    c = replace(c, sender_identity=replace(c.sender_identity, permissions=c.sender_identity.permissions | {PERMISSION}))
    async def allowed(ctx, conn=None, *, required_permission=None):
        checks.append(required_permission)
        return required_permission is None or required_permission in ctx.sender_identity.permissions
    handler.authorization.allowed = allowed
    async def invoices(state):
        calls.append(deepcopy(state))
        result = document_result(3)
        result['source'].update(publication_id=PUBLICATION, snapshot_id=SNAPSHOT)
        return result
    handler.capabilities.execute = invoices
    line_calls = []
    async def query(opts):
        line_calls.append(opts)
        return lines(opts)
    handler.capabilities.invoice_lines = query
    return handler, db, llm, calls, checks, c, line_calls


@run
async def test_invoice_products_ordinals_and_parent_survive_turns(monkeypatch):
    h, db, llm, calls, checks, c, line_calls = prepare(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents', '/limit': 3}, intent='NEW_QUERY'),
        select(1, result_id='turn-1'), document(),
        select(2, None, 'turn-3'), select(None, 'quantity', 'turn-3'), select(1, None, 'turn-3'),
        document('SELECT_DOCUMENT'), document('SELECT_DOCUMENT', field='doc_date'),
        document('SELECT_DOCUMENT', field='client')])
    for n in range(1, 10):
        response = await h.handle(event(), replace(c, correlation_id=f'turn-{n}'))
        assert response.classification == 'DIRECT_AVAILABLE', response.text
        audit = db.events[f'turn-{n}']['telchi_assistant_v1']
        assert audit['confirmed_state']['metric'] == 'sales.latest_documents'
        if n == 3:
            assert '260192728' in response.text and 'Producto 1' in response.text
            assert '900' not in response.text and 'unidad nativa' in response.text
        if n == 5:
            assert '11' in response.text
        if n >= 7:
            assert '260192728' in response.text
    assert len(calls) == len(line_calls) == 1
    assert line_calls[0]['doc_entry'] == '900'
    assert llm.calls[3]['result_context']['entity_label'] == 'producto'
    assert llm.calls[3]['document_context']['selected_ordinal'] == 1
    assert '260192728' not in str(llm.calls)
    assert db.thread['telchi_assistant_v1']['document_reference'] == dict(result_id='turn-1', selected_ordinal=1)
    assert PERMISSION in checks


@pytest.mark.parametrize('mode', ['ambiguous', 'forged', 'revoked', 'changed_publication', 'other_owner', 'new_query'])
@run
async def test_negative_document_reference_never_executes(monkeypatch, mode):
    h, db, llm, calls, checks, c, line_calls = prepare(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents'}, intent='NEW_QUERY'),
        select(1, result_id='turn-1'), document()])
    await h.handle(event(), replace(c, correlation_id='turn-1'))
    if mode != 'ambiguous':
        await h.handle(event(), replace(c, correlation_id='turn-2'))
    else:
        next(llm.proposals)
    if mode == 'forged':
        llm.proposals = iter([document(result_id='other-thread')])
    elif mode == 'revoked':
        c = replace(c, sender_identity=replace(c.sender_identity, permissions=c.sender_identity.permissions - {PERMISSION}))
    elif mode == 'changed_publication':
        db.events['turn-1']['telchi_assistant_v1']['execution_result']['source']['publication_id'] = 'invalidated'
    elif mode == 'other_owner':
        db.events['turn-1']['telchi_assistant_v1']['owner'][-1] = 'other-user'
    elif mode == 'new_query':
        db.thread['telchi_assistant_v1']['document_reference'] = None
        db.thread['telchi_assistant_v1']['result_reference'] = None
    response = await h.handle(event(), replace(c, correlation_id='turn-3'))
    assert response.classification != 'DIRECT_AVAILABLE'
    assert line_calls == []
    if mode == 'changed_publication':
        assert '260192728' in response.text and 'identificada' in response.text


@run
async def test_invoice_permission_revoked_during_interpretation_and_cached_line(monkeypatch):
    h, db, llm, calls, checks, c, line_calls = prepare(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents'}, intent='NEW_QUERY'),
        select(1, result_id='turn-1'), document(), select(2, 'quantity', 'turn-3')])
    for n in range(1, 5):
        response = await h.handle(event(), replace(c, correlation_id=f'turn-{n}'))
        assert response.classification == 'DIRECT_AVAILABLE'
    original = h.authorization.allowed
    async def revoked(ctx, conn=None, *, required_permission=None):
        return required_permission != PERMISSION and await original(ctx, conn, required_permission=required_permission)
    h.authorization.allowed = revoked
    cached = await h.handle(event(), replace(c, correlation_id='turn-4'))
    assert cached.classification == 'DENIED'
    h.authorization.allowed = original
    async def interpret(**kwargs):
        h.authorization.allowed = revoked
        return document()
    h.interpreter.interpret = interpret
    response = await h.handle(event(), replace(c, correlation_id='turn-5'))
    assert response.classification == 'DENIED' and len(line_calls) == 1


@run
async def test_new_query_clears_document_focus_without_deleting_audits(monkeypatch):
    h, db, llm, calls, checks, c, line_calls = prepare(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents'}, intent='NEW_QUERY'),
        select(1, result_id='turn-1'), document(),
        proposal({'/metric': 'sales.latest_documents', '/limit': 5}, intent='NEW_QUERY'), document()])
    for n in range(1, 6):
        response = await h.handle(event(), replace(c, correlation_id=f'turn-{n}'))
    assert response.classification == 'NEEDS_CLARIFICATION'
    assert len(line_calls) == 1 and len(calls) == 2
    assert db.thread['telchi_assistant_v1']['document_reference'] is None
    assert db.events['turn-3']['telchi_assistant_v1']['execution_result']['capability'] == CAPABILITY


@run
async def test_unavailable_operation_keeps_identified_invoice(monkeypatch):
    h, db, llm, calls, checks, c, line_calls = prepare(monkeypatch, [
        proposal({'/metric': 'sales.latest_documents'}, intent='NEW_QUERY'),
        select(1, result_id='turn-1'), document(), document('SELECT_DOCUMENT')])
    async def unavailable(opts):
        raise ValueError('unverifiable_source')
    h.capabilities.invoice_lines = unavailable
    for n in range(1, 4):
        response = await h.handle(event(), replace(c, correlation_id=f'turn-{n}'))
    assert response.classification == 'DIRECT_UNAVAILABLE'
    assert '260192728' in response.text and 'identificada' in response.text
    response = await h.handle(event(), replace(c, correlation_id='turn-4'))
    assert response.classification == 'DIRECT_AVAILABLE' and '260192728' in response.text
    assert len(calls) == 1


@pytest.mark.parametrize('axis', ['user', 'tenant', 'workspace', 'conversation'])
def test_document_selection_scope(axis):
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    audit = dict(owner=owner, confirmed_state=dict(EMPTY, metric='sales.latest_documents'),
        execution_status='executed', business_rbac_verified=True,
        response_prepared={'classification': 'DIRECT_AVAILABLE'}, required_permission='telchi.sales.latest_documents.read.v1',
        execution_result=document_result())
    audit['execution_result']['source'].update(publication_id=PUBLICATION, snapshot_id=SNAPSHOT)
    view = refs.presentation(audit, 'turn-1', owner, 'conversation')
    changed = list(owner)
    conversation = 'conversation'
    if axis == 'conversation': conversation = 'different'
    else: changed[{'user': 4, 'tenant': 1, 'workspace': 2}[axis]] = 'different'
    with pytest.raises(ValueError):
        refs.document_selection(document(), view, 1, changed, conversation)


def test_document_list_hides_internal_identity_but_explicit_request_is_available():
    result = document_result()
    text = format_result(result)
    assert 'Factura N.º 260192728' in text
    assert all(internal not in text for internal in ['DocEntry', 'DocNum', 'OINV', 'snapshot', '900'])
    owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
    audit = dict(owner=owner, confirmed_state=dict(EMPTY, metric='sales.latest_documents'),
        execution_status='executed', business_rbac_verified=True,
        response_prepared={'classification': 'DIRECT_AVAILABLE'}, required_permission='telchi.sales.latest_documents.read.v1',
        execution_result=result)
    view = refs.presentation(audit, 'turn-1', owner, 'conversation')
    _, explicit = refs.resolve(select(1, 'doc_entry', 'turn-1'), view, None, owner, 'conversation')
    assert '900' in explicit
    result['source'].pop('updated_at')
    assert 'fecha de actualización no está disponible' in format_result(result)


def test_line_output_contract_no_units_or_amounts_invented():
    result = lines()
    assert validate_result(options(), result) is result
    text = format_result(result)
    assert 'unidad nativa' in text and 'DocEntry' not in text
    for mutation in [lambda r: r['rows'][0].update(unit='L'),
                     lambda r: r['rows'][0].update(quantity='NaN'),
                     lambda r: r['rows'].reverse(),
                     lambda r: r['rows'][0].update(line_total='99'),
                     lambda r: r['document'].update(doc_num='other')]:
        bad = deepcopy(result)
        mutation(bad)
        with pytest.raises(ValueError):
            validate_result(options(), bad)
    for key, value in [('document_type', 'ORIN'), ('source_system', 'OTHER'), ('snapshot_id', 99), ('doc_entry', '1 OR 1=1')]:
        with pytest.raises(ValueError):
            parameters(dict(options(), **{key: value}))
    assert 'No hay líneas publicadas' in format_result(lines(count=0))
    missing = lines()
    missing['rows'][0]['description'] = None
    assert 'Descripción no disponible' in format_result(missing)

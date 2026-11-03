"""Offline contract tests; scripted proposals do not certify model semantics."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.luna import LunaInterpreter, MODEL
from .test_assistant import event, latest, proposal
from .test_sales_business_contract import setup


ORIGINAL = 'Mostrame las últimas 5 facturas de venta de Telchi.'


def documents(entity=None, action='EXECUTE'):
    return proposal({'/schema_version': 2, '/metric': 'sales.latest_documents',
                     '/requested_metrics': ['sales.latest_documents'], '/limit': 5,
                     '/entity_mention': entity, '/period': None, '/temporal_reference': None},
                    intent='NEW_QUERY', action=action)


@pytest.mark.parametrize('text', [ORIGINAL, 'Mostrame las últimas 5 facturas de venta.'])
def test_authorized_context_reaches_interpreter_without_text_derived_tenant(text):
    async def run():
        handler, store, calls, c = setup([documents()])
        result = await handler.handle(event(text), c)
        supplied = handler.interpreter.calls[0]['enterprise_context']
        assert supplied == {'source': 'authenticated_team360_workspace', 'tenant_id': 'telchi',
                            'workspace_id': 'workspace', 'own_company': {'name': 'Telchi', 'aliases': []}}
        assert result.classification == 'DIRECT_AVAILABLE'
        assert calls == ['sales.latest_documents']  # Query double, never Foundation.
        audit = latest(store)
        assert audit['required_permission'] == 'telchi.sales.latest_documents.read.v1'
        assert audit['interpretation_proposed'] == documents()  # no post-hoc entity removal
        assert audit['committed']
    asyncio.run(run())


@pytest.mark.parametrize('target', ['channel', 'sender_identity'])
@pytest.mark.parametrize('field,value', [('tenant_id', 'XYZ'), ('workspace_id', 'external')])
def test_mismatched_identity_has_no_company_context_or_model_call(target, field, value):
    async def run():
        handler, store, calls, c = setup([documents()])
        c = replace(c, **{target: replace(getattr(c, target), **{field: value})})
        assert handler.authorization.enterprise_context(c) is None
        result = await handler.handle(event(ORIGINAL), c)
        assert result.classification == 'DENIED'
        assert not handler.interpreter.calls and not calls
    asyncio.run(run())


def test_new_documents_clear_previous_period_and_filters():
    before = dict(deepcopy(engine.EMPTY), metric='sales.net_amount',
                  period={'start': '2026-05-01', 'end_exclusive': '2026-06-01'},
                  branches=['Saavedra'], sales_channel='HORIZONTAL')
    result = engine.process(before, documents(), {}, 'own-company')
    assert result['committed']
    state = result['state_after']
    assert state['metric'] == 'sales.latest_documents' and state['limit'] == 5
    assert not any(state.get(k) for k in ('period', 'branches', 'sales_channel', 'entity_mention',
                                         'temporal_reference', 'product_search_text', 'selected_item_codes'))


@pytest.mark.parametrize('text, name', [
    ('Mostrame las últimas cinco facturas de la empresa XYZ', 'XYZ'),
    ('Mostrame las ventas al cliente XYZ', 'XYZ'),
    ('Mostrame las compras al proveedor XYZ', 'XYZ'),
    ('Mostrame las ventas al cliente Telchi', 'Telchi'),
    ('Mostrame las compras al proveedor Telchi', 'Telchi')])
@pytest.mark.parametrize('action', ['DIRECT_UNAVAILABLE', 'EXECUTE'])
def test_external_mentions_never_become_global_queries(text, name, action):
    async def run():
        entity = {'text': name, 'type': None}
        handler, store, calls, c = setup([documents(entity, action)])
        result = await handler.handle(event(text), c)
        assert result.classification == 'DIRECT_UNAVAILABLE'
        assert not calls
        audit = latest(store)
        assert audit['committed'] and audit['confirmed_state']['entity_mention'] == entity
        assert audit['execution_status'] == 'not_executed'
        assert name in result.text and 'Todavía no puedo' in result.text
        for jargon in ('MAPPING_MISSING', 'pendiente de resolución', 'operación documental', 'Límite parametrizado'):
            assert jargon not in result.text
    asyncio.run(run())


def test_company_context_does_not_grant_document_permission():
    async def run():
        handler, store, calls, c = setup([documents()], grants=False)
        result = await handler.handle(event(ORIGINAL), c)
        assert result.classification == 'DENIED' and not calls
        assert latest(store)['execution_status'] == 'not_executed'
    asyncio.run(run())


def test_structured_context_is_transmitted_to_real_adapter_contract(monkeypatch):
    monkeypatch.setenv('OpenAI_Key_JAI_query', 'test-only')
    handler, _, _, c = setup([])
    trusted = handler.authorization.enterprise_context(c)
    def respond(request):
        body = json.loads(request.content)
        payload = json.loads(body['input'][1]['content'])
        assert payload['enterprise_context'] == trusted
        assert payload['user_message'] == ORIGINAL
        assert body['model'] == MODEL and body['reasoning']['effort'] == 'medium'
        assert not body['store'] and 'tools' not in body
        return httpx.Response(200, json={'model': MODEL, 'status': 'completed',
            'reasoning': {'effort': 'medium'}, 'output': [{'type': 'message',
            'content': [{'type': 'output_text', 'text': json.dumps(documents())}]}]})
    raw = asyncio.run(LunaInterpreter(transport=httpx.MockTransport(respond)).interpret(
        text=ORIGINAL, state=deepcopy(engine.EMPTY), history={}, turn_id='contract', enterprise_context=trusted))
    assert raw == documents()

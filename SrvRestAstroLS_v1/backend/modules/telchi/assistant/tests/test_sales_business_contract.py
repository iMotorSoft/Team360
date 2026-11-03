"""Regressions captured from real B02/B04 HTTP, without changing Luna/engine."""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler, documentary_request_contract
from modules.telchi.datalake.sales_query import PERMISSIONS, PUBLICATION, parameters
from .test_assistant import MemoryStore, Interpreter, context, event, proposal, latest


def documentary_proposal():
    return proposal({'/schema_version': 2, '/metric': 'sales.latest_documents',
                     '/requested_metrics': ['sales.latest_documents'], '/limit': 10}, intent='NEW_QUERY')


def setup(proposals, grants=True):
    c = context()
    c = replace(c, channel=replace(c.channel, tenant_id='telchi'),
        sender_identity=replace(c.sender_identity, tenant_id='telchi',
            permissions=frozenset({'fixture.business.read'} | (set(PERMISSIONS.values()) if grants else set()))))
    calls = []
    async def query(op, options, **kwargs):
        calls.append(op)
        rows = ([dict(first_date='2026-01-01', last_date='2026-09-24', documents=2,
                      latest_month_with_rows='2026-09', complete_month_certified=False)]
                if op == 'sales.coverage' else [dict(source_system='SAP_B1_HANA', doc_entry='2',
                    doc_num='22', doc_date='2026-09-24', canceled='N')])
        return dict(capability=op+'.v1', rows=rows, read_only=True, sap_accessed=False,
            sql_parameters=parameters(op, options), source=dict(publication_id=PUBLICATION, snapshot_id=1408))
    store = MemoryStore()
    handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
        BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
        interpreter=Interpreter(proposals), capabilities=SalesCapabilities(sales_query=query))
    return handler, store, calls, c


@pytest.mark.parametrize('grants', [True, False])
def test_latest_date_uses_coverage_with_its_own_permission(grants):
    async def run():
        handler, store, calls, c = setup([documentary_proposal()], grants)
        result = await handler.handle(event('¿Cuál es la última fecha de ventas registrada?'), c)
        assert result.classification == ('DIRECT_AVAILABLE' if grants else 'DENIED')
        assert calls == (['sales.coverage'] if grants else [])
        audit = latest(store)
        assert audit['interpretation_proposed']['state_delta']['set']['/metric'] == 'sales.latest_documents'
        assert audit['validated_state']['metric'] == 'sales.coverage'
    asyncio.run(run())


@pytest.mark.parametrize('action', ['ASK', 'EXECUTE'])
def test_previous_documents_preserve_context_no_second_query(action):
    async def run():
        ask = (proposal({}, intent='REFERENCE', action='ASK',
            clarification={'slot': 'reference', 'question': '¿A qué consulta anterior te referís?'})
            if action == 'ASK' else proposal({}, action='EXECUTE'))
        handler, store, calls, c = setup([documentary_proposal(), ask])
        await handler.handle(event('Dame las últimas 10 facturas'), c)
        result = await handler.handle(event('¿Y las anteriores?'), replace(c, correlation_id='second'))
        assert result.classification == 'DIRECT_UNAVAILABLE'
        assert 'no admite paginación' in result.text
        assert calls == ['sales.latest_documents']
        assert latest(store)['confirmed_state']['metric'] == 'sales.latest_documents'
        assert latest(store)['execution_status'] == 'not_executed'
    asyncio.run(run())


@pytest.mark.parametrize('change', ['monetary', 'limit', 'ask', 'invalid', 'conflict', 'refine'])
def test_no_general_interpretation_repair(change):
    raw = documentary_proposal()
    if change == 'monetary': raw['state_delta']['set']['/requested_metrics'].append('sales.net_amount')
    if change == 'limit': raw['state_delta']['set']['/limit'] = 50
    if change == 'ask': raw['action'] = 'ASK'
    if change == 'invalid': raw = None
    if change == 'conflict': raw['state_delta']['unset'] = ['/limit']
    if change == 'refine': raw['intent'] = 'REFINE'
    assert documentary_request_contract(deepcopy(raw), '¿Cuál es la última fecha de ventas registrada?') == raw


def test_corrected_proposal_still_cannot_bypass_commit_guard():
    async def run():
        handler, store, calls, c = setup([documentary_proposal()])
        handler.engine = lambda *args: dict(committed=False, state_after=engine.EMPTY, output={'action':'EXECUTE'})
        await handler.handle(event('¿Cuál es la última fecha de ventas registrada?'), c)
        assert calls == []
        assert latest(store)['decision'] == 'EXECUTION_FORBIDDEN'
    asyncio.run(run())

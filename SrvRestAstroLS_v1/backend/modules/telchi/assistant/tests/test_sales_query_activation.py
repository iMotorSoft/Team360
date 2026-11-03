"""New facts require new permissions; legacy grant never implies activation."""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.datalake.sales_query import PERMISSIONS, PUBLICATION, parameters, validate_result
from .test_assistant import MemoryStore, Interpreter, context, event, proposal, latest


def request(metric, **kwargs):
    return dict(deepcopy(engine.EMPTY), metric=metric, **kwargs)


@pytest.mark.parametrize('operation,options', [
    ('sales.latest_documents', {'limit': 0}), ('sales.latest_documents', {'limit': 51}),
    ('sales.latest_documents', {'limit': True}), ('sales.latest_documents', {'limit': '10'}),
    ('sales.latest_documents', {'sort': 'DROP TABLE'}), ('sales.coverage', {'limit': 1}),
    ('sales.coverage', {'entity_id': 'other-tenant'}), ('sales.period_summary', {}),
])
def test_allowlist(operation, options):
    with pytest.raises(ValueError):
        parameters(operation, options)


@pytest.mark.parametrize('metric', list(PERMISSIONS))
def test_periodless_commit(metric):
    out = engine.process(engine.EMPTY, proposal({'/metric': metric}, intent='NEW_QUERY'), {}, 'turn')
    assert out['committed'] is True
    assert SalesCapabilities().availability(out['state_after']).allowed


@pytest.mark.parametrize('limit', [False, 0, 51, '10'])
def test_invalid_limit_no_commit(limit):
    out = engine.process(engine.EMPTY, proposal({'/metric': 'sales.latest_documents', '/limit': limit}), {}, 'turn')
    assert out['committed'] is False


@pytest.mark.parametrize('metric', list(PERMISSIONS))
@pytest.mark.parametrize('authorized', [False, True])
def test_real_handler_permission_fence(metric, authorized):
    async def run():
        calls = []
        async def query(op, options, **kwargs):
            calls.append(op)
            rows = ([dict(first_date='2026-01-01', last_date='2026-09-24', documents=2,
                          latest_month_with_rows='2026-09', complete_month_certified=False)]
                    if metric == 'sales.coverage' else
                    [dict(source_system='SAP_B1_HANA', doc_entry='2', doc_num='22', doc_date='2026-09-24', canceled='N')])
            return dict(capability=metric+'.v1', rows=rows, read_only=True, sap_accessed=False,
                        sql_parameters=parameters(op, options),
                        source=dict(publication_id=PUBLICATION, snapshot_id=1408, updated_at='fixture'))
        c = context()
        c = replace(c, channel=replace(c.channel, tenant_id='telchi'),
                    sender_identity=replace(c.sender_identity, tenant_id='telchi',
                        permissions=frozenset({'fixture.business.read'} | ({PERMISSIONS[metric]} if authorized else set()))))
        store = MemoryStore()
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([proposal({'/metric': metric}, intent='NEW_QUERY')]),
            capabilities=SalesCapabilities(sales_query=query))
        result = await handler.handle(event(), c)
        assert result.classification == ('DIRECT_AVAILABLE' if authorized else 'DENIED')
        assert calls == ([metric] if authorized else [])
        assert latest(store)['execution_status'] == ('executed' if authorized else 'not_executed')
    asyncio.run(run())


def test_no_commit_means_zero_sales_calls():
    async def run():
        async def forbidden(*args, **kwargs):
            pytest.fail('rejected request touched Foundation')
        c = context()
        store = MemoryStore()
        handler = TelchiHandler(store=store, authorization=BusinessAuthorization(
            BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([proposal({'/metric': 'sales.coverage'})]),
            capabilities=SalesCapabilities(sales_query=forbidden),
            engine=lambda *args: dict(committed=False, state_after=request('sales.coverage'),
                                     output={'action': 'EXECUTE'}))
        await handler.handle(event(), c)
        assert latest(store)['decision'] == 'EXECUTION_FORBIDDEN'
    asyncio.run(run())


@pytest.mark.parametrize('metric', list(PERMISSIONS))
def test_no_entity_or_physical_aggregate(metric):
    state = dict(request(metric), **engine.INTENT_V2)
    state['requested_metrics'] = [metric]
    state['entity_mention'] = {'text': 'Calenta', 'type': None}
    assert SalesCapabilities().availability(state).category == 'MAPPING_MISSING'
    state['entity_mention'] = None
    state['requested_metrics'].append('sales.net_amount')
    assert SalesCapabilities().availability(state).category == 'METRIC_MISSING'


@pytest.mark.parametrize('change', ['publication', 'snapshot', 'read_only', 'sap', 'order', 'duplicate', 'canceled', 'source'])
def test_result_fail_closed(change):
    rows = [dict(source_system='SAP_B1_HANA', doc_entry=str(n), doc_num=str(n),
                 doc_date='2026-09-24T00:00:00', canceled='N') for n in (2, 1)]
    result = dict(capability='sales.latest_documents.v1', rows=rows, read_only=True, sap_accessed=False,
                  sql_parameters=['SAP_B1_HANA', 'N', 10],
                  source=dict(publication_id=PUBLICATION, snapshot_id=1408))
    if change == 'publication': result['source']['publication_id'] = 'candidate'
    elif change == 'snapshot': result['source']['snapshot_id'] = 1409
    elif change == 'read_only': result['read_only'] = False
    elif change == 'sap': result['sap_accessed'] = True
    elif change == 'order': rows.reverse()
    elif change == 'duplicate': rows[1] = rows[0].copy()
    elif change == 'canceled': rows[0]['canceled'] = 'Y'
    elif change == 'source': rows[0]['source_system'] = 'another_tenant'
    with pytest.raises(ValueError):
        validate_result('sales.latest_documents', {}, result)


def test_new_query_does_not_inherit_limit():
    before = request('sales.latest_documents', limit=50)
    result = engine.process(before, proposal({'/metric': 'sales.latest_documents'}, intent='NEW_QUERY'), {}, 'turn')
    assert result['committed'] and result['state_after'].get('limit', 10) == 10


def test_new_permission_revalidated_in_postgres():
    class Conn:
        pass
    from unittest.mock import AsyncMock, patch
    async def run():
        c = context()
        grant = PERMISSIONS['sales.coverage']
        c = replace(c, channel=replace(c.channel, tenant_id='telchi'),
                    sender_identity=replace(c.sender_identity, tenant_id='telchi',
                        permissions=frozenset({'fixture.business.read', grant})))
        auth = BusinessAuthorization(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True))
        with patch('modules.telchi.assistant.handler.PermissionConsoleRepository.list_effective_permissions',
                   new=AsyncMock(return_value={'fixture.business.read'})):
            assert not await auth.allowed(c, Conn(), required_permission=grant)
    asyncio.run(run())

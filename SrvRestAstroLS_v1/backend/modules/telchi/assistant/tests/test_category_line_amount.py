"""Category routing, permission barrier and history arithmetic, with explicit fixtures."""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.monetary_comparison import accredited, calculate
from modules.telchi.datalake import category_line_amount_query as query
from .test_business_categories import category, PERIOD
from .test_assistant import event, latest, proposal
from .test_sales_business_contract import setup


def result(options, amount='70.13'):
    return dict(capability=query.CAPABILITY, parameters=options, definition=query.DEFINITION,
        currency='BS', rows=[dict(amount=amount, product_count=1, line_count=1, document_count=1,
            first_date='2026-09-01', last_date='2026-09-24')],
        coverage=dict(first_date='2026-09-01', last_date='2026-09-24', complete=False),
        classification=dict(version=query.CLASSIFICATION_VERSION, sha256=query.CROSSWALK_SHA256,
            reference='fixture-reference', quality_lines={'VALIDATED': 1}),
        source=dict(publication_id=query.PUBLICATION, snapshot_id=query.SNAPSHOT, updated_at='2026-09-28'),
        read_only=True, sap_accessed=False, limitations=deepcopy(query.LIMITATIONS))


def options(code='RAW_MATERIAL'):
    return dict(category=code, date_from=PERIOD['start'], date_to_exclusive=PERIOD['end_exclusive'], currency='BS')


def grant(context):
    return replace(context, sender_identity=replace(context.sender_identity,
        permissions=context.sender_identity.permissions | {query.PERMISSION}))


def test_handler_continuity_then_revocation_without_global_or_search_substitution():
    async def run():
        follow = proposal({'/entity_mention': dict(text='LAB_FINISHED_PRODUCT', type=None)}, intent='REFINE')
        august = proposal({'/period': dict(start='2026-08-01',end_exclusive='2026-09-01')}, intent='REFINE')
        handler, store, wrong_calls, context = setup([category(action='EXECUTE'), follow, august])
        calls = []
        async def execute(opts, **kw):
            calls.append(opts)
            return result(opts)
        handler.capabilities = SalesCapabilities(category_query=execute)
        context = grant(context)
        for n in range(2):
            response = await handler.handle(event('consulta comercial'), replace(context, correlation_id=str(n)))
            assert response.classification == 'DIRECT_AVAILABLE'
            assert latest(store)['required_permission'] == query.PERMISSION
            assert 'Bs 70,13' in response.text and 'No incluye IVA' in response.text
        assert calls == [options(), options('LAB_FINISHED_PRODUCT')]
        context = replace(context, sender_identity=replace(context.sender_identity,
            permissions=context.sender_identity.permissions - {query.PERMISSION}))
        response = await handler.handle(event('¿Y en agosto?'), replace(context, correlation_id='revoked'))
        assert response.classification == 'DENIED' and len(calls) == 2 and not wrong_calls
    asyncio.run(run())


@pytest.mark.parametrize('change', ['tenant', 'workspace', 'permission'])
def test_no_unauthorized_foundation_execution(change):
    async def run():
        handler, store, calls, context = setup([category(action='EXECUTE')])
        if change != 'permission':
            context = grant(context)
            field = 'tenant_id' if change == 'tenant' else 'workspace_id'
            context = replace(context, sender_identity=replace(context.sender_identity, **{field: 'foreign'}))
        response = await handler.handle(event('ventas categoría'), context)
        assert response.classification == 'DENIED' and not calls
        if change == 'permission':
            assert latest(store)['capability_calls'] == 0
        else:
            assert not store.audits  # scope denied before entering conversation storage
    asyncio.run(run())


def test_explanation_no_query():
    async def run():
        explain = proposal({}, intent='EXPLAIN', action='DIRECT_UNAVAILABLE')
        handler, store, calls, context = setup([category(), explain])
        await handler.handle(event('ventas categoría'), context)
        response = await handler.handle(event('¿Por qué difiere de la cabecera?'), replace(context,correlation_id='explain'))
        assert response.classification == 'DIRECT_AVAILABLE' and not calls
        assert 'No toda la diferencia residual' in response.text
        assert latest(store)['capability_calls'] == 0
    asyncio.run(run())


def audit(code):
    from modules.telchi.assistant import state_engine as engine
    state = engine.process(deepcopy(engine.EMPTY), category(code=code,action='EXECUTE'),{},'test')['state_after']
    return dict(owner={'workspace':'fixture'},execution_status='executed', business_rbac_verified=True,
        required_permission=query.PERMISSION, response_prepared={'classification':'DIRECT_AVAILABLE'},
        confirmed_state=state, execution_result=result(options(code), '100' if code=='RAW_MATERIAL' else '200'))


def test_category_comparison_only_accredited_compatible_results():
    owner={'workspace':'fixture'}
    a=accredited(audit('RAW_MATERIAL'),'a',owner)
    b=accredited(audit('LAB_FINISHED_PRODUCT'),'b',owner)
    request=dict(intent='MONETARY_COMPARISON',action='CALCULATE',clarification=None,
        comparison=dict(target_id='b',baseline_id='a',mode='difference'))
    record,text=calculate(request,[a,b],owner)
    assert record['difference']=='100' and 'Producto terminado' in text
    percent_request=deepcopy(request)
    percent_request['comparison']['mode']='percent'
    assert '100,00 %' in calculate(percent_request,[a,b],owner)[1]
    assert accredited(audit('RAW_MATERIAL'),'a',{'workspace':'other'}) is None
    for key,value in [('currency','USD'),('coverage',dict(b['coverage'],last_date='2026-09-23')),
            ('period',dict(b['period'],date_from='2026-08-01'))]:
        other=dict(b,**{key:value})
        with pytest.raises(ValueError):
            calculate(request,[a,other],owner)


@pytest.mark.parametrize('execution_result', [None, {}, [], 'invalid'])
def test_nonexecution_history_does_not_break_result_reload(execution_result):
    assert accredited(dict(execution_result=execution_result),'none',{'workspace':'fixture'}) is None


def test_repository_retains_different_categories_in_same_period():
    from modules.telchi.assistant.repository import ConversationRepository
    from types import SimpleNamespace
    class Cursor:
        async def fetchall(self):
            return [dict(result_id=code,audit=audit(code)) for code in ('RAW_MATERIAL','LAB_FINISHED_PRODUCT')]
    class Connection:
        async def execute(self,*args):
            return Cursor()
    context=SimpleNamespace(conversation_id='thread',channel=SimpleNamespace(channel_id='channel',workspace_id='workspace',environment='dev'))
    results=asyncio.run(ConversationRepository().load_monetary_results(Connection(),context,
        dict(history={'RAW_MATERIAL':{},'LAB_FINISHED_PRODUCT':{}},owner={'workspace':'fixture'})))
    assert len(results)==2 and {r['category'] for r in results}=={'RAW_MATERIAL','LAB_FINISHED_PRODUCT'}


@pytest.mark.parametrize('reason', ['category_currency_not_accredited','category_classification_provisional'])
def test_data_limitations_keep_requested_period_without_execution_claim(reason):
    async def run():
        handler,store,_,context=setup([category(action='EXECUTE')])
        async def blocked(*args,**kwargs):
            from modules.telchi.datalake.messaging_sales_query import TelchiQueryError
            raise TelchiQueryError(reason)
        handler.capabilities=SalesCapabilities(category_query=blocked)
        response=await handler.handle(event('ventas categoría'),grant(context))
        assert response.classification=='DIRECT_UNAVAILABLE'
        assert latest(store)['confirmed_state']['period']==PERIOD
        assert latest(store)['execution_status']=='not_executed'
        assert 'importe sustituto' not in response.text
    asyncio.run(run())


def test_zero_formatter_does_not_certify_business_zero():
    r=result(options())
    r['rows'][0].update(amount='0',product_count=0,line_count=0,document_count=0,first_date=None,last_date=None)
    r['classification']['quality_lines']={}
    query.validate_result(options(),r)
    assert 'no acredita ventas cero' in format_result(r)

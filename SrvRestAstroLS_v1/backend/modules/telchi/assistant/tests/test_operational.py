import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.assistant.operational import options_for
from modules.telchi.datalake import operational_query as query
from .test_assistant import MemoryStore, Interpreter, context, event, proposal, latest


def state(metric):
    s = dict(deepcopy(engine.EMPTY | engine.INTENT_V2), metric=metric,requested_metrics=[metric])
    if metric in query.SNAPSHOT_METRICS:
        s['product_target']='EXPLICIT-CODE'
    else:
        s['period']={'start':'2026-10-01','end_exclusive':'2026-11-01'}
    return s


@pytest.mark.parametrize('metric',query.OPERATIONS)
def test_state_catalog_and_specific_permission(metric):
    s=state(metric)
    p=proposal({'/'+k:v for k,v in s.items() if k in {'metric','period','product_target'}},intent='NEW_QUERY')
    processed=engine.process(engine.EMPTY,p,{},'operation')
    assert processed['committed'] is True, processed
    assert SalesCapabilities().availability(processed['state_after']).allowed
    assert SalesCapabilities().required_permissions(s)==[query.PERMISSIONS[metric]]
    assert query.PERMISSIONS[metric] not in {'telchi.sales.period_billed_amount.read.v1','FULL_ACCESS'}


@pytest.mark.parametrize('metric',query.OPERATIONS)
@pytest.mark.parametrize('field,value',[('branches',['Sucursal']),('entity_mention',{'text':'Unknown supplier','type':None}),
                                      ('business_category','RAW_MATERIAL'),('comparison',{'start':'2026-09-01','end_exclusive':'2026-10-01'})])
def test_filters_never_disappear_into_global_total(metric,field,value):
    assert not SalesCapabilities().availability(state(metric)|{field:value}).allowed


@pytest.mark.parametrize('metric',query.OPERATIONS)
@pytest.mark.parametrize('authorized,tenant,committed',[(True,'telchi',True),(False,'telchi',True),(True,'other',True),(True,'telchi',False)])
@pytest.mark.parametrize('action',['EXECUTE','DIRECT_UNAVAILABLE'])
def test_handler_fences_and_persistence(monkeypatch,metric,authorized,tenant,committed,action):
    async def run():
        calls=[]
        async def worker(m,o,**kwargs):
            calls.append((m,o))
            return dict(contract=query.CONTRACT,metric=m,capability=m+'.v1',label='Operational fixture',parameters=o,rows=[],total_rows=0,omitted_rows=0,
                limitations=['Partial observations, not zero.'],controls={},coverage={},source={'publication_id':'fixture-only'})
        monkeypatch.setattr(query,'query_operational',worker)
        c=context()
        c=replace(c,channel=replace(c.channel,tenant_id=tenant),sender_identity=replace(c.sender_identity,
            tenant_id=tenant,permissions=frozenset({'fixture.business.read'} | ({query.PERMISSIONS[metric]} if authorized else set()))))
        s=state(metric)
        p=proposal({'/'+k:v for k,v in s.items() if k in {'metric','period','product_target'}},intent='NEW_QUERY',action=action)
        store=MemoryStore()
        handler=TelchiHandler(store=store,authorization=BusinessAuthorization(BusinessPolicy('telchi','workspace','fixture.business.read',True,True)),
            interpreter=Interpreter([p]),capabilities=SalesCapabilities())
        if not committed:
            handler.engine=lambda *args:dict(committed=False,state_after=deepcopy(engine.EMPTY),output=p)
        response=await handler.handle(event('Pregunta de operación'),c)
        allowed=authorized and tenant=='telchi' and committed
        assert len(calls)==int(allowed)
        if allowed:
            assert response.classification=='DIRECT_AVAILABLE'
            assert latest(store)['execution_status']=='executed'
            assert latest(store)['required_permission']==query.PERMISSIONS[metric]
            assert latest(store)['business_scope']['universe']=='CAPTURED_NATIVE_OBSERVATIONS'
            assert latest(store)['business_scope']['metric']==metric
        elif tenant=='telchi' and committed:
            assert response.classification=='DENIED'
    asyncio.run(run())


@pytest.mark.parametrize('options',[{'limit':True},{'limit':51},{'limit':0},{'sql':'SELECT 1'},
    {'date_from':'2026-10-01'},{'date_from':'2026-11-01','date_to_exclusive':'2026-10-01'}])
def test_bad_parameters(options):
    with pytest.raises(ValueError):
        query.parameters('production.consumption',options)


def test_snapshot_not_retroactive():
    with pytest.raises(ValueError):
        options_for(state('inventory.stock_by_warehouse')|{'period':{'start':'2026-10-01','end_exclusive':'2026-11-01'}})


def test_interpreter_has_no_stale_consumption_veto():
    import json
    from modules.telchi.assistant.business_categories import interpreter_context
    from modules.telchi.assistant.luna import SYSTEM
    context=interpreter_context()
    assert context['production_consumption_capability']=='production.consumption'
    assert len(json.dumps(context))<2000
    assert 'Consumo productivo es otra operación, NO ventas: metric=null' not in SYSTEM


@pytest.mark.parametrize('cancel',[False,True])
def test_worker_timeout_and_cancellation_cleanup(monkeypatch,cancel):
    class Process:
        returncode=None
        killed=False
        async def communicate(self):
            await asyncio.sleep(10)
        def kill(self):
            self.killed=True
        async def wait(self):
            self.returncode=-9
    process=Process()
    async def spawn(*args,**kwargs):
        return process
    monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
    async def run():
        task=asyncio.create_task(query.query_operational('production.consumption',dict(date_from='2026-10-01',date_to_exclusive='2026-11-01'),timeout_seconds=.02))
        if cancel:
            await asyncio.sleep(.005)
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task
        assert process.killed and process.returncode==-9
        assert not query._LOCK.locked()
    asyncio.run(run())

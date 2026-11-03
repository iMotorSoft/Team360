import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from uuid import uuid4
from modules.business_semantics.resolver import BusinessConceptResolver,VectorCandidatePolicy,luna_context
from modules.business_semantics.tests.test_semantics import Repo,resolve
from modules.telchi.assistant.tests.test_assistant import setup,proposal,context,event,latest


def test_latest_date_limit_one_still_uses_coverage_and_specific_grant():
    from modules.telchi.assistant.tests.test_sales_business_contract import setup as sales_setup, documentary_proposal
    async def run():
        raw=documentary_proposal();raw['state_delta']['set']['/limit']=1
        handler,store,calls,c=sales_setup([raw],True)
        response=await handler.handle(event('¿Cuál es la última fecha de ventas registrada?'),c)
        assert response.classification=='DIRECT_AVAILABLE' and calls==['sales.coverage']
        assert latest(store)['interpretation_proposed']['state_delta']['set']['/limit']==1
        assert latest(store)['validated_state']['metric']=='sales.coverage'
    asyncio.run(run())


def test_measured_candidate_margin_without_auto_truth():
    async def run():
        class Embed:
            config=None
            async def embed(self,text):
                return [0.1,0.2]
        repo=Repo()
        async def vectors(*args):
            return [{'concept_id':repo.concepts[4]['concept_id'],'score':0.4428},
                    {'concept_id':repo.concepts[3]['concept_id'],'score':0.3800}]
        repo.vector_search=vectors
        resolver=BusinessConceptResolver(repo,Embed(),VectorCandidatePolicy(0.4,0.05,'DEV-nine-concepts-evaluation'))
        result=await resolve(resolver,'negocios presupuestados no concretados')
        assert result['status']=='candidate' and result['ambiguous']
        assert result['ranking']['vector_eligible']
        assert len(luna_context(result)['concepts'])==1
        async def nearby(*args):
            return [{'concept_id':repo.concepts[1]['concept_id'],'score':0.4390},
                    {'concept_id':repo.concepts[0]['concept_id'],'score':0.4331}]
        repo.vector_search=nearby
        result=await resolve(resolver,'Dame ventas de Calenta')
        assert not result['ranking']['vector_eligible']
        assert not luna_context(result)['concepts']
    asyncio.run(run())


def test_known_followup_no_global_sales_substitution_and_new_query_releases_reference():
    async def run():
        handler,store,llm,calls=setup([
            proposal({'/metric':'sales.source_top_items','/period':{'start':'2026-01-01','end_exclusive':'2026-09-16'}},intent='NEW_QUERY'),
            proposal(),
            proposal({'/metric':'sales.source_top_items'},intent='NEW_QUERY')])
        original=store.turn
        @asynccontextmanager
        async def with_conn(ctx):
            async with original(ctx) as turn:
                yield dict(turn,conn=None)
        store.turn=with_conn
        handler.concept_resolver=BusinessConceptResolver(Repo())
        await handler.handle(event('Dame ventas de farmacia'),context())
        assert not calls
        from dataclasses import replace
        result=await handler.handle(event('Y septiembre'),replace(context(),correlation_id='turn2'))
        assert not calls and result.classification=='DIRECT_UNAVAILABLE'
        assert latest(store)['confirmed_state']['semantic_references']
        result=await handler.handle(event('Nueva consulta: top documental'),replace(context(),correlation_id='turn3'))
        assert result.classification=='DIRECT_AVAILABLE' and len(calls)==1
        assert not latest(store)['confirmed_state'].get('semantic_references')
    asyncio.run(run())


def test_disabled_resolver_cannot_execute_semantic_previous_plan():
    async def run():
        handler,store,llm,calls=setup([proposal({'/metric':'sales.source_top_items',
            '/period':{'start':'2026-01-01','end_exclusive':'2026-09-16'}}),proposal()])
        original=store.turn
        @asynccontextmanager
        async def with_conn(ctx):
            async with original(ctx) as turn:
                yield dict(turn,conn=None)
        store.turn=with_conn
        handler.concept_resolver=BusinessConceptResolver(Repo())
        await handler.handle(event('Dame ventas de farmacia'),context())
        handler.concept_resolver=None
        from dataclasses import replace
        response=await handler.handle(event('Y septiembre'),replace(context(),correlation_id='turn2'))
        assert not calls and response.classification=='DIRECT_UNAVAILABLE'
    asyncio.run(run())


def test_stale_reference_cannot_execute_previous_plan():
    async def run():
        handler,store,llm,calls=setup([proposal({'/metric':'sales.source_top_items',
                     '/period':{'start':'2026-01-01','end_exclusive':'2026-09-16'}}),proposal()])
        repo=Repo();handler.concept_resolver=BusinessConceptResolver(repo)
        original=store.turn
        @asynccontextmanager
        async def with_conn(ctx):
            async with original(ctx) as turn:
                yield dict(turn,conn=None)
        store.turn=with_conn
        await handler.handle(event('Dame ventas de farmacia'),context())
        repo.concepts=[]
        from dataclasses import replace
        result=await handler.handle(event('Y septiembre'),replace(context(),correlation_id='turn2'))
        assert not calls and result.classification=='DIRECT_UNAVAILABLE'
        assert latest(store)['bmd']['category']=='CONCEPT_REFERENCE_UNAVAILABLE'
    asyncio.run(run())

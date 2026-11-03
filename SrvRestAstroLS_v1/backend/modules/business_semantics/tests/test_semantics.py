import asyncio
from copy import deepcopy
from contextlib import asynccontextmanager
from uuid import uuid4
import pytest
from modules.business_semantics.resolver import BusinessConceptResolver,normalize,luna_context
from modules.business_semantics.telchi_seed import CONCEPTS
from modules.telchi.assistant.tests.test_assistant import setup,proposal,context,event,latest
from modules.telchi.assistant import state_engine


def concept(spec):
    spec=deepcopy(spec)
    return dict(concept_id=str(uuid4()),semantic_code=spec['code'],version=1,canonical_name=spec['name'],
                definition=spec['definition'],concept_type=spec['type'],aliases=spec['aliases'],
                operational_context=spec['context'],source=spec['source'],approval_status='published',
                capability_links=[],workspace_id='workspace',module_code='telchi')


class Repo:
    def __init__(self):
        self.concepts=[concept(s) for s in CONCEPTS]
        self.observations=[]
        self.text_hits=[]
    async def scope(self,*a):
        return {'organization_id':'organization'}
    async def authorize(self,conn,organization,workspace,actor):
        if actor!='user':
            raise PermissionError()
    async def catalog(self,*a):
        return deepcopy(self.concepts)
    async def text_search(self,*a):
        return self.text_hits
    async def vector_search(self,*a):
        return [{'concept_id':self.concepts[4]['concept_id'],'score':0.6}]
    async def observe(self,*a):
        self.observations.append(a[-1])


async def resolve(resolver,text,**kwargs):
    return await resolver.resolve(None,organization_id='organization',workspace_id='workspace',module='telchi',
                                  actor_id='user',text=text,**kwargs)


@pytest.mark.parametrize('n,text',[(0,'Dame ventas de farmacia'),(1,'¿Cuánto le vendimos a menona?'),
 (2,'¿Qué hay que importar?'),(3,'Dame las deudas'),(4,'Mostrame las ventas perdidas')])
def test_exact_without_embedding(n,text):
    class Never:
        async def embed(self,text):
            pytest.fail('exact match must not call embeddings')
    result=asyncio.run(resolve(BusinessConceptResolver(Repo(),Never()),text))
    assert result['status']=='resolved'
    assert result['concepts'][0]['semantic_code']==CONCEPTS[n]['code']
    assert result['concepts'][0]['operational_context']['dimension']==CONCEPTS[n]['context']['dimension']
    assert result['timings']['embedding_ms']==0


def test_code_and_normalization():
    assert normalize('¿CUÁNTO nos deben?')=='cuanto nos deben'
    assert normalize('Dame las deudas.')=='dame las deudas'
    result=asyncio.run(resolve(BusinessConceptResolver(Repo()),CONCEPTS[3]['code']))
    assert result['concepts'][0]['match']=='code'


def test_alias_collision_requires_disambiguation():
    repo=Repo();repo.concepts[1]['aliases'].append('Dame ventas de farmacia')
    result=asyncio.run(resolve(BusinessConceptResolver(repo),'Dame ventas de farmacia'))
    assert result['status']=='candidate' and result['ambiguous']


def test_scope_denied_before_retrieval():
    async def run():
        with pytest.raises(PermissionError):
            await BusinessConceptResolver(Repo()).resolve(None,organization_id='other',workspace_id='workspace',
                                                         module='telchi',actor_id='user',text='Dame ventas de farmacia')
    asyncio.run(run())


def test_unknown_observation_is_only_digest():
    repo=Repo()
    result=asyncio.run(resolve(BusinessConceptResolver(repo),'desconocido XYZ903',observe_unknown=True))
    assert result['status']=='unknown' and not result['concepts']
    assert len(repo.observations[0])==64


def test_offline_textual_available():
    repo=Repo();repo.text_hits=[{'concept_id':repo.concepts[0]['concept_id'],'score':0.1}]
    class Offline:
        async def embed(self,text):
            raise TimeoutError()
    result=asyncio.run(resolve(BusinessConceptResolver(repo,Offline()),'sucursales farmacia'))
    assert result['degraded']=='embedding_unavailable' and result['concepts'][0]['match']=='text'


def test_vectors_remain_candidates_not_definitions():
    class Embed:
        config=None
        async def embed(self,text):
            return [0.1,0.2]
    result=asyncio.run(resolve(BusinessConceptResolver(Repo(),Embed()),'oportunidades no concretadas'))
    assert result['status']=='candidate'
    assert luna_context(result)['requires_disambiguation']


@pytest.mark.parametrize('commit',[True,False])
def test_handler_known_definition_never_executes_or_repairs_rejection(commit):
    async def run():
        handler,store,llm,calls=setup([proposal({'/metric':'sales.source_top_items','/period':{'start':'2026-01-01','end_exclusive':'2026-09-16'}})])
        original=store.turn
        @asynccontextmanager
        async def with_conn(ctx):
            async with original(ctx) as turn:
                yield dict(turn,conn=None)
        store.turn=with_conn
        handler.concept_resolver=BusinessConceptResolver(Repo())
        if not commit:
            handler.engine=lambda *a:dict(committed=False,state_after=deepcopy(state_engine.EMPTY),output=proposal())
        result=await handler.handle(event('Dame ventas de farmacia'),context())
        assert not calls
        audit=latest(store)
        assert audit['committed'] is commit
        if commit:
            assert result.classification=='DIRECT_UNAVAILABLE' and 'sucursales' in result.text
            assert audit['confirmed_state']['semantic_references'][0]['version']==1
        else:
            assert audit['decision']=='EXECUTION_FORBIDDEN'
        assert llm.calls[0]['business_semantics']['concepts'][0]['operational_context']['dimension']=='branches'
    asyncio.run(run())


def test_reference_attachment_keeps_pending_hash_and_no_model_paths():
    p=proposal({'/metric':'sales.source_top_items'},action='ASK',clarification={'slot':'period','question':'¿Qué período?'})
    processed=state_engine.process(deepcopy(state_engine.EMPTY),p,{},'t1')
    assert processed['committed']
    after=processed['state_after']
    refs=[dict(concept_id=str(uuid4()),version=1)]
    state_engine.attach_semantic_references(after,refs)
    assert after['pending']['base_state_hash']==state_engine.state_hash(dict(after,pending=None))
    assert not state_engine.process(after,proposal({'/semantic_references':refs}),{},'t2')['committed']
    followup=proposal({'/period':{'start':'2026-01-01','end_exclusive':'2026-09-16'}},intent='ANSWER_CLARIFICATION')
    assert state_engine.process(after,followup,{},'t3')['committed']

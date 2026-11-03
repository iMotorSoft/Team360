"""Independent counterexamples; deliberately high scores cannot override business scope."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path

import pytest

from modules.business_semantics.resolver import BusinessConceptResolver, VectorCandidatePolicy, luna_context
from modules.business_semantics.tests.test_semantics import Repo, resolve

CASES = json.loads((Path(__file__).parent/'fixtures/semantic_boundaries_independent_v1.json').read_text())['cases']


def ranked_repo(case, *, fts=False):
    repo = Repo()
    target = next(c for c in repo.concepts if c['semantic_code'] == case['code'])
    other = next(c for c in repo.concepts if c['semantic_code'] != case['code'])
    async def hits(*args):
        return [dict(concept_id=target['concept_id'], score=0.99), dict(concept_id=other['concept_id'], score=0.10)]
    repo.vector_search = hits
    if fts:
        repo.text_hits = [dict(concept_id=target['concept_id'], score=0.8)]
    class Embed:
        config = None
        async def embed(self, text):
            return [0.1, 0.2]
    return repo, target, BusinessConceptResolver(repo, Embed(), VectorCandidatePolicy(0.4, 0.05, 'unchanged-fixture-policy'))


@pytest.mark.parametrize('case', CASES, ids=[c['query'] for c in CASES])
@pytest.mark.parametrize('fts', [False, True])
def test_independent_entity_domain_relationship_boundary(case, fts):
    repo, target, resolver = ranked_repo(case, fts=fts)
    result = asyncio.run(resolve(resolver, case['query']))
    delivered = luna_context(result)['concepts']
    assert any(c['semantic_code'] == case['code'] for c in delivered) is case['compatible']
    assert result['ranking']['vector_eligible'] is case['compatible']
    if not case['compatible']:
        assert all(c['semantic_code'] != case['code'] for c in result['concepts'])
        assert result['ambiguous'] and result['semantic_guard']['requires_clarification']


@pytest.mark.parametrize('code,text', [
    ('telchi.sales.pharmacy_branches', 'Ventas a las sucursales farmacia del distribuidor'),
    ('telchi.receivables.outstanding', 'Deudas de clientes a terceros'),
    ('telchi.receivables.outstanding', 'Nuestra deuda con los clientes'),
])
def test_direction_is_not_inferred_from_entity_name_alone(code, text):
    case = dict(code=code, query=text)
    repo, target, resolver = ranked_repo(case, fts=True)
    result = asyncio.run(resolve(resolver, text))
    assert not result['ranking']['vector_eligible']
    assert all(c['semantic_code'] != code for c in luna_context(result)['concepts'])


@pytest.mark.parametrize('code,text', [
    ('telchi.procurement.import_recommendations', 'Qué debemos a nuestros abastecedores'),
    ('telchi.sales.horizontal_channel', 'Detalle de venta de medicinas'),
])
def test_no_cross_domain_substitute_after_scope_veto(code, text):
    repo, target, resolver = ranked_repo(dict(code=code, query=text), fts=True)
    result = asyncio.run(resolve(resolver, text))
    assert not result['ranking']['vector_eligible']
    assert result['semantic_guard']['requires_clarification']
    assert all(c['semantic_code'] != code for c in luna_context(result)['concepts'])


def test_conflicting_followup_cannot_reintroduce_old_definition():
    case = dict(code='telchi.receivables.outstanding', query='¿Y las facturas que debemos a proveedores?')
    repo, target, resolver = ranked_repo(case)
    result = asyncio.run(resolve(resolver, case['query'], context={'semantic_references': [{'concept_id': target['concept_id'], 'version': 1}]}))
    assert not result['context_concepts']
    assert not luna_context(result)['conversation_concepts']


@pytest.mark.parametrize('text', ['Detalle de venta de medicinas', 'Saldo que debemos a proveedores'])
def test_explicit_conflict_remains_closed_with_empty_FTS_and_embedding_outage(text):
    class Offline:
        config = None
        async def embed(self, text):
            raise TimeoutError('unit-outage')
    result = asyncio.run(resolve(BusinessConceptResolver(Repo(), Offline()), text))
    assert not result['concepts']
    assert result['degraded'] == 'embedding_unavailable'
    assert result['semantic_guard']['requires_clarification']
    assert luna_context(result)['requires_disambiguation']


def test_boundary_clarification_cannot_execute_model_global_substitute():
    from modules.telchi.assistant.tests.test_assistant import setup, proposal, event, context, latest, plan
    case = dict(code='telchi.sales.pharmacy_branches', query='Ingresos por productos medicinales en junio')
    repo, target, resolver = ranked_repo(case)
    handler, store, interpreter, calls = setup([proposal({'/metric': plan()['metric'], '/period': plan()['period']})])
    original = store.turn
    @asynccontextmanager
    async def turn(ctx):
        async with original(ctx) as current:
            yield dict(current, conn=None)
    store.turn = turn
    handler.concept_resolver = resolver
    result = asyncio.run(handler.handle(event(case['query']), context()))
    assert result.classification == 'NEEDS_CLARIFICATION'
    assert not calls and not interpreter.calls
    assert latest(store)['execution_status'] == 'not_executed'

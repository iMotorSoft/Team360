"""Published name/alias retrieval in full questions; no new definitions or grants."""
import asyncio
from modules.business_semantics.tests.test_semantics import Repo, resolve
from modules.business_semantics.resolver import BusinessConceptResolver


def test_full_question_recovers_published_name_as_candidate_not_exact_authority():
    repo=Repo()
    c=dict(repo.concepts[0],concept_id='channel',semantic_code='telchi.sales.horizontal_channel',
           canonical_name='Venta horizontal',aliases=['venta horizontal','ventas horizontales'],
           operational_context={'dimension':'commercial_channel'},definition='Existing approved fixture meaning')
    repo.concepts = [x for x in repo.concepts if x['semantic_code'] != c['semantic_code']] + [c]
    result=asyncio.run(resolve(BusinessConceptResolver(repo),
        '¿Qué proporción de la facturación de febrero corresponde al canal horizontal?'))
    selected=[c for c in result['interpretation_concepts'] if c['concept_id']=='channel']
    assert selected and selected[0]['selection_reason']=='distinctive_published_name_token'
    assert selected[0]['match']=='text' and result['status']=='candidate'
    unrelated=asyncio.run(resolve(BusinessConceptResolver(repo),'¿Cuál fue la lluvia de febrero?'))
    assert unrelated['status']=='unknown' and not unrelated['interpretation_concepts']
    generic=asyncio.run(resolve(BusinessConceptResolver(repo),'Dame la venta del mes anterior'))
    assert not any(x['semantic_code']=='telchi.sales.horizontal_channel' for x in generic['interpretation_concepts'])


def test_embedded_alias_keeps_existing_entity_scope_veto():
    repo=Repo()
    result=asyncio.run(resolve(BusinessConceptResolver(repo),'Cuánto vendimos a clientes de farmacia durante octubre'))
    assert all(c['semantic_code']!='telchi.sales.pharmacy_branches' for c in result['interpretation_concepts'])

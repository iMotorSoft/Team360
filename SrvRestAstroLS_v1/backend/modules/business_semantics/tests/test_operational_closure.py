"""Local boundary regressions; these fixtures do not certify live auth or business facts."""
import asyncio
from copy import deepcopy

import pytest

from modules.business_semantics.resolver import BusinessConceptResolver, VectorCandidatePolicy, luna_context
from modules.business_semantics.tests.test_semantics import Repo, resolve


class EvidenceRepo(Repo):
    def __init__(self):
        super().__init__()
        self.evidence_reads = []

    async def relation_evidence(self, conn, cid, version):
        self.evidence_reads.append((cid, version))
        return {
            'entities': [{'entity_key': 'L00003', 'validation_status': 'PROVISIONAL',
                          'relationship': 'DIRECT_COMMERCIAL_SALE',
                          'evidence': {'ownership': 'UNKNOWN'}}],
            'rules': [{'rule_code': 'mixed_usage', 'validation_status': 'PROVISIONAL',
                       'limitations': ['Internal consumption is not commercial sales',
                                       'Document seller is not current account owner']}],
        }


def test_canonical_name_is_exact_without_embedding():
    repo = Repo()
    repo.concepts[0]['aliases'] = []
    result = asyncio.run(resolve(BusinessConceptResolver(repo), repo.concepts[0]['canonical_name']))
    assert result['status'] == 'resolved'
    assert result['concepts'][0]['match'] == 'alias'  # Preserve handler's exact-term contract.


def test_text_candidate_preserves_provisional_relations_for_luna():
    repo = EvidenceRepo()
    repo.text_hits = [{'concept_id': repo.concepts[0]['concept_id'], 'score': 0.8}]
    result = asyncio.run(resolve(BusinessConceptResolver(repo), 'sucursales farmacia'))
    data = luna_context(result)
    assert data['requires_disambiguation']
    assert data['concepts'][0]['related_evidence']['entities'][0]['validation_status'] == 'PROVISIONAL'
    assert data['concepts'][0]['related_evidence']['entities'][0]['evidence']['ownership'] == 'UNKNOWN'


def test_followup_preserves_provisional_evidence_and_deduplicates_reads():
    repo = EvidenceRepo()
    cid = repo.concepts[0]['concept_id']
    result = asyncio.run(resolve(BusinessConceptResolver(repo), 'seguimos',
                                context={'semantic_references': [{'concept_id': cid, 'version': 1}]}))
    evidence = luna_context(result)['conversation_concepts'][0]['related_evidence']
    assert evidence['rules'][0]['validation_status'] == 'PROVISIONAL'
    assert 'Document seller' in evidence['rules'][0]['limitations'][1]
    assert repo.evidence_reads == [(cid, 1)]


def test_eligible_compatible_vector_remains_candidate_with_provisional_evidence():
    repo = EvidenceRepo()

    class Embed:
        config = None

        async def embed(self, text):
            return [0.1, 0.2]

    async def hits(*args):
        return [{'concept_id': repo.concepts[0]['concept_id'], 'score': 0.95},
                {'concept_id': repo.concepts[1]['concept_id'], 'score': 0.70}]

    repo.vector_search = hits
    resolver = BusinessConceptResolver(repo, Embed(), VectorCandidatePolicy(0.8, 0.1, 'fixture-only'))
    # Similarity alone no longer establishes an entity or business relation.
    result = asyncio.run(resolve(resolver, 'ventas en locales clasificados como farmacias'))
    data = luna_context(result)
    assert result['ranking']['vector_eligible']
    assert data['status'] == 'candidate' and data['requires_disambiguation']
    assert data['concepts'][0]['related_evidence']['entities'][0]['validation_status'] == 'PROVISIONAL'
    assert repo.evidence_reads.count((repo.concepts[0]['concept_id'], 1)) == 1


def test_foreign_or_retired_reference_never_loads_evidence():
    repo = EvidenceRepo()
    result = asyncio.run(resolve(BusinessConceptResolver(repo), 'seguimos',
                                context={'semantic_references': [{'concept_id': 'foreign-private', 'version': 1}]}))
    assert not result['context_concepts']
    assert not repo.evidence_reads


@pytest.mark.parametrize('business_context', [
    {'scope': 'TELCHI_LITEL_OWN_PORTFOLIO', 'evidence_status': 'PROVISIONAL',
     'requires_verified_directorio_context': True, 'explicit_scope_precedence': True},
    {'uses': ['INTERNAL_PRODUCTION_CONSUMPTION', 'DIRECT_COMMERCIAL_SALE'], 'ownership': 'UNKNOWN'},
    {'ranking_metric': 'distinct_active_invoices', 'period': 'selected_window',
     'not_in_customer_top20': True, 'underselling': 'UNKNOWN', 'lost_sale': 'UNKNOWN'},
    {'customer_identifier_type': 'CardCode', 'product_identifier_type': 'ItemCode',
     'presentations': ['small', 'large'], 'entity_ambiguous': True},
    {'observed_document_seller_code': 'unverified-code', 'current_account_owner': 'UNKNOWN',
     'team360_user_mapping': 'UNKNOWN'},
    {'semantic_resolved': True, 'capability_status': 'UNAVAILABLE', 'data_status': 'UNKNOWN',
     'requested_metrics': ['amount', 'quantity']},
])
def test_business_contract_context_is_data_not_promoted_truth(business_context):
    repo = EvidenceRepo()
    repo.concepts[0]['operational_context'] = deepcopy(business_context)
    result = asyncio.run(resolve(BusinessConceptResolver(repo), repo.concepts[0]['semantic_code']))
    output = luna_context(result)['concepts'][0]
    assert output['operational_context'] == business_context
    assert output['capability_links'] == []
    # This proves serialization preservation, not LLM response correctness or execution.
    assert business_context == repo.concepts[0]['operational_context']

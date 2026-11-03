"""Tenant-first retrieval. Approximate matches are candidates, never execution authority."""
import hashlib
import unicodedata
import os
import math
import re
from dataclasses import dataclass
from time import perf_counter
from .repository import BusinessConceptRepository


def normalize(text):
    return ' '.join(''.join(c if c.isalnum() or c in '._' else ' ' for c in
        unicodedata.normalize('NFD',text.casefold()) if not unicodedata.combining(c)).split()).strip(' .')


def candidate_scope(concept, text):
    """Conservative compatibility for two EXISTING Telchi meanings, not an ontology.

    Lexical evidence can veto or request clarification; it never verifies real
    entity IDs, membership, balances or permission. Unknown/mixed scope abstains.
    Published definitions/thresholds are not changed by this check.
    """
    code = concept['semantic_code']
    query = normalize(text)
    has = lambda pattern: bool(re.search(pattern, query))
    result = dict(decision='compatible', entity_type='unspecified', domain='unspecified', relationship='unspecified')
    # A rejected receivable must not be replaced with an import recommendation
    # merely because both embeddings mention suppliers. No current concept is
    # an approved payable definition. This is a veto, not a new payable concept.
    supplier_debt = (has(r'\b(proveedores?|abastecedores?|acreedores?)\b') and
                     has(r'\b(deudas?|saldos?|debemos|adeudamos|debo|pagar|pendientes?|vencimientos?)\b'))
    checked_telchi_scope = (code.startswith('telchi.sales.') or code in {
        'telchi.procurement.import_recommendations', 'telchi.receivables.outstanding'})
    if checked_telchi_scope and supplier_debt:
        return dict(result, decision='incompatible', entity_type='supplier_or_creditor',
                    domain='debt', relationship='non_customer_or_mixed_direction',
                    reason='supplier_debt_cannot_substitute_sales_or_import_intent')
    pharmaceutical_product = has(r'\b(medicamentos?|medicinas?|farmacos?)\b|\bproductos? (?:farmaceuticos?|medicinales?)\b')
    if checked_telchi_scope and pharmaceutical_product:
        return dict(result, decision='incompatible', entity_type='product', domain='product_sales_or_mixed',
                    relationship='not_branch_or_channel_scope', reason='product_cannot_substitute_other_existing_scope')
    if code == 'telchi.sales.pharmacy_branches':
        if concept['concept_type'] != 'ENTITY_SCOPE' or concept['operational_context'].get('dimension') != 'branches':
            return dict(result, decision='incompatible', reason='published_scope_metadata_mismatch')
        branch = has(r'\b(sucursales?|locales?|tiendas?|establecimientos?)\b')
        pharmacy = has(r'\bfarmacias?\b')
        product = has(r'\b(medicamentos?|medicinas?|farmacos?|productos?|medicinales?)\b')
        customer = has(r'\b(clientes?|compradores?)\b|\b(?:a|para) (?:las? )?farmacias?\b'
                       r'|\b(?:a|para) (?:las? |una?s? |nuestr[ao]s? )?(?:sucursales?|locales?|tiendas?|establecimientos?)\b')
        purchase = has(r'\b(compras?|proveedores?|abastecedores?)\b')
        result.update(entity_type='branch' if branch else 'product' if product else 'customer' if customer else 'unspecified',
                      domain='purchasing' if purchase else 'sales', relationship='sale_at_branch' if branch else 'unspecified')
        if product or customer or purchase:
            return dict(result, decision='incompatible', reason='not_branch_sales_or_mixed_scope')
        if branch and pharmacy:
            return dict(result, reason='explicit_branch_pharmacy_scope')
        return dict(result, decision='unknown', reason='branch_entity_relationship_not_established')
    if code == 'telchi.receivables.outstanding':
        if concept['concept_type'] != 'COMPOSITE_METRIC' or concept['operational_context'].get('dimension') != 'receivables':
            return dict(result, decision='incompatible', reason='published_scope_metadata_mismatch')
        payable = has(r'\b(proveedores?|abastecedores?|acreedores?|debemos|adeudamos|debo|adeudo|compras?)\b|\bpor pagar\b'
                      r'|\b(?:a|con) (?:otros|terceros|bancos?)\b|\bnuestr[ao]s? deudas?\b'
                      r'|\bdeudas? (?:a|con) (?:los? )?clientes?\b')
        customer = has(r'\b(clientes?|compradores?)\b')
        owed_to_us = has(r'\bnos (?:deben|adeudan)\b|\bpor cobrar\w*\b')
        customer_debt = customer and has(r'\b(deudas?|adeudan|deben|morosos?)\b')
        result.update(entity_type='supplier_or_creditor' if payable else 'customer' if customer or owed_to_us else 'unspecified',
                      domain='payables' if payable else 'receivables' if owed_to_us or customer_debt else 'unspecified',
                      relationship='company_owes_or_mixed' if payable else 'customer_owes_company' if owed_to_us or customer_debt else 'unspecified')
        if payable:
            return dict(result, decision='incompatible', reason='not_customer_receivable_or_mixed_direction')
        if owed_to_us or customer_debt:
            return dict(result, reason='explicit_receivable_direction')
        return dict(result, decision='unknown', reason='debt_counterparty_direction_not_established')
    return dict(result, reason='outside_two_existing_scope_checks')


@dataclass(frozen=True)
class VectorCandidatePolicy:
    minimum_score: float
    minimum_margin: float
    calibration_id: str

    def __post_init__(self):
        if (not self.calibration_id or not math.isfinite(self.minimum_score)
                or not math.isfinite(self.minimum_margin) or not 0 <= self.minimum_score <= 1
                or not 0 < self.minimum_margin <= 1):
            raise ValueError('invalid_vector_candidate_policy')

    @classmethod
    def from_env(cls):
        calibration = os.getenv('TEAM360_SEMANTICS_VECTOR_CALIBRATION')
        if not calibration:
            return None
        return cls(float(os.environ['TEAM360_SEMANTICS_VECTOR_MINIMUM_SCORE']),
                   float(os.environ['TEAM360_SEMANTICS_VECTOR_MINIMUM_MARGIN']), calibration)


class BusinessConceptResolver:
    def __init__(self, repository=None, embeddings=None, vector_policy=None):
        self.repository=repository or BusinessConceptRepository()
        self.embeddings=embeddings
        self.vector_policy=vector_policy

    async def resolve(self, conn, *, organization_id, workspace_id, module, actor_id, text,
                      context=None, maximum=3, observe_unknown=False):
        if not 1<=maximum<=5:
            raise ValueError('concept_limit')
        repo=self.repository
        scope=await repo.scope(conn,workspace_id)
        if scope['organization_id']!=organization_id:
            raise PermissionError('business_semantics_scope_mismatch')
        await repo.authorize(conn,organization_id,workspace_id,actor_id)
        started=perf_counter()
        catalog=await repo.catalog(conn,organization_id,workspace_id,module)
        index={c['concept_id']:c for c in catalog}
        query=normalize(text[:4000])
        exact=[c for c in catalog if normalize(c['semantic_code'])==query]
        method='code'
        if not exact:
            exact=[c for c in catalog if normalize(c['canonical_name'])==query]
            method='alias'  # Existing exact-term contract consumed by the handler.
        if not exact:
            exact=[c for c in catalog if query in {normalize(a) for a in c['aliases']}]
            method='alias'
        metrics={'exact_ms':(perf_counter()-started)*1000,'text_ms':0.0,'embedding_ms':0.0,'vector_ms':0.0}
        degraded=None
        candidates=[]
        vector_hits=[]
        if exact:
            candidates=[dict(c,match=method,score=1.0) for c in exact]
        else:
            start=perf_counter()
            hits=await repo.text_search(conn,organization_id,workspace_id,module,text[:4000],maximum)
            metrics['text_ms']=(perf_counter()-start)*1000
            candidates=[dict(index[h['concept_id']],match='text',score=float(h['score'])) for h in hits if h['concept_id'] in index]
            # Text matches are not sufficient deterministic definitions. Vector retrieval can add candidates,
            # never automatically label a phrase true. No fabricated calibrated threshold in V1.
            if self.embeddings and catalog:
                start=perf_counter()
                stage='embedding'
                try:
                    vector=await self.embeddings.embed(text[:4000])
                    metrics['embedding_ms']=(perf_counter()-start)*1000
                    start=perf_counter()
                    stage='vector'
                    if conn is None:  # Pure unit-test repository port.
                        hits=await repo.vector_search(conn,organization_id,workspace_id,module,vector,self.embeddings.config,max(2,maximum))
                    else:
                        # A SQL failure must not poison the caller's turn transaction/FTS result.
                        async with conn.transaction():
                            hits=await repo.vector_search(conn,organization_id,workspace_id,module,vector,self.embeddings.config,max(2,maximum))
                    vector_hits=hits
                    metrics['vector_ms']=(perf_counter()-start)*1000
                    seen={c['concept_id'] for c in candidates}
                    candidates.extend(dict(index[h['concept_id']],match='vector',score=float(h['score']))
                                      for h in hits if h['concept_id'] in index and h['concept_id'] not in seen)
                except Exception:
                    metrics['embedding_ms' if stage=='embedding' else 'vector_ms']=(perf_counter()-start)*1000
                    degraded='embedding_unavailable' if stage=='embedding' else 'vector_search_unavailable'
            elif catalog:
                degraded='embedding_not_configured'
        ambiguous=not bool(exact) or len(exact)!=1
        if observe_unknown and not exact and query:
            await repo.observe(conn,organization_id,workspace_id,module,hashlib.sha256(query.encode()).hexdigest())
        rejected = []
        # Explicit cross-domain contradictions remain a veto during an embedding
        # outage or an empty FTS result; no global plan may replace them.
        requires_clarification = bool(not exact and catalog and all(
            candidate_scope(c, text)['decision'] == 'incompatible' for c in catalog))
        accepted = []
        for candidate in candidates:
            assessment = candidate_scope(candidate, text)
            # Exact, published full-expression aliases keep their approved meaning.
            # Approximate FTS/vector retrieval must establish compatible scope first.
            if (candidate['match'] not in {'code', 'alias'} and assessment['decision'] != 'compatible'):
                rejected.append(dict(semantic_code=candidate['semantic_code'], match=candidate['match'], **assessment))
                requires_clarification |= candidate['match'] == 'text'
            else:
                accepted.append(candidate)
        candidates = accepted
        interpretation_concepts = [c for c in candidates if c['match'] in {'code', 'alias', 'text'}][:maximum]
        policy = self.vector_policy
        ranking = {'calibration_id': policy.calibration_id if policy else None, 'vector_eligible': False}
        if policy and len(vector_hits) >= 2:
            score, runner_up = float(vector_hits[0]['score']), float(vector_hits[1]['score'])
            ranking.update(top_score=score, margin=score-runner_up,
                           minimum_score=policy.minimum_score, minimum_margin=policy.minimum_margin)
            if score >= policy.minimum_score and score-runner_up >= policy.minimum_margin:
                best_id = vector_hits[0]['concept_id']
                best = next((c for c in candidates if c['concept_id'] == best_id), None)
                ranking['vector_eligible'] = best is not None
                if best is None and best_id in index:
                    # Never rerank the runner-up after a semantic veto.
                    requires_clarification = True
                if best and best not in interpretation_concepts:
                    interpretation_concepts.append(best)
        context_ids = {r.get('concept_id') for r in (context or {}).get('semantic_references', [])}
        context_concepts = []
        for c in catalog:
            if c['concept_id'] not in context_ids:
                continue
            assessment = candidate_scope(c, text)
            if assessment['decision'] == 'incompatible':
                rejected.append(dict(semantic_code=c['semantic_code'], match='context', **assessment))
                requires_clarification = True
            else:
                context_concepts.append(c)
        context_concepts = context_concepts[:maximum]
        ambiguous = ambiguous or requires_clarification
        # Only IDs from the authorized current catalog reach this reader. Preserve evidence
        # for approximate interpretations and followups, not just exact first-turn matches.
        evidence_reader = getattr(repo, 'relation_evidence', None)
        if evidence_reader:
            evidence_by_version = {}
            for c in candidates[:maximum] + interpretation_concepts[:maximum] + context_concepts:
                key = (c['concept_id'], c['version'])
                if key not in evidence_by_version:
                    evidence = await evidence_reader(conn, *key)
                    evidence_by_version[key] = {'entities': evidence['entities'][:5], 'rules': evidence['rules'][:5]}
                c['related_evidence'] = evidence_by_version[key]
        return {'concepts':candidates[:maximum], 'interpretation_concepts':interpretation_concepts[:maximum],
                'ranking':ranking, 'context_concepts':context_concepts,
                'semantic_guard':dict(requires_clarification=requires_clarification, rejected=rejected),
                'ambiguous':ambiguous if candidates or requires_clarification else False,
                'status': 'candidate' if candidates and ambiguous else 'resolved' if candidates else 'unknown',
                'degraded':degraded,'timings':metrics}


def luna_context(result):
    """Bounded data, not instructions. Capability links never confer availability or permissions."""
    return {'status':result['status'],'requires_disambiguation':result['ambiguous'],
            'semantic_guard':result.get('semantic_guard', {}),
            'conversation_concepts':[{k:c[k] for k in ('concept_id','semantic_code','version','definition','operational_context')}
                                     | {'related_evidence':c.get('related_evidence',{})}
                                     for c in result.get('context_concepts', [])],
            'concepts':[{k:c[k] for k in ('concept_id','semantic_code','version','canonical_name','definition',
                        'concept_type','operational_context','approval_status','capability_links','match','score')}
                       | {'aliases':c['aliases'][:12], 'related_evidence':c.get('related_evidence',{})} for c in result.get('interpretation_concepts', result['concepts'])]}

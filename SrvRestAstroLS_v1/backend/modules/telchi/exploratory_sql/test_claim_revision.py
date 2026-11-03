"""Controller-level evidence of reconsideration, new query and no-progress stop."""
import asyncio
import threading
from dataclasses import replace
from .validator import validate

import pytest

from . import adaptive_research as runner
from .adaptive_verifier import reconstruct
from .claim_evidence import EvidenceRegistry
from .contracts import SecurityDecision, Decision
from .foundation import START, END
from .test_adaptive_research import fixture_results
from .test_claim_evidence import claim_for, observe


@pytest.mark.parametrize('ignore', [False, True])
def test_false_causal_hypothesis_feedback_then_revision_or_safe_stop(monkeypatch, ignore):
    ctx, refs = fixture_results()
    tables, _ = reconstruct(ctx, refs)
    synthetic = EvidenceRegistry(ctx, tables, (START, END))
    seen, executions = [], []
    class Probe:
        calls = []
        def __init__(self, **kwargs): pass
        async def next(self, *args, **kwargs): return {'ready': True}
    class Model:
        calls = []
        def __init__(self): self.rejected = None
        async def next(self, payload, **kwargs):
            seen.append(payload)
            feedback = [o for o in payload['observations'] if o.get('status') == 'INDEPENDENT_VERIFICATION_DISCREPANCY']
            successful = [o for o in payload['observations'] if o.get('evidence_manifest')]
            if not successful or (feedback and not ignore and len(successful) == 1):
                return dict(action='query', sql=('SELECT count(DISTINCT doc_entry) AS docs FROM sales_operation' if feedback else 'SELECT sum(line_total) AS money FROM sales_operation'),
                    objective='test', justification='contrast the rejected mechanism with document population' if feedback else 'initial measurement',
                    requested_sources=['sales_operation'], expected_grain='total', expected_result='one row', candidate_relations=[],
                    hypothesis='The null channel is caused by the seller' if not feedback else 'Cause not established; measure documents instead',
                    prior_observation_interpretation='Classifier rule/version is missing' if feedback else '',
                    hypothesis_state='CONTRADICTED' if feedback else 'OPEN', evidence_turns=[1] if feedback else [])
            if not feedback or ignore:
                self.rejected = self.rejected or claim_for(successful[0]['evidence_manifest'], kind='causal', text='Seller category caused the null channel')
                return dict(action='final', answer='A false causal explanation.', claims=[self.rejected])
            return dict(action='final', answer='One document, cause unproven.',
                claims=[claim_for(successful[-1]['evidence_manifest'], value='1')], hypothesis_state='INSUFFICIENT')
    class Executor:
        def __init__(self, context, **kwargs): self.n=0; self.cancel=threading.Event()
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, p, context):
            if p.objective == 'independent_reference':
                r = refs[self.n]; self.n += 1
            else:
                executions.append(p)
                _, _, r = observe(synthetic, p.sql)
                _, q = validate(p, context)
                r = replace(r, query_id=q.query_id, evidence=(q.context_digest,))
            return SecurityDecision(Decision.ALLOW, 'fixture'), r
    monkeypatch.setattr(runner, 'LunaSQL', Probe)
    report = {}
    asyncio.run(runner.run(report, lambda _: None, luna=Model(), executor_factory=Executor))
    assert report['final_reviews'][0]['claim_verifications'][0]['match'] is False
    assert len(report['controller_feedback']) == 1
    assert len(executions) == (1 if ignore else 2)
    assert report['status'] == ('PARTIAL' if ignore else 'VERIFIED_WITH_LIMITATIONS')
    assert 'A false causal explanation' not in report['business_answer']
    if not ignore:
        assert report['turns'][1]['hypothesis_state'] == 'CONTRADICTED'
        assert 'Documentos únicos: 1' in report['business_answer']
    else:
        assert report['hypothesis_revision']['repeated_without_progress']


def test_bounded_compaction_keeps_row_ids_aligned_and_flags_truncation():
    manifest = {'row_ids': list(map(str, range(30))), 'columns': [], 'limitations': runner.LIMITS + ('result-specific warning',)}
    payload = dict(observations=[dict(rows=[['x'*1500] for _ in range(30)], evidence_manifest=manifest, truncated=False)])
    compact = runner.bounded_payload(payload)
    assert len(compact['observations'][0]['rows']) == 3
    assert compact['observations'][0]['evidence_manifest']['row_ids'] == ['0', '1', '2']
    assert compact['observations'][0]['truncated']
    assert compact['observations'][0]['evidence_manifest']['limitations'] == ('result-specific warning',)
    assert compact['evidence_limitations'] == runner.LIMITS
    assert len(payload['observations'][0]['rows']) == 30

"""Offline batching regressions: same query budgets, observations and controls."""
import asyncio
import threading
from decimal import Decimal

import pytest

from . import adaptive_research as runner
from .contracts import Column, Decision, ExploratoryQueryResult, SecurityDecision
from .test_adaptive_research import fixture_results
from .test_claim_evidence import claim_for
from .validator import validate


def query(sql):
    return dict(action='query', sql=sql, objective='measure', justification='question',
        requested_sources=['sales_operation'], expected_grain='total', expected_result='one row',
        candidate_relations=[], hypothesis='open', prior_observation_interpretation='',
        hypothesis_state='OPEN', evidence_turns=[])


@pytest.mark.parametrize('case', ['ok', 'failed_first', 'future_dependency', 'over_budget', 'disabled', 'missing_action', 'revoked', 'denied'])
def test_independent_batch_preserves_controls(monkeypatch, case):
    ctx, refs = fixture_results()
    calls, executions = [], []
    revoked = False
    original_authorize = runner.authorize

    def authorize(context):
        if revoked:
            raise ValueError('authorization_changed')
        return original_authorize(context)

    monkeypatch.setattr(runner, 'authorize', authorize)

    class Probe:
        calls = []
        def __init__(self, **kwargs): pass
        async def next(self, payload, **kwargs): return {'ready': True}

    class Model:
        calls = []
        async def next(self, payload, **kwargs):
            calls.append(payload)
            if len(calls) == 1:
                if case == 'missing_action':
                    return dict(coverage='COMPLETE', answer='Not executable', claims=[])
                batch = [query('SELECT sum(line_total) AS amount FROM sales_operation'),
                         query('SELECT count(*) AS n FROM sales_operation')]
                if case == 'future_dependency':
                    batch[1]['evidence_turns'] = [1]
                if case == 'over_budget':
                    batch *= ctx.effective_budget.queries + 1
                return dict(action='queries', queries=batch)
            if case == 'ok':
                manifests = [o['evidence_manifest'] for o in payload['observations'] if o.get('evidence_manifest')]
                assert len(manifests) == 2
                return dict(action='final', answer='Observed sum.', claims=[claim_for(manifests[0], value='0.30')])
            # Prove the model sees the failure before the second SQL runs.
            raise RuntimeError('test_stop_after_feedback')

    class Executor:
        def __init__(self, context, **kwargs): self.n = 0; self.cancel = threading.Event()
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, p, context):
            nonlocal revoked
            if p.objective == 'independent_reference':
                r = refs[self.n]; self.n += 1
                return SecurityDecision(Decision.ALLOW, 'test'), r
            executions.append(p)
            _, q = validate(p, ctx)
            if case == 'failed_first':
                return SecurityDecision(Decision.INVALID_QUERY, 'test_failure'), ExploratoryQueryResult(q.query_id)
            if case == 'denied':
                return SecurityDecision(Decision.DENY, 'test_denied'), ExploratoryQueryResult(q.query_id)
            if case == 'revoked':
                revoked = True
            schema = (Column('amount', 'DECIMAL(38,6)'),) if len(executions) == 1 else (Column('n', 'BIGINT'),)
            rows = ((Decimal('0.30'),),) if len(executions) == 1 else ((2,),)
            return SecurityDecision(Decision.ALLOW, 'test'), ExploratoryQueryResult(q.query_id,
                schema=schema, rows=rows, returned_count=1, source=ctx.catalog.dataset,
                publication=ctx.publication, snapshot=ctx.snapshot, evidence=(q.context_digest,), status='COMPLETED')

    monkeypatch.setattr(runner, 'LunaSQL', Probe)
    report = {}
    asyncio.run(runner.run(report, lambda _: None, luna=Model(), executor_factory=Executor,
                          allow_query_batches=case != 'disabled', compact_evidence_ids=True))
    if case in {'revoked', 'denied'}:
        assert len(calls) == len(executions) == 1
        assert report['status'] == 'BLOCKED'
        if case == 'revoked':
            assert report['reason'] == 'authorization_changed'
            assert not report['business_answer']
            assert 'turns' not in report
        else:
            assert report['reason'] == 'execution_stopped:test_denied'
        return
    assert len(calls) == 2
    assert len(executions) == (2 if case == 'ok' else 1 if case == 'failed_first' else 0)
    assert report.get('query_attempts', 0) == len(executions)
    if case == 'ok':
        assert report['status'] == 'VERIFIED_WITH_LIMITATIONS'
        assert len(report['model_events']) == 2
        assert [t['evidence_turns'] for t in report['turns']] == [[], []]
    else:
        assert report['status'] == 'BLOCKED'
        assert report['reason'] == 'test_stop_after_feedback'
        assert calls[-1]['observations']
        if case == 'missing_action':
            feedback = calls[-1]['observations'][-1]
            assert feedback['reason'] == 'explicit_action_required'
            assert '"action":"final"' in feedback['guidance']

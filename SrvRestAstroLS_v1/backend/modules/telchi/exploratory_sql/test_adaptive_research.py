"""Offline regressions for adaptive autonomy, disclosure and independent arithmetic."""
from dataclasses import replace
from decimal import Decimal
import threading

import pytest

from .adaptive_sources import CATALOG, context_for_run
from .adaptive_research import model_proposal, observation_rows
from .adaptive_verifier import reference_proposals, reconstruct, verify_claim, profile_relation, summarize
from .contracts import CandidateRelation, Column, Decision, ExploratoryQueryResult
from .foundation_dev import proposal
from .validator import validate


def test_large_discovered_catalog_compacts_without_losing_columns():
    from dataclasses import asdict
    from .adaptive_research import bounded_payload
    table = asdict(CATALOG.tables[0])
    tables = [dict(table, name='source_'+str(i)) for i in range(40)]
    payload = {'catalog': dict(asdict(CATALOG), tables=tables), 'observations': []}
    result = bounded_payload(payload)
    assert result['compact_catalog_protocol']
    assert len(result['catalog']['tables']) == 40
    for original, compact in zip(tables, result['catalog']['tables']):
        types = result['catalog']['column_type_dictionary']
        constraints = result['catalog']['semantic_constraint_dictionary']
        assert {k: types[v] for k,v in compact['columns'].items()} == {c['name']: c['sql_type'] for c in original['columns']}
        assert tuple(constraints[i] for i in compact['semantic_constraints']) == original['semantic_constraints']
    assert isinstance(payload['catalog']['tables'][0]['columns'], tuple)


def test_new_catalog_is_exact_not_model_owned():
    ctx = context_for_run()
    assert validate(proposal('SELECT count(*) AS n FROM sales_operation', 'sales_operation'), ctx)[1]
    bad = replace(ctx, catalog=replace(CATALOG, dataset='invented'))
    assert validate(proposal('SELECT count(*) AS n FROM sales_operation', 'sales_operation'), bad)[0].decision == Decision.DENY
    assert validate(proposal('DELETE FROM sales_operation', 'sales_operation'), ctx)[1] is None
    assert validate(proposal("SELECT * FROM read_parquet('/tmp/x')", 'sales_operation'), ctx)[1] is None
    assert validate(proposal('SELECT count(*) AS n FROM sales_operation', 'sales_operation'), replace(ctx, permissions=frozenset()))[1] is None


def test_trace_metadata_not_executable_sql():
    p = model_proposal(dict(action='query', sql='SELECT count(*) AS n FROM sales_operation',
        objective='check', justification='observed anomaly', requested_sources=['sales_operation'],
        expected_grain='total', expected_result='one row', candidate_relations=[], hypothesis='missing classification',
        prior_observation_interpretation='first', hypothesis_state='OPEN', evidence_turns=[]))
    assert validate(p, context_for_run())[1]


@pytest.mark.parametrize('sql,cap', [
    ('SELECT sum(line_total) AS amount FROM sales_operation', 30),
    ('SELECT series AS series,count(*) AS n FROM sales_operation GROUP BY series', 30),
    ('SELECT doc_num AS doc_num FROM sales_operation', 3),
    ('SELECT doc_entry AS doc_entry,sum(line_total) AS amount FROM sales_operation GROUP BY doc_entry', 3),
    ('SELECT series AS series,min(doc_num) AS sample_doc FROM sales_operation GROUP BY series', 3),
    ('WITH x AS (SELECT doc_entry AS key,sum(line_total) AS amount FROM sales_operation GROUP BY doc_entry) SELECT key AS key,sum(amount) AS amount FROM x GROUP BY key', 3),
    ("SELECT doc_num AS doc_num FROM sales_operation WHERE doc_num='sum(line_total)'", 3),
    ('WITH x AS (SELECT doc_num AS doc_num,count(*) AS n FROM sales_operation GROUP BY doc_num) SELECT doc_num AS doc_num FROM x', 3),
])
def test_disclosure_from_outer_ast_not_regex(sql, cap):
    _, q = validate(proposal(sql, 'sales_operation'), context_for_run())
    assert q
    result = ExploratoryQueryResult('x', rows=tuple((n,) for n in range(40)))
    assert len(observation_rows(q, result)) == cap


def fixture_results():
    ctx = context_for_run()
    data = {
        'sales_document': [dict(doc_entry='1', doc_num='10', doc_date='2026-08-05', currency='BS', slp_code='7', series='9',
            sales_channel_code=None, sales_channel_semantic_status=None, raw_extraction_id='extract', source_as_of='2026-09-01')],
        'sales_line': [dict(doc_entry='1', line_num=str(i), item_code='L02822', currency='BS', line_total=Decimal(v),
            raw_extraction_id='extract', source_as_of='2026-09-01') for i, v in enumerate(('0.10', '0.20'))],
        'document_metadata': [dict(doc_entry='1', user_sign='5')],
        'line_metadata': [dict(doc_entry='1', line_num=str(i), whs_code='W') for i in range(2)],
        'salesperson': [dict(slp_code='7', name='Fiction', salesperson_category_code='2', salesperson_category_name='CORPORATIVO')],
    }
    results = []
    for p in reference_proposals():
        t = next(t for t in CATALOG.tables if t.name == p.requested_sources[0])
        _, q = validate(p, ctx)
        rows = tuple(tuple(r[c.name] for c in t.columns) for r in data[t.name])
        results.append(ExploratoryQueryResult(q.query_id, schema=t.columns, rows=rows, returned_count=len(rows),
            source=CATALOG.dataset, publication=ctx.publication, snapshot=ctx.snapshot,
            evidence=(q.context_digest,), status='COMPLETED'))
    return ctx, results


def test_reference_decimal_reconciles_and_documents_not_lines():
    ctx, results = fixture_results()
    tables, summary = reconstruct(ctx, results)
    assert Decimal(summary['total_bs']) == Decimal('0.30')
    assert summary['document_count'] == 1
    assert summary['line_count'] == 2
    assert verify_claim(dict(metric='line_amount_bs', filters={'sales_channel_code': None}, value='0.30'), tables['sales_operation'])['state'] == 'VERIFIED'
    assert verify_claim(dict(metric='document_count', filters={}, value='2'), tables['sales_operation'])['match'] is False


@pytest.mark.parametrize('change', ['duplicate', 'truncated', 'binding', 'wrong_period', 'orphan'])
def test_reference_fail_closed(change):
    ctx, results = fixture_results()
    r = results[0]
    if change == 'duplicate':
        results[0] = replace(r, rows=r.rows+r.rows, returned_count=2)
    elif change == 'truncated':
        results[0] = replace(r, truncated=True)
    elif change == 'binding':
        results[0] = replace(r, snapshot='wrong')
    elif change == 'wrong_period':
        row = list(r.rows[0]); row[2] = '2026-09-05'
        results[0] = replace(r, rows=(tuple(row),))
    else:
        results[0] = replace(r, rows=(), returned_count=0)
    with pytest.raises(ValueError):
        reconstruct(ctx, results)


@pytest.mark.parametrize('value', ['NaN', 'Infinity', 'not money', None, 0.3])
def test_invalid_claims_do_not_certify(value):
    assert verify_claim(dict(metric='line_amount_bs', filters={}, value=value), [])['state'] == 'UNVERIFIED'


def test_new_relationship_detects_fanout_without_business_promotion():
    relation = CandidateRelation('a', 'key', 'b', 'key')
    check = profile_relation(relation, {'a': [{'key': '1'}], 'b': [{'key': '1'}]*5})
    assert check['multiplication_detected'] and check['inner_join_pairs'] == 5
    assert check['state'] == 'INVESTIGATIVE'


@pytest.mark.parametrize('premature', [False, True])
@pytest.mark.parametrize('mismatch', [False, True])
def test_controller_accepts_sufficient_first_query_then_final(monkeypatch, premature, mismatch):
    import asyncio
    from . import adaptive_research as runner
    from .contracts import SecurityDecision
    ctx, refs = fixture_results()
    seen = []
    class Probe:
        calls = []
        def __init__(self, **kwargs): pass
        async def next(self, payload, **kwargs): return {'ready': True}
    class Model:
        calls = []
        async def next(self, payload, **kwargs):
            seen.append(payload)
            if premature and len(seen) == 1:
                return dict(action='final', answer='Need observations first', claims=[])
            if len(seen) == (2 if premature else 1):
                return dict(action='query', sql='SELECT sum(line_total) AS amount FROM sales_operation',
                    objective='measure', justification='question', requested_sources=['sales_operation'],
                    expected_grain='total', expected_result='one row', candidate_relations=[], hypothesis='open',
                    prior_observation_interpretation='', hypothesis_state='OPEN', evidence_turns=[])
            reviewed = any(h.get('status') == 'INDEPENDENT_VERIFICATION_DISCREPANCY' for h in payload['observations'])
            from .test_claim_evidence import claim_for
            manifest = next(o['evidence_manifest'] for o in payload['observations'] if o.get('evidence_manifest'))
            claim = claim_for(manifest, value='2.30' if mismatch and not reviewed else '0.30')
            return dict(action='final', answer='Bs 0,30. Causa no acreditada.', claims=[claim])
    class Executor:
        def __init__(self, context, **kwargs): self.n=0; self.cancel=threading.Event()
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, p, context):
            if p.objective == 'independent_reference':
                r = refs[self.n]; self.n += 1
            else:
                _, q = validate(p, ctx)
                r = ExploratoryQueryResult(q.query_id, schema=(Column('amount', 'DECIMAL(38,6)'),),
                    rows=((Decimal('0.30'),),), returned_count=1, source=CATALOG.dataset,
                    publication=ctx.publication, snapshot=ctx.snapshot, evidence=(q.context_digest,), status='COMPLETED')
            return SecurityDecision(Decision.ALLOW, 'test'), r
    monkeypatch.setattr(runner, 'LunaSQL', Probe)
    report = {}
    asyncio.run(runner.run(report, lambda _: None, luna=Model(), executor_factory=Executor))
    assert len(report['turns']) == 1  # no artificial minimum and no forced three-query route
    assert report['status'] == 'VERIFIED_WITH_LIMITATIONS'
    assert seen[0]['observations'] == []  # controls/oracles never enter model history
    assert next(h for h in seen[-1]['observations'] if h.get('status') == 'COMPLETED')['rows'] == ((Decimal('0.30'),),)
    assert len(seen) == (3 if premature else 2) + int(mismatch)
    if mismatch:
        feedback = seen[-1]['observations'][-1]
        assert feedback['status'] == 'INDEPENDENT_VERIFICATION_DISCREPANCY'
        assert all('expected' not in c for c in feedback['rejected_claims'])
        assert len(report['final_reviews']) == 2
        assert report['final_reviews'][0]['claim_verifications'][0]['match'] is False
    if premature:
        assert seen[1]['observations'][0]['status'] == 'PROTOCOL_FEEDBACK'
        assert 'SELECT' not in seen[1]['observations'][0]['reason']


def test_join_denial_closes_execution_even_if_model_proposes_more_sql(monkeypatch):
    import asyncio
    from . import adaptive_research as runner
    from .contracts import SecurityDecision
    ctx, refs = fixture_results()
    class Probe:
        calls = []
        def __init__(self, **kwargs): pass
        async def next(self, payload, **kwargs): return {'ready': True}
    class Model:
        calls = []
        async def next(self, payload, **kwargs):
            return dict(action='query', sql='SELECT count(*) AS n FROM sales_operation',
                objective='test', justification='test', requested_sources=['sales_operation'],
                expected_grain='total', expected_result='one row', candidate_relations=[], hypothesis='open',
                prior_observation_interpretation='', hypothesis_state='OPEN', evidence_turns=[])
    executions = []
    class Executor:
        def __init__(self, context, **kwargs): self.n=0; self.cancel=threading.Event()
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, p, context):
            if p.objective == 'independent_reference':
                r=refs[self.n]; self.n+=1
                return SecurityDecision(Decision.ALLOW, 'test'), r
            executions.append(p)
            return SecurityDecision(Decision.RESOURCE_BLOCKED, 'join_pair_budget'), ExploratoryQueryResult('x')
    monkeypatch.setattr(runner, 'LunaSQL', Probe)
    report = {}
    asyncio.run(runner.run(report, lambda _: None, luna=Model(), executor_factory=Executor))
    assert len(executions) == 1
    assert report['status'] == 'BLOCKED'
    assert report['reason'] == 'query_phase_closed_no_further_sql'

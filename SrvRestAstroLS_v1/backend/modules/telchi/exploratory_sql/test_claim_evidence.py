"""Adversarial checks on isolated in-memory data; never touch Foundation."""
from dataclasses import replace
from decimal import Decimal

import pytest

from .claim_evidence import EvidenceRegistry, verification_feedback
from .contracts import Column, ExploratoryQueryResult, ResolvedRelation, RelationState
from .foundation import START, END
from .foundation_dev import proposal
from .test_adaptive_research import fixture_results
from .adaptive_verifier import reconstruct
from .validator import validate


def claim_for(manifest, index=0, row=0, value='0.30', **changes):
    col = manifest['columns'][index]
    c = dict(kind='measure', result_id=manifest['result_id'], column_id=col['column_id'],
        row_id=manifest['row_ids'][row], value=value, metric=col['metric'], unit=col['unit'], currency=col['currency'],
        grain='document' if col['metric'] == 'document_count' else 'commercial_line', classification='observed',
        publication=manifest['publication'], snapshot=manifest['snapshot'], temporal_scope=list(manifest['temporal_scope']))
    return c | changes


@pytest.fixture
def registry():
    ctx, refs = fixture_results()
    tables, _ = reconstruct(ctx, refs)
    # Distinct second document so denominator and subsequent contradiction are meaningful.
    tables['sales_operation'].append(dict(tables['sales_operation'][0], doc_entry='2', line_num='0',
        sales_channel_code='X', sales_channel_semantic_status='SUPPORTED', line_total=Decimal('0.70')))
    return EvidenceRegistry(ctx, tables, (START, END))


def observe(registry, sql):
    """Controlled executor fixture, distinct from the Python reference evaluator."""
    import duckdb
    ctx = registry.context
    _, q = validate(proposal(sql, 'sales_operation'), ctx)
    assert q
    columns = next(t.columns for t in ctx.catalog.tables if t.name == 'sales_operation')
    with duckdb.connect(':memory:', config={'threads': '1', 'enable_external_access': 'false'}) as db:
        db.execute('CREATE TABLE sales_operation (' + ','.join(c.name+' '+c.sql_type for c in columns) + ')')
        db.executemany('INSERT INTO sales_operation VALUES (' + ','.join('?' for _ in columns) + ')',
            [tuple(r[c.name] for c in columns) for r in registry.tables['sales_operation']])
        cursor = db.execute(q.generated_sql, {p.name: p.value for p in q.parameters})
        schema = tuple(Column(d[0], str(d[1]), True) for d in cursor.description)
        rows = tuple(cursor.fetchall())
    result = ExploratoryQueryResult(q.query_id, schema=schema, rows=rows, returned_count=len(rows),
        source=ctx.catalog.dataset, publication=ctx.publication, snapshot=ctx.snapshot,
        evidence=(q.context_digest,), status='COMPLETED')
    return registry.register(q, result, rows), q, result


def total(registry):
    return observe(registry, 'SELECT sum(line_total) AS arbitrary_presentation FROM sales_operation')[0]


def test_alias_cannot_impersonate_source_or_metric(registry):
    m = total(registry)
    assert m['columns'][0]['source_or_calculation'] == 'CALCULATION'
    assert m['columns'][0]['metric'] == 'line_amount_bs'
    assert registry.verify(claim_for(m, value='1.00'))['match']
    assert not registry.verify(claim_for(m, value='1.00', column_id='arbitrary_presentation'))['match']
    disguised, _, _ = observe(registry, "SELECT COALESCE(sales_channel_code,'OFFICIAL') AS sales_channel_code,count(*) AS n FROM sales_operation GROUP BY COALESCE(sales_channel_code,'OFFICIAL')")
    assert disguised['columns'][0]['source_or_calculation'] == 'CALCULATION'
    assert disguised['columns'][0]['classification'] == 'DERIVED_NOT_OFFICIAL'


def test_calculated_classification_is_not_official(registry):
    m, _, _ = observe(registry, "SELECT CASE WHEN sales_channel_code IS NULL THEN 'SIN_CANAL' ELSE sales_channel_code END AS channel,sum(line_total) AS money FROM sales_operation GROUP BY CASE WHEN sales_channel_code IS NULL THEN 'SIN_CANAL' ELSE sales_channel_code END ORDER BY money")
    assert registry.verify(claim_for(m, 1, value='0.30'))['match']
    check = registry.verify(claim_for(m, 1, value='0.30', classification='official'))
    assert not check['match'] and 'official' in check['reason']


def test_correct_amount_wrong_business_concept(registry):
    c = claim_for(total(registry), value='1.00', metric='net_collections')
    assert registry.verify(c)['reason'] == 'measure_unit_currency_or_grain_mismatch'


def test_wrong_percentage_denominator(registry):
    m, _, _ = observe(registry, 'SELECT sales_channel_code AS ch,sum(line_total) AS amount FROM sales_operation GROUP BY sales_channel_code ORDER BY amount')
    a = claim_for(m, 1, 0, '0.30')
    b = claim_for(m, 1, 1, '0.70')
    c = dict(kind='share_of_universe', metric='share_of_universe', unit='percent', currency=None,
             grain='commercial_line', value='42.86', dependencies=[a, b])
    assert registry.verify(c)['reason'] == 'incorrect_denominator_or_population'
    c.update(value='30.00', dependencies=[a, claim_for(total(registry), value='1.00')])
    assert registry.verify(c)['match']
    assert not registry.verify(c | {'snapshot': 'changed'})['match']
    assert not registry.verify(c | {'classification': 'official'})['match']
    assert not registry.verify(c | {'value': '30.004'})['match']
    assert not registry.verify(c | {'value': 30})['match']


@pytest.mark.parametrize('right_rows', [2, 5])
def test_join_duplication_and_invoice_multiple_movements(registry, right_rows):
    m = total(registry)
    entry = registry.entries[m['result_id']]
    manifest, q, result, visible, node, source = entry
    registry.tables['movements'] = [{'doc_entry': '1'} for _ in range(right_rows)]
    relation = ResolvedRelation(('sales_operation', 'doc_entry'), ('movements', 'doc_entry'), RelationState.INVESTIGATIVE)
    # Mutation is confined to the adversarial fixture, simulating a post-join result.
    registry.entries[m['result_id']] = (manifest, replace(q, relations=(relation,)), result, visible, node, source)
    assert registry.verify(claim_for(m, value='1.00'))['reason'] == 'join_multiplication_detected'


@pytest.mark.parametrize('right,expected', [('lines', '300.00'), ('movements', '600.00')])
def test_actual_readonly_synthetic_joins_cannot_multiply_invoice_facts(right, expected):
    from .synthetic import synthetic_context, ROWS
    from .direct_readonly import DirectReadonlyExecutor
    from .contracts import ExploratoryQueryProposal, CandidateRelation
    ctx = synthetic_context()
    p = ExploratoryQueryProposal(f'SELECT sum(i.amount) AS line_amount_bs FROM invoices i LEFT JOIN {right} r ON i.id=r.invoice_id',
        'adversarial', 'test invoice multiplication', ('invoices', right), 'invoice', 'sum',
        candidate_relations=(CandidateRelation('invoices', 'id', right, 'invoice_id'),))
    _, q = validate(p, ctx)
    assert q
    with DirectReadonlyExecutor(ctx) as executor:
        _, result = executor.execute(p, ctx)
    assert result.rows == ((Decimal(expected),),)
    tables = {t.name: [dict(zip((c.name for c in t.columns), r)) for r in ROWS[t.name]] for t in ctx.catalog.tables}
    evidence = EvidenceRegistry(ctx, tables, ('synthetic_start', 'synthetic_end'))
    manifest = evidence.register(q, result, result.rows)
    check = evidence.verify(claim_for(manifest, value=expected))
    assert check['reason'] == 'join_multiplication_detected' and not check['match']


@pytest.mark.parametrize('change', [{'unit': 'kg'}, {'currency': 'USD'}, {'grain': 'document'}])
def test_incompatible_units_currency_grain(registry, change):
    assert not registry.verify(claim_for(total(registry), value='1.00', **change))['match']


def test_nonexistent_result_and_column_and_row(registry):
    m = total(registry)
    for field in ('result_id', 'column_id', 'row_id'):
        c = claim_for(m, value='1.00', **{field: 'invented'})
        assert not registry.verify(c)['match']


def test_snapshot_change(registry):
    assert registry.verify(claim_for(total(registry), value='1.00', snapshot='1409'))['reason'] == 'claim_foundation_version_mismatch'


def test_later_observation_contradicts_plausible_hypothesis(registry):
    # Initial observation discovers missing classification. Hypothesis: all sales are missing.
    missing, _, _ = observe(registry, 'SELECT sum(line_total) AS amount FROM sales_operation WHERE sales_channel_code IS NULL')
    universe = total(registry)
    c = dict(kind='hypothesis_equal', dependencies=[claim_for(missing), claim_for(universe, value='1.00')])
    check = registry.verify(c)
    assert check['reason'] == 'hypothesis_contradicted_by_observation'
    assert [e['observed'] for e in check['evidence']] == ['0.300000', '1.000000']
    feedback = verification_feedback([check])
    assert feedback['rejected_claims'][0]['evidence']
    assert 'expected' not in feedback['rejected_claims'][0]


def test_correlation_never_promotes_causality_and_raw_prose_never_delivered(registry):
    m = total(registry)
    false = claim_for(m, value='1.00', kind='causal', text='The seller caused the missing channel.')
    check = registry.verify(false)
    assert not check['match'] and 'classifier_version_missing' in check['reason']
    answer = registry.render([check, registry.verify(claim_for(m, value='1.00'))])
    assert 'The seller caused' not in answer
    assert '1.00' in answer and m['result_id'] in answer


def test_unknown_shapes_are_not_inferred_from_alias(registry):
    m, _, _ = observe(registry, 'WITH x AS (SELECT sum(line_total) AS revenue FROM sales_operation) SELECT revenue AS line_amount_bs FROM x')
    assert m['columns'][0]['metric'] is None
    assert not registry.verify(claim_for(m, value='1.00'))['match']


def test_unverified_calculations_are_not_rendered_as_group_facts(registry):
    m, _, _ = observe(registry, 'SELECT sum(line_total) AS money,min(doc_date) AS unverified_date FROM sales_operation')
    answer = registry.render([registry.verify(claim_for(m, value='1.00'))])
    assert '2026-08-05' not in answer
    assert 'unverified_date' not in answer


def test_duplicate_expression_has_distinct_ids_but_aliases_do_not_define_identity(registry):
    m, _, _ = observe(registry, 'SELECT sum(line_total) AS a,sum(line_total) AS b FROM sales_operation')
    assert m['columns'][0]['column_id'] != m['columns'][1]['column_id']
    renamed = total(registry)
    assert m['columns'][0]['column_id'] == renamed['columns'][0]['column_id']


def test_result_integrity_and_disclosure_boundaries(registry):
    m, q, r = observe(registry, 'SELECT sum(line_total) AS m FROM sales_operation')
    with pytest.raises(ValueError, match='binding'):
        registry.register(q, replace(r, snapshot='changed'), r.rows)
    hidden = registry.register(q, r, ())
    assert hidden['row_ids'] == ()
    assert not registry.verify(dict(claim_for(m, value='1.00'), result_id=hidden['result_id']))['match']

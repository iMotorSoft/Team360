"""Shared investigator regressions, independent of any business test question."""
from dataclasses import replace
import duckdb
import pytest

from .ask import requested_measure
from .authorized_foundation import EffectiveScope, SourcePolicy, ResearchBinding, DiscoveredSource
from .contracts import Column, Budget, DevResearchBudget, Decision, ExploratoryQueryProposal, TypedParameter
from .validator import validate
from .test_authorized_foundation import setup, proposal
from .authorized_foundation import AuthorizedFoundationExecutor


@pytest.mark.parametrize('text,previous,expected', [
    ('Importe comercial; no lo presentes como venta neta', None, 'commercial_line'),
    ('No calcules ventas netas', 'net_document', None),
    ('Sin importe bruto; calculá el neto', None, 'net_document'),
    ('No ventas netas, sino importe comercial', None, 'commercial_line'),
    ('Ventas netas de agosto', None, 'net_document'),
    ('¿Y en septiembre?', 'net_document', 'net_document'),
    ('Importe bruto y no neto', None, 'gross_document'),
])
def test_measure_negation(text, previous, expected):
    assert requested_measure(text, previous) == expected


@pytest.mark.parametrize('typ', ['TIMESTAMP', 'DATE', 'VARCHAR'])
@pytest.mark.parametrize('predicate', [
    "doc_date >= '2026-08-01' AND doc_date < '2026-09-01'",
    "'2026-08-01' <= doc_date",
    "doc_date BETWEEN '2026-08-01' AND '2026-08-31'",
    'doc_date >= $start',
])
def test_temporal_parameters_execute_for_catalog_type(typ, predicate):
    scope = EffectiveScope('u', 'o', 'w', frozenset({'read'}))
    source = DiscoveredSource('events', 'events', (Column('doc_date', typ),), ())
    binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope,
        publication='fixture', snapshot=1, sources=(source,),
        policies=(SourcePolicy('events', 'read', 'o', 'w', None, True),), investigation_id='test')
    try:
        p = ExploratoryQueryProposal('SELECT COUNT(*) AS n FROM events WHERE ' + predicate,
            'test', 'test', ('events',), 'aggregate', 'observed',
            parameters=((TypedParameter('start', 'VARCHAR', '2026-08-01'),) if '$start' in predicate else ()))
        decision, q = validate(p, binding.context)
        assert decision.decision == Decision.ALLOW, decision
        assert '2026-08-01' not in q.generated_sql
        with duckdb.connect(':memory:', config={'threads': '1'}) as db:
            db.execute(f'CREATE TABLE events(doc_date {typ})')
            db.execute("INSERT INTO events VALUES ('2026-08-15')")
            assert db.execute(q.generated_sql, {p.name:p.value for p in q.parameters}).fetchall() == [(1,)]
    finally:
        binding.close()


def test_dev_profile_keeps_base_and_security_limits():
    b = DevResearchBudget()
    assert (b.queries, b.query_seconds, b.total_seconds, b.result_rows) == (12, 5, 30, 500)
    for key in ('threads', 'process_memory_bytes', 'concurrency', 'max_join_pairs'):
        assert getattr(b, key) == getattr(Budget(), key)
    assert b.intersect(Budget()).queries == 5
    with pytest.raises(ValueError):
        DevResearchBudget(total_seconds=900)


def test_binder_feedback_is_closed_and_redacted(setup):
    binding = setup.bind()
    try:
        with AuthorizedFoundationExecutor(binding.context, reader=setup.reader) as executor:
            decision, result = executor.execute(proposal('SELECT SUM(doc_entry) AS n FROM sales_line'), binding.context)
            assert decision.decision == Decision.INVALID_QUERY
            assert decision.reason == 'sql_binding_error_check_catalog_types_and_grouping'
            assert 'secret' not in str(result)
    finally:
        binding.close()

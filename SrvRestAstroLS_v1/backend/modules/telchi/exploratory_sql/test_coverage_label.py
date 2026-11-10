"""The final coverage label follows the recovered population, not the page.

A fully recovered list presented progressively is not missing population data.
No model relabel or SQL is needed; temporal and business certification stay separate.
"""
import asyncio
import threading
from dataclasses import asdict
from decimal import Decimal

from . import adaptive_research as runner
from .ask_sources import context_for_run
from .contracts import (Column, Decision, ExploratoryQueryResult, SQLResultEvidence,
                        SecurityDecision)
from .validator import validate

QUESTION = ('¿Qué clientes compraron ácido nítrico en todas sus presentaciones en octubre de 2026?')


def query(sql):
    return dict(action='query', sql=sql, objective='list', justification='question',
                requested_sources=['sales_operation'], expected_grain='one row per account',
                expected_result='all accounts', candidate_relations=[], hypothesis='open',
                prior_observation_interpretation='', hypothesis_state='OPEN', evidence_turns=[])


class StubRegistry:
    """Minimal recovery-aware registry; execution is the real validator/executor."""

    def __init__(self, context):
        self.context, self.entries, self.audit = context, {}, []
        self.question = None
        self.population_recovery = {}
        self.population_pages = {}
        self.presentation_pages = {'r': [1, 2]}

    def register(self, query, result, visible_rows):
        manifest = SQLResultEvidence('r', query.query_id, 'v', self.context.catalog.dataset,
            self.context.publication, self.context.snapshot, 'group_of_source_rows', (), ('r1', 'r2', 'r3'),
            (), ('2026-10-01', '2026-11-01'), 'currency COMPARE_EQUAL "BS"',
            ('card_code', 'customer_name'), ())
        self.entries['r'] = (manifest, query, result, tuple(visible_rows), {}, 'sales_operation')
        self.population_recovery = {'r': dict(complete=True, recovered_records=311, pages=3,
            entity_column='card_code', distinct_entities=311)}
        return dict(asdict(manifest), population_recovery=self.population_recovery['r'])

    def verify(self, claim):
        return dict(claim=claim, state='EXECUTOR_OBSERVED_WITH_LIMITATIONS', match=True,
                    reason='test', limitations=())

    def final_feedback(self, claims, *, net_required=False):
        return None

    def render(self, checks):
        return 'Universo recuperado completo: 311 registros (311 cuentas SAP distintas)'

    def close(self):
        pass


def run(model, factory=None, context=None):
    factory = factory or StubRegistry
    context = context or context_for_run()

    class Probe:
        calls = []
        def __init__(self, **kwargs): pass
        async def next(self, payload, **kwargs): return {'ready': True}

    class Executor:
        def __init__(self, ctx, **kwargs): self.cancel = threading.Event()
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, p, ctx, cancel=None):
            _, q = validate(p, ctx)
            rows = ((Decimal('10'),), (Decimal('20'),), (Decimal('30'),))
            return (SecurityDecision(Decision.ALLOW, 'test'),
                    ExploratoryQueryResult(q.query_id, schema=(Column('amount', 'DECIMAL(38,6)'),),
                        rows=rows, returned_count=3, source=ctx.catalog.dataset,
                        publication=ctx.publication, snapshot=ctx.snapshot,
                        evidence=(q.context_digest,), status='COMPLETED'))

    original = runner.LunaSQL
    runner.LunaSQL = Probe
    try:
        report = {}
        asyncio.run(runner.run(report, lambda value: None, luna=model, executor_factory=Executor,
            question=QUESTION, context=context,
            registry_factory=factory, compact_evidence_ids=False))
        return report
    finally:
        runner.LunaSQL = original


class Model:
    def __init__(self, labels):
        self.labels, self.calls = labels, []

    async def next(self, payload, **kwargs):
        self.calls.append(payload)
        if len(self.calls) == 1:
            return query('SELECT item_code, count(*) AS lines FROM sales_operation '
                         'GROUP BY item_code ORDER BY item_code LIMIT 100')
        manifest = payload['observations'][0]['evidence_manifest']
        return dict(action='final', coverage=self.labels[len(self.calls) - 2],
                    answer='311 cuentas recuperadas; se muestran dos.',
                    claims=[dict(kind='executed_cell', result_id=manifest['result_id'],
                                 row_id=manifest['row_ids'][0], column_id='c1')])


def test_population_label_is_deterministic_without_model_relabel():
    model = Model(['PARTIAL', 'COMPLETE'])
    report = run(model)
    assert len(model.calls) == 2
    assert 'coverage_label_repairs' not in report
    assert report['population_coverage'] == 'COMPLETE'
    assert report['question_coverage'] == 'PARTIAL'
    assert report['temporal_coverage'] == 'NOT_CERTIFIED'
    assert report['business_interpretation'] == 'NOT_INDEPENDENTLY_CERTIFIED'
    assert report['population_pages'] == {}
    assert report['business_answer'].startswith('Universo recuperado completo: 311')


def test_a_stubborn_label_is_not_repaired_forever():
    model = Model(['PARTIAL', 'PARTIAL', 'PARTIAL'])
    report = run(model)
    assert len(model.calls) == 2  # Population coverage needs no model repair.
    assert 'coverage_label_repairs' not in report
    assert report['population_coverage'] == 'COMPLETE'
    assert report['question_coverage'] == 'PARTIAL'
    assert 'partes pendientes' in report['business_answer']


def test_no_repair_without_a_complete_recovered_population():
    model = Model(['PARTIAL', 'PARTIAL'])

    class Incomplete(StubRegistry):
        def register(self, query, result, visible_rows):
            manifest = super().register(query, result, visible_rows)
            self.population_recovery = {'r': dict(complete=False, recovered_records=100, pages=0)}
            return manifest

    report = run(model, factory=Incomplete)
    assert len(model.calls) == 2 and 'coverage_label_repairs' not in report
    assert report['question_coverage'] == 'PARTIAL'
    assert report['population_coverage'] == 'PARTIAL'


def test_unverified_universal_prose_cannot_become_an_audit_conclusion():
    class UniversalModel(Model):
        async def next(self, payload, **kwargs):
            value = await super().next(payload, **kwargs)
            if value['action'] == 'final':
                value['answer'] = 'Cada cliente compró las seis presentaciones.'
                value['conclusions'] = [value['answer']]
                value['prior_observation_interpretation'] = value['answer']
            return value

    report = run(UniversalModel(['COMPLETE']))
    assert report['model_answer'] == report['business_answer']
    assert 'Cada cliente' not in report['model_answer']
    assert report['model_conclusions'] == []
    assert report['final_observation_interpretation'] is None
    assert report['final_reviews'][0]['proposed_answer_state'] == 'UNVERIFIED_MODEL_PROPOSAL_NOT_EVIDENCE'
    assert report['business_interpretation'] == 'NOT_INDEPENDENTLY_CERTIFIED'


def test_unrelated_or_failed_population_cannot_certify_selected_population():
    from types import SimpleNamespace
    checks = [dict(match=True, claim=dict(result_id='accounts'))]
    registry = SimpleNamespace(population_recovery={
        'discovery': dict(complete=True, recovered_records=6),
        'accounts': dict(complete=False, recovered_records=100)})
    assert runner.population_coverage(registry, checks) == 'PARTIAL'
    assert runner.population_coverage(registry, []) == 'NOT_CERTIFIED'
    registry.population_recovery['accounts'] = dict(complete=True, recovered_records=311,
                                                   reason='continuation_scope_changed')
    assert runner.population_coverage(registry, checks) == 'PARTIAL'


def paged_entry(result_id='list', rows=10):
    from types import SimpleNamespace
    node = dict(group_expressions=[dict(class_='COLUMN_REF', type='COLUMN_REF', column_names=['item_code'])],
                select_list=[dict(class_='COLUMN_REF', type='COLUMN_REF', column_names=['item_code']),
                             dict(class_='FUNCTION', type='FUNCTION', function_name='count_star', children=[])])
    columns = [SimpleNamespace(column_id='item_code-col', alias='item_code'),
               SimpleNamespace(column_id='lines-col', alias='lines')]
    manifest = SimpleNamespace(result_id=result_id, columns=columns,
                               row_ids=tuple(f'r{index}' for index in range(rows)))
    return result_id, (manifest, None, None, tuple((index,) for index in range(rows)), node, 'sales_operation')


def test_only_the_paged_recovered_universe_is_delivered_when_unclaimed():
    from types import SimpleNamespace
    registry = SimpleNamespace(
        population_recovery={'list': dict(complete=True, pages=3, recovered_records=311),
                             'products': dict(complete=True, pages=0, recovered_records=6)},
        entries=dict([paged_entry()]))
    claims = [dict(kind='executed_cell', result_id='products', column_id='c', row_id='p')]
    synthesized = runner.recovered_population_claims(registry, claims)
    assert len(synthesized) == 10  # One identity cell per presented row, bounded.
    assert {claim['result_id'] for claim in synthesized} == {'list'}
    assert {claim['column_id'] for claim in synthesized} == {'item_code-col'}
    # A claim on that population, two paged populations or no recovered pages
    # deliver nothing: the controller never guesses which list was requested.
    assert runner.recovered_population_claims(registry, claims + synthesized) == []
    registry.population_recovery['other'] = dict(complete=True, pages=1)
    assert runner.recovered_population_claims(registry, claims) == []
    registry.population_recovery = {'list': dict(complete=True, pages=0,
                                                 recovered_records=6)}
    assert runner.recovered_population_claims(registry, claims) == []

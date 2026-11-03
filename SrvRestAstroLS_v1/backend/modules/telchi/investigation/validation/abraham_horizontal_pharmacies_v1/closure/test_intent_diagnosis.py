"""Offline characterization, not a runtime fix or an LLM accuracy evaluation."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from modules.telchi.assistant import state_engine as se
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import documentary_request_contract, fixed_ranking_request_contract

ROOT = Path(__file__).resolve().parents[8]
EVIDENCE = ROOT / 'data/reports/telchi/abraham_horizontal_pharmacies_v1/first_run/spontaneous.json'
FIT = ROOT.parent / 'LlmFit/benchmarks/telchi/conversation_state_v1'
FIXTURE = json.loads(Path(__file__).with_name('acceptance.json').read_text())


def proposal(sets, action='DIRECT_UNAVAILABLE'):
    return dict(intent='NEW_QUERY', action=action, state_delta=dict(set=sets, unset=[]), clarification=None)


def test_exact_observed_loss_precedes_normalization_and_state_engine():
    audit = json.loads(EVIDENCE.read_text())['turn']['response']['audit']
    raw = audit['interpretation_proposed']
    assert raw['state_delta']['set']['/requested_metrics'] == ['sales.net_amount']
    assert raw == fixed_ranking_request_contract(
        documentary_request_contract(deepcopy(raw), FIXTURE['question']), FIXTURE['question'])
    replay = se.process(audit['previous_state'], raw, {}, 'offline-abraham')
    assert replay['committed'] is True
    assert replay['state_after'] == audit['validated_state']
    assert audit['capability_calls'] == 0
    assert not SalesCapabilities().availability(replay['state_after']).allowed


@pytest.mark.parametrize('sets', [
    {'/metric': 'customers.distinct_buyers'},
    {'/metric': 'sales.net_amount', '/requested_metrics': ['sales.net_amount', 'customers.distinct_buyers'], '/schema_version': 2},
    {'/metric': 'sales.net_amount', '/segment': 'PHARMACY'},
    {'/metric': 'sales.net_amount', '/time_grain': 'month'},
])
def test_current_engine_cannot_encode_missing_requirements_and_does_not_partially_commit(sets):
    before = deepcopy(se.EMPTY)
    result = se.process(before, proposal(sets), {}, 'unsupported')
    assert result['committed'] is False
    assert result['state_after'] == before
    assert result['contract_error'] == 'CONTRACT_ERROR_NO_COMMIT'


def test_candidate_preserves_five_axes_without_promoting_catalog():
    from jsonschema import Draft202012Validator
    # Read-only reuse of LlmFit's existing general state schema, not a copied reducer.
    schema = json.loads((FIT / 'contracts/state.json').read_text())
    Draft202012Validator(schema).validate(FIXTURE['candidate_query'])
    q, req = FIXTURE['candidate_query'], FIXTURE['unresolved_requirements']
    assert q['filters'][0][0]['values'] == ['HORIZONTAL']
    assert req['entity']['kind'] == 'customer'
    assert req['segmentation']['focus'] == 'PHARMACY'
    assert len(q['metrics']) == 2 and 'calendar.month' in q['dimensions']
    assert q['time'] is None and req['customer_population']['confirmed'] is None
    assert FIXTURE['execution_authority'] is False
    catalog = json.loads((FIT / 'domain/catalog.json').read_text())
    assert not set(q['metrics']) & set(catalog['metrics'])


def test_reuses_existing_llmfit_count_and_ellipsis_fixture():
    fixture = json.loads((FIT / 'fixtures/TCS_001.json').read_text())
    assert fixture['title'] == 'Conteo comercial y elipsis mensual'
    assert fixture['turns'][2]['user_message'] == '¿Y agosto?'
    # DOCUMENT_COUNT is not a customer count: no fixture relabeling.
    catalog = json.loads((FIT / 'domain/catalog.json').read_text())
    assert 'DOCUMENT_COUNT@1' in catalog['metrics']


@pytest.mark.parametrize('metric,period,expected', [
    ('sales.net_amount', {'start': '2026-05-01', 'end_exclusive': '2026-06-01'}, True),
    ('sales.latest_documents', None, True),
    ('sales.coverage', None, True),
    ('sales.net_amount', None, False),
])
def test_simple_counterexamples_keep_existing_behavior(metric, period, expected):
    result = se.process(deepcopy(se.EMPTY), proposal({'/metric': metric, '/period': period}), {}, 'simple')
    assert result['committed'] is True
    assert SalesCapabilities().availability(result['state_after']).allowed is expected


def test_recorded_credit_channel_lineage_is_not_reproducible_by_current_classifier():
    from modules.telchi.datalake.executive_sales import classify_sales_channel
    evidence = json.loads(EVIDENCE.with_name('independent.json').read_text())
    rows = next(q['rows'] for q in evidence['queries'] if q['name'] == 'credit_memos_horizontal_series')
    assert {int(r['series']) for r in rows} == set(range(1269, 1281))
    assert all(classify_sales_channel(r['series'], r['user_sign']) == (None, None) for r in rows)
    # This confirms a lineage gap, not a proposed reassignment of credit notes.


def test_monthly_grain_is_not_a_month_filter():
    candidate = deepcopy(FIXTURE['candidate_query'])
    candidate['time'] = {'kind': 'PERIOD', 'periods': [
        {'start': '2026-05-01', 'end_exclusive': '2026-09-01'}], 'as_of': None}
    from jsonschema import Draft202012Validator
    Draft202012Validator(json.loads((FIT / 'contracts/state.json').read_text())).validate(candidate)
    assert candidate['dimensions'] == FIXTURE['candidate_query']['dimensions']
    assert candidate['metrics'] == FIXTURE['candidate_query']['metrics']
    assert candidate['filters'] == FIXTURE['candidate_query']['filters']

"""Offline characterization of Abraham 002. Passing tests do NOT fix the assistant."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from modules.telchi.assistant import state_engine as se
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.handler import documentary_request_contract, fixed_ranking_request_contract

ROOT = Path(__file__).resolve().parents[7]
CASE = Path(__file__).parent
EVIDENCE = ROOT / 'data/reports/telchi/abraham_citrate_distribution_v1/run01'
ACCEPTANCE = json.loads((CASE / 'acceptance.json').read_text())


def audit():
    return json.loads((EVIDENCE / 'spontaneous.json').read_text())['turn']['response']['audit']


def test_literal_question_and_unchanged_assistant():
    evidence = json.loads((EVIDENCE / 'spontaneous.json').read_text())
    assert evidence['question'] == ACCEPTANCE['question']
    assert evidence['assistant_sources_unchanged'] is True
    assert evidence['server_reaped'] is True
    assert evidence['own_processes_left_running'] == 0
    assert evidence['preflight']['model']['model'] == 'gpt-5.6-luna'


def test_recorded_interpretation_already_loses_relationships_before_engine():
    a = audit()
    raw = a['interpretation_proposed']
    assert raw == fixed_ranking_request_contract(
        documentary_request_contract(deepcopy(raw), ACCEPTANCE['question']), ACCEPTANCE['question'])
    replay = se.process(a['previous_state'], raw, {}, 'offline-abraham002')
    assert replay['committed'] is True
    assert replay['state_after'] == a['validated_state']
    state = replay['state_after']
    assert state['branches'] == ['La Paz', 'Cochabamba']
    assert state['product_search_text'] == 'Citrato de magnesio'
    assert 'L&S' not in json.dumps(state, ensure_ascii=False)
    assert state['selected_item_codes'] == []
    assert state['period'] is None


def test_blocking_condition_is_product_catalog_filter_not_missing_text():
    state = deepcopy(audit()['validated_state'])
    assert state['product_search_text']
    blocked = SalesCapabilities().availability(state)
    assert not blocked.allowed and blocked.category == 'CAPABILITY_MISSING'
    # Counterfactual offline only. No mutation of recorded intent, no execution.
    state['branches'] = []
    assert SalesCapabilities().availability(state).allowed
    assert audit()['execution_status'] == 'not_executed'
    assert audit()['capability_calls'] == 0
    assert audit()['execution_result'] is None


@pytest.mark.parametrize('path,value', [
    ('/distribution_relationships', ACCEPTANCE['literal_requirements']['relationships']),
    ('/sales_level', 'sell_in'),
    ('/time_grain', 'month'),
    ('/geographies', ['La Paz', 'Cochabamba']),
])
def test_current_contract_rejects_missing_axes_atomically(path, value):
    before = deepcopy(se.EMPTY)
    proposal = dict(intent='NEW_QUERY', action='DIRECT_UNAVAILABLE',
                    state_delta={'set': {path: value}, 'unset': []}, clarification=None)
    result = se.process(before, proposal, {}, 'unsupported-axis')
    assert not result['committed']
    assert result['state_after'] == before


def test_acceptance_preserves_literal_vs_analyst_added_requirements():
    assert ACCEPTANCE['execution_authority'] is False
    assert ACCEPTANCE['literal_requirements']['period'] is None
    assert ACCEPTANCE['literal_requirements']['metrics_explicit'] == []
    rel = ACCEPTANCE['literal_requirements']['relationships']
    assert rel[0]['territory'] == 'La Paz' and rel[0]['distribution'] == 'own'
    assert rel[1]['territory'] == 'Cochabamba' and rel[1]['operator'] == 'L&S'
    assert ACCEPTANCE['analysis_requirements']['window_is_not_in_original_question']
    assert {p['catalog_unit'] for p in ACCEPTANCE['primary_product_candidates']} == {'KG', 'BOLSA', 'FCO'}


def test_independent_evidence_is_pinned_and_has_no_final_query_errors():
    for filename in ('discovery_corrected.json','verification_corrected.json','geography.json'):
        data = json.loads((EVIDENCE / filename).read_text())
        assert data['read_only'] is True
        assert data['publication_unchanged'] is True
        assert data['foundation']['ducklake_snapshot_id'] == 1408
        assert not any('error' in q for q in data['queries'])
    rows = {q['name']: q['rows'] for q in json.loads((EVIDENCE / 'verification_corrected.json').read_text())['queries']}
    assert rows['sales_duplicate_documents'] == []
    assert rows['sales_duplicate_target_lines'] == []
    assert rows['sales_orphan_target_lines'] == [{'orphans': 0}]
    assert rows['legacy_customer_uniqueness'][0]['row_count'] == rows['legacy_customer_uniqueness'][0]['codes']
    assert rows['credit_memo_LS_monthly'] == []
    assert [(r['period_month'],r['item_code'],r['documentary_quantity']) for r in rows['sales_LS_monthly']] == [
        ('2026-02','L03612','25.000000'), ('2026-03','L03612','100.000000')]

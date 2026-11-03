from copy import deepcopy

from . import authorization


def _good_candidate():
    return {
        'literal_preservation_rate': 1.0,
        'new_authorizations': 0,
        'new_blocks_on_known_valid': 0,
        'accepted_state_changed': 0,
        'request_canonical': {'set_exact_turns': 30, 'recall_complete_turns': 35},
        'baseline_request_set_exact_turns': 30,
        'baseline_request_recall_turns': 35,
        'assertion_findings': 0,
        'additional_llm_calls': 0,
        'overhead_p95_ms': 10.0,
        'overhead_pct_p95': 1.0,
    }


def test_provisional_gold_cannot_authorize():
    result = authorization.authorize(_good_candidate(), gold_status='PROVISIONAL_GOLD')
    assert result['decision'] == 'INSUFFICIENT_EVIDENCE'


def test_all_gates_satisfied_authorize():
    result = authorization.authorize(_good_candidate(), gold_status='CERTIFIED')
    assert result['decision'] == 'AUTHORIZE'
    assert all(g['ok'] for g in result['gates'])


def test_new_authorization_rejects():
    candidate = _good_candidate()
    candidate['new_authorizations'] = 1
    assert authorization.authorize(candidate, 'CERTIFIED')['decision'] == 'REJECT'


def test_regression_rejects():
    candidate = _good_candidate()
    candidate['request_canonical']['set_exact_turns'] = 29
    assert authorization.authorize(candidate, 'CERTIFIED')['decision'] == 'REJECT'


def test_overhead_budget_rejects():
    candidate = _good_candidate()
    candidate['overhead_p95_ms'] = 80.0
    assert authorization.authorize(candidate, 'CERTIFIED')['decision'] == 'REJECT'
from copy import deepcopy

from . import evaluate, holdout, seed_gold


def _perfect(case):
    return {
        'turn_id': case['turn_id'],
        'user_message': case['user_message'],
        'request_intent': deepcopy(case['request_intent']),
        'accepted_intent': deepcopy(case.get('accepted_intent')),
        'allowed': case['expected_action'] == 'EXECUTE',
        'sidecar_error': None,
    }


def _run(cases):
    return evaluate.aggregate([evaluate.evaluate_case(c, _perfect(c)) for c in cases])


def test_seed_perfect_candidate_scores_all_layers():
    cases = seed_gold.build_cases()
    agg = _run(cases)
    assert agg['literal_preservation'] == len(cases)
    assert agg['request_canonical']['set_exact_turns'] == len(cases)
    assert agg['request_raw']['set_exact_turns'] == len(cases)
    assert agg['eligibility']['FP'] == 0
    assert agg['eligibility']['FN'] == 0
    assert agg['assertion_findings'] == 0


def test_holdout_perfect_candidate_scores_all_layers():
    cases = holdout.build_cases()
    agg = _run(cases)
    assert agg['literal_preservation'] == len(cases)
    assert agg['request_canonical']['set_exact_turns'] == len(cases)
    assert agg['eligibility']['FP'] == 0
    assert agg['eligibility']['FN'] == 0
    assert agg['assertion_findings'] == 0


def test_holdout_required_conversations_are_scored():
    cases = holdout.build_cases()
    results = [evaluate.evaluate_case(c, _perfect(c)) for c in cases]
    assert {r['group'] for r in results} == {'holdout'}
    assert len(results) == 20
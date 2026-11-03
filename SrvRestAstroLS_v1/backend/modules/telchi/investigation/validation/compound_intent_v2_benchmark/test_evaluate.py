from copy import deepcopy

from . import evaluate
from .case_builder import claim, make_case, period


def _gold():
    gold = make_case(
        turn_id='T1', conversation_id='C1', turn_index=1,
        user_message='Ventas de mayo de 2026',
        request={'metrics': ['sales.net_amount'],
                 'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [period('2026-05-01', '2026-06-01')]}},
        requirements=[
            ('T1.metric', 'metric', 'metrics', 'sales.net_amount', 'CURRENT_REQUEST', 'Ventas'),
            ('T1.time', 'temporal_periodicity', 'time', period('2026-05-01', '2026-06-01'), 'CURRENT_REQUEST', 'mayo de 2026')],
        expected_action='EXECUTE')
    gold['accepted_intent'] = {'metrics': ['sales.net_amount']}
    return gold


def _exact_candidate(gold):
    return {
        'turn_id': gold['turn_id'],
        'user_message': gold['user_message'],
        'request_intent': deepcopy(gold['request_intent']),
        'accepted_intent': {'metrics': ['sales.net_amount']},
        'allowed': True,
        'sidecar_error': None,
    }


def test_exact_candidate_scores_all_layers():
    gold = _gold()
    result = evaluate.evaluate_case(gold, _exact_candidate(gold))
    assert result['literal_preserved']
    assert result['request_canonical']['set_exact']
    assert result['request_canonical']['recall_complete']
    assert result['accepted_state_exact']
    assert result['eligibility']['outcome'] == 'TP'


def test_added_facet_is_not_set_exact_but_still_recall_complete():
    gold = _gold()
    candidate = _exact_candidate(gold)
    candidate['request_intent']['geographies'] = ['La Paz']
    result = evaluate.evaluate_case(gold, candidate)
    assert result['request_canonical']['recall_complete']
    assert not result['request_canonical']['set_exact']


def test_end_key_is_representation_not_loss():
    gold = _gold()
    candidate = _exact_candidate(gold)
    period_value = candidate['request_intent']['time']['periods'][0]
    period_value['end'] = period_value.pop('end_exclusive')
    result = evaluate.evaluate_case(gold, candidate)
    assert not result['request_raw']['set_exact']
    assert result['request_canonical']['set_exact']
    assert result['request_representation_is_sole_cause']


def test_ask_expected_and_blocked_is_true_negative():
    gold = _gold()
    gold['expected_action'] = 'ASK'
    candidate = _exact_candidate(gold)
    candidate['allowed'] = False
    result = evaluate.evaluate_case(gold, candidate)
    assert result['eligibility']['outcome'] == 'TN'


def test_certified_assertion_is_flagged():
    gold = _gold()
    candidate = _exact_candidate(gold)
    assertion = claim('texto', 'Ventas', 'T1')
    assertion['status'] = 'CERTIFIED'
    candidate['request_intent']['claims'] = [assertion]
    result = evaluate.evaluate_case(gold, candidate)
    assert result['assertion_findings']
    assert any(f['error'] == 'not_unverified' for f in result['assertion_findings'])


def test_aggregate_reports_layers_separately():
    gold = _gold()
    results = [evaluate.evaluate_case(gold, _exact_candidate(gold))]
    agg = evaluate.aggregate(results)
    assert agg['literal_preservation'] == 1
    assert agg['request_canonical']['set_exact_turns'] == 1
    assert agg['eligibility']['TP'] == 1
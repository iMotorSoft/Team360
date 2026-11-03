from copy import deepcopy

import pytest

from . import gold_schema, holdout, seed_gold


def _seed_cases():
    return seed_gold.build_cases()


def _holdout_cases():
    return holdout.build_cases()


def _messages(cases):
    return {c['turn_id']: c['user_message'] for c in cases}


def test_seed_and_holdout_validate():
    seed = _seed_cases()
    hold = _holdout_cases()
    assert gold_schema.validate_set(seed, _messages(seed)) == 10
    assert gold_schema.validate_set(hold, _messages(hold)) == 20


def test_holdout_independence_is_provisional():
    summary = gold_schema.independence_summary(_holdout_cases())
    assert summary['gold_status'] == 'PROVISIONAL_GOLD'
    assert summary['human_reviewed_cases'] == 0


def test_ungrounded_evidence_is_rejected():
    cases = _seed_cases()
    cases[0]['requirements'][0]['evidence'] = 'no-such-substring'
    with pytest.raises(ValueError, match='evidence_not_in_source'):
        gold_schema.validate_set(cases, _messages(cases))


def test_user_assertion_cannot_be_certified():
    cases = _holdout_cases()
    case = next(c for c in cases if any(r['provenance'] == 'USER_ASSERTED_UNVERIFIED' for r in c['requirements']))
    req = next(r for r in case['requirements'] if r['provenance'] == 'USER_ASSERTED_UNVERIFIED')
    req['status'] = 'CERTIFIED'
    with pytest.raises(ValueError, match='assertion_certified'):
        gold_schema.validate_set(cases, _messages(cases))


def test_requirement_must_appear_in_request_intent():
    cases = _seed_cases()
    cases[0]['requirements'][0]['value'] = 'not-an-atom'
    with pytest.raises(ValueError, match='requirement_not_in_request_intent'):
        gold_schema.validate_set(cases, _messages(cases))


def test_verified_evidence_requires_recorded_id():
    cases = _seed_cases()
    cases[0]['requirements'][0]['provenance'] = 'VERIFIED_EVIDENCE'
    cases[0]['requirements'][0]['status'] = 'CERTIFIED'
    with pytest.raises(ValueError, match='unrecorded_verified_evidence'):
        gold_schema.validate_set(cases, _messages(cases))


def test_duplicate_turn_ids_rejected():
    cases = _seed_cases()
    clone = deepcopy(cases[0])
    cases.append(clone)
    with pytest.raises(ValueError, match='duplicate_turn_ids'):
        gold_schema.validate_set(cases, _messages(cases))
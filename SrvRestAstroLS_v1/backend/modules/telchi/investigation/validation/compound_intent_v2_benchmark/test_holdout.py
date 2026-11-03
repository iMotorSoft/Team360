from copy import deepcopy

from . import holdout


def test_holdout_meets_entry_gate_size():
    cases, manifest = holdout.seal(holdout.build_cases())
    assert manifest['holdout_turns'] >= 20
    assert len(manifest['conversations']) >= 5
    assert set(manifest['conversations']) >= {'H1', 'H2', 'H3', 'H4', 'H5'}


def test_holdout_covers_required_categories():
    _, manifest = holdout.seal(holdout.build_cases())
    required = {'negation', 'correction', 'assertion', 'reference', 'relation', 'ambiguity'}
    assert required <= set(manifest['categories_covered'])


def test_seal_is_deterministic():
    _, first = holdout.seal(holdout.build_cases())
    _, second = holdout.seal(holdout.build_cases())
    assert first['aggregate_sha256'] == second['aggregate_sha256']


def test_editing_a_holdout_turn_changes_the_lock():
    cases, original = holdout.seal(holdout.build_cases())
    tampered = deepcopy(cases)
    tampered[0]['expected_action'] = 'BLOCK'
    _, changed = holdout.seal(tampered)
    assert changed['aggregate_sha256'] != original['aggregate_sha256']


def test_abraham_is_excluded_from_holdout():
    _, manifest = holdout.seal(holdout.build_cases())
    assert manifest['known_acceptance_cases_excluded'] == ['ABRAHAM_001', 'ABRAHAM_002']
    assert manifest['status'] == 'SEALED'
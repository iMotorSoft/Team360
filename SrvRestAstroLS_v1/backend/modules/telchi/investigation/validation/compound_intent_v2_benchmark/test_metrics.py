from . import metrics


def gold():
    return {'metrics': ['sales.net_amount'], 'scope': {'branch_ids': [], 'warehouse_ids': []}}


def test_recall_family_exact_ignores_facets_added_in_gold_empty_family():
    candidate = {'metrics': ['sales.net_amount'], 'scope': {'branch_ids': [], 'warehouse_ids': ['B']}}
    # gold has no scope atom, so summarize-style filtering is blind to the added scope.
    assert metrics.recall_family_exact(gold(), candidate)
    # raw_score-style gold-key restriction sees the empty-but-present scope field.
    assert not metrics.gold_keys_exact(gold(), candidate)


def test_set_exact_punishes_added_facets_in_full_universe():
    candidate = {'metrics': ['sales.net_amount'], 'geographies': ['La Paz']}
    result = metrics.score(gold(), candidate)
    assert not result['set_exact']
    assert result['recall_complete']
    assert result['added']


def test_missing_and_added_are_distinct_failure_modes():
    candidate = {'metrics': ['sales.unspecified']}
    result = metrics.score(gold(), candidate)
    assert result['missing'] and result['added']
    assert not result['recall_complete']
    assert not result['set_exact']


def test_representation_is_sole_cause():
    g = {'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [{'start': '2026-05-01', 'end_exclusive': '2026-06-01'}]}}
    c = {'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [{'start': '2026-05-01', 'end': '2026-06-01'}]}}
    assert metrics.representation_is_sole_cause(g, c)
    assert metrics.score(g, c, canonical=False)['set_exact'] is False
    assert metrics.score(g, c, canonical=True)['set_exact'] is True


def test_aggregate_counts():
    scores = [
        metrics.score({'metrics': ['a']}, {'metrics': ['a']}),
        metrics.score({'metrics': ['a']}, {'metrics': ['a'], 'geographies': ['x']}),
    ]
    agg = metrics.aggregate(scores)
    assert agg['turns'] == 2
    assert agg['set_exact_turns'] == 1
    assert agg['recall_complete_turns'] == 2
"""Tests of audit diagnostics, never of a new candidate assistant."""
from copy import deepcopy
from modules.telchi.investigation.validation.compound_intent_v1.rca.analyze import (
    atoms, end_keys, guard_reasons, representation, score,
)


def test_end_key_diagnostic_is_non_mutating_and_not_a_semantic_repair():
    value = {'time': {'periods': [{'start': '2026-05-01', 'end': '2026-06-01'}]}}
    before = deepcopy(value)
    result = end_keys(value)
    assert result['time']['periods'][0]['end_exclusive'] == '2026-06-01'
    assert value == before
    assert not score({'metrics': ['sales.net_amount']}, {'metrics': ['sales.unspecified']})['exact']


def test_atoms_do_not_prove_relational_binding():
    a = {'relations': [{'subject': 'P', 'object': 'L&S', 'geography': 'A'},
                       {'subject': 'P', 'object': 'propia', 'geography': 'B'}]}
    b = {'relations': [{'subject': 'P', 'object': 'propia', 'geography': 'A'},
                       {'subject': 'P', 'object': 'L&S', 'geography': 'B'}]}
    assert atoms(a) == atoms(b)  # Known limitation, must require tuple checks separately.
    assert a != b


def test_representation_equivalences_are_restricted():
    a = {'filters': [[{'field': 'channel', 'op': 'eq', 'values': ['A']}],
                     [{'field': 'channel', 'op': 'eq', 'values': ['B']}]]}
    b = {'filters': [[{'field': 'channel', 'op': 'in', 'values': ['A', 'B']}]]}
    assert score(representation(a), representation(b))['exact']
    other = deepcopy(a)
    other['filters'][1][0]['field'] = 'branch'
    assert not score(representation(other), representation(b))['exact']


def test_empty_gold_family_is_not_ignored_by_detail_score():
    assert not score({'scope': {'branch_ids': []}}, {'scope': {'branch_ids': ['SECRET']}})['exact']


def test_blanket_guard_blocks_even_correctly_matched_dimensions():
    row = {'candidate_intent': {'metrics': ['sales.latest_documents'],
                               'dimensions': ['document'], 'time': None},
           'candidate_plan': {'state_engine': {'state_after': {
               'metric': 'sales.latest_documents', 'period': None}}}, 'sidecar_error': None}
    assert guard_reasons(row) == ['blanket_nonempty:dimensions']


def test_guard_reasons_include_all_independent_blockers():
    row = {'candidate_intent': {'metrics': ['sales.unspecified'],
                               'time': {'kind': 'PERIOD', 'as_of': None, 'periods': [
                                   {'start': '2026-05-01', 'end': '2026-06-01'}]}},
           'candidate_plan': {'state_engine': {'state_after': {
               'metric': 'sales.net_amount', 'period': {
                   'start': '2026-05-01', 'end_exclusive': '2026-06-01'}}}}, 'sidecar_error': None}
    assert guard_reasons(row) == ['metric_not_in_plan', 'time_exact_dict_mismatch']

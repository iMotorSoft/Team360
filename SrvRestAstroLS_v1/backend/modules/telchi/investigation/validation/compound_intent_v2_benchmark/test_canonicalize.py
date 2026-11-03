from copy import deepcopy

from .canonicalize import atoms, atoms_of, canonicalize, end_key_only


def test_end_key_is_canonicalized_but_not_invented():
    value = {'time': {'periods': [{'start': '2026-05-01', 'end': '2026-06-01'}]}}
    assert canonicalize(value)['time']['periods'][0]['end_exclusive'] == '2026-06-01'
    assert 'end' not in canonicalize(value)['time']['periods'][0]
    # end_key_only applies ONLY this equivalence.
    assert end_key_only({'sort': {'field': 'x'}}) == {'sort': {'field': 'x'}}


def test_sort_dict_and_list_are_equivalent():
    a = {'sort': {'field': 'document_date', 'direction': 'desc'}}
    b = {'sort': [{'field': 'document_date', 'direction': 'desc'}]}
    assert atoms_of(a) == atoms_of(b)


def test_eq_and_single_in_are_equivalent():
    a = {'filters': [[{'field': 'sales_channel_id', 'op': 'eq', 'values': ['HORIZONTAL']}]]}
    b = {'filters': [[{'field': 'sales_channel_id', 'op': 'in', 'values': ['HORIZONTAL']}]]}
    assert atoms_of(a) == atoms_of(b)


def test_or_of_same_field_eq_merges_into_in():
    a = {'filters': [
        [{'field': 'sales_channel_id', 'op': 'eq', 'values': ['HORIZONTAL']}],
        [{'field': 'sales_channel_id', 'op': 'eq', 'values': ['SALON']}]]}
    b = {'filters': [[{'field': 'sales_channel_id', 'op': 'in', 'values': ['HORIZONTAL', 'SALON']}]]}
    assert atoms_of(a) == atoms_of(b)


def test_unlisted_difference_is_not_canonicalized():
    a = {'metrics': ['sales.net_amount']}
    b = {'metrics': ['sales.unspecified']}
    assert atoms_of(a) != atoms_of(b)


def test_canonicalize_is_idempotent():
    value = {'time': {'periods': [{'start': 'a', 'end': 'b'}]},
             'filters': [[{'field': 'f', 'op': 'eq', 'values': ['x']}]],
             'sort': {'field': 'g'}}
    once = canonicalize(value)
    assert canonicalize(once) == once


def test_atoms_ignore_provenance_metadata():
    base = {'metrics': ['a']}
    with_meta = {'metrics': ['a'], 'source_turn_id': 'T1', 'evidence': 'x', 'status': 'y'}
    assert atoms(base) == atoms(with_meta)
    assert deepcopy(base) != with_meta
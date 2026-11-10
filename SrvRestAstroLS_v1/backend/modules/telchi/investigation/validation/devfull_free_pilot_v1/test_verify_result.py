"""Independent acceptance supports exact codes or independently unique names."""
from modules.telchi.investigation.validation.devfull_free_pilot_v1.verify_result import compare_customers


def evidence(column='customer_name', value='Customer', claimed='customer'):
    return dict(claim_verifications=[dict(match=True, claim=dict(result_id='r', row_id='row', column_id=claimed))],
        turns=[dict(result=dict(schema=[dict(name=column), dict(name='amount')]),
            model_observation=dict(rows=[[value, 1]], evidence_manifest=dict(result_id='r', row_ids=['row'],
                columns=[dict(column_id='customer'), dict(column_id='amount')])))] )


def test_unique_name_maps_to_independent_code():
    assert compare_customers(evidence(), [('C1', 'Customer', '2026-10', 1)]) == (
        {'C1'}, {'C1'}, 'customer_name_unique_mapping')


def test_code_path_preserved():
    assert compare_customers(evidence('card_code', 'C1'), [('C1', 'Customer', '2026-10', 1)])[:2] == ({'C1'}, {'C1'})


def test_ambiguous_name_rejected():
    rows = [('C1', 'Customer', '2026-10', 1), ('C2', 'Customer', '2026-09', 1)]
    assert compare_customers(evidence(), rows)[1:] == (set(), 'ambiguous_or_unknown_customer_name')


def test_unclaimed_customer_cell_not_delivered():
    assert compare_customers(evidence(claimed='amount'), [('C1', 'Customer', '2026-10', 1)])[1] == set()


def test_september_presence_excludes_customer():
    rows = [('C1', 'Customer', '2026-10', 1), ('C1', 'Customer', '2026-09', 1)]
    expected, delivered, _ = compare_customers(evidence(), rows)
    assert expected != delivered


def test_unknown_name_rejected():
    assert compare_customers(evidence(value='Invented'), [('C1', 'Customer', '2026-10', 1)])[1] == set()

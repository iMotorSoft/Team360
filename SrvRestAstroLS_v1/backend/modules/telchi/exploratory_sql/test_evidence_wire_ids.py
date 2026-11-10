"""Short wire handles preserve the original issued evidence namespace exactly."""
from .adaptive_research import EvidenceWireIds, ordered_observation
from .adaptive_sources import context_for_run
from .foundation_dev import proposal
from .validator import validate


def test_only_outer_order_by_proves_an_ordered_prefix():
    for sql, expected in [
        ('SELECT sum(line_total) AS amount FROM sales_operation', False),
        ('SELECT item_code AS item_code,sum(line_total) AS amount FROM sales_operation GROUP BY item_code ORDER BY amount DESC', True),
        ('SELECT x.item_code AS item_code FROM (SELECT item_code AS item_code FROM sales_operation ORDER BY item_code) x', False),
    ]:
        _, query = validate(proposal(sql, 'sales_operation'), context_for_run())
        assert query is not None
        assert bool(ordered_observation(query)) == expected
    assert not ordered_observation(None)


def test_wire_handles_are_lossless_stable_and_investigation_local():
    ids = EvidenceWireIds()
    payload = dict(observations=[dict(evidence_manifest=dict(result_id='result_hash',
        columns=[dict(column_id='column_hash', alias='amount')], row_ids=['row_hash']))])
    compact = ids.payload(payload)
    manifest = compact['observations'][0]['evidence_manifest']
    assert manifest == dict(result_id='q1', columns=[dict(column_id='c1', alias='amount')], row_ids=['r1'])
    claim = dict(kind='executed_cell', result_id='q1', column_id='c1', row_id='r1')
    decoded = ids.claims([dict(kind='calculation', operation='subtract', dependencies=[claim, claim])])
    assert decoded[0]['dependencies'] == [dict(kind='executed_cell', result_id='result_hash',
        column_id='column_hash', row_id='row_hash')] * 2
    assert ids.payload(payload) == compact
    assert payload['observations'][0]['evidence_manifest']['result_id'] == 'result_hash'
    # No mapping means no authority; normal registry checks still reject these.
    assert ids.claims([dict(claim, column_id='c999')])[0]['column_id'] == 'c999'
    assert EvidenceWireIds().claims([claim]) == [claim]
    assert ids.claims([dict(claim, answer='c1')])[0]['answer'] == 'c1'


def test_model_feedback_cannot_issue_evidence_handles():
    ids = EvidenceWireIds()
    payload = dict(observations=[dict(status='REJECTED', rejected_claims=[dict(
        result_id='fake_result', row_id='fake_row', column_id='fake_column')])])
    assert ids.payload(payload) == payload
    assert all(not mapping for mapping in ids.encode.values())

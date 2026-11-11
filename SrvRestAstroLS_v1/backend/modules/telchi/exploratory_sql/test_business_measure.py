from decimal import Decimal
from types import SimpleNamespace

from modules.telchi.exploratory_sql.business_measure import deterministic_claims, paired_component_proposal
from modules.telchi.exploratory_sql.contracts import CandidateRelation, ExploratoryQueryProposal


def _manifest(result_id):
    return SimpleNamespace(
        result_id=result_id,
        row_ids=('row',),
        columns=(SimpleNamespace(column_id='amount'),),
    )


def _registry(*, include_credit=True, mismatched=False):
    sales_manifest = _manifest('sales-result')
    credit_manifest = _manifest('credit-result')
    sales_node = {'select_list': [{'class': 'FUNCTION', 'function_name': 'sum',
                                   'children': [{'class': 'COLUMN_REF', 'column_names': ['line_total']}]}]}
    credit_node = {'select_list': [{'class': 'FUNCTION', 'function_name': 'sum',
                                    'children': [{'class': 'COLUMN_REF', 'column_names': ['line_total']}]}]}
    entries = {
        'sales-result': (sales_manifest, None, None, (), sales_node, 'sales_line'),
    }
    if include_credit:
        entries['credit-result'] = (credit_manifest, None, None, (), credit_node, 'credit_memo_line')
    scopes = {
        ('sales-result', 'amount'): ('sales_line', ('same' if not mismatched else 'sales',)),
        ('credit-result', 'amount'): ('credit_memo_line', ('credit' if mismatched else 'same',)),
    }

    class Registry:
        def __init__(self):
            self.entries = entries

        def _executed_cell(self, ref, revalidate=False):
            source, scope = scopes[(ref['result_id'], ref['column_id'])]
            manifest, _q, _r, _rows, node, _source = self.entries[ref['result_id']]
            value = Decimal('100') if source == 'sales_line' else Decimal('7')
            return value, (manifest, node, source, 0, (value,))

        def _source_signature(self, ref):
            return scopes[(ref['result_id'], ref['column_id'])]

        def _operand_scope(self, ref, issued_cell=None):
            source, scope = scopes[(ref['result_id'], ref['column_id'])]
            return source, scope

    registry = Registry()
    return registry


def test_state_engine_builds_net_claim_from_both_executed_components():
    claims = deterministic_claims(_registry(), 'territorial_line_net')
    assert len(claims) == 1
    assert claims[0]['operation'] == 'subtract'
    assert [d['result_id'] for d in claims[0]['dependencies']] == ['sales-result', 'credit-result']


def test_state_engine_keeps_measure_incomplete_when_counterpart_is_missing_or_scope_differs():
    assert deterministic_claims(_registry(include_credit=False), 'territorial_line_net') == []
    assert deterministic_claims(_registry(mismatched=True), 'territorial_line_net') == []


def test_counterpart_preserves_declared_mapping_sources_and_rewrites_relation():
    proposal = ExploratoryQueryProposal(
        sql=("SELECT SUM(sales_line.line_total) AS line_total FROM sales_line "
             "JOIN warehouse_business_location ON sales_line.whs_code = "
             "warehouse_business_location.warehouse_code WHERE sales_line.source_table='INV1'"),
        objective='sales', justification='sales',
        requested_sources=('sales_line', 'warehouse_business_location'),
        expected_grain='one aggregate', expected_result='one numeric cell',
        candidate_relations=(CandidateRelation(
            'sales_line', 'whs_code', 'warehouse_business_location', 'warehouse_code', 'mapping'),))
    paired = paired_component_proposal(proposal, 'territorial_line_net', territory_code='Segundo Anillo')
    assert paired is not None
    assert paired.requested_sources == ('credit_memo_line', 'warehouse_business_location')
    assert paired.candidate_relations[0].left_table == 'credit_memo_line'
    assert 'SUM(credit_memo_line.line_total)' in paired.sql
    assert "source_table='RIN1'" in paired.sql
    assert "business_location_code = 'SEGUNDO_ANILLO'" in paired.sql

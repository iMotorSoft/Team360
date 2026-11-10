"""General contracts behind the sales-reliability residuals; no business literals."""
from copy import deepcopy

import duckdb
import pytest

from modules.telchi.assistant import result_references as refs
from modules.telchi.assistant.commercial_continuity import request_contract
from modules.telchi.assistant.state_engine import EMPTY, DEFAULTS, validate
from .test_research_continuity import saved, selection


def test_coverage_singleton_does_not_hide_durable_account_list():
    value = saved()
    full = value['full_result']
    full['evidence_manifests'][0]['group_expressions'] = ['card_code', 'customer_name']
    coverage = deepcopy(full['evidence_manifests'][0])
    coverage.update(result_id='coverage', query_id='dates', group_expressions=[])
    full['evidence_manifests'].append(coverage)
    full['claim_verifications'].append(dict(match=True, claim=dict(kind='executed_cell', result_id='coverage')))
    view = refs.research_presentation(value, ['owner'], 'conversation')
    assert view is not None
    assert view['rows'][1]['name'] == 'Cliente B'
    assert refs.resolve(selection(), view, None, ['owner'], 'conversation')[0] == 2


def test_progressive_durable_pages_are_local_and_bounded():
    value = saved()
    value['full_result']['results'][0]['rows'] = [[f'Account {i}', str(i)] for i in range(80)]
    value['full_result']['presentation_pages'] = {'executed': [1, 2, 3, 4, 5]}
    view = refs.research_presentation(value, ['owner'], 'conversation')
    assert refs.interpreter_context(view)['next_ordinal'] == 6
    assert len(view['rows']) == 80
    assert len(refs.interpreter_context(view)['rows']) == 50
    assert refs.interpreter_context(view)['rows_complete'] is False
    proposal = selection(6)
    proposal['action'] = 'PAGE_RESULT'
    ordinal, text = refs.resolve(proposal, view, None, ['owner'], 'conversation')
    assert ordinal == 10
    assert '6–10 de 80' in text and 'Account 5' in text and 'Account 9' in text
    with pytest.raises(ValueError):
        refs.resolve(proposal, view, None, ['another'], 'conversation')


def test_page_cursor_stops_at_last_record_that_fits_channel():
    value = saved()
    value['full_result']['results'][0]['rows'] = [['A'*2000, '10'], ['B'*2000, '20']]
    view = refs.research_presentation(value, ['owner'], 'conversation')
    proposal = selection(1)
    proposal['action'] = 'PAGE_RESULT'
    ordinal, text = refs.resolve(proposal, view, None, ['owner'], 'conversation')
    assert ordinal == 1 and 'B'*2000 not in text
    assert '1–1 de 2' in text and len(text) < 4096


def test_global_ranking_exclusion_uses_existing_state_without_customer():
    before = deepcopy(EMPTY | DEFAULTS)
    before.update(schema_version=2, metric='sales.commercial_line_amount_by',
                  requested_metrics=['sales.commercial_line_amount_by'], group_by='sap_product',
                  period=dict(start='2026-01-01', end_exclusive='2026-02-01'))
    proposal = dict(intent='REFINE', action='EXECUTE', clarification=None,
                    state_delta={'set': {}, 'unset': []})
    updated = request_contract(proposal, 'No muestres el primero, mostrame otros productos', before,
                               dict(rows=[dict(key='SKU_FIRST')]))
    assert updated['state_delta']['set']['/excluded_product'] == 'SKU_FIRST'
    state = dict(before, **{k[1:]: v for k, v in updated['state_delta']['set'].items()})
    validate(state)
    assert state['customer_target'] is None and state['product_target'] is None
    assert state['period'] == before['period']
    next_proposal = dict(proposal, state_delta={'set': {'/excluded_product': None}, 'unset': []})
    refined = request_contract(next_proposal, 'Y en el mes anterior con la misma exclusión', state)
    assert refined['state_delta']['set']['/excluded_product'] == 'SKU_FIRST'


def test_purchase_list_recovers_budget_without_changing_explicit_top_request():
    proposal = dict(intent='NEW_QUERY', action='EXECUTE', clarification=None,
                    state_delta={'set': {'/customer_target': 'ACCOUNT', '/group_by': 'sap_product', '/limit': 10},
                                 'unset': []})
    updated = request_contract(proposal, 'Qué productos compró ese cliente', {})
    assert updated['state_delta']['set']['/limit'] == 50
    updated = request_contract(proposal, 'Los 3 productos con mayor importe que compró ese cliente', {})
    assert updated['state_delta']['set']['/limit'] == 10  # No contract rewrite of an explicit ranking.


def test_research_product_pages_do_not_resurrect_hidden_rows():
    value = saved()
    full = value['full_result']
    full['evidence_manifests'][0].update(group_expressions=['item_code'], row_ids=['hidden', 'shown'])
    full['claim_verifications'][0]['claim']['row_id'] = 'shown'
    full['presentation_pages'] = {'executed': [2]}
    view = refs.research_presentation(value, ['owner'], 'conversation')
    assert view['rows'] == [{'name': 'Cliente B', 'amount': '9.250000'}]
    assert view['next_ordinal'] == 2  # Entire permitted presentation is exhausted.


def test_documentary_existence_is_not_zero_amount():
    # Includes both a zero-valued document and offsetting purchases. Neither
    # belongs in the anti-purchase set despite its zero monetary sum.
    with duckdb.connect(config={'threads': '1'}) as db:
        db.execute('CREATE TABLE lines(account VARCHAR, month INTEGER, document INTEGER, amount DECIMAL(12,2))')
        db.executemany('INSERT INTO lines VALUES (?,?,?,?)', [
            ('zero', 1, 1, 10), ('zero', 2, 2, 0),
            ('offset', 1, 3, 20), ('offset', 2, 4, 5), ('offset', 2, 5, -5),
            ('absent', 1, 6, 30)])
        rows = db.execute('''SELECT account FROM lines GROUP BY account
            HAVING count(CASE WHEN month=1 THEN document ELSE NULL END)>0
               AND count(CASE WHEN month=2 THEN document ELSE NULL END)=0''').fetchall()
        assert rows == [('absent',)]
        wrong = db.execute('''SELECT account FROM lines GROUP BY account
            HAVING sum(CASE WHEN month=2 THEN amount ELSE 0 END)=0''').fetchall()
        assert len(wrong) == 3
    from modules.telchi.exploratory_sql.ask import AUTHORIZED_SYSTEM
    assert 'SUM(amount)=0 is NEVER absence of purchases' in AUTHORIZED_SYSTEM

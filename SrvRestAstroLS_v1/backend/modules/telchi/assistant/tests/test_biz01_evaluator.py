"""Offline contract of the BIZ01 continuity evaluator.

The evaluator judges the persisted audit of each turn: what was inherited,
what was executed, what was reconciled and what was answered. It never judges
a simulated answer and never invents a value.
"""
import json
from pathlib import Path

from modules.telchi.assistant.tests.runtime_http.biz01_evaluator import evaluate, evaluate_turn

JULY = dict(start='2026-07-01', end_exclusive='2026-08-01')
AUGUST = dict(start='2026-08-01', end_exclusive='2026-09-01')


def _turn(index, *, executed=True, capability='sales.commercial_line_amount_by.v1',
          focus=None, periods=None, customer=None, product=None, group_by='card_code',
          amounts=('115044.44',),
          text=('FARMACORP S.A. (C000061) — Bs 115.044,44. «Cliente facturado en SAP» es la cuenta que '
                'recibe las líneas de factura (CardCode); la taxonomía de cliente comercial no está acreditada.')):
    state = dict(metric='sales.commercial_line_amount_by',
                 requested_metrics=['sales.commercial_line_amount_by'],
                 business_category='LAB_FINISHED_PRODUCT', product_target=product,
                 customer_target=customer, group_by=group_by, period_mode='union',
                 periods=periods if periods is not None else [dict(JULY), dict(AUGUST)],
                 period=dict(start='2026-07-01', end_exclusive='2026-09-01'),
                 focus=focus or {'product': 'L03281', 'customer': 'C000061'})
    audit = dict(committed=True, decision='EXECUTE',
                 execution_status='executed' if executed else 'not_executed',
                 business_rbac_verified=bool(executed),
                 required_permission='telchi.sales.commercial_line_amount_by.read.v1' if executed else None,
                 confirmed_state=state,
                 execution_result=(dict(capability=capability,
                                        reconciliation=dict(difference='0.000000'),
                                        rows=[dict(key='C000061', label='FARMACORP S.A.', amount=amounts[0])],
                                        total=dict(amount=amounts[0], product_count=1, line_count=4,
                                                   document_count=4, customer_count=1))
                                       if executed else None))
    return dict(user_text='pregunta', classification='DIRECT_AVAILABLE' if executed else 'DIRECT_UNAVAILABLE',
                response_text=text, audit=audit)


def test_turn_that_keeps_the_scope_and_the_amount_passes():
    report = evaluate_turn(5, _turn(5))
    assert report['pass_'] is True
    assert report['failures'] == []


def test_context_loss_is_detected():
    turn = _turn(5)
    turn['audit']['confirmed_state']['focus'] = {'product': None, 'customer': 'C000061'}
    report = evaluate_turn(5, turn)
    assert report['pass_'] is False
    assert any('producto en foco perdido' in f for f in report['failures'])


def test_lost_period_set_is_detected():
    turn = _turn(5)
    turn['audit']['confirmed_state']['periods'] = [dict(AUGUST)]
    report = evaluate_turn(5, turn)
    assert report['pass_'] is False
    assert any('períodos' in f for f in report['failures'])


def test_a_missing_accredited_amount_is_detected():
    turn = _turn(5, amounts=('1.00',), text='no hay importe')
    report = evaluate_turn(5, turn)
    assert report['pass_'] is False
    assert any('importe acreditado' in f for f in report['failures'])


def test_a_broken_reconciliation_is_detected():
    turn = _turn(5)
    turn['audit']['execution_result']['reconciliation'] = dict(difference='12.34')
    report = evaluate_turn(5, turn)
    assert report['pass_'] is False
    assert any('reconciliación' in f for f in report['failures'])


def test_a_missing_authorization_is_detected():
    turn = _turn(5)
    turn['audit']['business_rbac_verified'] = False
    report = evaluate_turn(5, turn)
    assert report['pass_'] is False
    assert any('autorización' in f for f in report['failures'])


def test_an_unexecuted_turn_is_never_a_pass():
    report = evaluate_turn(5, _turn(5, executed=False))
    assert report['pass_'] is False
    assert any('no se ejecutó' in f for f in report['failures'])


def _conversation_turn(index):
    """A synthetic turn that satisfies the published expectation of its number."""
    from modules.telchi.assistant.tests.runtime_http.biz01_evaluator import EXPECTATIONS
    expectation = EXPECTATIONS[index]
    scope = expectation.get('scope', {})
    capability = expectation['capability']
    figures = expectation.get('figures') or []
    rows = [dict(key='C000061', label='FARMACORP S.A.', amount=amount) for amount in figures]
    turn = _turn(index, capability=capability, amounts=figures or ('115044.44',))
    state = turn['audit']['confirmed_state']
    state['metric'] = ('sales.net_amount' if capability == 'sales.period_billed_amount.v1' else
                       'sales.category_line_amount' if capability == 'sales.category_line_amount.v1' else
                       'sales.product_line_amount_ranking' if capability == 'sales.product_line_amount_ranking.v1' else
                       'sales.commercial_line_amount_by')
    if scope.get('category'):
        state['business_category'] = scope['category']
    if scope.get('limit'):
        state['limit'] = scope['limit']
    if capability == 'sales.product_line_amount_ranking.v1':
        state['group_by'] = None
        state['periods'] = None
        state['period_mode'] = None
    if scope.get('group_by'):
        state['group_by'] = scope['group_by']
    if scope.get('product'):
        state['product_target'] = scope['product']
    if scope.get('customer'):
        state['customer_target'] = scope['customer']
    turn['audit']['execution_result']['rows'] = rows
    turn['audit']['execution_result']['total'] = dict(amount=figures[0] if figures else '0.00',
                                                       product_count=1, line_count=4, document_count=4,
                                                       customer_count=1)
    if index == 4:
        turn['audit']['execution_result']['view'] = 'historical_position'
        state['focus'] = {'product': 'L03281'}
    if index in (1, 2, 3):
        state['focus'] = {}
    if index == 1:
        state['period'] = dict(start='2026-09-01', end_exclusive='2026-10-01')
    return turn


def test_the_whole_conversation_is_judged(tmp_path: Path):
    turns = [_conversation_turn(index) for index in range(1, 11)]
    evidence = dict(run_id='test', scenarios=[dict(id='BIZ01', conversation='biz01', turns=turns)])
    path = tmp_path / 'results.json'
    path.write_text(json.dumps(evidence))
    report = evaluate(path)
    assert report['turns_total'] == 10
    assert report['turns_correct'] == 10
    assert report['unjustified_unavailability'] == 0
    assert report['context_loss'] == 0
    assert report['monetary_reconciliation'] == 'PASS'
    assert report['authorization'] == 'PASS'
    assert report['conversation_pass'] is True

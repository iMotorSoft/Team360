"""Offline, deterministic regressions of the conversational business scope.

These tests never call a model and never touch Foundation. They pin the
contract that the real incident of 21/10/2026 broke: the category, the
product, the customer and the periods must survive a change of question.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import business_plan, business_scope, state_engine as engine
from modules.telchi.assistant.capabilities import Availability, SalesCapabilities, format_result
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler, unavailable_response
from modules.telchi.assistant.state_engine import EMPTY, INTENT_V2
from modules.telchi.datalake import commercial_line_amount_by_query as reader

from .test_assistant import MemoryStore, Interpreter, context, event, latest, proposal

MEASURE = 'commercial_active_invoice_line_amount_excluding_line_tax_v1'
JULY = dict(start='2026-07-01', end_exclusive='2026-08-01')
AUGUST = dict(start='2026-08-01', end_exclusive='2026-09-01')
WINDOW = dict(start='2026-07-01', end_exclusive='2026-09-01')


def commercial_proposal(**sets):
    fields = {'/schema_version': 2, '/metric': 'sales.commercial_line_amount_by',
              '/requested_metrics': ['sales.commercial_line_amount_by']}
    fields.update(sets)
    return proposal(fields)


def scoped_state(**kw):
    state = dict(EMPTY | INTENT_V2)
    state.update(kw)
    return state


# ---------------------------------------------------------------- F0 incident

def test_incident_20261021_a_product_code_cannot_overwrite_the_category():
    """The real divergence: the product was written in the category slot."""
    before = scoped_state(entity_mention={'text': 'LAB_FINISHED_PRODUCT', 'type': None},
                          metric='sales.product_line_amount_ranking',
                          requested_metrics=['sales.product_line_amount_ranking'],
                          period=dict(AUGUST), comparison=dict(JULY))
    p1 = proposal({'/entity_mention': {'text': 'L03281', 'type': None}})
    out = engine.process(before, p1, {}, 'p1')
    assert out['committed'] is False
    assert out['state_after']['entity_mention'] == {'text': 'LAB_FINISHED_PRODUCT', 'type': None}
    assert out['state_after']['comparison'] == dict(JULY)


def test_incident_20261021_the_turn_after_does_not_need_to_ask_the_category():
    """The same turn, with the product in its own slot, commits and keeps both."""
    before = scoped_state(entity_mention={'text': 'LAB_FINISHED_PRODUCT', 'type': None},
                          metric='sales.product_line_amount_ranking',
                          requested_metrics=['sales.product_line_amount_ranking'],
                          period=dict(AUGUST), comparison=dict(JULY))
    p1 = proposal({'/product_target': 'L03281', '/ranking_target_item_code': 'L03281'})
    out = engine.process(before, p1, {}, 'p1')
    assert out['committed'] is True
    state = out['state_after']
    assert state['entity_mention'] == {'text': 'LAB_FINISHED_PRODUCT', 'type': None}
    assert state['product_target'] == 'L03281'
    assert state['comparison'] == dict(JULY) and state['period'] == dict(AUGUST)


# ------------------------------------------------------------- F2 entity split

def test_dedicated_category_slot_never_conflicts_with_the_entity_mention():
    state = scoped_state(business_category='LAB_FINISHED_PRODUCT',
                          entity_mention={'text': 'LAB_FINISHED_PRODUCT', 'type': None})
    engine.validate(state)
    with pytest.raises(ValueError):
        engine.validate(scoped_state(business_category='RAW_MATERIAL',
                                     entity_mention={'text': 'LAB_FINISHED_PRODUCT', 'type': None}))


def test_product_target_survives_the_change_of_dimension():
    before = scoped_state(business_category='LAB_FINISHED_PRODUCT', product_target='L03281',
                          metric='sales.product_line_amount_ranking',
                          requested_metrics=['sales.product_line_amount_ranking'], period=dict(AUGUST))
    out = engine.process(before, commercial_proposal(**{'/group_by': 'card_code'}), {}, 'turn')
    assert out['committed'] is True
    assert out['state_after']['product_target'] == 'L03281'
    assert out['state_after']['business_category'] == 'LAB_FINISHED_PRODUCT'
    assert out['state_after']['metric'] == 'sales.commercial_line_amount_by'


def test_commercial_entity_mention_is_rejected_for_a_product_scoped_metric():
    before = scoped_state(business_category='LAB_FINISHED_PRODUCT', metric='sales.product_line_amount_ranking',
                          requested_metrics=['sales.product_line_amount_ranking'], period=dict(AUGUST))
    out = engine.process(before, proposal({'/entity_mention': {'text': 'FARMACORP', 'type': None}}), {}, 'turn')
    assert out['committed'] is False


# ---------------------------------------------------------------- F3 periods

def test_union_of_two_months_is_one_window_that_keeps_both_months():
    out = engine.process(scoped_state(), commercial_proposal(**{
        '/period_mode': 'union', '/periods': [dict(JULY), dict(AUGUST)]}), {}, 'turn')
    assert out['committed'] is True
    state = out['state_after']
    assert state['period'] == WINDOW
    assert state['periods'] == [dict(JULY), dict(AUGUST)]
    assert state['period_mode'] == 'union'


def test_a_union_is_never_collapsed_into_one_month():
    out = engine.process(scoped_state(), commercial_proposal(**{
        '/period_mode': 'union', '/periods': [dict(JULY), dict(AUGUST)],
        '/period': dict(AUGUST)}), {}, 'turn')
    assert out['committed'] is True
    assert out['state_after']['period'] == WINDOW


def test_comparison_is_not_a_union():
    state = scoped_state(period=dict(AUGUST), comparison=dict(JULY))
    assert engine.effective_period_mode(state) == 'compare'
    assert engine.scope_window(state) == dict(AUGUST)
    out = engine.process(scoped_state(), proposal({'/metric': 'sales.net_amount',
                                                   '/requested_metrics': ['sales.net_amount'],
                                                   '/period': dict(AUGUST),
                                                   '/comparison': dict(JULY)}), {}, 'turn')
    assert out['committed'] is True
    assert out['state_after'].get('periods') is None
    assert out['state_after']['comparison'] == dict(JULY)


def test_period_set_must_be_contiguous():
    out = engine.process(scoped_state(), commercial_proposal(**{
        '/period_mode': 'union', '/periods': [dict(JULY), dict(start='2026-08-05', end_exclusive='2026-09-01')]}),
        {}, 'turn')
    assert out['committed'] is False


# ------------------------------------------------------------------- F4 plan

def test_plan_is_compiled_from_the_scope_and_is_closed():
    state = scoped_state(business_category='LAB_FINISHED_PRODUCT', product_target='L03281',
                          customer_target='C000061', group_by='card_code', period_mode='union',
                          periods=[dict(JULY), dict(AUGUST)], period=dict(WINDOW),
                          metric='sales.commercial_line_amount_by',
                          requested_metrics=['sales.commercial_line_amount_by'])
    plan = business_plan.build(state)
    assert plan['dataset'] == 'commercial_line_amount'
    assert plan['filters'] == dict(category='LAB_FINISHED_PRODUCT', item_code='L03281', card_code='C000061')
    assert plan['group_by'] == 'card_code' and plan['currency'] == 'BS'
    assert plan['date_from'] == '2026-07-01' and plan['date_to_exclusive'] == '2026-09-01'
    with pytest.raises(business_plan.PlanError):
        business_plan.build(dict(state, group_by='salesperson'))
    with pytest.raises(business_plan.PlanError):
        business_plan.build(dict(state, period=None, period_mode='single'))


def test_capability_requires_a_dimension_and_a_period():
    caps = SalesCapabilities()
    state = scoped_state(metric='sales.commercial_line_amount_by',
                         requested_metrics=['sales.commercial_line_amount_by'], period=dict(AUGUST))
    assert caps.availability(state).category == 'DIMENSION_NOT_ACCREDITED'
    state['group_by'] = 'card_code'
    assert caps.availability(state).allowed
    state['period'] = None
    assert caps.availability(state).category == 'PERIOD_UNRESOLVED'
    state['period'] = dict(AUGUST)
    state['comparison'] = dict(JULY)
    assert caps.availability(state).category == 'COMPARISON_UNSUPPORTED'


# --------------------------------------------------- F1/F5 scope and answers

def test_unavailable_answer_keeps_every_period_and_offers_a_next_step():
    state = scoped_state(metric='sales.commercial_line_amount_by',
                         requested_metrics=['sales.commercial_line_amount_by'],
                         group_by='card_code', period_mode='union',
                         periods=[dict(JULY), dict(AUGUST)], period=dict(WINDOW))
    text = unavailable_response(state, Availability(False, 'Falta la dimensión acreditada.', 'DIMENSION_NOT_ACCREDITED'))
    assert 'julio' in text and 'agosto' in text and '2026' in text
    assert 'dimensión' in text.lower()
    assert 'producto' in text.lower() or 'cliente' in text.lower()


def _commercial_result(**kw):
    """A valid result of the closed contract, built without a database."""
    options = dict(dataset='commercial_line_amount',
                   filters=dict(category='LAB_FINISHED_PRODUCT', item_code='L03281', card_code='C000061'),
                   date_from='2026-07-01', date_to_exclusive='2026-09-01', group_by='card_code',
                   breakdown_by='period', periods=[dict(JULY), dict(AUGUST)], measure=MEASURE,
                   order_by=[['amount', 'desc'], ['key', 'asc']], limit=10, currency='BS')
    options.update(kw)
    rows = [dict(key='C000061', label='FARMACORP S.A.', amount='115044.44', line_count=4, document_count=4,
                 periods=[dict(period=dict(JULY), amount='72383.99', line_count=2, document_count=2),
                          dict(period=dict(AUGUST), amount='42660.45', line_count=2, document_count=2)])]
    total = dict(amount='115044.44', product_count=1, line_count=4, document_count=4, customer_count=1)
    result = dict(capability=reader.CAPABILITY, parameters=options, plan=reader.plan_of(options),
                  definition=MEASURE, currency='BS', rows=rows, full_breakdown=rows, total=total,
                  universe_total=dict(amount='586227.06', product_count=1, line_count=2014, document_count=2012),
                  period_breakdown=[], exceptions=[], accreditation='verified', coverage=dict(
                      first_date='2026-07-01T00:00:00', last_date='2026-08-31T00:00:00', complete=False),
                  classification=None, source=dict(publication_id='p', snapshot_id=1408, updated_at='2026-09-24'),
                  limitations=reader.LIMITATIONS, read_only=True, sap_accessed=False,
                  unnamed_accounts=0, focus=dict(item_code='L03281', item_label='MINOXITEL 5%',
                                                 card_code='C000061', customer_label='FARMACORP S.A.'))
    result['reconciliation'] = reader.reconcile(rows, total, 'card_code')
    return result


def test_business_answer_states_the_amount_the_months_and_the_definition():
    text = format_result(_commercial_result())
    assert 'Bs 115.044,44' in text
    assert 'julio de 2026' in text and 'agosto de 2026' in text
    assert '72.383,99' in text and '42.660,45' in text
    assert '19,62 %' in text
    assert 'facturado en SAP' in text
    assert 'no está acreditada' in text


def test_executed_scope_is_projected_into_the_state():
    state = scoped_state(metric='sales.commercial_line_amount_by',
                         requested_metrics=['sales.commercial_line_amount_by'],
                         business_category='LAB_FINISHED_PRODUCT', product_target='L03281',
                         group_by='card_code', period_mode='union',
                         periods=[dict(JULY), dict(AUGUST)], period=dict(WINDOW))
    result = _commercial_result()
    business_scope.project(state, result)
    engine.validate(state)
    assert state['focus']['product'] == 'L03281'
    assert state['focus']['customer'] == 'C000061'
    assert state['focus']['customer_label'] == 'FARMACORP S.A.'
    assert state['focus']['customer_type'] == 'sap_billed'
    scope = business_scope.scope(state)
    assert scope['dimension'] == 'card_code' and scope['period_mode'] == 'union'
    assert scope['periods'] == [dict(JULY), dict(AUGUST)]


def test_scope_survives_a_change_of_question():
    state = scoped_state(metric='sales.commercial_line_amount_by',
                         requested_metrics=['sales.commercial_line_amount_by'],
                         business_category='LAB_FINISHED_PRODUCT', product_target='L03281',
                         group_by='card_code', period_mode='union',
                         periods=[dict(JULY), dict(AUGUST)], period=dict(WINDOW))
    business_scope.project(state, _commercial_result())
    # A new question about the same client and the same months keeps the scope.
    out = engine.process(state, commercial_proposal(**{'/group_by': 'sap_product'}), {}, 'turn')
    assert out['committed'] is True
    after = out['state_after']
    assert after['product_target'] == 'L03281'
    assert after['periods'] == [dict(JULY), dict(AUGUST)]
    assert after['focus']['customer'] == 'C000061'

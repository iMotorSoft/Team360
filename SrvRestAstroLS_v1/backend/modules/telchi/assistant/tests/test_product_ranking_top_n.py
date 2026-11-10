"""The real incident of 08/11/2026: «los 3 productos más vendidos».

The conversation asked for a product ranking of October 2026 with amount and
quantity, answered «ambas», and the catalog replied
«La agregación monetaria no admite límite de filas.» on every reformulation.

These tests pin the closure of that family of defects without a model, a
database or a Foundation read: a row limit belongs to the row-producing
operation that asked for it, a generic product ranking is the accredited
commercial breakdown, and its quantity is a published column of the same
accredited rows, never a converted or guessed unit.
"""
import asyncio
from copy import deepcopy

import pytest

from modules.messaging.handlers import ChannelContext, MessageContext, SenderIdentity
from modules.telchi.assistant import business_plan, business_scope, state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.assistant.state_engine import EMPTY, INTENT_V2
from modules.telchi.datalake import commercial_line_amount_by_query as reader

from .test_assistant import Interpreter, MemoryStore, event, latest, proposal

OCTOBER = dict(start='2026-10-01', end_exclusive='2026-11-01')
PERMISSION = 'telchi.sales.commercial_line_amount_by.read.v1'
PUBLICATION = 'foundation_38680850adc058b1bb11887632b7b681'


def scoped_state(**kw):
    state = dict(EMPTY | INTENT_V2)
    state.update(kw)
    return state


def ranking_state(**kw):
    state = scoped_state(metric='sales.commercial_line_amount_by',
                         requested_metrics=['sales.commercial_line_amount_by'],
                         group_by='sap_product', period=dict(OCTOBER), limit=3)
    state.update(kw)
    return state


def ranking_result(**kw):
    """A valid product-ranking envelope, built without touching Foundation."""
    options = dict(dataset='commercial_line_amount',
                   filters=dict(category=None, item_code=None, card_code=None),
                   date_from=OCTOBER['start'], date_to_exclusive=OCTOBER['end_exclusive'],
                   group_by='sap_product', breakdown_by=None, periods=None, measure=reader.MEASURE,
                   order_by=[list(order) for order in reader.ORDER_BY], limit=3, currency='BS')
    options.update(kw)
    rows = [dict(key='L00001', label='PRODUCTO A', amount='90000.00', line_count=4, document_count=3,
                 quantity='1200.000000000000'),
            dict(key='L00002', label='PRODUCTO B', amount='50000.00', line_count=3, document_count=2,
                 quantity='80.5'),
            dict(key='L00003', label='PRODUCTO C', amount='10000.00', line_count=2, document_count=2,
                 quantity='7')]
    total = dict(amount='150000.00', product_count=3, line_count=9, document_count=7,
                 customer_count=2, quantity='1287.5')
    result = dict(capability=reader.CAPABILITY, parameters=options, plan=reader.plan_of(options),
                  definition=reader.MEASURE, currency='BS', rows=rows, full_breakdown=rows,
                  total=total, universe_total=None, period_breakdown=[], exceptions=[],
                  accreditation='verified',
                  coverage=dict(first_date='2026-10-01T00:00:00', last_date='2026-10-31T00:00:00',
                                complete=False),
                  classification=None,
                  source=dict(publication_id=PUBLICATION, snapshot_id=1408, updated_at='2026-11-01'),
                  limitations=reader.LIMITATIONS, quantity_limitation=reader.QUANTITY_LIMITATION,
                  read_only=True, sap_accessed=False, unnamed_accounts=0, focus={})
    result['reconciliation'] = reader.reconcile(rows, total, 'sap_product')
    return result


# ------------------------------------------------------- capability selection

def test_generic_product_ranking_needs_no_business_category():
    """«los 3 productos más vendidos» is available without an accredited category."""
    state = ranking_state(ranking_by='amount')
    engine.validate(state)
    available = SalesCapabilities().availability(state)
    assert available.allowed, available.reason
    assert SalesCapabilities().required_permission(state) == PERMISSION
    plan = business_plan.build(state)
    assert plan['group_by'] == 'sap_product' and plan['limit'] == 3
    assert plan['order_by'] == [['amount', 'desc'], ['key', 'asc']]
    assert plan['filters']['category'] is None


def test_ordering_by_quantity_keeps_the_contract_and_changes_the_criterion():
    state = ranking_state(ranking_by='quantity')
    available = SalesCapabilities().availability(state)
    assert available.allowed, available.reason
    plan = business_plan.build(state)
    assert plan['order_by'] == [['quantity', 'desc'], ['key', 'asc']]


def test_a_row_limit_is_not_a_parameter_of_the_monetary_aggregate():
    """The exact rejection of the incident: limit 3 on a one-row aggregate."""
    state = scoped_state(metric='sales.net_amount',
                         requested_metrics=['sales.net_amount', 'sales.source_top_items'],
                         period=dict(OCTOBER), limit=3)
    available = SalesCapabilities().availability(state)
    assert available.allowed, available.reason
    assert available.category is None


def test_ranking_criterion_never_attaches_to_an_aggregate():
    with pytest.raises(ValueError):
        engine.validate(scoped_state(metric='sales.net_amount', requested_metrics=['sales.net_amount'],
                                     period=dict(OCTOBER), ranking_by='amount'))
    with pytest.raises(ValueError):
        engine.validate(ranking_state(group_by='card_code', ranking_by='amount'))
    with pytest.raises(ValueError):
        engine.validate(ranking_state(ranking_by='price'))


def test_a_limit_of_another_family_never_reaches_the_new_operation():
    before = ranking_state(ranking_by='amount')
    out = engine.process(before, proposal({'/metric': 'sales.net_amount',
                                           '/requested_metrics': ['sales.net_amount'],
                                           '/period': dict(OCTOBER)},
                                          intent='NEW_QUERY'), {}, 'turn')
    assert out['committed'] is True, out.get('contract_error')
    assert out['state_after'].get('limit', engine.DEFAULTS['limit']) == engine.DEFAULTS['limit']
    assert out['state_after'].get('ranking_by') is None


# ------------------------------------------------------------- presentation

def test_answer_lists_the_requested_products_with_amount_and_quantity():
    result = ranking_result()
    state = ranking_state(ranking_by='amount')
    text = format_result(result, business_scope.result_scope(state, result))
    assert '1. L00001 · PRODUCTO A — Bs 90.000,00 · 1.200 unidades documentales' in text
    assert '2. L00002 · PRODUCTO B — Bs 50.000,00 · 80,5 unidades documentales' in text
    assert '3. L00003 · PRODUCTO C — Bs 10.000,00 · 7 unidades documentales' in text
    assert 'Ordenado por importe vendido' in text
    assert 'octubre de 2026' in text
    assert reader.QUANTITY_LIMITATION in text
    assert 'no certifica el cierre completo' in text


def test_answer_reports_the_criterion_when_quantity_is_requested():
    from decimal import Decimal
    result = ranking_result(order_by=[list(order) for order in reader.QUANTITY_ORDER_BY])
    rows = sorted(result['full_breakdown'], key=lambda r: r['key'])
    rows.sort(key=lambda r: Decimal(r['quantity']), reverse=True)
    result['rows'], result['full_breakdown'] = rows[:3], rows
    result['reconciliation'] = reader.reconcile(rows, result['total'], 'sap_product')
    state = ranking_state(ranking_by='quantity')
    text = format_result(result, business_scope.result_scope(state, result))
    assert 'Ordenado por cantidad documental' in text
    assert text.index('1. L00001') < text.index('2. L00002')
    assert 'Bs 90.000,00' in text and 'Bs 50.000,00' in text


def test_result_contract_requires_quantity_and_declares_its_gap():
    result = ranking_result()
    broken = deepcopy(result)
    broken['quantity_limitation'] = None
    with pytest.raises(ValueError):
        reader.validate_result(broken['parameters'], broken)
    broken = ranking_result()
    broken['full_breakdown'][0].pop('quantity')
    broken['rows'] = broken['full_breakdown'][:3]
    with pytest.raises(ValueError):
        reader.validate_result(broken['parameters'], broken)
    broken = ranking_result()
    broken['full_breakdown'][0]['quantity'] = 'NaN'
    broken['rows'] = broken['full_breakdown'][:3]
    with pytest.raises(ValueError):
        reader.validate_result(broken['parameters'], broken)


def test_quantity_reconciliation_is_zero_tolerance():
    result = ranking_result()
    rows = result['full_breakdown']
    with pytest.raises(reader.CommercialAmountError):
        reader.reconcile(rows, dict(result['total'], quantity='1287.51'), 'sap_product')


# ------------------------------------------------------------------ handler

def commercial_context():
    c = ChannelContext('channel', 'evolution', 'instance', 'receiver', 'telchi', 'workspace', 'telchi')
    i = SenderIdentity('user', 'telchi', 'workspace',
                       permissions=frozenset({'fixture.business.read', PERMISSION}))
    return MessageContext(c, i, '123456789', 'conversation', 'turn-1', frozenset())


def test_handler_executes_the_top_three_with_amount_and_quantity():
    async def scenario():
        calls = []

        async def query(options, *, timeout_seconds=60):
            calls.append(deepcopy(options))
            return ranking_result(limit=options['limit'])

        proposal_ = proposal({'/schema_version': 2, '/metric': 'sales.commercial_line_amount_by',
                              '/requested_metrics': ['sales.commercial_line_amount_by'],
                              '/group_by': 'sap_product', '/ranking_by': 'amount',
                              '/limit': 3, '/period': dict(OCTOBER)},
                             intent='NEW_QUERY', action='EXECUTE')
        store = MemoryStore()
        handler = TelchiHandler(
            store=store,
            authorization=BusinessAuthorization(
                BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([proposal_]),
            capabilities=SalesCapabilities(commercial_query=query))
        response = await handler.handle(
            event('dame los 3 productos mas vendidos de octubre 2026, importe y cantidades'),
            commercial_context())
        assert calls and calls[0]['limit'] == 3 and calls[0]['group_by'] == 'sap_product'
        assert response.classification == 'DIRECT_AVAILABLE'
        assert 'PRODUCTO A' in response.text and 'Bs 90.000,00' in response.text
        assert '1.200 unidades documentales' in response.text
        audit = latest(store)
        assert audit['capability_calls'] == 1
        assert audit['confirmed_state']['ranking_by'] == 'amount'
    asyncio.run(scenario())


def test_a_new_query_does_not_inherit_the_previous_ranking_limit():
    before = ranking_state(ranking_by='amount')
    out = engine.process(before, proposal({'/schema_version': 2, '/metric': None,
                                           '/requested_metrics': []},
                                          unset=['/limit', '/period', '/group_by', '/ranking_by'],
                                          intent='NEW_QUERY', action='ASK',
                                          clarification={'slot': 'metric',
                                                         'question': '¿Importe de ventas, cantidades o ambas?'}),
                          {}, 'nueva')
    assert out['committed'] is True, out.get('contract_error')
    # An ASK protects the active state; the new scope lives in the pending proposal.
    proposed = out['state_after']['pending']['proposed']
    assert proposed.get('limit') == engine.DEFAULTS['limit']
    assert proposed.get('group_by') is None and proposed.get('ranking_by') is None
    after = dict(proposed, pending=None)
    # The new, explicit request reaches the ranking and is executable.
    out = engine.process(after, proposal({'/schema_version': 2,
                                          '/metric': 'sales.commercial_line_amount_by',
                                          '/requested_metrics': ['sales.commercial_line_amount_by'],
                                          '/group_by': 'sap_product', '/ranking_by': 'amount',
                                          '/limit': 3, '/period': dict(OCTOBER)},
                                         intent='ANSWER_CLARIFICATION'), {}, 'ambas')
    assert out['committed'] is True, out.get('contract_error')
    assert SalesCapabilities().availability(out['state_after']).allowed

# ------------------------------------------- self-sufficient reformulations

def pending_metric_question():
    """The exact state left by «nueva»: October still active, metric open."""
    before = dict(EMPTY | INTENT_V2)
    before['period'] = dict(OCTOBER)
    before['pending'] = dict(spec={'slot': 'metric', 'question': '¿Importe, cantidades o ambas?'},
                             proposed=dict(EMPTY | INTENT_V2),
                             base_state_hash=engine.state_hash(before), source_turn_id='t')
    return before


def test_a_complete_request_supersedes_the_open_clarification_it_answers():
    """Luna may label it REFINE: the turn must execute, not report garbage."""
    before = pending_metric_question()
    refine = proposal({'/schema_version': 2, '/metric': 'sales.commercial_line_amount_by',
                       '/requested_metrics': ['sales.commercial_line_amount_by'],
                       '/group_by': 'sap_product', '/limit': 3, '/ranking_by': 'amount'},
                      intent='REFINE', action='EXECUTE')
    out = engine.process(before, refine, {}, 'turn')
    assert out['committed'] is True, out.get('contract_error')
    assert out['state_after']['metric'] == 'sales.commercial_line_amount_by'
    assert out['state_after']['limit'] == 3 and out['state_after']['pending'] is None
    assert out['state_after']['period'] == dict(OCTOBER)  # the active period is kept


def test_an_execution_that_does_not_answer_the_question_stays_blocked():
    before = pending_metric_question()
    empty = proposal({'/schema_version': 2, '/limit': 3}, intent='REFINE', action='EXECUTE')
    out = engine.process(before, empty, {}, 'turn')
    assert out['committed'] is False and out['contract_error'] == 'CONTRACT_ERROR_NO_COMMIT'
    assert engine.answers_pending(before['pending'], empty['state_delta']) is False

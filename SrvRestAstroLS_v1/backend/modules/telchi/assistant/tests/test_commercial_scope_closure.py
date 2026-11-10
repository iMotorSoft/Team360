"""Commercial scope closure: availability, breakdown, decisions and limits.

Independent of any real question: the contracts are exercised with a fixture
reader. A consolidated value never answers a per-period request, an interpreter
decision never declares business unavailability, and a processing limit is
reported as such instead of as a missing capability.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import Availability, SalesCapabilities, format_result
from modules.telchi.assistant.handler import (
    BusinessAuthorization, BusinessPolicy, TelchiHandler, unavailable_response,
)
from modules.telchi.datalake.sales_query import (
    MONETARY_OPERATION as OP, MONETARY_PERMISSION as GRANT, PERIOD_LIMIT, PUBLICATION,
    parameters, period_arguments, period_values, validate_result,
)

from .test_assistant import Interpreter, MemoryStore, context, event, latest, proposal

AUGUST = {'start': '2026-08-01', 'end_exclusive': '2026-09-01'}
SEPTEMBER = {'start': '2026-09-01', 'end_exclusive': '2026-10-01'}
WINDOW = {'start': '2026-08-01', 'end_exclusive': '2026-10-01'}
JULY = {'start': '2026-07-01', 'end_exclusive': '2026-08-01'}
POLICY = BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)
PERMISSIONS = frozenset({'fixture.business.read', GRANT,
                         'telchi.sales.commercial_line_amount_by.read.v1'})


def permitted(permissions=PERMISSIONS):
    c = context()
    return replace(c, sender_identity=replace(c.sender_identity, permissions=permissions))


def state(**fields):
    value = deepcopy(dict(engine.EMPTY | engine.INTENT_V2))
    value.update(metric='sales.net_amount', requested_metrics=['sales.net_amount'])
    value.update(fields)
    engine.validate(value)
    return value


def breakdown(**fields):
    base = dict(period_mode='union', periods=[dict(AUGUST), dict(SEPTEMBER)],
                period=dict(WINDOW), breakdown_by='period')
    base.update(fields)
    return state(**base)


# --- availability contract -------------------------------------------------

def test_one_period_with_channel_is_available():
    available = SalesCapabilities().availability(state(period=dict(AUGUST), sales_channel='HORIZONTAL'))
    assert available.allowed and available.category is None


def test_two_periods_consolidated_is_available_as_a_declared_union():
    available = SalesCapabilities().availability(breakdown(breakdown_by=None))
    assert available.allowed


def test_two_periods_with_breakdown_and_channel_are_available():
    available = SalesCapabilities().availability(breakdown(sales_channel='HORIZONTAL'))
    assert available.allowed


@pytest.mark.parametrize('fields,category', [
    (dict(sales_channel='SALON'), 'CHANNEL_NOT_ACCREDITED'),
    (dict(branches=['Saavedra']), 'MAPPING_MISSING'),
    (dict(entity_mention={'text': 'Calenta', 'type': None}), 'MAPPING_MISSING'),
    (dict(group_by='physical_state', breakdown_by='day'), 'DIMENSION_NOT_ACCREDITED'),
])
def test_unsupported_representation_is_rejected_with_its_own_reason(fields, category):
    available = SalesCapabilities().availability(breakdown(**fields))
    assert not available.allowed and available.category == category


def test_non_contiguous_period_set_is_rejected_not_silently_merged():
    from modules.telchi.assistant.capabilities import representation_problem
    value = dict(period_mode='union', periods=[dict(JULY), dict(SEPTEMBER)],
                 period={'start': '2026-07-01', 'end_exclusive': '2026-10-01'},
                 breakdown_by='period', comparison=None, branches=[])
    # The state engine refuses to persist it at all.
    with pytest.raises(ValueError, match='invalid_period_set'):
        engine.validate(dict(deepcopy(engine.EMPTY | engine.INTENT_V2), metric='sales.net_amount',
                             requested_metrics=['sales.net_amount'], **value))
    # And the capability refuses it even if a caller built the dict by hand.
    assert representation_problem(value, allowed_breakdowns={None, 'period'}).category == 'PERIOD_SET_UNSUPPORTED'


def test_breakdown_without_a_period_set_asks_for_the_set_not_a_consolidation():
    from modules.telchi.assistant.capabilities import representation_problem
    with pytest.raises(ValueError, match='breakdown_requires_period_set'):
        state(period=dict(AUGUST), breakdown_by='period')
    problem = representation_problem(dict(period=dict(AUGUST), breakdown_by='period', periods=None),
                                     allowed_breakdowns={None, 'period'})
    assert problem.category == 'PERIOD_SET_UNSUPPORTED'


def test_metric_without_operation_is_an_interpretation_gap():
    value = dict(deepcopy(engine.EMPTY | engine.INTENT_V2))
    value.update(periods=[dict(AUGUST), dict(SEPTEMBER)], period_mode='union',
                 period=dict(WINDOW), sales_channel='HORIZONTAL')
    available = SalesCapabilities().availability(value)
    assert available.category == 'INTENT_INCOMPLETE'
    assert 'todavía no está disponible' not in available.reason


def test_channel_is_not_accredited_for_the_commercial_line_measure():
    value = state(metric='sales.commercial_line_amount_by',
                  requested_metrics=['sales.commercial_line_amount_by'],
                  period=dict(AUGUST), group_by='sap_product', sales_channel='HORIZONTAL')
    available = SalesCapabilities().availability(value)
    assert available.category == 'CHANNEL_NOT_ACCREDITED'
    assert 'facturación neta documental' in available.reason


def test_commercial_breakdown_by_period_stays_available():
    value = state(metric='sales.commercial_line_amount_by',
                  requested_metrics=['sales.commercial_line_amount_by'],
                  period_mode='union', periods=[dict(AUGUST), dict(SEPTEMBER)],
                  period=dict(WINDOW), breakdown_by='period', group_by='sap_product')
    assert SalesCapabilities().availability(value).allowed


# --- execution contract ----------------------------------------------------

def period_result(options, months=('1996773.280000', '1841198.640000'),
                  credits=('127550.360000', '0.000000')):
    periods = options['periods']
    rows = []
    for value, billed, credit in zip(periods, months, credits):
        rows.append(dict(period=dict(value), invoice_count=1, unique_invoices=1,
                         invoice_amount_count=1, billed_amount=billed,
                         credit_count=1 if credit != '0.000000' else 0,
                         unique_credits=1 if credit != '0.000000' else 0,
                         credit_amount_count=1 if credit != '0.000000' else 0,
                         credit_amount=credit,
                         net_amount=str(_decimal(billed) - _decimal(credit))))
    total = dict(
        invoice_count=sum(r['invoice_count'] for r in rows),
        unique_invoices=sum(r['unique_invoices'] for r in rows),
        invoice_amount_count=sum(r['invoice_amount_count'] for r in rows),
        billed_amount=str(sum(_decimal(r['billed_amount']) for r in rows)),
        credit_count=sum(r['credit_count'] for r in rows),
        unique_credits=sum(r['unique_credits'] for r in rows),
        credit_amount_count=sum(r['credit_amount_count'] for r in rows),
        credit_amount=str(sum(_decimal(r['credit_amount']) for r in rows)),
        net_amount=str(sum(_decimal(r['net_amount']) for r in rows)))
    result = dict(capability=OP + '.v1', rows=rows, total=total,
                  period={k: v for k, v in options.items() if k != 'periods'},
                  periods=[dict(p) for p in periods], currency='BS', grain='document_header',
                  granularity='per_period', scope='PERIOD_BREAKDOWN',
                  sql_parameters=parameters(OP, options),
                  period_sql_parameters=period_values(options),
                  read_only=True, sap_accessed=False,
                  source=dict(publication_id=PUBLICATION, snapshot_id=1408,
                              updated_at='2026-11-04T13:55:47.173006+00:00'),
                  definition='fixture', limitations='fixture')
    if 'sales_channel' in options:
        result.update(sales_channel=options['sales_channel'], channel_semantic_status='CONFIRMED',
                      channel_basis='materialized DMS numbering series', channel_limitations='fixture')
    return result


def _decimal(value):
    from decimal import Decimal
    return Decimal(value)


def single_result(options):
    return dict(capability=OP + '.v1',
                rows=[dict(invoice_count=1, unique_invoices=1, invoice_amount_count=1,
                           billed_amount='100.00', credit_count=0, unique_credits=0,
                           credit_amount_count=0, credit_amount='0.00', net_amount='100.00')],
                period=dict(options), currency='BS', grain='document_header',
                sql_parameters=parameters(OP, options), read_only=True, sap_accessed=False,
                source=dict(publication_id=PUBLICATION, snapshot_id=1408,
                            updated_at='2026-11-04T13:55:47.173006+00:00'))


@pytest.mark.parametrize('options', [
    dict(date_from=WINDOW['start'], date_to_exclusive=WINDOW['end_exclusive'], currency='BS',
         periods=[dict(AUGUST), dict(SEPTEMBER)]),
    dict(date_from=WINDOW['start'], date_to_exclusive=WINDOW['end_exclusive'], currency='BS',
         sales_channel='HORIZONTAL', periods=[dict(AUGUST), dict(SEPTEMBER)]),
])
def test_period_breakdown_parameters_and_validation(options):
    args = period_arguments(options)
    # 6 date bounds (two periods plus the union row) and the filter values twice.
    assert len(args) == 6 + 3 * 2 + (2 if 'sales_channel' in options else 0)
    validate_result(OP, options, period_result(options))


def test_breakdown_sql_arguments_cover_every_period_and_the_union():
    options = dict(date_from=WINDOW['start'], date_to_exclusive=WINDOW['end_exclusive'],
                   currency='BS', periods=[dict(AUGUST), dict(SEPTEMBER)])
    args = period_arguments(options)
    assert args[:6] == ['2026-08-01', '2026-09-01', '2026-09-01', '2026-10-01',
                        '2026-08-01', '2026-10-01']
    assert period_values(options) == [
        ['2026-08-01', '2026-09-01', 'SAP_B1_HANA', 'N', 'BS'],
        ['2026-09-01', '2026-10-01', 'SAP_B1_HANA', 'N', 'BS']]


@pytest.mark.parametrize('change', [
    dict(periods=[dict(AUGUST)]),
    dict(periods=[dict(AUGUST)] * (PERIOD_LIMIT + 1)),
    dict(periods=[dict(AUGUST), dict(JULY)]),
    dict(periods=[dict(AUGUST), {'start': '2026-09-02', 'end_exclusive': '2026-10-01'}]),
    dict(periods=[{'start': '2026-08-01'}]),
])
def test_period_set_parameter_rejection(change):
    options = dict(date_from=WINDOW['start'], date_to_exclusive=WINDOW['end_exclusive'],
                   currency='BS') | change
    with pytest.raises((ValueError, TypeError)):
        parameters(OP, options)


def test_period_set_must_cover_the_declared_window():
    options = dict(date_from=JULY['start'], date_to_exclusive=WINDOW['end_exclusive'],
                   currency='BS', periods=[dict(AUGUST), dict(SEPTEMBER)])
    with pytest.raises(ValueError):
        parameters(OP, options)


@pytest.mark.parametrize('change', ['total', 'periods', 'granularity', 'coverage', 'channel'])
def test_unreconciled_breakdown_is_rejected(change):
    options = dict(date_from=WINDOW['start'], date_to_exclusive=WINDOW['end_exclusive'],
                   currency='BS', periods=[dict(AUGUST), dict(SEPTEMBER)])
    result = period_result(options)
    if change == 'total':
        result['total']['net_amount'] = '1.00'
    elif change == 'periods':
        result['periods'] = [dict(SEPTEMBER), dict(AUGUST)]
        result['rows'] = list(reversed(result['rows']))
    elif change == 'granularity':
        result['granularity'] = 'per_window'
    elif change == 'coverage':
        result['rows'] = result['rows'][:1]
    else:
        result['sales_channel'] = 'HORIZONTAL'
    with pytest.raises(ValueError):
        validate_result(OP, options, result)


def test_breakdown_rendering_names_each_period_and_declares_the_total():
    options = dict(date_from=WINDOW['start'], date_to_exclusive=WINDOW['end_exclusive'],
                   currency='BS', sales_channel='HORIZONTAL', periods=[dict(AUGUST), dict(SEPTEMBER)])
    text = format_result(period_result(options))
    assert 'agosto de 2026' in text and 'septiembre de 2026' in text
    assert '1.869.222,92' in text and '1.841.198,64' in text
    assert 'no reemplaza el desglose' in text
    assert 'Canal horizontal' in text


def test_consolidated_union_is_declared_and_never_presented_as_months():
    async def run():
        async def query(operation, options, **kwargs):
            return single_result(options)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([proposal({
                                    '/metric': 'sales.net_amount',
                                    '/period': dict(WINDOW), '/period_mode': 'union',
                                    '/periods': [dict(AUGUST), dict(SEPTEMBER)]},
                                    intent='NEW_QUERY')]),
                                capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(event('¿Cuánto facturamos entre agosto y septiembre?'), permitted())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert 'un solo total' in response.text and 'desglose mensual' in response.text
        assert latest(handler.store)['execution_status'] == 'executed'
    asyncio.run(run())


def test_executed_breakdown_answers_the_two_months_separately():
    async def run():
        async def query(operation, options, **kwargs):
            assert options['periods'] == [dict(AUGUST), dict(SEPTEMBER)]
            return period_result(options)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([proposal({
                                    '/metric': 'sales.net_amount', '/sales_channel': 'HORIZONTAL',
                                    '/period': dict(WINDOW), '/period_mode': 'union',
                                    '/periods': [dict(AUGUST), dict(SEPTEMBER)],
                                    '/breakdown_by': 'period'}, intent='NEW_QUERY')]),
                                capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(
            event('¿Cuánto facturamos por el canal horizontal en agosto y septiembre de 2026? '
                  'Mostrame los dos importes por separado'), permitted())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert 'agosto de 2026' in response.text and 'septiembre de 2026' in response.text
        audit = latest(handler.store)
        assert audit['execution_status'] == 'executed' and audit['capability_calls'] == 1
        assert audit['confirmed_state']['breakdown_by'] == 'period'
    asyncio.run(run())


@pytest.mark.parametrize('mutate', [
    lambda result, options: result.update(rows=result['rows'][:1]),
    lambda result, options: result.update(granularity='per_window'),
    lambda result, options: result.update(sales_channel='SALON'),
])
def test_result_that_does_not_correspond_is_never_delivered(mutate):
    async def run():
        async def query(operation, options, **kwargs):
            result = period_result(options)
            return result
        capabilities = SalesCapabilities(sales_query=query)
        value = breakdown(sales_channel='HORIZONTAL')
        result = await capabilities.execute(value)
        mutate(result, dict())
        with pytest.raises(ValueError, match='capability_scope_mismatch'):
            capabilities.verify_representation(value, result)
    asyncio.run(run())


# --- D1: decisions are not availability evidence ---------------------------

def decision_proposals(action, **fields):
    sets = {'/metric': 'sales.net_amount', '/period': dict(WINDOW),
            '/period_mode': 'union', '/periods': [dict(AUGUST), dict(SEPTEMBER)],
            '/sales_channel': 'HORIZONTAL'}
    sets.update(fields)
    return proposal(sets, intent='NEW_QUERY', action=action)


@pytest.mark.parametrize('action', ['DIRECT_UNAVAILABLE', 'ANALYSIS_UNAVAILABLE'])
def test_interpreter_unavailability_never_renders_an_invented_gap(action):
    async def run():
        async def query(operation, options, **kwargs):
            return period_result(options)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([decision_proposals(action, **{
                                    '/breakdown_by': 'period'})]),
                                capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(event('Importe por canal horizontal, agosto y septiembre'), permitted())
        audit = latest(handler.store)
        assert audit['availability_inconsistency']['proposed_action'] == action
        assert 'todavía no está disponible' not in response.text
        if action == 'DIRECT_UNAVAILABLE':
            assert response.classification == 'DIRECT_AVAILABLE'
            assert audit['decision'] == 'EXECUTE'
            assert audit['availability_resolution'].startswith('AVAILABILITY_CONTRACT_CONSISTENT_EXECUTION')
        else:
            # No accredited operation answers an analysis: the researcher owns it.
            assert audit['availability_resolution'].startswith('ANALYSIS_ROUTED_TO_AUTHORIZED_RESEARCH')
            assert response.classification == 'ANALYSIS_UNAVAILABLE'
            assert 'datos comerciales del alcance sí están disponibles' in response.text
    asyncio.run(run())


def test_analysis_with_the_researcher_never_claims_missing_data():
    async def run():
        calls = []

        async def researcher(question, conversation_id, ctx):
            calls.append(question)
            return dict(status='READY', business_answer='Análisis acreditado.', publication='p',
                        snapshot='1', question_coverage='COMPLETE', model_calls=[], sql_executions=1)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([decision_proposals('ANALYSIS_UNAVAILABLE')]),
                                capabilities=SalesCapabilities(), researcher=researcher)
        response = await handler.handle(event('¿Por qué bajaron las ventas horizontales?'), permitted())
        assert calls and response.classification == 'DIRECT_AVAILABLE'
        assert 'no está disponible' not in response.text
    asyncio.run(run())


def test_a_real_denial_is_never_resolved_into_an_execution():
    async def run():
        calls = []
        async def query(operation, options, **kwargs):
            calls.append(options)
            return period_result(options)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([decision_proposals('DIRECT_UNAVAILABLE',
                                                                            **{'/breakdown_by': 'period'})]),
                                capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(event('Importe horizontal de agosto y septiembre'),
                                        permitted(frozenset({'fixture.business.read'})))
        assert response.classification == 'DENIED' and not calls
        assert latest(handler.store)['decision'] == 'DENIED'
    asyncio.run(run())


def test_accredited_gap_is_rendered_with_its_real_reason():
    value = breakdown(sales_channel='SALON')
    available = SalesCapabilities().availability(value)
    text = unavailable_response(value, available)
    assert 'canal' in text.lower() and 'todavía no está disponible' not in text
    assert 'agosto' in text and 'septiembre' in text


def test_a_confirmed_period_is_never_requested_again():
    for value in (state(period=dict(AUGUST)), breakdown()):
        text = unavailable_response(value, Availability(False, '', 'PERIOD_SET_UNSUPPORTED'))
        text += unavailable_response(value, Availability(False, '', 'PERIOD_UNRESOLVED'))
        assert 'indicame el mes' not in text.lower()


def test_measure_scope_mismatch_is_reported_and_not_delivered():
    async def run():
        async def query(operation, options, **kwargs):
            result = period_result(options)
            result['rows'] = result['rows'][:1]  # a consolidated answer
            return result
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([decision_proposals('EXECUTE', **{
                                    '/breakdown_by': 'period'})]),
                                capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(event('Importe horizontal por mes'), permitted())
        audit = latest(handler.store)
        assert audit['bmd']['category'] == 'MEASURE_SCOPE_MISMATCH'
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert '1.869.222,92' not in response.text and '1.841.198,64' not in response.text
    asyncio.run(run())


# --- D3: research limits ---------------------------------------------------

def test_research_limit_is_reported_as_a_limit_and_keeps_partial_evidence():
    async def run():
        async def researcher(question, conversation_id, ctx, **kwargs):
            return dict(status='RESOURCE_LIMITED', reason='observation_byte_budget',
                        business_answer='Investigación incompleta. Resultados parciales:\nAgosto: Bs 10,00',
                        observation_budget=dict(limit=32768, measured_bytes=41234),
                        publication='p', snapshot='1', model_calls=[], sql_executions=1)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([proposal({'/metric': 'sales.by_products',
                                                                   '/period': dict(AUGUST)},
                                                                  intent='NEW_QUERY')]),
                                capabilities=SalesCapabilities(), researcher=researcher)
        response = await handler.handle(event('Qué clientes compraron soda cáustica'), permitted())
        audit = latest(handler.store)
        assert audit['bmd']['category'] == 'RESEARCH_RESOURCE_LIMITED'
        assert audit['research_limit'] == dict(reason='observation_byte_budget', limit=32768,
                                               measured_bytes=41234)
        assert 'límite de procesamiento' in response.text
        assert 'Bs 10,00' in response.text
        assert 'no está disponible' not in response.text
    asyncio.run(run())


def test_research_limit_without_verified_evidence_still_explains_the_limit():
    async def run():
        async def researcher(question, conversation_id, ctx, **kwargs):
            return dict(status='RESOURCE_LIMITED', reason='observation_byte_budget',
                        business_answer='', observation_budget=dict(limit=32768),
                        publication='p', snapshot='1', model_calls=[], sql_executions=0)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([proposal({'/metric': 'sales.by_products'},
                                                                  intent='NEW_QUERY')]),
                                capabilities=SalesCapabilities(), researcher=researcher)
        response = await handler.handle(event('Qué clientes compraron soda cáustica'), permitted())
        assert 'límite de procesamiento' in response.text
        assert latest(handler.store)['bmd']['category'] == 'RESEARCH_RESOURCE_LIMITED'
    asyncio.run(run())

# --- continuity over confirmed periods -------------------------------------

def executed_breakdown(channel='HORIZONTAL'):
    """Run the real handler over a fixture reader and return (audit, results)."""
    async def run():
        async def query(operation, options, **kwargs):
            return period_result(options)
        handler = TelchiHandler(store=MemoryStore(), authorization=BusinessAuthorization(POLICY),
                                interpreter=Interpreter([proposal({
                                    '/metric': 'sales.net_amount', '/sales_channel': channel,
                                    '/period': dict(WINDOW), '/period_mode': 'union',
                                    '/periods': [dict(AUGUST), dict(SEPTEMBER)],
                                    '/breakdown_by': 'period'}, intent='NEW_QUERY')]),
                                capabilities=SalesCapabilities(sales_query=query))
        response = await handler.handle(
            event('¿Cuánto facturamos por el canal horizontal en agosto y septiembre de 2026? '
                  'Mostrame los dos importes por separado'), permitted())
        assert response.classification == 'DIRECT_AVAILABLE'
        return latest(handler.store)
    return asyncio.run(run())


def test_a_delivered_breakdown_exposes_one_operand_per_period():
    from modules.telchi.assistant.monetary_comparison import accredited_results
    audit = executed_breakdown()
    results = accredited_results(audit, 'turn-1', audit['owner'])
    assert [r['period']['date_from'] for r in results] == [AUGUST['start'], SEPTEMBER['start']]
    assert [r['amount'] for r in results] == ['1869222.920000', '1841198.640000']
    assert {r['metric'] for r in results} == {'net_amount'}
    assert len({r['result_id'] for r in results}) == 2
    assert all(r['required_permission'] == GRANT for r in results)


def test_the_difference_reuses_confirmed_periods_without_a_new_query():
    from modules.telchi.assistant.monetary_comparison import accredited_results, calculate
    audit = executed_breakdown()
    results = accredited_results(audit, 'turn-1', audit['owner'])
    august, september = (r['result_id'] for r in results)
    record, text = calculate(dict(intent='MONETARY_COMPARISON', action='CALCULATE',
        clarification=None, comparison=dict(target_id=september, baseline_id=august,
                                            mode='difference')), results, audit['owner'])
    assert record['formula'] == 'target - baseline'
    assert record['difference'].startswith('-28024.280000')
    assert 'Diferencia de venta neta documental' in text
    assert 'septiembre de 2026' in text and 'agosto de 2026' in text


def test_an_operand_from_another_owner_or_permission_is_never_reused():
    from modules.telchi.assistant.monetary_comparison import accredited_results
    audit = executed_breakdown()
    other = tuple(['someone-else', *audit['owner'][1:]])
    assert accredited_results(audit, 'turn-1', other) == []
    # Without a declared breakdown the result is never split into invented months.
    assert accredited_results(
        dict(audit, confirmed_state=dict(audit['confirmed_state'], breakdown_by=None)),
        'turn-1', audit['owner']) == []


def test_a_period_without_documents_is_not_a_zero_operand():
    from modules.telchi.assistant.monetary_comparison import accredited_results
    audit = deepcopy(executed_breakdown())
    audit['execution_result']['rows'][1].update(invoice_count=0)
    assert accredited_results(audit, 'turn-1', audit['owner']) == []


def test_comparing_one_period_against_itself_is_rejected():
    from modules.telchi.assistant.monetary_comparison import accredited_results, calculate
    audit = executed_breakdown()
    results = accredited_results(audit, 'turn-1', audit['owner'])
    with pytest.raises(ValueError, match='ambiguous_comparison'):
        calculate(dict(intent='MONETARY_COMPARISON', action='CALCULATE', clarification=None,
                       comparison=dict(target_id=results[0]['result_id'],
                                       baseline_id=results[0]['result_id'], mode='difference')),
                  results, audit['owner'])

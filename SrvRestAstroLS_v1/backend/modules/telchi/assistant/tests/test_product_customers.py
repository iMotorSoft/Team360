"""Product -> billed customer reuses the existing commercial breakdown.

Covers the audited failed turn of 08/11/2026: a product named in a previous
ranking and a follow-up asking who bought it. No new capability is created.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import ProductResolutionError, SalesCapabilities
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler, capability_failure
from modules.telchi.assistant.product_routing import request_contract
from modules.telchi.datalake.messaging_sales_query import TelchiQueryError
from .test_assistant import Interpreter, MemoryStore, context, event, proposal

OCTOBER = {'start': '2026-10-01', 'end_exclusive': '2026-11-01'}
ROWS = [
    {'key': 'L01772', 'label': 'SULFATO DE COBRE x 25kg.', 'amount': '321087.74'},
    {'key': 'L01010', 'label': 'SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg.', 'amount': '247286.63'},
    {'key': 'L00504', 'label': 'BENZOATO DE SODIO x 1kg.', 'amount': '247228.01'},
]
REFERENCE = {'rows': ROWS, 'label': 'producto', 'capability': 'sales.commercial_line_amount_by.v1'}


def ranked_state():
    state = deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS | engine.SCOPE_FIELDS)
    state.update(metric='sales.commercial_line_amount_by',
                 requested_metrics=['sales.commercial_line_amount_by'], group_by='sap_product',
                 ranking_by='amount', limit=3, period=dict(OCTOBER),
                 focus={'product': 'L01772', 'product_label': 'SULFATO DE COBRE x 25kg.'})
    engine.validate(state)
    return state


def failed_proposal():
    # Exactly the persisted proposal of turn 46000830: NEW_QUERY products.search,
    # which dropped the period and the commercial context.
    return proposal({'/metric': 'products.search', '/entity_mention': None,
                     '/schema_version': 2, '/requested_metrics': ['products.search'],
                     '/temporal_reference': None, '/product_search_text': 'SODA CAUSTICA de 25'},
                    unset=['/period', '/comparison', '/branches', '/sales_channel', '/group_by',
                           '/ranking_by', '/limit', '/product_target', '/customer_target',
                           '/business_category', '/selected_item_codes',
                           '/ranking_target_item_code', '/ranking_detail', '/physical_focus',
                           '/period_mode', '/breakdown_by'], intent='NEW_QUERY')


def test_audited_turn_routes_to_existing_capability_and_preserves_period():
    before = ranked_state()
    corrected = request_contract(failed_proposal(), 'la SODA CAUSTICA de 25 a quien se la vendidos',
                                 before, REFERENCE)
    processed = engine.process(before, corrected, {}, '46000830')
    assert processed['committed'] is True
    state = processed['state_after']
    assert state['metric'] == 'sales.commercial_line_amount_by'
    assert state['group_by'] == 'card_code'
    assert state['product_target'] == 'L01010'
    assert state['product_search_text'] is None
    assert state['period'] == OCTOBER
    assert state['ranking_by'] is None
    assert corrected['intent'] == 'REFINE'
    # The existing capability compiles the exact read-only plan.
    from modules.telchi.assistant.business_plan import build
    plan = build(state)
    assert plan['filters']['item_code'] == 'L01010'
    assert plan['filters']['card_code'] is None
    assert plan['group_by'] == 'card_code'
    assert plan['date_from'] == '2026-10-01'


def test_explicit_query_without_previous_context_uses_catalog_text_not_a_code():
    corrected = request_contract(failed_proposal(), 'a quien le vendimos soda caustica x 25',
                                 deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS),
                                 None)
    state = engine.process(deepcopy(engine.DEFAULTS), corrected, {}, 'explicit')['state_after']
    # An ASK keeps the known plan in the pending proposal, not in the active state.
    state = state['pending']['proposed']
    assert state['group_by'] == 'card_code'
    assert state['product_target'] is None
    assert state['product_search_text'] == 'SODA CAUSTICA de 25'
    # No period in the question: ask, never invent October.
    assert state['period'] is None
    assert corrected['action'] == 'ASK'


@pytest.mark.parametrize('text,proposal_text', [
    ('buscá soda caustica', 'soda caustica'),
    ('presentaciones de soda caustica', 'soda caustica'),
])
def test_catalog_search_is_not_converted_to_sales(text, proposal_text):
    p = proposal({'/metric': 'products.search', '/product_search_text': proposal_text,
                  '/requested_metrics': ['products.search'], '/schema_version': 2}, intent='NEW_QUERY')
    assert request_contract(p, text, deepcopy(engine.EMPTY), None) == p


def test_customer_as_subject_is_not_converted():
    p = proposal({'/metric': 'sales.commercial_line_amount_by', '/group_by': 'sap_product',
                  '/customer_target': 'C000061', '/period': dict(OCTOBER),
                  '/requested_metrics': ['sales.commercial_line_amount_by'], '/schema_version': 2},
                 intent='REFINE')
    assert request_contract(p, 'qué otros productos nos compró ese cliente', ranked_state(), REFERENCE) == p


def test_ambiguous_previous_rows_are_not_guessed():
    rows = ROWS + [{'key': 'L09999', 'label': 'SODA CAUSTICA x 25kg. OTRA', 'amount': '1'}]
    corrected = request_contract(failed_proposal(), 'a quien le vendimos la soda caustica de 25',
                                 ranked_state(), {'rows': rows})
    assert corrected['state_delta']['set']['/product_target'] is None
    assert corrected['state_delta']['set']['/product_search_text'] == 'SODA CAUSTICA de 25'


def catalog_row(code, description, rank=1, sell='Y'):
    return {'item_code': code, 'description': description, 'match_rank': rank,
            'sell_item': sell, 'namespace': 'SAP_HANA', 'status': 'ACTIVE',
            'catalog_sales_uom_id': None}


def product_result(options, rows):
    return dict(capability='products.search.v1', parameters=options, rows=rows,
                source={'publication_id': 'foundation_38680850adc058b1bb11887632b7b681',
                        'snapshot_id': 1408},
                truncated=False, read_only=True, sap_accessed=False)


def named_state(text='SODA CAUSTICA de 25'):
    state = deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS | engine.SCOPE_FIELDS)
    state.update(metric='sales.commercial_line_amount_by',
                 requested_metrics=['sales.commercial_line_amount_by'], group_by='card_code',
                 product_search_text=text, period=dict(OCTOBER), limit=10)
    engine.validate(state)
    return state


def test_catalog_resolution_is_unique_and_clears_the_text():
    async def run():
        async def query(op, options, **kwargs):
            return product_result(options, [
                catalog_row('L00180', 'BOLSA VACIA SODA CAUSTICA x 1kg.'),
                catalog_row('L01010', 'SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg.'),
            ])
        caps = SalesCapabilities(product_query=query)
        state = named_state()
        chosen = await caps.resolve_commercial_product(state)
        assert chosen['item_code'] == 'L01010'
        assert state['product_target'] == 'L01010'
        assert state['product_search_text'] is None
        assert state['focus']['product'] == 'L01010'
    asyncio.run(run())


def test_catalog_resolution_asks_when_several_are_compatible():
    async def run():
        async def query(op, options, **kwargs):
            return product_result(options, [
                catalog_row('L01010', 'SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg.'),
                catalog_row('L01011', 'SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg. OTRA'),
            ])
        caps = SalesCapabilities(product_query=query)
        with pytest.raises(ProductResolutionError) as failure:
            await caps.resolve_commercial_product(named_state())
        assert len(failure.value.candidates) == 2
    asyncio.run(run())


def test_catalog_resolution_never_invents_a_code():
    async def run():
        async def query(op, options, **kwargs):
            return product_result(options, [])
        caps = SalesCapabilities(product_query=query)
        with pytest.raises(ProductResolutionError) as failure:
            await caps.resolve_commercial_product(named_state())
        assert failure.value.reason == 'product_not_found'
        assert failure.value.candidates == []
    asyncio.run(run())


@pytest.mark.parametrize('code,category,classification', [
    ('product_binding_changed', 'PUBLICATION_INCOMPATIBLE', 'ERROR'),
    ('FOUNDATION_READ_BINDING_INVALID', 'PUBLICATION_INCOMPATIBLE', 'ERROR'),
    ('commercial_result_binding_mismatch', 'PUBLICATION_INCOMPATIBLE', 'ERROR'),
    ('Commercial publication accreditation missing', 'PUBLICATION_INCOMPATIBLE', 'ERROR'),
    ('product_worker_error', 'CAPABILITY_UNAVAILABLE', 'ERROR'),
    ('commercial_amount_worker_error', 'CAPABILITY_UNAVAILABLE', 'ERROR'),
    ('commercial_quantity_unaccredited', 'DATA_UNAVAILABLE', 'DIRECT_UNAVAILABLE'),
    ('item_code_absent_from_catalog', 'DATA_UNAVAILABLE', 'DIRECT_UNAVAILABLE'),
    ('unexpected_driver_error', 'EXECUTION_ERROR', 'ERROR'),
])
def test_failure_taxonomy_is_deterministic_and_safe(code, category, classification):
    failure = capability_failure(TelchiQueryError(code), {'metric': 'products.search'})
    assert failure['category'] == category
    assert failure['classification'] == classification
    assert failure['retryable'] is not None  # always present in the audit contract
    assert 'SELECT' not in failure['text'] and 'password' not in failure['text'].lower()


def test_handler_audits_publication_failure_without_retry_and_allows_new_query():
    async def run():
        state = ranked_state()
        calls = {'n': 0}

        async def execute(_state):
            calls['n'] += 1
            if calls['n'] == 1:
                raise TelchiQueryError('product_binding_changed')
            return dict(capability='sales.coverage.v1', rows=[dict(
                first_date='2026-09-01T00:00:00', last_date='2026-10-31T00:00:00',
                documents=10, latest_month_with_rows='2026-10',
                complete_month_certified=False)],
                source=dict(publication_id='fixture', snapshot_id=1, updated_at='2026-11-01T00:00:00'),
                read_only=True, sap_accessed=False, sql='', sql_parameters=[],
                sql_duration_ms=0, grain='invoice_header', document_type='OINV',
                limitations='Active invoices (N), by DocDate, not entry timestamp; excludes credit memos. Not net sales. Completeness not certified.')

        c = context()
        c = replace(c, sender_identity=replace(c.sender_identity, permissions=frozenset({
            'fixture.business.read', 'telchi.products.search.read.v1',
            'telchi.sales.by_products.read.v1', 'telchi.sales.coverage.read.v1',
            'telchi.sales.commercial_line_amount_by.read.v1'})))
        store = MemoryStore()
        owner = ['dev', 'telchi', 'workspace', 'channel', 'user']
        store.states[tuple(owner) + ('conversation',)] = deepcopy(state)
        handler = TelchiHandler(store=store, interpreter=Interpreter([
            proposal({'/metric': 'products.search', '/product_search_text': 'soda',
                      '/requested_metrics': ['products.search'], '/schema_version': 2},
                     intent='NEW_QUERY'),
            proposal({'/metric': 'sales.coverage', '/period': None,
                      '/requested_metrics': ['sales.coverage'], '/schema_version': 2},
                     intent='NEW_QUERY'),
        ]), authorization=BusinessAuthorization(
            BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True)),
            capabilities=SalesCapabilities())
        handler.capabilities.execute = execute
        first = await handler.handle(event('la SODA CAUSTICA de 25 a quien se la vendidos'), c)
        audit = store.audits[(tuple(owner) + ('conversation',), 'turn-1')]
        assert first.classification == 'ERROR'
        assert audit['bmd']['category'] == 'PUBLICATION_INCOMPATIBLE'
        assert audit['capability_failure']['reason'] == 'product_binding_changed'
        assert audit['capability_failure']['retryable'] is False
        assert 'Intentá nuevamente' not in first.text
        assert 'Continuar' not in first.text
        # A different consultation is not blocked by the failed operation.
        second = await handler.handle(event('cobertura de facturas'), replace(c, correlation_id='turn-2'))
        assert second.classification == 'DIRECT_AVAILABLE'
        assert calls['n'] == 2
    asyncio.run(run())

AUDITED_QUESTION = ('¿Qué clientes compraron soda cáustica x25 kg en octubre de 2026, '
                    'pero no en septiembre?')
SEPTEMBER = {'start': '2026-09-01', 'end_exclusive': '2026-10-01'}


def audited_proposal():
    """Exactly the interpretation persisted for turn 64f3a37c of 08/11/2026."""
    return proposal({
        '/limit': 10,
        '/metric': 'sales.commercial_line_amount_by',
        '/period': dict(OCTOBER),
        '/group_by': 'card_code',
        '/comparison': dict(SEPTEMBER),
        '/entity_mention': None,
        '/schema_version': 2,
        '/requested_metrics': ['sales.commercial_line_amount_by'],
        '/temporal_reference': None,
        '/product_search_text': 'soda cáustica x25 kg',
        '/selected_item_codes': [],
    }, unset=['/ranking_by', '/product_target', '/customer_target', '/period_mode',
              '/breakdown_by'], intent='REFINE')


def test_audited_exclusion_is_not_dropped_by_the_customer_contract():
    # Dropping the baseline executed a different question: «who bought in
    # October», without the requested «and not in September».
    corrected = request_contract(audited_proposal(), AUDITED_QUESTION, ranked_state(), None)
    assert corrected['state_delta']['set']['/comparison'] == SEPTEMBER
    assert corrected['state_delta']['set']['/product_search_text'] == 'soda cáustica x25 kg'
    assert corrected['action'] == 'EXECUTE'


def test_audited_question_is_refused_as_a_catalog_gap_not_as_missing_data():
    corrected = request_contract(audited_proposal(), AUDITED_QUESTION, ranked_state(), None)
    state = engine.process(ranked_state(), corrected, {}, '64f3a37c')['state_after']
    caps = SalesCapabilities()
    available = caps.availability(state)
    assert available.allowed is False
    assert available.category == 'COMPARISON_UNSUPPORTED'
    assert state['product_search_text'] == 'soda cáustica x25 kg'


def test_packaging_spacing_resolves_the_accredited_product_of_the_audited_question():
    async def run():
        async def query(op, options, **kwargs):
            assert op == 'products.search'
            # The catalog containment test is literal: the whole mention with
            # «x25 kg» matches nothing, exactly as in the audited turn.
            if 'x25 kg' in options['text']:
                return product_result(options, [])
            return product_result(options, [
                catalog_row('L00180', 'BOLSA VACIA SODA CAUSTICA x 1kg.'),
                catalog_row('L01010', 'SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg.'),
                catalog_row('L01013', 'SODA CAUSTICA (HIDROXIDO DE SODIO) x 1kg. REG. 3000-02139-24D'),
            ])
        caps = SalesCapabilities(product_query=query)
        state = named_state('soda cáustica x25 kg')
        chosen = await caps.resolve_commercial_product(state)
        assert chosen['item_code'] == 'L01010'
        assert state['focus']['product'] == 'L01010'
    asyncio.run(run())


def test_unresolvable_mention_still_reports_no_accredited_product():
    async def run():
        async def query(op, options, **kwargs):
            return product_result(options, [])
        caps = SalesCapabilities(product_query=query)
        with pytest.raises(ProductResolutionError) as failure:
            await caps.resolve_commercial_product(named_state('producto inexistente xyz'))
        assert failure.value.reason == 'product_not_found'
        assert failure.value.candidates == []
    asyncio.run(run())

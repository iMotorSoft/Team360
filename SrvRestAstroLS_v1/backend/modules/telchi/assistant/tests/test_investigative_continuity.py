"""A discovered entity becomes the subject of the next investigation.

Real turn of 09/11/2026: after selecting the billed customer from a persisted
research list, «decime BATEBOL que otras cosas compro» was rejected with
«No pude interpretar la consulta» because the interpreter preserved the
customer mention and the resolved CardCode together. The card code was already
the authorized target, so the mention was not an unresolved filter.

These tests use the existing commercial breakdown and the real state engine.
No new capability, router or per-question phrase is introduced.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import business_plan, state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.commercial_answer import format_commercial
from modules.telchi.assistant.commercial_continuity import request_contract
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy, TelchiHandler
from modules.telchi.datalake import commercial_line_amount_by_query as reader

from .test_assistant import Interpreter, MemoryStore, context, event, latest, proposal

OCTOBER = {'start': '2026-10-01', 'end_exclusive': '2026-11-01'}
PERMISSION = 'telchi.sales.commercial_line_amount_by.read.v1'
PUBLICATION = 'foundation_38680850adc058b1bb11887632b7b681'


def previous_state():
    """The persisted state of the audited conversation before the failed turn."""
    state = deepcopy(engine.EMPTY | engine.INTENT_V2 | engine.PRODUCT_FIELDS | engine.SCOPE_FIELDS)
    state.update(metric='sales.commercial_line_amount_by',
                 requested_metrics=['sales.commercial_line_amount_by'],
                 group_by='card_code', period=dict(OCTOBER), limit=10,
                 focus={'product': 'L01772', 'product_label': 'SULFATO DE COBRE x 25kg.'},
                 product_search_text='soda cáustica x25 kg')
    engine.validate(state)
    return state


def discovery_proposal(card_code, mention):
    """A new product investigation of the customer discovered in the prior list."""
    return proposal({
        '/metric': 'sales.commercial_line_amount_by',
        '/requested_metrics': ['sales.commercial_line_amount_by'],
        '/group_by': 'sap_product',
        '/customer_target': card_code,
        '/entity_mention': {'text': mention, 'type': None},
        '/schema_version': 2,
        '/temporal_reference': None,
    }, unset=['/product_search_text', '/selected_item_codes'], intent='REFINE')


def test_other_things_keeps_the_discussed_product_as_a_presentation_reference():
    before = previous_state()
    before.update(product_target='L01772', product_search_text=None,
                  customer_target='C001077', group_by='sap_product')
    engine.validate(before)
    corrected = request_contract(proposal({}, intent='REFINE'),
                                 'y qué otras cosas compró ese cliente en octubre de 2026', before)
    out = engine.process(before, corrected, {}, 'turn')
    assert out['committed'] is True, out.get('contract_error')
    assert out['state_after']['excluded_product'] == 'L01772'
    assert out['state_after']['customer_target'] == 'C001077'


def test_codes_cited_by_the_research_result_become_presentation_exclusions():
    before = previous_state()
    reference = dict(
        rows=[{'card_code': 'C001077', 'customer_name': 'BATEBOL S.A.'}],
        manifest=dict(filter_expression=(
            'CONJUNCTION_AND(item_code COMPARE_EQUAL "L01010",'
            'item_code COMPARE_EQUAL "98526300")')))
    corrected = request_contract(discovery_proposal('C001077', 'BATEBOL'),
                                 'decime BATEBOL que otras cosas compro', before, reference)
    out = engine.process(before, corrected, {}, 'turn')
    assert out['committed'] is True, out.get('contract_error')
    state = out['state_after']
    assert state['excluded_product'] is None
    assert state['excluded_products'] == ['L01010', '98526300']
    assert state['customer_target'] == 'C001077'
    assert state['limit'] == 7
    rows = [dict(key='L01010', label='SODA CAUSTICA', amount='300'),
            dict(key='98526300', label='SODA CAUSTICA PERLADA', amount='20'),
            dict(key='L00974', label='ACIDO ACETICO', amount='60')]
    result = dict(parameters={'group_by': 'sap_product', 'filters': {'card_code': 'C001077'},
                              'date_from': OCTOBER['start'],
                              'date_to_exclusive': OCTOBER['end_exclusive']},
                  rows=rows, total={'amount': '380'}, coverage={})
    text = format_commercial(result, {'excluded_products': state['excluded_products']})
    assert 'L01010 ·' not in text and '98526300 ·' not in text
    assert 'excluyendo 98526300, L01010' in text
    assert 'L00974 ·' in text


@pytest.mark.parametrize('card_code,mention', [
    ('C001077', 'BATEBOL'),
    ('C012227', 'CURTIEMBRE TAURO LTDA.'),
])
def test_discovered_customer_becomes_the_new_commercial_subject(card_code, mention):
    out = engine.process(previous_state(), discovery_proposal(card_code, mention), {}, 'turn')
    assert out['committed'] is True, out.get('contract_error')
    state = out['state_after']
    assert state['customer_target'] == card_code
    assert state['group_by'] == 'sap_product'
    assert state['period'] == OCTOBER
    assert state['product_search_text'] is None
    # The original mention survives as a reference, not as a hidden filter.
    assert state['entity_mention'] == {'text': mention, 'type': None}
    available = SalesCapabilities().availability(state)
    assert available.allowed, available.reason
    plan = business_plan.build(state)
    assert plan['filters']['card_code'] == card_code
    assert plan['filters']['item_code'] is None
    assert plan['filters']['category'] is None
    assert plan['group_by'] == 'sap_product'
    assert plan['date_from'] == OCTOBER['start']


def test_an_unresolved_entity_without_a_resolved_target_still_fails_closed():
    before = previous_state()
    before.update(customer_target=None, product_search_text=None)
    out = engine.process(before, proposal({
        '/metric': 'sales.commercial_line_amount_by',
        '/requested_metrics': ['sales.commercial_line_amount_by'],
        '/group_by': 'sap_product',
        '/entity_mention': {'text': 'FARMACORP', 'type': None},
        '/schema_version': 2,
    }, intent='REFINE'), {}, 'turn')
    assert out['committed'] is False
    state = dict(out['state_after'], group_by='sap_product',
                 entity_mention={'text': 'FARMACORP', 'type': None})
    assert SalesCapabilities().availability(state).category == 'MAPPING_MISSING'


def test_a_category_entity_still_cannot_overwrite_the_product_scope():
    before = previous_state()
    before.update(metric='sales.product_line_amount_ranking',
                  requested_metrics=['sales.product_line_amount_ranking'],
                  business_category='LAB_FINISHED_PRODUCT', group_by='sap_product')
    engine.validate(before)
    out = engine.process(before, proposal({
        '/entity_mention': {'text': 'FARMACORP', 'type': None}}, intent='REFINE'), {}, 'turn')
    assert out['committed'] is False


def commercial_result(options):
    rows = [
        dict(key='L01010', label='SODA CAUSTICA (HIDROXIDO DE SODIO) x 25kg.',
             amount='300.00', line_count=2, document_count=1, quantity='10'),
        dict(key='L00504', label='BENZOATO DE SODIO x 1kg.',
             amount='80.63', line_count=1, document_count=1, quantity='4'),
    ]
    total = dict(amount='380.63', line_count=3, document_count=2, product_count=2,
                 customer_count=1, quantity='14')
    result = dict(capability=reader.CAPABILITY, parameters=options, plan=reader.plan_of(options),
                  definition=reader.MEASURE, currency='BS', rows=rows, full_breakdown=rows,
                  total=total, universe_total=None, period_breakdown=[], exceptions=[],
                  accreditation='verified', quantity_limitation=reader.QUANTITY_LIMITATION,
                  coverage=dict(first_date='2026-10-01T00:00:00', last_date='2026-10-31T00:00:00',
                                complete=False),
                  limitations=reader.LIMITATIONS, read_only=True, sap_accessed=False,
                  source=dict(publication_id=PUBLICATION, snapshot_id=1408,
                              updated_at='2026-11-01T00:00:00'),
                  focus={'card_code': options['filters']['card_code'],
                         'customer_label': 'CLIENTE DESCUBIERTO S.A.'})
    result['reconciliation'] = reader.reconcile(rows, total, 'sap_product')
    return result


@pytest.mark.parametrize('card_code,mention,question,label', [
    ('C001077', 'BATEBOL', 'decime BATEBOL que otras cosas compro', 'BATEBOL S.A.'),
    ('C012227', 'CURTIEMBRE TAURO LTDA.',
     '¿Qué más compró CURTIEMBRE TAURO LTDA. en octubre de 2026?', 'CURTIEMBRE TAURO LTDA.'),
])
def test_handler_executes_a_new_commercial_query_for_the_discovered_entity(
        card_code, mention, question, label):
    async def run():
        queries = []

        async def commercial_query(options, **kwargs):
            queries.append(deepcopy(options))
            result = commercial_result(options)
            result['focus']['customer_label'] = label
            return result

        identity = replace(context().sender_identity,
                           permissions=frozenset({'fixture.business.read', PERMISSION}))
        ctx = replace(context(), sender_identity=identity)
        store = MemoryStore()
        key = tuple([ctx.channel.environment, ctx.channel.tenant_id, ctx.channel.workspace_id,
                     ctx.channel.channel_id, ctx.sender_identity.user_id]) + (ctx.conversation_id,)
        store.states[key] = previous_state()
        handler = TelchiHandler(
            store=store,
            authorization=BusinessAuthorization(BusinessPolicy(
                'telchi', 'workspace', 'fixture.business.read', True, True)),
            interpreter=Interpreter([discovery_proposal(card_code, mention)]),
            capabilities=SalesCapabilities(commercial_query=commercial_query))
        response = await handler.handle(event(question), ctx)
        audit = latest(store)
        assert response.classification == 'DIRECT_AVAILABLE'
        assert audit['decision'] == 'EXECUTE'
        assert audit['execution_status'] == 'executed'
        assert audit['capability_calls'] == 1
        assert len(queries) == 1
        assert queries[0]['filters']['card_code'] == card_code
        assert queries[0]['group_by'] == 'sap_product'
        assert queries[0]['date_from'] == OCTOBER['start']
        assert queries[0]['date_to_exclusive'] == OCTOBER['end_exclusive']
        assert label in response.text
        assert 'Bs 300,00' in response.text
        assert 'No pude interpretar' not in response.text

    asyncio.run(run())
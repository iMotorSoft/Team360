from copy import deepcopy
import asyncio
from types import SimpleNamespace
import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.commercial_continuity import request_contract, shares, format_category_analysis
from modules.telchi.assistant.commercial_answer import format_commercial
from .test_business_conversation import scoped_state, JULY, AUGUST, WINDOW
from .test_assistant import proposal

SEPTEMBER = dict(start='2026-09-01', end_exclusive='2026-10-01')


def customer_state():
    return scoped_state(metric='sales.commercial_line_amount_by', requested_metrics=['sales.commercial_line_amount_by'],
        period=WINDOW, periods=[JULY, AUGUST], period_mode='union', breakdown_by='period', group_by='card_code',
        business_category='LAB_FINISHED_PRODUCT', product_target='L03281', customer_target='C000061',
        focus={'product': 'L03281', 'customer': 'C000061'})


def committed(before, p, text):
    out = engine.process(before, request_contract(p, text, before), {}, 'v2')
    assert out['committed'], out.get('contract_error')
    return out['state_after']


def test_other_products_drops_implicit_category_but_keeps_account_and_periods():
    s = committed(customer_state(), proposal({'group_by': 'sap_product'}), 'y que otros productos nos compro en esos meses')
    assert s['customer_target'] == 'C000061' and s['period'] == WINDOW
    assert s['periods'] == [JULY, AUGUST]
    assert s['excluded_product'] == 'L03281' and s['product_target'] is None
    assert s['business_category'] is None and s['entity_mention'] is None
    assert s['group_by'] == 'sap_product' and s['breakdown_by'] is None


def test_explicit_category_is_not_removed():
    s = committed(customer_state(), proposal({}), 'que otros productos terminados nos compro')
    assert s['business_category'] == 'LAB_FINISHED_PRODUCT'


@pytest.mark.parametrize('text', [
    'quiero saber el porcentaje de la venta total de septiembre cual es el porcentaje de productos terminados, medicamentos, materia prima, fraccionados',
    'que procentaje de ventas globales son productos terminados y materia prima',
])
def test_global_analysis_abandons_customer_product_and_union(text):
    p = proposal({'/period': SEPTEMBER}, intent='NEW_QUERY', action='DIRECT_UNAVAILABLE')
    s = committed(customer_state(), p, text)
    assert s['period'] == SEPTEMBER and s.get('periods') is None
    assert s['customer_target'] is None and s['product_target'] is None and s['business_category'] is None
    assert 'LAB_FINISHED_PRODUCT' in s['analysis_categories']
    follow = committed(s, proposal({}, intent='EXPLAIN', action='DIRECT_UNAVAILABLE'), 'el procentaje de venta de productos terminados')
    assert follow['period'] == SEPTEMBER
    assert follow['analysis_categories'] == ['LAB_FINISHED_PRODUCT']


def test_customer_percentage_is_not_replaced_by_global_analysis():
    p = proposal({}, action='DIRECT_UNAVAILABLE')
    assert request_contract(p, 'porcentaje de productos terminados del cliente FARMACORP', customer_state())['action'] == 'DIRECT_UNAVAILABLE'


def compatible():
    parameters = dict(date_from=SEPTEMBER['start'], date_to_exclusive=SEPTEMBER['end_exclusive'])
    common = dict(source={'publication_id': 'p', 'snapshot_id': 1, 'updated_at': 'now'},
                  definition='lines', currency='BS', coverage={'complete': False})
    r = dict(common, parameters=dict(parameters, category='LAB_FINISHED_PRODUCT'), rows=[{'amount': '25', 'line_count': 1}])
    d = dict(common, parameters=dict(parameters, filters={'category': None, 'item_code': None, 'card_code': None}),
             total={'amount': '100'}, exceptions=[], accreditation='verified', reconciliation={'difference': '0'})
    return {'LAB_FINISHED_PRODUCT': {'result': r}}, d


def test_decimal_percentage_requires_same_source_measure_period_and_coverage():
    c, d = compatible()
    s = {'period': SEPTEMBER}
    assert shares(s, c, d) == {'LAB_FINISHED_PRODUCT': '25.00'}
    for key, value in [('definition', 'headers_with_tax'), ('currency', 'USD'), ('source', {}), ('coverage', {'complete': True})]:
        bad = deepcopy(d); bad[key] = value
        assert shares(s, c, bad) == {}
    d['exceptions'] = [{'excluded': True}]
    assert shares(s, c, d) == {}


def test_partial_answer_keeps_amount_without_a_percentage():
    c, _ = compatible()
    s = {'period': SEPTEMBER, 'analysis_categories': ['LAB_FINISHED_PRODUCT', 'MEDICATIONS']}
    text = format_category_analysis(s, c)
    assert 'Bs 25,00' in text and 'Porcentaje no calculado' in text
    assert 'Medicamentos: clasificación no acreditada' in text


def test_supported_classification_remains_visible_in_the_business_answer():
    c, _ = compatible()
    c['LAB_FINISHED_PRODUCT']['result']['classification'] = {'quality_lines': {'SUPPORTED': 1}}
    text = format_category_analysis({'period': SEPTEMBER, 'analysis_categories': ['LAB_FINISHED_PRODUCT']}, c)
    assert '1 línea con clasificación respaldada (SUPPORTED), no toda validada' in text


def test_other_products_shows_five_names_and_excludes_reference():
    rows = [dict(key=f'L{i}', label=f'Producto {i}', amount='10') for i in range(6)]
    r = dict(parameters={'group_by': 'sap_product', 'filters': {'card_code': 'C000061'},
                         'date_from': JULY['start'], 'date_to_exclusive': AUGUST['end_exclusive'], 'periods': [JULY, AUGUST]},
             rows=rows, total={'amount': '60'}, coverage={})
    text = format_commercial(r, {'excluded_product': 'L0'})
    assert 'L0 ·' not in text
    assert all(f'L{i} · Producto {i} — Bs 10,00' in text for i in range(1, 6))
    assert 'julio' in text and 'agosto' in text
    assert len(text) < 1500


def test_ordinals_match_the_five_additional_products_shown():
    from modules.telchi.assistant.result_references import presentation
    s = committed(customer_state(), proposal({}), 'que otros productos nos compro en esos meses')
    rows = [dict(key='L03281', label='Referencia', amount='10')] + [
        dict(key=f'X{i}', label=f'Producto {i}', amount='9') for i in range(5)]
    result = dict(capability='sales.commercial_line_amount_by.v1', rows=rows,
                  parameters={'group_by': 'sap_product'}, source={'publication_id': 'p', 'snapshot_id': 1, 'updated_at': 'now'})
    audit = dict(owner=['owner'], execution_status='executed', business_rbac_verified=True,
                 confirmed_state=s, execution_result=result, required_permission='permission',
                 response_prepared={'classification': 'DIRECT_AVAILABLE'})
    view = presentation(audit, 'result', ['owner'], 'conversation')
    assert [r['key'] for r in view['rows']] == [f'X{i}' for i in range(5)]


def test_more_products_preserves_scope_and_advances_the_page():
    before = committed(customer_state(), proposal({}), 'que otros productos nos compro en esos meses')
    after = committed(before, proposal({}, intent='NEW_QUERY', action='DIRECT_UNAVAILABLE'), 'mostrame mas')
    assert after['excluded_product'] == 'L03281' and after['product_offset'] == 5
    assert after['customer_target'] == 'C000061' and after['periods'] == [JULY, AUGUST]


@pytest.mark.parametrize('product,customer', [('X999', 'Z0123'), ('L01613', 'C098765')])
def test_scope_transfer_is_not_hardcoded_to_the_incident(product, customer):
    before = customer_state()
    before.update(product_target=product, customer_target=customer,
                  focus={'product': product, 'customer': customer})
    s = committed(before, proposal({}), 'que otros productos nos compro en esos meses')
    assert s['excluded_product'] == product and s['customer_target'] == customer


def test_global_share_directly_after_customer_without_an_intermediate_global_total():
    before = customer_state()
    s = committed(before, proposal({'/period': SEPTEMBER}, action='DIRECT_UNAVAILABLE'),
                  '¿Qué porcentaje de las ventas de septiembre corresponde a productos terminados?')
    assert s['customer_target'] is None and s['period'] == SEPTEMBER
    assert s['analysis_categories'] == ['LAB_FINISHED_PRODUCT']


def test_denominator_denied_still_returns_authorized_amount_and_cached_response_revalidates():
    from modules.telchi.assistant.handler import TelchiHandler, BusinessPolicy, BusinessAuthorization
    from .test_assistant import MemoryStore, Interpreter, context, event, latest

    class Auth(BusinessAuthorization):
        revoked = False
        async def allowed(self, context, conn=None, required_permission=None):
            return required_permission is None or (required_permission == 'category' and not self.revoked)

    class Caps:
        def required_permissions(self, state):
            return ['category', 'denominator'] if state.get('analysis_categories') else [
                'category' if state['metric'] == 'sales.net_amount' else 'denominator']
        def availability(self, state):
            return SimpleNamespace(allowed=True)
        async def execute(self, state):
            assert state['metric'] == 'sales.net_amount', 'unauthorized denominator must not execute'
            return compatible()[0]['LAB_FINISHED_PRODUCT']['result']

    async def scenario():
        auth = Auth(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True))
        store = MemoryStore()
        p = proposal({'/period': SEPTEMBER}, intent='NEW_QUERY', action='DIRECT_UNAVAILABLE')
        handler = TelchiHandler(store=store, authorization=auth, interpreter=Interpreter([p]), capabilities=Caps())
        message = event('porcentaje de la venta total de septiembre de productos terminados')
        result = await handler.handle(message, context())
        assert 'Bs 25,00' in result.text and 'Porcentaje no calculado' in result.text
        assert latest(store)['capability_calls'] == 1
        auth.revoked = True
        replay = await handler.handle(message, context())
        assert replay.classification == 'DENIED' and '25,00' not in replay.text
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['owner', 'scope', 'authorization', 'oversized', None])
def test_explanation_repository_only_reuses_exact_authorized_scope(failure):
    from modules.telchi.assistant.repository import ConversationRepository
    from .test_assistant import context
    s = dict(period=SEPTEMBER, analysis_categories=['MEDICATIONS'])
    audit = dict(owner=['owner'], confirmed_state=deepcopy(s), business_rbac_verified=True,
                 category_analysis={'components': {}, 'denominator': compatible()[1]})
    if failure == 'owner':
        audit['owner'] = ['foreign']
    if failure == 'scope':
        audit['confirmed_state']['period'] = JULY
    if failure == 'authorization':
        audit['business_rbac_verified'] = False
    class Conn:
        async def execute(self, sql, params):
            assert "thread_id=%s AND channel_id=%s AND workspace_id=%s" in sql
            assert "payload_jsonb->>'environment'=%s" in sql
            assert params[0] == context().conversation_id
            assert params[3] == ['prior']
            return self
        async def fetchone(self):
            return dict(result_id='prior', audit=None if failure == 'oversized' else audit)
    async def scenario():
        result = await ConversationRepository().load_category_analysis(Conn(), context(),
            dict(history={'prior': s}, owner=['owner']), s)
        assert (result is not None) is (failure is None)
    asyncio.run(scenario())


def test_engine_rejects_mixed_global_scope_and_unknown_classification():
    for changes in [dict(customer_target='C000061'), dict(analysis_categories=['MADE_UP'])]:
        s = scoped_state(metric='sales.net_amount', requested_metrics=['sales.net_amount'], period=SEPTEMBER,
                         analysis_categories=['LAB_FINISHED_PRODUCT'])
        s.update(changes)
        with pytest.raises(ValueError):
            engine.validate(s)


@pytest.mark.parametrize('numerator,denominator,compatible_source,base,percentage', [
    (False, True, True, True, False),
    (True, False, True, False, False),
    (True, True, True, True, True),
    (False, False, True, False, False),
    (True, True, False, True, False),
])
def test_independent_denominator_matrix(numerator, denominator, compatible_source, base, percentage):
    from modules.telchi.assistant.commercial_continuity import denominator_accredited
    c, d = compatible()
    if not compatible_source:
        c['LAB_FINISHED_PRODUCT']['result']['source'] = {'publication_id': 'other'}
    if not numerator:
        c = {}
    if not denominator:
        d = None
    s = dict(period=SEPTEMBER, analysis_categories=['LAB_FINISHED_PRODUCT', 'MEDICATIONS'])
    values = shares(s, c, d)
    assert denominator_accredited(s, d) is base
    assert bool(values) is percentage
    text = format_category_analysis(s, c, d, values)
    assert ('Base: Bs 100,00' in text) is base
    assert ('falta acreditar un total global' in text) is not base
    assert 'Medicamentos: clasificación no acreditada' in text
    assert 'no los equiparo con productos terminados' in text


@pytest.mark.parametrize('change', [
    {'accreditation': 'unverified'}, {'exceptions': [{}]}, {'currency': 'USD'},
    {'total': {'amount': 'NaN'}}, {'total': {'amount': '0'}},
    {'reconciliation': {'difference': '1'}}, {'parameters': {}},
])
def test_unaccredited_denominator_never_presented_as_base(change):
    from modules.telchi.assistant.commercial_continuity import denominator_accredited
    _, d = compatible()
    d.update(change)
    assert not denominator_accredited({'period': SEPTEMBER}, d)


def test_medications_raw_label_and_explanations_preserve_analysis_scope():
    s = scoped_state(metric='sales.net_amount', requested_metrics=['sales.net_amount'], period=SEPTEMBER,
                     analysis_categories=['FRACTIONATED_PRODUCT'])
    p = proposal({'metric': None, 'entity_mention': {'text': 'medicamentos', 'type': None}}, action='ASK')
    s = committed(s, p, 'entonces cuanto es el porcentaje de medicamentos vendidos')
    assert s['analysis_categories'] == ['MEDICATIONS']
    for text in ['¿por qué no podés calcularlo?', '¿qué información sí tenemos?']:
        s = committed(s, proposal({}, intent='EXPLAIN', action='DIRECT_UNAVAILABLE'), text)
        assert s['analysis_categories'] == ['MEDICATIONS'] and s['period'] == SEPTEMBER


def test_handler_medications_audits_verified_base_without_a_numerator():
    from modules.telchi.assistant.handler import TelchiHandler, BusinessPolicy, BusinessAuthorization
    from .test_assistant import MemoryStore, Interpreter, context, event, latest
    class Auth(BusinessAuthorization):
        async def allowed(self, *args, **kwargs):
            return True
    class Caps:
        def required_permissions(self, state):
            return ['denominator']
        def availability(self, state):
            return SimpleNamespace(allowed=True)
        async def execute(self, state):
            assert state['metric'] == 'sales.commercial_line_amount_by'
            return compatible()[1]
    async def scenario():
        store = MemoryStore()
        auth = Auth(BusinessPolicy('telchi', 'workspace', 'fixture.business.read', True, True))
        handler = TelchiHandler(store=store, authorization=auth,
            interpreter=Interpreter([proposal({'period': SEPTEMBER})]), capabilities=Caps())
        result = await handler.handle(event('porcentaje de medicamentos vendidos'), context())
        a = latest(store)['category_analysis']
        assert a['percentages'] == {} and a['denominator_status'] == 'VERIFIED'
        assert 'Base: Bs 100,00' in result.text and 'falta acreditar un total global' not in result.text
    asyncio.run(scenario())

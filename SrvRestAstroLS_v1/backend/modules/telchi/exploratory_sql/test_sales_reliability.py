"""Commercial sufficiency regressions, not a business acceptance gate."""
from .test_executed_presentation import executor_factory, evidence  # noqa: F401
from modules.telchi.assistant.commercial_continuity import request_contract


def test_selected_prefix_is_never_delivered_as_exhaustive(evidence):
    registry, executed = evidence
    checks = executed()
    text = registry.render(checks[:2])
    assert '1 de 7 filas recuperadas' in text
    assert 'No es una enumeración exhaustiva' in text


def test_sql_limit_is_not_an_exhaustiveness_certificate(evidence):
    registry, executed = evidence
    checks = executed('SELECT slp_code, sum(line_total) AS amount FROM sales_operation '
                      'GROUP BY slp_code ORDER BY amount DESC LIMIT 3')
    text = registry.render(checks)
    assert '3 de 3 filas recuperadas' in text
    assert 'SQL con LIMIT' in text
    assert 'Líder observado por importe' in text


def test_undisclosed_rows_are_counted_as_executed_not_only_visible(evidence):
    registry, executed = evidence
    checks = executed()
    result_id = checks[0]['claim']['result_id']
    entry = registry.entries[result_id]
    registry.entries[result_id] = (*entry[:3], entry[3][:3], *entry[4:])
    text = registry.render(checks[:2])
    assert '1 de 7 filas recuperadas; 3 divulgadas al investigador' in text


def test_long_conditions_are_defined_once_and_all_rows_deliver(evidence):
    from .test_executed_presentation import deliver
    registry, executed = evidence
    sql = ('SELECT slp_code, count(CASE WHEN doc_date>=\'2026-09-01\' '
           'AND doc_date<\'2026-10-01\' THEN item_code ELSE NULL END) AS prior, '
           'count(CASE WHEN doc_date>=\'2026-10-01\' AND doc_date<\'2026-11-01\' '
           'THEN item_code ELSE NULL END) AS current FROM sales_operation '
           'GROUP BY slp_code ORDER BY slp_code')
    text = registry.render(executed(sql))
    assert text.count('CASE WHEN') == 2
    assert 'campo 1' in text and 'campo 2' in text
    assert not deliver(text).applied
    for n in range(1, 8):
        assert f'SLP0{n}' in deliver(text).text


def test_quantity_order_never_becomes_a_global_physical_winner():
    import json
    import duckdb
    from decimal import Decimal
    from types import SimpleNamespace
    from .ask_verifier import AskRegistry
    with duckdb.connect() as db:
        node = json.loads(db.execute("SELECT json_serialize_sql(?)", (
            'SELECT item_code,card_code,sum(quantity) AS total FROM sales_line '
            'GROUP BY item_code,card_code ORDER BY total DESC',)).fetchone()[0])['statements'][0]['node']
    manifest = SimpleNamespace(columns=[SimpleNamespace(alias=a) for a in ('item_code', 'card_code', 'total')])
    for second_sku in ('SKU_A', 'SKU_B'):
        rows = [('SKU_A', 'C1', Decimal('12')), (second_sku, 'C2', Decimal('8'))]
        class RenderOnly(AskRegistry):
            def _executed_cell(self, ref):
                return rows[0][2], (manifest, node, 'sales_line', 2, rows[0])
        registry = object.__new__(RenderOnly)
        registry.entries = {'r': (manifest, None, SimpleNamespace(returned_count=2), tuple(rows))}
        registry.context = SimpleNamespace(publication='fixture', snapshot='1')
        text = registry._render_executed([dict(match=True, claim=dict(
            kind='executed_cell', result_id='r', row_id='first', column_id='quantity'))])
        assert 'Líder observado por cantidad' not in text
        assert 'no líder físico global' in text or 'no hay un líder físico global' in text


def test_presentation_exclusion_survives_month_refinement():
    before = {'excluded_products': ['SKU_A', 'SKU_B'], 'excluded_product': None}
    proposal = dict(intent='REFINE', action='EXECUTE', clarification=None,
                    state_delta={'set': {'/period': {'start': '2026-09-01',
                                                    'end_exclusive': '2026-10-01'}}, 'unset': []})
    updated = request_contract(proposal, 'Y en septiembre, con la misma exclusión', before)
    assert '/excluded_products' not in updated['state_delta']['set']
    assert '/excluded_products' not in updated['state_delta']['unset']


def test_other_products_accepts_confirmed_sap_code_as_customer_identity():
    before = dict(customer_target='C000123', product_target=None,
                  focus={'customer': 'C000123', 'customer_label': 'EMPRESA',
                         'product': 'SKU_A', 'product_label': 'Producto A'})
    for mention in ('C000123', 'cuenta SAP C000123'):
        proposal = dict(intent='REFINE', action='EXECUTE', clarification=None,
                        state_delta={'set': {'/entity_mention': {'text': mention, 'type': None}},
                                     'unset': []})
        updated = request_contract(proposal, 'Qué otros productos compró ese cliente', before)
        assert updated['state_delta']['set']['/excluded_product'] == 'SKU_A'
        assert updated['state_delta']['set']['/customer_target'] == 'C000123'
    proposal['state_delta']['set']['/entity_mention']['text'] = 'OTRA EMPRESA'
    updated = request_contract(proposal, 'Qué otros productos compró OTRA EMPRESA', before)
    assert '/excluded_product' not in updated['state_delta']['set']


def test_research_receives_committed_exclusions_as_context_not_predicates():
    import asyncio
    import json
    from modules.telchi.assistant.tests.test_research_fallback import build, record
    from modules.telchi.assistant.tests.test_assistant import event, context

    async def run():
        researcher = record()
        handler = build([], researcher)
        state = dict(metric='sales.commercial_line_amount_by', customer_target='C1',
                     excluded_products=['SKU_A', 'SKU_B'], branches=[])
        await handler._research_fallback(event('Y en el último mes completo?'), context(),
                                         {'state': state}, {'timings': {}})
        question = researcher.calls[0][0]
        assert question.startswith('Y en el último mes completo?\n')
        inherited = json.loads(question.split(': ', 1)[1])
        assert inherited['excluded_products'] == ['SKU_A', 'SKU_B']
        assert inherited['customer_target'] == 'C1'
        assert 'WHERE' not in question

    asyncio.run(run())


def test_channel_page_accounts_for_actual_delivered_rows():
    import json
    import duckdb
    from decimal import Decimal
    from types import SimpleNamespace
    from .ask_verifier import AskRegistry
    with duckdb.connect(config={'threads': '1'}) as db:
        node = json.loads(db.execute('SELECT json_serialize_sql(?)', (
            'SELECT product_name,sum(line_total) AS amount FROM sales_line GROUP BY product_name ORDER BY amount DESC',
        )).fetchone()[0])['statements'][0]['node']
    manifest = SimpleNamespace(columns=[SimpleNamespace(alias=a) for a in ('product_name', 'amount')],
                               row_ids=tuple(str(i) for i in range(30)))
    rows = [(f'PRODUCT-{i:03d}-' + 'x'*80, Decimal(i)) for i in range(30)]
    class RenderOnly(AskRegistry):
        def _executed_cell(self, ref):
            row = rows[int(ref['row_id'])]
            return row[1], (manifest, node, 'sales_line', 1, row)
    registry = object.__new__(RenderOnly)
    registry.entries = {'r': (manifest, None, SimpleNamespace(returned_count=30), tuple(rows))}
    registry.context = SimpleNamespace(publication='fixture', snapshot='1')
    text = registry._render_executed([dict(match=True, claim=dict(kind='executed_cell',
        result_id='r', row_id=str(i), column_id='amount')) for i in range(30)])
    assert len(text) < 4096
    assert 'pendientes de presentación' in text
    assert 'Podés pedir los siguientes' in text
    import re
    shown = int(re.search(r'Página: (\d+) de 30', text)[1])
    assert len(re.findall(r'^\d+\. product_name=', text, re.M)) == shown
    assert registry.presentation_pages == {'r': list(range(1, shown + 1))}


def test_business_feedback_rejects_zero_sum_as_absence_and_all_sku_intersection():
    import json
    import duckdb
    from .ask_verifier import AskRegistry
    with duckdb.connect(config={'threads': '1'}) as db:
        def registry(sql, question):
            node = json.loads(db.execute('SELECT json_serialize_sql(?)', (sql,)).fetchone()[0])['statements'][0]['node']
            result = object.__new__(AskRegistry)
            result.question = question
            result.entries = {'r': (None, None, None, None, node, 'sales_line')}
            return result
        prefix = 'SELECT card_code,sum(line_total) AS amount FROM sales_line GROUP BY card_code '
        result = registry(prefix + 'HAVING sum(line_total)=0', 'Clientes que compraron en enero pero no en febrero')
        assert 'documentary absence' in result.final_feedback([])
        result = registry(prefix + 'HAVING count(doc_entry)=0', 'Clientes que compraron en enero pero no en febrero')
        assert result.final_feedback([]) is None
        result = registry(prefix + 'HAVING sum(line_total)=0', 'Clientes con importe cero')
        assert result.final_feedback([]) is None  # A monetary-zero request is legitimate.
        result = registry(prefix + 'HAVING count(DISTINCT item_code)=4', 'Clientes del producto en todas sus presentaciones')
        assert 'expands the SKU universe' in result.final_feedback([])
        result.question = 'Clientes que compraron cada una de todas sus presentaciones'
        assert result.final_feedback([]) is None
        result = registry(prefix + "HAVING count(CASE WHEN item_code='A' THEN doc_entry ELSE NULL END)>0 "
                          "AND count(CASE WHEN item_code='B' THEN doc_entry ELSE NULL END)>0",
                          'Clientes del producto en todas sus presentaciones')
        assert 'expands the SKU universe' in result.final_feedback([])


def test_new_independent_question_clears_presentation_exclusion():
    before = {'excluded_products': ['SKU_A', 'SKU_B']}
    proposal = dict(intent='NEW_QUERY', action='EXECUTE', clarification=None,
                    state_delta={'set': {}, 'unset': []})
    updated = request_contract(proposal, 'Facturación global de octubre', before)
    assert updated['state_delta']['set']['/excluded_products'] is None

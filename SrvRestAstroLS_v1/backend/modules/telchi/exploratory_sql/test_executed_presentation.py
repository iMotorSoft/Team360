"""Delivery presentation of executed cells in the WhatsApp channel.

The 08/11/2026 free-analysis turn verified 7 customers but the channel guard
delivered only 3, because every cell repeated the same full SQL scope. These
contracts keep the whole population deliverable without raising the Meta limit,
dropping a figure or paraphrasing a condition.
"""
from contextlib import contextmanager
from types import SimpleNamespace

import duckdb
import pytest

from . import authorized_foundation as af
from . import foundation as f
from . import foundation_dev
from .ask_sources import AskExecutor, context_for_run
from .ask_verifier import AskRegistry
from .foundation_dev import proposal
from .validator import validate

META_TEXT_LIMIT = 4096
SELLERS = ('SLP01', 'SLP02', 'SLP03', 'SLP04', 'SLP05', 'SLP06', 'SLP07')


@pytest.fixture
def executor_factory(tmp_path, monkeypatch):
    """Seven sellers in October; two of them also bought in September."""
    path = tmp_path / 'fixture.duckdb'
    with duckdb.connect(str(path)) as db:
        db.execute('CREATE TABLE docs(source_system VARCHAR, source_table VARCHAR, canceled VARCHAR,'
                   ' doc_entry VARCHAR, doc_num VARCHAR, doc_date VARCHAR, currency VARCHAR,'
                   ' slp_code VARCHAR, series VARCHAR, sales_channel_code VARCHAR,'
                   ' sales_channel_semantic_status VARCHAR, raw_extraction_id VARCHAR,'
                   ' source_as_of VARCHAR)')
        db.execute('CREATE TABLE lines(source_system VARCHAR, source_table VARCHAR, doc_entry VARCHAR,'
                   ' line_num VARCHAR, item_code VARCHAR, currency VARCHAR, line_total VARCHAR,'
                   ' raw_extraction_id VARCHAR, source_as_of VARCHAR)')
        documents, lines = [], []
        for index, seller in enumerate(SELLERS):
            entry = str(index + 1)
            documents.append(f"('SAP_B1_HANA','OINV','N','{entry}','{entry}','2026-10-05','BS',"
                             f"'{seller}','9',NULL,'UNKNOWN','r1','2026-10-06')")
            lines.append(f"('SAP_B1_HANA','INV1','{entry}','0','L01010','BS',"
                         f"'{100 * (index + 1)}.50','r1','2026-10-06')")
        for index, seller in enumerate(SELLERS[:2]):
            entry = str(100 + index)
            documents.append(f"('SAP_B1_HANA','OINV','N','{entry}','{entry}','2026-09-05','BS',"
                             f"'{seller}','9',NULL,'UNKNOWN','r1','2026-09-06')")
            lines.append(f"('SAP_B1_HANA','INV1','{entry}','0','L01010','BS',"
                         "'10.00','r1','2026-09-06')")
        db.execute('INSERT INTO docs VALUES ' + ','.join(documents))
        db.execute('INSERT INTO lines VALUES ' + ','.join(lines))
    with duckdb.connect(str(path)) as db:
        db.execute("ALTER TABLE lines ADD COLUMN whs_code VARCHAR DEFAULT 'W'")
        db.execute("ALTER TABLE docs ADD COLUMN user_sign VARCHAR DEFAULT '1'")
        for dataset, sql in (
            ('products', "SELECT 'SAP_HANA' AS source_system,'L01010' AS item_code,'Soda' AS sap_item_name,"
                         "NULL::VARCHAR AS product_name,NULL::VARCHAR AS canonical_name,"
                         "'unit' AS inventory_uom_id"),
            ('salespersons', "SELECT 'SAP_HANA' AS source_system,'SLP01' AS source_native_id,"
                             "'Test' AS name,'X' AS salesperson_category_code,"
                             "'Example' AS salesperson_category_name")):
            target = tmp_path / (dataset + '.parquet')
            db.execute(f"COPY ({sql}) TO '{target}' (FORMAT PARQUET)")

    @contextmanager
    def session(*, read_only):
        assert read_only is True
        with duckdb.connect() as db:
            db.execute(f"ATTACH '{path}' AS telchi (READ_ONLY)")
            yield db

    access = SimpleNamespace(foundation_publication_id=f.PUBLICATION,
                             ducklake_snapshot_id=int(f.SNAPSHOT),
                             sales=lambda table: 'telchi.main.' + (
                                 'docs' if table == 'sales_document' else 'lines'),
                             reference=lambda name: tmp_path / (name + '.parquet'))
    reader = SimpleNamespace(connector=SimpleNamespace(session=session),
                             resolve_on=lambda db: access, access=access)
    monkeypatch.setattr(foundation_dev, 'host_read_preflight', lambda: dict(safe=True))

    class FixtureExecutor(AskExecutor):
        def __init__(self, context, *, authorized):
            super().__init__(context, authorized=authorized)
            self.reader = reader

    return FixtureExecutor


TWO_PERIODS = """SELECT slp_code,
 sum(CASE WHEN doc_date>='2026-10-01' THEN line_total ELSE 0 END) AS october_sales,
 sum(CASE WHEN doc_date<'2026-10-01' THEN line_total ELSE 0 END) AS september_sales
FROM sales_operation WHERE doc_date>='2026-09-01' AND doc_date<'2026-11-01'
GROUP BY slp_code ORDER BY slp_code"""

SEPTEMBER_ONLY = """SELECT slp_code, sum(line_total) AS september_sales
FROM sales_operation WHERE doc_date>='2026-09-01' AND doc_date<'2026-10-01'
GROUP BY slp_code ORDER BY slp_code"""


@pytest.fixture
def evidence(monkeypatch, executor_factory):
    """Real register/verify path, forced through the authorized execution branch."""
    ctx = context_for_run()
    monkeypatch.setattr(af, 'binding_for', lambda context: lambda: object())
    monkeypatch.setattr(af, 'authorize_issued', lambda context: None)
    registry = AskRegistry(ctx, executor_factory=executor_factory)

    def executed(sql=TWO_PERIODS):
        p = proposal(sql, 'sales_operation')
        _, query = validate(p, ctx)
        assert query is not None
        with executor_factory(ctx, authorized=True) as executor:
            decision, result = executor.execute(p, ctx)
        assert result.status == 'COMPLETED', (decision, result)
        manifest = registry.register(query, result, result.rows)
        assert manifest is not None
        checks = [registry.verify(dict(kind='executed_cell', result_id=manifest['result_id'],
                                      column_id=column['column_id'], row_id=row_id))
                  for row_id in manifest['row_ids'] for column in manifest['columns']
                  if column['alias'] not in manifest['group_expressions']]
        assert all(check['match'] for check in checks), [c['reason'] for c in checks]
        return checks

    try:
        yield registry, executed
    finally:
        registry.close()


def deliver(text):
    """Exactly the real channel composition: controls plus the Meta guard."""
    from modules.messaging.delivery_guard import guard_outbound
    from modules.telchi.assistant.conversation_controls import with_options
    return guard_outbound(with_options(text), limit=META_TEXT_LIMIT)


def test_delivered_list_keeps_every_row_and_one_scope(evidence):
    registry, executed = evidence
    checks = executed()
    assert len(checks) == 14
    text = registry.render(checks)
    rows = [line for line in text.split('\n') if line[:1].isdigit() and ' · ' in line]
    assert [line.split(' · ')[0] for line in rows] == [
        f'{position}. slp_code={seller}' for position, seller in enumerate(SELLERS, 1)]
    # One shared scope instead of one full filter per cell.
    assert text.count('Alcance consultado (aplica a todas las cifras):') == 1
    assert 'COMPARE_EQUAL' not in text and 'doc_date ≥ 2026-09-01' in text
    for amount in ('100,50', '200,50', '300,50', '400,50', '500,50', '600,50', '700,50', '10,00'):
        assert amount in text, amount
    delivered = deliver(text)
    assert delivered.applied is False and delivered.omitted_lines == 0
    assert len(delivered.text) <= META_TEXT_LIMIT
    assert delivered.full_text == delivered.text


def test_distinct_scopes_are_referenced_never_repeated(evidence):
    registry, executed = evidence
    text = registry.render(executed() + executed(SEPTEMBER_ONLY))
    assert 'Alcance consultado: 1) ' in text and '2) ' in text
    assert '[alcance 1]' in text and '[alcance 2]' in text
    assert text.count('doc_date ≥ 2026-09-01') == 2
    assert len(deliver(text).text) <= META_TEXT_LIMIT


def test_conditional_coverage_dates_keep_original_column(evidence):
    registry, executed = evidence
    sql = ("SELECT min(CASE WHEN doc_date>='2026-10-01' THEN doc_date ELSE NULL END) AS first_date, "
           "max(CASE WHEN doc_date>='2026-10-01' THEN doc_date ELSE NULL END) AS last_date "
           "FROM sales_operation")
    text = registry.render(executed(sql))
    assert '2026-10-05' in text
    assert 'CASE WHEN' in text


def test_conditional_counts_and_having_remain_visible(evidence):
    registry, executed = evidence
    sql = ("SELECT slp_code, count(CASE WHEN doc_date<'2026-10-01' THEN item_code ELSE NULL END) AS september, "
           "count(CASE WHEN doc_date>='2026-10-01' THEN item_code ELSE NULL END) AS october "
           "FROM sales_operation GROUP BY slp_code "
           "HAVING count(CASE WHEN doc_date<'2026-10-01' THEN item_code ELSE NULL END)=0 ORDER BY slp_code")
    checks = executed(sql)
    text = registry.render(checks)
    assert 'SLP03' in text and 'SLP01' not in text
    assert 'condición sobre grupos:' in text
    assert 'ELSE null END) = 0' in text


def test_rank_summary_is_from_primary_order_and_first_issued_row(evidence):
    registry, executed = evidence
    sql = ('SELECT slp_code, sum(line_total) AS amount FROM sales_operation '
           'GROUP BY slp_code ORDER BY amount DESC LIMIT 3')
    text = registry.render(executed(sql))
    assert 'Líder observado por importe comercial de líneas (antes de notas de crédito): slp_code=SLP07' in text
    assert 'importe, no de cantidad' in text
    # A selected nonleading row or ascending ordering cannot become a leader.
    assert 'Líder observado' not in registry.render(executed(sql)[1:])
    assert 'Líder observado' not in registry.render(executed(sql.replace('DESC', 'ASC')))


def test_nested_calculation_renders_issued_dependencies(evidence):
    registry, executed = evidence
    a, b = [c['claim'] for c in executed()[:2]]
    net = dict(kind='calculation', operation='subtract', dependencies=[a, b])
    comparison = dict(kind='calculation', operation='subtract', dependencies=[net, net])
    check = registry.verify(comparison)
    assert check['match'], check
    text = registry.render([check])
    assert 'Diferencia = 0,00' in text
    assert '100,50' in text and '10,00' in text


def test_percent_change_rejects_delta_as_new_value(evidence):
    registry, executed = evidence
    a, b = [c['claim'] for c in executed()[:2]]
    delta = dict(kind='calculation', operation='subtract', dependencies=[a, b])
    wrong = dict(kind='calculation', operation='percent_change', dependencies=[delta, b])
    check = registry.verify(wrong)
    assert not check['match']
    assert check['reason'] == 'percent_change_requires_comparable_measures_not_delta_and_base'
    correct = dict(kind='calculation', operation='percent_change', dependencies=[a, b])
    check = registry.verify(correct)
    assert check['match'] and check['value'] == '905.00'


def test_nested_unknown_reference_remains_closed(evidence):
    registry, executed = evidence
    a = executed()[0]['claim']
    missing = dict(a, result_id='nonexistent')
    claim = dict(kind='calculation', operation='subtract', dependencies=[a, missing])
    check = registry.verify(claim)
    assert not check['match'] and check['reason'] == 'unknown_result_id'
    assert '100,50' not in registry.render([check])


def test_labels_keep_conditions_and_use_operators():
    from .ask_verifier import compact_expression_label, predicate_label
    column = lambda name: {'class': 'COLUMN_REF',
        'column_names': ['sales_operation', name]}
    constant = lambda value: {'class': 'CONSTANT',
        'value': {'is_null': False, 'value': value}}
    comparison = {'class': 'COMPARISON', 'type': 'COMPARE_GREATERTHANOREQUALTO',
                  'left': column('doc_date'), 'right': constant('2026-09-01')}
    assert predicate_label(comparison) == 'doc_date ≥ 2026-09-01'
    assert predicate_label({'class': 'CONJUNCTION', 'type': 'CONJUNCTION_OR',
        'children': [comparison, comparison]}) == '(doc_date ≥ 2026-09-01 o doc_date ≥ 2026-09-01)'
    case = {'class': 'CASE', 'else_expr': constant(0), 'case_checks': [
        {'when_expr': comparison, 'then_expr': column('line_total')}]}
    # Qualified field and quoted literal are kept verbatim: the label is lineage.
    assert compact_expression_label(case) == (
        'CASE WHEN sales_operation.doc_date ≥ "2026-09-01" THEN '
        'sales_operation.line_total ELSE 0 END')
    assert predicate_label(None) == 'universo publicado accesible'
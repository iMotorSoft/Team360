"""Bounded list coverage: the recovered population, not the first page.

The 09/11/2026 closure left L01 with 311 authorized accounts, 100 executed rows
and 211 unrecovered because a page-sized prefix (SQL LIMIT 100) was accepted as
the list. These contracts keep the existing row/query budgets untouched and use
the existing keyset pagination plus the durable result to recover every record
once, in order, with an honest incomplete outcome when the page budget ends.
"""
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import duckdb
import pytest

from . import authorized_foundation as af
from . import foundation as f
from . import foundation_dev
from .ask_sources import AskExecutor, context_for_run
from .ask_verifier import AskRegistry
from .contracts import Budget
from .foundation_dev import proposal
from .validator import validate

ITEMS = 250
LARGE_ITEMS = 720


def codes(total):
    return [f'I{index:05d}' for index in range(1, total + 1)]


def context():
    """The real DEV ceilings: 100 rows and 5 queries per executor."""
    return replace(context_for_run(), effective_budget=Budget())


def build(tmp_path, monkeypatch, total):
    """One October line per item code; the population exceeds one 100-row page."""
    items = codes(total)
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
        for position, item in enumerate(items, 1):
            entry = str(position)
            documents.append(f"('SAP_B1_HANA','OINV','N','{entry}','{entry}','2026-10-05','BS',"
                             "'SLP01','9',NULL,'UNKNOWN','r1','2026-10-06')")
            lines.append(f"('SAP_B1_HANA','INV1','{entry}','0','{item}','BS','10.00','r1','2026-10-06')")
        db.execute('INSERT INTO docs VALUES ' + ','.join(documents))
        db.execute('INSERT INTO lines VALUES ' + ','.join(lines))
        db.execute("ALTER TABLE lines ADD COLUMN whs_code VARCHAR DEFAULT 'W'")
        db.execute("ALTER TABLE docs ADD COLUMN user_sign VARCHAR DEFAULT '1'")
        products = ','.join(f"('SAP_HANA','{item}','Producto {item}',NULL::VARCHAR,NULL::VARCHAR,'unit')"
                            for item in items)
        for dataset, sql in (
            ('products', 'SELECT * FROM (VALUES ' + products + ') AS t(source_system,item_code,'
                         'sap_item_name,product_name,canonical_name,inventory_uom_id)'),
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
        def __init__(self, ctx, *, authorized):
            super().__init__(ctx, authorized=authorized)
            self.reader = reader

    return FixtureExecutor


def recovered_registry(monkeypatch, factory):
    ctx = context()
    monkeypatch.setattr(af, 'binding_for', lambda value: lambda: object())
    monkeypatch.setattr(af, 'authorize_issued', lambda value: None)
    instance = AskRegistry(ctx, executor_factory=factory)

    def executed(sql):
        p = proposal(sql, 'sales_operation')
        _, query = validate(p, ctx)
        assert query is not None
        with factory(ctx, authorized=True) as executor:
            decision, result = executor.execute(p, ctx)
        assert result.status == 'COMPLETED', (decision, result)
        manifest = instance.register(query, result, result.rows[:30])
        assert manifest is not None
        return manifest, instance, result

    return instance, executed


@pytest.fixture
def registry(tmp_path, monkeypatch):
    instance, executed = recovered_registry(monkeypatch, build(tmp_path, monkeypatch, ITEMS))
    try:
        yield executed
    finally:
        instance.close()


@pytest.fixture
def large_registry(tmp_path, monkeypatch):
    instance, executed = recovered_registry(monkeypatch, build(tmp_path, monkeypatch, LARGE_ITEMS))
    try:
        yield executed
    finally:
        instance.close()


def page_sql(limit=100):
    return ('SELECT item_code, count(*) AS lines FROM sales_operation '
            "WHERE doc_date>='2026-10-01' AND doc_date<'2026-11-01' "
            f'GROUP BY item_code ORDER BY item_code LIMIT {limit}')


def test_page_sized_prefix_is_recovered_as_the_whole_ordered_population(registry):
    manifest, instance, result = registry(page_sql())
    assert result.returned_count == 100 and result.truncated is False
    recovery = manifest['population_recovery']
    assert recovery['complete'] is True and recovery['recovered_records'] == ITEMS
    assert recovery['first_page_records'] == 100 and recovery['pages'] == 2
    assert recovery['entity_column'] == 'item_code' and recovery['distinct_entities'] == ITEMS
    pages = instance.population_pages[manifest['result_id']]
    assert [page['page'] for page in pages] == [1, 2]
    recovered = [tuple(row) for row in result.rows] + [
        tuple(row) for page in pages for row in page['rows']]
    assert [row[0] for row in recovered] == codes(ITEMS)
    assert len(set(row[0] for row in recovered)) == ITEMS
    # Every continuation is one ordinary authorized execution of the same scope.
    assert [entry['decision']['decision'] for entry in instance.audit] == ['ALLOW', 'ALLOW']
    assert instance.audit[0]['keyset']['column'] == 'item_code'
    assert instance.audit[0]['keyset']['inclusive_lower_bound'] == "'I00100'"


def test_declared_limit_smaller_than_the_population_is_still_completed(registry):
    manifest, instance, _ = registry(page_sql(limit=10))
    recovery = manifest['population_recovery']
    assert recovery['complete'] is True and recovery['recovered_records'] == ITEMS
    assert recovery['first_page_records'] == 10 and recovery['pages'] >= 2
    recovered = [row[0] for page in instance.population_pages[manifest['result_id']]
                 for row in page['rows']]
    assert recovered == codes(ITEMS)[10:]


def test_recovered_population_is_delivered_as_complete_and_progressive(registry):
    manifest, instance, _ = registry(page_sql())
    checks = [instance.verify(dict(kind='executed_cell', result_id=manifest['result_id'],
                                   column_id=column['column_id'], row_id=row_id))
              for row_id in manifest['row_ids'][:10] for column in manifest['columns']]
    assert all(check['match'] for check in checks), [c['reason'] for c in checks]
    text = instance.render(checks)
    assert 'Universo recuperado completo: 250 registros (250 códigos de producto distintos)' in text
    assert '10 seleccionados en esta respuesta y 240 pendientes' in text
    assert 'No es una enumeración exhaustiva' not in text


def test_single_page_list_is_verified_without_a_durable_page(registry):
    manifest, instance, result = registry(
        'SELECT item_code, count(*) AS lines FROM sales_operation '
        "WHERE doc_date>='2026-10-01' AND item_code<'I00007' "
        'GROUP BY item_code ORDER BY item_code LIMIT 100')
    assert result.returned_count == 6
    # A declared LIMIT cannot certify the population, so one bounded keyset page
    # confirms there is no tail; it adds no durable records and no new limits.
    recovery = manifest['population_recovery']
    assert recovery['complete'] is True and recovery['recovered_records'] == 6
    assert recovery['pages'] == 0 and instance.population_pages[manifest['result_id']] == []
    assert len(instance.audit) == 1
    checks = [instance.verify(dict(kind='executed_cell', result_id=manifest['result_id'],
                                  column_id=column['column_id'], row_id=manifest['row_ids'][0]))
              for column in manifest['columns']]
    assert all(check['match'] for check in checks), [c['reason'] for c in checks]
    text = instance.render(checks)
    assert 'Universo recuperado completo: 6 registros' in text
    assert 'No es una enumeración exhaustiva' not in text


def test_ranking_order_is_never_recovered_as_a_population(registry):
    ranking, instance, _ = registry(
        'SELECT item_code, sum(line_total) AS amount FROM sales_operation '
        'GROUP BY item_code ORDER BY amount DESC LIMIT 10')
    assert 'population_recovery' not in ranking and instance.audit == []


def test_page_budget_exhaustion_stays_incomplete_and_not_durable(large_registry):
    manifest, instance, _ = large_registry(page_sql(limit=10))
    recovery = manifest['population_recovery']
    assert recovery['complete'] is False and recovery['reason'] == 'page_budget_reached'
    assert recovery['pages'] == 5 and recovery['recovered_records'] < LARGE_ITEMS
    assert manifest['result_id'] not in instance.population_pages
    checks = [instance.verify(dict(kind='executed_cell', result_id=manifest['result_id'],
                                   column_id=column['column_id'], row_id=row_id))
              for row_id in manifest['row_ids'][:3] for column in manifest['columns']]
    text = instance.render(checks)
    assert 'No es una enumeración exhaustiva' in text
    assert 'Universo recuperado completo' not in text
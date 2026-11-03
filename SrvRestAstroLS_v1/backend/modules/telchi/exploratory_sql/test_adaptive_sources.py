"""Real DuckDB fixture exercises projections and SAP namespace differences."""
from types import SimpleNamespace

import duckdb

from .adaptive_sources import AdaptiveExecutor, context_for_run
from .foundation import FoundationReadonlyExecutor
from .test_adaptive_research import fixture_results
from .foundation_dev import proposal
from .validator import validate


def test_repeated_case_group_literals_preserve_parameter_identity():
    sql = ("SELECT CASE WHEN sales_channel_code IS NULL THEN 'MISSING' ELSE 'CLASSIFIED' END AS bucket,"
           "count(*) AS n FROM sales_operation GROUP BY "
           "CASE WHEN sales_channel_code IS NULL THEN 'MISSING' ELSE 'CLASSIFIED' END")
    _, q = validate(proposal(sql, 'sales_operation'), context_for_run())
    assert q is not None
    assert len(q.parameters) == 2
    assert 'MISSING' not in q.generated_sql and 'CLASSIFIED' not in q.generated_sql
    with duckdb.connect(config={'threads': 1}) as db:
        db.execute('CREATE TABLE sales_operation(sales_channel_code VARCHAR)')
        db.execute("INSERT INTO sales_operation VALUES (NULL),('HORIZONTAL')")
        expected = db.execute(sql).fetchall()
        actual = db.execute(q.generated_sql, {p.name: p.value for p in q.parameters}).fetchall()
        assert sorted(actual) == sorted(expected)


def test_reference_native_key_namespace_and_no_projection_fanout(tmp_path, monkeypatch):
    ctx, results = fixture_results()
    with duckdb.connect(config={'threads': 1}) as db:
        for table, result in zip([t for t in ctx.catalog.tables if t.name != 'sales_operation'], results):
            if table.name in {'document_metadata', 'line_metadata', 'salesperson'}:
                continue
            columns = ','.join(c.name+' '+c.sql_type for c in table.columns)
            db.execute(f'CREATE TABLE {table.name} ({columns})')
            db.executemany(f'INSERT INTO {table.name} VALUES ('+','.join('?' for _ in table.columns)+')', result.rows)
        db.execute("CREATE TABLE raw_doc AS SELECT *, 'SAP_B1_HANA' AS source_system,'OINV' AS source_table,'5' AS user_sign FROM sales_document")
        db.execute("CREATE TABLE raw_line AS SELECT *, 'SAP_B1_HANA' AS source_system,'INV1' AS source_table,'W' AS whs_code FROM sales_line")
        # code deliberately differs: it is not the SAP native key.
        db.execute("CREATE TABLE seller_ref AS SELECT 'SAP_HANA' AS source_system,'7' AS source_native_id,'NOT_NATIVE' AS code,'Fiction' AS name,'2' AS salesperson_category_code,'CORPORATIVO' AS salesperson_category_name")
        path = tmp_path/'reference.parquet'
        db.execute('COPY seller_ref TO ? (FORMAT PARQUET)', [str(path)])
        access = SimpleNamespace(foundation_publication_id=ctx.publication, ducklake_snapshot_id=ctx.snapshot,
            sales=lambda name: {'sales_document': 'raw_doc', 'sales_line': 'raw_line'}[name], reference=lambda _: path)
        executor = object.__new__(AdaptiveExecutor)
        executor.reader = SimpleNamespace(resolve_on=lambda _: access)
        monkeypatch.setattr(FoundationReadonlyExecutor, '_prepare_connection', lambda *args: None)
        executor._prepare_connection(db, ctx)
        assert db.execute('SELECT slp_code,name FROM salesperson').fetchall() == [('7', 'Fiction')]
        assert db.execute('SELECT count(*),sum(line_total),count(DISTINCT doc_entry) FROM sales_operation').fetchone() == (2, __import__('decimal').Decimal('0.30'), 1)
        assert db.execute('SELECT DISTINCT user_sign,whs_code FROM sales_operation').fetchall() == [('5', 'W')]

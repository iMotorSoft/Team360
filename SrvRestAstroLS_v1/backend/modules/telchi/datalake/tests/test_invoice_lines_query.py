"""Exercise actual parameterized SQL against a small local DuckDB fixture."""
from contextlib import contextmanager
from types import SimpleNamespace
import duckdb
import pytest
from modules.telchi.datalake import invoice_lines_query as query


@pytest.fixture
def foundation(monkeypatch, tmp_path):
    con = duckdb.connect()
    con.execute('CREATE TABLE docs(source_system VARCHAR,source_table VARCHAR,doc_entry VARCHAR,doc_num VARCHAR,doc_date VARCHAR,canceled VARCHAR,raw_extraction_id VARCHAR,source_as_of VARCHAR)')
    con.execute("INSERT INTO docs VALUES ('SAP_B1_HANA','OINV','11532517','260192728','2026-09-24','N','extraction','2026-09-24')")
    con.execute('CREATE TABLE lines(source_system VARCHAR,source_table VARCHAR,doc_entry VARCHAR,line_num VARCHAR,item_code VARCHAR,quantity VARCHAR,source_as_of VARCHAR,raw_extraction_id VARCHAR)')
    con.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','11532517','1','B','2','2026-09-24','extraction'),('SAP_B1_HANA','INV1','11532517','0','A','10','2026-09-24','extraction')")
    path = tmp_path / 'products.parquet'
    con.execute('CREATE TABLE products(source_system VARCHAR,item_code VARCHAR,sap_item_name VARCHAR,product_name VARCHAR,canonical_name VARCHAR)')
    con.execute("INSERT INTO products VALUES ('SAP_HANA','A','Producto A',NULL,NULL),('SAP_HANA','B',NULL,NULL,NULL)")
    con.execute('COPY products TO ? (FORMAT PARQUET)', [str(path)])
    class Connection:
        def execute(self, sql, params=None):
            if 'SELECT readonly' in sql:
                return SimpleNamespace(fetchone=lambda: (True,))
            return con.execute(sql, params or [])
    @contextmanager
    def session(*, read_only):
        assert read_only is True
        yield Connection()
    access = SimpleNamespace(foundation_publication_id=query.PUBLICATION, ducklake_snapshot_id=query.SNAPSHOT,
        foundation_data_as_of='2026-09-28', sales=lambda t: 'docs' if t == 'sales_document' else 'lines', reference=lambda t: path)
    monkeypatch.setattr('modules.telchi.datalake.foundation_reader.FoundationReader.resolve_on', lambda self, conn: access)
    opts = dict(source_system='SAP_B1_HANA', document_type='OINV', doc_entry='11532517', doc_num='260192728',
                doc_date='2026-09-24', publication_id=query.PUBLICATION, snapshot_id=query.SNAPSHOT)
    yield con, SimpleNamespace(session=session), opts, access
    con.close()


def test_exact_document_order_and_collisions_excluded(foundation):
    con, connector, opts, _ = foundation
    con.execute("INSERT INTO docs VALUES ('OTHER','OINV','11532517','different','2026-09-24','N','other','other'),('SAP_B1_HANA','ORIN','11532517','credit','2026-09-24','N','other','other')")
    con.execute("INSERT INTO lines VALUES ('OTHER','INV1','11532517','0','evil','999','other','other'),('SAP_B1_HANA','RIN1','11532517','0','credit','99','other','other')")
    result = query.execute_query(opts, connector)
    assert [r['item_code'] for r in result['rows']] == ['A', 'B']
    assert result['rows'][1]['description'] is None
    assert all(r['unit'] is None for r in result['rows'])
    assert all('line_total' not in r for r in result['rows'])


@pytest.mark.parametrize('case', ['missing', 'canceled', 'duplicate_document', 'duplicate_line', 'lineage', 'publication'])
def test_invalid_document_lineage_fails_closed(foundation, case):
    con, connector, opts, access = foundation
    if case == 'missing': con.execute('DELETE FROM docs')
    if case == 'canceled': con.execute("UPDATE docs SET canceled='Y'")
    if case == 'duplicate_document': con.execute('INSERT INTO docs SELECT * FROM docs')
    if case == 'duplicate_line': con.execute('INSERT INTO lines SELECT * FROM lines LIMIT 1')
    if case == 'lineage': con.execute("UPDATE lines SET raw_extraction_id='other'")
    if case == 'publication': access.ducklake_snapshot_id += 1
    with pytest.raises((query.TelchiQueryError, ValueError)):
        query.execute_query(opts, connector)


def test_no_lines_is_explicit_empty_not_other_document(foundation):
    con, connector, opts, _ = foundation
    con.execute('DELETE FROM lines')
    assert query.execute_query(opts, connector)['rows'] == []

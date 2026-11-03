"""Actual bounded SQL on local DuckDB fixtures; live evidence is separate."""
import pytest
from modules.telchi.datalake import invoice_amount_query as query
from .test_invoice_lines_query import foundation


def prepare(foundation):
    con, connector, options, access = foundation
    con.execute('ALTER TABLE docs ADD COLUMN doc_total VARCHAR')
    con.execute('ALTER TABLE docs ADD COLUMN currency VARCHAR')
    con.execute("UPDATE docs SET doc_total='25.00',currency='BS'")
    return con, connector, options, access


def test_header_total_not_sum_of_lines(foundation):
    con, connector, options, _ = prepare(foundation)
    con.execute("INSERT INTO docs VALUES ('OTHER','OINV','11532517','other','2026-09-24','N','extraction','2026-09-24','9999','USD')")
    con.execute('DELETE FROM lines')
    result = query.execute_query(options, connector)
    assert result['rows'] == [dict(amount='25.00', currency='BS')]
    assert result['amount_source'] == 'OINV.DocTotal'
    assert result['read_only'] is True and result['sap_accessed'] is False


@pytest.mark.parametrize('change', ["doc_total=NULL", "currency=NULL", "doc_total='NaN'", "canceled='Y'", "raw_extraction_id=NULL"])
def test_invalid_header(foundation, change):
    con, connector, options, _ = prepare(foundation)
    con.execute('UPDATE docs SET ' + change)
    with pytest.raises((query.TelchiQueryError, ValueError)):
        query.execute_query(options, connector)


def test_duplicate_or_changed_publication(foundation):
    con, connector, options, access = prepare(foundation)
    access.ducklake_snapshot_id += 1
    with pytest.raises(query.TelchiQueryError):
        query.execute_query(options, connector)
    access.ducklake_snapshot_id -= 1
    con.execute('INSERT INTO docs SELECT * FROM docs')
    with pytest.raises(query.TelchiQueryError):
        query.execute_query(options, connector)


def test_foreign_type_cannot_replace_invoice(foundation):
    con, connector, options, _ = prepare(foundation)
    con.execute("UPDATE docs SET source_table='ORIN'")
    with pytest.raises(query.TelchiQueryError):
        query.execute_query(options, connector)


def test_native_currency_not_converted(foundation):
    con, connector, options, _ = prepare(foundation)
    con.execute("UPDATE docs SET currency='USD'")
    assert query.execute_query(options, connector)['rows'][0]['currency'] == 'USD'

from decimal import Decimal

import duckdb
import pytest

from modules.telchi.datalake.commercial_reconciliation import create_conversion_views, validate_conversion


@pytest.fixture
def con():
    c = duckdb.connect(':memory:')
    c.execute('SET threads=2')
    c.execute('''CREATE TABLE oqut_october_2026 AS SELECT 1 DocEntry,
        'CLIENT' CardCode, 'Client' CardName, 'O' DocStatus, 'N' CANCELED''')
    c.execute('''CREATE TABLE qut1_october_2026 AS SELECT 1 DocEntry, 0 LineNum,
        'A' ItemCode, 'Product' Dscription, 'O' LineStatus, '12' Quantity, '204' LineTotal''')
    for table in ('orders_from_quotations', 'deliveries_from_quotations', 'invoices_from_quotations'):
        c.execute(f'''CREATE TABLE {table} (DocEntry BIGINT, LineNum BIGINT,
            BaseType BIGINT, BaseEntry BIGINT, BaseLine BIGINT,
            Quantity VARCHAR, LineTotal VARCHAR, HeaderCANCELED VARCHAR)''')
    yield c
    c.close()


def test_two_deliveries_and_invoices_do_not_duplicate_quotation(con):
    con.execute("INSERT INTO orders_from_quotations VALUES (10,0,23,1,0,'12','204','N')")
    con.execute("INSERT INTO deliveries_from_quotations VALUES (20,0,17,10,0,'12','204','N'),(21,0,17,10,0,'12','204','N')")
    con.execute("INSERT INTO invoices_from_quotations VALUES (30,0,15,20,0,'12','204','N'),(31,0,15,21,0,'12','204','N')")
    create_conversion_views(con)
    r = validate_conversion(con)
    assert r['quotation_lines'] == 1
    assert r['budgeted'] == Decimal('204')
    assert r['invoiced'] == Decimal('408')
    assert r['pending'] == 0
    assert r['excess_invoiced'] == 204


def test_multiple_partial_invoices_classified_after_sum(con):
    con.execute("INSERT INTO invoices_from_quotations VALUES (30,0,23,1,0,'5','80','N'),(31,0,23,1,0,'7','120','N')")
    create_conversion_views(con)
    r = validate_conversion(con)
    assert r['pending'] == 4
    assert con.sql('SELECT ConversionCategory FROM quotation_conversion').fetchone()[0] == 'CONVERTED_FULLY'


def test_decimal_partial_canceled_invoice_and_scope_gap(con):
    con.execute("INSERT INTO invoices_from_quotations VALUES (30,0,23,1,0,'5','80.01','N'),(31,0,23,1,0,'7','120','Y'),(32,0,23,999,0,'1','0.10','N')")
    create_conversion_views(con)
    r = validate_conversion(con)
    assert r['invoiced'] == Decimal('80.01')
    assert r['pending'] == Decimal('123.99')
    assert r['outside_scope_invoice_lines'] == 1
    assert r['outside_scope_invoice_amount'] == Decimal('0.10')
    assert con.sql('SELECT ConversionCategory FROM quotation_conversion').fetchone()[0] == 'CONVERTED_PARTIALLY'


def test_canceled_order_does_not_create_pending_order_stage(con):
    con.execute("INSERT INTO orders_from_quotations VALUES (10,0,23,1,0,'12','204','Y')")
    create_conversion_views(con)
    validate_conversion(con)
    assert con.sql('SELECT ConversionCategory FROM quotation_conversion').fetchone()[0] == 'NO_DOCUMENTAL_CONVERSION'


def test_duplicate_keys_fail_closed(con):
    con.execute('INSERT INTO qut1_october_2026 SELECT * FROM qut1_october_2026')
    create_conversion_views(con)
    with pytest.raises(ValueError, match='DUPLICATE_DOCUMENT_LINE'):
        validate_conversion(con)


def test_missing_header_fails_reconciliation(con):
    con.execute('DELETE FROM oqut_october_2026')
    create_conversion_views(con)
    with pytest.raises(ValueError, match='QUOTATION_GRAIN'):
        validate_conversion(con)


def test_rank_is_pending_not_budget_and_preserves_customer_detail(con):
    from modules.telchi.datalake.commercial_purpose_reader import CommercialPurposeViews
    con.execute("UPDATE qut1_october_2026 SET LineTotal='421350',Quantity='100',ItemCode='COPPER'")
    con.execute("INSERT INTO qut1_october_2026 VALUES (1,1,'SODA','Soda','O','100','410742.24')")
    con.execute("INSERT INTO invoices_from_quotations VALUES (30,0,23,1,0,'70','281388.75','N'),(31,0,23,1,1,'60','247286.63','N')")
    create_conversion_views(con)
    validate_conversion(con)
    reader = CommercialPurposeViews.__new__(CommercialPurposeViews)
    reader.con = con
    products = reader.top_products_unconverted().fetchall()
    assert [r[0] for r in products] == ['SODA', 'COPPER']
    assert products[0][5] == Decimal('163455.61')
    clients = reader.clients_for_top_products(1).fetchall()
    assert len(clients) == 1
    assert clients[0][0:4] == ('SODA', 'Soda', 'CLIENT', 'Client')
    assert clients[0][8] == Decimal('163455.61')


def test_legacy_candidate_cannot_bypass_canonical_extension_validation():
    from types import SimpleNamespace
    from modules.telchi.datalake.commercial_purpose_candidate import validate_pinned_candidate, mark_candidate_ready
    from modules.telchi.datalake.foundation_publication import FoundationReaderError
    p = SimpleNamespace(foundation_publication_id='candidate', status='READY_TO_COMMIT',
                        manifest={'foundation_publication_id': 'candidate',
                                  'candidate_kind': 'COMMERCIAL_PURPOSE_V1'})
    store = SimpleNamespace(get=lambda _: p)
    with pytest.raises(FoundationReaderError, match='manifest kind'):
        validate_pinned_candidate(store, 'candidate')
    # No set_status method exists: validation must reject before writing READY.
    with pytest.raises(FoundationReaderError, match='manifest kind'):
        mark_candidate_ready(store, 'candidate')


def test_uninvoiced_delivery_is_separate_from_order(con):
    con.execute("INSERT INTO orders_from_quotations VALUES (10,0,23,1,0,'12','204','N')")
    con.execute("INSERT INTO deliveries_from_quotations VALUES (20,0,17,10,0,'12','204','N')")
    create_conversion_views(con)
    validate_conversion(con)
    assert con.sql('SELECT ConversionCategory FROM quotation_conversion').fetchone()[0] == 'DELIVERY_NO_INVOICE'

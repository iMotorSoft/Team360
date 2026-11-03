"""Small SQL-contract fixtures; no Foundation, services or authorization claims."""
from decimal import Decimal

import duckdb
import pytest

from modules.telchi.investigation.validation.business_categories_sales_v1.distribution import totals_cte


@pytest.fixture
def con():
    with duckdb.connect() as c:
        c.execute('SET threads=1')
        c.execute('''CREATE TABLE headers(source_system VARCHAR,source_table VARCHAR,doc_entry VARCHAR,
            doc_date VARCHAR,canceled VARCHAR,currency VARCHAR,doc_total VARCHAR,
            raw_extraction_id VARCHAR,source_as_of VARCHAR)''')
        c.execute('''CREATE TABLE lines(source_system VARCHAR,source_table VARCHAR,doc_entry VARCHAR,
            line_num VARCHAR,item_code VARCHAR,line_total VARCHAR,currency VARCHAR,
            raw_extraction_id VARCHAR,source_as_of VARCHAR)''')
        c.execute('CREATE TABLE crosswalk("ItemCode" VARCHAR, product_business_type VARCHAR,status VARCHAR)')
        c.execute("INSERT INTO crosswalk VALUES ('R','RAW_MATERIAL','VALIDATED'),('F','LAB_FINISHED_PRODUCT','VALIDATED')")
        yield c


def header(c, key='1', total='115', **kw):
    row = dict(source_system='SAP_B1_HANA', source_table='OINV', doc_entry=key,
               doc_date='2026-09-01', canceled='N', currency='BS', doc_total=total,
               raw_extraction_id='capture', source_as_of='2026-09-28')
    row.update(kw)
    c.execute('INSERT INTO headers VALUES (?,?,?,?,?,?,?,?,?)', list(row.values()))


def line(c, key='1', num='0', item='R', amount='100', **kw):
    row = dict(source_system='SAP_B1_HANA', source_table='INV1', doc_entry=key,
               line_num=num, item_code=item, line_total=amount, currency='BS',
               raw_extraction_id='capture', source_as_of='2026-09-28')
    row.update(kw)
    c.execute('INSERT INTO lines VALUES (?,?,?,?,?,?,?,?,?)', list(row.values()))


def query(c, select='SELECT doc_entry,header_amount,line_amount,delta,categories FROM a'):
    docs = "(SELECT * FROM headers WHERE source_system='SAP_B1_HANA' AND source_table='OINV')"
    lines = "(SELECT * FROM lines WHERE source_system='SAP_B1_HANA' AND source_table='INV1')"
    return c.execute(totals_cte(docs, lines, 'crosswalk') + ' ' + select).fetchall()


def test_mixed_categories_never_repeat_header_or_assign_it_to_category(con):
    header(con, total='115')
    line(con, amount='70')
    line(con, num='1', item='F', amount='30')
    assert query(con) == [('1', Decimal('115'), Decimal('100'), Decimal('15'), 2)]


def test_type_and_namespace_collisions_excluded(con):
    header(con)
    header(con, total='900', source_table='ORIN')
    header(con, total='800', source_system='OTHER')
    line(con)
    line(con, amount='900', source_table='RIN1')
    line(con, amount='800', source_system='OTHER')
    assert query(con)[0][2:4] == (Decimal('100'), Decimal('15'))


@pytest.mark.parametrize('date,canceled,expected', [
    ('2026-08-31', 'N', 0), ('2026-09-01', 'N', 1),
    ('2026-09-30', 'N', 1), ('2026-10-01', 'N', 0),
    ('2026-09-01', 'Y', 0), ('2026-09-01', 'C', 0)])
def test_half_open_period_and_active_headers(con, date, canceled, expected):
    header(con, doc_date=date, canceled=canceled)
    line(con)
    assert len(query(con)) == expected


def test_lineage_and_currency_mismatches_are_visible_not_silently_dropped(con):
    header(con)
    line(con, currency='USD', raw_extraction_id='other')
    assert query(con, 'SELECT currency_mismatches,lineage_mismatches FROM a') == [(1, 1)]


def test_missing_lines_and_amounts_never_imputed_to_zero(con):
    header(con)
    assert query(con, 'SELECT lines,line_amount,delta FROM a') == [(0, None, None)]
    line(con, amount=None)
    assert query(con, 'SELECT missing_line_amounts,line_amount,delta FROM a') == [(1, None, None)]


def test_cent_materiality_signed_and_absolute_do_not_cancel(con):
    for key, total in [('1', '100.01'), ('2', '99.98'), ('3', '100.02')]:
        header(con, key, total)
        line(con, key)
    row = query(con, '''SELECT COUNT(*) FILTER(WHERE abs_delta>0.01),
        SUM(delta),SUM(abs_delta) FROM a''')[0]
    assert row == (2, Decimal('.01'), Decimal('.05'))


def test_duplicate_line_join_visible(con):
    header(con)
    line(con)
    line(con)
    assert query(con, 'SELECT lines,distinct_lines FROM a') == [(2, 1)]


def test_unclassified_does_not_disappear_from_amount(con):
    header(con)
    line(con, item='missing')
    assert query(con, 'SELECT unclassified,line_amount FROM a') == [(1, Decimal('100'))]

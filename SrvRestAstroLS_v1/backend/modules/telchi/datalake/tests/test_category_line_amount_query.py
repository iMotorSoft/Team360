"""Small independent SQL fixtures; real Foundation parity is a separate probe."""
from decimal import Decimal

import duckdb
import pytest

from modules.telchi.datalake.category_line_amount_query import aggregate, parameters

OPTIONS = dict(category='RAW_MATERIAL', date_from='2026-09-01', date_to_exclusive='2026-10-01', currency='BS')


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
        c.execute("INSERT INTO headers VALUES ('SAP_B1_HANA','OINV','1','2026-09-24','N','BS','999','capture','2026-09-24')")
        c.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','1','0','R','70.13','BS','capture','2026-09-24'),('SAP_B1_HANA','INV1','1','1','F','30.02','BS','capture','2026-09-24')")
        yield c


def query(con, **kw):
    return aggregate(con, 'headers', 'lines', 'crosswalk', dict(OPTIONS, **kw))


def test_mixed_category_second_category_and_partial_coverage(con):
    row, coverage, quality = query(con)
    assert Decimal(row['amount']) == Decimal('70.13')  # never 999 header
    assert (row['product_count'], row['line_count'], row['document_count']) == (1, 1, 1)
    assert coverage == dict(first_date='2026-09-24', last_date='2026-09-24', complete=False)
    assert quality == {'VALIDATED': 1}
    assert Decimal(query(con, category='LAB_FINISHED_PRODUCT')[0]['amount']) == Decimal('30.02')


def test_zero_and_period_boundaries(con):
    row, _, _ = query(con, date_from='2026-08-01', date_to_exclusive='2026-09-01')
    assert row['line_count'] == 0 and Decimal(row['amount']) == 0 and row['first_date'] is None
    assert query(con, date_to_exclusive='2026-09-24')[0]['line_count'] == 0


@pytest.mark.parametrize('state', ['Y', 'C'])
def test_canceled_excluded(con, state):
    con.execute('UPDATE headers SET canceled=?', [state])
    assert query(con)[0]['line_count'] == 0


@pytest.mark.parametrize('sql', [
    'INSERT INTO headers SELECT * FROM headers',
    'INSERT INTO lines SELECT * FROM lines',
    'INSERT INTO crosswalk SELECT * FROM crosswalk',
    "UPDATE lines SET doc_entry='orphan'",
    "UPDATE lines SET currency='USD'",
    "UPDATE headers SET currency='USD'",
    "UPDATE lines SET raw_extraction_id='other'",
    "UPDATE lines SET line_total=NULL",
    "UPDATE lines SET line_total='NaN'",
    "DELETE FROM lines",
    "DELETE FROM crosswalk WHERE \"ItemCode\"='R'",
    "UPDATE crosswalk SET status='PROVISIONAL' WHERE \"ItemCode\"='R'",
    "UPDATE crosswalk SET status='UNKNOWN' WHERE \"ItemCode\"='R'",
])
def test_integrity_fails_closed(con, sql):
    con.execute(sql)
    with pytest.raises(Exception):
        query(con)


def test_supported_classification_is_visible(con):
    con.execute("UPDATE crosswalk SET status='SUPPORTED'")
    assert query(con)[2] == {'SUPPORTED': 1}


@pytest.mark.parametrize('kw', [dict(category='UNKNOWN'), dict(category='invented'), dict(currency='USD'),
    dict(date_to_exclusive='2026-09-01'), dict(date_to_exclusive='2028-01-01')])
def test_unaccredited_parameters(kw):
    with pytest.raises(ValueError):
        parameters(dict(OPTIONS, **kw))


def test_other_source_and_document_type_do_not_duplicate(con):
    con.execute("INSERT INTO headers SELECT source_system,'ORIN',doc_entry,doc_date,canceled,currency,doc_total,raw_extraction_id,source_as_of FROM headers")
    con.execute("INSERT INTO lines SELECT 'OTHER',source_table,doc_entry,line_num,item_code,line_total,currency,raw_extraction_id,source_as_of FROM lines")
    assert Decimal(query(con)[0]['amount']) == Decimal('70.13')

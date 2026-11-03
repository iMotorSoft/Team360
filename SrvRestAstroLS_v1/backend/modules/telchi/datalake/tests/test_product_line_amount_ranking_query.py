"""Independent tiny relations; fixtures do not accredit Foundation or real Luna."""
from decimal import Decimal

import pytest
from modules.telchi.datalake.tests.test_category_line_amount_query import con, OPTIONS
from modules.telchi.datalake import product_line_amount_ranking_query as ranking


@pytest.fixture
def db(con):
    con.execute('CREATE TABLE products(source_system VARCHAR,item_code VARCHAR,sap_item_name VARCHAR,product_name VARCHAR,canonical_name VARCHAR)')
    con.execute("INSERT INTO products VALUES ('SAP_HANA','R','Raw',NULL,NULL),('SAP_HANA','F','Finished',NULL,NULL),('SAP_HANA','A','Tied raw',NULL,NULL)")
    return con


def query(db, **kwargs):
    return ranking.aggregate(db, 'headers', 'lines', 'crosswalk', 'products', dict(OPTIONS, limit=5, **kwargs))


def test_mixed_invoice_grain_and_reconciliation(db):
    full, total, coverage, quality, rec = query(db)
    assert full == [dict(item_code='R', description='Raw', amount='70.130000', line_count=1, document_count=1)]
    assert Decimal(rec['difference']) == 0 and rec['product_count'] == 1
    assert total['amount'] == '70.130000' and coverage['complete'] is False
    assert query(db, category='LAB_FINISHED_PRODUCT')[0][0]['amount'] == '30.020000'


def test_aggregate_before_limit_and_deterministic_tie(db):
    db.execute("INSERT INTO crosswalk VALUES ('A','RAW_MATERIAL','VALIDATED')")
    db.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','1','2','A','70.13','BS','capture','2026-09-24')")
    # Limit is intentionally NOT applied inside the full breakdown.
    full, total, _, _, rec = ranking.aggregate(db, 'headers', 'lines', 'crosswalk', 'products', dict(OPTIONS, limit=1))
    assert [r['item_code'] for r in full] == ['A', 'R']
    assert Decimal(total['amount']) == Decimal('140.26') and Decimal(rec['difference']) == 0
    assert sum(Decimal(r['amount']) for r in full[:1]) != Decimal(total['amount'])
    db.execute("UPDATE lines SET line_total='0.01' WHERE item_code='A'")
    assert [r['item_code'] for r in query(db)[0]] == ['R', 'A']


@pytest.mark.parametrize('sql', [
    'INSERT INTO headers SELECT * FROM headers', 'INSERT INTO lines SELECT * FROM lines',
    'INSERT INTO crosswalk SELECT * FROM crosswalk', 'INSERT INTO products SELECT * FROM products',
    "DELETE FROM products WHERE item_code='R'", "UPDATE products SET sap_item_name=NULL WHERE item_code='R'",
    "UPDATE headers SET currency='USD'", "UPDATE lines SET currency='USD'",
    "UPDATE lines SET raw_extraction_id='wrong'", "UPDATE lines SET line_total='NaN'",
    "UPDATE lines SET doc_entry='orphan'", "UPDATE crosswalk SET status='PROVISIONAL'",
])
def test_fail_closed_no_duplicates_or_unaccredited_values(db, sql):
    db.execute(sql)
    with pytest.raises(Exception):
        query(db)


@pytest.mark.parametrize('category', ['PACKAGING', 'SERVICE'])
def test_empty_category(db, category):
    full, total, coverage, _, rec = query(db, category=category)
    assert full == [] and total['line_count'] == 0 and Decimal(rec['difference']) == 0
    assert coverage['last_date'] == '2026-09-24'


@pytest.mark.parametrize('status', ['Y', 'C'])
def test_canceled_excluded(db, status):
    db.execute('UPDATE headers SET canceled=?', [status])
    assert query(db)[0] == []


def test_source_and_production_documents_excluded(db):
    db.execute("INSERT INTO headers SELECT source_system,'OIGE',doc_entry,doc_date,canceled,currency,doc_total,raw_extraction_id,source_as_of FROM headers")
    db.execute("INSERT INTO lines SELECT source_system,'IGE1',doc_entry,line_num,item_code,line_total,currency,raw_extraction_id,source_as_of FROM lines")
    db.execute("INSERT INTO products VALUES ('OTHER','R','Not SAP',NULL,NULL)")
    assert query(db)[0][0]['amount'] == '70.130000'


def test_external_currency_does_not_block_finished_on_mixed_invoice(db):
    db.execute("UPDATE lines SET currency='USD' WHERE item_code='R'")
    full, total, *_ = query(db, category='LAB_FINISHED_PRODUCT')
    assert full[0]['item_code'] == 'F' and total['amount'] == '30.020000'
    with pytest.raises(Exception, match='category_currency_not_accredited'):
        query(db)


def test_period_exclusive(db):
    assert query(db, date_to_exclusive='2026-09-24')[0] == []
    assert query(db, date_from='2026-09-24')[0][0]['amount'] == '70.130000'


@pytest.mark.parametrize('change', [dict(category=None), dict(category='UNKNOWN'), dict(category='invented'),
    dict(currency='USD'), dict(limit=True), dict(limit=0), dict(limit=51), dict(date_to_exclusive='2026-09-01')])
def test_bad_parameters(change):
    with pytest.raises(ValueError):
        ranking.parameters(OPTIONS | {'limit': 5} | change)


def test_reconciliation_failure_retains_evidence(db):
    full, total, *_ = query(db)
    wrong = dict(total, amount='71')
    with pytest.raises(ranking.RankingError) as exc:
        ranking.reconcile(full, wrong)
    assert exc.value.evidence['full_breakdown'] == full
    assert Decimal(exc.value.evidence['difference']) != 0

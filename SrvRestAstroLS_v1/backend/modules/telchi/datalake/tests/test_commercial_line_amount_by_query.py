"""Small independent SQL fixtures for the commercial breakdown reader.

Real Foundation parity is a separate live probe; this file proves the contract:
closed plan, zero tolerance reconciliation, document partition and no silent
row loss.
"""
from decimal import Decimal

import duckdb
import pytest

from modules.telchi.datalake import category_line_amount_query as category
from modules.telchi.datalake import commercial_line_amount_by_query as reader

MEASURE = 'commercial_active_invoice_line_amount_excluding_line_tax_v1'
PLAN = dict(dataset='commercial_line_amount',
             filters=dict(category='LAB_FINISHED_PRODUCT', item_code=None, card_code=None),
             date_from='2026-07-01', date_to_exclusive='2026-09-01', group_by='card_code',
             breakdown_by=None, periods=None, measure=MEASURE,
             order_by=[['amount', 'desc'], ['key', 'asc']], limit=10, currency='BS')


@pytest.fixture
def con():
    with duckdb.connect() as c:
        c.execute('SET threads=1')
        c.execute('''CREATE TABLE headers(source_system VARCHAR,source_table VARCHAR,doc_entry VARCHAR,
            doc_date VARCHAR,canceled VARCHAR,currency VARCHAR,doc_total VARCHAR,card_code VARCHAR,
            raw_extraction_id VARCHAR,source_as_of VARCHAR)''')
        c.execute('''CREATE TABLE lines(source_system VARCHAR,source_table VARCHAR,doc_entry VARCHAR,
            line_num VARCHAR,item_code VARCHAR,line_total VARCHAR,currency VARCHAR,
            raw_extraction_id VARCHAR,source_as_of VARCHAR)''')
        c.execute('CREATE TABLE crosswalk("ItemCode" VARCHAR, product_business_type VARCHAR,status VARCHAR)')
        c.execute("INSERT INTO crosswalk VALUES ('P1','LAB_FINISHED_PRODUCT','VALIDATED'),"
                  "('P2','LAB_FINISHED_PRODUCT','VALIDATED'),('P3','RAW_MATERIAL','VALIDATED')")
        c.execute("INSERT INTO headers VALUES "
                  "('SAP_B1_HANA','OINV','1','2026-07-10','N','BS','999','C1','capture','2026-07-10'),"
                  "('SAP_B1_HANA','OINV','2','2026-08-10','N','BS','999','C1','capture','2026-08-10'),"
                  "('SAP_B1_HANA','OINV','3','2026-08-11','N','BS','999','C2','capture','2026-08-11')")
        c.execute("INSERT INTO lines VALUES "
                  "('SAP_B1_HANA','INV1','1','0','P1','100.00','BS','capture','2026-07-10'),"
                  "('SAP_B1_HANA','INV1','1','1','P1','20.00','BS','capture','2026-07-10'),"
                  "('SAP_B1_HANA','INV1','2','0','P1','50.00','BS','capture','2026-08-10'),"
                  "('SAP_B1_HANA','INV1','3','0','P2','30.00','BS','capture','2026-08-11')")
        yield c


def options(**kw):
    from copy import deepcopy
    return deepcopy(dict(PLAN, **kw))


def test_plan_is_closed_and_validated():
    with pytest.raises(ValueError):
        reader.parameters(options(dataset='anything'))
    with pytest.raises(ValueError):
        reader.parameters(options(group_by='salesperson'))
    with pytest.raises(ValueError):
        reader.parameters(options(measure='another_measure'))
    with pytest.raises(ValueError):
        reader.parameters(options(currency='USD'))
    with pytest.raises(ValueError):
        reader.parameters(options(limit=0))
    with pytest.raises(ValueError):
        reader.parameters(options(filters=dict(category='LAB_FINISHED_PRODUCT', item_code=None, card_code=None, extra='x')))
    with pytest.raises(ValueError):
        reader.parameters(options(filters=dict(category='UNKNOWN', item_code=None, card_code=None)))
    with pytest.raises(ValueError):
        reader.parameters(options(breakdown_by='period'))
    with pytest.raises(ValueError):
        reader.parameters(options(periods=[dict(start='2026-07-01', end_exclusive='2026-08-01')]))
    assert reader.parameters(options())


def test_period_set_must_cover_the_window():
    with pytest.raises(ValueError):
        reader.parameters(options(breakdown_by='period', periods=[
            dict(start='2026-07-01', end_exclusive='2026-08-01'),
            dict(start='2026-08-01', end_exclusive='2026-08-15')]))
    with pytest.raises(ValueError):
        reader.parameters(options(breakdown_by='period', periods=[
            dict(start='2026-07-01', end_exclusive='2026-08-01'),
            dict(start='2026-08-05', end_exclusive='2026-09-01')]))


def test_reconciliation_is_zero_tolerance():
    total = dict(amount='200.00', product_count=2, line_count=4, document_count=3)
    evidence = reader.reconcile([dict(key='C1', amount='170.00', line_count=3, document_count=2),
                                  dict(key='C2', amount='30.00', line_count=1, document_count=1)],
                                 total, 'card_code')
    assert Decimal(evidence['difference']) == 0 and evidence['tolerance'] == '0'
    with pytest.raises(reader.CommercialAmountError):
        reader.reconcile([dict(key='C1', amount='169.99', line_count=3, document_count=2)],
                          dict(total, amount='170.00'), 'card_code')


def test_grouping_partitions_documents_and_amounts():
    rows = [dict(key='C1', label='Cliente Uno', amount='170.00', line_count=3, document_count=2),
            dict(key='C2', label='Cliente Dos', amount='30.00', line_count=1, document_count=1)]
    total = dict(amount='200.00', product_count=2, line_count=4, document_count=3)
    evidence = reader.reconcile(rows, total, 'card_code')
    assert evidence['document_count'] == evidence['universe_document_count'] == 3
    # A product does not partition documents: only amount and lines must match.
    with pytest.raises(reader.CommercialAmountError):
        reader.reconcile([dict(key='P1', label='Producto', amount='200.00', line_count=4, document_count=3)],
                          dict(total, product_count=2), 'sap_product')


def test_result_contract_rejects_tampering():
    result = dict(capability=reader.CAPABILITY, parameters=options(), plan=reader.plan_of(options()),
                  definition=MEASURE, currency='BS', read_only=True, sap_accessed=False,
                  source=dict(publication_id=category.PUBLICATION, snapshot_id=category.SNAPSHOT,
                              updated_at='2026-09-01'),
                  limitations=reader.LIMITATIONS, coverage=dict(first_date=None, last_date=None, complete=False),
                  rows=[], full_breakdown=[], exceptions=[], accreditation='verified',
                  total=dict(amount='200.00', product_count=2, line_count=4, document_count=3,
                             customer_count=2), universe_total=None, unnamed_accounts=0, focus={})
    rows = [dict(key='C1', label='Cliente Uno', amount='170.00', line_count=3, document_count=2),
            dict(key='C2', label='Cliente Dos', amount='30.00', line_count=1, document_count=1)]
    result['full_breakdown'] = rows
    result['rows'] = rows[:options()['limit']]
    result['reconciliation'] = reader.reconcile(rows, result['total'], 'card_code')
    assert reader.validate_result(options(), result) is result
    for tamper in ('amount', 'order', 'limit', 'currency', 'reconciliation', 'universe'):
        broken = dict(result)
        if tamper == 'amount':
            broken['rows'] = [dict(rows[0], amount='999.00')]
        elif tamper == 'order':
            broken['full_breakdown'] = list(reversed(rows))
            broken['rows'] = broken['full_breakdown']
        elif tamper == 'limit':
            # The presented list must be exactly the first limit of the universe.
            broken['parameters'] = dict(options(), limit=1)
        elif tamper == 'currency':
            broken['currency'] = 'USD'
        elif tamper == 'reconciliation':
            broken['reconciliation'] = dict(broken['reconciliation'], difference='1.00')
        elif tamper == 'universe':
            broken['universe_total'] = dict(amount='not-a-number')
        with pytest.raises(Exception):
            reader.validate_result(options(), broken)

from decimal import Decimal

import pytest

from modules.telchi.datalake import category_line_amount_query as category
from modules.telchi.datalake import commercial_line_amount_by_query as commercial
from modules.telchi.datalake import physical_sales_dimension as physical
from .test_commercial_line_amount_by_query import con, options  # noqa: F401


def setup(con):
    con.execute('CREATE TABLE products(source_system VARCHAR,canonical_product_id VARCHAR,sap_forma_farmac_code VARCHAR,physical_classification_observed_at VARCHAR)')
    con.execute('CREATE TABLE identity_map(source_system VARCHAR,source_native_id VARCHAR,canonical_id VARCHAR)')
    for i,code in [('P1','1'),('P2','3'),('P3','2'),('P0','0'),('P4','4'),('P5','5'),('PM',None),('PU','99')]:
        con.execute("INSERT INTO products VALUES ('SAP_HANA',?,?, '2026-10-29T00:00:00Z')", [i,code])
        con.execute("INSERT INTO identity_map VALUES ('SAP_HANA',?,?)", [i,i])
    return dict(date_from='2026-07-01',date_to_exclusive='2026-09-01')


def source(con, base):
    cte,args = category.scoped_source(con,'headers','lines','crosswalk',base,project_card_code=True)
    total,_,_ = category.scoped_aggregate(con,'headers','lines','crosswalk',base,
        require_category=False,source=(cte,args))
    cte,args = physical.enrich(con,cte,args,'products','identity_map')
    rows = commercial._grouped(con,cte,args,options(group_by='physical_state',filters=dict(category=None,item_code=None,card_code=None)),None)
    return cte,args,rows,total


def test_mixed_invoice_discounts_unclassified_codes_and_exact_line_reconciliation(con):
    base = setup(con)
    for n,code,amount in [('2','P2','8.50'),('3','P3','4.25'),('4','P0','10'),('5','P4','20'),
                          ('6','P5','30'),('7','PM','40'),('8','PU','50'),('9','MISSING_ID','60')]:
        con.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','1',?,?,?,'BS','capture','2026-07-10')",[n,code,amount])
    cte,args,rows,total = source(con,base)
    amounts = {r['key']:Decimal(r['amount']) for r in rows}
    assert amounts['LIQUID']==Decimal('170')
    assert amounts['SOLID']==Decimal('38.50')  # not either invoice header's 999
    assert amounts['SEMISOLID']==Decimal('4.25')
    assert amounts['MEDICINE']==20 and amounts['NOT_APPLICABLE']==30
    assert amounts['UNCLASSIFIED']==10 and amounts['MISSING']==40
    assert amounts['UNKNOWN']==50 and amounts['IDENTITY_MISSING']==60
    assert commercial.reconcile(rows,total,'physical_state')['difference']=='0.000000'
    profile = physical.profile(con,cte,args)
    assert Decimal(profile['classified_amount'])==Decimal('212.75')
    assert Decimal(profile['without_explicit_amount'])==210
    assert profile['product_count']==9 and profile['classified_product_count']==3
    assert profile['audit'][0]['observed_from'] is None  # missing identity preserved
    assert 'no necesariamente vigente' in profile['observation_warning']
    assert sum(Decimal(r['amount']) for r in profile['daily'])==Decimal(total['amount'])
    assert sum(Decimal(r['amount']) for r in profile['products'])==Decimal(total['amount'])


def test_cancelled_invoices_and_credit_note_lines_do_not_change_invoice_measure(con):
    base=setup(con)
    con.execute("INSERT INTO headers VALUES ('SAP_B1_HANA','OINV','4','2026-08-01','Y','BS','100','C1','capture','2026-08-01'),"
                "('SAP_B1_HANA','ORIN','5','2026-08-01','N','BS','100','C1','capture','2026-08-01')")
    con.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','4','0','P1','100','BS','capture','2026-08-01'),"
                "('SAP_B1_HANA','RIN1','5','0','P1','100','BS','capture','2026-08-01')")
    _,_,rows,total=source(con,base)
    assert Decimal(total['amount'])==200
    assert sum(Decimal(r['amount']) for r in rows)==200


def test_currency_exclusion_is_upstream_of_physical_enrichment(con):
    base=setup(con)
    con.execute("UPDATE lines SET currency='USD' WHERE doc_entry='3'")
    cte,args=category.scoped_source(con,'headers','lines','crosswalk',base,project_card_code=True)
    exceptions=[]
    total,_,_=category.scoped_aggregate(con,'headers','lines','crosswalk',base,
        require_category=False,source=(cte,args),exceptions=exceptions)
    assert len(exceptions)==1 and Decimal(total['amount'])==170
    cte,args=physical.enrich(con,category.bs_only_cte(cte),args,'products','identity_map')
    assert Decimal(physical.profile(con,cte,args)['classified_amount'])==170


def test_disjoint_same_day_comparison_excludes_the_gap(con):
    base=setup(con)
    con.execute("INSERT INTO headers VALUES ('SAP_B1_HANA','OINV','6','2026-07-31','N','BS','99','C1','capture','2026-07-31')")
    con.execute("INSERT INTO lines VALUES ('SAP_B1_HANA','INV1','6','0','P1','99','BS','capture','2026-07-31')")
    periods=[dict(start='2026-07-01',end_exclusive='2026-07-30'),
             dict(start='2026-08-01',end_exclusive='2026-08-30')]
    opts=options(group_by='physical_state',date_to_exclusive='2026-08-30',
                 breakdown_by='period',periods=periods)
    assert commercial.parameters(opts)
    base.update(date_to_exclusive='2026-08-30',periods=periods)
    cte,args,rows,total=source(con,base)
    assert Decimal(total['amount'])==200
    assert sum(Decimal(r['amount']) for r in rows)==200


def test_profile_tampering_is_rejected(con):
    from copy import deepcopy
    base=setup(con)
    cte,args,rows,total=source(con,base)
    result=physical.profile(con,cte,args)
    assert physical.validate_profile(result,rows,total) is result
    for field in ('daily','products','coverage_percent'):
        altered=deepcopy(result)
        if field=='coverage_percent': altered[field]['amount']='999'
        else: altered[field][0]['amount']='99999'
        with pytest.raises(ValueError,match='invalid_physical_profile'):
            physical.validate_profile(altered,rows,total)


def test_duplicate_identity_cannot_inflate_sales(con):
    base=setup(con)
    con.execute("INSERT INTO identity_map VALUES ('SAP_HANA','P1','P1')")
    with pytest.raises(Exception,match='physical_identity_integrity_failed'):
        source(con,base)


def test_documentary_reader_accepts_exact_physical_successor():
    from modules.telchi.datalake import sales_query
    from .test_sales_promoted_binding import envelope
    params, result = envelope('2026-10-01','2026-10-30','11269116.22','457793.30','10811322.92')
    result['source']['publication_id'] = sales_query.PHYSICAL_SUCCESSOR_PUBLICATION
    assert sales_query.validate_result(sales_query.MONETARY_OPERATION,params,result) is result


def test_physical_breakdown_cannot_be_truncated():
    assert commercial.parameters(options(group_by='physical_state',limit=10))
    with pytest.raises(ValueError,match='must_not_be_truncated'):
        commercial.parameters(options(group_by='physical_state',limit=3))

from decimal import Decimal as D

import pytest

from modules.telchi.investigation.validation.bronceador_urucu_summer_2026_v1.summarize import summarize


def sample():
    codes=['L03124','L03125']
    a=dict(products=[dict(item_code=c,sap_item_name=c) for c in codes],invoice_2026=[],credit_2026=[],invoice_monthly=[],credit_monthly=[],historical_sales=[],product_stock=[],bom_headers=[],bom_lines=[],material_names=[],relevant_stock=[])
    for c in codes:
        a['invoice_2026'].append(dict(item_code=c,qty='20',amount_bs='100'))
        a['invoice_monthly'].append(dict(item_code=c,month='2026-01',qty='20',amount_bs='100'))
        a['historical_sales'] += [dict(item_code=c,month='2024-01',qty='10'),dict(item_code=c,month='2023-12',qty='5')]
        a['product_stock'] += [dict(item_code=c,whs_code='LAB-T1',available='4'),dict(item_code=c,whs_code='LAB-DAN',available='999'),dict(item_code=c,whs_code='LAB-P5',available='999')]
        a['bom_headers'].append(dict(Code=c,Qauntity='100'))
        a['bom_lines'].append(dict(Father=c,Code='EXTRACT',Quantity='10',Type=4,AddQuantit='0'))
    return a


def test_excludes_damaged_and_retained_stock():
    s=summarize(sample())
    assert s['candidate_commercial_stock']=={'L03124':D(4),'L03125':D(4)}


def test_ratio_and_buffer_are_explicit():
    s=summarize(sample())['scenario']['L03124']
    assert s['growth_factor']==2
    assert s['estimated_december2026']==10
    assert s['estimated_season']==30
    assert s['illustrative_season_plus20pct']==36


def test_bom_batch_denominator_and_shared_input():
    s=summarize(sample())
    assert s['illustrative_bom_requirements'][0]['required_bom_native']==D('325')


def test_reconciliation_fails_closed():
    a=sample()
    a['invoice_2026'][0]['qty']='21'
    with pytest.raises(AssertionError):
        summarize(a)


def test_preseason_depletion_is_not_ignored():
    a=sample()
    a['invoice_monthly'].append(dict(item_code='L03124',month='2026-07',qty='86',amount_bs='430'))
    a['invoice_2026'][0].update(qty='106',amount_bs='530')
    s=summarize(a)['scenario']['L03124']
    assert s['preseason_estimate']==67
    assert s['base_production_need']==93  # 30 summer + 67 pre-season - 4 stock.


def test_no_physical_returns_inference():
    a=sample()
    a['credit_2026']=[dict(item_code='L03124',qty='2',amount_bs='10')]
    a['credit_monthly']=[dict(item_code='L03124',month='2026-01',qty='2',amount_bs='10')]
    s=summarize(a)
    assert s['annual']['L03124']['net_document_qty']==18
    assert any('not proven physical returns' in x for x in s['limitations'])

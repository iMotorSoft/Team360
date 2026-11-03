"""Deterministic scenarios, not an approved demand or manufacturing plan."""
import csv
import json
from collections import defaultdict
from decimal import Decimal as D
from pathlib import Path

SALES_WAREHOUSES = {'LAB-T1', 'LPZ-T1', '2A-SAL', 'CM-SAL', 'RC-SAL', 'VI-SAL'}
CORE = ('L03124', 'L03125')


def summarize(a, lots=None):
    annual = {}
    for p in a['products']:
        code = p['item_code']
        inv = next((r for r in a['invoice_2026'] if r['item_code']==code), {})
        cr = next((r for r in a['credit_2026'] if r['item_code']==code), {})
        if not inv and not cr:
            continue
        annual[code] = dict(product=p['sap_item_name'], invoiced_qty=D(inv.get('qty',0)), credit_qty=D(cr.get('qty',0)), invoiced_bs=D(inv.get('amount_bs',0)), credit_bs=D(cr.get('amount_bs',0)))
        annual[code]['net_document_qty'] = annual[code]['invoiced_qty'] - annual[code]['credit_qty']
        annual[code]['net_line_bs'] = annual[code]['invoiced_bs'] - annual[code]['credit_bs']
    monthly = defaultdict(lambda: dict(invoiced_qty=D(0), credit_qty=D(0), invoiced_bs=D(0), credit_bs=D(0)))
    for label in ['invoice','credit']:
        for r in a[label+'_monthly']:
            if not r['month'].startswith('2026-'):
                continue
            qkey, akey = ('invoiced_qty','invoiced_bs') if label=='invoice' else ('credit_qty','credit_bs')
            monthly[r['month']][qkey] += D(r['qty'])
            monthly[r['month']][akey] += D(r['amount_bs'])
    for v in monthly.values():
        v['net_document_qty'] = v['invoiced_qty'] - v['credit_qty']
        v['net_line_bs'] = v['invoiced_bs'] - v['credit_bs']
    historical = defaultdict(lambda: defaultdict(lambda: D(0)))
    for r in a['historical_sales']:
        year, month = map(int, r['month'].split('-'))
        historical[str(year if month==12 else year-1)][r['item_code']] += D(r['qty'])
    sales_stock = defaultdict(lambda: D(0))
    lab_stock = defaultdict(lambda: D(0))
    for r in a['product_stock']:
        if r['whs_code'] in SALES_WAREHOUSES:
            sales_stock[r['item_code']] += D(r['available'])
        if r['whs_code']=='LAB-T1':
            lab_stock[r['item_code']] += D(r['available'])
    scenarios = {}
    for code in CORE:
        janfeb26 = sum((D(r['qty']) for r in a['invoice_monthly'] if r['item_code']==code and r['month'] in ['2026-01','2026-02']), D(0))
        janfeb24 = sum((D(r['qty']) for r in a['historical_sales'] if r['item_code']==code and r['month'] in ['2024-01','2024-02']), D(0))
        december23 = sum((D(r['qty']) for r in a['historical_sales'] if r['item_code']==code and r['month']=='2023-12'), D(0))
        growth = janfeb26 / janfeb24
        estimated_dec = december23 * growth
        seasonal = janfeb26 + estimated_dec
        recent_qty = sum((D(r['qty']) for r in a['invoice_monthly'] if r['item_code']==code and r['month'] in ['2026-07','2026-08','2026-09']), D(0))
        preseason = recent_qty / D(86) * D(67)  # Jul 1-Sep 24 rate, Sep 25-Nov 30 horizon.
        base_need = max(D(0), seasonal + preseason - sales_stock[code])
        buffer_need = max(D(0), seasonal*D('1.2') + preseason - sales_stock[code])
        scenarios[code] = dict(janfeb2026=janfeb26, janfeb2024=janfeb24, growth_factor=growth, estimated_december2026=estimated_dec, estimated_season=seasonal, illustrative_season_plus20pct=seasonal*D('1.2'), commercial_network_stock=sales_stock[code], lab_stock=lab_stock[code], preseason_estimate=preseason, base_production_need=base_need, buffered_production_need=buffer_need)
    # Illustrative rounded lots: actual BOM batches, NOT a demand forecast approval.
    lots = lots if lots is not None else {'L03124':D(2000),'L03125':D(1250)}
    headers = {r['Code']: D(r['Qauntity']) for r in a['bom_headers']}
    children = defaultdict(list)
    for r in a['bom_lines']:
        children[r['Father']].append(r)
    requirements = defaultdict(lambda: D(0))
    def expand(code, qty, stack=()):
        assert code not in stack
        assert headers[code]>0
        for r in children[code]:
            if r['Type']!=4:
                continue
            assert D(r['AddQuantit'])==0, 'Additional quantities need explicit handling'
            amount = qty * D(r['Quantity']) / headers[code]
            requirements[r['Code']] += amount
            if r['Code'] in headers and r['Code']!='L00050':
                expand(r['Code'], amount, stack+(code,))
    for code,qty in lots.items():
        expand(code,qty)
    # Count existing extract as input; do not also charge seed/vaseline to make it.
    names = {r['item_code']: r['sap_item_name'] for r in a['material_names']}
    material_rows=[]
    for code, required in sorted(requirements.items()):
        stock_m1=sum((D(r['available']) for r in a['relevant_stock'] if r['item_code']==code and r['whs_code']=='LAB-M1'), D(0))
        stock_p1=sum((D(r['available']) for r in a['relevant_stock'] if r['item_code']==code and r['whs_code']=='LAB-P1'), D(0))
        material_rows.append(dict(item_code=code,name=names.get(code),required_bom_native=required,lab_m1_uncommitted=stock_m1,lab_p1_uncommitted=stock_p1,lab_m1_arithmetic_gap=max(D(0),required-stock_m1),intermediate=code in headers and code!='L00050'))
    result=dict(annual=annual,monthly=dict(sorted(monthly.items())),historical_invoiced_units={k:dict(v) for k,v in historical.items()},candidate_commercial_stock=dict(sales_stock),lab_t1_uncommitted_stock=dict(lab_stock),scenario=scenarios,illustrative_production_lots=lots,illustrative_bom_requirements=material_rows,limitations=['2026 through September 24 only; credit coverage through September 23', 'No complete 2024-2025 or 2025-2026 summer found in selected sources', '2023-2024 historical export ends February 28, no February 29 evidence', 'Historical ItemSale is a separate metric; quantities are compared, not revenue growth', 'Credit quantities are documentary adjustments, not proven physical returns', 'BOM native units and quality release require production-owner confirmation', 'Candidate commercial warehouses selected by recorded descriptions, not a certified sellability crosswalk', 'Forecast is an illustrative carry-forward ratio plus optional 20% buffer; pre-December depletion uses Jul-Sep gross invoice rate and excludes October actuals and other-product future material demand', 'No live SAP, lot expiry, production capacity or completion-date certification'])
    for field in ['invoiced_qty','credit_qty','net_document_qty','invoiced_bs','credit_bs','net_line_bs']:
        assert sum(v[field] for v in annual.values()) == sum(v[field] for v in monthly.values())
    return result


def main():
    root=Path(__file__).resolve().parents[7]
    dest=root/'data/reports/telchi/bronceador-urucu-summer-2026-v1'
    a=json.loads((dest/'evidence.json').read_text())
    result=summarize(a)
    buffered=summarize(a, {'L03124':D(3000),'L03125':D(2500)})
    result['buffered_production_lots']=buffered['illustrative_production_lots']
    result['buffered_bom_requirements']=buffered['illustrative_bom_requirements']
    (dest/'summary.json').write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2)+'\n')
    for key in ['annual','monthly']:
        records=[dict(key=k,**v) for k,v in result[key].items()]
        with (dest/(key+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]),delimiter=';');w.writeheader();w.writerows(records)
    print(json.dumps(result,default=str,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

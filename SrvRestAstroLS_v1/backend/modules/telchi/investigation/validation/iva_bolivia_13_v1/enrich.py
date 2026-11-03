"""Independent currency evidence and explicit, non-causal exception diagnostics."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal as D, localcontext
from pathlib import Path
import duckdb

OUT = Path('../../data/reports/telchi/iva-bolivia-13-v1')
BASE = Path('modules/telchi/investigation/validation')


def main():
    ev = dict(reused_currency_evidence=[], price_identity=Counter(), amount_precision=Counter(),
              category_by_tax_rate={}, queries=[], sap_write_count=0)
    for folder, name in [('balance_sheet_pnl_reconstruction', 'balance_sheet_pnl_reconstruction_v1'),
                         ('financial_position_cash_flow', 'financial_position_cash_flow_v1_1')]:
        p = BASE / folder / (name+'.json')
        j = json.loads(p.read_text())
        source = BASE / folder / (name+'.py')
        ev['reused_currency_evidence'].append(dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            generated_at_utc=j['generated_at_utc'], source=j['source'], company_currency=j['company_currency'],
            source_script=str(source), source_script_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            oadm_sql=[line.strip() for line in source.read_text().splitlines() if 'MainCurncy' in line]))
    docs = list(csv.DictReader((OUT / 'documents.csv').open()))
    bound = {r['doc_entry']: r for r in docs}
    report = json.loads((OUT/'reconciliation.json').read_text())
    groups = defaultdict(list)
    for r in docs:
        e = D(r['E'])
        bridge = D(r['tax_bridge_residual'])
        partition = ('1_exact_13' if not e else '2_within_001_13' if abs(e)<=D('.01') else
                     '3_other_registered_tax_treatment' if abs(bridge)<=D('.01') else '4_unresolved')
        groups[partition].append(r)
    ev['exclusive_partition'] = {k: dict(documents=len(v), E=sum((D(r['E']) for r in v),D(0)),
        C=sum((D(r['C']) for r in v),D(0)), tax_bridge=sum((D(r['tax_bridge_residual']) for r in v),D(0))) for k,v in groups.items()}
    # Separate verified nonzero tax from documents whose tax is zero.
    ev['nonzero_tax_verified'] = sum(D(r['registered_line_tax']) != 0 and abs(D(r['tax_bridge_residual'])) <= D('.01') for r in docs)
    ev['zero_tax_reconciled'] = sum(D(r['registered_line_tax']) == 0 and abs(D(r['tax_bridge_residual'])) <= D('.01') for r in docs)
    ev['tax_comparison_crosstab'] = dict(Counter(r['match']+'/'+r['cause'] for r in docs))
    ev['unresolved_signed'] = dict(documents=sum(r['cause']=='unresolved' for r in docs),
        signed=sum((D(r['tax_bridge_residual']) for r in docs if r['cause']=='unresolved'),D(0)),
        absolute=sum((abs(D(r['tax_bridge_residual'])) for r in docs if r['cause']=='unresolved'),D(0)))
    con = duckdb.connect(config={'threads':1,'memory_limit':'128MB','max_temp_directory_size':'0B'})
    try:
        from modules.telchi.datalake.ducklake import DATA_ROOT
        crosswalk_path = DATA_ROOT/'crosswalk/_versions'/report['lineage']['reference_version']/'product_business_type/part-00000.parquet'
        assert hashlib.sha256(crosswalk_path.read_bytes()).hexdigest() == report['crosswalk_sha256']
        cur = con.execute(f'''SELECT "ItemCode",product_business_type FROM read_parquet('{crosswalk_path}')''')
        cats = dict(cur.fetchall())
        category = defaultdict(lambda: dict(lines=0, amount=D(0), registered_tax=D(0), documents=set(), products=set()))
        examples = []
        selected = 0
        for m in report['raw_manifests']:
            for f in m['files']:
                p = Path(f['path'])
                assert hashlib.sha256(p.read_bytes()).hexdigest() == f['sha256']
                sql = f'''SELECT "DocEntry","LineNum","ItemCode","Price","PriceBefDi","Quantity","LineDiscPrcnt","LineTotal","LineVatSum","VatPrcnt","TotalFrgn","TotalSumSy","LineRate" FROM read_parquet('{p}')'''
                ev['queries'].append(sql)
                cur = con.execute(sql)
                cols = [c[0] for c in cur.description]
                for row in cur.fetchall():
                    r = dict(zip(cols, row))
                    doc = bound.get(str(r['DocEntry']))
                    if not doc or doc['raw_extraction_id'] != m['run_id']+'_changed':
                        continue
                    selected += 1
                    total, qty, price, before, disc = (D(str(r[k])) for k in ['LineTotal','Quantity','Price','PriceBefDi','LineDiscPrcnt'])
                    diff = total-qty*price
                    diff2 = total-qty*before*(1-disc/D(100))
                    ev['price_identity']['quantity_times_price_exact' if not diff else 'quantity_times_price_within_001' if abs(diff)<=D('.01') else 'quantity_times_price_outside_001'] += 1
                    ev['price_identity']['discount_formula_exact' if not diff2 else 'discount_formula_within_001' if abs(diff2)<=D('.01') else 'discount_formula_outside_001'] += 1
                    ev['amount_precision']['cent_exact' if total==total.quantize(D('.01')) else 'subcent'] += 1
                    if disc and len(examples)<8:
                        examples.append({k:r[k] for k in ['DocEntry','LineNum','Price','PriceBefDi','Quantity','LineDiscPrcnt','LineTotal']} | dict(discount_formula_residual=diff2))
                    if cats.get(str(r['ItemCode'])) == 'RAW_MATERIAL':
                        c = category[str(r['VatPrcnt'])]
                        c['lines'] += 1
                        c['amount'] += total
                        c['registered_tax'] += D(str(r['LineVatSum']))
                        c['documents'].add(str(r['DocEntry']))
                        c['products'].add(str(r['ItemCode']))
        ev['matched_lines'] = selected
        assert selected == 65163
        ev['discount_examples'] = examples
        ev['category_by_tax_rate'] = {k:dict(v, documents=len(v['documents']),products=len(v['products'])) for k,v in category.items()}
        ev['category_tax_formula_warning'] = 'VatSum is recorded line tax; header discount/base attribution unresolved. Never auto-apply /0.87 to category.'
    finally:
        con.close()
    with (OUT/'diagnostics.json').open('x') as f:
        json.dump(ev,f,indent=2,default=str)
    print(json.dumps({k:v for k,v in ev.items() if k not in ['queries','discount_examples']}, indent=2,default=str))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    OUT = parser.parse_args().output
    with localcontext() as ctx:
        ctx.prec = 50
        main()

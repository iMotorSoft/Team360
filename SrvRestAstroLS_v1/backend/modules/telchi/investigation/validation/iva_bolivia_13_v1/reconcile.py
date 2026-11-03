"""Pinned Foundation + capture-matched Raw reconciliation, Decimal only.

No production imports of this runner, no writes to Foundation/SAP/Data Root.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.investigation.validation.business_categories_sales_v1.distribution import totals_cte, PUBLICATION

OUT = Path('../../data/reports/telchi/iva-bolivia-13-v1')
ZERO = Decimal(0)
RATE = Decimal('0.13')
TOL = Decimal('0.01')


def classification(a, b):
    c = a-b
    e = c-a*RATE
    return c, a*RATE, e, ('exact' if e == 0 else 'tolerance' if abs(e) <= TOL else 'exception')


def stats(rows):
    counts = Counter(r['match'] for r in rows)
    result = dict(documents=len(rows), counts=dict(counts), aggregate_difference=sum((r['C'] for r in rows), ZERO),
                  predicted_13=sum((r['D'] for r in rows), ZERO), aggregate_residual=sum((r['E'] for r in rows), ZERO),
                  absolute_residual=sum((abs(r['E']) for r in rows), ZERO))
    result['bands'] = []
    low = None
    for high in [Decimal('0'), TOL, Decimal('0.1'), Decimal('1'), Decimal('10'), Decimal('100'), Decimal('1000'), None]:
        subset = [r for r in rows if (low is None or abs(r['E']) > low) and (high is None or abs(r['E']) <= high)]
        result['bands'].append(dict(lower_exclusive=low, upper_inclusive=high, documents=len(subset),
                                    residual=sum((r['E'] for r in subset), ZERO), absolute_residual=sum((abs(r['E']) for r in subset), ZERO)))
        low = high
    return result


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    ev = dict(read_only=True, sap_write_count=0, threads=1, memory_limit='256MB', queries=[])
    def query(con, name, sql):
        cur = con.execute(sql)
        columns = [c[0] for c in cur.description]
        rows = [dict(zip(columns, r)) for r in cur.fetchall()]
        ev['queries'].append(dict(name=name, sql=sql, rows_returned=len(rows)))
        return rows
    with DuckLakeConnector().session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='256MB'")
        con.execute("SET max_temp_directory_size='0B'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() == (True,)
        access = FoundationReader().resolve_on(con)
        assert access.foundation_publication_id == PUBLICATION and access.ducklake_snapshot_id == 1408
        ev['lineage'] = access.as_dict()
        crosswalk = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_business_type/part-00000.parquet'
        ev['crosswalk_sha256'] = hashlib.sha256(crosswalk.read_bytes()).hexdigest()
        x = f"read_parquet('{crosswalk}')"
        d = f"(SELECT * FROM {access.sales('sales_document')} WHERE source_system='SAP_B1_HANA' AND source_table='OINV')"
        l = f"(SELECT * FROM {access.sales('sales_line')} WHERE source_system='SAP_B1_HANA' AND source_table='INV1')"
        cte = totals_cte(d, l, x)
        docs = query(con, 'documents', cte + ''' SELECT doc_entry,doc_num,SUBSTR(doc_date,1,10) doc_date,currency,
header_amount A,line_amount B,lines,categories,raw_extraction_id,source_as_of,
currency_mismatches,lineage_mismatches,missing_line_amounts FROM a ORDER BY doc_entry''')
        assert len(docs) == 30301 and len({r['doc_entry'] for r in docs}) == 30301
        for r in docs:
            assert r['A'] is not None and r['B'] is not None
            assert not (r['currency_mismatches'] or r['lineage_mismatches'] or r['missing_line_amounts'])
            r['C'], r['D'], r['E'], r['match'] = classification(r['A'], r['B'])
        lines = query(con, 'lines_for_parity', f'''SELECT l.doc_entry,l.line_num,l.item_code,l.line_total,l.quantity,l.price,l.currency,
l.raw_extraction_id,x.product_business_type,x.status FROM {d} d JOIN {l} l
ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry LEFT JOIN {x} x ON x."ItemCode"=l.item_code
WHERE d.canceled='N' AND d.doc_date>='2026-09-01' AND d.doc_date<'2026-10-01' ''')
        assert len({(r['doc_entry'], r['line_num']) for r in lines}) == len(lines)
        ev['foundation_raw_extraction_ids'] = dict(Counter(r['raw_extraction_id'] for r in docs))
        # Changed-only publications retain run_id_changed. Trace the same run's September raw segment.
        runs = {r['raw_extraction_id'].removesuffix('_changed') for r in docs}
        manifests = []
        for path in (DATA_ROOT / 'raw/sap').glob('*/sales-2026-09*/*/manifest.json'):
            m = json.loads(path.read_text())
            if m.get('run_id') in runs or m.get('extraction_id') in ev['foundation_raw_extraction_ids']:
                manifests.append((path, m))
        ev['raw_manifests'] = []
        raw = {}
        for path, m in manifests:
            entry = dict(path=str(path), manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         extraction_id=m['extraction_id'], run_id=m.get('run_id'), source_as_of=m.get('source_as_of'), files=[])
            for f in m['files']:
                p = path.parent / f['file']
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                assert digest == f['sha256']
                entry['files'].append(dict(path=str(p), sha256=digest))
                raw_rows = query(con, 'raw_selected_tax_fields', f'''SELECT "DocEntry","DocNum","DocDate","CANCELED","DocCur","DocTotal",
"DocTotalFC","DocTotalSy","LineNum","ItemCode","LineTotal","LineCurrency","Price","PriceBefDi","Quantity",
"LineDiscPrcnt","VatPrcnt","LineVatSum","TotalFrgn","TotalSumSy","LineRate"
FROM read_parquet('{p}')''')
                for r in raw_rows:
                    key = (str(r['DocEntry']), str(r['LineNum']), m.get('run_id') or m['extraction_id'])
                    assert key not in raw, 'ambiguous raw capture'
                    raw[key] = (r, m)
            ev['raw_manifests'].append(entry)
        doc_by_id = {r['doc_entry']: r for r in docs}
        taxes, rates, discounts = defaultdict(list), defaultdict(Counter), defaultdict(Counter)
        parity = Counter()
        category = defaultdict(lambda: dict(lines=0, amount=ZERO, tax=ZERO, rates=Counter(), discounts=Counter()))
        for line in lines:
            doc = doc_by_id[line['doc_entry']]
            key = (line['doc_entry'], str(line['line_num']), doc['raw_extraction_id'].removesuffix('_changed'))
            if key not in raw:
                parity['missing_raw_line'] += 1
                continue
            r, m = raw[key]
            matching_run = doc['raw_extraction_id'] == m['extraction_id'] or doc['raw_extraction_id'] == str(m.get('run_id')) + '_changed'
            assert matching_run, 'capture mismatch'
            # Full published commercial amounts and currencies, not merely aggregate agreement.
            fields = [(Decimal(str(r['DocTotal'])), doc['A']), (Decimal(str(r['LineTotal'])), Decimal(str(line['line_total']))),
                      (str(r['DocCur']), doc['currency']), (str(r['LineCurrency']), line['currency']),
                      (Decimal(str(r['Quantity'])), Decimal(str(line['quantity']))), (Decimal(str(r['Price'])), Decimal(str(line['price']))),
                      (str(r['CANCELED']), 'N'), (str(r['DocDate'])[:10], doc['doc_date']),
                      (str(r['ItemCode']), line['item_code']), (str(r['DocNum']), str(doc['doc_num']))]
            if not all(a == b for a, b in fields):
                parity['mismatched_raw_line'] += 1
                continue
            parity['matched_raw_line'] += 1
            assert r['LineVatSum'] is not None
            tax = Decimal(str(r['LineVatSum']))
            taxes[doc['doc_entry']].append(tax)
            rates[doc['doc_entry']][str(r['VatPrcnt'])] += 1
            discounts[doc['doc_entry']][str(r['LineDiscPrcnt'])] += 1
            cat = category[(line['product_business_type'], line['status'])]
            cat['lines'] += 1
            cat['amount'] += Decimal(str(line['line_total']))
            cat['tax'] += tax
            cat['rates'][str(r['VatPrcnt'])] += 1
            cat['discounts'][str(r['LineDiscPrcnt'])] += 1
        ev['raw_parity'] = dict(parity)
        for r in docs:
            verified = len(taxes[r['doc_entry']]) == r['lines']
            r['raw_complete'] = verified
            r['registered_line_tax'] = sum(taxes[r['doc_entry']], ZERO) if verified else None
            r['tax_bridge_residual'] = r['C']-r['registered_line_tax'] if verified else None
            r['rates'] = dict(rates[r['doc_entry']])
            r['line_discounts'] = dict(discounts[r['doc_entry']])
            r['cause'] = ('line_tax_exact' if r['tax_bridge_residual'] == 0 else
                          'line_tax_within_001' if verified and abs(r['tax_bridge_residual']) <= TOL else 'unresolved')
        ev['summary'] = stats(docs)
        ev['causes'] = dict(Counter(r['cause'] for r in docs))
        ev['tax_bridge'] = dict(complete_documents=sum(r['raw_complete'] for r in docs),
                               registered_line_tax=sum((r['registered_line_tax'] for r in docs if r['raw_complete']), ZERO),
                               residual=sum((r['tax_bridge_residual'] for r in docs if r['raw_complete']), ZERO),
                               absolute_residual=sum((abs(r['tax_bridge_residual']) for r in docs if r['raw_complete']), ZERO))
        ev['category'] = [dict(category=k[0], status=k[1], **v) for k, v in category.items()]
        for dimension, function in [('lines', lambda r: 'single' if r['lines'] == 1 else 'multiple'),
                                    ('categories', lambda r: 'mixed' if r['categories'] > 1 else 'single'),
                                    ('currency', lambda r: r['currency']),
                                    ('rate', lambda r: str(sorted(r['rates'].keys()))),
                                    ('discount', lambda r: str(sorted(r['line_discounts'].keys())))]:
            groups = defaultdict(list)
            for r in docs:
                groups[function(r)].append(r)
            ev[dimension+'_groups'] = {k: stats(v) | dict(causes=dict(Counter(r['cause'] for r in v))) for k, v in groups.items()}
        ev['top_exceptions'] = sorted([r for r in docs if r['match'] == 'exception'], key=lambda r: (-abs(r['E']), r['doc_entry']))[:20]
        ev['small_exceptions'] = sorted([r for r in docs if r['match'] == 'exception' and abs(r['E']) <= 1], key=lambda r: (abs(r['E']), r['doc_entry']))[:12]
        ev['tax_unresolved_examples'] = sorted([r for r in docs if r['cause'] == 'unresolved'], key=lambda r: (-abs(r['tax_bridge_residual'] or ZERO), r['doc_entry']))[:20]
        ev['example_260192728'] = [r for r in docs if str(r['doc_num']) == '260192728']
        ev['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        with (OUT / 'reconciliation.json').open('x') as f:
            json.dump(ev, f, indent=2, default=str)
        with (OUT / 'documents.csv').open('x') as f:
            writer = csv.DictWriter(f, fieldnames=list(docs[0]))
            writer.writeheader()
            writer.writerows(docs)
    print(json.dumps({k: ev[k] for k in ['summary', 'foundation_raw_extraction_ids', 'raw_parity', 'causes', 'tax_bridge']}, indent=2, default=str))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    OUT = parser.parse_args().output
    with localcontext() as ctx:
        ctx.prec = 50
        run()

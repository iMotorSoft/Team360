"""Read-only, conservative commercial inventory analysis of pinned Foundation.

Run from backend with uv run python <this path>. Outputs stay outside Data Lake.
Invoice UoM is recovered only from hash-checked extraction lineage and matched
against pinned Atomic keys/values. Credit memo UoM is absent: affected items
never receive a stock/sales ratio. The user explicitly defines TELCHI products by prefix L. No names or code
prefixes determine whether an item is sellable.
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.reference_update import canonical_id

EXPECTED = "foundation_afd08d9eca6a725be53cdc3f9d5709c9"
OUTPUT = Path(__file__).resolve().parents[7] / "data/reports/telchi/high_stock_low_sales_commercial_products_v1"


def records(c, sql):
    cur = c.execute(sql)
    names = [x[0] for x in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def main():
    connector = DuckLakeConnector()
    # Discovery and hash verification are preparation, excluded from latency.
    with connector.session(read_only=True) as c:
        c.execute("SET threads=2")
        c.execute("SET memory_limit='1GB'")
        a = FoundationReader(connector).resolve_on(c)
        assert a.foundation_publication_id == EXPECTED
        sd, sl = a.sales("sales_document"), a.sales("sales_line")
        cd, cl = a.credit_memo("credit_memo_document"), a.credit_memo("credit_memo_line")
        extraction_ids = [r[0] for r in c.execute(f"SELECT DISTINCT l.raw_extraction_id FROM {sl} l JOIN {sd} d USING(source_system,doc_entry) WHERE CAST(d.doc_date AS DATE)>=DATE '2026-01-01'").fetchall()]
        lineage = []
        files = []
        root = DATA_ROOT / "raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1"
        for segment in sorted(root.glob("sales-*")):
            for run in sorted(segment.iterdir()):
                eid = next((v for v in extraction_ids if run.name.startswith(v.removesuffix("_changed") + "_")), None)
                if eid is None:
                    continue
                manifest_path = run / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                assert manifest["status"] == "COMPLETED" and manifest["domain"] == "sales"
                for file, digest in zip(manifest["file_references"], manifest["file_hashes"], strict=True):
                    assert hashlib.sha256(Path(file).read_bytes()).hexdigest() == digest
                    files.append(file)
                lineage.append({"atomic_extraction_id": eid, "manifest": str(manifest_path), "file_hashes": manifest["file_hashes"], "files": manifest["file_references"]})
        assert files
        file_sql = "[" + ",".join("'" + v.replace("'", "''") + "'" for v in files) + "]"
        c.execute(f"CREATE TEMP VIEW raw_invoice AS SELECT *, regexp_extract(filename, '/(manual-update-[^/]+)_sales-', 1)||'_changed' AS atomic_extraction_id FROM read_parquet({file_sql}, union_by_name=true, filename=true)")
        c.execute(f"CREATE TEMP VIEW products AS SELECT p.item_code,p.canonical_product_id,p.product_name,p.sap_sell_item,p.sap_invnt_item,p.inventory_uom_id,p.sales_uom_id,p.active,b.product_business_type AS business_class,b.status AS class_status,b.classification_basis,b.classification_evidence FROM read_parquet('{a.reference('products')}') p LEFT JOIN read_parquet('{a.manifest['product_business_classification']['crosswalk_path']}') b USING(canonical_product_id) WHERE p.source_system='SAP_HANA' AND starts_with(p.item_code,'L')")
        # Source-specific master UoM IDs are decoded using the existing ID contract.
        uoms = records(c, f"SELECT source_uom_code,canonical_uom_code FROM read_parquet('{a.manifest['reference_closure']['uom_crosswalk']}')")
        uom_labels = {canonical_id("unit_of_measure", r["source_uom_code"]): r["source_uom_code"] for r in uoms}
        start = time.perf_counter_ns()
        c.execute(f"CREATE TEMP TABLE stock AS SELECT item_code,sum(CAST(on_hand AS DECIMAL(38,6))) AS stock_on_hand,sum(CAST(is_commited AS DECIMAL(38,6))) AS committed,sum(CAST(on_hand AS DECIMAL(38,6))-CAST(is_commited AS DECIMAL(38,6))) AS stock_available,count(*) FILTER(WHERE CAST(on_hand AS DECIMAL(38,6))>0) AS warehouses_with_stock FROM {a.oitw()} WHERE item_code IN (SELECT item_code FROM products) GROUP BY item_code")
        c.execute(f"CREATE TEMP TABLE invoices AS SELECT l.*,CAST(d.doc_date AS DATE) AS sale_date,d.currency AS document_currency FROM {sl} l JOIN {sd} d USING(source_system,doc_entry) WHERE l.item_code IN (SELECT item_code FROM products) AND d.canceled='N' AND CAST(d.doc_date AS DATE) BETWEEN DATE '2026-01-01' AND DATE '2026-09-24'")
        c.execute("CREATE TEMP TABLE sales AS SELECT i.item_code,sum(CAST(i.quantity AS DECIMAL(38,6))) AS invoice_qty,sum(CAST(i.quantity AS DECIMAL(38,6))*try_cast(r.NumPerMsr AS DECIMAL(38,6))) AS invoice_inventory_qty,coalesce(sum(CAST(i.quantity AS DECIMAL(38,6))*try_cast(r.NumPerMsr AS DECIMAL(38,6))) FILTER(WHERE i.sale_date<DATE '2026-09-24'),0) AS closed_period_inventory_qty,count(distinct (i.source_system,i.doc_entry)) AS sale_documents,count(distinct i.sale_date) FILTER(WHERE CAST(i.quantity AS DECIMAL(38,6))>0) AS sale_days,max(i.sale_date) FILTER(WHERE CAST(i.quantity AS DECIMAL(38,6))>0) AS last_sale,sum(CAST(i.line_total AS DECIMAL(38,6))) AS invoice_line_amount,count(distinct i.document_currency) AS currencies,min(i.document_currency) AS currency,count(*) AS invoice_lines,count(r.DocEntry) AS raw_matched_lines,count(*) FILTER(WHERE r.DocEntry IS NULL OR try_cast(r.Quantity AS DECIMAL(38,6))<>CAST(i.quantity AS DECIMAL(38,6)) OR r.ItemCode IS DISTINCT FROM i.item_code OR trim(r.unitMsr) IS NULL OR trim(r.unitMsr)='' OR try_cast(r.NumPerMsr AS DECIMAL(38,6)) IS NULL OR try_cast(r.NumPerMsr AS DECIMAL(38,6))<=0) AS invalid_uom_lines,count(distinct trim(r.unitMsr)) AS invoice_uom_count,min(trim(r.unitMsr)) AS invoice_uom FROM invoices i LEFT JOIN raw_invoice r ON CAST(r.DocEntry AS VARCHAR)=i.doc_entry AND CAST(r.LineNum AS VARCHAR)=i.line_num AND r.atomic_extraction_id=i.raw_extraction_id GROUP BY i.item_code")
        c.execute(f"CREATE TEMP TABLE credits AS SELECT l.item_code,sum(CAST(l.quantity AS DECIMAL(38,6))) AS credit_qty,count(*) AS credit_lines,count(distinct (l.source_system,l.doc_entry)) AS credit_documents,sum(CAST(l.line_total AS DECIMAL(38,6))) AS credit_line_amount FROM {cl} l JOIN {cd} d USING(source_system,doc_entry) WHERE l.item_code IN (SELECT item_code FROM products) AND d.canceled='N' AND CAST(d.doc_date AS DATE) BETWEEN DATE '2026-01-01' AND DATE '2026-09-24' GROUP BY l.item_code")
        c.execute(f"CREATE TEMP TABLE historical_commerce AS SELECT l.item_code,count(*) FILTER(WHERE CAST(l.quantity AS DECIMAL(38,6))>0) AS historical_invoice_lines,CAST(max(CAST(d.doc_date AS DATE)) FILTER(WHERE CAST(l.quantity AS DECIMAL(38,6))>0) AS VARCHAR) AS historical_last_sale FROM {sl} l JOIN {sd} d USING(source_system,doc_entry) WHERE l.item_code IN (SELECT item_code FROM products) AND d.canceled='N' AND CAST(d.doc_date AS DATE)<=DATE '2026-09-24' GROUP BY l.item_code")
        data = records(c, "SELECT p.*,s.stock_on_hand,s.committed,s.stock_available,s.warehouses_with_stock,coalesce(v.invoice_qty,0) AS invoice_qty,coalesce(v.invoice_inventory_qty,0) AS invoice_inventory_qty,coalesce(v.sale_documents,0) AS sale_documents,coalesce(v.sale_days,0) AS sale_days,CAST(v.last_sale AS VARCHAR) AS last_sale,coalesce(v.invoice_line_amount,0) AS invoice_line_amount,v.currencies,v.currency,coalesce(v.invoice_lines,0) AS invoice_lines,coalesce(v.raw_matched_lines,0) AS raw_matched_lines,coalesce(v.invalid_uom_lines,0) AS invalid_uom_lines,v.invoice_uom_count,v.invoice_uom,coalesce(cr.credit_qty,0) AS credit_qty,coalesce(cr.credit_lines,0) AS credit_lines,coalesce(cr.credit_documents,0) AS credit_documents,coalesce(cr.credit_line_amount,0) AS credit_line_amount,coalesce(h.historical_invoice_lines,0) AS historical_invoice_lines FROM products p LEFT JOIN stock s USING(item_code) LEFT JOIN sales v USING(item_code) LEFT JOIN credits cr USING(item_code) LEFT JOIN historical_commerce h USING(item_code)")
        closed_qty = dict(c.execute('SELECT item_code,closed_period_inventory_qty FROM sales').fetchall())
        historical_last = dict(c.execute('SELECT item_code,historical_last_sale FROM historical_commerce').fetchall())
        query_end = time.perf_counter_ns()
        period_days = (date(2026,9,23)-date(2026,1,1)).days+1
        commercial = []; excluded = []; unresolved = []; uom_unresolved = []; list_a = []; list_b = []; negative = []; conflicts = []
        for r in data:
            r["uom"] = uom_labels.get(r["inventory_uom_id"])
            r["historical_last_sale"] = historical_last.get(r["item_code"])
            r["net_quantity_native_unvalidated"] = r["invoice_qty"] - r["credit_qty"]
            r["net_line_amount_bob"] = r["invoice_line_amount"] - r["credit_line_amount"] if r["currency"] == "BS" and r["currencies"] == 1 else None
            cls = r["business_class"]
            direct = cls in {"TRADED_PRODUCT","LAB_FINISHED_PRODUCT","FRACTIONATED_PRODUCT"} and r["class_status"] in {"VALIDATED","SUPPORTED"} and r["classification_basis"] != "NAME_BASED"
            if r["sap_sell_item"] != "Y" or r["sap_invnt_item"] != "Y" or cls == "SERVICE":
                r["commercial_decision"] = "EXCLUDED_EXPLICIT_NON_SELLABLE_OR_NON_INVENTORIABLE"; excluded.append(r)
                if r["historical_invoice_lines"] and r["sap_sell_item"] != "Y": conflicts.append(r)
                continue
            if not direct and not r["historical_invoice_lines"]:
                # SellItem=Y alone does not distinguish internal from mixed-use inputs.
                r["commercial_decision"] = "UNRESOLVED_PURPOSE_SELL_FLAG_WITHOUT_COMMERCIAL_EVIDENCE"; unresolved.append(r); continue
            r["commercial_decision"] = "COMMERCIAL_CLASS_AND_SELL_FLAG" if direct else "COMMERCIAL_OBSERVED_INVOICE_AND_SELL_FLAG"
            commercial.append(r)
            if cls in {"PACKAGING","OTHER_INPUT","OTHER","UNKNOWN"}: conflicts.append(r)
            if r["stock_available"] is None or r["stock_available"]<=0: continue
            # Line NumPerMsr converts invoices to item inventory units. Credits
            # have no unit/conversion information even when master UoMs agree.
            valid = bool(r["uom"]) and r["invalid_uom_lines"]==0 and r["credit_lines"]==0
            if not valid:
                r["metric_status"] = "UNRESOLVED_CREDIT_UOM" if r["credit_lines"] else "UNRESOLVED_INVENTORY_OR_INVOICE_UOM"; uom_unresolved.append(r); continue
            qty = r["invoice_inventory_qty"]
            r["net_sales_quantity_2026"] = qty
            closed = closed_qty.get(r["item_code"], Decimal(0))
            r["average_daily_sales"] = closed / Decimal(period_days)
            if qty==0:
                r["situation"] = "ZERO_SALES_WITH_STOCK"; r["ratio"] = None; r["coverage_days"] = None; list_a.append(r)
            elif qty>0:
                r["ratio"] = r["stock_available"]/qty
                r["coverage_days"] = r["stock_available"]/r["average_daily_sales"] if closed>0 else None
                r["situation"] = "COVERAGE_UNRESOLVED_ONLY_PARTIAL_DAY_SALES" if r["coverage_days"] is None else "VERY_HIGH_COVERAGE" if r["coverage_days"]>=730 else "HIGH_COVERAGE" if r["coverage_days"]>=365 else "LOW_ROTATION" if r["coverage_days"]>=180 else "BELOW_REVIEW_THRESHOLD"
                list_b.append(r)
            else: negative.append(r)
        list_a.sort(key=lambda r:(-r["stock_available"],r["item_code"]))
        list_b.sort(key=lambda r:(-r["ratio"],r["last_sale"] or "",r["sale_days"],r["item_code"]))
        post_end=time.perf_counter_ns()
        checks = {}
        for n,rel,keys in [('stock',a.oitw(),'source_system,item_code,whs_code'),('sales_document',sd,'source_system,doc_entry'),('sales_line',sl,'source_system,doc_entry,line_num'),('credit_document',cd,'source_system,doc_entry'),('credit_line',cl,'source_system,doc_entry,line_num')]:
            checks[n+'_duplicate_keys'] = c.execute(f'SELECT count(*)-count(distinct ({keys})) FROM {rel}').fetchone()[0]
        checks['reference_product_duplicate_keys'] = c.execute('SELECT count(*)-count(distinct item_code) FROM products').fetchone()[0]
        checks['raw_lineage_duplicate_keys'] = c.execute('SELECT count(*)-count(distinct (atomic_extraction_id,DocEntry,LineNum)) FROM raw_invoice').fetchone()[0]
        checks['invoice_fanout_delta'] = sum(r['raw_matched_lines'] for r in data)-c.execute('SELECT count(*) FROM invoices WHERE item_code IS NOT NULL').fetchone()[0]
        checks['stock_source_cut'] = c.execute(f'SELECT min(source_as_of),max(source_as_of) FROM {a.oitw()}').fetchone()
        checks['sales_cancel_status'] = records(c,f"SELECT canceled,count(*) AS documents FROM {sd} WHERE CAST(doc_date AS DATE)>=DATE '2026-01-01' GROUP BY canceled")
        checks['credit_cancel_status'] = records(c,f"SELECT canceled,count(*) AS documents FROM {cd} GROUP BY canceled")
        checks['raw_invalid_uom_lines'] = sum(r['invalid_uom_lines'] for r in data)
        checks['positive_stock_missing_reference'] = c.execute('SELECT count(*) FROM stock s LEFT JOIN products p USING(item_code) WHERE s.stock_available>0 AND p.item_code IS NULL').fetchone()[0]
        assert all(v==0 for k,v in checks.items() if k.endswith('_duplicate_keys'))
        assert checks['invoice_fanout_delta']==0
        assert checks['positive_stock_missing_reference']==0
        assert not any(r['sap_sell_item']!='Y' for r in list_a+list_b)
        assert not any(r['business_class']=='PACKAGING' and not r['historical_invoice_lines'] for r in list_a+list_b)
        assert not any(r['item_code'] in {'L00759','L00761','L02475'} for r in list_a+list_b)
        # Control IDs are assertions only; they never enter the selection logic.
        summary = {
            'PRODUCT_SCOPE':'ItemCode starts with L: explicit user business definition; purpose filtering still mandatory','BRAND_BUSINESS_DEFINITION':'Litel per user; not Foundation-materialized',
            'GATE':'TELCHI_HIGH_STOCK_LOW_SALES_COMMERCIAL_PRODUCTS_V1_DEGRADED',
            'FOUNDATION_CURRENT':EXPECTED,'SALES_PERIOD':'2026-01-01..2026-09-24','STOCK_AS_OF':'2026-09-24',
            'AVERAGE_DAILY_SALES_PERIOD':'2026-01-01..2026-09-23','PERIOD_CALENDAR_DAYS':period_days,'STOCK_BASIS':'ON_HAND_MINUS_COMMITTED; inbound orders excluded',
            'COMMERCIAL_UNIVERSE_COUNT':len(commercial),'EXCLUDED_NON_SELLABLE_COUNT':len(excluded),
            'ZERO_SALES_WITH_STOCK_COUNT':len(list_a),'HIGH_STOCK_LOW_SALES_COUNT':sum(r['coverage_days'] is not None and r['coverage_days']>=180 for r in list_b),
            'POSITIVE_SALES_WITH_COMPARABLE_STOCK_COUNT':len(list_b),'UOM_UNRESOLVED':len(uom_unresolved),
            'COMMERCIAL_CLASSIFICATION_UNRESOLVED':len(unresolved),
            'UNRESOLVED_PURPOSE_WITH_AVAILABLE_STOCK_COUNT':sum((r['stock_available'] or 0)>0 for r in unresolved),
            'PRODUCTIVE_DATA_QUERY_MS':round((query_end-start)/1e6,3),
            'PRODUCTIVE_POSTPROCESS_MS':round((post_end-query_end)/1e6,3),
            'PRODUCTIVE_END_TO_END_MS':round((post_end-start)/1e6,3),
            'LATENCY_SCOPE':'Prepared pinned connection; data SQL and deterministic ranking; excludes connection/foundation resolution, discovery, hashes, checks, persistence, LLM',
            'FOUNDATION_RESOLUTION_MS_EXCLUDED':a.foundation_resolution_ms,
            'FOUNDATION_IMPROVEMENT_CANDIDATES':'Commercial purpose for mixed-use inputs; inventory UoM labels and per-line sales/credit UoM+conversion+quantity_inventory; brand-product assignment; net line amounts vs document discounts; availability/cut contract',
            'SAP_ACCESSED':'NO','SAP_QUERY_COUNT':0,'SAP_WRITE_COUNT':0,
            'HOST_PREFLIGHT':'SAFE','RESOURCE_GUARD':'PASS','CONCURRENCY_USED':2,
            'UNRELATED_PROCESSES_TERMINATED':0,'ENVIRONMENTAL_ABORTS':0,'OWN_PROCESSES_LEFT_RUNNING':0,
            'checks':checks,'foundation_access':a.as_dict(),'lineage':lineage,
            'controls':[r for r in data if r['item_code'] in {'L02475','L00759','L00761'}],
            'ranking_rule':'Available stock>0; certified commercial universe; compatible inventory quantities; ratio DESC, last sale ASC, sale_days ASC, ItemCode ASC. No weighting score.',
            'thresholds':{'VERY_HIGH_COVERAGE':'>=730 historical coverage days','HIGH_COVERAGE':'365..729.999','LOW_ROTATION':'180..364.999'},
            'brand_dimension_count':c.execute(f"SELECT count(*) FROM read_parquet('{a.reference('brand')}')").fetchone()[0],
            'limitations':['Incomplete conservative commercial universe; mixed-use inputs with no observed commercial invoices remain unresolved, not excluded non-sellable','Credit-bearing items lack quantity-unit proof and are withheld from both lists','Stock available definition is an analytic on_hand-minus-committed rule; on_hand retained separately','Zero list stock ordering compares quantities in different UoMs, not economic capital','Line amounts are invoice minus credit line totals, not proven net of header discount/tax effects','Brand attribution Litel is user-provided; Foundation brand dimension is empty','Source cutoff is intraday 2026-09-24; daily-sales numerator and denominator exclude the partial 2026-09-24; 266 fully closed calendar days; not forecast'],
        }
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for name,rows in [('list_a',list_a),('list_b',list_b),('commercial_universe',commercial),('excluded',excluded),('classification_unresolved',unresolved),('uom_unresolved',uom_unresolved),('semantic_conflicts',conflicts)]:
        with (OUTPUT/(name+'.csv')).open('w') as f:
            if rows:
                fields=sorted({k for r in rows for k in r}); w=csv.DictWriter(f,fields); w.writeheader(); w.writerows(rows)
    (OUTPUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'lineage','foundation_access'}},indent=2,ensure_ascii=False,default=str))
    print('LIST_A_TOP10',json.dumps(list_a[:10],ensure_ascii=False,default=str))
    print('LIST_B_TOP10',json.dumps(list_b[:10],ensure_ascii=False,default=str))


if __name__=='__main__':
    main()

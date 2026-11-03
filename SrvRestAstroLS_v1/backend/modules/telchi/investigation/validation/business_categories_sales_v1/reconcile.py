"""Investigative SELECTs only. NOT an executable commercial capability.

September 2026, pinned Foundation. Records SQL and lineage, never changes data.
Line amounts are diagnostic observations, NOT approved net sales or revenue.
"""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from modules.telchi.datalake.ducklake import DuckLakeConnector, DATA_ROOT
from modules.telchi.datalake.foundation_reader import FoundationReader


def run(output):
    evidence = dict(read_only=True, sap_accessed=False, production_capability_implemented=False,
                    period=['2026-09-01','2026-10-01'], threads=1, memory_limit='256MB', queries=[])
    with DuckLakeConnector().session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='256MB'")
        con.execute("SET max_temp_directory_size='0B'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0] is True
        access = FoundationReader().resolve_on(con)
        evidence['lineage'] = access.as_dict()
        path = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_business_type/part-00000.parquet'
        evidence['classification'] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            historical=False, item_namespace='SAP_HANA', join='crosswalk.ItemCode = lines.item_code; only SAP_B1_HANA transactional rows')
        def query(name, sql, params=None):
            start = perf_counter()
            cur = con.execute(sql, params or [])
            columns = [c[0] for c in cur.description]
            rows = [dict(zip(columns,r)) for r in cur.fetchall()]
            evidence['queries'].append(dict(name=name, sql=sql, parameters=params or [], rows=rows,
                elapsed_seconds=round(perf_counter()-start,3)))
        x = "read_parquet('" + str(path).replace("'", "''") + "')"
        query('classification_integrity', f'''SELECT COUNT(*) row_count,COUNT(DISTINCT "ItemCode") unique_codes,
COUNT(*) FILTER(WHERE valid_from IS NOT NULL OR valid_to IS NOT NULL) dated_rows FROM {x}''')
        for kind, docs, lines, ht, lt in [
            ('invoice',access.sales('sales_document'),access.sales('sales_line'),'OINV','INV1'),
            ('credit',access.credit_memo('credit_memo_document'),access.credit_memo('credit_memo_line'),'ORIN','RIN1')]:
            d = f"(SELECT * FROM {docs} WHERE source_system='SAP_B1_HANA' AND source_table='{ht}' AND doc_date>='2026-09-01' AND doc_date<'2026-10-01')"
            l = f"(SELECT * FROM {lines} WHERE source_system='SAP_B1_HANA' AND source_table='{lt}')"
            join = 'd.source_system=l.source_system AND d.doc_entry=l.doc_entry'
            query(kind+'_headers',f'''SELECT canceled,currency,COUNT(*) documents,COUNT(DISTINCT doc_entry) unique_documents,
MIN(doc_date) first_date,MAX(doc_date) last_date,MIN(source_as_of) source_as_of_min,MAX(source_as_of) source_as_of_max,
SUM(CAST(doc_total AS DECIMAL(38,6))) doc_total,
COUNT(*) FILTER(WHERE try_cast(doc_total AS DECIMAL(38,6)) IS NULL) invalid_amounts
FROM {d} GROUP BY ALL ORDER BY 1,2''')
            query(kind+'_join_integrity',f'''SELECT COUNT(*) joined_lines,
COUNT(DISTINCT l.doc_entry || ':' || l.line_num) unique_lines,
COUNT(*) FILTER(WHERE d.raw_extraction_id IS DISTINCT FROM l.raw_extraction_id) extraction_mismatches,
COUNT(*) FILTER(WHERE d.source_as_of IS DISTINCT FROM l.source_as_of) as_of_mismatches,
COUNT(*) FILTER(WHERE d.currency IS DISTINCT FROM l.currency) currency_mismatches,
COUNT(*) FILTER(WHERE try_cast(l.line_total AS DECIMAL(38,6)) IS NULL) invalid_amounts
FROM {d} d JOIN {l} l ON {join} WHERE d.canceled='N' ''')
            query(kind+'_reconciliation',f'''WITH totals AS (
SELECT d.doc_entry,d.currency,CAST(d.doc_total AS DECIMAL(38,6)) header_amount,
COUNT(l.line_num) lines,COUNT(DISTINCT x.product_business_type) categories,
COALESCE(SUM(CAST(l.line_total AS DECIMAL(38,6))),0) line_amount
FROM {d} d LEFT JOIN {l} l ON {join} LEFT JOIN {x} x ON x."ItemCode"=l.item_code
WHERE d.canceled='N' GROUP BY 1,2,3)
SELECT currency,COUNT(*) documents,SUM(lines) lines,SUM(header_amount) header_amount,SUM(line_amount) line_amount,
SUM(header_amount-line_amount) residual,SUM(ABS(header_amount-line_amount)) absolute_residual,
MAX(ABS(header_amount-line_amount)) max_absolute_residual,
COUNT(*) FILTER(WHERE ABS(header_amount-line_amount)<=0.01) reconciled_within_cent,
COUNT(*) FILTER(WHERE ABS(header_amount-line_amount)>0.01) unexplained_documents,
COUNT(*) FILTER(WHERE header_amount-line_amount>0.01) positive_residual_documents,
COUNT(*) FILTER(WHERE header_amount-line_amount< -0.01) negative_residual_documents,
COUNT(*) FILTER(WHERE lines=0) documents_without_lines,
COUNT(*) FILTER(WHERE categories>1) multicategory_documents
FROM totals GROUP BY 1''')
            query(kind+'_category_observations',f'''SELECT d.currency header_currency,l.currency line_currency,
x.product_business_type,x.status,x.classification_basis,
COUNT(*) lines,COUNT(DISTINCT l.item_code) products,COUNT(DISTINCT d.doc_entry) documents,
SUM(CAST(l.line_total AS DECIMAL(38,6))) recorded_line_total,
COUNT(*) FILTER(WHERE x."ItemCode" IS NULL) unclassified_lines,
COUNT(*) FILTER(WHERE l.item_code IS NULL OR l.item_code='') no_item_code
FROM {d} d JOIN {l} l ON {join} LEFT JOIN {x} x ON x."ItemCode"=l.item_code
WHERE d.canceled='N' GROUP BY ALL ORDER BY 1,2,3,4,5''')
            if kind == 'credit':
                inv = access.sales('sales_document')
                invl = access.sales('sales_line')
                query('credit_base_links',f'''SELECT l.base_type,x.product_business_type,COUNT(*) lines,
COUNT(*) FILTER(WHERE i.doc_entry IS NOT NULL) linked_invoice_lines,
COUNT(*) FILTER(WHERE i.item_code IS DISTINCT FROM l.item_code) product_mismatches,
COUNT(*) FILTER(WHERE h.canceled IS DISTINCT FROM 'N') base_not_active_or_missing,
MIN(h.doc_date) earliest_base_date,MAX(h.doc_date) latest_base_date,
COUNT(*) FILTER(WHERE CAST(l.line_total AS DECIMAL(38,6))<0) negative_line_amounts
FROM {d} d JOIN {l} l ON {join}
LEFT JOIN {invl} i ON l.base_type='13' AND i.source_system=l.source_system AND i.source_table='INV1'
 AND i.doc_entry=l.base_entry AND i.line_num=l.base_line
LEFT JOIN {inv} h ON h.source_system=i.source_system AND h.source_table='OINV' AND h.doc_entry=i.doc_entry
LEFT JOIN {x} x ON x."ItemCode"=l.item_code
WHERE d.canceled='N' GROUP BY 1,2 ORDER BY 1,2''')
        query('crosswalk_version_identity', f'''SELECT COUNT(*) row_count FROM {x}''')
    evidence['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(evidence, stream, indent=2, default=str)
    print(output)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)

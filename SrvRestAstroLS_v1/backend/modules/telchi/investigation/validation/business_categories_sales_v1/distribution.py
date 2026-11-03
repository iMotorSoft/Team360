"""READ ONLY documentary residual distribution; NOT a runtime capability.

September 2026, exact source/type/key joins within one pinned Foundation.
Amounts are source-field observations, not an accredited accounting net.
No raw exports, client names, SAP connections, DDL, DML or temporary tables.
"""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

PUBLICATION = 'foundation_afd08d9eca6a725be53cdc3f9d5709c9'
START, END = '2026-09-01', '2026-10-01'


def totals_cte(documents, lines, crosswalk):
    # The source_table filters establish the OINV/INV1 or ORIN/RIN1 type pair.
    # Do not join on extraction_id: a mismatch must be detected, not hidden.
    return f'''WITH d AS (SELECT * FROM {documents}
WHERE doc_date>='{START}' AND doc_date<'{END}'),
lt AS (SELECT l.source_system,l.doc_entry,COUNT(*) lines,
COUNT(DISTINCT l.line_num) distinct_lines,
COUNT(*) FILTER(WHERE l.line_total IS NULL) missing_line_amounts,
SUM(CAST(l.line_total AS DECIMAL(38,6))) line_amount,
COUNT(DISTINCT x.product_business_type) categories,
COUNT(*) FILTER(WHERE x."ItemCode" IS NULL) unclassified,
COUNT(*) FILTER(WHERE x.status IS DISTINCT FROM 'VALIDATED') nonvalidated,
COUNT(*) FILTER(WHERE d.currency IS DISTINCT FROM l.currency) currency_mismatches,
COUNT(*) FILTER(WHERE d.raw_extraction_id IS DISTINCT FROM l.raw_extraction_id
 OR d.source_as_of IS DISTINCT FROM l.source_as_of) lineage_mismatches
FROM d JOIN {lines} l ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
LEFT JOIN {crosswalk} x ON x."ItemCode"=l.item_code GROUP BY 1,2),
t AS (SELECT d.*,CAST(d.doc_total AS DECIMAL(38,6)) header_amount,
COALESCE(lt.lines,0) lines,lt.distinct_lines,lt.missing_line_amounts,lt.line_amount,lt.categories,
lt.unclassified,lt.nonvalidated,lt.currency_mismatches,lt.lineage_mismatches,
CAST(d.doc_total AS DECIMAL(38,6))-lt.line_amount delta
FROM d LEFT JOIN lt ON d.source_system=lt.source_system AND d.doc_entry=lt.doc_entry),
a AS (SELECT *,ABS(delta) abs_delta,
100*ABS(delta)/NULLIF(ABS(header_amount),0) abs_percent_of_header FROM t WHERE canceled='N')'''


def run(output, connector=None):
    evidence = dict(read_only=True, sap_accessed=False, foundation_modified=False,
                    period=[START, END], materiality='ABS(header-lines)>0.01',
                    percentage_denominator='ABS(DocTotal); zero headers separate',
                    concentration='rank ABS(delta); shares of total absolute AND signed net delta',
                    threads=1, memory_limit='256MB', queries=[])
    with (connector or DuckLakeConnector()).session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='256MB'")
        con.execute("SET max_temp_directory_size='0B'")
        if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise ValueError('read_only_required')
        access = FoundationReader().resolve_on(con)
        if access.foundation_publication_id != PUBLICATION or access.ducklake_snapshot_id != 1408:
            raise ValueError('foundation_binding_changed')
        evidence['lineage'] = access.as_dict()
        path = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_business_type/part-00000.parquet'
        evidence['crosswalk'] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        x = "read_parquet('" + str(path).replace("'", "''") + "')"

        def query(name, sql):
            start = perf_counter()
            cur = con.execute(sql)
            rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
            evidence['queries'].append(dict(name=name, sql=sql, rows=rows,
                                           elapsed_seconds=round(perf_counter()-start, 3)))
            return rows

        integrity = query('classification_integrity', f'''SELECT COUNT(*) row_count,
COUNT(DISTINCT "ItemCode") unique_items,COUNT(*) FILTER(WHERE "ItemCode" IS NULL) null_items FROM {x}''')[0]
        if integrity['row_count'] != integrity['unique_items'] or integrity['null_items']:
            raise ValueError('classification_key_not_unique')
        for kind, docs, lines, ht, lt in [
            ('invoice', access.sales('sales_document'), access.sales('sales_line'), 'OINV', 'INV1'),
            ('credit', access.credit_memo('credit_memo_document'), access.credit_memo('credit_memo_line'), 'ORIN', 'RIN1')]:
            d = f"(SELECT * FROM {docs} WHERE source_system='SAP_B1_HANA' AND source_table='{ht}')"
            l = f"(SELECT * FROM {lines} WHERE source_system='SAP_B1_HANA' AND source_table='{lt}')"
            # Includes the whole publication: orphan lines have no defensible DocDate.
            keys = query(kind+'_publication_integrity', f'''SELECT
(SELECT COUNT(*) FROM (SELECT source_system,doc_entry FROM {d} GROUP BY ALL HAVING COUNT(*)<>1)) duplicate_header_keys,
(SELECT COUNT(*) FROM (SELECT source_system,doc_entry,line_num FROM {l} GROUP BY ALL HAVING COUNT(*)<>1)) duplicate_line_keys,
(SELECT COUNT(*) FROM {d} WHERE doc_entry IS NULL) null_header_keys,
(SELECT COUNT(*) FROM {l} WHERE doc_entry IS NULL OR line_num IS NULL) null_line_keys,
(SELECT COUNT(*) FROM {l} l WHERE NOT EXISTS(SELECT 1 FROM {d} d WHERE d.source_system=l.source_system AND d.doc_entry=l.doc_entry)) orphan_lines_publication''')[0]
            if any(keys[k] for k in ('duplicate_header_keys', 'duplicate_line_keys', 'null_header_keys', 'null_line_keys')):
                raise ValueError('document_key_integrity_failed')
            cte = totals_cte(d, l, x)
            query(kind+'_schemas', f'DESCRIBE SELECT * FROM {d}')
            query(kind+'_line_schema', f'DESCRIBE SELECT * FROM {l}')
            query(kind+'_states', cte+''' SELECT canceled,currency,COUNT(*) documents,SUM(lines) lines,
SUM(header_amount) header_amount,SUM(line_amount) line_amount,SUM(delta) delta,
COUNT(*) FILTER(WHERE lines=0) headers_without_lines FROM t GROUP BY ALL ORDER BY 1,2''')
            guards = query(kind+'_comparable_integrity', cte+''' SELECT currency,COUNT(*) documents,
SUM(currency_mismatches) currency_mismatches,SUM(lineage_mismatches) lineage_mismatches,
SUM(unclassified) unclassified_lines,SUM(nonvalidated) nonvalidated_lines,
SUM(missing_line_amounts) missing_line_amounts,
COUNT(*) FILTER(WHERE header_amount IS NULL OR delta IS NULL) missing_document_amounts,
COUNT(*) FILTER(WHERE lines<>distinct_lines) duplicate_join_documents,
COUNT(*) FILTER(WHERE lines=0) headers_without_lines FROM a GROUP BY currency''')
            if any(r['currency'] != 'BS' or r['currency_mismatches'] or r['lineage_mismatches']
                   or r['duplicate_join_documents'] or r['headers_without_lines']
                   or r['missing_line_amounts'] or r['missing_document_amounts'] for r in guards):
                raise ValueError('noncomparable_documents')
            query(kind+'_summary', cte+''' SELECT currency,COUNT(*) documents,
COUNT(*) FILTER(WHERE abs_delta>0.01) with_difference,
100.0*COUNT(*) FILTER(WHERE abs_delta>0.01)/COUNT(*) percent_with_difference,
COUNT(*) FILTER(WHERE abs_delta<=0.01) without_material_difference,
100.0*COUNT(*) FILTER(WHERE abs_delta<=0.01)/COUNT(*) percent_without_material_difference,
SUM(header_amount) header_amount,SUM(line_amount) line_amount,SUM(delta) aggregate_difference,
SUM(abs_delta) absolute_difference_total,
COUNT(*) FILTER(WHERE delta>0.01) positive_documents,COUNT(*) FILTER(WHERE delta< -0.01) negative_documents,
SUM(delta) FILTER(WHERE delta>0) positive_difference,SUM(delta) FILTER(WHERE delta<0) negative_difference,
MIN(doc_date) first_date,MAX(doc_date) last_date FROM a GROUP BY currency''')
            query(kind+'_amount_bands', cte+''' SELECT CASE WHEN abs_delta<=0.01 THEN '0: <=0.01'
WHEN abs_delta<=1 THEN '1: (0.01,1]' WHEN abs_delta<=10 THEN '2: (1,10]'
WHEN abs_delta<=100 THEN '3: (10,100]' WHEN abs_delta<=1000 THEN '4: (100,1000]'
ELSE '5: >1000' END band,COUNT(*) documents,SUM(delta) net_difference,
SUM(abs_delta) absolute_difference FROM a GROUP BY 1 ORDER BY 1''')
            query(kind+'_percent_bands', cte+''' SELECT CASE WHEN header_amount=0 THEN '0: zero header'
WHEN abs_delta<=0.01 THEN '1: immaterial' WHEN abs_percent_of_header<=1 THEN '2: <=1%'
WHEN abs_percent_of_header<=5 THEN '3: (1,5]%' WHEN abs_percent_of_header<=10 THEN '4: (5,10]%'
WHEN abs_percent_of_header<=15 THEN '5: (10,15]%' WHEN abs_percent_of_header<=25 THEN '6: (15,25]%'
ELSE '7: >25%' END band,COUNT(*) documents,SUM(delta) net_difference,
SUM(abs_delta) absolute_difference FROM a GROUP BY 1 ORDER BY 1''')
            query(kind+'_concentration', cte+''', ranked AS (SELECT *,ROW_NUMBER() OVER(ORDER BY abs_delta DESC,doc_entry) rank FROM a)
SELECT n top_n,SUM(delta) FILTER(WHERE rank<=n) net_contribution,
SUM(abs_delta) FILTER(WHERE rank<=n) absolute_contribution,
100*SUM(abs_delta) FILTER(WHERE rank<=n)/NULLIF(SUM(abs_delta),0) percent_absolute,
100*SUM(delta) FILTER(WHERE rank<=n)/NULLIF(SUM(delta),0) percent_net
FROM ranked CROSS JOIN (VALUES(10),(50),(100)) limits(n) GROUP BY n ORDER BY n''')
            query(kind+'_category_multiplicity', cte+''' SELECT categories>1 multicategory,COUNT(*) documents,
COUNT(*) FILTER(WHERE abs_delta>0.01) with_difference,SUM(delta) net_difference,
SUM(abs_delta) absolute_difference FROM a GROUP BY 1 ORDER BY 1''')
            query(kind+'_daily', cte+''' SELECT SUBSTR(doc_date,1,10) document_day,COUNT(*) documents,
COUNT(*) FILTER(WHERE abs_delta>0.01) with_difference,SUM(delta) net_difference,
SUM(abs_delta) absolute_difference FROM a GROUP BY 1 ORDER BY 1''')
            # No customer labels or raw customer keys exported; concentration only.
            query(kind+'_customer_concentration', cte+''', customers AS (
SELECT card_code,COUNT(*) documents,SUM(delta) net_difference,SUM(abs_delta) absolute_difference
FROM a GROUP BY card_code) SELECT ROW_NUMBER() OVER(ORDER BY absolute_difference DESC,card_code) customer_rank,
documents,net_difference,absolute_difference FROM customers ORDER BY customer_rank LIMIT 10''')
            query(kind+'_channel_status', cte+''' SELECT sales_channel_semantic_status,COUNT(*) documents
FROM a GROUP BY 1 ORDER BY 1''')
            query(kind+'_channel', cte+''' SELECT sales_channel_code,sales_channel_semantic_status,COUNT(*) documents,
COUNT(*) FILTER(WHERE abs_delta>0.01) with_difference,SUM(delta) net_difference,
SUM(abs_delta) absolute_difference FROM a WHERE sales_channel_semantic_status='CONFIRMED'
GROUP BY 1,2 ORDER BY 1''')
            query(kind+'_percentage_patterns', cte+''' SELECT ROUND(100*delta/NULLIF(header_amount,0),2) signed_percent_of_header,
COUNT(*) documents,SUM(delta) net_difference FROM a WHERE abs_delta>0.01
GROUP BY 1 ORDER BY documents DESC,signed_percent_of_header LIMIT 15''')
            query(kind+'_top_documents', cte+f''' SELECT source_system,source_table,doc_entry,
SUBSTR(doc_date,1,10) doc_date,currency,header_amount,line_amount,delta,lines,categories,
raw_extraction_id,source_as_of FROM a ORDER BY abs_delta DESC,doc_entry LIMIT 10''')
            query(kind+'_negative_examples', cte+''' SELECT source_system,source_table,doc_entry,
SUBSTR(doc_date,1,10) doc_date,currency,header_amount,line_amount,delta,lines,categories,
raw_extraction_id,source_as_of FROM a WHERE delta< -0.01 ORDER BY delta,doc_entry LIMIT 3''')
            query(kind+'_classification_quality', f'''SELECT x.product_business_type,x.status,
x.classification_basis,COUNT(*) lines FROM {d} d JOIN {l} l
ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
LEFT JOIN {x} x ON x."ItemCode"=l.item_code WHERE d.canceled='N'
AND d.doc_date>='{START}' AND d.doc_date<'{END}' GROUP BY ALL ORDER BY 1,2,3''')
            query(kind+'_raw_material_observation', f'''SELECT d.currency,COUNT(*) lines,
COUNT(DISTINCT l.item_code) products,COUNT(DISTINCT d.doc_entry) documents,
SUM(CAST(l.line_total AS DECIMAL(38,6))) recorded_line_amount,
MIN(d.doc_date) first_date,MAX(d.doc_date) last_date
FROM {d} d JOIN {l} l ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
JOIN {x} x ON x."ItemCode"=l.item_code
WHERE d.canceled='N' AND d.doc_date>='{START}' AND d.doc_date<'{END}'
AND x.product_business_type='RAW_MATERIAL' AND x.status='VALIDATED' GROUP BY 1''')
    evidence['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(evidence, stream, indent=2, default=str)
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)

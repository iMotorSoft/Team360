"""Read-only ranking-universe audit. Run from backend with --output <new JSON>."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector, DATA_ROOT
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake import category_line_amount_query as category
from modules.telchi.datalake import product_line_amount_ranking_query as ranking


def audit(output):
    report = dict(read_only=True, sap_accessed=False, queries=[], months={})
    with DuckLakeConnector().session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() == (True,)
        access = FoundationReader().resolve_on(con)
        report['source'] = access.as_dict()
        assert (access.foundation_publication_id, access.ducklake_snapshot_id) == (category.PUBLICATION, category.SNAPSHOT)
        path = DATA_ROOT / 'crosswalk/_versions' / access.foundation.reference_version / 'product_business_type/part-00000.parquet'
        report['crosswalk_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert report['crosswalk_sha256'] == category.CROSSWALK_SHA256
        rel = lambda p: "read_parquet('" + str(p).replace("'", "''") + "')"
        d, l, x, p = access.sales('sales_document'), access.sales('sales_line'), rel(path), rel(access.reference('products'))

        def query(name, sql, args=None):
            cur = con.execute('SELECT to_json(audit_row) FROM (' + sql + ') audit_row', args or []) if not sql.startswith('DESCRIBE') else con.execute(sql)
            rows = [json.loads(row[0], parse_float=Decimal) for row in cur.fetchall()] if not sql.startswith('DESCRIBE') else [dict(zip([c[0] for c in cur.description], row)) for row in cur.fetchall()]
            report['queries'].append(dict(name=name, sql=sql, parameters=args or [], rows=rows))
            return rows

        for name, relation in [('documents', d), ('lines', l), ('crosswalk', x), ('products', p)]:
            query(name + '_schema', 'DESCRIBE SELECT * FROM ' + relation)
        query('L01412_classification', f'''SELECT * FROM {x} WHERE "ItemCode"='L01412' ''')
        query('L01412_catalog', f"SELECT * FROM {p} WHERE item_code='L01412'")
        query('L01412_august_original', f'''SELECT d AS header,l AS line FROM {d} d JOIN {l} l
          ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
          WHERE d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND l.source_table='INV1'
          AND d.canceled='N' AND d.doc_date>='2026-08-01' AND d.doc_date<'2026-09-01'
          AND l.item_code='L01412' ''')
        raw_root = DATA_ROOT / 'raw/sap/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1'
        for month in ('07', '08'):
            paths = sorted(raw_root.glob(f'sales-2026-{month}-*/manual-update-20260924T123403*/part-00000.parquet'))
            if not paths:
                report['queries'].append(dict(name=month+'_raw_source', status='UNRESOLVED', reason='raw_partition_missing'))
                continue
            raw = 'read_parquet([' + ','.join("'"+str(p).replace("'", "''")+"'" for p in paths) + '],union_by_name=true)'
            query(month+'_raw_source', f'''SELECT DocEntry,LineNum,ItemCode,Dscription,DocNum,DocCur,LineCurrency,
                LineTotal,LineRate,TotalFrgn,TotalSumSy,Price,Quantity FROM {raw}
                WHERE ItemCode='L01412' AND DocDate>='2026-{month}-01'
                AND DocDate<'2026-{'08' if month=='07' else '09'}-01' ''')
            query(month+'_raw_key_duplicates', f'''SELECT DocEntry,LineNum,COUNT(*) n FROM {raw} GROUP BY ALL HAVING COUNT(*)>1''')
            query(month+'_raw_missing_lineage', f'''SELECT d.doc_entry,d.doc_date,l.line_num,l.item_code,l.raw_extraction_id
                FROM {d} d JOIN {l} l ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
                JOIN {x} x ON x."ItemCode"=l.item_code
                LEFT JOIN {raw} r ON CAST(r.DocEntry AS VARCHAR)=l.doc_entry AND CAST(r.LineNum AS VARCHAR)=l.line_num
                WHERE d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND l.source_table='INV1'
                  AND d.canceled='N' AND d.doc_date>='2026-{month}-01'
                  AND d.doc_date<'2026-{'08' if month=='07' else '09'}-01'
                  AND x.product_business_type='LAB_FINISHED_PRODUCT' AND r.DocEntry IS NULL''')
            query(month+'_raw_correspondence', f'''SELECT COUNT(*) foundation_lines,
                COUNT(*) FILTER(WHERE r.DocEntry IS NULL) missing_raw,
                COUNT(*) FILTER(WHERE r.DocEntry IS NOT NULL AND (r.ItemCode IS DISTINCT FROM l.item_code
                  OR r.LineCurrency IS DISTINCT FROM l.currency OR r.DocCur IS DISTINCT FROM d.currency
                  OR CAST(r.LineTotal AS DECIMAL(38,6)) IS DISTINCT FROM CAST(l.line_total AS DECIMAL(38,6)))) mismatches
                FROM {d} d JOIN {l} l ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
                JOIN {x} x ON x."ItemCode"=l.item_code
                LEFT JOIN {raw} r ON CAST(r.DocEntry AS VARCHAR)=l.doc_entry AND CAST(r.LineNum AS VARCHAR)=l.line_num
                WHERE d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND l.source_table='INV1'
                  AND d.canceled='N' AND d.doc_date>='2026-{month}-01'
                  AND d.doc_date<'2026-{'08' if month=='07' else '09'}-01'
                  AND x.product_business_type='LAB_FINISHED_PRODUCT' ''')
        query('document_duplicates', f'''SELECT source_system,source_table,doc_entry,COUNT(*) n
          FROM {d} GROUP BY ALL HAVING COUNT(*)>1''')
        query('line_duplicates', f'''SELECT source_system,source_table,doc_entry,line_num,COUNT(*) n
          FROM {l} GROUP BY ALL HAVING COUNT(*)>1''')
        query('crosswalk_duplicates', f'''SELECT "ItemCode",COUNT(*) n FROM {x} GROUP BY ALL HAVING COUNT(*)>1''')
        for month, end in [('07', '08'), ('08', '09'), ('09', '10')]:
            start, stop = f'2026-{month}-01', f'2026-{end}-01'
            base = f'''FROM {d} d JOIN {l} l ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
              LEFT JOIN {x} x ON x."ItemCode"=l.item_code
              WHERE d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND l.source_table='INV1'
              AND d.canceled='N' AND d.doc_date>=? AND d.doc_date<?'''
            query(month+'_currency_universe', f'''SELECT x.product_business_type,x.status,d.currency header_currency,
              l.currency line_currency,COUNT(*) line_count,COUNT(DISTINCT l.item_code) product_count,
              SUM(CAST(l.line_total AS DECIMAL(38,6))) original_amount {base} GROUP BY ALL ORDER BY 1,2,3,4''', [start, stop])
            full = query(month+'_independent_full_ranking', f'''SELECT l.item_code,
              SUM(CAST(l.line_total AS DECIMAL(38,6))) amount,COUNT(*) line_count,
              COUNT(DISTINCT d.doc_entry) document_count {base}
              AND x.product_business_type='LAB_FINISHED_PRODUCT'
              GROUP BY l.item_code ORDER BY amount DESC,l.item_code ASC''', [start, stop])
            total = query(month+'_independent_category_total', f'''SELECT SUM(CAST(l.line_total AS DECIMAL(38,6))) amount,
              COUNT(*) line_count,COUNT(DISTINCT l.item_code) product_count {base}
              AND x.product_business_type='LAB_FINISHED_PRODUCT' ''', [start, stop])[0]
            assert sum((Decimal(str(r['amount'])) for r in full), Decimal(0)) == Decimal(str(total['amount']))
            assert sum(r['line_count'] for r in full) == total['line_count']
            assert len(full) == total['product_count']
            query(month+'_lineage_bad', f'''SELECT COUNT(*) n {base} AND x.product_business_type='LAB_FINISHED_PRODUCT'
              AND (d.raw_extraction_id IS DISTINCT FROM l.raw_extraction_id
                OR d.source_as_of IS DISTINCT FROM l.source_as_of OR d.raw_extraction_id IS NULL
                OR d.source_as_of IS NULL OR l.line_num IS NULL OR x.status NOT IN ('VALIDATED','SUPPORTED'))''', [start, stop])
            options = dict(category='LAB_FINISHED_PRODUCT', date_from=start, date_to_exclusive=stop, currency='BS', limit=5)
            try:
                worker = ranking.aggregate(con, d, l, x, p, options)
                worker_status = dict(status='PASS', reconciliation=worker[-1])
            except Exception as exc:
                worker_status = dict(status='ERROR', reason=str(exc))
            target = [dict(row, position=i+1) for i, row in enumerate(full) if row['item_code']=='L03281']
            report['months'][month] = dict(target=target, comparable_products=len(full), total=total, worker=worker_status)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, default=str)
    print(json.dumps(report['months'], indent=2, default=str))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    audit(parser.parse_args().output)

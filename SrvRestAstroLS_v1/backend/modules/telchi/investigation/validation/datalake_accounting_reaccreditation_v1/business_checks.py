"""Bounded business/source checks, pinned to canonical Foundation. No SAP."""
import json
from pathlib import Path
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from .audit import ROOT, PREVIOUS, records


def run():
    out = ROOT / 'data/reports/telchi/datalake-accounting-reaccreditation-v1-r3/business-checks.json'
    result = {}
    connector = DuckLakeConnector()
    if connector.host not in ('localhost','127.0.0.1','::1') or not connector.data_path.is_dir():
        raise RuntimeError('local existing catalog only')
    with connector.session(read_only=True) as c:
        c.execute('SET threads=2'); c.execute("SET memory_limit='768MB'")
        a = FoundationReader(connector=connector).resolve_on(c)
        expected = json.loads((out.parent / 'access.json').read_text())
        if a.foundation_publication_id != expected['foundation_publication_id'] or a.ducklake_snapshot_id != expected['ducklake_snapshot_id']:
            raise RuntimeError('Foundation changed; new accreditation required')
        def query(name, sql, params=None):
            result[name] = {'sql': sql, 'params': params or [], 'result': records(c,sql,params)}
        sales = a.sales('sales_document')
        lines = a.sales('sales_line')
        rc = f'(SELECT * FROM telchi.atomic.receivable_document AT (VERSION=>{a.manifest_base_snapshot_id}))'
        result['atomic_receivable_status'] = 'INVESTIGATION_LINEAGE_ONLY_NOT_CANONICAL_READER_CAPABILITY'
        query('receivable_schema', 'DESCRIBE SELECT * FROM ' + rc)
        query('receivable_keys', f'''SELECT source_system,source_table, count(*) AS rows,
        count(transaction_id) AS trans_id_nonnull, count(DISTINCT source_doc_entry) AS doc_entries,
        count(branch_id) AS branch_nonnull, count(DISTINCT branch_id) AS branch_values,
        min(document_date) AS first_date,max(document_date) AS last_date
        FROM {rc} GROUP BY 1,2''')
        query('receivable_branch_distribution', f'SELECT branch_id,count(*) AS rows FROM {rc} GROUP BY 1 ORDER BY 1')
        query('invoice_number_12345', f'SELECT source_system,doc_entry,doc_num,series,doc_date,canceled,currency,doc_total FROM {sales} WHERE doc_num=?', ['12345'])
        query('sales_2026_months', f'''SELECT substr(doc_date,1,7) AS month,canceled,currency,count(*) AS documents,
        sum(try_cast(doc_total AS DECIMAL(38,6))) AS document_total FROM {sales}
        WHERE doc_date>='2026-01-01' AND doc_date<'2027-01-01' GROUP BY 1,2,3 ORDER BY 1,2,3''')
        query('sales_identity_duplicates', f'SELECT count(*) AS duplicate_keys FROM (SELECT source_system,source_table,doc_entry FROM {sales} GROUP BY 1,2,3 HAVING count(*)>1)')
        query('line_identity_duplicates', f'SELECT count(*) AS duplicate_keys FROM (SELECT source_system,source_table,doc_entry,line_num FROM {lines} GROUP BY 1,2,3,4 HAVING count(*)>1)')
        query('invoice_to_receivable_key_coverage', f'''SELECT count(*) AS sales_documents,
        count(r.source_doc_entry) AS matched_receivable_rows,
        count(r.transaction_id) AS transaction_ids_available,
        count(CASE WHEN trim(coalesce(r.transaction_id,'')) NOT IN ('','0','-1') THEN 1 END) AS non_sentinel_transaction_ids,
        count(CASE WHEN trim(coalesce(r.branch_id,'')) NOT IN ('','0','-1') THEN 1 END) AS non_sentinel_documentary_branch
        FROM {sales} s LEFT JOIN {rc} r ON s.source_system=r.source_system AND s.doc_entry=r.source_doc_entry AND r.source_table='OINV+INV6' ''')
        for dataset in ['branches','business_locations','products','warehouses']:
            path = str(a.reference(dataset))
            query(dataset + '_schema', 'DESCRIBE SELECT * FROM read_parquet(?)', [path])
            if dataset in ('branches','business_locations'):
                query(dataset, 'SELECT COLUMNS(*)::VARCHAR FROM read_parquet(?)', [path])
        candidate = json.loads((PREVIOUS / 'report.json').read_text())['candidate']['reference_path']
        path = str(Path(candidate)/'products/part-00000.parquet')
        query('candidate_product_schema','DESCRIBE SELECT * FROM read_parquet(?)',[path])
        # This is source-state distribution only, not an inventory/business classification.
        cols = {x['column_name'] for x in result['candidate_product_schema']['result']}
        for col in sorted(cols):
            if col.startswith('physical_'):
                query('candidate_' + col, f'SELECT "{col}", count(*) AS rows FROM read_parquet(?) GROUP BY 1 ORDER BY 1',[path])
    out.write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(out)


if __name__ == '__main__':
    run()

"""Bounded independent discovery; read-only Foundation and SAP preflight, no capability."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket

from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.source import hana_config, HanaReadOnlySource


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing overwrite')
    out = dict(timestamp=datetime.now(timezone.utc).isoformat(), read_only=True,
               sap_write_count=0, queries=[], threads=2, memory_limit='768MB')
    def save():
        args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + '\n')
    try:
        cfg = hana_config()
        with socket.create_connection((cfg['host'], int(cfg['port'])), timeout=5):
            pass
        out['sap_preflight'] = HanaReadOnlySource().query_read_only('abraham002_preflight', 'SELECT 1 AS "ok" FROM DUMMY')
    except Exception as exc:
        out['sap_preflight'] = dict(status='BLOCKED', error_type=type(exc).__name__,
                                    reason='Configured HANA unavailable; no live reconciliation; no endpoint or secret recorded')
    r = FoundationReader()
    with r.connector.session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='768MB'")
        a = r.resolve_on(c)
        out['foundation'] = a.as_dict()
        def q(name, sql):
            item = dict(name=name, sql=sql)
            out['queries'].append(item)
            try:
                cur = c.execute(sql)
                item['rows'] = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
            except Exception as exc:
                item['error'] = str(exc)
            save()
            return item.get('rows', [])
        for comp, table in [('sales','sales_document'), ('sales','sales_line'),
                            ('credit_memo','credit_memo_document'), ('credit_memo','credit_memo_line')]:
            q(table + '_schema', 'DESCRIBE SELECT * FROM ' + a.relation(comp, table))
        out['reference_datasets'] = sorted(p.name for p in a.reference_path.iterdir() if p.is_dir())
        for name in out['reference_datasets']:
            p = str(a.reference(name)).replace("'", "''")
            q(name + '_schema', f"DESCRIBE SELECT * FROM read_parquet('{p}')")
        def ref(name):
            return "read_parquet('" + str(a.reference(name)).replace("'", "''") + "')"
        q('product_name_candidates', f"SELECT source_system,item_code,product_name,canonical_name,inventory_uom_id,sales_uom_id,purchase_uom_id,active,status,sap_sell_item FROM {ref('products')} WHERE upper(product_name) LIKE '%CITRAT%' OR upper(product_name) LIKE '%MAGNES%' ORDER BY source_system,item_code")
        q('distributor_name_candidates', f"SELECT source_system,source_native_id,code,name,branch_id,status,sap_card_type,sap_group_code FROM {ref('customers')} WHERE upper(name) LIKE '%L&S%' OR upper(name) LIKE '%L & S%' OR upper(name) LIKE '%L Y S%'")
        rawroot = r.connector.data_path.parents[1] / 'raw/sap/table_extract'
        out['raw_tables'] = sorted(str(p.relative_to(rawroot)) for p in rawroot.rglob('*.parquet'))
        for p in rawroot.rglob('OCRD.parquet'):
            q('raw_OCRD_schema:' + str(p), f"DESCRIBE SELECT * FROM read_parquet('{p}')")
        for name, rel in [('invoices', a.sales('sales_document')), ('credit_memos', a.credit_memo('credit_memo_document'))]:
            q(name + '_coverage', f"SELECT source_system,currency,canceled,MIN(doc_date) min_date,MAX(doc_date) max_date,COUNT(*) documents FROM {rel} WHERE doc_date>='2026-01-01' AND doc_date<'2027-01-01' GROUP BY ALL")
        out['publication_unchanged'] = r.resolve_on(c).foundation_publication_id == a.foundation_publication_id
    save()
    print(json.dumps({k:v for k,v in out.items() if k not in ('queries', 'raw_tables')}, indent=2, default=str))
    for item in out['queries']:
        if 'candidates' in item['name'] or 'coverage' in item['name'] or 'error' in item:
            print(json.dumps(item, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()

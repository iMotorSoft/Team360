"""Read-only independent aggregates, explicitly NOT a new assistant capability."""
import argparse
import json
import socket
from pathlib import Path
from datetime import datetime, timezone
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.source import hana_config, HanaReadOnlySource


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        raise SystemExit('Refusing overwrite')
    out = {'timestamp': datetime.now(timezone.utc).isoformat(), 'queries': [],
           'sap_write_count': 0, 'read_only': True, 'threads': 2,
           'monetary_definition': 'Active (canceled=N) invoice header DocTotal minus active credit memo header DocTotal, DocDate, BS only. Document total includes taxes; not tax-exclusive revenue. Returns only insofar as represented by credit memos. No SAP+DMS union.',
           'horizontal_definition': 'Existing Foundation sales_channel_code=HORIZONTAL, derived by existing ingestion from 14 series. Not newly inferred from pharmacies. Conditional proxy until DMS/U_ORIGIN and series census reconciled.',
           'pharmacy_definition': 'Requires authoritative customer classification, e.g. OCRD.U_CANAL_VENTAS=1 with verified UFD1 meaning; no name matching.'}
    try:
        cfg = hana_config()
        with socket.create_connection((cfg['host'], int(cfg['port'])), timeout=5):
            pass
        s = HanaReadOnlySource()
        out['sap_preflight'] = s.query_read_only('abraham_preflight', 'SELECT 1 AS "ok" FROM DUMMY')
    except Exception as exc:
        out['sap_preflight'] = {'status': 'BLOCKED', 'error_type': type(exc).__name__,
                                 'reason': 'Configured HANA source not reachable; no live reconciliation performed'}
    r = FoundationReader()
    with r.connector.session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='1GB'")
        a = r.resolve_on(c)
        out.update(foundation=a.foundation_publication_id, snapshot=a.ducklake_snapshot_id,
                   data_as_of=a.foundation_data_as_of, reference=str(a.reference_path))
        def query(name, sql):
            cur = c.execute(sql)
            rows = [dict(zip([x[0] for x in cur.description], row)) for row in cur.fetchall()]
            out['queries'].append({'name': name, 'sql': sql, 'rows': rows})
            return rows
        sales, credit = a.sales('sales_document'), a.credit_memo('credit_memo_document')
        for name, rel in [('invoices', sales), ('credit_memos', credit)]:
            query(name + '_coverage', f'''SELECT source_system, source_table, currency, canceled,
                MIN(doc_date) min_date,MAX(doc_date) max_date,COUNT(*) documents,
                COUNT(DISTINCT doc_entry) distinct_doc_entries FROM {rel}
                WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01' GROUP BY ALL''')
            query(name + '_channel_profile', f'''SELECT sales_channel_code,sales_channel_semantic_status,
                COUNT(*) documents,COUNT(DISTINCT card_code) customers,
                MIN(doc_date) min_date,MAX(doc_date) max_date FROM {rel}
                WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01' GROUP BY ALL''')
            query(name + '_horizontal_series', f'''SELECT series,user_sign,COUNT(*) documents FROM {rel}
                WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01'
                AND sales_channel_code='HORIZONTAL' GROUP BY ALL ORDER BY series,user_sign''')
        query('horizontal_buying_customers_conditional', f'''SELECT COUNT(DISTINCT card_code) buying_customer_codes,
            COUNT(*) active_invoices,COUNT(*) FILTER(WHERE card_code IS NULL) null_customer_codes,
            COUNT(*) FILTER(WHERE TRY_CAST(doc_total AS DECIMAL(38,6)) IS NULL) invalid_amounts
            FROM {sales} WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01'
            AND sales_channel_code='HORIZONTAL' AND canceled='N' ''')
        query('horizontal_monthly_conditional', f'''WITH i AS (
            SELECT SUBSTR(doc_date,1,7) AS period_month,COUNT(*) invoices,COUNT(DISTINCT card_code) buyers,
                SUM(TRY_CAST(doc_total AS DECIMAL(38,6))) billed,MAX(doc_date) latest_invoice
            FROM {sales} WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01'
                AND sales_channel_code='HORIZONTAL' AND canceled='N' AND currency='BS' GROUP BY 1),
            n AS (SELECT SUBSTR(doc_date,1,7) AS period_month,COUNT(*) credits,
                SUM(TRY_CAST(doc_total AS DECIMAL(38,6))) credited,MAX(doc_date) latest_credit
            FROM {credit} WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01'
                AND sales_channel_code='HORIZONTAL' AND canceled='N' AND currency='BS' GROUP BY 1)
            SELECT COALESCE(i.period_month,n.period_month) AS period_month, i.invoices,i.buyers,i.billed,
                COALESCE(n.credits,0) credits,COALESCE(n.credited,0) credited,
                COALESCE(i.billed,0)-COALESCE(n.credited,0) net_documental,
                i.latest_invoice,n.latest_credit FROM i FULL JOIN n USING(period_month) ORDER BY period_month''')
        cp = str(a.reference('customers')).replace("'", "''")
        query('customer_master_sources', f'''SELECT source_system,sap_card_type,COUNT(*) AS row_count,
            COUNT(DISTINCT source_native_id) native_ids,MAX(_source_snapshot_at) snapshot_at
            FROM read_parquet('{cp}') GROUP BY ALL''')
        query('horizontal_customer_master_match', f'''WITH b AS (SELECT DISTINCT card_code FROM {sales}
            WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01' AND canceled='N'
            AND sales_channel_code='HORIZONTAL'), m AS (SELECT source_native_id,COUNT(*) matches
            FROM read_parquet('{cp}') WHERE source_system='SAP_HANA' GROUP BY 1)
            SELECT COUNT(*) buyer_codes,COUNT(*) FILTER(WHERE matches=1) unique_master_matches,
            COUNT(*) FILTER(WHERE matches IS NULL) missing_master_matches,
            COUNT(*) FILTER(WHERE matches>1) ambiguous_master_matches FROM b LEFT JOIN m
            ON b.card_code=m.source_native_id''')
        for dataset in ('customers','sales_channel','customer_business_type'):
            p = str(a.reference(dataset)).replace("'", "''")
            query(dataset + '_schema', f"DESCRIBE SELECT * FROM read_parquet('{p}')")
            if dataset != 'customers':
                query(dataset + '_dictionary', f"SELECT code,name,status,source FROM read_parquet('{p}')")
        crosswalk = r.connector.data_path.parents[1] / 'crosswalk/_versions' / a.reference_path.name
        for dataset in ('customer_crosswalk','customer_business_type'):
            p = str(crosswalk / dataset / 'part-00000.parquet').replace("'", "''")
            query(dataset + '_crosswalk_schema', f"DESCRIBE SELECT * FROM read_parquet('{p}')")
        raw = next((r.connector.data_path.parents[1] / 'raw/sap/table_extract').rglob('OCRD.parquet'))
        out['inspected_raw_master'] = str(raw)
        query('raw_OCRD_schema', f"DESCRIBE SELECT * FROM read_parquet('{raw}')")
        out['publication_unchanged'] = r.resolve_on(c).foundation_publication_id == a.foundation_publication_id
    out['unresolved'] = {
        'registered_horizontal_clients': 'No inspected master provides registered DMS membership; buying customers != registered customers.',
        'horizontal_pharmacy_clients_and_amounts': 'Inspected pinned customers/master lack U_CANAL_VENTAS; business type dictionary has no pharmacy subtype. No mapping fabricated.',
        'dms_sap_identity_reconciliation': 'Native SAP CardCode matches can be checked locally; no independent DMS customer ledger reconciled.',
        'net_returns_completeness': 'Subtracts tagged active ORIN; cross-channel credits/base-document attribution and unposted DMS returns not certified.',
        'january_september_full_months_average': 'No full-month completeness certification. September latest available date must be read from coverage; no nine-month average certified.'}
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str) + '\n')
    print(json.dumps({k:v for k,v in out.items() if k!='queries'}, ensure_ascii=False, default=str, indent=2))
    for q in out['queries']:
        if q['name'] in ('horizontal_monthly_conditional','horizontal_buying_customers_conditional','horizontal_customer_master_match','invoices_coverage','credit_memos_coverage'):
            print(q['name'], json.dumps(q['rows'], default=str))


if __name__ == '__main__':
    main()

"""Geographic evidence only: warehouse movements are NOT commercial destinations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from modules.telchi.datalake.foundation_reader import FoundationReader
from .verify_data import PRIMARY_CODES, LEGACY


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing overwrite')
    out = dict(timestamp=datetime.now(timezone.utc).isoformat(), read_only=True, queries=[])
    r = FoundationReader()
    with r.connector.session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='512MB'")
        c.execute("SET max_temp_directory_size='0B'")
        a = r.resolve_on(c)
        out['foundation'] = a.as_dict()
        def q(name, sql):
            cur = c.execute(sql)
            rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
            out['queries'].append(dict(name=name, sql=sql, rows=rows))
            print(name, json.dumps(rows, ensure_ascii=False, default=str))
        legacy = LEGACY / 'DS/clientSB1.parq'
        q('historical_city_labels', f"SELECT ClientCity,COUNT(*) customers FROM read_parquet('{legacy}') GROUP BY 1 ORDER BY customers DESC LIMIT 40")
        q('historical_la_paz_spelling_candidates', f"SELECT ClientCity,COUNT(*) customers FROM read_parquet('{legacy}') WHERE contains(lower(strip_accents(ClientCity)), 'paz') GROUP BY 1")
        codes = ','.join("'"+x+"'" for x in PRIMARY_CODES)
        for component, doc, line in [('sales','sales_document','sales_line'), ('credit_memo','credit_memo_document','credit_memo_line')]:
            q(component + '_LPZ_WAREHOUSE_monthly_NOT_DESTINATION', f'''SELECT
                SUBSTR(d.doc_date,1,7) period_month,l.item_code,l.whs_code,
                COUNT(*) lines,COUNT(DISTINCT d.card_code) buyer_codes,
                MAX(d.doc_date) latest_date,d.currency document_currency,l.currency line_currency,
                SUM(TRY_CAST(l.quantity AS DECIMAL(38,6))) documentary_quantity,
                SUM(TRY_CAST(l.line_total AS DECIMAL(38,6))) raw_line_total
                FROM {a.relation(component,line)} l JOIN {a.relation(component,doc)} d
                ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
                WHERE d.canceled='N' AND l.item_code IN ({codes}) AND l.whs_code LIKE 'LPZ-%'
                AND d.doc_date>='2026-01-01' AND d.doc_date<'2027-01-01'
                GROUP BY ALL ORDER BY period_month,l.item_code,l.whs_code''')
        out['publication_unchanged'] = r.resolve_on(c).foundation_publication_id == a.foundation_publication_id
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + '\n')


if __name__ == '__main__':
    main()

"""Read-only, bounded historical monetary reconciliation; no activation or SAP.

Uses the existing financial contract, not a new metric. Reference verification
sums individual document Decimals in Python, separately from SQL aggregation.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[3] / 'SrvRestAstroLS_v1/backend'))
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

PUBLICATION = 'foundation_afd08d9eca6a725be53cdc3f9d5709c9'
PERIODS = [('2026-05-01', '2026-06-01'), ('2026-06-01', '2026-07-01')]
SQL = '''SELECT source_system,currency,canceled,COUNT(*) documents,
COUNT(DISTINCT doc_entry) distinct_documents,
SUM(CAST(doc_total AS DECIMAL(38,6))) document_total
FROM {relation} WHERE doc_date>=? AND doc_date<?
GROUP BY source_system,currency,canceled ORDER BY source_system,currency,canceled'''
REFERENCE_SQL = '''SELECT source_system,source_table,doc_entry,currency,canceled,doc_date,doc_total
FROM {relation} WHERE doc_date>=? AND doc_date<? ORDER BY source_system,doc_entry'''


def main():
    evidence = dict(executed_at=datetime.now(timezone.utc).isoformat(), read_only=True,
                    sap_accessed=False, foundation_modified=False, periods=[],
                    host_preflight='SAFE', threads=2, memory_limit='512MB')
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise ValueError('read_only_attachment_required')
        access = FoundationReader(connector).resolve_on(con)
        if access.foundation_publication_id != PUBLICATION or access.ducklake_snapshot_id != 1408:
            raise ValueError('binding_changed')
        evidence['binding'] = access.as_dict()
        for start, end in PERIODS:
            period = dict(date_from=start, date_to_exclusive=end, documents={})
            for kind, relation, source_table in [
                ('invoices', access.sales('sales_document'), 'OINV'),
                ('credits', access.credit_memo('credit_memo_document'), 'ORIN')]:
                begin = perf_counter()
                aggregate_sql = SQL.format(relation=relation)
                reference_sql = REFERENCE_SQL.format(relation=relation)
                cur = con.execute(aggregate_sql, [start, end])
                names = [c[0] for c in cur.description]
                aggregates = [dict(zip(names, row)) for row in cur.fetchall()]
                reference = con.execute(reference_sql, [start, end]).fetchall()
                groups = {}
                keys = set()
                hasher = hashlib.sha256()
                for system, table, entry, currency, canceled, day, amount in reference:
                    key = (system, entry)
                    if key in keys or not entry or table != source_table:
                        raise ValueError('invalid_document_grain_or_source')
                    keys.add(key)
                    value = Decimal(amount)
                    if not value.is_finite():
                        raise ValueError('nonfinite_amount')
                    if not start <= day[:10] < end:
                        raise ValueError('invalid_document_date')
                    hasher.update(json.dumps([system, table, entry, currency, canceled, day, amount]).encode())
                    group = groups.setdefault((system, currency, canceled), [0, Decimal(0)])
                    group[0] += 1
                    group[1] += value
                for row in aggregates:
                    reference_count, reference_total = groups[(row['source_system'], row['currency'], row['canceled'])]
                    if (row['documents'] != reference_count or row['distinct_documents'] != reference_count
                            or row['document_total'] != reference_total):
                        raise ValueError('independent_reference_mismatch')
                    row['reference_total'] = str(reference_total)
                    row['difference'] = str(row['document_total'] - reference_total)
                period['documents'][kind] = dict(sql=aggregate_sql, reference_sql=reference_sql,
                    parameters=[start, end], groups=aggregates, unique_documents=len(keys),
                    document_rows_sha256=hasher.hexdigest(), elapsed_ms=(perf_counter()-begin)*1000,
                    independent_reference='individual document Decimal sums; no SQL aggregate reuse', parity=True)
            def selected(kind):
                rows = [r for r in period['documents'][kind]['groups']
                        if r['source_system'] == 'SAP_B1_HANA' and r['currency'] == 'BS' and r['canceled'] == 'N']
                return sum((r['document_total'] for r in rows), Decimal(0)), sum(r['documents'] for r in rows)
            gross, invoices = selected('invoices')
            credit, credits = selected('credits')
            period['historical_metrics'] = dict(SALES_VALID_GROSS=str(gross), SALES_CREDIT_NOTES=str(credit),
                SALES_NET=str(gross-credit), currency='BS', invoice_count=invoices, credit_count=credits,
                semantics='DocDate; active N document headers; DocTotal; no cash/settlement metric')
            evidence['periods'].append(period)
            print(start, json.dumps(period['historical_metrics']))
    (OUT / 'foundation_reconciliation.json').write_text(json.dumps(evidence, indent=2, default=str)+'\n')


if __name__ == '__main__':
    main()

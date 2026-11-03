"""Pinned, read-only discovery and independent Python line/header parity evidence."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.product_sales_query import execute_query
from modules.telchi.datalake.sales_query import PUBLICATION, SNAPSHOT, execute_query as query_sales, MONETARY_OPERATION


def records(con, sql, values=None):
    cur = con.execute(sql, values or [])
    return [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]


def run(output):
    catalog = execute_query('products.search', {'text': 'Calenta', 'limit': 20})
    codes = [r['item_code'] for r in catalog['rows'] if r['match_rank'] == 1 and r['sell_item'] == 'Y']
    result = dict(executed_at=datetime.now(timezone.utc).isoformat(), catalog=catalog,
                  read_only=True, sap_accessed=False, threads=2, memory_limit='512MB',
                  independent_reference='Separate product scan and separate line/header reads; Python keyed merge, Decimal checks and sorting. No service SQL/result reuse for expected rows.',
                  codes=codes, cases=[])
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2'); con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        a = FoundationReader(connector).resolve_on(con)
        if (a.foundation_publication_id, a.ducklake_snapshot_id) != (PUBLICATION, SNAPSHOT):
            raise ValueError('binding_changed')
        result['binding'] = dict(publication_id=PUBLICATION, snapshot_id=SNAPSHOT)
        path = str(a.reference('products'))
        products = records(con, "SELECT item_code,source_native_id,_source_native_key,coalesce(sap_item_name,product_name,canonical_name) description,sap_sell_item sell_item FROM read_parquet(?) WHERE source_system='SAP_HANA'", [path])
        keys = [p['item_code'] for p in products]
        assert len(keys) == len(set(keys)) and all(p['item_code'] == p['source_native_id'] == p['_source_native_key'] for p in products)
        import unicodedata
        def reference_fold(value):
            return ''.join(c for c in unicodedata.normalize('NFKD', (value or '').lower()) if not unicodedata.combining(c))
        found = [p for p in products if 'calenta' in reference_fold(p['description']) or 'calenta' in reference_fold(p['item_code'])]
        assert {p['item_code'] for p in found} == {p['item_code'] for p in catalog['rows']}
        result['catalog_identity'] = dict(rows=len(products), unique_item_codes=len(set(keys)), natural_keys_unchanged=True, search_parity=True)
        l, d = a.sales('sales_line'), a.sales('sales_document')
        result['sales_schema'] = records(con, 'DESCRIBE SELECT * FROM '+l)
        coverage = records(con, f"SELECT item_code,count(*) line_count FROM {l} WHERE source_system=? GROUP BY item_code", ['SAP_B1_HANA'])
        result['relation_coverage'] = dict(total_lines=sum(r['line_count'] for r in coverage),
            related_lines=sum(r['line_count'] for r in coverage if r['item_code'] in set(keys)),
            missing_nonnull_codes=[r for r in coverage if r['item_code'] is not None and r['item_code'] not in set(keys)],
            null_item_lines=sum(r['line_count'] for r in coverage if r['item_code'] is None))
        all_codes = [r['item_code'] for r in catalog['rows'] if r['match_rank'] == 1]
        lines = records(con, f"SELECT source_system,doc_entry,line_num,item_code,quantity FROM {l} WHERE source_system=? AND item_code IN (SELECT unnest(?))", ['SAP_B1_HANA', all_codes])
        entries = sorted({r['doc_entry'] for r in lines})
        documents = records(con, f"SELECT source_system,doc_entry,doc_num,doc_date,canceled FROM {d} WHERE source_system=? AND doc_entry IN (SELECT unnest(?))", ['SAP_B1_HANA', entries])
        by_document = {(r['source_system'], r['doc_entry']): r for r in documents}
        assert len(by_document) == len(documents)
        line_keys = {(r['source_system'], r['doc_entry'], r['line_num']) for r in lines}
        assert len(line_keys) == len(lines)
        assert all((r['source_system'], r['doc_entry']) in by_document for r in lines)
        merged = []
        for line in lines:
            assert Decimal(line['quantity']).is_finite()
            doc = by_document[(line['source_system'], line['doc_entry'])]
            if doc['canceled'] == 'N':
                merged.append(dict(line, doc_date=doc['doc_date'], doc_num=doc['doc_num']))
        result['per_product'] = [dict(item_code=code,
            all_line_count=sum(r['item_code'] == code for r in lines),
            active_line_count=sum(r['item_code'] == code for r in merged),
            may_active_line_count=sum(r['item_code'] == code and '2026-05-01' <= r['doc_date'] < '2026-06-01' for r in merged),
            first_date=min((r['doc_date'] for r in merged if r['item_code'] == code), default=None),
            last_date=max((r['doc_date'] for r in merged if r['item_code'] == code), default=None)) for code in all_codes]
        result['identity_checks'] = dict(unique_line_keys=True, unique_document_keys=True, no_orphan_selected_lines=True, no_join_multiplication=True)
        for selected, start, end in [(codes,None,None),(codes,'2026-05-01','2026-06-01')] + [( [code],None,None) for code in all_codes]:
            options = dict(namespace='SAP_HANA', item_codes=selected, limit=10)
            if start: options.update(date_from=start, date_to_exclusive=end)
            expected = [r for r in merged if r['item_code'] in selected and (not start or start <= r['doc_date'] < end)]
            expected_counts = {code:sum(r['item_code'] == code for r in expected) for code in selected}
            expected.sort(key=lambda r:(r['doc_date'],int(r['doc_entry']),int(r['line_num']),r['item_code']),reverse=True)
            expected = expected[:10]
            # Service executes separately, never supplies expected rows.
            actual = execute_query('sales.by_products', options)
            fields = ('doc_date','doc_entry','line_num','item_code','quantity','doc_num')
            assert [[r[k] for k in fields] for r in expected] == [[r[k] for k in fields] for r in actual['rows']]
            assert {r['item_code']:r['line_count'] for r in actual['product_summary']} == expected_counts
            result['cases'].append(dict(options=options, parity=True,
                independent_expected=[{k:r[k] for k in fields} for r in expected],
                independent_counts=expected_counts, actual=actual))
    result['monthly_regression'] = []
    for month, following, expected in [('05','06','8552079.19'),('06','07','9763493.67')]:
        options = dict(date_from=f'2026-{month}-01',date_to_exclusive=f'2026-{following}-01',currency='BS')
        actual = query_sales(MONETARY_OPERATION, options)
        assert Decimal(actual['rows'][0]['net_amount']) == Decimal(expected)
        result['monthly_regression'].append(actual)
    output.mkdir(parents=True, exist_ok=True)
    (output/'foundation_reference.json').write_text(json.dumps(result,indent=2,default=str,ensure_ascii=False)+'\n')
    print(json.dumps(dict(products=len(catalog['rows']), selected_commercial=len(codes), parity_cases=len(result['cases']), relation_coverage=result['relation_coverage'])))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)

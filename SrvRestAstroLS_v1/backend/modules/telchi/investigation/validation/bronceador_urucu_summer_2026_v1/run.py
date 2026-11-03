"""Read-only Urucu analysis. Published facts pinned; captured BOM is investigative only."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

OUT = Path('data/reports/telchi/bronceador-urucu-summer-2026-v1')
D = Decimal


def rows(con, sql, args=None):
    cur = con.execute(sql, args or [])
    names = [c[0] for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def main():
    out = {}
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() == (True,)
        a = FoundationReader(connector).resolve_on(con)
        out['publication'] = a.foundation_publication_id
        out['snapshot'] = a.ducklake_snapshot_id
        out['component_as_of'] = {k: v.get('source_as_of') for k, v in a.manifest['components'].items()}
        con.execute("CREATE TEMP VIEW products AS SELECT * FROM read_parquet('" + str(a.reference('products')) + "') WHERE source_system='SAP_HANA'")
        con.execute("CREATE TEMP VIEW selected AS SELECT item_code,sap_item_name,active,inventory_uom_id,sales_uom_id FROM products WHERE sap_item_name LIKE 'BRONCEADOR%' AND sap_item_name LIKE '%URUCU%'")
        out['products'] = rows(con, 'SELECT * FROM selected ORDER BY item_code')
        assert len(out['products']) == 9
        assert not rows(con, 'SELECT item_code FROM selected GROUP BY 1 HAVING count(*)<>1')
        for label, docs, lines, dt, lt in [
            ('invoice', a.sales('sales_document'), a.sales('sales_line'), 'OINV', 'INV1'),
            ('credit', a.credit_memo('credit_memo_document'), a.credit_memo('credit_memo_line'), 'ORIN', 'RIN1'),
        ]:
            con.execute(f"CREATE TEMP VIEW {label}_docs AS SELECT * FROM {docs} WHERE source_system='SAP_B1_HANA' AND source_table='{dt}' AND canceled='N'")
            con.execute(f"CREATE TEMP VIEW {label}_lines AS SELECT l.* FROM {lines} l JOIN selected s USING(item_code) WHERE l.source_system='SAP_B1_HANA' AND l.source_table='{lt}'")
            assert not rows(con, f'SELECT doc_entry FROM {label}_docs GROUP BY 1 HAVING count(*)<>1')
            assert not rows(con, f'SELECT doc_entry,line_num FROM {label}_lines GROUP BY 1,2 HAVING count(*)<>1')
            assert not rows(con, f'SELECT l.doc_entry FROM {label}_lines l LEFT JOIN {docs} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry WHERE d.doc_entry IS NULL LIMIT 1')
            con.execute(f"CREATE TEMP TABLE {label}_chosen AS SELECT substr(d.doc_date,1,10) AS day,l.item_code,cast(l.quantity AS DECIMAL(28,6)) qty,cast(l.line_total AS DECIMAL(28,6)) amount,l.currency line_currency,d.currency doc_currency,l.doc_entry,l.line_num FROM {label}_lines l JOIN {label}_docs d USING(doc_entry)")
            assert not rows(con, f"SELECT * FROM {label}_chosen WHERE qty IS NULL OR amount IS NULL OR line_currency IS DISTINCT FROM 'BS' OR doc_currency IS DISTINCT FROM 'BS'")
            out[label + '_coverage'] = rows(con, f'SELECT min(doc_date) first_date,max(doc_date) last_date,max(source_as_of) source_as_of FROM {label}_docs')
            out[label + '_monthly'] = rows(con, f'SELECT substr(day,1,7) AS month,item_code,sum(qty) qty,sum(amount) amount_bs,count(*) lines FROM {label}_chosen GROUP BY 1,2 ORDER BY 1,2')
            out[label + '_2026'] = rows(con, f"SELECT item_code,sum(qty) qty,sum(amount) amount_bs,count(*) lines FROM {label}_chosen WHERE day>='2026-01-01' AND day<'2027-01-01' GROUP BY 1 ORDER BY 1")
            out[label + '_seasonal'] = rows(con, f"SELECT (CASE WHEN substr(day,6,2)='12' THEN cast(substr(day,1,4) AS INTEGER) ELSE cast(substr(day,1,4) AS INTEGER)-1 END) season_start,item_code,sum(qty) qty,sum(amount) amount_bs FROM {label}_chosen WHERE substr(day,6,2) IN ('12','01','02') GROUP BY 1,2 ORDER BY 1,2")
            total = con.execute(f'SELECT coalesce(sum(amount),0),coalesce(sum(qty),0) FROM {label}_chosen').fetchone()
            assert total == (sum((r['amount_bs'] for r in out[label + '_monthly']), D(0)), sum((r['qty'] for r in out[label + '_monthly']), D(0)))
        # Historical mirrored SAP exports are separate investigative evidence.
        # One file per month, with contained-date predicates: never concatenate -h.
        legacy = DATA_ROOT / 'raw/legacy/parquet'
        out['historical_months'] = []
        out['historical_sales'] = []
        for month in ['2022-12', '2023-01', '2023-02', '2023-12', '2024-01', '2024-02']:
            fs = list(legacy.glob(f'saleSB1Product-{month}-*.parq'))
            fs = [f for f in fs if not f.name.endswith('-h.parq')]
            assert len(fs) == 1
            f = fs[0]
            coverage = rows(con, "SELECT min(DocDate) first_date,max(DocDate) last_date,count(*) AS row_count,count(DISTINCT cast(DocDate AS DATE)) AS day_count FROM read_parquet(?) WHERE strftime(DocDate,'%Y-%m')=?", [str(f), month])[0]
            coverage.update(month=month, path=str(f), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
            out['historical_months'].append(coverage)
            records = rows(con, "SELECT strftime(DocDate,'%Y-%m') AS month,ItemCode item_code,ItemName item_name,sum(cast(ItemSaleCant AS DECIMAL(28,6))) qty,sum(cast(ItemSale AS DECIMAL(28,6))) amount_bs,count(*) lines FROM read_parquet(?) WHERE strftime(DocDate,'%Y-%m')=? AND u_estadofc<>'A' AND ItemCode IN (SELECT item_code FROM selected) GROUP BY 1,2,3 ORDER BY 1,2", [str(f), month])
            out['historical_sales'].extend(records)
        con.execute('CREATE TEMP VIEW stock AS SELECT * FROM ' + a.oitw() + " WHERE source_system='SAP_B1_HANA'")
        assert not rows(con, 'SELECT item_code,whs_code FROM stock GROUP BY 1,2 HAVING count(*)<>1')
        con.execute("CREATE TEMP VIEW roles AS SELECT * FROM read_parquet('" + str(a.reference('warehouse_roles')) + "')")
        assert not rows(con, 'SELECT warehouse_code FROM roles GROUP BY 1 HAVING count(*)<>1')
        stock_sql = "SELECT s.item_code,s.whs_code,cast(s.on_hand AS DECIMAL(28,6)) on_hand,cast(s.is_commited AS DECIMAL(28,6)) AS committed,cast(s.on_hand AS DECIMAL(28,6))-cast(s.is_commited AS DECIMAL(28,6)) available,cast(s.on_order AS DECIMAL(28,6)) on_order,r.warehouse_role,r.usable_for_supply_stock,s.source_as_of FROM stock s LEFT JOIN roles r ON r.warehouse_code=s.whs_code"
        out['warehouses'] = rows(con, "SELECT code,name,sap_locked,sap_inactive FROM read_parquet(?) WHERE source_system='SAP_HANA'", [str(a.reference('warehouses'))])
        out['invoice_year_coverage'] = rows(con, "SELECT substr(doc_date,1,4) AS year,count(*) AS documents,min(doc_date) first_date,max(doc_date) last_date FROM invoice_docs GROUP BY 1 ORDER BY 1")
        out['product_stock'] = rows(con, stock_sql + ' JOIN selected p ON p.item_code=s.item_code WHERE cast(s.on_hand AS DOUBLE)<>0 OR cast(s.is_commited AS DOUBLE)<>0 OR cast(s.on_order AS DOUBLE)<>0 ORDER BY s.item_code,s.whs_code')
        # Immutable captured BOM, NOT a new productive capability or a CURRENT component.
        raw = DATA_ROOT / 'raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1'
        out['bom_provenance'] = []
        for n in ['bom_header', 'bom_line']:
            fs = list((raw / n).glob('*/*/part-*.parquet'))
            assert len(fs) == 1
            f = fs[0]
            out['bom_provenance'].append(dict(dataset=n, path=str(f), sha256=hashlib.sha256(f.read_bytes()).hexdigest(), manifest=json.loads((f.parent/'manifest.json').read_text())))
            con.execute(f"CREATE TEMP VIEW {n} AS SELECT * FROM read_parquet('{f}')")
        headers = {r['Code']:r for r in rows(con, 'SELECT * FROM bom_header')}
        children = defaultdict(list)
        for r in rows(con, 'SELECT * FROM bom_line'):
            children[r['Father']].append(r)
        selected = {r['item_code'] for r in out['products']}
        relevant = set(selected)
        def discover(code, ancestors=()):
            assert code not in ancestors, 'BOM cycle'
            for r in children.get(code, []):
                if r['Type'] == 4:
                    relevant.add(r['Code'])
                    if r['Code'] in headers:
                        discover(r['Code'], ancestors+(code,))
        for code in selected:
            discover(code)
        con.execute('CREATE TEMP TABLE relevant(item_code VARCHAR)')
        con.executemany('INSERT INTO relevant VALUES (?)', [(x,) for x in sorted(relevant)])
        out['bom_headers'] = [headers[k] for k in sorted(relevant) if k in headers]
        out['bom_lines'] = [r for k in sorted(relevant) for r in children.get(k, [])]
        out['material_names'] = rows(con, 'SELECT p.item_code,p.sap_item_name,p.inventory_uom_id FROM products p JOIN relevant r USING(item_code)')
        out['relevant_stock'] = rows(con, stock_sql + ' JOIN relevant p ON p.item_code=s.item_code WHERE cast(s.on_hand AS DOUBLE)<>0 OR cast(s.is_commited AS DOUBLE)<>0 OR cast(s.on_order AS DOUBLE)<>0 ORDER BY s.item_code,s.whs_code')
        for name, dataset in a.manifest['components']['material_supply']['datasets'].items():
            out[name] = rows(con, 'SELECT d.* FROM read_parquet(?) d JOIN relevant r ON r.item_code=d.' + ('ItemCode' if name=='material_supply_status' else 'item_code'), [dataset['file_references']])
        out['checks'] = dict(read_only=True, sap_accessed=False, duplicate_selected_keys=0, duplicate_doc_keys=0, duplicate_line_keys=0, orphan_selected_lines=0, currency_exceptions=0, monthly_reconciliation='EXACT', threads=1, memory_limit='512MB', temp_spill=False)
    root = Path(__file__).resolve().parents[7]
    destination = root / OUT
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'evidence.json').write_text(json.dumps(out,default=str,ensure_ascii=False,indent=2)+'\n')
    print('EVIDENCE', destination/'evidence.json')
    print('CHECKS', json.dumps(out['checks']))


if __name__ == '__main__':
    main()

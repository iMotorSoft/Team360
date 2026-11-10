"""Independent first-principles SQL, authored without Luna answers or SQL.

Only CURRENT reader and raw source grains are shared with the evaluated system.
No production ranking/capability code is used; no source/policy/publication writes.
"""
import json
import os
from pathlib import Path
from time import perf_counter
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

OUT = Path('../../data/reports/telchi/blind-investigative-v1/independent-controls.json')
if OUT.exists():
    raise ValueError('new_output_required')
os.environ.update(json.loads(Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-dev-control.json').read_text())['env'])
report = dict(method=__doc__, controls=[])
connector = DuckLakeConnector()
with connector.session(read_only=True) as db:
    db.execute('SET threads=2')
    db.execute("SET memory_limit='768MB'")
    access = FoundationReader(connector).resolve_on(db)
    report['foundation'] = access.as_dict()
    report['coverage'] = {c: access.require_sales_coverage(c, '2026-10-01', '2026-11-01') for c in ('sales','credit_memo')}
    report['operational_manifest'] = {k:v for k,v in access.manifest.items() if 'observation' in k or 'stock' in k}
    def query(name, sql):
        start = perf_counter()
        cursor = db.execute(sql)
        columns = [r[0] for r in cursor.description]
        rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
        report['controls'].append(dict(name=name, sql=sql, rows=rows, seconds=round(perf_counter()-start,3)))
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n')
        print(name, json.dumps(rows[:8], default=str), flush=True)
        return rows
    docs, lines = access.sales('sales_document'), access.sales('sales_line')
    query('sales_header_duplicate_keys', f"SELECT source_system,doc_entry,count(*) n FROM {docs} WHERE source_table='OINV' GROUP BY ALL HAVING count(*)>1")
    db.execute(f'''CREATE TEMP VIEW inv AS SELECT * FROM {docs}
        WHERE source_system='SAP_B1_HANA' AND source_table='OINV' AND canceled='N' AND currency='BS'
        AND doc_date>='2026-10-01' AND doc_date<'2026-11-01' ''')
    db.execute(f'''CREATE TEMP VIEW sales AS SELECT d.card_code,d.doc_date,l.item_code,
        CAST(l.line_total AS DECIMAL(38,6)) amount, CAST(l.quantity AS DECIMAL(38,6)) quantity
        FROM {lines} l JOIN inv d ON d.doc_entry=l.doc_entry AND d.source_system=l.source_system
        WHERE l.source_table='INV1' AND l.currency='BS' ''')
    db.execute('CREATE TEMP VIEW accounts AS SELECT card_code,sum(amount) amount FROM sales GROUP BY card_code')
    query('A01_top5', 'SELECT * FROM accounts ORDER BY amount DESC,card_code LIMIT 5')
    query('A01_concentration', '''WITH ranked AS (SELECT *,row_number() OVER(ORDER BY amount DESC,card_code) rank FROM accounts)
        SELECT count(*) accounts,sum(amount) total,sum(amount) FILTER(WHERE rank<=5) top5,
        100*sum(amount) FILTER(WHERE rank<=5)/sum(amount) pct FROM ranked''')
    query('A02_without_leader', '''WITH ranked AS (SELECT *,row_number() OVER(ORDER BY amount DESC,card_code) rank FROM accounts)
        SELECT sum(amount) FILTER(WHERE rank BETWEEN 2 AND 5) numerator,sum(amount) FILTER(WHERE rank>1) denominator,
        100*sum(amount) FILTER(WHERE rank BETWEEN 2 AND 5)/sum(amount) FILTER(WHERE rank>1) pct FROM ranked''')
    stock = access.oitw()
    query('stock_sources_and_cut', f'SELECT source_system,source_table,min(source_as_of) first_observation,max(source_as_of) last_observation,count(*) positions FROM {stock} GROUP BY ALL')
    db.execute(f'CREATE TEMP VIEW stock AS SELECT item_code,whs_code,CAST(on_hand AS DECIMAL(38,6)) quantity FROM {stock}')
    query('stock_duplicate_keys', 'SELECT item_code,whs_code,count(*) n FROM stock GROUP BY ALL HAVING count(*)>1')
    query('B03_population', 'SELECT count(DISTINCT item_code) products,count(*) positions FROM stock WHERE quantity<0')
    query('B03_first5', 'SELECT DISTINCT item_code FROM stock WHERE quantity<0 ORDER BY item_code LIMIT 5')
    query('B04_negative_positions', '''SELECT * FROM stock WHERE quantity<0 AND item_code IN
        (SELECT DISTINCT item_code FROM stock WHERE quantity<0 ORDER BY item_code LIMIT 5) ORDER BY item_code,whs_code''')
    for name in ('purchase_order','purchase_order_line','purchase_receipt','purchase_receipt_line','ap_invoice'):
        db.execute('CREATE TEMP VIEW '+name+' AS SELECT * FROM '+access.operational_observation('purchasing',name))
    query('purchase_header_duplicate_keys', 'SELECT "DocEntry",count(*) n FROM purchase_order GROUP BY ALL HAVING count(*)>1')
    db.execute('''CREATE TEMP VIEW partial AS SELECT l."DocEntry" order_key,l."LineNum" line_num,
        h."CardCode" vendor,h."CardName" vendor_name,l."ItemCode" item_code,
        CAST(l."Quantity" AS DECIMAL(38,6)) ordered,CAST(l."OpenQty" AS DECIMAL(38,6)) open_qty
        FROM purchase_order_line l JOIN purchase_order h ON h."DocEntry"=l."DocEntry"
        WHERE h."CANCELED"='N' AND l."LineStatus"='O' AND CAST(l."OpenQty" AS DECIMAL(38,6))>0
        AND CAST(l."OpenQty" AS DECIMAL(38,6))<CAST(l."Quantity" AS DECIMAL(38,6))''')
    query('C05_population', 'SELECT count(*) partial_lines FROM partial')
    query('C05_first5', 'SELECT * FROM partial ORDER BY order_key,line_num LIMIT 5')
    query('C06_receipts', '''WITH selected AS (SELECT * FROM partial ORDER BY order_key,line_num LIMIT 5)
        SELECT s.order_key,s.line_num,r."DocEntry" receipt_key,h."DocNum" receipt_number,h."DocDate" receipt_date,
        r."LineNum" receipt_line,r."ItemCode" item_code,r."Quantity" received_quantity,h."CANCELED" canceled
        FROM selected s LEFT JOIN purchase_receipt_line r ON r."BaseEntry"=s.order_key AND r."BaseLine"=s.line_num AND r."BaseType"=22
        LEFT JOIN purchase_receipt h ON h."DocEntry"=r."DocEntry" ORDER BY s.order_key,s.line_num,receipt_key,receipt_line''')
    db.execute('CREATE TEMP VIEW diversity AS SELECT card_code,count(DISTINCT item_code) products,sum(amount) amount FROM sales GROUP BY card_code')
    query('D07_population', 'SELECT count(*) accounts FROM diversity WHERE products>=10')
    query('D07_top5', 'SELECT * FROM diversity WHERE products>=10 ORDER BY products DESC,card_code LIMIT 5')
    credit = access.credit_memo('credit_memo_document')
    query('E08_credit_incidence', f'''WITH credits AS (SELECT DISTINCT card_code FROM {credit}
        WHERE source_system='SAP_B1_HANA' AND source_table='ORIN' AND canceled='N' AND currency='BS'
        AND doc_date>='2026-10-01' AND doc_date<'2026-11-01'), buyers AS (SELECT DISTINCT card_code FROM inv)
        SELECT count(*) denominator,count(*) FILTER(WHERE c.card_code IS NOT NULL) numerator,
        100.0*count(*) FILTER(WHERE c.card_code IS NOT NULL)/count(*) pct FROM buyers b LEFT JOIN credits c USING(card_code)''')
    query('F09_peak_day', '''WITH days AS (SELECT doc_date,sum(amount) amount,count(DISTINCT card_code) accounts FROM sales GROUP BY doc_date)
        SELECT *,100*amount/(SELECT sum(amount) FROM sales) pct FROM days WHERE amount=(SELECT max(amount) FROM days) ORDER BY doc_date''')
    query('G10_zero_amount_population', 'SELECT count(DISTINCT item_code) products,count(*) lines FROM sales WHERE quantity>0 AND amount=0')
    query('G10_first5', 'SELECT item_code,count(*) lines FROM sales WHERE quantity>0 AND amount=0 GROUP BY item_code ORDER BY item_code LIMIT 5')
    db.execute('''CREATE TEMP VIEW sales_stock AS SELECT p.item_code,
        CASE WHEN s.positions IS NULL THEN 'NO_POSITION' ELSE 'ALL_NONPOSITIVE' END status
        FROM (SELECT DISTINCT item_code FROM sales) p LEFT JOIN
        (SELECT item_code,count(*) positions,max(quantity) maximum FROM stock GROUP BY item_code) s USING(item_code)
        WHERE s.positions IS NULL OR s.maximum<=0''')
    query('H11_population', 'SELECT status,count(*) products FROM sales_stock GROUP BY status ORDER BY status')
    for status in ('NO_POSITION','ALL_NONPOSITIVE'):
        query('H11_examples_'+status, f"SELECT * FROM sales_stock WHERE status='{status}' ORDER BY item_code LIMIT 5")
    query('ap_header_duplicate_keys', 'SELECT "DocEntry",count(*) n FROM ap_invoice GROUP BY ALL HAVING count(*)>1')
    db.execute('''CREATE TEMP VIEW ap_vendors AS SELECT "CardCode" vendor,sum(CAST("DocTotal" AS DECIMAL(38,6))) amount
        FROM ap_invoice WHERE "CANCELED"='N' AND "DocCur"='BS' AND "DocDate">='2026-10-01' AND "DocDate"<'2026-11-01' GROUP BY "CardCode"''')
    query('I12_total', 'SELECT count(*) vendors,sum(amount) total FROM ap_vendors')
    query('I12_leader', 'SELECT *,100*amount/(SELECT sum(amount) FROM ap_vendors) pct FROM ap_vendors WHERE amount=(SELECT max(amount) FROM ap_vendors) ORDER BY vendor')
report['status'] = 'CONTROLS_EXECUTED_NOT_BUSINESS_CERTIFICATION'
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n')

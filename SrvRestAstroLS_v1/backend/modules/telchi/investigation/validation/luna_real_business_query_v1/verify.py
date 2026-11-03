"""Independent Decimal recomputation: twelve bounded queries, one thread."""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import threading
import time

from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.exploratory_sql.authorized_foundation import published_file_relation
from modules.telchi.exploratory_sql.foundation import PUBLICATION, SNAPSHOT
from modules.telchi.exploratory_sql.foundation_dev import DevExecutor

ROOT = Path(os.getenv('TELCHI_BUSINESS_EVIDENCE_ROOT','../../data/reports/telchi/luna-real-business-query-v1'))

def main():
    os.umask(0o077)
    start = time.monotonic()
    if (ROOT/'independent.json').exists():
        raise ValueError('independent_evidence_exists')
    luna = json.loads((ROOT/'luna.json').read_text())
    assert any(e.get('action')=='final' for e in luna.get('model_events',[])), 'Luna must answer first'
    report = {'method':'Separate raw rows, Python Decimal and independent classification/customer lookup; no investigative SUM or classification/customer join reused',
              'sql':[], 'months':[], 'checks':{}, 'limitations':[]}
    reader = FoundationReader()
    initial_swap = DevExecutor.swap_bytes()
    with reader.connector.session(read_only=True) as db:
        db.execute('SET threads=1')
        db.execute("SET memory_limit='512MB'")
        db.execute("SET max_temp_directory_size='0B'")
        a = reader.resolve_on(db)
        assert (a.foundation_publication_id,str(a.ducklake_snapshot_id))==(PUBLICATION,SNAPSHOT)
        report['binding']=a.as_dict()
        def fetch(sql,params=()):
            mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
            if int(mem['MemAvailable'].split()[0])*1024<2*1024**3 or DevExecutor.swap_bytes()-initial_swap>=256*1024**2:
                raise RuntimeError('RESOURCE_BLOCKED_memory_or_swap')
            if len(report['sql'])>=12 or time.monotonic()-start>900:
                raise RuntimeError('independent_phase_budget')
            report['sql'].append({'sql':sql,'parameters':params})
            timer=threading.Timer(120,db.interrupt);timer.start()
            try:
                rows=db.execute(sql,params).fetchmany(5001)
                if len(rows)>5000 or len(json.dumps(rows,default=str).encode())>2*1024*1024:
                    raise ValueError('independent_result_budget')
                return rows
            finally:
                timer.cancel();timer.join()
        material=published_file_relation(a,'material_supply','material_supply_status')
        rows=fetch(f'SELECT "ItemCode",is_raw_material,material_class,material_name FROM {material}')
        flags=defaultdict(set)
        for code,flag,cls,name in rows: flags[code].add((flag,cls))
        assert all(len(v)==1 for v in flags.values()), 'conflicting classification'
        assert all(flag==(cls=='RAW_MATERIAL') for v in flags.values() for flag,cls in v)
        codes=sorted(k for k,v in flags.items() if next(iter(v))[0])
        report['classification']={'rows':len(rows),'unique_items':len(flags),'raw_material_items':len(codes),
            'duplicate_item_rows':len(rows)-len(flags),'codes':codes,
            'classes':dict(Counter(next(iter(v))[1] for v in flags.values())),
            'scope':'Current published material supply classification; structural BOM components, not certified complete commercial taxonomy'}
        db.execute('CREATE TEMP TABLE verify_raw_items(item_code VARCHAR PRIMARY KEY)')
        db.executemany('INSERT INTO verify_raw_items VALUES (?)',[(c,) for c in codes])
        docs,lines=a.sales('sales_document'),a.sales('sales_line')
        products=str(a.reference('products')).replace("'","''")
        customers=str(a.reference('customers')).replace("'","''")
        # One bounded metadata query, independent of the investigator projection.
        metadata=fetch(f'''WITH active AS (SELECT * FROM {docs} WHERE source_system='SAP_B1_HANA'
            AND source_table='OINV' AND canceled='N' AND doc_date>='2026-01-01' AND doc_date<'2027-01-01'),
            unclassified AS (SELECT l.currency,count(*) AS n,sum(TRY_CAST(l.line_total AS DECIMAL(38,6))) AS amount
                FROM {lines} l WHERE l.source_system='SAP_B1_HANA' AND l.source_table='INV1'
                AND NOT EXISTS (SELECT 1 FROM {material} m WHERE m."ItemCode"=l.item_code)
                AND EXISTS (SELECT 1 FROM active d WHERE d.doc_entry=l.doc_entry) GROUP BY l.currency)
            SELECT min(doc_date),max(doc_date),min(source_as_of),max(source_as_of),
            (SELECT count(*) FROM read_parquet('{products}') WHERE source_system='SAP_HANA'),
            (SELECT count(*)-count(DISTINCT code) FROM read_parquet('{customers}') WHERE source_system='SAP_HANA'),
            (SELECT to_json(list(struct_pack(currency:=currency,lines:=n,amount:=amount))) FROM unclassified),
            to_json(list(DISTINCT strftime(TRY_CAST(doc_date AS DATE),'%Y-%m'))),
            count(*)-count(DISTINCT doc_entry),
            (SELECT to_json(list(struct_pack(code:=item_code,name:=sap_item_name,grp:=sap_itms_grp_cod)))
                FROM read_parquet('{products}') WHERE source_system='SAP_HANA'
                AND item_code IN (SELECT item_code FROM verify_raw_items)) FROM active''')
        meta=metadata[0]
        assert meta[5]==0 and meta[8]==0, 'duplicate customer or document dimension'
        # Independent business-rule check, NOT the researcher's prejoined view:
        # structural leaf + canonical input group, excluding packaging names.
        from modules.telchi.datalake.product_business_classification import RAW_INPUT_GROUPS,FRACTIONATED_GROUPS,PACKAGING_RE
        product_rows=json.loads(meta[9])
        business_codes=sorted(r['code'] for r in product_rows
            if r['grp'] is not None and int(r['grp']) in (RAW_INPUT_GROUPS|FRACTIONATED_GROUPS)
            and not PACKAGING_RE.search(r['name'] or ''))
        crosswalk=json.loads((ROOT/'business-crosswalk.json').read_text())
        researcher_codes=sorted(r[0] for r in crosswalk['rows'] if r[1]=='RAW_MATERIAL' and r[2]=='VALIDATED')
        assert business_codes==researcher_codes, 'canonical classification discrepancy'
        report['classification']['structural_raw_material_items']=len(codes)
        report['classification']['business_raw_material_items']=len(business_codes)
        report['classification']['business_codes']=business_codes
        report['classification']['excluded_structural_items']=sorted(set(codes)-set(business_codes))
        report['classification']['scope']='PBT-006: published structural leaf plus SAP input/bulk group, excluding packaging; current and limited to published structural universe'
        codes=business_codes
        db.execute('DELETE FROM verify_raw_items')
        db.executemany('INSERT INTO verify_raw_items VALUES (?)',[(c,) for c in codes])
        report['sales_coverage']={'date_min':str(meta[0]),'date_max':str(meta[1]),
            'source_as_of_min':str(meta[2]),'source_as_of_max':str(meta[3]),'months':sorted(json.loads(meta[7]))}
        report['sap_products']=meta[4]
        report['unclassified_sales_lines_2026']=json.loads(meta[6])
        report['customer_duplicate_codes']=meta[5]
        report['header_duplicate_keys']=meta[8]
        monthly,rankings,all_keys={}, {}, set()
        currency_totals=defaultdict(Decimal)
        material_dates=[]
        for month in report['sales_coverage']['months']:
            y,m=map(int,month.split('-'))
            lo=date(y,m,1).isoformat();hi=date(y+(m==12),1 if m==12 else m+1,1).isoformat()
            raw=fetch(f'''SELECT l.doc_entry,l.line_num,l.item_code,l.currency,l.line_total,
                l.raw_extraction_id,l.source_as_of,d.card_code,d.currency AS document_currency,
                CAST(TRY_CAST(d.doc_date AS DATE) AS VARCHAR),d.raw_extraction_id AS document_extraction
                FROM {lines} l JOIN {docs} d ON d.doc_entry=l.doc_entry
                WHERE l.source_system='SAP_B1_HANA' AND l.source_table='INV1'
                AND d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND d.canceled='N'
                AND d.doc_date>=? AND d.doc_date<?
                AND l.item_code IN (SELECT item_code FROM verify_raw_items)''',[lo,hi])
            total=Decimal(0);ranks=defaultdict(Decimal);by_sku=defaultdict(Decimal)
            excluded=defaultdict(Decimal);documents=set();bs_lines=0;dates=[]
            for doc,num,item,ccy,amount,ext,asof,card,dccy,day,dext in raw:
                key=(str(doc),str(num))
                assert key not in all_keys, 'duplicate line or join fanout'
                all_keys.add(key)
                assert ext and asof and ext==dext, 'provenance mismatch'
                assert amount is not None and item in codes
                amount=Decimal(str(amount));currency_totals[str(ccy)]+=amount
                if ccy!='BS':excluded[str(ccy)]+=amount;continue
                assert dccy=='BS', 'incompatible header currency'
                total+=amount;ranks[card]+=amount;by_sku[item]+=amount;documents.add(doc)
                bs_lines+=1;dates.append(day);material_dates.append(day)
            assert total==sum(ranks.values(),Decimal(0))==sum(by_sku.values(),Decimal(0))
            monthly[month]=total;rankings[month]=ranks
            report['months'].append({'month':month,'amount_bs':total,'bs_lines':bs_lines,
                'bs_documents':len(documents),'all_currency_lines':len(raw),
                'excluded_currency_amounts':dict(excluded),'date_min':min(dates,default=None),
                'date_max':max(dates,default=None),'customer_sum_bs':sum(ranks.values(),Decimal(0)),
                'sku_sum_bs':sum(by_sku.values(),Decimal(0))})
        winner=max(monthly,key=monthly.get)
        ranked=sorted(rankings[winner].items(),key=lambda x:(-x[1],str(x[0])))
        db.execute('CREATE TEMP TABLE verify_customer_keys(code VARCHAR PRIMARY KEY)')
        db.executemany('INSERT INTO verify_customer_keys VALUES (?)',[(c,) for c,v in ranked])
        names=fetch(f"SELECT code,name FROM read_parquet('{customers}') WHERE source_system='SAP_HANA' AND code IN (SELECT code FROM verify_customer_keys)")
        name_map=dict(names)
        assert len(name_map)==len(names), 'duplicate billed customer reference'
        report['winner']={'month':winner,'amount_bs':monthly[winner],
            'customer_code':ranked[0][0],'customer_name':name_map.get(ranked[0][0]),'customer_amount_bs':ranked[0][1]}
        report['customer_ranking']=[{'code':c,'name':name_map.get(c),'amount_bs':v} for c,v in ranked]
        report['currency_totals']=dict(currency_totals)
        report['coverage_material_sales']={'min':min(material_dates),'max':max(material_dates)}
        report['checks']={'unique_raw_line_keys':len(all_keys),'duplicate_line_keys':0,
            'header_and_customer_duplicates':0,'classification_conflicts':0,
            'classification_flag_class_agree':True,'independent_customer_and_sku_sums_reconcile':True,
            'no_physical_quantities_summed':True,'queries':len(report['sql'])}
    report['elapsed_seconds']=time.monotonic()-start
    (ROOT/'independent.json').write_text(json.dumps(report,indent=2,default=str,ensure_ascii=False))
    print(json.dumps(report['winner'],default=str,ensure_ascii=False))

if __name__=='__main__':
    with open(f'/tmp/telchi-exploratory-dev-{os.getuid()}.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        main()

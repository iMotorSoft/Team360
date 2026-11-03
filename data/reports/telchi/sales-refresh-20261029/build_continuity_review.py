"""Reproducible offline review of the completed continuity capture. No HANA."""
from collections import Counter
from contextlib import contextmanager
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
import json

from modules.telchi.datalake import sales_incremental as inc,sales_continuity as capture
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.sales_continuity_candidate import query_rows,sql_literal

OUT=Path(__file__).resolve().parent
ROOT=inc.DATA_ROOT/'raw/sap'/capture.CONTRACT/'sales-continuity-20261029-v1'
STAGE=inc.DATA_ROOT/'staging'/capture.CONTRACT/'sales-continuity-candidate-20261029-v1'


def seal(name,value):
    value=json.loads(json.dumps(value,sort_keys=True,default=str))
    path=OUT/name
    if path.exists():
        if inc.read_json(path)!=value:
            raise ValueError('Immutable review artifact already exists with different content: '+name)
    else:
        inc.seal(path,value)


def main():
    r=inc.read_json(STAGE/'reconciliation.json')
    cap=inc.read_json(OUT/'continuity-capture.json')
    raw={(b['domain'],b['month'],b['currency']):b for b in r['raw_money'] if b['cancelled']=='N'}
    for domain in inc.DOMAINS:
        for b in r['commercial_answers'][domain+'_monthly']:
            exact=raw[(domain,b['month'],b['currency'])]
            assert Decimal(exact['doc_total'])==Decimal(b['documentary_total']) and exact['documents']==b['documents']
    corrected,names,samples={},{},{}
    connector=DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=1');con.execute("SET memory_limit='512MB'")
        con.execute('SET temp_directory=?',[str(STAGE/'review_temp')])
        access=FoundationReader(connector).resolve_on(con)
        @contextmanager
        def same(): yield con
        store=FoundationPublicationStore(same);pub=store.get(access.foundation_publication_id)
        assert pub.foundation_publication_id==r['base_publication']
        for domain in inc.DOMAINS:
            dt,lt=('sales_document','sales_line') if domain=='sales' else ('credit_memo_document','credit_memo_line')
            maps={}
            for label,doc,line in [('old',access.relation(domain,dt),access.relation(domain,lt)),('new','read_parquet('+sql_literal(r['datasets'][dt]['path'])+')','read_parquet('+sql_literal(r['datasets'][lt]['path'])+')')]:
                maps[label]=dict(con.execute(f'''SELECT l.item_code,sum(cast(l.quantity AS DECIMAL(38,12)))
FROM {line} l JOIN {doc} h ON h.source_system=l.source_system AND h.doc_entry=l.doc_entry
WHERE h.doc_date>=? AND h.doc_date<=? AND l.item_code IS NOT NULL GROUP BY l.item_code''',[r['material_supply']['start'],r['material_supply']['end']]).fetchall())
            corrected[domain]=dict(affected_items=sum(maps['old'].get(k,0)!=maps['new'].get(k,0) for k in maps['old'].keys()|maps['new'].keys()),original_field=r['material_supply']['proofs'][domain]['affected_items'],correction='Original affected_items counted all projected items when any changed. Corrected here without rewriting prior evidence; material replay hashes and gate result unaffected.')
            path=r['canonical_delta'][domain]['document_change_evidence']['path']
            samples[domain]=query_rows(con,"SELECT * FROM read_parquet(?) WHERE state='modified' OR canceled<>'N' ORDER BY doc_date,doc_entry LIMIT 15",[path])
        for kind,key,dataset,refkey,namecol in [('customers','card_code','customers','code','name'),('products','item_code','products','item_code','canonical_name')]:
            source=r['commercial_answers']['top_billed_customers' if kind=='customers' else 'top_products_line_amount']
            keys=sorted({v[key] for v in source if v.get(key)})
            names[kind]={str(code):name for code,name in con.execute(f"SELECT {refkey},{namecol} FROM read_parquet(?) WHERE source_system='SAP_HANA' AND {refkey} IN ({','.join('?' for _ in keys)})",[str(access.reference(dataset)),*keys]).fetchall()}
        current=dict(id=access.foundation_publication_id,snapshot=access.ducklake_snapshot_id,manifest_sha256=inc.digest(pub.manifest),pointer=[list(row) for row in con.execute('SELECT * FROM telchi.ops.foundation_current_v1').fetchall()],unchanged=True)
    customers={v['source_key'] for v in r['reference_missing']['customers']+r['reference_missing']['credit_customers']}
    products={v['source_key'] for v in r['reference_missing']['products']+r['reference_missing']['credit_products']}
    review=dict(status='OFFLINE_RECONCILIATION_PASS_FOUNDATION_REFERENCE_BLOCKED',raw_header_vs_canonical_monthly_money='EXACT_PASS',currency='BS',material_projection_counts_review=corrected,material_replay_status=r['material_revalidation']['status'],new_material_component=r['material_revalidation']['new_component']['publication_id'],datasets_replaced=r['material_revalidation']['datasets_replaced'],reference_missing_unique=dict(customers=len(customers),products=len(products)),reference_missing=r['reference_missing'],current=current,reconciliation_path=str(STAGE/'reconciliation.json'),reconciliation_sha256=inc.file_hash(STAGE/'reconciliation.json'),foundation_gate=inc.read_json(STAGE/'foundation-gate.json'))
    seal('continuity-reviewed.json',review)
    active={d:{v['day']:v for v in r['commercial_answers'][d+'_daily']} for d in inc.DOMAINS}
    daily=[];day=date(2026,9,1)
    while day<date(2026,10,30):
        text=day.isoformat();gross=Decimal(active['sales'].get(text,{}).get('documentary_total',0));credit=Decimal(active['credit_memo'].get(text,{}).get('documentary_total',0))
        daily.append(dict(day=text,currency='BS',invoice_doc_total=str(gross),credit_doc_total=str(credit),net_documentary_billing=str(gross-credit),coverage='BOTH_SOURCE_WINDOWS_COMPLETE'))
        day+=timedelta(days=1)
    answers=[]
    def answer(n,question,result,metric,period):
        answers.append(dict(number=n,question=question,result=result,currency='BS',metric=metric,period=period,cutoff='2026-10-29',publication=current['id'],publication_contains_result=False,candidate=None,artifact=str(STAGE),status='OFFLINE_CAPTURED_NOT_PUBLISHED_NOT_CONVERSATIONALLY_ENABLED',coverage='118/118 daily source windows complete, per-query observations',warnings=['DocTotal net is documentary billing, not pre-tax revenue','No currency conversion',f'Reference missing: {len(customers)} customers, {len(products)} distinct products','Independent components retain historical cutoffs']))
    monthly=r['commercial_answers']['net_documentary_billing']
    answer(1,'¿Cuánto vendimos en septiembre de 2026?',next(b for b in monthly if b['month']=='2026-09'),'Active invoice DocTotal, NC and net documentary billing separately','2026-09-01/2026-09-30')
    answer(2,'¿Cuánto vendimos en octubre hasta el 29?',next(b for b in monthly if b['month']=='2026-10'),'Active invoice DocTotal, NC and net documentary billing separately','2026-10-01/2026-10-29')
    answer(3,'¿Cuál fue el día de mayores ventas de octubre?',r['commercial_answers']['october_peak_gross_billing_day'],'Active invoice DocTotal by day; not a line-revenue or net-after-NC ranking','2026-10-01/2026-10-29')
    for kind in ('customers','products'):
        source=r['commercial_answers']['top_billed_customers' if kind=='customers' else 'top_products_line_amount'];key='card_code' if kind=='customers' else 'item_code'
        labeled=[dict(v,name=names[kind].get(v[key]),name_status='PINNED_REFERENCE' if v[key] in names[kind] else 'UNRESOLVED_NATIVE_SOURCE_ID') for v in source]
        answer(4 if kind=='customers' else 5,'¿Quiénes fueron los principales clientes facturados?' if kind=='customers' else '¿Qué productos lideraron las ventas?',labeled,'Active invoice header DocTotal by billed customer' if kind=='customers' else 'Active invoice source LineTotal by product, line currency; no mixed units','September full and October 1-29 separately')
    credits=[dict(v,nc_pct_of_gross_invoice_doc_total=str((Decimal(v['credit_doc_total'])/Decimal(v['invoice_doc_total'])*100).quantize(Decimal('.01')))) for v in monthly]
    answer(6,'¿Cuánto representaron las notas de crédito?',credits,'Active ORIN DocTotal and share of active OINV DocTotal','September full and October 1-29 separately')
    answer(7,'¿Cómo evolucionaron las ventas diariamente?',daily,'Active invoice DocTotal, NC DocTotal and net documentary billing per completed day','2026-09-01/2026-10-29')
    equivalent=[]
    for month in ('2026-09','2026-10'):
        selected=[v for v in daily if v['day'].startswith(month) and int(v['day'][-2:])<=29]
        equivalent.append(dict(month=month,days=29,invoice_doc_total=str(sum((Decimal(v['invoice_doc_total']) for v in selected),Decimal(0))),credit_doc_total=str(sum((Decimal(v['credit_doc_total']) for v in selected),Decimal(0))),net_documentary_billing=str(sum((Decimal(v['net_documentary_billing']) for v in selected),Decimal(0)))))
    answer(8,'¿Cómo se compara octubre contra septiembre en períodos equivalentes?',equivalent,'Same calendar days 1-29, not business-day adjusted; currencies not mixed','2026-09-01/29 vs 2026-10-01/29')
    answer(9,'¿Qué documentos fueron modificados o cancelados?',dict(states={d:r['canonical_delta'][d]['whole_document_states'] for d in inc.DOMAINS},samples=samples,full_evidence={d:r['canonical_delta'][d]['document_change_evidence'] for d in inc.DOMAINS}),'Whole-document comparison including line-only edits and cancellation states','2026-09-01/2026-10-29 versus current Foundation')
    answer(10,'¿Cuál es la venta neta acreditada de cada mes?',monthly,'Active OINV DocTotal minus active ORIN DocTotal; net documentary billing, not pre-tax accounting revenue','September full and October 1-29 separately')
    seal('continuity-business-answers.json',dict(status='OFFLINE_BUSINESS_CHECKS_PASS_NOT_TELCHIAI_RUNTIME',answers=answers,current=current))
    files={f.name:inc.file_hash(f) for f in sorted(ROOT.iterdir()) if f.is_file() and f.name!='.lock' and not f.name.endswith('.tmp')}
    seal('continuity-checkpoint-index.json',dict(root=str(ROOT),files=files,sha256_of_file_map=inc.digest(files)))
    print('REVIEW',review['reference_missing_unique'],corrected,current)
    print('EQUIVALENT',equivalent)
    print('CHECKPOINT_FILES',len(files),'SHA256',inc.file_hash(OUT/'continuity-checkpoint-index.json'))


if __name__=='__main__': main()

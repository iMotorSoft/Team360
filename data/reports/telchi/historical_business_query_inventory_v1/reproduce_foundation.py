"""Audit-only reproduction of historical registry; no SAP/runtime calls or writes."""
import sys,json,re,hashlib,time
from pathlib import Path
from decimal import Decimal,InvalidOperation
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parents[3]/'SrvRestAstroLS_v1/backend'))
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
REG=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_DIRECT_BUSINESS_QUERY_VALIDATION_V1')
registry=json.loads((REG/'query_registry.json').read_text());old={r['query_id']:r for r in json.loads((REG/'sap_ducklake_results.json').read_text())}
discovery=json.loads((REG/'summary.json').read_text())['DISCOVERY']
log={'read_only':True,'sap_accessed':False,'queries':[],'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'budget':{'threads':2,'memory_limit':'512MB','temp_limit':'0B','concurrency':1}}
if (OUT/'foundation_reproduction.json').exists():
 previous=json.loads((OUT/'foundation_reproduction.json').read_text())
 log['queries']=[q for q in previous['queries'] if q['status']=='EXECUTED_CURRENT_READ_ONLY']
def dump(): (OUT/'foundation_reproduction.json').write_text(json.dumps(log,indent=2,default=str,ensure_ascii=False)+'\n')
def params(qid,p,sql):
 if not sql.count('?'):return []
 if qid in ['sales_exact_document','sales_document_lines','sales_cancellation_status']:
  return [int(old[qid]['parts'][0]['DuckLake_result'][0]['doc_entry'])]
 if qid=='oinm_exact_movement':return [discovery['move']['TRANS_NUM'],discovery['move']['TRANS_SEQ']]
 if qid.startswith('oitw_'):
  scope=next(x['scope'] for x in old[qid]['parts'] if x['part_id']==p['part_id'])
  if qid=='oitw_onhand_bounded_aggregate':return scope.split('(')[1].split(')')[0].split(',')
  return [re.search(r'ItemCode=([^,; ]+)',scope)[1],re.search(r'WhsCode=([^,; ]+)',scope)[1]] if sql.count('?')==2 else [re.search(r'(?:ItemCode|WhsCode)=([^,; ]+)',scope)[1]]
 out=['2026-01-01','2026-09-16']
 scope=next(x['scope'] for x in old[qid]['parts'] if x['part_id']==p['part_id'])
 # Bind remaining placeholders in SQL predicate order from preserved scope/discovery.
 if sql.count('?')>2:
  if re.search(r'm\.trans_type\s*=\?',sql):out.append(str(discovery['move']['TRANS_TYPE']))
  elif re.search(r'(?:substr\([^)]*\)|(?:h|m)\.doc_date)\s*=\?',sql):out.append(re.search(r'DocDate=([^; ]+)',scope)[1])
  else:
   for key,col in [('ItemCode','item_code'),('CardCode','card_code'),('WhsCode','whs_code'),('Warehouse','warehouse')]:
    if re.search(r'\.'+col+r'\s*=\?',sql):out.append(re.search((r'(?:WhsCode|Warehouse)' if key=='WhsCode' else key)+r'=([^,; ]+)',scope)[1])
 if len(out)!=sql.count('?'):raise ValueError('unresolved_historical_params')
 return out
try:
 connector=DuckLakeConnector()
 if not connector.data_path.is_dir():raise RuntimeError('existing_data_path_required')
 with connector.session(read_only=True) as con:
  con.execute('SET threads=2');con.execute("SET memory_limit='512MB'");con.execute("SET max_temp_directory_size='0B'")
  assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()==(True,)
  access=FoundationReader(connector).resolve_on(con);log['current']=access.as_dict()
  assert access.foundation_publication_id=='foundation_afd08d9eca6a725be53cdc3f9d5709c9' and access.ducklake_snapshot_id==1408
  relations={t:access.relation(c,t) for c,ts in [('sales',['sales_document','sales_line']),('oinm',['inventory_movement']),('oitw',['inventory_balance'])] for t in ts}
  for q in registry:
   for p in q['parts']:
    if any(e['query_id']==q['query_id'] and e['part_id']==p['part_id'] for e in log['queries']):continue
    entry={'query_id':q['query_id'],'part_id':p['part_id'],'historical_sql':p['DuckLake_SQL'],'semantic_reservation':q['definition']}
    try:
     sql=p['DuckLake_SQL']
     for name,relation in relations.items():sql=sql.replace('telchi.atomic."'+name+'"',relation)
     ps=params(q['query_id'],p,sql);entry.update(sql=sql,params=ps,sql_sha256=hashlib.sha256(sql.encode()).hexdigest())
     start=time.monotonic();cursor=con.execute(sql,ps);names=[x[0] for x in cursor.description];rows=[dict(zip(names,row)) for row in cursor.fetchall()];entry.update(status='EXECUTED_CURRENT_READ_ONLY',rows=rows,row_count=len(rows),elapsed_ms=round(1000*(time.monotonic()-start),3))
    except Exception as e:entry.update(status='UNRESOLVED',error_class=type(e).__name__)
    log['queries'].append(entry);dump()
   print(q['query_id'],[e['status'] for e in log['queries'] if e['query_id']==q['query_id']],flush=True)
except Exception as e:log['error_class']=type(e).__name__
dump()

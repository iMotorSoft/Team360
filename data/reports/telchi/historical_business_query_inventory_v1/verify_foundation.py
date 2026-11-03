"""Bounded read-only CURRENT inspection, never SAP, ingestion or publication."""
import sys, json, time, hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent
BACKEND=OUT.parents[3]/'SrvRestAstroLS_v1/backend'
sys.path.insert(0,str(BACKEND))
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

def records(c):
 names=[x[0] for x in c.description];return [dict(zip(names,r)) for r in c.fetchall()]
result={'read_only':True,'sap_accessed':False,'threads':2,'memory_limit':'512MB','queries':[]}
try:
 connector=DuckLakeConnector()
 if not connector.data_path.is_dir():raise RuntimeError('existing_data_path_required')
 with connector.session(read_only=True) as con:
  con.execute('SET threads=2');con.execute("SET memory_limit='512MB'");con.execute("SET max_temp_directory_size='0B'")
  if con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()!=(True,):raise RuntimeError('read_only_not_confirmed')
  access=FoundationReader(connector).resolve_on(con)
  result['current']=access.as_dict();result['manifest']=access.manifest
  tables={}
  for component,names in [('sales',['sales_document','sales_line']),('credit_memo',['credit_memo_document','credit_memo_line']),('oinm',['inventory_movement']),('oitw',['inventory_balance']),('receivables_collections',['receivable_settlement_status','collection_method_fact','commercial_term_classification'])]:
   for name in names:
    try:
     rel=access.relation(component,name);tables[name]=rel
     result.setdefault('schemas',{})[name]=records(con.execute(f'DESCRIBE SELECT * FROM {rel}'))
    except Exception as e:result.setdefault('schema_errors',{})[name]=type(e).__name__
  for name in ['products','customers','warehouses','sellers','unit_of_measure','entity_aliases']:
   try:
    path=access.reference(name);rel="read_parquet('"+str(path).replace("'","''")+"')";tables[name]=rel
    result.setdefault('reference_schemas',{})[name]=records(con.execute(f'DESCRIBE SELECT * FROM {rel}'))
   except Exception as e:result.setdefault('reference_errors',{})[name]=type(e).__name__
  result['relations']=tables
except Exception as e:
 result['error_class']=type(e).__name__
(OUT/'foundation_current_inspection.json').write_text(json.dumps(result,indent=2,default=str,ensure_ascii=False)+'\n')
print(json.dumps({k:result[k] for k in ['current','schema_errors','reference_errors','error_class'] if k in result},default=str))

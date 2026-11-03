"""Bounded audit probes over sealed CURRENT facts. Not executable capabilities."""
import sys,json,time,hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parents[3]/'SrvRestAstroLS_v1/backend'))
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
result={'queries':[],'read_only':True,'sap_accessed':False,'purpose':'Historical portability checks; figures are tied to publication, not current SAP.'}
if (OUT/'foundation_business_cases.json').exists():
 result=json.loads((OUT/'foundation_business_cases.json').read_text())
try:
 connector=DuckLakeConnector();assert connector.data_path.is_dir()
 with connector.session(read_only=True) as con:
  con.execute('SET threads=2');con.execute("SET memory_limit='512MB'");con.execute("SET max_temp_directory_size='0B'")
  assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()==(True,)
  a=FoundationReader(connector).resolve_on(con);result['current']=a.as_dict()
  assert a.foundation_publication_id=='foundation_afd08d9eca6a725be53cdc3f9d5709c9' and a.ducklake_snapshot_id==1408
  h=a.sales('sales_document');l=a.sales('sales_line');products="read_parquet('"+str(a.reference('products'))+"')";customers="read_parquet('"+str(a.reference('customers'))+"')"
  def probe(name,sql,params=(),basis=None):
   if any(e['probe_id']==name and e['status']=='EXECUTED_CURRENT_READ_ONLY' for e in result['queries']):return
   entry=dict(probe_id=name,sql=sql,params=params,semantic_basis=basis,sql_sha256=hashlib.sha256(sql.encode()).hexdigest())
   try:
    start=time.monotonic();c=con.execute(sql,params);cols=[x[0] for x in c.description];entry.update(status='EXECUTED_CURRENT_READ_ONLY',rows=[dict(zip(cols,r)) for r in c.fetchall()],elapsed_ms=round(1000*(time.monotonic()-start),3))
   except Exception as e:entry.update(status='UNRESOLVED',error_class=type(e).__name__)
   result['queries'].append(entry)
   (OUT/'foundation_business_cases.json').write_text(json.dumps(result,indent=2,default=str,ensure_ascii=False)+'\n')
   print(name,entry['status'],flush=True)
  probe('sales_coverage',f'SELECT MIN(doc_date) AS first_date,MAX(doc_date) AS last_date,COUNT(*) AS documents,COUNT(DISTINCT source_system) AS source_systems FROM {h}',basis='Census runner MIN/MAX; maximum documentary date is not complete-month certification.')
  probe('sales_months',f'SELECT substr(doc_date,1,7) AS month,COUNT(*) AS documents,MIN(doc_date) AS first_date,MAX(doc_date) AS last_date FROM {h} WHERE doc_date>=? GROUP BY 1 ORDER BY 1 DESC LIMIT 12',['2026-01-01'],basis='Coverage by document date; rows do not certify completeness.')
  probe('latest_sales_documents',f'SELECT source_system,doc_entry,doc_num,doc_date,card_code,currency,doc_total,canceled FROM {h} ORDER BY doc_date DESC,TRY_CAST(doc_entry AS BIGINT) DESC LIMIT 10',basis='Historical source sample ORDER BY DocDate DESC, adapted to pinned facts. DocDate is not ingestion chronology.')
  probe('calenta_products',f"SELECT item_code,source_system,canonical_product_id,product_name,inventory_uom_id,sales_uom_id,sap_sell_item FROM {products} WHERE upper(product_name) LIKE ? ORDER BY item_code LIMIT 30",['%CALENTA%'],basis='Name contains matching identifies candidates, not an approved alias/family resolver.')
  probe('calenta_customers',f"SELECT code,name,source_system FROM {customers} WHERE upper(name) LIKE ? ORDER BY code LIMIT 10",['%CALENTA%'],basis='No matches does not prove absence in all historical sources.')
  probe('may_document_amounts',f"SELECT currency,canceled,COUNT(*) AS documents,SUM(TRY_CAST(doc_total AS DECIMAL(38,6))) AS document_total FROM {h} WHERE doc_date>=? AND doc_date<? GROUP BY currency,canceled ORDER BY currency,canceled",['2026-05-01','2026-06-01'],basis='DocTotal by currency/status; not LineTotal, net after credits, cash collected or product attribution.')
  probe('may_calenta_native_lines',f"SELECT p.item_code,p.product_name,p.sales_uom_id,h.currency,h.canceled,COUNT(*) AS lines,SUM(TRY_CAST(l.quantity AS DECIMAL(38,10))) AS source_quantity,SUM(TRY_CAST(l.line_total AS DECIMAL(38,10))) AS source_line_total FROM {h} h JOIN {l} l ON l.source_system=h.source_system AND l.doc_entry=h.doc_entry JOIN {products} p ON p.source_system=l.source_system AND p.item_code=l.item_code WHERE h.doc_date>=? AND h.doc_date<? AND upper(p.product_name) LIKE ? GROUP BY ALL ORDER BY p.item_code,h.currency,h.canceled LIMIT 30",['2026-05-01','2026-06-01','%CALENTA%'],basis='Registry sales_by_item adapted to bounded period with explicit source keys; quantities remain native, sales UoM is reference and not documentary proof.')
  probe('calenta_exact_skus_may',f"SELECT l.item_code,h.currency,h.canceled,COUNT(*) AS lines,SUM(TRY_CAST(l.quantity AS DECIMAL(38,10))) AS native_quantity,SUM(TRY_CAST(l.line_total AS DECIMAL(38,10))) AS native_line_total FROM {h} h JOIN {l} l ON l.source_system=h.source_system AND l.doc_entry=h.doc_entry WHERE h.doc_date>=? AND h.doc_date<? AND l.item_code IN ('L02822','L02823','L02877','L03035','L03648','L03649','L03650','L03658') GROUP BY ALL ORDER BY l.item_code,h.currency,h.canceled",['2026-05-01','2026-06-01'],basis='Exact SKU evidence from SAP_HANA Reference. Native Atomic namespace SAP_B1_HANA differs: no blind source_system join to Reference.')
  probe('calenta_aliases',"SELECT entity_type,canonical_id,alias,alias_source,resolution_status FROM read_parquet('"+str(a.reference('entity_alias'))+"') WHERE upper(alias) LIKE ? LIMIT 30",['%CALENTA%'],basis='Sealed alias candidates: contains match is not one resolved commercial family.')
  for name in ['salespersons','units_of_measure','entity_alias','brand','portfolio_family']:
   try:
    rel="read_parquet('"+str(a.reference(name))+"')";result.setdefault('reference_schemas',{})[name]=[dict(zip(['name','type','nullable','key','default','extra'],r)) for r in con.execute(f'DESCRIBE SELECT * FROM {rel}').fetchall()]
   except Exception as e:result.setdefault('reference_errors',{})[name]=type(e).__name__
  # Inspect sealed manifest datasets using metadata and bounded rows, never glob or latest.
  for component in ['purchasing','material_supply']:
   for name,d in a.manifest['components'][component]['datasets'].items():
    paths=d.get('file_references') or []
    if not paths:continue
    assert all(Path(p).is_file() for p in paths)
    rel='read_parquet('+json.dumps(paths).replace('"',"'")+')'
    probe(component+'_'+name+'_metadata',f'DESCRIBE SELECT * FROM {rel}',basis='Exact sealed manifest file references; schema-only mapping, not validation of business query.')
  probe('published_collections_sample',f'SELECT payment_date,currency,collection_method,effective_amount_local,cancelled,source_as_of FROM {a.receivables_collections("collection_method_fact")} ORDER BY payment_date DESC LIMIT 5',basis='Published method-component fact. Not invoice payment/application or sum per payment.')
  probe('published_receivables_sample',f'SELECT document_id,customer_code,currency,open_amount_local,settlement_state,source_as_of FROM {a.receivables_collections("receivable_settlement_status")} LIMIT 5',basis='Published receivable balances. Historical as-of reconstruction requires separate contract.')
except Exception as e:result['error_class']=type(e).__name__
(OUT/'foundation_business_cases.json').write_text(json.dumps(result,indent=2,default=str,ensure_ascii=False)+'\n')

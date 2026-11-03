"""Credit only reports naming SQL artifacts and declaring all N/N contracts executed.
Documentary execution is separate from exact registry/hash validation.
"""
import csv,json,re,hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];INV=ROOT/'SrvRestAstroLS_v1/backend/modules/telchi/investigation'
def load(n):return list(csv.DictReader((OUT/n).open()))
def save(n,rows):
 with (OUT/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
q=load('questions_master.csv');s=load('sql_master.csv');links=load('question_sql_links.csv');chains=[]
maptables={'OINV':'sales_document','INV1':'sales_line','ORIN':'credit_memo_document','RIN1':'credit_memo_line','OITW':'inventory_balance','OINM':'inventory_movement','OWHS':'reference/warehouses','OITM':'reference/products','OCRD':'reference/customers_or_suppliers','OPOR':'purchasing/purchase_order','POR1':'purchasing/purchase_order_line','OPDN':'purchasing/purchase_receipt','PDN1':'purchasing/purchase_receipt_line','OPCH':'purchasing/ap_invoice','PCH1':'purchasing/ap_invoice_line'}
for p in sorted(INV.rglob('*.md')):
 text=p.read_text();lines=text.splitlines();proof=[(i,l) for i,l in enumerate(lines,1) if re.search(r'SQL.*contracts?.*ejecut',l,re.I) and 'PASS' in l]
 sqlpaths=list(dict.fromkeys(re.findall(r'sql/current/[\w/.-]+\.sql',text)))
 if not proof or not sqlpaths:continue
 count=re.search(r'(\d+)/(\d+)',proof[0][1])
 if not count or int(count[1])!=int(count[2]) or int(count[1])!=len(sqlpaths):continue
 doc=str(p.relative_to(ROOT));report_questions=[x for x in q if x['source_reference']==doc and x['source_location']=='1']
 if not report_questions:
  title=lines[0].lstrip('# ').strip();qid='HQ-'+hashlib.sha256((doc+'|1|'+title).encode()).hexdigest()[:18]
  item={k:'' for k in q[0]};item.update(question_id=qid,original_question=title,normalized_intent='RESEARCH_OBJECTIVE',business_domain='PRODUCCION',source_reference=doc,source_location='1',extraction_kind='explicit_report_objective',lexical_variant_id='QV-'+hashlib.sha256(title.casefold().encode()).hexdigest()[:18])
  q.append(item);report_questions=[item]
 date=re.search(r'(?:Date|Fecha|date)[^\n]*?(202\d-\d\d-\d\d)',text)
 for rel in sqlpaths:
  actual=INV/rel
  if not actual.is_file():continue
  src=str(actual.relative_to(ROOT));matches=[x for x in s if x['source_reference']==src and x['extraction_kind']=='sql_file']
  assert len(matches)==1;sql=matches[0];ev=doc+':'+str(proof[0][0]);artifactline=next(i for i,l in enumerate(lines,1) if rel in l)
  known=sorted({v for k,v in maptables.items() if re.search(r'\b'+k+r'\b',sql['sql_text'])});missing=sorted({x for x in re.findall(r'"?TELCHI"?\."([A-Z0-9_]+)"',sql['sql_text']) if x not in maptables})
  sql.update(validation_status='SQL ejecutado con reservas',semantic_status='HISTORICAL',execution_evidence=ev,historical_result=doc,validity_period='Report date: '+(date[1] if date else 'UNKNOWN')+'; universo/período en informe fuente',business_rules='Contrato SQL ejecutado declarado por informe N/N + artefacto explícito; ver conclusiones y limitaciones del reporte.',known_gaps='Ejecución declarada documental; no hash SQL de aquella corrida. SQL actual con mismo path no garantiza misma versión. '+('Fuentes sin mapping: '+','.join(missing) if missing else 'Traducción/semántica por query pendiente.'),foundation_mapping=' | '.join(known),foundation_readiness='REQUIRES_SOURCE' if missing else 'REQUIRES_MAPPING',notes='REPORT_DECLARED_CONTRACT_EXECUTION; no se atribuye resultado numérico exacto a cada contrato SQL.')
  qids=[]
  for question in report_questions:
   qids.append(question['question_id']);question.update(semantic_status='HISTORICAL',execution_evidence=ev,historical_result=doc,known_gaps='Objetivo de investigación respaldado por informe y contratos SQL; no pregunta ejecutiva directamente habilitada.',foundation_readiness='HISTORICAL_ONLY')
   l=dict(question_id=question['question_id'],sql_id=sql['sql_id'],association_type='EXPLICIT_REPORT_OBJECTIVE_SQL_ARTIFACT',source_reference=doc,source_location=artifactline,validation_evidence=ev)
   if not any(x['question_id']==l['question_id'] and x['sql_id']==l['sql_id'] and x['association_type']==l['association_type'] for x in links):links.append(l)
  chains.append(dict(research_objective_question_ids='|'.join(qids),report=doc,report_execution_line=proof[0][0],report_execution_claim=proof[0][1],sql_id=sql['sql_id'],sql_path=src,artifact_line=artifactline,historical_results=doc,result_attribution='REPORT_LEVEL_NOT_PER_SQL_NUMERIC_RESULT',validation_level='DECLARED_N_OF_N_SQL_CONTRACT_EXECUTION',current_mapping_candidates='|'.join(known),sources_not_mapped='|'.join(missing),foundation_readiness=sql['foundation_readiness']))
byq={x['question_id']:set(filter(None,x['sql_reference'].split('|'))) for x in q};bys={x['sql_id']:set(filter(None,x['question_ids'].split('|'))) for x in s}
for l in links:byq[l['question_id']].add(l['sql_id']);bys[l['sql_id']].add(l['question_id'])
for x in q:x['sql_reference']='|'.join(sorted(byq[x['question_id']]))
for x in s:x['question_ids']='|'.join(sorted(bys[x['sql_id']]))
save('questions_master.csv',q);save('sql_master.csv',s);save('question_sql_links.csv',links);save('research_chains.csv',chains)
print('reports',len({x['report'] for x in chains}),'SQL contracts',len(chains),'links',len(links))

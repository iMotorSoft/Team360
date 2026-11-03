"""Offline knowledge inventory. Reads sources; writes only its own report directory.
No imports of investigation code, DB, models, SAP or application runtime.
"""
from pathlib import Path
import ast, csv, hashlib, json, re, os, gzip, subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
INV=ROOT/'SrvRestAstroLS_v1/backend/modules/telchi/investigation'
EXT=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi')
LEG=Path('/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience')
LLM=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/LlmFit/benchmarks/telchi')
TEXT={'.md','.py','.sql','.json','.jsonl','.csv','.tsv','.yaml','.yml','.txt','.sha256','.diff'}
SKIP={'.git','.venv','venv','node_modules','site-packages','__pycache__','.pytest_cache'}
BUS=re.compile(r'vent|vend|sales|factur|invoice|compr|purchas|stock|invent|rotaci|cobert|coverage|cr[eé]dit|deud|debt|cobran|collection|recep|receipt|producci|production|materi|material|vendedor|salesperson|sucursal|branch|almac[eé]n|warehouse|transfer|estacion|season|proyec|forecast|payment|pago|reconcil|cliente|customer|proveedor|supplier|BOM|recet|descuent|discount|usuario|user|permiso|permission|tesorer|treasury|contab|account|calenta|producto|product|cancel|lead.?time',re.I)
DOMAIN=[('VENTAS',r'vent|vend|sales|factur|invoice|descuent|discount'),('INVENTARIOS',r'stock|invent|warehouse|almac|rotaci|transfer|reposici|replenish'),('COMPRAS',r'compr|purchas|recep|receipt|proveedor|supplier|lead.?time|abastec'),('CREDITO_COBRANZAS',r'cr[eé]dit|deud|debt|cobran|collection|payment|pago|aging|receivable'),('PRODUCCION',r'producci|production|BOM|recet|materi|material|capacity'),('PRODUCTOS',r'producto|product|unit|uom|equival|clasif|calenta'),('ADMINISTRACION',r'usuario|user|permiso|permission|role|office|calidad'),('CONTABILIDAD',r'contab|account|treasury|tesorer|balance|cash.flow'),('FORECAST',r'estacion|season|forecast|proyecc')]
errors=[]; files=[]; questions={}; sqls={}; links=[]; evidences=[]; refs=[]; content_hashes=defaultdict(list)

def ref(p):
 try:return str(p.relative_to(ROOT))
 except ValueError:return str(p)
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def clean(s):
 # Do not publish credentials accidentally embedded in examples/logs.
 s=re.sub(r'(?i)(password|passwd|api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*[\"\']?[^\s,;\"\']+',r'\1=[REDACTED]',s)
 s=re.sub(r'(?i)(postgres(?:ql)?://[^:\s]+:)[^@\s]+@',r'\1[REDACTED]@',s)
 s=re.sub(r'\bsk-[A-Za-z0-9_-]{15,}\b','[REDACTED]',s)
 return s
def domains(s):return '|'.join(d for d,pat in DOMAIN if re.search(pat,s,re.I)) or 'TRANSVERSAL'
def qadd(p,loc,s,kind,context='',native=None):
 if not isinstance(s,str) or not s.strip() or len(s)>2500:return None
 s=clean(s.strip()); key=(ref(p),str(loc),s)
 qid='HQ-'+sha('|'.join(key))[:18]
 if qid in questions:return qid
 questions[qid]=dict(question_id=qid,original_question=s,normalized_intent=None,business_domain=domains(s+' '+context),source_reference=ref(p),source_location=str(loc),source_native_id=native,extraction_kind=kind,lexical_variant_id='QV-'+sha(re.sub(r'\s+',' ',s.casefold()))[:18],sql_reference=None,sql_engine=None,source_system=None,execution_evidence=None,historical_result=None,semantic_status='UNRESOLVED',known_gaps='No se acredita cadena completa mediante coincidencia temática.',foundation_mapping=None,foundation_readiness='UNRESOLVED',query_family=None,business_priority=None,notes='Redacción preservada; clasificación automática es índice de revisión, no validación.')
 return qid
SQL_START=re.compile(r'^\s*(?:(?:--[^\n]*(?:\n|$)|/\*.*?\*/)\s*)*(SELECT\b|WITH\s+\w+\s+AS\b|WITH\s+\w+\s*\(|CREATE\b|INSERT\b|UPDATE\b|DELETE\b|ALTER\b|DROP\b)',re.I|re.S)
def sadd(p,loc,s,kind,engine=None):
 if not isinstance(s,str) or (not SQL_START.search(s) and kind!='sql_file'):return None
 s=clean(s.strip()); sid='HS-'+sha(ref(p)+'|'+str(loc)+'|'+s)[:18]
 if sid in sqls:return sid
 norm=re.sub(r'\s+',' ',s.strip()).casefold()
 tables=sorted(set(re.findall(r'\b(?:FROM|JOIN)\s+([\w."{}]+)',s,re.I)))
 structural=bool(re.search(r'^\s*(CREATE|INSERT|UPDATE|DELETE|ALTER|DROP)',s,re.I))
 eng=engine or ('HANA' if re.search(r'"?TELCHI"?\."[A-Z]|ADD_DAYS|DAYS_BETWEEN|TO_NVARCHAR',s) else 'DuckDB/DuckLake' if re.search(r'telchi\.(atomic|business|ops)|read_parquet|ducklake_|duckdb_',s,re.I) else 'UNRESOLVED')
 status='SQL histórico' if 'legacy' in str(p).lower() else 'SQL ilustrativo' if kind=='markdown_block' else 'SQL propuesto'
 sqls[sid]=dict(sql_id=sid,question_ids=None,source_reference=ref(p),source_location=str(loc),extraction_kind=kind,sql_engine=eng,source_system='SAP_HANA' if eng=='HANA' else 'Foundation_or_DataLake_UNCONFIRMED' if eng=='DuckDB/DuckLake' else None,sql_text=s,sql_sha256=sha(s),lexical_sql_group='SD-'+sha(norm)[:18],business_domain=domains(str(p)+' '+s),statement_role='TECHNICAL_DDL_DML_NOT_EXECUTED' if structural else 'READ_QUERY',tables='|'.join(tables),columns='|'.join(sorted({a+'.'+b for a,b in re.findall(r'(\b\w+)\."?(\w+)"?',s)})),joins=' | '.join(re.findall(r'\bJOIN\s+.*?(?=\b(?:WHERE|GROUP BY|ORDER BY|JOIN|LEFT JOIN|INNER JOIN)\b|$)',s,re.I|re.S)),filters=clause(s,'WHERE'),metrics=' | '.join(re.findall(r'\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\([^)]*\)',s,re.I)),grain=None,groupings=clause(s,'GROUP BY'),orderings=clause(s,'ORDER BY'),potential_parameters='|'.join(sorted(set(re.findall(r'\{[^}]+\}|\?|:\w+',s)))),business_rules=None,execution_evidence=None,historical_result=None,validity_period=None,validation_status=status,semantic_status='UNRESOLVED',known_gaps='No atribuir ejecución por existencia del código; dialecto/fuentes inferidos.',foundation_mapping=None,foundation_readiness='UNRESOLVED',notes='Plantilla con expresiones no resueltas.' if '{' in s else '')
 return sid
def clause(s,k):
 m=re.search(r'\b'+k+r'\b(.*?)(?=\b(?:GROUP BY|ORDER BY|HAVING|LIMIT|UNION)\b|$)',s,re.I|re.S)
 return m.group(1).strip() if m else None
def strings(node):
 if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
 if isinstance(node,ast.JoinedStr):return ''.join(v.value if isinstance(v,ast.Constant) and isinstance(v.value,str) else '{'+ast.unparse(v.value)+'}' for v in node.values)
 if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):
  a,b=strings(node.left),strings(node.right)
  return a+b if a is not None and b is not None else None
 return None

def scan_json(p,x,ptr='$'):
 if isinstance(x,dict):
  for k,v in x.items():
   loc=ptr+'/'+str(k)
   if isinstance(v,str):
    if SQL_START.search(v):sadd(p,loc,v,'json_sql','HANA' if k.upper()=='SAP_SQL' else 'DuckDB/DuckLake' if k.upper()=='DUCKLAKE_SQL' else None)
    if k.lower() in {'business_question','example_question','question','original_question','user_message','user_text','prompt','query_text'} :qadd(p,loc,v,'structured_question',str(p),x.get('query_id') or x.get('id'))
    elif k.lower()=='text' and BUS.search(v) and ('?' in v or re.match(r'(?i)^(dame|mostra|ventas|stock|cuanto|cu[aá]l|quiero|necesito)',v)) and len(v)<300:qadd(p,loc,v,'conversation_candidate',str(p))
   elif isinstance(v,(dict,list)):scan_json(p,v,loc)
  # Keep exact result/validation pointers, not a blanket PASS for all SQL in file.
  if any(k in x for k in ['gate','gate_id','FINAL_RESULT','status','validation_status','result_hash']):
   state={k:clean(str(x[k]))[:800] for k in ['gate','gate_id','FINAL_RESULT','status','validation_status','result_hash','query_id','part_id','period','cutoff','foundation_publication_id','ducklake_snapshot_id'] if k in x}
   if state:evidences.append(dict(source_reference=ref(p),source_location=ptr,attributes=json.dumps(state,ensure_ascii=False)))
 elif isinstance(x,list):
  for i,v in enumerate(x):
   if isinstance(v,(dict,list)):scan_json(p,v,ptr+'/'+str(i))

def walk(root,exclude=False):
 result=[]
 def err(e):errors.append(dict(path=e.filename,error=type(e).__name__))
 if not root.exists():errors.append(dict(path=str(root),error='MISSING_ROOT'));return result
 for d,dirs,names in os.walk(root,onerror=err,followlinks=False):
  if exclude:dirs[:]=[n for n in dirs if n not in SKIP]
  for n in names:
   p=Path(d)/n
   if p.is_symlink():errors.append(dict(path=ref(p),error='SYMLINK_NOT_FOLLOWED'));continue
   if n in {'.env','postgres.env'} or p.suffix in {'.key','.pem'}:continue
   result.append(p)
 return sorted(result)

def scan(p,phase):
 try:
  st=p.stat();h=hashlib.sha256()
  with p.open('rb') as stream:
   for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
  digest=h.hexdigest();content_hashes[digest].append(ref(p))
  row=dict(path=ref(p),phase=phase,file_type=p.suffix or '[none]',size_bytes=st.st_size,modified_at=datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),sha256=digest,business_domain=domains(str(p)),function='SQL ejecutable candidato' if p.suffix=='.sql' else 'Artefacto generado' if p.suffix=='.pyc' else 'Catálogo de preguntas' if 'catalog' in p.name else 'Evidencia de pruebas/resultados' if p.suffix in {'.json','.jsonl','.csv','.tsv'} else 'Documentación arquitectónica / investigación empresarial' if p.suffix=='.md' else 'Implementación / validación' if p.suffix=='.py' else 'Otros',inspection='METADATA_AND_HASH',questions_detected=0,sql_detected=0,validation_references=None,duplicate_group=None)
  files.append(row)
  if p.suffix not in TEXT:return
  text=p.read_text(encoding='utf-8');row['inspection']='FULL_TEXT_SCANNED'
  nq,ns=len(questions),len(sqls)
  if p.suffix=='.py':
   tree=ast.parse(text);parents={ch:n for n in ast.walk(tree) for ch in ast.iter_child_nodes(n)}
   for n in ast.walk(tree):
    s=strings(n)
    if s is None:continue
    par=parents.get(n)
    if isinstance(par,(ast.JoinedStr,ast.BinOp,ast.FormattedValue)):continue
    if SQL_START.search(s):sadd(p,n.lineno,s,'python_string_expression')
    elif BUS.search(s) and len(s)<500 and ('¿' in s or '?' in s or re.match(r'(?i)^(dame|mostra|cu[aá]nt|ventas de|[uú]ltimas ventas)',s)):qadd(p,n.lineno,s,'python_question_literal',str(p))
  elif p.suffix=='.sql':sadd(p,1,text,'sql_file')
  elif p.suffix=='.md':
   blocks=[]
   for m in re.finditer(r'```(?:sql|SQL|hana|postgresql|duckdb)\s*\n(.*?)```',text,re.S):
    loc=text[:m.start()].count('\n')+2;sadd(p,loc,m.group(1),'markdown_block');blocks.append((m.start(),m.end()))
   headings=[];in_code=False
   for lineno,line in enumerate(text.splitlines(),1):
    if line.startswith('```'):in_code=not in_code;continue
    if in_code:continue
    m=re.match(r'^(#{1,6})\s+(.*)',line)
    if m:
     heading=m.group(2);headings.append((lineno,heading))
     if BUS.search(heading) and not re.search(r'(?i)source|archivo|gate|root|arquitect|contract|contrato|referenc|implement|status|readme|promoci|promotion|prueba|test',heading):qadd(p,lineno,heading,'business_heading_candidate',str(p))
    for match in re.finditer(r'¿[^?\n]{3,500}\?',line):
     if BUS.search(match.group()):qadd(p,lineno,match.group(),'documented_question',str(p))
    if re.match(r'(?i)^\s*(?:[-*>]\s*)?(?:objetivo|pregunta|business question|investigar|determinar|verificar|analizar|ventas del|[uú]ltimas ventas)\b',line) and BUS.search(line):qadd(p,lineno,line,'business_objective_candidate',str(p))
   for m in re.finditer(r'\[[^\]]*\]\(([^)]+)\)',text):
    dest=m.group(1).split('#')[0]
    if not dest or re.match(r'https?://|app://|mailto:',dest):continue
    target=Path(dest) if dest.startswith('/') else p.parent/dest
    refs.append(dict(source_reference=ref(p),source_location=text[:m.start()].count('\n')+1,target=ref(target.resolve()),exists=target.exists(),kind='markdown_link'))
  elif p.suffix in {'.csv','.tsv'}:
   for i,r in enumerate(csv.DictReader(text.splitlines(),delimiter='\t' if p.suffix=='.tsv' else ','),2):
    for k,v in r.items():
     if isinstance(v,str) and k and (k.lower() in {'business_question','example_question','question','original_question','question_text'}):qadd(p,f'row:{i}/{k}',v,'catalog_question',str(p),r.get('query_id') or r.get('question_id') or r.get('gate_id'))
     if isinstance(v,str) and SQL_START.search(v):sadd(p,f'row:{i}/{k}',v,'csv_sql')
  elif p.suffix=='.json':scan_json(p,json.loads(text))
  elif p.suffix=='.jsonl':
   for i,line in enumerate(text.splitlines(),1):
    if line.strip():scan_json(p,json.loads(line),f'line:{i}')
  elif p.suffix in {'.yaml','.yml','.txt'}:
   for i,line in enumerate(text.splitlines(),1):
    for m in re.finditer(r'¿[^?\n]{3,500}\?',line):
     if BUS.search(m.group()):qadd(p,i,m.group(),'text_question',str(p))
  row['questions_detected']=len(questions)-nq;row['sql_detected']=len(sqls)-ns
 except Exception as e:
  errors.append(dict(path=ref(p),error=type(e).__name__))
  if files and files[-1]['path']==ref(p):files[-1]['inspection']='ERROR_'+type(e).__name__

# Required order: complete investigation scan before expansion.
for p in walk(INV):scan(p,'A_INVESTIGATION')
print('investigation scanned',len(files),'questions',len(questions),'sql',len(sqls),flush=True)
related=set(walk(ROOT/'SrvRestAstroLS_v1/backend/modules/telchi'))|set(walk(ROOT/'data/reports/telchi'))
discovery=subprocess.run(['rg','-l','-i','telchi|foundation_afd08d9eca6a725be53cdc3f9d5709c9|calenta',*sum((['--glob','*'+ext] for ext in ['.md','.py','.json','.jsonl','.csv','.sql','.yaml','.yml','.tsv']),[]),'.'],cwd=ROOT,capture_output=True,text=True)
if discovery.returncode not in (0,1):raise RuntimeError('repository_discovery_failed')
related|={ROOT/line.strip().removeprefix('./') for line in discovery.stdout.splitlines()}
for p in sorted(related):
 if OUT in p.parents or INV in p.parents or p.suffix=='.pyc':continue
 scan(p,'G_REPOSITORY_EXTENSION')
for p in walk(EXT):scan(p,'G_EXTERNAL_EVIDENCE')
for p in walk(LLM,True):
 if p.suffix in TEXT:scan(p,'G_EXTERNAL_LLMFIT')
for p in walk(LEG,True):
 if p.suffix in {'.py','.sql','.md','.csv','.json','.yaml','.yml'}:scan(p,'G_EXTERNAL_LEGACY_SOURCE')
print('expanded',len(files),'questions',len(questions),'sql',len(sqls),'errors',len(errors),flush=True)
# Strict explicit associations: direct validation registry and its results.
regp=EXT/'TELCHI_DATALAKE_DIRECT_BUSINESS_QUERY_VALIDATION_V1/query_registry.json'
rsp=regp.parent/'sap_ducklake_results.json'
registry=json.loads(regp.read_text());results={r['query_id']:r for r in json.loads(rsp.read_text())}
for i,r in enumerate(registry):
 qid=qadd(regp,f'$/{i}/business_question',r['business_question'],'structured_question',r['domain'],r['query_id']);q=questions[qid]
 rr=results.get(r['query_id']);q['normalized_intent']=r['query_id'];q['query_family']=r['domain'];q['source_system']='SAP_HANA|DuckLake';q['sql_engine']='HANA|DuckDB/DuckLake'
 q['semantic_status']='CONDITIONAL';q['known_gaps']='EXACT valida fidelidad source-native en el corte; no valida venta neta, UoM agregable o CURRENT.';q['notes']=r['definition'];q['execution_evidence']=ref(rsp)+f'/$/{i}' if rr else None;q['historical_result']=q['execution_evidence'];q['foundation_readiness']='HISTORICAL_ONLY'
 sids=[]
 for j,part in enumerate(r['parts']):
  rp=next((x for x in (rr or {}).get('parts',[]) if x['part_id']==part['part_id']),None)
  for k,eng in [('SAP_SQL','HANA'),('DuckLake_SQL','DuckDB/DuckLake')]:
   sid=sadd(regp,f'$/{i}/parts/{j}/{k}',part[k],'json_sql',eng);s=sqls[sid];sids.append(sid)
   ev=ref(rsp)+f'/$/{i}/parts/{j}'
   exact=rp and rp.get('status')=='EXACT' and rp.get('SAP_result_hash')==rp.get('DuckLake_result_hash') and rp.get('SAP_result_hash')
   s.update(question_ids=qid,grain=r.get('source_identity_drilldown'),business_rules=r['definition'],validity_period=r.get('scope'),execution_evidence=ev if rp else None,historical_result=ev+'/'+('SAP_result' if k=='SAP_SQL' else 'DuckLake_result') if rp else None,validation_status='SQL ejecutado con reservas' if exact else 'SQL histórico',semantic_status='CONDITIONAL',foundation_readiness='HISTORICAL_ONLY',notes='EXACT por hashes y drilldown; agregación Quantity source-native no asegura compatibilidad física.',source_system='SAP_HANA' if k=='SAP_SQL' else 'DuckLake historical baseline')
   links.append(dict(question_id=qid,sql_id=sid,association_type='EXPLICIT_QUERY_REGISTRY_PART',source_reference=ref(regp),source_location=f'$/{i}/parts/{j}',validation_evidence=ev if exact else None))
 q['sql_reference']='|'.join(sids)
# Other links only if SQL and question share the same Markdown section, not domain matches.
for f in files:
 if f['file_type']!='.md' or not f['inspection'].startswith('FULL'):continue
 p=ROOT/f['path'] if not f['path'].startswith('/') else Path(f['path'])
 headings=[(i,line) for i,line in enumerate(p.read_text().splitlines(),1) if re.match(r'^#{1,6} ',line)]
 def section(line):return max((i for i,_ in headings if i<=line),default=0)
 for s in [s for s in sqls.values() if s['source_reference']==f['path']]:
  for q in [q for q in questions.values() if q['source_reference']==f['path']]:
   if str(s['source_location']).isdigit() and str(q['source_location']).isdigit() and section(int(s['source_location']))==section(int(q['source_location'])):
    links.append(dict(question_id=q['question_id'],sql_id=s['sql_id'],association_type='SAME_EXPLICIT_MARKDOWN_SECTION_NOT_EXECUTION',source_reference=f['path'],source_location=s['source_location'],validation_evidence=None))
# Preserve lexical duplicates, never label them semantically equivalent.
for f in files:
 if len(content_hashes[f['sha256']])>1:f['duplicate_group']='FD-'+f['sha256'][:18]
byq=defaultdict(set);bys=defaultdict(set)
for l in links:byq[l['question_id']].add(l['sql_id']);bys[l['sql_id']].add(l['question_id'])
for qid,ids in byq.items():questions[qid]['sql_reference']='|'.join(sorted(ids))
for sid,ids in bys.items():sqls[sid]['question_ids']='|'.join(sorted(ids))
def writecsv(name,rows,fields=None):
 rows=list(rows)
 with (OUT/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]) if rows else fields or ['empty']);w.writeheader();w.writerows(rows)
writecsv('physical_inventory.csv',files)
writecsv('questions_master.csv',questions.values())
writecsv('sql_master.csv',sqls.values())
writecsv('question_sql_links.csv',links)
writecsv('evidence_index.csv',evidences)
writecsv('reference_integrity.csv',refs)
writecsv('duplicate_files.csv',[dict(group='FD-'+h[:18],sha256=h,paths=json.dumps(paths,ensure_ascii=False),count=len(paths)) for h,paths in content_hashes.items() if len(paths)>1])
manifest=dict(inventory_date=datetime.now(timezone.utc).isoformat(),branch='feature/console-backend-core',head='09d2ec715a31bb88574d734eacb9f437f008624e',entity='TELCHI',stage='INVESTIGATION',write_scope=ref(OUT),directories=sorted({str(Path(f['path']).parent) for f in files}),counts_by_phase=dict(Counter(f['phase'] for f in files)),counts_by_type=dict(Counter(f['file_type'] for f in files)),counts_by_function=dict(Counter(f['function'] for f in files)),counts_by_directory=dict(Counter(str(Path(f['path']).parent) for f in files)),questions=len(questions),distinct_exact_wordings=len({q['lexical_variant_id'] for q in questions.values()}),questions_by_extraction=dict(Counter(q['extraction_kind'] for q in questions.values())),sql_occurrences=len(sqls),sql_lexical_groups=len({s['lexical_sql_group'] for s in sqls.values()}),sql_by_validation=dict(Counter(s['validation_status'] for s in sqls.values())),read_sql=sum(s['statement_role']=='READ_QUERY' for s in sqls.values()),question_sql_links=len(links),explicit_historically_validated_questions=len(registry),errors=errors,broken_markdown_links=[r for r in refs if not r['exists']],exclusions=[dict(scope='investigation/**/*.pyc',reason='Inventariados y hash; bytecode no interpretado como fuente nueva.'),dict(scope='external legacy dependency/venv/native/data files',reason='No son documentación empresarial; source y catálogos sí inspeccionados.'),dict(scope='Data Root Parquet',reason='Sin scan documental ni copia; únicamente metadata/esquemas mediante reader CURRENT en fase H.'),dict(scope='compressed .gz external evidence',reason='Inventariados/hash; contenido comprimido pendiente de inspección.'),dict(scope='PRIVATE_ROOT / credentials',reason='No se inventarían secretos; connector oficial sólo si fase H necesita acceso autorizado a Foundation.')],external_roots=[dict(path=str(p),accessible=p.is_dir()) for p in [EXT,LEG,LLM]],semantic_completeness='PARTIAL: extracción amplia automática; candidatos de títulos y objetivos requieren revisión; no conteo exacto de intents empresariales.',sap_accessed=False,source_modifications=0)
(OUT/'coverage_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:manifest[k] for k in ['counts_by_phase','questions','distinct_exact_wordings','questions_by_extraction','sql_occurrences','sql_lexical_groups','sql_by_validation','question_sql_links','explicit_historically_validated_questions']},ensure_ascii=False,indent=2))

"""Artifact integrity gate: references, IDs, counts, evidence and source hashes.
No application tests/models/SAP are run; this is the focal test for the audit scope.
"""
import csv,json,hashlib,re,time
from pathlib import Path
from collections import Counter
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
def rows(name):return list(csv.DictReader((OUT/name).open()))
def file(ref):return Path(ref) if ref.startswith('/') else ROOT/ref
checks=[]
def check(name,condition,details=None):checks.append(dict(check=name,status='PASS' if condition else 'FAIL',details=details))
q=rows('questions_master.csv');s=rows('sql_master.csv');links=rows('question_sql_links.csv');p=rows('physical_inventory.csv');fam=rows('family_membership.csv');ops=rows('verified_operations.csv');m=json.loads((OUT/'coverage_manifest.json').read_text());summary=json.loads((OUT/'audit_summary.json').read_text())
qi={x['question_id']:x for x in q};si={x['sql_id']:x for x in s}
check('QUESTION_IDS_UNIQUE',len(qi)==len(q));check('SQL_IDS_UNIQUE',len(si)==len(s));check('SOURCE_FILE_REFERENCES_EXIST',all(file(x['source_reference']).is_file() for x in q+s))
check('LINK_FOREIGN_KEYS',all(x['question_id'] in qi and x['sql_id'] in si for x in links));check('LINKS_UNIQUE',len({(x['question_id'],x['sql_id'],x['association_type']) for x in links})==len(links))
check('COUNTS_CONSISTENT',len(q)==m['questions']==summary['questions_occurrences'] and len(s)==m['sql_occurrences']==summary['sql_occurrences'] and len(links)==m['question_sql_links'] and len(p)==sum(m['counts_by_phase'].values()))
check('FAMILY_IDS_EXIST',all(x['family_id'] in {'F'+str(i).zfill(2) for i in range(1,27)} for x in fam))
for rootname,n,ids in [('datalake_ceo_query_semantics_and_performance_contract_v1',74,{'Q'+str(i).zfill(3) for i in range(1,75)}),('datalake_product_and_operating_model_contract_v2',8,{'Q-V2-'+str(i).zfill(3) for i in range(1,9)})]:
 src='SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/'+rootname+'/ceo_query_catalog.csv';actual=[r for r in q if r['source_reference']==src];check('CEO_CATALOG_'+rootname,len(actual)==n and {r['source_native_id'] for r in actual}==ids)
inv=ROOT/'SrvRestAstroLS_v1/backend/modules/telchi/investigation';actual={str(x.relative_to(ROOT)) for x in inv.rglob('*') if x.is_file()};scanned={x['path'] for x in p if x['phase']=='A_INVESTIGATION'}
check('INVESTIGATION_PHYSICAL_COVERAGE',actual==scanned,{'actual':len(actual),'scanned':len(scanned),'missing':sorted(actual-scanned),'unexpected':sorted(scanned-actual)})
check('ALL_SQL_FILES_REPRESENTED',{str(x.relative_to(ROOT)) for x in inv.rglob('*.sql')}=={x['source_reference'] for x in s if x['extraction_kind']=='sql_file' and x['source_reference'].startswith(str(inv.relative_to(ROOT)))})
for x in q+s:
 loc=x['source_location']
 if loc.isdigit():
  if int(loc)>len(file(x['source_reference']).read_text().splitlines()):checks.append(dict(check='LINE_REFERENCE',status='FAIL',details=x.get('question_id') or x.get('sql_id')))
check('SQL_HASHES_MATCH_EXTRACTED_TEXT',all(hashlib.sha256(x['sql_text'].encode()).hexdigest()==x['sql_sha256'] for x in s))
resultspath=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_DIRECT_BUSINESS_QUERY_VALIDATION_V1/sap_ducklake_results.json');historical=json.loads(resultspath.read_text())
check('HISTORICAL_EXACT_PART_HASHES',len(historical)==30 and all(part['status']=='EXACT' and part['SAP_result_hash']==part['DuckLake_result_hash'] and part.get('source_identity_drilldown') for r in historical for part in r['parts']))
r=json.loads((OUT/'foundation_reproduction.json').read_text());c=json.loads((OUT/'foundation_current_inspection.json').read_text())
check('CURRENT_REFERENCE_PIN_CONFIRMED',c['current']['foundation_publication_id']=='foundation_afd08d9eca6a725be53cdc3f9d5709c9' and c['current']['ducklake_snapshot_id']==1408 and c['current']['manifest_base_snapshot_id']==1322)
check('CURRENT_REPRODUCTION_COVERAGE',len(r['queries'])==35 and len({x['query_id'] for x in r['queries']})==30 and all(x['status']=='EXECUTED_CURRENT_READ_ONLY' for x in r['queries']))
check('READY_OPERATIONS_HAVE_CURRENT_EXECUTION',all(x['current_execution_status']=='EXECUTED_CURRENT_READ_ONLY' and x['current_evidence'] for x in ops if x['reuse_status'].startswith('READY')))
check('REPRODUCED_RELATIONS_PINNED',all('AT (VERSION => 1408)' in x['sql'] and not re.search(r'\b(?:INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b',x['sql'],re.I) for x in r['queries']))
check('DOCUMENTARY_CONTRACT_EVIDENCE',len(rows('research_chains.csv'))==24 and len({x['report'] for x in rows('research_chains.csv')})==8 and all(file(x['report']).is_file() and x['sql_id'] in si for x in rows('research_chains.csv')))
# Scan only actual credential patterns; symbols/env names are not secrets.
secrets=[]
patterns=[r'\bsk-[A-Za-z0-9_-]{20,}\b',r'(?i)postgres(?:ql)?://[^\s:\"\']+:[^\s@\[\"\']+@',r'(?i)\bBearer\s+eyJ[A-Za-z0-9_-]{30,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
for f in OUT.iterdir():
 if f.is_file() and f.suffix in {'.csv','.json','.md'}:
  t=f.read_text()
  for pat in patterns:
   if re.search(pat,t):secrets.append({'file':f.name,'pattern':pat})
check('NO_CREDENTIAL_PATTERNS_IN_DELIVERABLES',not secrets,secrets)
# Rehash inspected sources sequentially. Changes by other writers are reported, never reverted.
changes=[];missing=[]
for f in p:
 path=file(f['path'])
 try:
  digest=hashlib.sha256()
  with path.open('rb') as stream:
   for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
  if digest.hexdigest()!=f['sha256']:changes.append(f['path'])
 except OSError:missing.append(f['path'])
check('INSPECTED_SOURCE_HASHES_UNCHANGED',not changes and not missing,{'changed_sources':changes,'missing_sources':missing})
required=['INVENTORY_REPORT.md','questions_master.csv','sql_master.csv','question_sql_links.csv','query_families.md','foundation_readiness.csv','business_semantics.md','telchiai_priority_matrix.md','unresolved_questions.md','coverage_manifest.json','executive_query_reuse.md']
check('REQUIRED_DELIVERABLES_EXIST',all((OUT/x).is_file() for x in required))
# Markdown local links within reports also checked, because LAT may omit reports scope.
broken=[]
for doc in OUT.glob('*.md'):
 for dest in re.findall(r'\[[^\]]*\]\(([^)]+)\)',doc.read_text()):
  target=dest.split('#')[0]
  if target and not re.match(r'https?://',target) and not (doc.parent/target).exists():broken.append({'doc':doc.name,'target':dest})
check('REPORT_MARKDOWN_LINKS_RESOLVE',not broken,broken)
result=dict(checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),status='PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL',checks=checks,own_service_processes_created=0,source_changes=changes)
(OUT/'validation_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
raise SystemExit(result['status']!='PASS')

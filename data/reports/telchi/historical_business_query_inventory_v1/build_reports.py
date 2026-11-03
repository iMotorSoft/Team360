"""Assemble evidence-backed audit reports; reads inventory and historical artifacts only."""
from pathlib import Path
import csv,json,hashlib,re
from collections import Counter,defaultdict
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
MOD='SrvRestAstroLS_v1/backend/modules/telchi/';INV=MOD+'investigation/'
def loadcsv(n):return list(csv.DictReader((OUT/n).open(encoding='utf-8')))
def writecsv(n,rows,fields=None):
 rows=list(rows)
 with (OUT/n).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def md(n,s):(OUT/n).write_text(s.strip()+'\n',encoding='utf-8')
def link(p):return f'[{Path(p).name}]({p if p.startswith("/") else "../../../../"+p})'
def h(s):return hashlib.sha256(s.encode()).hexdigest()
qs=loadcsv('questions_master.csv');ss=loadcsv('sql_master.csv');ls=loadcsv('question_sql_links.csv');physical=loadcsv('physical_inventory.csv')
m=json.loads((OUT/'coverage_manifest.json').read_text());current=json.loads((OUT/'foundation_current_inspection.json').read_text());rep=json.loads((OUT/'foundation_reproduction.json').read_text());probes=json.loads((OUT/'foundation_business_cases.json').read_text())
regpath='/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_DIRECT_BUSINESS_QUERY_VALIDATION_V1/query_registry.json'
reg=json.loads(Path(regpath).read_text());rids={r['query_id']:r for r in reg}
ready={'sales_exact_document','sales_document_lines','sales_cancellation_status','oinm_exact_movement','oinm_source_drilldown','oitw_exact_item_warehouse','oitw_same_item_multiple_warehouses','oitw_warehouse_sample','oitw_commitments_orders'}
conditional={'sales_by_item','oinm_item_history','oinm_item_warehouse','oinm_multi_trans_item','cross_item_sales_movements','cross_item_warehouse_activity','cross_high_sales_item_movement_context','cross_warehouse_activity','cross_item_warehouse_activity_control'}
# cross_warehouse_activity has mixed-item quantity: requires definition, unlike single-SKU parts.
conditional.remove('cross_warehouse_activity')
readiness={k:'READY_FOUNDATION' if k in ready else 'READY_CONDITIONAL' if k in conditional else 'REQUIRES_METRIC_DEFINITION' for k in rids}
# Normalize at operation-family level only after extraction; membership is a proposed grouping.
F=[
 ('F01','Documentos y líneas comerciales',r'sales_exact_document|sales_document_lines|document contents|multi.line document|documento.*l[ií]neas','sql/current/sales/sales_v1_linenum.sql','docs/query_catalog.md','sales_document + sales_line, snapshot 1408','READY_FOUNDATION','DocEntry; source_system; LineNum; límite','Hechos nativos por documento, sin excluir estados ni interpretar venta neta.'),
 ('F02','Ventas por período y comparación',r'sales_daily|sales_monthly|sales_ytd|vendimos (hoy|ayer|este)|ventas.*mes|ventas.*mayo|ventas.*septiembre|factur.*mes','sql/current/seasonality/sales_monthly_v1.sql','FINANCIAL_REPORTING_CONTRACT.md','sales + credit_memo; DocTotal o LineTotal según métrica','REQUIRES_METRIC_DEFINITION','desde/hasta; moneda; status; métrica; baseline','Separar importe documental, importe de línea y neto; comparación requiere misma cobertura.'),
 ('F03','Ventas por cliente',r'sales_by_customer|sales by customer|vendimos a|ventas.*cliente|vend.*Farmacia','sql/current/sales/sales_v1_linenum.sql','docs/TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1.md','sales_document.card_code; Reference customers.code','REQUIRES_MAPPING','CardCode; período; métrica','No sumar cantidades de múltiples productos; resolver namespace y aliases.'),
 ('F04','Ventas por producto y presentación',r'sales_by_item|sales by item|vendimos de|ventas.*producto|calenta|creolina','sql/current/sales/sales_v1_linenum.sql','docs/product_seasonality_v1_report.md','sales_line.item_code; products.item_code; namespaces diferentes','READY_CONDITIONAL','SKU exacto; período; importe línea o cantidad nativa','Calenta es conjunto de candidatos de producto; cantidades por SKU, no suma kg/unidades.'),
 ('F05','Ventas por almacén y ubicación comercial',r'sales_by_warehouse|sales warehouse|ventas.*sucursal|vend.*Segundo Anillo','sql/current/sales/sales_v1_linenum.sql','validation/sales_dimensions/SALES_DIMENSIONS_FINAL_REPORT.md','sales_line.whs_code; Reference warehouses/business_locations','REQUIRES_MAPPING','WhsCode o ubicación validada; período; métrica','WhsCode no equivale a sucursal; warehouse planeado/documental/físico separados.'),
 ('F06','Vendedores, canales y venta corporativa',r'corporat|horizontal|vendedor|salesperson|canal de ventas','sql/current/masters/master_oslp.sql','validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md','executive_sales.corporate_sales_by_salesperson; salespersons','READY_CONDITIONAL','año/mes; categoría vendedor validada','DocTotal BS activo menos NC BS por SlpCode; no generalizar al total ni canal por transacción.'),
 ('F07','Rankings de productos y clientes',r'sales_top_items|top items|m[aá]s vendidos|top ItemCode|ranking|rankings|top \d+','sql/current/seasonality/sales_monthly_v1.sql','docs/query_catalog.md','sales_line + product; Quantity, importe o net_qty diferenciados','REQUIRES_METRIC_DEFINITION','métrica; UoM; período; top N; desempate','Top Quantity fuente no certifica comparación entre productos ni ventas netas.'),
 ('F08','Últimas operaciones comerciales',r'[uú]ltimas ventas|[uú]ltimas transacciones|latest sales|[uú]ltimos documentos','sql/current/sales/sales_v1_linenum.sql','validation/datalake_direct_business_query_validation_v1/runner.py','sales_document.doc_date; doc_entry orden determinista','READY_CONDITIONAL','fecha relevante; límite; entidad; status','DocDate no es instante de ingreso; no existe timestamp de registro demostrado.'),
 ('F09','Cobertura temporal y último mes',r'[uú]ltimo mes|last month|cobertura temporal|census|fecha.*m[aá]xima|[uú]ltima fecha','sql/current/atomic_inventory_and_sales/sales_extract_v1.sql','validation/datalake_2026_census_and_coverage_reconciliation_v1/runner.py','MIN/MAX doc_date por entidad/métrica; source_as_of separado','READY_CONDITIONAL','entidad; métrica; publicación; completitud requerida','Máxima fecha 2026-09-24; septiembre tiene datos, no mes completo certificado.'),
 ('F10','Cancelaciones y notas de crédito',r'cancel|anulad|credit.note|notas de cr[eé]dito','sql/current/credit_notes/credit_notes_v1_linenum.sql','docs/cancellation_findings.md','sales y credit_memo; canceled; base_type/base_entry/base_line','READY_CONDITIONAL','documento; tipo; período; evento','Original Y y reversa C preservados; NC positivas raw y signo según cálculo.'),
 ('F11','Stock actual y disponibilidad',r'oitw_|onhand|on.hand|available|disponib|stock position|stock actual','sql/current/stock/item_stock_position_v1.sql','docs/material_stock_position_v1_report.md','inventory_balance + stock_availability; inventario UoM','READY_FOUNDATION','SKU; WhsCode; source_as_of; UoM','Detalle por SKU/almacén; disponible=on_hand-is_commited; on_order separado.'),
 ('F12','Movimientos y trazabilidad de inventario',r'oinm_|movimientos|movement|transferencias|transfer trace','sql/current/inventory_movements/inventory_current_v1.sql','validation/inventory_movements/TRANSTYPE_MAP_FINAL_REPORT.md','inventory_movement, snapshot 1408; TransNum+TransSeq','READY_CONDITIONAL','clave fuente; SKU; warehouse; trans_type; período','InQty/OutQty separados; no inferir causalidad por item/fecha.'),
 ('F13','Rotación, cobertura y reposición',r'rotaci|inmoviliz|sin movimiento|high.stock|low.sales|replenish|reposici','sql/current/coverage/fg_usable_stock_v1.sql','docs/telchi_branch_replenishment_daily_stock_demand_v1_report.md','stock + sales + demanda/cobertura; sidecars comerciales no CURRENT','REQUIRES_METRIC_DEFINITION','SKU; ventana; propósito comercial; demanda válida','Consumo interno no venta externa; stockout censura demanda; faltan unidades comparables.'),
 ('F14','Órdenes, recepciones y facturas de compra',r'purchase chain|cadena.*compr|ordered|received|invoiced|[oó]rdenes de compra|recepciones parciales|purchase_document','sql/current/purchases/purchase_document_chain_v1.sql','docs/telchi_purchase_to_warehouse_receipt_reconciliation_v1_report.md','purchasing manifest: 6 fuentes + lineage + receipt inventory','READY_CONDITIONAL','proveedor; SKU; línea; período; path/cancelación','BaseType/BaseEntry/BaseLine; multi-recepción y out_of_coverage explícitos.'),
 ('F15','Abastecimiento, origen y lead time',r'lead.?time|proveedores|importaci|abastec|purchases by|compras locales','sql/current/lead_time/purchase_lead_time_event_v1.sql','docs/purchase_lead_time_v1_report.md','purchasing + material_supply.material_lead_time_profile','READY_CONDITIONAL','origen LF/LP/IMP/SAA; primera/última recepción; proveedor','DocDate lead time no prueba tiempo físico; Country no basta para importación.'),
 ('F16','Excepciones y diferencias de compras',r'invoiced.without|sin recepci|AP direct|purchase risk|riesgo.*compr','sql/current/purchases/ap_invoice_v1.sql','docs/telchi_ap_invoiced_without_warehouse_receipt_v1_report.md','purchasing_document_lineage + purchase_inventory_receipt','READY_CONDITIONAL','línea AP; evidencia OC/GR/OINM; causa; límites cobertura','AP directa no equivale a ausencia física; separar evidencias de categorías causales.'),
 ('F17','Deuda actual, aging y riesgo abierto',r'open risk|aging|saldo|vencid|open amount|current_ar|moros','sql/current/financial/ar/current_ar_v1.sql','docs/credit_open_risk_aging_v1_report.md','receivable_settlement_status, snapshot base 1322','READY_CONDITIONAL','cliente; as_of publicación; vencimiento; moneda','Saldo publicado no necesariamente reconstrucción histórica arbitrary as_of.'),
 ('F18','Crédito, excepciones y deuda histórica',r'cr[eé]dito aprobado|credit limit|cr[eé]dito|historical debt|as.of|autorizaci','sql/current/financial/ar/settlement_aggregation_v1.sql','docs/credit_exception_cases_v1_report.md','receivables; clientes credit_limit; fuentes históricas settlement','REQUIRES_MAPPING','cliente/grupo económico; instante; límite; reconciliación','Configuración de límite no prueba autorización; no hay historia suficiente de grants.'),
 ('F19','Cobranzas, pagos y aplicación',r'cobran|collection|pagos|payment application|aplicaci[oó]n de pagos','sql/current/financial/payment_application_v1.sql','docs/traceability_cash_accounting_h4_v1_report.md','collection_method_fact + receivable_settlement_status','READY_CONDITIONAL','fecha pago; método; cliente; documento; moneda','Componente de medio de pago no pago único; RCT2 no autoridad settlement histórica Telchi.'),
 ('F20','Producción y consumo real',r'production|producci|consumo.*materia|[oó]rdenes.*producci','sql/current/equivalence/production_consumed_v1.sql','docs/production_component_consumption_v1_report.md','material_supply.material_actual_consumption; BOM/source production parcial','REQUIRES_SOURCE','orden; componente; emisión/recibo real; período','BOM planificada no emisión real; no inferir producción desde venta.'),
 ('F21','Recetas, equivalencia y capacidad',r'BOM|recet|equival|producible|capacidad|capacity','sql/current/capacity/fg_component_requirement_v1.sql','docs/max_producible_by_component_v1_report.md','material_supply.material_equivalent_demand; stock; requisitos BOM','REQUIRES_MAPPING','producto terminado; componente; factor; UoM; capacidad','Equivalencia/densidad autorizada y dependencias multi-nivel; no suma kg/L.'),
 ('F22','Productos, clasificación y unidades',r'clasific|fraccion|materias primas|productos propios|product business|operating model|units|unidades','sql/current/stock/item_master_v1.sql','docs/TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1.md','Reference products/UoM; semántica comercial candidata no CURRENT','REQUIRES_MAPPING','SKU; propósito; vigencia; producto propio/tercero','Brand UNKNOWN; SellItem no basta para uso externo; no inventar clase desde código.'),
 ('F23','Estacionalidad, forecast y demanda',r'estacion|season|forecast|proyecci|demanda','sql/current/seasonality/sales_monthly_v1.sql','docs/product_seasonality_v1_report.md','sales + credit_memo; historia documentada parcial','REQUIRES_METRIC_DEFINITION','SKU; mes; ventana homogénea; censura; forecast método','No equiparar saldo sin filas con cero fuera de cobertura; no comparar año parcial/completo.'),
 ('F24','Usuarios, permisos y operaciones',r'usuario|superuser|superusuario|permiso|permission|roles|office|oficinas','sql/current/users/user_master_v1.sql','docs/users_roles_authorizations_v1_report.md','Reference users/salespersons/warehouses; permisos SAP completos no publicados','REQUIRES_SOURCE','usuario; aplicación; operación; fecha','Superusuario/categoría no prueba acción realizada; no se reconstruyen permisos históricos.'),
 ('F25','Contabilidad, tesorería y administración',r'contab|account|tesorer|treasury|balance|cash.flow|n[oó]mina|payroll|withholding','sql/current/atomic/source_cash_event_sap.sql','docs/telchi_financial_position_cash_flow_v1_1_report.md','Fuentes históricas GL/treasury; Foundation no publica GL completo','HISTORICAL_ONLY','cuenta; fecha; TransType; moneda; escenario','Reconstrucción/forecast histórico no saldo actual bancario ni nómina detallada.'),
 ('F26','Proformas, precios y descuentos',r'proforma|pricing|precio|descuent|discount','sql/current/sales/sales_v1_linenum.sql','docs/proforma_pricing_inventory.md','sales líneas; QUT1/OQUT completos no acreditados CURRENT','REQUIRES_SOURCE','documento/línea; BaseType=23; precio; descuento','Preservar granos y cambio precio; no asumir política comercial desde configuración.')]
# Replace missing preferred SQL with an existing exact path; never invent references.
for i,t in enumerate(F):
 t=list(t)
 if not (ROOT/INV/t[3]).exists():
  candidates=[s['source_reference'][len(INV):] for s in ss if s['extraction_kind']=='sql_file' and s['source_reference'].startswith(INV) and re.search(t[2],s['source_reference'],re.I)]
  t[3]=candidates[0] if candidates else None
 if not (ROOT/INV/t[4]).exists():t[4]=None
 F[i]=tuple(t)
qfamilies=defaultdict(set);sfamilies=defaultdict(set)
for q in qs:
 for fid,name,pat,*_ in F:
  if re.search(pat,q['original_question']+' '+(q.get('normalized_intent') or ''),re.I):qfamilies[q['question_id']].add(fid)
for s in ss:
 for fid,name,pat,*_ in F:
  if re.search(pat,s['source_reference'],re.I) or (fid=='F08' and s['source_reference'].endswith('datalake_direct_business_query_validation_v1/runner.py') and 'ORDER BY H."DocDate" DESC' in s['sql_text']):sfamilies[s['sql_id']].add(fid)
qbyid={q['question_id']:q for q in qs};sbyid={s['sql_id']:s for s in ss}
for l in ls:
 q=qbyid[l['question_id']];s=sbyid[l['sql_id']]
 if l['association_type']=='EXPLICIT_QUERY_REGISTRY_PART':
  native=q['source_native_id'];state=readiness[native]
  q.update(foundation_readiness=state,foundation_mapping='foundation_afd08d9eca6a725be53cdc3f9d5709c9 @ 1408; '+rids[native]['domain'],known_gaps=('Lectura nativa, identidad exacta y alcance documentado; integración/permisos TelchiAI pendiente.' if state=='READY_FOUNDATION' else 'Restringir SKU y unidades; no presentar SUM(Quantity) multi-SKU como magnitud comercial; moneda/status/NC deben declararse.'),business_priority='P1: reutilización directa con alcance explícito')
  if s['sql_engine']=='DuckDB/DuckLake':
   s.update(foundation_readiness=state,foundation_mapping=q['foundation_mapping'],notes=s['notes']+' Reproducido read-only en CURRENT; ver foundation_reproduction.json por query_id/part_id.')
  for fid in qfamilies[q['question_id']]:sfamilies[s['sql_id']].add(fid)
for q in qs:
 ids=sorted(qfamilies[q['question_id']]);q['query_family']='|'.join(ids) or q.get('query_family')
 if not q['normalized_intent'] and ids:q['normalized_intent']='CANDIDATE: '+' | '.join(t[1] for t in F if t[0] in ids)
# Retain all existing questions and add metric objectives missing from question-only columns.
metricfile=ROOT/INV/'validation/sap_knowledge_inventory_v1/sap_validated_metrics.csv'
findings=[]
for i,r in enumerate(csv.DictReader(metricfile.open()),2):
 qid='HQ-'+h(str(metricfile.relative_to(ROOT))+'|row:'+str(i)+'|'+r['metric_name'])[:18]
 if qid not in qbyid:
  q={k:'' for k in qs[0]};q.update(question_id=qid,original_question=r['metric_name'],normalized_intent='HISTORICAL_METRIC_OBJECTIVE',business_domain=r['domain'],source_reference=str(metricfile.relative_to(ROOT)),source_location='row:'+str(i),source_native_id=r['metric_id'],extraction_kind='metric_objective',lexical_variant_id='QV-'+h(r['metric_name'].casefold())[:18],source_system='SAP_HANA historical',historical_result=r['value'],semantic_status='HISTORICAL',foundation_readiness='HISTORICAL_ONLY',known_gaps='La tabla baseline afirma reproducibilidad; falta asociación exacta entre SQL y esta cifra en la matriz.',notes='Resultado preservado para su período '+r['period']+'; no es cifra actual. Evidencia declarada: '+r['gate_evidence'])
  qs.append(q);qbyid[qid]=q
 findings.append(dict(question_id=qid,**r))
writecsv('historical_findings.csv',findings)
writecsv('questions_master.csv',qs);writecsv('sql_master.csv',ss)
writecsv('family_membership.csv',[dict(record_type='QUESTION',record_id=qid,family_id=fid,association='PROPOSED_SEMANTIC_GROUP_NOT_SQL_LINK') for qid,ids in qfamilies.items() for fid in sorted(ids)]+[dict(record_type='SQL',record_id=sid,family_id=fid,association='RESEARCH_SCOPE_OR_EXPLICIT_REGISTRY') for sid,ids in sfamilies.items() for fid in sorted(ids)])
# Rich, one-row-per-operation portability assessment.
oprows=[]
for i,r in enumerate(reg):
 ev=[x for x in rep['queries'] if x['query_id']==r['query_id']]
 opqs=[q for q in qs if q['source_reference']==regpath and q['source_native_id']==r['query_id']]
 opids={q['question_id'] for q in opqs};sqlids=[l['sql_id'] for l in ls if l['question_id'] in opids and sbyid[l['sql_id']]['sql_engine']=='DuckDB/DuckLake']
 oprows.append(dict(operation_id=r['query_id'],question_ids='|'.join(sorted(opids)),question=r['business_question'],sql_ids='|'.join(sorted(set(sqlids))),historical_source=regpath+f'/$/{i}',historical_execution_evidence=str(Path(regpath).parent/'sap_ducklake_results.json')+f'/$/{i}',historical_status='EXACT_SOURCE_NATIVE_WITH_BUSINESS_RESERVATIONS',current_publication=current['current']['foundation_publication_id'],current_snapshot=1408,manifest_base_snapshot=1322,parts=len(ev),current_execution_status='EXECUTED_CURRENT_READ_ONLY' if ev and all(x['status']=='EXECUTED_CURRENT_READ_ONLY' for x in ev) else 'UNRESOLVED',current_evidence='foundation_reproduction.json/query_id='+r['query_id'],semantic_definition=r['definition'],reuse_status=readiness[r['query_id']],gap='Asistente requiere binding, scope autorizado, permisos, límites y contrato de respuesta.' if r['query_id'] in ready else 'Métrica/unidades/moneda y alcance deben restringirse antes de exponer el agregado.',minimum_effort='Reutilizar SQL con pinning, parametrización y contrato de salida; sin nueva investigación SAP.'))
writecsv('verified_operations.csv',oprows)
fr=[]
for s in ss:
 fr.append(dict(record_type='SQL',record_id=s['sql_id'],query_family='|'.join(sorted(sfamilies[s['sql_id']])),historical_source=s['source_reference'],historical_engine=s['sql_engine'],historical_tables=s['tables'],foundation_mapping=s['foundation_mapping'],current_publication=current['current']['foundation_publication_id'],current_snapshot=1408,current_execution_evidence='foundation_reproduction.json' if s['foundation_mapping'] else '',foundation_readiness=s['foundation_readiness'],semantic_status=s['semantic_status'],known_gaps=s['known_gaps']))
for fid,name,pat,sql,doc,mapping,state,pars,res in F:
 fr.append(dict(record_type='FAMILY',record_id=fid,query_family=name,historical_source=INV+doc if doc else '',historical_engine='HANA|Python|DuckLake según SQL relacionados',historical_tables='',foundation_mapping=mapping,current_publication=current['current']['foundation_publication_id'],current_snapshot=1408,current_execution_evidence='foundation_business_cases.json; foundation_reproduction.json (solo garantías ejecutadas)',foundation_readiness=state,semantic_status='CONDITIONAL' if state.startswith('READY') else 'UNRESOLVED',known_gaps=res+' Estados de familia no acreditan todos sus miembros ni integración.'))
writecsv('foundation_readiness.csv',fr)
# Evidence index summarizes declared gates; data-row status by itself is not a validation.
ev=loadcsv('evidence_index.csv')
ev=[r for r in ev if set(json.loads(r['attributes']))-{'status','period','cutoff','foundation_publication_id','ducklake_snapshot_id'}]
writecsv('evidence_index.csv',ev,['source_reference','source_location','attributes'])
# Record external references without reading private configuration or copying datasets.
extrefs=[]
for f in physical:
 if f['file_type'] not in {'.md','.py','.sql','.json','.jsonl','.csv','.tsv','.yaml','.yml','.txt'}:continue
 p=Path(f['path']) if f['path'].startswith('/') else ROOT/f['path']
 try:text=p.read_text()
 except (OSError,UnicodeError):continue
 for target in sorted(set(re.findall(r'/media/issajar/[^\s\"\'`<>),;\]}]+',text))):
  extrefs.append(dict(source_reference=f['path'],target=target,accessibility='NOT_INSPECTED_PRIVATE' if '/private/' in target else 'TEMPLATE_UNRESOLVED' if '{' in target or '...' in target else 'EXISTS' if Path(target).exists() else 'MISSING_OR_STALE_LITERAL_REFERENCE',policy='REFERENCE_ONLY_NO_COPY'))
writecsv('external_references.csv',extrefs,['source_reference','target','accessibility','policy'])
# A log contains a valid JSON object followed by a human summary. Keep the anomaly.
malformed=Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/users_audit/phase1_catalog_discovery_output.json')
obj,end=json.JSONDecoder().raw_decode(malformed.read_text())
m['error_resolutions']=[dict(path=str(malformed),classification='VALID_JSON_PREFIX_WITH_TRAILING_SUMMARY',json_object_keys=sorted(obj),trailing_text=malformed.read_text()[end:].strip(),source_rewritten=False)]
for f in physical:
 f['questions_detected']=sum(q['source_reference']==f['path'] for q in qs)
 f['sql_detected']=sum(s['source_reference']==f['path'] for s in ss)
writecsv('physical_inventory.csv',physical)
m['question_sql_links']=len(ls)
m['sql_by_validation']=dict(Counter(s['validation_status'] for s in ss))
m['documentary_sql_contracts_executed']=24
m['documentary_research_objectives']=8
m.update(questions=len(qs),distinct_exact_wordings=len({q['lexical_variant_id'] for q in qs}),questions_by_extraction=dict(Counter(q['extraction_kind'] for q in qs)),query_families=len(F),verified_operation_readiness=dict(Counter(readiness.values())),external_literal_references=len(extrefs),evidence_index_rows=len(ev),automatic_extraction_limits=['Las plantillas SQL se extraen como expresiones; no se reconstruyen dinámicamente todos los builders ni instrucciones múltiples.','Preguntas extraídas incluyen objetivos, rótulos de partes SQL y títulos candidatos; no son conteo de intents empresariales únicos.','Gzip de datasets externos sólo metadata/hash; no lectura completa de resultados fila a fila.','Resultados/validaciones fuera del registro directo se conservan en baseline y evidence_index, pero no se atribuyen por semejanza temática.'])
(OUT/'coverage_manifest.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
# Counts in these reports are generated from structured evidence, not guessed.
counts=Counter(readiness.values());hist_sql=[s for s in ss if s['execution_evidence']];reads=[s for s in ss if s['statement_role']=='READ_QUERY']
summary={ 'physical_files':len(physical),'investigation_files':sum(f['phase']=='A_INVESTIGATION' for f in physical),'questions_occurrences':len(qs),'wordings_lexical':m['distinct_exact_wordings'],'sql_occurrences':len(ss),'sql_read_occurrences':len(reads),'sql_lexical_groups':len({s['lexical_sql_group'] for s in ss}),'sql_historical_execution_occurrences':len(hist_sql),'sql_historical_execution_lexical_groups':len({s['lexical_sql_group'] for s in hist_sql}),'historical_verified_operations':len(oprows),'current_reproduced_operations':sum(r['current_execution_status']=='EXECUTED_CURRENT_READ_ONLY' for r in oprows),'current_reproduced_sql_parts':len(rep['queries']),'readiness':dict(counts),'families':len(F)}
(OUT/'audit_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
family_lines=[]
for fid,name,pat,sql,doc,mapping,state,pars,res in F:
 qids=[k for k,v in qfamilies.items() if fid in v];sids=[k for k,v in sfamilies.items() if fid in v]
 examples=[qbyid[q]['original_question'].replace('|','/') for q in qids if qbyid[q]['extraction_kind'] in {'catalog_question','structured_question','documented_question'}][:4]
 family_lines.append(f'''## {fid} — {name}

Agrupación conceptual respaldada por fuentes; las asociaciones completas están en `family_membership.csv`. La clasificación de familia no autoriza todos sus miembros.

- Variantes preservadas: {'; '.join(examples) or 'Ver preguntas/objetivos en las fuentes citadas.'}
- Parámetros posibles: {pars}.
- Semántica y dependencia: {res}
- Mapping CURRENT: {mapping}.
- Estado: **{state}**; no significa capability aprobada.
- Fuentes: {link(INV+doc) if doc else 'Fuente de familia pendiente de resolver.'}; SQL: {link(INV+sql) if sql else 'SQL/implementaciones indexadas, sin preferred SQL confirmado.'}.
- Miembros candidatos: {len(qids)} ocurrencias de preguntas y {len(sids)} ocurrencias SQL, con IDs exactos en el CSV; no frecuencia de uso.
''')
md('query_families.md','''# Familias de consultas históricas reutilizables

La agrupación posterior al inventario propone 26 familias. No genera código ni amplía TelchiAI; cada operación debe preservar su métrica, granularidad, permisos, fuente y cobertura.

Los IDs de preguntas y SQL están en `family_membership.csv`; las asociaciones SQL defendibles están separadas en `question_sql_links.csv`. Los mismos miembros pueden pertenecer a varias familias.

'''+'\n'.join(family_lines))
md('business_semantics.md','''# Semántica empresarial recuperada

Los estados se aplican a cada definición y su alcance, no a todo el dominio. Historicidad, paridad de valores y aptitud productiva son garantías distintas.

## Ventas, documentos, importes y fechas

El conocimiento monetario existente distingue cabecera, línea y notas de crédito; no debe reinterpretarse para ampliar el catálogo.

| Definición | Estado | Evidencia / restricción |
| --- | --- | --- |
| DocEntry es grano financiero de factura; LineNum es grano de detalle | VALIDATED histórico; CURRENT campos verificados | DECISIONS TELCHI-DEC-007; FINANCIAL_REPORTING_CONTRACT; registry sales_exact_document/lines |
| DocTotal de cabecera no equivale a suma LineTotal | VALIDATED como distinción | DECISIONS; executive_sales.py:20 y 42; impuestos, descuentos y redondeos requieren base explícita |
| Neto documental = facturas válidas − NC válidas bajo reglas del contrato | CONDITIONAL | FINANCIAL_REPORTING_CONTRACT; corporate_sales_by_salesperson sólo BS, categoría corporativa y SlpCode |
| Neto comercial general por producto | UNRESOLVED | PRODUCT_COMMERCIAL_SEMANTICS_V1.md:66: NET_PRODUCT_AMOUNT_UNRESOLVED; no asignación de descuento cabecera demostrada |
| CANCELED N / Y / C = activo / original cancelado / reversa | VALIDATED histórico | query_catalog.md §11; cancelaciones y NC preservadas en CURRENT |
| NC DocTotal raw positivo; signo negativo para cálculo comercial | VALIDATED histórico | DECISIONS TELCHI-DEC-008; no negar indiscriminadamente todos los importes fuente |
| DocDate es fecha documental | VALIDATED | fecha de venta documental; no timestamp de ingreso ni ingestión |
| UpdateDate demuestra exactamente cuándo se anuló | REJECTED como equivalencia general | query_catalog dice última actualización; lifecycle temporal exige reconstrucción/estado; una actualización puede tener otros motivos |
| Último mes disponible = mes de MAX(doc_date) | CONDITIONAL | prueba sales_coverage/sales_months da septiembre 2026 hasta 24/09; no garantiza mes completo |
| Último mes completo | UNRESOLVED | agosto tiene fechas hasta 31/08; presencia de esas filas no acredita ausencia de faltantes ni cierre empresarial |
| Canal vendedor equivale a canal de cada venta | REJECTED como regla universal | CORPORATE_SALES_FINAL_REPORT y CHANNEL_RULE_FINAL_REPORT separan categoría de vendedor y clasificación transaccional |

## Cantidades y productos

La fidelidad source-native no basta para convertir cantidades documentales en unidades físicas comparables ni para comparar productos.

| Definición | Estado | Evidencia / restricción |
| --- | --- | --- |
| SUM Quantity por SKU conserva cantidad fuente | CONDITIONAL | direct registry sales_by_item; CURRENT reproducción; no acredita factor/UoM documental |
| SUM Quantity por almacén, cliente o período multi-SKU como una magnitud | REJECTED | metric/uom contracts; kg, litros, unidades y paquetes no se suman |
| Ranking cross-SKU por Quantity documental | CONDITIONAL sólo como orden documental explícito; REJECTED como ranking físico/comercial universal | messaging_sales_query y assistant README no certifican UoM comparables ni venta neta |
| Conversión comercial requiere factor de línea verificado hacia inventario del mismo SKU | VALIDATED como invariante | PRODUCT_COMMERCIAL_SEMANTICS_V1.md:38–50; master o BaseEntry no sustituyen prueba de factor |
| Conversión kg/L sin densidad | REJECTED | MASS/VOLUME incompatible; no densidad inferida |
| Calenta es un único cliente o marca confirmada | UNRESOLVED / sin evidencia suficiente | productos SAP identificados, customers sin matches; brand UNKNOWN según contrato, alias AMBIGUOUS en varias presentaciones |
| Calenta tiene candidatos de producto SAP | VALIDATED como localización | L02822, L02823, L02877, L03035, L03648, L03649, L03650, L03658; dos variantes KG no vendibles |
| LIKE %CALENTA% resuelve familia comercial | REJECTED | también devuelve CALENTADOR y CALENTAMIENTO; no es resolver semántico |
| Namespace fuente es igual en Atomic y Reference | REJECTED | Atomic SAP_B1_HANA vs Reference SAP_HANA; join literal no recupera ventas Calenta. Consulta SKU exacto sí devuelve cuatro productos en mayo |
| Clasificación comercial temporal y sidecars UoM están en CURRENT | UNRESOLVED / no acreditado | manifest CURRENT tiene 8 componentes lógicos y no publica product_commercial_semantics/temporal; no usar candidate como CURRENT |

## Stock, compras y abastecimiento

Las magnitudes y las fechas mantienen su origen; equivalencias entre hechos comerciales y físicos requieren lineage probado.

- **VALIDATED / alcance actual:** OnHand, IsCommited y OnOrder son posiciones distintas. Disponible = OnHand − IsCommited conserva negativos; OnOrder no se agrega como existencia. OITW es as_of, no stock histórico.
- **CONDITIONAL:** stock agregado sólo entre unidades compatibles; snapshot y source_as_of obligatorios. Stock histórico derivado requiere OINM y baseline coherente.
- **VALIDATED histórico:** ordenado, recibido y facturado se unen por BaseType/BaseEntry/BaseLine. NumPerMsr debe ser explícito, finito y positivo. Multi-recepción y multi-almacén conservan grain de línea.
- **REJECTED:** base_ref solo identifica un documento globalmente; caso 262000261 colisiona entre OC/GR/AP. Requiere trans_type, doc_line_num, ItemCode y corroboración proveedor.
- **CONDITIONAL:** AP directa no demuestra no recepción física; TRUE_INVOICED_WITHOUT_RECEIPT es clasificación derivada con alcance/cobertura, no fact universal.
- **CONDITIONAL:** lead time documental es diferencia de fechas; no tiempo físico certificado ni estado de importación/aduana. U_TIPOCOMPRA clasifica origen; Country solo no basta.

## Crédito, cobranzas, producción y operaciones

Los reportes anteriores conservan respuestas defendibles en su universo; la publicación actual no demuestra toda la historia ni una integración de esas operaciones en el asistente.

- **VALIDATED histórico:** OITR/ITR1 es autoridad settlement Telchi; RCT2 no fue autoridad suficiente en aquel baseline. Reconciliado no equivale a cobrado en efectivo. No extrapolar esto a cualquier SAP.
- **CONDITIONAL:** receivable_settlement_status publica saldo/estado; collection_method_fact tiene componentes por medio de pago, no un pago único por fila. Pago, aplicación, reducción económica y deuda son métricas distintas.
- **UNRESOLVED:** reproducir cualquier deuda histórica al día de venta desde solo saldo publicado actual; necesita eventos, cancelaciones y fechas efectivos.
- **REJECTED:** límite configurado / vendedor / superusuario prueba aprobación o acción operacional. Falta historia de autorización.
- **VALIDATED histórico:** BOM es receta/plan; OWOR/IGE1/IGN1 y OINM soportan orden, consumo y salida reales. BOM vigente no demuestra consumo real histórico.
- **CONDITIONAL:** demanda equivalente, cobertura y capacidad necesitan factores y unidades verificados, dependencias entre componentes y validez temporal; consumo interno no se transforma en venta externa.
- **HISTORICAL:** cifras de tesorería, contabilidad, nómina, forecasting y backtests; no saldos bancarios actuales ni resultados nuevos de modelos.

Fuentes canónicas: [DECISIONS](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/DECISIONS.md), [contrato financiero](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/FINANCIAL_REPORTING_CONTRACT.md), [reglas SAP](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/sap_knowledge_inventory_v1/sap_business_rules_inventory.csv), [contrato compras](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/TELCHI_PURCHASING_ANALYTICAL_CONTRACT_V1.md), [semántica productos](../../../../SrvRestAstroLS_v1/backend/modules/telchi/datalake/PRODUCT_COMMERCIAL_SEMANTICS_V1.md).
''')
md('executive_query_reuse.md','''# Reutilización de las seis preguntas de TelchiAI

Las cifras de las sondas corresponden exclusivamente a Foundation CURRENT 1408 observada en esta auditoría. No representan SAP actual ni una nueva validación comercial general.

## A — Últimas ventas registradas

Existe ordenación histórica por DocDate descendente en el discovery del runner directo; aún no es una capability de últimas ventas aprobada.

- Pregunta original: «Dame las últimas ventas registradas»; fixture WhatsApp 20261011 y batería runtime_http.
- SQL histórico: validation/datalake_direct_business_query_validation_v1/runner.py, _discover / validation_closed_day_sample, ORDER BY H.DocDate DESC. Es discovery de fecha de muestra, no respuesta histórica a listado de últimas ventas.
- Prueba CURRENT: foundation_business_cases.json / latest_sales_documents; 10 headers, orden DocDate DESC + DocEntry DESC; última fecha 2026-09-24.
- Semántica: grano documental; puede incluir estados N/Y/C; «registradas» como fecha de ingreso no está demostrado con DocDate.
- Brecha: fijar fecha/estatus/alcance; devolver documento vs línea; filtro por cliente/producto y permisos; no reutilizar silenciosamente el top Quantity.
- Esfuerzo mínimo: adaptación de consulta existente, parámetros acotados y contrato de orden/grano; resolver timestamp si se exige registro cronológico real.
- Recomendación: **READY_CONDITIONAL** para «últimos documentos por fecha documental», no para afirmar últimas ventas en SAP vivo.

## B — Ventas de mayo 2026

Hay SQL mensual ejecutado para agosto, SQL de estacionalidad por producto y un cálculo monetario existente de ventas corporativas. Sus definiciones son distintas.

- Histórico: registry sales_monthly_august, EXACT; cutoff 15/09/2026. Grain DocEntry+LineNum, suma Quantity y LineTotal sin excluir estados; no es neto general.
- Semántica histórica alternativa: sql/current/seasonality/sales_monthly_v1.sql = unidades OINV activas menos ORIN activas por producto/mes; no importe.
- CURRENT: la sonda may_document_amounts agrupa DocTotal por moneda y cancelación. Mayo tiene 36.242 headers BS activos y suma DocTotal **8.761.459,22**; además 2 originales Y y 2 reversas C, cada grupo 740,22.
- La cifra es **importe de facturas activas BS del snapshot**, no neto tras NC, ventas por producto ni cobranza. No se presentó como respuesta empresarial actual.
- Brecha: acordar DocTotal vs LineTotal; moneda/impuestos/descuentos; NC y cancelaciones; completitud requerida. El SQL parametrizable y los datos ya existen.
- Esfuerzo mínimo: escoger contrato monetario respaldado, trasladar filtros/período y conectar un reader limitado; no repetir SAP.
- Recomendación: **REQUIRES_METRIC_DEFINITION** para «ventas» genéricas; **READY_CONDITIONAL** para importe documental con definición explícita.

## C — Calenta

Reference y resultados previos identifican productos; no prueban una única marca, cliente o familia comercial resuelta.

- Evidencia histórica: data/reports/telchi/high_stock_low_sales_commercial_products_v1/commercial_universe.csv y excluded.csv; CALENTA 250 g, 30 g, FORTE y KG interno.
- SQL histórico reutilizable: registry sales_by_item (EXACT); ventas por ItemCode fuente. No se localizó una consulta histórica validada llamada «últimas ventas Calenta».
- CURRENT: productos SAP L02822, L02823, L02877, L03035, L03648, L03649, L03650, L03658; L02877/L03648 SellItem=N, KG. Customers no tuvo matches en esta publicación.
- LIKE %CALENTA% también devuelve INCUBADORA...CALENTADOR y Horno de CALENTAMIENTO. Varios aliases están AMBIGUOUS; no tomar la búsqueda como resolver.
- Mapping material: Atomic source_system=SAP_B1_HANA; Reference=SAP_HANA. Igualdad literal devuelve cero filas; es una brecha real de namespace, no falta de ventas.
- Prueba por SKU exacto de mayo: L02822 1.568 / LineTotal 63.287,96; L02823 3.472 / 24.889,65; L03649 2.125 / 18.487,39; L03658 785 / 43.082,52. Todos BS y N. Las cantidades son nativas y permanecen por SKU; no se suman ni se convierten a peso.
- Brecha: conjunto comercial autorizado, Calenta vs Calenta Forte, excluir internos, namespace canónico; definición de importe neto por producto no resuelta.
- Esfuerzo mínimo: mapping/alias con provenance y filtro de SKUs exactos; reutilizar sales_by_item. No nuevo discovery SAP.
- Recomendación: **REQUIRES_MAPPING** para mención libre; **READY_CONDITIONAL** para SKU explícito y métrica fuente.

## D — Último mes disponible

El census histórico ya consulta MIN/MAX; la fecha máxima observada en CURRENT es reproducible, pero no acredita mes completo.

- SQL histórico: datalake_2026_census_and_coverage_reconciliation_v1/runner.py:529, MIN/MAX doc_date; resultados de census preservados en evidencia externa.
- CURRENT: first_date 2022-03-31, last_date 2026-09-24, 330.443 headers. Mes con datos más reciente: septiembre 2026; agosto alcanza 31/08.
- No afirmar historia completa desde 2022, ni último mes completo por encontrar el día 31. Publication data_as_of, component source_as_of, max DocDate y fecha de commit son diferentes.
- Brecha: metadata autorizada por entidad/métrica y certificación de completitud. TelchiAI sólo guarda latest_available_month, sin resolverlo.
- Esfuerzo mínimo: exponer metadata de cobertura existente con entidad/métrica y estado de completitud; reader pinned, sin cambiar CURRENT.
- Recomendación: **READY_CONDITIONAL** para último mes con registros; **UNRESOLVED** para último mes empresarial completo.

## E — Importes y cantidades

El registro directo ya devuelve ambas columnas; la limitación es semántica y contractual, además del catálogo del asistente.

- SQL/evidencia: sales_by_item, sales_by_customer, sales_daily_aggregate, sales_monthly_august, sales_ytd y sales_top_items; hashes EXACT históricos y reproducción CURRENT.
- Source-native LineTotal no es DocTotal ni neto comercial. Los agrupados de cliente/período pueden mezclar unidades; un SUM Quantity global es inadmisible como magnitud física.
- Foundation conserva importes y cantidades fuente, pero sales_line no incluye un factor documental/UoM completo. Reference sales_uom_id no sustituye esa evidencia.
- Esfuerzo mínimo: dos métricas con contratos separados, cantidad por SKU/UoM validada y moneda; no agregar métricas desde el LLM. Neto por producto necesita definición adicional.
- Recomendación: **READY_CONDITIONAL** para ambas medidas fuente por SKU; **REQUIRES_METRIC_DEFINITION** para agregados generales.

## F — Productos más vendidos

Hay varias definiciones históricas que no deben convertirse en un único ranking sin elegir qué significa «más».

- Variante source-native: registry sales_top_items, EXACT histórico, 2026-01-01..2026-09-15; Quantity por ItemCode, sin excluir cancelaciones/NC. Reproducida en CURRENT con mismo scope SQL.
- Capability actual: messaging_sales_query.SQL_TEMPLATE y assistant sales.source_top_items, top 10 fijo 01/01..16/09 exclusivo. No permite filtros generales, importe neto ni período parametrizable.
- Variante net units mensual: seasonality/sales_monthly_v1.sql y product_seasonality_v1_report; facturas activas menos NC activas; cantidades por producto y período.
- Variante comercial vs uso interno: high_stock_low_sales_commercial_products_v1 y semántica comercial de producto; no usar candidate sidecar como CURRENT.
- Variante por importe: SQL histórico tiene LineTotal; requiere distinguir importe de línea de neto producto y encabezado.
- Brecha: criterio de ranking, unidades, universo comercial, cancelaciones/NC, período, desempate y mappings.
- Esfuerzo mínimo: parametrizar familia existente después de fijar métrica/universo; validar resultados, no diseñar motor paralelo.
- Recomendación: **REQUIRES_METRIC_DEFINITION** para «más vendidos» genérico. El ranking documental fijo ya existe, con sus límites.
''')
md('telchiai_priority_matrix.md','''# Prioridad para reutilizar conocimiento existente

La prioridad combina incidentes documentados y valor empresarial inferido. No se dispone de frecuencia de usuarios en producción; ocurrencias repetidas en fixtures/benchmarks no se consideran demanda observada.

| Orden | Familia | Evidencia de demanda / valor | Disponibilidad | Brecha que decide habilitación |
| --- | --- | --- | --- | --- |
| 1 | F09 cobertura temporal | Incidente de último mes; prerequisito de respuestas fiables | Census + MAX CURRENT verificado | Cobertura por métrica/entidad; separar parcial/completo |
| 2 | F08 últimos documentos | Incidente WhatsApp / batería HTTP | ORDER BY histórico + 10 headers CURRENT | Fecha/grano/status, scope y binding |
| 3 | F02 importes por período | Mayo/septiembre documentados; utilidad comercial inferida alta | SQL mensual y DocTotal mayo demostrado | Contrato monetario, NC, moneda, cobertura |
| 4 | F04 ventas por SKU | Incidente Calenta, catálogo productos | sales_by_item EXACT y CURRENT; mayo cuatro SKUs | Alias comercial y namespace; UoM/importe fuente |
| 5 | F03 ventas por cliente | CEO Q003/Q004; valor comercial inferido | SQL nativo EXACT y CURRENT | Identidad/alias y métricas compatibles; cantidades multi-SKU |
| 6 | F01 documentos/líneas | Prerrequisito transversal de drilldown | READY_FOUNDATION nativo | Binding y permisos; no ampliar scope |
| 7 | F11 stock actual | CEO + auditorías stock | 4 operaciones nativas reproducidas, stock_availability existente | UoM/as_of por SKU, permisos |
| 8 | F19 cobranzas | CEO + reglas settlement y publicación RC | Fact publicado y sample pinned; no reproducción de todas las preguntas | Pago vs componente/aplicación; moneda/fechas |
| 9 | F14 cadena compras | Auditorías profundas, universo/paridad ya construidos | 8 datasets de purchasing en manifest CURRENT; schemas verificados | Query empresarial delimitada, lineage, out_of_coverage |
| 10 | F07 rankings | Incidente y capability fija existente | SQL EXACT fuente y variante net units histórica | Definir «más»: unidades compatibles, importe, neto y universo |
| Posterior | F12/F13/F15/F16/F17/F18/F20/F21/F22/F23/F24/F25/F26 | Oportunidad operacional inferida, evidencia histórica amplia | Ver familias, matriz y baselines | Mapping/metric/source/historia; no repetir investigaciones cerradas |

## Selección de 5, 10 o 20 familias

La amplitud debe seguir los contratos ya acreditados; el número no mide por sí mismo valor ni seguridad semántica.

- **Primer paquete de 5:** cobertura, últimos documentos, período monetario explícito, SKU exacto y cliente exacto. Son candidatos; no los cinco READY de forma incondicional. Drilldown F01 es dependencia de implementación existente.
- **Llegar a 10:** sumar stock, cobranzas, compras, rankings definidos y drilldown. Reutilizar las publicaciones existentes y focalizar validación de cada query; no reingestar.
- **Llegar a 20:** exige completar mappings comerciales, unidades, historia de settlement/producción y métricas. No hay evidencia para prometer 20 familias inmediatamente habilitables.

En el registro directo se acreditaron 30 operaciones nativas portables técnicamente. La revisión clasifica **9 READY_FOUNDATION**, **8 READY_CONDITIONAL** y **13 REQUIRES_METRIC_DEFINITION**. READY se refiere a la operación nativa exacta, no a capability TelchiAI. El catálogo actual continúa siendo una única lectura documental fija.

No se crearon capacidades ni cambios en Luna, State Engine, Messaging, Srv05, Foundation o datos. La próxima etapa puede reutilizar este inventario para formalizar contrato/binding y validar un primer paquete acotado.
''')
md('unresolved_questions.md','''# Preguntas y garantías pendientes

La falta de asociación completa queda explícita; no se llena con resultados ni equivalencias inferidas. El detalle por registro permanece en CSV.

| Pregunta / garantía | Causa | Conocimiento existente que debe conservarse |
| --- | --- | --- |
| ¿Cuántos intents empresariales diferentes investigamos en total? | 1.397 redacciones lexicalmente diferentes no equivalen a intents; títulos/rótulos requieren adjudicación semántica y deduplicación | questions_master + family_membership, sin eliminar variantes |
| ¿Cuántas consultas históricas se ejecutaron en todo el corpus? | 30 operaciones y 70 ocurrencias SQL acreditadas estrictamente; muchos scripts/gates aún sin enlace SQL→resultado granular | evidence_index, historical_findings y 116 gates del inventario SAP previo |
| ¿Cuántas preguntas adicionales a las 30 tienen cadena completa? | Los 19 baselines y reportes acreditan resultados históricos, pero no se atribuyó automáticamente cada cifra a un SQL exacto | historical_findings.csv conserva cifra, período, reglas y fuente |
| Neto comercial general de mayo/septiembre | DocTotal, LineTotal y neto tras NC no equivalen; imponer métrica aprobada | Contrato financiero, executive_sales, SQL mensual |
| Últimas ventas «registradas» | DocDate no demuestra timestamp de registro/ingestión | Discovery histórico y lista documental CURRENT |
| Últimas ventas de Calenta como familia | Aliases ambiguos, namespaces distintos, Forte/presentación/internos y coincidencias falsas por LIKE | SKUs, aliases y resultados mayo sin suma de unidades |
| Último mes completo por entidad | MAX documental no certifica completitud ni calendario empresarial | Census/source_as_of/manifest |
| Cantidad global y ranking universal | Faltan factores/documentary UoM compatibles; orden documental no magnitud física | Source quantities, contratos UoM, candidatos sidecar |
| Ventas por sucursal/canal horizontal | Warehouse, branch, vendedor y canal transaccional no equivalen | Sales dimensions, crosswalks y reglas comerciales históricas |
| Deuda histórica al día de venta | Eventos settlement/NC/cancelación y vencimiento efectivos; saldo publicado no sustituye historia | SQL financial/as-of y excepciones crédito |
| Aprobación de crédito / permisos históricos | Configuración no prueba decisión; historia autorizaciones insuficiente | Credit control y auditoría users |
| Consumo real usando sólo BOM vigente | BOM planificada no evidencia emisión real histórica | OWOR/IGE1/IGN1/OINM e investigaciones producción |
| Forecast/demanda perdida actual | Censura por stockout y ventanas parciales; backtests históricos no predicción nueva | Reportes seasonality/replenishment, sin benchmarks de modelos |
| Nómina detallada, GL completo y treasury actual | No acreditados en Foundation publicada | Reportes financieros/historical-only |
| Datasets externos gzip | Metadata/hash inventariados; contenido fila a fila excluido; cadena documental no debe usar valores no leídos | 37 rutas gzip y reports fuente preservados |

Las interrogantes con SQL dinámico no reconstruido y asociaciones débiles conservan UNRESOLVED. No se considera completa la auditoría semántica de toda la historia, aunque el recorrido físico de investigation sí está acreditado.
'''.replace('1.397',f'{m["distinct_exact_wordings"]:,}'.replace(',','.')))
invtypes=Counter(f['file_type'] for f in physical if f['phase']=='A_INVESTIGATION')
invdirs=Counter(str(Path(f['path']).parent.relative_to(Path(INV))).split('/')[0] for f in physical if f['phase']=='A_INVESTIGATION')
md('INVENTORY_REPORT.md',f'''# Telchi — Historical Business Query Inventory V1

Auditoría de conocimiento existente en `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. Sólo se escribieron artefactos del informe; SAP, datos, Foundation y runtime no fueron modificados.

## Conclusión acreditada

La hipótesis se confirma en un alcance mínimo verificable: hay más conocimiento empresarial ejecutado que la única lectura fija del asistente. La exhaustividad semántica integral sigue **PARTIAL**; no se convierte extracción automática en negocio resuelto.

- **30 operaciones históricas**: 10 ventas, 10 OINM, 5 cruces y 5 OITW, con SQL SAP/DuckLake, resultados, hashes EXACT y drilldown. Registro y resultados originales son externos y accesibles.
- **30 operaciones reproducidas en CURRENT**, con **35 partes SQL** read-only. Se sustituyeron sólo relaciones por pins del reader y se reconstruyeron bindings desde scope/discovery preservados; no se ejecutó SAP.
- **{counts['READY_FOUNDATION']} READY_FOUNDATION**, **{counts['READY_CONDITIONAL']} READY_CONDITIONAL**, **{counts['REQUIRES_METRIC_DEFINITION']} REQUIRES_METRIC_DEFINITION** dentro de esas 30. Primer estado: hechos nativos exactos, sin reetiquetarlos como ventas netas, rankings físicos o cifras actuales de SAP.
- **8 investigaciones adicionales con 24 contratos SQL** tienen ejecución N/N declarada y artefactos explícitos. Se conservan como evidencia documental con reservas de versión, distinta de paridad por hashes; ver research_chains.csv.
- **19 objetivos métricos baseline adicionales** preservados con resultados/períodos. El inventario SAP previo documenta 116 gates, 79 objetos, 31 relaciones, 26 reglas y 18 gaps; esas cifras son evidencia histórica, no conteos nuevos de preguntas SQL completas.
- Foundation publica también **purchasing, material_supply y receivables_collections**; se verificaron referencias selladas, schemas y muestras acotadas. No todos sus análisis históricos fueron reproducidos ni declarados READY.
- **26 familias conceptuales** permiten planificar reutilización. No equivalen a 26 capabilities listas. Primera selección recomendada: cobertura, últimos documentos, período monetario explícito, SKU y cliente; validar sus brechas antes de habilitar.

## Alcance físico y método

Se completó el recorrido recursivo de investigation antes de extender búsqueda a módulo, documentación relacionada, reportes, evidencia externa, LlmFit y source legacy. No se siguieron symlinks ni dependencias externas como negocio.

| Alcance | Archivos inventariados |
| --- | ---: |
'''+ '\n'.join(f'| {k} | {v} |' for k,v in m['counts_by_phase'].items())+f'''
| Total | {len(physical)} |

Investigation: **1.219 archivos**, 82.450.514 bytes al recorrido inicial; {dict(invtypes)}. Las 445 entradas pyc tienen metadata/hash, sin extracción de fuente. Conteo por primer directorio: {dict(invdirs)}. El manifest incluye todos los directorios/conteos, no sólo esta tabla.

No hubo directorios inaccesibles identificados. Un archivo `.json` externo tiene JSON válido seguido por SUMMARY; se registró JSONDecodeError y se verificó el prefijo sin reescribirlo. Los 37 gzip externos son datasets generados, inventariados/hash; no se leyeron completos. No se copiaron Parquet ni datasets grandes.

## Catálogo de preguntas y SQL

Los conteos distinguen ocurrencias, redacciones, consultas técnicas y operaciones verificadas. No se acredita un total de intents empresariales únicos con deduplicación por texto.

| Medida | Conteo | Interpretación |
| --- | ---: | --- |
| Ocurrencias pregunta/objetivo/candidato | {len(qs)} | Una fila por ubicación y redacción; conserva duplicados históricos |
| Redacciones lexicalmente distintas | {m['distinct_exact_wordings']} | Casefold/espacios; no equivalencia semántica ni frecuencia de usuario |
| Ocurrencias SQL/implementación extraídas | {len(ss)} | Archivos, AST, JSON, CSV y bloques Markdown; incluye técnico/fixtures |
| Ocurrencias read-query | {len(reads)} | No todas son preguntas de negocio o SQL completo dinámico |
| Grupos SQL lexicales | {summary['sql_lexical_groups']} | No demuestra equivalencia SQL por álgebra/semántica |
| SQL con ejecución acreditada / declarada | {len(hist_sql)} | 70 ocurrencias registry + 24 contratos declarados en informes; {summary['sql_historical_execution_lexical_groups']} textos lexicales distintos |
| Asociaciones pregunta-SQL explícitas/contextuales | {len(ls)} | {sum(l['association_type']=='EXPLICIT_QUERY_REGISTRY_PART' for l in ls)} registry; 24 artefactos de reportes con ejecución declarada; 17 misma sección Markdown sin ejecución |
| Operaciones empresariales nativas verificadas | 30 | Límite inferior; no sumar automáticamente los baselines ni todos los PASS anteriores |

Ambos catálogos CEO están cubiertos: **Q001–Q074 (74)** y **Q-V2-001–008 (8)**. query_catalog.md tiene **22 bloques SQL** preservados con secciones; parte son placeholders/ilustración y no se marcaron ejecutados por el título «realizadas». Todos los **102 archivos .sql** de investigation se encuentran representados. Se incluyeron SQL embebido y reportes, además de catálogos.

La extracción automática incluye encabezados de métricas y rótulos internos de query parts. Las filas conservan extraction_kind y UNRESOLVED cuando falta evaluación. Builders dinámicos y múltiples statements por implementación no se reconstruyeron exhaustivamente; el conteo SQL es de artefactos/expresiones, no un total definitivo de consultas de negocio.

## Foundation efectiva y casos del asistente

El reader oficial resolvió la única CURRENT y su manifest; el acceso fue READ_ONLY confirmado sobre el attachment, con pins de publicación, dos threads y 512 MB por conexión propia.

- Publicación: `{current['current']['foundation_publication_id']}`; snapshot de commit **1408**; base de manifest **1322**.
- Componentes lógicos: {', '.join(current['manifest']['components'])}. component_count=5 corresponde al set core, no demuestra ausencia de los tres extensibles.
- Source as_of ventas 2026-09-24; publication data_as_of 2026-09-28; commit 2026-10-01. Ninguna de estas fechas equivale a «SAP actual».
- Máxima DocDate **2026-09-24**; último mes con filas **septiembre**. Agosto llega a 31/08, pero no se certificó último mes empresarial completo ni toda historia desde 2022.
- Mayo: 36.242 facturas BS activas, DocTotal **8.761.459,22** del snapshot; no importe neto tras NC ni importe por producto. Las reservas y estados Y/C están en executive_query_reuse.
- Calenta: candidatos de producto, no cliente/marca único acreditado; cuatro SKUs tienen filas mayo. Alias ambiguos y namespace `SAP_B1_HANA` vs `SAP_HANA` impiden un join literal fiable. LIKE incluye calentadores ajenos.
- Neto producto, conversiones de cantidades, universo comercial temporal y ranking genérico conservan gaps. El catálogo TelchiAI sigue limitado a sales.source_top_items fijo; ninguna capability nueva fue habilitada.

## Entregables y trazabilidad

Los CSV permiten continuar revisión sin repetir discovery. Los JSON contienen pruebas read-only y manifest efectivo; los informes separan conclusiones y criterios de integración.

- [questions_master.csv](questions_master.csv), [sql_master.csv](sql_master.csv), [question_sql_links.csv](question_sql_links.csv).
- [physical_inventory.csv](physical_inventory.csv), [coverage_manifest.json](coverage_manifest.json), [duplicate_files.csv](duplicate_files.csv), [external_references.csv](external_references.csv).
- [verified_operations.csv](verified_operations.csv), [foundation_readiness.csv](foundation_readiness.csv), [historical_findings.csv](historical_findings.csv), [evidence_index.csv](evidence_index.csv).
- [query_families.md](query_families.md), [business_semantics.md](business_semantics.md), [telchiai_priority_matrix.md](telchiai_priority_matrix.md), [unresolved_questions.md](unresolved_questions.md), [executive_query_reuse.md](executive_query_reuse.md).
- [foundation_current_inspection.json](foundation_current_inspection.json), [foundation_reproduction.json](foundation_reproduction.json), [foundation_business_cases.json](foundation_business_cases.json).

## Gaps y límites de exhaustividad

Todos los archivos del root principal tienen metadata/hash y los textos fueron escaneados, pero extracción amplia no acredita cada cadena ni una taxonomía semántica definitiva.

1. Queda adjudicar títulos/objetivos/variantes y reconstruir SQL dinámico, además de vincular resultados granulares fuera del registry directo. No se inventan asociaciones por dominio o coincidencia de tablas.
2. Los archivos idénticos, SQL lexicalmente repetido, resultados de snapshots distintos y correcciones se conservan. {len(loadcsv('duplicate_files.csv'))} grupos de archivos idénticos; no eliminación.
3. No se acreditó equivalencia SQL completa ni «versión corregida/reemplazada» para cada par. Historia FAIL/PASS permanece en evidence_index y fuentes; un PASS de gate no convierte todo SQL cercano en validado.
4. Material privado quedó fuera del inventario. El connector oficial consumió su configuración para Foundation; no se imprimieron credenciales ni se accedió a SAP/servicios externos.
5. Referencias literales externas incluyen paths obsoletos y plantillas; external_references no presenta cada literal faltante como documento perdido. Markdown links existentes están en reference_integrity.

## Validación, impacto y continuación

La validación final se registra en validation_results.json y validation_commands.log. Los gates de inventario tienen alcance explícito; no se declara PASS integral desde el total de archivos.

Impacto transversal: ninguno sobre código/datos/configuración. Sólo nuevos archivos bajo este directorio; worktree previo preservado; sin commit, push, deploy, DDL/DML, SAP, modelos ni servicios creados. Los procesos SQL propios cerraron sus conexiones.

Próximo paso: completar el adjudicado semántico y los vínculos SQL→resultado del resto de investigaciones; después formalizar bindings/permisos y contratos de un primer conjunto de familias. No repetir SAP ni comenzar desde cero.
''')
print(json.dumps(summary,ensure_ascii=False,indent=2))

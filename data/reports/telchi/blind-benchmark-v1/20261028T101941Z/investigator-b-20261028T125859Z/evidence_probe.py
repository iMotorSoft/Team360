"""Private benchmark B evidence runner; existing reader/executor, no source changes."""
import os
os.umask(0o077)
import json, time, resource, fcntl
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
from modules.telchi.exploratory_sql.ask_sources import context_for_run, AskExecutor
from modules.telchi.exploratory_sql.foundation_dev import proposal

def utc(): return datetime.now(timezone.utc).isoformat()
def resources():
    m = dict(s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines())
    return dict(mem_available=m['MemAvailable'].strip(),swap_total=m['SwapTotal'].strip(),swap_free=m['SwapFree'].strip(),self_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,load=os.getloadavg())
base=Path(__file__).resolve().parent
start=time.monotonic()
report=dict(start_utc=utc(),start_monotonic=start,first_host_preflight_utc='2026-10-28T12:58:59Z',question='Durante 2026, ¿en qué mes vendimos más materias primas y cuál fue el cliente al que más le vendimos en ese mes?',clarification_human='Sí. Ambos investigadores recibieron la misma pregunta,\nestán congelados y utilizan Foundation snapshot 1408.\n\n"Más" significa mayor importe comercial facturado\nde líneas de venta, expresado en bolivianos (Bs).\nNo sumar cantidades físicas de unidades incompatibles.\n\n"Materias primas" significa productos identificados como\nmaterias primas mediante información empresarial acreditada\ndel Data Lake.\n\nInvestigá qué clasificación disponible permite identificar\nese universo. No supongas que el nombre del producto\nconstituye una clasificación oficial.\n\nSi la clasificación es incompleta, entregá los resultados\nverificables disponibles y explicá sus limitaciones.\n\nIdentificá el mes de mayor venta, el principal cliente\nfacturado de ese mes y los cinco principales clientes.\n\nDiferenciá meses completos de meses parciales.\n\nContinuá la investigación en modo READ_ONLY.',interpretation='Rank monthly commercial line amounts in observed Bs currency for accredited raw-material products; top five invoiced customers in winning month. No net billing interpretation.',hypotheses=['Authorized product projection may not expose an accredited raw-material classification.','Authorized invoice projection may not expose customer identity.','Observed document dates do not certify complete monthly coverage.'],resources_initial=resources(),queries=[],limitations=['No access to other researcher evidence.','Operational source foundation_dev.py contains legacy business prompt literals; not used as evidence or executed.','No OS RSS/CPU/scan-byte sandbox.','Pi LLM calls/tokens/cost not exposed to runner; no equal enforceable LLM cap to A. No auxiliary model calls.'])
def save():
    (base/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
context=context_for_run()
assert context.publication=='foundation_afd08d9eca6a725be53cdc3f9d5709c9' and context.snapshot=='1408'
report['context']=asdict(context)
report['catalog_findings']={'product_fields':[c.name for t in context.catalog.tables if t.name=='product' for c in t.columns],'customer_fields':[c.name for t in context.catalog.tables for c in t.columns if 'customer' in c.name or 'card_code' in c.name or 'card_name' in c.name],'classification':'No product classification field in authorized CATALOG; names not accredited membership. Salesperson category describes salesperson, not product.'}
report['first_useful_result_utc']=utc()
report['first_useful_result_monotonic']=time.monotonic()
save()
month='CASE '+ ' '.join(f"WHEN doc_date < '2026-{m+1:02d}-01' THEN '2026-{m:02d}'" for m in range(1,7))+' ELSE CASE '+ ' '.join(f"WHEN doc_date < '2026-{m+1:02d}-01' THEN '2026-{m:02d}'" for m in range(7,12))+" ELSE '2026-12' END END"
queries=[
('product',"SELECT COUNT(*) AS reference_rows, COUNT(DISTINCT item_code) AS distinct_item_codes, COUNT(item_name) AS named_rows, COUNT(inventory_uom_id) AS rows_with_uom FROM product"),
('sales_document',f"SELECT {month} AS month, currency, COUNT(*) AS documents, MIN(doc_date) AS first_document_day, MAX(doc_date) AS last_document_day, COUNT(DISTINCT doc_date) AS observed_days, MIN(source_as_of) AS earliest_source_as_of, MAX(source_as_of) AS latest_source_as_of FROM sales_document WHERE doc_date >= '2026-01-01' AND doc_date < '2027-01-01' GROUP BY {month}, currency ORDER BY month, currency LIMIT 30"),
('sales_operation',"SELECT currency, COUNT(*) AS lines, COUNT(DISTINCT item_code) AS distinct_items, COUNT(line_total) AS lines_with_amount, MIN(doc_date) AS first_document_day, MAX(doc_date) AS last_document_day FROM sales_operation WHERE doc_date >= '2026-01-01' AND doc_date < '2027-01-01' GROUP BY currency ORDER BY currency LIMIT 30")]
lock=open('/tmp/telchi-exploratory-dev-'+str(os.getuid())+'.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
try:
    with AskExecutor(context,authorized=True) as executor:
        for source,sql in queries:
            if time.monotonic()-start>1100: break
            p=proposal(sql,source)
            entry=dict(proposal=asdict(p),start_utc=utc(),start_monotonic=time.monotonic(),resources_before=resources())
            report['queries'].append(entry);save()
            decision,result=executor.execute(p,context)
            entry.update(decision=asdict(decision),result=asdict(result),end_utc=utc(),end_monotonic=time.monotonic(),resources_after=resources(),preflight=executor.last_preflight)
            save()
            observation=dict(query=len(report['queries']),decision=asdict(decision),result=asdict(result))
            text=json.dumps(observation,ensure_ascii=False,default=str)
            if len(result.rows)>30 or len(text.encode())>32768:
                print(json.dumps(dict(query=len(report['queries']),observation='Saved locally; egress bound exceeded')))
            else: print(text,flush=True)
            if result.status!='COMPLETED': break
except Exception as e:
    report['error']=dict(type=type(e).__name__,message=str(e));save();raise
finally:
    report.update(end_utc=utc(),end_monotonic=time.monotonic(),elapsed_runner_seconds=time.monotonic()-start,query_count=len(report['queries']),resources_final=resources())
    save()
    fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

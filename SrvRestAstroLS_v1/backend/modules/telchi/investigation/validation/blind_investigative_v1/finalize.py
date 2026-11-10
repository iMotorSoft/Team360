"""Package evidence and honest review; never executes business questions."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from .run import snapshot, ROOT, HERE

OUT = ROOT / 'data/reports/telchi/blind-investigative-v1'
base = json.loads((OUT / 'run-01/freeze-before.json').read_text())
after = snapshot()
changed = [p for p in sorted(set(base['files']) | set(after)) if base['files'].get(p) != after.get(p)]
questions_unchanged = hashlib.sha256((HERE/'questions.json').read_bytes()).hexdigest() == base['questions_sha256']
freeze = dict(frozen=not changed, changed_paths=changed, files=after,
              questions_unchanged=questions_unchanged, monitored_files=len(after),
              initial_runner_terminated=True, reason='Resource guard incident; SIGINT ignored by background child, own Python child terminated with SIGTERM. Runtime not modified.',
              own_pids=[323843,323846,329088,329091], unrelated_processes_terminated=0)
(OUT/'freeze-final.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
first = json.loads((OUT/'run-01/live.json').read_text())
last = json.loads((OUT/'question-12.json').read_text())
assert len(first['cases']) == 10 and len(last['cases']) == 1
questions = json.loads((HERE/'questions.json').read_text())['cases']
ordered = [(case,q) for case,qs in questions.items() for q in qs]
reviews = [
 ('PARTIAL','FUNCTIONAL_FAILURE','Parcial: reconoce cuentas/mes/BS pero reduce concentración conjunta a líder.','Baja: no entrega cinco cuentas ni 31,58890497 %.','No; respuesta de otro alcance estadístico.','A01_top5; A01_concentration'),
 ('BLOCKED','FUNCTIONAL_FAILURE','No representa exclusión del líder ni cociente residual.','Pide una aclaración pese al antecedente persistido.','Falla operativa con antecedente no vacío; no prueba pérdida física de memoria.','A02_without_leader'),
 ('COMPLETE','EMPTY_UNIVERSE','Interpreta productos con stock negativo y corte.','Baja legibilidad empresarial; cero correcto, no hay cinco ejemplos.','Primer turno; universo vacío, no demuestra conservación de entidades.','B03_population; B03_first5'),
 ('BLOCKED','EMPTY_UNIVERSE_DEPENDENCY','Pide una lista previa que era vacía.','No explica que no existen cinco productos seleccionables.','No evaluable sobre entidades reales; no inventa productos.','B04_negative_positions'),
 ('PARTIAL','FUNCTIONAL_FAILURE','Reconoce compras pero reemplaza recepción parcial por cantidad abierta no cero.','Incorrecta: 786 y ejemplos totalmente pendientes; cero líneas parciales en ambas versiones.','Primero selecciona cinco, publica tres incorrectas; no hay población parcial real.','C05_population; legacy_partial_population'),
 ('BLOCKED','INVALID_ANTECEDENT_DEPENDENCY','No relaciona líneas de compra con recepciones.','Solicita cinco líneas sin resolver el antecedente defectuoso.','No acredita continuidad; no prueba capacidad sobre un conjunto correcto no vacío.','C06_receipts'),
 ('BLOCKED','RESOURCE_BLOCKED','Plan de diversidad adecuado; hay evidencia SQL correcta antes del bloqueo.','No hay respuesta final utilizable; no puntuar como defecto del modelo.','Independiente.','D07_population; D07_top5'),
 ('BLOCKED','RESOURCE_BLOCKED','No evaluable: excepción host_io_or_memory_pressure.','Aborto ambiental, no fallo funcional demostrado.','Independiente; iniciada por defecto de control del runner.','E08_credit_incidence'),
 ('PARTIAL','FUNCTIONAL_FAILURE_SECONDARY_ONLY','Día, importe y cuentas correctos; porcentaje no resuelto.','728467,12 / 10827982,84; faltó 6,72763460 % y confirmar empates.','Independiente; resultado secundario posterior a incidente de guard.','F09_peak_day'),
 ('COMPLETE','EMPTY_UNIVERSE_SECONDARY_ONLY','Criterios exactos; cero códigos y líneas.','Correcta sobre vacío; presentación técnica, no demuestra análisis complejo.','Independiente; resultado secundario posterior a incidente de guard.','G10_zero_amount_population; G10_first5'),
 ('BLOCKED','ENVIRONMENTAL_ABORT','No evaluable: runner propio terminado durante este turno.','Sin respuesta final; no reintento.','Cruce ventas/stock no medido de extremo a extremo.','H11_population; H11_examples_NO_POSITION; H11_examples_ALL_NONPOSITIVE'),
 ('BLOCKED','EXECUTION_CONTRACT_BLOCK','Reconoce proveedor/importe pero insiste en ap_invoice histórico; no descubre observed_ap_invoice.','Sin cifras; cuatro execution_rejected y un join_pair_budget; no confundir con falta de permisos.','Independiente; único primer intento tras nuevo preflight seguro.','I12_total; I12_leader; legacy_ap_october'),
]
rows=[]
for idx,((case,question),review) in enumerate(zip(ordered,reviews,strict=True),1):
    raw=first['cases'][idx-1] if idx<=10 else last['cases'][0] if idx==12 else None
    status,cause,interpretation,quality,continuity,controls=review
    audit=(raw or {}).get('audit') or {}
    research=(raw or {}).get('research_evidence') or {}
    ra=audit.get('research') or {}
    calls=ra.get('model_calls',research.get('model_calls') or [])
    interpreter=(raw or {}).get('interpreter_metadata') or {}
    llm=interpreter.get('attempts',1)+len(calls) if raw else None
    sql=ra.get('sql_executions',0) if raw and idx!=1 else None
    rows.append(dict(question_number=idx,conversation=case,question=question,status=status,cause_class=cause,
        interpretation=interpretation,business_answer_quality=quality,continuity=continuity,
        control_names=controls.split('; '),primary_evidence=idx not in (9,10),
        latency_seconds=(raw or {}).get('elapsed_seconds'),llm_calls_observed=llm,
        research_sql_completed=sql,capability_calls=audit.get('capability_calls'),
        sql_metric_scope='research dataset executions only; operational PG/RBAC/history SQL not counted; capability SQL uninstrumented',
        route=audit.get('decision'),investigated=bool(research.get('queries')) if raw else None,
        raw_evidence='run-01/live.json' if idx<=10 else 'question-12.json' if idx==12 else 'question-11-aborted.json'))
assert len(rows)==12
for f in HERE.glob('*.py'):
    ast.parse(f.read_text())
report=dict(status='EVALUATED_WITH_PROTOCOL_DEVIATION_AND_ENVIRONMENTAL_ABORTS',
    raw_totals=dict(Counter(r['status'] for r in rows)),
    primary_totals=dict(Counter(r['status'] for r in rows if r['primary_evidence'])),
    primary_exclusions=[9,10], frozen=freeze['frozen'], questions_unchanged=questions_unchanged,
    schema_syntax_and_protocol_checks='PASS', evaluations=rows,
    not_enterprise_certification=True, deepseek_comparison='NOT_RUN; Pi independent SQL controls have broader SQL tools and are not a model-isolated baseline')
(OUT/'matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('FINAL',report['raw_totals'],'PRIMARY',report['primary_totals'],'FROZEN',freeze['frozen'])
print('git diff --check',subprocess.run(['git','diff','--check'],cwd=ROOT).returncode)

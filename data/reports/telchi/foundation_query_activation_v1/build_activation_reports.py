"""Build a focalized activation matrix from existing inventory, not a new scan."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT.parent / 'historical_business_query_inventory_v1'


def read_csv(name):
    with (INVENTORY / name).open() as stream:
        return list(csv.DictReader(stream))


def md(name, content):
    target = ROOT / name
    if target.exists():
        raise RuntimeError('Refuse overwrite of report: ' + name)
    target.write_text(content.strip() + '\n')


operations = read_csv('verified_operations.csv')
sqls = {r['sql_id']: r for r in read_csv('sql_master.csv')}
questions = {r['question_id']: r for r in read_csv('questions_master.csv')}
links = read_csv('question_sql_links.csv')
readiness = read_csv('foundation_readiness.csv')
manifest = json.loads((INVENTORY / 'coverage_manifest.json').read_text())
assert len(operations) == 30
assert Counter(o['reuse_status'] for o in operations) == {'READY_FOUNDATION': 9, 'READY_CONDITIONAL': 8, 'REQUIRES_METRIC_DEFINITION': 13}
rows = []
for op in operations:
    native_sql = [sqls[s] for s in op['sql_ids'].split('|')]
    assert op['question_ids'] in questions
    for s in native_sql:
        assert any(l['question_id'] == op['question_ids'] and l['sql_id'] == s['sql_id'] for l in links)
    area = 'VENTAS' if op['operation_id'].startswith('sales_') else 'STOCK_E_INVENTARIOS' if op['operation_id'].startswith('oitw_') else 'TRAZABILIDAD_DOCUMENTAL'
    row = dict(op, area=area, historical_sql='\n'.join(s['sql_text'] for s in native_sql),
        canonical_tables=' | '.join(s['tables'] for s in native_sql),
        inventory_grain=' | '.join(s['grain'] for s in native_sql),
        filters=' | '.join(s['filters'] for s in native_sql),
        metrics=' | '.join(s['metrics'] for s in native_sql),
        potential_parameters=' | '.join(s['potential_parameters'] for s in native_sql),
        priority='P0' if op['operation_id'] in {'sales_exact_document','sales_document_lines','sales_monthly_august','sales_by_item','sales_top_items'} else 'P1' if op['operation_id'].startswith('sales_') else 'NEXT_DOMAIN',
        assistant_aptitude='BLOCKED_NEW_GRANT_REQUIRED; additional original semantic reservations preserved',
        independent_test='foundation_comparison.json for derived latest/coverage; original operation reproduction is historical, not rerun',
        permission='existing fixed ranking grant only' if op['operation_id']=='sales_top_items' else 'NO_APPROVED_OPERATION_GRANT')
    if op['operation_id']=='sales_top_items':
        row['assistant_aptitude']='EXISTING_FIXED_DOCUMENTARY_RANKING_ONLY; not generic top sellers'
    rows.append(row)
with (ROOT / 'SELECTED_HISTORICAL_QUERIES.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
# These are discovery/census references, NOT two new members of the 30 EXACT operations.
extra = ['HS-e24b48c12f48051f9e', 'HS-6e541cc586d91546bc']
(ROOT / 'supplementary_inventory_references.json').write_text(json.dumps([sqls[s] for s in extra], indent=2, ensure_ascii=False)+'\n')

comparison = json.loads((ROOT / 'foundation_comparison.json').read_text())
preflight = json.loads((ROOT / 'preflight_and_trace.json').read_text())
current = comparison['binding']
runtime = json.loads((ROOT / 'runtime_http_r2/runtime_http_results.json').read_text())
legacy = json.loads((ROOT / 'legacy_runtime_http_r2/runtime_http_results.json').read_text())
assert sum(len(s['turns']) for s in legacy['scenarios']) == 32
assert not any(t['classification']=='ERROR' for s in legacy['scenarios'] for t in s['turns'])

matrix = '\n'.join('| '+ ' | '.join([o['operation_id'], o['question_ids'], o['sql_ids'], o['reuse_status'], o['semantic_definition'].replace('|','/'), 'BLOCKED grant' if o['operation_id']!='sales_top_items' else 'Fixed V1 only'])+' |' for o in operations)
md('ACTIVATION_PLAN.md', f'''# Foundation Query Activation V1

Incremento DEVELOPMENT en Telchi. Selección y paridad técnica acreditadas; activación empresarial nueva bloqueada por permisos explícitamente limitados. No se declara BUSINESS_PASS ni RUNTIME_PASS nuevo.

## Resultado ejecutivo

La evidencia existente permite implementar hechos documentales sin inventar métricas. El permiso real no autoriza exponerlos al piloto; esa frontera se mantuvo cerrada.

- Rama `feature/console-backend-core`; HEAD inicial `09d2ec715a31bb88574d734eacb9f437f008624e` conservado.
- Foundation CURRENT `{current['foundation_publication_id']}`, snapshot `{current['ducklake_snapshot_id']}`; sin promoción, SAP, DDL/DML empresarial ni modificaciones de Parquet.
- Implementadas `sales.latest_documents` y `sales.coverage`: SQL parametrizado, Foundation pinned, worker acotado y State Engine existente. Véase [contratos](SALES_QUERY_CONTRACTS.md).
- Grant existente real: `telchi.sales.source_quantity.read.v1`. Descripción PostgreSQL: **Only** `telchi.sales_top_items.source_quantity.20260101_20260915.v1`; excluye **other capabilities**.
- No hay ninguna nueva candidata P0 autorizada al piloto. Habilitar coverage bajo ese grant sería una ampliación prohibida, aunque sólo entregue fechas. Véase [preflight read-only](preflight_and_trace.json).
- Dos paridades SQL independientes PASS; HTTP real nuevo muestra DENIED sin ejecución, no respuestas empresariales nuevas. Ranking previo devuelve datos reales.
- Regresión HTTP inicial: ocho CONTRACT_ERROR de continuidad. Se preservó la evidencia, se corrigió el contrato del prompt sin cambiar modelo/guard y se repitieron los 32 turnos: cero ERROR. No se usa HTTP 200 como criterio.

## Selección y bloqueos P0

Las referencias discovery/census no se presentan como nuevas operaciones EXACT del registro de treinta.

| Operación | Evidencia histórica | SQL Foundation | Semántica | Implementación | HTTP real |
| --- | --- | --- | --- | --- | --- |
| Últimas facturas activas | HS-e24b48c12f48051f9e; HQ-703df2860ba482327d / HS-604de2e2e229ed2525; sonda latest_sales_documents | PASS independiente | PASS documental DocDate; no timestamp de registro | PASS técnica | BLOCKED nuevo grant |
| Ventas por período | HQ-cf162105a169e5ec63 / HS-7b42e2b4867a054e81 | Histórico VALIDATED_SQL; mayo DocTotal sondeo, no nuevo total neto | GAP neto genérico; NC/impuestos/descuento por definir | BLOCKED métrica y grant | BLOCKED semántica |
| Cobertura temporal | HS-6e541cc586d91546bc; HQ-db9e682ef8aa01cdd1 | PASS independiente | PASS facturas activas; GAP mes completo | PASS técnica | BLOCKED nuevo grant |
| Calenta | HQ-fbdda4165b64b30810 / HS-56822a0ce444d328eb | PASS histórico SKU exacto; GAP join de namespaces | GAP familia/aliases/UoM | BLOCKED mapping y grant | BLOCKED mapping |
| Más vendidos | HQ-75ddaf55d0ace2fbab / HS-99232ce7f29843ba20 | V1 preservado | Sólo ranking Quantity documental fijo; no ranking físico | EXISTING V1 | PASS compatibilidad; no nueva operación |

## Matriz de treinta operaciones

Se conserva la clasificación original 9/8/13, preguntas, SQL y referencias. Cada fila del CSV agrega parámetros, grano del inventario, riesgo y aptitud; READY_FOUNDATION nunca se convirtió en autorización.

| Operación | Pregunta ID | SQL ID | Clase histórica | Definición fuente | Aptitud TelchiAI |
| --- | --- | --- | --- | --- | --- |
{matrix}

## Próxima tanda sin SAP

Se requiere una decisión humana de acceso antes de una nueva respuesta comercial, no una reingesta ni otro motor.

1. Autorizar y provisionar por el mecanismo existente los grants específicos de últimos documentos/cobertura para una identidad/workspace DEV aprobados; no se ejecutó ese cambio.
2. Repetir TQ01/TQ03 por el runner existente y comparar sus resultados HTTP completos con referencia SQL. Sólo entonces RUNTIME_PASS y BUSINESS_PASS.
3. SKU explícito: resolver crosswalk namespace y unidad documental, después reutilizar sales_by_item. Calenta libre permanece ambiguo.
4. Importe documental vs neto: adoptar contrato explícito por moneda, impuesto/descuento y NC. No sustituir importe por cantidad ni bloquear futuros hechos nativos por esa deuda.
''')

md('SALES_QUERY_CONTRACTS.md', '''# Sales Query Contracts

Contrato cerrado de dos lecturas documentales candidatas. No incluye importe ni suma física; cada operación nueva exige un grant propio además del acceso base y del scope workspace aprobado.

## Parámetros y permisos

La allowlist se valida antes de crear el worker. No se interpolan valores, entidades ni columnas del modelo en SQL.

| Operación interna | Capability | Parámetros | Grant específico |
| --- | --- | --- | --- |
| sales.latest_documents | sales.latest_documents.v1 | limit entero estricto 1..50, default 10 | telchi.sales.latest_documents.read.v1 |
| sales.coverage | sales.coverage.v1 | ninguno; referencia latest_available_month permitida | telchi.sales.coverage.read.v1 |

`date_from`, `date_to_exclusive`, `entity_type`, `entity_id`, `metrics`, `group_by`, `sort` no se aceptan por este servicio: no son parámetros autorizados de estas dos operaciones. No hay query genérica ni SQL del modelo.

`limit` es opcional compatible con estados anteriores; NEW_QUERY no lo hereda. Períodos del State Engine conservan ISO y máximo 366 días para otras métricas. No se exige período a latest/coverage. Entidad, sucursal, canal, comparación, período concreto y solicitudes multimétrica bloquean esta primera versión.

## Hechos y resultados

Las dos consultas leen sales_document, fuente SAP_B1_HANA, CANCELED=N. Son facturas OINV activas por fecha documental, no movimientos de producción, registro cronológico ni ventas netas.

Latest: grano cabecera; source_system + doc_entry es identidad fuente. Orden DocDate DESC, DocEntry numérico DESC y desempate textual; se excluyen fechas nulas. Devuelve DocEntry, DocNum, DocDate y N. No expone cliente, líneas, productos, Quantity, moneda ni DocTotal en esta versión. Esos campos existen históricamente, pero no se aprobó su exposición/semántica adicional.

Coverage: primera/última DocDate y número de cabeceras activas con fecha; último mes se toma de la última fecha real. `complete_month_certified=False` siempre. No certifica historia completa, cobertura monetaria, ventas netas ni último mes cerrado. Sin filas devuelve cobertura desconocida, nunca ventas cero.

Cancelaciones Y/C excluidas expresamente; notas de crédito excluidas de ambas relaciones. No se computan impuestos, descuentos ni importes. No hay agregación de unidades incompatibles ni atribución comercial por descripción.

## Fronteras de ejecución

No se cambió identidad, Messaging, Srv05, modelo ni State Engine por otro sistema. El registro SalesCapabilities es la implementación existente extendida, no un motor paralelo.

TelchiHandler sólo entra tras `committed is True`, acción EXECUTE y availability. Revalida el permiso base y el grant específico con PermissionConsoleRepository; el permiso en identidad no sustituye la revalidación PostgreSQL. Nuevo acceso exige tenant Telchi, entorno DEV y workspace coincidente. Rechazos ejecutan cero capabilities y cero lecturas Foundation.

El worker verifica attachment read-only y CURRENT exacto 1408/publicación aprobada; si CURRENT cambia falla cerrado. Usa dos threads, 512 MB, sin temp spill; timeout 30 s y reap del hijo propio. No escribe datos Foundation, snapshots ni configuración global. La persistencia conversacional existente del runner HTTP sí escribe auditoría PG, como requiere su contrato; no se confundió con DML empresarial.

El grant real del piloto sólo autoriza V1 fijo. Los nuevos códigos no fueron insertados, concedidos ni usados como permisos implícitos. Toda activación queda pendiente de autorización y provisioning explícitos.
''')

old = json.loads((INVENTORY / 'foundation_business_cases.json').read_text())
probes = {r['probe_id']: r for r in old['queries']}
products = [r for r in probes['calenta_products']['rows'] if r['item_code'].startswith('L')]
pt = '\n'.join(f"| {r['item_code']} | {r['canonical_product_id']} | {r['product_name']} | {r['sap_sell_item']} |" for r in products)
ct = '\n'.join(f"| {r['item_code']} | {r['native_quantity']} | {r['native_line_total']} | {r['currency']} | {r['canceled']} |" for r in probes['calenta_exact_skus_may']['rows'])
md('CALENTA_RESOLUTION.md', f'''# Calenta Resolution

Brecha delimitada, no alias nuevo. Evidencia sellada del inventario reutilizada al comprobar CURRENT 1408; no se declaró una marca, familia o cliente único por semejanza textual.

## Identificadores acreditados

Reference SAP_HANA contiene estos productos. Las dos presentaciones KG son SellItem=N; las demás no prueban por sí solas finalidad comercial externa.

| SKU | ID canónico Reference | Descripción original | SellItem |
| --- | --- | --- | --- |
{pt}

## Relación que falta

La igualdad de claves físicas y la equivalencia de namespaces son garantías distintas. No se añadió un join correctivo ni un crosswalk sin provenance.

Atomic sales_line/sales_document: `source_system=SAP_B1_HANA`. Reference products: `source_system=SAP_HANA`, clave `item_code`, ID `canonical_product_id`. Falta una relación publicada y autorizada que mapee `(SAP_B1_HANA, item_code)` a `(SAP_HANA, item_code, canonical_product_id)` con evidencia de equivalencia y unicidad.

La sonda `may_calenta_native_lines` une namespaces literalmente y retorna vacío. La sonda `calenta_exact_skus_may`, por SKU exacto, demuestra filas. Ese vacío **no** demuestra ausencia de ventas.

Aliases en `entity_aliases`: PRODUCT con `alias_source=reference.products:SAP_HANA`; hay AMBIGUOUS para Calenta 30 g y KG y MAPPED para determinadas presentaciones Forte. Un alias de presentación MAPPED no acredita una familia Calenta/Forte conjunta. Brand sigue UNKNOWN; customers no tuvo matches en la sonda, no prueba inexistencia universal de un cliente.

LIKE también encuentra INCUBADORA...CALENTADOR y Horno de CALENTAMIENTO en otros namespaces. Es discovery, no resolución ni filtro autorizado.

## Ventas documentadas por SKU

Resultados históricos de mayo CURRENT 1408, no nuevos resultados HTTP. Cantidades nativas por SKU y LineTotal fuente; UoM de catálogo no sustituye unidad/factor de línea.

| SKU | Quantity fuente | LineTotal fuente | Moneda | Cancelación |
| --- | --- | --- | --- | --- |
{ct}

Referencias: HQ-fbdda4165b64b30810 / HS-56822a0ce444d328eb; `foundation_business_cases.json` del inventario, sondas calenta_products/calenta_aliases/calenta_exact_skus_may. El detalle original se conserva en [comparación](foundation_comparison.json).

TQ04/TQ12 mantienen la mención sin inventar tipo, ID, familia ni ventas cero. Estado REQUIRES_MAPPING; además no existe grant de consulta por SKU/entidad. Próximo paso: crosswalk namespace con provenance, selección comercial explícita y contrato documental UoM antes de publicar un alias familiar.
''')

sql_text = ''
for op, r in comparison['service'].items():
    ref = comparison['comparisons'][op]
    sql_text += f'''\n## {op}\n\nParidad exacta read-only de filas, fechas, IDs, estados, límites y orden. No equivale a BUSINESS_PASS HTTP autorizado.\n\nServicio ({r['sql_duration_ms']:.3f} ms), parámetros `{r['sql_parameters']}`:\n\n```sql\n{r['sql']}\n```\n\nReferencia independiente ({ref['elapsed_ms']:.3f} ms), parámetros `{ref['parameters']}`:\n\n```sql\n{ref['sql']}\n```\n\nResultado: `{json.dumps(r['rows'], ensure_ascii=False)}`. Diferencias: ninguna.\n'''
md('FOUNDATION_SQL_COMPARISON.md', '''# Foundation SQL Comparison

Se ejecutó cada operación candidata y un algoritmo SQL independiente sobre CURRENT verificado. Permisos del usuario se prueban aparte: esta comparación de auditoría no autoriza exposición por el handler.

Latest usa ROW_NUMBER frente a LIMIT; coverage usa fechas distintas ordenadas y suma de conteos por fecha frente a MIN/MAX/COUNT. No se copió el builder como oracle. Misma población explícita: facturas activas N, SAP_B1_HANA, fecha no nula.

Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408. Cobertura activa cuenta 330429, no 330443 de la sonda histórica con todos los estados: diferencia de población deliberada. Última fecha 2026-09-24; último mes con filas 2026-09; no se certifica agosto ni septiembre completos.

SQL fuente, parámetros, filas, latencias y binding completos en [foundation_comparison.json](foundation_comparison.json). No hay cantidades, unidades, importes, signos ni monedas en el nuevo contrato: comparación monetaria/física NOT_APPLICABLE, no PASS inventado.
''' + sql_text)

turn_lines = []
for s in runtime['scenarios']:
    for t in s['turns']:
        turn_lines.append(f"| {s['id']} | {t['user_text']} | {t['classification']} | {t['committed']} | {t['execution_status']} | {t['metric']} |")
md('BUSINESS_RUNTIME_RESULTS.md', '''# Business Runtime Results

Preguntas reales por curl al adaptador existente, misma cadena Srv05 DEV, identidad y permisos PostgreSQL. No hay WhatsApp outbound. Ninguna operación nueva obtuvo BUSINESS_PASS: permisos específicos ausentes.

## Escenarios focalizados

Resultado final con Luna GPT-5.6 Medium, sin fallback ni otro verificador. La auditoría conservada distingue intención, commit, disponibilidad y ejecución real.

| Test | Pregunta | Clasificación | Committed | Ejecución | Métrica |
| --- | --- | --- | --- | --- | --- |
''' + '\n'.join(turn_lines) + '''

TQ01/TQ03/TQ09: DENIED, committed=True, execution_status=not_executed, execution_result=null. Respuesta: «requiere un permiso comercial específico. No se consultó Foundation». No se declara consulta empresarial autorizada desde ese HTTP.

TQ02/TQ06: aclaración material importe/cantidad; mes completo conserva mayo y seguimiento abril. No se implementó importe genérico sin definición. TQ05 no sustituye importes por cantidades. TQ04/TQ12 no inventan Calenta ni ausencia de ventas. TQ11 no ejecuta agregación física; ese bloqueo mensual no acredita comprensión universal de unidades incompatibles.

TQ10 no se expone mediante campo HTTP falsificable: prueba de guard inyecta committed=False en el handler real de test y exige cero llamadas. El adapter no permite que un cliente controle committed, identidad ni grants.

TQ07 inicial ejecutó V1 existente; TQ07 final quedó bloqueado porque Luna propuso fin exclusivo 2026-09-17 sin período solicitado. Esa limitación conversacional no demuestra ausencia de datos. El registry no amplió la ventana. La corrida legacy final ejecutó dos lecturas V1; sólo su compatibilidad fija se declara PASS.

## Regresión anterior

Se conservaron dos corridas completas del runner sin cambiar sus doce escenarios ni treinta y dos turnos. La segunda usa el prompt corregido y mantiene el guard estricto.

Primera corrida: 8 ERROR, todos propuestas rechazadas sin ejecución, causados por ASK metric manteniendo métrica elegida y por EXECUTE monetario sin período. Se corrigió Luna para que «las dos» signifique importes/cantidades y no límite 2; no se flexibilizó el State Engine. Evidencia inicial en legacy_runtime_http/runtime_http_results.json.

Final: 12 escenarios/32 turnos, 0 ERROR; 28 DIRECT_UNAVAILABLE, 2 DIRECT_AVAILABLE V1, 1 ANALYSIS_UNAVAILABLE, 1 NEEDS_CLARIFICATION. Rechazos y semánticas pendientes no se contabilizan como fallo funcional. Evidencia en [legacy final](legacy_runtime_http_r2/runtime_http_results.json).

Nuevos: [runtime final](runtime_http_r2/runtime_http_results.json), once escenarios HTTP/doce turnos más TQ10 unitario. Primeras corridas y logs preservados; los owners de auditoría se redactaron del export por minimización.
''')

md('WHATSAPP_MISSING_MESSAGE.md', '''# WhatsApp Missing Message

Estado EVIDENCE_INSUFFICIENT para «Ventas de mayo 2026», 12/10/2026. No se atribuye el silencio a semántica o al handler sin un inbound correlacionable.

## Trazabilidad focalizada

Consultas read-only acotadas en PostgreSQL y Evolution. No hubo envío, replay, cambio de webhook ni edición de Messaging.

| Etapa | Evidencia | Conclusión |
| --- | --- | --- |
| Evolution inbound | Últimos 100 de 135 mensajes; sin match exacto en la página consultada | Parcial; no demuestra no recibido |
| Webhook/Srv05 | GET actual: enabled=false, events=[]; URL configurada | Configuración actual, no prueba de configuración a la hora del mensaje |
| Dispatcher/identidad | No inbound exacto en canal Telchi DEV el 12/10 UTC para la frase | No reconstruible por ID; no afirmar rechazo |
| Estado/handler | Sin evento correlacionable | No afirmar procesado ni sin respuesta |
| Outbound intent/publicación | Sin inbound correlacionable | No acreditar envío, fallo ni entrega |
| Entrega observable | Conversación compartida sin respuesta visible | Evidencia de interfaz, no confirmación de recepción técnica |

[preflight_and_trace.json](preflight_and_trace.json) y [evolution_trace.json](evolution_trace.json) conservan estados minimizados. Búsqueda PG estricta por fecha UTC y redacción exacta tiene límite de zona horaria/variantes; no se considera búsqueda exhaustiva del canal. Historia Evolution excede el bound y no se ocultó esa condición.

Próximo paso: aportar provider message ID o timestamp/zona exactos para correlacionar inbound → dispatcher → intent → provider status. El webhook actual deshabilitado es un riesgo operacional verificable, no un defecto de código demostrado ni autorización para activarlo.
''')

md('GATES.md', '''# Activation Gates

Cierre PARTIAL: implementación y paridad SQL documental demostradas, pero ninguna nueva consulta empresarial autorizada produjo datos HTTP. No se amplió el grant fijo ni se fabricaron métricas/mappings.

```text
TELCHI_HISTORICAL_QUERY_SELECTION=PASS
TELCHI_SALES_LATEST=PARTIAL
TELCHI_SALES_PERIOD_SUMMARY=BLOCKED
TELCHI_SALES_COVERAGE=PARTIAL
TELCHI_CALENTA_ENTITY_RESOLUTION=BLOCKED
TELCHI_SALES_TOP_PRODUCTS_COMPATIBILITY=PASS
TELCHI_SALES_SQL_REFERENCE_PARITY=PASS
TELCHI_SALES_METRIC_SEMANTICS=PARTIAL
TELCHI_SALES_PERMISSION_ENFORCEMENT=PASS
TELCHI_SALES_STATE_ENGINE_GUARD=PASS
TELCHI_SALES_RUNTIME_HTTP=PARTIAL
TELCHI_WHATSAPP_MISSING_MESSAGE_TRACE=PARTIAL
TELCHI_FOUNDATION_QUERY_ACTIVATION_V1=PARTIAL
```

## Evidencia y alcance

Los PASS se restringen a garantías observadas, no se transfieren entre estados de dato, implementación y autorización.

- Selección: treinta cadenas originales, 9/8/13 preservado en SELECTED_HISTORICAL_QUERIES.csv; cobertura/discovery identificados aparte, no sumados como EXACT.
- Latest/coverage: DISCOVERED → VALIDATED_SQL → definición documental defendible → IMPLEMENTED. Sin RUNTIME_PASS ni BUSINESS_PASS por grants nuevos ausentes.
- Paridad SQL: latest diez IDs/fechas/orden y cobertura 330429 cabeceras activas, septiembre hasta 24/09; dos algoritmos oracle independientes y binding 1408 comprobado.
- Permisos: grant PG **only V1**, nuevos grants no existen; tests de permiso presente/revocado y HTTP DENIED antes de Foundation. No se hizo DDL/DML empresarial ni auth provisioning.
- Guard: committed=False nunca llega al registry/Foundation; validación de parámetros/resultados, rechazo retiene estado y no reejecuta plan anterior.
- Compatibilidad: tests V1 y batería final de doce escenarios/treinta y dos turnos, cero ERROR; primera regresión corregida y preservada.
- Monetario/Calenta: bloqueos concretos de contrato, namespace/alias, UoM y grant; sin respuesta parcial monetaria ficticia.
- WhatsApp: evidencia insuficiente; webhook actual deshabilitado no prueba cronología del incidente.

## Archivos de implementación

Sólo scope Telchi; cambios preexistentes preservados. Ninguna edición en Messaging, Evolution, Flow, Diagnosis, Console/Auth, Srv01, launchers ni dependencias.

- modules/telchi/datalake/sales_query.py (nuevo).
- modules/telchi/assistant/capabilities.py, handler.py, state_engine.py, luna.py (extensión localizada).
- modules/telchi/assistant/tests/test_sales_query_activation.py (nuevo).
- modules/telchi/assistant/tests/runtime_http/run_battery.py (escenarios opt-in, default previo intacto).
- Artefactos propios: data/reports/telchi/foundation_query_activation_v1/.

## Validación y recursos

Comandos, resultados y limitaciones de esta ejecución; no se declara PASS por un HTTP 200 ni por evidencia previa sin binding vigente.

- `uv run pytest modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py modules/telchi/datalake/tests/test_messaging_sales_query.py -q`: 126 PASS, una advertencia baseline de repositorio diagnosis in-memory en composición fixture.
- `verify_activation.py`: PG 18.4 read-only, grants efectivos, CURRENT 1408 y dos paridades SQL PASS.
- `live_probe --luna --preflight`: provider OpenAI directo/modelo GPT-5.6 Luna Medium autenticado, respuesta real sin fallback; Milvus/LiteLLM no consumidos por esta cadena.
- Runner HTTP existente: dos corridas focalizadas y dos legacy; resultado final consignado en BUSINESS_RUNTIME_RESULTS.md. Servidores propios reaped por el runner; sin outbound WhatsApp.
- LAT y revisión final: ver validation_commands.log generado al cierre; sólo declarables después de ejecutar los gates.

HOST_PREFLIGHT=SAFE; RESOURCE_GUARD=PASS; CONCURRENCY_USED=2 threads DuckDB por conexión, un worker SQL o servidor propio a la vez, tests secuenciales sin xdist.
MemAvailable inicial ~7.5 GB, carga 1.28/2.65/3.08 en 8 cores, vmstat sin swap creciente sostenida; posterior ~7.3 GB y carga ~1.1. No se iniciaron browsers ni scans amplios.
UNRELATED_PROCESSES_TERMINATED=0; ENVIRONMENTAL_ABORTS=0. Cleanup: los runners confirman pid_reaped; workers SQL síncronos cerraron conexiones y subprocess SQL tiene reap propio.

## Siguiente decisión requerida

La limitación no se elimina cambiando SQL o dando por implícito un permiso. Se requiere autorización de alcance empresarial y provisioning separado, preservando el grant V1 existente.

Autorizar explícitamente `telchi.sales.latest_documents.read.v1` y `telchi.sales.coverage.read.v1` para una identidad/workspace DEV aprobados. Después repetir las dos preguntas por HTTP y cotejar sus filas; hasta entonces el objetivo comercial permanece incompleto.
''')
print('Created eight requested reports and thirty-operation CSV; no inventory regeneration')

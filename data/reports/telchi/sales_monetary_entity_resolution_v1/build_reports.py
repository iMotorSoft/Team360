"""Build the nine scoped reports from preserved evidence, not model estimates."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
MODULE = '../../../../SrvRestAstroLS_v1/backend/modules/telchi/'
ref = json.loads((OUT/'foundation_reconciliation.json').read_text())
parity = json.loads((OUT/'http_reference_comparison.json').read_text())
auth = json.loads((OUT/'effective_authorization.json').read_text())
http = json.loads((OUT/'business_http_current/runtime_http_results.json').read_text())
ranking = json.loads((OUT/'ranking_http_current/runtime_http_results.json').read_text())


def doc(name, title, body):
    (OUT/name).write_text('# '+title+'\n\n'+body.strip()+'\n')


def link(path, label):
    return f'[{label}]({MODULE}{path})'


contract = link('investigation/FINANCIAL_REPORTING_CONTRACT.md', 'contrato financiero histórico')
corporate = link('investigation/validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md', 'informe corporativo original')
executive = link('datalake/executive_sales.py', 'implementación monetaria Foundation previa')
doc('HISTORICAL_BILLING_EVIDENCE.md', 'Historical billing evidence', f'''
La facturación no era desconocida: existen contrato financiero, informes con montos, SQL financieros originales e implementación Foundation monetaria previa. La recuperación específica distingue evidencia documental de ejecución y recepción.

## Definición recuperada

La selección reutiliza DocTotal documental y las reglas del contrato oficial, sin crear una venta neta por producto ni convertir cobros en facturación.

- {contract}, versión 1.0.0 del 21/08/2026, §§2, 13 y 18: SALES_VALID_GROSS = facturas N; SALES_CREDIT_NOTES = NC N positivas; SALES_NET = diferencia. «Cuánto vendimos» corresponde a SALES_NET.
- {corporate}, 20/08/2026, §§A/J/L/P/R/S: declara monto corporativo entregado; grano DocEntry único y controles de doble conteo. No existe comprobante externo de recepción en la evidencia revisada.
- {executive}: SQL exacto previo con CTE invoices/credits, DocTotal DECIMAL(38,6), fechas exclusivas, moneda BS y categoría corporativa 2. ID de índice HS-d5edfa79b93bef8444. No se afirma que el texto dinámico sea el SQL literalmente ejecutado el 20/08.
- {link('investigation/sql/current/financial/invoice_contract_v1.sql', 'SQL FINANCIAL-001')} y {link('investigation/sql/current/financial/credit_note_contract_v1.sql', 'SQL FINANCIAL-002')}: extracción financiera original de cabeceras y campos fiscales; preservados, no ejecutados contra SAP.

## Cálculos históricos localizados

Los valores siguientes son históricos, no resultados nuevos ni prueba de aceptación individual. Las referencias permiten conservar sus universos sin fusionarlos.

| Cálculo / pregunta | Resultado original | Período y fecha declarada | Fuente / grano | Reglas y validación | Entrega / limitación |
| --- | --- | --- | --- | --- | --- |
| Ventas corporativas de agosto 2026 | facturas 1.516.859,75; NC 45.889,46; neto 1.470.970,29; 376 facturas / 7 NC | MTD 01/08–20/08, informe 20/08/2026; timestamp fino y exclusividad del día final no acreditados | OINV, ORIN, OSLP; DocEntry; categoría vendedor 2 | N; NC restadas una vez; descuentos incluidos en DocTotal según §J; impuestos no desglosados; §S declara unicidad y controles | §A declara delivered; sin acuse externo. Original usa símbolo $, no codifica DocCur; no inferir USD. BS explícito en implementación ejecutiva posterior |
| Luz, mismo informe | 220.870,83 facturas − 4.594,66 NC = 216.276,17 | mismo MTD | SlpCode 13 / cabecera | misma definición, no canal transaccional | misma declaración de informe, no aceptación individual demostrada |
| Vendedores corporativos, mismo informe | Selva 741.459,63; Heglin 332.673,79; Diego 180.560,70 netos | mismo MTD | SlpCode 11/139/236 | suman con Luz el neto corporativo; no total compañía | no ampliar a venta horizontal |
| Corporativo agosto 2022, §H | Federico 2.310.292,86; Selva 2.301.950,88; Kaly 454.814,92; Luz 698.029,55 DocTotal | agosto 2022, revisión del 20/08/2026 | Parquet histórico; informe muestra rows | NC/impuestos/moneda/grano de agregado 2022 no suficientemente acreditados | no seleccionado para implementación ni certificado por ausencia de reclamos |
| Agosto mensual directo / productos / clientes / almacenes | registro histórico EXACT, Quantity y LineTotal | agosto y otras ventanas del registry, cutoff histórico 15/09/2026 | líneas DocEntry+LineNum | sin filtro universal de cancelación ni NC; SUM Quantity multi-SKU no es unidad física | operación ejecutada, no evidencia automática de entrega; no sustituye DocTotal |
| Ejecutivo septiembre / venta horizontal | SQL ejecutivo y clasificación de series existentes | función parametrizada; rótulo septiembre no prueba ejecución | Foundation, DocTotal; clasificación distinta de categoría vendedor | no fusionar atributo vendedor, canal de cliente y canal transaccional | no se recuperó un monto septiembre entregado verificable en esta búsqueda focalizada |

El artefacto externo `investigation-consolidation-v1/files/validation/corporate_sales/august_2026_corporate_sales.json` conserva esos resultados y la fecha declarada. El directorio histórico `TELCHI_DATALAKE_EXECUTIVE_SALES_FOUNDATION_V1` estaba vacío al inspeccionarlo: sus referencias de índice no se transforman en resultados disponibles.

## Aceptación y fidelidad

La declaración expresa del responsable se conserva como evidencia contextual: Telchi recibió informes monetarios y no reclamó. No se atribuye automáticamente esa ausencia de reclamos a cada cifra anterior.

SQL existente, resultados declarados, validación declarada, entrega declarada, utilización contextual y reconciliación nueva son niveles distintos. Falta recuperar el SQL agregado literalmente ejecutado para el informe corporativo y comprobantes externos, si existen. HISTORICAL_BILLING_RECOVERY=PARTIAL; la definición documental seleccionada sí está explícita y se verifica técnicamente ahora.

La recuperación usó los CSV/índices ya existentes y los reportes de activation/RBAC. No se repitió la auditoría de 4.186 archivos, no se ejecutó SAP ni se inventó otra métrica.
''')

doc('BILLING_SEMANTICS.md', 'Billing semantics', f'''
Se reutiliza el contrato financiero histórico: facturación válida y ventas netas documentales son magnitudes distintas, expuestas simultáneamente y etiquetadas.

Autoridad: {contract}.

| Aspecto | Contrato seleccionado |
| --- | --- |
| Facturación válida | SALES_VALID_GROSS = SUM OINV.DocTotal con CANCELED=N |
| Notas de crédito | SALES_CREDIT_NOTES = SUM ORIN.DocTotal con CANCELED=N; importe positivo fuente |
| Ventas solicitadas | SALES_NET = facturación válida − NC; criterio oficial histórico para «Ventas de mayo» |
| Moneda | BS únicamente; sin USD, conversión ni mezcla de monedas |
| Grano | Una cabecera por (source_system, DocEntry), separada por tipo OINV/ORIN; sin join de líneas |
| Fechas | DocDate >= date_from y DocDate < date_to_exclusive; nunca fecha de cobro, actualización o ingestión |
| Cancelaciones | N exclusivamente; excluye Y y reversas C; estado publicado, no reconstrucción de anulaciones as-of histórica |
| Descuentos / impuestos | DocTotal fuente conserva el cálculo SAP; no sustituir por LineTotal, recalcular impuestos ni repartir descuentos |
| Signos | NC restada exactamente una vez; no reutilizar settlement como segunda resta |
| Cantidades | Conteos de documentos separados de unidades físicas; ranking fijo por SKU conserva límites nativos |

No se confunde facturación con pagos, reconciliación, deuda ni caja. Foundation no expone aquí VatSum/DiscSum: la fidelidad del total de cabecera es acreditada; una reconciliación fiscal separada no lo es. No se certifica cierre contable absoluto ni completitud empresarial.

Esta es una capacidad válida con restricciones explícitas, no un neto comercial por producto. Se rechazan filtros no acreditados de entidad, sucursal, canal y comparación; Calenta no puede convertir una consulta filtrada en un total global.
''')

rows = '\n'.join(f"| {p['date_from'][:7]} | {p['historical_metrics']['SALES_VALID_GROSS']} | {p['historical_metrics']['SALES_CREDIT_NOTES']} | {p['historical_metrics']['SALES_NET']} | {p['historical_metrics']['invoice_count']} / {p['historical_metrics']['credit_count']} |" for p in ref['periods'])
doc('MAY_2026_FOUNDATION_RECONCILIATION.md', 'May 2026 Foundation reconciliation', f'''
CURRENT efectivo fue confirmado sin modificarlo: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, commit snapshot 1408. La extracción independiente cotejó cada documento y no reutilizó la agregación del servicio.

| Mes | Facturación BS | NC BS | Neto documental BS | Facturas / NC activas |
| --- | --- | --- | --- | --- |
{rows}

[foundation_reconciliation.json](foundation_reconciliation.json) conserva SQL, parámetros, grupos por moneda/estado/source, documentos únicos, hashes de filas, latencias y diferencias cero. Mayo usa [2026-05-01, 2026-06-01); junio [2026-06-01, 2026-07-01).

Control 1: DocTotal, N, DocDate y NC siguen el contrato histórico. Control 2: grano único por fuente/documento y tipo; sin joins ni duplicación por líneas. Control 3: segundo SQL sin agregación recupera cabeceras, sumadas mediante Decimal en Python; comparado con SQL agregado y luego con el servicio/HTTP.

La factura anulada original Y y reversa C de mayo aparecen en dos grupos de dos documentos, 740,22 BS por grupo: quedan fuera del valor válido. Todos los demás grupos y NC están en el JSON; no se ocultan exclusiones ni se suman monedas diferentes.

Resultado PASS para reproducción del total documental seleccionado. CONDITIONAL respecto a cobertura empresarial completa y desglose fiscal, explícitamente fuera de esta certificación. No se extrapola la comparación a SAP actual ni se compara un MTD corporativo con el total compañía de otro snapshot.
''')

doc('CALENTA_NAMESPACE_RESOLUTION.md', 'Calenta namespace resolution', f'''
Calenta tiene productos y operaciones documentadas. No se trata como palabra sin contexto, cliente demostrado ni marca única; la consulta empresarial permanece bloqueada por un crosswalk no acreditado.

La autoridad detallada recuperada es [CALENTA_RESOLUTION previa](../foundation_query_activation_v1/CALENTA_RESOLUTION.md). Conserva IDs canónicos, nombres, SellItem, aliases y cantidades/LineTotal por SKU; se reutiliza porque CURRENT sigue siendo el mismo snapshot 1408.

- Reference SAP_HANA: L02822, L02823, L02877, L03035, L03648, L03649, L03650 y L03658, con sus canonical_product_id originales. L02877 y L03648 son KG con SellItem=N.
- Atomic sales_line: SAP_B1_HANA y item_code fuente. El join literal de namespace queda vacío; no prueba ausencia de ventas.
- Cuatro SKUs tienen líneas de mayo documentadas: L02822, L02823, L03649, L03658. Cantidades y LineTotal nativos no son neto por producto ni conversión física.
- Aliases AMBIGUOUS y MAPPED de presentaciones no acreditan una única familia Calenta/Forte; LIKE también encuentra calentadores ajenos.

SQL de evidencia: `calenta_exact_skus_may` en [sondas históricas selladas](../historical_business_query_inventory_v1/foundation_business_cases.json), y registry `sales_by_item`, HQ-fbdda4165b64b30810 / HS-56822a0ce444d328eb. Conserva ItemCode exacto y unión (source_system, DocEntry) cabecera/línea; no filtra negocio por texto libre ni usa un candidato como CURRENT.

Brecha precisa: falta acreditar y versionar la correspondencia (SAP_B1_HANA, item_code) → (SAP_HANA, item_code, canonical_product_id), su unicidad y provenance. Además debe decidirse presentación o conjunto comercial Calenta vs Forte, sin incluir automáticamente KG internos.

No se creó mapping ni alias ficticio, no se ejecutó sales.latest_by_entity y no se provisionó un permiso sin operación defendible. M04/M11 conservaron la mención y ejecutaron cero consultas. ENTITY_RESOLUTION=PARTIAL; CALENTA_BUSINESS_QUERY=BLOCKED. Próximo paso focalizado: acreditar el crosswalk de estos ocho SKUs y pedir selección concreta de presentaciones, sin otro discovery universal.
''')

doc('MONETARY_CAPABILITY_CONTRACT.md', 'Monetary capability contract', f'''
La capability amplía el servicio existente {link('datalake/sales_query.py', 'sales_query')}; no crea otro servicio comercial ni State Engine.

| Campo | Contrato |
| --- | --- |
| Operación | sales.period_billed_amount.v1 |
| Parámetros exactos | date_from, date_to_exclusive, currency=BS; ISO canónico; rango positivo de hasta 366 días |
| Intent existente | sales.net_amount; SALES_NET histórico; devuelve también facturación válida y NC separadas |
| Permiso específico | telchi.sales.period_billed_amount.read.v1; no sustituido por latest_documents |
| Resultado | billed_amount, credit_amount, net_amount, invoice_count, credit_count, conteos de unicidad y montos presentes; moneda, período, definición, grano, publicación/snapshot, restricciones |
| Binding | publicación esperada y snapshot 1408; cambio de binding rechaza, nunca usa un snapshot reciente |
| Ejecución | worker bounded, conexión read-only, dos threads y 512MB; SQL registrado con parámetros, no SQL de Luna |
| Rechazos | parámetros extra, moneda distinta, entidad no acreditada, duplicados, montos ausentes, resultado inconsistente, falta de permiso o committed distinto de True |

[capabilities](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/capabilities.py) conecta el intent previo sin cambiar su significado a facturación bruta. Ambas magnitudes se muestran: «Ventas» es neto documental; «Facturación válida» es el total de facturas antes de NC. No hay entity_id aprobado aún.

Modelo y effort conservados: GPT-5.6 Luna Medium. Se actualizó sólo su catálogo declarado, sin fallback. El engine determinístico V2 no se modificó; la guardia committed=True permanece obligatoria.

Para ambas métricas se preservan requested_metrics y prioridad; sólo se entrega la parte monetaria del período cuando el ranking fijo es incompatible, explicando que unidades físicas no están habilitadas. No se presenta el conteo de documentos como cantidades de productos.

Se añadió un binding estrecho para la pregunta exacta de ranking genérico, después de reproducir fechas/ASK inconsistentes: fija la ventana registrada, conserva raw/propuesta y pasa por el mismo engine. No corrige paths inválidos, períodos explícitos ni decisiones rejected. El scope de neto por producto se rechaza sin consultar un total global.
''')

doc('RBAC_ACTIVATION.md', 'RBAC activation', '''
La autorización no quedó pendiente: el permiso específico está registrado, delegado y efectivo para devfull@telchiai.com en telchi_dev. No se crearon usuarios ni se otorgó FULL_ACCESS.

Se extendió el CLI existente `modules.telchi.provisioning.live_cli --monetary-activation`, reutilizando las garantías de backup privado, DSN loopback team360, identidad de sistema PostgreSQL 18, source hashes y transacción SERIALIZABLE.

[activation_precheck_first.json](activation_precheck_first.json), [activation_plan.json](activation_plan.json), [activation_apply.json](activation_apply.json) y [activation_idempotent.json](activation_idempotent.json) documentan backup recuperable, catálogo, rol monetario acotado, delegación global y asignación administrativa. La segunda aplicación creó cero filas/asignaciones.

La delegación monetaria usa eventos propios y conserva intacta la anterior de latest/coverage. Los grants anteriores conservan un permiso monetario ya aprobado, sin concederlo como efecto de grant-sales. No se modificaron perfiles globales, esquemas ni entitlements de otros clientes.

[effective_authorization.json](effective_authorization.json) acredita cuatro permisos efectivos (source_quantity, latest_documents, coverage y period_billed_amount), verificación live del piloto, negativos para dos identidades existentes y cero permisos del piloto en otro workspace. El handler real ejecutó la operación con el permiso específico en seis turnos HTTP cotejados.

M08 HTTP es una fixture explícita de ausencia de permiso en el harness, no una retirada real del grant piloto. Se conserva esa distinción; los negativos de identidades existentes sí consultan PostgreSQL real. En todos los rechazos hubo cero ejecución Foundation.
''')

turns = []
for scenario in http['scenarios']:
    if scenario['id'] == 'M07':
        continue
    for turn in scenario['turns']:
        turns.append(f"| {scenario['id']} | {turn['user_text']} | {turn['classification']} | {turn['execution_status']} | {turn['elapsed_ms']} |")
for scenario in ranking['scenarios']:
    for turn in scenario['turns']:
        turns.append(f"| {scenario['id']} | {turn['user_text']} | {turn['classification']} | {turn['execution_status']} | {turn['elapsed_ms']} |")
doc('BUSINESS_HTTP_RESULTS.md', 'Business HTTP results', '''
HTTP 200 no decide el gate: se cotejaron committed, permiso, capability, parámetros, binding, conteos, montos y SQL independiente. El runtime usó loopback, autenticación y la identidad piloto resuelta por PostgreSQL.

| Caso | Pregunta | Clasificación | Ejecución | ms |
| --- | --- | --- | --- | --- |
'''+'\n'.join(turns)+'''

Respuestas exactas y auditorías: [corrida actual](business_http_current/runtime_http_results.json). El ranking genérico tiene una [revalidación focalizada posterior](ranking_http_current/runtime_http_results.json), después del binding de ventana registrada.

M01 obtuvo neto Bs 8.552.079,19 y facturación válida Bs 8.761.459,22. M02 obtuvo neto Bs 9.763.493,67 y facturación válida Bs 10.033.501,02. M06 conservó estado y volvió de junio a mayo; M05 conservó importes y cantidades sin sumar unidades ni ofrecer el ranking fijo como cantidades mensuales.

M08/M09 recorren el mismo endpoint/handler con fixtures explícitas de permiso denegado e interpretación inválida: [security_http_results.json](security_http_results.json). M09 conserva el estado anterior, committed=False y cero capability_calls. No se creó otra API.

M10 responde la limitación concreta del neto por producto; M04/M11 siguen bloqueados por identidad/crosswalk, no por ausencia de datos. M12 son seis comparaciones monetarias independientes con diferencia cero en [http_reference_comparison.json](http_reference_comparison.json).

La corrida actual B01 fue rechazada por un `/pending` prohibido propuesto por Luna: committed=False y cero ejecución. Hubo B01 positivos en [corrida previa](business_http_final/runtime_http_results.json); no se borra ni se presenta el rechazo como PASS. La capability y permisos anteriores siguen válidos, pero la confiabilidad lingüística de últimas facturas queda PARTIAL por esa intermitencia. No ocurrió en las consultas monetarias cotejadas.

No se cambió el modelo, se debilitó el engine ni se ejecutaron capacidades al rechazar. Todos los servidores propios fueron detenidos por el harness; no se envió WhatsApp, no hubo deploy ni acceso SAP.
''')

doc('FOUNDATION_REFERENCE_COMPARISON.md', 'Foundation reference comparison', '''
La referencia monetaria no reutiliza la función del servicio: agrupa fuente/moneda/cancelación por un SQL separado y coteja un segundo SELECT de cabeceras mediante sumas Decimal individuales.

- [foundation_reconciliation.json](foundation_reconciliation.json): SQL exacto, parámetros, filas agregadas, hashes de documentos y diferencias de cada grupo.
- [http_reference_comparison.json](http_reference_comparison.json): comparación de seis resultados del handler con esa referencia, período, documentos, NC y source binding.
- [luna_preflight.json](luna_preflight.json): llamada real OpenAI Responses, modelo/effort verificados y ausencia de fallback.

Se excluyen Y/C; NC activas se restan una vez; se mantiene BS. La consulta de servicio rechaza duplicados y montos faltantes, no sólo filas HTTP plausibles. No hay joins financieros que multipliquen cabeceras.

El cotejo acredita totales documentales y fidelidad semántica, no detalle fiscal no publicado, integridad de SAP actual, recepción histórica externa ni cierre empresarial completo. Los límites de Calenta y UoM se preservan. El guard no deja que una petición de neto por producto ejecute el total compañía.
''')

states = {
'TELCHI_HISTORICAL_BILLING_RECOVERY':'PARTIAL',
'TELCHI_BILLING_SEMANTICS':'PASS',
'TELCHI_MAY_2026_FOUNDATION_PARITY':'PASS',
'TELCHI_MONETARY_CAPABILITY':'PASS',
'TELCHI_MONETARY_RBAC':'PASS',
'TELCHI_MONETARY_BUSINESS_HTTP':'PASS',
'TELCHI_MONETARY_ACTIVATION':'PASS',
'TELCHI_CALENTA_NAMESPACE_RESOLUTION':'PARTIAL',
'TELCHI_CALENTA_BUSINESS_QUERY':'BLOCKED',
'TELCHI_MULTI_METRIC_RESPONSE':'PASS',
'TELCHI_SALES_EXISTING_CAPABILITIES':'PARTIAL',
'TELCHI_SALES_SECURITY_REGRESSION':'PASS',
'TELCHI_SALES_MONETARY_AND_ENTITY_RESOLUTION_V1':'PARTIAL',
}
(OUT/'gates.json').write_text(json.dumps(states, indent=2)+'\n')
doc('GATES.md', 'Gates', '''
El incremento monetario está ACTIVATED en DEV: DATA_PASS, SEMANTIC_PASS, AUTH_PASS y BUSINESS_RUNTIME_PASS para el contrato documental acotado. No se declara cierre total de Calenta ni reconciliación contable absoluta.

```text
'''+ '\n'.join(k+'='+v for k,v in states.items())+'''
```

La recuperación histórica es PARTIAL por SQL literal de algunas ejecuciones/monedas originales y recepción externa no acreditados; la definición oficial DocTotal/N/NC sí está recuperada y probada, no inventada. Por eso no bloquea un PASS monetario auténtico.

Semántica y datos: [billing](BILLING_SEMANTICS.md), [historia](HISTORICAL_BILLING_EVIDENCE.md), [reconciliación](MAY_2026_FOUNDATION_RECONCILIATION.md). Activación: [contrato](MONETARY_CAPABILITY_CONTRACT.md), [RBAC](RBAC_ACTIVATION.md), [HTTP](BUSINESS_HTTP_RESULTS.md), [referencia](FOUNDATION_REFERENCE_COMPARISON.md). Entidad: [Calenta](CALENTA_NAMESPACE_RESOLUTION.md).

MULTI_METRIC_RESPONSE=PASS significa intención conservada y respuesta parcial explícita cuando faltan cantidades mensuales; no significa cantidades físicas habilitadas. EXISTING_CAPABILITIES=PARTIAL refleja la intermitencia lingüística B01 con guard funcionando, no un fallo SQL ni RBAC. Los tests focalizados y el ranking/cobertura aceptados preservan sus contratos.

Validación: 179 tests focalizados PASS en [tests.log](tests.log), [validation_commands.log](validation_commands.log), fuentes actuales y estado Git preservados.

Comandos focalizados ejecutados desde backend: `uv run pytest modules/telchi/assistant/tests modules/telchi/provisioning/tests/test_sales_admin.py modules/telchi/provisioning/tests/test_monetary_admin.py -q`; runners `reconcile_foundation.py`, `verify_activation.py`, `security_http.py` y `modules.telchi.assistant.tests.runtime_http.run_battery --only M01,M02,M03,M04,M05,M06,M07,M10,M11,B01` con outputs de este reporte. Gates documentales desde raíz: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`. Sin commits/push/deploy ni cambios a SAP, Foundation, Messaging horizontal, Srv01, Flow o Diagnosis. State Engine sin cambios.

HOST_PREFLIGHT=SAFE; dos threads DuckDB propios, 512MB por conexión, suites focalizadas sin pools ilimitados. No procesos ajenos terminados. Los runtimes propios reportan pid_reaped; OWN_PROCESSES_LEFT_RUNNING=0 según handles del harness, ENVIRONMENTAL_ABORTS=0. El PASS de recursos no sustituye los controles de datos.

Próximo paso: recuperar el SQL literalmente ejecutado y pruebas externas de entrega si existen; acreditar el crosswalk de ocho SKUs Calenta; resolver presentaciones; reproducir la intermitencia de interpretación sin reparar `/pending` ni debilitar committed.
''')

paths = [
'modules/telchi/datalake/sales_query.py', 'modules/telchi/assistant/capabilities.py',
'modules/telchi/assistant/handler.py', 'modules/telchi/assistant/luna.py',
'modules/telchi/assistant/tests/test_assistant.py', 'modules/telchi/assistant/tests/test_real_conversation.py',
'modules/telchi/assistant/tests/test_sales_monetary.py', 'modules/telchi/assistant/tests/runtime_http/run_battery.py',
'modules/telchi/provisioning/monetary_repository.py', 'modules/telchi/provisioning/sales_repository.py',
'modules/telchi/provisioning/sales_cli.py', 'modules/telchi/provisioning/live_cli.py',
'modules/telchi/provisioning/tests/test_monetary_admin.py',
]
hashes = {p:hashlib.sha256((ROOT/'SrvRestAstroLS_v1/backend'/p).read_bytes()).hexdigest() for p in paths}
(OUT/'reviewed_source_hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
print('Nine reports generated; monetary PASS / overall PARTIAL with explicit gaps')

# Business HTTP results

Batería final: seis escenarios, ocho turnos, todos HTTP 200 y cero ERROR. No se interpreta el status HTTP como garantía empresarial: resultados, permisos, estado y SQL se verifican por separado.

## B01

Turnos reales del mismo pipeline con estado persistido PG.

**Pregunta:** Dame las últimas 10 facturas de venta registradas

**Respuesta:**

Últimas facturas activas por fecha documental (no instante de ingreso):
2026-09-24 · OINV DocEntry 11532517 · DocNum 260192728 · N
2026-09-24 · OINV DocEntry 11532516 · DocNum 260192727 · N
2026-09-24 · OINV DocEntry 11532515 · DocNum 260192726 · N
2026-09-24 · OINV DocEntry 11532514 · DocNum 260192725 · N
2026-09-24 · OINV DocEntry 11532513 · DocNum 260739131 · N
2026-09-24 · OINV DocEntry 11532512 · DocNum 260192724 · N
2026-09-24 · OINV DocEntry 11532511 · DocNum 260192723 · N
2026-09-24 · OINV DocEntry 11532510 · DocNum 260192722 · N
2026-09-24 · OINV DocEntry 11532509 · DocNum 260192721 · N
2026-09-24 · OINV DocEntry 11532508 · DocNum 260739130 · N
Orden: DocDate descendente, DocEntry descendente. Excluye anuladas y notas de crédito. No es venta neta.
Foundation foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408.

Estado: `DIRECT_AVAILABLE`; committed=True; ejecución=executed; latencia=5622.58 ms; capability=sales.latest_documents.v1; invocaciones=1; permiso=telchi.sales.latest_documents.read.v1; correlación=`02bf0a0b-1815-4fea-b83a-a68d2f77a7ed`.

## B02

Turnos reales del mismo pipeline con estado persistido PG.

**Pregunta:** ¿Cuál es la última fecha de ventas registrada?

**Respuesta:**

Último mes con facturas activas registradas por fecha documental: 2026-09. Última fecha: 2026-09-24T00:00:00. Documentos: 330429. No certifica último mes completo ni cobertura de ventas netas.
Foundation foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408.

Estado: `DIRECT_AVAILABLE`; committed=True; ejecución=executed; latencia=6722.42 ms; capability=sales.coverage.v1; invocaciones=1; permiso=telchi.sales.coverage.read.v1; correlación=`20a95c6d-a61b-44da-980b-318da0baa2e2`.

## B03

Turnos reales del mismo pipeline con estado persistido PG.

**Pregunta:** ¿Cuál es el último mes con ventas registradas?

**Respuesta:**

Último mes con facturas activas registradas por fecha documental: 2026-09. Última fecha: 2026-09-24T00:00:00. Documentos: 330429. No certifica último mes completo ni cobertura de ventas netas.
Foundation foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408.

Estado: `DIRECT_AVAILABLE`; committed=True; ejecución=executed; latencia=5099.19 ms; capability=sales.coverage.v1; invocaciones=1; permiso=telchi.sales.coverage.read.v1; correlación=`858a0abc-e92d-41ef-a298-14ba0952fc6a`.

## B04

Turnos reales del mismo pipeline con estado persistido PG.

**Pregunta:** Dame las últimas 10 facturas

**Respuesta:**

Últimas facturas activas por fecha documental (no instante de ingreso):
2026-09-24 · OINV DocEntry 11532517 · DocNum 260192728 · N
2026-09-24 · OINV DocEntry 11532516 · DocNum 260192727 · N
2026-09-24 · OINV DocEntry 11532515 · DocNum 260192726 · N
2026-09-24 · OINV DocEntry 11532514 · DocNum 260192725 · N
2026-09-24 · OINV DocEntry 11532513 · DocNum 260739131 · N
2026-09-24 · OINV DocEntry 11532512 · DocNum 260192724 · N
2026-09-24 · OINV DocEntry 11532511 · DocNum 260192723 · N
2026-09-24 · OINV DocEntry 11532510 · DocNum 260192722 · N
2026-09-24 · OINV DocEntry 11532509 · DocNum 260192721 · N
2026-09-24 · OINV DocEntry 11532508 · DocNum 260739130 · N
Orden: DocDate descendente, DocEntry descendente. Excluye anuladas y notas de crédito. No es venta neta.
Foundation foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408.

Estado: `DIRECT_AVAILABLE`; committed=True; ejecución=executed; latencia=5100.94 ms; capability=sales.latest_documents.v1; invocaciones=1; permiso=telchi.sales.latest_documents.read.v1; correlación=`a00ab52f-648b-4964-b17b-a2aac352109f`.

**Pregunta:** ¿Y las anteriores?

**Respuesta:**

Conservo la consulta de las últimas facturas activas. Esta operación no admite paginación: no puedo mostrar las diez anteriores ni presentar otra vez la primera lista como una segunda página. No se consultó Foundation.

Estado: `DIRECT_UNAVAILABLE`; committed=True; ejecución=not_executed; latencia=4340.16 ms; capability=ninguna; invocaciones=0; permiso=None; correlación=`d3ce5cc6-8ff5-4e44-aa12-fb717ec5f4eb`.

## B05

Turnos reales del mismo pipeline con estado persistido PG.

**Pregunta:** ¿Cuánto facturamos neto en mayo de 2026?

**Respuesta:**

Entendí que pedís importe de ventas en [2026-05-01, 2026-06-01). La consulta de importes de ventas todavía no tiene una capability aprobada. No puedo reemplazarla por cantidades. No es un problema con la fecha elegida.

Estado: `DIRECT_UNAVAILABLE`; committed=True; ejecución=not_executed; latencia=5120.75 ms; capability=ninguna; invocaciones=0; permiso=None; correlación=`a70fdc70-21f7-4437-95f2-4000db2e5915`.

## B06

Turnos reales del mismo pipeline con estado persistido PG.

**Pregunta:** ¿Cuáles son los productos más vendidos?

**Respuesta:**

Top 10 por cantidad documental, 01/01–15/09/2026:
L00505: 557199.0000000000
L02467: 200000.0000000000
M05970: 133931.0000000000
L01698: 116567.0000000000
L01003: 115269.0000000000
L01613: 108791.0000000000
L02837: 101919.0000000000
L00003: 98511.0000000000
M05239: 94065.0000000000
M05486: 93144.0000000000
Unidades originales por producto, no comparables entre productos. Sin descontar notas de crédito ni anulaciones; no es facturación ni venta neta. Cobertura histórica completa no certificada. Actualización: 2026-09-28T18:18:35.264000. Fuente: Foundation foundation_afd08d9eca6a725be53cdc3f9d5709c9.

Estado: `DIRECT_AVAILABLE`; committed=True; ejecución=executed; latencia=8272.92 ms; capability=telchi.sales_top_items.source_quantity.20260101_20260915.v1; invocaciones=1; permiso=telchi.sales.source_quantity.read.v1; correlación=`4ee38178-0b28-4a2e-93b4-fcfa1814582a`.

**Pregunta:** Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros

**Respuesta:**

Top 10 por cantidad documental, 01/01–15/09/2026:
L00505: 557199.0000000000
L02467: 200000.0000000000
M05970: 133931.0000000000
L01698: 116567.0000000000
L01003: 115269.0000000000
L01613: 108791.0000000000
L02837: 101919.0000000000
L00003: 98511.0000000000
M05239: 94065.0000000000
M05486: 93144.0000000000
Unidades originales por producto, no comparables entre productos. Sin descontar notas de crédito ni anulaciones; no es facturación ni venta neta. Cobertura histórica completa no certificada. Actualización: 2026-09-28T18:18:35.264000. Fuente: Foundation foundation_afd08d9eca6a725be53cdc3f9d5709c9.

Estado: `DIRECT_AVAILABLE`; committed=True; ejecución=executed; latencia=7654.58 ms; capability=telchi.sales_top_items.source_quantity.20260101_20260915.v1; invocaciones=1; permiso=telchi.sales.source_quantity.read.v1; correlación=`8a005651-0277-47b0-8243-c49b5d74a314`.

## Regresión y defectos observados

Se preservan todas las corridas, incluidos rechazos y correcciones; no se declara que el intérprete sea infalible.

- Primero: [legacy_http](legacy_http/runtime_http_results.json), doce escenarios/32 turnos, cero ERROR antes de correcciones.
- [business_http](business_http/runtime_http_results.json): B01 interpretación no disponible/propuesta null, cero ejecución; causa upstream/parse no acreditada. Repetición sin cambios funcionó; no se agregó retry automático ni fallback.
- B02 reprodujo dos veces la lista latest en vez de coverage. Se mantuvo raw en auditoría y añadió contrato documental acotado en handler, que propone coverage al mismo motor, exige su permiso y no amplía filtros ni catálogo. Regresión pytest y HTTP final acreditan corrección.
- B04 reprodujo dos veces ASK de referencia pese a contexto latest. Handler ahora explica paginación no soportada después de commit validado, sin ejecutar. Contexto y auditoría preservados.
- [legacy_http_final](legacy_http_final/runtime_http_results.json): un ERROR seguro, correlación `28694df9-66aa-45ac-b07b-79c48e7859b3`, en «ultimo mes registrado». Raw propuso `unset=['/pending']`, path fuera del contrato: State Engine rechazó correctamente, committed=False y cero consultas. No es fallo RBAC/SQL ni se clasifica como aborto ambiental.
- [legacy_http_recheck](legacy_http_recheck/runtime_http_results.json), mismo código: doce escenarios/32 turnos, cero ERROR; ranking original ejecutado. Variación de propuestas del intérprete sigue como riesgo residual; no se cambió Luna ni se repararon propuestas inválidas.
- [business_http_validated](business_http_validated/runtime_http_results.json): B01 latest, B02/B03 coverage, B04 sin segunda página, B05 sin importe, B06 ranking original.
- Todas las ejecuciones usan Srv05 real vía adapter DEV existente; WhatsApp outbound no ejecutado. Servidores loopback propios cerrados por el runner con `pid_reaped=True`.

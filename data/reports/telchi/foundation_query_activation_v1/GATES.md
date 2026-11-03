# Activation Gates

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
- modules/telchi/assistant/README.md (contrato local actualizado).
- modules/telchi/assistant/tests/test_sales_query_activation.py (nuevo).
- modules/telchi/assistant/tests/runtime_http/run_battery.py (escenarios opt-in, default previo intacto).
- Artefactos propios: data/reports/telchi/foundation_query_activation_v1/.

## Validación y recursos

Comandos, resultados y limitaciones de esta ejecución; no se declara PASS por un HTTP 200 ni por evidencia previa sin binding vigente.

- `uv run pytest modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py modules/telchi/datalake/tests/test_messaging_sales_query.py -q`: 126 PASS, una advertencia baseline de repositorio diagnosis in-memory en composición fixture.
- `verify_activation.py`: PG 18.4 read-only, grants efectivos, CURRENT 1408 y dos paridades SQL PASS.
- `live_probe --luna --preflight`: provider OpenAI directo/modelo GPT-5.6 Luna Medium autenticado, respuesta real sin fallback; Milvus/LiteLLM no consumidos por esta cadena.
- Runner HTTP existente: dos corridas focalizadas y dos legacy; resultado final consignado en BUSINESS_RUNTIME_RESULTS.md. Servidores propios reaped por el runner; sin outbound WhatsApp.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`: PASS; `git diff --check`: PASS. Evidencia en validation_commands.log. Advertencias LAT de init/key sin impacto en estos checks.
- Revisión final focalizada: permisos nuevos no existen ni se concedieron; consultas/columnas cerradas; no hay ejecución tras rechazo. Limitación observada: TQ07 final propuso período fuera de la ventana fija, bloqueado correctamente; no se declara ranking genérico RUNTIME_PASS.

HOST_PREFLIGHT=SAFE; RESOURCE_GUARD=PASS; CONCURRENCY_USED=2 threads DuckDB por conexión, un worker SQL o servidor propio a la vez, tests secuenciales sin xdist.
MemAvailable inicial ~7.5 GB, carga 1.28/2.65/3.08 en 8 cores, vmstat sin swap creciente sostenida; posterior ~7.3 GB y carga ~1.1. No se iniciaron browsers ni scans amplios.
UNRELATED_PROCESSES_TERMINATED=0; ENVIRONMENTAL_ABORTS=0; OWN_PROCESSES_LEFT_RUNNING=0. Cleanup: los runners confirman pid_reaped tras stop/wait; workers SQL síncronos cerraron conexiones y subprocess SQL tiene reap propio. No quedó servidor creado por esta ejecución.

## Siguiente decisión requerida

La limitación no se elimina cambiando SQL o dando por implícito un permiso. Se requiere autorización de alcance empresarial y provisioning separado, preservando el grant V1 existente.

Autorizar explícitamente `telchi.sales.latest_documents.read.v1` y `telchi.sales.coverage.read.v1` para una identidad/workspace DEV aprobados. Después repetir las dos preguntas por HTTP y cotejar sus filas; hasta entonces el objetivo comercial permanece incompleto.

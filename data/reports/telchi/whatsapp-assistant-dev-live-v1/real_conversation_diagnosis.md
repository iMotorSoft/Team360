# Telchi — diagnóstico conversacional real del 11/10/2026

Se reconstruyó el incidente desde PostgreSQL 18 y se corrigieron defectos conversacionales locales. No se desplegó ni reinició el canal. La repetición WhatsApp queda pendiente del operador.

## A. Reconstrucción verificable

La consulta read-only acotó Telchi DEV a 23:41–23:46 UTC (20:41–20:46 Buenos Aires). Recuperó 35 eventos, siete auditorías inbound y los estados durables, sin teléfonos ni secretos.

Rama: `feature/console-backend-core`. HEAD inicial: `09d2ec715a31bb88574d734eacb9f437f008624e`. Worktree previo extenso, preservado. Scope: TELCHI / VENTAS / DEVELOPMENT; sin cambios GLOBAL, Messaging, Foundation, SAP, modelo o producción.

Fuentes: [traza PG](diagnosis-trace.json), [extractor read-only](diagnosis_trace.py). Thread: `baea2cb9-a8fa-478d-84e0-808994beac11`. Canal: `489e6f2c-8bac-4805-99ba-7dbe4d48c10e`. Identidad piloto estable en las siete auditorías; permisos actuales: `telchi.sales.source_quantity.read.v1`. El conjunto histórico exacto de permisos no fue persistido: **NO OBSERVABLE**; no se lo sustituye por los permisos actuales.

Hubo una consulta documental **anterior** a los seis turnos, a las 20:42:10, evento `7bc705a9-9ac3-47fd-90f3-f053a9f580da`. Ejecutó la capability documental y dejó activa esa métrica/ventana. Su resultado auditado confirma binding efectivo `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, actualización `2026-09-28T18:18:35.264000`.

La tabla abrevia `Q` = sales.source_top_items, `W` = [2026-01-01,2026-09-16), `M` = [2026-05-01,2026-06-01). La traza enlazada conserva íntegramente anterior, propuesta, intent/action/delta/clarification, validado y confirmado.

| Turno / hora BA / correlation (evento inbound) | Mensaje recibido | Estado anterior → posterior | Propuesta y validación | Origen exacto de respuesta enviada |
| --- | --- | --- | --- | --- |
| 1 / 20:42:43 / b1b19579-1dea-4f7a-acda-bf08f415fe08 | dame las ultimas ventas de calenta | Q/W → Q/W + pending metric; propuesta conocida sin Calenta | NEW_QUERY / ASK; delta vacío; committed=true | Luna `clarification.question`, handler rama ASK: importe o cantidades |
| 2 / 20:43:00 / 9482bd5b-6129-4c89-a031-cde878ec5d5f | las dos | Q/W + pending metric → mismo activo, nueva pregunta metric | ANSWER_CLARIFICATION / ASK; delta vacío; committed=true | Luna `clarification.question`, handler ASK: cuál primero |
| 3 / 20:43:30 / cf7a3acd-7c4c-4ebc-bda4-2aad00498e5d | primero dame el importe de las ventas del mes | Q/W → mismo activo + pending period; **no importe guardado** | ANSWER_CLARIFICATION / ASK; delta vacío; committed=true | Luna `clarification.question`, handler ASK: mes/año |
| 4 / 20:43:49 / b73b82ee-6c87-4e8c-aa24-434644a9b18f | ultimo mes registrado | Q/W → mismo activo + nueva pregunta period | ANSWER_CLARIFICATION / ASK; delta vacío; committed=true | Luna `clarification.question`, handler ASK: no puede determinar último mes |
| 5 / 20:44:08 / 947b3d01-e494-44c1-9a90-1a580dd11dc4 | mayo 2026 | Q/W + pending → Q/M, pending=null | ANSWER_CLARIFICATION / EXECUTE; set /period=M; committed=true; registry bloquea | Plantilla `SalesCapabilities.availability`: COVERAGE_GAP, no ejecución |
| 6 / 20:44:43 / f231b236-72ea-45d8-8732-21f854895882 | todo mayo de 2026 | Q/M → Q/M | REFINE / EXECUTE; set /period=M; committed=true; registry bloquea | Misma plantilla de availability, no ejecución |

Las seis respuestas preparadas coinciden con `dispatch_result` y los textos outbound. Los seis outbound tienen evidencia `read`, además de callbacks de entrega. No se reconstruyó una supuesta salida del modelo a partir del texto WhatsApp: se usó `interpretation_proposed` persistido.

Request HTTP original a Luna, system prompt efectivamente cargado, IDs de respuesta del proveedor y copia exacta de contexto/history enviado: **NO OBSERVABLE**. Los logs backend inspeccionados no aportan ese cuerpo. El código muestra que se envían texto, estado, history, EMPTY y turn_id; esto describe el mecanismo, no prueba el payload histórico exacto.

## B. Causas raíz

Las causas comprobadas se separan del límite de observabilidad. No hubo rechazo determinístico en ninguno de los seis turnos ni ejecuciones empresariales durante ellos.

- **Modelo:** propuso ASK con deltas vacíos en turnos 1–4. No representó ambas métricas ni actualizó importe. La traza no permite afirmar que comprendió internamente ambas y el motor las descartó: el motor recibió un delta vacío.
- **Contrato:** sólo admitía una métrica; no tenía entidad mencionada, lista/prioridad ni referencia temporal de disponibilidad. Calenta sobrevivió en la primera pregunta pendiente, pero no como slot estructurado; luego esa pregunta fue reemplazada.
- **Motor:** aceptó esas propuestas; en ASK de seguimiento utilizaba el estado activo en vez de conservar los slots conocidos de la propuesta pendiente anterior. El defecto se reproduce con deltas conocidos, aunque los deltas del incidente fueron vacíos.
- **Registry:** comparación por **igualdad de ventana completa**, no por contención. Mayo fue reconocido correctamente, pero es un subperíodo no parametrizable. Clasificar toda desigualdad como COVERAGE_GAP fue un error de explicación, no una comparación temporal equivocada.
- **Selección:** el estado heredó Q de la consulta anterior porque importe nunca se guardó. No existe un selector que haya rechazado un importe correctamente representado en el turno 5: recibió Q/M.
- **Cobertura:** no hay operación autorizada de último mes por entidad/métrica. La ventana fija y la actualización Foundation no prueban disponibilidad mensual ni completitud. No se inventa septiembre ni se confunde sin datos con fuera de cobertura.
- **Persistencia:** PG conservó fielmente los estados propuestos, incluido Q/M entre turnos 5 y 6. El defecto fue de representación/transición, no evidencia de pérdida de PG o dependencia de memoria local.
- **Repetición:** el turno 6 tuvo interpretación nueva y commit=true, sin cambio material de estado; reutilizó el mismo rechazo estático del registry. No fue respuesta cacheada ni rechazo del motor.

## C. Cambios mínimos realizados

La extensión V2 es conversacional y compatible con los estados V1 existentes. No amplía el catálogo ni convierte una intención pendiente en autorización de ejecución.

Paths relativos a `SrvRestAstroLS_v1/backend/modules/telchi/assistant/`:

| Archivo | Justificación |
| --- | --- |
| state_engine.py | Campos V2 opcionales/versionados; métricas ordenadas coherentes con metric; entidad sin tipo inventado; referencia temporal sin período ficticio; seguimiento ASK conserva pending.proposed; NEW_QUERY V2 independiente; rechaza aclaraciones V2 ya respondidas |
| luna.py | Instrucciones semánticas de múltiples métricas/prioridad/entidad/mes; distingue comprensión de disponibilidad; no cambia provider, modelo ni medium |
| capabilities.py | Distingue métrica, mapping, metadata, período no resuelto, subperíodo no parametrizable y ventana excedida; no ejecuta filtros inexistentes |
| handler.py | DIRECT_UNAVAILABLE usa clasificación del catálogo y resume intención validada; no pide fecha para habilitar una capacidad ausente; mantiene ASK en pending sin tocar estado activo ni ejecutar |
| README.md | Contrato V2 y límites de recuperación/ejecución documentados |
| tests/fixtures/whatsapp_20261011.json | Seis textos exactos, respuestas negativas y siete variantes, sin identidad |
| tests/test_real_conversation.py, tests/test_v2_independent_query.py | 19 regresiones nuevas del contrato y del handler |
| tests/live_real_conversation.py | Smoke opt-in del caso real con Luna y variantes; auth/persistencia/query doubles explícitos |

La evidencia nueva está en este directorio: diagnosis_trace.py / diagnosis-trace.json, diagnosis_foundation_probe.py / diagnosis-foundation-probe.json, diagnosis_handler_replay.py / diagnosis-handler-replay-final.json, diagnosis-luna-smoke*.json, diagnosis-tests.txt y este informe. No se modificaron ni borraron reportes previos. Los archivos del asistente ya eran untracked; `git diff` no los representa como cambios de archivos tracked.

Blast radius: contrato, intérprete, availability y presentación del handler deben cambiar juntos para evitar representar ambas métricas y luego ejecutar sólo una silenciosamente. Tests/fixture/doc no son nuevos motores. Repository, SQL y composición permanecen intactos.

## D. Regresiones y validación

Las garantías locales y las sondas reales se reportan por separado. Ninguna sonda representa recepción o entrega WhatsApp de la versión corregida.

- `uv run pytest modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py tests/test_messaging_handlers.py tests/test_messaging_horizontal_runtime.py -q`: **145 passed**, una advertencia preexistente de Diagnosis in-memory; [salida](diagnosis-tests.txt).
- 19 tests nuevos: diálogo completo, prioridad, pending conocido, aclaraciones ya respondidas, fecha innecesaria ante importe ausente, V2 inválido, mayo dentro de ventana pero no parametrizable, metadata ausente, entidad sin mapping, consulta exacta válida, roundtrip repository y consulta nueva sin heredar período/filtros.
- Safety existente: `committed` debe ser literalmente True; cero ejecución ante rechazo, protección del estado anterior, permisos antes del LLM y revalidación, isolation/caching y crash fence de Messaging.
- Persistencia V2: save/reload con instancia nueva del repository y puerto PG controlado; reinicio del handler contra store externo. PG histórico real read-only confirma continuidad. **No hubo escritura de prueba en PG operacional ni restart de servicios.**
- Cuatro smokes focalizados de este incidente, no benchmarks generales: preflight real OpenAI y seis turnos más siete variantes por corrida. Los intentos r1–r3 quedan preservados, incluidos fallos. La última [sonda Luna](diagnosis-luna-smoke.json) valida los seis turnos y siete variantes con `gpt-5.6-luna`, medium, provider directo verificado y cero llamadas de capability.
- La evaluación inicial de una variante miraba el estado activo de ASK, no pending.proposed; el recheck registrado corrige únicamente esa evaluación, sin alterar propuestas ni respuestas ni llamar de nuevo al proveedor.
- Un [replay final del handler](diagnosis-handler-replay-final.json) usa las propuestas reales registradas tras el último ajuste de presentación: mismo estado confirmado, seis commits válidos, cero consultas; es replay, **no una nueva llamada Luna ni WhatsApp**.
- [Prueba Foundation real](diagnosis-foundation-probe.json): ejecución V2 exacta, committed=true, 10 filas, read_only=true, sap_accessed=false. Abortaría antes de SQL empresarial ante drift de publicación/snapshot; confirmó el mismo binding 1408. No mostró importes ni filas al modelo.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: **PASS**, exit 0 en los seis comandos; resultados en diagnosis-gate-*.txt. El alcance final se revisó sin staging/commit. Branch/HEAD finales coinciden con el inicio.

No existe metadata válida para resolver último mes comercial ni mapping Calenta: esos caminos conservan la intención y explican el gap. No se asegura calidad semántica universal por una sola conversación.

## E. Catálogo real y ejecutabilidad

Existe una sola capability aprobada para esta ruta. La cobertura documental fija no equivale a consultas por mes, entidad ni importes.

`telchi.sales_top_items.source_quantity.20260101_20260915.v1`: invoices/sales_document unidos a sales_line por doc_entry; suma quantity por item_code. Sin cancelación ni resta de créditos. Ventana [2026-01-01,2026-09-16), grano producto, ORDER BY quantity DESC,item_code, LIMIT 10. Sin parámetros empresariales libres; sólo timeout técnico. Fuente FoundationReader CURRENT pinned; permiso operacional seleccionado `telchi.sales.source_quantity.read.v1`, con revalidación Console y scope workspace completo.

`line_total` aparece en SQL/resultado interno existente, pero no autoriza importe neto ni se presenta como respuesta monetaria. No hay filtros por Calenta, cliente, marca, sucursal, canal o mes en esta capability; no hay operación de metadata de disponibilidad mensual.

| Necesidad | Comprensible | Capability existente | Ejecutable hoy |
| --- | --- | --- | --- |
| Cantidades generales | Sí | Top 10 documental, ventana completa, sin filtros | Sí, sólo contrato exacto y permiso efectivo |
| Cantidades Calenta | Sí, entidad mencionada sin tipo inventado | No mapping/filtro aprobado | No |
| Importe Calenta | Sí | No capability monetaria por entidad | No |
| Mayo completo | Sí, [2026-05-01,2026-06-01) | No parametrización mensual | No, aunque está dentro de la ventana |
| Último mes disponible | Sí, referencia de disponibilidad | Sin metadata autorizada por entidad/métrica | No, no se sustituye por mes del reloj o ventana fija |

Mensajes finales distinguen METRIC_MISSING, MAPPING_MISSING, TEMPORAL_METADATA_MISSING, PERIOD_UNRESOLVED, PERIOD_PARAMETER_UNSUPPORTED y COVERAGE_GAP de la ventana fija. No clasifican ninguna de estas limitaciones como ventas cero o período sin filas.

## F. Repetición WhatsApp pendiente

La conversación fallida tiene evidencia de entrega real. La corrección sólo se validó localmente y con Luna/Foundation reales fuera del transporte; no se envió ningún mensaje ni se reinició el canal.

Acciones del operador: abrir una ventana DEV de runtime mediante los mecanismos existentes para cargar el código actualizado, sin deploy productivo ni borrar histórico. Enviar una petición nueva explícita para no depender de la representación incompleta del incidente anterior; NEW_QUERY V2 separa la consulta preservando history.

Secuencia desde el teléfono piloto vinculado:

1. `Nueva consulta: dame las ultimas ventas de calenta`
2. `las dos`
3. `primero dame el importe de las ventas del mes`
4. `ultimo mes registrado`
5. `mayo 2026`
6. `todo mayo de 2026`
7. Consulta positiva independiente: `Nueva consulta: top 10 productos por cantidad documental del 1 de enero al 15 de septiembre de 2026, sin filtros`.

Esperado: una aclaración inicial de métrica compatible; después ambas conservadas, importe primero, Calenta sin tipo inventado, último mes sin fecha inventada, mayo completo reconocido y limitación monetaria concreta. Cero ejecución monetaria. La consulta positiva debe devolver cantidad documental con fuente/limitaciones. Capturar nuevos correlation/thread IDs, auditorías y outbound delivered/read; no declarar PASS sólo por respuestas locales.

No se puede recuperar automáticamente Calenta ni ambas métricas del estado histórico que nunca las guardó: iniciar petición independiente evita fabricar retroactivamente ese contexto.

## G. Gaps para siguiente incremento

Los gaps comerciales quedan en backlog; no se implementaron capabilities ni se promovió Foundation durante este diagnóstico.

1. **Alta:** importes por entidad/período con semántica contable, créditos/cancelaciones, currency/UoM, autorización y reconciliación Foundation.
2. **Alta:** resolución comercial de Calenta contra dimensiones/crosswalks validados; ambigüedad explícita y sin asumir cliente/marca/fabricante.
3. **Alta:** metadata temporal por fuente, entidad y métrica para resolver último mes y distinguir sin datos de fuera de cobertura.
4. **Media:** cantidades mensuales parametrizadas; contrato y permisos antes de abrir agregaciones.
5. **Media:** ejecución/presentación conjunta de métricas compatibles cuando existan ambas capacidades; hoy sólo se conserva la solicitud.
6. **Operacional:** traza versionada del contexto enviado a Luna y permisos efectivos históricos, con minimización de datos; resumption de conversaciones V1 incompletas mediante solicitud explícita, no migración inferida.

## H. Estados finales y riesgos

PASS indica garantías ejecutadas en el alcance indicado, no promoción ni éxito del transporte corregido. La reconstrucción y resolución temporal siguen parciales por gaps observables explícitos.

```text
TELCHI_REAL_TRACE_RECONSTRUCTION=PARTIAL
TELCHI_MULTI_METRIC_INTENT=PASS
TELCHI_CONTEXT_PRESERVATION=PASS
TELCHI_TEMPORAL_RESOLUTION=PARTIAL
TELCHI_CAPABILITY_ERROR_CLASSIFICATION=PASS
TELCHI_CLARIFICATION_LOOP_PREVENTION=PASS
TELCHI_STATE_ENGINE_SAFETY=PASS
TELCHI_REAL_CONVERSATION_REGRESSION=PASS
TELCHI_WHATSAPP_REAL_RETEST=BLOCKED
```

Context preservation PASS se refiere al contrato V2 y continuidad probada; **el incidente sí perdió representación estructurada de Calenta/importe**, no se declara recuperado. Temporal PARTIAL: mes explícito correcto y referencia conservada, pero no resolver empresarial disponible. Clarification PASS está limitado a opciones compatibles, slots V2 ya respondidos y fechas incapaces de habilitar una consulta ausente.

Host: BUSY_BUT_SAFE, 8 cores, ~5.5 GB disponibles; swap histórica ~4.7 GB sin crecimiento observado, muestras vmstat sin swapping activo. Ejecución secuencial, una conexión PG de lectura, una petición LLM por vez; Foundation dos threads y 512 MB en conexión propia. Sin browsers, servidores propios ni procesos ajenos terminados. Subprocesos uv/pytest/probes finalizaron; sin workers propios persistentes.

Impacto transversal: contrato consumido sólo por handler Telchi; se conservan las interfaces Messaging y la composición Srv05. Riesgos: variabilidad de Luna, conversaciones antiguas incompletas y ausencia de capacidades comerciales. Próximo paso: operador carga versión DEV y repite secuencia real; sólo después avanzar backlog comercial mediante gates separados.

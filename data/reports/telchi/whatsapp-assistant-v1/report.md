# Telchi WhatsApp Business Assistant V1 — desarrollo local

Implementación funcional opt-in, no promoción ni entrega WhatsApp real. Evidencia fechada del 11/10/2026. El código y sus límites están en el [contrato local](../../../../SrvRestAstroLS_v1/backend/modules/telchi/assistant/README.md).

## A. Estado inicial y scope

La base Git y las fronteras horizontales permanecieron intactas. Se agregaron archivos Telchi y un test de composición inequívocamente Telchi; no se adoptó trabajo ajeno.

- Rama: `feature/console-backend-core`.
- HEAD inicial y tras el reset mencionado por el usuario: `09d2ec715a31bb88574d734eacb9f437f008624e`.
- Worktree: numerosos cambios tracked/untracked preexistentes de Flow, Diagnosis, Messaging, Srv05, Telchi, Console, frontend y documentación. Se preservaron; ningún archivo preexistente fue editado por esta implementación.
- Baseline horizontal recibido: 356 PASS / 5 skips y 1 PASS PG18 aislado; [reporte anterior](../../messaging/horizontal-v1-srv05-identity/report.json). No se convirtió ese PASS en readiness actual.
- Contexto: TELCHI / VENTAS / DEVELOPMENT / DATA_LAKE / CONVERSATIONAL_CONTEXT. Foundation exclusiva, SAP_ACCESS=0, DDL=0, deploy=0, commits/push=0.
- CURRENT verificado realmente: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`, actualización `2026-09-28T18:18:35.264000`. No se asumió desde el status; lo resolvió el reader coherente existente.

## B. LlmFit y adaptación

Se estudiaron contratos y resultados existentes, sin benchmark comparativo nuevo ni copia del módulo experimental como dependencia runtime.

Root leído: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/LlmFit/benchmarks/telchi/conversation_state_v1/`.

Artefactos revisados: `experimental/state_engine.py`, `harness/contract.py`, `prompts/system.txt`, `tests/test_experimental_state_engine.py`, fixture TCS_019, `live_state_engine_validation.py`, reporte `runs/20261007T124246Z/live_state_engine_validation/REPORT.md` (LUNA_LIVE_ENGINE), `adapters/direct.py`, y `fallback_ground_truth_v1/downstream_contract_evidence_v1/REPORT.md` (LLMFIT_TELCHI_DOWNSTREAM_CONTRACT_EVIDENCE_V1).

También se leyó la investigación Team360 `response_verifier_false_simple_analysis/FALSE_SIMPLE_ANALYSIS.md`. Se preservan sus límites: validación estructural no certifica interpretación semántica, no se agrega segundo LLM ni rules verifier ajustado a gold.

Adaptaciones acotadas: delta atómico, herencia sin resets implícitos, listas finales para extend, defaults explícitos para remove, comparación conservando objetivo, referencias a solicitudes visibles, pending enlazado con hash y turno, rechazo atómico y guard downstream literal `committed is True`.

La primera sonda real obtuvo `set.metric` sin slash: [live-probe.json](live-probe.json). El motor lo rechazó, ejecutó cero capabilities y retuvo estado; esa evidencia no se borró. Se incorporó la normalización general `atomic_paths` ya estudiada en LlmFit, rechazando colisiones. No se agregaron reglas por frase, producto o benchmark ID.

LlmFit sólo aportaba adapters experimentales externos al módulo. Se adaptó el transporte directo a HTTPX async ya disponible, sin importar LlmFit, archivos temporales, fixtures ni investigación en runtime. El JSON se valida localmente; duplicate keys/NaN/Infinity se rechazan.

## C. Handler y ciclo funcional

Existe un MessageHandler Telchi real y una composición local que lo registra por el puerto existente de Srv05. No se cambió el motor Messaging ni su entrypoint global.

Archivos nuevos bajo `SrvRestAstroLS_v1/backend/modules/telchi/assistant/`:

- `handler.py`: MessageHandler, política y autorización, store transaccional, guard, decisiones, auditoría y timings.
- `state_engine.py`: contrato tipado de solicitudes y reducer sales-only.
- `luna.py`: GPT-5.6 Luna Medium directo, timeout y verificación de modelo/esfuerzo devueltos.
- `capabilities.py`: catálogo cerrado, capability fija Foundation, validación del resultado y formatter determinístico.
- `repository.py`: namespace JSON en filas existentes, aislamiento y locks.
- `composition.py`: `create_telchi_app(policy, pool opcional) → Srv05.create_app(messaging_handlers=...)`. El default resuelve el pool existente después del startup, sin nuevo lifecycle.
- `__init__.py`, `README.md`, y tests propios `test_assistant.py`, `test_repository.py`, `test_safety.py`, `live_probe.py`, `tests/__init__.py`.
- Test nuevo fuera del módulo, dentro de su scope inequívoco: `backend/tests/test_telchi_assistant_srv05.py`.

Interfaces usadas: `InboundMessage`, `MessageContext`, `MessageResult`, `HandlerRegistration`, `MessageDispatcher`, `MessagingService`, pool/transaction Team360, `PermissionConsoleRepository`, `FoundationReader` y `query_fixed_sales` existentes. Dependencias nuevas instaladas: cero.

Turno: acceso preliminar → thread/event lock → permiso efectivo → cache o interpretación → state engine → guard → disponibilidad y params → recheck de acceso → lectura Foundation → formatter → persistencia de estado/resultado/respuesta → commit → retorno a Messaging → intent outbound y envío horizontal.

ASK no ejecuta. Commit rechazado produce ERROR seguro, no entrega la pregunta raw ni ejecuta el estado anterior. DIRECT_UNAVAILABLE retiene parámetros validados como solicitud, no como resultado. ANALYSIS_UNAVAILABLE informa funcionalidad futura, sin jobs ficticios. DENIED no revela datos; ERROR no inventa cifras.

## D. Capabilities y semántica comercial

Hay una lectura empresarial verificable muy acotada. No se sustituyó facturación por cantidades ni se extrapolaron contratos monetarios existentes a otro alcance.

Disponible: `sales.source_top_items`, delegando a `telchi.sales_top_items.source_quantity.20260101_20260915.v1`, período fijo 01/01–15/09/2026. Consulta parametrizada y aprobada existente; top 10 cantidades documentales por producto, sin sucursal, canal o comparación.

Resultado: período, params normalizados, capability, filas sin `line_total`, publicación, snapshot, actualización, cobertura, unidades y limitaciones. La respuesta determinística informa que no descuenta notas de crédito/anulaciones, no es venta neta/facturación, no compara unidades entre productos y no certifica completitud histórica. No agrega cantidades entre productos ni hace conversiones.

Revisión monetaria: `executive_sales.py` ya define DocTotal local BS/BOB, facturas menos notas de crédito no canceladas, fecha DocDate, atribución al vendedor de cabecera y categoría corporativa confirmada. Sus tests pasaron. Esto no acredita el total general solicitado, facturación neta por producto, descuentos/impuestos por producto, sucursal física ni cobertura mensual completa. No se creó una definición comercial nueva ni se borró ese camino existente.

La semántica comercial candidata conserva `NET_PRODUCT_AMOUNT_UNRESOLVED`; sus componentes no se asumen publicados. Los series mappings horizontales existentes tampoco se convierten automáticamente en un filtro aprobado de esta query fija.

Bloqueos: `sales.net_amount` general, mapping Saavedra, filtros de canal y comparación/otros períodos para la query fija. Son bloqueos del pedido concreto: eliminarlos habilita la consulta fija. Cobranza, stock, compras y producción no se implementaron.

Falta para habilitar importe general: sign-off de métrica y bases bruta/neta/impuestos, tratamiento de créditos/devoluciones/cancelaciones, moneda, alcance/sucursal/vendedor/canal, cobertura 2026 completa o parcial explícita y capability aprobada sobre la publicación vigente.

## E. Estado, atomicidad e idempotencia

La persistencia extiende JSON existente, no otra base o esquema. Las garantías de atomicidad del handler no se confunden con las del intent outbound horizontal.

Conversación: thread ID recibido de Messaging. Turno: correlation ID del evento inbound. Owner guardado: entorno, tenant, workspace, canal y usuario. Cambiar el usuario de un thread existente falla cerrado, sin compartir su contexto. Historia de hasta 20 solicitudes, con orden explícito independiente del orden JSONB.

`message_threads.metadata_jsonb.telchi_assistant_v1`: owner, estado confirmado e historia. `message_events.payload_jsonb.telchi_assistant_v1`: anterior, propuesta, validado, confirmado, decisión, committed, execution_status, resultado, respuesta preparada, BMD y timings.

Confirmación: tras validar, una solicitud unavailable puede persistir para continuidad con `not_executed`; ASK sólo guarda pending. Fallo de capability mantiene estado anterior. Estado, resultado y respuesta preparada se guardan en una transacción; sólo se devuelve éxito tras commit.

Locks: thread antes de inbound event, concordando con Messaging. Turnos se serializan entre procesos sobre ese thread. Cache de turno completado retorna respuesta sin LLM/query, con permisos revalidados. Duplicados y retries normales siguen el fence/recuperación horizontal: no reinvocan handler.

Brecha reconocida: commit Telchi y commit del intent outbound Messaging son transacciones distintas. Crash en esa brecha conserva resultado Telchi pero el duplicado puede quedar `execution_uncertain`; no se añadió recuperación horizontal ni se afirma entrega eventual/exactly-once. Crash antes del commit puede dejar una lectura realizada sin estado persistido; el fence Messaging impide replay automático. Fuera de ese circuito no se garantiza exactly-once tras rollback.

La persistencia real PG del handler NO se escribió/probó operacionalmente: faltan binding y fixture autorizada. SQL y límites, load/save, aislamiento, orden JSONB y lifecycle commit se probaron contra puertos controlados. Operación se mantiene PARTIAL.

## F. Seguridad y restricciones

El módulo consume identidad verificada por Messaging y reusa Console. No genera permisos especiales WhatsApp ni considera un texto o número como prueba de acceso.

Número desconocido, permiso faltante, tenant/workspace/entorno incorrecto, módulo deshabilitado y scope no acreditado: cero LLM/capability calls. Fallo del resolver: ERROR horizontal sin downgrade anónimo. Telchi no declara capacidades públicas.

`BusinessPolicy` no tiene permiso por defecto. Los permisos semilla `dashboard.view`, `task.view`, etc. NO se adoptaron como permiso comercial. El owner debe seleccionar un grant comercial existente y demostrar que expresa acceso al workspace completo antes de atestar scope. Esa selección está pendiente; las pruebas usan `fixture.business.read`, sólo una fixture, no un permiso creado o aplicado.

No se implementa un nuevo resolver de scope. Si la autorización real está limitada por sucursal/cliente/datos y el servicio vigente no puede acreditarla para la lectura global, el flag queda falso y se bloquea. Una atestación de composición no es un grant RBAC. Esta limitación impide declarar autorización empresarial operacional PASS.

No se aplicó 027, ninguna migración, DDL, deploy ni PROD. Sin SAP/HANA, SQL del LLM, routing IA de módulos, Redis, broker, frontend, framework paralelo ni cambios a Srv01, Flow, Diagnosis o Messaging.

## G. Validaciones y evidencia

Las pruebas distinguen garantías locales, servicios reales y fronteras simuladas. La versión final pasó regresión y replay de las interpretaciones reales, sin repetir benchmarking comparativo.

Comando final desde backend:

```bash
env -u TEAM360_MESSAGING_ISOLATED_TEST_DSN -u TEAM360_MESSAGING_POSTGRES_TEST -u TEAM360_MESSAGING_TELCHI_SQL_TEST OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run pytest modules/telchi/assistant/tests modules/telchi/datalake/tests tests/test_telchi_assistant_srv05.py tests/test_messaging* tests/test_srv05* tests/test_console* -q --tb=short
```

[regression-pool-final.txt](regression-pool-final.txt): **900 PASS / 5 skips**, 45.34 s. Incluye resolución lazy del pool existente después del startup; la corrida previa de 900 PASS está preservada en [regression-final.txt](regression-final.txt). Skips: tests PG explícitamente opt-in; no DDL/DB writes operacionales. Warning conocido: repositorio Diagnosis in-memory de fixture. No tests existentes modificados para esconder fallos. Corrida previa preservada: 881 PASS / 5 skips en [regression.txt](regression.txt).

Tests propios y composición: 72 casos incluidos en la corrida final. Cubren conversación, ASK/pending/answer/resume, prefix normalization/conflictos, rechazo raw EXECUTE con plan previo válido, committed no literal, override/extend/remove, comparación/referencia/stale pending, denegaciones y revocación de permiso, fuente ausente/inválida, errores seguros, duplicate/concurrent retry, timeout/commit failure y crash antes del outbound.

Integración local: mapper Evolution real → MessagingService real → dispatcher real → identidad simulada → autorización de módulo real → handler/state engine/catalog/formatter reales → repositorios PG simulados → intent outbound y sender simulado. No es WhatsApp real ni PG operacional.

Registro Srv05: factory Telchi ejecutada contra `create_app` real, con baseline lifecycle/pool/provider inertes. Registro privado DEV y startup builder horizontal acreditados sin modificar Srv05.

Sondas reales desde backend, con outputs nuevos y sin secretos:

```bash
uv run python -m modules.telchi.assistant.tests.live_probe --luna --foundation --output ../../data/reports/telchi/whatsapp-assistant-v1/luna-foundation-handler.json
uv run python -m modules.telchi.assistant.tests.live_probe --luna --preflight --output ../../data/reports/telchi/whatsapp-assistant-v1/luna-reasoning-preflight-final.json
```

Los nombres anteriores ya existen: para reproducir elegir paths nuevos; el runner rechaza sobrescribir evidencia. [luna-foundation-handler.json](luna-foundation-handler.json): siete turnos con Luna real; ASK por año, respuesta 2026, Saavedra, comparación agosto, horizontal, remove, y nueva solicitud explícita de cantidades. Última lectura por handler real/capability real/Foundation real; PG/auth/transport simulados, sin enviar filas empresariales al modelo.

[luna-reasoning-preflight-final.json](luna-reasoning-preflight-final.json): adapter final acredita modelo devuelto `gpt-5.6-luna` y echo `medium`; ASK válido, cero capability calls. Sin LiteLLM ni fallback. [final-replay.json](final-replay.json): siete interpretaciones previas reproducen estado/clasificación/decisión en código final, cero network calls y una capability controlada.

Foundation real: 10 filas, publicación/snapshot/actualización indicados en A; hash reducido `cba2bd24f0fa00573343eebf3f31d3376a85a63f0a89da05fb82573adf8ea706`. Reader coherente/pinned y attachment read-only verificados por query existente. No se publican filas sensibles completas.

Latencia observada en la integración real focalizada: interpretación 2.17–5.84 s; última capability 4.70 s y último procesamiento interno 7.59 s. Sonda Foundation independiente inicial: 19.73 s, sin restarla de otras muestras. Engine/formatter medidos en JSON; no estimaciones del LLM. `total_processing_ms` excluye locks, commit PG y transporte; no es E2E WhatsApp ni SLA. Límites: Luna 45 s, query 30 s, turno 80 s configurables; PG lock 3 s/statement 5 s locales.

Host preflight: BUSY_BUT_SAFE; 8 cores, MemAvailable aproximadamente 4.2–5.7 GB. La swap usada creció durante la ventana compartida (2.0 a 3.7 GB); las muestras breves registradas no mostraron swap-in/out sostenida. Se mantuvieron workloads focalizados/secuenciales, sin asumir host libre. Carga/concurrencia ajena preservadas; una suite secuencial, OMP/BLAS 2, worker DuckDB 2 threads/512 MB, un request por conversación. RESOURCE_GUARD=PASS en alcance observado, ENVIRONMENTAL_ABORTS=0, UNRELATED_PROCESSES_TERMINATED=0. Worker propio comunicado/reaped por lifecycle; sin servidores/browsers propios persistentes.

Gates documentales y whitespace se registran en `documentation-gates.txt` y `report.json`; ningún PASS documental se infiere antes de sus resultados. El diff final de archivos nuevos y su scope se revisó; no se cambió el estado GLOBAL ni documentos ajenos.

## H. Producto futuro

Las direcciones de producto permanecen separadas de funcionalidades que todavía no tienen infraestructura o semántica aprobada.

```text
ACG=BASIC
APD=FUTURE
BMD=MINIMAL
```

ACG cubre aclaración de métrica/período y pending. Análisis extensos, diagnósticos/recomendaciones/pronósticos y entrega email no se ejecutan. BMD registra categoría en auditoría existente, sin tickets, trabajos o PII adicional. Comparar ventas es una solicitud directa; V1 conserva baseline pero no inventa una capability de comparación.

## I. Estado final y próximo paso

Los PASS siguientes son garantías de alcance explícito, no certificación productiva. El asistente local avanza a PARTIAL y no depende ya sólo de infraestructura horizontal.

| Estado | Resultado | Evidencia y límite |
| --- | --- | --- |
| TELCHI_CONVERSATION_HANDLER | PARTIAL | Handler registrado por factory real, ciclo funcional y lectura Foundation real; sin identidad/PG/canal operacionales |
| TELCHI_LUNA_INTEGRATION | PASS | Directo, siete turnos controlados reales y preflight final con modelo/medium devueltos; no certifica comprensión universal |
| TELCHI_STATE_ENGINE | PASS | Contrato sales-only, 72 tests propios/composición y replay final; no motor general multidominio ni garantía semántica perfecta |
| TELCHI_EXECUTION_GUARD | PASS | committed no literal y raw EXECUTE rechazado dan cero ejecuciones, también con plan previo válido |
| TELCHI_SALES_CAPABILITY | PARTIAL | Query fija documental con resultado real verificable; facturación general y dimensiones objetivo bloqueadas |
| TELCHI_FOUNDATION_READ_ONLY | PASS | CURRENT coherente, snapshot pinned y attachment read-only reales; SAP_ACCESS=0 |
| TELCHI_BUSINESS_AUTHORIZATION | PARTIAL | Resolver Console reusado y fail-closed probados; permiso comercial y scope reales pendientes |
| TELCHI_CONVERSATION_PERSISTENCE | PARTIAL | Repository PG/namespace/atomicidad implementados y tests controlados; sin escritura PG autorizada ni recuperación nueva de brecha outbound |
| TELCHI_MESSAGING_INTEGRATION | PARTIAL | Circuito real de código, dispatch privado/intent/dedup/recovery probados con PG/provider dobles; no delivery WhatsApp |
| TEAM360_TELCHI_WHATSAPP_ASSISTANT_V1 | PARTIAL | Asistente funcional local con Luna y Foundation reales; bloqueos operacionales/comerciales expresos |

Próximo paso: ventana operacional independiente para fixture de usuario/tenant/workspace, permiso comercial y scope acreditados, aplicación autorizada de 027, binding telefónico y canal DEV. Revalidar persistencia y envío con esos servicios, sin ampliar permisos ni confundir cantidades con facturación. PROD, migraciones y WhatsApp real NO quedaron habilitados aquí.

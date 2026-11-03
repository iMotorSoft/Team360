# Telchi assistant — Runtime HTTP validation V1

Validación del asistente Telchi **ejecutándose como servicio real DEV**, con Luna
real, State Engine V2, permisos y persistencia PostgreSQL reales y Foundation real
read-only, mediante una batería `curl` reproducible. No se envió ningún mensaje
WhatsApp y no se desplegó ni reinició ningún servicio productivo.

- Rama: `feature/console-backend-core`
- HEAD al inicio y al cierre: `09d2ec715a31bb88574d734eacb9f437f008624e`
- Alcance: `ENTITY=TELCHI` / `DOMAIN=VENTAS` / `STAGE=DEVELOPMENT`
- Evidencia: `data/reports/telchi/whatsapp-assistant-dev-live-v1/runtime_http/`
  (`runtime_http_results.json`, `security/security_results.json`,
  `restart/restart_results.json`, `tests.txt`, `git-diff-check.txt`,
  `full-before-fixes/`, `focused-r2/`).

## 1. Arquitectura inspeccionada

Recorrido real de una solicitud Telchi y dueño de cada operación:

| # | Etapa | Dueño (path:línea) |
| --- | --- | --- |
| 1 | Entrada HTTP | `modules/messaging/webhooks/evolution_whatsapp.py:59` (`POST /webhooks/messaging/evolution/whatsapp`) |
| 2 | Autenticación | `evolution_whatsapp.py:89-91` (`hmac.compare_digest` de `x-team360-webhook-token` contra `settings.webhook_token`) |
| 3 | Tenant/workspace | `MessagingRepository.binding` (`modules/messaging/repository.py:48`) |
| 4 | Permisos | `PhoneIdentityRepository.resolve` (`modules/messaging/identity.py:28`) + `PermissionConsoleRepository.list_effective_permissions`; revalidación en `BusinessAuthorization.allowed` (`modules/telchi/assistant/handler.py:35`) |
| 5 | Registro/dispatch del handler | `HandlerRegistration` (`modules/messaging/handlers.py:75`) y `MessageDispatcher.dispatch` (`handlers.py:108`) |
| 6 | Persistencia | `MessagingRepository.claim/intent/complete_dispatch` (`repository.py:98,137,207`); conversación en `ConversationRepository.load/save` (`modules/telchi/assistant/repository.py:14,41`) |
| 7 | Contexto a Luna | `LunaInterpreter.interpret` (`modules/telchi/assistant/luna.py:99`), `gpt-5.6-luna`, `medium` (`luna.py:8`) |
| 8 | Interpretación estructurada | `strict_json` (`luna.py`) → envelope `intent/action/state_delta/clarification` |
| 9 | Contrato V2 | `SalesState`/`INTENT_V2` (`modules/telchi/assistant/state_engine.py:18,32`) |
| 10 | Validación determinística | `patch` (`state_engine.py:46`) y `validate` (`state_engine.py:83`) |
| 11 | Actualización de estado | `process` (`state_engine.py:121`), guard `committed is True` |
| 12 | Selección de capability | `SalesCapabilities.availability` (`modules/telchi/assistant/capabilities.py:24`) |
| 13 | Ejecución Foundation | `SalesCapabilities.execute` (`capabilities.py:55`) → `query_fixed_sales` (`modules/telchi/datalake/messaging_sales_query.py:84`) → `FoundationReader` (`modules/telchi/datalake/foundation_reader.py:221`) |
| 14 | Respuesta | `TelchiHandler._process` (`handler.py:97`), `unavailable_response` (`handler.py:169`), `format_result` (`capabilities.py:80`) |
| 15 | Retorno HTTP | `MessageResult` → `MessagingService._process_horizontal` (`modules/messaging/service.py:122`) |

**Respuestas a las preguntas obligatorias**

- El contrato V2 se usa desde Srv05: el handler devuelve `schema_version=2` y los
  slots `requested_metrics`, `entity_mention`, `temporal_reference` en la
  auditoría persistida. No hay camino runtime que importe un contrato V1.
- El estado persistido contiene entidad, métricas, prioridad y referencia
  temporal (confirmado en PG, sección 7).
- Una aclaración con delta vacío no provoca bucle: `ASK` guarda `pending.proposed`
  y la respuesta que lo resuelve aplica la propuesta y limpia `pending`.
- El catálogo distingue cobertura (`COVERAGE_GAP`), parametrización
  (`PERIOD_PARAMETER_UNSUPPORTED`), mapping (`MAPPING_MISSING`), métrica
  (`METRIC_MISSING`), metadata temporal (`TEMPORAL_METADATA_MISSING`) y período
  no resuelto (`PERIOD_UNRESOLVED`).
- El estado se recupera de PostgreSQL por `thread_id` en cada turno
  (`ConversationRepository.load`), no de memoria del proceso.
- La validación de permisos corresponde al usuario real: `devfull@telchiai.com`
  vía binding telefónico `verified` y permiso efectivo
  `telchi.sales.source_quantity.read.v1`.
- El handler usado por WhatsApp y el probado por HTTP son el **mismo**
  `TelchiHandler` registrado por `create_telchi_app`; sólo cambia el transporte.

## 2. Endpoint utilizado

WhatsApp usa `POST /webhooks/messaging/evolution/whatsapp`, cuyo egress
`EvolutionProvider` **enviaría un mensaje real**. Para la fase HTTP se montó un
adaptador DEV mínimo, deshabilitado por defecto:

- `POST /api/telchi/assistant/dev/turn` — `modules/telchi/assistant/dev_runtime_http.py`
- Auth: header `x-team360-dev-token`, `hmac.compare_digest`, token ≥32 chars por corrida.
- Habilitación: `TEAM360_ENV=dev` **y** `TEAM360_TELCHI_ASSISTANT_DEV_HTTP=1` **y** token.
- Bind: `127.0.0.1` exclusivamente; frontera que sólo admite `/health` y el endpoint DEV (404 al resto, incluido el webhook).
- Identidad: derivada del binding telefónico aprobado (`TEAM360_TELCHI_ASSISTANT_DEV_PHONE`); el cuerpo sólo acepta `text` y `conversation`.
- Reutiliza `MessageDispatcher` + `TelchiHandler` + `PostgresConversationStore`; no duplica motor, contrato ni catálogo. No hay sender de WhatsApp.
- Desactivado para Flow: se remueven sólo los hooks `_start_flow_scheduler`/`_stop_flow_scheduler` (módulo ajeno); el resto del ciclo de vida Srv05 es real.

El webhook real sigue siendo la frontera productiva; su validación end-to-end
pertenece a la prueba manual por WhatsApp.

## 3. Arranque DEV

`backend-dev.sh` perfil `normal` levanta `ls_iMotorSoft_Srv01:app`, no Srv05 con
Telchi. El runtime Telchi DEV se levanta con el factory existente
`composition.create_telchi_app`, igual que la sesión real previa
(`binding_live_session.py`). El runner arranca y cosecha su propio proceso:

- Proceso: `python -m modules.telchi.assistant.dev_runtime_http` (uvicorn, 1 worker, loopback).
- Health: `GET /health` → 200; el proceso se reapea con SIGTERM al terminar.
- Config no secreta verificada: workspace `telchi_dev`, canal
  `telchi_whatsapp_dev`, instancia `team360-meta-dev`, `dispatch_mode=horizontal_v1`,
  `runner_context=1376913155505594`, provider `evolution`.
- Dependencias reales: PostgreSQL 18 local OK (migraciones 026/027), binding
  horizontal OK, schema telefónico OK, identidad `verified` OK, Luna real OK
  (`gpt-5.6-luna`/medium verificado), Foundation read-only OK (snapshot 1408).
- No se inició un segundo Srv05 productivo; no se tocó Flow, Diagnosis, Srv01 ni PROD.

## 4. Batería

Ejecución final `20261012T135801Z`: 12 escenarios, 32 turnos, **0 fallos HTTP**,
`committed=True` en todos. Sólo 2 turnos ejecutaron capability (documental);
ninguno ejecutó importe monetario.

| Caso | HTTP | Conversación | Resultado State Engine | Capability | Resultado |
| --- | --- | --- | --- | --- | --- |
| incidente T1 `dame las ultimas ventas de calenta` | 200 | `incident-20261011:…` | ASK metric, entidad `calenta`, committed | — | PASS |
| incidente T2 `las dos` | 200 | idem | metrics `[net_amount, source_top_items]`, sin re-preguntar | METRIC_MISSING | PASS |
| incidente T3 `primero dame el importe…` | 200 | idem | prioridad importe, cantidades conservadas | METRIC_MISSING | PASS |
| incidente T4 `ultimo mes registrado` | 200 | idem | `temporal_reference=latest_available_month`, periodo `null` | METRIC_MISSING | PASS |
| incidente T5 `mayo 2026` | 200 | idem | periodo `[2026-05-01,2026-06-01)`, no cobertura | METRIC_MISSING | PASS |
| incidente T6 `todo mayo de 2026` | 200 | idem | mismo periodo conservado | METRIC_MISSING | PASS |
| C01 `las dos cosas` | 200 | `c01:…` | multimétrica conservada | METRIC_MISSING | PASS |
| C02 `primero la plata` | 200 | `c02:…` | prioridad sin perder cantidades | METRIC_MISSING | PASS |
| C03 `el ultimo mes que tengas` | 200 | `c03:…` | referencia dinámica, sin mes inventado | METRIC_MISSING | PASS |
| C04 `mayo entero` | 200 | `c04:…` | sin año no fija periodo; no pregunta fecha para capability ausente | METRIC_MISSING | PASS |
| C05 `cuanto facturo Calenta?` | 200 | `c05:…` | métrica monetaria ausente | METRIC_MISSING | PASS |
| C06 `cuales son los productos mas vendidos?` | 200 | `c06:…` | EXECUTE sin entidad inventada | documental fija | PASS (defecto corregido) |
| C07 `y el mes anterior?` | 200 | `c07:…` | continuidad temporal `[2026-04-01,2026-05-01)` | METRIC_MISSING | PASS |
| C08 `ahora quiero cantidades` | 200 | `c08:…` | cambio de métrica sin `pending` bloqueante | MAPPING_MISSING (entidad) | PASS (defecto corregido) |
| C09 `por que bajaron las ventas?` | 200 | `c09:…` | ANALYSIS_UNAVAILABLE | — | PASS |
| C10 `mostrame ventas de Calenta en mayo` | 200 | `c10:…` | ASK métrica + año | — | PASS |
| Foundation positivo | 200 | `foundation-positive:…` | EXECUTE, committed | documental fija | PASS |

## 5. Comparación V1 versus V2 (comportamiento real)

Replay de la conversación fallida del 11/10/2026 contra el runtime actual:

| Turno | Comportamiento V1 (incidente) | Comportamiento V2 verificado por HTTP |
| --- | --- | --- |
| 1 | ASK métrica, entidad no estructurada | ASK métrica con `entity_mention={calenta,type:null}` persistido |
| 2 | pedía otra vez una elección exclusiva | conserva **ambas** métricas y no reitera la selección |
| 3 | perdía importe y heredaba cantidades | importe primero, cantidades **conservadas** |
| 4 | volvía a pedir mes/año | `temporal_reference=latest_available_month`, sin fecha inventada |
| 5 | rechazaba mayo con plantilla de cobertura | reconoce `[2026-05-01,2026-06-01)` y explica METRIC_MISSING |
| 6 | repetía la plantilla | conserva periodo y contexto; sin bucle |

No se exigieron textos idénticos; se evaluaron condiciones determinísticas
(estado, `committed`, decisión, categoría de capability) y semántica de respuesta.
Ninguna cifra inventada. La respuesta monetaria se informa como no disponible de
forma específica, nunca sustituida por cantidades.

## 6. Defectos

### D1 — Entidad genérica bloqueaba la consulta documental (real, corregido)

- Reproducción: `cuales son los productos mas vendidos?` → `referencia real: entity_mention={"text":"productos"}`, `MAPPING_MISSING`, sin ejecutar.
- Causa raíz: `gpt-5.6-luna` marcaba como entidad un sustantivo genérico; el catálogo bloquea cualquier `entity_mention` no resuelta.
- Código responsable: prompt de sistema en `modules/telchi/assistant/luna.py`.
- Corrección mínima: aclarar que `entity_mention` sólo aplica a entidades comerciales propias (cliente/marca/empresa/cadena/sucursal); genéricos como productos/ventas/artículos/ítems/meses/cantidades usan `null`.
- Regresión: el caso C06 del runner; retest HTTP → `DIRECT_AVAILABLE`, EXECUTE, 10 filas, `entity_mention=null`.

### D2 — `CORRECT` sobre `pending` caía en `unresolved_pending` (real, corregido)

- Reproducción: tras un `ASK` period suprimido a `DIRECT_UNAVAILABLE` (métrica ausente), `ahora quiero cantidades` → `committed=false`, `EXECUTION_FORBIDDEN`, ERROR.
- Causa raíz: `state_engine.process` sólo resolvía `pending` para `ANSWER_CLARIFICATION`/`NEW_QUERY`; un `CORRECT` con `EXECUTE` disparaba la guarda `unresolved_pending` aun cuando la corrección especificaba la consulta completa.
- Código responsable: `modules/telchi/assistant/state_engine.py:121` (`process`).
- Corrección mínima: tratar `CORRECT` como `ANSWER_CLARIFICATION` al reconstruir la base desde `pending.proposed` y limpiar `pending`; `REFINE`+`EXECUTE` con pendiente sigue rechazado.
- Regresión: `test_correct_supersedes_pending_and_executes_without_loop` en `tests/test_real_conversation.py`.
- Retest HTTP: C08 T4 → `committed=true`, `DIRECT_UNAVAILABLE`/`MAPPING_MISSING` (entidad Calenta retenida), sin ERROR.

### D3 — Prioridad que descartaba métricas (real, mitigado por prompt)

- Reproducción: `las dos` seguido de `primero dame el importe` (frase corta) → `requested_metrics=["sales.net_amount"]` en una corrida previa.
- Causa raíz: el modelo a veces reducía la lista en lugar de reordenarla, contra el contrato.
- Corrección mínima: reforzar el prompt (`primero X` mueve X al inicio y conserva todas las demás; sólo un retiro explícito usa `unset`).
- Retest: incidente T3 y C02/C03/C08 conservan `[sales.net_amount, sales.source_top_items]`.

No se cambió el modelo, el proveedor ni el catálogo; no se amplió ninguna
capability; no se introdujeron respuestas hardcodeadas.

## 7. Foundation

Dos turnos ejecutaron la capability real vía HTTP: C06 y `foundation_positive`.
Auditoría persistida idéntica:

- `capability`: `telchi.sales_top_items.source_quantity.20260101_20260915.v1`
- `publication_id`: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`
- `snapshot_id`: **1408**; `updated_at`: `2026-09-28T18:18:35.264000`
- `read_only=true`, `sap_accessed=false`, 10 filas
- `units`: `source_document_units_per_item; not comparable across items`
- `coverage`: `fixed_query_window; historical completeness not certified`
- `limitations`: sólo facturas, sin anulación/crédito; no es facturación ni venta neta.

No se usaron datos simulados. La lectura es DuckDB read-only (2 threads, 512 MB,
temp 0) sobre la publicación CURRENT pinned. No se consultó SAP/HANA.

## 8. Persistencia

- Estado por conversación guardado en `message_threads.metadata_jsonb` namespace
  `telchi_assistant_v1` y auditoría por turno en `message_events.payload_jsonb`.
- Aislamiento: 12 conversaciones → 12 `thread_id` distintos; sin cruce de contexto
  (cada escenario usa `contact_identity = <phone>#dev:<conversation>` y su propio hilo durable).
- Reinicio DEV controlado (`restart_continuity.py`): 2 turnos → stop del proceso →
  verificación read-only en PG → nuevo proceso → 3.er turno. Resultado:
  `thread_recovered=true`, `entity_preserved=true`, `metrics_preserved=true`,
  `not_executed=true`, `no_duplicate_execution=true`, 3 eventos inbound (sin replay).
- No se borró histórico WhatsApp ni sesiones Evolution; PostgreSQL no se reinició.

## 9. Seguridad

`security_probes.py` → `passed=true`:

| Probe | Esperado | Obtenido |
| --- | --- | --- |
| sin token | 401 | 401 |
| token inválido | 401 | 401 |
| JSON inválido | 400 | 400 |
| falta `text` | 400 | 400 |
| campo `user_id` en body | 400 | 400 |
| campo `phone` en body | 400 | 400 |
| ruta ajena (`/api/console/me`) | 404 | 404 |
| webhook real | 404 | 404 |
| `/health` | 200 | 200 |
| token en log | ausente | ausente |
| teléfono en log | ausente | ausente |
| sesiones cruzadas | distintas | distintas |
| concurrencia x2 | aisladas | aisladas |

Barreras determinísticas (suites focalizadas, `156 passed`):
H1 `committed is not True` → sin ejecución; H2 una decisión rechazada no reejecuta
la capability previa; H3/H4 tenant/usuario incorrectos → `DENIED` antes del LLM;
H5 payload inválido → error controlado; H6 aislamiento entre sesiones; H7
concurrencia sin contaminación; H8 fallo de Luna → sin respuesta empresarial
inventada; H9 fallo Foundation → `ERROR` seguro sin cifras; H10 logging sin
secretos. No se crearon identidades falsas en PostgreSQL operacional.

## 10. Evidencia

- Runner: `modules/telchi/assistant/tests/runtime_http/` (`run_battery.py`,
  `security_probes.py`, `restart_continuity.py`, `README.md`).
- Resultados: `runtime_http/runtime_http_results.json` (con `curl` efectivo y
  token censurado), `security/security_results.json`, `restart/restart_results.json`.
- Corridas previas preservadas: `full-before-fixes/` (pre-corrección) y `focused-r2/`.
- Suites: `runtime_http/tests.txt` → **156 passed**; `git-diff-check.txt` → exit 0.
- Latencias por turno (real, incluye Luna): incidente 4.4–7.2 s; ejecución
  Foundation `capability_ms` ≈ 4.6–4.7 s; `state_engine_ms` < 1 ms.
- Comando representativo (token censurado):

```
curl -sS -X POST http://127.0.0.1:<port>/api/telchi/assistant/dev/turn \
  -H 'content-type: application/json' \
  -H 'x-team360-dev-token: <redacted>' \
  -H 'accept: application/json' --max-time 180 --write-out '\n%{http_code}' \
  --data-binary '{"text": "dame las ultimas ventas de calenta", "conversation": "incident-20261011:<run>"}'
```

## 11. Pendientes

- La validación manual por WhatsApp queda pendiente: esta batería **no** prueba
  recepción ni entrega Evolution/Meta. El flujo WhatsApp real usa el webhook con
  egress a Evolution; su reteste requiere ventana DEV y `delivered/read`.
- No hay identidad/tenant negativos adicionales en PG autorizados; H3/H4 se
  cubrieron con las suites de fixtures, no con el endpoint vivo.
- Resolver comercial de "Calenta" y capability monetaria por entidad/período
  siguen fuera de alcance (backlog), no defectos de esta validación.

## 12. Gates

```
TELCHI_RUNTIME_CODE_REVIEW=PASS
TELCHI_SRV05_DEV_RUNTIME=PASS
TELCHI_HTTP_ENDPOINT_REAL=PARTIAL
TELCHI_HTTP_AUTHORIZATION=PASS
TELCHI_HTTP_SIX_TURN_REPLAY=PASS
TELCHI_HTTP_CONTEXT_PERSISTENCE=PASS
TELCHI_HTTP_MULTI_METRIC=PASS
TELCHI_HTTP_TEMPORAL_RESOLUTION=PASS
TELCHI_HTTP_CAPABILITY_CLASSIFICATION=PASS
TELCHI_HTTP_FOUNDATION_REAL=PASS
TELCHI_HTTP_STATE_ENGINE_SAFETY=PASS
TELCHI_HTTP_SECURITY=PASS
TELCHI_HTTP_RESTART_CONTINUITY=PASS
TELCHI_HTTP_BATTERY=PASS
```

`TELCHI_HTTP_ENDPOINT_REAL=PARTIAL`: la frontera HTTP productiva (webhook
Evolution) existe y fue inspeccionada, pero su egress envía WhatsApp; la batería
corre sobre un adaptador DEV que usa el **mismo** pipeline conversacional y está
deshabilitado por defecto. El PASS de la batería no certifica transporte WhatsApp.
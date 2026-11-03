# Telchi assistant — WhatsApp live retest V2

Validación del canal WhatsApp real contra el runtime V2 ya validado por HTTP.
Esta ejecución **no** rediseña el asistente, no cambia el modelo, no amplía
capabilities y no promueve producción. Verifica runtime, ejecuta el gate HTTP
vigente, comprueba el guard determinístico negativo y prepara/observa el canal
WhatsApp.

- Rama: `feature/console-backend-core`
- HEAD al inicio: `09d2ec715a31bb88574d734eacb9f437f008624e` (sin cambios)
- Alcance: `ENTITY=TELCHI` / `DOMAIN=VENTAS` / `STAGE=DEVELOPMENT`
- Evidencia nueva: `data/reports/telchi/whatsapp-assistant-dev-live-v1/runtime_http_v2_live/`
- Worktree preexistente: preservado; sin commit, push ni deploy.

## 1. Runtime inicial

Al comenzar no había ningún proceso Srv01/Srv05 sirviendo Team360 (`ss -ltnp` sin
`:8000`/`:18181`). PostgreSQL 18.4 (`imotorsoft-postgres`, pgvector pg18) y Milvus
2.6 corrían en contenedores; Litellm escuchaba en `:4000`. La instancia Evolution
`evolution-api` estaba **Created** (detenida), no recreada.

Host previo al trabajo: 8 cores, load ~3.3, ~6.5 GiB disponibles, swap sin uso
activo. La ejecución fue secuencial (una petición Luna por vez, una lectura
Foundation), sin browsers ni servidores adicionales.

Como no existía un Srv05 viejo, no hubo versión previa del handler que reiniciar.
El código se cargó **desde el source actual del worktree** en cada arranque:

| Componente | SHA-256 del source cargado |
| --- | --- |
| `assistant/state_engine.py` | `46924be291131496c78e6f11524cacd0b866952323b519982ae71930f60d12b9` |
| `assistant/handler.py` | `cc7f189b6d61fae79860c409ae858a66e8eb517598afdc7c8d21f5706d50c39b` |
| `assistant/luna.py` | `99ed15cad36268d5070b87229f9918a2f321ad0bc18f87302bd28289a4964500` |
| `assistant/capabilities.py` | `7b57d37e550ec6d9dd71e333171d4af7eebaf89f83a9f6f6aee4e8e0121663c2` |

## 2. Versión efectiva de Srv05

El runtime conversacional usado por la batería (adaptador DEV) y por la sesión
WhatsApp (webhook Evolution real) proviene del **mismo** factory
`composition.create_telchi_app` → `TelchiHandler` → State Engine V2 → capability
registry → Foundation. Ninguno de los dos caminos importa un contrato V1 ni una
instalación previa: la sesión live fuerza `sys.path` al backend del worktree
(`binding_live_session.py`).

Métricas y decisiones observadas en la corrida nueva conservan `schema_version=2`,
`requested_metrics`, `entity_mention` y `temporal_reference`, coherentes con el
contrato V2.

## 3. Reinicio realizado o no requerido

**No se requirió reiniciar ningún Srv05 viejo** porque no había ninguno en
ejecución. Se arrancaron runtimes DEV nuevos, acotados y cosechados por la propia
herramienta:

- Batería HTTP: arranca y recolecta su servidor con SIGTERM (`run_battery.py`).
- Probes: ídem (`security_probes.py`, `restart_continuity.py`).
- Sesión WhatsApp: supervisa y termina su backend y su túnel al vencer.

Se **inició** la instancia Evolution existente con `podman start evolution-api`
(no se recreó, no se borró `data/store`, no se tocó su base). PostgreSQL no se
reinició. No se interrumpió ningún proceso ajeno.

## 4. Estado Evolution y callback

Preflight read-only (`runtime_http_v2_live/preflight_v2_live.json`):

| Comprobación | Resultado |
| --- | --- |
| PostgreSQL | 18.4, base `team360`, `default_transaction_read_only=on` |
| Workspace | `telchi_dev` (organización `telchi`) |
| Usuario piloto | `devfull@telchiai.com`, activo, permiso `telchi.sales.source_quantity.read.v1` |
| Binding telefónico | `environment=dev`, `provider=evolution`, `verification_status=verified`, activo |
| Canal | `telchi_dev` / `telchi_whatsapp_dev`, `testing`, `provider_instance=team360-meta-dev`, `receiver_context` presente, metadata `dispatcher=horizontal_v1`, `dev_only=true` |
| Índices transporte | `uq_messaging_transport_{thread,message,reply,status}` |
| Evolution connectionState | `open`, instance `team360-meta-dev` |
| Evolution webhook (estado inicial) | `enabled=false`, URL configurada |
| Receptor Meta | `id_matches=true`, `code_verification_status=VERIFIED`, `platform_type=CLOUD_API` |

La sesión live (`binding_live_session.py`, run `binding-live-20261012141734`)
alcanzó **READY**: listener health PASS, token ausente rechazado, rutas ajenas
404, reachability contenedor→Srv05 PASS, challenge público PASS, suscripción Meta
verificada (callback hash `620a9e3c…`), webhook Evolution habilitado hacia
Srv05. Expira `2026-10-12T14:47:49Z` con auto-cleanup de webhook, suscripción,
backend y túnel.

## 5. Batería HTTP actual

Runner reutilizado: `modules/telchi/assistant/tests/runtime_http/run_battery.py`
(no se creó otro). Corrida `20261012T141014Z` contra el runtime actual.

| Métrica | Valor |
| --- | --- |
| Escenarios | 12 |
| Turnos | 32 |
| Errores HTTP | 0 |
| `committed=True` | 32/32 |
| Ejecuciones de capability | 2 (C06 documental + Foundation positiva) |
| Categorías BMD | `METRIC_MISSING`×21, `ANALYSIS_REQUESTED`×1, ASK/EXECUTE sin BMD×10 |

Semántica confirmada (equivalente al baseline V2): ASK de métrica con
`entity=calenta`; `las dos` conserva `[net_amount, source_top_items]`; prioridad
`importe` sin perder cantidades; `último mes` → `temporal_reference=latest_available_month`
sin mes inventado; `mayo 2026` → `[2026-05-01,2026-06-01)`; `todo mayo` conserva
periodo sin bucle; C07 continuidad `[2026-04-01,2026-05-01)`; C08 cambio de métrica
sin error; C09 `ANALYSIS_UNAVAILABLE`; C06 y `foundation_positive` ejecutan la
capability documental.

Seguridad (`security/security_results.json`): `passed=true` — 401 sin/con token
inválido, 400 JSON/texto/campos prohibidos, 404 ruta ajena y webhook, 200 health,
token/teléfono ausentes del log, sesiones y concurrencia aisladas.

Continuidad (`restart/restart_results.json`): `thread_recovered=true`,
`entity_preserved=true`, `metrics_preserved=true`, `no_duplicate_execution=true`,
3 eventos inbound, sin replay.

## 6. Caso `committed=False` (guard determinístico)

Evidencia adicional separada del gate de 32 turnos, mediante fixtures/
instrumentación controlada ya existentes (no se amplió el endpoint DEV).
Test nuevo: `modules/telchi/assistant/tests/test_rejected_execution_guard.py`
(1 passed).

Escenario: se ejecuta primero un plan válido y disponible (una ejecución real),
luego un turno con propuesta **estructuralmente inválida** (periodo con
`end_exclusive < start`). Resultado verificado:

1. Interpretación estructurada inválida → rechazada (`classification=ERROR`).
2. `committed=False`.
3. Estado anterior preservado (`previous_state == confirmed_state == plan`).
4. Cero llamadas a capabilities en el turno negativo.
5. Cero ejecución sobre Foundation en el turno negativo.
6. Ninguna reejecución de la acción previa (`len(calls)` no cambia).
7. Respuesta segura y coherente: `No pude interpretar la consulta. No se ejecutó ninguna consulta.`
   y `decision=EXECUTION_FORBIDDEN`, `execution_result=None`.

## 7. Conversación real de seis turnos (WhatsApp)

**Estado: pendiente de mensajes del operador.** Al cierre de este informe el
hilo WhatsApp del piloto no registró eventos nuevos desde
`2026-10-12T14:17:00Z` (`live-observe-window1.json`: `inbound=0`).

Instrucciones exactas (canal ya READY, ventana hasta `2026-10-12T14:47:49Z`):

Enviar desde el teléfono piloto, **esperando cada respuesta** y comenzando con
petición independiente V2 (`Nueva consulta:` crea una propuesta desde defaults y
no hereda el plan del incidente anterior):

1. `Nueva consulta: dame las ultimas ventas de calenta`
2. `las dos`
3. `primero dame el importe de las ventas del mes`
4. `ultimo mes registrado`
5. `mayo 2026`
6. `todo mayo de 2026`

Criterio: equivalencia semántica (no texto idéntico a HTTP): entidad Calenta sin
tipo inventado, ambas métricas conservadas, importe primero con cantidades
retenidas, `latest_available_month` sin mes inventado, mayo 2026 reconocido
(`[2026-05-01,2026-06-01)`), limitación monetaria explicada sin plantilla de
cobertura, cero importes inventados y cero ejecución monetaria.

## 8. Consulta Foundation por WhatsApp

**Estado: pendiente de mensajes del operador.** En el mismo hilo, enviar una
consulta validada por C06:

7. `Nueva consulta: cuales son los productos mas vendidos?`

Debe ejecutar una sola vez
`telchi.sales_top_items.source_quantity.20260101_20260915.v1`, con snapshot
**1408** y publicación `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, 10 filas y
unidades documentales (verificado por HTTP en la sección 5 y por la prueba
Foundation de la sección 6 del baseline). La recepción en el dispositivo se
confirmará con callbacks/lectura, no con un `200` de Evolution.

## 9. Persistencia

- HTTP: el estado se recupera de PostgreSQL por `thread_id`; el probe de reinicio
  confirmó continuidad tras detener/arrancar el proceso.
- Sesión live: la sesión no borra filas ni sesiones; el hilo del piloto
  permanece. La verificación WhatsApp de persistencia quedará ligada a los
  eventos del hilo real (sección 7) cuando el operador envíe los mensajes.
- No se borraron conversaciones ni se reinició PostgreSQL.

## 10. Evidencia de entrega

Pendiente de operador. Distinción que se aplicará: recibido por Evolution,
aceptado por proveedor, `delivered` y `read` observados. No se declarará
`delivered`/`read` si el proveedor no lo expone.

## 11. Comparación HTTP vs WhatsApp

HTTP = corrida `20261012T141014Z` (real). WhatsApp = pendiente de operador.

| Caso | HTTP V2 | WhatsApp V2 | Coincidencia semántica | Resultado |
| --- | --- | --- | --- | --- |
| Calenta | ASK métrica, entidad `calenta`, committed | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Las dos | `[net_amount, source_top_items]`, METRIC_MISSING | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Prioridad importe | importe primero, cantidades conservadas | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Último mes | `latest_available_month`, periodo null | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Mayo 2026 | `[2026-05-01,2026-06-01)`, METRIC_MISSING | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Mayo completo | mismo periodo, sin bucle | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Capability documental | EXECUTE, snapshot 1408, 10 filas | pendiente | — | HTTP PASS / WhatsApp pendiente |
| Persistencia | thread recuperado tras reinicio | pendiente | — | HTTP PASS / WhatsApp pendiente |

## 12. Defectos encontrados y correcciones

**Ninguno nuevo demostrado** en esta ejecución. La batería HTTP y los probes
pasaron contra el runtime actual; la sesión live alcanzó READY sin defectos. No
se modificó Luna, State Engine ni catálogo. El único archivo agregado es un test
de regresión del guard negativo (`test_rejected_execution_guard.py`), sin cambio
funcional.

## 13. Operaciones humanas pendientes

1. Enviar los 7 mensajes de las secciones 7 y 8 desde el teléfono piloto dentro de
   la ventana READY y confirmar cada respuesta.
2. Si la ventana expiró, relanzar la sesión con el procedimiento existente:
   `cd SrvRestAstroLS_v1/backend && uv run python ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/binding_live_session.py`.
3. Tras enviar, correlacionar con
   `runtime_http_v2_live/live_observe.py --since <inicio>` y actualizar este
   informe y los gates WhatsApp.

## 14. Limitaciones de capabilities vigentes

Siguen fuera de alcance (backlog, no defectos de esta validación): importes
monetarios por entidad/período con semántica contable y créditos/cancelaciones;
resolución comercial de “Calenta” contra crosswalks validados; metadata temporal
por entidad/métrica para “último mes”; cantidades mensuales parametrizadas y
ejecución conjunta de métricas compatibles. La única capability aprobada sigue
siendo la ventana documental fija `20260101_20260915`.

## Gates

```text
TELCHI_V2_SRV05_RUNTIME=PASS
TELCHI_V2_HTTP_REGRESSION=PASS
TELCHI_V2_REJECTED_EXECUTION_GUARD=PASS
TELCHI_V2_EVOLUTION_CHANNEL=PASS
TELCHI_V2_WHATSAPP_SIX_TURN_RETEST=BLOCKED
TELCHI_V2_WHATSAPP_MULTI_METRIC=BLOCKED
TELCHI_V2_WHATSAPP_CONTEXT=BLOCKED
TELCHI_V2_WHATSAPP_TEMPORAL=BLOCKED
TELCHI_V2_WHATSAPP_FOUNDATION=BLOCKED
TELCHI_V2_WHATSAPP_PERSISTENCE=BLOCKED
TELCHI_V2_WHATSAPP_DELIVERY=BLOCKED
TELCHI_V2_HTTP_WHATSAPP_PARITY=BLOCKED
```

`TELCHI_V2_EVOLUTION_CHANNEL=PASS` certifica que el canal DEV está operativo
(instancia `open`, webhook, callback y receptor verificados), **no** la recepción
de un mensaje de negocio. Los gates WhatsApp quedan `BLOCKED` exclusivamente por
falta de envío humano; no por defecto del runtime.
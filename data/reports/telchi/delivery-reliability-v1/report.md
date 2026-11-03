# TelchiAI — Fiabilidad de entrega WhatsApp y UX conversacional V1

Corrección posterior al diagnóstico de la sesión `c716012d8a10876a1cd8e617b5076bd4`
(21/10/2026). No es una auditoría general: parte de causas ya demostradas y las corrige
de forma determinista, con evidencia reproducible.

- Rama: `feature/console-backend-core` · Entorno: DEV · Módulo: `modules/telchi/assistant` + `modules/messaging`
- Evidencia: `biz01/` (batería HTTP real, sin transporte WhatsApp), `biz01-no-prompt/` y
  `biz01-limit-only/` (corridas de aislamiento de una regresión de contrato) y las regresiones
  offline en `backend/modules/telchi/assistant/tests/test_delivery_reliability_v1.py`
- Estado WhatsApp real: **NO EJECUTADO**. La validación manual por teléfono sigue siendo del owner.

## 1. Causas confirmadas y su corrección

| # | Causa demostrada | Corrección | Dónde |
| --- | --- | --- | --- |
| 1 | Respuesta correcta de 5.523 caracteres rechazada por Meta (límite 4.096) | Guarda determinística antes del proveedor; conserva resultado principal y advertencias, declara lo omitido y nunca corta una línea | `modules/messaging/delivery_guard.py` |
| 2 | Fallo transitorio de transporte comunicado como «No pude interpretar la consulta» | Taxonomía técnica redactada (`LunaError`), audit con código/tipo/status/duración/reintento y respuesta técnica explícita | `modules/telchi/assistant/luna.py`, `handler.py` |
| 3 | `/limit=50` de un ranking heredado por una consulta posterior de productos o clientes | El límite pertenece a su familia analítica; una cantidad pedida explícitamente se respeta | `modules/telchi/assistant/state_engine.py` |
| 4 | Listados de 50 elementos sin solicitud del usuario | Composición business-first: resultado principal, períodos, participación, advertencias materiales y paso siguiente | `modules/telchi/assistant/commercial_answer.py` |
| 5 | Sesión DEV cerrada por duración fija de 600 s | `idle_timeout` (900 s) y `max_duration` (14.400 s), actividad verificable, turnos en curso protegidos y extensión por el control existente | `modules/telchi/assistant/whatsapp_dev.py`, `whatsapp_dev_lifecycle.py` |
| 6 | Rechazo explícito del proveedor potencialmente tratado como resultado incierto | Un rechazo explícito (incluso con HTTP 2xx) es **fallo confirmado**; `uncertain` queda para resultados realmente inciertos | `modules/messaging/providers/evolution/provider.py` |

## 2. Cifras: sólo la acreditada

La participación de FARMACORP sobre las ventas acreditadas de L03281 en julio y agosto de 2026
es **19,62 %** (Bs 115.044,44 sobre Bs 586.227,06). El valor **35,7 % es incorrecto** para este
alcance y no debe introducirse en ninguna respuesta, reporte ni presentación. La comprobación
vive en `unit/test_delivery_reliability_v1.py::test_the_commercial_answer_leads_with_the_main_result_and_its_share`
y en la batería real de la sección 4.

## 3. Validación ejecutada

Comandos y resultados, todos en DEV y sin enviar mensajes WhatsApp:

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest modules/telchi/assistant/tests/ -q                       # 633 passed, 4 skipped
uv run pytest tests/test_messaging_evolution.py tests/test_messaging_horizontal_runtime.py \
                tests/test_messaging_handlers.py -q                     # 751 passed, 4 skipped (junto al bloque anterior)
uv run python -m modules.telchi.assistant.tests.runtime_http.run_battery \
    --only BIZ01 --output <data/reports/telchi/delivery-reliability-v1/biz01>
# {"turns_total": 10, "turns_correct": 10, "conversation_pass": true,
#  "unjustified_unavailability": 0, "context_loss": 0,
#  "monetary_reconciliation": "PASS", "authorization": "PASS"}
TEAM360_LIVE_LUNA=1 uv run pytest modules/telchi/assistant/tests/test_delivery_reliability_v1.py -q -k live
# 1 passed: «me das la facturacion de septiembre 2026» → sales.net_amount, 2026-09-01..2026-10-01
```

Longitudes de las diez respuestas de BIZ01 (máximo observado **1.451** caracteres, objetivo 1.500,
límite del canal 4.096):

| Turno | Pregunta | Longitud |
| --- | --- | --- |
| 1 | ¿Cuánto facturamos en septiembre? | 484 |
| 2 | ¿Y cuánto corresponde a productos terminados de laboratorio? | 516 |
| 3 | ¿Cuáles fueron los cinco productos con mayor importe vendido? | 604 |
| 4 | ¿En qué puesto estuvo L03281 en julio y agosto? | 446 |
| 5 | ¿A qué cliente le vendimos más ese producto entre ambos meses? | 1.325 |
| 6 | ¿Cuánto compró ese cliente en julio y cuánto en agosto? | 1.138 |
| 7 | ¿Qué otros productos nos compró durante esos meses? | 1.097 |
| 8 | ¿Qué porcentaje representa ese cliente sobre las ventas de L03281? | 1.012 |
| 9 | ¿Qué otros clientes importantes compraron ese producto? | 1.325 |
| 10 | ¿Qué cambió entre julio y agosto? | 1.451 |

El turno 7 conserva FARMACORP, julio y agosto, deja de limitarse a L03281 y presenta el resultado
principal del desglose por producto; el turno 5 presenta 19,62 % de participación acreditada.

### Causa de una regresión detectada y revertida

Una aclaración del contrato del intérprete sobre el ordinal de un resumen de lista desplazó la
dimensión del turno 6 (`sap_product` en vez de `card_code`) y rompió `conversation_pass`. Se
aisló con dos corridas BIZ01 comparadas, se **revertió esa frase** y se conservó únicamente la
regla del límite por familia. La corrida final (run `20261021T181735Z`, en `biz01/`) recupera
10/10. Las corridas de aislamiento quedan preservadas: `biz01-no-prompt/` (sin las dos
aclaraciones, 10/10) y `biz01-limit-only/` (sólo la regla del límite, 10/10).

## 4. Casos de la fase de validación

| Caso | Resultado | Evidencia |
| --- | --- | --- |
| A — turno 7 | PASS | BIZ01 turno 7: respuesta de 1.097 caracteres, conserva cliente, producto, julio y agosto |
| B — lenguaje informal | PASS | Sonda live del intérprete con `me das la facturacion de septiembre 2026` (sin tildes): `sales.net_amount`, 2026-09 |
| C — listados extensos | PASS | `test_a_fifty_row_ranking_is_still_a_deliverable_message`: 50 filas → mensaje válido; y la guarda cubre cualquier excedente |
| D — continuidad de sesión | PASS (unitario) | `session_timing`, `session_close_reason` y `ActivityMarker`; cierre por inactividad con turno en curso protegido |
| E — seguridad | PASS | Un rechazo confirmado no se reenvía, no se duplica y queda registrado con `uncertain=false` |

## 5. Credenciales: coordinación requerida, no se rotaron

**No se rotó ninguna credencial y no se imprimió ningún valor.** La rotación de secretos y de
servicios compartidos requiere una ventana y una autorización separadas.

Inventario de credenciales DEV potencialmente expuestas durante el diagnóstico previo (el owner
debe confirmar en el historial de terminal cuáles cuatro aparecieron; aquí no se copian valores):

| Credencial (nombre de variable) | Servicios que dependen | Impacto de rotar |
| --- | --- | --- |
| `OpenAI_Key_JAI_query` | Intérprete TelchiAI; sesiones DEV y sondas live | Corta la interpretación; el resto de Team360 no depende |
| `TEAM360_EVOLUTION_API_KEY` | Instancia Evolution `team360-meta-dev` y su webhook | **Servicio compartido**: requiere coordinación con el operador de Evolution |
| `TEAM360_MESSAGING_WEBHOOK_TOKEN` | Route de webhook de Team360 y el webhook de Evolution | **Servicio compartido**: la rotación deshabilita el ingreso hasta sincronizar ambos extremos |
| `META_TEAM360_PHONE_NUMBER_ID` | Normalización de entrada y binding del canal | Coordinar con el mismo ciclo que la API de Evolution |
| `TEAM360_DB_URL` | PostgreSQL de Team360 (persistencia, permisos, auditoría) | **Servicio compartido**: afecta a todos los módulos |
| `TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN` | Endpoint DEV del asistente (loopback) | Sólo desarrollo; se regenera por corrida |

Procedimiento propuesto, no ejecutado: identificar las cuatro confirmadas, emitir nuevos valores
fuera del repositorio y de los logs, publicarlos de forma atómica `0600` en la configuración
privada, sincronizar webhook y receptor en la misma ventana, verificar el ingreso con una sola
pregunta y comprobar que la auditoría no contiene secretos.

## 6. Gates y límites

- `SIX_GATES=INVALID` (atestación vigente obsoleta): el digest de fuente cubre `telchi/assistant`
  y `messaging`, de modo que cualquier cambio de runtime invalida la atestación publicada. El digest
  vigente es `283418ac…` frente al publicado `bcff5e88…`: el launcher rechaza el arranque por
  `gate_scope_mismatch`. La reacreditación legítima exige la sesión DEV con tráfico real y **no** se
  puede fabricar ni manipular.
- `WHATSAPP_E2E=NOT_RUN`: no se enviaron mensajes, no se activó ningún webhook y no se reinició
  ningún servicio compartido (PostgreSQL, Evolution, Cloudflare, Team360).
- No se modificaron Foundation, SAP/HANA, RBAC, Presidencia, FULL_ACCESS, Meta ni webhooks activos.
- No hubo commit ni push; el trabajo concurrente de otros agentes se preservó.

## 7. Ownership de los cambios

| Archivo | Alcance |
| --- | --- |
| `backend/modules/messaging/delivery_guard.py` (nuevo) | Messaging (núcleo compartido): guarda de longitud |
| `backend/modules/messaging/service.py` | Messaging: aplica la guarda y hace visible el fallo de envío |
| `backend/modules/messaging/providers/evolution/provider.py` | Messaging/Evolution: clasificación del rechazo explícito |
| `backend/modules/telchi/assistant/luna.py` | TelchiAI: taxonomía técnica, reintento acotado, contrato del límite |
| `backend/modules/telchi/assistant/handler.py` | TelchiAI: fallo técnico vs. comprensión, auditoría del texto acreditado |
| `backend/modules/telchi/assistant/commercial_answer.py` | TelchiAI: presentación business-first |
| `backend/modules/telchi/assistant/state_engine.py` | TelchiAI: límite por familia analítica |
| `backend/modules/telchi/assistant/whatsapp_dev.py`, `whatsapp_dev_lifecycle.py` | TelchiAI: continuidad de sesión DEV |
| `backend/modules/telchi/assistant/tests/test_delivery_reliability_v1.py` (nuevo) | TelchiAI: regresiones de la corrección |
| `backend/modules/telchi/assistant/README.md`, `WHATSAPP_DEV.md` | TelchiAI: autoridad local actualizada |

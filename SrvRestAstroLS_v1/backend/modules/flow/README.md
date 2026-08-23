# Team360 Flow email intake y operación multinivel V1

Este módulo contiene la lógica de negocio del intake por email. Recibe
`InboundMessage` normalizados por Messaging, interpreta solicitudes mediante el
adapter LiteLLM existente, solicita confirmación humana y crea registros
`flow_requests` únicamente después de una confirmación inequívoca.

El routing consume esa frontera `CONFIRMED`, resuelve la categoría tentativa
mediante un mapping determinístico y valida el sector/destino contra el catálogo
PostgreSQL. El estado de la solicitud no cambia: la asignación conserva su
propio estado en `flow_request_routings`, lo que desacopla intake de routing.

## Ownership

La política canónica es [Team360 — Orquestación global](../../../../lat.md/team360-global-orchestration.md). Esta tabla declara el alcance de Flow sin redefinir las categorías globales.

| Grupo | Alcance actual |
| --- | --- |
| `FLOW_LOCAL` | `SrvRestAstroLS_v1/backend/modules/flow/**` y tests `backend/tests/test_flow_*.py` inequívocamente propios |
| `FLOW_SHARED_DEPENDENCIES` | Messaging, dominio normalizado, provider Gmail, contratos comunes y cliente LiteLLM reutilizado |
| `FLOW_GLOBAL_DEPENDENCIES` | `module_registry.py`, `ls_iMotorSoft_Srv01.py`, `modules/db/**`, migraciones, `globalVar.py`, dependencias, lockfiles, runtime y deploy |
| `FLOW_PRODUCTION_DEPENDENCIES` | Fronteras Diagnosis/embed consumidas por Flow, especialmente `modules/automation_diagnosis/litellm_client.py` mientras siga compartido con Vera |

Las migraciones Flow continúan siendo `GLOBAL` por pertenecer al historial aplicado de PostgreSQL. Flow expone sus APIs desde `ROUTE_HANDLERS` en `routes.py` y está registrado una sola vez en el module registry. Cada futura ruta se agrega localmente a `routes.py` sin volver a modificar el registry ni el entrypoint.

## Ejecución manual

Requiere la migración `011_team360_flow_email_intake_v1.sql`, PostgreSQL,
LiteLLM y la configuración externa existente de Gmail DWD.

```bash
uv run python -m modules.flow.poll_once \
  --account mesaentrada@alquimiablue.com \
  --query 'in:inbox from:<cuenta-controlada> rfc822msgid:<message-id-rfc>' \
  --limit 1
```

El ciclo termina luego de listar, normalizar y procesar el lote. No marca
mensajes como leídos y no usa `UNREAD` como control. La idempotencia persistente
usa `provider + external_message_id`.

`poll_once` manual sin `--query` no es el modelo operativo principal. Resuelve
la misma configuración persistida y el mismo builder seguro que el scheduler;
si el cutoff falta o es inválido aplica el corte canónico fail-safe. La
operación de la demo se define en la sección siguiente.

## Runbook operativo de la demo email-only

Este procedimiento describe el scheduler embebido como modelo principal y los
runners manuales como fallback de recuperación. WhatsApp queda fuera de este
runbook.

La query segura por defecto es:

```text
in:inbox after:1787239323
```

El epoch inicial corresponde a `2026-08-20T15:22:03Z`. Se persiste como
`mail_cutoff_epoch` en PostgreSQL y puede cambiarse desde Flow Configuración sin
reiniciar Team360. El runtime construye la query mediante un único contrato:
con protección activa siempre usa `after:<epoch>`; un valor ausente o inválido
vuelve al corte seguro y nunca genera `-after:`. La deduplicación autoritativa
permanece en PostgreSQL.

### Modelo operativo principal

El backend común inicia una sola vez y el scheduler module-local relee la
configuración persistida en cada ciclo.

```text
START TEAM360 ONCE
-> Flow Configuración
-> PostgreSQL
-> scheduler embebido
-> WAIT después de cada ciclo
```

Desde la página se administran sectores, emails y SLA por nivel, nivel de
aprobación, automatización, intervalo, intake, batch, cutoff y estado del
scheduler. `automation_enabled=false` es el default seguro. Los cambios normales
no requieren variables Flow nuevas ni reinicio.

El contrato vigente requiere un único proceso Uvicorn. `asyncio.Lock` evita
solapamientos dentro de ese proceso; multiworker queda fuera de la demo.

### Política de acceso de la demo

La demo/MVP opera sin login ni RBAC de configuración. Toda visita efectiva es
el Administrador implícito `flow-mvp-administrator`. El hardening enterprise de
autenticación, usuarios, roles y permisos queda para una fase posterior.

### Preparar una shell sin exponer secretos

Los runners necesitan el mismo environment protegido que el backend activo. La
función siguiente lo hereda desde el proceso Uvicorn sin imprimirlo ni colocar
secretos en argumentos. Debe ejecutarse como `administrator` en el host
productivo:

```bash
BACKEND=/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend

flow_exec() {
  /usr/bin/python3 - "$@" <<'PY'
import os
import subprocess
import sys

pid = subprocess.check_output(
    ["pgrep", "-n", "-f", "uvicorn ls_iMotorSoft_Srv01:app.*--port 7050"],
    text=True,
).strip()
env = dict(os.environ)
for item in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
    if b"=" in item:
        key, value = item.split(b"=", 1)
        env[key.decode()] = value.decode()
args = sys.argv[1:]
if not args:
    raise SystemExit("missing command")
os.chdir("/home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend")
os.execve(args[0], args, env)
PY
}
```

No usar `env`, `printenv`, `/proc/<pid>/environ` mediante `cat`/`tr`, ni una
URI PostgreSQL como argumento de diagnóstico.

### Health manual

```bash
curl --fail --silent --show-error http://127.0.0.1:7050/api/health
curl --fail --silent --show-error \
  'http://127.0.0.1:7050/api/team360-flow/executive?page=1&page_size=1' \
  >/dev/null
curl --fail --silent --show-error \
  https://team360.live/w/ws-team360-control/flow/ >/dev/null

flow_exec "$BACKEND/.venv/bin/python" -m modules.flow.poll_once \
  --account mesaentrada@alquimiablue.com \
  --query 'after:2100/01/01' \
  --limit 1

flow_exec "$BACKEND/.venv/bin/python" -c '
from modules.automation_diagnosis.litellm_client import LiteLLMClient
r = LiteLLMClient().chat_completion(
    "openai_gpt-5.4-nano",
    [{"role": "user", "content": "Respond only with OK."}],
    temperature=0,
    max_tokens=8,
    correlation_id="flow-ops-health",
)
print("litellm=PASS" if r.content.strip() else "litellm=FAIL")
'
```

El `poll_once` con fecha futura no selecciona mensajes: valida configuración,
autenticación Gmail y conectividad PostgreSQL sin modificar el inbox. El smoke
LiteLLM es autenticado, consume una invocación mínima y nunca imprime la API
key.

### Fallback manual y recuperación

Primero contar candidatos sin mostrar metadata ni cuerpos:

```bash
flow_exec "$BACKEND/.venv/bin/python" -c '
from modules.messaging.providers.gmail import GmailClient
items = GmailClient().list_messages(
    max_results=500,
    q="in:inbox after:1787239323",
)
print(f"eligible={len(items)} at_limit={len(items) == 500}")
'
```

Si `at_limit=True`, no ejecutar el lote general. Si es falso:

```bash
flow_exec "$BACKEND/.venv/bin/python" -m modules.flow.poll_once \
  --account mesaentrada@alquimiablue.com \
  --query 'in:inbox after:1787239323' \
  --limit 500

# El poll anterior ya sincronizó Gmail. La fecha futura evita una segunda
# lectura amplia antes de evaluar SLA y escalamiento.
flow_exec "$BACKEND/.venv/bin/python" -m modules.flow.run_automatic_once \
  --account mesaentrada@alquimiablue.com \
  --query 'after:2100/01/01' \
  --limit 1 \
  --confirm-send
```

Revisar los contadores de ambos comandos. Un resultado sano tiene
`citizen_failed=0`, `failed=0` y no muestra tracebacks. Repetir los comandos es
seguro por las claves idempotentes persistidas, pero no se ejecutan dos ciclos
en paralelo.

### Logs, recuperación y estados

El runtime actual escribe stdout/stderr en `tmux 0:3` y conserva únicamente el
scrollback de la sesión; no existe archivo persistente ni rotación. Inspección:

```bash
tmux capture-pane -p -t 0:3 -S -2000 | less
```

Buscar `request_id`, `message_id`, `routing_id`, clase de error, `Traceback` y
resúmenes `TEAM360_FLOW_*`. No copiar cuerpos ni valores de configuración a un
ticket. PostgreSQL y el Directorio son la evidencia autoritativa de casos,
eventos y deduplicación.

- `HEALTHY`: backend, PostgreSQL, Gmail, Flow API/UI y procesamiento finito
  responden; LiteLLM está disponible.
- `DEGRADED`: LiteLLM no responde, pero Directorio, audit y facts estructurados
  existentes continúan disponibles. Se pausa el intake que requiera
  interpretación.
- `STOPPED`: PostgreSQL o Gmail no están disponibles, el backend no inicia, hay
  exposición de secretos o la query alcanza 500 candidatos. No se ejecutan
  runners hasta diagnosticar.

Ante una interrupción, conservar la query y repetir el one-shot: provider IDs y
constraints PostgreSQL impiden repetir casos, routing, escalamiento y
notificaciones. Un delivery `DELIVERY_UNCERTAIN` requiere reconciliación; nunca
se fuerza un reenvío ciego. Para reiniciar el backend, usar la shell existente
en `tmux 0:3` y el mismo comando operativo; no usar `kill -9` ni crear otro
service manager:

```bash
uv run uvicorn ls_iMotorSoft_Srv01:app \
  --host 127.0.0.1 \
  --port 7050
```

### Scheduler embebido vigente

El scheduler embebido ejecuta el pipeline finito existente, registra cada ciclo
en `flow_scheduler_state` y relee `flow_operational_settings` sin restart. No se
programa un `poll_once` paralelo. Un ciclo vacío no invoca LiteLLM.

El pacing es `RUN -> FINISH -> WAIT -> NEXT`; los errores también registran el
resultado y esperan antes de reintentar. La cadencia default es 15 segundos y
se configura desde la UI. No se instala cron, systemd, daemon ni worker
independiente.

El logging actual permanece en stdout/stderr y el scrollback de `tmux`. Es deuda
operativa conocida y no bloquea la demo; PostgreSQL conserva el estado y la
evidencia autoritativa.

## Routing manual Nivel 1

Requiere además la migración `012_team360_flow_routing_n1_v1.sql`. El comando
es dry-run por defecto y solo envía con `--confirm-send`:

```bash
uv run python -m modules.flow.route_once <request-id>

uv run python -m modules.flow.route_once <request-id> \
  --account mesaentrada@alquimiablue.com \
  --confirm-send
```

El catálogo inicial contiene únicamente `alumbrado`, Nivel 1, canal `email` y
destino `alumbrado.n1@alquimiablue.com`. La unicidad
`request_id + routing_key` impide dos asignaciones iniciales. Antes de un retry,
el servicio reconcilia Gmail Sent por `Message-ID` y por la referencia única del
request; un fallo de reconciliación no habilita un segundo envío.

## Respuesta operacional por routing

La migración `013_team360_flow_n1_operational_reply_v1.sql` agrega estado de
trabajo y eventos auditables. `poll_once` intenta primero una correlación
operacional determinística por `In-Reply-To`, `References` o UUID persistido en
el subject. Solo los mensajes no correlacionados continúan al intake ciudadano;
ni sender ni Gmail `threadId` deciden identidad técnica. La correlación RFC
consulta todos los routings, incluidos niveles históricos: una respuesta tardía
N1 continúa perteneciendo a N1 aunque ya exista N2.

Los nuevos emails incluyen un token estable `[R:<routing_key>]`. Si faltan
headers RFC, Flow combina ese token con el UUID del request. Un subject que
contiene solamente el request UUID se acepta únicamente cuando existe un solo
routing `ASSIGNED`; con múltiples niveles queda deliberadamente sin correlación.

El contenido correlacionado se interpreta mediante LiteLLM y el alias
`openai_gpt-5.4-nano`. `ACK_OR_PROGRESS` cambia el estado operacional de
`ASSIGNED` a `IN_PROGRESS`; `AMBIGUOUS`, `UNRELATED` y
`UNSUPPORTED_OPERATIONAL_ACTION` se auditan sin transición. El timestamp
`first_response_at_utc` usa `InboundMessage.received_at`, queda inmutable y se
persiste independientemente para cada `routing_id`.
El mismo mecanismo opera sobre N1, N2 y N3: el RFC observado o el token del
routing seleccionan el nivel concreto aunque todos los aliases lleguen al mismo
buzón físico. Un N3 sin política SLA puede registrar respuesta e IN_PROGRESS
sin crear un snapshot SLA como efecto colateral.

## SLA de primera respuesta por routing

La migración `014_team360_flow_n1_first_response_sla_v1.sql` configura el SLA
en segundos por nivel y crea un snapshot inmutable al asignar. Para Alumbrado
N1 la duración inicial es 30 segundos. El snapshot usa `assigned_at_utc` como
inicio y persiste `due_at_utc`; no vuelve a consultar el catálogo al evaluar.
La migración `016_team360_flow_n2_first_response_sla_v1.sql` habilita la misma
política de 30 segundos para nuevos routings Alumbrado N2. No backfillea N2
históricos: cada SLA conserva la política vigente cuando su routing pasó a
`ASSIGNED`.
La migración `018_team360_flow_n3_first_response_sla_v1.sql` configura también
Alumbrado N3 en 30 segundos. El runtime no distingue niveles: cada routing nuevo
consulta la política de su `sector_level_id`, crea como máximo un snapshot
FIRST_RESPONSE y luego se evalúa por su propio `routing_id`. Los N3 creados
cuando la política era nula permanecen sin SLA.

```bash
uv run python -m modules.flow.check_sla_once
```

El checker finito clasifica `PENDING`, `MET` o `BREACHED` sin IA ni efectos
externos. Una respuesta exactamente en `due_at_utc` cumple. Un breach
provisional puede reconciliarse a MET si luego se procesa evidencia Gmail cuyo
`received_at` real era anterior o igual al vencimiento; una respuesta realmente
tardía conserva BREACHED aunque el trabajo pase a IN_PROGRESS.

## Escalamiento al siguiente nivel activo

La migración `015_team360_flow_n1_to_n2_escalation_v1.sql` hace que el estado
operacional pertenezca al routing concreto, agrega el catálogo Alumbrado N2 y
audita la relación entre el SLA N1 vencido y el nuevo routing N2. N1 conserva
su email, work state y SLA; con la migración 016, un nuevo N2 `ASSIGNED` crea su
propio snapshot FIRST_RESPONSE mediante el mismo método por `routing_id`.
La migración `017_team360_flow_n2_to_n3_escalation_v1.sql` agrega Alumbrado N3
sin SLA y habilita el mismo servicio para resolver el menor nivel activo mayor
al routing vencido. No existen rutas de código separadas N1→N2 o N2→N3.

```bash
# inspección, sin escrituras ni email
uv run python -m modules.flow.escalate_once

# sincroniza replies, reconcilia SLA y recién después permite el envío
uv run python -m modules.flow.escalate_once \
  --account mesaentrada@alquimiablue.com \
  --confirm-send
```

El comando es dry-run por defecto. Antes del envío real procesa evidencia
operacional, ejecuta el checker SLA y vuelve a bloquear/releer el breach. Una
respuesta recibida a tiempo impide el escalamiento aunque el SLA hubiese sido
marcado provisionalmente como BREACHED. La unicidad por SLA disparador y por
`request_id + routing_key` evita duplicar escalamiento, routing o email.
El destino, canal y política SLA salen del catálogo del nivel resuelto; niveles
inactivos se omiten. Así, un request puede conservar N1 y N2 BREACHED mientras
N3 queda ASSIGNED con su work state y snapshot SLA propios. Si N3 vence, la
ausencia de un nivel activo posterior deja el breach persistido como fin normal
de la cadena actual: el escalador no crea N4 ni envía otro email.

## Consulta ejecutiva de casos (Director)

Requiere la migración `019_team360_flow_supervisor_closure_audit_v1.sql` y el
cierre con aprobación de supervisor. El servicio `executive_service.py` es de
solo lectura: no muta el workflow, no crea mensajes, routings, eventos ni audit
records.

- `data_source = AUDIT_SNAPSHOT` para casos `RESOLVED` con registro en
  `flow_case_audit_records` (representación inmutable del cierre);
- `data_source = LIVE` para casos abiertos, construida desde las tablas
  operacionales; no se fabrican audit records para casos abiertos;
- contrato: request, routing_history, sla, escalations, operational_events,
  resolution, closure_approval, result, metrics, timeline, audit y el hecho
  operacional determinístico `status_fact` (closed/open/pending_approval);
- trazabilidad: routing:<id>, sla:<id>, event:<id>, resolution:<id>,
  approval:<id>, audit:<id>;
- LLM: LiteLLM `openai_gpt-5.4-nano`, recibe únicamente los hechos
  estructurados y reglas que prohíben inventar eventos/estados y contradicen
  `status_fact`.

CLI:

```bash
uv run python -m modules.flow.executive_query_once <request-id> \
  --question "¿Qué pasó con el reclamo?"
```

Ruta HTTP autenticada con PASETO console:

```text
GET /api/team360-flow/executive/{request_id}?question=...
```

## Executive Query Authorization

La ruta HTTP separa AUTHENTICATION de AUTHORIZATION:

- autenticación: PASETO `console_access` demuestra identidad (401 si falta o es
  inválido);
- autorización: capability persistente `flow.executive.read`, resuelta por el
  RBAC existente (`core_permissions` + `list_effective_permissions`) mediante
  `executive_auth.py` (403 si el usuario autenticado no la tiene);
- fail closed: sin capability explícita → DENY; el dominio `@alquimiablue.com`
  no otorga acceso Directorio;
- el 403 se emite antes de cualquier acceso a datos o al LLM, y también para
  request_ids inexistentes (evita enumeración); el 404 solo llega a usuarios
  autorizados;
- el servicio interno (`executive_service.py`) y el CLI
  `executive_query_once.py` siguen funcionando sin transporte HTTP.

## Límites V1

La demo no incluye N4, escalamiento N3→N4, delegación, reopen, ciudadano
aprobando cierre, PDF, Excel, BI, WhatsApp, Pub/Sub, multiworker, cron, systemd
ni daemon externo. Sí incluye frontend Directorio, Configuración y scheduler
embebido single-process.

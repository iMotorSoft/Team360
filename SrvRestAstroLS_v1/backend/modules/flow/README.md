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

Las migraciones Flow continúan siendo `GLOBAL` por pertenecer al historial aplicado de PostgreSQL. Flow todavía no expone `routes.py` ni está registrado en el module registry; esa alta inicial requerirá una ventana GLOBAL separada.

## Ejecución manual

Requiere la migración `011_team360_flow_email_intake_v1.sql`, PostgreSQL,
LiteLLM y la configuración externa existente de Gmail DWD.

```bash
uv run python -m modules.flow.poll_once \
  --account mesaentrada@alquimiablue.com \
  --query 'in:inbox' \
  --limit 25
```

El ciclo termina luego de listar, normalizar y procesar el lote. No marca
mensajes como leídos y no usa `UNREAD` como control. La idempotencia persistente
usa `provider + external_message_id`.

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

## Límites V1

No incluye N4, escalamiento N3→N4, delegación, resolución, frontend, WhatsApp,
Pub/Sub, scheduler ni daemon.

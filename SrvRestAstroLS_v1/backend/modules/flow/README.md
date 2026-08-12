# Team360 Flow email intake, routing y respuesta operacional N1 V1

Este módulo contiene la lógica de negocio del intake por email. Recibe
`InboundMessage` normalizados por Messaging, interpreta solicitudes mediante el
adapter LiteLLM existente, solicita confirmación humana y crea registros
`flow_requests` únicamente después de una confirmación inequívoca.

El routing consume esa frontera `CONFIRMED`, resuelve la categoría tentativa
mediante un mapping determinístico y valida el sector/destino contra el catálogo
PostgreSQL. El estado de la solicitud no cambia: la asignación conserva su
propio estado en `flow_request_routings`, lo que desacopla intake de routing.

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

## Respuesta operacional Nivel 1

La migración `013_team360_flow_n1_operational_reply_v1.sql` agrega estado de
trabajo y eventos auditables. `poll_once` intenta primero una correlación
operacional determinística por `In-Reply-To`, `References` o UUID persistido en
el subject. Solo los mensajes no correlacionados continúan al intake ciudadano;
ni sender ni Gmail `threadId` deciden identidad técnica.

El contenido correlacionado se interpreta mediante LiteLLM y el alias
`openai_gpt-5.4-nano`. `ACK_OR_PROGRESS` cambia el estado operacional de
`ASSIGNED` a `IN_PROGRESS`; `AMBIGUOUS`, `UNRELATED` y
`UNSUPPORTED_OPERATIONAL_ACTION` se auditan sin transición. El timestamp
`first_response_at_utc` usa `InboundMessage.received_at` y queda inmutable.

## SLA de primera respuesta N1

La migración `014_team360_flow_n1_first_response_sla_v1.sql` configura el SLA
en segundos por nivel y crea un snapshot inmutable al asignar. Para Alumbrado
N1 la duración inicial es 30 segundos. El snapshot usa `assigned_at_utc` como
inicio y persiste `due_at_utc`; no vuelve a consultar el catálogo al evaluar.

```bash
uv run python -m modules.flow.check_sla_once
```

El checker finito clasifica `PENDING`, `MET` o `BREACHED` sin IA ni efectos
externos. Una respuesta exactamente en `due_at_utc` cumple. Un breach
provisional puede reconciliarse a MET si luego se procesa evidencia Gmail cuyo
`received_at` real era anterior o igual al vencimiento; una respuesta realmente
tardía conserva BREACHED aunque el trabajo pase a IN_PROGRESS.

## Límites V1

No incluye Nivel 2/3, escalamiento, envío a supervisor, delegación, resolución,
frontend, WhatsApp, Pub/Sub ni daemon permanente.

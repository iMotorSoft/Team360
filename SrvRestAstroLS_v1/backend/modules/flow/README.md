# Team360 Flow email intake V1

Este módulo contiene la lógica de negocio del intake por email. Recibe
`InboundMessage` normalizados por Messaging, interpreta solicitudes mediante el
adapter LiteLLM existente, solicita confirmación humana y crea registros
`flow_requests` únicamente después de una confirmación inequívoca.

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

## Límites V1

No incluye routing, sectores, SLA, niveles, escalamiento, frontend, WhatsApp,
Pub/Sub ni daemon permanente.

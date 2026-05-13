# Team360 - Arquitectura Multi WhatsApp y Multi LLM

## 1. Resumen ejecutivo

- Vertice360 ya tiene piezas reales para WhatsApp Meta/Gupshup, webhooks, mappers, pruebas, AG-UI/SSE y demos operativas.
- Esas piezas sirven para Team360 como patrones y adaptadores base, no como copia directa de arquitectura.
- El mayor riesgo observado es que Vertice360 configura proveedor, numero y modelo LLM desde variables globales de proceso.
- Team360 actual todavia es mayormente estructura base: no tiene backend Litestar funcional, DB runtime, registry productivo de providers, SSE real ni multi-tenant persistido.
- Team360 no debe modelar "un WhatsApp global"; debe modelar canales por workspace, area, provider, numero y credencial.
- El numero WhatsApp debe ser una entidad versionable y reemplazable, no identidad del cliente ni del provider.
- OpenAI/OpenRouter deben resolverse por politica de workspace y automatizacion, nunca desde una unica key global obligatoria.
- Las credenciales deben vivir en secret manager o cifradas con referencia segura; el frontend no debe recibir claves.
- Los webhooks deben resolver workspace/canal/numero desde metadata del provider, no desde rutas hardcodeadas por demo.
- Scheduler, Local Runner, WhatsApp y LLM deben compartir `workspace_id`, `task_run_id`, `workflow_run_id`, `channel_id`, `number_id`, `llm_provider_id` y `correlation_id`.
- El LAB debe contener pruebas de providers, browser automation y probes; produccion debe contener solo adaptadores, registries, tablas y rutas estabilizadas.

## 2. Observado en Vertice360

### Observado en repo

- Backend Litestar demo/productivo:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/ls_iMotorSoft_Srv01.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/ls_iMotorSoft_Srv01_demo.py`
- Configuracion global:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/globalVar.py`
  - Observado: `OpenAI_Key`, `OpenAI_Model`, Meta WhatsApp y Gupshup se resuelven desde env vars globales.
- Meta WhatsApp:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/meta/whatsapp/client.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/meta/whatsapp/service.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/meta/whatsapp/mapper.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/routes/messaging.py`
- Gupshup WhatsApp:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/client.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/service.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/mapper.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/signature.py`
- Provider registry:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/registry.py`
  - Observado: normaliza `meta` y `gupshup`, pero no es registry multi-workspace ni multi-numero.
- AG-UI/SSE:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/broadcaster.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/routes.py`
  - Observado: broadcaster en memoria, handshake, keep-alive, cola por subscriber y eventos `CUSTOM`.
- Eventos/workflow:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_workflow_demo/events.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_workflow_demo/store.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_workflow_demo/services.py`
  - Observado: eventos tipo `ticket.created`, `ticket.updated`, `messaging.inbound`, `messaging.outbound`, timeline y dedupe, pero acoplados a demo inmobiliaria.
- AI workflow:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/events.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/store.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/langgraph_flow.py`
- Telemetry:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/telemetry/context.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/telemetry/logging.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/middleware/telemetry_middleware.py`
- Frontend Astro/Svelte:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/shared/sse.js`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/shared/http.js`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/components/demo/messaging/providers/meta/whatsapp/MetaWhatsAppLab.svelte`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/components/demo/messaging/providers/gupshup/whatsapp/GupshupWhatsAppLab.svelte`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/vertice360_workflow/ui/LiveEventLog.svelte`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/vertice360_workflow/ui/Inbox.svelte`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/vertice360_workflow/ui/TicketDrawer.svelte`
- Pruebas relevantes:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_meta_whatsapp_mapper.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_gupshup_whatsapp_mapper.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_gupshup_webhook_filters.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_demo_whatsapp_unified_send.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_inbound_idempotency.py`

### Hallazgos sobre rigidez

- Meta esta atado a env vars globales como `META_VERTICE360_WABA_TOKEN`, `META_VERTICE360_WABA_ID`, `META_VERTICE360_PHONE_NUMBER_ID`, `META_VERTICE360_VERIFY_TOKEN`, `META_APP_SECRET_IMOTORSOFT` y `META_GRAPH_VERSION` en `backend/globalVar.py`.
- Gupshup esta atado a env vars globales por ambiente como `GUPSHUP_APP_NAME_DEV/STG/PRO`, `GUPSHUP_API_KEY_DEV/STG/PRO`, `GUPSHUP_SRC_NUMBER_DEV/STG/PRO`, `GUPSHUP_BASE_URL_DEV/STG/PRO`, `GUPSHUP_WA_SENDER` y `GUPSHUP_SRC_NUMBER`.
- OpenAI esta atado a `VERTICE360_OPENAI_KEY` u `OPENAI_API_KEY`, y a `VERTICE360_OPENAI_MODEL` con default `gpt-4o-mini`.
- OpenRouter: no encontrado en la inspeccion por texto.
- Hay archivos sensibles o de notas internas que no deben copiarse ni versionarse como fuente de verdad:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/temp1.txt`
  - No se copiaron ni se transcriben secretos.

## 3. Observado en Team360

### Observado en repo

- Backend actual:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/ls_iMotorSoft_Srv01.py`
  - Observado: entrypoint placeholder, no app Litestar productiva.
- Configuracion:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/globalVar.py`
  - Observado: contiene config basica de servicio, SSE placeholder y soporte futuro opcional para OpenAI/pgvector.
- OpenAI en Team360:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/globalVar.py`
  - Observado: `FUTURE_OPTIONAL_OPENAI_API_KEY` lee `TEAM360_OPENAI_KEY`, `OPENAI_API_KEY` o `VERTICE360_OPENAI_KEY`; no es runtime LLM multi-workspace.
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/scripts/sync_v360_catalog_to_team360.py`
  - Observado: usa OpenAI solo para embeddings opcionales de catalogo futuro.
- OpenRouter en Team360: no encontrado.
- AG-UI/SSE:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/routes/agui.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/agui_stream/README.md`
  - Observado: reservado/placeholder, sin broadcaster funcional.
- Orquestador:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/team360_orquestador/README.md`
  - Observado: estructura intencional, sin runtime productivo.
- Messaging/Gupshup:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/README.md`
  - Observado: carpetas base, no adaptador funcional.
- Mercado Libre LAB/local browser automation:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/actions.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/context.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/session_store.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/probes/smoke_login.py`
  - Observado: es la pieza mas concreta actual de Team360 para LAB/local automation, con perfil persistente y login humano.
- Local Runner productivo:
  - `backend/modules/local_runner/`: no encontrado.
  - `backend/modules/lab/`: no encontrado como modulo formal general; existe LAB de Mercado Libre dentro de provider.
- Frontend:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/astro/src/README.md`
  - Observado: estructura inicial, no UI operativa.
- DB:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/db/team360_pgvector_catalog.sql`
  - Observado: futuro opcional, no runtime de conversaciones/tareas/providers.
- Archivo sensible:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/temp1.txt`
  - Observado: contiene notas sensibles. No se transcriben valores. Debe retirarse o moverse fuera del repo y rotar cualquier secreto que haya sido expuesto.

## 4. Problema de diseño: multi-numero WhatsApp

### Observado en repo

- Vertice360 resuelve Meta y Gupshup desde configuracion global de proceso.
- Vertice360 permite elegir provider en endpoints demo, pero no modela multiples numeros por workspace, area o cliente.
- Team360 no tiene todavia modelo productivo de canales, numeros, threads, eventos o credenciales.

### Propuesto

Team360 debe tratar WhatsApp como una red de canales configurables por workspace:

- `workspace` es el cliente/tenant.
- `communication_provider` es Meta, Gupshup u otro proveedor.
- `communication_channel` es el canal operativo dentro del workspace, por ejemplo `administracion`, `ventas`, `cobranzas` o `soporte`.
- `whatsapp_number` es una identidad tecnica versionable asociada al canal y al provider.
- `provider_credentials` es el secreto o referencia a secreto que permite operar con el provider.
- `message_thread` conserva la historia funcional de la conversacion aunque el numero cambie.

Regla de arquitectura:

- Numero != cliente.
- Numero != provider.
- Numero = canal configurable dentro de un workspace.

Esto evita cirugias tecnicas ante:

- Alta de un segundo numero por area.
- Cambio de numero.
- Provider nuevo.
- Desactivacion de numero anterior con trazabilidad.
- Migracion de reglas desde numero viejo a nuevo.

## 5. Arquitectura propuesta para WhatsApp Channels

### Propuesto

Separar resolucion de canal en cuatro capas:

1. Provider fisico: Meta WhatsApp Cloud API, Gupshup, futuro provider.
2. Credencial: platform-owned o workspace-owned, por ambiente y scope.
3. Numero: telefono real, estado, provider phone id/app name, verificacion y reemplazos.
4. Canal operativo: alias estable usado por producto, reglas y automatizaciones.

Ejemplos:

- `workspace=cliente_a`, `channel_alias=administracion`, `department=administracion`, `provider=gupshup`, `phone=+1 438 619 6686`.
- `workspace=cliente_a`, `channel_alias=ventas`, `department=ventas`, `provider=meta`, `phone=+54 ...`.

El codigo de negocio no deberia llamar `send_whatsapp(to, text, provider="gupshup")`. Deberia pedir:

- `send_message(workspace_id, channel_alias="administracion", contact_id, text, correlation_id)`.

El resolver interno decide:

- canal activo;
- numero activo;
- provider;
- credencial;
- adapter;
- idempotency key;
- evento y auditoria.

### Productivo vs LAB

- Productivo:
  - registry de providers;
  - tablas de channels/numeros/credenciales;
  - webhooks verificados;
  - outbound con idempotencia;
  - audit logs;
  - eventos AG-UI/SSE.
- LAB:
  - pruebas manuales de alta de numero;
  - simuladores de webhook;
  - pruebas de providers nuevos;
  - experimentos con payloads no normalizados;
  - probes contra Meta/Gupshup antes de promocion.

## 6. Cambio de numero WhatsApp: flujo recomendado

### Ejemplo requerido

- antiguo: `+45 26 32 52 50`
- nuevo: `+1 438 619 6686`

### Propuesto

1. Crear `whatsapp_numbers` para el numero nuevo con estado `testing`.
2. Asociarlo al mismo `communication_channel` del numero anterior, pero sin hacerlo default.
3. Crear o verificar `webhook_binding` del nuevo numero.
4. Ejecutar prueba inbound:
   - verificar que provider payload resuelve `workspace_id`, `channel_id`, `number_id`.
   - emitir `whatsapp.number.test_inbound.succeeded` o `whatsapp.number.test_inbound.failed`.
5. Ejecutar prueba outbound:
   - enviar mensaje controlado desde el nuevo numero.
   - registrar `provider_message_id`.
6. Copiar o migrar `channel_routing_rules` desde el numero anterior al nuevo.
7. Crear `migration_history` con:
   - `old_number_id`;
   - `new_number_id`;
   - politica de threads;
   - usuario que aprobo;
   - timestamps UTC.
8. Activar el numero nuevo como `current_whatsapp_number_id` del canal.
9. Marcar el numero anterior como `retired` o `inactive`, nunca borrarlo.
10. Mantener `message_threads` historicos vinculados al numero anterior, pero permitir continuidad funcional por `contact_identity` y `channel_id`.

### Conservacion de historial

- `message_threads.channel_id` debe mantenerse estable.
- `message_events.number_id` debe registrar el numero exacto usado en cada evento.
- El cambio de numero no debe reescribir eventos viejos.
- Si se necesita continuar una conversacion con el mismo contacto, se crea un nuevo evento con `new_number_id` dentro del mismo thread o se abre un thread nuevo vinculado por `previous_thread_id`, segun politica del workspace.

## 7. Entidades/tablas sugeridas para WhatsApp

### Propuesto

`communication_providers`

- `id`
- `code`: `meta_whatsapp`, `gupshup_whatsapp`, futuro provider
- `display_name`
- `provider_type`: `whatsapp`, `marketplace`, `email`, etc.
- `status`
- `capabilities_jsonb`
- `created_at_utc`

`provider_credentials`

- `id`
- `workspace_id` nullable para credencial de plataforma
- `provider_id`
- `scope`: `platform`, `workspace`, `channel`
- `environment`: `dev`, `stg`, `pro`
- `secret_ref` o valor cifrado, nunca secreto plano
- `public_config_jsonb`: Graph version, base URL, app name no secreto
- `status`
- `rotated_at_utc`
- `created_at_utc`

`communication_channels`

- `id`
- `workspace_id`
- `provider_id`
- `channel_type`: `whatsapp`
- `channel_alias`: `ventas`, `proveedores`, `cobranzas`, `soporte`, `administracion`, `operaciones`
- `department`
- `display_name`
- `status`: `testing`, `active`, `paused`, `retired`
- `current_whatsapp_number_id`
- `default_for_department`
- `created_at_utc`

`whatsapp_numbers`

- `id`
- `workspace_id`
- `provider_id`
- `channel_id`
- `phone_e164`
- `phone_display`
- `provider_phone_number_id`: Meta `phone_number_id` o equivalente
- `provider_business_id`: Meta WABA id, Gupshup app name u otro
- `credential_id`
- `phone_number_status`: `provisioning`, `testing`, `active`, `paused`, `retired`, `failed`
- `verification_status`: `pending`, `verified`, `failed`, `expired`
- `activated_at_utc`
- `retired_at_utc`
- `replaced_by_number_id`
- `metadata_jsonb`

`webhook_bindings`

- `id`
- `workspace_id`
- `provider_id`
- `channel_id`
- `whatsapp_number_id`
- `webhook_url`
- `verify_token_ref`
- `signing_secret_ref`
- `provider_external_id`
- `status`
- `last_verified_at_utc`

`channel_routing_rules`

- `id`
- `workspace_id`
- `channel_id`
- `rule_type`: `provider_number`, `department`, `keyword`, `default`, `automation`
- `match_value`
- `priority`
- `active_from_utc`
- `active_to_utc`
- `status`

`message_threads`

- `id`
- `workspace_id`
- `channel_id`
- `contact_identity`
- `current_status`
- `started_at_utc`
- `last_message_at_utc`
- `previous_thread_id`
- `metadata_jsonb`

`message_events`

- `id`
- `workspace_id`
- `thread_id`
- `channel_id`
- `whatsapp_number_id`
- `provider_id`
- `provider_message_id`
- `direction`: `inbound`, `outbound`
- `event_type`: `message`, `status`, `error`, `system`
- `payload_jsonb`
- `occurred_at_utc`
- `correlation_id`

`whatsapp_number_migration_history`

- `id`
- `workspace_id`
- `channel_id`
- `old_whatsapp_number_id`
- `new_whatsapp_number_id`
- `migration_policy_jsonb`
- `migrated_by_user_id`
- `started_at_utc`
- `completed_at_utc`
- `status`
- `notes`

## 8. Endpoints sugeridos para administracion WhatsApp

### Propuesto

- `GET /api/admin/workspaces/{workspace_id}/communication/providers`
- `POST /api/admin/workspaces/{workspace_id}/communication/providers`
- `GET /api/admin/workspaces/{workspace_id}/communication/channels`
- `POST /api/admin/workspaces/{workspace_id}/communication/channels`
- `PATCH /api/admin/workspaces/{workspace_id}/communication/channels/{channel_id}`
- `GET /api/admin/workspaces/{workspace_id}/whatsapp/numbers`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers`
- `PATCH /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{number_id}`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{number_id}/verify`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{number_id}/test-inbound`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{number_id}/test-outbound`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{number_id}/activate`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{number_id}/retire`
- `POST /api/admin/workspaces/{workspace_id}/whatsapp/numbers/{old_number_id}/migrate`
- `GET /api/admin/workspaces/{workspace_id}/channel-routing-rules`
- `POST /api/admin/workspaces/{workspace_id}/channel-routing-rules`
- `PATCH /api/admin/workspaces/{workspace_id}/channel-routing-rules/{rule_id}`
- `GET /api/admin/workspaces/{workspace_id}/message-threads`
- `GET /api/admin/workspaces/{workspace_id}/message-threads/{thread_id}/events`

Webhooks productivos sugeridos:

- `GET /webhooks/messaging/meta/whatsapp`
- `POST /webhooks/messaging/meta/whatsapp`
- `POST /webhooks/messaging/gupshup/whatsapp`

Nota propuesta: conservar rutas por provider para compatibilidad, pero resolver workspace/canal/numero desde payload, firma y `webhook_bindings`, no desde globalVar.

## 9. Eventos AG-UI/SSE sugeridos para WhatsApp

### Propuesto

Eventos de configuracion:

- `communication.channel.created`
- `communication.channel.updated`
- `communication.channel.paused`
- `communication.channel.retired`
- `webhook.binding.verified`
- `webhook.binding.failed`

Eventos de numero:

- `whatsapp.number.created`
- `whatsapp.number.verification.started`
- `whatsapp.number.verification.succeeded`
- `whatsapp.number.verification.failed`
- `whatsapp.number.activated`
- `whatsapp.number.retired`
- `whatsapp.number.migration.started`
- `whatsapp.number.migration.completed`
- `whatsapp.number.migration.failed`

Eventos de mensajeria:

- `messaging.inbound`
- `messaging.outbound.requested`
- `messaging.outbound.sent`
- `messaging.outbound.failed`
- `messaging.status`
- `messaging.routing.matched`
- `messaging.routing.missed`

Envelope recomendado:

- `type`: `CUSTOM`
- `name`: nombre del evento
- `timestamp`: UTC ISO
- `correlationId`: `message_event_id`, `thread_id`, `task_run_id` o `migration_id`
- `value.workspaceId`
- `value.channelId`
- `value.whatsappNumberId`
- `value.providerId`
- `value.threadId`
- `value.status`

## 10. Problema de diseño: multi-LLM OpenAI/OpenRouter

### Observado en repo

- Vertice360 configura OpenAI desde `backend/globalVar.py` con `OpenAI_Key` y `OpenAI_Model`.
- Vertice360 contiene flujos AI/workflow y pruebas, pero no se observo registry multi-LLM productivo.
- OpenRouter no encontrado en Vertice360.
- Team360 solo tiene OpenAI como soporte futuro opcional en `backend/globalVar.py` y en script de embeddings opcionales.
- OpenRouter no encontrado en Team360.

### Propuesto

Team360 debe separar:

- provider LLM;
- credencial;
- modelo;
- perfil de modelo;
- politica de workspace;
- politica por automatizacion;
- fallback;
- auditoria de uso/costo.

El codigo de automatizacion no deberia llamar directamente a `OpenAI(api_key=...)`. Deberia pedir una resolucion:

- `resolve_llm_policy(workspace_id, automation_key, environment)`.

Esa resolucion devuelve:

- provider primario;
- modelo primario;
- credencial aplicable;
- scope de key;
- fallbacks permitidos;
- limites;
- trazabilidad para `llm_usage_logs`.

## 11. Arquitectura propuesta para LLM Providers

### Propuesto

Soportar cuatro modos desde el inicio:

- OpenAI con key global de plataforma.
- OpenAI con key propia del workspace.
- OpenRouter con key global de plataforma.
- OpenRouter con key propia del workspace.

Reglas:

- La plataforma puede proveer defaults por ambiente.
- El workspace puede traer su propia key.
- La automatizacion puede pedir un perfil especifico.
- El fallback debe estar declarado, no improvisado en catch blocks.
- El frontend nunca ve claves ni headers de providers.
- Los costos se registran por workspace, task run, workflow run, automation y modelo.

Resolucion recomendada:

1. Buscar `automation_llm_policy` activa para `workspace_id + automation_key`.
2. Si no existe, usar `workspace_llm_settings.default_model_profile_id`.
3. Resolver credencial segun `llm_key_scope`:
   - `workspace_first`;
   - `platform_first`;
   - `workspace_only`;
   - `platform_only`.
4. Validar limites y seguridad.
5. Ejecutar request.
6. Registrar `llm_usage_logs`.
7. Si falla por condicion habilitada, aplicar `llm_fallback_policy`.

## 12. Entidades/tablas sugeridas para LLM

### Propuesto

`llm_providers`

- `id`
- `code`: `openai`, `openrouter`
- `display_name`
- `base_url`
- `auth_type`
- `status`
- `capabilities_jsonb`
- `created_at_utc`

`llm_credentials`

- `id`
- `workspace_id` nullable para key de plataforma
- `provider_id`
- `scope`: `platform`, `workspace`
- `environment`: `dev`, `stg`, `pro`
- `secret_ref` o valor cifrado
- `status`
- `created_by_user_id`
- `rotated_at_utc`
- `created_at_utc`

`llm_model_profiles`

- `id`
- `provider_id`
- `model_id`: por ejemplo `gpt-4o-mini` u OpenRouter model slug
- `display_name`
- `model_capabilities`: chat, tools, vision, json_schema, embeddings
- `context_window`
- `input_cost_per_million`
- `output_cost_per_million`
- `currency`
- `latency_class`
- `enabled`
- `metadata_jsonb`

`workspace_llm_settings`

- `id`
- `workspace_id`
- `default_model_profile_id`
- `fallback_policy_id`
- `key_scope_preference`
- `monthly_budget_limit`
- `daily_budget_limit`
- `safety_policy_jsonb`
- `data_retention_policy`
- `updated_at_utc`

`automation_llm_policy`

- `id`
- `workspace_id`
- `automation_key`
- `primary_model_profile_id`
- `fallback_policy_id`
- `credential_scope_preference`
- `max_tokens`
- `temperature`
- `timeout_ms`
- `retry_policy_jsonb`
- `enabled`

`llm_fallback_policy`

- `id`
- `workspace_id` nullable para policy global
- `name`
- `ordered_model_profile_ids`
- `fallback_on_error_codes`
- `max_attempts`
- `cooldown_seconds`
- `enabled`

`llm_usage_logs`

- `id`
- `workspace_id`
- `automation_key`
- `task_run_id`
- `workflow_run_id`
- `provider_id`
- `model_profile_id`
- `credential_scope`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `estimated_cost`
- `currency`
- `latency_ms`
- `status`
- `error_code`
- `correlation_id`
- `created_at_utc`

`llm_cost_estimates`

- `id`
- `provider_id`
- `model_id`
- `currency`
- `input_cost_per_million`
- `output_cost_per_million`
- `effective_from_utc`
- `effective_to_utc`

## 13. Endpoints sugeridos para administracion LLM

### Propuesto

- `GET /api/admin/llm/providers`
- `POST /api/admin/llm/providers`
- `GET /api/admin/llm/model-profiles`
- `POST /api/admin/llm/model-profiles`
- `PATCH /api/admin/llm/model-profiles/{profile_id}`
- `GET /api/admin/workspaces/{workspace_id}/llm/credentials`
- `POST /api/admin/workspaces/{workspace_id}/llm/credentials`
- `POST /api/admin/workspaces/{workspace_id}/llm/credentials/{credential_id}/test`
- `POST /api/admin/workspaces/{workspace_id}/llm/credentials/{credential_id}/rotate`
- `GET /api/admin/workspaces/{workspace_id}/llm/settings`
- `PATCH /api/admin/workspaces/{workspace_id}/llm/settings`
- `GET /api/admin/workspaces/{workspace_id}/automations/{automation_key}/llm-policy`
- `PUT /api/admin/workspaces/{workspace_id}/automations/{automation_key}/llm-policy`
- `GET /api/admin/workspaces/{workspace_id}/llm/usage`
- `GET /api/admin/workspaces/{workspace_id}/llm/costs`

Endpoint interno sugerido:

- `POST /api/internal/workspaces/{workspace_id}/llm/resolve`

Nota: el endpoint interno no debe exponer secretos; solo devuelve una decision de ejecucion al backend autorizado o ejecuta la llamada server-side.

## 14. Eventos AG-UI/SSE sugeridos para LLM

### Propuesto

Eventos de configuracion:

- `llm.provider.enabled`
- `llm.provider.disabled`
- `llm.credential.created`
- `llm.credential.tested`
- `llm.credential.failed`
- `llm.credential.rotated`
- `llm.policy.updated`

Eventos de ejecucion:

- `llm.request.started`
- `llm.request.completed`
- `llm.request.failed`
- `llm.fallback.started`
- `llm.fallback.succeeded`
- `llm.fallback.failed`
- `llm.usage.logged`
- `llm.budget.threshold_reached`
- `llm.budget.exceeded`

Envelope recomendado:

- `type`: `CUSTOM`
- `name`: nombre del evento
- `timestamp`: UTC ISO
- `correlationId`: `task_run_id`, `workflow_run_id` o `llm_usage_log_id`
- `value.workspaceId`
- `value.providerId`
- `value.modelProfileId`
- `value.credentialScope`
- `value.automationKey`
- `value.taskRunId`
- `value.workflowRunId`
- `value.estimatedCost`
- `value.status`

## 15. Integracion con Scheduler, Tasks y Local Runner

### Observado en repo

- Team360 no tiene `backend/modules/local_runner/` productivo.
- Team360 si tiene base concreta para browser automation local/lab en Mercado Libre:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/browser/`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/probes/`
- Scheduler central productivo: no encontrado.

### Propuesto

Para una tarea diaria que descarga extracto bancario con Local Runner, resume con LLM y envia por WhatsApp desde administracion:

1. Scheduler cloud crea `task_run` en UTC:
   - `workspace_id`
   - `scheduled_task_id`
   - `task_run_id`
   - `required_runner_capability=browser_automation`
   - `timezone` del workspace solo para calcular proxima ocurrencia, no para almacenar ejecucion.
2. Local Runner hace polling y toma lease:
   - `runner_id`
   - `lease_id`
   - `lease_expires_at_utc`
3. Runner ejecuta accion local:
   - no expone puerto entrante;
   - maneja sesion local;
   - pide login/2FA humano si hace falta;
   - sube resultado sanitizado.
4. Cloud procesa resultado:
   - resuelve `automation_llm_policy`;
   - selecciona OpenAI/OpenRouter;
   - registra `llm_usage_logs`.
5. Cloud envia WhatsApp:
   - resuelve `communication_channel` con `channel_alias=administracion`;
   - obtiene numero activo;
   - usa provider/credencial;
   - registra `message_events`.
6. AG-UI/SSE emite:
   - `task.run.started`;
   - `runner.heartbeat`;
   - `task.run.completed`;
   - `llm.request.completed`;
   - `messaging.outbound.sent`.

Campos minimos a preservar en eventos y logs:

- `workspace_id`
- `runner_id`
- `task_run_id`
- `workflow_run_id`
- `communication_channel_id`
- `whatsapp_number_id`
- `communication_provider_id`
- `llm_provider_id`
- `llm_model_profile_id`
- `llm_credential_scope`
- `estimated_cost`
- `correlation_id`

## 16. Seguridad, secretos y credenciales

### Observado en repo

- Vertice360 y Team360 contienen archivos `backend/temp1.txt` con material sensible o notas que no deben usarse como fuente de configuracion.
- Vertice360 usa env vars globales y `boot_log` con enmascarado en `backend/globalVar.py`.
- Gupshup signature en Vertice360 tiene stub/no implementacion completa:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/signature.py`
- Bird signature observado como stub inseguro:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/bird/signature.py`

### Propuesto

- Guardar secretos en secret manager o cifrados con `secret_ref`.
- No guardar claves bancarias en Team360 Cloud.
- Local Runner conserva secretos locales de bancos/sesion del navegador fuera de Cloud.
- Cloud solo recibe artefactos sanitizados, estados y resultados necesarios.
- El frontend nunca recibe API keys, tokens de WhatsApp, app secrets ni LLM keys.
- Webhook signature validation debe ser obligatoria por provider cuando el provider lo soporte.
- Logs deben redactionar:
  - access tokens;
  - API keys;
  - phone ids sensibles si aplica;
  - payloads bancarios;
  - prompts con datos sensibles.
- OpenRouter debe tener policy explicita por workspace porque puede rutear requests a terceros segun modelo.
- Rotar cualquier secreto que haya sido escrito en archivos dentro del repo.

## 17. Configuracion por ambiente dev/stg/pro

### Observado en repo

- Vertice360 maneja dev/stg/pro para Gupshup con env vars por ambiente en `backend/globalVar.py`.
- Team360 no tiene todavia modelo DB de configuracion por ambiente.

### Propuesto

Mantener en env/secret manager solo configuracion de plataforma:

- URL base del servicio;
- database URL;
- secret manager keys;
- claves platform-owned por ambiente si se decide operar modo plataforma;
- feature flags globales;
- CORS/origins.

Mover a DB por workspace:

- numeros WhatsApp;
- alias de canales;
- areas/departamentos;
- reglas de routing;
- provider credentials del workspace o referencias a secreto;
- webhook bindings;
- modelo LLM default;
- politicas por automatizacion;
- limites de uso/costo;
- fallback policy.

Cada fila sensible debe tener `environment` para evitar mezclar dev/stg/pro.

## 18. Que portar desde Vertice360

| Pieza | Ruta origen | Uso en Team360 | Accion | Riesgo |
|---|---|---|---|---|
| AG-UI broadcaster en memoria | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/broadcaster.py` | Base inicial para SSE cloud | Adaptar | En memoria no escala multi-instancia |
| Rutas AG-UI/SSE | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/routes.py` | Endpoint SSE, handshake, keep-alive | Adaptar | CORS y auth deben hacerse por Team360 |
| Mapper Meta WhatsApp | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/meta/whatsapp/mapper.py` | Normalizacion inbound/status | Copiar con adaptacion | Debe agregar resolucion de workspace/canal/numero |
| Client/service Meta | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/meta/whatsapp/client.py` | Adapter outbound | Adaptar | Hoy usa globalVar y unico phone id |
| Mapper Gupshup | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/mapper.py` | Normalizacion inbound/status | Copiar con adaptacion | Falta firma/verificacion fuerte |
| Client/service Gupshup | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/client.py` | Adapter outbound | Adaptar | Hoy usa app/source/api key global |
| Provider registry simple | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/registry.py` | Semilla de normalizacion | Extraer patron | No modela canales ni DB |
| Eventos workflow | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_workflow_demo/events.py` | Nombres/event envelope/timeline | Extraer patron | Dominio ticket/demo inmobiliario |
| Telemetry middleware/context | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/telemetry/` | Request/correlation ids | Adaptar | Integrar auth/workspace |
| SSE frontend helper | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/shared/sse.js` | Helper EventSource Team360 | Adaptar | URL global hardcodeada en Vertice360 |
| HTTP helper frontend | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/lib/shared/http.js` | Fetch wrapper | Adaptar | Revisar auth/errors Team360 |
| Provider labs UI | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/components/demo/messaging/providers/` | LAB Team360 providers | Referencia/adaptar | No llevar textos demo a producto |
| Tests Meta/Gupshup | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_meta_whatsapp_mapper.py` y `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/tests/test_gupshup_whatsapp_mapper.py` | Base de pruebas de adaptadores | Adaptar | Deben agregar multi-workspace |

## 19. Que NO portar o portar solo como referencia

### No portar directo

- Configuracion global de Meta/Gupshup/OpenAI desde `Vertice360/SrvRestAstroLS_v1/backend/globalVar.py`.
- Endpoints demo como contrato productivo:
  - `/api/demo/messaging/whatsapp/send`
  - `/api/demo/messaging/meta/whatsapp/send`
  - `/api/demo/messaging/gupshup/whatsapp/send`
- Logica inmobiliaria de workflows:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_workflow_demo/services.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/langgraph_flow.py`
- Stores en memoria como persistencia productiva:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_workflow_demo/store.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/store.py`
- URLs frontend hardcodeadas:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/astro/src/components/global.js`
- Signature stubs sin hardening:
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/gupshup/whatsapp/signature.py`
  - `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/bird/signature.py`
- Archivos con secretos/notas sensibles:
  - `backend/temp1.txt` en ambos repos.

### Portar solo como referencia

- UI de workflow/tickets de Vertice360: util para patrones de Inbox, Drawer y Event Log, pero no para copiar dominio inmobiliario.
- DB schemas de seguimiento de visitas: pueden inspirar scheduler/state, pero estan atados a real estate.
- LangGraph/demo AI workflow: util como patron de estados y eventos, no como flujo Team360.

## 20. Gaps actuales de Team360

| Area | Estado actual | Gap | Prioridad | Accion recomendada |
|---|---|---|---|---|
| Backend Litestar | Placeholder en `backend/ls_iMotorSoft_Srv01.py` | No hay app productiva montando rutas reales | Alta | Crear app Litestar base con auth, workspace context y routers |
| AG-UI/SSE | Placeholder en `backend/routes/agui.py` y README | No hay broadcaster funcional | Alta | Adaptar broadcaster/rutas de Vertice360 con auth/workspace |
| WhatsApp providers | Estructura Gupshup vacia en Team360 | No hay adapters reales Meta/Gupshup | Alta | Portar mappers/adapters con registry multi-canal |
| Multi-numero | No encontrado | Falta modelo channels/numeros/routing | Alta | Crear entidades y migraciones antes de outbound productivo |
| Webhooks multi-numero | No encontrado | Falta resolver workspace/canal/numero por payload | Alta | Disenar `webhook_bindings` y normalizadores |
| Conversaciones/mensajes | No encontrado productivo | Falta `message_threads` y `message_events` | Alta | Modelar persistencia antes de UI inbox |
| OpenAI runtime | Solo futuro opcional en `globalVar.py` | No hay provider registry ni uso auditado | Alta | Crear `llm_*` tables y resolver server-side |
| OpenRouter | No encontrado | Falta adapter y policy | Media | Agregar como provider LLM desde el modelo inicial |
| Usage/cost LLM | No encontrado | Falta auditoria y budget | Alta | Crear `llm_usage_logs` desde primera integracion |
| Scheduler central | No encontrado | Falta task scheduler UTC/leases/retries | Alta | Modelar con `task_runs`, leases, idempotencia |
| Local Runner productivo | No encontrado | Solo hay LAB Mercado Libre/browser | Alta | Crear modulo separado de runner/polling |
| LAB formal | Parcial en Mercado Libre | Falta area LAB transversal | Media | Separar `backend/modules/lab/` o convención equivalente |
| Frontend operativo | README/base | No hay admin multi-canal ni LLM | Media | Portar patrones UI despues de backend contracts |
| Secret hygiene | `backend/temp1.txt` sensible | Riesgo de exposicion | Alta | Retirar del repo y rotar secretos expuestos |

## 21. Plan incremental de implementacion

### Fase 1

- Modelar `communication_providers`, `communication_channels`, `whatsapp_numbers`, `provider_credentials`, `webhook_bindings`.
- Modelar `llm_providers`, `llm_credentials`, `llm_model_profiles`, `workspace_llm_settings`.
- Limpiar dependencia conceptual de envs rigidos para numeros/modelos.
- Mantener envs solo para plataforma/dev bootstrap.
- Consolidar este documento como base de arquitectura.

### Fase 2

- Crear registry de WhatsApp channels server-side.
- Portar/adaptar mappers Meta/Gupshup desde Vertice360.
- Crear admin basico para numeros/canales.
- Implementar pruebas inbound/outbound controladas.
- Agregar eventos AG-UI/SSE para altas, pruebas y errores.

### Fase 3

- Implementar cambio de numero controlado.
- Agregar `whatsapp_number_migration_history`.
- Agregar `channel_routing_rules`.
- Conservar historial en `message_threads` y `message_events`.
- Probar caso `+45 26 32 52 50` a `+1 438 619 6686` sin reescribir historia.

### Fase 4

- Crear LLM provider registry.
- Implementar adapters OpenAI y OpenRouter.
- Agregar `workspace_llm_settings`.
- Agregar `automation_llm_policy`.
- Resolver modelo/credencial siempre server-side.

### Fase 5

- Implementar `llm_usage_logs` y costos estimados.
- Implementar `llm_fallback_policy`.
- Integrar LLM con `task_runs` y `workflow_runs`.
- Emitir eventos `llm.request.*`, `llm.fallback.*` y budget.

### Fase 6

- Construir UI operativa:
  - admin de canales/numeros;
  - pruebas inbound/outbound;
  - inbox/event log;
  - settings LLM por workspace;
  - usage/cost dashboard.
- Agregar auditoria completa.
- Hardening de firmas, secrets, redaction y permisos.
- Mantener Vertice360 como referencia, no dependencia runtime.

## 22. Recomendacion final

Team360 debe incorporar multi-numero WhatsApp y multi-LLM como primitivas fundacionales, no como features posteriores. Vertice360 aporta pruebas reales y codigo valioso para Meta, Gupshup, AG-UI/SSE, telemetry y UI operativa, pero su configuracion global por proceso no debe trasladarse al producto.

La linea tecnica recomendada es portar adaptadores y patrones, no arquitectura de demo: primero DB y resolvers por workspace, luego providers, despues UI. Esto permite que un workspace tenga varios numeros por area, cambie numeros sin perder trazabilidad, use OpenAI u OpenRouter con keys de plataforma o propias, y audite cada task run con canal, provider, numero, modelo, scope de credencial y costo estimado.

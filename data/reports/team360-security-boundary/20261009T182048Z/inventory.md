# Inventario de superficies

## A. Diagnosis DEV adapter

- Path/método: `POST /api/dev/sales-diagnosis-runtime/turn`.
- Handler: `routes/sales_diagnosis_runtime_dev.py::dev_sales_diagnosis_turn`.
- Montaje: directo en `ls_iMotorSoft_Srv01.create_app`; Srv05 reexporta la misma app/factory.
- Propósito real: adapter interno de desarrollo para runtime Diagnosis; fake retrieval/LLM y memoria por default. Permite opt-in PostgreSQL, Milvus y LiteLLM mediante variables DEV.
- Operaciones/side effects: un turno conversacional; puede persistir estado si se selecciona PostgreSQL y puede llamar LiteLLM/Milvus si se seleccionan explícitamente.
- Auth original: ninguna. Entorno original esperado: DEV según docstring/path, pero no existía guard; por eso `TEAM360_ENV=production` ejecutaba y respondía 201.
- Clasificación: `DEV_ONLY`.
- Contrato nuevo: sólo `TEAM360_ENV=dev|development` explícito. Production, ausente, vacío o desconocido → 404 antes de providers/estado. La ruta queda montada/documentada para conservar 28 operaciones y compatibilidad OpenAPI.

## B. Console bootstrap

- Path/método: `POST /api/console/bootstrap`.
- Handler: `routes/console_bootstrap.py::console_bootstrap`; montaje directo Srv01/Srv05.
- Request original: `workspace_id` y `user_id` elegidos por el caller; sin principal de entrada.
- Resolución: PostgreSQL valida workspace, membership, permisos, paquetes, capabilities, tareas y alertas.
- Token: PASETO v4.public opcional (`TEAM360_PASETO_ENABLED`), `typ=console_access`, `iss=team360`, `sub=user:<id>`, `user_id`, `iat`, `exp`, `jti`; TTL default 900 s. Keys desde entorno o par efímero DEV. El token no incorpora workspace/capabilities; éstos permanecen en el DTO.
- Uso frontend encontrado: no hay caller en `astro/src`; Console usa fixtures/mocks en los E2E actuales. El contrato histórico final exige una sesión previa Bearer y validación de workspace, aún no implementadas.
- Frontera previa original: ninguna dentro de la app; el endpoint experimental confiaba en IDs del body.
- Clasificación: `bootstrap de desarrollo`; era `bootstrap inseguro` si se habilitaba en production.
- Contrato nuevo: DEV-only con la misma condición explícita. Production/ausente/desconocido → 404 antes de DB/PASETO. El flujo DEV conserva claims, TTL y capabilities; no se cambió criptografía ni se creó otro auth.

## C. Gupshup webhook

- Path/método: `POST /webhooks/messaging/gupshup/whatsapp`.
- Controller: `modules/messaging/webhooks/gupshup_whatsapp.py::GupshupWhatsAppWebhookController`; montaje directo Srv01/Srv05.
- Contrato proveedor en repo: no documenta firma/HMAC Gupshup utilizable. El source anterior afirmaba que DEV no soportaba firma y dependía de tunnel, lo cual no autenticaba al sender.
- Procesamiento: JSON → clasificación status/message → normalización → claim PostgreSQL → bridge Flow sólo si `is_new=true`. Status/unknown sólo se reconocen/ignoran.
- Persistencia/side effects: inbound nuevo crea/actualiza conversación y mensaje Flow; puede invocar intake Flow/interpretación. Rechazos nuevos ocurren antes de leer body, DB o bridge.
- Idempotencia: `IDEMPOTENT` para mensajes con ID estable. `flow_messages` tiene unique `(provider, external_message_id)` y `ON CONFLICT DO NOTHING`; duplicados retornan `is_new=false` y no invocan Flow. Tests cubren duplicado y concurrencia PG existentes.
- Replay: deduplicación durable por ID, sin ventana temporal. Status/unknown no tienen side effect de negocio. No se afirma exactly-once delivery.
- Contrato nuevo: reutiliza `TEAM360_MESSAGING_WEBHOOK_TOKEN` y `x-team360-webhook-token`, ya usados por Messaging/Evolution. Config ausente o menor a 32 → 503; credencial inválida/ausente → 401 mediante comparación constante; body máximo 1 MiB. Token válido habilita procesamiento en DEV o PROD.
- Límite: es autenticación precompartida de sender/ingress, no firma request-bound nativa. TLS/ingress debe proteger integridad en tránsito. Compatibilidad/configuración real Gupshup o ingress permanece `NOT_TESTED`; sin ella la app falla cerrada.

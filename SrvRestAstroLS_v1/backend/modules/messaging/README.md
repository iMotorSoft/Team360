# Messaging Module

Base de integraciones de mensajeria y canales conversacionales; Evolution es el transporte WhatsApp DEV, no la autoridad funcional de conversación de Team360.

## Composición Srv05 exclusiva

Entre los entrypoints Team360, Evolution pertenece sólo a Srv05 opt-in. El laboratorio messaging-only sigue separado; no se declara transporte ni promoción productivos por esta composición.

- [Contrato canónico](../../../docs/team360_srv05_evolution_isolation.md): Srv01 no importa/monta Evolution con ningún env; Srv05 OFF → 404, ON DEV válido → montaje explícito, config inválida → aborto saneado, binding/schema inválido → startup fail-closed.
- `TEAM360_SRV05_EVOLUTION_ENABLED=1` es adicional a los settings DEV/proveedor existentes. `TEAM360_SRV05_MESSAGING_PROVIDER` sólo admite evolution; default evolution. No se modifica globalVar ni se crea configuración legacy duplicada.
- Settings/binding por app, pool base compartido con el lifecycle existente; validación read-only antes de iniciar Flow, sin workers Evolution nuevos. Replays usan persistencia/unique/intent existentes; no se promete exactly-once ni se inventa firma proveedor.
- Gupshup sigue legacy/fallback, no habilitado como transporte de esta medición y no requisito de promoción cuando Evolution sea principal. No se elimina su ruta ni se amplía autorización.
- El source se ejecuta desde backend con uv. Launchers/frontend conservados; no arrancar dos schedulers PG contra destinos compartidos.

## Evolution DEV: frontera arquitectónica

Evolution transporta WhatsApp; Team360 posee la conversación. El adapter está validado con veinte intercambios WhatsApp reales, delivery/read, idempotencia y recuperación. El runtime temporal quedó detenido.

Estado validado al 2026-10-06, en `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/evolution-api`:

```text
WhatsApp ↔ Meta WhatsApp Cloud API ↔ Cloudflare Tunnel (DEV) ↔ Evolution API ↔ PostgreSQL 18
```

Flujo implementado y validado con WhatsApp real:

```text
WhatsApp → Meta → Evolution → EvolutionProvider → Team360 Messaging
→ Conversation → fixed responder → EvolutionProvider → Evolution → Meta → WhatsApp
```

`TEAM360_MESSAGING_EVOLUTION_ADAPTER_V1=PASS` y `TEAM360_MESSAGING_FIXED_RESPONSE_LATENCY_V1=PASS`. Perfil `messaging-only` con Milvus apagado, 20/20 pings/PONG/delivered/read, una conversación, sin duplicados ni respuesta no autorizada. La línea base Evolution y su gate formal PENDING permanecen intactos.

## Messaging ↔ Telchi SQL: trabajo posterior del 08/10

La integración SQL fija está en desarrollo DEV; su profiling es INVESTIGATION, no promoción. Este frente existente se reconoce sin atribuir autoría ni alterar el cierre histórico Evolution del 06/10.

- Implementación: [adapter](telchi_sql.py), [sesión SQL](telchi_sql_session.py), [benchmark](telchi_sql_benchmark.py), [instrumentación](profile_trace.py) y [sesión de profiling](pre_sql_profile_session.py); consumidor [query Telchi](../telchi/datalake/messaging_sales_query.py).
- [Reporte canónico del 2026-10-08](../../../../data/reports/messaging/telchi-datalake-pre-sql-profile-v1/report.md): profiling autónomo y validación WhatsApp real PASS, consulta fija DuckDB sobre Foundation pinned/read-only; PostgreSQL respalda catálogo y Messaging. Sin LLM, SAP ni habilitación productiva.
- Condición operativa al cierre de esa evidencia: la restauración del callback Meta anterior falló; se retiró la suscripción temporal y no quedó suscripción Meta Team360 activa. No asumir transporte disponible hoy ni restaurarlo desde esta reconciliación.
- [Estado Telchi](../telchi/status_actual.md) y [CONTEXT](../telchi/CONTEXT.md) conservan los límites de etapa. Las afirmaciones de transporte saludable/restauración del 06/10 abajo son históricas, no estado posterior al 08/10.

## Decisión del adapter Team360

Se reutilizan los contratos y las tablas core, sin enlazar Flow ni LLM. El alta GLOBAL y la migración aditiva fueron autorizadas por el usuario antes de implementarse.

- Contratos: `InboundMessage`, `OutboundMessageReceipt` y `WhatsAppMessageSenderPort.send_text`; `EvolutionProvider` implementa el port síncrono y el service usa `asyncio.to_thread`, sin bloquear el event loop. `DeliveryEvent` y `MessagingSendError` son internos y provider-neutral.
- Adapter en `providers/evolution/`; HTTP en `webhooks/evolution_whatsapp.py`; `routes.py` exporta los handlers, seleccionados explícitamente por Srv05 ON (el registry legacy ya no los importa). Endpoint: `POST /webhooks/messaging/evolution/whatsapp`.
- Solo el adapter conoce endpoints, API key y formatos Evolution. El webhook autentica un header privado, valida la instancia y normaliza texto/status. Payload, apikey, contactos y formatos Evolution no cruzan al service. Se conserva una referencia hash, no el evento crudo con secretos.
- `repository.py` reutiliza `message_threads`/`message_events` de `001`; no usa `flow_conversations`/`flow_messages`. El claim Gupshup/Flow existente no se reutiliza por su acoplamiento funcional. Pool y transacciones existentes; SQL parametrizado en repository.
- Migración `026_team360_messaging_transport_v1.sql`, aplicada a Team360 PostgreSQL 18.4: scope nullable `provider_instance`, `transport_status` separado del estado operacional e índices únicos de conversación, provider message ID, respuesta por inbound y callback por estado. Filas de otros módulos con scope NULL no cambian. No se reescriben migraciones aplicadas.
- Un remitente/canal/instancia reutiliza una conversación. Inbound se confirma antes de routing; el intent outbound se confirma antes del I/O. Duplicados secuenciales o concurrentes no vuelven a despachar.
- Timeouts/respuestas inválidas/resultados 5xx quedan `unknown`; conexión rechazada queda `failed`. No hay reintento automático: un corte entre commit e I/O puede dejar un inbound sin respuesta o un intent `pending`; requiere reconciliación manual, no garantiza exactly-once delivery. Reiniciar no borra conversación ni vuelve a enviar intents.
- Callbacks `sent`, `delivered`, `read`, `failed` se persisten y correlacionan por ID externo. Se maneja callback temprano mediante bloqueo transaccional compartido con aceptación; read/delivered no retroceden por callbacks tardíos. Meta v2.3.7 usa `keyId`, y puede emitir `fromMe=false` en delivery: no confundirlo con inbound.
- DEV channel preparado en workspace existente `team360_public_site`, alias `evolution-meta-dev`, provider `evolution`, instance `team360-meta-dev`. No contiene credenciales. Setup explícito con `MessagingRepository.provision_dev_channel`; el webhook no aprovisiona nada automáticamente.

Evolution = transport/provider. Team360 = conversation owner. Sin segundo framework, servidor PostgreSQL, Redis, broker, automatizaciones ni inteligencia en este gate.

## Configuración DEV y seguridad

El adapter está deshabilitado por defecto y exige configuración explícita de identidad y transporte desde el entorno existente; nunca habilita autorización de negocio por un teléfono.

- `TEAM360_MESSAGING_DEV_ENABLED=1`; `TEAM360_ENV=development` (producción rechazada).
- `TEAM360_MESSAGING_WORKSPACE_SLUG`, `TEAM360_MESSAGING_CHANNEL_ALIAS`: binding al canal DEV preparado.
- `TEAM360_MESSAGING_DEV_AUTHORIZED_SENDER`: único número autorizado, dígitos sin `+` ni JID; privado, sin valor en código/documentación. **Phone number != business authorization**: allowlist exclusivamente DEV.
- `TEAM360_MESSAGING_WEBHOOK_TOKEN`: privado, mínimo 32 caracteres; Evolution debe enviar `x-team360-webhook-token` en los headers de su webhook local. Sin header correcto: 401. Endpoint sin configuración: 503. Body limitado a 1 MiB.
- `TEAM360_EVOLUTION_BASE_URL`, `TEAM360_EVOLUTION_INSTANCE`, `TEAM360_EVOLUTION_API_KEY`, `TEAM360_EVOLUTION_TIMEOUT_SECONDS` (default 10, máximo 30). Solo el adapter los resuelve; sin secretos en repr ni mensajes de error.
- `META_TEAM360_PHONE_NUMBER_ID` identifica el destinatario interno normalizado. Meta sigue en Evolution; Team360 no consume tokens Meta para enviar WhatsApp. No hay fallback a activos Vertice360.
- Usar el entorno/overrides privados existentes, fuera de Git. No se copiaron secretos de `.bashrc`, no se guardó raw payload y no se imprime el remitente en responses/logs del módulo.
- Durante la prueba, webhook local Evolution con `MESSAGES_UPSERT` y `MESSAGES_UPDATE`, URL Team360 accesible desde Podman y header privado; quedó desactivado al finalizar. La API v2.3.7 recibe `byEvents=false` y `base64=false`; sus campos persistidos se llaman `webhookByEvents`/`webhookBase64`. Webhook global y Quick Tunnel Meta sin cambios.

## Gupshup inbound: autenticidad e idempotencia

`POST /webhooks/messaging/gupshup/whatsapp` es un webhook público legítimo, no una superficie DEV. El contrato Gupshup disponible en el repositorio no documenta una firma request-bound utilizable; por eso Team360 no inventa un HMAC incompatible y exige la frontera precompartida ya existente de Messaging.

- Sender o ingress confiable debe agregar `x-team360-webhook-token`, comparado en tiempo constante con `TEAM360_MESSAGING_WEBHOOK_TOKEN` (mínimo 32 caracteres).
- Configuración ausente/incompleta → 503; credencial ausente o inválida → 401. El rechazo ocurre antes de leer JSON, reclamar mensajes, persistir o invocar Flow. Body máximo: 1 MiB.
- TLS/ingress protege integridad en tránsito; esta frontera no se presenta como firma nativa de Gupshup. La compatibilidad/configuración real del sender o ingress permanece evidencia de destino, sin habilitar delivery aquí.
- Inbound válido se normaliza y reclama atómicamente en PostgreSQL. La unique key `(provider, external_message_id)` hace que un replay con ID estable retorne `is_new=false`; sólo el primer claim llega al bridge Flow. Status/unknown no generan side effects de negocio.
- Evolution continúa DEV-only y ahora también requiere `TEAM360_ENV=dev|development` explícito; entorno ausente o desconocido falla 503 aunque `TEAM360_MESSAGING_DEV_ENABLED=1`.

## Perfil DEV messaging-only

El launcher canónico ofrece un perfil explícito que reutiliza las rutas Messaging y PostgreSQL sin cargar módulos ajenos. El modo normal permanece default y conserva sus preflights y entrypoint.

Desde la raíz Team360, con configuración privada válida:

```bash
TEAM360_DEV_PROFILE=messaging-only TEAM360_BACKEND_PORT=18181 ./SrvRestAstroLS_v1/backend-dev.sh
```

`backend/modules/messaging/dev_app.py` abre el pool únicamente en startup y valida DSN real, binding e índices de `026`. Monta solo `/health` y el webhook Messaging existente; no importa module registry, Flow, Telchi, Vera, Milvus, LiteLLM ni clientes LLM. Producción, perfiles desconocidos y puertos ocupados se rechazan; no mata listeners existentes ni exige Evolution disponible para arrancar.

El preflight normal (PostgreSQL, Milvus y LiteLLM TCP/HTTP) y su entrypoint `ls_iMotorSoft_Srv01:app` se conservan. No hay mocks ni health falsificado. En messaging-only solo se requieren Python/Litestar/Uvicorn, configuración y PostgreSQL Team360. `/health` hace `SELECT 1` real.

Para callbacks desde Podman, `TEAM360_BACKEND_HOST` debe ser la dirección del host que resuelve `host.containers.internal`, no `0.0.0.0`; el bind loopback por defecto sirve para pruebas locales. Esa dirección se obtiene con DNS dentro del contenedor, sin exponer secretos. El endpoint LAN es DEV y exige header privado + allowlist.

La configuración actual usa `.env.backend-dev.local` existente como mecanismo (ignorado, modo 600), sin copiar secretos Meta ni `.bashrc`. La allowlist contiene únicamente el remitente ya autorizado en el transporte previo; no se publica su número.

La sonda operativa `providers/evolution/probes/gate_session.py` inicia el launcher, habilita solo el webhook local si estaba desactivado y valida container→Team360 HTTP sin enviar WhatsApp. No genera pings ni respuestas proactivas. Rechaza un replay no autorizado y selecciona un inbound con respuesta aceptada para verificar duplicado. Al completar veinte pares, reinicia solo su backend y comprueba preservación de las filas previas (callbacks posteriores pueden agregar filas).

Sesión acotada (entorno privado cargado, desde `backend`):

```bash
uv run python -m modules.messaging.providers.evolution.probes.gate_session --host <host-resuelto-por-Podman> --duration 1800 --output <directorio-nuevo-Team360>
```

No reemplaza un webhook activo. Finalizar o vencer el plazo restaura/desactiva el webhook local y cierra únicamente su backend. La sesión `20261006-165557` expiró tras completar el tráfico: el contador original incluyó 3 textos no enrutados y la prueba duplicada eligió uno sin respuesta. Su evidencia original se conserva, no se convirtió retrospectivamente en PASS.

El cierre independiente `providers/evolution/probes/verify_session.py --session <directorio> --host <host-Podman>` cruza los veinte pares con Evolution, repite sus IDs reales sin enviar mensajes nuevos, verifica unauthorized/empty text y reinicia solo sus propios backends. La prueba operativa solicitada reinició además únicamente `evolution-api`: conservó 90 IDs de transporte, 103 filas Team360 y la conversación, con instancia `open`.

Todos los backends/supervisores temporales terminaron; Evolution continúa saludable como antes. No hay autostart. Evidencia de cierre en `data/reports/messaging/evolution-adapter-v1/20261006-165557/verified/`, con puntero en `active-session.json`.

## Pruebas y benchmark Team360-only

Los veinte intercambios humanos y las pruebas independientes de cierre complementan la suite local. El reporte conserva tráfico extra y fallos de instrumentación originales, sin alterar el benchmark histórico Evolution.

- `TEAM360_MESSAGING_POSTGRES_TEST=1 uv run pytest tests/test_messaging_*.py tests/test_module_registry.py -q`: 175 passed; PostgreSQL real + HTTP loopback, cuatro tests del perfil y dos regresiones de scope/replay del benchmark.
- Suite relevante Messaging/registry/DB/Console/Flow: 703 passed, 39 skipped (gates externos opt-in no habilitados). Warning existente de diagnóstico in-memory, sin requests LLM.
- Casos: normalización, filtros, auth, unit idempotency, webhook completo, duplicate concurrente, remitente no autorizado, texto vacío, texto sin routing, error/timeout/respuesta inválida/Evolution inaccesible, callback temprano/reordenado/duplicado y reconstrucción app/pool. Intent interrumpido no se reenvía tras reconstrucción.
- Tráfico real: 20 pings exactos, 20 PONG aceptados, 20 delivered y 20 read correlacionados con IDs Meta en Evolution y Team360. Una conversación y 0 respuestas a 3 textos adicionales no enrutados, todos conservados en PostgreSQL.
- Cierre real: replay de los 20 IDs inbound → 20 resultados duplicate, 0 filas y 0 mensajes Evolution nuevos; unauthorized y texto vacío rechazados/ignorados. Dos arranques y reinicio real Team360 preservaron todas las filas; tras reiniciar Evolution, mismos IDs de transporte y conversación. Webhook local desactivado y procesos propios cerrados.
- `benchmark.py` registra/reporta T0 recepción HTTP, T1 normalización, T2 commit inbound, T3 routing, T4 inicio `send_text`, T5 aceptación HTTP y T6 callback delivered. T0→T4 es overhead Team360; T0→T6 es total observable desde Team360. Timestamps de pared locales; intervalos negativos se rechazan. T5 no es Graph accept y T6 no es timestamp del teléfono.
- Reporte separado, desde `backend`: `uv run python -m modules.messaging.benchmark --since <ISO-con-timezone> --output <directorio-Team360-separado>`. Requiere configuración DEV y canal existente. Percentiles con interpolación `(N−1)*p`; valida 20 pares ordenados y delivery antes del siguiente inbound. No declara por sí solo tráfico real ni PASS.
- `preflight.json`, `session.json` y `latency.json` originales conservan la historia, incluido timeout y falsas aserciones de la sonda. `verified/verification.json` contiene verificación independiente, hashes de correlación y recuperación; `verified/evidence.json`/`report.md`, el benchmark final.
- Scope corregido: solo pings exactos 01..20 entran en el benchmark; los 3 textos fuera del contrato se reportan aparte con hashes y 0 replies. Un nuevo ID para un ping válido, un ping válido desordenado o cualquier reply a texto no enrutado sigue invalidando la sesión. No se ocultaron intentos ni cambiaron timestamps.

| Métrica Team360 (ms) | N | Min | Mean | p50 | p90 | p95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Processing T0→T4 | 20 | 27.32 | 69.28 | 56.37 | 134.27 | 146.04 | 169.44 |
| Evolution HTTP acceptance T4→T5 | 20 | 662.26 | 833.54 | 807.44 | 1056.89 | 1117.19 | 1133.97 |
| Observable total T0→T6 | 20 | 2155.22 | 2569.25 | 2516.86 | 2881.89 | 2972.98 | 2998.47 |

Overhead Team360 medido: p50 56.37 ms (<100), p95 146.04 ms (<250). Baseline WhatsApp/Evolution: p50 2567.4 ms, p95 3091.8 ms. El total nuevo es comparable (≈2.52/2.97 s); no estimar overhead restando muestras distintas y con distinto punto de inicio. El gate formal histórico Evolution continúa PENDING.

## Instalación y activos propios

Evolution base v2.3.7 corre a demanda con Podman rootless, PostgreSQL 18.4 reutilizado, base/schema propios, Redis OFF y cache local ON.

- Publicación: `127.0.0.1:18180 → container:8080`; 8080 del host libre. Health interno continúa en 8080.
- Base, rol y schema: `evolution_api`; PostgreSQL compartido, sin crear otro servidor.
- Persistencia: PostgreSQL y `data/store`; sin systemd, cron, auto-start ni restart automático.
- Instancia: `team360-meta-dev`, integración `WHATSAPP-BUSINESS`.
- Activos Meta independientes: app `Team360 Messaging Hub`, WABA propia, System User `team360-messaging` y número WhatsApp propio DEV (sólo sufijo `***4780` aquí).
- `backend/globalVar.py` conserva los nombres públicos `TEAM360_META_*`, pero lee exclusivamente `META_TEAM360_WABA_TOKEN`, `META_TEAM360_WABA_ID`, `META_TEAM360_PHONE_NUMBER_ID`, `META_TEAM360_VERIFY_TOKEN`, `META_TEAM360_APP_SECRET` y `META_TEAM360_GRAPH_VERSION`. Graph conserva `v20.0` como default no secreto.
- No existe fallback a `META_VERTICE360_*`, `META_APP_SECRET_IMOTORSOFT` ni `META_GRAPH_VERSION`. Si faltan token, phone number ID o verify token Team360, el helper de habilitación retorna falso. Las variables se resuelven al importar el módulo; un proceso existente requiere recargar su configuración.
- Los activos históricos `META_VERTICE360_*` **no son fuente de verdad de Team360**. No copiar tokens, App Secret, PIN ni verify token desde archivos privados o `~/.bashrc`.
- Quick Tunnel efímero para `/webhook/meta`, no producción. Cambiar hostname exige sincronizar `SERVER_URL` y la suscripción de la app; el callback actual no valida HMAC, una limitación pendiente para producción.

Operación canónica: [README del laboratorio](../../../../../../lab/evolution-api/README.md); no crear otra instalación ni duplicar sus scripts.

## Patch reproducible y rollback

Un backport mínimo protege los contactos opcionales de callbacks Meta sin actualizar Evolution, schema, dependencias ni activos.

Valores verificados contra `image.ref`, patch e imagen local:

- Tag: `localhost/team360/evolution-api:v2.3.7-meta-statusfix1`.
- Manifest digest: `sha256:ffe2a98adcfd2575e71f90041747b023cf1bc22696684a7589fdd7155b38be00`.
- Image ID: `86142b5f352c2abe141d5a1cffbc13524ec3c351b4a9cb13e3fa6bf4d0eed461`.
- Source/tag 2.3.7: commit `cd800f2976e1e5b682fbf86a01ee4d85ae61f370`.
- Patch: `patches/meta-statusfix1/contacts-profile.patch`, sobre `src/api/integrations/channel/meta/whatsapp.business.service.ts`, línea 390 del tag.

```diff
-      if (received.contacts) pushName = received.contacts[0].profile.name;
+      const incomingContact = received?.contacts?.[0];
+      pushName = incomingContact?.profile?.name ?? incomingContact?.name ?? incomingContact?.wa_id ?? undefined;
```

Build: `./build-statusfix.sh`, source fijado, sin red y reutilizando dependencias de la imagen oficial. Receta, fixtures y proveniencia: [patch local](../../../../../../lab/evolution-api/patches/meta-statusfix1/README.md).

Rollback desde el laboratorio: detener y eliminar **sólo** `evolution-api`, luego ejecutar `./start.sh` con `EVOLUTION_IMAGE=docker.io/evoapicloud/evolution-api:v2.3.7@sha256:1bd8afc4a6cf48822e6cf02469aeae7bd35a12a6b616eacd1291926307f4d339`. Para selección permanente usar esa referencia en `image.ref`. Nunca `rm -v`, borrar `data/store` ni tablas. El rollback conserva datos y reintroduce el bug; no es una recomendación operativa.

## Tráfico real y gates

Inbound, outbound, bidireccionalidad, callbacks SENT/DELIVERED/READ tras el patch, restart/recreate y persistencia fueron validados con tráfico real.

- `TEAM360_EVOLUTION_META_CLOUD_DEV_V1=PASS`.
- `TEAM360_EVOLUTION_V237_META_STATUS_PATCH_V1=PASS`.
- `TEAM360_EVOLUTION_PORT_REMAP_V1=PASS`: la sesión real posterior al remapeo tiene 20 pares ping/pong correlacionados por hash y persistidos con DELIVERED, además del mapping, health y challenge registrados.
- `TEAM360_EVOLUTION_WHATSAPP_LATENCY_BASELINE_V1=PENDING`: el criterio vigente exige cinco métricas completas y cero violaciones; esta sesión carece de correlación Graph y registra un ping 20 anticipado ignorado.

Evidencia local: `data/statusfix-real-evidence.json`, `data/port-remap-evidence.json` y sesión `data/latency/20261006-105237-46852ac6/` dentro del laboratorio. SHA-256 de `probe.jsonl`: `475b46be7c0b47a147968b4bca4c9c39023681fb888dc78119368cf48944a7dc`. No se sustituyó evidencia por fixtures ni se borró la violación.

## Línea base observable sin Team360 ni LLM

Los 20 intercambios aceptados son secuenciales y entregados; las cifras coinciden con timestamps de la sonda y mensajes persistidos. El gate formal sigue pendiente, aunque el transporte observable es usable.

| Métrica | N | Min ms | Mean ms | p50 ms | p90 ms | p95 ms | Max ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Inbound → event dispatch (Evolution) | 20 | 6.4 | 18.8 | 21.7 | 29.4 | 36.8 | 47.5 |
| Inbound → delivered callback total | 20 | 2016.0 | 2625.2 | 2567.4 | 2882.8 | 3091.8 | 3497.6 |
| Evolution → Meta accept | 0 | — | — | — | — | — | — |
| Meta accept → sent | 0 | — | — | — | — | — | — |
| Meta accept → delivered | 0 | — | — | — | — | — | — |
| Responder dispatch → Graph request | 0 | — | — | — | — | — | — |

Valoración de las dos métricas observables: **GOOD - suitable for normal conversational WhatsApp use**. Procesamiento hasta despacho en decenas de ms; total p50 ≈2.57 s, p95 ≈3.09 s, máximo ≈3.50 s, con 20/20 respuestas entregadas y buena estabilidad de la muestra. No llega al objetivo orientativo EXCELLENT de p50 <2 s. No hay evidencia que justifique Redis, brokers o escalado adicional para el volumen previsto; esta muestra no es un test de capacidad ni una garantía de producción.

T1 es despacho del evento, anterior al commit de PostgreSQL. T5 es llegada local del callback delivered e incluye su retorno desde Meta, no el instante exacto en el teléfono. T5−T0 no incluye tiempo humano. No se pueden separar cuantitativamente red/Meta/WhatsApp ni aceptación Graph sin T3. READ depende del lector. Los percentiles usan interpolación lineal `(N−1)*p`.

La sonda registró 21 pings: un ping 20 fuera de orden fue ignorado y no recibió respuesta; luego se aceptó el ping 20 correcto. Los veinte pares aceptados no se solapan, pero el intento ignorado sigue siendo una violación bajo el contrato actual. `benchmark/latency.py --report data/latency/20261006-105237-46852ac6` reproduce PENDING; no es un cierre/reporting olvidado. Cerrar el gate completo requiere una nueva sesión conforme o una revisión explícita del contrato, fuera de este cierre documental.

# Inventario cruzado de capacidades reutilizables

Fecha: 2026-05-06
Scope revisado:

- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/JudaismoenVivo`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SolFXHub`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Vertice360`
- `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`

Este inventario surge de inspeccion estatica de codigo, manifiestos y docs. No valida runtime ni ejecuta servidores.

Contexto de negocio complementario:

- [Team360 ERP AI Layer](../negocio/contexto_negocio_team360_erp_ai_layer_2026-05-06.md)
- [Estrategia tecnica y negocio con OpenClaw](informe_estrategia_tecnica_negocio_openclaw_2026-05-06.md)

## Lectura ejecutiva

La base mas reutilizable para proyectos nuevos esta en tres repos:

1. `Vertice360`: mejor fuente para AG-UI/SSE reusable, broadcaster, helper frontend SSE, mensajeria WhatsApp Meta/Gupshup, CRM demo, workflow demo, AI workflow con LangGraph y orquestador demo.
2. `concilia`: mejor fuente para flujos de wizard accionables con SSE por `run_id`, notificaciones por `threadId`, uploads/ingesta, conciliacion bancaria, fallback en memoria y smoke tools.
3. `SolFXHub`: mejor fuente como laboratorio AG-UI por "oleadas": muchos patrones pequeños de streaming, formularios, listas, acciones, parser/orquestador FX, golden tests y OpenAPI.

`Team360` ya tiene la estructura objetivo para convertir esas piezas en plataforma, pero hoy AG-UI/orquestador son placeholders y Mercado Libre browser lab es la capacidad mas concreta. `JudaismoenVivo` aporta capacidades de producto, RAG/contenido, e-commerce, auth y analytics educativos. `SpendIQ` aporta OCR/document AI temprano, audio, Telegram/webhooks y datasets de conciliacion.

## Matriz cruzada

| Capacidad | JudaismoenVivo | SolFXHub | SpendIQ | concilia | Vertice360 | Team360 | Estado reusable |
|---|---:|---:|---:|---:|---:|---:|---|
| SSE backend Litestar | No | Si | No | Si | Si | Placeholder | Reusable desde Vertice360/concilia |
| Cliente `EventSource` Svelte/Astro | No | Si | No | Si | Si | Pendiente | Reusable con adaptacion |
| AG-UI compatible oficial | No | Parcial/lab | No | No, ad-hoc | Parcial/custom `CUSTOM` | Pendiente | Requiere compat layer |
| Broadcaster multi-subscriber | No | Basico/labs | No | Por topic en memoria | Si, limpio | Pendiente | Extraer de Vertice360 |
| SSE por thread/topic | No | Notify global | No | Si, `threadId` | Global/custom | Pendiente | Extraer patron de concilia |
| SSE por run con acciones | No | Varios labs | No | Si, wizard | AI workflow/custom | Pendiente | Reusable desde concilia |
| Orquestador conversacional | No | Parser/orquestador FX | No | Chat/wizard/reconcile | Demo avanzado | Skeleton | Base: Vertice360 + concilia |
| LangGraph / AI workflow | No | Si | No | Dependencias, uso parcial | Si | Dependencias | Extraer patrones, no dominio |
| WhatsApp Meta adapter | No | No | No | No | Si | No | Portar desde Vertice360 |
| WhatsApp Gupshup adapter | No | No | No | No | Si | Placeholder docs | Portar desde Vertice360 |
| Mercado Libre browser lab | No | No | Datos docs | No | No | Si | Reusable para probes/control |
| Upload/ingesta archivos | Parcial | No principal | Si/docs | Si fuerte | Parcial | No | Concilia/SpendIQ |
| Conciliacion bancaria | No | No | Datos/analisis | Si fuerte | No | No | Producto reusable como modulo |
| OCR/document AI | RAG PDFs | No | Si fuerte | Ingesta Excel | No | No | SpendIQ/Judaismo |
| RAG/vector DB/Milvus | Si fuerte | No | Dependencias | No | No | No | JudaismoenVivo |
| ArangoDB domain app | Si | No | Si legacy | No | No | No | Reusable con hardening |
| Auth/usuarios/e-commerce | Si | No | No | No | No | No | JudaismoenVivo |
| Paypal/cupones | Si | No | No | No | No | No | JudaismoenVivo |
| CRM/pipeline/tasks UI | No | No | No | No | Si | No | Vertice360 demo adaptable |
| Telemetry/correlation | No | No | No | No | Si | Estructura | Vertice360 |
| Skills Codex locales | Si | No | No | No | Si | Si fuerte | Reusable como metodo de trabajo |

## Capacidades por proyecto

### Team360

Estado general: repo objetivo/plataforma, con estructura modular ya preparada.

Capacidades encontradas:

- `team360_orquestador` con carpetas `api`, `agui`, `domain`, `services`, `workflows`, `tools`, `repositories`, `telemetry`, `prompts`, `db`.
- `agui_stream` reservado para eventos AG-UI/SSE.
- `messaging` con base para providers y webhooks.
- Provider Mercado Libre con laboratorio aislado:
  - `browser/config.py`, `context.py`, `session_store.py`, `pages.py`, `actions.py`, `selectors.py`
  - `probes/smoke_login.py`, `smoke_inbox.py`, `smoke_questions_*`, `smoke_reply_draft.py`, `smoke_thread_read.py`
  - `runtime/profiles`, `runtime/screenshots`, `runtime/storage_state`
- Dependencias backend modernas: Litestar, OpenAI, LangGraph, LangChain, psycopg, Playwright.
- Docs de arquitectura multi WhatsApp / multi LLM con matriz explicita de que portar desde Vertice360.
- Skills locales: `team360-project`, `agent-browser`, `ai-sdk`, `deploy-to-vercel`, `vercel-cli-with-tokens`, `supabase-postgres-best-practices`, `web-design-guidelines`.

Rutas clave:

- `SrvRestAstroLS_v1/backend/modules/team360_orquestador/`
- `SrvRestAstroLS_v1/backend/modules/agui_stream/`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/`
- `SrvRestAstroLS_v1/docs/team360_multi_whatsapp_multi_llm_architecture.md`

Reutilizacion:

- Bueno como esqueleto de plataforma nueva.
- No tomar AG-UI/SSE de Team360 todavia como implementacion lista: hoy son placeholders.
- Mercado Libre browser lab si es reutilizable como laboratorio conservador para canal con UI externa.

### Vertice360

Estado general: fuente mas madura para plataforma conversacional demo con SSE, mensajeria y workflows.

Capacidades encontradas:

- AG-UI/SSE backend:
  - `backend/modules/agui_stream/broadcaster.py`: broadcaster en memoria multi-subscriber.
  - `backend/modules/agui_stream/routes.py`: `GET /api/agui/stream`, `OPTIONS /api/agui/stream`, `POST /api/agui/debug/trigger`, handshake, heartbeat y headers CORS.
- SSE frontend:
  - `astro/src/lib/shared/sse.js`: manager con reconexion y backoff.
  - `astro/src/lib/messaging/sse.js`, `astro/src/lib/crm/sse.js`, `astro/src/lib/vertice360_workflow/sse.js`, `astro/src/lib/vertice360_ai_workflow_studio/sse.js`.
- Messaging providers:
  - Meta WhatsApp: client/service/mapper.
  - Gupshup WhatsApp: client/service/mapper/signature stub/fixtures/snippets.
  - Bird webhook parser/signature/snippets.
  - Registry simple de providers.
- Webhooks:
  - `backend/modules/messaging/webhooks/routes.py`
  - `backend/modules/messaging/webhooks/dispatcher.py`
- Demos UI:
  - CRM: inbox, pipeline, tasks, timeline, conversation.
  - Messaging labs Meta/Gupshup.
  - Orquestador Vertice360.
  - Workflow y AI workflow studio.
- Orquestacion/workflow:
  - `backend/modules/vertice360_orquestador_demo/`
  - `backend/modules/vertice360_workflow_demo/`
  - `backend/modules/vertice360_ai_workflow_demo/`
  - LangGraph en `langgraph_flow.py`.
- Endpoints demo importantes:
  - `/api/demo/vertice360-orquestador/...`
  - `/api/demo/vertice360-ai-workflow/...`
  - `/api/demo/messaging/meta/whatsapp/send`
  - `/api/demo/messaging/gupshup/whatsapp/send`
  - `/api/agui/pozo/flow/v1/run`

Rutas clave:

- `SrvRestAstroLS_v1/backend/modules/agui_stream/`
- `SrvRestAstroLS_v1/astro/src/lib/shared/sse.js`
- `SrvRestAstroLS_v1/backend/modules/messaging/providers/`
- `SrvRestAstroLS_v1/backend/routes/messaging.py`
- `SrvRestAstroLS_v1/backend/routes/demo_vertice360_orquestador.py`
- `SrvRestAstroLS_v1/backend/routes/demo_vertice360_ai_workflow.py`

Reutilizacion:

- Portar a proyectos nuevos: broadcaster, ruta SSE, helper frontend SSE, mappers Meta/Gupshup, tests de mappers, telemetry.
- Adaptar antes de producto: CORS/auth, multi-workspace, secretos, persistencia, provider config, event envelope.
- No portar directo: dominio inmobiliario, stores en memoria como persistencia final, endpoints demo como contrato productivo.

### concilia

Estado general: producto funcional de conciliacion con AG-UI/SSE ad-hoc, wizard y pipeline de datos.

Capacidades encontradas:

- SSE notificaciones por thread:
  - `routes/v1/agui_notify.py`
  - `GET /api/ag-ui/notify/stream?threadId=...`
  - buffer en memoria por topic, evento `DEBUG CONNECTED`, payload JSON ad-hoc.
- Wizard SSE por run:
  - `routes/v1/reconcile_wizard_start.py`
  - `GET /api/reconcile_wizard/runs/{run_id}/events`
  - `POST /api/reconcile_wizard/runs/{run_id}/action`
  - `services/wizard_runtime.py` como fallback en memoria.
  - `services/wizard_engine.py` para estado y eventos de pasos.
- Frontend Svelte:
  - `clientA/src/components/agui/ConciliaApp.svelte`
  - `clientA/src/components/agui/ReconciliarApp.svelte`
  - `ReconciliarResumen`, `ReconciliarDetalle`, cards de detalle N->1 y 1->1.
- Reconcile API:
  - `/api/reconcile/start`
  - `/api/reconcile/summary`
  - `/api/reconcile/details`
  - `/api/reconcile/details/no-banco`
  - `/api/reconcile/details/no-contable`
  - `/api/reconcile/details/n1/grupos`
  - `/api/reconcile/details/n1/sugeridos`
- Upload/ingesta:
  - `/api/uploads/ingest`
  - `/api/uploads/v2/ingest`
  - `/api/ingest/confirm`
  - sniffing bancario, SICOM Excel, parquet preview.
- Smoke tools:
  - `backend/tools/agui_sse_smoke_test.py`
  - `backend/tools/wizard_smoke_test.py`
- Docs utiles:
  - `api_inventory.md`
  - `docs/sse_implementacion_litestar_svelte.md`
  - `docs/agui_notes.md`
  - `docs/STAGES_CATALOG_...md`
  - `docs/status_actual.md`

Nota AG-UI:

- `concilia` usa `EventSource` crudo y eventos custom.
- No usa realmente `@ag-ui/client`, `@ag-ui/core`, `HttpAgent` ni esquemas oficiales AG-UI, aunque tiene dependencias relacionadas.
- Es muy reusable como patron practico de UI reactiva + backend streaming, no como implementacion AG-UI canonica.

Reutilizacion:

- Excelente para wizard/run/action/SSE, conciliacion, ingesta Excel/Parquet y estado con fallback.
- Requiere wrapper de eventos si se quiere compatibilidad AG-UI formal.
- El broadcaster por topic es simple y util para proyectos chicos, pero no escala multi-instancia sin Redis/Postgres pubsub.

### SolFXHub

Estado general: laboratorio AG-UI/SSE mas amplio, organizado en oleadas.

Capacidades encontradas:

- Muchos endpoints SSE Litestar bajo `/api/ag-ui/lab/...`:
  - o0 text stream.
  - o1 text ok/warn/error.
  - o2 forms/action/rest/sse/run.
  - o3 list/page/action/run.
  - o4 preview/commit/status/run.
  - o5 preview/commit/status/list/page/action/run.
  - o11/o12/o13/o14/o21/o22/o23 chat/run.
- Notify broadcast:
  - `GET /api/ag-ui/notify/stream`
  - `POST /api/ag-ui/notify/broadcast`
- Frontend AG-UI lab:
  - `clientA/src/components/lab/agui/Oleada*.svelte`
  - `clientA/src/pages/lab/agui/oleada-*.astro`
  - `clientA/src/lib/runas/agui.ts` con helper `startSSE`.
- FX parser/orquestacion:
  - `routes/pruebas/graphs/o24_*`
  - `routes/pruebas/graphs/o31_*`
  - `routes/pruebas/graphs/o41_*`
  - `lab_oleada24.py`, `lab_oleada31.py`, `lab_oleada41.py`
- Config/schema/tests:
  - `config/o24_schema_v2.json`, `config/o24_rails.yaml`, `config/o24_states.yaml`, `config/o24_lexicon.yaml`
  - `schemas/sio-v1.schema.json`
  - `openapi/oleada41.yaml`
  - golden tests en `test/golden/`.
- Dependencias: Litestar, ag-ui-protocol, OpenAI, LangGraph, LangChain, MLflow, jsonschema, pytest.

Reutilizacion:

- Usar como catalogo de patrones chicos de AG-UI/SSE.
- Muy bueno para extraer casos: streaming texto, formularios, listas paginadas, acciones, preview/commit, parser con schema y golden tests.
- No tomarlo como arquitectura productiva unica: esta en `routes/pruebas`, con muchos experimentos paralelos.

### JudaismoenVivo

Estado general: producto web educativo/comercial con backend FastAPI, ArangoDB, RAG/Milvus y frontend Astro/Svelte.

Capacidades encontradas:

- Backend FastAPI:
  - `faJudaismoenVivoAstroSrv02.py` registra routers `person`, `analytics`, `payment`, `study`, `book`, `encuentro`.
- Auth/personas:
  - login, recovery email, password reset, registro, registro curso, areas, modelos, CRUD personas.
- Pagos:
  - PayPal process, pending payments, coupon validation.
- Estudio/libros/encuentros:
  - progreso de estudio, period data, divisions, encuentro data/completed, listar/datos/responder/progreso.
- Analytics/asistente:
  - prompts curso, nuevas preguntas, evaluacion, webhooks Telegram.
- RAG/contenido:
  - `milvus_app/markdown_milvus_v3.py`: PDF a Markdown, chunking semantico, Arango MD/Chunk, Milvus, embeddings/OpenAI.
  - backups parquet y utilidades de consulta/check stats.
- Frontend:
  - Astro + Svelte + Tailwind + DaisyUI.
  - home 2026, landings de cursos/libros/encuentros.
  - componentes de checkout PayPal, login, preregistro, suscripcion, video, curso, libro, donacion.
- Skill local:
  - `.codex/skills/judaismoenvivo/SKILL.md` con reglas operativas, validacion y separacion tecnico/comercial.

Reutilizacion:

- Muy util para proyectos con contenido educativo/comunidad/pagos.
- RAG/Milvus + Arango es reusable como pipeline documental, pero tiene acoplamientos fuertes a DB local y secretos/config global.
- No hay AG-UI/SSE relevante detectado.

### SpendIQ

Estado general: backend/document AI temprano con FastAPI, Mistral OCR, OpenAI vision/audio, Telegram y datasets de conciliacion.

Capacidades encontradas:

- Backend FastAPI:
  - `faSpendIQAstroSrv02.py` registra `analytics.router`.
  - `routers/analytics.py` y `analytics.py` con endpoints de assistant/prompts.
- Document AI/OCR:
  - `mistral_v1.py` usa Mistral OCR para PDF/document URL e imagen base64.
  - fallback/alternativa con OpenAI vision para imagenes y PDF rasterizados.
  - PyMuPDF/pdf2image para detectar texto o convertir PDF a imagen.
- Audio/Telegram:
  - upload de audio, transcripcion Whisper, query al indice y respuestas.
  - webhooks BCRA/Telegram/demo.
- RAG legacy:
  - endpoints cargan indices persistidos y consultan con LlamaIndex/LangChain/OpenAI.
- Datos:
  - `Doc/FCE/Conciliacion/` contiene excels usados despues por `concilia`.
  - `Doc/Daniel_Yerno/` tiene reportes Mercado Libre/Mercado Shops/liquidaciones.
- Dependencias:
  - FastAPI, Arango, OpenAI, MistralAI, PyMuPDF, pdf2image, pandas, pymilvus, chonkie, pydub.

Reutilizacion:

- Bueno para OCR/documentos, audio a consulta, Telegram/webhook y primeros datasets.
- Codigo mas legacy/prototipo que modulo productivo; conviene extraer funciones limpias antes de portar.
- No hay AG-UI/SSE relevante detectado.

## Capacidades listas para extraer primero

| Prioridad | Capacidad | Origen recomendado | Destino sugerido | Motivo |
|---:|---|---|---|---|
| 1 | SSE broadcaster + endpoint global | Vertice360 `agui_stream` | Team360 `backend/modules/agui_stream` | Base limpia y corta |
| 2 | Helper frontend SSE con reconexion | Vertice360 `astro/src/lib/shared/sse.js` | Team360 `astro/src/lib/shared/sse.js` | Evita duplicar EventSource |
| 3 | Wizard run/action/events | concilia `reconcile_wizard_*`, `wizard_runtime`, `wizard_engine` | Modulo generic `wizard_runtime` | Patron potente para flujos guiados |
| 4 | Compatibilidad AG-UI `CUSTOM` | Vertice360 + notas concilia | Capa `agui/events.py` | Normaliza payloads sin romper UI |
| 5 | WhatsApp provider adapters | Vertice360 Meta/Gupshup | Team360 `messaging/providers` | Base real de canales |
| 6 | Mercado Libre browser probes | Team360 | Mantener y endurecer | Ya esta en el repo objetivo |
| 7 | Catalogo AG-UI labs | SolFXHub | Docs/templates internos | Sirve para nuevos prototipos |
| 8 | OCR/document pipeline | SpendIQ + JudaismoenVivo | Modulo `document_ai` | Reusable para backoffice |
| 9 | RAG Milvus/Arango | JudaismoenVivo | Modulo `knowledge_base` | Reusable para asistentes con documentos |
| 10 | Auth/pagos/curso | JudaismoenVivo | Plantilla producto | Reusable fuera de Team360 |

## Decision tecnica recomendada para proyectos nuevos

### Para un proyecto nuevo con UI streaming

Usar:

- Backend: Vertice360 `agui_stream` como base.
- Frontend: Vertice360 `shared/sse.js`.
- Si hay wizard: concilia `run_id/events/action`.
- Si se necesita AG-UI formal: agregar wrapper que emita eventos con envelope `CUSTOM { name, value, timestamp }` y despues evolucionar a schemas oficiales.

No usar directo:

- EventSource duplicado en cada componente como patron final.
- Stores en memoria si se espera multi-instancia.

### Para un proyecto nuevo conversacional multicanal

Usar:

- Team360 como esqueleto.
- Vertice360 para Meta/Gupshup mappers/client/services.
- Team360 Mercado Libre browser lab para exploracion de canales no API.
- Vertice360 telemetry/correlation.

Adaptar antes de produccion:

- Multi-workspace.
- Secret manager / env por ambiente.
- Configuracion de provider en DB.
- Validacion de firma/webhook.
- Persistencia de eventos y mensajes.

### Para un proyecto nuevo de backoffice documental

Usar:

- SpendIQ para OCR Mistral/OpenAI y audio.
- JudaismoenVivo para RAG Milvus/Arango.
- concilia para uploads/ingesta/preview/confirmacion.

Adaptar antes de produccion:

- Separar secretos de `globalVar`.
- Evitar rutas absolutas.
- Agregar contratos de entrada/salida.
- Agregar tests de parseo y fixtures.

## Riesgos comunes detectados

- Muchas implementaciones usan memoria local para eventos/subscriptores; no escala a multiples procesos sin Redis/Postgres/pubsub.
- Hay payloads AG-UI ad-hoc: utiles hoy, pero no compatibles con `@ag-ui/client` de forma canonica.
- Varios repos usan `globalVar.py` con configuracion y potenciales secretos acoplados.
- Hay rutas demo/prototipo bajo nombres productivos o viceversa.
- SolFXHub tiene alto valor como laboratorio, pero no conviene portarlo entero.
- JudaismoenVivo y SpendIQ contienen logica valiosa, aunque mezclada con rutas absolutas, archivos locales y dependencias legacy.

## Fuentes clave inspeccionadas

- `Team360/SrvRestAstroLS_v1/backend/modules/team360_orquestador/`
- `Team360/SrvRestAstroLS_v1/backend/modules/agui_stream/`
- `Team360/SrvRestAstroLS_v1/backend/modules/messaging/providers/mercadolibre/`
- `Team360/SrvRestAstroLS_v1/docs/team360_multi_whatsapp_multi_llm_architecture.md`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/routes.py`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/agui_stream/broadcaster.py`
- `Vertice360/SrvRestAstroLS_v1/astro/src/lib/shared/sse.js`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/messaging/providers/`
- `Vertice360/SrvRestAstroLS_v1/backend/modules/vertice360_ai_workflow_demo/langgraph_flow.py`
- `concilia/SrvRestAstroLS_v1/routes/v1/agui_notify.py`
- `concilia/SrvRestAstroLS_v1/routes/v1/run_action.py`
- `concilia/SrvRestAstroLS_v1/services/wizard_runtime.py`
- `concilia/SrvRestAstroLS_v1/docs/agui_notes.md`
- `SolFXHub/SrvRestAstroLS_v1/routes/pruebas/`
- `SolFXHub/SrvRestAstroLS_v1/clientA/src/components/lab/agui/`
- `JudaismoenVivo/SrvRestAstro_v2/routers/`
- `JudaismoenVivo/milvus_app/markdown_milvus_v3.py`
- `SpendIQ/SrvRestAstro_v2/routers/analytics.py`
- `SpendIQ/SrvRestAstro_v2/mistral_v1.py`

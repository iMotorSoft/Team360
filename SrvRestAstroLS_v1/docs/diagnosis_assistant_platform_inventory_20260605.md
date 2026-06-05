# Inventario tecnico para Asistente Inteligente de Venta y Diagnostico

Fecha: 2026-06-05  
Objetivo: disenar sobre la plataforma real Team360 la primera version real minima del paquete "Asistente Inteligente de Venta y Diagnostico de Automatizacion".  
Alcance: inspeccion de codigo y documentacion. No se modifico implementacion.

## 1. Rama activa y estado git

- Rama actual: `feature/console-backend-core`.
- Ultimo commit: `e8b9a3d feat: close Team360 diagnosis assistant demo path`.
- Estado previo a generar este informe: sin cambios pendientes reportados por `git status --short`.
- Cambio generado por esta tarea: nuevo documento `SrvRestAstroLS_v1/docs/diagnosis_assistant_platform_inventory_20260605.md`.
- No se detectaron archivos modificados o no trackeados relevantes antes de crear el informe.

## 2. Mapa actual de rutas reales

| Ruta | Archivo | Proposito | Componentes principales |
| --- | --- | --- | --- |
| `/` | `SrvRestAstroLS_v1/astro/src/pages/index.astro` | Home publica comercial de Team360. | `PublicMarketingLayout`, `MarketingHeader`, `MarketingFooter`, `HeroProcessVisual`, `SectionHeading`, `Badge`, `LinkButton`. |
| `/login` | `SrvRestAstroLS_v1/astro/src/pages/login.astro` | Entrada mock de diseno a Console, sin autenticacion real. | `MockAccessLayout`, `LinkButton`, `ROUTES`. |
| `/select-workspace` | `SrvRestAstroLS_v1/astro/src/pages/select-workspace.astro` | Selector de perfiles/workspaces mock. | `MockAccessLayout`, `getMockProfiles`, `buildConsoleRoute`. |
| `/w/[workspaceId]` | `SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/index.astro` | Dashboard de Console por workspace. | `ConsoleAppLayout`, `AppShell`, `ConsoleDashboard`. |
| `/w/[workspaceId]/services` | `SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/services/index.astro` | Listado de servicios visibles. | `ConsoleAppLayout`, `ServicesList`. |
| `/w/[workspaceId]/services/[serviceId]` | `SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/services/[serviceId].astro` | Detalle de servicio. | `ConsoleAppLayout`, `ServiceDetail`, `Tabs`, `StatusBadge`, `StatCard`, `EmptyState`. |
| `/w/[workspaceId]/diagnosis` | `SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/diagnosis/index.astro` | Flujo de diagnostico actual en Console. | `ConsoleAppLayout`, `ConsoleDiagnosis`, `src/lib/api/diagnosis.ts`. |
| `/w/[workspaceId]/workers` | `.../workers/index.astro` | Vista mock de workers. | `WorkersList`. |
| `/w/[workspaceId]/runs` | `.../runs/index.astro` | Vista mock de ejecuciones. | `RunsList`. |
| `/w/[workspaceId]/reports` | `.../reports/index.astro` | Reportes. | `ReportsList`. |
| `/w/[workspaceId]/alerts` | `.../alerts/index.astro` | Alertas. | `AlertsList`. |
| `/w/[workspaceId]/tasks` | `.../tasks/index.astro` | Tareas. | `TasksList`. |
| `/w/[workspaceId]/team` | `.../team/index.astro` | Equipo/usuarios mock. | `TeamList`. |
| `/w/[workspaceId]/settings` | `.../settings/index.astro` | Configuracion de workspace. | `WorkspaceSettings`. |
| `/w/[workspaceId]/organizations`, `/partners`, `/clients`, `/workspaces`, `/client-services`, `/results`, `/support` | paginas bajo `src/pages/w/[workspaceId]/...` | Secciones de Console genericas o especificas. | `ConsoleSectionPage` u otros listados existentes. |

Las rutas de Console usan `getWorkspaceStaticPaths()` o `getServiceStaticPaths()` desde `src/lib/mock/staticPaths.ts`, por lo que hoy se generan desde fixtures, no desde backend real.

## 3. Estado actual de la Home publica

La home publica (`src/pages/index.astro`) ya esta orientada a diagnostico y automatizacion. Secciones existentes:

- Hero con propuesta "Automatizacion con IA para procesos reales de negocio".
- Bloque de problemas operativos.
- Metodo "Como trabaja Team360".
- Caminos de entrada, donde "Diagnostico de Automatizacion" ya aparece como primer item.
- Casos de uso.
- Metodo/confianza por control humano.
- Bloque de tecnologia conectada.
- Seccion de partners.
- CTA final `#contacto`.

CTA principal actual:

- En hero: `Solicitar diagnostico` apunta a `#contacto`.
- En `#contacto`: CTA por `mailto:contacto@team360.live?subject=Solicitar diagnostico Team360`.
- El texto aclara que en la primera version el contacto se inicia por email y que el formulario se incorporara luego.

Insercion recomendada del paquete "Diagnostico Inteligente":

- Reemplazar progresivamente el CTA mailto por un bloque interactivo en la home: `MarketingDiagnosisEntry.astro` o isla Svelte `PublicDiagnosisAssistant.svelte`.
- Ubicacion ideal: primer viewport, debajo del copy hero o inmediatamente antes de `#contacto`, porque el usuario debe empezar con texto libre y recibir valor inmediato.
- Mantener `#contacto` como fallback comercial, no como flujo principal.
- Reutilizar `PublicMarketingLayout`, `MarketingHeader`, `LinkButton`, `Badge`, `SectionHeading` y estilos globales.

Faltantes para Team360 y Mama Mia 360 sin hardcodear:

- No existe landing publica de partner ni ruta tipo `/p/[partnerSlug]`, `/partners/[partnerSlug]` o dominio configurable.
- No hay `PartnerBranding` / `DistributorConfig` frontend.
- La home publica esta escrita como Team360 fijo; `BRAND` global no permite variacion por partner.
- No existe componente publico conversacional. El unico flujo real esta dentro de Console.
- No hay seleccion de `assistant_instance_id` desde canal publico excepto payload opcional en `src/lib/api/diagnosis.ts`.

## 4. Estado actual de la Console

### AppShell

`src/components/console/AppShell.svelte` es el shell unico de Console. Carga:

- `Sidebar`, `Topbar`, `Breadcrumbs`, `ContextBanner`.
- Vistas principales por `view`.
- Panel lateral con workspace activo, pendientes y reportes recientes.
- `ConsoleDiagnosis` para `view === "diagnosis"`.

Inicializacion actual:

- Se inicializa primero con `team360_admin` y `initialWorkspaceId`.
- En `onMount`, lee `?profile=` y `?locale=`.
- Todo el contexto viene de `src/stores/consoleContext.svelte.ts` y mocks.

### Navegacion

`src/lib/navigation/registry.ts` define `ConsoleView` y `navigationRegistry`.

- `diagnosis` existe como vista.
- Grupo: `operations`.
- Audiencias: `owner`, `operator`, `partner`.
- Requiere workspace.

`src/lib/navigation/derive.ts` resuelve rutas con `routeSuffixByView`, incluyendo `/diagnosis`.

Inconsistencia detectada:

- `diagnosis` aparece en la navegacion para audiencia `partner`.
- Pero `partner_admin` en `src/lib/mock/bootstrap.ts` no incluye `"diagnosis"` en `enabledModules`.
- Resultado: un partner como Mama Mia 360 no ve el modulo de diagnostico en Console aunque la navegacion lo permita por audiencia.

### Workspace activo

`WorkspaceSwitcher.svelte` cambia de workspace usando `buildConsoleRoute(workspaceId, view, profile)`.

Mocks relevantes:

- Team360: `ws-team360-control`, organizacion `org-team360`.
- Mama Mia 360: `ws-mama-mia-israel`, organizacion `org-mama-mia-360`, tipo `partner`.
- Clientes de partner: `ws-netzaj-marketplace`, `ws-galil-commerce`.

### Service Detail

`ServiceDetail.svelte` ya soporta tabs:

- `summary`
- `results`
- `reports`
- `alerts`
- `tasks`
- `history`
- `configuration` para no-clientes
- `technical` para owner/operator

La pantalla permite mostrar un diagnostico como servicio contratado, pero hoy el diagnostico vive como vista global `/diagnosis`, no como detalle de `Service` ni como servicio `svc-...` del paquete.

Insercion recomendada en Console:

- Mantener `/w/[workspaceId]/diagnosis` como workspace-level intake para crear sesiones.
- Agregar un `Service` mock/real "Asistente Inteligente de Venta y Diagnostico" para Team360 y Mama Mia 360.
- En `ServiceDetail`, agregar tab o deep link para sesiones/resultados del diagnostico cuando `service.category === "sales_diagnosis"` o `service.packageName` corresponda.
- Para Team360 interno: mostrar vista operacional completa con sesiones, leads, scoring, costos y eventos.
- Para partner/distribuidor: mostrar leads atribuidos al partner, estado comercial, idioma/canal y diagnosticos de su subarbol autorizado, sin exponer otros partners ni clientes directos Team360.

## 5. Inventario de componentes UI reutilizables

Wrappers UI existentes en `src/components/ui`:

- `Button.svelte`: boton DaisyUI con variantes y loading.
- `LinkButton.astro`: CTA enlazable para Astro.
- `Card.svelte`: contenedor base.
- `Badge.svelte`: badge de estado simple.
- `StatusBadge.svelte`: normaliza labels/variantes de estados.
- `Tabs.svelte`: tabs accesibles por teclado basicas.
- `Alert.svelte`: alertas DaisyUI.
- `EmptyState.svelte`: estados vacios/error/permiso.
- `Loading.svelte`: spinner.
- `SectionHeader.svelte`: encabezados de seccion.
- `StatCard.svelte`: metricas.

Componentes de layout reutilizables:

- `PublicMarketingLayout.astro`.
- `MockAccessLayout.astro`.
- `ConsoleAppLayout.astro`.
- `AppShell.svelte`.
- `ConsoleSectionPage.svelte`.
- `ContextBanner.svelte`.

Limitaciones para experiencia conversacional + checklist dinamico:

- No existen `FormField`, `TextInput`, `Textarea`, `Select`, `CheckboxGroup`, `RadioGroup`, `Stepper`, `Progress`, `ChatMessage`, `ConversationPanel`, `DynamicChecklist`, `LeadCaptureForm`.
- `ConsoleDiagnosis.svelte` usa clases directas y botones HTML en varios lugares en vez de wrappers UI.
- El flujo actual esta optimizado para cuestionario secuencial, no para conversacion natural.
- La UI no deduplica preguntas inferidas desde texto libre.
- No hay render semantico AG-UI/SSE; el resultado se renderiza desde JSON final.

## 6. Inventario de mock data

### Organizaciones

Archivo: `src/lib/mock/organizations.ts`.

- `org-team360`: `team360_owner`.
- `org-carmel-retail`: cliente directo.
- `org-mama-mia-360`: partner, region Israel. Comentario explicito: primera fixture regional, no ramificar por nombre.
- `org-netzaj-racing`, `org-galil-home`: clientes de partner.
- `org-nexo-iberia`: partner onboarding.

### Workspaces

Archivo: `src/lib/mock/workspaces.ts`.

- `ws-team360-control`: plataforma Team360.
- `ws-mama-mia-israel`: red partner Israel, locale `es`, direction `ltr`.
- Workspaces de clientes con locale/direction `es` o `he`.

### Perfiles/roles

Archivo: `src/lib/mock/bootstrap.ts` y `users.ts`.

- `team360_admin`: ve red completa y tiene `diagnosis`.
- `team360_operator`: tiene `diagnosis`.
- `team360_support`: no tiene `diagnosis`.
- `partner_admin`: Mama Mia 360, no tiene `diagnosis` aunque la registry lo permite.
- `client_admin`: no tiene `diagnosis`.

### Servicios

Archivo: `src/lib/mock/services.ts`.

Servicios existentes:

- Operacion interna Team360.
- Leads/CRM, marketplace, reportes, catalogo, partner operations, atencion inicial.
- `svc-mama-mia-network` representa operacion de red comercial del partner.

No existe servicio mock para:

- `svc-team360-sales-diagnosis`.
- `svc-mamamia360-sales-diagnosis`.

### Donde modelar lo nuevo

- Team360: `organizations.ts`, `workspaces.ts` ya existen; agregar workspace publico si el mock debe reflejar `team360_public_site` del backend.
- Mama Mia 360: ya existe como organization/workspace; agregar config de partner/branding separada, no condicional por nombre.
- Paquete Diagnostico Inteligente: en `services.ts` como servicio visible y en backend como `automation_package`/`assistant_instance`.
- Templates L0/L1: frontend mock inicial en `src/lib/mock/diagnosisTemplates.ts`; backend real en `modules/automation_diagnosis/templates.py` o persistido en PostgreSQL.
- Diagnosis sessions/checklist/scoring: hoy backend lo maneja en `automation_diagnosis`; frontend mock podria tener `src/lib/mock/diagnosis.ts` solo si se necesita demo sin backend.

## 7. Estado backend real

### Framework y estructura

- Framework: Litestar (`backend/app.py`).
- Server recomendado en docs: `uv run uvicorn app:app`.
- Dependencias: `litestar`, `pydantic`, `httpx`, `openai`, `langgraph`, `langchain`, `psycopg[binary]`, `psycopg-pool`, `playwright`, `pytest`.
- DB runtime: `psycopg 3 async` directo, segun `.agents/skills/team360-project/SKILL.md` y `lat.md/postgres-driver-policy.md`.

Modulos relevantes:

- `backend/modules/automation_diagnosis/`: dominio actual del diagnostico.
- `backend/routes/automation_diagnosis.py`: endpoints HTTP.
- `backend/modules/db/`: pool/settings/transaction.
- `backend/db/migrations/001..004`: schema core, RBAC/packages/workers/knowledge, pgvector, persistence de diagnostico.

### Endpoints existentes

En `backend/app.py` se registran:

- `GET /api/health`
- `GET /health`
- `POST /api/automation-diagnosis/session/start`
- `POST /api/automation-diagnosis/session/{session_id}/answer`
- `POST /api/automation-diagnosis/session/{session_id}/classify`

No existen todavia los endpoints pedidos con nombres:

- `POST /api/diagnosis/start`
- `POST /api/diagnosis/message`
- `POST /api/diagnosis/submit-checklist`
- `GET /api/diagnosis/session/:id`
- `POST /api/diagnosis/lead`

El servicio de dominio si tiene metodos no expuestos por HTTP:

- `get_session`.
- `capture_contact`.
- `finalize`.
- `debug`.
- `search_knowledge`.

### LiteLLM

Existe adapter real:

- `modules/automation_diagnosis/ai_interpreter.py`.
- `modules/automation_diagnosis/litellm_client.py`.

Variables:

- `TEAM360_AI_PROVIDER=mock|litellm|none`.
- `TEAM360_LITELLM_BASE_URL`.
- `TEAM360_LITELLM_API_KEY` / `LITELLM_API_KEY` / `LITELLM_MASTER_KEY`.
- `TEAM360_LITELLM_MODEL_ALIAS`.
- `TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL`.
- `TEAM360_LITELLM_TIMEOUT_SECONDS`.
- `TEAM360_LITELLM_FALLBACK_TO_MOCK`.

La metadata enviada a LiteLLM incluye organization, workspace, assistant instance, package, knowledge scope, session, correlation id, feature, phase y model alias.

### PostgreSQL

Existe modo activable:

- `AUTOMATION_DIAGNOSIS_REPOSITORY=memory|postgres`.
- `TEAM360_DB_URL`.

`PostgresAutomationDiagnosisService` delega logica al servicio in-memory y persiste snapshots. Limitacion documentada: continuidad de sesion entre reinicios/procesos aun depende del proceso hasta hidratar desde DB.

Migracion `004_team360_automation_diagnosis_runtime.sql` crea:

- `automation_diagnosis_sessions`.
- `automation_diagnosis_answers`.
- `automation_diagnosis_leads`.
- Soporte para `assistant_instances.assistant_code`.
- Seeds de worker definitions del paquete de venta/diagnostico.

### Diagnostico/automation existente

Existe Fase 1 operativa:

- Flujo guiado de 10 pasos (`guided_flow.py`).
- Interpretacion IA mock/LiteLLM.
- Knowledge simple desde Markdown fixtures.
- Retrieval simple in-memory.
- Scoring y clasificacion deterministica.
- Resultado visible e internal card.
- Eventos.
- Persistencia PostgreSQL activable.
- Smoke real LiteLLM (`scripts/smoke_automation_diagnosis_litellm.py`).
- E2E Playwright de flujo completo (`astro/e2e/diagnosis.spec.ts`).

### Faltante para endpoints objetivo

- Exponer alias/public contract `/api/diagnosis/*` o migrar frontend a ese contrato.
- Endpoint conversacional `message` que acepte texto libre, haga slot extraction y devuelva valor inmediato + missing slots.
- Endpoint `submit-checklist` que guarde solo datos faltantes y clasifique.
- Endpoint `GET session/:id` para recuperar/hidratar sesion, especialmente en modo PostgreSQL.
- Endpoint `lead` para contacto/CTA, usando `capture_contact` y persistencia.
- Soporte runtime para `mamamia360_sales_diagnosis`.
- Contrato de checklist dinamico derivado de L1 y slots, no lista fija de 10 pasos.

## 8. Propuesta de arquitectura minima real, no descartable

Mantener `automation_diagnosis` como modulo base. No crear otro motor.

Entidades recomendadas:

- `DiagnosisTemplate`: define el paquete/configuracion de diagnostico. Contiene L0/L1 internos, slots requeridos, reglas, locales soportados, CTA disponibles y version.
- `DiagnosisSession`: sesion publica o de consola. Siempre lleva organization/workspace/service/assistant_instance/package/knowledge_scope/locale/channel/correlation.
- `DiagnosisMessage`: historial conversacional. Permite auditar texto libre, respuestas del asistente y extracciones.
- `DiagnosisSlot`: dato requerido o inferible. Tiene valor, confianza, origen (`inferred`, `user_confirmed`, `checklist`), locale y `asked_at`.
- `DiagnosisChecklist`: view model dinamico de slots faltantes. No debe repetir slots inferidos con confianza suficiente.
- `DiagnosisResult`: resultado comercial/tecnico, scoring, factibilidad, impacto, complejidad, fuentes requeridas, automatizaciones sugeridas y proximos pasos.
- `LeadCapture`: evento/contacto comercial asociado a una sesion y CTA.
- `PartnerBranding` / `DistributorConfig`: configuracion visible y comercial por canal/partner.

L0/L1 internos:

- L0: resumen corto del tipo de diagnostico/servicio, por template y locale.
- L1: mapa operativo del diagnostico: dolores, fuentes, preguntas minimas, automatizaciones posibles, scoring, riesgos, CTA y slots.
- L2: documentos completos en knowledge scope cuando existan.

Multi idioma:

- Guardar `locale` y `direction` por session.
- `DiagnosisTemplate` debe tener textos localizados `es`, `en`, `he`.
- LLM puede interpretar en el idioma del usuario, pero la salida estructurada debe mantener claves canonicas.
- Para hebreo, UI necesita `dir="rtl"` por locale; Console ya soporta direction en `consoleContext`, pero la home publica no tiene seleccion runtime.

Separacion Organization / Workspace / Service:

- `Organization`: entidad comercial/contractual. Team360 y Mama Mia 360 son organizaciones.
- `Workspace`: contexto operativo. `team360_public_site` y `mamamia360_public_site` deberian existir como workspaces de canal publico.
- `Service`: resultado/paquete visible. El diagnostico debe aparecer como servicio activo en Console y como asistente embebible en canal publico.
- `AssistantInstance`: configuracion tecnica-comercial del asistente por workspace/canal.

## 9. Propuesta frontend concreta

### Archivos sugeridos

Nuevos:

- `SrvRestAstroLS_v1/astro/src/components/diagnosis/PublicDiagnosisAssistant.svelte`: isla conversacional publica reutilizable.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/DiagnosisConversation.svelte`: panel conversacional comun.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/DynamicChecklist.svelte`: checklist de slots faltantes.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/DiagnosisResultCard.svelte`: resultado comercial/tecnico.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/LeadCaptureCta.svelte`: CTA y captura de lead.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/types.ts`: tipos compartidos frontend.
- `SrvRestAstroLS_v1/astro/src/lib/api/diagnosisConversation.ts`: cliente nuevo para `/api/diagnosis/*`.
- `SrvRestAstroLS_v1/astro/src/lib/mock/diagnosisTemplates.ts`: mock inicial de templates y branding si se necesita demo sin backend.
- `SrvRestAstroLS_v1/astro/src/pages/partners/[partnerSlug]/index.astro` o `src/pages/p/[partnerSlug].astro`: landing configurable de partner.

Modificar:

- `src/pages/index.astro`: insertar asistente publico Team360.
- `src/pages/w/[workspaceId]/diagnosis/index.astro`: usar componente comun o adaptar `ConsoleDiagnosis` a conversacional.
- `src/components/console/diagnosis/ConsoleDiagnosis.svelte`: reemplazar flujo fijo por wrapper Console sobre componentes comunes.
- `src/lib/api/diagnosis.ts`: mantener compatibilidad o migrar gradualmente a `diagnosisConversation.ts`.
- `src/lib/mock/services.ts`: agregar servicios de diagnostico para Team360 y Mama Mia 360.
- `src/lib/mock/bootstrap.ts`: habilitar `diagnosis` en `partner_admin` si aplica.
- `src/components/global.js`: ampliar `BRAND` o mover a configs por canal.
- `src/lib/i18n/messages.es.ts`, `messages.en.ts`, `messages.he.ts`: textos de diagnostico/CTA.

### A) Insercion en home publica Team360

- Primer release: bloque conversacional bajo el hero con textarea libre y CTA "Analizar proceso".
- Payload inicial:
  - `assistant_instance_id: team360_sales_diagnosis`
  - `source_url`
  - `locale`
  - `visitor`
- Respuesta inmediata: resumen del problema interpretado, 2-3 oportunidades preliminares y aviso de datos faltantes.
- Luego mostrar `DynamicChecklist` solo con slots faltantes.
- Terminar con `DiagnosisResultCard` y CTA: solicitar revision, WhatsApp, agendar demo, enviar diagnostico.

### B) Insercion en pagina/landing Mama Mia 360

- Crear landing configurable por `partnerSlug`, no hardcodear por nombre.
- Resolver config:
  - brand name, logo, colores limitados, locale default, supported locales, WhatsApp/contacto, assistant instance.
- Para Mama Mia 360:
  - `assistant_instance_id: mamamia360_sales_diagnosis`.
  - locale `es|en|he`.
  - `lead_owner: Mama Mia 360`.
  - market Israel.
- El componente conversacional debe ser el mismo que Team360, con branding/config distinto.

### C) Uso dentro de Console como servicio activo

- Agregar servicio visible:
  - Team360: "Asistente Inteligente de Venta y Diagnostico".
  - Mama Mia 360: "Diagnostico Inteligente para red comercial".
- `/w/[workspaceId]/diagnosis` puede mostrar nuevas sesiones.
- `ServiceDetail` puede mostrar tabs:
  - Resumen.
  - Sesiones.
  - Leads.
  - Resultados.
  - Configuracion.
  - Tecnico (solo owner/operator).

### D) Flujo conversacional

1. Usuario escribe texto libre inicial.
2. Backend crea sesion, extrae slots e interpreta contexto.
3. UI muestra valor inmediato: resumen, hipotesis, posibles automatizaciones y riesgos preliminares.
4. UI genera checklist dinamico solo con faltantes.
5. Usuario completa/ajusta slots.
6. Backend clasifica/scoring.
7. UI muestra diagnostico:
   - factibilidad;
   - impacto;
   - complejidad;
   - datos/fuentes necesarias;
   - automatizaciones sugeridas;
   - proximos pasos comerciales;
   - CTA.

## 10. Propuesta backend concreta

### API

Nuevos o modificados:

- `backend/routes/diagnosis.py`: contrato publico nuevo `/api/diagnosis/*`.
- `backend/routes/diagnosis_schemas.py`: ampliar schemas HTTP para message/checklist/lead/session.
- `backend/app.py`: registrar nuevas rutas.

Endpoints:

- `POST /api/diagnosis/start`: crea sesion con `assistant_instance_id`, locale, channel, visitor y texto libre opcional.
- `POST /api/diagnosis/message`: guarda mensaje, extrae slots, responde valor inmediato y checklist faltante.
- `POST /api/diagnosis/submit-checklist`: guarda slots confirmados y genera resultado.
- `GET /api/diagnosis/session/{id}`: recupera sesion/resultados/mensajes/checklist.
- `POST /api/diagnosis/lead`: captura contacto/CTA y crea lead event.

Mantener temporalmente los endpoints actuales `/api/automation-diagnosis/*` para compatibilidad de E2E mientras se migra.

### Modelos/schemas

- `modules/automation_diagnosis/conversation.py`: `DiagnosisMessage`, roles, message events.
- `modules/automation_diagnosis/slots.py`: definicion/extraccion/merge de slots.
- `modules/automation_diagnosis/checklist.py`: generacion de checklist dinamico.
- `modules/automation_diagnosis/templates.py`: `DiagnosisTemplate`, L0/L1 interno versionado.
- `modules/automation_diagnosis/partner_configs.py`: configuracion de canales/partners.

### Repositorios

- `postgres_repository.py`: agregar lectura/hidratacion desde DB, mensajes, slots, result y lead events.
- Mantener SQL en repositories, no en rutas.
- En memory mode, agregar repositorios equivalentes para demo persistente en proceso.

### Servicios de diagnostico

- `service.py`: evolucionar de cuestionario fijo a orquestacion conversacional.
- Mantener scoring/clasificador deterministico actual.
- `guided_flow.py` puede convertirse en definicion de slots/checklist, no UI fija.

### LiteLLM

- Reutilizar `LiteLLMAIInterpreter`.
- Agregar extractor estructurado de slots:
  - `process_to_automate`
  - `business_pain`
  - `systems_involved`
  - `frequency_volume`
  - `rules_clarity`
  - `human_dependency`
  - `access_security`
  - `data_sensitivity`
  - `expected_result`
  - `economic_impact`
- La LLM propone señales; Team360 decide scoring/clasificacion.

### Persistencia PostgreSQL

Usar tablas existentes como base:

- `automation_diagnosis_sessions`.
- `automation_diagnosis_answers`.
- `automation_diagnosis_leads`.
- `core_events`.

Agregar migracion futura si hace falta:

- `automation_diagnosis_messages`.
- `automation_diagnosis_slots`.
- `partner_configs` o configuracion equivalente si no existe en core.
- `diagnosis_templates` si se quiere versionar L0/L1 desde DB.

### Mocks/stubs

- Mantener `AUTOMATION_DIAGNOSIS_REPOSITORY=memory` como demo navegable.
- Usar `TEAM360_AI_PROVIDER=mock` como fallback local.
- No inventar otro backend paralelo.

## 11. Modelo de datos sugerido

### `diagnosis_templates`

- `id uuid`
- `template_code text unique`
- `version int`
- `name text`
- `description text`
- `l0_jsonb jsonb`
- `l1_jsonb jsonb`
- `supported_locales text[]`
- `default_locale text`
- `allowed_package_ids_jsonb jsonb`
- `status text`
- `created_at_utc timestamptz`
- `updated_at_utc timestamptz`

### `diagnosis_sessions`

Puede mapearse inicialmente a `automation_diagnosis_sessions`.

- `id uuid`
- `public_session_id text unique`
- `template_id uuid`
- `workspace_id uuid`
- `service_id uuid nullable`
- `assistant_instance_id uuid`
- `automation_package_id uuid`
- `knowledge_scope_id uuid`
- `organization_code text`
- `workspace_slug text`
- `assistant_instance_code text`
- `site_channel text`
- `lead_owner text`
- `partner_id text nullable`
- `market_country text nullable`
- `locale text`
- `direction text`
- `status text`
- `source_url text`
- `visitor_jsonb jsonb`
- `result_jsonb jsonb`
- `created_at_utc timestamptz`
- `updated_at_utc timestamptz`

### `diagnosis_messages`

- `id uuid`
- `session_id uuid`
- `role text` (`user`, `assistant`, `system`)
- `content text`
- `locale text`
- `message_type text`
- `extracted_slots_jsonb jsonb`
- `metadata_jsonb jsonb`
- `created_at_utc timestamptz`

### `diagnosis_slots`

- `id uuid`
- `session_id uuid`
- `slot_key text`
- `value_jsonb jsonb`
- `confidence numeric`
- `source text` (`inferred`, `user_confirmed`, `checklist`, `system`)
- `status text` (`missing`, `inferred`, `confirmed`, `rejected`)
- `asked_at_utc timestamptz nullable`
- `confirmed_at_utc timestamptz nullable`
- `metadata_jsonb jsonb`
- unique `(session_id, slot_key)`

### `diagnosis_results`

Puede estar embebido en `automation_diagnosis_sessions.result_jsonb` al inicio.

- `id uuid`
- `session_id uuid unique`
- `classification text`
- `score_total int`
- `score_breakdown_jsonb jsonb`
- `feasibility text`
- `impact text`
- `complexity text`
- `automation_mode text`
- `recommended_package_type text`
- `suggested_automations_jsonb jsonb`
- `required_sources_jsonb jsonb`
- `risk_flags_jsonb jsonb`
- `blocked_actions_jsonb jsonb`
- `next_steps_jsonb jsonb`
- `created_at_utc timestamptz`

### `lead_events`

Puede mapearse a `automation_diagnosis_leads` + `core_events`.

- `id uuid`
- `session_id uuid`
- `workspace_id uuid`
- `assistant_instance_id uuid`
- `lead_owner text`
- `partner_id text nullable`
- `cta_type text`
- `contact_jsonb jsonb`
- `diagnosis_summary_jsonb jsonb`
- `status text`
- `consent boolean`
- `created_at_utc timestamptz`

### `partner_configs`

- `id uuid`
- `organization_id uuid nullable`
- `organization_code text`
- `partner_slug text unique`
- `display_name text`
- `market_country text`
- `supported_locales text[]`
- `default_locale text`
- `branding_jsonb jsonb`
- `contact_channels_jsonb jsonb`
- `assistant_instance_code text`
- `lead_owner text`
- `cost_center text`
- `status text`
- `created_at_utc timestamptz`
- `updated_at_utc timestamptz`

## 12. Riesgos tecnicos y comerciales

- Salida rapida bloqueada si se intenta redisenar todo: ya hay una Fase 1 funcional; conviene evolucionarla.
- El flujo actual empieza con boton y cuestionario fijo, no con texto libre.
- `GUIDED_STEPS` esta duplicado en frontend (`src/lib/api/diagnosis.ts`) y backend (`guided_flow.py`).
- `partner_admin` no tiene `diagnosis` habilitado en mocks aunque la registry lo permite.
- Mama Mia 360 esta documentado como invariante, pero no existe `mamamia360_sales_diagnosis` en `assistant_instances.py`.
- La home publica aun usa mailto como CTA real.
- No hay landing/config publica para partner/distribuidor.
- Multi idioma existe para navegacion (`es/en/he`) y direction, pero no para contenido del diagnostico, prompts visibles ni resultados.
- No hay tracking/analytics formal de conversion, CTA, abandono, idioma, partner o costo por lead.
- Modo PostgreSQL persiste snapshots, pero la continuidad/hidratacion de sesion desde DB sigue pendiente.
- Seguridad/permisos productivos de Console siguen mock; la documentacion `lat.md/console-multi-organization.md` advierte que UI filtering no es autorizacion.
- El contrato HTTP actual ignora campos desconocidos en `StartSessionRequest`; eso puede ocultar errores de scope si el cliente envia config incorrecta.

## 13. Plan de implementacion por fases cortas

### Fase 1: demo real navegable con mock persistente o backend simple

- Mantener backend actual en memory/postgres simple.
- Crear componente conversacional publico reutilizable.
- Agregar texto libre inicial + slot extraction mock/deterministica/LLM segun provider.
- Generar checklist dinamico desde slots faltantes.
- Insertar en home Team360.
- Agregar servicio mock de diagnostico en Console.
- Configurar `mamamia360_sales_diagnosis` en backend in-memory y landing partner basica.
- Habilitar `diagnosis` para `partner_admin`.

### Fase 2: backend persistente y LiteLLM

- Exponer `/api/diagnosis/*`.
- Persistir mensajes y slots.
- Hidratar sesiones desde PostgreSQL.
- Conectar `capture_contact` por HTTP.
- Mantener scoring deterministico.
- Repetir smoke LiteLLM y smoke LiteLLM+Postgres.

### Fase 3: multi partner / multi idioma

- Crear `PartnerBranding` / `DistributorConfig`.
- Landing configurable por partner.
- Textos visibles por `es/en/he`.
- Direction RTL en flujo publico.
- Configurar `mamamia360_sales_diagnosis` con lead owner/cost center/market.

### Fase 4: analytics, scoring y automatizacion comercial

- Eventos de conversion y abandono.
- Cost/latency logs por model call y partner.
- Pipeline comercial: lead status, asignacion, WhatsApp/demo/email.
- Scoring versionado por template.
- RAG real ArangoDB + Milvus segun `lat.md/ai-diagnosis-rag-runtime.md`.

## 14. Lista exacta de archivos a crear/modificar

Crear:

- `SrvRestAstroLS_v1/astro/src/components/diagnosis/PublicDiagnosisAssistant.svelte`: experiencia publica inicial.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/DiagnosisConversation.svelte`: conversacion comun.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/DynamicChecklist.svelte`: checklist dinamico.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/DiagnosisResultCard.svelte`: resultado visible.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/LeadCaptureCta.svelte`: CTA comercial.
- `SrvRestAstroLS_v1/astro/src/components/diagnosis/types.ts`: tipos frontend.
- `SrvRestAstroLS_v1/astro/src/lib/api/diagnosisConversation.ts`: cliente API nuevo.
- `SrvRestAstroLS_v1/astro/src/lib/mock/diagnosisTemplates.ts`: templates/config mock.
- `SrvRestAstroLS_v1/astro/src/pages/p/[partnerSlug].astro`: landing publica configurable de partner.
- `SrvRestAstroLS_v1/backend/routes/diagnosis.py`: endpoints `/api/diagnosis/*`.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/templates.py`: L0/L1 internos versionados.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/slots.py`: extraccion/merge de slots.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/checklist.py`: checklist faltante.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/conversation.py`: mensajes y respuesta inmediata.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/partner_configs.py`: configs Team360/Mama Mia iniciales.
- `SrvRestAstroLS_v1/backend/db/migrations/005_team360_diagnosis_conversation_slots.sql`: si se decide persistir mensajes/slots en tablas propias.
- `SrvRestAstroLS_v1/backend/tests/test_diagnosis_conversation_router.py`: contrato nuevo.
- `SrvRestAstroLS_v1/astro/e2e/diagnosis_conversation.spec.ts`: E2E texto libre + checklist + resultado.

Modificar:

- `SrvRestAstroLS_v1/astro/src/pages/index.astro`: insertar asistente Team360.
- `SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/diagnosis/index.astro`: usar experiencia nueva.
- `SrvRestAstroLS_v1/astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte`: adaptar o reemplazar cuestionario fijo.
- `SrvRestAstroLS_v1/astro/src/components/console/services/ServiceDetail.svelte`: mostrar sesiones/leads si el servicio es diagnostico.
- `SrvRestAstroLS_v1/astro/src/lib/mock/services.ts`: agregar servicios de diagnostico.
- `SrvRestAstroLS_v1/astro/src/lib/mock/bootstrap.ts`: habilitar diagnostico para partner.
- `SrvRestAstroLS_v1/astro/src/lib/mock/workspaces.ts`: agregar workspace publico si se refleja backend.
- `SrvRestAstroLS_v1/astro/src/lib/mock/organizations.ts`: no requiere cambio para Mama Mia, salvo metadata extra si se modela branding.
- `SrvRestAstroLS_v1/astro/src/lib/i18n/messages.es.ts`, `messages.en.ts`, `messages.he.ts`: textos.
- `SrvRestAstroLS_v1/backend/app.py`: registrar rutas nuevas.
- `SrvRestAstroLS_v1/backend/routes/diagnosis_schemas.py`: ampliar schemas.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/assistant_instances.py`: agregar `MAMAMIA360_SALES_DIAGNOSIS_CONFIG`.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/service.py`: agregar start/message/checklist/lead conversacional.
- `SrvRestAstroLS_v1/backend/modules/automation_diagnosis/postgres_repository.py`: lectura/hidratacion, mensajes, slots, leads.
- `SrvRestAstroLS_v1/backend/scripts/smoke_automation_diagnosis_litellm.py`: agregar modo conversacional o crear smoke separado.

## 15. Recomendacion final

Conviene poner el asistente primero en la home publica de Team360 y, en paralelo chico, dejarlo visible como servicio en Console. La razon: el objetivo comercial empieza en conversion publica, pero la arquitectura correcta se valida cuando la sesion queda atribuida a organization/workspace/service/assistant_instance y se puede operar desde Console.

No conviene empezar solo por Console: seria util internamente, pero no resuelve la mecanica de producto deseada para usuarios reales. Tampoco conviene empezar solo por home si no queda modelado como package/service/assistant instance, porque se reharia al integrar Mama Mia 360.

Minimo real para salir con Team360 y Mama Mia 360:

- Un solo motor `automation_diagnosis`.
- Dos assistant instances configuradas: `team360_sales_diagnosis` y `mamamia360_sales_diagnosis`.
- Un componente conversacional reutilizable.
- Texto libre inicial, respuesta inmediata, checklist dinamico, resultado y CTA.
- Persistencia memory/postgres simple con session/result/lead.
- Console mostrando el servicio y sus leads/sesiones.
- Config de partner para branding, idioma, lead owner y cost attribution.

## Decisiones documentadas relevantes

- `.agents/skills/team360-project/SKILL.md`: no crear rama `desarrollo`; usar `feature/console-backend-core` para desarrollo/backend; no tocar `team360_orquestador` salvo objetivo; SQL en repositories; `psycopg 3 async` directo.
- `lat.md/automation-diagnosis.md`: el asistente no es chatbot abierto; LLM enriquece, Team360 decide con scoring; primeras salidas `team360_sales_diagnosis` y `mamamia360_sales_diagnosis`.
- `lat.md/ai-diagnosis-rag-runtime.md`: primer runtime de diagnostico usa ArangoDB + Milvus + LiteLLM, con PostgreSQL como verdad operacional.
- `lat.md/customer-packaged-assistant-instance.md`: Team360 direct debe ser primera instalacion cliente real del paquete, no demo interna.
- `lat.md/console-multi-organization.md`: Mama Mia 360 es partner configurable; UI filtering no es autorizacion; Console usa un App Shell unico.
- `SrvRestAstroLS_v1/docs/status_actual.md`: Fase 1 de `automation_diagnosis` ya esta operativa con frontend real, API Litestar, LiteLLM, modo PostgreSQL, tests y smokes.

## Comandos ejecutados

```bash
pwd && git branch --show-current && git status --short && git log -1 --oneline
sed -n '1,220p' .agents/skills/team360-project/SKILL.md
sed -n '1,220p' SrvRestAstroLS_v1/docs/status_actual.md
sed -n '1,220p' lat.md/lat.md
sed -n '1,220p' lat.md/status_actual.md
find SrvRestAstroLS_v1/astro/src/pages -maxdepth 5 -type f | sort
find SrvRestAstroLS_v1/astro/src/components -maxdepth 5 -type f | sort
find SrvRestAstroLS_v1/astro/src/lib -maxdepth 5 -type f | sort
find SrvRestAstroLS_v1/astro/src/styles -maxdepth 4 -type f | sort
find SrvRestAstroLS_v1/backend -maxdepth 4 -type f | sort
sed -n '1,220p' SrvRestAstroLS_v1/astro/package.json
sed -n '1,220p' SrvRestAstroLS_v1/astro/astro.config.mjs
sed -n '1,620p' SrvRestAstroLS_v1/astro/src/pages/index.astro
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/pages/login.astro
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/pages/select-workspace.astro
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/diagnosis/index.astro
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/pages/w/[workspaceId]/services/[serviceId].astro
find SrvRestAstroLS_v1/astro/src/layouts -maxdepth 2 -type f -print -exec sed -n '1,120p' {} \;
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/components/console/AppShell.svelte
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/components/console/Sidebar.svelte
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/components/console/Topbar.svelte
sed -n '1,240p' SrvRestAstroLS_v1/astro/src/components/console/WorkspaceSwitcher.svelte
sed -n '1,520p' SrvRestAstroLS_v1/astro/src/components/console/services/ServiceDetail.svelte
sed -n '1,700p' SrvRestAstroLS_v1/astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/lib/api/diagnosis.ts
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/lib/navigation/registry.ts
sed -n '1,320p' SrvRestAstroLS_v1/astro/src/lib/navigation/derive.ts
sed -n '1,620p' SrvRestAstroLS_v1/astro/src/lib/mock/services.ts
sed -n '1,340p' SrvRestAstroLS_v1/astro/src/lib/mock/bootstrap.ts
sed -n '1,280p' SrvRestAstroLS_v1/astro/src/lib/mock/selectors.ts
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/lib/mock/users.ts
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/lib/mock/organizations.ts
sed -n '1,260p' SrvRestAstroLS_v1/astro/src/lib/mock/workspaces.ts
for f in SrvRestAstroLS_v1/astro/src/components/ui/*.svelte SrvRestAstroLS_v1/astro/src/components/ui/*.astro SrvRestAstroLS_v1/astro/src/components/ui/README.md; do ...; done
sed -n '1,240p' SrvRestAstroLS_v1/astro/src/styles/global.css
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/styles/marketing.css
sed -n '1,240p' SrvRestAstroLS_v1/astro/src/components/global.js
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/lib/i18n/locales.ts
sed -n '1,220p' SrvRestAstroLS_v1/astro/src/lib/i18n/index.ts
sed -n '1,260p' SrvRestAstroLS_v1/backend/README.md
sed -n '1,280p' SrvRestAstroLS_v1/backend/pyproject.toml
sed -n '1,280p' SrvRestAstroLS_v1/backend/app.py
sed -n '1,360p' SrvRestAstroLS_v1/backend/routes/automation_diagnosis.py
sed -n '1,280p' SrvRestAstroLS_v1/backend/routes/diagnosis_schemas.py
sed -n '1,360p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/schemas.py
sed -n '1,420p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/service.py
sed -n '1,320p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/guided_flow.py
sed -n '1,360p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/assistant_instances.py
sed -n '1,360p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/ai_interpreter.py
sed -n '1,420p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/postgres_repository.py
sed -n '1,380p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/postgres_service.py
sed -n '1,340p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/repository.py
sed -n '1,360p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/knowledge_connector.py
sed -n '1,300p' SrvRestAstroLS_v1/backend/modules/automation_diagnosis/litellm_client.py
rg -n "create table|automation_diagnosis|assistant_instances|automation_packages|knowledge_scopes|lead|partner|organization|workspace" SrvRestAstroLS_v1/backend/db/migrations/*.sql
sed -n '1,260p' SrvRestAstroLS_v1/backend/db/README.md
sed -n '1,260p' SrvRestAstroLS_v1/backend/scripts/README.md
sed -n '1,320p' SrvRestAstroLS_v1/backend/scripts/smoke_automation_diagnosis_litellm.py
find SrvRestAstroLS_v1/backend/modules/automation_diagnosis/fixtures -maxdepth 4 -type f | sort | ...
sed -n '1,260p' lat.md/automation-diagnosis.md
sed -n '1,260p' lat.md/ai-diagnosis-rag-runtime.md
sed -n '1,260p' lat.md/customer-packaged-assistant-instance.md
sed -n '1,260p' lat.md/console-multi-organization.md
sed -n '1,220p' SrvRestAstroLS_v1/astro/README.md
sed -n '1,220p' SrvRestAstroLS_v1/astro/playwright.config.ts
sed -n '1,260p' SrvRestAstroLS_v1/backend/tests/test_automation_diagnosis.py
sed -n '1,240p' SrvRestAstroLS_v1/backend/tests/test_automation_diagnosis_router.py
rg -n "mamamia|mama|Mamá|diagnosis|automation_diagnosis|team360_sales_diagnosis|assistant_instance" ...
date +%Y%m%d && git status --short && git branch --show-current && git log -1 --oneline
```

Nota: no se ejecutaron tests ni servidores; esta tarea fue de inspeccion e inventario.

# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-05-31

## Directorio de trabajo

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1`

## Estado general

Se inicializo la DB viva `team360` en PostgreSQL local y se aplicaron correctamente las migraciones `001_team360_core_schema.sql`, `002_team360_rbac_packages_workers_knowledge.sql` y `003_team360_pgvector_knowledge_embeddings.sql`. Tambien existe una Fase 1 aislada para `automation_diagnosis`, con IA via LiteLLM por adapter, knowledge scope propio, retrieval simple sobre documentos Markdown, scoring/classifier deterministico, fixtures y tests. Se documento la politica de driver DB runtime (`psycopg 3 async` directo como estandar). El backend Litestar productivo sigue pendiente de integracion.

## Acciones realizadas

### 2026-05-31 - Revisión UX, consistencia visual y preparación para diseño de Team360 Console

- Se auditó la consola mock en desktop, laptop, tablet, mobile y preview RTL.
- Se corrigió uso inválido de `class:list` dentro de componentes Svelte que impedía aplicar clases condicionales en drawer, navegación, banner y tabs.
- Se agregaron `/login` y `/select-workspace` como entradas explícitamente mock sin formularios, credenciales ni auth real.
- Se separó la audiencia visual `team360_operator` para conservar navegación técnica resumida sin exponer red global.
- Se agregaron cards mobile para reportes y clientes, labels operativos para estados, formato `Intl` para fechas/duraciones y estados vacíos reutilizables.
- Se pulieron foco visible, navegación por teclado en tabs, reduced motion, interacción táctil y overscroll del drawer.
- Se crearon `docs/console_design_review_inventory.md` y `docs/console_ux_visual_review_phase.md`.
- Se validó con `corepack pnpm check`, `corepack pnpm build`, smoke HTTP/DOM, capturas locales y medición CDP de overflow.
- Resultado: `0 errors`, `0 warnings`, `0 hints`; build estático OK con `111` páginas y sin overflow horizontal en rutas críticas.
- No se implementaron backend, auth real, permisos productivos, DB, migraciones ni AG-UI funcional.

### 2026-05-31 - Team360 Console servicios y pantallas mock concretas

- Se implementaron listas concretas de servicios, reportes, alertas, tareas y equipo usando fixtures sintéticos realistas.
- Se agregó detalle de servicio con tabs adaptadas por audiencia: cliente, partner y Team360 mock.
- Se agregaron settings de workspace solo lectura e integraciones placeholder sin conexiones reales.
- Se agregaron vistas técnicas mock de workers y runs con resúmenes seguros, ocultas en navegación y con guarda visual ante URL directa fuera del perfil Team360.
- Se ampliaron fixtures tipados con Automatización de Leads y CRM, Reporte Ejecutivo Semanal, Control de Stock y Publicaciones, Conciliación Bancaria Asistida y Agente de Atención Inicial.
- Se agregaron wrappers UI `SectionHeader`, `StatCard`, `StatusBadge` y `Tabs`, manteniendo DaisyUI encapsulado.
- El detalle operativo queda en `docs/console_services_reports_alerts_mock_phase.md`.
- Se validó con `corepack pnpm check`, `corepack pnpm build`, smoke HTTP local, smoke DOM local con Chrome headless y auditorías acotadas.
- Resultado: `0 errors`, `0 warnings`, `0 hints`; build estático OK con `109` páginas.
- No se implementaron backend, auth real, permisos productivos, DB, migraciones, descargas reales ni AG-UI funcional.

### 2026-05-31 - Team360 Console App Shell navegable con mock data

- Se creó `astro/src/layouts/ConsoleAppLayout.astro`, separado del layout público de marketing.
- Se creó `astro/src/components/console/` con App Shell Svelte, sidebar, topbar, switchers mock, breadcrumbs, banner de contexto, notificaciones, dashboard adaptativo y vistas de sección.
- Se agregó navegación declarativa en `astro/src/lib/navigation/`, derivada desde capacidades, módulos, workspace, organización activa y servicios contratados.
- Se crearon rutas mock estáticas bajo `/w/[workspaceId]/` para dashboard, red, servicios, resultados, operación técnica, reportes, alertas, tareas, equipo, soporte y configuración.
- Se materializaron tres experiencias de diseño: Team360 Admin, Partner Admin y Cliente Final.
- El selector de perfil queda rotulado como herramienta mock de diseño; no representa auth ni impersonation productivo.
- Se mantuvo `Mamá Mía 360` únicamente como fixture configurable de partner regional, sin branching arquitectónico.
- Se validó con `corepack pnpm check`, `corepack pnpm build`, smoke HTTP local, smoke Chrome headless local y auditorías acotadas.
- Resultado: `0 errors`, `0 warnings`, `0 hints`; build estático OK con `97` páginas.
- No se implementaron backend, DB, migraciones, auth real ni AG-UI funcional.

### 2026-05-31 - Team360 Console mock context e i18n base

- Se creó `astro/src/components/global.js` para centralizar URLs públicas, rutas, flags visibles, branding, locale default y perfil mock inicial; `global.d.ts` conserva tipado estricto.
- Se agregó `astro/src/lib/mock/` con organizaciones, workspaces, usuarios, servicios, reportes, alertas, tareas, runs, cards de dashboard y bootstrap tipado.
- Se agregaron perfiles mock `team360_admin`, `team360_operator`, `team360_support`, `partner_admin` y `client_admin`.
- Se modeló `Mamá Mía 360` únicamente como dato mock configurable del primer partner regional para Israel, sin branching de producto por nombre o región.
- Se agregó `astro/src/lib/i18n/` con base simple propia para español, inglés y hebreo, incluyendo resolución `ltr` / `rtl`.
- Se agregó `astro/src/stores/consoleContext.svelte.ts` con Runes para perfil, bootstrap, locale, direction, organización, workspace, permisos, servicios y notificaciones.
- El cambio de workspace reconstruye el bootstrap y valida scope para descartar contexto anterior.
- Se validó con `corepack pnpm check`, `corepack pnpm build`, `git diff --check` acotado, búsqueda de whitespace, revisión de lockfiles incompatibles y búsqueda de términos sensibles en runtime.
- No se implementaron App Shell visual, dashboards renderizados, auth real, backend, DB, migraciones ni AG-UI funcional.

### 2026-05-31 - Home comercial publica `team360.live` Fase 1

- Se reemplazo el smoke visual de `/` por la primera home comercial publica de Team360.
- Se creo `PublicMarketingLayout.astro`, separado de layouts futuros de autenticacion y consola.
- Se agregaron componentes Astro de marketing para marca, header, footer, encabezados de seccion y panel conceptual del hero.
- Se agrego `LinkButton.astro` como wrapper UI minimo para CTAs enlazables con DaisyUI encapsulado.
- La home presenta diagnostico, implementacion gradual, medicion, casos de uso, partners y contacto por email sin promesas excesivas.
- Se valido con `corepack pnpm check`, `corepack pnpm build`, smoke local desktop y mobile, busqueda de referencias prohibidas y `git diff --check`.
- No se implementaron backend, autenticacion real, consola, App Shell, AG-UI funcional, DB ni migraciones.

### 2026-05-31 - Frontend Team360 Fase 1 Astro, Svelte, Tailwind y DaisyUI

- Se completo el scaffold real en `SrvRestAstroLS_v1/astro/`.
- Se fijo `packageManager: pnpm.5.0` y se genero `pnpm-lock.yaml` exclusivamente con pnpm.
- Se agrego `pnpm-workspace.yaml` con `allowBuilds` restrictivo para `esbuild` y `sharp`, segun politica pnpm 11.
- Se configuro Astro 6 con Svelte 5, TypeScript strict, Tailwind CSS 4 via `/vite` y DaisyUI 5 CSS-first.
- Se creo el tema neutral `team360` y wrappers UI iniciales: Alert, Badge, Button, Card y Loading.
- Se reservo `src/lib/agui/` sin transporte ni integracion funcional.
- Se movio un README placeholder fuera de `src/pages/` para evitar una ruta accidental.
- No se implementaron pantallas finales, App Shell, autenticacion, navegacion contextual, backend, DB ni migraciones.

### 2026-05-31 - Politica frontend pnpm, DaisyUI 5 y wrappers Team360 — SOLO DOCUMENTACION

- Se agrego `docs/frontend/team360-package-manager-and-ui-policy.md`.
- Se agrego `docs/adr/ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`.
- Se fijo pnpm como package manager frontend obligatorio.
- Se fijo Tailwind CSS 4 + DaisyUI 5 CSS-first como stack UI inicial obligatorio.
- Se fijo el encapsulamiento DaisyUI detras de wrappers Team360 en `src/components/ui/`.
- No se implemento codigo, `package.json`, dependencias, componentes, rutas, build, migraciones ni cambios en DB.

### 2026-05-31 - Correccion documental frontend DaisyUI 5 + Tailwind 4 — SOLO DOCUMENTACION

- Se corrigio la premisa incorrecta de incompatibilidad entre DaisyUI 5 y Tailwind 4.
- Se documento Tailwind CSS 4 + DaisyUI 5 como combinacion valida con integracion CSS-first y wrappers Team360.
- Se mantuvo la restriccion de no reutilizar `tailwind.config.cjs`, `postcss.config.cjs` legacy ni tema `vertice360`.
- No se implemento codigo, paquetes, componentes, rutas, build, migraciones ni cambios en DB.

### 2026-05-31 - App Shell y layouts base de Team360 Console — SOLO DOCUMENTACION

- Se agrego `docs/ux/team360-console-app-shell-and-layout-system.md`.
- Se agrego `docs/adr/ADR-003-team360-console-app-shell-and-layout-system.md`.
- Se documentaron App Shell, sidebar, topbar, switchers, breadcrumbs, layouts reutilizables, estados de UI, responsive y bootstrap esperado.
- Se amplio `lat.md/console-multi-organization.md` con el invariante estable de shell reutilizable y descarte de estado obsoleto.
- No se implementaron pantallas, componentes, rutas, build, migraciones ni cambios en DB.

### 2026-05-31 - Modelo de navegacion contextual para Team360 Console — SOLO DOCUMENTACION

- Se agrego `docs/ux/team360-console-navigation-model.md`.
- Se agrego `docs/adr/ADR-002-team360-console-navigation-by-role.md`.
- Se documento navegacion por tipo de organizacion, rol, permisos efectivos, workspace activo, servicios contratados y modulos habilitados.
- Se definieron App Shell adaptable, selector de contexto, tabs por servicio, wireframes textuales e implicancias para Astro, Svelte 5 con Runes y backend.
- Se amplio `lat.md/console-multi-organization.md` con el invariante estable de navegacion contextual.
- No se implementaron pantallas, componentes, rutas, navegacion funcional, migraciones ni cambios en DB.

### 2026-05-31 - Decision UX y arquitectura base para Team360 Console — SOLO DOCUMENTACION

- Se documento la separacion entre `team360.live` como sitio comercial publico y `console.team360.live` como plataforma privada operativa.
- Se definio Team360 Console como plataforma multi-organizacion para Team360, partners regionales y clientes finales.
- Se registro a `Mamá Mía 360` como primera instancia configurable de Partner / Distribuidor Regional para Israel, sin reglas hardcodeadas.
- Se documento la diferencia entre `organization` y `workspace`, el alcance delegado de partners y la brecha del schema actual.
- Se agregaron guia extensa en `docs/ux/`, ADR en `docs/adr/` e invariante estable en `lat.md/console-multi-organization.md`.
- No se implementaron pantallas, componentes, rutas, migraciones ni cambios en DB.

### 2026-05-29 - Documentacion de politica DB driver psycopg 3 async

- Se creo `lat.md/postgres-driver-policy.md` como regla estable de arquitectura.
- Define `psycopg 3 async` como driver runtime estandar de Team360, con `psycopg_pool.AsyncConnectionPool`.
- Prohibe SQLAlchemy/SQLModel como fuente de verdad del core; solo evaluables para herramientas perifericas.
- Prohibe asyncpg como driver base salvo workers especializados con metrica de cuello de botella.
- Define patron de repositorios, unit-of-work, estructura de modulos `backend/modules/db/`.
- Establece relacion con pgvector (mismo psycopg layer) y LangGraph PostgresSaver (schema `langgraph` separado, mismo driver, pool independiente).
- Se actualizaron `lat.md/lat.md`, `lat.md/status_actual.md`, `.agents/skills/team360-project/SKILL.md` (reglas 11-14) y `AGENTS.md` (referencia breve).
- No se toco DB, no se aplicaron migraciones, no se modificaron migraciones 001/002/003, no se toco v360, litellm ni temp1.txt.
- Proximo paso recomendado: disenar `backend/modules/db/` con pool, transaccion y repositorios base.

### 2026-05-29 - Aplicacion migracion 003 pgvector knowledge embeddings sobre team360

- Se verifico preflight antes de aplicar:
  - conexion sanitizada apunta a `team360`;
  - migracion 002 seguia aplicada (`knowledge_scopes`, `knowledge_documents`, `knowledge_chunks`, `package_workers`, `credential_references` presentes);
  - `vector` esta disponible en el servidor como `0.8.2`;
  - tablas objetivo de 003 no existian previamente;
  - `python3 -m py_compile` sobre `backend/scripts/audit_team360_schema.py` OK;
  - `git diff --check` sobre archivos 003/auditor/doc OK.
- Se creo `backend/db/migrations/003_team360_pgvector_knowledge_embeddings.sql`.
- `psql` no se uso; la aplicacion se ejecuto con `psycopg` en transaccion explicita sobre `team360`, con rollback automatico ante error.
- Resultado de aplicacion: `migration_003_applied=ok`.
- Se instalo `vector` en `team360` y quedo en version `0.8.2`.
- Se crearon `knowledge_embedding_models`, `knowledge_chunk_embeddings` y la view `knowledge_ready_chunks`.
- Se creo el indice vectorial `idx_kce_embedding_hnsw_cosine` con HNSW + `vector_cosine_ops`, parcial para `embedding_status = 'ready'`.
- Se cargo solo el seed tecnico `knowledge_embedding_models.default_1536` para `openai/text-embedding-3-small`; no se llamo a OpenAI ni se guardaron API keys.
- Se actualizo `backend/scripts/audit_team360_schema.py` para validar la 003: extension `vector`, tablas, view, constraints, indices, seed, duplicados chunk/modelo, status invalidos, embeddings `ready` con vector NULL y consistencia basica de `knowledge_scope_id`.
- Auditoria post-003:
  - checks pasados: 88;
  - checks fallidos: 0;
  - tablas base esperadas 001+002+003: 48/48;
  - view `knowledge_ready_chunks`: OK;
  - seed `default_1536`: OK;
  - indice HNSW cosine: OK;
  - sin embeddings `ready` con vector NULL;
  - sin duplicados chunk/modelo;
  - sin datos reales de clientes ni embeddings cargados.
- No se tocaron `v360`, `litellm`, `postgres`, `.codex` ni `temp1.txt`.
- Proximo paso recomendado: disenar la fase de runtime para generar/cargar embeddings o, si hay un workflow concreto, disenar `004_team360_langgraph_checkpointing.sql` separado del modelo core.

### 2026-05-29 - Aplicacion migracion 002 sobre team360

- Se verifico preflight antes de aplicar:
  - conexion sanitizada apunta a `team360`;
  - migracion 001 seguia aplicada (`core_workspaces`, `core_users`, `core_events`, `task_runs` presentes);
  - migracion 002 todavia no estaba aplicada (`0/6` tablas sonda de 002 presentes);
  - `python3 -m py_compile` sobre `backend/scripts/audit_team360_schema.py` OK;
  - `git diff --check` sobre archivos relevantes OK.
- `psql` no estaba disponible en el entorno, por lo que se aplico 002 con `psycopg` en transaccion explicita sobre `team360`, con rollback automatico ante error.
- Resultado de aplicacion: `migration_002_applied=ok`.
- Se ejecuto auditoria post-002 con `backend.scripts.audit_team360_schema` usando conexion sanitizada.
- Resultado de auditoria:
  - checks pasados: 74;
  - checks fallidos: 0;
  - tablas esperadas 001+002: 46/46;
  - columnas nuevas de `task_runs` presentes: `automation_package_id`, `package_worker_id`, `area_id`, `assigned_user_id`, `required_permission`, `approval_status`;
  - `chk_task_runs_approval_status` OK sin `bypassed`;
  - indices unicos parciales criticos OK, incluidos `uq_ksb_default_internal`, `uq_ksb_default_workspace` y `uq_ksb_default_per_entity`;
  - FKs esperadas encontradas: 5/5;
  - `chk_ksb_convention` OK;
  - no se detectaron defaults ambiguos en `knowledge_scope_bindings`;
  - `credential_references.metadata_jsonb` sin claves sospechosas;
  - consistencia multi-tenant basica sin datos operativos que verificar.
- Tablas principales creadas por 002: RBAC, planes/features, subscriptions, assistant instances, automation packages, workers, credential references, knowledge scopes/bindings/documents/chunks.
- Datos cargados por seeds: 20 permisos, 4 planes, 17 features, 49 asignaciones plan-feature y 8 worker definitions.
- No se cargaron datos reales de clientes; las tablas operativas de 002 quedaron en 0 filas.
- No se tocaron `v360`, `litellm`, `postgres`, `.codex` ni `temp1.txt`.

### 2026-05-29 - Decision arquitectonica PostgreSQL 18, pgvector y LangGraph — SOLO DOCUMENTACION

- Se agrego `lat.md/postgres-ai-persistence.md` para documentar PostgreSQL 18 como nucleo transaccional unico de Team360.
- Se definio que el modelo core de Team360 vive en tablas propias (`core_workspaces`, `core_users`, `core_events`, `task_runs`, `automation_packages`, `package_workers`, `knowledge_scopes`, `knowledge_documents`, `knowledge_chunks`).
- Se documento que pgvector queda para una fase posterior sugerida `003_team360_pgvector_knowledge_embeddings.sql`.
- Se documento que LangGraph PostgresSaver queda para una fase posterior sugerida `004_team360_langgraph_checkpointing.sql`, idealmente en schema `langgraph`.
- Se fijo que LangGraph checkpoints no reemplazan `task_runs` ni `core_events`; solo guardan estado interno/reanudable de workflows/agentes.
- Se agrego precaucion sobre `pg_checkpointer`: no asumir existencia ni depender de esa extension sin verificar `pg_available_extensions`.
- Se actualizo `lat.md/lat.md`, `lat.md/status_actual.md` y `docs/postgresql_live_team360_setup.md`.
- No se toco la DB, no se aplicaron migraciones y no se modifico la migracion 002.

### 2026-05-29 - Auditor 002 v3 con predicates semanticos — NO APLICADA

- Se corrigio `backend/scripts/audit_team360_schema.py` para dejar de comparar predicates de indices parciales por substring literal contra `pg_indexes.indexdef`.
- El auditor ahora consulta `pg_index`, `pg_get_indexdef(pg_index.indexrelid)` y `pg_get_expr(pg_index.indpred, pg_index.indrelid)`.
- Para `uq_ksb_default_internal`, `uq_ksb_default_workspace` y `uq_ksb_default_per_entity`, valida que los indices existan sobre `knowledge_scope_bindings`, sean `UNIQUE`, sean parciales y cumplan semanticamente los tipos esperados junto con `is_default = true`.
- Se mantuvo la regex/lista de claves sospechosas para `credential_references.metadata_jsonb`: password, passwd, token, api_key, apikey, secret, private_key, credential.
- Se corrigieron textos stale en `docs/postgresql_002_rbac_packages_workers_knowledge_design.md` y la frase de defaults para indicar "a lo sumo una" fila default.
- **002 v3 sigue NO aplicada sobre team360.** No se toco DB team360, v360, litellm ni temp1.txt.

### 2026-05-28 - Inicializacion DB viva Team360 con migracion 001

- Se elimino la DB temporal `team360_dev` creada durante la preparacion inicial, por pedido explicito de usar `team360` como DB viva.
- Se creo la DB PostgreSQL `team360` en el servidor local activo en puerto `5432`.
- No se modificaron las DB `v360`, `litellm` ni `postgres`.
- Se aplico `backend/db/migrations/001_team360_core_schema.sql` sobre `team360`.
- La migracion quedo aplicada completa: 24 tablas versionadas, 51 indices versionados, 58 foreign keys, 24 primary keys, 9 unique constraints y `pgcrypto 1.4` instalado.
- La migracion usa `gen_random_uuid()` y no usa `uuidv7()`.
- Todas las tablas quedaron con `0` filas; no se cargaron seeds ni datos reales.
- Se documento el setup y audit en `docs/postgresql_live_team360_setup.md`.
- No se diseno ni aplico migracion `002`; queda como siguiente fase sobre la DB viva ya inicializada.

### 2026-05-28 - automation_diagnosis Fase 1 con LiteLLM, RAG simple y classifier deterministico

- Se creo el modulo aislado `backend/modules/automation_diagnosis/`.
- El modulo implementa una experiencia guiada de diagnostico de automatizacion, no un chatbot abierto.
- Se agrego adapter de IA con `LiteLLMAIInterpreter` como camino real inicial y `MockAIInterpreter`/`NoopAIInterpreter` para tests o fallback.
- Se creo el knowledge scope interno `ks_team360_automation_diagnosis`.
- Se agrego carga de documentos Markdown, chunking y retrieval keyword simple para Fase 1.
- Se dejaron campos y nombres preparados para GraphRAG futuro: `retrieval_mode`, `graph_enabled`, `entity_extraction_status` y `relation_extraction_status`.
- Se implementaron scoring y classifier deterministico para `standard_package`, `operational_automation`, `consulting_required` y `not_recommended`.
- El resultado interno produce paquete recomendado, workers sugeridos, config requerida de `package_worker`, refs de credenciales, scope de conocimiento, modo de automatizacion, riesgos, acciones bloqueadas y aprobacion humana.
- Se agregaron fixtures de knowledge y sesiones para las cuatro clasificaciones.
- Se agregaron funciones de ruta en `backend/routes/automation_diagnosis.py`, preparadas para montarse luego en Litestar.
- Se documento la fase en `docs/automation_diagnosis_fase1.md`.
- No se tocaron `team360_orquestador`, AG-UI/SSE, Mercado Libre browser lab, messaging providers ni archivos sensibles.
- No se guardaron secretos planos.
- Se creo `lat.md/` en la raiz del repo como capa de arquitectura viva para Team360, siguiendo el patron usado en JudaismoenVivo.
- Se agregaron anchors `@lat` en puntos clave del modulo `automation_diagnosis`.
- Se formalizo el uso de `lat.md/` en `AGENTS.md` y en `.agents/skills/team360-project/SKILL.md` para proximos agentes y cambios de arquitectura.


### 2026-05-20 - Evidencia manual Kommo para arquitectura RPA

- Se incorporo evidencia manual de Kommo Dashboard, Inbox/Chats y `Analitica > Registro de actividades` dentro de `automation_mario_castro/docs/`.
- Hallazgo principal: `Registro de actividades` expone una tabla estructurada de eventos con fecha, usuario, objeto, nombre, actividad, valor previo y valor posterior.
- Se confirmaron eventos utiles para KPIs: nuevo lead, mensaje entrante/saliente, conversacion comenzada/cerrada, cambio de etapa, fuente lead, emprendimiento/proyecto y lead eliminado.
- Se agrego `automation_mario_castro/src/kommo/inspect_activity_log.py` para validar filtro, export o captura estructurada de filas.
- Decision tecnica: usar Registro de actividades Kommo como fuente candidata primaria para eventos historicos; Dashboard queda como control agregado e Inbox como evidencia secundaria de canal/respuesta.
- No se guardaron screenshots reales ni credenciales en el repo.

### 2026-05-20 - Laboratorio RPA exploratorio para Kommo, Facebook y Meta Ads de Mario Castro

- Se creo `automation_mario_castro/` como laboratorio aislado de browser automation para auditoria tecnica previa a una automatizacion productiva.
- Objetivo del laboratorio:
  - analizar el Excel `KPIs_CEO_Proyectos_Inmobiliarios_COMPLETO.xlsx`;
  - mapear KPIs contra fuentes probables;
  - preparar probes Playwright para Kommo, Facebook Page/Inbox y Meta Ads Manager;
  - documentar factibilidad y flujo MVP sin usar APIs.
- Se agregaron scripts Python para:
  - analizar el workbook desde `docs/clients/mario_castro/KPIs_CEO_Proyectos_Inmobiliarios_COMPLETO.xlsx`;
  - iniciar login exploratorio en Kommo y Facebook leyendo credenciales desde `.env` o variables de entorno;
  - inspeccionar dashboard, leads, pipeline y modulo WhatsApp/conversaciones en Kommo;
  - inspeccionar paginas Facebook, Inbox/Meta Business Suite y Ads Manager;
  - generar `runtime/inspect/data_inventory.json`.
- Se agrego helper reutilizable de Playwright con `storage_state`, screenshots, timeouts largos y pausa HITL/manual ante 2FA, captcha o verificacion.
- Se documento analisis de Excel, matriz KPI -> fuente probable, mapa de fuentes, factibilidad Playwright y flujo MVP recomendado.
- No se guardaron credenciales reales en archivos del repo.
- No se ejecuto login real contra Kommo/Facebook en esta etapa.
- No se integro este laboratorio con `team360_orquestador`, AG-UI, backend productivo ni frontend.

### 2026-05-13 - Reubicacion del documento SAP Business One fuera de docs tecnicos de runtime

- Se movio `sap_b1_desktop_automation_factibilidad.md` desde `SrvRestAstroLS_v1/docs/` hacia `docs/analisis-tecnico/`.
- Motivo:
  - el documento es de factibilidad tecnico-comercial interna;
  - no documenta runtime, backend, Astro, migraciones ni implementacion productiva actual;
  - corresponde a la zona de analisis tecnico no operativo.
- Se actualizaron los status locales de `docs/` y `docs/analisis-tecnico/`.
- Se limpio una entrada duplicada previa sobre la ampliacion del documento SAP.
- No se tocaron archivos funcionales.

### 2026-05-13 - Probes Mercado Libre para lista de preguntas y borrador de respuesta

- Se incorporo inspeccion superficial de la lista visible de preguntas del vendedor.
- Se agrego `smoke_questions_list_inspect.py` para:
  - reutilizar sesion persistente;
  - abrir preguntas del vendedor;
  - detectar lista, filtros, empty state y muestra superficial de items;
  - guardar screenshot, storage state y reporte de inspeccion.
- Se amplio `smoke_reply_draft.py` para validar borradores de respuesta sin publicar:
  - localizar un item con accion de responder;
  - completar textarea;
  - validar estado del boton;
  - limpiar el borrador por defecto salvo `--keep-draft`.
- Se actualizaron helpers/selectores/configuracion del browser lab para soportar inspeccion de preguntas.
- Se actualizaron README y `login-flow.md` con los probes disponibles.
- No se integraron estos probes con `team360_orquestador`, AG-UI ni frontend.

### 2026-05-13 - Documento de factibilidad SAP Business One Desktop Client

- Se creo inicialmente `sap_b1_desktop_automation_factibilidad.md`.
- El documento analiza la factibilidad tecnica y comercial de automatizar SAP Business One v10 Desktop Client sin depender inicialmente de:
  - certificacion SAP;
  - marketplace SAP;
  - add-on oficial;
  - acceso directo a HANA/SQL.
- Se cubrieron las opciones:
  - Service Layer;
  - DI API / SDK local;
  - RPA Desktop sobre SAP Business One Client;
  - modelo asistido por RDP;
  - fases recomendadas de evolucion;
  - riesgos, mitigaciones y arquitectura minima propuesta.
- Decision registrada en el documento:
  - salida comercial rapida con RPA Desktop asistido en sesion del usuario por RDP;
  - evolucion tecnica a VM dedicada y usuario BOT;
  - robustez profesional posterior con DI API / Service Layer;
  - no prometer autonomia total ni solucion SAP certificada al inicio.
- No se genero codigo funcional ni se tocaron backend, Astro, `team360_orquestador`, AG-UI o laboratorio browser de Mercado Libre.

### 2026-05-13 - Status locales por directorio documental

- Se agrego la convencion de `status_actual.md` local por directorio documental activo.
- Se crearon status locales en:
  - `docs/`
  - `docs/negocio/`
  - `docs/estrategia/`
  - `docs/analisis-tecnico/`
  - `docs/templates/`
  - `data/reports/`
  - `data/reports/mercadolibre/`
  - `data/reports/mercadolibre/netzaj-racing/`
  - `data/reports/snapshots/`
- Se actualizo `AGENTS.md` para que proximos agentes sepan que cada status local describe el ultimo estado de su propio directorio.
- No se tocaron archivos funcionales, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser de Mercado Libre.

### 2026-05-13 - Orden documental no tecnico y reportes

- Se reorganizo documentacion no tecnica de Team360 en `docs/`:
  - `docs/negocio/` para contexto comercial y analisis de negocio.
  - `docs/estrategia/` para continuidad, estrategia e inventarios tecnico-negocio.
  - `docs/analisis-tecnico/` para analisis tecnico no operativo ni runtime.
- Se agruparon reportes y evidencias generadas en `data/reports/`:
  - `data/reports/mercadolibre/netzaj-racing/` para relevamientos, playbook e intents del seller NETZAJ RACING.
  - `data/reports/snapshots/` para snapshots historicos.
- Se agregaron indices `README.md` en las carpetas documentales principales.
- Se actualizaron enlaces relativos afectados por los movimientos.
- No se tocaron archivos funcionales, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser de Mercado Libre.

### 2026-05-13 - Automatizacion browser para permisos GitHub en `iMotorSoft/concilia`

- Se uso browser automation sobre la web de GitHub para configurar el repositorio `iMotorSoft/concilia`.
- Se invito a `msamia@gmail.com`, que GitHub resolvio como usuario `@msamia`.
- La invitacion quedo pendiente de aceptacion:
  - `0 collaborators`
  - `1 invitation`
  - invitacion visible para `@msamia`
- Se creo y verifico una regla clasica de proteccion de rama para `main`.
- Configuracion verificada de la regla:
  - `Branch name pattern`: `main`
  - `Lock branch`: activo
  - `Do not allow bypassing the above settings`: desactivado
  - `Allow force pushes`: desactivado
  - `Allow deletions`: desactivado
- Efecto esperado:
  - colaboradores comunes no pueden modificar directamente `main`;
  - owner y administradores conservan bypass;
  - `@msamia` podra crear y actualizar ramas propias cuando acepte la invitacion, pero no deberia poder modificar `main`.

### 2026-05-13 - Observacion tecnica sobre diferencia entre intentos GPT-5.4 y GPT-5.5

- Intento anterior con GPT-5.4:
  - el login y la invitacion del colaborador funcionaron;
  - la UI de GitHub mostro el formulario de proteccion de rama con `main` y `Lock branch` cargados;
  - el click automatizado sobre `Create` no disparo el submit real del formulario;
  - no aparecio la navegacion de regreso a `settings/branches`;
  - por eso la regla de proteccion no quedo guardada.
- Intento posterior con GPT-5.5:
  - se diagnostico que el problema no era la configuracion elegida sino el disparo del submit en la UI automatizada;
  - primero se intento enviar el formulario por HTTP usando la sesion temporal, pero GitHub respondio `422` por proteccion anti-CSRF;
  - luego se envio el formulario desde el contexto real de la pagina con `requestSubmit()`;
  - esa variante si ejecuto el submit aceptado por GitHub y navego de vuelta a `settings/branches`;
  - despues se abrio `Edit` para verificar que la regla quedo guardada con `main` y `Lock branch` activo.
- Conclusion:
  - el fallo anterior fue operativo del flujo de browser automation contra una UI dinamica de GitHub;
  - el intento final funciono porque se uso el formulario real ya cargado por GitHub y se disparo el submit desde el contexto de la pagina, preservando las validaciones de sesion.

### 2026-05-13 - Ampliacion del documento SAP con licenciamiento, checklist, costos, monitoreo y rollback

- Se agregaron 5 secciones nuevas al documento `docs/analisis-tecnico/sap_b1_desktop_automation_factibilidad.md`:
  - **Seccion 11 - Licenciamiento SAP**: tipos de licencia SAP B1 (Professional, Limited, Indirect Access, Partner) y recomendaciones por fase, con regla practica para evitar riesgos de licenciamiento.
  - **Seccion 12 - Checklist de relevamiento**: checklist estructurada para evaluar prospectos en primera conversacion, cubriendo entorno, procesos, infraestructura y aceptacion comercial, con criterio de aptitud rapida para Fase 1.
  - **Seccion 13 - Estimaciones de esfuerzo y costo**: tablas por fase con tiempos, costos Team360 e infraestructura (cliente), mas estructura de costos sugerida (one-time, por flujo, soporte mensual).
  - **Seccion 14 - Monitoreo remoto**: heartbeat, logs estructurados JSON, evidencias visuales, alertas automaticas, canales (dashboard/webhook/email) y consideraciones de seguridad con modo offline.
  - **Seccion 15 - Rollback operativo**: principios, tabla por tipo de operacion (pre-carga, maestro, actualizacion), operaciones excluidas de rollback automatico, procedimiento general, checklist pre y post ejecucion.
- El documento paso de 600 a 868 lineas.
- No se toco codigo funcional, backend, Astro, `team360_orquestador`, AG-UI ni laboratorio browser.

### 2026-05-01 - Base documental y migration inicial de Team360

- Se creo `docs/team360_multi_whatsapp_multi_llm_architecture.md`.
- Se creo `docs/team360_postgres_dev_setup.md`.
- Se creo `backend/db/migrations/001_team360_core_schema.sql`.

### Estado observado en esta etapa

- Team360 todavia no tiene backend Litestar productivo completo.
- `backend/db/team360_pgvector_catalog.sql` existe, pero esta marcado como futuro opcional y no integrado al runtime actual.
- `backend/globalVar.py` contiene configuracion basica y variables DB/OpenAI futuras opcionales.
- No se implementaron repositorios Python ni rutas nuevas.
- No se tocaron archivos funcionales.

### PostgreSQL dev propuesto

- DB local sugerida: `team360_dev`.
- Usuario dev sugerido: `team360_dev`.
- Puerto local sugerido: `54329`.
- DSN backend sugerido:

```bash
export TEAM360_DB_URL="postgresql+psycopg://team360_dev:team360_dev_password@localhost:54329/team360_dev"
```

- DSN CLI sugerido:

```bash
export TEAM360_DB_URL_PSQL="postgresql://team360_dev:team360_dev_password@localhost:54329/team360_dev"
```

### Migration inicial

Archivo:

`backend/db/migrations/001_team360_core_schema.sql`

Incluye estructura inicial para:

- workspaces
- usuarios placeholder
- eventos core
- communication providers
- WhatsApp channels
- WhatsApp numbers
- provider credentials
- webhook bindings
- routing rules
- message threads
- message events
- migracion de numeros WhatsApp
- LLM providers
- LLM credentials
- LLM model profiles
- workspace LLM settings
- automation LLM policy
- fallback policy
- usage logs
- cost estimates
- scheduled tasks
- task runs
- local runners
- runner heartbeats

## Validacion

- Se audito `team360` contra `001_team360_core_schema.sql`: no hay tablas, indices ni extensiones versionadas faltantes.
- Se ejecuto `python3 -m py_compile` sobre los scripts del laboratorio `automation_mario_castro/`.
- Se ejecuto `python3 src/excel/analyze_workbook.py` y genero `automation_mario_castro/runtime/inspect/excel_inventory.json`.
- Se ejecuto `python3 src/reports/build_data_inventory.py` y genero `automation_mario_castro/runtime/inspect/data_inventory.json`.
- Se verifico que `.env.example` no contiene credenciales reales.
- No se probaron los logins contra Kommo/Facebook porque requieren configuracion local de `.env` e intervencion humana si aparece 2FA.
- Se agrego pero no se ejecuto `kommo.inspect_activity_log`; requiere sesion Kommo local.
- Se verifico que Playwright no esta instalado en el entorno Python actual; los probes quedan preparados pero requieren instalar dependencias antes de ejecutarse.
- Se verifico que `sap_b1_desktop_automation_factibilidad.md` existe en `docs/analisis-tecnico/`.
- Se verifico que ya no queda ubicado en `SrvRestAstroLS_v1/docs/`.
- Se ejecuto `python3 -m py_compile` sobre los modulos Python tocados del browser lab Mercado Libre.
- `git diff --check` paso sin errores para el commit de probes Mercado Libre.
- `git diff --check` paso sin errores para el documento SAP B1.
- Se verifico la estructura de directorios documentales activos antes de crear status locales.
- `git diff --check` paso sin errores para los cambios documentales.
- Se verifico la estructura final de `docs/` y `data/reports/`.
- Se buscaron referencias internas a documentos movidos y se actualizaron enlaces relativos relevantes.
- Se verifico en GitHub que la regla de rama existe entrando a `Settings > Branches > Edit`.
- Se verifico que el formulario editado muestra `Branch name pattern = main` y `Lock branch` activo.
- Se verifico que `msamia@gmail.com` quedo como invitacion pendiente a `@msamia`.
- `git diff --check` paso sin errores para los archivos creados.
- Se verifico que la migration contiene las tablas principales pedidas.
- No se ejecuto la migration porque `psql` no estaba disponible en el `PATH` de esta sesion.

## Pendientes recomendados

1. Levantar PostgreSQL local con Docker.
2. Aplicar `backend/db/migrations/001_team360_core_schema.sql`.
3. Definir herramienta formal de migrations.
4. Crear seed dev sin secretos reales.
5. Integrar `TEAM360_DB_URL` al backend cuando exista runtime Litestar productivo.
6. Crear repositorios Python en una fase posterior.

### 2026-05-29 - Correccion migracion 002 v3 — bloqueante knowledge_scope_bindings resuelto — NO APLICADA

- GPT-5.5 reviso v2 y encontro bloqueante: `knowledge_scope_bindings` permitia defaults ambiguos con `bound_entity_id IS NULL`.
- Correcciones aplicadas en v3:
  - **CHECK constraint `chk_ksb_convention`**: reemplaza al viejo `chk_knowledge_scope_bindings_type`. Valida nulabilidad segun `binding_type`:
    - `internal` -> workspace_id NULL, bound_entity_id NULL
    - `workspace` -> workspace_id NOT NULL, bound_entity_id NOT NULL, bound_entity_id = workspace_id
    - `assistant_instance`/`automation_package`/`package_worker` -> workspace_id NOT NULL, bound_entity_id NOT NULL
  - **Indices unicos parciales** reestructurados:
    - `uq_ksb_default_internal`: `WHERE binding_type = 'internal' AND is_default = true`
    - `uq_ksb_default_workspace`: `UNIQUE(workspace_id) WHERE binding_type = 'workspace' AND is_default = true` (NUEVO)
    - `uq_ksb_default_per_entity`: `UNIQUE(binding_type, bound_entity_id) WHERE binding_type IN ('assistant_instance','automation_package','package_worker') AND is_default = true` (mas preciso)
  - **DO blocks**: filtros `conrelid` en pg_constraint y `table_schema = 'public'` en information_schema para evitar falsos positivos.
  - **audit_team360_schema.py**: nueva seccion 7 de validacion de knowledge_scope_bindings; validacion de predicate en indices; claves sospechosas ampliadas (passwd, apikey); mensaje final cambiado.
  - **Design doc**: seccion knowledge_scope_bindings reescrita con convencion fuerte, tabla de nulabilidad, defaults por tipo, y separacion DB vs app.
- Archivos modificados:
  - `backend/db/migrations/002_team360_rbac_packages_workers_knowledge.sql` (v3)
  - `backend/scripts/audit_team360_schema.py` (v3)
  - `docs/postgresql_002_rbac_packages_workers_knowledge_design.md` (v3)
  - `docs/status_actual.md` (esta entrada)
- **002 v3 NO fue aplicada sobre team360.** No se toco DB team360, v360, litellm ni temp1.txt.
- Validacion: `python3 -m py_compile` sobre audit script OK; `git diff --check` sin errores.

### 2026-05-28 - Correccion migracion 002 v2 (RBAC, packages, workers, knowledge) — NO APLICADA

- Se aplicaron las 15 correcciones recomendadas por GPT-5.5 sobre el borrador 002 v1:
  - **core_roles**: workspace_id nullable, is_system_role, indices unicos parciales.
  - **core_permission_profiles**: indices unicos parciales para nullable workspace_id.
  - **core_user_profiles**: area_id + indices unicos parciales (mismo perfil en areas distintas).
  - **automation_packages**: package_code scoped a workspace (no global) + FK a package_plans.
  - **knowledge_scope_bindings**: nueva tabla, binding movido desde knowledge_scopes.
  - **knowledge_scopes**: eliminados binding_type/binding_id.
  - **assistant_instances**: default_knowledge_scope_id sin FK (evita circular).
  - **package_workers**: agregado package_worker_code + UNIQUE.
  - **workspace_plan_subscriptions**: UNIQUE parcial para active only + ended_at_utc.
  - **approval_status**: eliminado 'bypassed', valores seguros (not_required, pending, approved, rejected, expired, cancelled).
  - **worker_definitions seeds**: 8 workers alineados con lat.md.
  - **credential_references**: documentacion de seguridad + audit de metadata_jsonb.
  - **Indices unicos parciales**: 11 criticales para integridad con workspace_id nullable.
- Archivos corregidos:
  - `backend/db/migrations/002_team360_rbac_packages_workers_knowledge.sql` (reescrito)
  - `docs/postgresql_002_rbac_packages_workers_knowledge_design.md` (reescrito)
  - `backend/scripts/audit_team360_schema.py` (reescrito con 8 checkpoints)
- La migracion 002 v2 propone **22 tablas nuevas** (+1: knowledge_scope_bindings).
- **11 indices unicos parciales** para restricciones UNIQUE con workspace_id nullable.
- **ALTER TABLE**: task_runs +6 columnas + check constraint + 4 FKs; package_workers FK a knowledge_scopes.
- **Seeds**: 20 permisos, 4 planes, 17 features, 8 worker_definitions.
- Pendiente: validar v2 con GPT-5.5 antes de ejecutar.
- No se modificaron `v360`, `litellm`, `postgres`, `.codex` ni `temp1.txt`.

## Notas de seguridad

- No se grabo la password de GitHub en archivos del proyecto.
- Se uso un archivo temporal de sesion en `/tmp/team360_github_state.json` solo para diagnostico y se elimino al terminar.
- Se cerro la sesion del navegador automatizado al finalizar la tarea.
- No se hardcodearon secretos reales.
- Las credenciales de providers/LLM se modelaron como `secret_ref`.
- `backend/temp1.txt` aparece modificado en el worktree y contiene material sensible o notas internas; no fue tocado en esta etapa.

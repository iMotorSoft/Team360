# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-06-14 (Fase 1.4 — Endpoint hardening: scope, permisos y seguridad)

## Directorio de trabajo

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1`

## Estado general

Se inicializo la DB viva `team360` en PostgreSQL local y se aplicaron correctamente las migraciones `001_team360_core_schema.sql`, `002_team360_rbac_packages_workers_knowledge.sql`, `003_team360_pgvector_knowledge_embeddings.sql` y `004_team360_automation_diagnosis_runtime.sql`. Tambien existe una Fase 1 de `automation_diagnosis` operativa para demo controlada, con frontend real conectado a API Litestar, IA via LiteLLM por adapter, modo PostgreSQL activable, knowledge scope propio, retrieval simple sobre documentos Markdown, scoring/classifier deterministico, fixtures, tests y smokes reales. Se documento la politica de driver DB runtime (`psycopg 3 async` directo como estandar).

## Acciones realizadas

### 2026-06-10 - Aclaracion de ownership por tipo de trabajo y rama

- Se reviso la documentacion operativa existente en `AGENTS.md`, `.agents/skills/team360-project/SKILL.md`, `lat.md/`, `docs/` y `SrvRestAstroLS_v1/docs/`.
- Se detecto que la regla ya estaba parcialmente documentada para `feature/console-backend-core`, `ux/team360-console-design-handoff` y ownership de experimentos `lab/`, pero faltaba explicitar `feature/knowledge-ingestion-service` como rama de investigacion/validacion/decision notes fuera de labs.
- Se agrego la regla minima en `AGENTS.md` y `.agents/skills/team360-project/SKILL.md`: Knowledge branch para investigar/validar/decidir, Console backend core para implementar funcional y UX/design para mock/handoff visual.
- No se toco codigo productivo, frontend, backend runtime, labs, migraciones, DB, endpoints ni `team360_orquestador`.
- No se hizo checkout, merge, rebase, push, git add ni commit.

### 2026-06-10 - Fase 1.7e — Sales Diagnosis Assistant Lab Closure and Architecture Decision Note

- Se creo la decision note de cierre de labs del asistente conversacional de ventas/diagnostico en `lab/sales-diagnosis-assistant-conversation/decision_notes/20260610_sales_diagnosis_assistant_lab_closure.md`.
- Labs cerrados: Fase 1.6j (Milvus vs pgvector benchmark), 1.6k (RAG answer generation), 1.7 (Conversation lab), 1.7b (Evaluacion heuristica refinada), 1.7c (Guardrail forensic fix), 1.7d (Progressive response simulation).
- Decisiones arquitectonicas documentadas:
  - PostgreSQL 18 = source of truth.
  - Milvus 2.6 = vector runtime derivado para conversacion.
  - pgvector = baseline/dev/fallback.
  - gpt-5-nano low = primera respuesta inteligente.
  - Template seguro = solo acuse/progreso, no reemplaza LLM.
  - AG-UI/SSE = experiencia progresiva futura.
  - ArangoDB y cross-encoder = fuera por ahora.
  - GPT-5.5 = judge/oracle offline, no runtime.
- Guardrails estables: 0 real failures despues de 1.7c.
- Respuesta progresiva adoptada conceptualmente, no implementada como runtime.
- Proximo paso recomendado: Fase 1.8 — Runtime Design Handoff.
- Se actualizo `README.md` del lab con seccion "Lab closure decision" y link relativo a la decision note.
- No se toco runtime productivo, frontend, routes, endpoints, SSE productivo, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, corpus knowledge ni embeddings.
- No se hardcodearon API keys. No se hizo git add/commit.

### 2026-06-10 - Fase 1.8 — Sales Diagnosis Assistant Runtime Design

- Se creo el documento de diseno runtime en `docs/architecture/sales_diagnosis_assistant_runtime_design.md`.
- Diseno basado en decisiones validadas por labs (Fase 1.6j–1.7e):
  - PostgreSQL 18 = source of truth.
  - Milvus 2.6 = vector runtime derivado para conversacion.
  - pgvector = baseline/dev/fallback.
  - gpt-5-nano low = primera respuesta inteligente.
  - Template seguro = solo acuse/progreso, no reemplaza LLM.
  - AG-UI/SSE = contrato futuro de eventos.
- Componentes disenados (10): AssistantConversationRuntime, ConversationState, RetrievalProvider, MilvusVectorIndex, PromptPolicy, GuardrailPolicy, LLMProvider, ProgressiveEventEmitter, MetricsRecorder, AuditTrail.
- Flujo runtime documentado: 13 pasos desde validacion hasta metricas.
- Contratos de datos definidos (6): AssistantTurnInput, AssistantTurnOutput, ConversationState, RetrievedChunk, GuardrailResult, ProgressiveEvent.
- Guardrails obligatorios documentados (5 reglas): no vender como listo, no inventar, diferenciar, limite de preguntas, empty response policy.
- Template seguro documentado con reglas de configuracion por assistant_instance/package/dominio.
- Progressive event contract definido (9 eventos semanticos).
- Fallbacks documentados (8 escenarios con respuestas seguras).
- Metricas definidas (por turno y por sesion).
- Fuera de alcance documentado (10 componentes excluidos explicitamente).
- Riesgos abiertos documentados (8 riesgos con mitigaciones).
- Plan de implementacion futuro sugerido (Fase 1.8a–1.8f).
- Criterios de avance definidos (8 condiciones).
- No se implemento codigo productivo, no se crearon endpoints, no se toco frontend, no se modifico runtime, no se llamo LLM, Milvus ni DB.
- No se hardcodearon API keys. No se hizo git add/commit.

### 2026-06-10 - Fase 1.7c — Fix real guardrail failures del Conversation Lab

- Se realizo forensic audit de los 2 guardrail failures reales detectados en Fase 1.7b.
- Ambos resultaron ser falsos positivos del evaluador heurístico, no fallos genuinos del modelo.
- Se corrigio evaluator.py (6 fix):
  - forward negation detection en `_is_near_negation()` — revisa adelante y atras del termino prohibido;
  - patron "evita prometer [termino]" explicitamente detectado;
  - marcadores plurales para planned_extension (estan + disponibles/listos);
  - marcador `ya\s+est[aa]` reducido a `ya\s+est[aa]\s+listo` para evitar falso positivo con "ya esta disponible";
  - token de negacion "sin prometer" agregado;
  - patrones SLA interno (SLA de respuesta, SLA interno) reconocidos como contexto de cliente, no promesa Team360;
  - question_count corregido: cuenta solo `?` en vez de `¿` + `?`.
- Se endurecio system prompt en run_conversation_lab.py para no sugerir planes que equivalgan a capacidades planned_extension y no mencionar SLA como oferta Team360.
- Se creo scripts/audit_guardrail_failures.py para auditoria forense de fallos.
- Metricas antes/despues:
  - Guardrail failures: 2 → 0
  - Real forbidden claims: 2 → 0
  - Scenario pass rate: 10% → 40%
  - Turn pass rate: 55% → 85%
  - Orientation rate: 100% mantenido
  - Fallos residuales: 0 de guardrail; 6 escenarios con slots faltantes (knowledge coverage, fuera de alcance de 1.7c).
- No se toco frontend, routes, endpoints HTTP, diagnosis productivo, migraciones, corpus, ArangoDB, cross-encoder, runtime productivo, Step-to-Action, lead capture, diagnostic_code, WhatsApp handoff ni CRM real.
- No se hardcodearon API keys. No se hizo git add/commit.

### 2026-06-10 - Fase 1.7d — Progressive Response Simulation Lab

- Se creo `run_progressive_response_lab.py` con 3 estrategias:
  - `single-call`: baseline (1 LLM call, final answer como primer valor de usuario)
  - `progressive-two-step`: LLM quick (120 tok) + LLM final (500 tok), quick answer como primer valor
  - `templated-quick-final-llm`: template contextual (0ms LLM) + LLM final, quick answer como primer valor
- Se implementaron eventos semanticos simulados (team360.status.*, team360.sources.*, team360.answer.*, team360.metrics.*, team360.done, team360.error) sin endpoints reales, sin SSE, sin frontend.
- Se creo `scripts/generate_progressive_report.py` para reporte detallado por turno/evento.
- Se creo `scripts/generate_progressive_infographics.py` para infografia HTML con latencias, quick/final pass rates y bars por scenario.
- Se actualizo README.md con documentacion de Fase 1.7d, eventos, estrategias, ejecucion y metricas.
- Metricas registradas: avg time to first status, sources ready, quick answer, final answer; p50/p95 quick/final; quick safe rate; final pass rate; guardrail failures; perceived latency gain vs baseline.
- No se toco frontend, routes, endpoints HTTP, diagnosis productivo, migraciones, corpus, ArangoDB, cross-encoder, runtime productivo, Step-to-Action, lead capture, diagnostic_code, WhatsApp handoff, CRM real ni SSE productivo.
- No se hardcodearon API keys. No se hizo git add/commit. Pendiente de confirmacion para commit.

### 2026-06-10 - Fase 1.7b — Evaluación heurística refinada del Sales Diagnosis Conversation Lab

- Se creo `lab/sales-diagnosis-assistant-conversation/evaluator.py` con 5 capas de evaluación independientes: response shape, commercial usefulness, safety/anti-overpromise (con word boundaries y detección de negación contextual), knowledge grounding y slot behavior.
- Se agregaron categorías separadas para `pricing_correctly_declined`, `sla_correctly_declined`, `timeline_correctly_declined` vs `unsupported_*_claim`, eliminando falsos positivos de la heurística Fase 1.7.
- Se implementó detección de negación cercana (no, no tenemos, no contamos, todavía no, falta, no documentado) para evitar marcar respuestas correctas como fallos de guardrail.
- Se agregó `scripts/reevaluate_results.py` para reprocesar resultados JSON existentes sin re-llamar LLM, agregando `refined_evaluation` por turno y `refined_scenario_evaluation` por escenario.
- Se modificó `run_conversation_lab.py` para importar `evaluator.py` y almacenar `refined_evaluation` junto a la evaluación inline original.
- Se modificaron `scripts/generate_report.py` y `scripts/generate_infographics.py` para soportar datos refinados cuando `refined_summary` existe en el JSON.
- Se actualizó `README.md` con documentación de la nueva taxonomía, reevaluación y scripts.
- Reevaluación sobre resultado `conversation_lab_20260610_112024.json`: scenario pass rate subió de 0% → 10%, turn pass rate subió de 0% → 55%, orientation rate se mantiene en 100%. Real forbidden claims se redujeron a 2 (casos genuinos). Guardrail failures bajaron a 2.
- No se modificó frontend, routes, endpoints HTTP, diagnosis productivo, migraciones, corpus, ArangoDB, cross-encoder, runtime productivo, Step-to-Action, lead capture, diagnostic_code, WhatsApp handoff ni CRM real.
- No se hardcodearon API keys. No se hicieron git add/commit.

### 2026-06-08 - Fase 1.3a primer documento approved para Knowledge Ingestion

- Se agrego una copia controlada approved del manual de `pkg_sales_diagnosis` en `knowledge/packages/pkg_sales_diagnosis/approved/automatizaciones/team360_sales_diagnosis_package_manual.md`.
- El draft original `knowledge/packages/pkg_sales_diagnosis/drafts/team360_sales_diagnosis_package_manual.md` no se movio, no se borro y conserva `status: draft` + `ingestion_status: not_ready`.
- El documento approved usa `status: approved`, `ingestion_status: ready`, `organization_code: team360_live`, `workspace_code: team360_public_site`, `area_key: automatizaciones`, `topic_key: diagnostico_automatizacion`, `node_path: /automatizaciones/diagnostico-automatizacion`, `package_code: pkg_sales_diagnosis` y `knowledge_scope_code: ks_team360_sales_diagnosis`.
- El scanner dry-run detecta el documento approved como `candidate_for_ingestion=True` con `candidate_count=1`.
- Se agregaron tests para validar que el paquete real tenga al menos un candidato approved, que drafts sigan excluidos por defecto y que el draft original siga en estado no listo.
- Validacion: scanner dry-run real sobre `pkg_sales_diagnosis` = `scanned_count=1`, `valid_count=1`, `candidate_count=1`, `skipped_count=3`, sin errores de resultado.
- Validacion: `uv run pytest tests/test_knowledge_ingestion.py` = 67 passed; `uv run pytest` = 155 passed.
- No se implemento persistencia DB, upsert de `knowledge_documents`, upsert de `knowledge_chunks`, chunks, embeddings, ArangoDB, Milvus, SemanticChunker, endpoints HTTP, frontend ni cambios en `automation_diagnosis`.

### 2026-06-08 - Fase 1.15 base organizacional para Knowledge Ingestion

- Se preparo la base DB minima para que `knowledge_ingestion` resuelva una raiz organizacional real antes de registrar corridas.
- Se agrego migracion `007_team360_core_organizations_users.sql` con:
  - `core_organizations`;
  - `core_organization_roles` como capacidades de organizacion;
  - `core_organization_members` usando `user_id` real hacia `core_users`;
  - `core_organization_member_roles` como roles del usuario dentro de la organizacion.
- `core_users` ya existia desde la migracion 001; no se recreo, no se eliminaron columnas, no se hizo `email NOT NULL` y se agrego indice unico parcial sobre `lower(email)` solo cuando `email is not null`.
- Se agregaron `organization_id` nullable en `core_workspaces` y `organization_id` + `triggered_by_user_id` nullable en `knowledge_ingestion_runs`.
- Se seedearon organizaciones minimas `team360_platform` y `team360_live`, usuarios reales de Mario Rojas y memberships/roles separados por organizacion.
- Se actualizo `KnowledgeIngestionRepository` para resolver `organization_code`, `workspace_code`, `knowledge_scope_code`, `package_code`, `assistant_instance_code`, `worker_code` y `triggered_by_email` a IDs reales.
- Se actualizo `KnowledgeIngestionWorker.validate_and_register()` para crear corridas usando UUIDs reales y conservar codigos en `metadata_snapshot`; `dry_run` no crea runs ni simula UUIDs.
- Se extendieron tests de `knowledge_ingestion` para cubrir resolucion de contexto, usuario disparador, errores claros y separacion de roles de organizacion vs miembro.
- No se implemento auth, passwords, login, sessions, OAuth, endpoints, frontend, billing, CRM, ArangoDB, Milvus, embeddings, SemanticChunker ni upsert de documents/chunks.

### 2026-06-07 - Diseno tecnico Knowledge Ingestion multi-scope / multi-nivel

- Se creo `docs/knowledge_ingestion_multiscope_design_20260607.md` como documento de diseno tecnico para ingesta de conocimiento reusable multi-scope.
- Se identifico la brecha actual: las tablas existentes (knowledge_scopes, knowledge_documents, knowledge_chunks) son planas y no permiten representar jerarquia organizacional (Empresa > Area > Sector > Proceso > Tema) ni filtrado por rol (CEO > Director > Gerente > Responsable).
- Se propuso modelo conceptual con entidades nuevas: KnowledgeMap (estructura jerarquica), KnowledgeNode (nodos individuales), KnowledgeIngestionRun (registro de ingesta), KnowledgeAccessPolicy (politicas de acceso por rol), KnowledgeRetrievalPolicy (politicas de retrieval por asistente).
- Se definieron 8 niveles de scope: global, package, partner, organization, workspace, service, assistant_instance, session.
- Se diseño worker generico `knowledge_ingestion_worker` con 8 fases: validar metadata, convertir a texto, generar L0/L1, chunk semantico, guardar, generar embeddings, indexar, registrar estado.
- Se documento la cascada de retrieval por capas y la relacion con ArangoDB/Milvus.
- Se probo migracion minima futura (tablas KnowledgeMap, KnowledgeNode, KnowledgeIngestionRun, KnowledgeAccessPolicy, KnowledgeRetrievalPolicy) sin implementarla.
- Se mantuvieron identificadores tecnicos estables: `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis`, `svc_sales_diagnosis`. `Vera` solo como marca comercial visible.
- No se implemento codigo, no se crearon migraciones, no se tocaron frontend ni backend runtime.
- Referencias: `lat.md/knowledge-scope-contract.md`, `lat.md/ai-diagnosis-rag-runtime.md`.

### 2026-06-07 - Fase 1 Knowledge Ingestion Platform Service

- Se creo migracion `db/migrations/006_team360_knowledge_ingestion_phase1.sql` (numero 006, siguiente disponible tras 005 seed).
- Tabla nueva: `knowledge_ingestion_runs` para registrar cada corrida de ingesta con fases, estado, errores y stats.
- Columnas nuevas en `knowledge_documents`: `node_path` (text) para referencia jerarquica.
- Columnas nuevas en `knowledge_chunks`: `node_path` (text) + `permission_tags` (text[]) para filtrado por rol.
- Seed de `worker_definitions.knowledge_ingestion_worker` con `worker_kind=api`, `default_mode=assisted`.
- NO se agregaron columnas a `knowledge_chunk_embeddings` (decision: difiere a Fase 2 porque metadata_jsonb existente sirve como almacen temporal).
- Se creo modulo `backend/modules/knowledge_ingestion/` con schemas, repository y worker skeleton:
  - `schemas.py`: `IngestionMetadata` dataclass con validacion de 15 campos obligatorios.
  - `repository.py`: `KnowledgeIngestionRepository` con `create_ingestion_run`, `update_ingestion_run_status`, `update_document_node_path`, `update_chunk_node_path_and_tags`.
  - `worker.py`: `KnowledgeIngestionWorker` con metodo `validate_and_register` que valida metadata y crea run.
- Se crearon tests `backend/tests/test_knowledge_ingestion.py`: 20 tests que cubren validacion de metadata (campos requeridos, tipos, valores), serializacion a dict, contrato del worker y constantes.
- Se actualizo `backend/scripts/audit_team360_schema.py` con tablas/columnas esperadas de 006 y seed `knowledge_ingestion_worker`.
- No se implementaron: upload publico, ArangoDB/Milvus, KnowledgeMap/KnowledgeNode, chunker semantico, embeddings pipeline, endpoints HTTP, cambios en automation_diagnosis.
- Identificadores tecnicos estables: `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis`, `svc_sales_diagnosis`. Sin `vera_*`.

### 2026-06-07 - Fase 1.1 Hardening de Knowledge Ingestion Platform Service

- Se reviso y endurecio la migracion 006, schemas, repository, worker y tests basado en el analisis de consistencia del diseno original.
- **Migration 006**: se agrego `updated_at_utc` a `knowledge_ingestion_runs` (columna faltante vs patron del proyecto), se agrego status `running` al CHECK constraint (para separar pending→running→completed|failed), se recreo la constraint de forma idempotente via `drop constraint if exists + add constraint`.
- **Schemas**: se agrego `SOURCE_TYPES` constant (markdown, pdf, text, html) con validacion en `IngestionMetadata.validate()`. Se elimino `RETRIEVAL_MODES` y `NODE_TYPES` (no usados en Phase 1). Se agrego validacion de `node_path` sin trailing slash (excepto raiz `/`), `area_key`/`topic_key` sin `/`, `access_tags` sin strings vacios. Se agrego `updated_at_utc` a `IngestionRunRecord`. Se removio `register_completion` de `INGESTION_PHASES` (no es fase de procesamiento).
- **Repository**: se agrego `DatabaseExecutionError` cuando `create_ingestion_run` devuelve None. Se agrego `started_at_utc = coalesce(started_at_utc, now())` en transicion a status `running`. Se agrego `updated_at_utc = now()` en todo status update. Se agrego `updated_at_utc` al SELECT de `get_ingestion_run`.
- **Worker**: se cambio status inicial de `validating` a `running` (separacion semantica: running indica pipeline activo, los detalles de fase van en phases_jsonb). Se agrego metodo `advance_phase()` como stub estructural con validacion de orden, fase no completada y saltos invalidos.
- **Tests**: se agregaron 8 tests nuevos (trailing slash en node_path, root `/` permitido, access_tags empty string, area_key/topic_key con `/`, source_type invalido, advance_phase unknown phase, advance_phase incomplete current, advance_phase skip). Se actualizaron tests existentes para reflejar el status `running`. Se elimino import no usado de `IngestionRunRecord`. Se agrego `SOURCE_TYPES` al test de constantes. Total: 30 tests.
- **Module exports**: se agrego `__init__.py` con export publico de todas las clases y constantes.
- Validacion: `uv run pytest` = 110/110 passed. `git diff --check` = OK. Sin identificadores `vera_*`.

### 2026-06-07 - Analisis de estado del adapter publico Vera y proximos pasos

- Se analizaron los 4 archivos funcionales de la entrada publica Vera (PublicVeraEntry.svelte, publicDiagnosis.ts, index.astro, public-vera.spec.ts) mas el backend asociado (routes, schemas, assistant_instances) y el diseno L0/L1/L2 existente.
- Se creo `SrvRestAstroLS_v1/docs/public_vera_adapter_next_steps_20260607.md` con diagnostico de 10 puntos.
- Hallazgos principales:
  - El componente es single-shot: no hay loop conversacional, no hay mensaje backend (buildPreliminaryMessage es cadenas fijas locales), no hay checklist, no hay classify, no hay lead capture.
  - El adapter reusa `/api/automation-diagnosis/session/start` y `/answer` pero nunca llama a `/classify`.
  - La metadata enviada es completa (13 campos en visitor) y conserva identificadores tecnicos estables.
  - El contrato futuro recomendado (`/api/diagnosis/*`) ya esta documentado en el diseno L0/L1/L2 y no requiere nuevo diseno.
- No se modifico codigo funcional, backend, home ni se crearon endpoints.
- No se introdujeron identificadores tecnicos `vera_*`.

### 2026-06-07 - Contrato publico /api/diagnosis/* wrapper sobre automation_diagnosis

- Se creo `backend/routes/diagnosis.py` con 3 endpoints wrapper que reutilizan el mismo servicio `automation_diagnosis` (comparten instancia via `get_service()`).
- Endpoints creados:
  - `POST /api/diagnosis/start` — crea sesion, acepta metadata publica (assistant_instance_code, source_channel, locale, etc.), devuelve session_id + technical_metadata.
  - `POST /api/diagnosis/message` — guarda texto libre como `process_to_automate`, devuelve mensaje preliminar honesto desde backend.
  - `GET /api/diagnosis/session/{id}` — hidrata estado basico de sesion (answers, result, status).
- `POST /api/diagnosis/submit-checklist` y `POST /api/diagnosis/lead` quedan como stubs 501 Not Implemented.
- La respuesta mensaje es backend-real (no sintetica cliente) pero aun es preliminary wrapper.
- No se modifico service.py, scoring, guided_flow, postgres_repository, migraciones ni frontend.
- Se agrego `get_service()` exportable a `routes/automation_diagnosis.py` y `get_session` en `_SyncToAsyncAdapter` para que el wrapper pueda leer sesiones.
- Se extendio `routes/diagnosis_schemas.py` con schemas PublicStartRequest, PublicMessageRequest y stubs.
- Se registraron las rutas en `app.py`.
- Tests: `tests/test_diagnosis_public_router.py` — 16 tests que cubren defaults, metadata custom, visitor merge, mensaje, error handling y stubs 501.
- Validacion: `uv run pytest` = 88/88 passed (16 nuevos + 72 existentes).
- No se introdujeron identificadores tecnicos `vera_*`.

### 2026-06-07 - Entrada publica Vera en Home

- Se agrego una isla publica en la Home para `Hablá con Vera`, con textarea de texto libre, ejemplos breves y CTA `Analizar oportunidad`.
- Se creo un adapter frontend minimo que reutiliza `/api/automation-diagnosis/session/start` y guarda el texto inicial como respuesta `process_to_automate`, sin clasificar ni mostrar checklist inicial.
- El payload conserva los codigos tecnicos estables `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis`, `svc_sales_diagnosis` y `team360_sales_automation_diagnosis`; `Vera` queda solo como display/copy.
- La respuesta publica es preliminar y honesta: no afirma motor conversacional completo, lead creado ni resultado final.
- Se mantiene el mailto como fallback y la UI no pierde el texto si el backend no responde.
- No se modifico backend, no se crearon endpoints definitivos `/api/diagnosis/*`, no se cambio scoring/guided flow, no se implemento captura de lead y no se activo L2/RAG ArangoDB/Milvus.

### 2026-06-07 - Console muestra Team360.live y servicio Vera productivo mock

- Se ajusto la Console mock para que el selector de perfiles muestre los emails reales de acceso mock: `mario.rojas@alquimiablue.com` como platform admin y `mario.rojas.marconi@gmail.com` como client admin.
- El perfil `client_admin` de Team360.live ahora tiene el modulo `diagnosis` visible en navegacion mock sin cambiar el motor ni el flujo actual.
- El detalle del servicio `svc_sales_diagnosis` muestra `Asistente Inteligente Vera` como servicio visible/comercial y conserva los codigos tecnicos `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis` y `svc_sales_diagnosis`.
- Se agrego en el mock del servicio la indicacion visible de canal futuro `Home publica`, knowledge L2 preparado sin ingesta activa y flujo publico todavia no enganchado.
- No se toco home publica, no se crearon rutas `/api/diagnosis/*`, no se cambio `automation_diagnosis`, no se activo ArangoDB/Milvus y no se modificaron migraciones.
- No se introdujeron identificadores tecnicos `vera_*`; `Vera` sigue limitado a display/commercial/copy.

### 2026-06-07 - Seeds y mocks productivos iniciales Team360.live / Vera

- Se agrego `backend/db/migrations/005_team360_platform_live_vera_seed.sql` como seed idempotente sobre tablas existentes para Team360 Platform, Team360.live, administradores, RBAC minimo, assistant instance, paquete, knowledge scope, package workers y bindings.
- La seed mantiene identificadores tecnicos estables: `team360_sales_diagnosis`, `pkg_sales_diagnosis`, `ks_team360_sales_diagnosis`; `Vera` queda solo como nombre visible/comercial en metadata y labels.
- Se actualizo `modules/automation_diagnosis/assistant_instances.py` con metadata visible/comercial de Vera sin cambiar el default tecnico ni el motor `automation_diagnosis`.
- Se actualizaron mocks de Console para representar `Team360.live` como cliente real, `mario.rojas@alquimiablue.com` como platform admin, `mario.rojas.marconi@gmail.com` como client admin y el servicio visible `Asistente Inteligente Vera` con `service_code` tecnico `svc_sales_diagnosis`.
- No se implemento la home publica, no se crearon endpoints `/api/diagnosis/*`, no se cambio el flujo conversacional actual y no se implemento L2/RAG ArangoDB/Milvus.
- Limitacion vigente: backend todavia no tiene tabla formal de organizaciones ni servicios contratados; la separacion Team360 Platform / Team360.live se representa por metadata de workspace y mocks hasta una migracion estructural futura.

### 2026-06-07 - Decision de naming Vera como marca comercial

- Se actualizo `docs/platform_initial_configuration_vera_team360_live_20260605.md` para dejar aprobada la Opcion B de naming.
- `Vera` queda como nombre comercial visible, configurable en display/commercial metadata, marketing copy, Console label, home publica y CTA.
- Se mantienen los identificadores tecnicos estables `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis`.
- No se deben introducir identificadores tecnicos `vera_*` en runtime, seeds, migrations, tests, workers, knowledge scopes ni integraciones core.
- Esta decision evita migraciones por rebranding y mantiene compatibilidad con tests/runtime/docs actuales.
- No se implemento codigo funcional, no se modificaron migraciones, no se toco frontend y no se agregaron secretos.

### 2026-06-07 - Configuracion inicial productiva Vera para Team360.live

- Se creo `docs/platform_initial_configuration_vera_team360_live_20260605.md` como documento tecnico de configuracion/seeding productivo inicial para el primer paquete real `Asistente Inteligente Vera`.
- El documento separa `Team360 Platform` de `Team360.live` como primer cliente real y define plataforma, admins, cliente, workspace, paquete, servicio, assistant instance, workers, knowledge scope, home publica y Console.
- Se inspeccionaron migraciones 001-004, runtime `automation_diagnosis`, routes Litestar, modulo DB, mocks de Console, navegacion y documentos `lat.md` relacionados.
- Se documento la brecha principal: el runtime actual usa `team360_sales_diagnosis`, `pkg_sales_diagnosis` y `ks_team360_sales_diagnosis`; quedaba pendiente cerrar si Vera seria marca visible o identificador tecnico.
- No se implemento codigo funcional, no se modificaron migraciones, no se toco frontend y no se agregaron secretos.

### 2026-06-04 - Cierre pre-commit del asistente de diagnostico Team360

- Estado de cierre para demo controlada: frontend real + API Litestar + PostgreSQL + LiteLLM real + E2E + smoke real.
- Playwright E2E previo: verde (`1 passed`, `1 skipped`) para el flujo de diagnostico.
- Backend pytest de cierre: `72 passed`.
- Frontend check de cierre: `0 errors`, `0 warnings`, `0 hints`.
- Smoke LiteLLM real: OK con `provider=litellm`, `model=openrouter_qwen3_30b_a3b_thinking_2507`, `classification=operational_automation`.
- Smoke LiteLLM + PostgreSQL real: OK; session y lead verificados en PostgreSQL con `status=classified`.
- No se implementaron ArangoDB, Milvus ni embeddings en runtime.
- Riesgos pendientes reales: continuidad de sesion postgres desde DB, observabilidad formal de costos/latencia, repeticion de smokes para medir estabilidad, fallback IA controlado y RAG real con ArangoDB/Milvus en fase posterior.

### 2026-06-04 - Smoke real LiteLLM + PostgreSQL para automation_diagnosis

- Se extendio `backend/scripts/smoke_automation_diagnosis_litellm.py` con `--print-sql` para imprimir la query de verificacion PostgreSQL por `session_id`.
- Se ejecuto el flujo completo contra backend aislado en modo combinado:
  - `TEAM360_AI_PROVIDER=litellm`
  - `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`
  - `TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1`
  - `TEAM360_LITELLM_MODEL_ALIAS=openrouter_qwen3_30b_a3b_thinking_2507`
- Proxy LiteLLM:
  ```bash
  cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/litellm-server
  ./scripts/run.sh
  ```
- Backend LiteLLM + PostgreSQL:
  ```bash
  cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
  TEAM360_AI_PROVIDER=litellm \
  AUTOMATION_DIAGNOSIS_REPOSITORY=postgres \
  TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1 \
  TEAM360_LITELLM_MODEL_ALIAS=openrouter_qwen3_30b_a3b_thinking_2507 \
  TEAM360_LITELLM_TIMEOUT_SECONDS=45 \
  TEAM360_LITELLM_FALLBACK_TO_MOCK=0 \
  uv run uvicorn app:app --host 127.0.0.1 --port 8011
  ```
- Comando smoke:
  ```bash
  cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
  uv run python scripts/smoke_automation_diagnosis_litellm.py --backend-url http://127.0.0.1:8011 --timeout 120 --print-sql
  ```
- Resultado real:
  - session_id: `diag_30d865c6-ddf7-4a00-a3e7-6ba2c89da3c8`
  - classification: `operational_automation`
  - score_total: `100`
  - automation_mode: `assisted`
  - provider: `litellm`
  - model: `openrouter_qwen3_30b_a3b_thinking_2507`
  - latency_ms: `17336`
  - usage total_tokens: `3398`
  - cost reportado por LiteLLM: `0.00413114`
- Verificacion PostgreSQL read-only:
  ```sql
  SELECT ads.public_session_id, ads.status,
         adl.classification, adl.score_total,
         adl.automation_mode, adl.recommended_package_type,
         ads.updated_at_utc
  FROM automation_diagnosis_sessions ads
  LEFT JOIN automation_diagnosis_leads adl ON adl.session_id = ads.id
  WHERE ads.public_session_id = 'diag_30d865c6-ddf7-4a00-a3e7-6ba2c89da3c8'
  ORDER BY ads.updated_at_utc DESC
  LIMIT 10;
  ```
- Resultado DB: `status=classified`, `classification=operational_automation`, `score_total=100`, `automation_mode=assisted`, `recommended_package_type=team360_ops_starter`.
- Validacion de error PostgreSQL: el contrato de ruta sigue cubierto por tests; si persistence falla durante el snapshot, el backend devuelve HTTP 503 y el smoke reporta el cuerpo truncado del error.
- No se toco frontend, Playwright, ArangoDB, Milvus, embeddings ni migraciones.
- Riesgos pendientes: falta observar repeticion de smoke en varias corridas para medir latencia/costo, probar fallback IA controlado y agregar telemetria persistente de costos.

### 2026-06-04 - Smoke real LiteLLM para automation_diagnosis

- Se agrego `backend/scripts/smoke_automation_diagnosis_litellm.py` como smoke HTTP controlado de backend.
- El smoke no arranca servidores, no toca DBs, no usa Playwright y no lee secretos; consume un backend ya levantado.
- Proxy LiteLLM esperado:
  ```bash
  cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/litellm-server
  ./scripts/run.sh
  ```
- Backend LiteLLM para smoke:
  ```bash
  cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
  TEAM360_AI_PROVIDER=litellm \
  TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1 \
  TEAM360_LITELLM_API_KEY=... \
  TEAM360_LITELLM_MODEL_ALIAS=openrouter_qwen3_30b_a3b_thinking_2507 \
  TEAM360_LITELLM_TIMEOUT_SECONDS=45 \
  TEAM360_LITELLM_FALLBACK_TO_MOCK=0 \
  uv run uvicorn app:app --host 127.0.0.1 --port 8010
  ```
- Comando smoke:
  ```bash
  cd /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend
  uv run python scripts/smoke_automation_diagnosis_litellm.py --backend-url http://127.0.0.1:8010 --timeout 120
  ```
- Resultado real ejecutado contra LiteLLM local:
  - session_id: `diag_4923d34f-eee0-4517-bec6-23354ccd0a4d`
  - classification: `operational_automation`
  - score_total: `100`
  - automation_mode: `assisted`
  - provider: `litellm`
  - model: `openrouter_qwen3_30b_a3b_thinking_2507`
  - latency_ms: `30181`
  - usage total_tokens: `2433`
  - cost reportado por LiteLLM: `0.00071144`
- No hubo JSON invalido del modelo en este smoke; la respuesta fue parseada y clasificada correctamente.
- Riesgos pendientes: falta smoke real en modo postgres, validacion de fallback controlado, logging de errores IA sin exponer datos de cliente y observabilidad formal de costos/latencia.

### 2026-06-04 - Integracion activable de LiteLLM real en automation_diagnosis

- Se mantuvo `mock` como provider default seguro para `automation_diagnosis`.
- `TEAM360_AI_PROVIDER=litellm` activa el adapter real OpenAI-compatible contra LiteLLM.
- El alias recomendado inicial es `openrouter_qwen3_30b_a3b_thinking_2507`; el fallback estable documentado es `openai_gpt_4o_mini_2024_07_18`.
- El modelo se resuelve por `TEAM360_LITELLM_MODEL_ALIAS`, luego `TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL`, y finalmente el alias recomendado.
- El cliente LiteLLM toma `TEAM360_LITELLM_BASE_URL` y normaliza a `/v1`; la API key se toma de `TEAM360_LITELLM_API_KEY`, `LITELLM_API_KEY` o `LITELLM_MASTER_KEY`.
- `TEAM360_LITELLM_TIMEOUT_SECONDS` controla timeout; default: `45`.
- El fallback a mock ante error de LiteLLM queda apagado por default y solo se habilita con `TEAM360_LITELLM_FALLBACK_TO_MOCK=1`.
- Las rutas HTTP traducen errores de IA a respuesta controlada `502`, sin traceback publico.
- Se agrega metadata Team360 al payload LiteLLM: organization, workspace, assistant instance, automation package, knowledge scope, session y correlation id.
- No se toco frontend, Playwright, migraciones, ArangoDB, Milvus ni embeddings.
- Modo mock:
  ```bash
  cd backend
  TEAM360_AI_PROVIDER=mock uv run uvicorn app:app --host 127.0.0.1 --port 8000
  ```
- Modo LiteLLM local:
  ```bash
  cd backend
  TEAM360_AI_PROVIDER=litellm \
  TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1 \
  TEAM360_LITELLM_API_KEY=... \
  TEAM360_LITELLM_MODEL_ALIAS=openrouter_qwen3_30b_a3b_thinking_2507 \
  TEAM360_LITELLM_TIMEOUT_SECONDS=45 \
  TEAM360_LITELLM_FALLBACK_TO_MOCK=0 \
  uv run uvicorn app:app --host 127.0.0.1 --port 8000
  ```
- ArangoDB y Milvus siguen documentados pero no implementados en runtime; el retrieval sigue usando el repository in-memory actual.

### 2026-06-04 - Endurecimiento de modo PostgreSQL para automation_diagnosis

- Se elimino el silenciamiento de errores en `PostgresAutomationDiagnosisService._persist_session()`: en modo postgres, si falla la persistencia critica de session/answers/lead/events, se levanta `AutomationDiagnosisPersistenceError`.
- Las rutas HTTP traducen `AutomationDiagnosisPersistenceError` a HTTP 503 con detalle claro, evitando mostrar exito silencioso cuando PostgreSQL no guardo el snapshot.
- El servicio postgres ahora filtra eventos ya persistidos en el proceso y solo envia eventos nuevos al repository.
- El repository inserta eventos en `core_events` con `insert ... where not exists` usando workspace, event name, entity, correlation, timestamp y payload para reducir duplicados sin requerir nueva migracion.
- Se agregaron tests para validar persistencia de session, answers, lead/result, eventos nuevos sin duplicacion y errores de persistencia no silenciados.
- Memory sigue siendo el default seguro (`AUTOMATION_DIAGNOSIS_REPOSITORY=memory`) y postgres se activa con `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`.
- Limitacion vigente: el runtime postgres todavia delega logica a memoria y persiste snapshots; la continuidad de sesion entre reinicios/procesos todavia depende del proceso hasta implementar carga/hidratacion desde DB.
- Modo postgres:
  ```bash
  cd backend
  AUTOMATION_DIAGNOSIS_REPOSITORY=postgres TEAM360_DB_URL=postgresql://... uv run uvicorn app:app --host 127.0.0.1 --port 8000
  ```
- Query demo:
  ```sql
  SELECT ads.public_session_id, ads.status,
         adl.classification, adl.score_total
  FROM automation_diagnosis_sessions ads
  LEFT JOIN automation_diagnosis_leads adl ON adl.session_id = ads.id
  ORDER BY ads.updated_at_utc DESC
  LIMIT 10;
  ```

### 2026-06-04 - Documentacion del contrato KnowledgeScope derivado de JudaismoEnVivo

- Se formalizo en `lat.md/knowledge-scope-contract.md` el contrato `KnowledgeScope / KnowledgeDocument / KnowledgeChunk / VectorEmbedding`.
- Se agrego el analisis no-runtime `docs/analisis-tecnico/team360_knowledge_scope_contract_judaismo_pattern.md`.
- Se documento la equivalencia JudaismoEnVivo `Catalog/MD/Chunk` hacia Team360 `KnowledgeScope/Document/Chunk`.
- Se fijo que ArangoDB sera fuente textual/grafo y Milvus indice derivado, con filtros obligatorios multi-tenant por organizacion, workspace, assistant instance, knowledge scope, status y version.
- Se recomendo persistir `chunk_text` en Team360 y definir fallback Arango-only.
- Se aclaro que pgvector queda como laboratorio/fallback, que Milvus 2.6 es prueba paralela y que no se debe migrar ArangoDB a PostgreSQL ahora.
- No se modifico runtime, backend, frontend, API, migraciones, ArangoDB, Milvus ni LiteLLM.

### 2026-06-04 - Conexion de endpoints HTTP a PostgreSQL real via AUTOMATION_DIAGNOSIS_REPOSITORY

- Se creo `backend/modules/automation_diagnosis/postgres_service.py` con `PostgresAutomationDiagnosisService` que envuelve el servicio sync existente y persiste session/answers/lead/events a PostgreSQL via `AutomationDiagnosisPostgresRepository` y pool de conexiones.
- Se actualizo `backend/routes/automation_diagnosis.py` para leer `AUTOMATION_DIAGNOSIS_REPOSITORY=memory|postgres`. En modo memory usa `_SyncToAsyncAdapter` envolviendo `build_default_service()`. En modo postgres construye `PostgresAutomationDiagnosisService` con pool.
- Se actualizo `backend/app.py` con hooks `on_startup`/`on_shutdown` que abren/cierran el pool solo cuando `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`.
- El pool se crea con `open=False` en el routes module (import time seguro), se abre explicitamente en startup de Litestar.
- No se abrio pool al importar modulos.
- No se toco frontend.
- Se mantuvo AI mock, knowledge in-memory y scoping por assistant_instance_id.
- Se agregaron 5 tests en `tests/test_automation_diagnosis_postgres_service.py` que validan la delegacion de logica de negocio con pool fake.
- Validacion: `uv run pytest` = 59 passed (54 anteriores + 5 nuevos).
- Comandos:
  - Memory (default): `cd backend && uv run uvicorn app:app --host 127.0.0.1 --port 8000`
  - PostgreSQL:  `cd backend && AUTOMATION_DIAGNOSIS_REPOSITORY=postgres TEAM360_DB_URL=postgresql://... uv run uvicorn app:app --host 127.0.0.1 --port 8000`
  - Tests: `cd backend && uv run pytest`
- Query SQL para verificar sesiones/leads guardados:
  ```sql
  SELECT ads.public_session_id, ads.status, adl.classification, adl.score_total
  FROM automation_diagnosis_sessions ads
  LEFT JOIN automation_diagnosis_leads adl ON adl.session_id = ads.id
  ORDER BY ads.updated_at_utc DESC
  LIMIT 10;
  ```

### 2026-06-04 - Frontend conectado a endpoints HTTP reales de automation_diagnosis

- Se creo `astro/src/lib/api/diagnosis.ts` con cliente API tipado para startSession, saveAnswer y classifySession, mas definicion de GUIDED_STEPS y OPTION_LABELS desde el backend.
- Se creo `astro/src/components/console/diagnosis/ConsoleDiagnosis.svelte` con flujo completo: pantalla de bienvenida → preguntas guiadas una por una con progreso → clasificacion → resultado con desglose, riesgos y proximos pasos.
- Se creo `astro/src/pages/w/[workspaceId]/diagnosis/index.astro` siguiendo el patron de paginas existentes (getStaticPaths + ConsoleAppLayout).
- Se configuro proxy en `astro.config.mjs` para que `/api` se reenvie a `http://127.0.0.1:8000` en dev.
- Se registro "diagnosis" en `navigation/registry.ts` como ConsoleView + nav item en grupo "operations" para audiencias owner/operator/partner.
- Se agrego "diagnosis" a `enabledModules` en perfiles team360_admin y team360_operator.
- Se agrego ruta `workspaceDiagnosis` en `global.js` y entrada "diagnosis" en `derive.ts`.
- Se agregaron claves i18n `nav.diagnosis` en es/en/he.
- Validacion: `pnpm check` = 0 errors, 0 warnings, 0 hints. Backend tests = 54/54 passed.
- Smoke: backend responde `POST /api/automation-diagnosis/session/start` = 201 con defaults correctos.
- No se modifico arquitectura RAG, no se toco DB, no se rompio mock UX existente.

Comandos para correr:
  Backend:  cd backend && uv run uvicorn app:app --host 127.0.0.1 --port 8000
  Frontend: cd astro && corepack pnpm dev

### 2026-06-04 - Primer endpoint HTTP Litestar para automation_diagnosis

- No existia app Litestar montada. El entrypoint `ls_iMotorSoft_Srv01.py` era placeholder sin Litestar.
- Los route handlers en `routes/automation_diagnosis.py` eran funciones planas sin decoradores HTTP.
- Se creo `backend/app.py` con factory `create_app()` que monta Litestar 2.21.1 con route handlers para health, start_session, save_answer y classify.
- Se reescribio `routes/automation_diagnosis.py` con decoradores `@post()` de Litestar, usando Pydantic solo en boundary HTTP (request validation en `routes/diagnosis_schemas.py`).
- `StartSessionRequest` expone solo `source_url`, `locale`, `visitor`, `assistant_instance_id`; `knowledge_scope_id` y campos internos no son pasables por API (defense-in-depth).
- El servicio usa `build_default_service(ai_provider="mock")` porque LiteLLM real no tiene configuracion (alineado con requisito 9).
- Errores `ValueError` del service se traducen a HTTP 422.
- Se crearon 9 tests de integracion via `Litestar.testing.TestClient` que cubren: health, start_session default, scope stripping, answer+classify full flow, errores 422 para session inexistente o sin respuestas, payload minimo.
- Se reservaron los metodos `get_session`, `capture_contact`, `finalize`, `debug`, `search_knowledge` del router anterior sin exponerlos (disponibles para proxima iteracion).
- Validacion: 54 tests pasan (45 anteriores + 9 nuevos).
- No se abrio pool DB al importar. No se introdujo SQLAlchemy/SQLModel/asyncpg. No se modifico frontend.

### 2026-06-04 - DB writes: persistencia runtime de automation_diagnosis

- Se creo y aplico `backend/db/migrations/004_team360_automation_diagnosis_runtime.sql` sobre la DB viva `team360`.
- La migracion agrega `assistant_instances.assistant_code`, crea `automation_diagnosis_sessions`, `automation_diagnosis_answers` y `automation_diagnosis_leads`, y agrega `uq_ksb_binding_scope_entity` para bindings idempotentes.
- Se agregaron seeds de `worker_definitions` para los package workers del paquete de venta/diagnostico.
- Se creo `backend/modules/automation_diagnosis/postgres_repository.py` con repository async de escritura usando `psycopg 3`, SQL parametrizado y conexiones recibidas desde el caller.
- El repository implementa `upsert_package_installation()` y `persist_session_snapshot()` para instalar `team360_sales_diagnosis` y persistir sesion, respuestas, lead y eventos en `core_events`.
- Se agrego `backend/tests/test_automation_diagnosis_postgres_repository.py`.
- Smoke real sobre `team360`:
  - `migration_004_applied=ok`.
  - package installation: 9 package workers.
  - persistencia snapshot: 1 sesion, 10 respuestas, 1 lead y 16 eventos.
- Validacion:
  - `python3 -m py_compile` sobre modulos/tests tocados: OK.
  - `uv run pytest tests/test_automation_diagnosis.py tests/test_automation_diagnosis_postgres_repository.py`: `13 passed`.
  - `uv run pytest`: `45 passed`.
  - `uv run python -m scripts.audit_team360_schema`: `102` checks pasados, `0` fallidos, tablas esperadas `001+002+003+004`: `51/51`.
  - `git diff --check`: OK.
- No se implementaron ArangoDB, Milvus, LiteLLM real, endpoints Litestar nuevos ni frontend.

### 2026-06-04 - Implementacion base: Team360 como cliente del paquete venta/diagnostico

- Se agrego `backend/modules/automation_diagnosis/assistant_instances.py` con contrato in-memory de `AssistantInstanceConfig` y `PackageWorkerBinding`.
- Se materializo `team360_sales_diagnosis` como primera instalacion cliente real del paquete `pkg_sales_diagnosis` para el workspace `team360_public_site`, con `knowledge_scope_id = ks_team360_sales_diagnosis`.
- Se conservaron fixtures/lab existentes mediante `automation_diagnosis_default` y `ks_team360_automation_diagnosis` como compatibilidad explicita.
- `AutomationDiagnosisService.start_session()` ahora resuelve la configuracion por `assistant_instance_id`, aplica locale soportado, rechaza overrides de scope que no coincidan y propaga organizacion, workspace, canal, lead owner, cost attribution y package workers.
- Eventos y ficha interna de lead ahora incluyen `organization_id`, `site_channel`, `lead_owner`, `locale`, `package_worker_ids` y `cost_attribution`.
- El repositorio knowledge in-memory carga scopes por assistant instance para evitar mezclar retrieval entre `ks_team360_sales_diagnosis` y el lab legacy.
- Se actualizaron tests de `automation_diagnosis` para cubrir Team360 como cliente directo, rechazo de scope mismatch y metadata de ArangoDB/Milvus declarada.
- Validacion:
  - `python3 -m py_compile` sobre modulos `automation_diagnosis` y test: OK.
  - `uv run pytest tests/test_automation_diagnosis.py`: `11 passed`.
  - `uv run pytest`: `43 passed`.
- En esa etapa no se implementaron DB writes, migraciones, ArangoDB, Milvus, LiteLLM real, endpoints Litestar nuevos ni frontend.

### 2026-06-04 - Decision documental: RAG inicial de diagnostico con ArangoDB + Milvus

- Se documento la direccion inicial para el asistente inteligente de venta y diagnostico de automatizacion.
- Se documento el alcance inicial de salida: asistente de venta/diagnostico para Team360 directo y asistente de venta/diagnostico para Mamá Mía 360 como distribuidor regional en Israel, con soporte español, ingles y hebreo.
- Se fijo que ambos casos deben compartir motor tecnico y separarse por `assistant_instance`, organizacion/workspace, canal, knowledge scope, lead owner y atribucion de costos.
- Se documento que `team360_sales_diagnosis` debe tratarse como primera instalacion cliente real del paquete de venta/diagnostico, con package workers, scope propio y persistencia/auditoria como cualquier cliente.
- Se documento la decision inicial para ArangoDB/Milvus: scoping logico obligatorio por organizacion/workspace/assistant/scope y no coleccion fisica por cliente como default.
- Decision: para acelerar la salida de Team360, el runtime RAG/knowledge inicial replica el patron probado en JudaismoenVivo:
  - ArangoDB para knowledge graph/documentos de diagnostico.
  - Milvus para retrieval semantico.
  - LiteLLM como gateway AI y control de aliases/modelos/costos.
- PostgreSQL 18 sigue siendo la fuente de verdad transaccional para organizaciones, workspaces, permisos, paquetes, package workers, diagnosticos finales, eventos, auditoria, consumo y billing.
- `003_team360_pgvector_knowledge_embeddings.sql` queda como capacidad instalada/disponible, pero no como RAG principal de la primera salida.
- Se agrego `lat.md/ai-diagnosis-rag-runtime.md`.
- Se actualizo `lat.md/knowledge-rag-graphrag.md`, `lat.md/postgres-ai-persistence.md`, `lat.md/lat.md` y `lat.md/status_actual.md`.
- Se agrego el analisis no operativo `docs/analisis-tecnico/team360_ai_diagnostico_stack_arango_milvus_litellm.md` y se actualizaron indices/status documentales.
- No se implemento codigo, no se tocaron DBs, migraciones, backend, frontend ni configuracion de LiteLLM.

### 2026-06-02 - ConsoleBootstrap Fase C repositories read-only y servicio

- Se crearon `backend/modules/console/repositories.py`, `service.py` y `errors.py`.
- Se implementaron repositories read-only para workspace, permisos efectivos,
  paquetes visibles, entitlements, flags seguros de knowledge/workers, resumen de
  tareas y alertas acotadas a eventos `console.alert.*`.
- Se implemento `ConsoleBootstrapService.build_bootstrap()` sin endpoint Litestar.
- Se mantuvo la autorizacion provisional workspace-centric con
  `core_users.workspace_id`; organizaciones y membresias multi-workspace siguen
  requiriendo una migracion futura explicita.
- `organization_context` se proyecta provisionalmente desde workspace.
- No se consultan ni exponen `credential_references`, `package_worker_configs`,
  `automation_packages.settings_jsonb`, payloads internos ni secretos.
- Se corrigio `backend/modules/db/settings.py` para normalizar URLs
  `postgresql+psycopg://` al formato `postgresql://` aceptado por psycopg/libpq.
- Se corrigieron helpers existentes de `backend/modules/db/transaction.py` para
  aceptar `dict_row` y adquirir conexiones del pool mediante context manager.
- Se elimino un callback `configure` invalido de `backend/modules/db/pool.py`
  que impedia inicializar `AsyncConnectionPool`.
- Validacion:
  - `python3 -m py_compile` sobre modulos Console y helpers DB tocados: OK.
  - `uv run pytest`: `39 passed`.
  - smoke real de schema y repositories contra `team360` con
    `transaction_read_only=on`: OK.
  - smoke real de pool, context manager y `fetch_one()` contra `team360` con
    `transaction_read_only=on`: OK.
  - build real completo omitido porque `team360` no tiene usuarios activos
    sembrados; el armado se valido con fake repositories.
  - busqueda de dependencias prohibidas y `git diff --check`: OK.
- No se tocaron DB en modo escritura, migraciones, endpoints, frontend,
  `v360`, `litellm`, `temp1.txt`, `.codex` ni labs de cliente.

### 2026-06-02 - Modulo db base con psycopg 3 async

- Se creo `SrvRestAstroLS_v1/backend/modules/db/` con 5 archivos:
  - `errors.py`: `DatabaseError`, `DatabaseConfigurationError`, `DatabasePoolNotInitializedError`, `DatabaseExecutionError`.
  - `settings.py`: `DatabaseSettings` (dataclass frozen), `get_database_settings()` con resolucion DSN desde `TEAM360_DB_URL` / `TEAM360_DB_URL_PSQL` / `DB_PG_V360_URL`, `sanitize_dsn()` para logging seguro.
  - `pool.py`: `create_pool()`, `set_pool()`, `get_pool()`, `open_pool()`, `close_pool()`, `reset_pool_for_tests()`. Pool se crea con `open=False`, no abre conexiones al importar.
  - `transaction.py`: `fetch_one()`, `fetch_all()`, `execute()`, `transaction()` context manager async.
  - `__init__.py`: export publico de todas las funciones y excepciones.
- Se creo `SrvRestAstroLS_v1/docs/db_runtime_psycopg_async.md` con documentacion del modulo.
- Se crearon tests `SrvRestAstroLS_v1/backend/tests/test_db_module.py` (14 tests, todos pasan).
- No se toco DB, migraciones, codigo runtime existente, `v360`, `litellm`, `temp1.txt`, `.codex` ni archivos no relacionados.
- No se introdujo SQLAlchemy, SQLModel, asyncpg ni Pydantic.

### 2026-06-02 - Contrato ConsoleBootstrap documentado

- Se creo `SrvRestAstroLS_v1/docs/console_bootstrap_contract.md` con el diseno completo del contrato read-only que alimentara la carga inicial de Team360 Console.
- Se creo `SrvRestAstroLS_v1/backend/modules/console/types.py` con TypedDicts y dataclass internos sin Pydantic, validado con `py_compile`.
- Se creo `SrvRestAstroLS_v1/backend/modules/console/__init__.py`.
- El contrato define:
  - Endpoint recomendado: `GET /api/workspaces/{workspace_id}/console/bootstrap`.
  - DTO JSON completo con 9 secciones: workspace, current_user, effective_permissions, capabilities, entitlements, navigation, services, tasks_summary, alerts, workspace_context, organization_context, debug.
  - Mapeo DB a DTO contra las migraciones 001 y 002.
  - Reglas de seguridad y visibilidad por audiencia.
  - TypedDicts Python en `types.py` sin Pydantic.
  - Diseno de 6 repositories futuros y 6 fases de implementacion.
  - Exclusiones explicitas.
- No se toco DB, migraciones, codigo runtime existente, `v360`, `litellm`, `temp1.txt`, `.codex` ni archivos no relacionados.

### 2026-06-02 - Pydantic Boundary: Pydantic no es obligatorio en repositorios ni dominio

- Se ajusto la politica de driver DB en `lat.md/postgres-driver-policy.md` para que Pydantic no sea obligatorio en repositories ni core de dominio.
- Nueva regla: repositories devuelven `dict`, `dataclass`, `TypedDict` o DTO explicitos; Pydantic solo en bordes HTTP/API para validacion, serializacion JSON, OpenAPI o proteccion de campos.
- Se agrego la seccion `Pydantic Boundary` que lista usos permitidos, no permitidos y guia para contratos internos.
- Se actualizo el ejemplo de repositorio de Pydantic a dataclass (`dataclasses.dataclass`).
- Se agrego la regla correspondiente en `.agents/skills/team360-project/SKILL.md`.
- Se actualizaron `lat.md/status_actual.md`, `lat.md/postgres-driver-policy.md` y esta bitacora.
- No se toco DB, migraciones, codigo runtime, `v360`, `litellm`, `temp1.txt`, `.codex` ni archivos no relacionados.

### 2026-06-01 - Analisis de alineacion UX Console con backend PostgreSQL

- Se revisaron la home publica, layouts, App Shell, rutas Astro, bootstrap mock, store de contexto, navegacion derivada, servicios, workers y runs de Team360 Console.
- Se contrasto la UX actual con las migraciones aplicadas `001`, `002` y `003`, sin ejecutar migraciones ni tocar DB.
- Se creo `docs/ux_console_backend_alignment.md` con estado UX, modelo backend disponible, mapeo UX-DB, rutas recomendadas, separacion publico/privado, visibilidad, fases y riesgos.
- Se recomendo implementar primero un `ConsoleBootstrap` backend read-only con repositories y `psycopg 3 async`, antes de sustituir fixtures o agregar cambios grandes.
- Se registro como brecha futura explicita el modelo de organizaciones, membresias multi-workspace, scope delegado y servicios visibles separados de paquetes/workers.
- Se detectaron ajustes visuales posteriores en `ux/team360-console-design-handoff` todavia no integrados; no se mezclaron ramas en esta tarea.
- No se tocaron frontend, backend, DB, migraciones, `temp1.txt`, `.codex`, `v360`, `litellm` ni labs de cliente.

### 2026-06-01 - Aclaracion de rama para contexto de desarrollo

- Se documento en `AGENTS.md` que `main` es la rama estable, `ux/team360-console-design-handoff` es la rama de diseno UX y `feature/console-backend-core` es la rama de desarrollo e integracion general.
- Se reforzo en `.agents/skills/team360-project/SKILL.md` que una instruccion con `desarrollo`, `dev` o `backend` selecciona `feature/console-backend-core`.
- Se aclaro que `Objetivo: desarrollo` en esta bitacora identifica documentacion tecnica y no implica crear una rama Git llamada `desarrollo`.
- No se tocaron frontend, backend, DB, migraciones, `temp1.txt`, `.codex`, `v360`, `litellm` ni labs de cliente.

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
7. Validar diseno de Knowledge Ingestion multi-scope (`docs/knowledge_ingestion_multiscope_design_20260607.md`) con el equipo.
8. Definir metadata mocks para estructura Empresa/Area/Sector/Proceso/Tema.
9. Evaluar migracion minima para KnowledgeMap, KnowledgeNode y policies cuando haya decision de implementacion.

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

### 2026-06-08 - Fase 1.2: Scanner dry-run de paquetes knowledge

- Se agrego `modules/knowledge_ingestion/package_scanner.py` como scanner/validator interno sin DB writes.
- Se extendio `schemas.py` con `DocumentValidationIssue`, `ParsedKnowledgeDocument`, `PackageScanRequest`, `PackageScanResult`, `PackageMetadata`.
- Se agrego `validate_package_dry_run()` en `KnowledgeIngestionWorker` como metodo interno/testeable.
- Reglas de drafts: no incluidos por defecto; solo con `include_drafts=True` + `dry_run=True` o `experimental=True`; si falta dry_run/experimental, falla con error claro.
- Validacion de frontmatter: YAML entre `---`, status, ingestion_status, document_type, area_key, topic_key, node_path, access_tags, locale, scope_type, visibility, source_type.
- Validacion contra _metadata: package_code, knowledge_scope_code, workspace_code y access_tags catalog.
- Validacion de paquete real `pkg_sales_diagnosis` contra metadata real: package-profile.yaml, knowledge-scope-mapping.yaml, access-tags.yaml.
- 23 tests nuevos de scanner (total: 65 tests knowledge ingestion).
- 153/153 tests suite completa.
- No se persisten documents/chunks. No embeddings. No ArangoDB/Milvus.
- No se toco frontend, routes, diagnosis ni automation_diagnosis.
- No se modificaron documentos knowledge existentes.

### 2026-06-08 - Fase 1.3a-fix: runtime target explícito en scope mapping

- Se agregó `default_runtime_organization_code: team360_live` y `default_runtime_workspace_code: team360_public_site` en `knowledge-scope-mapping.yaml`.
- El scanner reconoce `default_runtime_workspace_code` + `organization_code` como target válido; si un documento apunta al runtime target, no genera warning de workspace_code mismatch.
- Si un documento apunta a un workspace no declarado (ni package ni runtime), el warning se mantiene.
- 2 tests nuevos: `test_runtime_workspace_matches_no_warning` (aprobación + candidate) y `test_undeclared_workspace_still_warns` (warning preservado).
- 69/69 tests knowledge ingestion pasan.
- No se tocó el documento approved, drafts, frontend, routes, diagnosis, migrations ni embeddings.

### 2026-06-08 - Fase 1.3b: persistencia controlada de KnowledgeDocument

- Se agregó `persist_package_documents()` en `worker.py`:
  - Recibe codes (org, workspace, scope, package), resuelve contexto, scanea, persiste.
  - `dry_run=True`: solo scanea, 0 writes, no crea ingestion_run.
  - `dry_run=False`: crea ingestion_run, upserta candidates como KnowledgeDocuments, marca run completed.
  - Si falla upsert → run `failed`.
- Se agregaron en `repository.py`:
  - `find_knowledge_document_by_source()` — busca por `knowledge_scope_id` + `source_uri`.
  - `insert_knowledge_document()` — INSERT con RETURNING id.
  - `update_knowledge_document()` — UPDATE por id.
  - `upsert_knowledge_document()` — lógica unificada: no existe → inserted; existe + mismo hash → unchanged; existe + hash distinto → updated.
- Idempotencia por `(knowledge_scope_id, source_uri)` sin constraint DB.
- `content_hash` = sha256 del contenido completo del archivo.
- `source_uri` obligatorio: si falta o vacío, no se persiste.
- `title` usa `frontmatter.title` o fallback a filename stem.
- `document_type` y resto de metadata van dentro de `metadata_jsonb`.
- No se tocó migration: `knowledge_documents` existente cubre todas las columnas.
- 8 tests nuevos (total: 77 tests knowledge ingestion).
- No se crean chunks, embeddings, ArangoDB ni Milvus.

### 2026-06-08 - Fase 1.4a: chunking estructural por headings Markdown

- Se creó `markdown_chunker.py` con `chunk_markdown()`:
  - Ignora frontmatter YAML, divide por `#`/`##`/`###`.
  - Sin headings → 1 chunk con todo el body.
  - `chunk_hash` sha256 del contenido en `metadata_jsonb`.
  - Heading path jerárquico preservado en metadata.
  - Sin LLM, sin SemanticChunker.
- Se agregó `include_chunks: bool = False` a `persist_package_documents()`.
  - `include_chunks=True` + documento `inserted`/`updated` → `replace_chunks_for_document()`.
  - `include_chunks=True` + `unchanged` → no toca chunks.
  - `dry_run=True` + `include_chunks=True` → estima chunk_count sin writes.
- Nuevos métodos en `repository.py`:
  - `delete_chunks_for_document()` — DELETE por document_id.
  - `insert_knowledge_chunk()` — INSERT de chunk individual.
  - `replace_chunks_for_document()` — DELETE + INSERT batch.
- No se tocó migration: `knowledge_chunks` (002 + 006) cubre todas las columnas.
- 12 tests nuevos (total: 89 tests knowledge ingestion, 177 suite completa).
- No se generan embeddings, no se activa Milvus/ArangoDB/SemanticChunker/LLM.

### 2026-06-08 - Fase 1.4a-integration: validación real contra PostgreSQL local

- Migraciones 006 y 007 aplicadas contra DB local `team360`.
- Se creó `scripts/run_knowledge_ingestion_local.py` para integración local:
  - `--dry-run` (default): lee el paquete, estima chunks, 0 writes.
  - `--no-dry-run`: persiste documents + chunks contra DB real.
- Se corrigió `worker.py`: `_sanitize_metadata()` convierte `datetime.date` a ISO string para JSON serialization.
- Dry-run (`--dry-run`): 1 scanned, 1 candidate, ~40 chunks estimados, 0 writes.
- Primera persistencia real (`--no-dry-run`): 1 documento inserted, 40 chunks creados, run completed.
- Segunda persistencia (idempotencia): 1 unchanged, 0 chunks reemplazados.
- DB verification:
  - `knowledge_ingestion_runs`: 3 runs (1 failed de intento previo, 2 completed)
  - `knowledge_documents`: 1 documento (status=active, source_uri, content_hash, node_path ok)
  - `knowledge_chunks`: 40 chunks (embedding_status='pending', permission_tags heredados, heading_path preservado)
  - `knowledge_chunk_embeddings`: 0 rows (no embeddings generados)
  - No Milvus, no ArangoDB, no LLM calls.
- 89/89 tests knowledge ingestion, 177/177 suite completa.
- Comando de integración: `cd backend && DB_PG_V360_URL="..." uv run python scripts/run_knowledge_ingestion_local.py`

### 2026-06-09 - Fase 1.6a: retrieval local PostgreSQL/pgvector

- Se agregó `search_chunks_by_embedding()` en `repository.py`:
  - Búsqueda por similitud coseno (`<=>` operator) sobre `knowledge_chunk_embeddings`.
  - Filtros obligatorios: `knowledge_scope_id`, `embedding_version`, `embedding_status='ready'`.
  - Filtro opcional: `min_score`.
  - Limit validado entre 1 y 50.
  - JOIN con `knowledge_chunks` (recupera `chunk_metadata` con `heading_path`, `chunk_strategy`, `access_tags`, `chunk_hash`) y `knowledge_documents` (recupera `source_uri`).
  - Score = `1 - cosine_distance`.
- Se agregó `retrieve_knowledge_chunks()` en `worker.py`:
  - Resuelve contexto organizacional (códigos → UUIDs).
  - Genera embedding de la query con `OpenAIEmbeddingProvider`.
  - Delega la búsqueda al repository.
  - Devuelve estructura con `query`, `embedding_version`, `result_count`, `results[]`.
  - No llama LLM/chat — solo embedding + pgvector.
- Se creó `scripts/run_knowledge_retrieval_local.py`:
  - `--query` obligatorio, `--limit` (1–50, default 5), `--min-score` opcional.
  - Imprime advertencia clara: OpenAI para embedding, PostgreSQL/pgvector para retrieval, no Milvus, no ArangoDB, no LLM.
  - Muestra rank, score, chunk_id, source_uri, title, node_path, content_preview.
- Se agregaron 12 tests en `TestKnowledgeRetrieval`:
  - query vacía, limit <1, limit >50, embedding_version vacío.
  - repository valida limit y version.
  - resultados incluyen chunk_metadata y embedding_metadata.
  - scope_id filtrado en SQL.
  - min_score en SQL.
  - sin resultados devuelve vacío.
  - sin LLM/chat completions.
- No se creó migración: schema 003 cubre todo (HNSW cosine index listo).
- No se tocó frontend, routes, diagnosis, automation_diagnosis, Milvus, ArangoDB, LLM.
- Validación:
  - 127 KI tests pasan (115 anteriores + 12 nuevos).
  - 215 suite completa pasan (203 anteriores + 12 nuevos).
  - 3 queries reales contra DB local con resultados semánticamente relevantes:
    - "automatizable pero no vendible hoy" → rank 1 Offer Decision (0.604), rank 2 Límite comercial (0.541).
    - "preguntas mínimas del diagnóstico" → rank 1 Criterios de diagnóstico (0.506).
    - "aporte del diagnóstico comercial" → rank 1 Diagnóstico amplio de automatización (0.681).

### 2026-06-09 - Fase 1.5: pipeline de embeddings productivo con OpenAI

- Se implementó el pipeline de generación y persistencia de embeddings para chunks con
  `embedding_status='pending'` usando OpenAI `text-embedding-3-small` (1536d, cosine).
- Se creó `modules/knowledge_ingestion/embedding_provider.py`:
  - `OpenAIEmbeddingProvider` con `httpx`, sin dependencia directa del paquete `openai`.
  - `embed_texts(texts)` → `list[list[float]]` con validación de dimensión, encoding, errores HTTP.
  - API key desde `OPENAI_API_KEY` con fallback `OpenAI_Key_JAI_query`.
  - No se hardcodean secrets ni se loggean keys.
- Se extendió `repository.py` con 7 métodos:
  - `find_embedding_model_id()` — busca modelo semilla por `provider/model/dimensions`.
  - `list_pending_chunks_for_embedding()` — chunks `pending`, opcional `knowledge_scope_id`, join a `knowledge_documents`.
  - `find_existing_chunk_embedding()` — idempotencia por `chunk_id + model_id + content_hash`.
  - `insert_chunk_embedding()` — INSERT con `embedding_status='ready'`.
  - `update_chunk_embedding_status()` — actualiza `knowledge_chunks.embedding_status`.
  - `mark_chunk_embedding_ready/failed()` — actualiza `knowledge_chunk_embeddings.embedding_status`.
- Se extendió `worker.py` con `embed_pending_chunks()`:
  - `dry_run=True` por defecto: reporta pendientes, 0 writes.
  - `dry_run=False`: por cada chunk → verifica idempotencia, marca processing, genera embedding, inserta, marca completed.
  - En error → marca chunk `failed`, marca embedding `failed` si existía registro previo.
- Se creó `scripts/run_knowledge_embedding_local.py` con `--dry-run` (default), `--no-dry-run`, `--limit N`.
- Se agregaron 12 tests: `TestOpenAIEmbeddingProvider` (8 tests) + `TestEmbedPendingChunks` (4 tests).
- Dry-run real: 40 pending chunks detectados, 0 writes.
- Embedding real (`--no-dry-run --limit 10`): 10/10 embeddings insertados, 1536d, estado ready, version `team360-openai-small-1536-v1`.
- Se corrigió `list_pending_chunks_for_embedding`: `knowledge_scope_id` se resuelve mediante JOIN a `knowledge_documents` (`kc` no tiene columna directa), `content_hash` extraído de `metadata_jsonb ->> 'content_hash'`.
- Validación: 203/203 tests suite completa.
- DB verificada: 10 embeddings `ready`, 1536d, `knowledge_chunks` chunks 0-9 marcados `completed`, chunks 10-39 `pending`.
- No se implementaron: Milvus, ArangoDB, retrieval, endpoints HTTP, frontend, SemanticChunker, Qwen/Perplexity como provider default.

### 2026-06-08 - Fase 1.4b: estrategia de chunking controlada (semantic wrapper)

- Se creó `modules/knowledge_ingestion/semantic_chunker.py`:
  - Wrapper que intenta importar `SemanticChunker` de `langchain_experimental`.
  - `is_semantic_chunker_available()` detecta disponibilidad en import time.
  - `chunk_semantic()` retorna `list[ChunkResult]` compatible con persistencia actual.
  - `_SEMANTIC_CHUNKER_AVAILABLE = False` actualmente (langchain_experimental no instalado).
- Se extendió `worker.py`:
  - `persist_package_documents()` ahora acepta `chunk_strategy` parameter.
  - `CHUNK_STRATEGIES = {"structural", "semantic", "semantic_with_structural_fallback"}`.
  - `_choose_chunking()`: dispatcher interno que selecciona chunker según estrategia.
  - `structural` (default): comportamiento exacto pre-Fase 1.4b.
  - `semantic`: error claro `RuntimeError` si SemanticChunker no disponible.
  - `semantic_with_structural_fallback`: intenta semantic, cae a structural con warning.
  - dry_run con `semantic` propaga error `RuntimeError` (no silent fallback).
- Se actualizó `scripts/run_knowledge_ingestion_local.py`:
  - Nuevo flag `--chunk-strategy` con choices: `structural`, `semantic`, `semantic_with_structural_fallback`.
  - Se muestra estrategia en output.
- Tests: 14 nuevos (total: 103 KI tests, 191 suite completa).
  - `TestSemanticChunker`: verifica que module-level flag es False, `chunk_semantic()` raisea RuntimeError.
  - `TestChunkStrategyStructural`: default, explicit, dry_run, no embeddings/Milvus/Arango.
  - `TestChunkStrategySemantic`: unavailable → doc INVALID en persist, RuntimeError en dry_run, unchanged no llama chunking.
  - `TestChunkStrategyFallback`: unavailable → structural + warning visible en output, dry_run estima chunks, unchanged no toca chunks.
  - `TestChunkStrategyInvalid`: strategy inválida → ValueError.
- No se tocó `pyproject.toml`: SemanticChunker no disponible, tests usan mock implícito vía module flag.
- No embeddings, no Milvus, no ArangoDB, no LLM, no frontend, no routes, no migrations.
- Integración local dry-run validada:
  - `--chunk-strategy structural`: 40 chunks estimados.
  - `--chunk-strategy semantic_with_structural_fallback`: 40 chunks estimados (fallback estructural).

### 2026-06-09 - Fase 1.6d completa: Breaking Points lab runner + ejecucion real

- Creado `run_breaking_points.py`: runner que importa `KnowledgeIngestionWorker` desde backend vía sys.path, lee `golden_cases/breaking_point_cases.json`, ejecuta retrieval pgvector con OpenAI embedding, evalúa expected/forbidden concepts sin LLM, guarda JSON+Markdown.
- Creado `scripts/generate_report.py`: lee JSON y genera reporte detallado con matriz de ruptura, análisis por caso, arquitectura implicada.
- Creado `scripts/generate_infographics.py`: genera HTML dark-theme con summary cards y tabla ejecutiva.
- Actualizado README.md con instrucciones de ejecución (desde `backend/` con `uv run`), tabla de parámetros, variables de entorno, resultados baseline.
- **Ejecución real validada**:
  - `--dry-run`: 25/25 casos OK.
  - `--max-cases 3`: 2/3 PASS, bp_03 FAIL (step_to_action no en chunks).
  - `--limit 5` (full 25): 5/25 PASS (20%), 20/25 FAIL, score total -31.
  - 0 conceptos prohibidos en top-3 (el sistema no alucina ni recupera ruido).
- **Hallazgo principal**: 20/20 fallos son `embedding_ranking_problem` → **content_gap**, no límite de pgvector. Cuando el chunk contiene el concepto exacto (automatizable, diagnostic_code, scope), el retrieval funciona perfectamente. El punto de ruptura actual es cobertura del corpus (40 chunks), no el backend vectorial.
- Decisión algorítmica: D. Pero interpretación humana: PostgreSQL alcanza con mejor contenido/metadata filters/reranking.
- No se tocó: pipeline productivo, frontend, routes, HTTP, diagnosis, automation_diagnosis, Milvus, ArangoDB, migraciones.
- Rama: `feature/knowledge-ingestion-service`
- No se hizo git add ni commit.

### 2026-06-09 - Fase 1.6g: Oracle-lite reranking experiment (techo del reranker)

- Se creó `run_oracle_lite_reranking_experiment.py` con reranker oracle-lite que reordena candidates usando `expected_concepts` del golden case como señal perfecta.
- Resultado: oráculo basado en conceptos esperados mejora de 11/25 (44%) a 17/25 (68%), +24pp, gap al techo = 24pp.
- Casos mejorados: 6 (bp_01, bp_03, bp_07, bp_08, bp_14, bp_18). Casos empeorados: 0 (oráculo nunca empeora).
- Decisión arquitectónica: B. Diseñar reranker runtime — el margen de 24pp justifica una Fase 1.6h con reranker no-oráculo.
- No se tocó: pipeline productivo, frontend, routes, HTTP, diagnosis, automation_diagnosis, Milvus, ArangoDB, migraciones.
- Rama: `feature/knowledge-ingestion-service`

### 2026-06-09 - Fase 1.6h: Non-oracle reranking experiment (señales reales)

- Se creó `run_non_oracle_reranking_experiment.py` con reranker determinístico usando 6 señales reales (lexical_overlap, phrase_match, domain_vocabulary, safety, metadata_boost, vector_distance).
- Baseline: 11/25 (44%). Non-oracle reranked: 11/25 (44%). Delta: +0.0pp. Oracle-lite: 68%.
- Gap to oracle: 24pp — margen que un cross-encoder puede recuperar.
- Casos mejorados: 1 (bp_14). Casos empeorados: 1 (bp_05 — conceptos prohibidos entraron en top-5).
- Conceptos prohibidos baseline: 0. Conceptos prohibidos reranked: 3 — riesgo comercial: el reranker lexical empujó chunks con contenido sensible.
- Clasificación de fallos post-reranking: correct_not_in_candidates (8), reranker_not_powerful_enough (3), forbidden_concepts_still_present (2), semantic_gap_or_paraphrase_problem (1).
- Recomendación: F. Cross-encoder necesario — señales léxicas no alcanzan. El gap de 24pp entre oracle-lite (68%) y non-oracle (44%) significa que el conocimiento semántico (qué conceptos esperar por caso) es necesario; un cross-encoder real (ej. BAAI/bge-reranker-v2-m3) puede cerrar ese gap.
- Reportes generados: `results/non_oracle_reranking_20260609_165520.json`, `.md`, `_detailed_report.md`.
- Rama: `feature/knowledge-ingestion-service`
- No se hizo git add ni commit.

### 2026-06-09 - Fase 1.6i: Cross-encoder reranking experiment (preparación)

- Se creó `run_cross_encoder_reranking_experiment.py` con estructura completa para evaluar BAAI/bge-reranker-v2-m3 sobre los 25 breaking point cases.
- El script detecta dependencias faltantes (sentence-transformers, torch, transformers) y termina con status BLOCKED + instrucciones claras, sin traceback.
- Se creó `scripts/generate_cross_encoder_reranking_report.py` que maneja ausencia de resultados con mensaje instructivo.
- Se actualizó `README.md` con sección Fase 1.6i completa: objetivo, hipótesis, estrategia, parámetros, decision rules, outputs.
- **No se instalaron dependencias.** No se descargaron modelos. No se modificó pyproject.toml.
- Dependencias opcionales para ejecutar: `uv add "sentence-transformers>=3.0" "torch>=2.0" "transformers>=4.40"`.
- **Estado: bloqueado por dependencias.** El experimento queda preparado para ejecutarse cuando se instalen las dependencias.
- No se tocó: backend productivo, frontend, routes, migrations, Milvus, ArangoDB, LLM.
- Rama: `feature/knowledge-ingestion-service`
- No se hizo git add ni commit.

### 2026-06-09 - Fase 1.6j: Milvus 2.6 vs pgvector benchmark

- Se ejecutó benchmark comparando Milvus 2.6 vs PostgreSQL/pgvector como índice vectorial derivado para los 25 breaking-point cases.
- Se crearon `scripts/generate_report.py`, `scripts/generate_infographics.py` y `README.md` en `lab/milvus-pgvector-benchmark/`.
- **Resultados:** pgvector 11/25 (44.0%), Milvus 11/25 (44.0%). Calidad idéntica.
- **Latencia:** pgvector 859.2ms avg vs Milvus 13.9ms avg (~62x más rápido).
- **Casos mejorados/empeorados:** 0/0. Ambos sistemas recuperan los mismos candidatos correctos (17/25) y fallan los mismos 14 casos.
- **Clasificación de fallos:** 8 correct_not_in_candidates (content_gap), resto ranking/overpromise — idéntico en ambos sistemas.
- **Recomendación:** D. Evaluar Milvus como índice derivado por latencia — significativamente más rápido. No mejora calidad de retrieval. PostgreSQL sigue siendo source of truth.
- Reportes generados: `results/milvus_pgvector_benchmark_20260609_172200.json`, `.md`, `_detailed_report.md`, `infografias/milvus_pgvector_benchmark_20260609_172200_infografia.html`.
- Se corrigió import path en `run_milvus_benchmark.py` (sys.path para shared utils desde breaking-points lab) y API de `IndexParams` para pymilvus 3.0.
- Colección Milvus experimental: `team360_lab_pgvector_benchmark_openai_small_1536` (139 embeddings indexados, HNSW COSINE).
- Rama: `feature/knowledge-ingestion-service`
- No se hizo git add ni commit.

### 2026-06-09 - Fase 1.6k: RAG answer generation lab — Milvus + gpt-5-nano low

- Se creó `lab/rag-answer-generation-milvus-gpt5nano/` con flujo RAG completo: query → Milvus retrieval → contexto Markdown → gpt-5-nano low → respuesta comercial.
- **16 casos de prueba** creados en `cases/rag_answer_cases.json` cubriendo: comercial general, ventas/seguimiento, WhatsApp, diagnóstico, anti-overpromise, límites comerciales, ambigüedad y seguridad/scope.
- **Retrieval:** Milvus devuelve 20 chunks en ~5.3ms promedio. La colección Fase 1.6j (139 embeddings) reutilizada sin re-embedding.
- **gpt-5-nano low:** Disponible en OpenAI API. Requiere `max_completion_tokens` (no `max_tokens`). Reasoning effort `low` soportado.
- **Resultados heurísticos:** 7/16 pass (43.8%), 4/8 high-risk pass (50.0%). Latencia total ~4.8s (retrieval ~5ms + LLM ~4s).
- **Hallazgos:** Retrieval en Milvus excelente (baja latencia). gpt-5-nano low genera respuestas coherentes. Evaluación heurística con falsos positivos en safety flags (substring matching muy agresivo — "ars"/"sla" matchean como subcadenas).
- **Recomendación:** C. Probar gpt-5-mini / medium en siguiente lab. La latencia LLM (~4s) domina el tiempo total. Milvus no es cuello de botella.
- Archivos creados: `README.md`, `run_rag_answer_lab.py`, `cases/rag_answer_cases.json`, `scripts/generate_report.py`, `scripts/generate_infographics.py`, `results/*.json/*.md`, `infografias/*.html`.
- Fix: se corrigió `call_llm` para usar `max_completion_tokens` en modelos o-series/gpt-5.
- No se tocó: frontend, routes, endpoints HTTP, diagnosis productivo, ArangoDB, cross-encoder, production runtime, migrations, documents approved/drafts, secrets.
- Rama: `feature/knowledge-ingestion-service`
- No se hizo git add ni commit.

## Notas de seguridad

- No se grabo la password de GitHub en archivos del proyecto.
- Se uso un archivo temporal de sesion en `/tmp/team360_github_state.json` solo para diagnostico y se elimino al terminar.
- Se cerro la sesion del navegador automatizado al finalizar la tarea.
- No se hardcodearon secretos reales.
- Las credenciales de providers/LLM se modelaron como `secret_ref`.
- `backend/temp1.txt` aparece modificado en el worktree y contiene material sensible o notas internas; no fue tocado en esta etapa.

### 2026-06-14 - Fase 1.3c: Pre-ingestion readiness gate

- Se agregó `check_document_ingestion_readiness()` en `schemas.py` como gate estricto previo a chunking/embedding/indexing.
- Se agregó `IngestionReadinessGateResult` dataclass con `ready`, `error_codes`, `error_messages`.
- Se agregó constante `INGESTION_READINESS_ERROR_CODES` con: `document_not_ready`, `ingestion_status_not_ready`, `missing_ingestion_status`, `planned_extension_not_active`.
- Validaciones del gate: `ingestion_status` ausente → `missing_ingestion_status`; `ingestion_status != "ready"` → `ingestion_status_not_ready`; `status == "draft"` → `document_not_ready`; `extension` no vacío → `planned_extension_not_active`.
- Integración en `worker.py`: gate se ejecuta en skip block (no candidato) + como validación adicional para candidatos que pasan scanner (catch planned_extension).
- Gate acepta frontmatter `None` y produce `document_not_ready` con error claro.
- Scanner sigue reportando draft/not_ready sin fallar (dry-run compatible).
- Worker rechaza documentos no ready con `action="rejected_by_gate"` y `status=INVALID`.
- No se crean chunks para documentos rechazados por el gate.
- 11 tests nuevos (6 pura función + 5 integración worker), total: 138 tests knowledge ingestion, 226 suite completa.
- No se tocaron manuales/drafts/docs branch/endpoints/Milvus/embeddings/diagnosis runtime.

### 2026-06-14 - Fase 1.3d: Backend-only ingestion pipeline smoke

- Se creó `backend/scripts/smoke_knowledge_ingestion_pipeline.py` como smoke autónomo:
  - Crea paquete temporal en tmpdir con 2 documentos: approved/ready + draft/not_ready.
  - Ejecuta scanner → readiness gate → markdown chunking → worker persist (fake DB).
  - Verifica que ready doc produce chunks y not_ready es rechazado.
  - Verifica preservación de node_path, area_key, topic_key, access_tags, status, ingestion_status.
  - Verifica planned_extension rejection con error code claro.
  - Verifica que no hay embeddings/Milvus en el pipeline.
  - Usa `_FakeConnection` autónomo (no importa de tests).
  - Exit code 0 si todo pasa.
- Se agregó `TestIngestionPipelineSmoke` en `test_knowledge_ingestion.py` con 8 tests:
  - `test_pipeline_smoke_scans_ready_and_not_ready`: scanner reporta ambos sin fallar.
  - `test_pipeline_smoke_chunks_only_ready`: solo ready genera chunks.
  - `test_pipeline_smoke_reports_not_ready_gate_errors`: errores del gate se reportan.
  - `test_pipeline_smoke_preserves_node_path_and_area_topic`: metadatos preservados.
  - `test_pipeline_smoke_preserves_access_tags_and_permission_tags`: tags propagados.
  - `test_pipeline_smoke_does_not_use_embeddings_or_milvus`: sin llamadas a embeddings/Milvus.
  - `test_pipeline_smoke_planned_extension_not_active`: extension rechazada antes de chunking.
  - `test_pipeline_smoke_markdown_chunking_before_embedding`: chunking estructural antes de embedding.
- Validación: 8 nuevos tests + 138 existentes = 146 tests knowledge ingestion; suite completa: 234/234 passed.
- `git diff --check` limpio. Sin cambios en corpus documental, manuales, drafts, endpoints, Milvus, embeddings reales, SemanticChunker obligatorio, frontend, diagnosis runtime.

### 2026-06-14 - Fase 1.3e: Internal dev endpoint contract

- Se creó `backend/routes/knowledge_ingestion_dev.py` con endpoint interno/dev:
  - `POST /api/dev/knowledge-ingestion/ingest` con `status_code=200`.
  - Request: `DevIngestRequest` (Pydantic) con `package_code`, `package_path`, `mode` (dry_run/persist), `include_drafts`, `chunking_strategy`.
  - Response: `DevIngestResponse` con `ok`, `mode`, `package_code`, `document_count`, `candidate_count`, `ready_count`, `rejected_count`, `chunk_count`, `documents[]`, `errors[]`.
  - Cada documento en respuesta incluye: `relative_path`, `node_path`, `status`, `ingestion_status`, `candidate_for_ingestion`, `gate_ready`, `chunk_count`, `error_codes`, `error_messages`.
- Seguridad de path: rechaza `..` traversal antes de `Path.resolve()`, rechaza paths inexistentes o que no son directorios.
- `dry_run` (default): escanea paquete via `KnowledgePackageScanner`, aplica `check_document_ingestion_readiness()` en cada documento, estima chunks via `chunk_markdown()`. Sin DB, sin OpenAI, sin Milvus, sin SemanticChunker.
- `persist`: rechazado con error claro ("requires a database connection") — disponible para fase posterior con infraestructura DB.
- `include_drafts` se pasa al scanner; `chunking_strategy` solo acepta `"markdown"` por ahora.
- Registrado en `app.py` como `ingest_dev` en `route_handlers`.
- Se creó `backend/tests/test_knowledge_ingestion_dev_route.py` con 16 tests:
  - `test_post_ingest_dry_run_returns_scan_summary`
  - `test_post_ingest_requires_package_code`
  - `test_post_ingest_requires_package_path`
  - `test_post_ingest_rejects_invalid_path`
  - `test_post_ingest_rejects_path_traversal`
  - `test_post_ingest_rejects_path_that_is_file`
  - `test_post_ingest_rejects_unknown_mode`
  - `test_post_ingest_rejects_unknown_chunking_strategy`
  - `test_post_ingest_reports_not_ready_gate_errors`
  - `test_post_ingest_does_not_chunk_not_ready_documents`
  - `test_post_ingest_chunks_ready_documents_with_markdown_chunker`
  - `test_post_ingest_does_not_call_openai_or_milvus`
  - `test_post_ingest_does_not_use_semantic_chunker_when_unavailable`
  - `test_post_ingest_response_contract_is_stable`
  - `test_post_ingest_persist_mode_returns_error_no_db`
  - `test_route_is_marked_dev_internal`
- Todos los tests usan `tmp_path` para crear paquetes temporales — no tocan corpus documental real.
- Validación: 16 nuevos tests, suite completa 250/250 passed.
- `git diff --check` limpio. Sin frontend, sin Milvus, sin embeddings reales, sin OpenAI, sin SemanticChunker obligatorio, sin manuales/drafts reales, sin docs branch, sin diagnosis runtime, sin upload público.

### 2026-06-14 - Fase 1.3f: Controlled DB-backed persist mode for dev endpoint

- Se reescribió `backend/routes/knowledge_ingestion_dev.py` con soporte `persist` mode completo:
  - `_run_persist_pipeline()` es función module-level async, diseñada para ser monkeypatcheable en tests (evita dependencia DB real).
  - Persist mode auto-detecta `organization_code`, `workspace_code`, `knowledge_scope_code` del frontmatter del primer documento ready en el scan.
  - Reusa `worker.persist_package_documents()` con `chunk_strategy="structural"`, `dry_run=False`, `include_chunks=True`.
  - Responde con `run_id`, `persisted_document_count`, `persisted_chunk_count`, `errors` del worker.
  - Resultados de persistencia se mergean con scanner metadata (preserva `node_path`, `status`, `ingestion_status`, `gate_ready`, `persisted`, `document_id` por documento).
  - Errores del worker se capturan con `try/except` y devuelven como mensajes de error, no stacktraces.
  - Sin DB configurada → error claro "persist mode requires a database connection: set TEAM360_DB_URL or equivalent".
  - Sin códigos detectables (org/workspace/scope) → error con mensaje específico.
- Se actualizaron tests en `test_knowledge_ingestion_dev_route.py`:
  - Se agregó `import routes.knowledge_ingestion_dev as dev_route` para monkeypatch.
  - Se eliminó el viejo test `test_post_ingest_persist_mode_returns_error_no_db` (no funcionaba en entornos con `DB_PG_V360_URL` set).
  - Se reescribió como `test_post_ingest_persist_requires_database_configuration` con `monkeypatch` de `_is_db_configured` → False.
  - 9 tests nuevos de persist mode (total route tests: 25):
    - `test_post_ingest_persist_requires_database_configuration`
    - `test_post_ingest_persist_uses_worker_or_repository`
    - `test_post_ingest_persist_persists_only_ready_documents_with_fake_repo`
    - `test_post_ingest_persist_does_not_persist_not_ready_chunks`
    - `test_post_ingest_persist_reports_gate_errors`
    - `test_post_ingest_persist_response_contract_is_stable`
    - `test_post_ingest_persist_does_not_call_openai_or_milvus`
    - `test_post_ingest_persist_handles_repository_error_without_stacktrace`
    - `test_post_ingest_persist_preserves_node_path_access_tags_permission_tags`
    - `test_post_ingest_dry_run_still_works_after_persist_changes`
  - Helper `_fake_persist_result()` para construir respuestas fake del pipeline.
- Validación: suite completa 259/259 passed (250 + 9 nuevos).
- `git diff --check` limpio. Sin DB real para persist mode, sin OpenAI, sin Milvus, sin SemanticChunker, sin frontend, sin manuales/drafts reales, sin diagnóstico productivo.

### 2026-06-14 - Fase 1.3g: PostgreSQL smoke for dev ingestion endpoint

- Se creó `scripts/smoke_knowledge_ingestion_dev_endpoint_postgres.py`:
  - Usa `TestClient(app)` para llamar endpoint real.
  - Paquete temporal via `tempfile.mkdtemp()` con prefix `smoke_persist_pkg_`.
  - Docs ready y not_ready con prefijo `smoke_doc_` en source_uri y node_path.
  - Usa códigos seed existentes (`team360_live`, `team360_public_site`, `ks_team360_sales_diagnosis`, `pkg_sales_diagnosis`) pero aislado por source_uri único.
  - `mode=persist` contra PostgreSQL real.
  - Cleanup por `run_id` + `source_uri`, explícitamente sin `package_code` DELETE amplio.
  - DB verification directa via `AsyncConnection.connect()` (evita pool hang issue).
  - No Milvus, no OpenAI, no embeddings reales.
- Se crearon 15 tests contract en `tests/test_knowledge_ingestion_dev_endpoint_postgres_smoke_contract.py`:
  - Verifica estructura del script: existe, es Python, importable.
  - Verifica uso de temp package (no corpus real).
  - Verifica endpoint POST persist.
  - Verifica DB config check con error claro.
  - Verifica `sanitize_dsn` para no imprimir DB URL raw.
  - Verifica checks de ready/not_ready persistence.
  - Verifica chunks solo para ready docs.
  - Verifica no embeddings/Milvus/OpenAI.
  - Verifica cleanup sin broad `package_code` delete.
  - Verifica cleanup usa `run_id` y `source_uri`.
  - Verifica smoke usa namespace real pero controlado.
- Smoke real contra PostgreSQL: **50/50 passed** (48 funcionales + 2 dinámicos de fuente).
- Suite completa: **274/274 passed** (259 + 15 contract nuevos).
- `git diff --check` limpio. Sin DB real, sin Milvus, sin OpenAI, sin manuales/drafts reales.

### 2026-06-14 - Fase 1.3h: Chunk embedding persistence contract

- **Auditoría**: `knowledge_chunk_embeddings` ya existe via migration 003 con pgvector `vector(1536)`, HNSW index, `knowledge_embedding_models` catalog. Repository ya tenía `find_existing_chunk_embedding`, `insert_chunk_embedding`, `search_chunks_by_embedding` (con `<=>` operator). Worker ya tenía `embed_pending_chunks()` y `retrieve_knowledge_chunks()`.
- **Sin migración nueva** — la tabla existente es la definitiva.
- **No se modificó endpoint dev** para generar embeddings automáticos.
- **schemas.py**: agregados:
  - `EmbeddingStatus` class con constantes `PENDING`, `PROCESSING`, `READY`, `FAILED`, `SKIPPED` y `VALID_STATUSES`.
  - `KnowledgeChunkEmbeddingRecord` dataclass con `chunk_embedding_id`, `knowledge_chunk_id`, `provider`, `model`, `embedding_version`, `dimensions`, `content_hash`, `embedding_status`, `vector`, `metadata_jsonb`, timestamps.
  - `ChunkEmbeddingUpsertRequest` dataclass con validación de campos requeridos (chunk_id, provider, model, embedding_version, dimensions>0, content_hash, status válido, vector dimensión consistente).
- **embedding_provider.py**: agregados:
  - `__repr__` seguro en `OpenAIEmbeddingProvider` (no expone API key).
  - `FakeEmbeddingProvider` para tests: devuelve vector unitario normalizado de dimensión configurable (default 1536). Sin llamadas externas.
- **repository.py**: agregados:
  - `upsert_chunk_embedding()`: resuelve `embedding_model_id` del catálogo, usa `INSERT ... ON CONFLICT (knowledge_chunk_id, embedding_model_id) DO UPDATE` sobre la tabla existente. Almacena `embedding_version`, `provider`, `model`, `dimensions` en `metadata_jsonb`.
  - `list_chunk_embeddings_for_run()`: join a través de `knowledge_ingestion_runs` → `knowledge_documents` (por `knowledge_scope_id`) → `knowledge_chunks` → `knowledge_chunk_embeddings`. Retorna lista con chunk_id, document_id, source_uri, chunk_index, provider, model, dimensions, status, content_hash, metadata, timestamps.
  - Métodos existentes no modificados.
- **worker.py**: agregado parámetro `include_embeddings: bool = False` en `persist_package_documents()`. Por defecto `False`. Si `True` sin `include_chunks=True`, lanza `ValueError`. Endpoint dev no pasa `include_embeddings`.
- **Tests**: 36 tests en `tests/test_knowledge_ingestion_embeddings.py`:
  - `TestEmbeddingStatus`: 7 tests (constantes válidas, cobertura total).
  - `TestKnowledgeChunkEmbeddingRecord`: 3 tests (preserva chunk_id/model/version/dimensions/status, vector default None, metadata default empty).
  - `TestChunkEmbeddingUpsertRequest`: 8 tests (validación campos requeridos, dimensiones, status inválido, mismatch vector/dimension).
  - `TestFakeEmbeddingProvider`: 6 tests (dimensiones default y custom, vector unitario normalizado, multi-text, empty input, repr sin secrets).
  - `TestOpenAIEmbeddingProviderContract`: 2 tests (repr sin API key, no API call en import/init).
  - `TestRepositoryEmbeddingMethods`: 4 tests (upsert refiere a tabla existente, usa chunk_id+content_hash, list join correcto, find_embedding_model_id refiere a catálogo).
  - `TestWorkerEmbeddingDefault`: 2 tests (default False, True requiere include_chunks).
  - `TestDevEndpointNoEmbeddings`: 2 tests (endpoint no pasa include_embeddings, docstring explicita no real embeddings).
  - `TestPlannedExtensionNotActivatingEmbeddings`: 1 test (planned_extension no activa embeddings).
  - `TestNoMilvusInTests`: 1 test (no import Milvus).
- **Validación**: 36 tests nuevos embedding + 274 existentes = **310/310 passed**.
- **Smoke PostgreSQL**: 50/50 passed (sin cambios en smoke — endpoint sigue sin generar embeddings).
- `git diff --check` limpio. Secret scan: sin leaks nuevos.
- Sin Milvus, sin OpenAI real en tests, sin embeddings automáticos desde endpoint, sin frontend, sin upload público, sin corpus documental real, sin docs branch, sin diagnosis runtime.

### 2026-06-14 - Fase 1.3i: OpenAI embeddings + Milvus 2.6 indexing smoke

- **Sin cambios en módulos productivos** — solo se agregaron scripts y tests contract.
- **Sin Milvus module wrapper** — el smoke usa pymilvus inline (patrón de labs existentes).
- **No se modificó endpoint dev** — sigue sin generar embeddings ni indexar Milvus por defecto.
- **No se tocó corpus real, frontend, ni diagnosis runtime.**
- Se creó `scripts/smoke_knowledge_ingestion_embeddings_milvus.py`:
  - Valida 6 env vars/flags antes de ejecutar:
    - `TEAM360_DB_URL`
    - `OPENAI_API_KEY`
    - `TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS=true`
    - `TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS=true`
    - `TEAM360_MILVUS_HOST` (o `MILVUS_URI`)
    - `TEAM360_MILVUS_PORT` (opcional, default 19530)
  - Usa `sanitize_dsn()` para DB URL, `_sanitize()` para secrets — no imprime API keys ni tokens.
  - Crea paquete temporal con documento ready y not_ready.
  - Llama endpoint dev persist (`POST /api/dev/knowledge-ingestion/ingest`) para crear run/docs/chunks.
  - Genera embeddings reales via `OpenAIEmbeddingProvider` solo para chunks ready.
  - Persiste embeddings en `knowledge_chunk_embeddings` (PostgreSQL, tabla existente).
  - Verifica que not_ready NO tiene chunks → NO embeddings.
  - Crea colección temporal Milvus con prefijo `team360_smoke_<timestamp>`.
  - Indexa embeddings a Milvus en batches de 100 (HNSW/COSINE).
  - Busca en Milvus con query relacionada al contenido del documento ready.
  - Verifica que el resultado contiene el chunk ready esperado (score > 0, node_path smoke, contenido financiero).
  - Cleanup PostgreSQL: DELETE por source_uri prefix + run_id, no por package_code.
  - Cleanup Milvus: drop de la colección temporal smoke (nunca borra colección productiva).
  - Aborta con SKIP exit code 0 si faltan env vars.
  - Mensaje de error claro listando cada variable faltante.
- Se crearon 18 tests contract en `tests/test_knowledge_ingestion_embeddings_milvus_smoke_contract.py`:
  - Verifica existencia, estructura y requerimientos de env/flags.
  - Verifica que no imprime API key, DB URL, ni Milvus token.
  - Verifica que usa temp package, no corpus real.
  - Verifica que cleanup no usa package_code DELETE amplio.
  - Verifica que Milvus cleanup solo dropea colección smoke, no colección productiva.
  - Verifica checks de not_ready sin embeddings/vectores.
  - Verifica checks de búsqueda Milvus.
  - Todos sin OpenAI/Milvus real.
- Suite completa: **328/328 passed** (310 previos + 18 contract tests nuevos).
- Smokes existentes no modificados: PostgreSQL smoke sigue 50/50.
- `git diff --check` limpio. Secret scan: sin leaks nuevos.
- **Smoke real OpenAI+Milvus no ejecutado** por falta de `OPENAI_API_KEY` y `TEAM360_MILVUS_HOST` en el entorno.
  - Comando listo:
    ```bash
    TEAM360_KNOWLEDGE_INGESTION_ENABLE_REAL_EMBEDDINGS=true \
    TEAM360_KNOWLEDGE_INGESTION_ENABLE_MILVUS=true \
    PYTHONPATH=. uv run python scripts/smoke_knowledge_ingestion_embeddings_milvus.py
    ```
- Sin Milvus, sin OpenAI real en tests, sin embeddings automáticos desde endpoint, sin frontend, sin upload público, sin corpus documental real, sin docs branch, sin diagnosis runtime.

### 2026-06-14 - Fase 1.4: Endpoint hardening — scope, permisos y seguridad

- **Endpoint `DevIngestRequest` extendido** con campos obligatorios para persist:
  - `organization_code` (requerido para persist)
  - `workspace_code` (requerido para persist)
  - `knowledge_scope_code` (requerido para persist)
  - `requested_by` (default `dev_internal`)
  - `source_type` (default `markdown`, validado contra `SOURCE_TYPES`)
- **`DevIngestResponse` extendido** con:
  - `scope_warnings: list[str]` — advertencias de scope (reportadas en dry_run)
  - `scope_errors: list[str]` — errores de scope (rechazan persist)
  - `requested_by: str` — quién solicitó la operación
- **`DevIngestDocumentResult` extendido** con `scope_errors: list[str]` por documento.
- **Validaciones agregadas:**
  - `_validate_scope_codes()`: requiere org/ws/ks para persist, rechaza identificadores `vera_*`, valida `source_type`.
  - `_check_document_scope_consistency()`: compara códigos del request vs frontmatter de documentos ready.
  - `_check_access_tags()`: verifica que documentos ready tengan `access_tags` no vacío.
  - `_reject_forbidden_technical_id()`: rechaza prefijos `vera_*` con HTTP 422.
- **Persist mode**: rechaza scope incompleto, mismatch, falta de access_tags, identificadores prohibidos.
- **Dry run mode**: scope opcional, mismatch reportado como warning, no aborta.
- **Tests**: 38 en `test_knowledge_ingestion_dev_route.py` (25 previos + 13 nuevos: scope requerido, mismatch por org/ws/ks/pkg, vera_*, dry_run warning, access_tags, planned_extension, response contract).
- **Smoke PostgreSQL actualizado**: incluye scope codes en request.
- Suite completa: **341/341 passed**. Smoke PostgreSQL: **50/50 passed**.
- Sin frontend, sin upload público, sin Milvus/OpenAI default, sin corpus real.

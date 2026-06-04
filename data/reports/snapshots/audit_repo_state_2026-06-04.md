# Auditoría de estado del repositorio Team360

**Fecha:** 2026-06-04
**Rama:** `feature/console-backend-core`
**Propósito:** Relevar estado real del desarrollo para continuidad técnica.

---

## 1. Estado Git

| Elemento | Valor |
|---|---|
| Rama activa | `feature/console-backend-core` |
| Commits sin publicar | ~8 (ultimo commit: `5fd0f21 Add read-only ConsoleBootstrap repositories`) |
| Archivos modificados (unstaged) | 23 |
| Archivos nuevos (untracked) | 8 |

### Últimos commits
```
5fd0f21 Add read-only ConsoleBootstrap repositories
66a7130 Add psycopg async DB runtime module
10a8948 Document ConsoleBootstrap contract
906fe04 Document console backend alignment
9efb584 docs: add Team360 branch workflow shortcuts
6eeac3d chore: ignore local Codex state
5a2f0f2 chore: add Team360 backend schema audit and knowledge migration
ba980b7 feat: add Team360 public home and console mock UX
```

### Archivos nuevos sin trackear
- `004_team360_automation_diagnosis_runtime.sql` — migracion 004
- `assistant_instances.py` — contratos de assistant instance package
- `postgres_repository.py` — repository async de escritura
- `test_automation_diagnosis_postgres_repository.py` — tests del repository
- `postgresql_004_automation_diagnosis_runtime.md` — documentacion migracion 004
- `team360_ai_diagnostico_stack_arango_milvus_litellm.md` — analisis tecnico RAG
- `ai-diagnosis-rag-runtime.md` — decision arquitectura viva RAG
- `customer-packaged-assistant-instance.md` — decision arquitectura viva customer installation

---

## 2. automation_diagnosis — Módulo completo

**Ubicación:** `backend/modules/automation_diagnosis/`
**Archivos (21 entries):** 15 modulos Python + `fixtures/` + `__pycache__/`

### Componentes existentes
| Archivo | Rol | Status |
|---|---|---|
| `service.py` | Orquestador del flujo de diagnostico | Modificado (scope por assistant_instance) |
| `assistant_instances.py` | **NUEVO** — Contrato de configuracion de assistant instance como cliente | Untracked |
| `postgres_repository.py` | **NUEVO** — Repository async de escritura PostgreSQL | Untracked |
| `schemas.py` | Dataclasses: KnowledgeScope, DiagnosisSession, DiagnosisEvent, etc. | Modificado (defaults apuntan a team360_sales_diagnosis) |
| `events.py` | InMemoryEventRecorder | Modificado (payload enrich) |
| `knowledge_connector.py` | InMemoryKnowledgeRepository con carga multi-scope | Modificado (carga por assistant_instance configs) |
| `lead_output.py` | build_internal_card() con metadata completa | Modificado (organization_id, site_channel, locale, etc.) |
| `ai_interpreter.py` | Puerto IA, LiteLLM real + MockAIInterpreter | Estable |
| `answer_collector.py` | Normalizacion de respuestas | Estable |
| `classifier.py` | Clasificador deterministico | Estable |
| `chunker.py` | Chunking de documentos | Estable |
| `document_loader.py` | Carga de documentos Markdown | Estable |
| `guided_flow.py` | Flujo guiado de preguntas | Estable |
| `litellm_client.py` | Cliente LiteLLM | Estable |
| `repository.py` | InMemoryDiagnosisRepository | Estable |
| `result_generator.py` | Generacion de resultado usuario | Estable |
| `retrieval.py` | Retrieval keyword simple | Estable |
| `scoring.py` | Score de session | Estable |
| `__init__.py` | Export publico | Modificado (agrega assistant_instances) |

### Flujo del servicio (`AutomationDiagnosisService`)
```
start_session()
  -> resolve_assistant_instance_config()  # scope por assistant_instance_id
  -> config.resolve_locale()               # validacion locale
  -> crea DiagnosisSession con metadata completa (org, workspace, channel, lead_owner, workers, cost_attribution)
  -> save_session() en repository
  -> event_recorder.emit() con payload enriquecido

classify()
  -> answers_as_text()
  -> knowledge_repository.search(scope_id, ...)  # scoped por assistant_instance
  -> ai_interpreter.interpret()
  -> score_session()
  -> classify_session()
  -> generate_user_result() + build_internal_card()
  -> session.result = result
```

### Contrato de Assistant Instance (`assistant_instances.py`)
- `AssistantInstanceConfig`: dataclass frozen con organization_id, workspace_id, assistant_instance_id, knowledge_scope_id, site_channel, lead_owner, supported_locales, package_workers, arangodb_scope, milvus_scope
- `TEAM360_SALES_DIAGNOSIS_CONFIG`: instancia concreta de Team360 como primer cliente (workspace `team360_public_site`, 9 package workers)
- `LEGACY_AUTOMATION_DIAGNOSIS_CONFIG`: config de compatibilidad para fixtures/lab legacy
- `resolve_assistant_instance_config()`: resuelve por payload o default, valida scope
- `validate_payload_scope()`: rechaza overrides de workspace_id, automation_package_id, knowledge_scope_id

---

## 3. PostgreSQL Runtime — psycopg 3 async

**Ubicación:** `backend/modules/db/`
**Archivos (6 entries):** `__init__.py`, `errors.py`, `pool.py`, `settings.py`, `transaction.py`

### Componentes
| Archivo | Funcion |
|---|---|
| `settings.py` | `DatabaseSettings` (dataclass), resuelve DSN desde `TEAM360_DB_URL` / `TEAM360_DB_URL_PSQL` / `DB_PG_V360_URL`, sanitiza DSN para logs |
| `pool.py` | `create_pool()`, `open_pool()`, `close_pool()`, `get_pool()`, `reset_pool_for_tests()` |
| `transaction.py` | `fetch_one()`, `fetch_all()`, `execute()`, `transaction()` context manager async |
| `errors.py` | `DatabaseError`, `DatabaseConfigurationError`, `DatabasePoolNotInitializedError`, `DatabaseExecutionError` |

### Politica establecida
- Driver: `psycopg` 3 async con `AsyncConnectionPool`
- Pool se crea con `open=False` (no abre conexiones al importar)
- SQL parametrizado directo, sin SQLAlchemy/SQLModel/Pydantic en repositorios
- Repositories reciben `AsyncConnection` desde el caller (no abren conexiones propias)

---

## 4. Migración 004 — automation_diagnosis_runtime

**Archivo:** `backend/db/migrations/004_team360_automation_diagnosis_runtime.sql`
**Status:** Aplicada sobre DB `team360` (verificado por smoke real y auditoria)

### Lo que crea
1. **`assistant_instances.assistant_code`** — columna + unique index parcial `uq_assistant_instances_workspace_code`
2. **`automation_diagnosis_sessions`** — sesiones con FK a workspace, assistant_instance, automation_package, knowledge_scope + constraints de status/locale
3. **`automation_diagnosis_answers`** — respuestas por sesion, unique por `(session_id, step_id)`
4. **`automation_diagnosis_leads`** — leads con FK a session + constraints de status, classification, automation_mode
5. **`uq_ksb_binding_scope_entity`** — unique index parcial para bindings idempotentes
6. **9 worker definitions** seeds para guided_intake, lead_qualification, knowledge_retrieval, diagnosis_scoring, package_recommendation, proposal_outline, crm_handoff, calendar_handoff, agui_render

---

## 5. PostgreSQL Repository (`postgres_repository.py`)

**Archivo:** `backend/modules/automation_diagnosis/postgres_repository.py` (695 lines)

### Metodos
| Metodo | Funcion |
|---|---|
| `upsert_package_installation()` | Crea/actualiza workspace, knowledge_scope, assistant_instance, automation_package, package_workers + configs + bindings |
| `upsert_session()` | INSERT/UPDATE en `automation_diagnosis_sessions` con ON CONFLICT |
| `upsert_answers()` | INSERT/UPDATE en `automation_diagnosis_answers` por step_id |
| `upsert_lead_from_session()` | INSERT/UPDATE en `automation_diagnosis_leads` con ON CONFLICT |
| `insert_event()` | INSERT en `core_events` con payload enrich |
| `persist_session_snapshot()` | Metodo compuesto: session + answers + lead + events en una llamada |
| `get_installation_refs()` | Resuelve UUIDs de workspace/assistant/package/knowledge desde codes |

### Observaciones
- Repository recibe `AsyncConnection` del caller (no pool propio)
- SQL parametrizado con `%(name)s`, usa `psycopg.types.json.Jsonb`
- No hay secrets en SQL, no hay queries sin parametrizar
- Los upserts usan `on conflict do update` con `now()` en `updated_at_utc`

---

## 6. Decisión RAG Inicial — ArangoDB + Milvus + LiteLLM

### Documentos de decision

| Documento | Contenido |
|---|---|
| `lat.md/ai-diagnosis-rag-runtime.md` | Decision estable: ArangoDB + Milvus + LiteLLM como runtime RAG inicial; PostgreSQL como verdad operacional; pgvector como disponible no primario |
| `lat.md/customer-packaged-assistant-instance.md` | Team360 directo como primera instalacion cliente del paquete venta/diagnostico; scoping compartido en ArangoDB/Milvus por organization/workspace/assistant/scope |
| `docs/analisis-tecnico/team360_ai_diagnostico_stack_arango_milvus_litellm.md` | Analisis de factibilidad tecnico-comercial |
| `lat.md/knowledge-rag-graphrag.md` | Actualizado con frontera runtime inicial |
| `lat.md/postgres-ai-persistence.md` | Actualizado: pgvector disponible, LangGraph pasa a `005_team360_langgraph_checkpointing.sql` |

### Scope rules
- **ArangoDB:** colecciones compartidas (`diagnosis_vertices`, `diagnosis_edges`, `diagnosis_documents`, `diagnosis_playbooks`) con filtros obligatorios por `organization_id`, `workspace_id`, `assistant_instance_id`, `knowledge_scope_id`. Aislamiento fisico solo por necesidad explicita.
- **Milvus:** coleccion compartida `team360_diagnosis_chunks` con `partition_key: knowledge_scope_id` y `required_filter_fields` identicos.
- **Ambos runtime NOT source of truth** — PostgreSQL es la fuente de verdad comercial.

### Definido pero NO implementado
- ArangoDB no tiene conexion ni driver implementado
- Milvus no tiene conexion ni driver implementado
- LiteLLM tiene adapter/port pero NO configuracion real de aliases/modelos
- AG-UI/SSE no tiene endpoint Litestar ni renderizado

---

## 7. Knowledge Scopes / Scoping por assistant_instance_id

### Implementado en memoria
```python
# knowledge_connector.py
build_default_knowledge_repository()
  -> Itera list_assistant_instance_configs()
  -> Crea KnowledgeScope por config con id=config.knowledge_scope_id
  -> Carga documents/chunks por scope_id

# service.py classify()
context = self.knowledge_repository.search(session.knowledge_scope_id, query, ...)
```

### Scopes actuales
| Scope ID | Assistant Instance | Uso |
|---|---|---|
| `ks_team360_sales_diagnosis` | `team360_sales_diagnosis` | Team360 direct (produccion real) |
| `ks_team360_automation_diagnosis` | `automation_diagnosis_default` | Fixtures/lab legacy (compatibilidad) |

### Validacion de scope
- `AssistantInstanceConfig.validate_payload_scope()`: rechaza overrides de workspace, package, knowledge_scope que no coincidan con la config de la instancia
- `resolve_assistant_instance_config()` en `service.py` linea 45

---

## 8. Estado de Tests

### Resultado: **45 passed, 0 failed** (0.30s)

### Tests de automation_diagnosis (`test_automation_diagnosis.py`) — 11 tests
| Test | Que valida |
|---|---|
| `test_default_session_uses_team360_direct_package_installation` | Session default usa `team360_sales_diagnosis` con org, workspace, package, scope, locale, cost_attribution correctos |
| `test_team360_direct_classification_preserves_customer_attribution` | Classificacion preserva org_id, workspace_id, assistant_instance_id, cost_attribution |
| `test_start_session_rejects_scope_override_that_does_not_match_assistant_instance` | Rechaza knowledge_scope_id que no coincide con assistant_instance |
| `test_team360_direct_config_documents_arangodb_and_milvus_scope_rules` | Config tiene arangodb_scope/milvus_scope con rules correctas |
| `test_normalize_answer_rejects_unknown_step` | Rechaza step_id desconocido |
| `test_chunk_document_splits_markdown_sections` | Chunking por secciones markdown |
| `test_default_knowledge_repository_retrieves_mfa_context` | Retrieval keyword encuentra contexto MFA |
| `test_standard_package_fixture_classification` | Fixture standard_package = `standard_package` |
| `test_operational_automation_fixture_classification` | Fixture operational = `operational_automation` |
| `test_consulting_required_fixture_classification` | Fixture consulting = `consulting_required` |
| `test_not_recommended_fixture_classification` | Fixture not_recommended = `not_recommended` |

### Tests de postgres_repository (`test_automation_diagnosis_postgres_repository.py`) — 2 tests
| Test | Que valida |
|---|---|
| `test_postgres_repository_upserts_team360_package_installation_contract` | Contrato upsert: workspace, scope, assistant, package, workers, configs, bindings |
| `test_postgres_repository_persists_session_answers_lead_and_events_snapshot` | Snapshot completo: session, answers, lead, core_events con metadata de customer |

### Tests de Console Bootstrap (3 files) — ver status_actual.md (ConsoleBootstrap Fase C)

### Schema Audit: **Checks pasados: >100 (0 fallidos)**

---

## 9. Inventario de archivos nuevos sin commit

| Archivo | Categoria | Depende de |
|---|---|---|
| `004_team360_automation_diagnosis_runtime.sql` | Migracion DB | 001+002+003 |
| `assistant_instances.py` | Modulo Python | schemas |
| `postgres_repository.py` | Modulo Python | schemas, assistant_instances, db/transaction |
| `test_automation_diagnosis_postgres_repository.py` | Tests | assistant_instances, postgres_repository, service |
| `postgresql_004_automation_diagnosis_runtime.md` | Doc tecnica | 004 migration |
| `team360_ai_diagnostico_stack_arango_milvus_litellm.md` | Analisis no operativo | — |
| `ai-diagnosis-rag-runtime.md` | Arquitectura viva (lat.md) | — |
| `customer-packaged-assistant-instance.md` | Arquitectura viva (lat.md) | — |

---

## 10. Brechas y decisiones pendientes

### NO implementado (planificado/documentado)
- **ArangoDB**: Sin driver, conexion, queries ni fixtures reales
- **Milvus**: Sin driver, conexion, queries ni fixtures reales
- **LiteLLM real**: Solo adapter/port con `LiteLLMAIInterpreter`; sin configuracion de aliases, modelos, costos ni budget
- **Endpoints Litestar**: `backend/routes/automation_diagnosis.py` existe pero NO montado en app Litestar
- **Console Bootstrap endpoint**: Repositories listos, sin endpoint HTTP
- **AG-UI/SSE rendering**: Sin implementacion
- **LangGraph PostgresSaver**: Reservado para `005_team360_langgraph_checkpointing.sql`

### Frontend
- Scaffold completo en `SrvRestAstroLS_v1/astro/` (Astro 6, Svelte 5, Tailwind 4, DaisyUI 5)
- App Shell navegable con mock data
- Sin conexion a backend real

### DB
- `team360` corriendo en PostgreSQL local (puerto 5432)
- Migraciones 001+002+003+004 aplicadas
- Sin datos reales de clientes (solo seeds tecnicos: 20 permisos, 4 planes, 17 features, 8+9 worker definitions)
- Schema audit OK: >100 checks, 0 fallidos, 51/51 tablas esperadas

---

## 11. Resumen de riesgos tecnicos

1. **Dependencia externa ArangoDB+Milvus**: No hay PoC ni driver implementado. El runtime RAG sigue siendo 100% in-memory. Si ArangoDB/Milvus se demoran, pgvector (003) es una alternativa disponible pero no disenada como RAG principal.
2. **LiteLLM sin configuracion real**: El adapter existe pero probar con LiteLLM real requiere configuracion de aliases y modelo real.
3. **Sin endpoint HTTP**: Todo el flujo de diagnostico es invocable solo via Python directo. No hay endpoint Litestar para integrar con frontend.
4. **Package_worker_configs sin workers reales**: Los workers del paquete venta/diagnostico existen como seeds y bindings, pero no como implementaciones de worker reales.
5. **Workspace-centric auth**: `ConsoleBootstrap` usa `core_users.workspace_id` como unico scope; organizaciones y membresias multi-workspace requieren migracion futura.

---

## 12. Datos de contacto operativo

| Elemento | Valor |
|---|---|
| Rama activa | `feature/console-backend-core` |
| DB viva | `team360` @ localhost:5432 |
| Python | 3.11 (via uv) |
| Test runner | `cd backend && uv run pytest` |
| Schema audit | `cd backend && uv run python -m scripts.audit_team360_schema` |
| Ultimo commit | `5fd0f21` — ConsoleBootstrap read-only repositories |
| Archivos sin commit | 8 untracked + 23 modified (ver seccion 9) |

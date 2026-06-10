# Sales Diagnosis Runtime Module -- Fase 1.8a

## Objetivo

Modulo interno skeleton para el runtime del asistente de ventas/diagnostico de Team360.

Define contratos, interfaces y orquestador basico sin implementar:

* endpoints HTTP;
* SSE productivo;
* frontend;
* Milvus real;
* LLM real (gpt-5-nano low);
* persistencia real en PostgreSQL;
* Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Arquitectura

PostgreSQL 18 = source of truth
Milvus 2.6     = vector runtime derivado (provider futuro)
gpt-5-nano low = primera respuesta inteligente (provider futuro)
Template seguro = acuse/progreso, no reemplaza LLM

## Que hace este modulo

* Define 6 contratos de datos (dataclasses).
* Define 5 interfaces/protocols (QueryEmbeddingProvider, RetrievalProvider, LLMProvider, StateRepository, MetricsRecorder).
* Implementa providers null para testeo y desarrollo.
* Implementa MilvusRetrievalProvider con config por env.
* Implementa PromptPolicy y GuardrailPolicy con reglas de Fase 1.7c.
* Implementa AssistantConversationRuntime skeleton completo.
* Incluye errores controlados (8 clases).
* Incluye tests unitarios sin red.

## Que NO hace

* No expone endpoints HTTP.
* No implementa SSE.
* No llama LLM real.
* No toca DB.
* No modifica frontend.
* No modifica corpus knowledge.
* No re-embeddiza.

## Archivos

| Archivo | Proposito |
|---------|-----------|
| `__init__.py` | Export publico |
| `contracts.py` | Dataclasses: TurnInput, TurnOutput, ConversationState, RetrievedChunk, GuardrailResult, ProgressiveEvent, RuntimeMetrics |
| `embedding_provider.py` | QueryEmbeddingConfig + OpenAIQueryEmbeddingProvider |
| `errors.py` | Excepciones controladas |
| `milvus_provider.py` | MilvusRetrievalProvider + MilvusRuntimeConfig |
| `providers.py` | Interfaces, Null providers y QueryEmbeddingProvider |
| `policies.py` | PromptPolicy y GuardrailPolicy |
| `runtime.py` | AssistantConversationRuntime orchestrator |
| `state_repository.py` | ConversationStateSerializer, InMemoryConversationStateRepository, PostgresConversationStateRepository |

## MilvusRetrievalProvider — Fase 1.8b

Implementa `RetrievalProvider` contra Milvus 2.6 como indice vectorial derivado.

### Dependencia

Requiere `pymilvus>=3.0.0`. No instalado por defecto en pyproject.toml.
Instalar con: `uv add pymilvus>=3.0.0`

### Env vars

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `TEAM360_MILVUS_URI` | — | URI completa de conexion |
| `TEAM360_MILVUS_HOST` | — | Host (alternativa a URI) |
| `TEAM360_MILVUS_PORT` | 19530 | Puerto |
| `TEAM360_MILVUS_TOKEN` | — | Token de autenticacion |
| `TEAM360_MILVUS_COLLECTION` | `knowledge_chunks` | Nombre de coleccion |
| `TEAM360_EMBEDDING_VERSION` | — | Version de embedding para filtrar |
| `TEAM360_KNOWLEDGE_SCOPE_ID` | — | Knowledge scope ID para filtrar |

### Contrato

Requiere `QueryEmbeddingProvider` para convertir texto a vector de query.
Sin embedding provider configurado, lanza `RetrievalUnavailableError`.

### No implementa

* pgvector fallback (futuro).
* Cross-encoder reranking (fuera de alcance).
* ArangoDB (fuera de alcance).
* LLM (modelo separado).

## Tests

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_sales_diagnosis_runtime_contracts.py -v
uv run pytest tests/test_sales_diagnosis_milvus_provider.py -v
```

## Fase 1.8d — ConversationState persistence skeleton

### ConversationStateSerializer

Convierte `ConversationState` a/desde dict JSON-compatible para almacenamiento jsonb.

* `to_dict(state)` — serializa todos los campos incluyendo `last_sources` (list[RetrievedChunk]).
* `from_dict(data)` — reconstruye `ConversationState` desde dict; campos faltantes usan defaults seguros.
* Valida `session_id` no vacío en ambas direcciones.

### InMemoryConversationStateRepository

Implementa `StateRepository` protocol sin DB. Almacena estados serializados como dicts para fidelidad round-trip con el serializer. Usado en tests y desarrollo.

### PostgresConversationStateRepository skeleton

Implementa `StateRepository` protocol con pool inyectado.

* Usa SQL directo con psycopg 3.
* `load(session_id)` — SELECT con fetch_one.
* `save(state)` — INSERT ... ON CONFLICT DO UPDATE (upsert).
* Requiere pool inyectado; levanta `StateRepositoryError` si no hay pool.
* `__repr__` sin secrets.
* `SUGGESTED_DDL` contiene la DDL de referencia (sincronizada con la migracion).
* `MIGRATION_FILE` apunta a `db/migrations/007_sales_diagnosis_conversation_states.sql`.
* **Los metodos `load()` y `save()` son skeleton sync — no envuelven async calls correctamente. La futura frontera async del runtime resolvera esto.**

### Tests

* `test_sales_diagnosis_state_repository.py` — 27 tests (serializer round-trip, in-memory repo, postgres skeleton, runtime integration, graceful failure).

### No implementa

* Endpoints HTTP.
* SSE productivo.
* Frontend.
* DB real via repository (el smoke script valida la tabla directamente).
* Milvus real.
* LLM real.
* ArangoDB / cross-encoder.

## Fase 1.8e — PostgreSQL 18 local integration smoke for ConversationState

### Migracion

`db/migrations/007_sales_diagnosis_conversation_states.sql`:

```sql
sales_diagnosis_conversation_states (
    session_id              text        PRIMARY KEY,
    assistant_instance_code text        NOT NULL,
    package_code            text        NOT NULL,
    knowledge_scope_code    text        NOT NULL,
    state_jsonb             jsonb       NOT NULL,
    created_at_utc          timestamptz NOT NULL DEFAULT now(),
    updated_at_utc          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_sd_cs_jsonb_is_object
        CHECK (jsonb_typeof(state_jsonb) = 'object'::text)
);
```

4 indexes: `updated_at_utc DESC`, `assistant_instance_code`, `package_code`, `knowledge_scope_code`.

### Env vars

| Variable | Descripcion |
|----------|-------------|
| `TEAM360_DB_URL` | DSN PostgreSQL (prioridad) |
| `TEAM360_DB_URL_PSQL` | Fallback si TEAM360_DB_URL no esta |

### Smoke

```bash
cd SrvRestAstroLS_v1/backend
TEAM360_DB_URL=postgresql://user:pass@localhost:5432/v360 \
  uv run python scripts/smoke_sales_diagnosis_state_postgres.py
```

Flujo del smoke:
1. Lee `TEAM360_DB_URL` (error si no configurado).
2. Crea `AsyncConnectionPool`, adquiere conexion.
3. Aplica `007_sales_diagnosis_conversation_states.sql` (idempotente).
4. Genera `ConversationState` via `ConversationStateSerializer`.
5. INSERT → SELECT + deserializa + verifica campos.
6. UPSERT (update turn_count) → SELECT + verifica cambio.
7. Verifica `updated_at_utc >= created_at_utc`.
8. DELETE cleanup.
9. Exit 0 en exito, 1 en fallo.

### Tests de contrato

`tests/test_sales_diagnosis_state_postgres_contract.py` — 8 tests:

| Test | Que valida |
|------|------------|
| `test_migration_file_exists` | Archivo existe |
| `test_migration_has_table_name` | Nombre de tabla en SQL |
| `test_migration_has_jsonb_check_constraint` | CHECK constraint jsonb_typeof |
| `test_migration_has_expected_indexes` | 4 indices esperados |
| `test_migration_has_idempotent_create` | `IF NOT EXISTS` |
| `test_repository_has_migration_reference` | `MIGRATION_FILE` apunta a `007_*.sql` |
| `test_repository_table_name_matches_migration` | `TABLE_NAME` aparece en migracion |
| `test_repository_repr_has_no_password` | `__repr__` sin secrets |
| `test_load_raises_error_without_pool` | Error controlado sin pool |
| `test_save_raises_error_without_pool` | Error controlado sin pool |
| `test_smoke_script_exists` | Script existe |
| `test_smoke_script_requires_env_var` | Error si TEAM360_DB_URL no configurado |
| `test_smoke_script_sanitizes_url` | URL sanitizada en logs |
| `test_smoke_script_uses_migration_file` | Referencia a migracion |
| `test_smoke_passes_with_db_url` | (skip sin env) Smoke real contra PostgreSQL |

### No implementa

* Endpoints HTTP.
* SSE productivo.
* Frontend.
* LLM real.
* Milvus real.
* ArangoDB / cross-encoder.
* Llamada a `PostgresConversationStateRepository.load()/save()` (skeleton sync).
* Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Fase 1.8f — Backend-only runtime integration smoke with fakes + Postgres state

### Que prueba

* `AssistantConversationRuntime` real con todas sus policies activas.
* `PostgreSQL 18` real para ConversationState via `_SmokePostgresStateRepository` (sync bridge con psycopg 3 sync).
* `fake RetrievalProvider` que devuelve chunks controlados (no Milvus).
* `fake LLMProvider` con modos: safe, too_many_questions, unsafe_claim (no OpenAI, no LiteLLM).
* `PromptPolicy` y `GuardrailPolicy` reales.
* `GuardrailPolicy` evalua respuestas seguras e inseguras.
* `UnsafeResponseError` se captura en el caso hard guardrail.

### Que no prueba

* Endpoints HTTP.
* SSE productivo.
* Frontend.
* LLM real.
* Milvus real.
* OpenRouter / LiteLLM.
* ArangoDB / cross-encoder.
* Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

### Flujo del smoke

4 turnos:

| Turno | LLM mode | Que valida |
|-------|----------|------------|
| 1 | safe | output con response_text, turn_count=1, state guardado en Postgres |
| 2 | safe | turn_count=2, session_id preservado, state cargado desde Postgres |
| 3 | too_many_questions | soft guardrail: max_questions_exceeded, fallback aplicado, state guardado |
| 4 | unsafe_claim | hard guardrail: UnsafeResponseError capturado, menciona lead_capture |

### Como correr

```bash
cd SrvRestAstroLS_v1/backend

# Asegurar migracion 007 aplicada
psql $TEAM360_DB_URL < db/migrations/007_sales_diagnosis_conversation_states.sql

# Smoke
TEAM360_DB_URL=postgresql://user:pass@localhost:5432/team360 \
  uv run python scripts/smoke_sales_diagnosis_runtime_postgres.py
```

### Requiere

* `TEAM360_DB_URL` configurado (lee desde `globalVar.get_team360_db_url()`).
* Migracion `007_sales_diagnosis_conversation_states.sql` aplicada.
* PostgreSQL 18 accesible desde el entorno.

### Tests de contrato

`tests/test_sales_diagnosis_runtime_postgres_smoke_contract.py` — 10 tests:

| Test | Que valida |
|------|------------|
| `test_smoke_script_exists` | Script existe |
| `test_uses_team360_db_url` | Usa `get_team360_db_url()` |
| `test_does_not_print_raw_db_url` | No imprime URL en crudo |
| `test_fails_without_team360_db_url` | Error si no hay env |
| `test_uses_fake_retrieval_not_milvus` | FakeRetrievalProvider, no Milvus |
| `test_uses_fake_llm_not_openai` | FakeLLMProvider, no OpenAI |
| `test_has_guardrail_failure_case` | unsafe_claim + UnsafeResponseError |
| `test_cleans_up_smoke_session` | DELETE en finally |
| `test_references_migration_007` | Menciona migracion 007 |
| `test_runtime_postgres_smoke_real_db` | (skip sin env) Smoke real |

### No implementa

* Endpoints HTTP.
* SSE productivo.
* Frontend.
* LLM real.
* Milvus real.
* ArangoDB / cross-encoder.
* Llamada a `PostgresConversationStateRepository.load()/save()` (sigue siendo sync skeleton).
* Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Fase 1.8c — QueryEmbeddingProvider and Policy Hardening

### QueryEmbeddingProvider

* `QueryEmbeddingConfig` — config con model, dimensions, timeout, api_key_env, base_url_env; repr sin secretos; constructor `from_env()`.
* `OpenAIQueryEmbeddingProvider` — implementa `QueryEmbeddingProvider`; lazy import de `openai`; lee API key de env en runtime, no en import; valida texto no vacio; valida dimension 1536; `__repr__` sin secretos.

### GuardrailPolicy (hardened)

* `CAPABILITY_PATTERNS` — mapeo extensible de capacidades futuras (step_to_action, lead_capture, diagnostic_code, whatsapp_handoff, crm, auto_billing).
* `DECLINE_PATTERNS` — patrones de declinacion compartidos.
* `_has_decline()` — verificador unificado de declinacion.
* `_build_contextual_fallback()` — fallback contextual segun el tipo de violation.
* Metodos individuales: `is_lead_capture_ready()`, `is_diagnostic_code_ready()`, `is_whatsapp_handoff_ready()`, `is_crm_ready()`, `is_auto_billing_ready()`.

### PromptPolicy (hardened)

* System prompt con diferenciacion: automatizable / vendible hoy / planned_extension / no documentado.
* Turn prompt con source, title, node_path y preview de cada chunk recuperado.
* Recordatorio de maximo 3 preguntas, espanol claro, sin HTML, sin AG-UI.

### Tests

* `test_sales_diagnosis_embedding_provider.py` — 11 tests (config, config repr, missing key, empty query, fake client, wrong dimension, secret repr, config model, API failure).
* `test_sales_diagnosis_policies.py` — 39 tests (PromptPolicy hardening, GuardrailPolicy individual capabilities, evaluate_response integration, fallback contextual, negation detection).

### No implementa

* Endpoints HTTP.
* SSE productivo.
* Frontend.
* LLM real en tests.
* Milvus real en tests.
* DB real.
* ArangoDB / cross-encoder.

## Fase 1.8g — Async runtime boundary / Postgres state repository decision

### Decision

**Runtime core stays sync.** `AsyncStateRepository` protocol and
`AsyncPostgresConversationStateRepository` are added as the async boundary
for production persistence. Full rationale in `async_boundary_decision.md`.

### AsyncStateRepository protocol

```python
class AsyncStateRepository(Protocol):
    async def load(self, session_id: str) -> ConversationState | None: ...
    async def save(self, state: ConversationState) -> None: ...
```

Defined in `providers.py`. Mirrors sync `StateRepository` with async methods.

### AsyncInMemoryStateRepository

Async in-memory implementation for testing. Same contract as
`AsyncStateRepository`, no DB required.

### AsyncPostgresConversationStateRepository

Real async production repository in `state_repository.py`:

- Owns an injected `AsyncConnectionPool` from `psycopg_pool`.
- Uses `modules.db.transaction.fetch_one` and `execute` — no ORM.
- `load()` — `SELECT state_jsonb` → `ConversationStateSerializer.from_dict`.
- `save()` — `INSERT ... ON CONFLICT DO UPDATE` (UPSERT).
- Raises `StateRepositoryError` if no pool injected.
- `__repr__` without secrets.

### Async smoke

`scripts/smoke_sales_diagnosis_state_postgres_async.py`:

- Applies migration 007, instantiates `AsyncPostgresConversationStateRepository`.
- Validates: save → load → verify fields → update → load again → verify.
- Loads non-existent session_id → returns None.
- Cleans up after itself.

```bash
cd SrvRestAstroLS_v1/backend
TEAM360_DB_URL=postgresql://user:pass@localhost:5432/v360 \
  uv run python scripts/smoke_sales_diagnosis_state_postgres_async.py
```

### Archivos nuevos

| Archivo | Proposito |
|---------|-----------|
| `async_boundary_decision.md` | Documenta la decision async boundary |
| `scripts/smoke_sales_diagnosis_state_postgres_async.py` | Async smoke contra PostgreSQL real |
| `tests/test_sales_diagnosis_async_state_repository.py` | 19 tests (12 pass sin DB, 7 skip) |

### Tests

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_sales_diagnosis_async_state_repository.py -v
```

Resultado: 12 passed, 7 skipped (dependen de TEAM360_DB_URL).

### No implementa

- Conversion de `handle_turn()` a async.
- Endpoints HTTP publicos.
- SSE productivo.
- LLM real.
- Milvus real.
- ArangoDB / cross-encoder.
- Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Fase 1.8h — Internal dev endpoint contract

### Endpoint

`POST /api/dev/sales-diagnosis-runtime/turn`

Endpoint backend-only interno/dev. NO es endpoint publico final.

### Request

```json
{
  "session_id": "dev-session-001",
  "message": "Quiero automatizar consultas comerciales por WhatsApp",
  "assistant_instance_code": "team360_sales_diagnosis",
  "package_code": "pkg_sales_diagnosis",
  "knowledge_scope_code": "ks_team360_sales_diagnosis",
  "metadata": {
    "channel": "dev"
  }
}
```

- `session_id` y `message` son obligatorios.
- Los codes tienen defaults seguros.
- Rechaza IDs prohibidos con prefijo `vera_`.

### Response

```json
{
  "session_id": "dev-session-001",
  "response_text": "...",
  "response_type": "final",
  "fallback_applied": false,
  "guardrail_flags": [],
  "retrieved_sources": [...],
  "turn_count": 1,
  "events": [...],
  "runtime_mode": "dev_fake"
}
```

`runtime_mode: "dev_fake"` indica que es una ejecucion interna/dev con providers fake.

### Providers por defecto

- `_DevFakeRetrievalProvider`: chunks controlados, no Milvus.
- `_DevFakeLLMProvider`: retorna SAFE_ACK_TEXT, no OpenAI/LiteLLM.
- `InMemoryConversationStateRepository`: estado en memoria, compartido entre requests.
- `PromptPolicy` real.
- `GuardrailPolicy` real.

### Modo unsafe test

Si `metadata.dev_test_unsafe_llm = true`, se usa `_DevUnsafeFakeLLMProvider` que genera texto inseguro para ejercitar `GuardrailPolicy`. El endpoint responde con `response_type: "unsafe_blocked"` y `guardrail_flags: ["unsafe_response_blocked"]`.

### Archivos nuevos

| Archivo | Proposito |
|---------|-----------|
| `routes/sales_diagnosis_runtime_schemas.py` | Schemas Pydantic para request/response |
| `routes/sales_diagnosis_runtime_dev.py` | Route handler con fakes |
| `tests/test_sales_diagnosis_runtime_dev_route.py` | 12 tests HTTP |

### Tests

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest tests/test_sales_diagnosis_runtime_dev_route.py -v
```

Resultado: 12 passed.

### No implementa

- Endpoint publico final.
- SSE productivo.
- Frontend.
- LLM real / OpenAI / LiteLLM.
- Milvus real.
- ArangoDB / cross-encoder.
- DB real por defecto.
- Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Fase 1.8i — Dev endpoint hardening + smoke script

### Smoke script

`scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py` invoca el endpoint
por HTTP y valida 12 condiciones:

1. Request valido devuelve 201.
2. Response contract estable (9 keys esperadas).
3. session_id se preserva entre requests.
4. turn_count incrementa en misma sesion.
5. Defaults seguros de codes.
6. IDs prohibidos Vera devuelven 400.
7. Fake unsafe controlado activa guardrail.
8. No stacktrace en errores.
9. runtime_mode = dev_fake.
10. No LLM real.
11. No Milvus real.
12. No DB real por defecto.

Requiere backend corriendo, no requiere DB, no requiere LLM real,
no requiere Milvus.

```bash
cd SrvRestAstroLS_v1/backend
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
```

## Fase 1.8j — Postgres opt-in state repository

### Que cambio

El endpoint interno/dev `POST /api/dev/sales-diagnosis-runtime/turn` ahora
soporta dos modos de repositorio de estado seleccionables via env var:

| Variable | Valor | Comportamiento |
|----------|-------|---------------|
| `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY` | *(unset)* o `inmemory` | InMemoryConversationStateRepository (**default**) |
| `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY` | `postgres` | PostgreSQL via `_DevPostgresStateRepository` (psycopg 3 sync, per-request connection) |

### Modo PostgreSQL

- Usa `TEAM360_DB_URL` via `globalVar.get_team360_db_url()`.
- Requiere migracion 007 aplicada (tabla `sales_diagnosis_conversation_states`).
- Cada operacion abre conexion sincrona propia — aceptable para dev.
- Si falta `TEAM360_DB_URL`, retorna HTTP 500 con mensaje claro.
- Si el modo es invalido, retorna HTTP 500 con valores aceptados.

### Smoke con PostgreSQL

```bash
cd SrvRestAstroLS_v1/backend
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run uvicorn app:app --host 127.0.0.1 --port 8000
# En otra terminal:
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
```

### Tests nuevos (6)

En `tests/test_sales_diagnosis_runtime_dev_route.py`:
- `test_default_uses_inmemory_state_repository`
- `test_postgres_opt_in_requires_db_url`
- `test_invalid_state_repository_mode_returns_controlled_error`
- `test_endpoint_still_works_with_default_inmemory`
- `test_no_real_db_called_by_default`
- `test_no_secret_leak_on_postgres_config_error`

### No implementa

- Endpoint publico final.
- SSE productivo.
- Frontend.
- LLM real / OpenAI / LiteLLM.
- Milvus real.
- ArangoDB / cross-encoder.
- Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Fase 1.8k — Postgres opt-in HTTP smoke

### Que cambio

El smoke script `scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py` se
extendio para soportar el modo PostgreSQL via el flag `--cleanup`.

Cuando el backend corre con `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres`,
el smoke detecta y muestra el modo activo en su encabezado.

Con `--cleanup`, al finalizar elimina las sesiones de prueba de la tabla
`sales_diagnosis_conversation_states` en PostgreSQL (requiere `TEAM360_DB_URL`
en el entorno del smoke). El cleanup es opcional y no bloqueante.

### Smoke con PostgreSQL (opt-in)

```bash
# Terminal 1: backend con Postgres
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run uvicorn app:app --host 127.0.0.1 --port 8000

# Terminal 2: smoke con cleanup opcional
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup
```

### No implementa

- Endpoint publico final.
- SSE productivo.
- Frontend.
- LLM real / OpenAI / LiteLLM.
- Milvus real.
- ArangoDB / cross-encoder.
- Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.

## Proximas fases sugeridas

1. ~~1.8b -- MilvusRetrievalProvider runtime con fallback pgvector.~~ **(Completado)**
2. ~~1.8c -- QueryEmbeddingProvider + Prompt/GuardrailPolicy hardening.~~ **(Completado)**
3. ~~1.8d -- ConversationState persistence skeleton.~~ **(Completado)**
4. ~~1.8e -- PostgreSQL 18 local integration smoke for ConversationState persistence.~~ **(Completado)**
5. ~~1.8f -- backend-only runtime integration smoke with fakes + Postgres state.~~ **(Completado)**
6. ~~1.8g -- Async runtime boundary / Postgres state repository decision.~~ **(Completado)**
7. ~~1.8h -- Internal dev endpoint contract.~~ **(Completado)**
8. ~~1.8i -- Dev endpoint hardening + smoke script.~~ **(Completado)**
9. ~~1.8j -- Postgres opt-in state repository for dev endpoint.~~ **(Completado)**
10. ~~1.8k -- Postgres opt-in HTTP smoke for dev endpoint.~~ **(Completado)**

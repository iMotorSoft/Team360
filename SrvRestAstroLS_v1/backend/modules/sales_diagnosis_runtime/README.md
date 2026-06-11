# Sales Diagnosis Runtime Module -- Fase 1.8a

## Objetivo

Modulo interno skeleton para el runtime del asistente de ventas/diagnostico de Team360.

Define contratos, interfaces y orquestador basico. La unica superficie HTTP
vigente es el endpoint interno/dev documentado en Fase 1.8h-1.8p; no hay
endpoint publico final.

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

* No expone endpoint publico final.
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

## Fase 1.8l — Provider mode boundary

### Que cambio

El endpoint interno/dev ahora expone dos nuevas variables de entorno para
seleccionar el proveedor de retrieval y LLM:

| Variable | Default | Valores aceptados | Descripcion |
|----------|---------|-------------------|-------------|
| `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER` | `fake` | `fake` | Fake retrieval (no Milvus). Futuros valores: `milvus`. |
| `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER` | `fake` | `fake` | Fake LLM (no OpenAI/LiteLLM). Futuros valores: `openai`, `litellm`. |

### Comportamiento

- **Default:** ambos son `fake`. Comportamiento identico a Fase 1.8h.
- **Valor invalido:** HTTP 500 con mensaje controlado que lista valores aceptados.
- **`dev_test_unsafe_llm` en metadata:** tiene prioridad sobre la env var `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER`. Si se activa, usa `_DevUnsafeFakeLLMProvider` independientemente del valor de la env var.
- No hay proveedores reales conectados — solo el boundary preparado.

### Funciones nuevas

En `routes/sales_diagnosis_runtime_dev.py`:

- `_resolve_retrieval_provider()` — lee `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER`, retorna `_DevFakeRetrievalProvider` o lanza HTTP 500.
- `_resolve_llm_provider(metadata)` — primero evalua flag `dev_test_unsafe_llm` en metadata; si no esta, lee `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER`. Retorna `_DevFakeLLMProvider`, `_DevUnsafeFakeLLMProvider` o lanza HTTP 500.

### Tests nuevos (10)

En `tests/test_sales_diagnosis_runtime_dev_route.py`:

| Test | Que valida |
|------|------------|
| `test_default_uses_fake_retrieval_provider` | Sin env, `_resolve_retrieval_provider()` retorna `_DevFakeRetrievalProvider` |
| `test_default_uses_fake_llm_provider` | Sin env, `_resolve_llm_provider({})` retorna `_DevFakeLLMProvider` |
| `test_explicit_fake_retrieval_provider_is_accepted` | `=fake` explicito aceptado |
| `test_explicit_fake_llm_provider_is_accepted` | `=fake` explicito aceptado |
| `test_invalid_retrieval_provider_returns_controlled_error` | HTTP 500 con `"milvus"` y `"fake"` en mensaje |
| `test_invalid_llm_provider_returns_controlled_error` | HTTP 500 con `"openai"` y `"fake"` en mensaje |
| `test_unsafe_llm_flag_takes_precedence_over_env` | Metadata flag gana a env var `=fake` |
| `test_unsafe_llm_flag_works_without_env` | Metadata flag funciona sin env var |
| `test_explicit_fake_env_does_not_break_runtime` | HTTP 201, response contract intacto |
| `test_invalid_provider_does_not_leak_secrets` | HTTP 500 sin `sk-` ni `password` |

### No implementa

- Milvus real (solo opt-in).
- OpenAI/LiteLLM real.
- Conexion a proveedores reales — solo el boundary selector preparado.

## Fase 1.8m — Milvus retrieval opt-in boundary

### Que cambio

El endpoint interno/dev ahora acepta `milvus` como valor para la env var
`TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER`:

| Variable | Valores aceptados |
|----------|-------------------|
| `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER` | `fake` (default), `milvus` |

Cuando se selecciona `milvus`:

1. Se crea `MilvusRetrievalProvider` con config desde env (`MilvusRuntimeConfig.from_env()`).
2. Se inyecta `_DevFakeEmbeddingProvider` (devuelve vector estatico 1536-dim, **no OpenAI**).
3. Si falta `TEAM360_MILVUS_URI` y `TEAM360_MILVUS_HOST` → HTTP 500 controlado.
4. Si Milvus no esta disponible, el runtime captura el error y continua con empty sources.
5. Fake embedding no es real — no hay conexion a OpenAI ni a ningun embedding service.

### Funcion nueva

- `_DevFakeEmbeddingProvider` en `routes/sales_diagnosis_runtime_dev.py`: implementa `QueryEmbeddingProvider` protocol, retorna `[0.0] * 1536`.
- `_resolve_retrieval_provider()` extendida para aceptar `"milvus"` y validar config minima.

### Tests nuevos (4 + 1 modificado)

En `TestDevSalesDiagnosisRouteMilvus`:

| Test | Que valida |
|------|------------|
| `test_milvus_mode_is_accepted_with_env_config` | `TEAM360_MILVUS_URI` seteado → `_resolve_retrieval_provider()` retorna `MilvusRetrievalProvider` |
| `test_milvus_mode_without_config_returns_controlled_error` | Sin `TEAM360_MILVUS_*` → HTTP 500 con mensaje |
| `test_milvus_mode_config_error_does_not_leak_secrets` | HTTP 500 sin `sk-` ni `password` |
| `test_postgres_state_still_works_with_fake_retrieval` | Postgres state mode coexiste con fake retrieval |

Modificado:

| Test | Cambio |
|------|--------|
| `test_invalid_retrieval_provider_returns_controlled_error` | Usa `"pinecone"` en vez de `"milvus"` (ahora valido) |

### No implementa

- OpenAI real por default.
- LiteLLM real (solo opt-in boundary).
- LLM real.
- Milvus real en tests — solo opt-in mockeado.
- Frontend, Astro, Svelte, UI, SSE, ArangoDB, pgvector, cross-encoder.
- Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real.

## Fase 1.8n — LiteLLM LLM provider opt-in boundary

### Que cambio

El endpoint interno/dev ahora acepta `litellm` como valor para la env var
`TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER`:

| Variable | Valores aceptados |
|----------|-------------------|
| `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER` | `fake` (default), `litellm` |

Cuando se selecciona `litellm`:

1. Se crea `_DevLiteLLMProvider` que usa `LiteLLMClient` de `automation_diagnosis`.
2. Requiere `TEAM360_LITELLM_BASE_URL` y `TEAM360_LITELLM_API_KEY` — si falta → HTTP 500.
3. Usa `PromptPolicy.build_system_prompt()` y `build_turn_prompt()` para construir el prompt.
4. Modelo via `TEAM360_LITELLM_MODEL_ALIAS` (default: `openrouter_qwen3_30b_a3b_thinking_2507`).
5. No OpenAI SDK — usa urllib directo via `LiteLLMClient`.
6. `dev_test_unsafe_llm` en metadata sigue teniendo prioridad sobre la env var.

### Funcion nueva

- `_DevLiteLLMProvider` en `routes/sales_diagnosis_runtime_dev.py`: implementa `LLMProvider` protocol, construye prompts y llama LiteLLM proxy.

### Tests nuevos (4)

En `TestDevSalesDiagnosisRouteLiteLLM`:

| Test | Que valida |
|------|------------|
| `test_litellm_mode_is_accepted_with_env_config` | Env vars seteadas → `_DevLiteLLMProvider` |
| `test_litellm_mode_without_config_returns_controlled_error` | Sin config → HTTP 500 |
| `test_litellm_mode_does_not_leak_secrets` | HTTP 500 sin `sk-` ni `password` |
| `test_milvus_retrieval_does_not_force_real_llm` | Milvus retrieval + fake LLM coexisten |

### No implementa

- OpenAI real por default.
- LiteLLM real sin config explicita.
- LLM real en tests — solo opt-in mockeado.
- Frontend, Astro, Svelte, UI, SSE, ArangoDB, pgvector, cross-encoder.
- Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real.

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
11. ~~1.8l -- Provider mode boundary.~~ **(Completado)**
12. ~~1.8m -- Milvus retrieval opt-in boundary.~~ **(Completado)**
13. ~~1.8n -- LiteLLM LLM provider opt-in boundary.~~ **(Completado)**
14. ~~1.8o -- LiteLLM HTTP smoke opt-in for dev endpoint.~~ **(Completado)**
15. ~~1.8p -- Runtime dev endpoint release gate.~~ **(Completado)**

## Fase 1.8o — LiteLLM HTTP smoke opt-in for dev endpoint

### Smoke script separado

`scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py`:

- Smoke HTTP opt-in que requiere backend corriendo con `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm`.
- Si el provider env no es `litellm`, hace skip con mensaje claro (exit 0).
- Si faltan `TEAM360_LITELLM_BASE_URL` o `TEAM360_LITELLM_API_KEY`, el backend devuelve HTTP 500 y el smoke valida el mensaje de error controlado (sin leaks de secrets).
- Si LiteLLM esta configurado, valida:
  1. Status 201.
  2. Response contract estable (9 keys esperadas).
  3. session_id preservado.
  4. runtime_mode = `dev_fake`.
  5. retrieved_sources son chunks fake (prefijo `dev_doc_`), no Milvus real.
  6. Guardrail unsafe (dev_test_unsafe_llm) funciona: response_type `unsafe_blocked`.
  7. No stack traces en errores 400.
  8. No leaks de DB por defecto.
- Sin cambios en el script base, sin tocar frontend, sin Milvus real, sin DB real.
- Sin dependencias extra (urllib stdlib).

## Fase 1.8p — Runtime dev endpoint release gate

### Alcance

Esta fase consolida el estado final del endpoint interno/dev antes de abrir
cualquier endpoint no-dev.

Endpoint vigente:

`POST /api/dev/sales-diagnosis-runtime/turn`

Este endpoint sigue siendo interno/dev:

- ruta bajo `/api/dev/`;
- `runtime_mode = "dev_fake"`;
- defaults seguros sin servicios reales;
- Pydantic solo en el borde HTTP;
- `AssistantConversationRuntime`, `PromptPolicy` y `GuardrailPolicy` reales;
- sin frontend, sin SSE productivo y sin endpoint publico nuevo.

No llamar esta etapa MVP. No representa superficie publica ni contrato final de
producto.

### Matriz de modos

| Dimension | Env var | Default seguro | Opt-in dev | Servicios reales por default |
|-----------|---------|----------------|------------|------------------------------|
| State | `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY` | `inmemory` | `postgres` | No |
| Retrieval | `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER` | `fake` | `milvus` | No |
| LLM | `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER` | `fake` | `litellm` | No |

Defaults seguros:

- state = `inmemory`;
- retrieval = `fake`;
- llm = `fake`.

Con los defaults, pytest normal y el smoke base no usan PostgreSQL, Milvus,
LiteLLM, OpenAI, ArangoDB, pgvector, cross-encoder ni servicios externos.

### Combinaciones soportadas en dev

| State | Retrieval | LLM | Estado |
|-------|-----------|-----|--------|
| `inmemory` | `fake` | `fake` | Default soportado |
| `postgres` | `fake` | `fake` | Opt-in soportado con `TEAM360_DB_URL` y migracion 007 |
| `inmemory` | `milvus` | `fake` | Opt-in soportado con `TEAM360_MILVUS_URI` o `TEAM360_MILVUS_HOST`; embedding fake |
| `inmemory` | `fake` | `litellm` | Opt-in soportado con `TEAM360_LITELLM_BASE_URL` + `TEAM360_LITELLM_API_KEY` |
| `postgres` | `milvus` | `fake` | Combinacion dev permitida si ambas configuraciones existen |
| `postgres` | `fake` | `litellm` | Combinacion dev permitida si ambas configuraciones existen |
| `inmemory` | `milvus` | `litellm` | Combinacion dev permitida si ambas configuraciones existen |
| `postgres` | `milvus` | `litellm` | Permitida para pruebas manuales; no es default ni gate obligatorio |

Valores invalidos devuelven HTTP 500 controlado y sin secrets.

### Env vars por opt-in

La configuracion runtime se resuelve desde `backend/globalVar.py`.
Las env vars siguientes son las entradas que `globalVar.py` y los resolvers del
endpoint dev leen para activar cada modo.

State Postgres:

| Variable | Requerida | Nota |
|----------|-----------|------|
| `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres` | Si | Activa state en PostgreSQL |
| `TEAM360_DB_URL` o `TEAM360_DB_URL_PSQL` | Si | DSN PostgreSQL resuelto via `globalVar.get_team360_db_url_psql()`; no imprimir en logs |
| Migracion `007_sales_diagnosis_conversation_states.sql` | Si | Tabla `sales_diagnosis_conversation_states` |

Retrieval Milvus:

| Variable | Requerida | Nota |
|----------|-----------|------|
| `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=milvus` | Si | Activa `MilvusRetrievalProvider` |
| `TEAM360_MILVUS_URI` o `TEAM360_MILVUS_HOST` | Si | Config minima de Milvus |
| `TEAM360_MILVUS_PORT` | No | Default `19530` |
| `TEAM360_MILVUS_TOKEN` | No | No debe imprimirse |
| `TEAM360_MILVUS_COLLECTION` | No | Default del provider |
| `TEAM360_EMBEDDING_VERSION` | No | Filtro opcional |
| `TEAM360_KNOWLEDGE_SCOPE_ID` | No | Filtro opcional |

LLM LiteLLM:

| Variable | Requerida | Nota |
|----------|-----------|------|
| `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm` | Si | Activa `_DevLiteLLMProvider` |
| `TEAM360_LITELLM_BASE_URL` | Si | URL del proxy LiteLLM |
| `TEAM360_LITELLM_API_KEY` | Si | No debe imprimirse |
| `TEAM360_LITELLM_MODEL_ALIAS` | No | Default `openrouter_qwen3_30b_a3b_thinking_2507` |

### Smoke commands

Base InMemory:

```bash
cd SrvRestAstroLS_v1/backend

# Terminal 1
uv run uvicorn app:app --host 127.0.0.1 --port 8000

# Terminal 2
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
```

Postgres opt-in:

```bash
cd SrvRestAstroLS_v1/backend

# Terminal 1
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run uvicorn app:app --host 127.0.0.1 --port 8000

# Terminal 2
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup
```

LiteLLM opt-in:

```bash
cd SrvRestAstroLS_v1/backend

# Terminal 1
TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \
  uv run uvicorn app:app --host 127.0.0.1 --port 8000

# Terminal 2
TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py
```

## Fase 1.9c — Product adapter Postgres HTTP smoke

### Alcance

Esta fase agrega un smoke HTTP reproducible para validar el endpoint no-dev
con Postgres state real:

    POST /api/sales-diagnosis-runtime/turn

No es endpoint final publico, no es MVP y no activa producto comercial.

### Script

`scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py`

Requiere backend corriendo con:

```bash
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres
```

### Comportamiento

- Si las envs requeridas no estan presentes, el script hace skip (exit 0,
  no es fallo), con mensaje claro indicando que se necesita configurar.
- Si las envs estan presentes, valida el contrato HTTP completo del endpoint
  product adapter contra PostgreSQL real.

### Validaciones del smoke

1. Request valido devuelve 201 con respuesta segura.
2. Response contract estable (9 keys esperadas).
3. `session_id` se preserva.
4. `turn_count` incrementa (1 → 2) en la misma sesion.
5. `runtime_mode` = `product_adapter_skeleton` en todas las respuestas.
6. No LLM real: response_text es SAFE_ACK_TEXT, no texto generado por
   LLM real.
7. No Milvus real: retrieved_sources son chunks fake con prefijo
   `dev_doc_*`.
8. No stacktrace en errores 400.
9. Rechaza IDs Vera prohibidos (`vera_team360_sales_diagnosis`,
   `pkg_vera_sales_diagnosis`, `ks_vera_team360_sales_diagnosis`) con
   HTTP 400.
10. No LiteLLM real: no aparece referencia a `litellm` en respuestas.

### Cleanup

`--cleanup` flag opcional:

- Borra solo filas con prefijo `smoke_product_pg_%` de la tabla
  `sales_diagnosis_conversation_states`.
- No borra sesiones de otros smokes ni datos de sesiones no-smoke.
- Verifica `remaining_smoke_rows=0` despues del DELETE.
- Usa `globalVar.get_team360_db_url_psql()` para resolver la DSN.
- No imprime DSN ni credenciales.

### Requisitos

- Backend corriendo con las envs necesarias.
- PostgreSQL 18 con migracion 007 aplicada.
- `TEAM360_DB_URL` o `TEAM360_DB_URL_PSQL` configurada.

### Providers

| Dimension | Default 1.9c | Servicio real por default |
|-----------|--------------|---------------------------|
| Retrieval | `fake` | No |
| LLM | `fake` | No |

No se activa por default:

- Milvus real;
- LiteLLM real;
- OpenAI SDK;
- ArangoDB;
- pgvector;
- cross-encoder.

### Capacidades futuras no activadas

Esta fase no implementa ni habilita:

- frontend;
- Astro;
- Svelte;
- UI;
- SSE productivo;
- Step-to-Action;
- lead_capture;
- diagnostic_code;
- WhatsApp handoff;
- CRM real.

### Validacion esperada

```bash
cd SrvRestAstroLS_v1/backend

uv run pytest tests/test_sales_diagnosis_runtime_route.py
uv run pytest tests/test_sales_diagnosis_runtime_dev_route.py
uv run pytest
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py

# Smoke product adapter Postgres (requiere backend con envs configuradas):
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py --cleanup
```

Si faltan `TEAM360_LITELLM_BASE_URL` o `TEAM360_LITELLM_API_KEY`, el smoke
LiteLLM valida el HTTP 500 controlado como skip operativo, no como fallo.

### Release gate confirmado

- Pytest normal no usa servicios reales.
- El endpoint sigue bajo `/api/dev/`.
- No hay endpoint publico nuevo.
- La configuracion DB del endpoint y smokes pasa por `backend/globalVar.py`.
- No se toca frontend, Astro, Svelte, UI ni SSE productivo.
- No se activa por default PostgreSQL, Milvus, LiteLLM, OpenAI, ArangoDB,
  pgvector ni cross-encoder.
- No hay Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff ni CRM real.

## Fase 1.9a — Product route adapter skeleton

### Alcance

Esta fase agrega una ruta no-dev controlada para preparar la transicion desde
el endpoint interno/dev hacia una superficie de producto.

Endpoint:

`POST /api/sales-diagnosis-runtime/turn`

Importante:

- es un `product adapter skeleton`;
- no es endpoint final publico;
- no reemplaza `POST /api/dev/sales-diagnosis-runtime/turn`;
- no debe llamarse MVP;
- no representa superficie productiva final.

La ruta queda deshabilitada por default. Para habilitarla en pruebas
controladas:

```bash
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1
```

Valores verdaderos aceptados: `1`, `true`, `yes`, `on`.

Si el flag no esta activo, la ruta responde HTTP 404 controlado y sin
stacktrace.

### Contrato HTTP

Request minimo:

```json
{
  "session_id": "prod-adapter-session-001",
  "message": "Quiero automatizar consultas comerciales por WhatsApp"
}
```

Defaults seguros de identificadores:

```text
assistant_instance_code = team360_sales_diagnosis
package_code = pkg_sales_diagnosis
knowledge_scope_code = ks_team360_sales_diagnosis
```

Tambien acepta metadata:

```json
{
  "metadata": {
    "channel": "api"
  }
}
```

Response estable:

```json
{
  "session_id": "prod-adapter-session-001",
  "response_text": "...",
  "response_type": "final",
  "fallback_applied": false,
  "guardrail_flags": [],
  "retrieved_sources": [],
  "turn_count": 1,
  "events": [],
  "runtime_mode": "product_adapter_skeleton"
}
```

El contrato reutiliza los schemas HTTP existentes con nombres separados:

- `ProductTurnRequest`
- `ProductTurnResponse`

### Defaults seguros del adapter

Cuando la feature flag esta activa, el adapter usa:

| Dimension | Default 1.9a | Servicio real por default |
|-----------|--------------|---------------------------|
| State | `inmemory` | No |
| Retrieval | `fake` | No |
| LLM | `fake` | No |

Decision 1.9a: no exigir PostgreSQL para esta fase porque pytest normal no
debe depender de DB real. El adapter queda documentado como skeleton no
productivo; la persistencia PostgreSQL para runtime ya esta validada en el
endpoint dev via opt-in y PG18.

No se activa por default:

- PostgreSQL real;
- Milvus real;
- LiteLLM real;
- OpenAI SDK;
- ArangoDB;
- pgvector;
- cross-encoder.

### Guardrails y rechazos

La ruta usa `AssistantConversationRuntime`, `PromptPolicy` y
`GuardrailPolicy` reales.

Rechaza HTTP 400 controlado para IDs prohibidos:

- `vera_team360_sales_diagnosis`
- `pkg_vera_sales_diagnosis`
- `ks_vera_team360_sales_diagnosis`
- `svc_vera_sales_diagnosis`

No expone stacktraces ni secrets en errores controlados.

### Capacidades futuras no activadas

Esta fase no implementa ni habilita:

- frontend;
- Astro;
- Svelte;
- UI;
- SSE productivo;
- Step-to-Action;
- lead_capture;
- diagnostic_code;
- WhatsApp handoff;
- CRM real.

### Validacion esperada

```bash
cd SrvRestAstroLS_v1/backend

uv run pytest tests/test_sales_diagnosis_runtime_dev_route.py
uv run pytest tests/test_sales_diagnosis_runtime_route.py
uv run pytest
```

El smoke HTTP existente sigue apuntando al endpoint interno/dev:

```bash
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py
```

## Fase 1.9b — Product adapter state hardening

### Alcance

Esta fase endurece el adapter no-dev:

`POST /api/sales-diagnosis-runtime/turn`

El endpoint sigue siendo un `product adapter skeleton`. No es endpoint final
publico, no es MVP y no activa producto comercial.

### Feature flags y state repository

La ruta mantiene la feature flag:

```bash
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1
```

Cuando la ruta esta deshabilitada responde HTTP 404 controlado.

Cuando la ruta esta habilitada, ahora exige state repository explicito:

```bash
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres
```

Valores aceptados:

| Valor | Uso | Productivo |
|-------|-----|------------|
| `postgres` | Camino recomendado para product adapter con estado persistente | Si, cuando DB y migracion 007 estan configuradas |
| `inmemory_test` | Pruebas controladas del adapter sin DB real | No |

No existe default silencioso a InMemory cuando la ruta esta habilitada.

Si `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY` falta, es invalida o
Postgres no esta configurado, la ruta responde HTTP 503 controlado, sin
stacktrace y sin exponer DSN, usuario, password ni secrets.

### Postgres

`postgres` usa `globalVar.get_team360_db_url_psql()` para resolver la DSN desde:

- `TEAM360_DB_URL`;
- `TEAM360_DB_URL_PSQL`;
- fallback documentado de `globalVar.py`.

No se hardcodea DB URL y no se imprime la DSN en logs de aplicacion.

El adapter usa `SyncPostgresConversationStateRepository`, un repositorio sync
con psycopg 3 directo y SQL encapsulado en `state_repository.py`.

### InMemory test

`inmemory_test` existe solo para tests y smokes controlados del adapter.

Ejemplo:

```bash
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
  uv run pytest tests/test_sales_diagnosis_runtime_route.py
```

No debe usarse como produccion real.

### Providers

Retrieval y LLM siguen con defaults seguros:

| Dimension | Default 1.9b | Servicio real por default |
|-----------|--------------|---------------------------|
| Retrieval | `fake` | No |
| LLM | `fake` | No |

No se activa por default:

- Milvus real;
- LiteLLM real;
- OpenAI SDK;
- ArangoDB;
- pgvector;
- cross-encoder.

### Capacidades futuras no activadas

Esta fase no implementa ni habilita:

- frontend;
- Astro;
- Svelte;
- UI;
- SSE productivo;
- Step-to-Action;
- lead_capture;
- diagnostic_code;
- WhatsApp handoff;
- CRM real.

### Validacion esperada

```bash
cd SrvRestAstroLS_v1/backend

uv run pytest tests/test_sales_diagnosis_runtime_route.py
uv run pytest tests/test_sales_diagnosis_runtime_dev_route.py
uv run pytest
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py
```

## Fase 1.9d — Product adapter release gate

### Alcance

Esta fase cierra documental y operativamente el bloque 1.9a–1.9c del product
adapter antes de avanzar a cualquier integracion real de LLM/retrieval.

No agrega features nuevas. No modifica la logica del endpoint. Es un release
gate: verificacion + documentacion.

### Matriz del product adapter

| # | TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED | TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY | HTTP esperado | State backend | Retrieval | LLM | runtime_mode |
|---|------------------------------------------------|---------------------------------------------------|---------------|---------------|-----------|-----|--------------|
| A | unset / 0 | — | 404 controlado | — | — | — | — |
| B | `1` | unset | 503 controlado | — | — | — | — |
| C | `1` | `inmemory_test` | 201 | `InMemoryConversationStateRepository` (explicito) | `fake` | `fake` | `product_adapter_skeleton` |
| D | `1` | `postgres` | 201 (si PG config OK) / 503 (si falta config DB) | `SyncPostgresConversationStateRepository` | `fake` | `fake` | `product_adapter_skeleton` |
| E | `1` | valor invalido | 503 controlado | — | — | — | — |

Casos:

- **Caso A**: route flag ausente. El endpoint no responde. No expone stacktrace.
- **Caso B**: route flag activo pero state repository no especificado. Error
  controlado indicando que se requiere `postgres` o `inmemory_test`.
- **Caso C**: route flag + state test explicito. Unico modo de usar InMemory
  cuando la ruta esta habilitada. No productivo.
- **Caso D**: route flag + Postgres. Exige `TEAM360_DB_URL` o
  `TEAM360_DB_URL_PSQL`. Si falta config DB, HTTP 503 controlado sin secrets.
- **Caso E**: state repository invalido (ej: `inmemory`, `mysql`, `redis`).
  HTTP 503 controlado con valores aceptados.

### Comandos smoke consolidados

```bash
cd SrvRestAstroLS_v1/backend

# Dev endpoint — InMemory (no DB, no LLM, no Milvus)
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py

# Dev endpoint — Postgres opt-in
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup

# Dev endpoint — LiteLLM opt-in
TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py

# Product adapter — Postgres opt-in
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py --cleanup
```

### Cleanup prefix confirmado

El smoke product adapter Postgres con `--cleanup` borra solo filas con prefijo
`smoke_product_pg_%` de `sales_diagnosis_conversation_states`.

No borra:
- `smoke_dev_*` (sesiones del dev endpoint smoke)
- `smoke_unsafe_*` (sesiones de prueba de guardrail unsafe)
- sesiones reales productivas

El cleanup verifica `remaining_smoke_rows=0` despues del DELETE.

### Defaults seguros confirmados

| Dimension | Product adapter | Dev endpoint |
|-----------|----------------|--------------|
| State | `inmemory_test` (explicito) o `postgres` | `inmemory` default, `postgres` opt-in |
| Retrieval | `fake` (no configurable) | `fake` default, `milvus` opt-in |
| LLM | `fake` (no configurable) | `fake` default, `litellm` opt-in |

Los defaults del product adapter NO tienen opt-in para retrieval ni LLM real.
No existe env `TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER` ni
`TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER`. Es intencional: el adapter
debe permanecer como skeleton controlado hasta que el release gate del bloque
siguiente decida lo contrario.

### Errores controlados sin exposicion

Todas las respuestas de error del product adapter cumplen:

- Sin stacktrace (`Traceback`, `File "..."` ausentes en body HTTP).
- Sin DB URL ni DSN en detalles.
- Sin API keys, tokens, ni headers sensibles.
- Sin identificadores `vera_*` en logs de aplicacion.

### Capacidades futuras no activadas

Esta fase no implementa ni habilita:

- frontend;
- Astro;
- Svelte;
- UI;
- Home premium;
- Console UI;
- SSE productivo;
- OpenAI SDK;
- OpenAI real;
- LiteLLM real;
- Milvus real;
- ArangoDB;
- pgvector;
- cross-encoder;
- Step-to-Action;
- lead_capture;
- diagnostic_code;
- WhatsApp handoff;
- CRM real.

## Fase 1.9e — Product adapter OpenAI direct opt-in boundary

### Alcance

Esta fase agrega un selector de LLM para el product adapter que permite
usar OpenAI directo solo por opt-in explicito.

No es endpoint final publico, no es MVP y no activa producto comercial.

### Nueva env

`TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER`

Valores aceptados:

| Valor | Comportamiento |
|-------|----------------|
| unset o `fake` | `_DevFakeLLMProvider` (default seguro, no OpenAI) |
| `openai` | `_ProductOpenAILLMProvider` via OpenAI SDK directo |

Default: `fake`.

### OpenAI directo

Cuando `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai`:

- Requiere `TEAM360_OPENAI_KEY` o `OPENAI_API_KEY`.
- Modelo via `TEAM360_OPENAI_MODEL` (default `gpt-5-nano`).
- Usa el SDK de OpenAI con lazy import (no se importa al cargar el modulo).
- Construye prompts via `PromptPolicy`.
- Si la API key falta, responde HTTP 503 controlado sin secrets.
- Si la llamada a OpenAI falla, el provider retorna `SAFE_ACK_TEXT` como
  fallback (no expone stacktrace).
- No usa LiteLLM.

### Comportamiento ante errores

- Provider invalido: HTTP 503 controlado listando valores aceptados.
- API key faltante: HTTP 503 controlado, sin stacktrace, sin exponer env values.
- API call fallida: el runtime devuelve respuesta 201 con fallback seguro
  (SAFE_ACK_TEXT), sin leaks de secrets ni stacktrace.

### Matriz actualizada del product adapter

| # | TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED | TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY | TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER | HTTP esperado | State backend | Retrieval | LLM | runtime_mode |
|---|------------------------------------------------|---------------------------------------------------|-----------------------------------------------|---------------|---------------|-----------|-----|--------------|
| A | unset / 0 | — | — | 404 controlado | — | — | — | — |
| B | `1` | unset | — | 503 controlado | — | — | — | — |
| C | `1` | `inmemory_test` | unset o `fake` | 201 | `InMemoryConversationStateRepository` | `fake` | `fake` | `product_adapter_skeleton` |
| D | `1` | `inmemory_test` | `openai` | 201 (con fallback si API no disponible) | `InMemoryConversationStateRepository` | `fake` | `openai` | `product_adapter_skeleton` |
| E | `1` | `postgres` | unset o `fake` | 201 (si PG config OK) / 503 (si falta config DB) | `SyncPostgresConversationStateRepository` | `fake` | `fake` | `product_adapter_skeleton` |
| F | `1` | `inmemory_test` | valor invalido | 503 controlado | — | — | — | — |

### Tests agregados

1. `test_product_route_llm_default_remains_fake`
2. `test_product_route_accepts_explicit_fake_llm_provider`
3. `test_product_route_rejects_invalid_llm_provider`
4. `test_product_route_openai_missing_api_key_returns_controlled_error`
5. `test_product_route_openai_config_error_does_not_leak_secrets`
6. `test_product_route_openai_mode_does_not_call_openai_in_unit_tests`
7. `test_product_route_state_hardening_still_required`

Total: 28 tests en `test_sales_diagnosis_runtime_route.py`.

### Capacidades futuras no activadas

Esta fase no implementa ni habilita:

- frontend;
- Astro;
- Svelte;
- UI;
- Home premium;
- Console UI;
- SSE productivo;
- OpenAI real por default;
- LiteLLM;
- Milvus real;
- ArangoDB;
- pgvector;
- cross-encoder;
- Step-to-Action;
- lead_capture;
- diagnostic_code;
- WhatsApp handoff;
- CRM real.

## Fase 1.9f — Product adapter OpenAI direct HTTP smoke

### Script

`scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py`

### Requisitos

- Backend corriendo con:
  - `TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1`
  - `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test` (o `postgres`)
  - `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai`
  - `TEAM360_OPENAI_KEY` o `OPENAI_API_KEY`
- Puerto default: `8018`
- Modelo via `TEAM360_OPENAI_MODEL` (default `gpt-5-nano`)

### Skip controlado

Si `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER` no es `openai`
o faltan las API key envs, el script sale con `exit 0` sin error.

### Validaciones

1. Request valido devuelve 201 con response_text presente.
2. session_id preservado.
3. runtime_mode = `product_adapter_skeleton`.
4. Response contract estable (9 keys esperadas).
5. No Milvus real (chunks fake `dev_doc_*`).
6. No stacktrace en errores 400.
7. No LiteLLM real (sin referencia a litellm en respuestas).
8. No DB real leak (inmemory_test — sin "postgres" en respuesta).
9. Provider result event (`team360.llm.provider_result`):
   - `response_is_fallback` indica si OpenAI respondio realmente o se uso fallback.
   - Por defecto, falla si detecta fallback (SAFE_ACK_TEXT).
   - `--allow-fallback` ignora el fallback y pasa igual.
10. turn_count incrementa (1 → 2).

### Nuevo evento en runtime

En `modules/sales_diagnosis_runtime/runtime.py`, despues de `self._llm.generate()`,
se agrega un `ProgressiveEvent` con `event_type="team360.llm.provider_result"`
y payload `{"response_is_fallback": bool}`.

Esto permite distinguir si un provider devolvio texto real o el safe ack
de fallback sin exponer secrets, stacktrace ni detalles del provider.

### Comando

```bash
cd backend

# Sin envs -> skip
uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py

# Con envs -> OpenAI real
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
TEAM360_OPENAI_KEY=sk-... \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py

# Con allow-fallback
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
TEAM360_OPENAI_KEY=sk-... \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py --allow-fallback
```

### Casos de la matriz (actualizada)

| # | Route | State | LLM | HTTP | Notas |
|---|-------|-------|-----|------|-------|
| A | disabled | — | — | 404 | — |
| B | enabled | unset | — | 503 | — |
| C | enabled | inmemory_test | fake | 201 | LLM fake |
| D | enabled | inmemory_test | openai | 201 | OpenAI opt-in |
| E | enabled | postgres | fake | 201/503 | PG config |
| F | enabled | inmemory_test | invalido | 503 | — |
| G | enabled | inmemory_test | openai (smoke) | 201 | Smoke valida provider_result |

### Lo que no se toco

- No frontend, Astro, Svelte, UI.
- No SSE productivo.
- No LiteLLM.
- No Milvus real.
- No ArangoDB, pgvector, cross-encoder.
- No Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real.
- NO se agregaron tests que dependan de OpenAI real.
- Pytest normal sigue sin network real (363 passed, 9 skipped).

## Fase 1.9g — OpenAI direct real validation

### Resolucion centralizada desde globalVar.py

La API key de OpenAI se resuelve mediante `get_team360_openai_key()` en
`globalVar.py` con la siguiente prioridad:

1. `OpenAI_Key_JAI_query` (usada por infraestructura JAI)
2. `TEAM360_OPENAI_KEY`
3. `OPENAI_API_KEY`
4. `VERTICE360_OPENAI_KEY`

El modelo se resuelve mediante `get_team360_openai_model()`:
- `TEAM360_OPENAI_MODEL`
- Default: `gpt-5-nano`

No es necesario exportar la key en el shell si ya esta configurada en
`.bashrc`, entorno o `globalVar.py`.

### Estado

La validacion real contra OpenAI con `gpt-5-nano` fue ejecutada y paso:

- `smoke_sales_diagnosis_runtime_product_adapter_openai.py`: **14/14 passed**
- HTTP 201 con response_text presente.
- `runtime_mode`: `product_adapter_skeleton`.
- Contrato de respuesta estable (9 keys).
- `team360.llm.provider_result` presente con `response_is_fallback=false`.
- OpenAI respondio realmente (no fallback).
- No se uso LiteLLM.
- No se uso Milvus real (chunks `dev_doc_*`).
- turn_count incrementa (1 → 2).

### Comando

```bash
cd backend

# Terminal 1:
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run uvicorn app:app --host 127.0.0.1 --port 8018

# Terminal 2:
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py
```

Nota: La key y modelo se resuelven desde `globalVar.py`; no es necesario
pasarlos por shell si ya estan configurados en el entorno.

### Lo que valida el smoke cuando se ejecute con OpenAI real

1. HTTP 201 con response_text presente.
2. session_id preservado.
3. runtime_mode = `product_adapter_skeleton`.
4. Response contract estable (9 keys).
5. No Milvus real (chunks `dev_doc_*`).
6. No stacktrace en errores 400.
7. No LiteLLM real.
8. No DB leak (inmemory_test).
9. `team360.llm.provider_result` event con `response_is_fallback=false`.
10. turn_count incrementa (1 → 2).

### Lo que no se toco

- No frontend, Astro, Svelte, UI.
- No SSE productivo.
- No LiteLLM.
- No Milvus real.
- No ArangoDB, pgvector, cross-encoder.
- No Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real.
- No se modifico codigo, runtime, rutas, schemas ni tests existentes.

### Resumen del bloque 1.9

| Fase | Que agrega | Estado |
|------|------------|--------|
| 1.9a | Product route adapter skeleton con feature flag, defaults seguros, contrato HTTP y tests | Committed |
| 1.9b | State hardening: state repository obligatorio, `SyncPostgresConversationStateRepository`, errores controlados sin secrets | Committed |
| 1.9c | Smoke HTTP product adapter con Postgres opt-in, cleanup prefijado y validacion de contrato completo | Committed |
| 1.9d | Release gate: matriz, comandos consolidados, confirmacion de defaults y limites | Committed |
| 1.9e | Product adapter OpenAI direct opt-in boundary: nueva env `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER`, `_ProductOpenAILLMProvider`, tests, matriz actualizada | Committed |
| 1.9f | Product adapter OpenAI direct HTTP smoke: script, `team360.llm.provider_result` event, --allow-fallback, docs | Committed |
| 1.9g | OpenAI direct real validation: helpers `get_team360_openai_key()` y `get_team360_openai_model()` en `globalVar.py`, resolucion centralizada con `OpenAI_Key_JAI_query`, smoke real OpenAI **14/14 passed**, `response_is_fallback=false` | Este documento |

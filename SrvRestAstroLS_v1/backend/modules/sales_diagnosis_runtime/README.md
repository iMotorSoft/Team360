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

## Proximas fases sugeridas

1. ~~1.8b -- MilvusRetrievalProvider runtime con fallback pgvector.~~ **(Completado)**
2. ~~1.8c -- QueryEmbeddingProvider + Prompt/GuardrailPolicy hardening.~~ **(Completado)**
3. ~~1.8d -- ConversationState persistence skeleton.~~ **(Completado)**
4. ~~1.8e -- PostgreSQL 18 local integration smoke for ConversationState persistence.~~ **(Completado)**
5. 1.8f -- backend-only runtime integration smoke with fakes.

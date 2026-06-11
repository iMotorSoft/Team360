# Backend Scripts

Scripts operativos y utilitarios del backend.

Si aparecen scripts de catalogo, pgvector o sync desde `v360`, deben tratarse como infraestructura futura opcional.
No forman parte del runtime central actual de Team360 ni de la prioridad principal del producto.

## automation_diagnosis

- `smoke_automation_diagnosis_litellm.py`: smoke HTTP controlado para validar que un backend ya levantado con `TEAM360_AI_PROVIDER=litellm` puede iniciar sesion, guardar 10 respuestas y clasificar usando el proxy LiteLLM real. Tambien sirve para modo combinado `TEAM360_AI_PROVIDER=litellm` + `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`; usar `--print-sql` para imprimir la query read-only de verificacion PostgreSQL por `session_id`.

Modo combinado LiteLLM + PostgreSQL:

```bash
cd backend
uv run python scripts/smoke_automation_diagnosis_litellm.py --backend-url http://127.0.0.1:8011 --timeout 120 --print-sql
```

Si PostgreSQL falla durante el snapshot, el backend debe responder HTTP 503 y el smoke imprime el cuerpo truncado del error.

## sales_diagnosis_runtime

### Runtime dev endpoint release gate

Endpoint interno/dev:

`POST /api/dev/sales-diagnosis-runtime/turn`

Defaults seguros:

| Dimension | Env var | Default | Opt-in |
|-----------|---------|---------|--------|
| State | `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY` | `inmemory` | `postgres` |
| Retrieval | `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER` | `fake` | `milvus` |
| LLM | `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER` | `fake` | `litellm` |

El endpoint sigue siendo interno/dev. Pytest normal no usa servicios reales.
No hay endpoint publico nuevo, frontend, SSE productivo, Step-to-Action,
lead_capture, diagnostic_code, WhatsApp handoff ni CRM real.
La configuracion DB de los modos Postgres se resuelve desde `backend/globalVar.py`
via `get_team360_db_url_psql()`; las env vars son entradas de esa configuracion.

Comandos smoke del gate:

```bash
cd backend

# Base InMemory
uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py

# Postgres opt-in (backend debe correr con TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres)
TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup

# LiteLLM opt-in (backend debe correr con TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm)
TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py
```

- `smoke_sales_diagnosis_runtime_postgres.py`: smoke backend-only del runtime completo `AssistantConversationRuntime` contra PostgreSQL 18 real.
  - Usa fake RetrievalProvider (no Milvus), fake LLMProvider (no OpenAI), fake MetricsRecorder y fake AuditTrail.
  - Realiza 4 turnos: safe → safe → soft guardrail (too_many_questions) → hard guardrail (unsafe_claim / UnsafeResponseError).
  - Valida que state se guarda/carga entre turnos, turn_count incrementa, guardrails funcionan y cleanup se ejecuta.
  - Requiere `TEAM360_DB_URL` y migracion 007 aplicada.
  - No endpoint, no frontend, no LLM real, no Milvus real.

  ```bash
  cd backend
  TEAM360_DB_URL=postgresql://user:pass@localhost:5432/team360 \
    uv run python scripts/smoke_sales_diagnosis_runtime_postgres.py
  ```

- `smoke_sales_diagnosis_state_postgres_async.py`: smoke async de `AsyncPostgresConversationStateRepository` contra PostgreSQL 18 real.
  - Usa psycopg_pool.AsyncConnectionPool directamente.
  - Valida save → load → update → load non-existent → verify round-trip fidelity con ConversationStateSerializer y RetrievedChunks.
  - Requiere `TEAM360_DB_URL` (o `TEAM360_DB_URL_PSQL`) y migracion 007 aplicada.
  - No runtime, no endpoint, no LLM, no Milvus.

  ```bash
  cd backend
  TEAM360_DB_URL=postgresql://user:pass@localhost:5432/v360 \
    uv run python scripts/smoke_sales_diagnosis_state_postgres_async.py
  ```

## sync_conversation_states

- `smoke_sales_diagnosis_state_postgres.py`: smoke original (sync bridge) para validar tabla `sales_diagnosis_conversation_states` contra PostgreSQL real. Pre-1.8g, reemplazado por el smoke async.

- `smoke_sales_diagnosis_runtime_dev_endpoint.py`: smoke HTTP del endpoint interno/dev `POST /api/dev/sales-diagnosis-runtime/turn`. Requiere backend corriendo. Valida response contract, turn_count, guardrails, IDs prohibidos, runtime_mode, y que no se usen servicios reales. No requiere DB, no requiere LLM real, no requiere Milvus.

  Soporta el flag `--cleanup` para eliminar las sesiones de prueba de PostgreSQL
  cuando el backend corre con `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres`
  (requiere `TEAM360_DB_URL` en el entorno del smoke).

  ```bash
  cd backend
  # terminal 1: backend (default inmemory)
  uv run uvicorn app:app --host 127.0.0.1 --port 8000
  # terminal 2: smoke default
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py

  # terminal 1: backend (postgres opt-in)
  TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres \
    uv run uvicorn app:app --host 127.0.0.1 --port 8000
  # terminal 2: smoke postgres con cleanup
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py --cleanup
  ```

- `smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py`: smoke HTTP opt-in del endpoint interno/dev con proveedor LLM LiteLLM. Requiere backend corriendo con `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm`. Si faltan `TEAM360_LITELLM_BASE_URL` o `TEAM360_LITELLM_API_KEY`, el backend devuelve HTTP 500 controlado y el smoke lo valida como skip. Si estan configuradas, valida response contract, session_id, runtime_mode, retrieved_sources fake, guardrail unsafe y no stack traces. No requiere DB, no requiere Milvus.

  ```bash
  cd backend
  # terminal 1: backend con LiteLLM
  TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \
    uv run uvicorn app:app --host 127.0.0.1 --port 8000
  # terminal 2: smoke LiteLLM opt-in
  TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm \
    uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py
  ```

### Fase 1.9c — Product adapter Postgres HTTP smoke

Script:

- `smoke_sales_diagnosis_runtime_product_adapter_postgres.py`: smoke HTTP para el
  endpoint no-dev `POST /api/sales-diagnosis-runtime/turn` con
  `TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1` y
  `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres`.

  Requiere backend corriendo con Postgres opt-in. Usa solo stdlib (urllib).
  No levanta servidores.

  Si faltan las envs, hace skip con mensaje claro (exit 0, no es fallo).

  Valida:
  1. Request valido devuelve 201 con respuesta segura.
  2. Response contract estable (9 keys esperadas).
  3. session_id preservado entre turnos.
  4. turn_count incrementa (1 → 2).
  5. runtime_mode = `product_adapter_skeleton`.
  6. No LLM real (SAFE_ACK_TEXT, no texto generado por LLM real).
  7. No Milvus real (chunks fake con prefijo `dev_doc_*`).
  8. No stacktrace en errores 400.
  9. Rechazo de IDs Vera prohibidos.
  10. No LiteLLM real (no referencia a litellm en respuestas).

  Cleanup: `--cleanup` borra solo filas con prefijo `smoke_product_pg_%`
  de `sales_diagnosis_conversation_states` y verifica remaining=0.
  No borra sesiones de otros smokes.

  La configuracion DB se resuelve desde `globalVar.get_team360_db_url_psql()`.
  No imprime DSN ni credenciales.

  ```bash
  cd backend

  # terminal 1: backend con product adapter habilitado + Postgres
  TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
    uv run uvicorn app:app --host 127.0.0.1 --port 8018

  # terminal 2: smoke product adapter Postgres
  TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py

  # Con cleanup:
  TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py --cleanup
  ```

  Opt-in explicito: requiere ambas envs en el entorno del smoke.
  Usa PostgreSQL 18 real solo si esta configurado.

  Retrieval y LLM siguen fake por default.
  No activa frontend, SSE, Step-to-Action, lead_capture, diagnostic_code,
  WhatsApp handoff ni CRM real.

### Fase 1.9f — Product adapter OpenAI direct HTTP smoke

Script:

- `smoke_sales_diagnosis_runtime_product_adapter_openai.py`: smoke HTTP para el
  endpoint no-dev `POST /api/sales-diagnosis-runtime/turn` con
  `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai`.

  Requiere backend corriendo con OpenAI opt-in. Usa solo stdlib (urllib).
  No levanta servidores.

  Si `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER` no es `openai` o falta
  `TEAM360_OPENAI_KEY` / `OPENAI_API_KEY`, hace SKIP controlado con exit 0.

  Valida:
  1. Request valido devuelve 201.
  2. session_id preservado.
  3. runtime_mode = `product_adapter_skeleton`.
  4. Response contract estable (9 keys esperadas).
  5. No Milvus real (chunks fake con prefijo `dev_doc_*`).
  6. No stacktrace en errores 400.
  7. No LiteLLM real (no referencia a litellm en respuestas).
  8. No DB real leak (inmemory_test state).
  9. Provider result event distingue respuesta real OpenAI vs fallback
     (SAFE_ACK_TEXT). Por defecto falla si detecta fallback.
  10. turn_count incrementa (1 → 2).

  Flags:
  - `--allow-fallback`: no fallar si OpenAI devolvio fallback seguro.

  Comandos:

  ```bash
  cd backend

  # terminal 1: backend con product adapter + OpenAI
  TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  TEAM360_OPENAI_KEY=sk-... \
    uv run uvicorn app:app --host 127.0.0.1 --port 8018

  # terminal 2: smoke OpenAI (sin envs -> skip)
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py

  # smoke OpenAI (con envs -> real)
  TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  TEAM360_OPENAI_KEY=sk-... \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py

  # smoke OpenAI (con allow-fallback)
  TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  TEAM360_OPENAI_KEY=sk-... \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py --allow-fallback
  ```

  Modelo default: `gpt-5-nano` via `TEAM360_OPENAI_MODEL`.

  OpenAI directo es opt-in explicito. No usa LiteLLM, no activa Milvus.
  Retrieval sigue fake, state debe ser explicito (inmemory_test o postgres).
  No activa frontend, SSE, Step-to-Action, lead_capture, diagnostic_code,
  WhatsApp handoff ni CRM real.

### Fase 1.9h — Product adapter LiteLLM HTTP smoke

Script:

- `smoke_sales_diagnosis_runtime_product_adapter_litellm.py`: smoke HTTP para el
  endpoint no-dev `POST /api/sales-diagnosis-runtime/turn` con
  `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm`.

  Requiere backend corriendo con LiteLLM opt-in. Usa solo stdlib (urllib).
  No levanta servidores.

  Si `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER` no es `litellm` o faltan
  `TEAM360_LITELLM_BASE_URL` o `TEAM360_LITELLM_API_KEY`, hace SKIP controlado
  con exit 0.

  Valida:
  1. Request valido devuelve 201.
  2. session_id preservado.
  3. runtime_mode = `product_adapter_skeleton`.
  4. Response contract estable (9 keys esperadas).
  5. No Milvus real (chunks fake con prefijo `dev_doc_*`).
  6. No stacktrace en errores 400.
  7. No DB real leak (inmemory_test state).
  8. Provider result event distingue respuesta real LiteLLM vs fallback
     (SAFE_ACK_TEXT). Por defecto falla si detecta fallback.
  9. turn_count incrementa (1 → 2).

  Flags:
  - `--allow-fallback`: no fallar si LiteLLM devolvio fallback seguro.

  Comandos:

  ```bash
  cd backend

  # terminal 1: backend con product adapter + LiteLLM
  TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
  TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
  TEAM360_LITELLM_API_KEY=sk-... \
    uv run uvicorn app:app --host 127.0.0.1 --port 8018

  # terminal 2: smoke LiteLLM (sin envs -> skip)
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py

  # smoke LiteLLM (con envs -> real)
  TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
  TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
  TEAM360_LITELLM_API_KEY=sk-... \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py

  # smoke LiteLLM (con allow-fallback)
  TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
  TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
  TEAM360_LITELLM_API_KEY=sk-... \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py --allow-fallback
  ```

  Modelo default: `openai_gpt-5-nano` via `TEAM360_LITELLM_MODEL_ALIAS`.

  LiteLLM es opt-in explicito. No usa OpenAI directo, no activa Milvus.
  Retrieval sigue fake, state debe ser explicito (inmemory_test o postgres).
  No activa frontend, SSE, Step-to-Action, lead_capture, diagnostic_code,
  WhatsApp handoff ni CRM real.

- `inspect_sales_diagnosis_milvus_schema.py`: inspector reproducible del schema/corpus real de Milvus para Sales Diagnosis.

  - Conecta solo si existe `TEAM360_MILVUS_URI` o `TEAM360_MILVUS_HOST`.
  - Lista collection, fields, index info y row count.
  - Resuelve aliases reales del provider:
    - `knowledge_scope_code` -> `knowledge_scope_id`
    - `source_uri` -> `node_path`
    - `content` -> `content_preview`
  - Reporta coverage de `knowledge_scope_id`, `embedding_version`, `source_uri`, `content` y metadata.
  - Ejecuta una search minima con vector cero para confirmar retrieval real.
  - Con la collection real de esta fase valida:
    - `team360_lab_pgvector_benchmark_openai_small_1536`
    - `knowledge_scope_id = 8b071443-5bd6-4fe4-bbc3-fc2dca179a5b`
    - `embedding_version = team360-openai-small-1536-v1`

  ```bash
  cd backend
  TEAM360_MILVUS_HOST=127.0.0.1 \
  TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
  TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
  TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
    uv run --with pymilvus python scripts/inspect_sales_diagnosis_milvus_schema.py
  ```

- `smoke_sales_diagnosis_runtime_product_adapter_milvus.py`: smoke HTTP opt-in
  del product adapter con Milvus retrieval.

  ```
  # terminal 1: backend con product adapter + Milvus
  TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
  TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
  TEAM360_MILVUS_HOST=127.0.0.1 \
    uv run uvicorn app:app --host 127.0.0.1 --port 8018

  # terminal 2: smoke Milvus (sin envs -> skip)
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_milvus.py

  # smoke Milvus (con envs -> real)
  TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
  TEAM360_MILVUS_HOST=127.0.0.1 \
  TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
  TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
  TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_milvus.py

  # smoke Milvus (con allow-empty-results, sin corpus cargado)
  TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
  TEAM360_MILVUS_HOST=127.0.0.1 \
  TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
  TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
  TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
    uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_milvus.py --allow-empty-results
  ```

  Revisa conectividad/retrieval path contra Milvus real. Embedding fake
  1536-dim (no OpenAI, no LiteLLM). Con la collection real de esta fase,
  `TEAM360_KNOWLEDGE_SCOPE_ID` y `TEAM360_EMBEDDING_VERSION` deben apuntar
  al UUID/version observados para que `retrieved_sources` salga real.
  Si el corpus no tiene resultados, usar `--allow-empty-results`. No activa
  frontend, SSE, Step-to-Action, lead_capture, diagnostic_code,
  WhatsApp handoff ni CRM real.

### Fase 1.9n — Headless diagnostic response validation

Script:

- `evaluate_sales_diagnosis_headless_responses.py`: evaluador semantico headless
  para preguntas de diagnostico de ventas. Envía un dataset JSON al endpoint
  HTTP, evalua cobertura de claims esperados y claims prohibidos, y produce
  PASS/WARN/FAIL/SKIP sin depender de UI, navegador o frontend.

  - Usa `urllib` de la stdlib.
  - Soporta `--endpoint product` y `--endpoint dev`.
  - Default: `--endpoint product`.
  - Si el product adapter no esta habilitado o faltan las envs minimas
    (`TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1` y
    `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test` o
    `postgres`), hace skip controlado.
  - Default fake/fake: LLM y retrieval quedan en fake salvo que el entorno
    habilite OpenAI/LiteLLM/Milvus.
  - `--fail-on-warn` hace fallar la ejecucion si alguna respuesta queda en WARN.
  - `--allow-fallback` evita fallar si un modo real cae en fallback seguro.
  - `--single-case <id>` ejecuta un solo caso del dataset.
  - `--debug-request` imprime endpoint, metadata, session_id y timeout sin
    headers sensibles.
  - `--print-events` imprime eventos runtime sanitizados.
  - `--dump-provider-events` imprime solo `team360.llm.provider_result`.
  - `--require-real-llm` exige env cliente de LLM real y evidencia de provider
    cuando el contrato HTTP la conserva.
  - `--fail-on-fallback` falla solo si
    `provider_result.response_is_fallback=true`; no confunde
    `fallback_applied=true` de guardrails con fallback del provider LLM.

Dataset:

- `tests/fixtures/sales_diagnosis_headless_questions_v1.json`

Comandos:

```bash
cd backend

# Baseline product adapter fake/fake
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py

# Evaluacion dev
uv run python scripts/evaluate_sales_diagnosis_headless_responses.py --endpoint dev

# Diagnostico de un caso con LiteLLM real
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=fake \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --single-case speed_simple_001 \
    --debug-request \
    --print-events \
    --require-real-llm
```

No activa frontend, SSE productivo, Step-to-Action, lead_capture,
diagnostic_code, WhatsApp handoff ni CRM real.

### Fase 1.9p — LiteLLM fallback diagnosis

La diferencia entre el smoke LiteLLM y el evaluator headless no era que
LiteLLM estuviera roto:

- El smoke y el evaluator usan el mismo endpoint por defecto:
  `POST /api/sales-diagnosis-runtime/turn`.
- Ambos usan `Content-Type: application/json` y no envian Authorization desde
  el script cliente; la auth LiteLLM la usa el backend hacia el proxy.
- Las envs del evaluator no modifican un backend ya levantado. Si el proceso
  backend fue iniciado con token LiteLLM anterior o invalido, el proxy puede
  responder 401 y el backend devolvera fallback seguro.
- Con backend reiniciado con envs correctas, el evaluator muestra
  `provider_result.response_is_fallback=false` en los casos que preservan
  eventos.
- `fallback_applied=true` pertenece a guardrails/runtime y no debe contarse
  como fallback del provider LiteLLM.
- En respuestas `unsafe_blocked`, la ruta actual no devuelve `events`; el
  evaluator lo reporta como brecha de evidencia diagnostica, no como fallback
  LiteLLM.

Si quedan WARN/FAIL con `response_is_fallback=false`, corresponden a calidad,
guardrails o PromptPolicy y deben tratarse en una fase posterior.

### Fase 1.9q — Headless PromptPolicy/GuardrailPolicy tuning

El evaluator se uso para validar la afinacion de PromptPolicy/GuardrailPolicy
sin tocar UI ni activar capacidades futuras.

Comandos principales:

```bash
# fake/fake baseline
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=fake \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=fake \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --print-events

# LiteLLM/fake
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=fake \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --print-events \
    --require-real-llm

# LiteLLM/Milvus principal
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --print-events \
    --require-real-llm
```

Resultados finales observados:

| Escenario | Resultado | Estado fallback |
| --- | ---: | --- |
| fake/fake | 0 PASS / 10 WARN / 0 FAIL / 0 SKIP | `response_is_fallback=true` esperado |
| LiteLLM/fake `openai_gpt-5-nano` | 2 PASS / 8 WARN / 0 FAIL / 0 SKIP | `response_is_fallback=false` |
| LiteLLM/Milvus `openai_gpt-5-nano` | 5 PASS / 5 WARN / 0 FAIL / 0 SKIP | `response_is_fallback=false` |
| LiteLLM/Milvus `gpt5.5-nano` | SKIP operativo | `response_is_fallback=true` en 10/10 |

### Fase 1.9r — Headless diagnostic quality expansion

El dataset headless se expandio de 10 a 25 casos (15 nuevos) para cubrir
situaciones comerciales y tecnicas reales adicionales sin tocar UI ni activar
capacidades futuras.

**Categorias nuevas (14):**
1. Proceso manual repetitivo (Excel a sistema)
2. Datos sensibles / privacidad
3. Sistema legacy sin API
4. Portal externo de proveedor
5. Proceso de baja frecuencia
6. Error humano alto
7. Automatizacion parcial
8. Integracion CRM
9. WhatsApp handoff
10. Lead capture
11. ROI
12. Responsabilidad / supervision
13. Acceso no autorizado (rechazo)
14. Evasion de MFA (rechazo)
15. Expectativa extrema

**Cambios en evaluator:**
- `RISK_HINTS` expandido con 20 nuevas entradas para flags de riesgo
- `GLOBAL_FORBIDDEN_PATTERNS` ampliado de ~26 a ~47 patrones

**Cambios en PromptPolicy:**
- Reglas generales agregadas para cada nueva categoria (sin if por pregunta)
- GuardrailPolicy sin cambios (ya cubre capacidades futuras via patrones)

**Resultados con dataset ampliado (25 casos):**

| Escenario | Resultado | Estado fallback |
| --- | ---: | --- |
| fake/fake | 1 PASS / 24 WARN / 0 FAIL / 0 SKIP | `response_is_fallback=true` esperado en fake |
| LiteLLM/Milvus `openai_gpt-5-nano` | 0 PASS / 0 WARN / 25 FAIL / 0 SKIP | `response_is_fallback=true` — modelo devuelve contenido vacio |
| LiteLLM/Milvus `openrouter_deepseek_4_flash` | 0 PASS / 0 WARN / 25 FAIL / 0 SKIP | `response_is_fallback=true` — Milvus devuelve `dev_doc_*` fakes |
| `gpt5.5-nano` | SKIP operativo | Alias no existe en proxy |

Los FAIL en LLM real corresponden a `response_is_fallback=true` por modelo
que devuelve contenido vacio o config de retrieval que no conecta Milvus real.
No se relajo el evaluador ni se hicieron cambios agresivos de prompt.

Comandos principales (ver Fase 1.9q para comandos base):

```bash
# fake/fake con dataset ampliado
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --print-events

# LiteLLM/Milvus
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --print-events \
    --require-real-llm

# Con allow-fallback para evaluar semanticamente aunque el LLM falle
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_COLLECTION=team360_lab_pgvector_benchmark_openai_small_1536 \
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
  uv run python scripts/evaluate_sales_diagnosis_headless_responses.py \
    --allow-fallback
```

No se creo frontend, no se activaron capacidades futuras
(Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM).
LLM fake y retrieval fake siguen siendo default.

Acotacion Milvus: la validacion real uso Milvus estandar local
`milvus26-standalone` (`127.0.0.1:19530`) con MinIO y etcd del stack
`milvus26-*`. No se configuro token Milvus ni se activo retrieval real por
default; Milvus sigue siendo opt-in por env.

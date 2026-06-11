# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-06-11 (Fase 1.9l — Product adapter Milvus real smoke)

## Directorio de trabajo

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1`

## Estado general

Se inicializo la DB viva `team360` en PostgreSQL local y se aplicaron correctamente las migraciones `001_team360_core_schema.sql`, `002_team360_rbac_packages_workers_knowledge.sql`, `003_team360_pgvector_knowledge_embeddings.sql` y `004_team360_automation_diagnosis_runtime.sql`. Tambien existe una Fase 1 de `automation_diagnosis` operativa para demo controlada, con frontend real conectado a API Litestar, IA via LiteLLM por adapter, modo PostgreSQL activable, knowledge scope propio, retrieval simple sobre documentos Markdown, scoring/classifier deterministico, fixtures, tests y smokes reales. Se documento la politica de driver DB runtime (`psycopg 3 async` directo como estandar).

## Acciones realizadas

### 2026-06-10 - Fase 1.9b — Product adapter state hardening

- Se endurecio `POST /api/sales-diagnosis-runtime/turn` para que no use InMemory silencioso cuando `TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1`.
- Se agrego `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY` como selector obligatorio de state para el adapter.
- Valores aceptados: `postgres` e `inmemory_test`.
- `postgres` usa `globalVar.get_team360_db_url_psql()` y `SyncPostgresConversationStateRepository` con SQL encapsulado en `state_repository.py`.
- `inmemory_test` queda permitido solo de forma explicita para tests/control adapter; no es produccion real.
- Si falta state repo, es invalido o falta config DB para Postgres, la ruta devuelve HTTP 503 controlado, sin stacktrace ni secrets.
- Retrieval y LLM siguen fake por default; no se activan Milvus real, LiteLLM real ni OpenAI real por default.
- El endpoint dev `POST /api/dev/sales-diagnosis-runtime/turn` conserva su comportamiento y defaults.
- No se toco frontend, Astro, Svelte, UI, SSE productivo, ArangoDB, pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff ni CRM real.
- No se creo rama nueva.

### 2026-06-11 - Fase 1.9c — Product adapter Postgres HTTP smoke

- Se creo `scripts/smoke_sales_diagnosis_runtime_product_adapter_postgres.py`:
  - Smoke HTTP para el endpoint no-dev `POST /api/sales-diagnosis-runtime/turn` con Postgres state.
  - Usa solo stdlib (urllib), no levanta servidores.
  - Default base URL: `http://127.0.0.1:8018` (distinto del dev endpoint para coexistencia).
  - Si `TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED` no esta habilitada, hace skip (exit 0).
  - Si `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY` no es `postgres`, hace skip (exit 0).
  - Valida 10 condiciones:
    1. Request valido devuelve 201 con respuesta segura.
    2. Response contract estable (9 keys).
    3. session_id preservado.
    4. turn_count incrementa (1 → 2).
    5. runtime_mode = `product_adapter_skeleton`.
    6. No LLM real (SAFE_ACK_TEXT).
    7. No Milvus real (chunks fake `dev_doc_*`).
    8. No stacktrace en errores 400.
    9. Rechazo de IDs Vera prohibidos.
    10. No LiteLLM real en respuestas.
  - Cleanup: `--cleanup` borra solo filas `smoke_product_pg_%` y verifica remaining=0.
  - No imprime DSN ni credenciales.
- Se actualizaron:
  - `scripts/README.md`: nueva entrada con descripcion, validaciones y comando.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.9c agregada.
  - `status_actual.md`: este registro (Fase 1.9c).
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI, LiteLLM, Milvus, ArangoDB, pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, routes, schemas, tests existentes, endpoint dev, endpoint product adapter, smokes existentes.
- No se creo rama nueva.

### 2026-06-11 - Fase 1.9d — Product adapter release gate

- Se documento Fase 1.9d como release gate del bloque 1.9a–1.9c.
- Se agrego matriz del product adapter (5 casos: A–E) en:
  - `modules/sales_diagnosis_runtime/README.md`
  - `docs/status_actual.md`
- Se documentaron comandos smoke consolidados (dev InMemory, dev Postgres, dev LiteLLM, product adapter Postgres).
- Se confirmo cleanup prefix: `smoke_product_pg_%` exclusivo; no toca `smoke_dev_*`, `smoke_unsafe_*` ni sesiones reales.
- Se confirmaron defaults seguros:
  - State: `inmemory_test` (explicito) o `postgres` para product adapter.
  - Retrieval: `fake` no configurable en product adapter.
  - LLM: `fake` no configurable en product adapter.
- Se confirmo que product adapter NO tiene envs opt-in para retrieval ni LLM. Es intencional.
- Se confirmo que errores controlados no exponen stacktrace, DB URL, API keys, tokens ni headers sensibles.
- Se confirmo que product adapter sigue feature-flagged, no es endpoint publico final.
- Se confirmo que no hay frontend, SSE, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff ni CRM real.
- Se agrego resumen del bloque 1.9 con estado de cada fase.
- No se modifico logica del endpoint, routes, schemas, tests, ni smokes existentes.
- No se activaron servicios reales nuevos.
- No se creo rama nueva.

### 2026-06-11 - Fase 1.9e — Product adapter OpenAI direct opt-in boundary

- Se agrego `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER` env para selector de LLM en product adapter.
- Valores aceptados: `fake` (default) y `openai`.
- Se creo `_ProductOpenAILLMProvider` en `routes/sales_diagnosis_runtime.py`:
  - Lazy import de OpenAI SDK (no se importa al cargar modulo).
  - API key via `TEAM360_OPENAI_KEY` o `OPENAI_API_KEY`.
  - Modelo via `TEAM360_OPENAI_MODEL` (default `gpt-5-nano`).
  - Prompts via `PromptPolicy`.
  - Errores de API retornan `SAFE_ACK_TEXT` como fallback (sin stacktrace).
- Si API key falta: HTTP 503 controlado sin secrets.
- Si provider invalido: HTTP 503 controlado listando valores aceptados.
- Se agregaron 7 tests nuevos en `test_sales_diagnosis_runtime_route.py`:
  1. LLM default remains fake.
  2. Accepts explicit fake LLM provider.
  3. Rejects invalid LLM provider.
  4. OpenAI missing API key returns controlled error.
  5. OpenAI config error does not leak secrets.
  6. OpenAI mode does not call OpenAI in unit tests.
  7. State hardening still required.
- Total tests: 28 en route file.
- Matriz actualizada (6 casos: A–F).
- Se actualizaron:
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.9e, matriz actualizada.
  - `status_actual.md`: este registro.
- No se tocaron: frontend, Astro, Svelte, UI, SSE, LiteLLM, Milvus, ArangoDB, pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, endpoint dev, smokes existentes.
- No se creo rama nueva.

### 2026-06-11 - Fase 1.9f — Product adapter OpenAI direct HTTP smoke

- Se creo `scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py`.
- Skip controlado si falta `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai`
  o `TEAM360_OPENAI_KEY` / `OPENAI_API_KEY` (exit 0, no es fallo).
- Valida: 201, session_id, runtime_mode, response contract, fake retrieval,
  no stacktrace, no LiteLLM, no DB leak, provider result event, turn_count.
- Flag `--allow-fallback` para no fallar si OpenAI devolvio SAFE_ACK_TEXT.
- Se agrego `team360.llm.provider_result` event en `runtime.py` despues de
  `self._llm.generate()` para distinguir respuesta real vs fallback.
- Se actualizaron:
  - `scripts/README.md`: seccion Fase 1.9f.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.9f, matriz caso G.
  - `docs/status_actual.md`: este registro.
- No se tocaron: frontend, Astro, Svelte, UI, SSE, LiteLLM, Milvus, ArangoDB,
  pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code,
  WhatsApp handoff, CRM real, endpoint dev, smokes existentes, tests existentes.
- No se agregaron tests que dependan de OpenAI real.
- No se modifico el contrato HTTP publico.
- No se creo rama nueva.

### 2026-06-11 - Fase 1.9g — OpenAI direct real validation

- Se agregaron helpers `get_team360_openai_key()` y `get_team360_openai_model()` en `globalVar.py`.
- `get_team360_openai_key()` resuelve con prioridad: `OpenAI_Key_JAI_query` > `TEAM360_OPENAI_KEY` > `OPENAI_API_KEY` > `VERTICE360_OPENAI_KEY`.
- `get_team360_openai_model()` resuelve: `TEAM360_OPENAI_MODEL` (default `gpt-5-nano`).
- `_ProductOpenAILLMProvider` en `routes/sales_diagnosis_runtime.py` ahora usa `get_team360_openai_key()` de `globalVar.py` como fuente unica, no lee env vars directas.
- `_detect_openai_envs()` en el smoke script ahora usa `get_team360_openai_key()` de `globalVar.py`.
- Tests actualizados: se agrego `monkeypatch.delenv("OpenAI_Key_JAI_query")` en los 3 tests que requieren ausencia de key.
- Se ejecuto smoke real OpenAI con `gpt-5-nano`:
  - Backend levantado en puerto 8018.
  - **14/14 checks PASSED**.
  - `response_is_fallback=false` — OpenAI respondio realmente.
  - No se uso fallback silencioso.
  - No se uso LiteLLM.
  - No se uso Milvus real.
  - `/api/dev/sales-diagnosis-runtime/turn` sigue funcionando correctamente.
- Tests unitarios pasan sin network real:
  - `test_sales_diagnosis_runtime_route.py`: **28 passed**.
  - `test_sales_diagnosis_runtime_dev_route.py`: **36 passed**.
  - Suite completa: **363 passed, 9 skipped**.
- Product adapter sigue feature-flagged (`TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED`).
- State sigue explicito (inmemory_test o postgres).
- LLM default sigue fake.
- OpenAI solo opt-in explicito.
- LiteLLM no se activo.
- Milvus real no se activo.
- Retrieval sigue fake.
- No se toco frontend, Astro, Svelte, UI, SSE, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real.
- Se elimino `bun.lock`, `index.ts`, `package.json`, `tsconfig.json` (artefactos del crash anteriores).
- No se creo rama nueva.

La key OpenAI se resuelve desde `globalVar.get_team360_openai_key()`, que lee `OpenAI_Key_JAI_query`, `TEAM360_OPENAI_KEY` o `OPENAI_API_KEY` del entorno.
No es necesario exportarla explicitamente si ya esta configurada.

### 2026-06-11 - Fase 1.9h — Product adapter LiteLLM opt-in boundary

- Se agrego `_ProductLiteLLMProvider` en `routes/sales_diagnosis_runtime.py`.
- Usa `LiteLLMClient` de `modules.automation_diagnosis.litellm_client` (urllib, no OpenAI SDK).
- Requiere `TEAM360_LITELLM_BASE_URL` y `TEAM360_LITELLM_API_KEY`.
- Modelo default: `openai_gpt-5-nano` via `TEAM360_LITELLM_MODEL_ALIAS`.
- `_resolve_product_llm_provider()` actualizado para aceptar `litellm`.
- Errores de config devuelven HTTP 503 controlado (no 500 como dev endpoint).
- Tests agregados (6): accept, missing base_url, missing api_key, no-leak, no-network, invalid provider msg actualizado.
- Se creo `scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py`.
- Smoke skip controlado si falta config (exit 0).
- Smoke con flag `--allow-fallback`.
- Se actualizaron:
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.9h, matriz caso H.
  - `scripts/README.md`: seccion Fase 1.9h.
  - `docs/status_actual.md`: este registro.
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI real, Milvus, ArangoDB,
  pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code,
  WhatsApp handoff, CRM real, endpoint dev, smokes existentes, tests existentes.
- No se agregaron tests que dependan de LiteLLM real.
- No se modifico el contrato HTTP publico.
- No se creo rama nueva.

### 2026-06-11 - Fase 1.9i — LiteLLM real validation for Sales Diagnosis Product Adapter

- Se valido el product adapter contra LiteLLM real con alias `openai_gpt-5-nano`.
- Backend levantado con:
  - `TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1`
  - `TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test`
  - `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm`
  - `TEAM360_LITELLM_BASE_URL=http://localhost:4000`
  - `TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano`
- Smoke LiteLLM real: **13/13 checks PASSED**.
  - `response_is_fallback=false` — LiteLLM respondio realmente.
  - No se uso fallback silencioso.
  - No se uso OpenAI directo desde Team360.
  - No se uso Milvus real.
  - Retrieval sigue fake (chunks `dev_doc_*`).
  - State: inmemory_test explicito.
  - Sin stacktrace ni secrets en errores.
- `/api/dev/sales-diagnosis-runtime/turn` sigue funcionando (30/30 passed en smoke InMemory).
- Product adapter sigue feature-flagged.
- LLM default sigue fake.
- LiteLLM solo opt-in explicito.
- No se modifico codigo, runtime, rutas, schemas ni tests existentes.
- No se creo rama nueva.
- Se ejecutaron todas las validaciones obligatorias:
  - pytest completa: **368 passed, 9 skipped**.
  - Smoke dev InMemory: 30/30 passed.
  - Smoke dev LiteLLM (sin env): SKIP correcto.
  - Smoke product adapter LiteLLM (sin env): SKIP correcto.
  - Secret scan: sin leaks.
  - `git diff --check`: limpio.

### 2026-06-11 - Fase 1.9j — Product adapter LLM release gate

- Se cerro documental y operativamente el bloque LLM del product adapter.
- Se definio la matriz LLM del product adapter:

| Provider | Env | Default | Network real | Smoke | Validacion real | Fallback esperado |
|----------|-----|---------|-------------|-------|----------------|-------------------|
| `fake` | `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER` unset o `fake` | **Si** | No | No aplica | No aplica | No aplica |
| `openai` | `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai` | No | Solo opt-in | `smoke_sales_diagnosis_runtime_product_adapter_openai.py` | `response_is_fallback=false` con gpt-5-nano | SAFE_ACK_TEXT (con --allow-fallback) |
| `litellm` | `TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm` + `TEAM360_LITELLM_BASE_URL` + alias `openai_gpt-5-nano` | No | Solo opt-in | `smoke_sales_diagnosis_runtime_product_adapter_litellm.py` | `response_is_fallback=false` con openai_gpt-5-nano | SAFE_ACK_TEXT (con --allow-fallback) |

- `team360.llm.provider_result` event documentado:
  - `response_is_fallback=false`: provider real respondio. Smoke falla si detecta fallback.
  - `response_is_fallback=true`: provider devolvio SAFE_ACK_TEXT (fallback seguro).
  - `--allow-fallback` permite pasar incluso con fallback, para entornos sin credencial real.
- Validaciones ejecutadas en el gate:
  - pytest completa: **368 passed, 9 skipped**.
  - Smoke dev InMemory: 30/30 passed.
  - Smoke product adapter OpenAI (skip sin env): correcto.
  - Smoke product adapter LiteLLM (skip sin env): correcto.
  - Smoke product adapter Postgres (skip sin env): correcto.
  - **Smoke OpenAI real**: 14/14 passed, `response_is_fallback=false`.
  - **Smoke LiteLLM real**: 13/13 passed, `response_is_fallback=false`.
  - Secret scan: sin leaks.
  - `git diff --check`: limpio.
- No se modifico codigo, runtime, rutas, schemas ni tests existentes.
- No se creo rama nueva.

Comandos smoke consolidados:

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

# Product adapter — OpenAI opt-in (skip si falta env o key)
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py

# Product adapter — LiteLLM opt-in (skip si falta env)
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py

# Reales con backend levantado:
# Terminal 1:
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run uvicorn app:app --host 127.0.0.1 --port 8018
# Terminal 2:
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py

# O con LiteLLM:
# Terminal 1:
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
  uv run uvicorn app:app --host 127.0.0.1 --port 8018
# Terminal 2:
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=litellm \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_litellm.py
```

```bash
# Terminal 1:
TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1 \
TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test \
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run uvicorn app:app --host 127.0.0.1 --port 8018

# Terminal 2:
TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai \
  uv run python scripts/smoke_sales_diagnosis_runtime_product_adapter_openai.py
```

### 2026-06-11 - Fase 1.9k — Product adapter Milvus retrieval opt-in boundary

- Se agrego `TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER` en `routes/sales_diagnosis_runtime.py`.
- Valores aceptados: `fake` (default) y `milvus` (opt-in).
- Default obligatorio: `fake`.
- `_resolve_product_retrieval_provider()` creada, con patron consistente con el dev endpoint.
- `_build_product_adapter_runtime()` actualizada para usar `_resolve_product_retrieval_provider()`.
- Modo `milvus` requiere `TEAM360_MILVUS_URI` o `TEAM360_MILVUS_HOST`.
- Modo `milvus` usa `MilvusRetrievalProvider` con `_DevFakeEmbeddingProvider` (1536-dim, no OpenAI real).
- Embedding fake: placeholder dev/product-adapter-boundary, no es estrategia final.
- Errores de config devuelven HTTP 503 controlado (no 500), sin stacktrace ni secrets.
- `MilvusRuntimeConfig.from_env()` usada tal cual existe; `__repr__` ya enmascara token.
- No se creo `_ProductMilvusRetrievalProvider` — se reusa `MilvusRetrievalProvider` directo.
- No se modifico `milvus_provider.py` ni `embedding_provider.py`.
- No se modifico `runtime.py` ni `contracts.py`.
- No se modifico el endpoint dev ni sus tests.
- Tests agregados (9):
  1. `product_route_retrieval_default_remains_fake`
  2. `product_route_accepts_explicit_fake_retrieval_provider`
  3. `product_route_accepts_milvus_retrieval_provider_with_mocked_config`
  4. `product_route_invalid_retrieval_provider_returns_controlled_503`
  5. `product_route_invalid_retrieval_provider_lists_fake_and_milvus`
  6. `product_route_milvus_missing_config_returns_controlled_503`
  7. `product_route_milvus_config_error_does_not_leak_secrets`
  8. `product_route_milvus_mode_does_not_call_real_network_in_unit_tests`
  9. `product_route_openai_litellm_paths_not_broken_by_retrieval_selector`
- Smoke real Milvus queda para Fase 1.9l.
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI real, LiteLLM real,
  Milvus real por default, ArangoDB, pgvector, cross-encoder, Step-to-Action,
  lead_capture, diagnostic_code, WhatsApp handoff, CRM real.
- No se creo rama nueva.

Se actualizaron:
  - `routes/sales_diagnosis_runtime.py`: env var, resolver, imports, docstring.
  - `tests/test_sales_diagnosis_runtime_route.py`: 9 nuevos tests.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.9k, resumen bloque 1.9.
  - `docs/status_actual.md`: este registro.

### 2026-06-11 - Fase 1.9l — Product adapter Milvus real smoke

- Se creo `scripts/smoke_sales_diagnosis_runtime_product_adapter_milvus.py`:
  - Smoke HTTP opt-in que requiere backend corriendo con `TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER=milvus`.
  - Si no es `milvus` o faltan configs Milvus → skip (exit 0).
  - Sin dependencias extra (urllib stdlib).
  - Usa `_DevFakeEmbeddingProvider` (1536-dim zeros, no OpenAI/LiteLLM real).
  - Valida: HTTP 201, session_id, runtime_mode, contract keys, sources no-fake, sin stacktrace, LLM fake, sin LiteLLM, sin DB leak, sin secrets, turn_count increment.
  - Flag `--allow-empty-results` para entornos sin corpus cargado.
- Ejecucion real contra Milvus standalone `127.0.0.1:19530` con coleccion `team360_lab_pgvector_benchmark_openai_small_1536`:
  - **15/15 checks PASSED** (con `--allow-empty-results`).
  - Backend conecto a Milvus real.
  - Milvus search fallo por schema incompatible (falta `source_uri`) → runtime captura `MilvusSearchError` → devuelve HTTP 201 con sources vacios.
  - Sin secrets, sin stacktraces, runtime_mode estable, contratos HTTP estables.
  - LLM fake (SAFE_ACK_TEXT).
- Sin envs: **SKIP correcto** (exit 0).
- Sin modificacion de codigo productivo, routes, schemas, tests ni smokes existentes.
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI real, LiteLLM real,
  ArangoDB, pgvector, cross-encoder, Step-to-Action, lead_capture,
  diagnostic_code, WhatsApp handoff, CRM real.
- No se creo rama nueva.

Se actualizaron:
  - `scripts/README.md`: seccion Fase 1.9l con comandos y validaciones.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.9l, resumen bloque 1.9 actualizado.
  - `docs/status_actual.md`: este registro.

### 2026-06-10 - Fase 1.9a — Product route adapter skeleton

- Se agrego la ruta controlada `POST /api/sales-diagnosis-runtime/turn` como `product adapter skeleton`.
- La ruta no reemplaza el endpoint interno/dev `POST /api/dev/sales-diagnosis-runtime/turn`.
- La ruta queda deshabilitada por default via feature flag `TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED`; si no esta activa responde HTTP 404 controlado y sin stacktrace.
- Con la feature flag activa usa `AssistantConversationRuntime`, `PromptPolicy` y `GuardrailPolicy` reales.
- Defaults seguros 1.9a: state `inmemory`, retrieval `fake`, LLM `fake`. No se activan servicios reales por default.
- Se agregaron schemas HTTP separados `ProductTurnRequest` y `ProductTurnResponse`, manteniendo contrato compatible con el endpoint dev y `runtime_mode = product_adapter_skeleton`.
- Se rechazan IDs prohibidos `vera_team360_sales_diagnosis`, `pkg_vera_sales_diagnosis`, `ks_vera_team360_sales_diagnosis` y `svc_vera_sales_diagnosis` con HTTP 400 controlado.
- Se agrego `tests/test_sales_diagnosis_runtime_route.py` para cubrir feature flag, contrato, defaults seguros, no uso de LiteLLM/Milvus real y continuidad del endpoint dev.
- No se toco frontend, Astro, Svelte, UI, SSE productivo, OpenAI SDK, servicios reales por default, ArangoDB, pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff ni CRM real.
- No se creo rama nueva.

### 2026-06-10 - Fase 1.8p — Runtime dev endpoint release gate

- Se audito el endpoint interno/dev `POST /api/dev/sales-diagnosis-runtime/turn` antes de abrir cualquier endpoint no-dev.
- Se documento en `backend/modules/sales_diagnosis_runtime/README.md` una matriz clara de modos:
  - State: `inmemory` default / `postgres` opt-in.
  - Retrieval: `fake` default / `milvus` opt-in.
  - LLM: `fake` default / `litellm` opt-in.
- Defaults seguros confirmados: `state=inmemory`, `retrieval=fake`, `llm=fake`.
- Se documentaron env vars necesarias para cada opt-in, combinaciones soportadas en dev y comandos smoke base InMemory, Postgres opt-in y LiteLLM opt-in.
- Se aclaro que la configuracion DB se resuelve desde `backend/globalVar.py` via `get_team360_db_url_psql()`; las env vars son entradas de esa configuracion.
- Se actualizo `backend/scripts/README.md` con el release gate operativo y comandos smoke.
- Pytest normal no usa servicios reales; los servicios reales siguen siendo opt-in.
- El endpoint sigue siendo interno/dev bajo `/api/dev/`; no se abrio endpoint publico.
- No se toco frontend, Astro, Svelte, UI, SSE productivo, endpoint publico, OpenAI SDK, ArangoDB, pgvector, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff ni CRM real.
- No se creo rama nueva.

### 2026-06-10 - Fase 1.8l — Provider mode boundary for dev endpoint

- Se agregaron dos nuevas variables de entorno en `routes/sales_diagnosis_runtime_dev.py`:
  - `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER` (default `fake`) — selecciona proveedor de retrieval.
  - `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER` (default `fake`) — selecciona proveedor de LLM.
- `_resolve_retrieval_provider()`: acepta `fake`, rechaza valores invalidos con HTTP 500.
- `_resolve_llm_provider(metadata)`: prioriza flag `dev_test_unsafe_llm` en metadata sobre env var.
- `_build_dev_runtime()` refactorizada para usar los nuevos resolvers.
- No se conectaron proveedores reales — solo el boundary/config selector preparado y testeado.
- Se agregaron 10 tests en `TestDevSalesDiagnosisRouteProviders`:
  - Default, explicit fake, invalid values (controlled error, no secret leaks), unsafe flag precedence, runtime intacto.
- Validacion: `uv run pytest` = 327 passed, 9 skipped (sin regresiones).
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI, LiteLLM, Milvus, Postgres real por defecto, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, scripts existentes.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8m — Milvus retrieval opt-in boundary for dev endpoint

- Se extendio `_resolve_retrieval_provider()` en `routes/sales_diagnosis_runtime_dev.py`:
  - `TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=milvus` ahora es valido.
  - Crea `MilvusRetrievalProvider` con `MilvusRuntimeConfig.from_env()` + `_DevFakeEmbeddingProvider` (vector estatico 1536-dim, no OpenAI).
  - Si falta `TEAM360_MILVUS_URI` y `TEAM360_MILVUS_HOST` → HTTP 500 controlado.
  - Valores invalidos siguen dando HTTP 500 (ej: `"pinecone"`).
- Se creo `_DevFakeEmbeddingProvider`: implementa `QueryEmbeddingProvider` protocol sin OpenAI.
- Se agrego `TestDevSalesDiagnosisRouteMilvus` con 4 tests:
  - `test_milvus_mode_is_accepted_with_env_config` — Milvus mode con mock config es aceptado.
  - `test_milvus_mode_without_config_returns_controlled_error` — Sin config → HTTP 500.
  - `test_milvus_mode_config_error_does_not_leak_secrets` — Error sin secrets.
  - `test_postgres_state_still_works_with_fake_retrieval` — Postgres state + fake retrieval OK.
- Se modifico `test_invalid_retrieval_provider_returns_controlled_error` para usar `"pinecone"` en vez de `"milvus"` (ahora valido).
- Validacion: `uv run pytest` = 331 passed, 9 skipped (+4 nuevos).
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI, LiteLLM, Milvus real por defecto, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, scripts existentes.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8n — LiteLLM LLM provider opt-in boundary for dev endpoint

- Se extendio `_resolve_llm_provider()` en `routes/sales_diagnosis_runtime_dev.py`:
  - `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm` ahora es valido.
  - Crea `_DevLiteLLMProvider` que usa `LiteLLMClient` de `automation_diagnosis` (urllib, no OpenAI SDK).
  - Requiere `TEAM360_LITELLM_BASE_URL` y `TEAM360_LITELLM_API_KEY` — si falta → HTTP 500.
  - Construye prompts via `PromptPolicy.build_system_prompt()` y `build_turn_prompt()`.
  - Modelo via `TEAM360_LITELLM_MODEL_ALIAS` (default: `openrouter_qwen3_30b_a3b_thinking_2507`).
  - Valores invalidos siguen dando HTTP 500.
  - `dev_test_unsafe_llm` en metadata sigue teniendo prioridad.
- Se creo `_DevLiteLLMProvider` en la route file: implementa `LLMProvider` protocol.
- Se agrego `TestDevSalesDiagnosisRouteLiteLLM` con 4 tests:
  - `test_litellm_mode_is_accepted_with_env_config` — LiteLLM mode con env vars aceptado.
  - `test_litellm_mode_without_config_returns_controlled_error` — Sin config → HTTP 500.
  - `test_litellm_mode_does_not_leak_secrets` — Error sin secrets.
  - `test_milvus_retrieval_does_not_force_real_llm` — Milvus retrieval + fake LLM coexisten.
- Validacion: `uv run pytest` = 335 passed, 9 skipped (+4 nuevos).
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI real por default, Milvus real por default, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, scripts existentes.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8o — LiteLLM HTTP smoke opt-in for dev endpoint

- Se creo `scripts/smoke_sales_diagnosis_runtime_dev_endpoint_litellm.py`:
  - Smoke HTTP opt-in independiente del smoke base (evita ensuciar el existente).
  - Si `TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER` no es `litellm`, hace skip (exit 0, no es fallo).
  - Si faltan `TEAM360_LITELLM_BASE_URL` o `TEAM360_LITELLM_API_KEY`, el backend devuelve HTTP 500 controlado; el smoke valida mensaje de error sin leaks de secrets.
  - Si LiteLLM esta configurado, valida:
    1. Status 201.
    2. Response contract estable (9 keys esperadas).
    3. session_id preservado.
    4. runtime_mode = `dev_fake`.
    5. retrieved_sources son chunks fake (prefijo `dev_doc_*`), no Milvus real.
    6. Guardrail unsafe (`dev_test_unsafe_llm`) funciona: response_type `unsafe_blocked`.
    7. No stack traces en errores 400.
    8. No leaks de DB por defecto.
  - Sin dependencias extra (urllib stdlib). No imprime API keys ni headers sensibles.
- Se actualizaron:
  - `scripts/README.md`: nueva entrada con descripcion y ejemplo de uso.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.8o agregada.
  - `status_actual.md`: este registro.
- Validacion: `uv run pytest` = 335 passed, 9 skipped (sin regresiones).
- Validacion: `uv run pytest tests/test_sales_diagnosis_runtime_dev_route.py` = 36 passed.
- Validacion: smoke default InMemory = OK.
- Validacion: smoke Postgres opt-in = OK.
- Validacion: smoke LiteLLM opt-in (sin env LiteLLM) = SKIP con mensaje claro.
- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI real por default, Milvus real por default, ArangoDB, cross-encoder, routes, schemas, tests existentes, smoke base.
- Sin creacion de rama nueva.

### 2026-06-10 - Team360 DB URL visible en globalVar

- Se actualizo `backend/globalVar.py` para exponer `TEAM360_DB_URL`, `TEAM360_DB_URL_PSQL`, `TEAM360_DB_NAME`, `TEAM360_DB_SCHEMA` y helpers `get_team360_db_url()` / `get_team360_db_url_psql()` como configuracion Team360 activa.
- Se mantuvieron los nombres `FUTURE_OPTIONAL_*` como aliases compatibles para scripts existentes.
- La resolucion activa de DSN queda alineada con `modules/db/settings.py`: prioridad `TEAM360_DB_URL`, fallback `TEAM360_DB_URL_PSQL`, fallback derivado desde `DB_PG_V360_URL`; sin DSN falso si no hay env configurada.
- El fallback placeholder previo queda limitado al helper legacy `get_future_optional_team360_db_url()` para compatibilidad de scripts exploratorios.
- Se agregaron tests directos en `tests/test_global_var.py`.
- No se tocaron frontend, endpoints HTTP, routes, migraciones, labs ni `team360_orquestador`.

### 2026-06-10 - Fase 1.8f — Backend-only runtime integration smoke with fakes + Postgres state

- Se creo `scripts/smoke_sales_diagnosis_runtime_postgres.py`:
  - `_SmokePostgresStateRepository`: sync bridge que implementa `StateRepository` protocol usando psycopg 3 sync directo, sin async, sin pool. Cada operacion abre/cierra conexion. Especifico para smoke; no reemplaza el async skeleton de `PostgresConversationStateRepository`.
  - `FakeRetrievalProvider`: devuelve 2 chunks controlados (`CONTROLLED_CHUNKS`), no llama Milvus.
  - `FakeLLMProvider`: modos configurables `safe`, `too_many_questions`, `unsafe_claim`, `empty`. No llama OpenAI/LiteLLM/OpenRouter.
  - `FakeMetricsRecorder`: almacena turns en memoria.
  - `FakeAuditTrail`: almacena records en memoria.
  - Flujo de 4 turnos:
    1. Turno 1 safe LLM: `AssistantConversationRuntime` real + fake retrieval + fake LLM safe → output con `response_type="final"`, `turn_count=1`. State guardado en Postgres real. Verifica `state_jsonb` y `turn_count` via SQL directo.
    2. Turno 2 safe LLM: mismo `session_id` → carga state desde Postgres → `turn_count=2`. Slots/history_summary preservados.
    3. Turno 3 soft guardrail: fake LLM `too_many_questions` → `max_questions_exceeded=True`, fallback aplicado, state guardado (`turn_count=3`).
    4. Turno 4 hard guardrail: fake LLM `unsafe_claim` con `lead_capture listo y WhatsApp handoff con SLA` → `UnsafeResponseError` capturado, verifica bloqueo.
  - Verifica existencia de tabla `sales_diagnosis_conversation_states` via `information_schema.tables`; si no existe, falla con mensaje claro: aplicar migracion 007.
  - Cleanup via `_delete_smoke_session` en bloque `finally`.
  - Usa `globalVar.get_team360_db_url()` para resolver DSN.
  - No imprime URL cruda en logs.
  - Exit 0 en exito, 1 en fallo, stdout con checks detallados.
- Se creo `tests/test_sales_diagnosis_runtime_postgres_smoke_contract.py` con 10 tests:
  - script exists, usa `get_team360_db_url()`, no imprime URL, falla sin env.
  - usa fake retrieval (no Milvus), fake LLM (no OpenAI).
  - guardrail failure case presente.
  - cleanup de session smoke.
  - referencia a migracion 007.
  - integration test (skip sin env).
- Se actualizo `README.md` del modulo con seccion Fase 1.8f.
- Se actualizo `backend/scripts/README.md` con entrada del nuevo smoke.
- Tests: `uv run pytest` = 281/282 passed, 1 skipped (integration sin env).
- No se crearon endpoints HTTP, no se toco frontend, no se modificaron routes.
- No se llama LLM real, no se llama Milvus real, no se tocan otras tablas.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.
- No se hardcodearon API keys.
- `PostgresConversationStateRepository` sigue siendo sync skeleton documentado; el smoke usa su propio bridge sync.
- No se creo rama nueva; todo en `feature/console-backend-core`.

### 2026-06-10 - Fase 1.8g — Async runtime boundary / Postgres state repository decision

- Se realizo la auditoria completa de contratos sync/async del Sales Diagnosis Runtime:
  - Todos los protocolos son sync: `StateRepository`, `RetrievalProvider`, `LLMProvider`, `MetricsRecorder`, `AuditTrail`, `QueryEmbeddingProvider`.
  - `AssistantConversationRuntime.handle_turn()` es sync — convertir a async romperia ~250 lineas de tests existentes en 5+ archivos.
  - `PostgresConversationStateRepository` es un skeleton sync que lanza `StateRepositoryError` — nunca fue operacional por el async boundary irresuelto.
  - El proyecto ya tiene un patron async establecido en `automation_diagnosis`: `AutomationDiagnosisPostgresRepository` (async def, AsyncConnection inyectada), `modules/db/transaction.py` (fetch_one, execute async), y `modules/db/pool.py` (AsyncConnectionPool).

- **Decision**: Runtime core se mantiene sync. Se agrega el async boundary solo para persistencia.
  - `AsyncStateRepository` protocol en `providers.py` — async version de `StateRepository` para produccion.
  - `AsyncInMemoryStateRepository` en `providers.py` — implementacion in-memory async para testing.
  - `AsyncPostgresConversationStateRepository` en `state_repository.py` — repositorio async productivo real contra PostgreSQL 18 con psycopg 3 pool.
  - `PostgresConversationStateRepository` sync skeleton se mantiene como documentacion/referencia (no removido).
  - Se creo `scripts/smoke_sales_diagnosis_state_postgres_async.py` — smoke async que valida save → load → update → load non-existent → verify round-trip con RetrievedChunks.
  - Se creo `tests/test_sales_diagnosis_async_state_repository.py` — 19 tests: 2 protocolo, 5 in-memory async, 5 postgres sin DB (pool raises, repr, etc), 7 postgres con DB (skip si no hay TEAM360_DB_URL).
  - Se creo `async_boundary_decision.md` — documenta la decision, arquitectura, archivos y futuro.

- Se actualizaron READMEs:
  - `modules/sales_diagnosis_runtime/README.md` con seccion Fase 1.8g.
  - `backend/scripts/README.md` con entrada del nuevo smoke y referencias cruzadas.
  - `docs/status_actual.md` con esta entrada.

- Validacion: `uv run pytest` = 299/299 passed, 9 skipped (DB-dependent). Sin regresiones.
- No se convirtio `handle_turn()` a async. No se tocaron endpoints, frontend, routes, migraciones, LLM real, Milvus real, ArangoDB.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.

### 2026-06-10 - Fase 1.8h — Internal dev endpoint contract for Sales Diagnosis Runtime

- Se creo el endpoint interno/dev `POST /api/dev/sales-diagnosis-runtime/turn`:
  - Usa `AssistantConversationRuntime` real con providers fake por defecto.
  - `_DevFakeRetrievalProvider`: 2 chunks controlados, no Milvus.
  - `_DevFakeLLMProvider`: retorna `SAFE_ACK_TEXT`, no OpenAI/LiteLLM.
  - `InMemoryConversationStateRepository` compartido entre requests para persistencia de sesion.
  - `PromptPolicy` real y `GuardrailPolicy` real activos.
  - Si `metadata.dev_test_unsafe_llm = true`, usa `_DevUnsafeFakeLLMProvider` que genera texto inseguro → guardrail bloquea → `response_type: "unsafe_blocked"`.
  - Rechaza IDs prohibidos (prefijo `vera_*`) con HTTP 400.
  - `runtime_mode: "dev_fake"` en toda respuesta.
  - No expone stack traces.

- Se crearon schemas Pydantic en `routes/sales_diagnosis_runtime_schemas.py`:
  - `DevTurnRequest`: session_id, message (requeridos), codes con defaults, metadata.
  - `DevTurnResponse`: session_id, response_text, response_type, fallback_applied, guardrail_flags, retrieved_sources, turn_count, events, runtime_mode.

- Se registro el route handler en `app.py`.

- Se crearon 12 tests en `tests/test_sales_diagnosis_runtime_dev_route.py`:
  1. Returns 201 with safe response.
  2. Requires message (400).
  3. Requires session_id (400).
  4. Uses default codes.
  5. Rejects prohibited vera assistant_instance_code.
  6. Rejects prohibited vera package_code.
  7. Guardrail blocks unsafe fake LLM.
  8. Increments turn_count same session.
  9. Does not call real LLM.
  10. Does not call real Milvus (fake sources returned).
  11. Response contract stable (expected keys).
  12. No stack trace in error responses.

- Validacion: `uv run pytest tests/test_sales_diagnosis_runtime_dev_route.py` = 12/12 passed.
- Sin frontend, sin SSE, sin LLM real, sin Milvus real, sin DB real, sin ArangoDB.
- Sin Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8i — Dev endpoint hardening + smoke script

- Se creo `scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py`:
  - Invoca `POST /api/dev/sales-diagnosis-runtime/turn` por HTTP.
  - Requiere backend corriendo (no DB, no LLM real, no Milvus).
  - `--backend-url` argumento (default `http://127.0.0.1:8000`).
  - Usa `urllib.request` (stdlib, sin dependencias extras).
  - Valida 12 condiciones:
    1. Request valido devuelve 201.
    2. Response contract estable (9 keys).
    3. session_id se preserva.
    4. turn_count incrementa (1 → 2).
    5. Defaults seguros de codes.
    6. IDs prohibidos Vera (`vera_team360_sales_diagnosis`, `pkg_vera_sales_diagnosis`, `ks_vera_team360_sales_diagnosis`) devuelven 400 con detail "prohibited".
    7. Fake unsafe controlado (`dev_test_unsafe_llm`) → response_type `unsafe_blocked` + guardrail_flags `["unsafe_response_blocked"]`.
    8. No stack trace en errores 400.
    9. runtime_mode = `dev_fake` en todas las respuestas.
    10. No LLM real (response es SAFE_ACK_TEXT, no texto generado por LLM real).
    11. No Milvus real (sources son chunks con prefijo `dev_doc_*`).
    12. No DB real (no leaks de "postgres" en respuestas).
  - Report PASS/FAIL por check, exit 0 si todo pasa, exit 1 si falla.

- Se actualizaron:
  - `scripts/README.md`: nueva entrada con descripcion y ejemplo de uso.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.8i agregada.
  - `status_actual.md`: este registro.

- Sin tocar frontend, Astro, Svelte, UI, SSE, OpenAI, LiteLLM, Milvus, Postgres real por defecto, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8j — Postgres opt-in state repository for dev endpoint

- Se modifico `routes/sales_diagnosis_runtime_dev.py`:
  - Nuevo env `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY`:
    - `inmemory` (default) o no seteado → `InMemoryConversationStateRepository`.
    - `postgres` → `_DevPostgresStateRepository` via psycopg 3 sync.
    - Cualquier otro valor → HTTP 500 con mensaje de valores aceptados.
  - `_DevPostgresStateRepository`: sync, per-request connection, reusa SQL de `AsyncPostgresConversationStateRepository`, serializa via `ConversationStateSerializer`.
  - Si `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres` pero no hay `TEAM360_DB_URL` → HTTP 500 con mensaje claro.
  - Errores de psycopg capturados como HTTP 500 controlado.
  - No leaks de secrets en errores.
  - No se crea pool propio.
  - `_shared_inmemory_repo` se mantiene como singleton para modo default.

- Se agregaron 6 tests en `tests/test_sales_diagnosis_runtime_dev_route.py`:
  1. `test_default_uses_inmemory_state_repository` — confirma que sin env se usa InMemory.
  2. `test_postgres_opt_in_requires_db_url` — mode=postgres sin DB_URL → 500 con mensaje.
  3. `test_invalid_state_repository_mode_returns_controlled_error` — modo invalido → 500.
  4. `test_endpoint_still_works_with_default_inmemory` — endpoint funcional sin env.
  5. `test_no_real_db_called_by_default` — no leak de "postgres" en respuesta default.
  6. `test_no_secret_leak_on_postgres_config_error` — error de config sin secrets.

- Se actualizaron:
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.8j.
  - `status_actual.md`: este registro.

- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI, LiteLLM, Milvus, Postgres real por defecto, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, scripts existentes, smoke existente.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8k — Postgres opt-in HTTP smoke for dev endpoint

- Se extendio `scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py`:
  - Detecta y muestra `TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY` activo en backend.
  - Nuevo flag `--cleanup`: elimina las sesiones de prueba de PostgreSQL al finalizar.
  - `_cleanup_postgres_sessions()`: conecta via `get_team360_db_url_psql()`, DELETE por session_id, no bloqueante, warning si no hay `TEAM360_DB_URL`.
  - Requiere `TEAM360_DB_URL` en el entorno del smoke (no necesita estar seteado para InMemory).
  - Sin cambios en el flujo de validaciones HTTP existentes (sigue 30 checks).

- Se actualizaron:
  - `scripts/README.md`: entrada con flag `--cleanup` y ejemplo postgres.
  - `modules/sales_diagnosis_runtime/README.md`: seccion Fase 1.8k.
  - `status_actual.md`: este registro.

- No se tocaron: frontend, Astro, Svelte, UI, SSE, OpenAI, LiteLLM, Milvus, Postgres real por defecto, ArangoDB, cross-encoder, Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM real, routes, schemas, tests existentes.
- Sin creacion de rama nueva.

### 2026-06-10 - Fase 1.8e — PostgreSQL 18 local integration smoke for ConversationState persistence

- Se creo migracion `db/migrations/007_sales_diagnosis_conversation_states.sql` con:
  - Tabla `sales_diagnosis_conversation_states` con `session_id` PK, `assistant_instance_code`, `package_code`, `knowledge_scope_code`, `state_jsonb` jsonb NOT NULL, `created_at_utc`, `updated_at_utc`.
  - CHECK constraint `chk_sd_cs_jsonb_is_object` que valida `jsonb_typeof(state_jsonb) = 'object'`.
  - 4 indices: `idx_sd_cs_updated_at` (DESC), `idx_sd_cs_assistant_instance`, `idx_sd_cs_package`, `idx_sd_cs_knowledge_scope`.
  - Idempotente (`IF NOT EXISTS`).
- Se actualizo `state_repository.py`:
  - Agregada constante `MIGRATION_FILE` apuntando a `db/migrations/007_sales_diagnosis_conversation_states.sql`.
  - `PostgresConversationStateRepository.load()` y `save()` ahora lanzan `StateRepositoryError` con mensaje claro de que son sync skeleton y la validacion via smoke script. La guardia `_ensure_pool()` se mantiene.
  - `SUGGESTED_DDL` actualizada con CHECK constraint y 4 indices (sincronizada con migracion).
- Se creo `scripts/smoke_sales_diagnosis_state_postgres.py`:
  - Lee `TEAM360_DB_URL` (con fallback a `TEAM360_DB_URL_PSQL`); error si no configurado.
  - Sanitiza URL para logging (password oculto).
  - Crea `AsyncConnectionPool`, adquiere conexion.
  - Aplica migracion 007 (idempotente).
  - Flujo: generate test state via `ConversationStateSerializer` → INSERT → SELECT + deserializa + verifica (session_id, turn_count, slots, history_summary, pending_questions) → UPSERT (turn_count 3→5) → SELECT + verifica cambio → verifica `updated_at_utc >= created_at_utc` → DELETE cleanup.
  - Exit 0 en exito, 1 en fallo.
- Se creo `tests/test_sales_diagnosis_state_postgres_contract.py` con 15 tests:
  - Migration contract (5): file exists, table name, CHECK constraint, 4 indexes, idempotent.
  - Repository contract (5): migration reference, table name matches, repr no password, repr with pool, errors without pool.
  - Smoke script contract (4): script exists, requires env var, sanitizes URL, uses migration file.
  - Integration (1, skip sin env): smoke real passes with DB URL.
- No se crearon endpoints HTTP, no se toco frontend, no se modificaron routes.
- No se llama LLM real, no se toca Milvus, no se tocan otras tablas.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.
- No se hardcodearon API keys.

### 2026-06-10 - Fase 1.8d — ConversationState persistence skeleton

- Se creo `backend/modules/sales_diagnosis_runtime/state_repository.py` con:
  - `ConversationStateSerializer`: serializa ConversationState a/desde dict JSON-compatible (jsonb-ready); preserva todos los campos incluyendo `last_sources` con `RetrievedChunk`; valida `session_id` no vacio en `to_dict`/`from_dict`; maneja campos faltantes con defaults seguros.
  - `InMemoryConversationStateRepository`: implementa `StateRepository` protocol; almacena dicts serializados para round-trip fiel con el serializer; devuelve copias independientes en cada `load()`; usado en tests y dev.
  - `PostgresConversationStateRepository skeleton`: implementa `StateRepository` protocol con pool inyectado; SQL directo con `INSERT ... ON CONFLICT DO UPDATE`; `load()` via SELECT/fetch_one; `__repr__` sin secrets; `SUGGESTED_DDL` constante con DDL de tabla sugerida (`sales_diagnosis_conversation_states` con state_jsonb). Requiere pool inyectado; levanta `StateRepositoryError` si no hay pool. No crea migracion, no conecta a DB real.
- Se agregaron errores `StateRepositoryError` y `StateSerializationError` en `errors.py`.
- Se actualizo `runtime.py`:
  - `_load_or_create_state()`: maneja gracefulmente errores de load (falla → crea estado fresco); incrementa `turn_count` en cada turno (estado nuevo o existente).
  - `_save_state()`: maneja gracefulmente errores de save (non-blocking, no falla la respuesta).
- Se actualizo `__init__.py` con 6 nuevos exports.
- Se crearon 27 tests en `tests/test_sales_diagnosis_state_repository.py` que cubren: serializer round-trip (core fields, chunks, sin chunks, optional fields, empty session_id, JSON compat, None fields), in-memory repo (save/load, missing, independent copy, overwrite, multiple sessions), postgres skeleton (repr sin secret, pool injection, error sin pool, DDL contract), runtime integration (initial state, turn_count increment, save after turn, preserve across turns, load existing, load failure graceful, save failure graceful, sin state repo, serializer-compatible storage).
- Validacion: `uv run pytest` = 257/257 passed (230 existentes + 27 nuevos).
- `git diff --check` = OK. Secret scan = 0 hits.
- No se crearon endpoints HTTP, no se toco frontend, no se modificaron routes.
- No se llama LLM real, no se toca DB, no se crearon migraciones.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.
- No se hardcodearon API keys.

### 2026-06-10 - Fase 1.8c — QueryEmbeddingProvider + Prompt/GuardrailPolicy hardening

- Se creo `backend/modules/sales_diagnosis_runtime/embedding_provider.py` con:
  - `QueryEmbeddingConfig`: dataclass con model, dimensions (1536 default), timeout_seconds, api_key_env, base_url_env; `from_env()` constructor; `__repr__` sin api_key_env.
  - `OpenAIQueryEmbeddingProvider`: implementa `QueryEmbeddingProvider`; import lazy de `openai`; lee API key de env en runtime, no en import; valida texto no vacio (`InvalidAssistantRuntimeInputError`); valida dimension 1536 (`LLMUnavailableError`); `__repr__` sin secretos; acepta `_client` para tests.
- Se endurecio `policies.py`:
  - `PromptPolicy.build_system_prompt()`: diferenciacion explicita de automatable / vendible hoy / planned_extension / no documentado; prohibicion de CRM, cierre de ventas automatico y facturacion automatica como disponibles.
  - `PromptPolicy.build_turn_prompt()`: contexto recuperado con source_uri, title, node_path y preview en formato estructurado; recordatorio de maximo 3 preguntas, espanol claro, sin HTML, sin AG-UI.
  - `GuardrailPolicy`: `CAPABILITY_PATTERNS` extensible (step_to_action, lead_capture, diagnostic_code, whatsapp_handoff, crm, auto_billing); `DECLINE_PATTERNS` compartidos; `_has_decline()` unificado; `_build_contextual_fallback()` para fallback segun tipo de violation; metodos individuales: `is_lead_capture_ready()`, `is_diagnostic_code_ready()`, `is_whatsapp_handoff_ready()`, `is_crm_ready()`, `is_auto_billing_ready()`; `build_fallback_response()` con argumentos opcionales `input`/`state`.
- Se actualizo `__init__.py` con exports de `QueryEmbeddingConfig`, `OpenAIQueryEmbeddingProvider`.
- Se crearon 11 tests en `tests/test_sales_diagnosis_embedding_provider.py` con fakes que cubren: config defaults, config repr sin api_key_env, config from_env, import lazy, missing API key, empty query, fake client 1536, wrong dimension, repr sin secretos, config model, API failure.
- Se crearon 39 tests en `tests/test_sales_diagnosis_policies.py` que cubren: PromptPolicy hardening (safe ack, future capabilities, system prompt con reglas, turn prompt con chunks, limits, diferenciacion), GuardrailPolicy individual capabilities (step_to_action, lead_capture, diagnostic_code, whatsapp_handoff, crm, auto_billing), evaluate_response integration (pricing, SLA, max questions, empty, happy path), fallback contextual (pricing, planned_extension, generico), negation detection.
- Validacion: `uv run pytest` = 230/230 passed (180 existentes + 50 nuevos).
- `git diff --check` = OK. Secret scan = 0 hits.
- No se crearon endpoints HTTP, no se toco frontend, no se modificaron routes.
- No se llama LLM real en tests, no se toca DB, no se crearon migraciones.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.
- No se hardcodearon API keys.

### 2026-06-10 - Fase 1.8b — MilvusRetrievalProvider runtime backend-only

- Se creo `backend/modules/sales_diagnosis_runtime/milvus_provider.py` con:
  - `MilvusRuntimeConfig`: dataclass configurable por constructor o env vars (TEAM360_MILVUS_URI, TEAM360_MILVUS_HOST, TEAM360_MILVUS_PORT, TEAM360_MILVUS_TOKEN, TEAM360_MILVUS_COLLECTION, TEAM360_EMBEDDING_VERSION, TEAM360_KNOWLEDGE_SCOPE_ID). `__repr__` oculta token.
  - `MilvusRetrievalProvider`: implementa `RetrievalProvider`, import lazy de pymilvus, conexion lazy al llamar retrieve, filtros por knowledge_scope_code y embedding_version, mapeo seguro a RetrievedChunk con fallbacks para campos faltantes.
- Se agrego `QueryEmbeddingProvider` protocol en `providers.py` para separar embedding de retrieval.
- Se agregaron errores `MilvusConfigurationError` y `MilvusSearchError` en `errors.py`.
- Se actualizo `__init__.py` con exports de MilvusRetrievalProvider, MilvusRuntimeConfig, MilvusConfigurationError, MilvusSearchError, QueryEmbeddingProvider.
- Se crearon 20 tests en `tests/test_sales_diagnosis_milvus_provider.py` con fakes (FakeEmbeddingProvider, FakeMilvusCollection, FakeHit) que cubren:
  - QueryEmbeddingProvider protocol con fake embedding.
  - MilvusRetrievalProvider: requiere embedding provider, mapeo de resultados, multiples resultados, filtros, configuracion, campos faltantes, resultado vacio, multiples result sets.
  - MilvusRuntimeConfig: defaults, from_env, repr oculta token, int_or_none helper, no secrets en error.
  - Runtime integration: runtime con MilvusRetrievalProvider real sin LLM, eventos, capacidades futuras.
  - Configuracion: no secrets en repr ni error messages.
- pymilvus 3.0.0 disponible en entorno. No se modifico pyproject.toml.
- Validacion: `uv run pytest tests/test_sales_diagnosis_milvus_provider.py tests/test_sales_diagnosis_runtime_contracts.py` = 57/57 passed.
- No se crearon endpoints HTTP, no se toco frontend, no se modificaron routes.
- No se llama LLM real, no se toca DB, no se crearon migraciones.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.
- No se hardcodearon API keys.

### 2026-06-10 - Fase 1.8a — Sales Diagnosis Assistant Runtime Skeleton

- Se creo el modulo `backend/modules/sales_diagnosis_runtime/` con 7 archivos:
  - `contracts.py`: 6 dataclasses (AssistantTurnInput, AssistantTurnOutput, ConversationState, RetrievedChunk, GuardrailResult, ProgressiveEvent, RuntimeMetrics) y constantes (SAFE_ACK_TEXT, PLANNED_EXTENSIONS, FORBIDDEN_TERMS).
  - `providers.py`: interfaces Protocol (RetrievalProvider, LLMProvider, StateRepository, MetricsRecorder, AuditTrail) y Null providers para testeo (NullRetrievalProvider, NullLLMProvider, InMemoryStateRepository).
  - `policies.py`: PromptPolicy con prompts configurables por assistant/package/domain y GuardrailPolicy con evaluacion heuristica (forbidden claims, planned extension, pricing/SLA, max questions, empty response).
  - `errors.py`: 6 excepciones controladas (SalesDiagnosisRuntimeError, RetrievalUnavailableError, LLMUnavailableError, GuardrailViolationError, UnsafeResponseError, InvalidAssistantRuntimeInputError).
  - `runtime.py`: AssistantConversationRuntime skeleton con metodo handle_turn() que valida input, carga estado, emite eventos progresivos, aplica fallback seguro sin LLM sin Milvus y registra metricas/auditoria.
  - `README.md`: documentacion del modulo.
  - `__init__.py`: export publico completo.
- Se crearon 37 tests en `backend/tests/test_sales_diagnosis_runtime_contracts.py` que cubren:
  - Contratos: validacion de campos requeridos, serializacion, defaults.
  - Runtime skeleton: fallback sin LLM, eventos progresivos, state repo, capacidades futuras.
  - GuardrailPolicy: Step-to-Action detection, forbidden claims con/sin negacion, pricing/SLA, max questions, empty response, fallback responses.
  - PromptPolicy: safe ack por dominio, system prompt con reglas, turn prompt con user message.
  - Providers: Null providers, InMemoryStateRepository roundtrip.
  - Constantes: PLANNED_EXTENSIONS, FORBIDDEN_TERMS, SAFE_ACK_TEXT.
- Validacion: `uv run pytest tests/test_sales_diagnosis_runtime_contracts.py` = 37/37 passed.
- No se crearon endpoints HTTP, no se toco frontend, no se modificaron routes.
- No se llama LLM real, no se llama Milvus, no se toca DB.
- No se activo Step-to-Action, lead_capture, diagnostic_code ni WhatsApp handoff.
- No se hardcodearon API keys.

### 2026-06-10 - Documento global de orquestacion Team360

- Se creo `lat.md/team360-global-orchestration.md` como vista transversal para coordinar ramas Git, hilos de chat, frentes tecnicos, labs, knowledge y decisiones comerciales/productivas.
- Se enlazo el documento desde `lat.md/lat.md`.
- Se actualizo `lat.md/status_actual.md` porque se agrego un nuevo documento dentro de `lat.md/`.
- El documento registra roles de ramas, regla de UX real vs handoff visual, separacion knowledge ingestion vs documentacion editorial, ownership de `lab/`, decisiones globales de producto y formato de cierre por rama.
- No se modifico codigo productivo, backend runtime, frontend, migraciones, paquetes knowledge editoriales ni ramas distintas a `feature/console-backend-core`.

### 2026-06-09 - Convencion de laboratorio tecnico reproducible

- Se creo `SrvRestAstroLS_v1/lab/README.md` como convencion base para experimentos tecnicos pequenos, reproducibles, aislados de produccion, auditables y comparables.
- Se documento que `lab/` no es codigo temporal descartable, sino un banco de pruebas para decidir rapido sin reconstruir contexto.
- Se definieron casos de uso para comparar modelos LLM, embeddings, prompts, chunking, golden answers, paquetes knowledge, proveedores externos e infografias HTML.
- Se establecieron reglas de estructura por experimento, resultados auditables en JSON/Markdown/HTML, ejecucion desde la raiz del proyecto y preferencia por `uv run` cuando corresponda.
- Se agrego una referencia breve en `AGENTS.md` apuntando a `SrvRestAstroLS_v1/lab/README.md`.
- No se crearon scripts, experimentos de ejemplo, integraciones productivas ni cambios de runtime.

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

## Notas de seguridad

- No se grabo la password de GitHub en archivos del proyecto.
- Se uso un archivo temporal de sesion en `/tmp/team360_github_state.json` solo para diagnostico y se elimino al terminar.
- Se cerro la sesion del navegador automatizado al finalizar la tarea.
- No se hardcodearon secretos reales.
- Las credenciales de providers/LLM se modelaron como `secret_ref`.
- `backend/temp1.txt` aparece modificado en el worktree y contiene material sensible o notas internas; no fue tocado en esta etapa.

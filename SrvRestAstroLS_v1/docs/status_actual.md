# Status actual - Team360

Objetivo: `desarrollo`

Ultima actualizacion: 2026-06-07

## Directorio de trabajo

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1`

## Estado general

Se inicializo la DB viva `team360` en PostgreSQL local y se aplicaron correctamente las migraciones `001_team360_core_schema.sql`, `002_team360_rbac_packages_workers_knowledge.sql`, `003_team360_pgvector_knowledge_embeddings.sql` y `004_team360_automation_diagnosis_runtime.sql`. Tambien existe una Fase 1 de `automation_diagnosis` operativa para demo controlada, con frontend real conectado a API Litestar, IA via LiteLLM por adapter, modo PostgreSQL activable, knowledge scope propio, retrieval simple sobre documentos Markdown, scoring/classifier deterministico, fixtures, tests y smokes reales. Se documento la politica de driver DB runtime (`psycopg 3 async` directo como estandar).

## Acciones realizadas

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

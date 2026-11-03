# Team360 Srv05 — Fase 1 de compatibilidad

Inspección y evidencia del worktree `feature/console-backend-core`, 2026-10-07. Srv01 sigue siendo la implementación y el entrypoint desplegado; no se reorganiza configuración ni se modifica producción.

## Contrato posterior de composición

Este documento conserva la evidencia histórica de Fase 1. El [aislamiento Evolution posterior](team360_srv05_evolution_isolation.md) sustituye la identidad app/factory por base compartida + extensión Srv05 explícita, sin duplicar módulos ni promover.

## Alcance y fuentes

La fase agrega una segunda dirección ASGI hacia la misma aplicación, no un motor nuevo. Se separa evidencia de código, estado DEV consultado y baseline productivo confirmado por el usuario.

- [Srv01](../backend/ls_iMotorSoft_Srv01.py): referencia funcional, intacta.
- [Srv05](../backend/ls_iMotorSoft_Srv05.py): reexporta `app` y `create_app` de Srv01.
- [Launcher backend DEV](../backend-dev.sh), [launcher Astro DEV](../astro-dev.sh): inspeccionados completos, intactos.
- [Política runtime](../../lat.md/team360-runtime-operational-policy.md) y [arquitectura embed](../../lat.md/diagnosticador-embeddable-component-architecture.md): contratos existentes, no sustituidos por este informe.
- Los cambios preexistentes GLOBAL, Messaging, Telchi y documentación se preservan. La ventana exclusiva autoriza únicamente esta fase.

## Ejecución real

Uvicorn importa una aplicación ASGI; ejecutar el archivo Python directamente no levanta un listener. El launcher configura y comprueba infraestructura, pero Srv01 no la provisiona.

### Backend DEV

El script normal usa defaults productivos, acepta overrides y arranca un único proceso. Su preflight es del stack completo, no una declaración de dependencias individuales de Flow.

1. Resuelve `SCRIPT_DIR` y hace `cd` a `SrvRestAstroLS_v1`, no a `backend`.
2. Resuelve host/port backend y PostgreSQL **antes** de cargar `.env.backend-dev.local` mediante `source` y `set -a`. Los defaults de servicios/configuración posteriores sí usan ese environment.
3. Perfil normal: exporta las variables productivas de la tabla siguiente, preservando overrides.
4. Comprueba TCP PostgreSQL, Milvus y LiteLLM con timeout; consulta `/v1/models` en LiteLLM. Con clave rechazada falla; sin clave admite 401 como reachable. La ausencia del alias esperado solo produce warning.
5. No levanta/reinicia PostgreSQL, Milvus, LiteLLM ni Evolution. Evolution y Gmail no tienen preflight normal.
6. Intenta liberar el puerto backend con TERM y luego KILL sobre listeners existentes: **riesgo heredado**, no ejecutado en esta validación.
7. Ejecuta `.venv/bin/uvicorn ls_iMotorSoft_Srv01:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"` mediante `exec`; defaults `127.0.0.1:7050`. Sin reload ni `--workers`.
8. El perfil preexistente `messaging-only` exporta `PYTHONPATH`, comprueba configuración/PostgreSQL propios y ejecuta `modules.messaging.dev_app:app`, sin Flow/Diagnosis/Milvus/LiteLLM. Rechaza un puerto ocupado sin matar listeners.

Desde el directorio real del launcher, el Python de `.venv` resolvió **ambos** módulos al source de `backend`; el source está en `sys.path`. El script normal no añade `--app-dir` ni exporta ese `PYTHONPATH`: depende de la preparación del environment Python.

### Backend PROD y contrato Srv05

El comando productivo fue confirmado explícitamente por el usuario. La única sustitución compatible propuesta es el nombre del módulo ASGI; no se cambia el deployment en esta fase.

```bash
cd SrvRestAstroLS_v1/backend
AUTOMATION_DIAGNOSIS_REPOSITORY=postgres \
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
TEAM360_AI_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://127.0.0.1:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5.4-nano \
TEAM360_LITELLM_API_MODE=chat \
TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_PORT=19530 \
TEAM360_MILVUS_COLLECTION=team360_sales_diagnosis_knowledge_v1 \
TEAM360_DIAGNOSIS_STATE_PROVIDER=postgres \
TEAM360_PUBLIC_ORGANIZATION_CODE=team360_live \
TEAM360_PUBLIC_WORKSPACE_CODE=team360_public_site \
TEAM360_PUBLIC_PACKAGE_CODE=pkg_sales_diagnosis \
TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE=ks_team360_sales_diagnosis \
uv run uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port 7050
```

La variante Srv05 conserva **todas** esas variables, DSN y secretos privados; cambia solamente `ls_iMotorSoft_Srv01:app` por `ls_iMotorSoft_Srv05:app`. También exporta el factory para `uvicorn ls_iMotorSoft_Srv05:create_app --factory`.

No hay evidencia local de systemd, Gunicorn o Docker como launcher de este backend. La política documenta operación en tmux; no se inspeccionó el host remoto. No se debe inferir su estado actual desde el worktree.

### Frontend DEV y PROD

Astro sirve las superficies UX y assets; no es un router incorporado al backend. Su launcher no levanta servicios backend ni configura automáticamente la URL REST según el puerto elegido.

- `astro-dev.sh` exige `IS_REST_PRO=false` en [global.js](../astro/src/components/global.js), además de `npx` y `node`.
- Defaults `ASTRO_HOST=127.0.0.1`, `ASTRO_PORT=3050`; no carga `.env.backend-dev.local`.
- También intenta terminar listeners del puerto elegido: riesgo heredado, no ejecutado sobre servicios existentes.
- Hace `cd astro`, ejecuta `npx astro build` para materializar el grafo embed y luego `exec npx astro dev --config astro.config.dev.mjs --host ... --port ...`.
- [Config DEV](../astro/astro.config.dev.mjs) conserva la base y añade [assets embed DEV](../astro/scripts/embed-dev-assets.mjs); ignora directorios de reportes Playwright en el watcher.
- `global.js` tiene REST DEV `http://localhost:7050`, REST PROD vacío para reverse proxy `/api`, y `API_BASE_URL` derivada. Actualmente `IS_REST_PRO=false`, `IS_MOCK_MODE=true` para las superficies Console que lo consumen.
- [Config base](../astro/astro.config.mjs) configura ahora el proxy `/api` a **7050** y el entry browser `embed/team360-diagnosticador.js`. La referencia histórica a proxy 8000 en la política runtime no describe este source actual.
- Cambiar `TEAM360_BACKEND_PORT` no actualiza `global.js`; elegir otro puerto Astro tampoco amplía el CORS del backend.
- PROD frontend usa assets/Nginx según el script y políticas; no utiliza `astro-dev.sh`. No se cambió ningún asset, página ni configuración frontend.

## Mapa transitivo de arranque

El orden observado distingue construcción lazy, lifecycle ASGI y ejecución de capacidades. Importar un adapter de servicio no implica conectar a ese servicio.

```text
Environment / configuración privada
  -> Uvicorn importa Srv01 (o Srv05 -> Srv01)
  -> modules.db.pool: singleton, inicialmente sin pool
  -> module_registry: imports Flow routes + Messaging Evolution routes
  -> automation_diagnosis routes: _SERVICE creado al importar
       postgres -> settings -> AsyncConnectionPool(open=False) -> set_pool
       otro modo -> servicio in-memory/adaptador sync-async
  -> diagnosis routes: state repo creado al importar
       postgres -> SyncPostgresConversationStateRepository (DSN, sin conexión)
       memory/default -> InMemoryConversationStateRepository, warning
  -> imports rutas Console, health, producto/dev diagnosis, Gupshup y scheduler
  -> app = create_app(): rutas + CORS + debug + logging Litestar
  -> ASGI startup: open_pool -> start FlowScheduler asyncio.Task
  -> requests / ciclos: settings PG, Gmail, LLM, retrieval, bindings según capacidad
  -> ASGI shutdown: stop/cancel Flow task -> close_pool
```

- El [registry](../backend/modules/module_registry.py) actual registra Flow y Messaging; Diagnóstico y Console se agregan explícitamente desde Srv01. No se importa Telchi desde este registry ni se lo inicia por este entrypoint.
- [Automation routes](../backend/routes/automation_diagnosis.py) crean el pool cuando `AUTOMATION_DIAGNOSIS_REPOSITORY` es exactamente `postgres`; tamaño 1–5, lazy. [Pool](../backend/modules/db/pool.py) usa psycopg 3 async y `AsyncConnectionPool`.
- [Diagnosis routes](../backend/routes/diagnosis.py) seleccionan estado con `AUTOMATION_DIAGNOSIS_REPOSITORY` o, si está ausente/vacío, `TEAM360_DIAGNOSIS_STATE_PROVIDER`. El estado público actual usa conexiones psycopg **sync por operación**, no el pool async: deuda existente.
- No existe parser CLI ni listener en Srv01/Srv05. No hay supervisor de servicios o subprocesses iniciados por el entrypoint.
- Litestar crea un thread de logging QueueListener al construir la aplicación. Se observó en la prueba de imports; Srv05 no crea otro `app` ni otro listener.
- El pool gestiona sus workers/tasks al abrirse; Flow crea una tarea `flow-scheduler` y un `asyncio.Lock`. Messaging Evolution usa `asyncio.to_thread` para dispatch HTTP. Las llamadas Gmail, LLM y parte del estado público son sync dentro de caminos async.
- `package_workers` en [assistant_instances](../backend/modules/automation_diagnosis/assistant_instances.py) son bindings/metadatos; estos imports no levantan nueve procesos/colas de workers.
- Startup ignora `DatabasePoolNotInitializedError`; otros errores del pool no son capturados por ese wrapper. Fallos de start/stop scheduler se silencian en Srv01. El loop Flow registra fallos y espera antes de continuar.
- [Health](../backend/routes/health.py) devuelve estado/version estáticos. `/health` y `/api/health` **no** prueban DB, Gmail, Milvus, LiteLLM ni disponibilidad funcional del scheduler.
- Las 36 rutas observadas incluyen health, automation diagnosis, diagnosis pública/embed, adaptadores producto/dev, Console, Flow, webhooks Gupshup/Evolution y OpenAPI. Paths/métodos, CORS, debug, callbacks y OpenAPI se compararon.

## Consumidores de configuración productiva

La tabla describe consumidores efectivos, no una reorganización propuesta. No todas las variables rotuladas como contexto público son actualmente resolutores de contexto.

| Variable | Consumidor efectivo / momento | Frontera conceptual |
| --- | --- | --- |
| `AUTOMATION_DIAGNOSIS_REPOSITORY` | Automation `_SERVICE` al importar; estado público; hooks pool startup/shutdown | Módulo Diagnosis con acoplamiento GLOBAL al pool |
| `TEAM360_EMBEDDING_VERSION` | `MilvusRuntimeConfig.from_env`, filtro retrieval | Binding índice/modelo Diagnosis |
| `TEAM360_AI_PROVIDER` | `build_ai_interpreter`; provider público y classifier | Selección IA Diagnosis, no switch universal Flow |
| `TEAM360_LITELLM_BASE_URL` | `LiteLLMClient`; generación y embeddings públicos | Servicio horizontal |
| `TEAM360_LITELLM_MODEL_ALIAS` | Diagnosis y adapters AI Flow | Selección compartida con acoplamiento por módulo |
| `TEAM360_LITELLM_API_MODE` | `LiteLLMClient.text_completion` | Policy adapter/gateway, `chat` productivo |
| `TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER` | Retrieval legacy automation y modo estricto del embedding público | Módulo Diagnosis |
| `TEAM360_MILVUS_HOST` | Config provider público, conexión lazy durante retrieval | Servicio horizontal/binding Diagnosis |
| `TEAM360_MILVUS_PORT` | Igual, convertido a entero | Servicio horizontal |
| `TEAM360_MILVUS_COLLECTION` | Colección consultada por provider | Binding índice Diagnosis |
| `TEAM360_DIAGNOSIS_STATE_PROVIDER` | Fallback del estado público; no inicializa por sí solo el pool global | Módulo Diagnosis |
| `TEAM360_PUBLIC_ORGANIZATION_CODE` | Export/log del launcher; no leída por las rutas/modules Python inspeccionadas | Marcador operativo de contexto público |
| `TEAM360_PUBLIC_WORKSPACE_CODE` | Igual; runtime usa constantes/resolver | Marcador operativo de contexto público |
| `TEAM360_PUBLIC_PACKAGE_CODE` | Igual | Marcador operativo de contexto público |
| `TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE` | Igual | Marcador operativo de contexto público |

Otras entradas activas: `TEAM360_DB_URL`/`TEAM360_DB_URL_PSQL`, secretos LiteLLM, `TEAM360_EMBEDDING_MODEL`, `TEAM360_MILVUS_URI`/token y `TEAM360_KNOWLEDGE_SCOPE_ID`. No se eliminaron ni renombraron variables.

[globalVar.py](../backend/globalVar.py) es hoy un adapter de env con valores capturados al importar y algunos getters. `TEAM360_ENV` default `development` decide selección Gupshup DEV/PROD; debug es independiente mediante `TEAM360_BACKEND_DEBUG`. No hay composición base/environment/module/binding ni detección automática del host.

La resolución DB en [settings](../backend/modules/db/settings.py) prioriza URL Team360, URL PSQL, luego URL heredada `DB_PG_V360_URL` cambiando el nombre DB, y finalmente el getter global. OpenAI conserva entradas heredadas; Meta Team360 usa exclusivamente `META_TEAM360_*` en el worktree actual. Se preservan mecanismos sin imprimir valores.

## Inventario Flow

Las dependencias se expresan por capacidad. Flow no requiere que todos los servicios horizontales estén disponibles para cada consulta o ciclo.

| Capacidad | Required real | Optional / ajeno |
| --- | --- | --- |
| Casos, routing, SLA, aprobación, auditoría y configuración | PostgreSQL, repositorios `modules/flow`, migraciones correspondientes | Sin Milvus/Evolution |
| Intake Gmail, replies, notificaciones | PostgreSQL + Gmail API + Service Account/DWD + LiteLLM para interpretación | Scheduler no necesario para CLI finita |
| Scheduler embebido | PostgreSQL/settings; Gmail/LLM al ejecutar capacidades habilitadas | Automation disabled no llama Gmail; scheduler no es servicio externo |
| Resumen ejecutivo IA | PostgreSQL + LiteLLM | Gmail para acciones de reenvío, no lectura de casos |
| Canal Gupshup inbound | PostgreSQL + webhook/bridge Messaging + LiteLLM intake | Replies WhatsApp son no-op en ese bridge; no Evolution |

- [Rutas Flow](../backend/modules/flow/routes.py): `/api/team360-flow/executive` y detalle, configuración por sector, operational-settings, scheduler/status, resend-approval y cases/clear.
- [Scheduler](../backend/modules/flow/scheduler.py): singleton module-local, relee settings PostgreSQL por ciclo, pacing terminar→esperar→siguiente, backoff ante error, contrato de **un solo proceso**.
- [poll_once](../backend/modules/flow/poll_once.py): CLI finita con `--account`, `--query`, `--limit`; abre/cierra un pool propio 1–3, normaliza correo, intake, routing, SLA, replies operacionales/aprobación y notificaciones ciudadanas.
- Gmail está en [Messaging Gmail](../backend/modules/messaging/providers/gmail/client.py). Credenciales desde `TEAM360_GMAIL_SERVICE_ACCOUNT_FILE`, delegación desde `TEAM360_FLOW_GMAIL_ACCOUNT` o `TEAM360_GMAIL_DELEGATED_USER`; scope `gmail.modify`. `with_subject` + refresh Google al crear cliente, no en import.
- `FlowAutomaticRunner` reutiliza repositorios y sender; no se añade motor paralelo. El filtro de correo/cutoff viene de PostgreSQL, con builder fail-safe existente.
- LiteLLM intake, interpretación operacional, aprobación y resumen ejecutivo reutilizan `modules.automation_diagnosis.litellm_client`; comparten alias env. No hay llamadas Milvus, Evolution ni ArangoDB encontradas en el código Flow inspeccionado.
- El [webhook Gupshup](../backend/modules/messaging/webhooks/gupshup_whatsapp.py) sí enlaza realmente con `FlowIntakeService`. No debe confundirse con el webhook Evolution, que usa `MessagingService` y binding propio.
- UI: [Flow](../astro/src/pages/w/[workspaceId]/flow/index.astro), [Configuración](../astro/src/pages/w/[workspaceId]/flow/configuracion.astro), clients `flowExecutive.ts` y `flowConfiguration.ts`, shell Console.
- Seguridad actual: [access_mode](../backend/modules/flow/access_mode.py) default `default_admin` con identidad sintética MVP. Modo `authenticated` conserva PASETO y capabilities persistentes `flow.executive.read`, `flow.configuration.read/write`. Modo inválido vuelve a default admin: deuda heredada, no cambiada.
- Tests `test_flow_*.py`, `test_gmail_flow_normalization.py`, Gupshup/WhatsApp y E2E `console-flow-*.spec.ts`. Los tests PostgreSQL opt-in no se habilitaron porque varios escriben fixtures/datos.

## Inventario Diagnóstico y contexto server-side

Home, web y componente son superficies distintas que comparten contratos de diagnóstico. Console conserva su contexto separado; no se absorbe en el Core público.

- Home pública: [index](../astro/src/pages/index.astro), [t360](../astro/src/pages/t360.astro), adapter [PublicVeraEntry](../astro/src/components/diagnosis/PublicVeraEntry.svelte), zona `/t360#vera`.
- Web: conversación pública y `/w/[workspaceId]/diagnosis`, `ConsoleDiagnosis.svelte`. El API client [publicDiagnosis.ts](../astro/src/lib/api/publicDiagnosis.ts) usa URL central o URL explícita para embed.
- Core/componente: [DiagnosticadorCore](../astro/src/lib/t360/diagnosticador/DiagnosticadorCore.svelte), wrappers Vera/Embed, session storage configurable, interaction blocks y resultados. El Core actual aún importa `API_BASE_URL` como fallback: diferencia respecto del ideal completamente desacoplado.
- Distribución browser: `src/lib/t360/embed/browser-global.ts`, `public/embed/vera-loader.js`, loader/manifest/entry y chunks Astro. Mamamia demo en `public/embed-demo/mamamia360.html`. Assets, CORS estático y API son fronteras distintas, sin cambios aquí.
- Backend: `routes/automation_diagnosis.py`, `routes/diagnosis.py`, `modules/automation_diagnosis`, `modules/sales_diagnosis_runtime`, `modules/embed_clients`. Adaptadores producto/dev están registrados pero sujetos a sus flags; no son el runtime público productivo.
- Instancia estable `team360_sales_diagnosis`; nombre visible Vera. Package `pkg_sales_diagnosis`, workspace `team360_public_site`, scope `ks_team360_sales_diagnosis`, organization code público `team360_live`. El modelo legacy también usa el identificador `org_team360`: no se deben fusionar ids y codes por similitud.
- PostgreSQL es required para estado y contexto productivos. [Scope resolver](../backend/modules/sales_diagnosis_runtime/knowledge_scope_resolver.py) comprueba workspace/scope activos, organization code en metadata y binding del package activo, y devuelve UUID.
- Milvus es required para retrieval real de Diagnóstico productivo; se conecta durante retrieval, no en startup. Filtra scope y versión del embedding. El provider público se selecciona por URI/host configurados; el env `...RETRIEVAL_PROVIDER=milvus` endurece errores de embeddings y también selecciona retrieval legacy.
- LiteLLM es required para generation/classifier/embeddings reales. Alias generación `openai_gpt-5.4-nano`, embedding `openai_text_embedding_3_small`, dimensión actual 1536. No se hizo una llamada facturable en esta fase.
- Gmail, Evolution y scheduler Flow no son dependencias funcionales del turn Diagnosis. ArangoDB aparece en contratos/metadatos conceptuales; no se encontró una conexión Arango requerida en este camino público.

Resolución embed efectiva:

1. El wrapper envía `client_id`, session y mensaje a `/api/diagnosis/embed/auth`.
2. El backend consulta `embed_clients` por `client_id`, exige activo y valida Origin; usa Referer como fallback. Aplica rate limit/auditoría por proceso.
3. Emite HMAC del canonical `client_id/timestamp/session/message`; el secreto queda server-side. Tolerancia default 300 segundos.
4. `/api/diagnosis/turn` con `client_id` verifica firma, timestamp, session y origin y reconstruye assistant/organization/workspace/package/scope **desde la fila DB**. Los campos de contexto enviados por el browser no gobiernan ese camino.
5. Sin client_id, completa defaults y valida una allowlist de la tupla completa de cinco campos. No acepta un scope arbitrario del browser.
6. Resuelve scope UUID en PostgreSQL; el retrieval aplica filtro. El estado se guarda bajo session_id.

Los controles de contexto no equivalen a login enterprise. El endpoint de firma usa validación de origin, no identidad autenticada del usuario. HMAC/timestamp no es un nonce de uso único; rate limiter es local al proceso. Revisar afinidad session↔binding/tenant antes de activar contextos realmente distintos: el runtime carga estado por session_id sin comparación explícita de toda la tupla en `_load_or_create_state`.

Hay fallbacks existentes: memory si no se configura estado; NullRetrieval si no hay host/URI; safe acknowledgements en ciertos errores; errores de scope pueden convertirse en scope no resuelto; algunos errores de estado se silencian en el runtime. No se ocultaron ni se modificaron en esta fase.

## Mamamia360, distribuidor y clientes

La representación comercial/mock y el binding embed operacional no son lo mismo. Se comprobó PostgreSQL DEV con consultas de solo lectura, sin seleccionar secretos.

- Concepto partner: [customer packaged assistant](../../lat.md/customer-packaged-assistant-instance.md) describe instancia/scope Mamamia propios como patrón de reutilización, no como prueba de deployment activo.
- [Mock organizations](../astro/src/lib/mock/organizations.ts): Mamá Mía 360 es `partner`, padre Team360; NETZAJ Racing y Galil Home son `partner_client` bajo ese partner. [Mock workspaces](../astro/src/lib/mock/workspaces.ts) incluye Red Israel, Marketplace principal y Comercio digital. Son fixtures UX, no filas DB comprobadas.
- Migraciones 009/010 crean/actualizan un **embed client** `mamamia360`, con etiqueta de distribuidor piloto. No crean automáticamente todo ese subárbol de clientes.
- DEV real: `mamamia360` activo apunta a **`team360_sales_diagnosis / team360_live / team360_public_site / pkg_sales_diagnosis / ks_team360_sales_diagnosis`**. Comparte contexto público Vera; no tiene una instancia/scoped corpus Mamamia independiente en ese binding.
- Origins DEV observados: localhost/127.0.0.1:3050, Mamamia con/sin www y team360.live. La migration 010 tiene un conjunto ligeramente distinto; el estado DEV no prueba que 010 esté aplicada como en PROD.
- Otro embed client DEV: `local_embed_demo`, también en el contexto Team360 público. El código del repository permite múltiples bindings; no se probó multi-tenant productivo arbitrario.
- Organizaciones DEV consultadas: `team360_platform` (`platform_owner`) y `team360_live` (`internal_client`, parent plataforma). Único workspace observado: `team360_public_site`. No había organizaciones Mamamia/NETZAJ/Galil en ese snapshot.
- Scope resolver real: contexto Team360 resolvió UUID; organization ajena con el mismo workspace/scope fue denegada. No hubo escrituras.
- No se consultó DB remota ni se alteró `mamamia360`. La UI mock del distribuidor no debe presentarse como provisioning multi-cliente productivo completo.

## Servicios horizontales y aislamiento

La clasificación se basa en consumidores actuales. Servicio compartido no significa datos, secretos o identidad externa compartidos, ni disponibilidad obligatoria para cada módulo.

| Infraestructura | Consumidores comprobados | Aislamiento/provisión actual |
| --- | --- | --- |
| PostgreSQL | Flow, Diagnosis, Console/Auth, Messaging | DB Team360, tablas/scopes/workspaces y repositories; pool global acoplado a bootstrap Diagnosis |
| LiteLLM | Diagnosis y capacidades AI Flow | Gateway externo, alias/env compartidos, adapters; no iniciado por Srv01 |
| Milvus | Retrieval Diagnosis | Índice derivado con scope/version; no dependencia Flow demostrada |
| Gmail | Correo/automatización Flow vía provider Messaging | API externa, archivo SA privado, delegated subject/config Flow |
| Evolution | Messaging DEV, no bridge Flow encontrado | Binding workspace/channel/provider/instance en PG; token/webhook/allowlist DEV, lazy por request |
| Gupshup | Messaging y bridge Flow inbound | Config DEV/PROD y claimer PG; sin firma DEV en handler existente |
| Scheduler | Flow | Tarea module-local, no un servicio horizontal externo provisionado hoy |
| Auth/Permissions | Console y Flow autenticado | PASETO + roles/profiles/capabilities/entitlements PG; no login nuevo por módulo |
| Astro/Nginx | Home/web/embed/Console | Proceso DEV o assets PROD separados del ASGI |

Console bootstrap combina permisos efectivos y entitlements del workspace/package; el contexto organización se presenta provisionalmente. No se implementó en Srv05 el modelo futuro de administración delegada de módulos por tenant.

## Implementación y diferencias

Srv05 evita duplicación de rutas, inicialización, estado y shutdown. No añade servicios requeridos ni selecciona módulos antes de comprender y aislar el bootstrap existente.

- Archivos nuevos: `backend/ls_iMotorSoft_Srv05.py`, `backend/tests/test_srv05_compatibility.py`, `backend/tests/test_srv05_launchers.py`, este informe.
- Único archivo existente cambiado: `backend/pyproject.toml`, un elemento adicional en `include` del wheel. No cambió dependency list ni lockfile.
- `Srv05.app is Srv01.app`, `Srv05.create_app is Srv01.create_app`. Srv05 no llama nuevamente al factory al importar.
- Srv01, registry, globalVar, ambos launchers, Flow, Diagnosis, frontend y migraciones permanecen intactos por esta tarea.
- Diferencia externa: un nuevo import target disponible. `backend-dev.sh` sigue usando Srv01; no hay switch ni variable nueva en el launcher.
- `python ls_iMotorSoft_Srv05.py` solo importa/construye como Srv01; **no levanta Team360 completo**. No hay `--module`, discovery, manifests, deduplicación, secret provider o health agregado. Esas capacidades son futuras, no promesas implementadas.
- Packaging source declarado; build wheel no ejecutado porque Hatchling no está instalado en este environment. No se instalaron herramientas/dependencias para este cambio.

## Validación ejecutada

Los tests de contrato son evidencia de compatibilidad, no un PASS de producción o del stack funcional completo. Los smokes propios se cerraron y no terminaron procesos ajenos.

- Baseline previo a editar: 1342 passed, 48 skipped, 1 failed. El fallo fue usar `TEAM360_AI_PROVIDER=none` en un test que espera `mock`; la repetición del archivo con `mock` dio **14 passed**. No se cambió producto por ese resultado.
- Regresión posterior de Flow, Gmail normalization, Diagnosis/automation/sales runtime, embed, Console, Gupshup/WhatsApp, Evolution y registry: **1549 passed, 48 skipped** en 37,26 s, incluido el conjunto inicial de seis tests Srv05.
- Cierre final con el test del comando productivo y el cwd real del launcher: **1550 passed, 48 skipped**, 35,26 s; los **7 tests Srv05** están incluidos. Imports con configuración productiva seleccionan pool lazy, estado PostgreSQL, Milvus lazy y alias/base LiteLLM; conectividad bloqueada durante ese test y credenciales sintéticas efímeras.
- Smoke Uvicorn real secuencial Srv01/Srv05 con cwd `SrvRestAstroLS_v1`, sockets loopback propios, memory/mock: health y OpenAPI idénticos; startup/shutdown ASGI y salida graceful confirmados. No equivale a PROD con DB/LLM reales.
- App factory/TestClient: rutas, CORS/debug/callbacks idénticos; 403 de contexto no autorizado; validación HTTP/health idéntica; tarea Flow real iniciada y cerrada con settings inertes; orden pool→scheduler→stop→close verificado con spies; errores heredados aislados.
- Launchers completos ejecutados desde copias temporales con comandos externos inertes: argv/cwd del backend Srv01 y secuencia build→Astro DEV confirmados. No se cargaron overrides privados ni se mataron listeners.
- `py_compile` Srv05; resolución imports desde cwd del launcher; `bash -n` de ambos scripts; `pnpm check`: **0 errors, 0 warnings, 7 hints**.
- Preflight local TCP: PostgreSQL 5432, Milvus 19530, LiteLLM 4000 disponibles; backend 7050 y frontend 3050 no estaban levantados. TCP no certifica auth/provider/crédito ni corpus.
- PostgreSQL real: SELECT 1, presencia de tablas, bindings/contextos/workspaces/organizaciones, settings Flow y resolución scope permitida/denegada; transacciones READ ONLY, statement timeout, conexiones cerradas.
- Automatización Flow DEV estaba **habilitada**, intervalo 5 s y mail intake activo. Por seguridad no se arrancó el stack productivo normal ni se ejecutó un ciclo Gmail real.
- Gates `lat check md/index/sections/code-refs`, `lat check` y `git diff --check`: PASS. LAT advierte ausencia de init/key para búsqueda semántica; no falla los gates. Se validaron además los párrafos iniciales de este informe.
- Los diffs tracked preexistentes se compararon por SHA-256 contra la captura anterior a escribir: byte-identical. No se escribieron paths no trackeados preexistentes. Sin commit/stage, cambios de rama, deploy ni reorganización de Fase 2.

Comando reproducible de regresión focalizada, sin activar los tests DB opt-in:

```bash
cd SrvRestAstroLS_v1/backend
AUTOMATION_DIAGNOSIS_REPOSITORY=memory TEAM360_AI_PROVIDER=mock \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --no-sync pytest -q \
  tests/test_flow_*.py tests/test_gmail_flow_normalization.py \
  tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py \
  tests/test_automation_diagnosis*.py tests/test_sales_diagnosis*.py \
  tests/test_structured_diagnosis.py tests/test_console_*.py \
  tests/test_messaging_gupshup_*.py tests/test_messaging_whatsapp_*.py \
  tests/test_messaging_evolution.py tests/test_module_registry.py \
  tests/test_srv05_*.py
```

## NOT_TESTED y riesgos pendientes

La cobertura no se extiende por inferencia a servicios, browsers o datos productivos. El wrapper preserva también deudas del baseline, que no corresponde arreglar durante esta fase.

- **NOT_TESTED** Gate 1 operativo mínimo Flow/Diagnosis y Gate 2 stack completo: no existen aquí modos `--module`; no se habilitaron ciclos que pueden enviar correo real ni se reemplazó el launcher.
- **NOT_TESTED** Gmail/DWD remoto y entrega real, Evolution/WhatsApp real, llamadas IA/embeddings facturables, retrieval/corpus Milvus real, persistencia de conversación multi-turn real con Srv05.
- **NOT_TESTED** Playwright Home/web/embed/Mamamia/Flow y CORS de assets servido en browser: servicios UX no estaban activos; levantar Astro incluye build compartido. Se verificaron contratos fuente/tests backend y tipos, no visual ni interacción real.
- **NOT_TESTED** PostgreSQL tests opt-in de escritura (48 skips del conjunto), DB remota, restart productivo, wheel instalado.
- Pool global inicializado por configuración Diagnosis y scheduler Flow arrancado siempre: separarlos necesitará un gate propio de lifecycle e independencia.
- Preflight normal Milvus/LiteLLM puede bloquear launcher para capacidades Flow que no los usan. Srv05 no agrega ese acoplamiento ni lo elimina silenciosamente.
- Single-worker scheduler; shell scripts que matan listeners; settings env capturados al importar; scopes de debug que pueden sobreescribir resolución; estado sync y errores silenciados; autorización Flow MVP y Console provisional.
- API CORS fijo y allowlist embed DB pueden divergir; CORS de assets es una tercera frontera. HMAC/origin no reemplazan login ni seguridad completa multi-tenant.
- Las reglas/contratos declarativos Arango y partner propios no deben confundirse con consumidores/corpus operacionales comprobados.

## Próxima fase recomendada

Antes de reorganizar configuración, acordar un gate operativo controlado con datos/bindings de test y sin envíos reales accidentales; después aislar bootstrap por capacidad mediante adaptadores pequeños.

1. Fijar baseline reproducible Srv01/Srv05 con PG, alias/corpus/scope reales y UI Home/web/embed/Mamamia, incluidos permisos y contexto negativo.
2. Modelar inventario de dependencias **por capacidad**: mandatory, optional y bindings; no arrancar todos los servicios por su disponibilidad global.
3. Desacoplar creación del pool de la ruta Diagnosis y lifecycle Flow, preservando un proceso y shutdown. Coordinar esa ventana GLOBAL separadamente.
4. Proponer resolución base/environment/module/service/binding sobre adapters existentes y proveedor de secretos sin moverlos masivamente.
5. Solo después diseñar launcher autónomo/`--module` y gates minimal/full stack. Esta fase termina sin esa segunda reorganización.

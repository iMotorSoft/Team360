# Telchi Data Lake Pre-SQL Profile V1

Perfil DEV de la capability fija sin optimizaciones, LLM, SAP ni envíos proactivos. Fecha: 2026-10-08. Incluye N=10 autónomos y una validación WhatsApp real posterior enviada por el usuario.

## Estado y alcance

El perfil autónomo y la validación WhatsApp real están completos. El bloqueo inicial de PostgreSQL se resolvió por arranque del usuario; el cleanup retiró el callback temporal al fallar la restauración del anterior.

```text
TEAM360_TELCHI_DATALAKE_PRE_SQL_PROFILE_V1=PASS
AUTONOMOUS_WORK=PASS
WHATSAPP_FINAL_VALIDATION=PASS
```

Rama `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. Contexto: ENTITY=TELCHI; DOMAIN=VENTAS; STAGE=INVESTIGATION; SOURCE=DATA_LAKE/Foundation CURRENT read-only; OUTPUT=ANALYSIS/REPORT. La instrumentación reversible de la capacidad existente no es promoción ni cambio de arquitectura.

No stage/commit/reset/stash/clean. Estado inicial completo: `initial-status.txt`. Los originales de los archivos editados están en `before/`, incluidos cambios preexistentes; `task-only.patch` separa las adiciones de esta tarea del diff contra HEAD. No se tocaron GLOBAL, frontend, Flow, Vera, dependencias ni infraestructura compartida.

## Hallazgo central y motor efectivo

El motor analítico real es DuckDB, no PostgreSQL. PostgreSQL respalda el catálogo DuckLake y la persistencia Messaging; los datos analíticos provienen de Parquet Foundation pinned.

El SQL fijo hace JOIN de sales_document y sales_line, filtro temporal, dos conversiones a DECIMAL(38,10), GROUP BY y TOP 10. Usa snapshot **1408** y Foundation **foundation_afd08d9eca6a725be53cdc3f9d5709c9**. El hash de query, SQL efectivo y resultados de las veinte muestras coincide con el baseline WhatsApp real previo: `offline-verification.json`.

La medición anterior `SQL ≈2362 ms` envolvía exactamente `connection.execute(sql, params).fetchall()`, dentro de `execute_fixed_query`. **No** incluía spawn, attachment, Foundation.resolve_on ni close. **Sí** incluía binding/planificación/optimización/ejecución DuckDB, posible trabajo de catálogo durante binding, materialización interna del motor y conversión de fetch Python. La conversión a dict/str de las diez filas ocurre después del timestamp final. No se puede atribuir ese intervalo a PostgreSQL puro.

## Camino real y puntos de instrumentación

Las duraciones finas usan perf_counter_ns; los timestamps epoch anteriores se conservan solamente para compatibilidad y correlación, no para las nuevas duraciones.

| Orden | Archivo / función | Dependencia y costo local p50 |
|---|---|---|
| P0 | messaging/webhooks/evolution_whatsapp.py: receive → _receive | Entrada handler; Trace empieza antes de t0 anterior. No mide llegada TCP anterior al handler. |
| P1 | mismo: _receive | Settings/config, hmac, body JSON, normalize_events; más allowlist posterior: 0.300 ms combinados. |
| P2 | mismo: build_service | MessagingRepository.binding con pool PostgreSQL; workspace/channel/provider: 3.073 ms. |
| P3 | mismo: build_service / TelchiSqlAdapter.__init__ | Tenant proviene de configuración DEV explícita, no de resolver DB separado. Capability fija: 0.007 ms. |
| P4 | messaging/service.py: process | Allowlist antes de claim. Claim/upsert conversation + inbound commit: 14.660 ms; trigger/tenant: 0.004 ms. |
| P5 | mismo: process / record_sql_gate | Persistencia de intención SQL previa al worker: 11.067 ms. |
| P6 | telchi/datalake/messaging_sales_query.py: query_fixed_sales → _query_in_worker | Lock runtime no-queue; create_subprocess_exec. Spawn retorno: 1.151 ms. |
| P7 | mismo: _worker | Entry tras intérprete/imports de módulo: 85.669 ms desde inicio parent, incluyendo spawn. No existe handshake READY. |
| P8 | mismo: execute_fixed_query | Imports capability + configuración + import duckdb: 68.849 ms. |
| P9 | telchi/datalake/ducklake.py: session | duckdb.connect: 11.892 ms; LOAD ducklake/postgres: 106.910 ms. |
| P10 | mismo: session | ATTACH READ_ONLY + adquisición inicial de catálogo: 38.345 ms; presupuesto y verificación readonly: 1.909 ms. |
| P11 | telchi/datalake/foundation_reader.py: resolve_on | Resolve/validate publicación, commit snapshot, componentes/reference: 1386.003 ms. |
| P12 | messaging_sales_query.py: execute_fixed_query | Construcción de relaciones pinned + template: 0.015 ms; no prepared statements. |
| P13–P14 | mismo: connection.execute | DuckDB execute incluyendo preparación interna: 2336.129 ms. |
| P15 | mismo: cursor.fetchall | Fetch de diez filas a Python: 1.249 ms. |
| P16 | mismo: execute_fixed_query / ducklake.session | Dict/str: 0.017 ms; hash: 0.074 ms; close: 9.807 ms. |
| P17 | _query_in_worker / TelchiSqlAdapter.execute | JSON/stdout IPC y salida/decode residual: 74.136 ms; formatting: 0.032 ms. |
| P18 | messaging/service.py: process | SQL result persistence: 29.781 ms; outbound intent commit: 10.942 ms. |
| P19 | mismo: dispatch | pre_send monotónico capturado inmediatamente antes del sender; no transporte externo en N=10 local. |

Paths de la tabla son relativos a `SrvRestAstroLS_v1/backend/modules/`. Settings/auth suceden antes de binding; la allowlist del remitente está después de build_service y antes de cualquier claim. El tenant se configura al construir el servicio y se verifica al resolver trigger: no inventamos dos consultas tenant independientes.

El trace JSON contiene schema, clock, total_ms y spans `{label,start_ms,end_ms,duration_ms}` relativos a cada origen. El worker exporta además parent.spawn_ms, worker_entry_ms, total_ms, ipc_exit_decode_residual_ms y worker_pid. El handler conserva sus spans en `timings.pre_sql_profile`, y el resultado worker en `sql_gate.result.profile`. Los contextos async se aíslan mediante ContextVar. El bridge Messaging es lazy: bootstrap normal no importa Telchi.

Los spans son anidados: connector_configuration incluye private_config_read y foundation_resolution incluye seis subspans. **No sumarlos doble**. Linux permite comparar perf_counter_ns entre procesos del mismo host; el cálculo derivado usa worker_entry como anchor. El micro-gap lock/call y código no cubierto queda explícitamente en residual, no se rellena con puntos ficticios.

## Tabla principal

Los percentiles son interpolación lineal sobre N=10. Los porcentajes usan sumas de tiempos de las mismas diez muestras HTTP locales / suma de pre_send, no restas de medianas independientes.

| Componente | p50 ms | p95 ms | % pre-send | Clasificación |
|---|---:|---:|---:|---|
| Config/auth/body/normalization/allowlist | 0.300 | 0.416 | 0.01 | REQUIRED |
| Binding workspace/channel | 3.073 | 4.172 | 0.07 | REQUIRED |
| Conversation/claim/commit | 14.660 | 23.661 | 0.40 | REQUIRED |
| Trigger/tenant/capability | 0.013 | 0.017 | 0.00 | REQUIRED |
| SQL intent persistence | 11.067 | 11.624 | 0.26 | REQUIRED |
| Worker entry (incluye spawn) | 85.669 | 121.826 | 2.08 | ARCHITECTURAL / potentially AVOIDABLE |
| Imports/configuration | 68.849 | 97.961 | 1.74 | ARCHITECTURAL / potentially AVOIDABLE |
| DuckDB connection | 11.892 | 14.545 | 0.30 | ARCHITECTURAL |
| Extension LOAD | 106.910 | 138.692 | 2.66 | ARCHITECTURAL / potentially AVOIDABLE |
| Attachment + PostgreSQL catalog session | 38.345 | 51.111 | 0.95 | ARCHITECTURAL / REQUIRED |
| Query budget + readonly check | 1.909 | 2.238 | 0.05 | REQUIRED |
| Foundation resolution/validation | 1386.003 | 1484.224 | 33.05 | REQUIRED / ARCHITECTURAL |
| Query preparation | 0.015 | 0.019 | 0.00 | REQUIRED |
| DuckDB execute (incluye planning) | 2336.129 | 2373.605 | 55.26 | DATABASE / potentially AVOIDABLE cast work |
| Fetch | 1.249 | 1.621 | 0.03 | REQUIRED |
| Materialization/hash | 0.092 | 0.157 | 0.00 | REQUIRED |
| Attachment/connection close | 9.807 | 11.795 | 0.23 | REQUIRED / ARCHITECTURAL |
| IPC/exit/decode residual | 74.136 | 83.179 | 1.78 | ARCHITECTURAL / UNKNOWN internal split |
| Formatting/result + outbound persistence | 40.753 | 89.953 | 1.11 | REQUIRED / INSTRUMENTATION_ARTIFACT JSON adicional |
| Orchestration/unspanned paired residual | 1.146 | 1.442 | 0.03 | UNKNOWN / INSTRUMENTATION_ARTIFACT |

SQL planning PostgreSQL, execution PostgreSQL analítico e índices/buffers PostgreSQL: **N/A** para esta query. Planning DuckDB se mide en EXPLAIN detallado N=1, no existe distribución N=10 separada ni se inventa p50/p95. Adquisición PostgreSQL y transaction setup internos a ATTACH no tienen API separable en este connector; se conservan juntos, no como cero.

## Descomposición Foundation

El costo pre-SQL principal está en resolución coherente y fail-closed de Foundation, no en crear el attachment.

| Subetapa resolve_on | p50 ms | p95 ms | Qué incluye |
|---|---:|---:|---|
| current_count | 368.542 | 459.199 | Primer SELECT parametrizado de estado CURRENT; binding/catálogo/scan/fetch, potencial inicialización lazy del driver Python no separada. |
| current metadata | 200.267 | 211.394 | list_publications, pointer count, pointer, current publication y transformación metadata. |
| publication get | 27.341 | 28.454 | SELECT parametrizado y transformación publicación. |
| manifest validation | 0.010 | 0.010 | Validación in-memory; no SQL. |
| commit snapshot resolution | 676.550 | 689.504 | Lista snapshots, búsqueda binaria, dos SELECTs por predicate, revalidación del primer CURRENT. |
| component verification | 111.449 | 115.849 | Cuatro publicaciones sales/credit_memo/oinm/oitw en snapshot, estado y domain binding. |

Reference immutable-directory check y construcción FoundationAccess permanecen dentro del span padre; el pequeño resto no se presenta como una DB llamada adicional. Estos tiempos incluyen DuckDB sobre las tablas ops y trabajo de catálogo, **no** son duración PostgreSQL server puro. Validar coherencia/pinning es REQUIRED; ejecutar toda esa resolución nuevamente por llamada es ARCHITECTURAL y su costo no demuestra que cada milisegundo sea inevitable.

## Worker, attachment y DB/session

Cada llamada mantiene aislamiento por proceso, consume Foundation read-only y destruye su conexión y worker antes de devolver el resultado.

- Quién crea el worker: _query_in_worker, invocado por query_fixed_sales. Es un subprocess Python `sys.executable -m modules.telchi.datalake.messaging_sales_query`, no thread/pool/daemon. Cada una de las veinte muestras registra su PID propio.
- Spawn API p50/p95: **1.151 / 2.990 ms**. Entry incluyendo spawn e imports de intérprete/módulo: **85.669 / 121.826 ms**. No son dos componentes aditivos.
- Ready real no tiene mensaje IPC. Se mide entry y milestones: attachment terminado ≈**308.548 ms** desde inicio worker parent; readonly verificado ≈310.407 ms; Foundation resuelta ≈1697.301 ms (medianas locales). Son milestones acumulados, no costos adicionales.
- IPC: un JSON por stdout; communicate espera EOF y salida. Residual IPC/JSON/exit/decode ≈74 ms no separable con el protocolo actual; no fingimos que todo es IPC puro.
- Fin: close DuckDB/attachment en finally; worker imprime resultado y termina; communicate lo espera. Timeout/cancel mata y espera exclusivamente el child creado. Lock rechaza superposición dentro del runtime sin queue.
- Razón explícita en código: PGPASSWORD es process-global; aislar evita carreras de modificación/restauración del entorno y hace que SQL no sobreviva timeout/cancel. Reutilización futura sería técnicamente posible pero exigiría mantener aislamiento por tenant, lifecycle/cancel, restauración de entorno y pinning por petición. No se implementó ni se recomienda aquí como prioridad.
- Attachment real: no hay objeto Foundation Attachment aparte. session crea una conexión DuckDB in-memory, carga extensiones y ejecuta ATTACH alias telchi READ_ONLY usando configuración privada. Config read ≈0.197 ms, configuración completa ≈0.470 ms; conexión DuckDB ≈11.892 ms; LOADs ≈106.910 ms; ATTACH+catálogo ≈38.345 ms; readonly check ≈0.708 ms; close ≈9.807 ms.
- El attachment se recrea por cada sesión/request porque el worker/conexión son efímeros. READ_ONLY y pinning son requisitos; recrearlo no está documentado como requisito independiente obligatorio: es consecuencia de esta frontera y una limitación actual, potencialmente evitable con un gate posterior.
- No hay acquire nuevo de psycopg ni read-only transaction setup explícito para la query analítica. La sesión PostgreSQL del catálogo la gestiona la extensión nativa dentro de ATTACH y consultas posteriores; handshake/auth/BEGIN individual no se exponen y no se instrumentaron ficticiamente. Messaging sí usa el pool psycopg preexistente; sus transacciones se midieron incluyendo acquire y commit, sin crear pool nuevo en runtime.

## EXPLAIN ANALYZE efectivo

Se ejecutó EXPLAIN ANALYZE en DuckDB, con exactamente los parámetros, relaciones Foundation y presupuesto de la query real, en attachment READ_ONLY; no se accedió a SAP.

`explain-analyze.json` conserva SQL efectivo, parámetros, pins y plan JSON completo. `explain-detailed.json` añade profiling_mode=detailed sólo a la sesión diagnóstica. PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` sobre esta query **no es compatible**: la query tiene DuckLake snapshot syntax, `?` y Parquet relations no presentes como tablas analíticas PostgreSQL. Explicar un SELECT catálogo distinto no respondería esta pregunta.

Plan detallado N=1:

- Latencia EXPLAIN: **2455.721 ms**; CPU acumulada operadores: **4456.622 ms**, con threads=2. CPU por operadores no es wall time ni se suma a la latencia.
- Planner/binding: **3.251 ms**, all_optimizers: **5.508 ms**, physical planner: **0.186 ms**. Submétricas del planner se solapan: no sumar planner_binding al planner. Estos costos diagnósticos no se restan del N=10 como si fueran pareados.
- Nodo dominante PROJECTION con `CAST(quantity AS DECIMAL(38,10))` y `CAST(line_total AS DECIMAL(38,10))`: **4295.719 ms operator CPU**, ≈96.4% del CPU de operadores, **693711 filas**. No se puede separar el costo de cada cast individual dentro del nodo.
- HASH_JOIN: **65.161 ms CPU**, 693711 filas; HASH_GROUP_BY: **28.520 ms CPU**, 6538 grupos; TOP_N: **0.292 ms CPU**, diez filas.
- DUCKLAKE_SCAN sales_line: **54.535 ms CPU**, 693910 filas emitidas; sales_document: **12.310 ms CPU**, 320398 emitidas, con filtro temporal. Un archivo por relación. operator_rows_scanned es contador del profiler paralelo, no recuento autoritativo de filas únicas.
- Plan inicial: 41468 total_bytes_read, peak buffer memory ≈81 MB, peak temp size 0 y bytes_written 0. No hubo spill. Estos contadores no representan shared buffers PostgreSQL ni todo el tráfico de filesystem.
- No existen nodos PostgreSQL Seq Scan/Index Scan en el plan: son DUCKLAKE_SCAN, HASH_JOIN, HASH_GROUP_BY y TOP_N. PostgreSQL buffers/cache hits, índice y execution/planning server de las consultas internas de catálogo: **UNKNOWN / not exposed**, no cero.

## N=10, cold/warm y comparación

Se conservaron los veinte resultados y spans individuales; las muestras son secuenciales y no hubo reinicios de servicios entre consultas.

| Serie | Pre-SQL p50/p95 ms | Execute p50/p95 ms | Total p50/p95 ms |
|---|---:|---:|---:|
| Direct capability N=10, sin Messaging | 1761.564 / 2024.570 | 2400.064 / 2798.439 | 4255.371 / 4875.955 |
| HTTP ASGI Messaging N=10, sin transporte externo | 1727.396 / 1934.370 | 2336.129 / 2373.605 | 4207.774 / 4396.423 hasta sender |
| WhatsApp SQL previo N=10 | 1835.399 / 1883.399 | 2362.236 / 2454.166 execute+fetch | 4375.924 / 4504.164 hasta sender |
| WhatsApp fixed previo | N/A | N/A | 56.37 / 146.04 hasta sender |

Post-SQL local (fetch completo → send) p50/p95=**126.673/173.576 ms**. El intervalo histórico llamado formatting/persistencia (138.912/228.543 ms) incluía también materialización, close y IPC/worker exit; no era sólo formatter.

Total observable histórico: SQL 6908.797/7338.677 ms; fixed 2516.86/2972.98 ms p50/p95. Son referencia, **no muestras pareadas** con este perfil. No se calcula ahorro por resta entre series. El total directo llega hasta worker result decode; el local llega hasta sender entry. HTTP es ASGI in-process reproducible, no mide socket/HTTP network overhead ni delivery; hubo PostgreSQL/repositories reales, workspace temporal y port sender de test. No se fabricaron delivered/read para los N=10.

`direct.json`, `messaging-local.json` conservan las diez muestras por serie. `direct-summary.json`, `messaging-local-summary.json` conservan min/mean/p50/p90/p95/max por span y milestones; `analysis.json` conserva las mismas estadísticas para pre-SQL/total, individuales, warm #2–#10 y tabla exclusiva.

Direct #1 total=4936.468 ms; #2–#10 p50=4151.431 ms. Local #1=4190.375 ms; #2–#10 p50=4210.367 ms. **No clasificar #1 como cold puro**: el host ya había usado Foundation, las páginas OS/PG/Parquet no se enfriaron, parent modules ya estaban importados, PostgreSQL preflight ejecutó SELECT 1. El runner no ejecutó la capability antes de direct #1; EXPLAIN y direct N=10 ocurrieron antes del local. Cada worker vuelve a importar/cargar/attach. La variación de las primeras muestras directas no prueba warm-up causal; el local no muestra mejora warm significativa.

## Respuestas explícitas

Las conclusiones distinguen lo medido en esta corrida de atribuciones retrospectivas no observables en los mensajes anteriores.

1. **¿Dónde están los ~1.84 s pre-SQL?** En el camino worker→imports/connect/LOAD/ATTACH→Foundation fail-closed, más claims/intención Messaging. Ahora pre-SQL local p50=1727.396 ms; Foundation=1386.003 ms domina (snapshot≈676.550, current_count≈368.542, metadata≈200.267, verification≈111.449). No asignamos retroactivamente los 1835 ms históricos a valores nuevos exactos: el trace identifica el camino y mide nuevas muestras.
2. **¿Los ~2.36 s son PostgreSQL puro?** No. Eran DuckDB execute+fetch; ahora execute≈2336.129 ms y fetch≈1.249 ms. Incluye preparación interna y posible metadata del catálogo, no attachment/Foundation setup.
3. **¿Worker?** Spawn API≈1.151 ms; entry acumulado≈85.669 ms; imports/config/LOADs son adicionales. El fin IPC/exit/decode≈74.136 ms. No confundir spawn con disponibilidad analítica.
4. **¿Attachment?** ATTACH+sesión catálogo≈38.345 ms; LOADs≈106.910 ms y close≈9.807 ms son separados. No cuesta por sí solo ~1.84 s.
5. **¿DB/session?** DuckDB connect≈11.892 ms; adquisición catálogo PostgreSQL incluida en ATTACH≈38.345 ms; auth/BEGIN internos no separables. Messaging acquire+SQL+commit está en sus spans persistencia.
6. **¿PostgreSQL realmente?** No ejecuta la query analítica; duración interna catálogo UNKNOWN. El motor efectivo DuckDB ejecuta≈2336 ms; EXPLAIN confirma ~2456 ms diagnósticos y planificación de pocos ms, con CPU dominante en casts.
7. **¿Fetch/materialization?** Fetch Python≈1.249 ms; dict/str≈0.017 ms; hash≈0.074 ms. Materialización interna DuckDB no se separa de execute/operadores; no atribuir todo execute a CPU SQL PostgreSQL.
8. **¿Inevitable por seguridad?** Allowlist/auth, durable claim/intent, readonly enforcement, coherencia manifest/componentes/pin CURRENT y cleanup/cancel. Aislamiento actual de PGPASSWORD es deliberado; no demuestra que toda repetición o todo su tiempo sea inevitable.
9. **¿Evitable?** El costo de conversiones idénticas de fuente a DECIMAL cada consulta parece movible a publicación tipada exacta; repetición de setup/resolución es arquitectónica, no validación falsa. Ningún cambio aplicado.
10. **¿Mayor cuello real?** La ejecución DuckDB y, dentro de ella, la proyección de dos casts sobre 693711 filas; segundo bloque es Foundation.resolve_on. No WhatsApp, spawn API, attachment, fetch ni formatter.

## Recomendación única

La recomendación es una hipótesis para otro gate y no una decisión adoptada ni implementación de este perfil.

```text
PRIORITY_OPTIMIZATION:
Publicar en un candidate Foundation columnas numéricas tipadas exactas
DECIMAL(38,10) para quantity/line_total y consumirlas sin repetir los dos
casts por consulta, conservando columnas fuente, lineage, pins y semántica.

Expected target:
Recuperar orden de 1–2 s por consulta analítica; objetivo SQL <1 s.
Hipótesis, no ahorro demostrado: el nodo casts/projection domina ~96% del
CPU con dos threads; su CPU NO equivale directamente a tiempo wall ahorrable.

Risk:
MEDIUM
```

Requiere gold/parity exacto en rounding, NULL, overflow, agregación, ordering y resultados; candidate/promotion explícitos y rollback al reader/query actuales. No crear este candidate ni cambiar SQL, schemas, índices, datos o CURRENT durante este gate. El riesgo se controla con publicación candidata aislada y validación exacta; no se promete un speedup antes de medirlo.

## Validaciones y límites

Se ejecutaron checks focalizados y PostgreSQL real; no se lanzaron suites globales, Milvus, LiteLLM ni proveedores LLM.

- Tests finales focalizados Telchi reader/query + Messaging service/adapter/benchmark/session/Evolution/bootstrap: **112 PASS, 1 SKIP** opt-in PG launcher. `tests-final.txt` conserva comando/resultados; el launcher isolation incluye checks de importación normal sin Telchi.
- PostgreSQL opt-in y Foundation real, instrumentación enabled: **3 PASS**; `tests-postgres-final.txt`. Los tres tests cubren persistence/dedup/errors/timeout/early callbacks/recovery y capability real. `tests-postgres.txt` conserva un fallo inicial de compatibilidad: metadata profiling se agregaba también a fixed responders y el test ordenaba todos los valores timings. Se corrigió limitando esa metadata a tenant Telchi + hola; rerun y final pasan. No se ocultó el fallo ni se cambió el test.
- Recheck final tras los últimos cambios del profiler/continuación: **10 PASS**, `tests-profile-final.txt`. Nuevos tests: monotonic/nested spans, ContextVar isolation/reset, continuation rejects missing transport status/Foundation drift y preflight fallido no arranca procesos ni guarda secretos. Tests sintéticos no equivalen a WhatsApp.
- Offline evidence schema/monotonic spans/pins/query/result igual al WhatsApp previo: **PASS**, `offline-verification.json`.
- `uv run --no-sync python -m modules.messaging.pre_sql_profile_session --check`: **LOCAL_PREREQUISITES=PASS**. No arrancó transporte ni validó credenciales externas; la continuación valida esas condiciones antes de READY.
- AST/syntax de los archivos de esta tarea, `git diff --check`, revisión task-only diff y `lat check md/index/sections/code-refs/check`: **PASS**, ver `static-checks.json`, `lat-checks.txt` y `review.json`. Warnings LAT: versión init/semantic key no configuradas; no se habilitó LLM.
- Instrumentación opt-in `TEAM360_TELCHI_PRE_SQL_PROFILE=1`, removable y sin SQL adicional en ruta funcional. Añade spans y payload JSON de auditoría; su costo de serialization/persistencia está incluido, no se supone impacto exactamente cero. El bridge lazy se corrigió después del N=10 para mantener aislamiento import del bootstrap normal; no cambia etiquetas/clock/SQL/camino medido y pasó integración real posterior.

## Cleanup y recursos

Se mantuvo capacidad compartida estable y se cerraron los recursos de esta tarea, sin tocar procesos preexistentes.

Preflight: ocho cores, load≈1.34, MemAvailable≈6299 MB, swap≈4 MB sin crecimiento; durante el perfil load≈1.70, MemAvailable≈6045 MB, sin swap-in/out. Concurrencia una capability; threads DuckDB=2, memoria query=512 MB, temp=0B; no se alteraron settings del servidor. Milvus/LiteLLM ya corrían: no fueron usados, iniciados ni detenidos.

```text
HOST_PREFLIGHT=SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 query / 2 DuckDB threads
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

Runner cerró pools, eliminó únicamente fixtures Messaging de su workspace temporal y reaped veinte subprocesses. No se arrancaron backend/tunnel/Evolution durante el profiling autónomo. Tests cerraron sus listeners/procesos propios. Evolution conserva estado original exited; PostgreSQL e infraestructura compartida quedaron intactos. `runner-cleanup.json` y `cleanup.json` conservan la comprobación final.

## Intento de continuación humana

La sesión `human-20261008T171405117511` falló antes de READY y no recibió una muestra WhatsApp; no se reinició infraestructura compartida ni se repitió N=10.

Evolution terminó con exit code 1 y Prisma **P1001**, indicando conectividad fallida hacia su PostgreSQL interno. El preflight de challenge público falló porque el origen Evolution ya no estaba disponible. No se modificó la suscripción Meta ni se levantó el backend. La causa específica de indisponibilidad DB no se presume resuelta.

`transport-blocker.json` conserva la clasificación; `continuation.json` confirma tunnel reaped y transporte propio detenido. Se sanitizaron query strings del log propio y se corrigió la persistencia del log cloudflared para redactarlas antes de escritura: sus errores pueden ecoar el verify token del challenge. Regresión y sesión: **6 PASS**, `tests.txt`. Cambios adicionales sólo en pre_sql_profile_session.py y su test; no cambian el perfil SQL ni corrigen artificialmente el entorno.

Pendiente en aquel intento: restablecer DB y volver a abrir la sesión. El usuario arrancó posteriormente PostgreSQL y completó el hola real, como documenta el cierre siguiente.

## Cierre WhatsApp real

El usuario envió un hola tras READY en `human-20261008T172521188606`; se confirmó por lectura PostgreSQL independiente y sin repetir N=10 ni pedir otro mensaje.

`session/evidence.json` conserva N=1 real, callbacks delivered/read, spans worker y handler; `final-verification.json` verifica misma capability/query/pins/resultados que N=10 y baseline histórico. La sesión también comprobó deduplicación sin segundo envío y restauración del webhook local.

| Medición real N=1 | ms |
|---|---:|
| Pre-SQL observable | 2326.870 |
| Foundation resolution | 1393.451 |
| Worker spawn API / entry acumulado | 0.886 / 89.516 |
| Attachment + sesión catálogo | 57.251 |
| DuckDB connect | 15.514 |
| DuckDB execute / fetch | 2261.377 / 1.241 |
| Dict materialization | 0.019 |
| Post-SQL hasta send | 135.503 |
| Team360 hasta send | 4725.028 |
| Total observable hasta delivered callback | 8111.136 |

La muestra tuvo claim/conversation+commit=470.561 ms y SQL intent persistence=77.668 ms. PostgreSQL compartido acababa de arrancarse por el usuario; esto no establece causalidad ni representa una nueva distribución de latencia. No restar esta muestra de medianas históricas para inferir ahorro o regresión.

**Cleanup final:** backend, worker, launcher y tunnel propios cerrados; Evolution propio detenido; PostgreSQL del usuario sigue running. La restauración del callback Meta anterior falló. Se retiró solamente la suscripción temporal, tras verificar URL exacta de nuestro tunnel y field messages único; DELETE HTTP 200 y GET posterior confirmaron ausencia. `subscription-cleanup.json` conserva la diferencia: **el callback anterior no se restauró y no queda suscripción Meta Team360 activa**. La próxima sesión deberá configurarla de nuevo. El `continuation.json` original conserva BLOCKED de ese fallo; `final-verification.json` registra la resolución y cierre PASS sin ocultarlo.

No hay pendientes del gate ni optimizaciones implementadas. Riesgo operativo residual: ingress DEV cerrado intencionalmente, no runtime WhatsApp permanente. N=1 no sustituye los N=10 del perfil ni un nuevo gate de latencia.

## Comando para futuras sesiones

No hace falta otra sesión para este gate. El comando conserva el mecanismo count=1 con timeout y no repite N=10; una nueva ejecución crea evidencia separada y configura nuevamente ingress DEV.

1. Ejecutar desde la raíz Team360:

```bash
(cd SrvRestAstroLS_v1/backend && uv run --no-sync python -m modules.messaging.pre_sql_profile_session)
```

2. Esperar `READY`.
3. Enviar `hola` desde el WhatsApp autorizado.
4. Esperar `TEAM360_TELCHI_DATALAKE_PRE_SQL_PROFILE_V1=PASS`.

La sesión espera como máximo 300 s una vez iniciada, más preflight/cleanup acotados; no repite N=10 ni EXPLAIN. Ejecuta una consulta preflight de la sesión existente y una consulta del hola. Arranca el contenedor existente sólo si estaba detenido y un tunnel propio; usa backend-dev.sh. Rechaza backend port ocupado, local webhook activo o suscripción con fields ajenos, restaura suscripción/webhook y detiene solamente transporte iniciado por ella. Guarda evidencia nueva en `human-<timestamp>/`, sin sobrescribir las muestras autónomas. Si Foundation/query/result cambian, no declara PASS con perfil viejo. Timeout conserva WAITING_HUMAN, problemas técnicos/restauración producen BLOCKED. El primer intento terminó antes de READY; el segundo capturó el hola real y cerró sus recursos, con el cleanup alternativo documentado arriba.

## Reproducibilidad y archivos

Los runners viven en investigation y no son dependencias del runtime productivo; la evidencia permanece en este directorio, no en Data Root.

Desde backend, regenerar únicamente estadísticas y verificar evidencia sin consultas:

```bash
uv run --no-sync python -m modules.telchi.investigation.validation.pre_sql_profile_v1.summarize
uv run --no-sync python -m modules.telchi.investigation.validation.pre_sql_profile_v1.validate_evidence
```

Para una nueva medición intencional (no necesaria para continuación), `uv run --no-sync python -m modules.telchi.investigation.validation.pre_sql_profile_v1.run_profile` ejecuta N=10 directo, dos EXPLAIN y N=10 HTTP local. Ese runner escribe los archivos de medida de este directorio: conservar snapshot si se desea otra corrida; no lo usa la continuación humana.

Modificados por esta tarea, todos relativos a backend:

- modules/telchi/datalake/ducklake.py (tracked, antes limpio).
- modules/telchi/datalake/foundation_reader.py (tracked, ya modificado; se preservaron sus cambios).
- modules/telchi/datalake/messaging_sales_query.py (ya untracked antes).
- modules/messaging/service.py, telchi_sql.py, telchi_sql_benchmark.py y webhooks/evolution_whatsapp.py (ya untracked antes).

Nuevos de esta tarea:

- modules/telchi/datalake/query_profile.py.
- modules/messaging/profile_trace.py y pre_sql_profile_session.py.
- modules/telchi/investigation/validation/pre_sql_profile_v1/{run_profile,summarize,validate_evidence}.py.
- tests/test_messaging_pre_sql_profile.py.
- Este directorio de reporte y sus artefactos, inventariados en `task-files.json`.

`telchi_sql_session.py` fue leído/snapshot pero **no modificado**. Los demás paths preexistentes de `initial-status.txt` no se editaron. No se actualizó estado GLOBAL/LAT ni arquitectura declarada. Impacto transversal limitado a metadata opt-in del camino Telchi Messaging y lifecycle DEV documentado; gate cerrado. Una eventual optimización requiere tarea y promoción propias.

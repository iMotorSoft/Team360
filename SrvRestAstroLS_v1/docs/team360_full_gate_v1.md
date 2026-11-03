# Full Team360 Gate V1

Primera medición de convivencia del baseline Srv05 en DEV, ejecutada el 2026-10-07. Structural PASS; Operational DEGRADED. No es autorización de promoción ni cierre operacional completo.

## Composición vigente tras aislamiento Evolution

La medición del 11/10 sustituye sólo el contrato de composición vigente; las corridas fechadas siguientes se preservan. Srv05 OFF Structural PASS, Operational DEGRADED; no promoción.

- [Contrato de aislamiento](team360_srv05_evolution_isolation.md): Srv01 27 operaciones; Srv05 OFF 27, ON fixture 28. Única excepción al baseline previo: retirar Evolution DEV de Srv01.
- No identidad app/factory entre entrypoints: comparten implementación base, no activación de extensiones. Pool/scheduler legacy conservados; ON agrega validación read-only antes del scheduler.
- El harness mide Srv05 OFF explícitamente, Evolution → 404. ON coverage/IDs/refs y fail-closed se validan en tests de aislamiento, no se mezclan con probes operacionales OFF.
- [Nueva corrida](../../data/reports/team360-srv05-evolution-isolation/20261011T133928Z/full-gate-r2/report.json): todas las suites PASS; PostgreSQL/Milvus/LiteLLM READY en alcance de probes, no certificación productiva. Sin delivery ni browser nuevo.
- Evolución principal prevista: Evolution; Gupshup legacy/fallback conservado, deshabilitado como transporte en esta medición y no requisito de promotion readiness por disponibilidad/ingress/outbound.

## Scope y autoridad

Full significa todas las operaciones realmente compuestas por Srv05/Srv01, no todos los directorios del repo ni el perfil declarativo `full`.

- Rama: `feature/console-backend-core`; HEAD observado: `09d2ec715a31bb88574d734eacb9f437f008624e` más worktree preexistente autorizado.
- Srv05 reexporta `app` y `create_app` de Srv01: una implementación de servidor, sin nuevo bootstrap.
- Autoridades: [AGENTS](../../AGENTS.md), [GLOBAL](status_actual.md), [ownership](../../lat.md/team360-global-orchestration.md), [preflight](../../lat.md/service-preflight-methodology.md).
- Ventana GLOBAL exclusiva únicamente para construir/ejecutar este gate. Runtime, configuración, frontend y cambios ajenos preservados.
- `resolve_runtime_profile("full") != Full Team360 Gate`.
- No se modificó producción, no se reemplazó Srv01 y no se administró infraestructura.

## Inventario vigente

La construcción inspeccionada contiene 28 operaciones de negocio/core en 26 paths, además de OPTIONS y las superficies OpenAPI generadas por Litestar.

| Superficie | Clasificación | Evidencia / límite |
| --- | --- | --- |
| Flow | MOUNTED | 10 operaciones; configuración, operational settings, Directorio, scheduler/status, clear y resend |
| Diagnosis público/embed | MOUNTED | 7 operaciones `/api/diagnosis/*`; contratos HMAC y contexto backend |
| Automation diagnosis | MOUNTED | 3 operaciones start/answer/classify |
| Console/Auth | MOUNTED | bootstrap y me; PASETO separado de HMAC embed |
| Messaging/Gupshup | MOUNTED | webhook directo en Srv01, bridge explícito hacia Flow |
| Messaging/Evolution | MOUNTED | webhook en registry; consumidor DEV deshabilitado por defecto, responde 503 sin configuración |
| Diagnosis product adapter | REGISTERED_BUT_DISABLED | ruta físicamente montada, activación explícita; no confundir con Vera pública |
| Diagnosis dev adapter | DEV_ONLY | ruta físicamente montada; no es aislamiento por proceso ni eliminación en PROD |
| Health | MOUNTED | `/health` y `/api/health` |
| OpenAPI | MOUNTED | `/schema/*`, generadas por Litestar; no son módulos adicionales |
| Telchi | NOT_IN_GLOBAL_SERVER | sin handler Telchi en constructor/registry/rutas; no inventar API Foundation |

El registry actual monta Flow y Messaging. Diagnosis, Console, health y Gupshup se agregan directamente en Srv01. El inventario completo y ownership por handler está en [routes.json](../../data/reports/team360-full-gate/final-run/routes.json).

Telchi se examinó como `ENTITY=TELCHI`, alcance transversal de integración, `STAGE=INVESTIGATION`, fuente software/autoridades, output inventario. [CONTEXT](../backend/modules/telchi/CONTEXT.md) prevalece: Foundation/Data Lake e investigación no son automáticamente APIs. No se consultó SAP/HANA ni se alteró CURRENT.

Knowledge, seguridad y DB son dependencias internas, no módulos HTTP independientes aquí. Los launchers `messaging-only`, scripts, labs, Foundation opt-in y artefactos investigativos quedan fuera del servidor global medido.

## Ejecución reproducible

Un comando compone workers frescos, probes read-only y suites existentes, con resultados JSON por subgate y códigos de salida no ambiguos.

```bash
cd SrvRestAstroLS_v1/backend
uv run python scripts/validate_team360_full_stack.py
```

- Harness: [validate_team360_full_stack.py](../backend/scripts/validate_team360_full_stack.py).
- SQL acotado y read-only: [repository del gate](../backend/scripts/team360_full_gate_repository.py).
- Regresiones propias: [tests](../backend/tests/test_team360_full_gate.py).
- Directorio nuevo por corrida bajo `data/reports/team360-full-gate/`; `--output` debe señalar un directorio inexistente.
- Exit 0 reservado a Full PASS; 1 a fallo estructural; 2 a degradación operacional; 3 a recurso bloqueado antes del trabajo.
- El alcance read-only V1 conserva Operational DEGRADED: no certifica conversación/persistencia completa ni auditoría del fallback interno del proxy. No transforma readiness de servicios en Full PASS.
- Las suites opt-in externas no se habilitan; no hay writes PostgreSQL deliberados, migraciones ni mensajes enviados.
- El worker estructural usa memory/mock exclusivamente para construcción sin I/O; no demuestra readiness pública.
- El operacional usa configuración pública equivalente local: postgres, Milvus y LiteLLM Chat Completions. Respeta valores existentes del entorno; defaults no secretos documentados en el harness.
- DSN/keys vienen del entorno/configuración existente. No se carga el archivo privado de Messaging ni se copian secretos desde otros procesos.
- `PGOPTIONS` restringe conexiones del operacional a read-only y statement timeout. Se comprueba `transaction_read_only=on` tanto en el preflight como en el pool real usado por los handlers.

## Structural Gate

Construcción e inventario pasan sin conectividad externa; las suites aportan validación estática, contratos, permisos y lifecycle controlado, no certificación productiva.

- Import Srv05 y acceso a `app`: PASS; identidad con Srv01: PASS.
- `create_app`: PASS; inventario determinístico respecto de la app exportada.
- Se capturan los inputs del constructor para detectar colisiones antes de que el framework pueda sobrescribir handlers.
- Unicidad method/path, normalización de parámetros y correspondencia entre declaraciones/handlers efectivos: PASS.
- OpenAPI: cobertura completa de operaciones inventariadas, operation IDs únicos y referencias internas resolubles: PASS.
- Registry sin handlers repetidos: PASS.
- Hooks conservados una vez y en orden: pool → scheduler; scheduler → pool.
- Fases Srv05 1/2/3 reutilizadas: PASS, incluida configuración pública lazy sin conexiones en import.

## Matriz operacional

READY significa solamente las pruebas explicitadas abajo. La dependencia externa de un submódulo no se extrapola a todos los consumidores del monolito.

| Servicio | Estado observado | Requerido por / prueba |
| --- | --- | --- |
| PostgreSQL | READY | Flow, contexto Diagnosis/embed, core Console y Messaging; DB `team360` 18.4, read-only, tablas seleccionadas e índices Messaging 026 presentes |
| Milvus | READY | Diagnosis; colección canónica, dimensión 1536, fila con scope/version pública y búsqueda vectorial real filtrada |
| LiteLLM | READY | Diagnosis; condicional para Flow según capacidad; `/models` autenticado, alias presente y chat mínimo no vacío |
| Evolution | NOT_REQUIRED | consumidor DEV no habilitado en esta corrida; health/transporte NOT_TESTED; no dependencia Flow/Diagnosis |
| Gmail/DWD | CONDITIONAL | Flow email; probe NOT_TESTED por ausencia de cuenta delegada de prueba seleccionada |
| Gupshup | CONDITIONAL | bridge WhatsApp/Flow registrado; outbound NOT_TESTED; webhook ignorado seguro probado |
| SAP/HANA | NOT_REQUIRED | no superficie Telchi en este app; cero consultas/writes |

LiteLLM devolvió `openai_gpt-5.4-nano`, smoke chat 1242 ms en la corrida validada. El cliente no tiene fallback en esa llamada; el alias devuelto no demuestra por sí solo upstream exacto ni ausencia de fallback interno del proxy. Esa auditoría permanece NOT_TESTED.

## Resultados por módulo

Los probes HTTP usan la única `Srv05.app` en proceso, con pool real read-only. Al omitir lifespan no se los presenta como un Uvicorn operacional completo.

| Módulo | Resultado demostrado | Límite |
| --- | --- | --- |
| Flow | Structural/tests PASS; GET configuración, operational settings y Directorio PASS con PostgreSQL real | Operational parcial; scheduler/automatización real no ejecutados; Gmail/outbound NOT_TESTED |
| Diagnosis | Structural/tests PASS; contexto público DB, rechazo wrong-tenant, HTTP 403 por override de tenant y embedding/search real PASS | mamamia360 binding NOT_READY local; conversación/persistencia real NOT_TESTED |
| Console | imports/PASETO/permisos/bootstrap contracts PASS; `/api/console/me` sin token → 401 | bootstrap real con usuario/entitlements y token real NOT_TESTED; no nuevo login |
| Messaging | routers y adapter suites PASS; Evolution sin configuración → 503; Gupshup evento vacío → ignored/200 | no transporte real, replay DB, callback ni bindings ficticios; Gupshup sí consume Flow por su bridge existente |
| Telchi | NOT_APPLICABLE como API de este servidor | no PASS de Foundation, Data Lake, SAP ni TelchiAI |

Flow no adquiere dependencias Milvus/Evolution por convivir en este servidor. Evolution Messaging no consume Flow/Diagnosis; Gupshup tiene una integración real distinta y explícita hacia Flow, no una dependencia inventada.

## Lifecycle y degradaciones

El lifespan real permanece pendiente por seguridad. Los tests controlados pasan, pero no sustituyen startup/shutdown sobre servicios y configuración reales.

1. PostgreSQL DEV tiene `automation_enabled=true`. Iniciar el scheduler podría enviar correos y registrar ciclos: no se inició ni se cambió esa configuración.
2. Se abrió/cerró manualmente el singleton pool solo para probes read-only sin lifespan. Cleanup del pool PASS, scheduler ausente; esto no prueba pool/scheduler coexistiendo operativamente.
3. Los tests Srv05 sí ejecutan lifecycle de tarea Flow con settings simulados deshabilitados y Uvicorn temporal en memory; prueban wiring/paridad/cleanup, no ejecución operacional completa.
4. `mamamia360_embed` no existe en la DB DEV consultada. No se creó ni cambió ningún binding y no se concluye que falte en producción.
5. La primera versión del probe esperaba 401 en Directorio; observó 200. Investigación confirmó `access_mode.py`: `default_admin` es default e incluye todas las capabilities Flow, no solo configuración.
6. Ese comportamiento es explícito y testeado, no un bypass nuevo de Srv05. El README Flow/status GLOBAL describen Directorio PASETO incondicional: divergencia documental/de hardening registrada, sin reconciliar aquí.
7. Gupshup está montado sin autenticación de firma DEV; el adapter dev Diagnosis sigue físicamente expuesto. Son riesgos preexistentes de promoción, no colisiones descubiertas ni funcionalidad modificada.

No se demostró un defecto de convivencia nuevo. Se distinguieron límites ambientales, falta de binding local, deuda contractual y comportamiento MVP deliberado. No se corrigió runtime para obtener PASS.

## Suites y evidencia

La corrida validada reutiliza 809 tests PASS y 2 skips; cada comando exacto y resumen por grupo está en el reporte. Las suites se ejecutaron secuencialmente sin pools de todos los cores.

| Grupo | Passed | Skipped |
| --- | ---: | ---: |
| Srv05 compatibilidad/arquitectura/runtime/launchers | 93 | 0 |
| Registry/DB | 27 | 0 |
| Flow focalizado | 114 | 2 |
| Diagnosis/embed/contexto/Milvus/contracts | 349 | 0 |
| Console/Auth/PASETO/SQL safety | 51 | 0 |
| Messaging/Gupshup/Evolution/ports/benchmark | 167 | 0 |
| Harness | 8 | 0 |

- [Reporte final validado](../../data/reports/team360-full-gate/final-run/report.json), [OpenAPI](../../data/reports/team360-full-gate/final-run/openapi.json), [rutas](../../data/reports/team360-full-gate/final-run/routes.json).
- Gates documentales ejecutados: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`, sin errores. LAT reportó warnings de init/key opcionales; no se alteró su configuración.
- [Primera corrida del harness](../../data/reports/team360-full-gate/first-run/report.json) preservada: abortó agregación operacional por aserción de binding ausente; no es evidencia de defecto del runtime.
- Corrección únicamente del harness: preservar evidencia parcial, distinguir binding ausente y evaluar HTTP contra el access mode real, conservando la discrepancia documental.
- Las pruebas PostgreSQL con writes opt-in, los smokes que crean sesiones y los gates que envían mensajes no se ejecutaron.

## Frontend, procesos y preservación

Esta fase no construye frontend ni inicia browser. Las superficies se enumeran separadas del gate de coexistencia backend.

- Home `/t360`, web/embed, Console y Flow UI existen con E2E en `astro/e2e/`; sus contratos backend se cubren donde lo permiten los tests citados.
- TelchiAI es trabajo frontend preexistente sin API global Telchi; no se lo declara integrado por el mero archivo de página.
- `pnpm check`, `pnpm build` y browser E2E: NOT_TESTED. No había frontend/runtime real compatible disponible en 3050/7050; no se activó scheduler para suplirlo.
- Servicios utilizados: PostgreSQL, Milvus y LiteLLM ya levantados. Ningún servicio horizontal fue iniciado, detenido o reiniciado.
- Procesos propios: workers Python/pytest; tests Srv05 crean Uvicorn temporales con sockets propios. El operacional no inició Uvicorn ni listeners.
- Guard del host: 8 cores, aproximadamente 6.3 GiB disponibles, load bajo y swap sin crecimiento observado; concurrencia de suites 1. Reporte incluye snapshot del runner.
- Worker sessions son propias; PID, retorno y verificación de cleanup por worker/suite están en el reporte final. Cleanup limitado a sus descendientes. Verificación final sin runners/listeners propios pendientes; procesos ajenos terminados: 0.
- Diffs tracked preexistentes idénticos antes/después: SHA-256 `56b367d6a0b9333048d617d5e9514ba35eb9b1f383e2df15b5fe8eb6af52c6f8`.
- Solo se agregaron harness, repository SQL del gate, tests propios, este documento y evidencia bajo `data/reports/team360-full-gate/`.
- No se actualizó el status GLOBAL: el Full Gate operacional todavía no está cerrado.

## Decisión y próximo paso

Srv05 es estructuralmente compatible con el servidor completo actual; esta evidencia no alcanza para declararlo listo para promoción posterior.

Preparar una ventana separada con DB/bindings de prueba autorizados, automatización Flow deshabilitada explícitamente en ese entorno, cuenta Gmail segura y auditoría LiteLLM. Ejecutar lifespan real, conversación/embed y E2E reproducibles sin tocar producción.

La promoción, reconciliación del contrato de acceso Flow y cualquier defecto que requiera cambios runtime necesitan autorizaciones separadas. El resultado de esta medición es `TEAM360_FULL_GATE_DEGRADED`.

## Reconciliación posterior: acceso Flow

El follow-up permanece evidencia fechada: Operational DEGRADED y Srv05 no elegible para promoción. El hardening posterior cambia sólo la lectura vigente del riesgo de acceso Flow, no convierte este gate en PASS operacional.

`TEAM360_FLOW_DEFAULT_ADMIN_HARDENING_PASS` según baseline confirmado: demo sólo con DEV explícito + `default_admin`; ausente → `authenticated`; configuración inválida o demo fuera de DEV → 503. [Política vigente](../backend/modules/flow/README.md#política-de-acceso-de-la-demo) y [estado GLOBAL](status_actual.md). Las observaciones permisivas de abajo describen la corrida anterior, no el contrato actual. La evidencia original no se reescribe; Diagnosis y los restantes límites se preservan.

## Reconciliación Diagnosis antes de revalidar

El defecto post-cierre fue corregido después del follow-up. Las corridas DEGRADED anteriores se preservan; el estado final requiere una nueva ejecución del Full Gate.

`TEAM360_DIAGNOSIS_POST_CLOSE_STATE_FIX_PASS`: persistencia correcta, required como política y completed como cierre. Solicitud explícita puede volver a renderizar diagnóstico, sin reapertura ni approved. [Autoridad local y tests](../backend/modules/sales_diagnosis_runtime/status_actual.md#fix-post-cierre). La deuda Flow `default_admin` también está corregida según la sección anterior.

## Followup operacional seguro

La ventana GLOBAL siguiente conserva la corrida anterior y cierra garantías parciales, no promoción. Ejecutada el 2026-10-07 local / 2026-10-08 UTC: Structural PASS, Operational DEGRADED, 812 tests PASS y 2 skips.

```bash
cd SrvRestAstroLS_v1/backend
uv run python scripts/validate_team360_full_stack.py --safe-operational \
  --output ../../data/reports/team360-full-gate/<directorio-nuevo>
```

- [Reporte final](../../data/reports/team360-full-gate/operational-followup-final/report.json), [hallazgos y límites](../../data/reports/team360-full-gate/operational-followup-final/findings.json).
- [Primer intento](../../data/reports/team360-full-gate/operational-followup-20261007/report.json): el harness contaba tareas en el loop llamador, no en el portal de lifespan Litestar; startup no certificado por esa aserción, shutdown/cleanup sí observados.
- [Segunda corrida](../../data/reports/team360-full-gate/operational-followup-20261007-r2/report.json): lifespan y conversación controlados PASS. La final agrega comprobación del pool real y auth Mamamia.
- Solo se extendieron harness, repository del gate, tests propios, este documento, resumen GLOBAL y evidencia. Sin cambios funcionales, Git mutante, deploy ni administración de infraestructura.

### Lifespan y side effects

Srv05 ejecutó los hooks reales de startup/shutdown ASGI con pool PostgreSQL y scheduler reales. La automatización habilitada en DB no fue ejecutada: se aplicó una fixture explícita, exclusivamente dentro del harness.

- `FlowScheduler._read_settings` conserva la consulta real y proyecta `automation_enabled=false`, intervalo 1 s. No cambia DB, configuración persistida ni código Flow.
- El scheduler real relee PG: 10 lecturas, una tarea en el portal de lifespan, segundo `start_scheduler()` sin duplicación. `_execute_cycle` tiene un guard que falla si se intenta delivery; intentos observados: 0.
- Pool real read-only comprobado dentro del lifespan. Un pool estándar nuevo reemplaza el pool del probe anterior ya cerrado: ningún pool operativo duplicado; un pool cerrado de psycopg no puede reabrirse.
- Guard Python de conexiones: solo PG/Milvus/LiteLLM locales. DSN y endpoints nativos libpq/grpc se verifican por separado; no es firewall del host ni auditoría del proxy.
- Startup PASS, shutdown PASS, pool cerrado, singleton scheduler eliminado y cero tareas restantes. No certifica Uvicorn con configuración DB-enabled sin fixture ni ciclos automáticos con transporte real.
- Gmail, WhatsApp, Evolution, Gupshup, webhooks externos y notificaciones: cero envíos solicitados. LiteLLM sí recibió prompts sintéticos de prueba y consumió cuota de generación/embeddings.

### Resultados por superficie

Se separan stack funcional, controles HTTP y calidad conversacional. Ningún PASS parcial reemplaza los requisitos del Full Gate operacional.

| Superficie | Resultado nuevo | Alcance / pendiente |
| --- | --- | --- |
| Flow | PASS controlado | configuración/Director read-only PG; scheduler lifecycle real con fixture; suites de lógica. Ciclo automático, delivery y probe Gmail NOT_TESTED |
| Diagnosis | PASS stack real/controlado | tres turnos 201, persistencia 1→2→3, cinco hits por turno en scope público; turno 2 completa diagnóstico. Calidad post-cierre con preocupación explícita |
| Mamamia | PASS binding/contexto/API local | ID canónico presente, origin permitido 200 / denegado 403, turno sin HMAC 403; sin provisionar |
| Embed demo | PASS API/conversación | `local_embed_demo` existente; HMAC request-bound, tamper 403, origin deny 403, override de workspace ignorado, estado persistido |
| Console/Auth | PASS fixture autorizado | bootstrap 201, token Ed25519 válido → me 200, manipulado/ausente → 401; permisos/entitlements por fakes oficiales. Identidad/RBAC DB real NOT_TESTED |
| Messaging | PASS coexistencia/tests | Evolution deshabilitado → 503; Gupshup vacío ignorado → 200; transporte/callback/persistencia real NOT_TESTED en esta fase |
| Frontend/browser | NOT_TESTED | sin listeners 3050/7050 disponibles; no se iniciaron launchers, build, browser ni servidores alternativos |
| TelchiAI | NOT_APPLICABLE | no superficie Telchi integrada en Srv05; no consultas Telchi/SAP/Data Lake |

Diagnosis usó `openai_gpt-5.4-nano` por LiteLLM y embeddings `openai_text_embedding_3_small`, dimensión 1536. Colección/version canónicas y scope `8b071443-5bd6-4fe4-bbc3-fc2dca179a5b`. Latencias HTTP de los tres turnos: 3215, 5227 y 3406 ms; no benchmark.

La respuesta y decisiones están en el reporte. Los tres turnos declararon generación exitosa sin fallback runtime/provider y se observaron ocho llamadas chat incluyendo clasificador y embed. Provider upstream exacto y fallback interno del proxy siguen NOT_TESTED.

### Mamamia y default_admin

La investigación histórica corrige la interpretación del probe, no el binding ni el comportamiento de acceso Flow de aquella corrida. Las fuentes oficiales contradicen dos supuestos de la corrida anterior.

- Seeds manuales oficiales `009_seed_mamamia360_embed_client.sql` y `010_update_mamamia360_production.sql` usan `mamamia360`, no `mamamia360_embed`. Ninguno fue aplicado aquí. El ID canónico existe/está activo en DEV y resuelve el scope público; el ID anterior sigue ausente.
- Mamamia sigue siendo un binding distribuidor/embed al contexto Vera público: `team360_live/team360_public_site/pkg_sales_diagnosis/ks_team360_sales_diagnosis`. No es cliente DB independiente. No se consultó DB productiva ni se inventó otro tenant.
- Rechazo de override público y lookup wrong-tenant PASS; ese tenant es inexistente. Cross-session entre dos tenants reales y carga browser del sitio Mamamia permanecen NOT_TESTED.
- `default_admin = DEMO_MODE_INTENTIONAL`: explícito en `access_mode.py`, README demo, tests y caller `_require_flow_actor` de `routes.py`; el frontend configuración también documenta ese modo.
- Riesgo productivo `SECURITY_DEBT` observado en aquella corrida (sustituido por el hardening posterior): no estaba restringido a DEV; modo ausente o desconocido habilita administrador implícito, incluyendo Directorio y configuración. Solo `authenticated` exige PASETO/capability. La documentación que describe PASETO incondicional diverge; no se corrigió comportamiento ni contrato en esta fase.

### Hallazgos, fixtures y cleanup

El stack puede conversar y persistir sin delivery, pero apareció una preocupación funcional que no se oculta bajo el PASS de conectividad. Las correcciones runtime quedan fuera de esta autorización.

- En r2 y final, después de un diagnóstico completo en turno 2, el turno 3 pidió diagnóstico final y obtuvo `reflect_and_ask` con `diagnosis_status=completed`; volvió a preguntar por aprobación humana ya informada como obligatoria. Causa raíz pendiente; requiere investigación protegida separada, no fix silencioso.
- La respuesta también ubica stock en planilla aunque el primer prompt decía sistema; el segundo menciona Excel y puede ser ambiguo. No se declara causa demostrada ni defecto de infraestructura por esta observación.
- Console reutiliza `_service` de `test_console_bootstrap_service.py`, workspace/user ficticios existentes y claves Ed25519 efímeras. Omitir capability workers prueba visibilidad del bootstrap, no acceso a una ruta worker protegida; no se inventaron usuarios DB ni login.
- Única excepción read-write: repository real de estado con opciones de conexión DEV explícitas, dos IDs frescos `full_gate_<UUID>` verificados ausentes antes de uso. Cleanup parametrizado solo de esos IDs, siguiendo el smoke oficial de estado; final: 2 eliminadas, 0 restantes.
- Corpus, tenants, bindings, configuración Flow y datos Messaging no cambiaron. Las respuestas sintéticas quedan en evidencia; no se guardan claves, firmas HMAC ni tokens.
- Workers Python/pytest y Uvicorn temporales de suites cerrados; sesiones propias verificadas por el runner. Ningún proceso ajeno terminado ni servicio horizontal iniciado/reiniciado/detenido. PG/Milvus clients nativos se cierran al terminar el worker; no queda runtime propio escuchando.
- El error de import del primer test nuevo y el conteo en loop equivocado se corrigieron únicamente en test/harness. Los intentos previos se preservan; no fueron defectos de Srv05.

### Matriz final y decisión

READY conserva el alcance del preflight real y de las operaciones observadas, no implica todas las capacidades del servicio. Las superficies condicionales no justifican tráfico a destinatarios inferidos.

| Servicio | Estado | Usado por / límite |
| --- | --- | --- |
| PostgreSQL | READY | Flow, Diagnosis/contextos, pool Console fixture; tablas/índices Messaging; estado Diagnosis real y cleanup |
| Milvus | READY | Diagnosis real; nunca dependencia Flow |
| LiteLLM | READY | generación/clasificación/embeddings Diagnosis; smoke adapter compartido Flow; upstream interno no auditado |
| Evolution | NOT_REQUIRED | consumidor deshabilitado en esta configuración; health/delivery NOT_TESTED; nunca dependencia Flow/Diagnosis |
| Gmail/DWD | CONDITIONAL | Flow email; auth/config probe NOT_TESTED sin cuenta de prueba explícitamente seleccionada |
| Gupshup | CONDITIONAL | webhook vacío seguro; delivery NOT_TESTED sin sandbox/target autorizado |

Structural Gate final PASS: 28 operaciones, sin colisiones, hooks únicos, Srv05/Srv01 consistentes; suites 812 PASS / 2 skips. Operational Gate final DEGRADED: lifespan seguro probado con fixture, no con automatización habilitada sin controles.

Restan browser/loader/assets/CORS, segundo tenant real, identidad Console/RBAC DB, transporte Flow/Messaging sandbox, Gmail probe y auditoría upstream LiteLLM. La preocupación conversacional también requiere ventana separada. La validación ASGI no certifica por sí sola un servidor de red completo.

Srv05 **no queda declarado técnicamente elegible para revisión de promoción** con esta evidencia. No se promocionó ni reemplazó Srv01. Próximo paso: fixture de transporte/identidad autorizada y servicios frontend ya disponibles, más investigación Diagnosis; no rediseñar ambientes.

Validación de cierre: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check` sin errores; LAT conserva warnings opcionales de init/key. Revisión del diff y tests focalizados del harness: 11 PASS.

El resultado final de esta ventana sigue siendo `TEAM360_FULL_GATE_DEGRADED`.

## Revalidación 2026-10-09

Corrida `revalidation-20261009T115343Z`: Structural PASS, Operational DEGRADED; fixes Flow/Diagnosis revalidados. Sus bloqueos son históricos: ver [cierre posterior](#reconciliación-global-posterior-aislamiento-diagnosis).

```bash
cd SrvRestAstroLS_v1/backend
TEAM360_ENV=development TEAM360_FLOW_ACCESS_MODE=default_admin \
  uv run python scripts/validate_team360_full_stack.py --safe-operational \
  --output ../../data/reports/team360-full-gate/revalidation-20261009T115343Z
```

[Reporte](../../data/reports/team360-full-gate/revalidation-20261009T115343Z/report.json), [suites adicionales](../../data/reports/team360-full-gate/revalidation-20261009T115343Z/supplemental-tests.json), [cierre y límites](../../data/reports/team360-full-gate/revalidation-20261009T115343Z/closure.json). Evidencia anterior intacta.

- Structural: import/factory Srv05=Srv01, registry, handlers, routing, OpenAPI y hooks únicos PASS. 28 operaciones idénticas a la corrida anterior; `resolve_runtime_profile("full") != Full Team360 Gate`.
- Flow: 242 PASS / 2 skips. Hardening DEV/demo, PROD/no DEV 503, unknown/vacío/whitespace/typo 503, modo ausente authenticated, sin token 401 y sin capability 403 cubiertos por suites existentes. HTTP/PG real read-only PASS; no depende de Milvus/Evolution.
- Lifespan: startup/shutdown PASS; pool real read-only; scheduler único, diez lecturas PG, segundo start sin duplicación, cero ciclos/delivery y cero tareas finales. La fixture proyecta automation=false; DB conserva automation=true. No equivale a producción con automatización activa.
- Diagnosis: tres turnos reales 201; acción final diagnose, diagnóstico presente, sin preguntas, human_approval=required y diagnosis_status=completed persistidos y recargados. Sin reapertura ni approved. PG/Milvus/LiteLLM reales, scope/version canónicos, generación sin fallback reportado por runtime/adapter. Test post-close PG separado: 12 PASS.
- Mamamia360: binding canónico existente; HMAC request-bound, origin allow 200/deny 403, tamper/unsigned 403, contexto backend y override ignorado; conversación firmada 201 persistida en sesión distinta. Sin provisionar bindings; aislamiento entre dos tenants reales NOT_TESTED.
- Console/Auth: 51 PASS; fixture oficial bootstrap 201, PASETO válido 200, ausente/manipulado 401, capabilities/entitlements restringidos. Identidad/RBAC DB real NOT_TESTED.
- Messaging: 167 PASS y coexistencia HTTP; Evolution deshabilitado 503, Gupshup vacío ignored/200. Trabajo Messaging↔Telchi del 08/10 preservado y no atribuido. No se consultó Meta: ausencia de suscripción permanece evidencia histórica, no disponibilidad actual.
- Telchi: NOT_APPLICABLE como API global, inventario sin superficie montada. No se ejecutaron SAP/HANA, Foundation, Data Lake ni TelchiAI.
- Browser/frontend: NOT_TESTED. Puertos 3050/7050 sin listeners. Aunque global.js permite DEV, el launcher normal inicia el scheduler con automation=true de DB; no existe override seguro usado por esta corrida. No se alteró configuración ni se levantó frontend para forzar PASS.

La matriz refleja probes reales de esta corrida, no disponibilidad inferida de puertos abiertos.

| Servicio | Estado | Required / used by |
| --- | --- | --- |
| PostgreSQL | READY | REQUIRED: Flow, estado/contexto Diagnosis/embed, pool; tablas Messaging; identidad Console real NOT_TESTED |
| Milvus | READY | REQUIRED: Diagnosis, embedding/search filtrado, dimensión 1536 |
| LiteLLM | READY | REQUIRED: Diagnosis chat/clasificador/embeddings; alias openai_gpt-5.4-nano; routing interno upstream NOT_TESTED |
| Evolution | NOT_REQUIRED | consumidor DEV deshabilitado; health/outbound NOT_TESTED |
| Gmail | CONDITIONAL | Flow email; probe/delivery NOT_TESTED sin cuenta sandbox autorizada |
| Gupshup | CONDITIONAL | coexistencia webhook PASS; outbound NOT_TESTED |
| SAP/HANA | NOT_REQUIRED | sin API Telchi global; cero consultas/writes |

Suite principal: 951 PASS / 3 skips (antes 812/2; hardening Flow +128 PASS y post-close +11 PASS/+1 skip). Suites adicionales: post-close PG 12 PASS; Diagnosis ampliada 769 PASS / 14 FAIL / 10 skips. Total de ejecuciones, incluyendo repeticiones: 1732 PASS / 14 FAIL / 13 skips; no es conteo de tests únicos.

`PREEXISTING_TEST_ISOLATION_ISSUE`: reaparecen los 14 fallos de test_diagnosis_public_router al combinar todos los test_sales_diagnosis*. El subset oficial Diagnosis pasa 360/1. El antecedente contra HEAD proviene del cierre informado; no se reejecutó HEAD ni se modificó el árbol para hacerlo. No se atribuye al fix post-cierre ni se oculta en el total.

Skips: dos Flow opt-in del grupo principal, un post-close PG no habilitado en ese grupo (cubierto aparte), diez skips PostgreSQL en ampliada (post-close opt-in y async repository sin URL DB de fixture). El JSON conserva comandos y node IDs fallidos; no se habilitaron transportes reales.

Dos sesiones full_gate UUID eliminadas, cero restantes; test PG adicional elimina su propia sesión. Todos los workers y sesiones de proceso verificaron cleanup; ningún listener propio final. No envíos Gmail/WhatsApp/Gupshup/Evolution, migraciones, corpus writes, cambios de bindings ni lifecycle horizontal. LiteLLM sí consumió cuota sintética. Diffs tracked ajenos, excluyendo GLOBAL autorizado, idénticos antes/después.

Operational permanece DEGRADED por la política conservadora del harness existente; no se cambió su agregación para forzar PASS. Las garantías backend obligatorias controladas pasaron, pero persiste el bloqueo técnico de aislamiento de suites y riesgos de promoción anteriores: adapter dev físicamente montado y webhook Gupshup DEV sin firma. Browser/assets, identidad/RBAC DB y auditoría interna LiteLLM siguen sin evidencia nueva. Transportes condicionales no se consideran fallos funcionales.

Srv05 **no queda declarado technically eligible for promotion review** mientras exista ese bloqueo técnico conocido. Próximo paso: ventana separada para aislamiento de suites y revisión de límites de promoción; luego E2E con runtime seguro autorizado. Sin nuevos fixes, reemplazo Srv01 ni producción.

Gates documentales y git diff --check ejecutados sin errores; LAT mantiene warnings opcionales de init/key. Resultado: `TEAM360_FULL_GATE_DEGRADED`.

## Reconciliación GLOBAL posterior: aislamiento Diagnosis

El cierre posterior del 2026-10-09 elimina el motivo de degradación por aislamiento de tests, no cambia las corridas anteriores ni declara promoción. Esta ventana es documental; no ejecuta otro Full Gate operacional.

- Hallazgo histórico `PREEXISTING_TEST_ISOLATION_ISSUE` cerrado como `TEST_ISOLATION_ONLY` con `TEAM360_DIAGNOSIS_TEST_ISOLATION_PASS`. No representa defecto productivo Diagnosis ni defecto demostrado de estado global runtime.
- Mínimo causal: `test_litellm_mode_is_accepted_with_env_config` seguido de `test_public_turn_with_context_smoke`. El primero eliminaba en su `finally` la `LITELLM_MASTER_KEY` heredada; el classifier posterior quedaba sin API key y devolvía 500. Orden invertido PASS.
- Corrección exclusivamente de infraestructura de test: `monkeypatch` reversible y regresiones de teardown; cero cambios funcionales de runtime por este fix de aislamiento.
- Evidencia posterior: 14 afectados PASS; ampliada 785 PASS / 0 FAIL / 10 skips, dos corridas y orden de archivos invertido; router/embed 91 PASS; post-close 11 PASS / 1 skip; subset Diagnosis Full Gate 362 PASS / 1 skip. No son una nueva corrida operacional completa.
- [Reporte causal y validaciones](../../data/reports/diagnosis/test-isolation-20261009/report.json), [estado local Diagnosis](../backend/modules/sales_diagnosis_runtime/status_actual.md#aislamiento-de-tests-diagnosis), [estado GLOBAL y pendientes](status_actual.md#evidencia-pendiente-de-promoción-srv05). La autoridad local ya contiene el cierre y no se modifica nuevamente.

### Decisión vigente y readiness pendiente

El resultado Full Gate sigue siendo `TEAM360_FULL_GATE_DEGRADED` hasta una evaluación explícita. Structural PASS y backend operacional controlado PASS en garantías ejecutadas no equivalen a promoción Srv05.

Flow hardening y Diagnosis post-close están revalidados; aislamiento Diagnosis está cerrado. Las frases históricas sobre un bloqueo de 14 fallos o una investigación Diagnosis pendiente quedan sustituidas por este cierre, no borradas de la evidencia original.

| Pendiente / condición | Clasificación | Requisito para readiness |
| --- | --- | --- |
| Browser/frontend E2E | NOT_TESTED | check/build, páginas, loader/assets/CORS y montaje sobre composición Srv05 segura; incluye Mamamia browser |
| Identidad/RBAC real | NOT_TESTED | Console contra DB con identidades/entitlements autorizados y aislamiento entre dos tenants reales |
| Auditoría LiteLLM | NOT_TESTED | upstream/provider y fallback interno del proxy; PASS del adapter no cubre routing interno |
| Lifecycle con automatización activa | NOT_TESTED | fixture automation=false ya PASS; falta ejecución segura de automatización/delivery, sin habilitar efectos de la DB actual por inferencia |
| Gmail/DWD y outbound Gupshup/Flow | CONDITIONAL | probe/transporte NOT_TESTED; exigir sólo con alcance pertinente y sandbox/targets explícitamente autorizados |
| Evolution | NOT_REQUIRED | deshabilitado en corrida medida; health/delivery NOT_TESTED, CONDITIONAL si se habilita |
| Exposición de superficies DEV | CONDITIONAL | revisar adapter Diagnosis montado y webhook Gupshup DEV sin firma según configuración destino; riesgos preexistentes, no defectos causados por aislamiento de tests |
| SAP/HANA y API Telchi | NOT_REQUIRED | fuera del servidor global medido |

**DEFECT** no aplica al problema cerrado de los 14 fallos; los NOT_TESTED no son defectos. Las observaciones conversacionales históricas no constituyen un nuevo defecto demostrado ni autorización para reabrir Diagnosis.

Srv05 promoción: **NOT YET DECLARED** en aquella reconciliación. La siguiente medición de readiness se registra abajo; este cierre documental previo no realizó fix, deploy, reemplazo de Srv01 ni promoción.

## Promotion readiness 2026-10-09

La ventana GLOBAL / SRV05_PROMOTION_READINESS revalida garantías controladas y clasifica requisitos. Full Gate sigue DEGRADED; readiness específica BLOCKED por packaging y evidencia obligatoria pendiente, sin fixes productivos.

- [Matriz completa, comandos, clasificación y cleanup](../../data/reports/team360-promotion-readiness/20261009T123839Z/report.md), [corrida nueva](../../data/reports/team360-promotion-readiness/20261009T123839Z/full-gate/report.json). Evidencia Full Gate previa preservada.
- Structural PASS: 28 operaciones; suite principal 951 PASS / 3 skips. Diagnosis ampliada + adapter: 798 PASS / 10 skips (785 + 13); cero regresiones de aislamiento. Stack real/post-close/Mamamia y lifecycle con fixture PASS, sin automatización activa ni delivery.
- Frontend check/build DEV PASS, build en output aislado. Browser E2E NOT_TESTED / BLOCKING_FOR_PROMOTION: normal launcher inicia scheduler con automation=true y sin override seguro; messaging-only no certifica Srv05.
- Identidad/RBAC DB y segundo tenant real: NOT_TESTED / BLOCKING_FOR_PROMOTION. Seeds inspeccionados no designan usuarios/tenants autorizados para estas pruebas; no impersonar administradores reales ni provisionar fixtures silenciosamente.
- LiteLLM: auditoría read-only de config y GET autenticados model/info/router/settings confirma upstreams OpenAI y fallbacks activos vacíos para el alcance probado. Falla upstream viva NOT_TESTED / NON_BLOCKING_FOR_PROMOTION con contratos de error adapter PASS; ningún routing modificado ni proxy interrumpido.
- Lifecycle ASGI controlled PASS no equivale a real production automation enabled. Scheduler único, 10 lecturas PG, cero ciclos, shutdown/cleanup PASS. Automatización activa NOT_TESTED / BLOCKING_FOR_PROMOTION hasta delimitar/controlar destino automation=false o sandbox seguro autorizado; delivery condicional no se exige indiscriminadamente.
- Packaging: **DEFECT / BLOCKING_FOR_PROMOTION**. uv build wheel exitoso omite ls_iMotorSoft_Srv05.py, ls_iMotorSoft_Srv01.py y globalVar.py; import desde wheel fuera del source y sin procesamiento editable .pth falla ModuleNotFoundError. [Reproducción](../../data/reports/team360-promotion-readiness/20261009T123839Z/packaging/report.json). No se corrigió pyproject ni runtime.
- Gmail/Gupshup outbound CONDITIONAL, Evolution NOT_REQUIRED deshabilitado, SAP/HANA NOT_REQUIRED. Exposición DEV/bootstrap/Gupshup requiere decisión explícita de controles según destino; no se declara un exploit nuevo ni se activa transporte.
- Cleanup: dos sesiones sintéticas eliminadas/0 restantes, pool cerrado/scheduler eliminado/0 tareas; workers propios cerrados y sin listeners propios. Ningún servicio horizontal administrado, ningún mensaje enviado; LiteLLM consumió cuota sintética del stack.
- Elegibilidad exige Structural, lifecycle defendible, Flow fail-closed, Diagnosis real, auth/tenants suficientemente probados, browser/API smoke, cero defectos bloqueantes, cleanup, packaging válido y pendientes no bloqueantes/condicionales. No se satisface; no deploy ni reemplazo de Srv01.

Conclusión de esa ventana: `TEAM360_SRV05_PROMOTION_READINESS_BLOCKED`. Full Gate conserva `TEAM360_FULL_GATE_DEGRADED`; no hubo promoción. Packaging/runtime/browser fueron abordados después en el cierre siguiente; esta evidencia histórica permanece intacta.

## Packaging y E2E seguro 2026-10-09

La ventana posterior cierra packaging y listener/browser controlados, pero no declara elegibilidad por exposición y fixtures pendientes. [Readiness vigente](team360_srv05_promotion_readiness.md) conserva decisión y reproducción.

- [Nueva corrida y matriz](../../data/reports/team360-promotion-readiness/20261009T130833Z/report.md): Structural PASS (28 operaciones); Full Gate DEGRADED sin cambiar agregación del harness. Suite principal 951 PASS / 3 skips; ampliada/adapters 798 PASS / 10 skips; launcher/harness 16 PASS (conteos solapados).
- Fix mínimo Hatch: force-include de Srv05/Srv01/globalVar. Build repetido idéntico; instalación en venv limpio, imports site-packages, cwd fuera del checkout, app/OpenAPI/health y listener instalado PASS. El smoke instalado usa lifespan off; lifecycle real se prueba separadamente.
- Perfil opt-in srv05-e2e en backend-dev.sh: app Srv05 y hooks reales, pool PG read-only, scheduler único con fixture de proyección automation=false y guard de ciclos; DB conserva automation=true. Shutdown/cleanup PASS, 4 sesiones browser eliminadas y 0 restantes.
- Browser: 41 PASS / 2 skips. Home y Mamamia: dos turnos reales por sesión final, sin fallback, HMAC cuando corresponde, PG reload; loaders/assets y Flow read-only PASS. Console UX/contratos fixture no equivalen a identidad/RBAC DB.
- Auditoría production-env sintética: adapter DEV 201 sin guard de entorno; bootstrap PASETO habilitado emite token sin autenticación de entrada, usable en me 200. EXPOSURE_RISK bloqueante hasta guard/ingress probado; Gupshup sin firma según source. No se usaron identidades/claves reales ni se corrigió PASETO/Diagnosis protegido.
- Auth DB y segundo tenant: BLOCKED_BY_MISSING_AUTHORIZED_IDENTITY_FIXTURE / BLOCKED_BY_MISSING_SECOND_TENANT_FIXTURE. Automatización/delivery destino no certificados; no son fallos funcionales por ausencia de evidencia.
- PostgreSQL/Milvus/LiteLLM READY en nueva corrida; auditoría activa LiteLLM confirma upstreams OpenAI y fallbacks vacíos en campos inspeccionados. Sin routing change ni falla viva provocada.
- No mensajes, migraciones, cambios de corpus/tenant/config persistente, administración de servicios horizontales, deploy, reemplazo Srv01 ni Git mutante. Procesos propios y entornos temporales cerrados; evidencia previa preservada.

Decisión posterior: `TEAM360_SRV05_PROMOTION_READINESS_BLOCKED`, por exposición técnica sin frontera productiva demostrada, no por packaging. Los controles del harness no son guards de producción. Full Gate mantiene `TEAM360_FULL_GATE_DEGRADED`.

## Security boundary hardening 2026-10-09

La ventana posterior cierra los tres defectos de source sin cambiar la agregación conservadora del gate ni promover Srv05. [Reporte y evidencia](../../data/reports/team360-security-boundary/20261009T182048Z/report.md).

- DEV Diagnosis y bootstrap experimental: production/ausente/desconocido → 404 antes de provider, DB o token; DEV explícito conserva contratos. PASETO, claims y capacidades no se ampliaron.
- Gupshup inbound: configuración auth ausente → 503, credencial ausente/inválida → 401 antes de body/claim/Flow; token válido + evento vacío → ignored/200. No hay firma Gupshup documentada y no se inventó HMAC; la configuración sender/ingress permanece evidencia externa.
- Idempotencia: PASS por claim atómico y unique `(provider, external_message_id)`; duplicado no llega a Flow. Evolution DEV también quedó fail-closed ante `TEAM360_ENV` ausente/desconocido.
- Full Gate nuevo: Structural PASS, 28 operaciones y OpenAPI sin cambios; 961 PASS / 3 skips. PostgreSQL/Milvus/LiteLLM READY, Flow/Diagnosis PASS, HTTP Gupshup fail-closed y cleanup PASS. Operational sigue DEGRADED por lifecycle/delivery/fixtures no ejecutados, no por exposición.
- Packaging aislado PASS (wheel/site-packages/listener/cleanup). Browser vivo Srv05 2 PASS con lifecycle controlado, scheduler sin ciclos y dos sesiones eliminadas; regresión frontend anterior 39 PASS / 2 skips permanece aplicable porque no hubo cambios frontend.
- Readiness vigente: `TEAM360_SRV05_PROMOTION_READINESS_DEGRADED`. Restan identidad/RBAC y segundo tenant autorizados, compatibilidad/configuración ingress Gupshup y automatización destino. No deploy ni reemplazo Srv01.

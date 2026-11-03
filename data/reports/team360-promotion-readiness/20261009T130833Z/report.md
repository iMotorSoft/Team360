# Srv05 packaging, safe E2E and promotion readiness

Ventana autorizada en feature/console-backend-core, 2026-10-09. Packaging y browser seguro cerrados; readiness sigue BLOCKED por exposición sin frontera productiva demostrada, además de fixtures externas faltantes. No promoción ni deploy.

## Estado inicial y alcance

El baseline anterior era TEAM360_SRV05_PROMOTION_READINESS_BLOCKED por wheel incompleto y evidencia pendiente. Flow/Diagnosis funcionales cerrados permanecieron intactos; todo trabajo ajeno se preservó.

- Repo: /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360; rama feature/console-backend-core.
- Preflight Git: branch/status/diff --check correctos. [Estado inicial](initial-status.txt), [diff inicial](initial-diff.patch).
- Autorización: packaging, test harness/launchers/E2E y documentación delimitada; no cambios productivos, commits ni lockfiles.
- Host compartido: secuencial, workers=1; inicio load 1.83/2.18/2.14, 5969 MiB disponibles, swap 1475 MiB. Final observado load 2.28/1.86/1.89, 6991 MiB disponibles, swap 2526 MiB. Swap del host aumentó; memoria disponible también, sin bloqueo ni agotamiento observado. No se atribuye uso compartido a esta tarea.
- Suite runner guard SAFE: 6050 MiB disponibles; cada tarea se ejecutó acotada. Cero procesos ajenos terminados.

## Causa y corrección de packaging

Hatch convierte packages en selección restringida de directorios. include no reincorporaba módulos top-level fuera de esa selección; build exitoso producía una distribución no ejecutable por el entrypoint declarado.

- Reproducción nueva: [wheel antes](packaging/before/), [build](packaging/before-build.log): 5522 miembros, Srv05/Srv01/globalVar ausentes. ModuleNotFoundError aislado ya demostrado por el [cierre anterior](../20261009T123839Z/packaging/report.json).
- Fix mínimo en backend/pyproject.toml: reemplazar include por force-include, con tres mappings filename→filename. packages y dependencias originales preservados; sin mover layout, copiar archivos post-build, tocar imports ni modificar Srv01/Srv05/globalVar.
- Artefacto corregido: 5525 miembros. [Lista completa](packaging/final/contents.txt), [reporte](packaging/final/report.json). SHA-256: 9e9f42736893851b6d84df5b5fbcd434aab87d140f08ee2f463735c58bb74b79, idéntico en builds after/locked/final.
- Venv nuevo con uv venv, dependencias exportadas del lock frozen sin checkout/editable e instalación del wheel. cwd /tmp/srv05-wheel-yrh1q1gg, Python -I, sin PYTHONPATH/PYTHONHOME ni editable .pth.
- Origins: /tmp/srv05-wheel-yrh1q1gg/venv/lib/python3.12/site-packages/{ls_iMotorSoft_Srv05.py,ls_iMotorSoft_Srv01.py,globalVar.py}. No importa accidentalmente desde source.
- App/factory idénticos a Srv01; globalVar contract PASS; OpenAPI 28 operaciones; health ASGI 200. Guard socket durante import/factory evita I/O externo.
- Comando instalado probado: python -I -m uvicorn ls_iMotorSoft_Srv05:app --host 127.0.0.1 --port 34285 --lifespan off. PID 84402; health 200, shutdown PASS, logs en reporte. lifespan off es intencional para smoke sin efectos, no certificación de lifecycle productivo.
- Comando objetivo desde entorno instalado: uvicorn ls_iMotorSoft_Srv05:app --host 127.0.0.1 --port 7050, sólo con configuración privada y política de automatización/ingress autorizadas. No se desplegó ni ejecutó ese lifecycle sobre DB-enabled sin fixture.
- Package data de los roots seleccionados se conservó; el import/app instalado no requirió assets/templates del checkout. El wheel no publica frontend; assets se construyen por Astro. La validación rechaza extensiones .env/.pem/.key, sin afirmar auditoría completa del contenido investigativo empaquetado.
- Regresión permanente: backend/scripts/validate_srv05_wheel.py; build/install/import/health/listener instalados y cleanup, output nuevo obligatorio. Tests baratos de mappings y harness en backend/tests/test_srv05_packaging_harness.py.
- Primer install offline sin pins no encontró paquetes cached: ENVIRONMENTAL_ABORT, no defecto de runtime. Se corrigió reproducibilidad del script con export frozen; final offline PASS. Entornos temporales eliminados.

## Structural y backend por módulo

Se reutilizó el Full Gate existente sin alterar su agregación conservadora. Sus resultados se mantienen separados de browser, identidad DB, tenants y deployability.

- [Full Gate](full-gate/report.json): Structural PASS / Operational DEGRADED, exit 2 esperado. Srv05/Srv01 identity, registry, app/factory, 28 operaciones, OpenAPI, referencias/operation IDs y hooks únicos PASS; cero colisiones. [Rutas](full-gate/routes.json), [OpenAPI](full-gate/openapi.json).
- [Structural final](structural-final.log) repetido después del cierre del harness: PASS, 28 operaciones; source import/factory no realiza I/O.
- Flow: 242 PASS / 2 skips. Auth default fail-closed, DEV default_admin explícito, PROD demo 503, invalid/empty modes 503, token/capability denial; lectura PG real. No changes funcionales ni dependencias nuevas Milvus/Evolution.
- Diagnosis: 362 PASS / 1 skip en gate; ampliada/adapters 798 PASS / 10 skips. Aislamiento revalidado; post-close required/completed, diagnose sin reapertura ni approved, persist/reload real y scope Milvus PASS.
- Mamamia360/embed: API/HMAC/origin/tamper/override/contexto/persistencia PASS en gate, más browser real debajo. No bindings/seeds nuevos; Mamamia no es segundo tenant.
- Console/Auth: 51 PASS fixture; bootstrap/me/token/entitlements/capabilities. No identidad DB real usada.
- Messaging: 167 PASS, coexistencia Gupshup ignored 200/Evolution disabled 503; no transportes externos. Telchi/SAP/HANA/Data Lake fuera de alcance, no consultados/modificados.

## Listener, scheduler y browser

El harness opt-in prueba server completo y hooks reales sin habilitar automatización compartida. Sus restricciones de test no son guards de producción ni certifican delivery.

- Launcher autorizado: TEAM360_ENV=development TEAM360_FLOW_ACCESS_MODE=default_admin TEAM360_DEV_PROFILE=srv05-e2e TEAM360_E2E_EVIDENCE=<archivo-nuevo> bash SrvRestAstroLS_v1/backend-dev.sh.
- Normal sigue lanzando Srv01 sin cambios de defaults; nuevo perfil no permite PROD, host no loopback ni puerto ocupado, y nunca mata listeners existentes.
- Harness usa Srv05 real, pool PG read-only, fixture existente de scheduler (lectura DB real, proyección automation=false, intervalo 1 s, guard _execute_cycle). Mutaciones HTTP bloqueadas excepto auth/turn de sesiones full_gate UUID frescas; state repo real permite sólo IDs verificados ausentes y cleanup exacto parametrizado.
- Listener PID 80274 en 7050: startup PASS, pool read-only, una tarea scheduler, segundo start no duplica; 261 lecturas DB, DB automation=true intacto, cero ciclos/delivery. Shutdown PASS, pool cerrado, singleton ausente, cero tareas finales. [Lifecycle con browser y cleanup](lifecycle.json), [logs](uvicorn-safe.log).
- Última versión del harness revalidada con listener PID 84545: startup/health/shutdown/cleanup PASS, 4 lecturas PG, cero tareas/ciclos/sesiones. [Lifecycle final](lifecycle-final.json), [logs](uvicorn-last.log).
- Se corrigió un defecto exclusivo del harness: Uvicorn repropagaba SIGTERM antes del finally async y no escribía evidencia. Subclase test-only maneja el signal de salida graceful sin repropagarlo, restaura handlers y ejecuta cleanup. Primeros procesos 79017/80040 no tuvieron conversación ni writes; logs preservados. No cambio de lifecycle productivo.
- Automatización: scheduler lifecycle y lógica cubierta por tests PASS; business execution real DB-enabled y delivery NOT_TESTED. El scheduler no tiene dry-run oficial y run_once usa confirm_send=True. AUTOMATION_DELIVERY_NOT_TESTED, bloqueo de evidencia hasta política destino automation=false verificable o sandbox autorizado; no se transforma en fallo lógico.
- Astro: bash SrvRestAstroLS_v1/astro-dev.sh, sesión propia 80059, Node listener 80175 en 3050; build DEV y arranque PASS en [astro.log](astro.log). Dist normal reconstruido por launcher autorizado, sin deploy; source frontend/protected embed intacto.
- pnpm check PASS: 0 errors / 0 warnings / 7 hints en [frontend-check.log](frontend-check.log). build PASS por launcher oficial; no build productivo aprobado.
- Playwright con PLAYWRIGHT_SKIP_WEBSERVER=1, PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050, project=chromium, workers=1; nunca webServer automático.
- [E2E vivo final](browser-live-r2.json): 2 PASS. Home y Mamamia, dos turnos reales por sesión, visible assistant rendering, input re-enabled, turn_count 1→2, misma sesión, sin fallback, dos requests turn (no duplicados), cero 5xx/console errors. Mamamia usa dos auth HMAC reales; origin local oficial, assets loader de build real. Se cambió únicamente session_id a UUID sintético antes de transportar los requests; no respuestas mock.
- PostgreSQL reload se comprueba en save real del harness: sesiones finales e9a12295228b410da737fd7a0674de6d/f9bf1851c09c42a8a443effb92aa4a2e con 2 turnos persistidos. Cuatro sesiones de browser (incluidos intentos previos) eliminadas, cero restantes.
- Primer E2E [preservado](browser-live.json): 2 fallos de assertion test-only porque comparaba Markdown crudo con DOM renderizado; respuestas reales 201. Corregido test para observar mensaje renderizado; no fix frontend/runtime ni bug de producto demostrado.
- [Regresión browser](browser-regression.json): 36 PASS / 2 skips (Home/Vera/protección, dev-serving/manifest, Console shell). Mocks oficiales validan UI/error states, no identidad ni conversación DB. [Read-only](browser-readonly.json): 3 PASS (Flow configuración/refresh PG y Mamamia loader mount/bytes/origins/console).
- Total browser final: 41 PASS / 2 skips, ambos preexistentes en public-vera.spec.ts: "reload limpia session_id pero preserva idioma" (test.skip incondicional) y "smoke real /t360 contra backend vivo" (gate T360_REAL_E2E=1). El segundo cubre el mismo terreno real que srv05-safe-runtime.spec.ts; no se elevan a PASS ni se modificó el spec ajeno. No certifica montaje en www.mamamia360.com ni identidad/login real Console; tests de identidad son un frente independiente.

## Auth, tenants, LiteLLM y servicios

Se buscaron sólo mecanismos oficiales de test. No se impersonaron administradores ni se emitieron tokens para identidad DB real; se separa ausencia de autorización de ausencia física de registros.

- Seeds existentes: 005 plataforma/public/admins reales, 008 embed example, 009/010 Mamamia. Ninguno designa test user/segundo tenant autorizado para esta ventana; no seed aplicado.
- Identidad real → client/tenant → workspace → entitlement → module → capability/access: BLOCKED_BY_MISSING_AUTHORIZED_IDENTITY_FIXTURE. Rechazos ausente/manipulado y capability en fixture pasan, pero no completan la cadena DB.
- Dos tenants DB reales/cross-token isolation: BLOCKED_BY_MISSING_SECOND_TENANT_FIXTURE. Public/control workspaces y binding Mamamia no son segundo tenant. Wrong-tenant inexistente/override PASS no sustituyen aislamiento real; package/knowledge entitlement cruzados NOT_TESTED.
- [Auditoría LiteLLM activa](litellm-audit.json): authenticated GET model/info y router/settings 200; aliases generación/embedding → OpenAI, fallbacks presentes vacíos, model group alias/default-param fallback vacíos en campos inspeccionados. Routing no modificado.
- Error propagation/HTTP/network/JSON-invalid y transient fallback metadata cubiertos por 13 tests adapter dentro de ampliada; no failure inyectado al proxy compartido, timeout/fallo vivo NOT_TESTED no bloqueante con ese alcance. Cuota mínima de conversaciones sintéticas y preflight, sin benchmark ni probes masivos.
- Servicios horizontales nueva corrida: PostgreSQL READY (pool/contexto/estado), Milvus READY (scope/version/search/embeddings 1536 Diagnosis), LiteLLM READY (chat/classifier/embedding). No readiness inferida de mediciones históricas.
- Gmail/DWD y Gupshup outbound CONDITIONAL; delivery no probado, ningún destino autorizado. Evolution NOT_REQUIRED con consumidor deshabilitado. SAP/HANA NOT_REQUIRED sin superficie global Telchi. Ningún servicio horizontal iniciado/reiniciado/detenido.

## Superficies y bloqueo técnico aislado

La auditoría prueba la falta de guard en el app con entorno production y fixtures sintéticas. No demuestra compromiso de un despliegue existente ni reemplaza inspección ingress del destino.

- [Probe reproducible](surface_audit.py), [evidencia sanitizada](surface-audit.json): lifespan omitido, state memory/fake sólo para boundary audit, repos oficiales fake y claves Ed25519 nuevas efímeras; cero DB/provider/outbound I/O.
- DEV Diagnosis: POST /api/dev/sales-diagnosis-runtime/turn responde 201 con TEAM360_ENV=production y sin identidad. DEV_ONLY era inventario/naming, no guard. EXPOSURE_RISK técnico bloqueante para composición normal sin filtro autorizado.
- Bootstrap: POST /api/console/bootstrap sin Authorization, workspace-1/user-1 fixture, emite token cuando PASETO habilitado; me con token 200, me sin token 401. Causa: handler confía en IDs de body, sin vínculo con principal autenticado de entrada. EXPOSURE_RISK técnico bloqueante si esa superficie es pública/habilitada; no hay guard ingress demostrado. No se usaron usuarios, claves ni tokens productivos.
- Gupshup: unsigned empty 200 es sólo coexistencia; source no verifica firma/env antes de claimer/Flow bridge. EXPOSURE_RISK condicional del destino; no inbound real ni writes para probarlo.
- Flow: AUTH_GUARDED por hardening vigente; default_admin sólo DEV explícito. Embed: AUTH_GUARDED HMAC/context/origin. Evolution: DEV_GUARDED disabled=503. Product adapter: CONDITIONAL opt-in. Health: PRODUCTION_SAFE informativo. Debug/schema: CONDITIONAL, debug default off y schema montado; ingress debe delimitar.
- No se presenta el deny-all parcial del test harness como fix productivo. Remediar bootstrap implica contrato de autenticación y scope PASETO protegido; guards/filtrado de Diagnosis requieren ventana protegida específica. No es un cambio packaging necesario ni un refactor autorizado. Se aisló y siguieron todos los frentes independientes.
- Para cerrar este blocker: control fail-closed de DEV/bootstrap/webhook en destino o guard autorizado con regresión específica. No basta documentar DEV ni afirmar que un proxy probablemente bloquea la ruta.

## Matriz final de promotion readiness

Blocking distingue defecto/frontera técnica, evidencia externa y componentes condicionales. No se reutilizan conclusiones antiguas: packaging/browser salen de la lista de bloqueos; exposición reproducida entra explícitamente.

| Área | Estado | Evidencia | Blocking |
| --- | --- | --- | --- |
| Packaging/install/import/deployability | PASS, defecto cerrado | force-include, wheel limpio reproducible, installed listener | No |
| Structural | PASS | 28 operaciones, factory/registry/OpenAPI/hooks/collision | No |
| Lifecycle Uvicorn | PASS controlado | real pool/scheduler único/startup/shutdown | No para harness; sí condición destino |
| Flow | PASS | 242/2, fail-closed, PG/read-only browser | No en alcance probado |
| Diagnosis/post-close/isolation | PASS | gate real + ampliada 798/10 | No |
| Embed/Mamamia API/browser | PASS local | HMAC, assets, origin, conversación y PG reload | No en alcance local |
| Frontend/browser | PASS focalizado | check/build, 41 PASS/2 skips | No en alcance probado |
| Console/Auth contracts | PASS fixture | 51 tests, bootstrap/me/entitlements | No como fixture |
| Identity/RBAC DB | EVIDENCE_BLOCKED_BY_MISSING_FIXTURE | BLOCKED_BY_MISSING_AUTHORIZED_IDENTITY_FIXTURE | Sí, no defecto |
| Segundo tenant DB | EVIDENCE_BLOCKED_BY_MISSING_FIXTURE | BLOCKED_BY_MISSING_SECOND_TENANT_FIXTURE | Sí, no defecto |
| Scheduler business/delivery destino | NOT_TESTED | lifecycle/tests; no safe target/dry-run | Sí evidencia/control destino |
| DEV/bootstrap exposure | TECHNICAL_DEFECT / EXPOSURE_RISK | production-env DEV 201, unauth token fixture | Sí; guard/ingress no demostrado |
| Gupshup ingress | EXPOSURE_RISK conditional | source sin firma, ignored probe seguro | Sí si públicamente habilitado |
| LiteLLM | READY en alcance auditado | upstreams/empty fallback/adapter errors/real stack | No; live failure no requerido |
| Messaging coexistence | PASS | 167 tests y HTTP seguro | No con transportes deshabilitados |
| Gmail/Evolution/Gupshup delivery | CONDITIONAL/NOT_REQUIRED | no destinatario fixture autorizado | No fuera del runtime obligatorio |
| PostgreSQL/Milvus | READY | preflight y uso real fechado | No |
| Telchi/SAP/HANA | NOT_REQUIRED | no API global, cero consultas | No |
| Cleanup | PASS | pools/tasks/sesiones/listeners/temp venv cerrados | No |

## Validaciones, cleanup y decisión

Los conteos de ejecución tienen solapamiento; no son tests únicos. Los fallos de harness/assertions previos se conservan y no se confunden con defectos funcionales de Flow/Diagnosis.

- Final backend: principal 951 PASS / 3 skips; ampliada/adapters 798 PASS / 10 skips; harness/launcher 16 PASS. Total de ejecuciones finales 1765 PASS / 13 skips, no únicos. Harness incluye dos tests launcher ya contados en Srv05.
- Skips backend: dos Flow opt-in, un post-close PG (persist/reload real cubierto por stack), diez Diagnosis PG/repository opt-in sin URL fixture. No activar suites externas de escritura/transporte.
- Browser final 41 PASS / 2 skips. Primeras assertions browser fallidas y primeros listener cleanup sin evidencia se conservan; última versión/regresiones/lifecycle PASS.
- LAT md/index/sections/code-refs/full y git diff --check: ver final-validation.json y lat-gates.log. No declarar PASS global si falla un gate.
- [Cleanup](cleanup.json): cuatro sesiones browser exactas eliminadas/0 restantes; Full Gate limpia además sus dos UUID según reporte propio. Pools/scheduler/tareas cerrados; PIDs propios 79017/80040/80274/84545, Astro sesión 80059/Node 80175 y installed Uvicorn 84402 ausentes. Puertos 3050/7050 libres. Venvs temporales eliminados; evidencia/wheels/build DEV retenidos.
- Diffs tracked fuera de paths propios idénticos al inicio; untracked ajenos no editados ni atribuidos. Ningún reset/clean/restore/stash/checkout/add/commit/push ni lockfile edit.
- Side effects evitados: cero Gmail/WhatsApp/Evolution/Gupshup, migraciones/SAP/corpus/tenants/bindings/config persistente/servicios administrados/deploy. Sólo estado sintético Diagnosis y cleanup; LiteLLM sí consume cuota mínima real.
- Archivos propios: backend/pyproject.toml; backend-dev.sh (sólo perfil opt-in); backend/scripts/validate_srv05_wheel.py y srv05_e2e_runtime.py; backend/tests/test_srv05_packaging_harness.py y test_srv05_e2e_launcher.py; astro/e2e/srv05-safe-runtime.spec.ts; docs/status_actual.md, team360_full_gate_v1.md y team360_srv05_promotion_readiness.md; evidencia nueva bajo este directorio.
- Blast radius: packaging afecta todos los imports instalados, regresión amplia ejecutada; launcher conserva camino normal testeado. Scripts/harness/E2E test-only, sin cambios en consumidores productivos. Documentación GLOBAL únicamente estado/decisión/reproducción; diffs ajenos preservados.
- Full Team360 Gate: TEAM360_FULL_GATE_DEGRADED, agregación original intacta. Readiness: BLOCKED por ausencia de guard en superficies reproducidas, no por packaging. No elegible para revisión de promoción; no deploy/reemplazo Srv01.
- Acción humana mínima: autorizar ventana específica de guards/ingress y frontera de autenticación bootstrap (sin reabrir lógica Diagnosis), designar identidad y segundo tenant oficiales de test existentes, y decidir política de automatización destino. Luego revalidar boundaries y readiness; no solicitar envío real si delivery no es obligatorio.

TEAM360_SRV05_PROMOTION_READINESS_BLOCKED

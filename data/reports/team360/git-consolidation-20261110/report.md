# Consolidación Git Team360 — 10/11/2026

Base DEV recuperable de ambos agentes, sin implementar las dos conexiones TelchiAI pendientes ni certificar runtime productivo.

## Alcance y recuperación

Rama `feature/console-backend-core`; HEAD inicial local y remoto `1f75959f8c208b29ae3346100f43d09521c3f54b`, confirmado mediante fetch y ls-remote. No hubo divergencia inicial ni cambios staged previos.

- Snapshot inicial: 57 archivos tracked modificados y 679 archivos nuevos; 736 archivos con cambios en total.
- Respaldo privado: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/team360-git-backups/20261110T123919Z/`.
- `repository.bundle` y `repository-with-reflogs.bundle`, verificados con `git bundle verify`, preservan historia, refs y revisiones alcanzables desde reflogs, incluidos stashes preexistentes. Ningún stash fue aplicado o eliminado.
- `worktree.tar` conserva todos los archivos tracked y untracked no ignorados del snapshot; patches binarios, índice, refs, inventario y SHA-256 permiten reconstruir el estado Git en un directorio separado. Los roots privados/datos no se sobrescriben. Los ignorados no se incorporan ni limpian; `.astro` y `dist` preexistentes se respaldaron separadamente antes de check/build. Las validaciones pueden regenerar caches ignoradas de herramientas.
- El inventario detallado inicial, hashes, trazas de edición y logs de validación están en ese respaldo, no en GitHub. La lista exacta publicada se obtiene con `git show --name-status` sobre el commit que contiene este informe.

## Aportes y solapamientos

La atribución usa llamadas de edición exitosas y sus resultados en registros de sesiones, más comparación de bloques con el contenido actual. El timestamp de un archivo no decide precedencia ni corrección.

Se identificaron 879 registros de edición/escritura exitosos sobre paths del snapshot desde el checkpoint, procedentes de `openai-codex/gpt-6.1-sol` y `openrouter/@preset/ds41-flash-alibaba`. Son identidades de ejecución registradas, no autoría humana inferida; el inventario no pretende cubrir herramientas o sesiones no observadas.

Los 18 paths no pertenecientes a reports con aportes registrados de ambos modelos son:

- `assistant/commercial_answer.py`, `assistant/commercial_continuity.py`, `assistant/handler.py`, `assistant/luna.py`.
- `assistant/result_references.py`, `assistant/state_engine.py`, `assistant/tests/test_research_fallback.py`, `assistant/tests/verify_l01_population.py`.
- `console_http.py`, `datalake/commercial_line_amount_by_query.py`.
- `exploratory_sql/adaptive_research.py`, `exploratory_sql/ask.py`, `exploratory_sql/ask_verifier.py`, `exploratory_sql/console_bridge.py`.
- `exploratory_sql/test_coverage_label.py`, `exploratory_sql/test_executed_presentation.py`, `research_port.py`, `status_actual.md`.

Todos son relativos a `SrvRestAstroLS_v1/backend/modules/telchi/`. No hay conflictos de índice ni marcadores de merge por resolver. El contenido de implementación consolidado coincide byte a byte con el snapshot respaldado; esta tarea solo agrega documentación de consolidación y actualiza los dos estados.

## Precedencia y versiones sustituidas

Se conserva la integración local verificable, no una restauración completa del archivo de uno de los agentes. Ningún aporte independiente se elimina para favorecer al otro.

| Superposición histórica | Evidencia verificable y decisión |
| --- | --- |
| Montaje Telchi en registry central frente a runtime independiente | Sesiones del 04–05/11 documentan la transición a `dev_app.py`, proxy específico y launcher `telchiai-only`; registry central permanece igual a HEAD y su test exige ausencia de rutas Telchi incluso con flag. No se recupera el montaje central anterior. |
| Recuperación de población y continuidad frente a cambios posteriores de semántica | Sesión DeepSeek `2026-11-09T20-36-26-309Z_01a1c206-c645-7376-9827-689400aa55d0` aporta paginación y recuperación durable. Sesión GPT `2026-11-09T21-22-15-785Z_01a1c230-ba67-77cd-9986-392c7a205c0c` agrega cierre semántico OR y separa cobertura de certificación empresarial. Ambas contribuciones permanecen, con sus tests. |
| Fallback restringido anterior frente a investigador como ruta primaria fuera del fast path representable | Sesión GPT `2026-11-09T22-59-09-023Z_01a1c289-6e5e-77cd-9986-39324c018a7b` registra cambios posteriores en handler, intérprete, contratos y tests. Se conserva esa implementación local, sin borrar autorización, fast path ni recuperación aportados antes. |
| Presentación y cobertura frente a evidencia temporal posterior | Sesión GPT `2026-11-10T01-21-55-738Z_01a1c30c-2618-77cd-9986-3935579dcd61` registra ajustes DATE/TIMESTAMP posteriores en investigador/verificador y su regresión. Se conservan junto con la recuperación de población. El reporte de esa sesión mantiene selección de fuentes discrepantes pendiente; no acredita generalización. |

Estas versiones anteriores se consideran sustituidas donde los registros muestran evolución del mismo mecanismo. No se ejecutó un descarte adicional de código durante la consolidación, ni se reconstruyeron versiones hipotéticas a partir de fechas. Historia Git, respaldos y registros locales permanecen recuperables.

## Archivos publicados y exclusiones

Se consolidan 162 archivos de código, tests, launchers y documentación preexistentes, tres dependencias de regresión revisadas y este informe (166 archivos). Incluyen Foundation/publicación y CxC, investigación SQL, recuperación/continuidad conversacional, frontend TelchiAI DEV, herramientas Evolution y aislamiento del runtime central.

- Se excluyen del commit 571 de los 574 archivos nuevos iniciales bajo `data/reports/telchi/`: contienen evidencia empresarial/SAP, auditorías, salidas live, capturas, logs, locks y scripts operativos ligados a ejecuciones concretas. Se preservan íntegros en disco y en el respaldo; excluir no significa invalidar ni eliminar trabajo.
- Se incluyen tres dependencias de regresión revisadas: `l01-population-closure-v1/reconciliation.json` (contadores/estados de verificación, sin cuentas ni importes), `presidencia-sourcepolicy-v1/matrix.csv` (contratos y permisos propuestos, sin registros SAP) y `stock-production-october-v1/finalize_publication.py` (source inspeccionado estáticamente por un test). Son metadata/source reproducibles, no dumps SAP, secretos ni salidas temporales. No se ejecuta el runner ni se activan los permisos propuestos.
- No se incluyen credenciales, configuraciones privadas, bases de datos, Parquet, dumps ni artefactos temporales nuevos. Las fuentes de herramientas, tests y validadores reproducibles dentro del módulo sí se preservan.
- Los stashes históricos de Knowledge no se incorporan a esta rama: su propósito registrado es el rescate hacia la rama documental correspondiente, ajeno a TelchiAI.
- Los enlaces preexistentes a evidencia nueva excluida describen evidencia disponible localmente, no disponibilidad de esos archivos en GitHub. No se publica su contenido ni se convierte en una certificación nueva.
- El escaneo de los 162 archivos fuente/documentales detectó solo el literal de test `fixture-key`; revisión manual confirma fixture sintética, no credencial operacional. Escaneo por patrones más revisión no garantiza ausencia universal de secretos.

## Validaciones

Las pruebas son regresiones aisladas con fixtures, no demostraciones empresariales ni WhatsApp externo. No se modificó comportamiento funcional para obtener resultados verdes.

Comandos backend desde `SrvRestAstroLS_v1/backend`, mediante `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --no-sync pytest -q`:

| Selección / comando | Resultado observado |
| --- | --- |
| `modules/telchi/assistant/tests`, `test_console_http.py`, `test_dev_app.py`, `test_research_port.py`, `test_research_recovery.py`, test del actualizador Meta y `tests/test_module_registry.py` | 1.111 PASS, 4 SKIP, 9 subtests PASS y 1 fallo de timeout de arranque del servidor sintético central. No se declara PASS de esa corrida. |
| `modules/telchi/test_dev_app.py::test_independent_process_restart_preserves_srv05_pid`, aislado y sin cambios | 1 PASS en 6,71 s; el timeout anterior no se reprodujo. No se atribuye una causa funcional no demostrada. |
| `modules/telchi/exploratory_sql` | 391 PASS en 143,71 s. |
| Foundation/CxC: 14 archivos focales bajo `modules/telchi/datalake/tests`, misma selección sobre tmpfs | 251 PASS, 1 SKIP en 169,29 s. |
| Tests nuevos de `devfull_free_pilot_v1`, `presidencia_sourcepolicy_v1` y `presidencia_sourcepolicy_final_v1` | 30 PASS en 1,46 s; fixtures, sin activación real. |

Otras validaciones ejecutadas:

- Desde `SrvRestAstroLS_v1/astro`: `pnpm check` → 0 errores, 0 warnings, 7 hints; `pnpm build` → 162 páginas construidas. Node v24.17.0 y pnpm 10.33.0 disponibles; el proyecto declara pnpm 11.5.0. No se actualizan herramientas ni lockfiles en esta consolidación.
- Desde `SrvRestAstroLS_v1`: `node --test backend/modules/telchi/test_dev_proxy.mjs` → 1 PASS; upstream sintético, cleanup propio, no E2E empresarial.
- AST Python de los 142 archivos fuente modificados/nuevos del snapshot: válido. `bash -n SrvRestAstroLS_v1/backend-dev.sh meta-webhook-update.sh whatsapp-dev.sh`: PASS.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check`: PASS sobre el worktree; los links a evidencia excluida pueden existir solo localmente, como se declara arriba. LAT avisa falta de init/key semántica, sin fallo de gates.
- `git diff --check`, `git diff --cached --check`, allowlist exacta de 166 paths y revisión de diff staged: PASS.
- La primera corrida combinada backend venció el timeout externo de 240 s; la primera ejecución de `pnpm check` venció el de 120 s. Se conservan ambos logs y no se acreditan como PASS. Se segmentó backend y se repitió check sin modificar código.
- La primera corrida Foundation/CxC quedó bajo bloqueo I/O de fixtures en disco. Se intentó detener únicamente el pytest propio con SIGINT y SIGTERM; sus controles convirtieron señales en errores y continuaron. Se terminó ese worker atribuible (sin hijos) con SIGKILL y se descartó toda la corrida como `ENVIRONMENTAL_ABORT`, no como PASS ni defecto funcional. Se repitió la misma selección con `--basetemp=/dev/shm/team360-consolidation-20261110`, sin cambiar código, assertions ni datasets. Logs originales preservados.

Preflight: 8 CPU, load inicial 1,58/2,30/2,42, ~5,5 GiB disponibles y swap inicial ~6 MiB. Se mantuvo un pytest por suite, BLAS/OMP=1, con hasta 9 threads nativos observados en Foundation; no hubo consumo sostenido de todos los cores. Se monitorizaron memoria, swap y disco; clasificación `BUSY_BUT_SAFE`, sin terminar procesos ajenos. La repetición tmpfs ocupó menos de 1 GiB y se eliminó su directorio propio al finalizar. No se ejecutaron PG opt-in, modelos reales ni browser E2E.

`RESOURCE_GUARD=PASS` en seguridad de recursos, no certificación funcional; `ENVIRONMENTAL_ABORTS=3` (dos timeouts externos y la corrida Foundation en disco); `UNRELATED_PROCESSES_TERMINATED=0`; `OWN_PROCESSES_LEFT_RUNNING=0`. El fallo inicial de startup se registra separadamente de estos abortos y solo su repetición aislada fue PASS.

## Límites y siguiente paso

La actualización de estados agrega únicamente el alcance Git y los límites de evidencia; no cambia CURRENT, permisos, SourcePolicy, presupuestos, modelos ni servicios.

- La inspección local `canonical-connections-inspection-v1/inspection.json` es parcial: integración de conocimiento canónico parcial, prueba funcional durable Inbox → Worker → Outbox pendiente y generalización empresarial no demostrada.
- Las observaciones de `source-temporal-20261109/result.json` no resuelven la selección de fuentes discrepantes. La consolidación no corrige ni oculta esa limitación funcional.
- Sin consultas SAP, llamadas Luna reales, envíos WhatsApp, deploy ni reinicios de servicios compartidos. Los servidores de prueba propios son sintéticos y temporales.
- Publicación: commit de consolidación con push normal a la misma rama, sin force. La comprobación final del HEAD remoto se informa en la entrega; este documento no certifica por adelantado una operación remota.
- Próximo paso funcional, solo después de la publicación verificada: continuar las dos conexiones TelchiAI mediante una tarea separada.

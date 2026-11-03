# Cierre offline Reference física y preparación SAP

Dictamen **PARTIAL** en `feature/console-backend-core`. Se completaron la caracterización del gate, el ensayo sintético y el runbook; no se autorizó ni ejecutó SAP, refresh compartido, publicación real ni commit.

## A. Test fallido y baseline

El fallo se reproduce antes y después: `test_productive_and_shared_static_scan_are_clean` termina con `UNCLASSIFIED_DIRECT_READS=2`, no con lectores productivos o shared inseguros.

| Referencia | Causa verificada | Clasificación |
| --- | --- | --- |
| `exploratory_sql/foundation.py:151` | Comentario que explica que no se usa acceso Atomic directo; la implementación obtiene relaciones mediante FoundationReader y verifica publication/snapshot | Falso positivo como lectura ejecutable; clasificación estática pendiente |
| `exploratory_sql/test_foundation.py:67` | SQL negativo de `test_denied_before_open`, que exige DENY y ninguna apertura de conexión | Fixture legítimo de seguridad, no vulnerabilidad demostrada |

El scanner usa regex por línea, incluidos comentarios y strings; fuera de su allowlist estas rutas quedan UNKNOWN. No se modificó scanner, test, comentarios, SQL ni allowlists para ocultar el resultado. `exploratory_sql/` preexistía como untracked al inicio y se preservó fuera del cambio Reference asignado.

[audit.json](audit.json) compara el scanner de HEAD `09d2ec715a31bb88574d734eacb9f437f008624e` contra el actual SOBRE EL MISMO worktree: las dos coincidencias son idénticas. Los archivos exploratory no existen en HEAD; por tanto no se afirma que HEAD limpio fallara. Es un problema preexistente del worktree, también documentado por el cierre anterior, no regresión de clasificación física.

La suite local de ese consumidor aprueba 24 tests, incluidos los seis SQL negativos rechazados antes de abrir conexión. Una solución futura requiere ownership de su integración con el inventario estático y evidencia acotada; no autoriza excluir el directorio ni ampliar globalmente allowlists.

## B. Ensayo integral y regresión

Todos los datos del ensayo son sintéticos en tmp_path. El nuevo test usa `run_reference_update(source=simulated)` para recorrer la extracción de cinco llamadas simuladas y el builder real, no sólo helpers de clasificación.

| Garantía solicitada | Resultado y evidencia |
| --- | --- |
| Seis códigos oficiales | PASS: diccionario y persistencia en reader integrado |
| Ausentes, nulos e inválidos | PASS: MISSING/UNKNOWN; blancos y códigos mal formados en regresión |
| canonical_product_id estable | PASS: mismos IDs source-scoped antes/después |
| product_crosswalk íntegro | PASS: igualdad de filas e identidad; rechazo de remapeo |
| Clasificación comercial conservada | PASS: CURATED_SYNTHETIC preservada en flujo integrado |
| Sólo U_FormaFarmac cambiado | PASS: siete productos cambian entre nueve, sin cambios comerciales |
| NOOP sin cambios | PASS: nueva captura simulada no crea versión |
| Nueva versión con atributo cambiado | PASS: cambio de content/version determinístico |
| Ocho componentes | PASS: Reference cambia; Sales, Credit Memo, OINM, OITW, Material Supply, Receivables & Collections y Purchasing permanecen exactos |
| Versiones y snapshots | PASS: hash anterior intacto, manifest anterior intacto, base_snapshot_id=84 preservado |
| FoundationReader compatible | PASS: lectura de products/clasificación y snapshot fijado, aunque resolver devuelve 999 |
| Rollback | PASS: rollback lógico aislado y protección compare-and-swap |
| Interrupción antes/durante publicación | PASS: DURING_VALIDATION, AFTER_REFERENCE, BEFORE_LOGICAL_COMMIT, DURING_LOGICAL_COMMIT; anterior único y reintento seguro |
| Idempotencia | PASS: builder y publicación NOOP al repetir |
| Publicaciones anteriores | PASS: manifest de cinco componentes y lectura/historia de ocho |
| Facts sin cambios | PASS: siete entradas no Reference exactas y mismo snapshot; no se ejecuta extractor/escritor de facts |
| Dependencias incompatibles | PASS: rechazo de cambio comercial/schema/identity/crosswalk/physical/Purchasing y delta facts con derivados sellados |

La recuperación adicional interrumpe la copia real hacia carpetas inmutables Reference y crosswalk. El pointer anterior permanece byte-a-byte intacto; reintentar con destino parcial falla cerrado, sin activar versiones incompletas. Tras cuarentena SÓLO del destino sintético se repite desde fixtures y termina en NOOP. No se promete recuperación automática de una carpeta parcial real.

La interrupción AFTER_LOGICAL_COMMIT tiene otra semántica: la nueva publicación completa ya está vigente, con ocho componentes; repetir es NOOP. No se afirma que el CURRENT anterior siga vigente después de un commit exitoso. El rollback posterior sólo se ensayó en memoria.

Resultados finales verificables:

- Suite Data Lake completa: **507 PASS / 1 FAIL / 0 SKIP**, 508 casos, 38,68 s. Único fallo: el scan anterior. [JUnit](datalake.xml), [log](datalake.log).
- Regresión consumidor exploratory Foundation: **24 PASS / 0 FAIL / 0 SKIP**, 111,10 s. [JUnit](exploratory.xml), [log](exploratory.log).
- Primera focalizada: **37 PASS**, antes de agregar los dos tests de interrupción física; estos dos pasan dentro de la suite completa final. [Log](focused.log).
- Comando de captura preparado: syntax compile PASS, NO ejecutado. Hashes y comparación de baseline: [audit](audit.json).
- LAT: `md`, `index`, `sections`, `code-refs`, completo: PASS en logs `lat-*.log`. Avisos no bloqueantes: init/key semántica ausentes; no se configuraron.
- `git diff --check`: PASS; revisión de los dos archivos nuevos realizada. No hay cambios de código runtime en esta tarea.

El primer intento de la regresión exploratory fue interrumpido por timeout del harness a los 60 s, tras 11 puntos de progreso, sin fallo lógico demostrado. Se verificó ausencia de workers propios antes de repetir con presupuesto 240 s; esa ejecución terminó en PASS. ENVIRONMENTAL_ABORT=1, no se ocultó mediante cambios de código.

## Reproducción segura de pruebas

El plugin de la corrida bloquea socket.connect/connect_ex/create_connection y sustituye hdbcli por un driver que falla al conectar. No modifica políticas de producción ni se instala en el repositorio runtime.

Se conserva como [offline_guard.py.txt](offline_guard.py.txt). Para reproducir, copiarlo como `offline_guard.py` a un directorio temporal nuevo y usarlo en PYTHONPATH. La ejecución final utilizó `/tmp/team360-offline-lidqdv` y estos comandos desde `SrvRestAstroLS_v1/backend`:

```bash
PYTHONPATH=/tmp/team360-offline-lidqdv:$PWD TEAM360_TELCHI_DATA_ROOT=/tmp/team360-offline-lidqdv/isolated-data PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --no-sync pytest -q -p no:cacheprovider -p offline_guard modules/telchi/datalake/tests --junitxml=../../data/reports/telchi/physical-reference-offline-close/datalake.xml
PYTHONPATH=/tmp/team360-offline-lidqdv:$PWD TEAM360_TELCHI_DATA_ROOT=/tmp/team360-offline-lidqdv/isolated-data PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --no-sync pytest -q -p no:cacheprovider -p offline_guard modules/telchi/exploratory_sql/test_foundation.py --junitxml=../../data/reports/telchi/physical-reference-offline-close/exploratory.xml
```

No se ejecutaron runners SAP. Los tests nuevos además impiden construir HanaReadOnlySource. El Data Root env no se considera sandbox universal: las pruebas usan conexiones DuckDB de memoria/fixtures y el guard bloquea la ruta hdbcli nativa.

## CURRENT compartido y recursos

No se abrió el catálogo Foundation real ni se ejecutó ningún publisher compartido. Todas las transiciones CURRENT/rollback descritas pertenecen al store sintético, nunca al real.

Los 23 archivos observados bajo manifests compartidos mantienen los mismos hashes antes/después: [antes](shared-manifests-before.sha256), [después](shared-manifests-after.sha256), `cmp` PASS. Esto acredita los archivos observados; no se consultó PostgreSQL para afirmar un valor actual de Foundation ni descartar modificaciones de terceros. Esta ejecución no modificó CURRENT real.

Host observado: 8 cores, load aproximadamente 4–6, memoria disponible aproximadamente 7,8 GB, swap sin crecimiento apreciable; CPU libre pero iowait alto. Presupuesto conservador: un pytest, ningún xdist, DuckDB del builder/fixture con 2 threads, librerías numéricas 1; suites secuenciales, sin scans de facts ni browsers.

```text
HOST_PREFLIGHT=BUSY_BUT_SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 pytest; 2 threads DuckDB builder/fixture; 1 numérico
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=1 (timeout del harness, reejecutado con éxito)
OWN_PROCESSES_LEFT_RUNNING=0
```

Se verificó la lista de procesos al terminar: ningún pytest/python propio restante; el uv ajeno preexistente no se tocó. No se reinició servicio, Podman ni VPN.

## C. Preparación SAP

El [runbook](../../../../SrvRestAstroLS_v1/backend/modules/telchi/datalake/PHYSICAL_REFERENCE_SAP_RUNBOOK.md) contiene comandos reales preparados, CWD, variables sin secretos, columnas completas y contingencias. No se ejecutó ninguno de sus comandos operacionales.

Resumen: cinco SELECT / cinco conexiones secuenciales, máximo una activa, cuatro maestros OITM/OCRD/OWHS/OSLP, joins CUFD/UFD1 existentes. Sin COUNT adicional, extracción de facts ni retries automáticos. Falta timeout/cancelación explícitos, no hay snapshot multi-query, y cifrado del adapter actual está desactivado: el owner debe aceptar/verificar el canal privado antes de cualquier autorización remota.

Captura preparada mediante `extract_from_sap` y marcador de integridad; construcción posterior vía `--fixture-dir` contra copias aisladas. Foundation se mantiene intacta. Publicación posterior mediante API existente, no CLI inventado. El wrapper de lock/guard, instalación inmutable y reconciliación de dos pointers sigue pendiente; el runbook no simula que exista.

## D. Archivos de esta tarea

Sólo se agregaron dos archivos del módulo y evidencia local. Todos los archivos modificados/untracked preexistentes se preservaron, sin commit, staging ni formateo global.

- `SrvRestAstroLS_v1/backend/modules/telchi/datalake/tests/test_physical_reference_end_to_end.py`: tres tests nuevos, uno integral y dos de recuperación de copia inmutable.
- `SrvRestAstroLS_v1/backend/modules/telchi/datalake/PHYSICAL_REFERENCE_SAP_RUNBOOK.md`: procedimiento preparado y límites explícitos de la operación futura.
- `data/reports/telchi/physical-reference-offline-close/`: este reporte, auditoría, JUnit/logs, guard reproducible y hashes compartidos. Los archivos de evidencia no representan publicaciones del Data Lake.

Impacto transversal: ninguno en contratos/runtime de otros módulos. Se valida un consumidor offline existente sin editarlo. No se alteran políticas ni índices LAT/GLOBAL.

## E. Dictamen y autorización faltante

**PARTIAL**, no PASS OFFLINE global: persiste el gate estático preexistente; además la futura operación compartida no tiene wrapper completo seguro ni credenciales/conectividad acreditadas.

1. Código preparado para incorporar clasificación física: **sí en el alcance offline validado**, con rechazo conservador de incompatibilidades; suite global no totalmente verde.
2. Extracción futura segura/verificable: **procedimiento preparado, no acreditado en vivo**. Requiere ventana única, credenciales vigentes, aceptación del canal y límites/cancelación acordados; cinco SELECT, no sólo OITM.
3. Reference sin afectar ocho componentes: **demostrado sintéticamente para cambios compatibles**. La compatibilidad del candidato real y la orquestación operativa aún deben validarse; no publicación incondicional.
4. Falta autorización concreta: primero lectura HANA acotada de los cuatro maestros; por separado instalación/activación Reference y publicación Foundation compartidas tras revisión del candidato y cierre del wrapper/guard. Rollback real y cambios de credenciales/infraestructura requerirían autorizaciones propias.

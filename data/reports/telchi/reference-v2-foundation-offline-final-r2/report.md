# Reference V2 y Foundation — cierre offline

Candidata física real, aislada y sin publicación. Rama `feature/console-backend-core`; evidencia del 29/10/2026. El dictamen y los resultados finales legibles por máquina están en [report.json](report.json) y [gates.json](gates.json).

## Dictamen y alcance

**PASS del alcance offline**: construcción, compatibilidad del candidato real, regresiones pertinentes y gates LAT aprobados. No equivale a publicación ni a certificación del CURRENT vivo: no se abrió HANA, PostgreSQL ni el catálogo DuckLake compartido.

La candidata conserva el universo Reference completo y pasa compatibilidad contra la Reference y el manifest Foundation reales previamente acreditados. Las identidades no conciliables quedan explícitamente pendientes; no se inventaron altas ni correspondencias.

## Capturas y consolidación

Se verificaron los dos checkpoints autorizados, las respuestas selladas, el orden de ItemCode, los hashes, el plan de solicitudes, la partición de respuestas y la ausencia de journals/intenciones pendientes.

- Original: checkpoint `7b8bbb992fcb83e3d0ec4ae4951084fad90fa12e5c7761ce0f408bf9b7b69099`; 10.000 identidades encontradas.
- Selectiva final: checkpoint `efac34ab7ae8492dbd748d652ad734ceb8ebe902d1eafbc9f03a851969851245`; 3.242 solicitadas, 3.199 encontradas y 43 NOT_RETURNED.
- Universo operativo: **8.001** claves únicas; **7.958** encontradas; **43** NOT_RETURNED; **0** pendientes de captura.
- Capturas encontradas fuera del universo operativo: **5.241**; conservadas como evidencia, no usadas para ampliar el enriquecimiento autorizado.
- Se verificaron 28 roots de la cadena selectiva y la captura original, antes/después, sin escrituras ni recuperación sobre fuentes. Se reutilizaron los lectores de checkpoint y ledger existentes.
- Consolidado lógico: SHA-256 `63c915b39dceeac998547e933e2da9aa362fe0331c7f8e27da251ee65e293cb3`.
- Archivo consolidado: SHA-256 `819e0b6ca19e34a53e8db967f78d5770ab6554aba067482a44eb104ffa0598f2`.

El consolidado nuevo está en `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-reference-offline-63c915b39dceeac998547e93-r2/consolidated.json`. Su identidad depende del contenido, no del sufijo de intento. La inmutabilidad es lógica y verificable por hashes; no se cambiaron permisos ni se sobrescribieron capturas.

## Conciliación de identidades

La conciliación usa claves SAP exactas, sin trim, similitud, descripciones ni matching canónico inventado. El detalle está en [identity-reconciliation.json](identity-reconciliation.json).

| Conjunto independiente | Cantidad | Resolución |
| --- | ---: | --- |
| Operativas existentes en Reference | 7.958 | Enriquecidas con observación acreditada |
| SAP encontradas ausentes de Reference | 0 | Ninguna alta estructural pendiente por esta causa |
| NOT_RETURNED | 43 | No significa eliminación; no genera clasificación |
| Operativas históricamente ausentes de Reference | 43 | Pendiente identidad maestra/canónica acreditada |
| SAP Reference fuera del universo operativo | 8.976 | Preservadas íntegramente |
| Reference no SAP | 36.458 | Preservadas, sin backfill legacy |

Los dos conjuntos de 43 se compararon por sus claves reales: **intersección 43, sólo ausentes 0, sólo NOT_RETURNED 0**. La igualdad es un resultado verificado, no una premisa. Las claves M/R/S completas y sus motivos permanecen en el JSON; no se crearon filas vacías para ellas.

Identidades encontradas bloqueadas por incompatibilidad: **0**. Identidades históricas pendientes de resolución específica: **43**, por falta de respuesta SAP y ausencia de identidad Reference acreditada.

## Distribución física definitiva

Se conservan código original, etiqueta contractual oficial, estado físico, estado de clasificación, fuente y timestamp acreditado de cada batch. Sólo 1, 2 y 3 determinan un estado físico.

| Código | Etiqueta | Productos | Estado físico |
| --- | --- | ---: | --- |
| 0 | Ninguna | 6.642 | NULL |
| 1 | Líquido | 695 | LIQUID |
| 2 | Semisólido | 93 | SEMISOLID |
| 3 | Sólido | 490 | SOLID |
| 4 | Medicamento | 37 | NULL |
| 5 | No corresponde | 1 | NULL |

Total explícito: **1.278**. Nulos/desconocidos entre respuestas encontradas: **0**. Los NOT_RETURNED no se cuentan como código 0. No se infirieron estados físicos, fechas históricas ni efectividad de negocio; la captura es multisesión, no un snapshot transaccional SAP.

## Reference candidata

Se reutilizó `reference_update.prepare_physical_reference`, una entrada aditiva del productor existente que no activa pointers ni ejecuta el refresh completo de maestros.

- Base Foundation: `v2_reference_closure_2088d5885204313a`, no el pointer histórico divergente `v2_b19ceecf40d3ba09`.
- Productos totales: **53.392**; filas enriquecidas: **7.958**; preservadas sin cambios materiales: **45.434**, aparte de las nuevas columnas nullable.
- Versión candidata: **`v2_aabf716d342de26794c09797`**.
- Hash lógico Reference + crosswalk: **`aabf716d342de26794c09797c1e1fe6ff305c267982467242830059641076cc8`**.
- Root: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-reference-offline-63c915b39dceeac998547e93-r2/candidate/`.
- Reference: `reference/_versions/v2_aabf716d342de26794c09797`; crosswalk: `crosswalk/_versions/v2_aabf716d342de26794c09797`.
- Sellos físicos: `candidate-seal.json` en el root privado padre de `candidate/`; prueba de conservación: [reference-compatibility.json](reference-compatibility.json).

Se conservaron datasets, columnas y tipos anteriores, identidades, crosswalks, clasificaciones comerciales, relaciones, metadata y lineage. Todas las otras familias se copiaron byte por byte. El NOOP sobre la candidata real fue revalidado con el código final; el replay no activa pointers ni reemplaza fechas selladas.

## Compatibilidad Foundation y ocho componentes

Se validaron contratos reales y el candidato real contra `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, usando su manifest acreditado y el ancestro original sellado. No se crearon componentes ficticios.

| Componente real | Resultado |
| --- | --- |
| Reference | COMPATIBLE_PHYSICAL_ONLY |
| Sales | PRESERVED_EXACT |
| Credit Memo | PRESERVED_EXACT |
| OINM | PRESERVED_EXACT |
| OITW | PRESERVED_EXACT |
| Material Supply | PRESERVED_EXACT, resolver existente |
| Receivables & Collections | PRESERVED_EXACT, resolver existente |
| Purchasing | PRESERVED_EXACT, datasets/algoritmo/dependencias existentes |

Se preservaron identidad, schemas, registry de datasets, dependencias, versiones, referencias, snapshots y componentes derivados. Se verificaron hashes de 13 archivos de datasets derivados declarados. Los siete componentes no Reference mantienen exactamente sus entradas originales; no se extrajeron ni reconstruyeron facts.

La validación offline no recompone fingerprints de tablas DuckLake sin export del catálogo. Se conserva la evidencia acreditada y las dependencias exactas; el verifier físico de facts del reader se inyectó expresamente en la simulación local. No presentar esa inyección como lectura de facts reales. Esta limitación no impide demostrar que una actualización aditiva de Reference conserva sus contratos y snapshots.

## Defecto corregido de snapshots

La candidata real reveló que el snapshot de datos del reader es **1408**, mientras `base_snapshot_id` de las derivaciones es **1322**. Los fixtures previos usaban el mismo número para ambas funciones y ocultaban el defecto.

Causa raíz: la ruta Reference-only fijaba las relaciones Atomic al `base_snapshot_id` en vez del snapshot de datos anterior. Se añadió `reference_data_snapshot_id`, conservando por separado el snapshot de derivación y validando los refresh encadenados. Sin connector se exige un snapshot explícitamente acreditado; con connector se obtiene por el reader canónico y se comprueba la identidad CURRENT.

Regresión permanente: `test_reference_refresh_snapshot.py` cubre snapshots distintos, selección exacta del reader y rechazo de valores faltantes/inválidos. Una mutación local del método, en un proceso separado y sin editar source, reprodujo el fallo anterior exacto: `84 != 1408`; el XML de fallo esperado se conserva. El primer harness de mutación tenía un root congelado incorrecto, se corrigió y su fallo también se conservó. La simulación real acredita **1408/1322** preservados. No se migraron manifests compartidos ni versiones históricas.

## Publicación, recuperación y lectores simulados

Todas las operaciones de publicación usaron metadata DuckDB local aislada, sin DuckLake, PostgreSQL ni CURRENT compartido. Los manifests originales y la candidata sellada permanecieron intactos.

- Preparación y validación previa: PASS.
- Interrupción de copia inmutable/preparación: PASS con fixtures, sin reparar ni sobrescribir destinos parciales.
- Fallos de validación, selección Reference, precommit y commit: PASS sobre candidata real; CURRENT anterior íntegro.
- Interrupción postcommit, recuperación y reintento NOOP: PASS sobre candidata real.
- Rollback compare-and-swap: PASS; reader ya fijado conserva su snapshot.
- Dos candidatas concurrentes, CURRENT cambiado y rechazo de la stale: PASS sobre metadata del candidato real.
- Lectores preparados/nuevos/fijados intercalados: PASS; nunca se observó una Foundation parcial.
- Registry Reference incompleto: rechazo explícito sobre fixture aislada asociada a la candidata real.
- Componente desconocido: rechazo explícito, sin descartarlo del manifest local.
- Incompatibilidades semánticas, identidad, schema, crosswalk y contrato Purchasing: fixtures de regresión PASS.

Resultados adicionales: [real-candidate-additional-validation.json](real-candidate-additional-validation.json). El conjunto de garantías sintéticas no sustituye la proyección y validación realizadas sobre la candidata real.

## Tests, gate estático e incidencias

Las regresiones se ejecutaron secuencialmente, sin xdist, con bloqueo de sockets/HANA y guard de escrituras compartidas. Los resultados y comandos exactos de cierre están en [gates.json](gates.json).

La suite Data Lake completa más el test Foundation exploratorio aprobó **545 tests** en 63,73 s. Después se ejecutaron **2 PASS** focalizados del scanner, uno de ellos nuevo: **546 tests únicos** aprobados. Sin skips ni exclusiones de tests Data Lake.

El gate `test_productive_and_shared_static_scan_are_clean` fue reproducido fallando por dos falsos positivos: comentario del executor y SQL prohibido de una prueba negativa. Se corrigió el comentario y se clasificó únicamente `exploratory_sql/test_foundation.py` como TEST_ONLY. No se excluyó el directorio ni el executor; una regresión demuestra que el executor y sus siblings siguen detectándose.

Incidencias preservadas, no ocultadas:

1. Primer intento real: timeout local de 240 s, proceso propio terminado por el harness; artefactos conservados sin reutilizarlos como captura. Clasificación `ENVIRONMENTAL_ABORT`; el segundo intento completo terminó.
2. Primera regresión con guard: 12 intentos de crear el temp compartido bloqueados antes de escribir. Se configuró `TELCHI_DUCKDB_TEMP_DIRECTORY` aislado.
3. Segundo intento: 1 fixture comercial usaba un profile explícito que ignora ese env. Se aisló su temp mediante monkeypatch sólo en ese test; no se cambió el productor comercial ni se debilitó el guard.
4. Regresión completa posterior: 545 PASS; los XML de los intentos bloqueados se conservaron por separado.

## Preservación y recursos

El inventario de los **52.744 archivos compartidos** coincidió antes/después de la construcción y simulación. La comprobación final posterior a las regresiones está en [final-preservation.json](final-preservation.json): PASS también del sello físico y hash lógico de la candidata; no se escanearon facts completos para producir esta evidencia.

El hash físico original de products permanece `02e635f28ff91d42b7faadfe517d9c4f4d8c12fe41e6766f3f5d334346ee3c16`. Capturas: inventarios SHA-256 antes/después; datasets derivados: hashes declarados; otros snapshots: tamaño, mtime_ns e inode. El guard impidió escrituras compartidas, y no se abrió ningún catálogo compartido.

Host: 8 cores, load observado aproximadamente 0,5–1,3, memoria disponible 6,1–6,5 GB, iowait sostenido alto y swap final estable en unos 62 MB. Se mantuvo presupuesto conservador: un runner/pytest, DuckDB 2 threads, librerías numéricas 1; sin browsers ni suites simultáneas.

`HOST_PREFLIGHT=BUSY_BUT_SAFE`; `RESOURCE_GUARD=PASS` en las ejecuciones completadas; `UNRELATED_PROCESSES_TERMINATED=0`; `ENVIRONMENTAL_ABORTS=1`; `OWN_PROCESSES_LEFT_RUNNING=0`. Se verificó que no quedaron python/pytest propios; el uv preexistente se preservó. No se reiniciaron servicios, VPN ni Podman.

## Publicación futura controlada

Este procedimiento es una condición para una autorización futura; no es un comando listo para activar ni una autorización implícita. La publicación compartida y la resolución de las 43 identidades siguen separadas.

1. Obtener autorización explícita y ventana exclusiva de productores, con preflight de recursos.
2. Verificar los hashes de consolidado, candidata y crosswalk; no volver a consultar HANA.
3. Resolver y fijar CURRENT vivo con el reader canónico; comparar publicación, ocho componentes, versión Reference, snapshot de datos y snapshot de derivación con esta evidencia. Cualquier deriva bloquea y requiere revalidación.
4. Resolver explícitamente la divergencia del pointer histórico Reference; no sustituir la Reference enriquecida por el maestro anterior.
5. Preparar instalación inmutable en rutas finales sin sobreescritura, con registro durable y base esperada. Revalidar schemas, proyecciones, identidades, archivos y contratos existentes.
6. Usar `publish_reference_only` bajo lock/guard, con snapshot de datos canónico y compare-and-swap; conservar snapshots, siete componentes y versiones exactas. No extraer facts.
7. Comprobar CURRENT único, manifests completos, readers anterior/nuevo fijados y contenido instalado. Reconciliar el pointer Reference mediante el wrapper operativo durable todavía pendiente.
8. Si se interrumpe después del commit, inspeccionar estado antes de reintentar: una excepción no demuestra rollback. Reintento compatible debe ser NOOP. Rollback real requiere autorización y expected-current específicos.

No ejecutar `reference_update` de maestros ni `update.py --dry-run` para publicar esta candidata: esas rutas pueden conectar SAP. No está autorizada ninguna modificación de permisos, credenciales, Atomic, facts o snapshots compartidos.

## Archivos y límites de ownership

Se modificaron únicamente paths Telchi asignados y sus reportes. El diff preexistente de la rama se conservó, sin operaciones de index, commits ni cambios GLOBAL.

- Productor y contratos: `datalake/reference_update.py`, `update.py`, `foundation_manifest.py`, `foundation_reader.py`, `foundation_reader_scan.py`.
- Tests existentes: `test_physical_reference_offline.py`, `test_physical_reference_end_to_end.py`, `test_product_commercial_semantics.py`.
- Tests nuevos: `test_physical_reference_candidate.py`, `test_reference_refresh_snapshot.py`, `test_foundation_static_scope.py`.
- Comentario sin cambio funcional: `exploratory_sql/foundation.py`.
- Documentación local: `PHYSICAL_PRODUCT_CLASSIFICATION_V1.md`, `PHYSICAL_REFERENCE_SAP_RUNBOOK.md`.
- Orquestación/evidencia: `investigation/validation/physical_reference_candidate_v2/` y este directorio de reportes. La orquestación importa productores existentes; ningún código productivo importa runners investigativos.

## Riesgos y decisiones pendientes

La candidata queda lista para evaluación de publicación, no para activación automática. No se requiere otra fase de captura para completar este trabajo offline.

- Confirmar CURRENT vivo y sus fingerprints en la futura ventana autorizada; aquí se acreditó sólo el snapshot congelado.
- Mantener separadas las 43 identidades históricas pendientes y el concepto NOT_RETURNED, aunque sus claves coincidan en esta captura.
- El pointer Reference histórico diverge del Foundation acreditado; hace falta un wrapper durable de instalación/publicación/reconciliación, no otro motor Reference.
- El nuevo contrato de snapshot del reader requiere desplegar código compatible antes de promover esta transición; las publicaciones históricas existentes no fueron reescritas.
- No hay nuevos endpoints, habilitación TelchiAI, deploy, commit, push ni impacto sobre otros módulos. Los cambios preexistentes del worktree se preservaron.

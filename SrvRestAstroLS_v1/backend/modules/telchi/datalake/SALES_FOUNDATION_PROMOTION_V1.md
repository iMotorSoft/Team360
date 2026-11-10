# Sales Foundation promotion V1

Runbook del wrapper durable, sin consultas SAP. La existencia de una candidata o un gate offline no autoriza activar CURRENT. El scheduler permanece deshabilitado.

## Autoridades y alcance

Se reutilizan los publicadores existentes; no se escribe CURRENT directamente ni se reconstruye Atomic. La instrucción del responsable del proyecto de publicar una candidata concreta es la autoridad; lo que debe quedar inequívoco es *qué* se publica, no una ceremonia nominal alrededor.

- [Contexto Telchi](../CONTEXT.md).
- [Publicación y reader canónicos](UPDATE_README.md).
- [Contrato extensible](FOUNDATION_EXTENSIBLE_MANIFEST_COMPATIBILITY_V1.md).
- [Evidencia final](../../../../../data/reports/telchi/sales-foundation-final-promotion-v1/report.json).
- Foundation candidata: `foundation_38680850adc058b1bb11887632b7b681`.
- Reference candidata: `v2_sales_e02883116f4b4991c396010a`; la candidata física `v2_aabf716d342de26794c09797` queda separada.
- Base esperada: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`.

## Preparación sin activación

Ejecutar desde backend, después del preflight de recursos y de comprobar ownership. El plan fija hashes, base, Reference previa, archivos y cortes; cualquier cambio posterior exige reconciliar, nunca sobrescribir una publicación ajena.

```bash
cd SrvRestAstroLS_v1/backend
DATA=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi
CANDIDATE="$DATA/staging/sales-continuity-recovery-v1.0.0/sales-foundation-release-20261030-v2/foundation-candidate.json"
JOURNAL="$DATA/staging/sales-foundation-final-promotion-v1/journal"
uv run python -m modules.telchi.datalake.sales_foundation_promotion prepare \
  --candidate "$CANDIDATE" --journal "$JOURNAL"
```

No modificar un journal ya preparado. Si CURRENT cambió, no reutilizar este plan: reconciliar contra el nuevo estado, producir una candidata validada y abrir un journal distinto. Las versiones previas no se borran.

## Autorización y promoción

El wrapper no exige una autorización nominal aparte. La instrucción del owner sobre esta candidata exacta es suficiente y el journal registra la operación automáticamente. Un campo `authorized_by`, una referencia externa o un ticket son trazas opcionales: se guardan si existen, nunca bloquean.

El binding técnico se valida contra el plan preparado (`candidate`, `base`, `manifest_sha256`, `reference`, `retained_component_cutoffs`): cualquier valor provisto que no coincida aborta con `EXACT_OPERATIONAL_AUTHORIZATION_REQUIRED`. Ejecutar una sola instancia:

```bash
uv run python -m modules.telchi.datalake.sales_foundation_promotion promote \
  --journal "$JOURNAL"
```

`--authorization` sigue disponible para adjuntar identidad o referencia; se archiva una vez y no condiciona la promoción. Repetir el comando sobre el mismo journal es idempotente aunque cambie la nota humana.

El wrapper comprueba hashes y manifiesto y adquiere los locks existentes. Prepara la Reference mediante el mismo publicador; Foundation sigue fijada a su versión anterior. `logical_commit(..., accredit=...)` valida el reader completo y persiste el recibo dentro de la misma transacción que selecciona CURRENT.

Un fallo de validación o persistencia revierte selección, estados y recibo. Los lectores concurrentes siguen viendo la aprobación anterior hasta el commit atómico. Una caída posterior al commit pierde como máximo el acuse: la nueva publicación ya está completa y el journal se recupera sin reacreditarla. La Reference de lectura sigue fijada por Foundation, nunca por el pointer independiente.

Los consumidores del pointer independiente incluyen `create_initial.py` y `update.py`; no ejecutarlos durante esta ventana. El publicador de masters comparte el nuevo lock/CAS. Scripts históricos de investigación no constituyen publicadores habilitados.

## Sucesoras Reference-only

El mismo wrapper admite `FOUNDATION_REFERENCE_REFRESH_V1`; no necesita otro motor de publicación ni cambia las dependencias selladas para simular una derivación nueva.

- Instalar primero la Reference y crosswalk inmutables completos, comprobando hashes; ninguna instalación cambia CURRENT. Preparar con `publish_reference_only(..., prepare_only=True)` reutiliza las validaciones canónicas y deja la candidata READY_TO_COMMIT.
- El artefacto de candidata conserva la fila serializada exacta del catálogo, incluido `component_hash`; el loader reconstruye sólo la metadata rica de Reference. Los componentes de ventas heredados conservan su representación catalogada y contrato original.
- Ejecutar `prepare --candidate <artefacto> --journal <journal-nuevo>` y después `promote --journal <journal-nuevo>` mediante este mismo CLI. Preparación y commit comprueban la base exacta; no escribir CURRENT manualmente ni reusar un journal de otra operación.
- La validación conserva ocho componentes, ledger, snapshots y archivos sellados. El reader conserva las relaciones de ventas/NC file-backed cuando la base es `SALES_FACTS_TRANSITION_V1`; no vuelve a Atomic histórico.
- La integración física publicada y el journal efectivo están en el [estado local](../status_actual.md) y su evidencia. Repetir `promote` sobre ese journal sólo reconcilia la misma publicación idempotentemente; rollback continúa siendo una operación explícita con motivo y expected-current.

## Contrato de publicación y actualización completa

La acreditación se almacena en `foundation_publications_v1.read_binding_json`, dentro del catálogo existente. No crea un registro paralelo, caché global, servicio ni infraestructura; el publicador incorpora la columna al asegurar su esquema.

1. Capturar sólo si existe alcance fuente autorizado; esta implementación no captura ni consulta SAP. Los productores existentes sellan archivos/versiones y conservan los anteriores.
2. Preparar candidata, manifiesto, cobertura por componente y journal; fijar base y hashes exactos. PREPARING/VALIDATING/READY_TO_COMMIT nunca autorizan lectura productiva.
3. Con locks y preflight, revalidar manifiesto, ancestry, Reference/crosswalks, archivos, hashes, conciliaciones y compatibilidad empresarial antes del CAS. No se elimina ningún gate completo del actualizador.
4. Preparar la activación Reference con el publicador existente. No adivinar el snapshot siguiente ni usar `MAX(snapshot_id)`. Antes de seleccionar CURRENT, la candidata READY_TO_COMMIT ya tiene un checkpoint durable.
5. Dentro de `logical_commit`, el reader explícito `full_validation=True` valida la selección aún no visible, los datos, las conciliaciones y la admisión comercial/física. Una conexión read-only independiente verifica la candidata exacta en el checkpoint preparado: DuckLake superpone escrituras propias incluso en time travel dentro de la transacción escritora.
6. Guardar el recibo y seleccionar CURRENT en esa única transacción CAS. Cualquier fallo anterior al COMMIT conserva la aprobación anterior. Los writers legacy no pueden sustituir una aprobación con recibo sin acreditación atómica; rollback a un target sin recibo se rechaza. Reentrada después del commit conserva los checks de integridad del plan y comprueba el recibo durable sin repetir el reader de acreditación.
7. El reader habitual sólo consulta metadata consistente en una transacción: pointer único, estado CURRENT único, componentes coherentes y recibo ligado a manifiesto/cobertura/cortes. Devuelve relaciones fijadas, publicación y fecha; no recorre snapshots/ancestry ni relee hashes Foundation/Reference.
8. Avanzar watermarks sólo después de publicación acreditada y los gates del consumidor. Un recibo no concede permisos: identidad, RBAC, workspace, datasets, columnas, filas, SQL read-only y auditoría siguen en sus boundaries existentes; Luna no puede sustituirlos.

| Campo del recibo | Contrato |
| --- | --- |
| `contract` | `foundation-read-binding-v1` |
| `foundation_publication_id` | Identidad exacta de la fila publicada |
| `commit_snapshot_id` | Recibo legacy: snapshot de selección CURRENT. Con `activation.protocol=atomic-current-receipt-v1`: checkpoint de preparación ya comprometido, igual a `activation.prepared_snapshot_id`; no representa el snapshot posterior de selección |
| `snapshot_id` | Snapshot de datos acreditado; puede ser anterior al commit de metadata |
| `manifest_sha256`, `components` | Manifiesto y descriptores/hashes físicos ya validados; se comprueba sólo su vínculo de metadata |
| `coverage`, `component_cutoffs`, `catalog_component_cutoffs`, `source_as_of` | Cobertura, cortes de todos los componentes del manifiesto y columnas fuente del catálogo; cortes ausentes siguen desconocidos, sin simular frescura integral |
| `reference_version` | Versión inmutable, nunca el pointer independiente más reciente |
| `validated_at` | Instante de emisión de la acreditación completa, separado de la fecha fuente |
| `commercial`, `physical` | Admisión comercial y hashes Reference físicos acreditados al actualizar |
| `receipt_sha256` | Checksum de metadata, no firma ni autorización del ejecutor |

Las relaciones Atomic usan `snapshot_id`; los facts sellados usan exclusivamente los paths de la versión aprobada y las derivaciones conservan su snapshot contractual. Ejemplo medido: commit 1506, datos independientes 1408, derivaciones históricas 1322.

El protocolo atómico separa el checkpoint acreditado del instante posterior de selección. No promete conocer por anticipado el ID de ese commit ni lo calcula sumando uno. El recibo y CURRENT se hacen visibles juntos; el snapshot de datos continúa independiente. Los recibos legacy conservan su significado original y no se reescriben.

## Migración sin modificar CURRENT

El código no migra ni reacredita una publicación antigua durante la lectura. Habilitar el reader rápido en un catálogo sin recibo requiere una operación de actualización/reacreditación explícita del publicador, no un fallback silencioso.

El cierre inicial del reader no escribió el catálogo. La inspección read-only posterior encontró un recibo preexistente para `foundation_42483d2e035e98e73e0a2d98ddc7d986`, emitido el 03/11/2026 a las 12:33:00 UTC. Esta corrección del publicador tampoco cambia CURRENT operativo ni publica CxC; la evidencia de cada operación distingue validación aislada de activación real.

El [benchmark read-only](../../../../../data/reports/telchi/foundation-read-binding-v1/benchmark.json) acredita igualdad sobre datos reales usando el recibo sólo en metadata efímera en memoria. No prueba migración viva, actor RBAC real ni arranque/conexión fríos.

## Recuperación y rollback

El journal registra intención antes del commit y conserva eventos inmutables. Repetir el mismo comando autorizado reconcilia el estado real aunque el proceso se interrumpiera antes de registrar el commit o la activación.

- Antes del commit atómico: la publicación anterior permanece efectiva, incluso si la preparación Reference ya avanzó. Reanudar únicamente con el mismo journal y sus pointers exactos.
- Después del commit atómico: CURRENT ya contiene su recibo completo. Verificar integridad de los inputs del plan y recuperar el acuse desde metadata; no repetir captura, commit ni reader de acreditación.
- Un CURRENT legacy sin recibo requiere reacreditación explícita del publicador: nunca se repara desde consultas normales ni se presenta como una activación atómica completada.
- Si existe otro run activo o un pointer distinto: rechazar y coordinar; no robar locks ajenos ni desactivar CAS.
- Un run propio interrumpido se recupera bajo el flock del mismo journal; no se roba un run distinto por antigüedad.
- El rollback necesita un motivo auditado y conserva la traza opcional si existía; no exige una autorización nominal previa. Verifica la base retenida, incluso si la candidata nueva quedó corrupta.

```bash
uv run python -m modules.telchi.datalake.sales_foundation_promotion rollback \
  --journal "$JOURNAL" --reason "Motivo operativo auditado"
```

El rollback aplica `logical_rollback` con expected-current y restaura el pointer Reference previo mediante CAS. Esto restaura el estado anterior completo, incluida su divergencia histórica independiente; el reader sigue fijado a la Reference de la Foundation restaurada.

Si el rollback se interrumpe, repetirlo con el mismo motivo. Un journal con intención de rollback no puede volver a promover: exige una preparación nueva. No se borran candidatos, snapshots, versiones ni journal.

## Verificación posterior y TelchiAI

La verificación del wrapper no equivale a `PUBLISHED_PASS`: falta acreditar el consumo conversacional real y los permisos efectivos del actor autorizado, sin impersonación ni cambios de grants.

- Resolver CURRENT y Reference nuevamente; verificar ocho nombres reales: `reference`, `sales`, `credit_memo`, `oinm`, `oitw`, `material_supply`, `purchasing`, `receivables_collections`.
- Reader completo del publicador sin snapshot inyectado: cobertura, conteos, importes documentales, conciliación contra raw y hashes; después, reader rápido con recibo persistido.
- Probar las siete preguntas comerciales solicitadas con identidad autorizada; rechazos de roles sin permiso deben conservarse.
- Septiembre completo: neto documental Bs 10.591.046,24. Octubre 1–29: Bs 10.811.322,92; no es un mes completo ni ingreso contable.
- Distinguir cliente facturado y comercial; rankings de líneas no son netos documentales; no inferir sucursal contable.
- Otros componentes conservan sus cortes históricos, sin refresh de compras, producción, inventario, cobranzas ni contabilidad.

## Sucesión incremental y acreditación comercial

La identidad de publicación cambia con el contenido; la compatibilidad empresarial se demuestra por el lineage canónico, no por una lista creciente de IDs permitidos.

`sales_succession.py` conserva las acreditaciones históricas como raíces de confianza. Sólo al actualizar recorre `base_foundation_publication_id` y valida hashes físicos. El wrapper comprueba admisión documental y física antes del CAS y acredita el consumo final; queries y proceso padre comprueban únicamente procedencia de metadata, sin reacreditar Foundation.

- `SALES_FACTS_TRANSITION_V1` exige plan incremental durable, base acreditada, ledger sin regresión, snapshot independiente conservado, schemas exactos y metadata empresarial heredada sin cambios. Nuevos documentos, modificaciones y cancelaciones acreditadas pueden cambiar los fingerprints.
- La validación canónica conserva ocho componentes, dependencias, identidades, crosswalks, hashes, sellados, conciliación y revalidación Material Supply. Una Reference append-only se prueba con los checkpoints locales del productor de maestros, sin acceso SAP durante la validación.
- `FOUNDATION_REFERENCE_REFRESH_V1` conserva los contratos de ventas y su snapshot. La admisión física heredada exige además preservar las observaciones físicas; un cambio de clasificación necesita acreditación explícita y no se acepta por similitud de columnas.
- La clasificación comercial conserva su versión y hash acreditados; una clasificación perdida, provisional o no renovada correctamente sigue rechazándose. Los permisos continúan resolviéndose por Console en cada turno, fuera del SQL; no se amplía ningún grant.
- El resultado de una publicación nueva se contrasta con el CURRENT real, snapshot, Reference, corte de ventas y cobertura. Una promoción concurrente provoca rechazo seguro, nunca mezcla de publicaciones. El padre no confía en un sello de compatibilidad autodeclarado por el worker.
- `source.updated_at` sigue siendo actualización Foundation; `source.sales_cutoff` procede de los checkpoints de ventas/NC, separado de la observación posterior de maestros. La cobertura de ventanas no convierte el día de captura ni noviembre en períodos completos ni constituye CDC.

Las acreditaciones legacy conservan su alcance original. Un cambio de schema, métrica, identidad, permisos, dependencia o semántica exige otro contrato explícito; no se acepta automáticamente. Continúa el límite canónico de ancestry de 32 niveles: no es una cadena ilimitada ni se elude el gate de futura consolidación.

## Próximos ciclos y scheduler deshabilitado

`sales_refresh_cycle.py` adapta el motor durable existente. No se programa cron ni se ejecuta SAP desde este cierre. La captura futura requiere una autorización de fuente y scope distinta de la autorización de publicación.

1. Resolver la Foundation efectiva y obtener `published_end` exclusivamente de su cobertura acreditada; no del último DocEntry ni de un checkpoint de captura.
2. Construir `make_plan(base=..., published_end=..., end_exclusive=..., authorization_reference=...)` con solape explícito de 1–14 días; como máximo 31 días distintos por ciclo.
3. Para cambios tardíos fuera del solape, aportar `late_dates` y `late_change_evidence` acreditada. No se afirma CDC ni completitud global de modificaciones; sin esa evidencia no inventar watermark.
4. Inyectar explícitamente la source autorizada en `capture(root, plan, source)`. Root: `DATA_ROOT/raw/sap/sales-refresh-cycle-v1/<cycle>`. Mantener presupuestos del motor, checkpoints, no retry automático de peticiones inciertas y reanudación del mismo plan.
5. Ejecutar offline `prepare_candidate(root, destination)` bajo `DATA_ROOT/staging/sales-refresh-cycle-v1/<cycle>`. Hace upsert de documentos completos, conserva historia, concilia cancelaciones/importes y revalida componentes sellados y Material Supply.
6. Claves nuevas Reference quedan bloqueadas hasta su resolución acreditada; nunca disparar OCRD/OITM automáticamente. Desapariciones de documentos históricos abortan y requieren investigación.
7. Preparar y promover exclusivamente con el wrapper anterior bajo instrucción del owner para esa candidata exacta. Avanzar `record_published_watermark` sólo con publicación CURRENT y reader verificado; el checkpoint representa cobertura de negocio, no watermark global de cambios.
8. Mantener `sales_refresh_scheduler.disabled.json` con `enabled=false`, `installed=false`. Antes de instalar un singleton hacen falta timezone fuente verificado, autorización del horario/scope, permisos efectivos y prueba controlada del ciclo completo.

Los límites de 12.000 SELECT y cuatro horas son máximos del motor existente, no una concesión para consumirlos ni autorización de extracción. El guard de recursos puede detener antes; nunca elevar límites para conseguir PASS.

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

El wrapper comprueba hashes y manifiesto, adquiere flock del journal y del publicador Reference, adquiere el lock Foundation y aplica `logical_commit` con CAS. Después activa Reference mediante el publicador existente y verifica el reader real.

El commit Foundation es el punto de visibilidad. Durante una interrupción entre commit y activación, los readers canónicos usan la Reference fijada por Foundation, no el pointer independiente. Los lectores legacy de `reference_current.json` no deben mezclar ese slot con facts de CURRENT.

Los consumidores del pointer independiente incluyen `create_initial.py` y `update.py`; no ejecutarlos durante esta ventana. El publicador de masters comparte el nuevo lock/CAS. Scripts históricos de investigación no constituyen publicadores habilitados.

## Sucesoras Reference-only

El mismo wrapper admite `FOUNDATION_REFERENCE_REFRESH_V1`; no necesita otro motor de publicación ni cambia las dependencias selladas para simular una derivación nueva.

- Instalar primero la Reference y crosswalk inmutables completos, comprobando hashes; ninguna instalación cambia CURRENT. Preparar con `publish_reference_only(..., prepare_only=True)` reutiliza las validaciones canónicas y deja la candidata READY_TO_COMMIT.
- El artefacto de candidata conserva la fila serializada exacta del catálogo, incluido `component_hash`; el loader reconstruye sólo la metadata rica de Reference. Los componentes de ventas heredados conservan su representación catalogada y contrato original.
- Ejecutar `prepare --candidate <artefacto> --journal <journal-nuevo>` y después `promote --journal <journal-nuevo>` mediante este mismo CLI. Preparación y commit comprueban la base exacta; no escribir CURRENT manualmente ni reusar un journal de otra operación.
- La validación conserva ocho componentes, ledger, snapshots y archivos sellados. El reader conserva las relaciones de ventas/NC file-backed cuando la base es `SALES_FACTS_TRANSITION_V1`; no vuelve a Atomic histórico.
- La integración física publicada y el journal efectivo están en el [estado local](../status_actual.md) y su evidencia. Repetir `promote` sobre ese journal sólo reconcilia la misma publicación idempotentemente; rollback continúa siendo una operación explícita con motivo y expected-current.

## Recuperación y rollback

El journal registra intención antes del commit y conserva eventos inmutables. Repetir el mismo comando autorizado reconcilia el estado real aunque el proceso se interrumpiera antes de registrar el commit o la activación.

- Antes del commit: la publicación anterior permanece efectiva.
- Después del commit: detectar CURRENT exacto y completar activación; no repetir captura ni commit.
- Después de activación: revalidar el reader; duplicación retorna el mismo resultado.
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
- Reader sin snapshot inyectado: cobertura, conteos, importes documentales, conciliación contra raw y hashes.
- Probar las siete preguntas comerciales solicitadas con identidad autorizada; rechazos de roles sin permiso deben conservarse.
- Septiembre completo: neto documental Bs 10.591.046,24. Octubre 1–29: Bs 10.811.322,92; no es un mes completo ni ingreso contable.
- Distinguir cliente facturado y comercial; rankings de líneas no son netos documentales; no inferir sucursal contable.
- Otros componentes conservan sus cortes históricos, sin refresh de compras, producción, inventario, cobranzas ni contabilidad.

## Sucesión incremental y acreditación comercial

La identidad de publicación cambia con el contenido; la compatibilidad empresarial se demuestra por el lineage canónico, no por una lista creciente de IDs permitidos.

`sales_succession.py` conserva las acreditaciones históricas como raíces de confianza y recorre únicamente `base_foundation_publication_id` en el catálogo existente. No agrega un registro paralelo. El wrapper comprueba admisión documental y física de cada incremental antes del CAS; los readers y el proceso padre revalidan la procedencia del resultado.

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

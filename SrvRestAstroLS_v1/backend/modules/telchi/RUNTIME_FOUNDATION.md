# TELCHI — Segment Execution Runtime Foundation V1

Gate: `TELCHI_DATALAKE_SEGMENT_EXECUTION_RUNTIME_FOUNDATION_V1`

Esta capacidad es una foundation opt-in para ejecutar trabajos en segmentos
acotados. Es domain-agnostic: no conoce SAP, tablas, SQL de HANA ni modelos de
negocio. No se inicia durante el startup del backend y no crea scheduler,
worker permanente, pool HANA, PostgreSQL ni DuckLake.

## Fronteras

`SegmentExecutor` coordina un `SegmentHandler` por fases (`prepare`,
`extract`, `transform`, `validate`, `reconcile`, `build_candidate` y
`cleanup`) y delega la publicación a `PublicationBoundary`. El estado candidato
no es estado trusted. Solo una publicación exitosa expone el resultado trusted.

El código usa stores/protocols separados para job, segmento, checkpoint,
coverage, watermark y dirty scope. V1 trae un backend in-memory para pruebas;
`pg_durable` puede implementarse después sin acoplarlo al executor.

## Seguridad de recursos

`ResourceGuard` hace `preflight` antes de cada segmento y checks cooperativos
entre fases y chunks. Inspecciona memoria disponible y porcentaje usado, swap,
load/CPU, disco, disco temporal, workers activos y tiempo transcurrido. La
carga se expresa relativa al número de CPUs. La presión warning produce
`REDUCE_NEXT_SEGMENT`; la presión crítica produce `SafeAbort`.

Los defaults son deliberadamente conservadores: un worker pesado y una query
HANA concurrente. Los nombres de configuración son comunes para DEV/PROD y se
ajustan mediante environment; no hay entidades separadas `*_DEV`/`*_PROD`.

El timeout es cooperativo. Un segmento corre en un thread daemon acotado para
que el proceso no quede esperando indefinidamente, y un `Event` de cancelación
impide continuar a la publicación. Un handler que bloquee sin cooperar puede
necesitar una futura frontera de proceso aislado; V1 no mata procesos
violentamente.

## Publication, checkpoint y recuperación

El orden es:

```text
preflight -> RUNNING -> extract/transform -> VALIDATING -> RECONCILING
-> PUBLISHING -> trusted publication -> checkpoint -> PUBLISHED
```

`CANDIDATE_READY -> VALIDATED -> RECONCILED` ocurre antes de cualquier
mutación trusted. `TransactionalPublicationBoundary` (y su adapter
`DuckLakePublication`) es el único owner de la conexión, `BEGIN`, trusted
writes, publication record y `COMMIT`. Todas las tablas de una publicación
lógica y el registro durable `publication_id` participan en una única
transacción explícita; el path trusted no usa autocommit ni commits dispersos.
Candidate permanece aislado y nunca se ofrece por el reader trusted.

El reader oficial usa una conexión independiente y una transacción de lectura:
solo puede observar el estado completo anterior o el estado completo nuevo.
Validation, reconciliation, timeout, safe abort y excepciones no publican ni
avanzan watermark trusted. El checkpoint solo se escribe después de la
publicación trusted y contiene identidad de contenido y publicación.

Si la publicación ocurrió y el checkpoint falló, el segmento sigue siendo
`PUBLISHED` con `CHECKPOINT_FAILED`. Una ejecución posterior consulta la
identidad durable por `publication_id`/`idempotency_key`, escribe el checkpoint
faltante y no vuelve a publicar. Si el resultado del `COMMIT` es incierto, el
runtime resuelve primero esa identidad; nunca reintenta escrituras trusted a
ciegas. El `idempotency_key` incluye segmento, source identity, reference
version y transformation version.

## Coverage, split y dirty scope

Los scopes son rangos half-open `[from, to)`. `CoverageTracker` rechaza
overlaps no controlados y reporta gaps; un job solo puede pasar a `COMPLETED`
cuando el coverage requerido es contiguous y trusted. `split_segment` conserva
`parent_segment_id` y exige que los hijos cubran exactamente el padre.

`DirtyScopeTracker` modela `DIRTY -> REPROCESSING -> RECONCILING -> CLEARED`
y permite `DIVERGED` sin fingir que el histórico está sano. La fuente futura
de detección queda fuera de esta foundation.

Los watermarks distinguen `detected`, `processed`, `validated` y `published`.
El watermark trusted no puede saltar un gap de coverage.

## DuckDB safety profile

Las futuras conexiones de ingesta deben usar `open_safe_duckdb` o aplicar
`apply_duckdb_safety_profile`, con `memory_limit`, `threads`,
`temp_directory` y `max_temp_directory_size` explícitos. La verificación local
se realizó contra DuckDB 1.5.5. El spill usa una ruta absoluta configurable,
no el cwd ni `/tmp` como default lógico. El cleanup exige el nombre exacto del
artefacto propio `segment-<job>-<segment>`; nunca borra raw, reference o legacy.

## Auditoría del intento Atomic

Antes de cualquier cleanup se ejecutó una inspección bounded y read-only por
metadata (paths, nombres, tamaños y timestamps) en Data Root, manifests y
DuckLake data. No se leyeron datasets completos, no se calcularon hashes
recursivos y no se modificaron PostgreSQL, DuckLake o datos. La clasificación y
las preguntas obligatorias están en la evidencia externa:

- `TELCHI_DATALAKE_SEGMENT_EXECUTION_RUNTIME_FOUNDATION_V1/interrupted_run_audit.json`
- `TELCHI_DATALAKE_SEGMENT_EXECUTION_RUNTIME_FOUNDATION_V1/interrupted_run_audit.md`

No se hizo cleanup destructivo. La inspección DuckLake catalog quedó como
`UNKNOWN` cuando no podía garantizarse acceso read-only.

## Validación

Los tests sintéticos viven en `runtime/tests/test_foundation.py`. Cubren
máquinas de estado, fallos por fase, publicación/checkpoint, resume,
idempotencia, split/rangos, coverage gaps, dirty scope, watermark safety,
pressure simulado, timeout cooperativo, chunks bounded, DuckDB settings y
worker limit. No consultan SAP ni ejecutan ingesta real.

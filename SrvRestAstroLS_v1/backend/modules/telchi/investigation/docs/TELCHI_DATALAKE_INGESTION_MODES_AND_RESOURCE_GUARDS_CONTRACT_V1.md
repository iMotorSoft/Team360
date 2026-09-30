# TELCHI Data Lake — Ingestion Modes and Resource Guards Contract V1

Este gate fija el modelo operativo documental de ingesta sin habilitar runtime productivo.

## Gate result

El contrato queda listo para revisión, con exactamente dos modos y sin mutaciones de datos.

```text
GATE=TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1
RESULT=TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS
STAGE=INVESTIGATION
ARCHITECTURE_UPDATED=YES
ADR_INDEX_UPDATED=YES
```

## Contract scope

La autoridad detallada vive en `TELCHI_DATALAKE_ARCHITECTURE_V1.md`; los CSV y JSON reproducibles viven en la carpeta de validación del gate.

| Contract | Decision |
| --- | --- |
| `INITIAL_INGESTION` | Construye baseline histórico por ventanas acotadas, preferentemente `MONTH`, con checkpoint/resume. |
| `INCREMENTAL_UPDATE` | Mantiene el estado local desde cambios y lecturas autoritativas afectadas, preferentemente en `MICRO_BATCH`. |
| Reconciliation | FAST/FOCAL y PERIODIC/AUTHORITATIVE son controles internos del UPDATE; no un tercer modo principal. |
| Publication | Candidate state queda separado del trusted published state; validation/reconciliation fallida es fail-closed. |
| Priority | `CORRECTNESS > FRESHNESS > LATENCY`. |
| HANA | Es fuente de autoridad READ ONLY, nunca runtime de preguntas del chat. |
| Resources | Preflight, guards continuos, límites DuckDB, baja concurrencia, backpressure y safe abort son obligatorios. |

## Required output

Estos flags son el cierre machine-readable y contractual del gate.

```text
INITIAL_INGESTION_DEFINED=YES
INCREMENTAL_UPDATE_DEFINED=YES
RECONCILIATION_AS_UPDATE_CONTROL_DEFINED=YES
SHARED_CANONICAL_TRANSFORMATION=YES
CORRECTNESS_OVER_FRESHNESS_OVER_LATENCY=YES
FAIL_CLOSED_PUBLICATION=YES
CANDIDATE_STATE_SEPARATE_FROM_TRUSTED_STATE=YES
WATERMARK_ADVANCES_AFTER_TRUSTED_PUBLISH_ONLY=YES
TRUST_STATES_DEFINED=YES
DATA_AS_OF_CONTRACT_DEFINED=YES
HANA_IS_SOURCE_AUTHORITY=YES
HANA_IS_CHAT_QUERY_RUNTIME=NO
HANA_QUERY_ON_USER_REQUEST=NO
HANA_FULL_SCAN_POLLING_ALLOWED=NO
HANA_BOUNDED_READS_REQUIRED=YES
HANA_LOW_CONCURRENCY_REQUIRED=YES
HANA_LOAD_MINIMIZATION_MANDATORY=YES
INITIAL_DEFAULT_WORK_UNIT=MONTH
INITIAL_MONTH_EQUALS_ATOMIC_PARQUET_FILE=NO
LIVE_INGESTION_MODE=MICRO_BATCH
MICRO_BATCH_EQUALS_PARQUET_FILE=NO
ATOMIC_FILE_OWNERSHIP=DUCKLAKE
RESOURCE_PREFLIGHT_REQUIRED=YES
RESOURCE_CONTINUOUS_GUARDS_REQUIRED=YES
DUCKDB_MEMORY_LIMIT_REQUIRED=YES
DUCKDB_THREADS_LIMIT_REQUIRED=YES
TEMP_STORAGE_GUARD_REQUIRED=YES
HANA_CONCURRENCY_LIMIT_REQUIRED=YES
BACKPRESSURE_DEFINED=YES
SAFE_ABORT_DEFINED=YES
CHECKPOINT_RESUME_DEFINED=YES
POSTGRES_MODIFIED=NO
DUCKLAKE_MODIFIED=NO
DATA_FILES_MODIFIED=0
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
RUNTIME_IMPLEMENTED=NO
INGESTION_OPERATIONAL_CONTRACT_READY=YES
```

## Safety boundary

Este gate no crea scheduler, worker, pg_durable workflow, polling recurrente, backfill nuevo, business/current build, chat integration ni Atomic facts. El siguiente paso requiere revisión explícita.

```text
TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS
STOP AND REVIEW
```

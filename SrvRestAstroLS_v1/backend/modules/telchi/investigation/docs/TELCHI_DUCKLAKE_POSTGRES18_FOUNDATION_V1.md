# TELCHI — DuckLake + PostgreSQL 18 Foundation V1

Gate de fundación real para Telchi. La etapa es `INVESTIGATION`: no crea hechos
`atomic`, `business` o `current`, no consulta SAP y no migra los 14 datasets
`reference` ni los 8 `crosswalk` existentes.

## Resultado de la corrida

La evidencia reproducible vive junto al runner en
`../validation/ducklake_postgres18_foundation_v1/evidence/`.
El archivo `summary.json` es la salida técnica de la última corrida; no contiene
credenciales. El gate se ejecuta desde `SrvRestAstroLS_v1/backend/`:

```bash
uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.provision --check
uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.run_foundation --check
uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.run_foundation --execute
uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.run_foundation --verify
```

`--execute` es idempotente respecto de objetos y filas determinísticas: detecta
el catálogo y el probe existentes, no resetea snapshots ni elimina Parquet.
Una falla parcial no borra la database ni el storage. `--verify` es read-only.

## Arquitectura y ownership

- **PostgreSQL 18.4**: catálogo/metadata backend de DuckLake, en la database
  dedicada `team360_telchi_ducklake`.
- **DuckLake**: snapshots, transacciones, evolución de schema y referencias a
  los archivos administrados.
- **DuckDB 1.5.5**: motor de attach, lectura, transformación y validación.
- **Parquet**: storage físico bajo
  `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/ducklake/data`.
- **Team360**: futura identidad, autorización, semantic layer y API; este gate
  no agrega integración global ni endpoints.

DuckLake 1.0 escribe sus tablas de metadata en `public`; por eso el aislamiento
se logra con la database dedicada, no con un schema dentro de la database de
Team360. La inspección confirma que `public` de
`team360_telchi_ducklake` contiene únicamente metadata `ducklake_*` y no objetos
de aplicación. Un schema de metadata configurable no está expuesto por la
versión instalada y no se mueven tablas internas manualmente. Los schemas
lógicos `reference`, `crosswalk`, `atomic`, `business`, `current` y `ops` se
mantienen dentro del catálogo para el diseño futuro. La única tabla de datos
creada en este gate es `ops.foundation_probe`, sintética.

DuckLake no adquiere ownership de:

- `raw/legacy/parquet` (696 archivos preservados);
- `reference/**` (14 datasets existentes);
- `crosswalk/**` (8 datasets existentes).

El runner los lee directamente con `read_parquet(?)` y compara tamaño/SHA-256
antes y después. No usa `ducklake_add_data_files` sobre esas rutas.

## Configuración y seguridad

El runtime carga variables `TELCHI_DUCKLAKE_PG_*` o el archivo privado
`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/ducklake/postgres.env`.
El archivo está fuera de Git, con permisos de propietario, y no se genera un
DSN con password en SQL ni en logs. La versión instalada de DuckLake usa
opciones libpq para este catálogo; por eso el adaptador coloca temporalmente la
password en `PGPASSWORD` durante `ATTACH`, en memoria del proceso, y la retira
inmediatamente después. El role de runtime es dedicado, `LOGIN`,
`NOSUPERUSER`, `NOCREATEDB` y `NOCREATEROLE`; el provisioning administrativo
queda separado de `runtime.py`.

No se modifican `postgresql.conf`, `pg_hba.conf`, puertos, otras databases,
SAP/HANA, `globalVar.py`, registry, rutas públicas ni configuración productiva.
SAP queda explícitamente en `SAP_ACCESSED=NO` y `SAP_WRITE_COUNT=0`.

## Validaciones

El probe fuerza `DATA_INLINING_ROW_LIMIT 0`, generando Parquet físico bajo el
`DATA_PATH`. Se validan:

- `CREATE TABLE`, `INSERT`, `SELECT` y snapshot actual;
- commit multi-operación, rollback y cierre de conexión con escritura no
  committeada;
- snapshots dinámicos y time travel con `AT (VERSION => n)`;
- `ALTER TABLE ... ADD COLUMN` sin cambio destructivo y lectura de snapshot
  anterior;
- reconnect independiente y data path absoluto persistente;
- attach `READ_ONLY`, donde las lecturas pasan y los INSERT son rechazados;
- reader/writer concurrentes y dos writers focalizados;
- coexistencia con un reference, un crosswalk y un raw legacy externos;
- backup custom del catálogo con `pg_dump`, sin restaurar sobre el catálogo
  activo; restore queda documentado como procedimiento aislado;
- retención: `SNAPSHOT_EXPIRATION_POLICY=PRESERVE`; no se ejecuta cleanup,
  expire ni compaction productiva.

La evidencia está separada por contrato en `environment.csv`,
`postgres_catalog_objects.csv`, `ducklake_snapshots.csv`,
`ducklake_managed_files.csv`, `transaction_tests.csv`,
`time_travel_tests.csv`, `concurrency_tests.csv`,
`performance_benchmark.csv`, `external_parquet_tests.csv`,
`filesystem_integrity.csv`, `backup_validation.csv` y `summary.json`.

## Performance y límites restantes

Se separan attach/startup y query warm; no se usa Dask ni pandas. Este gate no
representa el benchmark de millones de filas ni las preguntas CEO. No se fija
retención definitiva hasta medir volumen real. La autorización final debe
ocurrir antes del semantic plan y no se implementa aquí.

Si `summary.json` informa `DEGRADED`, se conserva la infraestructura y la
causa se revisa sin borrar ni resetear el catálogo. El siguiente gate, solo
luego de revisión explícita, es el contrato de semántica y performance para
preguntas ejecutivas; no comenzar aún atomic, ventas, stock, producción,
crédito, business read models ni chat.

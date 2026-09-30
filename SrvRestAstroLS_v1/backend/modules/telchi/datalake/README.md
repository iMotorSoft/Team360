# Telchi Data Lake

## `create_initial.py`

`create_initial.py` es un builder explícito, acotado y secuencial para Sales e Inventory. No es un scheduler.

## `reference_update.py`

`reference_update.py` implementa `TELCHI_DATALAKE_REFERENCE_V2_SAP_MASTER_INGESTION_V1`:
ingesta bounded y secuencial de OITM/OCRD/OWHS, diff por source key,
preservación de canonical IDs/crosswalks y publicación versionada mediante un
puntero atómico. No modifica facts ni DuckLake.

```bash
uv run python -m modules.telchi.datalake.reference_update
```

Debe ejecutarse y pasar antes de la ejecución normal de `update.py`.

## `update.py`

`update.py` implementa `TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1`: una
actualización manual, de una sola ejecución, de la foundation 2026 (Sales
`OINV`/`INV1`, OINM, OITW). No es scheduler, cron, daemon, queue ni framework de
orquestación. Detalle completo en [`UPDATE_README.md`](UPDATE_README.md).

```bash
uv run python -m modules.telchi.datalake.update            # fail-closed
uv run python -m modules.telchi.datalake.update --plan-only
uv run python -m modules.telchi.datalake.update --dry-run
uv run python -m modules.telchi.datalake.update --defer-new-reference-keys
```

## Modos de `create_initial.py`

- **create**: extracción SAP read-only, raw immutable, validación, reconciliación y publicación.
- **resume**: retoma el manifiesto de segmentos sin confundir publicaciones previas.
- **plan** (`--plan-only`): sin `--coverage-file` muestra placeholders y no contacta SAP; con `--coverage-file` consume cobertura agregada SAP ya capturada y genera el plan completo sin volver a extraer ni publicar.
- **coverage discovery** (`python -m modules.telchi.datalake.source_coverage`): consulta SAP/HANA sólo con agregados bounded, registra conectividad, cobertura real, legacy separado y el plan completo.
- **rebuild** (`--rebuild-scope`): reutiliza raw existente (`REUSE_RAW`) y reemplaza un keyset exacto en Atomic.
- **reset** (`--reset-atomic-scope`): alias explícito para el reemplazo Atomic acotado.
- **raw rewrite** (`--rewrite-raw-scope`): reextrae con un nuevo `extraction_id`; nunca sobrescribe el raw anterior.
- **raw purge** (`--purge-raw-scope`): excepcional; sólo raw creado por esta implementación, con dependencia revisada y `--confirm-destructive`.

Las operaciones destructivas requieren `--domain`, `--segment-id`, un plan previo (`--plan-only`) y `--confirm-destructive`. No existe `--reset-all` y no se acepta scope implícito por fechas.

## Regla física no negociable

Los Parquet administrados por DuckLake se auditan mediante `ducklake_list_files` y metadata de snapshots. Nunca se usa `rm`, `unlink` ni `shutil.rmtree` sobre ellos. El reemplazo de Atomic ocurre dentro de `TransactionalPublicationBoundary`; DuckLake puede retener los archivos anteriores por time travel.

`raw/sap` es evidencia externa: su purge sólo puede operar sobre el root gate-owned, un `segment_id` explícito, sin referencias trusted y con confirmación. `raw/legacy` no puede purgarse.

## Alcance futuro

Una cobertura completa debe seguir siendo segmentada por dominio y keys (`DocEntry + LineNum` para Sales, `ItemCode + WhsCode` para Inventory), con una publicación por segmento. Este gate no ejecuta el histórico completo, no expira snapshots y no ejecuta compaction global.

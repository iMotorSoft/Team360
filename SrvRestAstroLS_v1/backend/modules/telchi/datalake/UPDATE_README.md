# Telchi Data Lake `update.py`

`update.py` implementa `TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1`: una
actualización manual, de una sola ejecución, de la foundation 2026 ya validada
(Sales `OINV`/`INV1`, OINM, OITW). No es scheduler, cron, daemon, worker, queue
ni framework de orquestación.

## Uso

```bash
# Ejecución normal (fail-closed ante claves nuevas de Reference V2)
uv run python -m modules.telchi.datalake.update

# Solo plan (no contacta SAP)
uv run python -m modules.telchi.datalake.update --plan-only

# Lee SAP, calcula el delta y valida, pero no publica
uv run python -m modules.telchi.datalake.update --dry-run

# Autoriza explícitamente publicar facts con claves nuevas sin Reference V2
uv run python -m modules.telchi.datalake.update --defer-new-reference-keys
```

## Contrato

- `SAP_MODE=READ_ONLY`, `SAP_WRITE_COUNT=0`, `AI_INVOCATIONS=0`.
- Relee el universo 2026 completo de forma segmentada (`MAX_HANA_CONCURRENT_QUERIES=1`,
  `MAX_WORKERS=1`). `DocDate` define el scope de negocio, nunca el *change detection*.
- Staging transitorio en `DATA_ROOT/staging/manual_update_v1/staging.duckdb`
  (data-only, fuera del catálogo DuckLake). Nada es visible mientras se extrae.
- Diff por source key + campos: `NEW`/`UPDATED`/`UNCHANGED`/`CANCELLED`.
  - Sales se refresca por unidad `DocEntry` (header + todas sus líneas).
  - OINM preserva `TransNum + TransSeq`.
  - OITW es *current state*: snapshot completo reemplazado (las desapariciones
    de claves son legítimas).
- Desaparición de una clave histórica de Sales u OINM ⇒ aborto antes de publicar.
- Publicación física por dataset mediante `TransactionalPublicationBoundary`, con
  escrituras set-based (`DELETE` por keyset + un `INSERT ... SELECT` por tabla).
  La visibilidad global usa `foundation_publication.py`: `PREPARING` → `VALIDATING`
  → `READY_TO_COMMIT` → un único logical commit atómico del current pointer.
  Un fallo pre-commit preserva la foundation anterior; el reader oficial usa
  `get_current_foundation()` y nunca mezcla los componentes más recientes de cada tabla.
- Reference V2 nunca se reasigna. Este gate sólo *verifica* cobertura; no
  reconstruye la capa versionada.

## Global logical publication boundary

El modelo vigente es `MULTIPLE_ATOMIC_TRANSACTIONS_WITH_LOGICAL_COMMIT`.
La metadata vive en el catálogo DuckLake existente (`telchi.ops`) y mantiene
una sola publicación `CURRENT`, cuatro componentes y candidatos retenidos para
auditoría. Los lectores nuevos deben resolver primero `get_current_foundation()`;
los lectores legacy que consultan `telchi.atomic` directamente deben migrar al
contrato antes de usarse como consumidores de la foundation global.

## Reference V2 antes de `update.py`

La cobertura se resuelve explícitamente en dos pasos y no se reconstruye de forma
silenciosa desde `update.py`:

```bash
uv run python -m modules.telchi.datalake.reference_update
uv run python -m modules.telchi.datalake.update
```

`reference_update.py` ingiere únicamente OITM/OCRD/OWHS, crea una versión
inmutable y activa el puntero después de validar source keys, canonical IDs y
crosswalks. SAP permanece READ ONLY. Los roles C/S/L de OCRD se mantienen
separados; no hay fuzzy merge. El refresh conserva entidades desaparecidas como
históricas y no sobrescribe relaciones curated/manual.

Después de un refresh PASS, `update.py` debe ejecutarse sin
`--defer-new-reference-keys`. Ese flag queda únicamente como escape operativo
explícito para una referencia todavía degradada; no es parte del camino normal.

## Evidencia

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_GLOBAL_LOGICAL_PUBLICATION_BOUNDARY_V1/`
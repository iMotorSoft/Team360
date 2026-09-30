# TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1 — Reporte del gate

```text
GATE=TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1
FINAL_RESULT=TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1_DEGRADED
BRANCH=feature/console-backend-core
ENTITY=TELCHI
STAGE=DEVELOPMENT
UPDATE_ENTRYPOINT=SrvRestAstroLS_v1/backend/modules/telchi/datalake/update.py
EVIDENCE_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1
DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi
SAP_MODE=READ_ONLY
SAP_WRITE_COUNT=0
AI_INVOCATIONS=0
MAX_HANA_CONCURRENT_QUERIES=1
MAX_WORKERS=1
SCHEDULER_CRON_DAEMON_QUEUE=NONE
DOCDATE_ONLY_WATERMARK=PROHIBITED
FULL_2026_SEGMENTED_RE_READ=YES
```

## 1. Objetivo

Actualizar la foundation 2026 ya validada (Sales `OINV`/`INV1`, OINM, OITW)
mediante **una ejecución manual**: relee de forma segmentada el universo 2026,
detecta filas tardías/retroactivas, calcula el delta, lo publica de forma
transaccional y valida contra SAP capturado. Correctness > efficiency.

## 2. Resultado

`FINAL_RESULT=TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1_DEGRADED`.

La reconciliación de datos fue **EXACTA** (`PUBLISHED_VS_CAPTURED_SAP=EXACT`,
`TRUE_MISMATCH_COUNT=0`, `UNEXPLAINED_MISMATCH_COUNT=0`). El resultado se declara
**DEGRADED**, no PASS, porque SAP introdujo claves maestras nuevas que la capa
Reference V2 existente no puede ingerir de forma segura; ver §38 y §6.

## 3. Evidencia de la corrida real (canónica)

Corrida `manual-update-canonical-1`, 2026-09-22:

| Métrica | Antes | Después |
| --- | --- | --- |
| `sales_document` (2026) | 327,806 | 327,883 |
| `sales_line` (2026) | 709,153 | 709,358 |
| `inventory_movement` (2026) | 1,524,770 | 1,525,024 |
| `inventory_balance` (OITW) | 1,370,242 | 1,370,313 |

- Sales: +77 docs nuevos, +10 actualizados, +225 líneas nuevas, 0 desaparecidos.
- OINM: +254 filas nuevas, 0 actualizadas, 0 desaparecidas.
- OITW: +71 claves, 442 filas cambiadas, 0 removidas (snapshot corriente).
- 3 publicaciones transaccionales: `update_publication_4bba28dc…`,
  `…13bb616b…`, `…d175f3e3…`.
- `bulk_write_metrics`: 4 inserts set-based, 1,370,879 filas publicadas.

Segunda corrida (`SECOND_RUN`, `manual-update-real-2`) reprodujo el mismo
comportamiento con `PUBLISHED_VS_CAPTURED_SAP=EXACT`, confirmando convergencia.

## 4. Contrato verificado

- Relectura segmentada completa 2026; `DocDate` define *scope de negocio*, nunca
  el *change detection*.
- Staging transitorio (`DATA_ROOT/staging/manual_update_v1/staging.duckdb`),
  invisible a Atomic durante la extracción.
- Sales se refresca por unidad `DocEntry` (header + todas sus líneas).
- OINM preserva `TransNum + TransSeq`.
- OITW es *current state*: reemplazo de snapshot (desapariciones legítimas).
- Desaparición de claves históricas Sales/OINM ⇒ aborto antes de publicar
  (probado con fault-injection).
- Publicación transaccional con escrituras set-based (`DELETE` por keyset +
  `INSERT … SELECT` por tabla). Fallo ⇒ se preserva la foundation anterior
  (probado con fault-injection).
- Validación bidireccional por keyset y por totales decimales exactos.
- Idempotencia: segunda corrida sin cambios ⇒ `NOOP` (probado en contrato y
  observado en vivo cuando SAP no cambia).

## 5. Pruebas

- `modules/telchi/investigation/validation/datalake_manual_single_run_update_v1/test_contract.py` — 21 tests de contrato (diff, unidad `DocEntry`, snapshot OITW, rollback, fallo set-based, idempotencia, política fail-closed ante claves nuevas).
- `modules/telchi/datalake/tests/` — 22 tests de regresión del módulo.
- **Total: 43 passing**.

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest modules/telchi/investigation/validation/datalake_manual_single_run_update_v1/ \
               modules/telchi/datalake/tests/ -q
```

## 6. Bloqueo declarado (por qué DEGRADED y no PASS)

Reference V2 (`DATA_ROOT/reference/_versions/v2`, incluido crosswalk) es una capa
versionada construida **offline** a partir de un snapshot maestro previo. **No
existe un mecanismo validado que ingeste maestros actuales de SAP.** Cuando SAP
crea productos/clientes nuevos no resolubles:

- comportamiento **por defecto**: `REFERENCE_REFRESH_REQUIRED_BUT_UNSAFE=YES`,
  aborto antes de publicar (§38, fail-closed);
- con autorización explícita `--defer-new-reference-keys`: publica los facts
  registrando `REFERENCE_COVERAGE=DEGRADED`, sin reasignar canonical IDs ni crear
  FKs (Atomic no almacena `canonical_*_id`).

En la corrida canónica: `UNRESOLVED_REFERENCE_KEYS=1`,
`REFERENCE_NEW_PRODUCTS=1`, `EXISTING_CANONICAL_IDS_CHANGED=0`,
`REFERENCE_MODIFIED=NO`. Ver `RUN1_ABORTED/` para la evidencia del aborto
fail-closed (27 claves nuevas no resolubles).

Crear ingestion de maestros SAP → Reference V2 está **fuera de alcance** de este
gate (§4/§80) y no se improvisó ningún mecanismo nuevo (§38).

## 7. Bandera prohibida

`DocDate`-only watermark: **NO USADO**. La detección de filas tardías/retroactivas
se hace por relectura completa segmentada + diff por source key.

## 8. Fuera de alcance (no tocado)

Órdenes, entregas, notas de crédito, devoluciones, histórico 2022–2025, Business
Assistant, y el runtime productivo protegido (Diagnosticador/Vera).
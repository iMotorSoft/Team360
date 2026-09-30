# TELCHI DATA LAKE — LEGACY PARQUET MIRROR V1

## A. Gate

**TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS**

Este gate copia exclusivamente los 696 Parquet del inventario histórico aprobado. No transforma datos, no crea capas derivadas y no accede SAP/HANA.

## B. Roots

- `DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
- `LEGACY_SOURCE_ROOT=/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS` (READ_ONLY / IMMUTABLE_SOURCE)
- `LEGACY_MIRROR_PATH=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet`

## C. Preflight

- Inventario autoridad: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/historical_data_inventory_v1/historical_files_inventory.csv`; esperado/presente: 696/696.
- SOURCE_TOTAL_BYTES=799199945; DESTINATION_FREE_BYTES=473025916928; REQUIRED_COPY_BYTES=799199945.
- Fuente leída por bloques; footer DuckDB; no pandas; destino verificado como escribible.

## D. Source drift

- SOURCE_DRIFT=0; cambios durante gate=0. Si es distinto de cero el proceso detiene la copia o queda FAIL.
- Se comparó SHA-256 y tamaño actual contra la evidencia `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`.

## E. Copy execution

- COPY_REQUIRED=696; COPIED=696; ALREADY_VERIFIED=0.
- Cada archivo faltante se publicó desde un temporal propio tras fsync, hash, tamaño y footer; no se sobrescriben colisiones.
- Segunda ejecución `--check`: `COPY_REQUIRED=0`, `COPIED=0`, `ALREADY_VERIFIED=696` (idempotencia confirmada).

## F. SHA-256 verification

- DESTINATION_PRESENT=696; SHA256_VERIFIED=696; HASH_MISMATCHES=0.
- Identidad: SHA-256 + size; el payload Parquet no se reescribe.

## G. Row/schema verification

- ROW_COUNT_MISMATCHES=0; SCHEMA_MISMATCHES=0.
- Row count y fingerprint se leen desde footer, sin full scan.

## H. Resultado por familia

| family | expected_files | verified_files | bytes | rows | status |
|---|---:|---:|---:|---:|---|
| `ProductSaleCostDay` | 30 | 30 | 2331922 | 174425 | PASS |
| `cash` | 40 | 40 | 32620185 | 1177874 | PASS |
| `clientSB1` | 1 | 1 | 368537 | 11512 | PASS |
| `cuentasxCobrar` | 27 | 27 | 4312569 | 125233 | PASS |
| `movProduct` | 63 | 63 | 41962271 | 2597952 | PASS |
| `movProductSB1` | 26 | 26 | 210604681 | 4033041 | PASS |
| `mpRel` | 1 | 1 | 123920 | 10490 | PASS |
| `ncB1Product` | 27 | 27 | 1993000 | 19933 | PASS |
| `oactSB1` | 1 | 1 | 28330 | 523 | PASS |
| `oitbSB1` | 1 | 1 | 9512 | 38 | PASS |
| `owhsSB1` | 1 | 1 | 6898 | 59 | PASS |
| `paymentB1` | 13 | 13 | 17533854 | 368552 | PASS |
| `payout` | 9 | 9 | 400588 | 17643 | PASS |
| `person` | 1 | 1 | 291803 | 11969 | PASS |
| `product` | 1 | 1 | 1301762 | 25221 | PASS |
| `productSB1` | 1 | 1 | 658120 | 11245 | PASS |
| `productTKB` | 1 | 1 | 49408 | 1450 | PASS |
| `productTracking` | 39 | 39 | 52547564 | 3742587 | PASS |
| `productTransform` | 20 | 20 | 915368 | 41397 | PASS |
| `productosPrioridad` | 1 | 1 | 28001 | 764 | PASS |
| `prontoProducts` | 1 | 1 | 417118 | 15182 | PASS |
| `purchase` | 121 | 121 | 20369192 | 216655 | PASS |
| `purchaseExpense` | 124 | 124 | 31068940 | 2122092 | PASS |
| `recetasNiveles01` | 1 | 1 | 40293 | 1690 | PASS |
| `reconB1` | 13 | 13 | 32895127 | 869473 | PASS |
| `saleProduct` | 52 | 52 | 163817326 | 3785327 | PASS |
| `saleSB1Product` | 77 | 77 | 180037562 | 5621744 | PASS |
| `sapWhsOfficeName` | 1 | 1 | 5038 | 60 | PASS |
| `wareHouseOffice` | 1 | 1 | 5224 | 41 | PASS |
| `wareHouseSB1` | 1 | 1 | 2455832 | 819167 | PASS |

## I. Destination inventory

- MISSING_DESTINATION_FILES=0; UNEXPECTED_DESTINATION_PARQUETS=0; UNEXPECTED_SYMLINKS=0.
- MIRROR_TOTAL_BYTES=799199945.
- No se eliminaron archivos inesperados ni temporales preexistentes.
- Se inspeccionaron 18 Parquet preexistentes fuera del scope autorizado (bajo `business/`); este gate no los creó ni modificó.

## J. Manifest

- CSV físico: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/manifests/legacy/legacy_parquet_mirror_v1.csv`.
- Evidencia: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/legacy_parquet_mirror_v1`.
- El manifest conserva nombre original, relative path, family, fecha de filename, hash source/destination, tamaño, footer y estados.

## K. Immutability contract

`raw/legacy/parquet/` es PRESERVED_SOURCE e IMMUTABLE. Futuros procesos sólo leen esta capa y escriben en capas derivadas. El root legacy original no se limpia, mueve ni modifica.

## L. Riesgos / incidencias

- Los snapshots y schemas históricos se preservan tal como fueron encontrados; no se deduplican ni normalizan.
- Un archivo destino existente con hash distinto es `STOP_DESTINATION_COLLISION`; no se sobrescribe.
- SOURCE_FILES_MODIFIED=0; MOVED=0; DELETED=0.

## M. Siguiente gate

No se avanza automáticamente. El siguiente gate es `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1`; no se accedió SAP/HANA.

## Cierre

```text
DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi
LEGACY_SOURCE_ROOT=/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS
LEGACY_MIRROR_PATH=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet
LEGACY_PARQUET_EXPECTED=696
LEGACY_SOURCE_PRESENT=696
COPY_REQUIRED=0
COPIED=696
ALREADY_VERIFIED=0
LEGACY_DESTINATION_PRESENT=696
LEGACY_SHA256_VERIFIED=696
SOURCE_DRIFT=0
DESTINATION_COLLISIONS=0
HASH_MISMATCHES=0
ROW_COUNT_MISMATCHES=0
SCHEMA_MISMATCHES=0
MISSING_DESTINATION_FILES=0
UNEXPECTED_DESTINATION_PARQUETS=0
SOURCE_TOTAL_BYTES=799199945
MIRROR_TOTAL_BYTES=799199945
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
SOURCE_FILES_MODIFIED=0
SOURCE_FILES_MOVED=0
SOURCE_FILES_DELETED=0
ATOMIC_PARQUETS_CREATED=0
BUSINESS_PARQUETS_CREATED=0
REFERENCE_PARQUETS_CREATED=0
CROSSWALK_PARQUETS_CREATED=0
LEGACY_MIRROR_COMPLETE=YES
```

TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS

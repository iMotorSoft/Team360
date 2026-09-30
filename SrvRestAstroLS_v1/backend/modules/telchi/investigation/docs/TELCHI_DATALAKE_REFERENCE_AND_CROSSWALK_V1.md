# TELCHI DATA LAKE — REFERENCE & CROSSWALK V1

## Gate

**TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS**

Contexto: `ENTITY=TELCHI`, `STAGE=INVESTIGATION`, usuario
`administrator/administrators`, alcance completo y SAP/HANA `READ ONLY`.

Este gate materializa únicamente `reference/` y `crosswalk/`. No crea hechos
`atomic/`, modelos `business/` ni `decision/`.

## Inputs y preservación

- `raw/legacy/parquet/`: 696 archivos, consumidos sin modificar.
- Fuente organizacional original: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS/almacenOficina.xlsx`.
- Copia preservada byte-identical en
  `raw/legacy/reference_sources/almacenOficina.xlsx` (SHA-256
  `5eb978339c73efab7e98171cfa4fcbebeb37435ebc8c32e1d797f6955e47e466`).
- SAP actual fue consultado sólo para los maestros autorizados `OITM`, `OCRD`,
  `OWHS`, `OSLP`, `OUSR`, `OHEM` y `OITB`. Cada extracción quedó preservada como
  Parquet bajo `raw/sap/table_extract/` y documentada en
  `validation/datalake_reference_and_crosswalk_v1/evidence/sap_master_extractions.csv`.
- `OHEM` se preservó como extracción, pero no se crea `reference/employee`: el
  catálogo físico V1 aprobado contiene 14 referencias y clasifica EMPLOYEE como
  `CORE_LATER`. No se inventa un dataset físico fuera de ese contrato.

## Datasets creados

Las 14 referencias aprobadas fueron materializadas como Parquet ZSTD en
`reference/<dataset>/part-00000.parquet`:

| Dataset | Filas | Resultado |
|---|---:|---|
| products | 53.318 | SAP actual + observaciones legacy; nombres original y normalizado |
| product_groups | 78 | SAP y grupo legacy sin fusionar por nombre |
| customers | 35.057 | OCRD cliente + maestros legacy observados |
| suppliers | 2.130 | OCRD proveedor + personas legacy marcadas proveedor |
| warehouses | 133 | 82 SAP actuales + 51 observados por reference file |
| branches | 7 | códigos 1, 2, 3, 4, 5, 7 y 8 del workbook |
| users | 173 | OUSR actual |
| salespersons | 253 | OSLP actual |
| document_types, payment_terms, channels, units_of_measure, warehouse_roles, currencies | 0 | schema físico vacío, fuente V1 no validada |

Cada fila poblada conserva `source_system`, `source_native_id`, su ID canónico
estable y el envelope de lineage (`_source_*`, versiones y calidad). Los IDs se
generan determinísticamente mediante SHA-256; no se usan nombres como identidad.
`LEGACY_DS` y `LEGACY_DS0` distinguen familias históricas cuando comparten un
espacio de códigos, sin afirmar equivalencia SAP.

En `products` se preserva además `product_name`,
`normalized_product_name`, UoM observada, `active` e `is_telchi_l_product`.
El universo `ItemCode LIKE 'L%'` queda identificado: **7.158 productos**.
La normalización sólo sirve para búsqueda: no reemplaza el nombre original.

## Crosswalks

Se crearon los ocho datasets físicos aprobados:

- `product_crosswalk`
- `customer_crosswalk`
- `supplier_crosswalk`
- `warehouse_crosswalk`
- `branch_crosswalk`
- `salesperson_crosswalk`
- `user_crosswalk`
- `warehouse_branch_mapping`

Los siete crosswalks de identidad asignan cada identidad de fuente a un canonical
ID propio de esa observación (`CONFIRMED`, `canonical_source_identity`). Esto no
fusiona automáticamente SAP con legacy. Las equivalencias no evidenciadas quedan
para un mapping posterior.

`warehouse_branch_mapping` contiene 51 relaciones confirmadas del workbook y 82
almacenes SAP actuales `UNMAPPED`, porque no existe crosswalk validado entre sus
códigos y los códigos históricos del workbook. Para las 51 relaciones conocidas,
`valid_from` y `valid_to` son **NULL**: la vigencia histórica es desconocida, no se
proyecta artificialmente. No hay conflictos multi-sucursal.

## Resolver rápido

Se materializó `reference/entity_alias/part-00000.parquet` como dataset auxiliar
reconstruible. Tiene una fila por alias/candidato y conserva `alias`,
`normalized_alias`, `priority`, `confidence`, fuente y versiones. Sólo se
usaron nombres observados de SAP, legacy, workbook y mappings; no hay aliases
manuales.

Si un alias normalizado tiene varios candidatos, se registran varias filas con
`resolution_status=AMBIGUOUS`; el consumidor no escoge arbitrariamente. En el
build observado:

- `creolina`: 122 candidatos por búsqueda tokenizada;
- `saavedra`: 11 alias de almacén;
- `segundo anillo`: no existe como alias exacto de branch aprobado y queda
  `EXAMPLE_ENTITY_NOT_FOUND`, sin inventar una sucursal.

Las consultas DuckDB del benchmark se ejecutaron sólo contra este dataset pequeño:
3 pruebas, máximo observado **7.959 ms**, muy por debajo del objetivo de un
segundo. El futuro orden de seguridad permanece: identidad → autorización →
resolución dentro del scope → hechos.

## Evidencia y reconstrucción

Código reproducible:

`validation/datalake_reference_and_crosswalk_v1/build_outputs.py`

Tests focales:

`validation/datalake_reference_and_crosswalk_v1/test_validation.py`

Evidencia estructurada:

- `reference_datasets.csv`
- `crosswalk_datasets.csv`
- `mapping_quality.csv`
- `warehouse_branch_quality.csv`
- `entity_alias_quality.csv`
- `sap_master_extractions.csv`
- `fast_lookup_benchmark.csv`
- `build_manifest.csv`
- `summary.json`

El manifest de build registra `build_id`, inputs, hashes/snapshots, paths, filas,
SHA-256, versiones, fecha y estado. El manifest JSON físico vive bajo
`DATA_ROOT/manifests/runs/`. Todos los productos de este gate son
`REBUILDABLE`; las fuentes raw legacy y el workbook preservado son
`PRESERVED_SOURCE`.

## Métricas de calidad

```text
PRODUCTS_CANONICAL=53318
L_PRODUCTS=7158
CUSTOMERS_CANONICAL=35057
SUPPLIERS_CANONICAL=2130
WAREHOUSES_CANONICAL=133
BRANCHES_CANONICAL=7
SALESPERSONS_CANONICAL=253
USERS_CANONICAL=173

CROSSWALK_MAPPED=91122
CROSSWALK_UNMAPPED=82
CROSSWALK_AMBIGUOUS=0

WAREHOUSE_BRANCH_MAPPED=51
WAREHOUSE_BRANCH_UNMAPPED=82
WAREHOUSE_BRANCH_TEMPORAL_UNKNOWN=51
WAREHOUSE_MULTI_BRANCH_CONFLICTS=0

FAST_LOOKUP_TESTS=3
FAST_LOOKUP_MAX_MS=7.959
```

`UNMAPPED` es válido y está explícito; no se ocultó con heurísticas de nombre.
Las ambigüedades del resolver se conservan como candidatos.

## Validación y cierre

- `py_compile`: PASS.
- Tests focales: **7 passed**.
- Lectura directa DuckDB de las 14 referencias, 8 crosswalks y alias: PASS.
- `git diff --check`: PASS.
- SAP/HANA writes: `0`.
- No se creó ningún Parquet `atomic`, `business` ni `decision`.
- El mirror legacy mantiene 696/696 archivos y SHA-256 byte-identical.

```text
DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi

REFERENCE_DATASETS_EXPECTED=14
REFERENCE_DATASETS_CREATED=14

CROSSWALK_DATASETS_EXPECTED=8
CROSSWALK_DATASETS_CREATED=8

ENTITY_ALIAS_DATASET_CREATED=YES

PRODUCTS_CANONICAL=53318
L_PRODUCTS=7158
CUSTOMERS_CANONICAL=35057
SUPPLIERS_CANONICAL=2130
WAREHOUSES_CANONICAL=133
BRANCHES_CANONICAL=7
SALESPERSONS_CANONICAL=253
USERS_CANONICAL=173

CROSSWALK_MAPPED=91122
CROSSWALK_UNMAPPED=82
CROSSWALK_AMBIGUOUS=0

WAREHOUSE_BRANCH_MAPPED=51
WAREHOUSE_BRANCH_UNMAPPED=82
WAREHOUSE_BRANCH_TEMPORAL_UNKNOWN=51

FAST_LOOKUP_TESTS=3
FAST_LOOKUP_MAX_MS=7.959

SAP_ACCESSED=YES
SAP_ACCESS_PURPOSE=MASTER_DATA_REFERENCE_ONLY
SAP_WRITE_COUNT=0

RAW_LEGACY_FILES_MODIFIED=0
RAW_LEGACY_FILES_DELETED=0
RAW_LEGACY_FILES_MOVED=0

ATOMIC_PARQUETS_CREATED=0
BUSINESS_PARQUETS_CREATED=0
DECISION_PARQUETS_CREATED=0

REFERENCE_CROSSWALK_READY_FOR_ATOMIC=YES
```

**TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS**

El siguiente gate queda pendiente de revisión y no se inicia automáticamente:
`TELCHI_DATALAKE_ATOMIC_BUILD_V1`.

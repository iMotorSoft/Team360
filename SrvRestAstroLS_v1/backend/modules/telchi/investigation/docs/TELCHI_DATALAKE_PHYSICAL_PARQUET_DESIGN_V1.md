# TELCHI DATA LAKE — PHYSICAL PARQUET DESIGN V1

Esta especificación define el diseño físico ejecutable del Data Lake Telchi. No copia históricos, no consulta SAP, no crea Parquet productivos ni habilita ingesta.

## A. Gate

El gate cierra en PASS porque ubicación, grain, schema, temporalidad, incrementalidad, lineage, seguridad, lectura y reconstrucción quedan definidos y testeados.

**PASS — `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS`**

Autoridades consumidas sin reabrir inventarios ni rediseñar el modelo canónico:

- `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`;
- `TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`;
- `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`;
- `TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS`.

El contexto resuelto es `ENTITY=TELCHI`, `STAGE=INVESTIGATION`, `SOURCES=LEGACY_DS + SAP_HANA + EXTERNAL_FILES` y `OUTPUTS=DATA_LAKE + PARQUET_DESIGN`. SAP conserva política read-only, pero no fue accedido.

## B. Resumen ejecutivo

V1 usa una raíz, separa evidencia preservada de productos reconstruibles y evita capas sin consumidor concreto.

- 51 contratos físicos: 3 familias raw, 14 referencias, 8 crosswalks, 20 atomic y 6 business.
- `raw/legacy/parquet/<source_relative_path>` es el destino definitivo de los 696 Parquet, sin reencode, rename ni rewrite.
- No habrá `staging`, `snapshots` ni `decision` como capas durables V1: staging será temporal de proceso, y snapshot es semántica del dataset.
- Parquet generado usa ZSTD, tipos Arrow explícitos, archivos objetivo de 128–512 MiB y row groups de 64–128 MiB.
- Los read models reemplazan nombres `360` ambiguos por grains visibles: `product_flow`, `inventory_position`, `sales_line_read_model`, `purchase_cycle_line`, `production_order_flow` y `customer_credit_state`.
- DuckDB resuelve nombres lógicos desde un registry y aplica scope autorizado antes de resolver paths y escanear Parquet.

La autoridad machine-readable está en `validation/datalake_physical_parquet_design_v1/`. `physical_datasets.csv` y `physical_columns.csv` son el contrato completo de datasets y columnas.

## C. Data Root

La única raíz física es la ya aprobada; el código, tests y documentación permanecen en Team360.

```text
DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi
LEGACY_ROOT=/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS
LEGACY_POLICY=READ_ONLY
DATA_ROOT_POLICY=DATA_ONLY
```

El sistema podrá dejar de depender del root legacy una vez que un gate posterior copie y verifique todo el mirror. Hasta entonces, esta especificación no afirma que el mirror exista.

## D. Layout físico

El layout recomendado conserva sólo responsabilidades justificadas.

```text
telchi/
├── raw/
│   ├── legacy/
│   │   ├── parquet/<source_relative_path>
│   │   ├── reference_sources/
│   │   └── auxiliary_sources/
│   └── sap/
│       ├── table_extract/<extract_id>/extraction_date=YYYY-MM-DD/run_id=<id>/
│       └── query_extract/<extract_id>/extraction_date=YYYY-MM-DD/run_id=<id>/
├── reference/<dataset_id>/
├── crosswalk/<dataset_id>/
├── atomic/<dataset_id>/[year=YYYY/month=MM|snapshot_date=YYYY-MM-DD]/
├── business/<dataset_id>/[year=YYYY/month=MM|snapshot_date=YYYY-MM-DD]/
└── manifests/
    ├── legacy_mirror/
    ├── runs/
    ├── watermarks/
    └── registry/
```

`raw/**` es `PRESERVED_SOURCE`. `atomic/**` y `business/**` son `REBUILDABLE`; `reference/**` y `crosswalk/**` son contratos versionados de referencia. `manifests/**` es metadata operacional.

No se crea una capa durable `staging/`: DuckDB/PyArrow usarán temporales locales y escritura a un run path antes de publicación atómica. No se crea una carpeta genérica `snapshots/`, porque `stock_snapshots` y `customer_credit_state` ya expresan grain y tiempo. `decision/` queda fuera de V1 hasta tener consumidor y grain concretos.

El detalle de cada path, responsabilidad y decisión está en `physical_layout.csv`.

## E. Dataset catalog

Esta tabla es el inventario físico que debe consumir el próximo gate; schema y atributos ampliados están en los CSV estructurados.

| Dataset | Layer | Grain | Source | Partition | Incremental | Security scope |
|---|---|---|---|---|---|---|
| `legacy_parquet_mirror` | raw | un archivo fuente preservado en su relative path | LEGACY_DS | NO_PARTITION | IMMUTABLE_COPY | source family; sin filtro row-level |
| `sap_table_extracts` | raw | una fila inmutable de un run de tabla SAP | SAP_HANA | EXTRACTION_DATE | DATASET_SPECIFIC | source family; sin filtro row-level |
| `sap_query_extracts` | raw | una fila inmutable de un run de query SAP | SAP_HANA | EXTRACTION_DATE | DATASET_SPECIFIC | source family; sin filtro row-level |
| `products` | reference | una versión de identidad de producto | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | product_id |
| `product_groups` | reference | una versión de grupo | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | product_group_id |
| `customers` | reference | una versión de cliente | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | customer_id |
| `suppliers` | reference | una versión de proveedor | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | supplier_id |
| `warehouses` | reference | una versión de almacén | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | warehouse_id |
| `branches` | reference | una versión de sucursal | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | branch_id |
| `document_types` | reference | una versión de tipo documental | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | company_id |
| `payment_terms` | reference | una versión de término de pago | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | branch_id |
| `channels` | reference | una versión de canal | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | branch_id |
| `units_of_measure` | reference | una versión de unidad | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | company_id |
| `warehouse_roles` | reference | una versión de rol de almacén | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | warehouse_id |
| `currencies` | reference | una versión de moneda | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | legal_entity_id |
| `users` | reference | una versión de usuario | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | organizational_scope |
| `salespersons` | reference | una versión de vendedor | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | salesperson_id;branch_id |
| `product_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | product_id |
| `customer_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | customer_id |
| `supplier_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | supplier_id |
| `warehouse_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | warehouse_id |
| `branch_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | branch_id |
| `salesperson_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | salesperson_id |
| `user_crosswalk` | crosswalk | source-native mapping por vigencia | SAP/legacy/external | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | user_id |
| `warehouse_branch_mapping` | crosswalk | almacén→sucursal por vigencia | external/SAP/legacy | NO_PARTITION | SNAPSHOT_UPSERT_SCD2 | warehouse_id;branch_id |
| `sales_documents` | atomic | un documento de venta | SAP/legacy | YEAR_MONTH | DOCUMENT_WATERMARK | customer_id;branch_id;salesperson_id |
| `sales_lines` | atomic | una línea de venta | SAP/legacy | YEAR_MONTH | DOCUMENT_WATERMARK | branch_id;salesperson_id |
| `credit_notes` | atomic | un documento NC | SAP/legacy | YEAR_MONTH | DOCUMENT_WATERMARK | customer_id;branch_id |
| `credit_note_lines` | atomic | una línea NC | SAP/legacy | YEAR_MONTH | DOCUMENT_WATERMARK | branch_id;salesperson_id |
| `inventory_movements` | atomic | una línea/evento de movimiento | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | warehouse_id |
| `stock_snapshots` | atomic | producto×almacén×snapshot_at | SAP/legacy | SNAPSHOT_DATE | SNAPSHOT_WATERMARK | warehouse_id |
| `purchase_requests` | atomic | una línea de solicitud | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | branch_id;warehouse_id |
| `purchase_orders` | atomic | una línea de orden | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | supplier_id;branch_id |
| `goods_receipts` | atomic | una línea de recepción | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | supplier_id;warehouse_id |
| `supplier_invoices` | atomic | una línea de factura proveedor | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | supplier_id;branch_id |
| `purchase_returns` | atomic | una línea de devolución | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | supplier_id;warehouse_id |
| `transfer_documents` | atomic | un documento de transferencia | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | from/to_warehouse_id |
| `transfer_lines` | atomic | una línea de transferencia | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | from/to_warehouse_id |
| `boms` | atomic | producto padre×versión/vigencia | SAP/legacy | NO_PARTITION | SNAPSHOT_WATERMARK | warehouse_id;plant_id |
| `bom_components` | atomic | BOM×componente×posición | SAP/legacy | NO_PARTITION | SNAPSHOT_WATERMARK | warehouse_id;plant_id |
| `production_orders` | atomic | una orden de producción | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | warehouse_id;plant_id |
| `production_component_consumptions` | atomic | una línea real de consumo | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | warehouse_id;plant_id |
| `production_outputs` | atomic | una línea real de output | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | warehouse_id;plant_id |
| `payments` | atomic | un pago y dirección | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | customer/supplier/branch_id |
| `reconciliations` | atomic | reconciliación×documento miembro | SAP/legacy | YEAR_MONTH | UPDATE_WATERMARK | customer/supplier/branch_id |
| `product_flow` | business | un evento que afecta producto | derived | YEAR_MONTH | REBUILD_ON_INPUT_CHANGE | warehouse/branch/salesperson_id |
| `inventory_position` | business | producto×almacén×snapshot_at | derived | SNAPSHOT_DATE | REBUILD_ON_INPUT_CHANGE | warehouse_id;branch_id |
| `sales_line_read_model` | business | una venta bruta enriquecida | derived | YEAR_MONTH | REBUILD_ON_INPUT_CHANGE | branch_id;salesperson_id |
| `purchase_cycle_line` | business | una línea de etapa de procurement | derived | YEAR_MONTH | REBUILD_ON_INPUT_CHANGE | supplier/branch/warehouse_id |
| `production_order_flow` | business | orden×producto×rol | derived | YEAR_MONTH | REBUILD_ON_INPUT_CHANGE | warehouse_id;plant_id |
| `customer_credit_state` | business | cliente×as_of_date×versión | derived | SNAPSHOT_DATE | REBUILD_ON_INPUT_CHANGE | customer_id;branch_id |

`stock_current` y `customer_credit_current` serán vistas DuckDB sobre el último corte autorizado; no son copias físicas V1.

## F. Atomic datasets

Los 20 datasets atomic preservan hechos mínimos sin convertir una observación denormalizada en verdad.

Las cabeceras se separan de líneas donde su estado propio importa: venta, NC y transferencia. El ciclo de compras conserva cinco hechos y `BaseEntry/BaseType` como links, no como una fila mágica. BOM y componentes preservan fórmula; orden, consumo y output preservan ejecución real.

`product`, `customer`, `supplier`, `warehouse`, `branch`, `user` y `salesperson` viven en `reference` porque su grain es una versión de identidad. `warehouse_branch_mapping` vive en `crosswalk` porque es una relación temporal de scope. `customer_credit_state` es derivado as-of y vive en `business`.

`movProductSB1` nunca origina por sí solo un `inventory_movement`: las 181.384 colisiones candidatas siguen protegidas por `UNKNOWN`/cuarentena hasta identidad fuerte. `movProduct` nunca se concatena como eventos.

## G. Business read models

Los seis modelos físicos reducen joins repetidos sin reemplazar atomic truth.

- `product_flow` preserva la ventaja funcional de `movProductSB1`: producto, documento/movimiento, tiempo, entrada, salida, almacén, sucursal, cliente, proveedor, vendedor, usuario, cantidad, costo, precio y lineage.
- `inventory_position` enriquece stock por almacén/sucursal a un corte explícito.
- `sales_line_read_model` une línea, cabecera y dimensiones sin mezclar gross sale, NC, pago o net sale.
- `purchase_cycle_line` expone cada etapa y sus links base sin fanout de importes.
- `production_order_flow` compara plan, consumo y output sin fingir FK producción→despacho.
- `customer_credit_state` reconstruye open, vencido y aging a fecha T desde documentos, NC, pagos y reconciliaciones.

Cada build declara inputs, hashes, schema/semantic/transformation version y output files. Un cambio de input crea un build nuevo; la publicación reemplaza sólo particiones validadas y mantiene el run manifest anterior.

## H. Legacy mirror design

El mirror definitivo será `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet`.

Cada archivo va a `raw/legacy/parquet/<source_relative_path>`. El relative path completo evita colisiones y el filename original se conserva exactamente, incluidos ejemplos como `movProduct-2022-04-30.parq` y `movProductSB1-2024-05-31.parq`.

La copia posterior exige este flujo por archivo:

```text
lstat source → reject symlink/path escape → hash+size source
→ copy to temporary destination in same filesystem
→ fsync → hash+size destination
→ compare source/destination SHA-256
→ atomic rename → re-read final hash → manifest VERIFIED
```

No se permite reencode, recompress, rename, merge, deduplicate, metadata rewrite ni cambio de mtime como sustituto de hash. `SOURCE == MIRROR` sólo cuando size y SHA-256 coinciden.

El manifest por archivo exige `source_relative_path`, `source_filename`, `destination_relative_path`, `size_bytes`, `sha256`, `family`, `filename_date`, `schema_fingerprint`, `row_count`, `copied_at` y `copy_status`. `filename_date` puede ser null y nunca sustituye tiempo de negocio. El contrato exacto está en `legacy_mirror_contract.csv`.

Los no-Parquet no se copian en este gate ni junto al mirror Parquet:

| Categoría | Destino candidato | Tratamiento posterior |
|---|---|---|
| 6 Excel | `raw/legacy/reference_sources/` si son referencia aprobada; resto se clasifica antes | Conservar original; normalizar después a `reference` sólo con schema y lineage. |
| `almacenOficina.xlsx` | `raw/legacy/reference_sources/almacenOficina.xlsx` | `REFERENCE SOURCE`; luego produce `warehouse_branch_mapping`, sin inventar vigencia. |
| 1 CSV | `raw/legacy/auxiliary_sources/` sólo si se aprueba como evidencia | Inventariar encoding/delimiter/hash; no mezclar con facts. |
| 1 Python | `raw/legacy/auxiliary_sources/code/` sólo por gate explícito | Provenance no ejecutable; nunca scheduler ni código del Data Root. |
| 2 temporales | ningún destino por defecto | Excluir; conservar sólo la entrada del inventario y razón. |

## I. Physical schemas

`physical_columns.csv` es la autoridad columna por columna para los 50 datasets con schema normalizado; el mirror legacy conserva el schema fuente y por eso no declara columnas transformadas.

El contrato Arrow/Parquet V1 usa:

| Semántica | Tipo físico | Regla |
|---|---|---|
| códigos e IDs empresariales | `string` | Preserva ceros, formato y semántica; no es magnitud. |
| canonical IDs | `string` | ID estable separado de `source_system` y `source_native_id`. |
| enteros reales/posiciones | `int32` o `int64` | Sólo para magnitudes/ordinales demostrados. |
| fecha civil | `date32` | Nunca columna genérica `date`. |
| instante | `timestamp[us,UTC]` | UTC; timezone original puede conservarse como atributo fuente si existe. |
| booleano | `bool` | No usar `Y/N` fuera de raw. |
| dinero/precio/costo | `decimal128(38,6)` | Sin float; scale no menor a la evidencia V1. |
| cantidad/tasa/cambio/confianza | `decimal128(38,12)` | Evita pérdida en unidades fraccionarias y rates. |

Si una fuente futura supera precisión/scale, se activa `STOP_PHYSICAL_DECISION_FOR_AFFECTED_DATASET`; no se redondea silenciosamente. En raw se conserva el tipo fuente. En normalizado, el writer valida overflow, nullability y rango antes de publicar.

Toda fila normalizada mantiene `canonical_id` o key canónica y, por separado, `_source_system`, `_source_native_key` y los IDs nativos aplicables. Un ID SAP numérico puede exponerse además como `int64`, pero el native key serializado sigue siendo string trazable.

## J. Partitioning

Sólo se particionan datasets temporales con scans dominantes por período.

- `YEAR_MONTH`: eventos atomic y business de flujo, con directorios `year=YYYY/month=MM` derivados del tiempo contractual declarado.
- `SNAPSHOT_DATE`: `stock_snapshots`, `inventory_position` y `customer_credit_state`.
- `EXTRACTION_DATE`: runs raw SAP, siempre bajo `extract_id` y `run_id` inmutables.
- `NO_PARTITION`: dimensiones, crosswalks, BOM y mirror legacy.

No se particiona por producto, cliente, proveedor o almacén. El objetivo por archivo generado es 128–512 MiB y por row group 64–128 MiB; son targets, no mínimos que obliguen a padding. Una partición pequeña legítima puede ser un solo archivo. La compactación sólo opera dentro de una partición derivada y nunca sobre raw preservado.

El default de compresión es ZSTD por ratio, lectura y compatibilidad DuckDB/PyArrow. El mirror conserva su codec original. Una excepción futura debe quedar por dataset en registry y decision log.

El sort se aplica sólo donde mejora locality: `product_id,warehouse_id,event_at` en movimientos/flow; `customer_id,document_date` en ventas; `supplier_id,document_date` en compras; `snapshot_at,warehouse_id,product_id` en estados. No es garantía de orden global entre archivos.

## K. Temporal/snapshot representation

Cada dataset declara una verdad temporal explícita y no usa `date` genérico.

Eventos usan según corresponda `event_at`, `document_date`, `posting_date`, `due_date`, `order_date` o `reconciliation_date`. Estados usan `snapshot_at` o `valid_from/valid_to`. Toda fila normalizada conserva `_source_extracted_at` e `_ingested_at`.

Las correcciones no borran historia. Evento nuevo se añade; cancelación/reversión conserva el hecho y su estado; restatement produce nueva observación/build con manifest. Late arrivals reabren sólo la ventana afectada y publican una nueva versión de partición.

La política legacy de snapshots es:

| Familia | Source snapshot | Canonical target | Dedupe y cutoff |
|---|---|---|---|
| `movProduct` | archivo raw y filename date sólo como observación | `stock_snapshots` únicamente si el grain producto×almacén×corte queda probado | Dedupe dentro del mismo corte por key fuerte; elegir último corte `<= as_of`, nunca sumar archivos. |
| `movProductSB1` | observación business repetible | `product_flow` sólo para filas con identidad fuerte | Mismo native event en varios snapshots es observación repetida; ambiguos quedan fuera de sumas. |
| `cash` | snapshot specialized raw | ningún atomic V1 por defecto | No convertir en `payments` sin crosswalk confirmado; cutoff declarado por archivo/observación. |
| `cuentasxCobrar` | estado as-of raw | input de validación o `customer_credit_state` versionado | No convertir saldo en pago; una fila más reciente restates state, no borra eventos. |

`stock_current` será una vista sobre `stock_snapshots` con `row_number()` por producto/almacén, filtrada por scope y máximo `snapshot_at`. `customer_credit_current` aplica la misma regla a `customer_credit_state`. No se materializan hasta que una medición justifique duplicación.

## L. Incremental/watermark strategy

No existe watermark global; cada dataset conserva la estrategia adecuada a su fuente.

- `DOCUMENT_WATERMARK`: ventas y NC con cursor compuesto `source_update_at + source_document_id`.
- `UPDATE_WATERMARK`: movimientos, ciclo documental, producción, pagos y reconciliaciones con `source_update_at + source_native_key`.
- `SNAPSHOT_WATERMARK`: stock y BOM por `snapshot_at`.
- `SNAPSHOT_UPSERT_SCD2`: dimensiones/crosswalks por extracción y comparación de atributos.
- `DATASET_SPECIFIC`: raw SAP declara cursor y query hash por extract ID.
- `REBUILD_ON_INPUT_CHANGE`: business por IDs/hashes de manifests de input.
- `IMMUTABLE_COPY`: legacy por SHA-256.

Cada watermark registra `dataset_id`, `watermark_type`, `watermark_field`, `last_success_value`, `last_attempt_value`, `source_max_value`, `extraction_started_at`, `extraction_completed_at` y `status`. Vive en `manifests/watermarks/<dataset_id>.json`; cada cambio exitoso también queda referenciado por un run manifest inmutable.

SAP no se presume append-only. Cada extracción define backfill/reconciliation window configurable, reconsulta updates y claves del borde, compara máximos y conserva restatements. Fallo no avanza `last_success_value`. Cancelaciones, pagos tardíos y reconciliaciones tienen ventanas independientes.

## M. Lineage físico

Las columnas técnicas usan `_`; las columnas de negocio y scope no.

El núcleo normalizado es `_source_system`, `_source_dataset`, `_source_native_key`, `_source_extracted_at`, `_ingested_at`, `_transformation_version`, `_semantic_version` y `_lineage_quality`. `_source_file` es required para legacy y optional en otros; `_source_snapshot_at` es required en snapshots.

`_source_document_type`, `_source_document_id`, `_source_line_id` y `_source_transaction_id` son required cuando la fuente/grain los soporta y optional o not applicable en el resto. No se agregan campos SAP vacíos a toda dimensión. Los siete perfiles completos (`source_file`, `sap_raw`, `reference`, `crosswalk`, `event`, `snapshot`, `derived`) están en `lineage_physical_contract.csv`.

Los manifests mínimos son:

| Tipo | Registro |
|---|---|
| legacy mirror | `manifest-v1.parquet` por archivo + JSON summary del run; source/destination hash y status. |
| SAP extraction | JSON inmutable por run: extract/query ID, query hash, parámetros no secretos, cursor, filas, archivos y hashes. |
| atomic build | JSON inmutable: inputs, schema/transformation version, output partitions/files, counts, hashes, validation status. |
| business build | Igual a atomic, más semantic version y métricas/checks de fanout. |
| snapshot | Run manifest con cutoff, autoridad, dedup rule, source maxima y output partition. |

Así puede responderse qué se ejecutó, con qué input, qué output produjo, versión, watermark, hash y estado sin desplegar una plataforma de metadata separada.

## N. Crosswalk

Los siete crosswalks de identidad comparten un contrato físico y permiten ingesta incompleta.

```text
canonical_id string nullable sólo cuando status=UNMAPPED
source_system string required
source_native_id string required
valid_from timestamp[us,UTC] nullable
valid_to timestamp[us,UTC] nullable
mapping_source string required
confidence decimal128(38,12) required
status CONFIRMED|PROPOSED|UNKNOWN|UNMAPPED
```

`warehouse_branch_mapping` usa `warehouse_id`, `branch_id`, `valid_from`, `valid_to`, `mapping_source`, `confidence` y `status`. Cuando vigencia o branch histórico se desconocen, permanecen null con `UNKNOWN/UNMAPPED`; no se inventan fechas ni se proyecta el mapping actual al pasado.

## O. Security readiness

Cada dataset declara `security_domain`, `scope_columns`, `sensitive_columns`, `sensitive_metrics` y política cross-scope en `security_physical_contract.csv`.

El administrador tiene `FULL_ACCESS` en este gate, pero el orden futuro queda fijado:

```text
authenticated principal
→ authorized domains/datasets/columns/metrics/scopes
→ registry resolves allowed paths and mandatory partition/row predicates
→ DuckDB scans only authorized Parquet
→ aggregation/retrieval
→ assistant
```

No se registra una vista sin scope para exponerla al assistant. Un branch desconocido no amplía acceso: la política futura debe resolverlo explícitamente o fallar cerrada. Campos como costos, margen, crédito, deuda, fórmula y cuenta bancaria exigen capability de columna/métrica además del scope row-level.

## P. DuckDB read strategy

Los consumidores usarán IDs lógicos, no paths hardcodeados.

El registry JSON proyectado desde `dataset_registry.csv` registra path, versión, grain, particiones, scopes e inputs. Un bootstrap controlado crea vistas versionadas con `read_parquet(..., hive_partitioning=true, union_by_name=false, filename=true)`. `union_by_name=false` hace fallar schema drift en vez de ocultarlo.

Los globs apuntan sólo a archivos publicados por manifests `SUCCEEDED`. Raw legacy no se lee con un glob global porque sus familias pueden tener schemas diferentes; cada family resolverá su lista desde el mirror manifest. Predicate pushdown usa año/mes/snapshot y columnas scope antes de joins.

Macros o vistas `stock_current` y `customer_credit_current` seleccionan la última observación autorizada. Las views business apuntan a Parquet materializado, no reconstruyen todos los joins por consulta. No se implementa API final en este gate.

## Q. Dataset registry

La fuente versionada más simple es `dataset_registry.csv`; el runtime futuro consumirá una proyección JSON validada y generada, no una segunda configuración manual.

No se elige YAML porque no aporta capacidad y agrega parser; SQLite introduce estado mutable innecesario; Python config acopla datos a código. CSV permite diff y tests, y JSON permite lectura portable. Ambos se validan contra `physical_datasets.csv`; no son dos autoridades editables.

Versionado:

- `schema_version`: cambia major por incompatibilidad física, minor por columna compatible y patch por metadata sin cambio de lectura.
- `semantic_version`: cambia cuando significado, métrica, cutoff, dedup o autoridad cambia, aunque el schema sea igual.
- `transformation_version`: identifica código/config reproducible de build; cambia ante lógica ejecutable distinta.

Nombres de directorio, dataset, columnas, particiones y manifests usan `snake_case`. Raw conserva nombres nativos y filenames exactos. Las versiones no llevan timestamps; los run IDs sí.

## R. Decision log

Las 15 decisiones ejecutables están en `decision_log.csv`; éstas son las de mayor impacto.

- Un root y separación `PRESERVED_SOURCE`/`REBUILDABLE`.
- Mirror en `raw/legacy/parquet/<source_relative_path>`.
- Sin staging/snapshots/decision durables V1.
- ZSTD, decimal128 y temporal partitions de baja cardinalidad.
- Current state mediante views, no copia física.
- Nombres business con grain explícito en lugar de `360` ambiguo.
- Raw preserva overlap Legacy/SAP; atomic aplica autoridad por concepto/ventana, con cuarentena si no hay resolución.
- Registry CSV versionado y JSON generado.
- DuckDB con views registry-backed y `union_by_name=false`.
- Publicación por manifest validado y reemplazo de particiones derivadas, nunca mutación raw.

## S. Riesgos residuales

Los riesgos pendientes están encapsulados y no bloquean la especificación física.

- Algunos legacy rows no alcanzarán identidad atomic y permanecerán raw/quarantine.
- Vigencia histórica warehouse→branch puede seguir null, lo que impide atribución branch pero no warehouse.
- La precisión fuente SAP debe verificarse en el primer extractor; overflow detiene sólo el dataset afectado.
- Ventanas de backfill SAP deberán calibrarse con evidencia operativa; no se inventa una global.
- El target de archivos es orientativo hasta medir datasets reales; compaction no debe producir churn.
- El registry/runtime y enforcement RBAC aún no existen; este gate sólo garantiza que los scopes físicos están presentes.
- `cash`, `purchaseExpense` y `productTransform` siguen source-scoped hasta crosswalk probado.

No surgió contradicción que exija `STOP_PHYSICAL_DECISION_FOR_AFFECTED_DATASET`. SAP no fue consultado.

## T. Siguiente gate

El siguiente gate debe limitarse a `TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1`.

Debe crear únicamente los directorios necesarios para el mirror, copiar 696 archivos sin transformación, calcular SHA-256 en fuente y destino, verificar size/schema fingerprint/row count, publicar el manifest y demostrar cero modificaciones/moves/deletes en source. No debe construir atomic, business ni ingesta SAP.

La evidencia ejecutable de este gate incluye `build_outputs.py`, `test_validation.py`, los 10 CSV mínimos, `dataset_registry.csv`, `decision_log.csv` y `summary.json`. No contiene `.parq` ni `.parquet`.

## Cierre obligatorio

Los contadores se derivan de los contratos estructurados generados.

```text
DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi

PHYSICAL_DATASETS=51
ATOMIC_DATASETS=20
BUSINESS_DATASETS=6
REFERENCE_DATASETS=14
CROSSWALK_DATASETS=8

LEGACY_PARQUET_EXPECTED=696
LEGACY_MIRROR_PATH=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet
LEGACY_COPY_EXECUTED=NO

PARTITION_STRATEGIES=4
INCREMENTAL_STRATEGIES=7
WATERMARK_CONTRACTS=44
LINEAGE_PHYSICAL_CONTRACTS=7
SECURITY_PHYSICAL_CONTRACTS=51

SAP_ACCESSED=NO
SAP_WRITE_COUNT=0

PRODUCTION_PARQUETS_CREATED=0
LEGACY_PARQUETS_COPIED=0
SOURCE_FILES_MODIFIED=0
SOURCE_FILES_MOVED=0
SOURCE_FILES_DELETED=0

PHYSICAL_PARQUET_DESIGN_READY=YES

TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS
```

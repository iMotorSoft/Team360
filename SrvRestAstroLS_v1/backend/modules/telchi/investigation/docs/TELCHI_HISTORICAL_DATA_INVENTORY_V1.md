# TELCHI DATA LAKE — HISTORICAL DATA INVENTORY V1

## A. Gate

**PASS — `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`**

El inventario físico, Parquet y auxiliares se completó sobre el root histórico en modo read-only. No se consultó SAP/HANA por diseño de esta etapa; el lineage de sistema se conserva como unknown cuando no está declarado en los footers o nombres históricos.

## B. Resumen ejecutivo

- Se relevaron **706 archivos** (696 Parquet y 10 auxiliares), 762,60 MB en total; las fuentes no fueron modificadas.
- Los Parquet contienen **25.823.339 filas** según metadata de footer; el mayor volumen está en compras, ventas y movimientos.
- Hay familias mensuales históricas desde 2012 hasta 2024, además de snapshots maestros y una serie diaria de costos.
- `movProduct` es compacto y agregado; `movProductSB1` conserva trazabilidad transaccional mucho más rica.
- `saleProduct` es el histórico legacy; `saleSB1Product` es una familia SAP B1 enriquecida por líneas/documentos.
- `almacenOficina.xlsx` es una referencia explícita almacén→oficina/sucursal.
- Se observan cambios de schema en `movProductSB1`, `payout` y `ncB1Product`, principalmente nombres históricos.
- Las fechas de filename y las fechas contenidas deben tratarse separadamente: muchos archivos son snapshots acumulativos.
- La calidad presenta claves compuestas, columnas auxiliares de índice y riesgo de solapamiento entre snapshots.
- No se diseñaron capas nuevas ni Parquet definitivos; el siguiente gate debe decidir lineage y contratos.

## C. Inventario físico

Root consultado: `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS`.

### Conteo y volumen

| Extensión | Archivos |
|---|---:|
| `.csv` | 1 |
| `.parq` | 696 |
| `.py` | 1 |
| `.xlsx` | 6 |
| `[no_extension]` | 2 |

| Tipo | Archivos |
|---|---:|
| `csv` | 1 |
| `otros` | 2 |
| `parq` | 696 |
| `py` | 1 |
| `xlsx` | 6 |

Directorios: el root es plano; no se encontraron subdirectorios con archivos. Volumen total: **799.639.194 bytes (762,60 MB)**.

La tabla completa reproducible está en `historical_files_inventory.csv`; incluye ruta relativa, tamaño, modificación y SHA-256. Los únicos nombres temporales/anómalos detectados son `.goutputstream-4D8NM0` y `.goutputstream-CKMFL0`; `read_parquet_schema.py` es auxiliar de código histórico. No hubo hashes repetidos exactos entre archivos.

## D. Familias de Parquet

`family` elimina solo la fecha del filename y el sufijo `-h`; los nombres estáticos permanecen como familias individuales.

| Familia | Archivos | Fecha filename min | Fecha filename max | Fecha contenida min → max | Volumen | Filas | Schemas |
|---|---:|---|---|---|---:|---:|---:|
| `movProductSB1` | 26 | 2022-04-30 | 2024-05-31 | 2022-04-01 → 2024-05-31 | 200,85 MB | 4.033.041 | 2 |
| `saleSB1Product` | 77 | 2018-01-31 | 2024-05-31 | 2018-01-02 → 2024-05-31 | 171,70 MB | 5.621.744 | 2 |
| `saleProduct` | 52 | 2018-01-31 | 2022-04-30 | 2018-01-02 → 2022-04-05 | 156,23 MB | 3.785.327 | 1 |
| `productTracking` | 39 | 2019-01-31 | 2022-04-30 | 2019-01-01 → 2022-04-04 | 50,11 MB | 3.742.587 | 1 |
| `movProduct` | 63 | 2017-01-31 | 2022-04-30 | 2017-01-31 → 2022-04-30 | 40,02 MB | 2.597.952 | 1 |
| `reconB1` | 13 | 2022-04-30 | 2023-05-31 | 2022-04-01 → 2023-05-31 | 31,37 MB | 869.473 | 1 |
| `cash` | 40 | 2019-01-31 | 2022-04-30 | 2018-11-06 → 2022-04-05 | 31,11 MB | 1.177.874 | 1 |
| `purchaseExpense` | 124 | 2012-01-31 | 2022-04-30 | 2014-04-15 → 2022-03-28 | 29,63 MB | 2.122.092 | 1 |
| `purchase` | 121 | 2012-03-31 | 2022-03-31 | 2012-03-27 → 2022-04-06 | 19,43 MB | 216.655 | 1 |
| `paymentB1` | 13 | 2022-04-30 | 2023-05-31 | 2022-04-01 → 2023-05-31 | 16,72 MB | 368.552 | 1 |
| `cuentasxCobrar` | 27 | 2020-01-31 | 2022-03-31 | 2019-10-22 → 2022-03-07 | 4,11 MB | 125.233 | 1 |
| `wareHouseSB1` | 1 | — | — | 2021-12-08 → 2024-06-03 | 2,34 MB | 819.167 | 1 |
| `ProductSaleCostDay` | 30 | 2021-12-03 | 2022-03-25 | 2021-12-03 → 2022-03-25 | 2,22 MB | 174.425 | 1 |
| `ncB1Product` | 27 | 2022-04-30 | 2024-06-30 | 2022-04-01 → 2024-06-03 | 1,90 MB | 19.933 | 1 |
| `product` | 1 | — | — | — → — | 1,24 MB | 25.221 | 1 |
| `productTransform` | 20 | 2019-01-31 | 2020-08-31 | 2019-01-02 → 2020-08-15 | 0,87 MB | 41.397 | 1 |
| `productSB1` | 1 | — | — | 2022-03-31 → 2024-06-03 | 0,63 MB | 11.245 | 1 |
| `prontoProducts` | 1 | — | — | — → — | 0,40 MB | 15.182 | 1 |
| `payout` | 9 | 2019-11-30 | 2021-11-30 | 2019-11-02 → 2021-11-22 | 0,38 MB | 17.643 | 3 |
| `clientSB1` | 1 | — | — | — → — | 0,35 MB | 11.512 | 1 |
| `person` | 1 | — | — | — → — | 0,28 MB | 11.969 | 1 |
| `mpRel` | 1 | — | — | — → — | 0,12 MB | 10.490 | 1 |
| `productTKB` | 1 | — | — | — → — | 0,05 MB | 1.450 | 1 |
| `recetasNiveles01` | 1 | — | — | — → — | 0,04 MB | 1.690 | 1 |
| `oactSB1` | 1 | — | — | — → — | 0,03 MB | 523 | 1 |
| `productosPrioridad` | 1 | — | — | — → — | 0,03 MB | 764 | 1 |
| `oitbSB1` | 1 | — | — | 2019-02-05 → 2022-12-01 | 0,01 MB | 38 | 1 |
| `owhsSB1` | 1 | — | — | — → — | 0,01 MB | 59 | 1 |
| `wareHouseOffice` | 1 | — | — | — → — | 0,00 MB | 41 | 1 |
| `sapWhsOfficeName` | 1 | — | — | — → — | 0,00 MB | 60 | 1 |

La tabla completa es `historical_dataset_families.csv`. La fecha de filename no fue usada como fecha de negocio. `missing_calendar_months` documenta meses sin archivo dentro del rango de cada familia.

## E. Schemas y evolución

`historical_parquet_schemas.csv` contiene una fila por Parquet con columnas, tipos, row groups, compression, creator/footer, conteos de null del footer y estadísticas min/max de campos temporales disponibles. `historical_schema_evolution.csv` contiene la matriz columna × familia solicitada.

Hallazgos principales:

- La mayoría de familias mensuales conserva schema estable dentro de su período.
- `movProductSB1` tiene **45 columnas** en los archivos iniciales, pero en archivos posteriores aparecen renombres `OINV_DocNum`→`OINV.DocNum`, `OINV_CardCode`→`OINV.CardCode` y `UserSB1`→`User`; no deben tratarse como nuevas dimensiones sin una decisión semántica.
- `payout` agrega `UserName` en parte de su historia; esto es una evolución real del schema, no evidencia suficiente de cambio de granularidad.
- `ncB1Product` usa variantes `fu_*` frente a campos análogos de ventas; la semántica debe conservarse separada hasta reconciliación.
- `__index_level_0__` aparece en múltiples Parquet y es un artefacto de exportación, no una clave de negocio confirmada.

## F. `movProduct` / `movProductSB1`

### `movProduct`

- **Granularidad observada:** fila producto × almacén × período/snapshot (`WareHouseCode`, `ProductCode`, `YMD`), con `ProductMovCant`; no contiene `TransNum`, documento, línea documental, cliente, proveedor ni vendedor.
- `TSSync` coincide operacionalmente con la fecha de generación/sincronización del archivo; `YMD`/`YM` son períodos derivados. Esto respalda snapshot/período, no prueba por sí solo que sea fecha de extracción.
- Puede servir como evidencia histórica de posición/variación agregada por producto y almacén, pero no permite reconstruir una cadena documental.

### `movProductSB1`

- **Granularidad observada:** línea de movimiento de inventario enriquecida: `TransNum` + `DocLineNum` + `ItemCode`/`Warehouse`, con `TransType`, `base_ref`, `DocDate`, `InQty`, `OutQty`, costos y saldo.
- **Trazabilidad presente:** producto, documento/base reference, movimiento, entrada/salida, almacén, cliente (cuando el join resolvió), vendedor, oficina, usuario, fecha, cantidad, costo y precio de venta. Importación, lote y serie no aparecen como campos dedicados en el schema inventariado.
- La distinción entre `movProduct` y `movProductSB1` está respaldada por schema y métricas reproducibles en `historical_movproduct_analysis.csv`, no solo por el sufijo `SB1`.
- El origen SAP B1 es **LIKELY**, por `TransNum`, `TransType`, `OINV.*`, `WhsCode` y nomenclatura de documentos; es **UNKNOWN como declaración formal** porque no hay metadata de lineage en los Parquet.
- Métricas: 2.597.952 filas, 14.659 productos, 38 almacenes y 63 períodos YMD; 1.068.611 filas con cantidad no cero.
- Métricas: 4.033.041 filas, 10.155 productos, 64 almacenes, 3.851.657 TransNum, 1.019.333 filas InQty y 3.012.388 filas OutQty; duplicados de clave candidata dentro de archivo: 181.384.
- Solapamiento de filename: 2022-04. Ese solapamiento no demuestra que ambos conjuntos sean duplicados: su granularidad y columnas son distintas.

## G. Excel/CSV auxiliares

`historical_auxiliary_files.csv` contiene hojas, filas, columnas, schema y duplicados por archivo. Todos los `.xlsx` encontrados tienen una sola hoja; `artist.csv` es un auxiliar no relacionado con Telchi (nombres de artistas).

### `almacenOficina.xlsx`

- Columnas observadas: `WareHouseCode, WareHouseName, OfficeCode, Oficina`.
- 51 almacenes, 7 códigos de oficina y 7 nombres de oficina.
- Almacenes sin oficina: ninguno observado.
- Filas duplicadas exactas por mapping: 0; almacenes con múltiples oficinas: ninguno.
- Oficinas con múltiples almacenes: 5 casos; ver `almacen_oficina_analysis.json` para el detalle.
- Conclusión: es una referencia maestra útil para normalizar almacén→oficina, pero debe versionarse con vigencia temporal antes de usarla como dimensión histórica.

## H. Relaciones detectadas

| Relación | Estado | Evidencia / límite |
|---|---|---|
| `movProduct.ProductCode` ↔ `movProductSB1.ItemCode` | LIKELY | Identificador de producto y períodos solapados; tipos/nombres distintos; no se probó equivalencia completa. |
| `movProduct.WareHouseCode` ↔ `movProductSB1.Warehouse` / `WhsCode` | POSSIBLE | Representan almacén, pero uno es código numérico y otros son códigos/texto; requiere catálogo temporal. |
| `saleSB1Product.DocEntry` ↔ `movProductSB1` documento/base reference | POSSIBLE | Hay campos documentales, pero no todos los movimientos son ventas y no existe join formal universal en legacy. |
| `purchase.NroOrden` ↔ `purchaseExpense.NroOrden` | LIKELY | Clave explícita compartida y misma fuente legacy; cardinalidad debe validarse antes de unir. |
| `almacenOficina.WareHouseCode` ↔ campos de almacén | CONFIRMED (por código) | La tabla contiene el mapping explícito; vigencia histórica no está documentada. |
| archivos snapshot de una misma familia | CONFIRMED | Fecha mensual en filename y filas repetidas entre cortes son esperables; no equivale a duplicado físico. |

No se convierten correlaciones en hechos SAP. La evidencia detallada de claves y calidad está en los CSV externos.

## I. Calidad y riesgos

`historical_quality_by_family.csv` mide claves incompletas, duplicados dentro de cada archivo, cantidades negativas/cero y valores de almacén no encontrados en `almacenOficina.xlsx` cuando fue posible. Las claves son candidatas de diagnóstico y no contratos confirmados.

| Familia | Filas | Clave candidata | Incompletas | Duplicados dentro de archivo | Archivos afectados |
|---|---:|---|---:|---:|---:|
| `saleSB1Product` | 5.621.744 | `DocEntry+ItemCode` | 0 | 3.579.847 | 77 |
| `movProductSB1` | 4.033.041 | `TransNum+DocLineNum+ItemCode+Warehouse` | 0 | 181.384 | 26 |
| `movProduct` | 2.597.952 | `WareHouseCode+ProductCode+YMD` | 0 | 0 | 0 |
| `purchase` | 216.655 | `NroOrden+PurchaseProductCode` | 0 | 319 | 72 |
| `purchaseExpense` | 2.122.092 | `NroOrden+ProductCode` | 0 | 1.861.809 | 124 |
| `cash` | 1.177.874 | `NroTransaccion` | 0 | 7.377 | 39 |
| `productTracking` | 3.742.587 | `NroTrasaccion+ProductCode+TrackingDate` | 0 | 30.795 | 39 |
| `paymentB1` | 368.552 | `DocEntry` | 0 | 0 | 0 |
| `reconB1` | 869.473 | `ReconNum+LineSeq` | 0 | 0 | 0 |

Los duplicados de `cash`, `purchaseExpense`, `cuentasxCobrar` y otras familias pueden ser repetición de snapshots o una clave demasiado corta; no se clasifican automáticamente como errores. En `saleSB1Product`, `DocEntry+ItemCode` es la clave diagnóstica porque `WhsCode` está vacío en parte del histórico `-h`; ese campo queda como dimensión opcional a reconciliar.

Principales riesgos que condicionan una migración futura:

- Los snapshots mensuales pueden producir doble conteo si se concatenan sin una política de corte/versión.
- Las claves de negocio no son uniformes: algunas familias tienen documento + línea, otras solo producto/almacén/período, y otras conservan índices pandas.
- Fechas como `YMD`, `YM`, `TrackingDate` y `ExpirationDate` son strings; no tienen la misma confiabilidad que timestamps.
- La presencia de nombres y datos derivados (`DocTotal`, `ItemSale`, `Deuda`, `Limite`) no prueba que sean hechos atómicos ni que su cálculo sea reproducible.
- Valores nulos, ceros y negativos tienen semántica dependiente del dataset: por ejemplo, negativos en movimientos pueden representar salidas y no errores.
- El mapping almacén→oficina no tiene vigencia ni evidencia de historización.
- La ausencia de lote/serie/importación dedicados en `movProductSB1` limita la trazabilidad completa solicitada.

## J. Datasets prioritarios

| Prioridad | Familias | Motivo |
|---|---|---|
| CRITICAL | `saleSB1Product`, `movProductSB1` | Ventas/movimientos SAP B1 con documentos, productos, almacén, cantidades y costos; alto valor de trazabilidad. |
| HIGH_VALUE | `purchase`, `purchaseExpense`, `saleProduct`, `ncB1Product`, `paymentB1`, `reconB1` | Compras, gastos, ventas legacy, notas de crédito, pagos y conciliaciones; cubren preguntas económicas clave con lineage incompleto. |
| SUPPORTING | `productTracking`, `productTransform`, `payout`, `cash`, `cuentasxCobrar`, `ProductSaleCostDay` | Movimientos operativos, producción/transformación, caja, cuentas por cobrar y costos derivados; útiles pero con semántica/cobertura desigual. |
| REFERENCE | `product`, `productSB1`, `clientSB1`, `person`, `wareHouseSB1`, `owhsSB1`, `sapWhsOfficeName`, `wareHouseOffice`, `almacenOficina.xlsx`, `oitbSB1`, `oactSB1`, `recetasNiveles01` | Catálogos, productos, clientes, almacenes, mapping y recetas. |
| LEGACY_UNKNOWN | `mpRel`, `productosPrioridad`, `prontoProducts`, `productTKB`, `artist.*`, `horizontalTeam.xlsx`, `materiaPrima01.xlsx`, `matrizElaboración.xlsx` | Existe contenido, pero el uso Telchi y la vigencia no quedan probados en este inventario. |
| REDUNDANT_CANDIDATE | Ninguno declarado | No se elimina ni descarta ningún archivo; la redundancia requiere reconciliación semántica. |

## K. Riesgos / Unknowns

- No se consultó SAP/HANA y no se inferió equivalencia entre legacy SQL Server, SAP B1 y cada Parquet.
- No existe en los footers un lineage formal con consulta, sistema origen, zona horaria, usuario extractor o snapshot watermark.
- Filename date puede ser extracción, snapshot, fecha de corte o período; la clasificación por familia está documentada como evidencia, no como contrato definitivo.
- No se determinó una autorización histórica por fila; el usuario fue considerado administrator/all para este inventario. El requisito futuro de autorización previa al retrieval/análisis queda registrado, sin implementarlo.
- Los `xls` clásicos no aparecieron; sí seis `.xlsx`, un `.csv`, 696 Parquet, dos temporales sin extensión y un `.py`.
- Las métricas completas de null por campo no se forzaron sobre todo el universo: se usó metadata/footer y métricas focales para proteger memoria y tiempo. Requiere una auditoría de nulls por campo en el gate siguiente si se decide migración.

## L. Recomendación para el siguiente gate

Antes de diseñar Parquet nuevos, cerrar un segundo inventario independiente: **conocimiento/pruebas SAP ya realizado**, incluyendo consultas, tablas, semántica, cardinalidad, límites READ ONLY, evidencia y gaps. Después, aprobar un contrato de lineage y una política de snapshots/solapamientos; recién entonces evaluar un modelo físico.

## Control de seguridad y cierre

```text
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
SOURCE_FILES_MODIFIED=0
SOURCE_FILES_DELETED=0
SOURCE_FILES_MOVED=0
TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS
```

### Evidencia reproducible

- `historical_files_inventory.csv`
- `historical_parquet_schemas.csv`
- `historical_dataset_families.csv`
- `historical_schema_evolution.csv`
- `historical_auxiliary_files.csv`
- `historical_quality_by_family.csv`
- `historical_movproduct_analysis.csv`
- `almacen_oficina_analysis.json`
- `movproduct_comparison.json`

Evidencia externa: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/historical_data_inventory_v1`. Informe versionado: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md`.

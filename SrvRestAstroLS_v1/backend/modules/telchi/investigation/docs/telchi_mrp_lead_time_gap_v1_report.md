# TELCHI — MRP LEAD TIME GAP V1

## Gate

`TELCHI_MRP_LEAD_TIME_GAP_V1` — **PASS**

No MRP executed. SAP/HANA was SELECT-only; `SAP_WRITE_COUNT=0`.

## Universo

- Artículos: **16,853**; activos: **12,041**; MRP incluidos: **13,338**.
- BUY activos incluidos en MRP: **10,037**; MAKE activos MRP: **1,087**.
- Sin SAP lead time: **1,456** NULL y **0** cero (total **1,456**); BUY NULL/cero: **1,183**; MAKE NULL/cero: **273**.
- BUY con cualquier historia y sin parámetro: **241**; con historia completa N≥3: **66**.
- Comparables: **5,837**; sin historia completa: **1,997**; recepciones completas válidas: **85,281**; cobertura comparable: **58.15%**.

## Lead Time SAP

`OITM.LeadTime` queda nombrado prudentemente `SAP_CONFIGURED_LEAD_TIME`. La evidencia confirma que es un campo de OITM, único por artículo y no dimensionado por proveedor/tipo/almacén en el baseline; no demuestra por sí sola la promesa proveedor→disponibilidad física.

## Lead Time real

La métrica primaria es `CompleteReceiptLeadTime`: OPOR.DocDate → OPDN.DocDate cuando la suma recibida alcanza la cantidad ordenada. Primera recepción, parciales y abiertos se conservan fuera de los percentiles primarios.

| Tipo | N completo | First median/p90 | Complete median/p90/p95 |
|---|---:|---:|---:|
| LF | 77,847 | 0/4 | 0/4/6 |
| IMP | 4,355 | 3/87 | 3/85/132 |
| LP | 2,919 | 7/43 | 7/49/100 |
| SAA | 160 | 7/34 | 7/34/55 |

## Comparación

- Denominador: **active MRP BUY items with N>=3 nonnegative complete receipts**.
- SAP por debajo de mediana: **295 (5.05%)**.
- SAP por debajo de p90: **3,901 (66.83%)**.
- Entre mediana y p90: **3,606**; SAP ≥ p90: **1,870**; sin parámetro: **1,183**.

## Importaciones

N completo **4,355**; first median/p90 **3/87** días; complete median/p90/p95 **3/85/132** días.

## Casos críticos / representativos

### Bien parametrizados
| ItemCode | Description | PurchaseType | SAPLeadTime | ObservedMedian | ObservedP90 | SampleN | GapClassification |
|---|---|---|---|---|---|---|---|
| L00205 | ETIQUETA PARA MATERIA PRIMA | MULTIPLE | 10.00 | 2 | 10 | 10 | NO_GAP_CONFIRMED |
| L00562 | FRASCO LISO TRANSPARENTE - 1L. (ALCOHOL GEL) | MULTIPLE | 20.00 | 7 | 20 | 15 | NO_GAP_CONFIRMED |
| L02290 | VASO PRECIPITADO FORMA BAJA 100 mL. | MULTIPLE | 5.00 | 0 | 5 | 19 | NO_GAP_CONFIRMED |

### SAP potencialmente optimista
| ItemCode | Description | PurchaseType | SAPLeadTime | ObservedMedian | ObservedP90 | SampleN | GapP90 | Confidence |
|---|---|---|---|---|---|---|---|---|
| L01128 | CREOLINA EXTRACTO x 200kg. MATERIA PRIMA | IMP | 40.00 | 106 | 330 | 8 | 290.00 | MEDIUM_CONFIDENCE |
| L00242 | FRASCO ACANALADO CAFE REFORZADO - 500ml. CREOLINA | MULTIPLE | 20.00 | 31 | 203 | 5 | 183.00 | MEDIUM_CONFIDENCE |
| L01772 | SULFATO DE COBRE x 25kg. | IMP | 40.00 | 130 | 210 | 5 | 170.00 | MEDIUM_CONFIDENCE |

### Sin SAP lead time
| ItemCode | Description | PurchaseType | SAPLeadTime | ObservedMedian | ObservedP90 | SampleN | GapClassification |
|---|---|---|---|---|---|---|---|
| L03153 | PAPEL FILTRO (58x58cm.) | MULTIPLE | — | 0 | 4 | 21 | SAP_NOT_POPULATED |
| L02885 | PORTA OBJETO ESMERILADO B/MATE x 50unid | MULTIPLE | — | 0 | 4 | 16 | SAP_NOT_POPULATED |
| L03335 | JABON BASE DE GLICERINA BARRA x kg. | MULTIPLE | — | 0 | 98 | 15 | SAP_NOT_POPULATED |

### Importación relevante
| ItemCode | Description | PurchaseType | SAPLeadTime | ObservedMedian | ObservedP90 | SampleN | GapP90 |
|---|---|---|---|---|---|---|---|
| L01128 | CREOLINA EXTRACTO x 200kg. MATERIA PRIMA | IMP | 40.00 | 106 | 330 | 8 | 290.00 |
| L00968 | TAPA SPRAY  CUELLO 24 | MULTIPLE | 40.00 | 10 | 212 | 28 | 172.00 |
| L00044 | ACIDO ESTEARICO GRANULADO x CAJA 25kg. | IMP | 40.00 | 122 | 202 | 6 | 162.00 |

## Proveedor

- Filas detalladas item×proveedor×tipo: **6,564**; filas proveedor×tipo N≥5: **322**.

| Supplier | PurchaseType | N | median | p90 |
|---|---|---:|---:|---:|
| PL000032 | LF | 7,905 | 0 | 4 |
| PL000017 | LF | 5,908 | 0 | 2 |
| PL000007 | LF | 4,571 | 0 | 4 |
| PL000026 | LF | 3,584 | 1 | 6 |
| PL000074 | LF | 3,376 | 0 | 3 |
| PL000003 | LF | 3,344 | 0 | 4 |
| PL000002 | LF | 3,189 | 1 | 6 |
| PL000001 | LF | 2,357 | 0 | 3 |

## Multiproveedor

- Artículos con ≥2 proveedores regulares (N≥5 por grupo): **303**.
- No se colapsaron sus distribuciones en una sola conclusión: el único OITM.LeadTime no expresa proveedor ni tipo.

## Brechas

- `SAP_MISCONFIGURED`: **1,388** artículos BUY MRP.
- `NO_GAP_CONFIRMED`: **4,383** artículos BUY MRP.
- `SAP_NOT_POPULATED`: **1,183** artículos BUY MRP.
- `UNKNOWN`: **3,083** artículos BUY MRP.

## Calidad de datos

- Estados PO: `{'FULL': 85673, 'NO_RECEIPT': 3291, 'PARTIAL': 167, 'OPEN': 63}`; primera recepción negativa: **392**; completa negativa: **392**.
- PO canceladas: `730`; recepciones canceladas: `618`; devoluciones activas: `3881`; líneas de recepción activas sin lineage PO soportado: **14**; cantidades inválidas: **662**; duplicados base link: **0**.
- Outlier máximo completo conservado: **1613 días**; no se eliminaron extremos.

## Hallazgos

1. El dato Gate 1 de artículos MRP BUY sin parámetro se puede separar ahora entre ausencia de configuración e historia real; el grupo BUY con compras y sin parámetro es el candidato prioritario.
2. La comparación usa recepción completa, no factura, y mantiene primera recepción/partials/open como estados separados.
3. LF, LP, IMP y SAA se distribuyen de forma distinta; no se mezclan en una única recomendación.
4. Un SAP por debajo de la mediana es potencialmente optimista; la severidad se mantiene acotada cuando no hay evidencia de stockout/parada.
5. IMP se reporta como cohorte propia porque su p90 puede ser de semanas.
6. Multiproveedor y multi-tipo son limitaciones de modelado del único OITM.LeadTime; se preserva detalle.
7. `NO_GAP_CONFIRMED` se incluye explícitamente y no equivale a que el parámetro sea óptimo para todos los escenarios.

## Limitaciones

- La semántica exacta de OITM.LeadTime como días de disponibilidad física no queda demostrada al 100%; por eso se usa `SAP_CONFIGURED_LEAD_TIME`.
- OPOR.DocDate puede ser administrativo/backdated en compras locales; la evidencia no convierte automáticamente el lead time documental LF en tiempo físico.
- No se mezclan MAKE con compras; el lead time MAKE queda fuera de este gate.
- No se afirma causalidad de stockout ni un valor recomendado único; solo se preservan mediana/p90/p95.

## Recursos

SAP_WRITE_COUNT=0; una conexión HANA; extracción ordenada y procesada en lotes de 5.000 filas; DuckDB solo para lectura de Gate 1 Parquet; sin pandas, multiprocessing ni MRP ejecutado.

## Archivos

- Reporte: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_mrp_lead_time_gap_v1_report.md`
- Evidencia externa: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/business/mrp_lead_time_gap_v1`
- Matriz: `mrp_lead_time_gap_item_matrix.csv` y `mrp_lead_time_gap_item_supplier_type.csv`.

## Validaciones

- Preflight HANA DUMMY y usuario/schema registrados; `SAP_WRITE_COUNT=0`.
- Tests puros y `py_compile` ejecutados por el agente.
- No se modificó SAP ni `investigation/STATUS_ACTUAL.md`.

## Siguiente paso

`TELCHI_MRP_FORECAST_DEMAND_GAP_V1` (solo después de cerrar este Gate).

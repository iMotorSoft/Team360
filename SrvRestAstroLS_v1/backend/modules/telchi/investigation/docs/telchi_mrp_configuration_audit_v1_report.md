# TELCHI — MRP CONFIGURATION AUDIT V1

## A. Gate
**TELCHI_MRP_CONFIGURATION_AUDIT_V1_PASS**
- MRP CONFIGURATION MATURITY: **LOW** (clasificador reproducible sobre cobertura y consistencia aparente)

## B. SAP safety
`SAP_WRITE_COUNT=0` · SELECT-only · no MRP executed

## C. Universo analizado
- items: **16,853**
- active_items: **12,041**
- mrp_items: **13,338**
- make_items: **1,366**
- warehouses: **82**
- item_warehouse: **1,366,364**
- BOM: **1,044**
- forecasts: **13**

## D. Cobertura MRP

| Parámetro | Configurados | Universo | % |
|---|---:|---:|---:|
| Planning Method | 16,853 | 16,853 | 100.0% |
| Procurement Method | 16,853 | 16,853 | 100.0% |
| LeadTime | 11,709 | 16,853 | 69.5% |
| SafetyStock | 0 | 16,853 | 0.0% |
| ReorderPointProxy | 16,853 | 16,853 | 100.0% |
| MinimumInventory | 16,853 | 16,853 | 100.0% |
| MaximumInventory | 16,853 | 16,853 | 100.0% |
| OrderMultiple | 16,852 | 16,853 | 100.0% |
| MinimumOrderQty | 16,853 | 16,853 | 100.0% |
| PreferredVendor | 13,602 | 16,853 | 80.7% |
| BOM | 1,044 | 16,853 | 6.2% |
| Forecast | 4,910 | 16,853 | 29.1% |

## E. Principales anomalías
1. **WAREHOUSE_STOCK_WITHOUT_MINIMUM** — 24,539 casos; ejemplo `A00001`/VI-SAL → warehouse stock exists without positive local minimum
2. **MAXIMUMINVENTORY_ZERO** — 9,411 casos; ejemplo `A00001` → policy parameter is explicitly zero
3. **MINIMUMINVENTORY_ZERO** — 9,401 casos; ejemplo `A00001` → policy parameter is explicitly zero
4. **ORDERMULTIPLE_ZERO** — 7,661 casos; ejemplo `A00001` → policy parameter is explicitly zero
5. **MINIMUMORDERQTY_ZERO** — 2,657 casos; ejemplo `A00001` → policy parameter is explicitly zero
6. **LEAD_TIME_MISSING** — 2,346 casos; ejemplo `A00001` → time-phased supply may be immediate or unresolved
7. **PURCHASE_WITHOUT_VENDOR** — 1,795 casos; ejemplo `A00001` → source selection unavailable
8. **PRODUCTION_WITHOUT_BOM** — 250 casos; ejemplo `E00009` → MRP cannot explode components
9. **BOM_PROCUREMENT_INCONSISTENT** — 91 casos; ejemplo `B00011` → MRP may buy finished item instead of exploding BOM

## F. Forecast
- definitions: **13**
- rows: **250,224**
- SKUs: **4,910**
- warehouses: **78**
- coverage active items: **39.3%**
- ActiveStatus: `NOT_EXPOSED` en OFCT/FCT1; no se infiere activo/inactivo por fecha.

## G. BOM / Procurement
- productos con BOM: **1,044**
- BOM + MAKE: **939**
- BOM + no MAKE: **105**
- MAKE sin BOM: **427**
- inconsistencias explícitas BOM/procurement: **91**

## H. Lead time SAP
- configurados: **11,709**
- cero: **0**
- ausentes: **5,144**
- distribución: `{"MISSING": 5144, "POSITIVE": 11709}`

## I. Stock policy SAP
- MinimumInventoryWarehouse: 1,366,364 / 1,366,364 (100.0%)
- MaximumInventoryWarehouse: 1,366,364 / 1,366,364 (100.0%)
- MinimumOrderQtyWarehouse: 1,366,364 / 1,366,364 (100.0%)
- OrderMultiple: 16,852 / 16,853 (100.0%)
- OrderInterval: 11,736 / 16,853 (69.6%)
- PlanningIncludedWarehouse: 1,366,364 / 1,366,364 (100.0%)

## J. Casos representativos

| ItemCode | ItemName | Warehouse | Planning | Procurement | LeadTime | Min | Max | MOQ | Multiple | Vendor | BOM | Forecast | Base |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|
| E00019 | COLAGENO HIDROLIZADO SABOR SANDIA LIMON x 400g  LIV4 | DV-SAL | MRP | MAKE | None | 0.0 | 0.0 | 1500.0 | 0.0 | None | True | False | BOM_MAKE |
| E00020 | COLAGENO HIDROLIZADO FRUTOS ROJOS  x 400g  LIV4 | LAB-P1 | MRP | MAKE | None | 0.0 | 0.0 | 1500.0 | 0.0 | None | True | False | BOM_MAKE |
| E00024 | COLAGENO HIDROLIZADO SABOR NEUTRO x 400G LIV4 | LAB-P1 | MRP | MAKE | None | 0.0 | 0.0 | 1500.0 | 0.0 | None | True | False | BOM_MAKE |
| L00001 | ALCOHOL 70% x L. GRANEL | LAB-D12 | MRP | MAKE | 1 | 0.0 | 0.0 | 1000.0 | 10.0 | None | True | True | BOM_MAKE |
| A00001 | MAQUINA DE RASPADILLO | LAB-D12 | NO_MRP | BUY | None | 0.0 | 0.0 | 0.0 | 0.0 | None | False | False | BUY |
| A00002 | CLIMATIZADOR PORTATIL MARCA GALAXI CAP. 5L. | LAB-D12 | NO_MRP | BUY | None | 0.0 | 0.0 | 0.0 | 0.0 | None | False | False | BUY |
| A00003 | PARLANTE SONY MHC-V21D | LAB-D12 | NO_MRP | BUY | None | 0.0 | 0.0 | 0.0 | 0.0 | None | False | False | BUY |
| A00004 | TOLDO | LAB-D12 | NO_MRP | BUY | None | 0.0 | 0.0 | 0.0 | 0.0 | None | False | False | BUY |
| E00004 | SUCRALOSA | LAB-P2 | MRP | BUY | 5 | 0.0 | 0.0 | 0.0 | 0.0 | PL000319 | False | False | NONZERO_LEAD_TIME |
| E00005 | ACESULFAME | LAB-P2 | MRP | BUY | 5 | 0.0 | 0.0 | 0.0 | 0.0 | PL000319 | False | False | NONZERO_LEAD_TIME |
| E00006 | VITAMINA E ACETATO PO 50% | LAB-P2 | MRP | BUY | 5 | 0.0 | 0.0 | 0.0 | 0.0 | PL000319 | False | False | NONZERO_LEAD_TIME |
| E00007 | SABORIZANTE SANDIA LIMON x kg. | DV-SAL | MRP | BUY | 90 | 0.0 | 0.0 | 0.0 | 0.0 | None | False | False | NONZERO_LEAD_TIME |
| ArtNoCatalogado | Preparado de Receta | DV-SAL | NO_MRP | BUY | None | 0.0 | 0.0 | 0.0 | 0.0 | None | False | True | FORECAST |
| Delivery | Preparado Delivery | LAB-VMP | NO_MRP | BUY | None | 0.0 | 0.0 | 0.0 | 0.0 | None | False | True | FORECAST |
| L00002 | ALCOHOL 96° x granel | DMS-PROF | MRP | BUY | 5 | 0.0 | 0.0 | 35000.0 | 1.0 | PL000089 | False | True | FORECAST |

## K. Preparación siguiente gate
**READY** para cruzar configuración SAP con lead time real; la matriz contiene `REAL_*` nulos por diseño.

## L. Próximo gate recomendado
`TELCHI_MRP_LEAD_TIME_GAP_V1`

## Limitaciones
- `SafetyStock` no se observó como campo estándar físico en OITM/OITW; se preserva `ReorderPnt` como proxy etiquetado, no como safety stock confirmado.
- La cobertura warehouse se calcula sobre las filas físicas OITW; no se infiere una fila para cada combinación matemática artículo×almacén.
- Los casos y tiers son selección reproducible de configuración y actividad agregada de 12 meses; no declaran calidad operativa ni repiten el diagnóstico real.
- Forecast se reporta solo cuando OFCT/FCT1 tienen filas y joins identificables.

## Artefactos
- Parquet root: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/business/mrp_configuration_audit_v1`
- Manifest: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/business/mrp_configuration_audit_v1/manifest.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/mrp_configuration/mrp_configuration_audit_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

# TELCHI — GATE 3: FORECAST SAP VS DEMANDA REAL

## Gate

`TELCHI_MRP_FORECAST_DEMAND_GAP_V1` — **DEGRADED**

El forecast SAP fue auditado en modo de investigación. SAP/HANA permaneció READ ONLY; no se ejecutó MRP ni se modificaron OFCT, FCT1, OITM u OITW.

Snapshot de investigación: **2026-09-14**.

## Universo

- Artículos: **16,853**; activos: **12,041**; incluidos en MRP: **13,338**; activos incluidos: **11,124**.
- Productos L activos MRP: **3,385**; MAKE: **1,087**; BUY: **10,037**.
- Item × Warehouse físicos: **1,366,364**; warehouses: **82**.

## Forecast SAP

- Definiciones OFCT: **13**; líneas FCT1: **250,224**.
- Ítems con cualquier forecast histórico/actual: **4,910**; activos MRP: **4,714**.
- Actuales o mixtos por línea temporal: **507** ítems; futuros puros: **0**; vencidos seleccionados: **4,617**; cero: **588**.
- Uso efectivo por escenario MRP: **MRP_USAGE_UNKNOWN**; OFCT/FCT1 no exponen el selector de escenario usado.

### Definiciones y cobertura temporal

| ForecastId | Código | Inicio | Fin | Bucket | Ítems | Warehouses | MinDate | MaxDate | Estado | Días futuros |
|---:|---|---|---|---|---:|---:|---|---|---|---:|
| 18 | Test His 3M Ant | 2026-03-09 | 2026-06-21 | W | 753 | 26 | 2026-03-09 | 2026-06-15 | EXPIRED | 0 |
| 5 | PREVLITQ4 | 2022-08-01 | 2022-12-31 | M | 39 | 4 | 2022-08-01 | 2022-12-01 | EXPIRED | 0 |
| 6 | PRY23 | 2023-01-01 | 2023-12-31 | M | 357 | 5 | 2023-01-01 | 2023-12-01 | EXPIRED | 0 |
| 7 | PROY_TL_2023 | 2023-03-01 | 2023-12-31 | M | 357 | 5 | 2023-03-01 | 2023-12-01 | EXPIRED | 0 |
| 8 | 7ijuy6trewq | 2023-10-01 | 2023-12-31 | M | 572 | 24 | 2023-10-01 | 2023-12-01 | EXPIRED | 0 |
| 9 | test Periodo22 S | 2023-11-13 | 2024-02-04 | W | 4433 | 28 | 2023-11-13 | 2024-01-29 | EXPIRED | 0 |
| 10 | MRP 2024 | 2024-10-28 | 2024-12-29 | W | 826 | 25 | 2024-10-28 | 2024-12-23 | EXPIRED | 0 |
| 11 | MP 2024 | 2024-11-01 | 2025-01-31 | M | 868 | 77 | 2024-11-01 | 2024-11-01 | EXPIRED | 0 |
| 19 | Previsicion lit | 2026-07-27 | 2026-11-01 | W | 507 | 22 | 2026-07-27 | 2026-10-26 | MIXED | 42 |
| 12 | MP 2024 - 1 | 2024-11-01 | 2025-01-31 | M | 46 | 20 | 2024-11-01 | 2025-01-01 | EXPIRED | 0 |
| 15 | MP 2024-2 | 2024-11-01 | 2025-12-31 | M | 284 | 1 | 2024-11-01 | 2025-12-01 | EXPIRED | 0 |
| 17 | MP 2024 - 3 | 2024-11-01 | 2025-12-31 | M | 222 | 1 | 2024-11-01 | 2025-12-01 | EXPIRED | 0 |
| 16 | MED25 | 2025-01-01 | 2025-12-31 | M | 50 | 1 | 2025-01-01 | 2025-12-01 | EXPIRED | 0 |

El ForecastId **19 / Previsicion lit** es el único snapshot temporal no vencido; sus líneas son semanales, cubren 2026-07-27..2026-10-26 y dejan aproximadamente 42 días de cobertura de líneas desde el snapshot. La cabecera finaliza 2026-11-01.

## Cobertura

| Segmento | Universo | Cualquier forecast | Actual/futuro | Sin forecast |
|---|---:|---:|---:|---:|
| Activos MRP | 11,124 | 4,714 / 11,124 (42.4%) | 504 / 11,124 (4.5%) | 6,410 / 11,124 (57.6%) |
| L% | 3,385 | 1,239 / 3,385 (36.6%) | 504 / 3,385 (14.9%) | 2,146 / 3,385 (63.4%) |
| MAKE | 1,087 | 632 / 1,087 (58.1%) | 487 / 1,087 (44.8%) | 455 / 1,087 (41.9%) |
| BUY | 10,037 | 4,082 / 10,037 (40.7%) | 17 / 10,037 (0.2%) | 5,955 / 10,037 (59.3%) |

L_TOTAL=3,385; L_WITH_FORECAST=1,239; L_WITHOUT_FORECAST=2,146; L_CURRENT_OR_FUTURE=504. L_SEASONAL_WITHOUT_FORECAST=UNKNOWN; L_GROWING_WITHOUT_FORECAST=UNKNOWN.
La cobertura por clase de demanda no puede calcularse de forma trazable: el reporte histórico conserva los totales SEASONAL/GROWING/STABLE/INTERMITTENT, pero no existe en DATA_ROOT el mapping ItemCode→DemandClass ni sus métricas mensuales.

| DemandClass | UniverseN | ForecastedN | CoveragePct | Estado |
|---|---:|---:|---:|---|
| SEASONAL | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| GROWING | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| STABLE | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| INTERMITTENT | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

## Demanda real

Se reutilizó la clasificación agregada auditada de **10,775 ítems**: SEASONAL 1,950, GROWING 1,003, STABLE 922, INTERMITTENT 342. No se recalculó el histórico y no se inventó un join por artículo.

Observed12M, Observed6M, trend, seasonality, sales_frequency, months_with_sales, stockout flags y pedidos abiertos quedan **UNKNOWN** en esta ejecución por ausencia de sus artefactos reutilizables.

## Forecast vs realidad

- ComparableN: **0**; Aligned: **UNKNOWN**; Underforecast: **UNKNOWN**; Overforecast: **UNKNOWN**; Stale: **UNKNOWN**.
- No se calcula AbsoluteError, APE ni MAE porque no existe un período de demanda observado compatible por ItemCode × Warehouse.
- Por ello no se declaran casos críticos de SEASONAL/GROWING sin forecast ni casos correctamente cubiertos.

## Calidad de datos forecast

- Líneas cero: **6,672**; negativas: **0**; sin artículo: **0**; sin warehouse: **0**; fecha inválida: **0**.
- Grupos duplicados por ForecastId × ItemCode × Warehouse × Period: **0**; líneas con warehouse no encontrado en OITW snapshot: **0**.
- No se pudo auditar futuro sobre DISCONTINUED porque falta el mapping de clase por artículo.

## Casos críticos

No se publican falsos positivos: la selección de casos SEASONAL/GROWING/HIGH_VOLUME/STOCKOUT y la clasificación de desalineación requieren demanda por artículo. Se dejó una muestra de 20 casos de calidad/forecast en `forecast_data_quality_cases.csv`, todos marcados con `GapType=UNKNOWN`.

## Casos correctos

No demostrables en este snapshot: existencia de forecast no equivale a calidad ni a uso efectivo.

## Cruce con Lead Time

- El runner cruza Gate 2 a nivel item: `LeadTimeGapClassification` y banderas `LeadTimeGapFlag`/`LeadTimeMissingFlag` quedan en la matriz.
- NO_FORECAST + LT_GAP: **800** artículos activos MRP; NO_FORECAST + LT_MISSING: **1,087**.
- MAKE + BOM + NO_FORECAST: **245** artículos activos MRP; no se etiqueta causalidad y la demanda sigue UNKNOWN.

## Brechas

- `SAP_NOT_POPULATED`: candidato para artículos sin forecast, pero requiere confirmación de política de negocio; no se concluye error automáticamente.
- `SAP_STALE_PARAMETER`: no demostrable sin comparar contra demanda reciente.
- `SAP_MISCONFIGURED`: no demostrable como warehouse incorrecto; el forecast observado sí tiene granularidad ItemCode × Warehouse.
- `SAP_MODEL_LIMITATION`: no demostrable sin demanda comparable, especialmente para INTERMITTENT.
- `OPERATIONAL_DATA_NOT_CONNECTED`: posible hipótesis, no confirmada.
- `NO_GAP_CONFIRMED`: no asignado porque no hay comparación forecast-real.
- `UNKNOWN`: clasificación aplicada a la brecha de calidad y a la cobertura por clase.

## Hallazgos

1. SAP conserva **13 definiciones** y **250.224 líneas**, pero solo el ForecastId 19 tiene horizonte no vencido al 2026-09-14.
2. El snapshot actual alcanza **504 ítems activos incluidos en MRP**; los demás ítems con forecast son históricos o están fuera del universo activo-MRP.
3. La granularidad física observada es **ItemCode × Warehouse**; no se observó forecast global sin warehouse.
4. Existen **6.672 líneas con cantidad cero**; cantidad cero se conserva como bandera y no como cobertura útil.
5. El uso efectivo por escenario MRP es **MRP_USAGE_UNKNOWN**.
6. La calidad forecast vs demanda es **UNKNOWN**, no PASS: falta el mapping per-item de la clasificación histórica y las métricas recientes reutilizables.
7. La falta de forecast no se convierte automáticamente en error; queda como candidato a `NEEDS_BUSINESS_CONFIRMATION`.

## Limitaciones

- `product_seasonality_v1_report.md` está disponible como resumen agregado, pero no su Parquet/CSV de clasificación por ItemCode.
- No se reconsultaron ni cargaron millones de ventas; no se ejecutó un nuevo modelo predictivo.
- OFCT/FCT1 no expone en el snapshot un estado activo ni la selección efectiva del escenario MRP.
- Stockouts, pedidos abiertos y compatibilidad temporal de ventas no están disponibles como artefactos reutilizables en DATA_ROOT.

## Recursos

- `SAP_WRITE_COUNT=0`; no se ejecutó MRP ni se modificó SAP.
- Snapshot OFCT/FCT1 físicamente confirmado por consulta read-only previa y reutilizado desde Gate 1.
- DuckDB con `threads=1`, `memory_limit=1GB`; sin multiprocessing, sin pandas sobre datasets completos y sin extracción histórica de ventas.

## Archivos

- Reporte: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs/telchi_mrp_forecast_demand_gap_v1_report.md`
- Evidencia: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/business/mrp_forecast_demand_gap_v1`
- Matriz completa: `forecast_demand_item_warehouse_matrix.parquet`
- Definiciones: `forecast_definitions.parquet`
- Selección por item×warehouse: `selected_forecast_item_warehouse.parquet`
- Manifest y resumen: `manifest.json`, `summary.json`

## Validaciones

- Preflight HANA read-only de OFCT/FCT1: columnas físicas, COUNT, MIN/MAX, DISTINCT forecast/item/warehouse y cantidad cero confirmados.
- Tests focalizados: PASS (4 tests); `py_compile`: PASS.
- `git diff --check`: PASS.
- No se modificó `investigation/STATUS_ACTUAL.md` ni archivos concurrentes.

## Siguiente paso

Para cerrar este Gate como PASS se requiere reponer el artefacto histórico ItemCode×DemandClass×Month (o autorizar una consulta agregada acotada de demanda reciente). Después: `TELCHI_MRP_STOCK_POLICY_GAP_V1`.

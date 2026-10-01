# TELCHI — Gate 5C Level B · 100 productos L V1

**Continuación:** `TELCHI_AVAILABILITY_BACKTEST_V1_PASS`\
**Autorización:** `EXECUTE_LEVEL_B`\
**Veredicto:** `TELCHI_REPLENISHMENT_LEVEL_B_100_L_PRODUCTS_V1_PASS`

La investigación se ejecutó en `STAGE=INVESTIGATION`, Branch `2A`, con
`ItemCode LIKE 'L%'`, 365 días, `SAP_WRITE_COUNT=0`, `MAX_WORKERS=1` y
`RESOURCE_GUARD=ENABLED`. No se incluyeron productos no-L en los resultados
principales.

## 1. Ejecución y muestra

Se ejecutaron los tres escalones solicitados, sin saltar directamente a 100:

| Smoke | Productos | Simulaciones | RSS máximo | MemAvailable mínimo | Runtime | Resultado |
|---|---:|---:|---:|---:|---:|---|
| B1 | 25 | 2.850 | 233,34 MiB | 5.796,21 MiB | 25,28 s | PASS |
| B2 | 50 | 5.700 | 244,97 MiB | 5.803,31 MiB | 42,92 s | PASS |
| B3 | 100 | 11.400 | 267,30 MiB | 5.809,64 MiB | 79,89 s | PASS |

La muestra B3 es una muestra **estratificada, determinística y anidada**. Se
seleccionó desde 816 productos L activos válidos de 2A; se excluyeron 60
inactivos. No se tomó el primer `LIMIT 100`. La selección fuerza la presencia
del caso control `L02467` y recorre en round-robin estratos de rotación
alta/media/baja, demanda intermitente, stockout frecuente, disponibilidad alta,
inventario alto, muchas/pocas reposiciones y demanda estable/variable. Los
cortes son cuantiles empíricos del universo descubierto y `ItemCode` solo es
desempate. La trazabilidad completa está en `sample_selection.json`.

La historia de los 100 productos es completa: 365 días por producto, del
2025-09-12 al 2026-09-11. `TRANSIT_EXCLUDED`; la demanda censurada no se imputó.

## 2. Respuesta ejecutiva

### A. ¿Cuántos productos L tienen problema?

| Clase | Productos | Porcentaje |
|---|---:|---:|
| `SERVICE_PROBLEM` | 53 | 53% |
| `EXCESS_INVENTORY_PROBLEM` | 14 | 14% |
| `BOTH` | 2 | 2% |
| `NEITHER` | 31 | 31% |
| `INSUFFICIENT_HISTORY` | 0 | 0% |
| `INCONCLUSIVE` | 0 | 0% |

La clasificación primaria es por producto×branch. `SERVICE_PROBLEM` significa
stockout observado mayor que cero; `EXCESS_INVENTORY_PROBLEM` exige una política
que preserve disponibilidad y días de stockout y reduzca inventario promedio.
Los criterios y umbrales no son una recomendación productiva: el stockout es
falta de stock observada, no venta perdida confirmada.

### B. ¿Cuánto del problema es stockout?

55 de 100 productos tuvieron al menos un día de stockout: 53 `SERVICE_PROBLEM`
y 2 `BOTH`. La muestra acumuló **11.492 días-producto** de stockout, o
**114,92 días por producto** en promedio. Este promedio no suma unidades ni
mezcla UoM.

Los casos más severos incluyen ocho productos con los 365 días sin stock en la
proyección observada. Los rankings completos están en `rankings.json`, con
`TOP_SERVICE_PROBLEM`, `TOP_AVAILABILITY_IMPROVEMENT` y
`TOP_STOCKOUT_REDUCTION`.

### C. ¿Cuánto es sobrestock?

16 productos (14 `EXCESS_INVENTORY_PROBLEM` + 2 `BOTH`) tienen al menos una
alternativa que mantiene availability/stockout y reduce inventario bajo el
grid probado. En esos 16 casos, la reducción media fue **67,38 unidades de la
UoM propia por producto** (−3,50 reposiciones); no se suman cantidades físicas
heterogéneas. En los 100 productos,
CURRENT tiene availability media **68,52%**, stockout medio **114,92 días**,
inventario medio **190,91 unidades de la UoM propia por producto** y **19,20
reposiciones**.

### D. ¿Existen políticas mejores?

Sí, bajo la definición de candidato no dominado del backtest, **59/100** tienen
una alternativa con mejora de servicio (availability mayor y stockout menor) o
servicio comparable con menor inventario. No es una recomendación de producción.
En 41 productos no se encontró una mejora clara: 10 quedaron como
`NO_CLEAR_IMPROVEMENT` (`NO_POLICY_IMPROVES` en el grid probado) y los 31
`NEITHER` como `KEEP_CURRENT_CANDIDATE`.

Distribución de la política del mejor candidato por producto:

| Familia/configuración | Productos |
|---|---:|
| `DAYS_OF_SUPPLY` | 49 |
| `DYNAMIC_TARGET` | 5 |
| `MIN_MAX` | 5 |
| `REORDER_POINT` | 0 |
| `PERIODIC_REVIEW` | 0 |
| `HYBRID` | 0 |

El grid conserva exactamente las **19 configuraciones** de Gate 5B y los seis
escenarios `ASSUMED_REPLENISHMENT_LEAD_TIME=0/1/2/3/5/7`.

### E. ¿Son robustas?

Para los 59 productos con candidato:

| Clasificación | Productos |
|---|---:|
| `ROBUST_HIGH` (5–6/6) | 24 |
| `ROBUST_MEDIUM` (3–4/6) | 3 |
| `ROBUST_LOW` (1–2/6) | 32 |
| `NOT_ROBUST` (0/6) | 0 |

`L02467` reproduce `ROBUST_LT_COUNT=1`, por lo que permanece como `ROBUST_LOW`.
La mejora de ese caso no debe generalizarse como robusta. Además, la
sensibilidad por producto, clasificada por terciles empíricos del rango de
availability más el rango de stockout normalizado, fue:

| Sensibilidad | Productos |
|---|---:|
| `LT_INSENSITIVE` | 35 |
| `LT_MODERATE` | 33 |
| `LT_HIGHLY_SENSITIVE` | 32 |

El resultado muestra una mezcla: existen mejoras repetibles, pero 32/100 son
altamente sensibles y 32/59 candidatos solo tienen robustez baja. La trazabilidad
por política y lead time está en `lead_time_robustness.jsonl`.

### F. ¿Qué limita la decisión?

La barrera principal sigue siendo la ausencia de lead time físico trazable. El
runner mide escenarios supuestos; no los presenta como tiempos físicos reales.
La demanda censurada permanece solo como sensibilidad (`OBSERVED_DEMAND_ONLY`) y
`fill_rate` es `SECONDARY_CONTROL_ONLY`. Por tanto, no se puede afirmar venta
perdida ni decidir una política única para todo L. La siguiente investigación
recomendada es:

`GATE_PHYSICAL_LEAD_TIME_LOGISTICS_PROCESS_INVESTIGATION`

No se autoriza todavía una recomendación ni escritura en SAP.

## 3. Impacto comparativo

El agregado se reporta como medias por producto y no como suma física:

| Métrica | CURRENT (100) | Mejor candidato no dominado (59) |
|---|---:|---:|
| Availability media | 68,52% | 90,80% |
| Stockout medio | 114,92 días | 33,59 días |
| Inventario medio por producto | 190,91 | 336,26 |
| Reposiciones medias | 19,20 | 4,90 |
| Inventory-days medio por producto | 69.683,46 | 122.735,34 |

La mejora de servicio viene con mayor inventario medio en el subconjunto de
candidatos. No se debe concluir que 90,80% de availability sea económicamente
óptimo: availability, inventario y reposiciones deben evaluarse conjuntamente.
La comparación completa está en `aggregate.json`.

## 4. Casos y control L02467

Se generaron **20 casos trazables** en `case_traces.jsonl`, cubriendo service,
excess, both, neither, sensibilidad a lead time y keep-current cuando están
disponibles. Cada caso tiene `ItemCode`, `Branch`, clase, decisión, política y
traza diaria o baseline observado.

El caso de control reproduce aproximadamente la configuración original:

| Métrica | CURRENT | `DAYS_OF_SUPPLY(7/3), LT=0` |
|---|---:|---:|
| Availability | 7,12% | 67,95% |
| Stockout days | 339 | 117 |
| Δ inventario promedio | — | +8.730,6 |
| `ROBUST_LT_COUNT` | — | 1 |

Esto confirma que Level B no alteró la semántica de Gate 5B. La mejora requiere
inventario adicional y depende del supuesto de lead time; no es una política
ganadora general.

## 5. Validaciones y artefactos

| Control | Resultado |
|---|---|
| `NO_LOOKAHEAD` | PASS |
| `INVENTORY_CONSERVATION` | PASS |
| `DETERMINISM` | PASS |
| `RESOURCE_SAFETY` | PASS |
| `SAP_WRITE_COUNT` | 0 |
| `MAX_WORKERS` | 1 |
| `PRIMARY_UNIVERSE` | `ItemCode LIKE 'L%'` |
| `TRANSIT` | `TRANSIT_EXCLUDED` |
| Pareto | Availability ↑ / AverageInventory ↓ / ReplenishmentCount ↓ |
| Fill rate | Secondary control only |

Código: `validation/branch_replenishment/run_level_b_v1.py`. Tests focalizados:
`test_level_b_v1.py` más regresión Gate 5B. Evidencia externa B1/B2/B3:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/branch_replenishment_level_b/`

Artefactos B3: `sample_selection.json`, `current_policy.jsonl`,
`policy_metrics.jsonl`, `pareto_candidates.jsonl`, `product_summary.jsonl`,
`lead_time_robustness.jsonl`, `aggregate.json`, `rankings.json`,
`case_traces.jsonl`, `resource_metrics.jsonl` y `gate_result.json`.

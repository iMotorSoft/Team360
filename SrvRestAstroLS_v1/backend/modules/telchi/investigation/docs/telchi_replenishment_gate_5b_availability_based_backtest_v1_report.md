# TELCHI — Gate 5B Availability-Based Backtest V1

**Continuación:** `FILL_RATE_CEILING_EFFECT_DETECTED`\
**Universo:** `ItemCode LIKE 'L%'`, Branch `2A`, 10 productos, 365 días\
**Estado:** `INVESTIGATION` · READ ONLY · `SAP_WRITE_COUNT=0` · `MAX_WORKERS=1` · `RESOURCE_GUARD=ENABLED`

## A. Veredicto

`TELCHI_AVAILABILITY_BACKTEST_V1_PASS`

El backtest ejecutó exactamente las 19 configuraciones y los lead times
`0/1/2/3/5/7`: **1.140 simulaciones** (`10 × 19 × 6`). El fill rate observado
se conserva únicamente como `SECONDARY_CONTROL`; Pareto usa:

1. disponibilidad ↑;
2. inventario promedio ↓;
3. reposiciones ↓.

Se demostró un trade-off operacional reproducible: para `L02467`,
`DAYS_OF_SUPPLY(target_dos=7, trigger_dos=3, LT=0)` mejora disponibilidad de
7,12% a 67,95% y reduce stockout de 339 a 117 días, con costo de inventario
(+8.730,6 unidades). No es una decisión de despliegue ni una afirmación de
venta perdida.

**Level B:** `EXECUTE_LEVEL_B`. La autorización es metodológica para continuar
la evaluación; no selecciona todavía una política definitiva. La ventaja
observada no es robusta en cuatro o más lead times: el caso L02467 tiene
`ROBUST_LT_COUNT=1`.

## B. CURRENT — 10 productos L

`AVAILABLE` en V1 significa `AvailableStock > 0` y no se introdujo `LOW_STOCK`.

| ItemCode | Availability | Stockout days | Episodes | Duration mean / median / p90 / max | Avg inventory | Replenishments | Observed fill (secondary) |
|---|---:|---:|---:|---:|---:|---:|---:|
| L00003 | 99,73% | 1 | 1 | 1,0 / 1,0 / 1,0 / 1 | 489,5 | 43 | 100,00% |
| L00503 | 100,00% | 0 | 0 | 0,0 / 0,0 / 0,0 / 0 | 256,3 | 105 | 100,00% |
| L00504 | 100,00% | 0 | 0 | 0,0 / 0,0 / 0,0 / 0 | 1.260,0 | 87 | 100,00% |
| L00505 | 99,73% | 1 | 1 | 1,0 / 1,0 / 1,0 / 1 | 1.177,2 | 46 | 100,00% |
| L01013 | 100,00% | 0 | 0 | 0,0 / 0,0 / 0,0 / 0 | 247,5 | 58 | 100,00% |
| L01059 | 100,00% | 0 | 0 | 0,0 / 0,0 / 0,0 / 0 | 552,2 | 92 | 100,00% |
| L01675 | 100,00% | 0 | 0 | 0,0 / 0,0 / 0,0 / 0 | 317,2 | 73 | 100,00% |
| L01785 | 100,00% | 0 | 0 | 0,0 / 0,0 / 0,0 / 0 | 315,8 | 38 | 100,00% |
| L02467 | 7,12% | 339 | 2 | 169,5 / 169,5 / 209,9 / 220 | 7.123,3 | 1 | 100,00% |
| L03192 | 99,45% | 2 | 1 | 2,0 / 2,0 / 2,0 / 2 | 426,8 | 59 | 100,00% |

Promedios CURRENT: **availability 90,60%**, **34,3 stockout days**,
**1.216,6 inventario promedio** y **60,2 reposiciones**. El 100% de fill
observado no contradice estos faltantes: SAP solo registra demanda observada.

## C. Mejoras y candidatos Pareto

La lista completa de candidatos no dominados por producto está en
`pareto_candidates.jsonl`. La siguiente tabla muestra un candidato
representativo; cuando no existe un win primario, se marca como trade-off o
`INCONCLUSIVE` y no se recomienda elegirlo.

| ItemCode | Política / LT | Availability simulada | Stockout | Δ inventario | Δ reposiciones | Clasificación |
|---|---|---:|---:|---:|---:|---|
| L00003 | DAYS_OF_SUPPLY 14 / 0 | 93,15% | 25 | +1.405,7 | −2 | INCONCLUSIVE |
| L00503 | DAYS_OF_SUPPLY 7 / 0 | 93,15% | 25 | −26,3 | −28 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L00504 | REORDER_POINT 0,99 / 0 | 93,42% | 24 | −72,1 | −49 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L00505 | DAYS_OF_SUPPLY 21 / 0 | 93,42% | 24 | −9,8 | −25 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L01013 | DAYS_OF_SUPPLY 14 / 0 | 96,71% | 12 | −28,1 | −17 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L01059 | DAYS_OF_SUPPLY 7 / 0 | 93,70% | 23 | −225,7 | −31 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L01675 | DAYS_OF_SUPPLY 14 / 0 | 96,71% | 12 | −56,5 | −34 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L01785 | DAYS_OF_SUPPLY 14 / 0 | 98,08% | 7 | −45,5 | −18 | INVENTORY_WIN_WITH_AVAILABILITY_COST |
| L02467 | DAYS_OF_SUPPLY 7 / 0 | 67,95% | 117 | +8.730,6 | 0 | AVAILABILITY_WIN_WITH_INVENTORY_COST |
| L03192 | DAYS_OF_SUPPLY 14 / 0 | 91,23% | 32 | −48,7 | −30 | INVENTORY_WIN_WITH_AVAILABILITY_COST |

Las diferencias de fill rate no deciden estos resultados. Por ejemplo, la
política de `L02467` mantiene fill observado secundario inferior al CURRENT
porque se evalúa contra la misma demanda observada, mientras la dimensión
operacional principal mejora disponibilidad.

## D. Lead-time robustness

`ROBUST_LT_COUNT` cuenta escenarios donde una política es no dominada y presenta
mejora de servicio o menor inventario con servicio comparable. No se eligió una
política definitiva porque ninguna ventaja de producto se mantuvo en al menos
4/6 escenarios.

- `L02467`: `DAYS_OF_SUPPLY` tiene `ROBUST_LT_COUNT=1`; la mejora se concentra en
  LT=0 y desaparece bajo los demás escenarios.
- Los restantes productos tienen `ROBUST_LT_COUNT=0` para sus candidatos
  representativos; sus fronteras muestran principalmente trade-offs de menor
  inventario con peor disponibilidad.
- Los 190 resúmenes producto×configuración (cada uno con los seis lead times)
  y sus deltas están en `lead_time_robustness.jsonl`; el agregado completo está
  en `aggregate.json`.

Esto impide presentar una configuración como robusta solo porque gana bajo un
único supuesto de lead time.

## E. Problem class

| Clase | Productos | Productos |
|---|---:|---|
| `SERVICE_PROBLEM` | 4 | L00003, L00505, L02467, L03192 |
| `EXCESS_INVENTORY_PROBLEM` | 0 | No se demostró reducción de inventario manteniendo disponibilidad práctica |
| `BOTH` | 0 | No observado en este Level A |
| `NEITHER` | 6 | L00503, L00504, L01013, L01059, L01675, L01785 |

Los cuatro `SERVICE_PROBLEM` se identifican por disponibilidad inferior a 100%
o stockout positivo. Los seis restantes no se etiquetan automáticamente como
sobrestock: esa etiqueta requiere una política que mantenga disponibilidad
prácticamente equivalente y reduzca inventario. La ausencia de esa evidencia
se reporta como `NEITHER`, no como sobrestock confirmado.

## F. Censored demand y semántica

La corrida primaria usa `OBSERVED_DEMAND_ONLY`; no imputa LOW/BASE/HIGH ni
convierte un día de stockout en venta perdida. `POSSIBLE_CENSORED_DEMAND` queda
como análisis separado y se conserva por producto en `current_policy.jsonl`.
Un stockout significa únicamente **producto no disponible**; no significa venta
perdida confirmada.

## G. Gates de cierre

| Control | Resultado |
|---|---|
| `NO_LOOKAHEAD` | `PASS` |
| `INVENTORY_CONSERVATION` | `PASS` |
| `DETERMINISM` | `PASS` |
| `RESOURCE_SAFETY` | `PASS` |
| `SAP_WRITE_COUNT` | `0` |
| `MAX_WORKERS` | `1` |
| `NON_L` en métricas principales | `0` |
| Level B 100 productos | No ejecutado |

## H. Artefactos y reproducibilidad

Código:

- `validation/branch_replenishment/backtest_engine_v1.py`
- `validation/branch_replenishment/run_availability_backtest_gate_5b_v1.py`
- `validation/branch_replenishment/test_availability_backtest_gate_5b_v1.py`

Evidencia externa:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation/branch_replenishment_availability_backtest/v1_level_A/`

Incluye `current_policy.jsonl`, `policy_metrics.jsonl`,
`pareto_candidates.jsonl`, `product_summary.jsonl`,
`lead_time_robustness.jsonl`, `aggregate.json`, `resource_metrics.jsonl` y
`gate_result.json`.

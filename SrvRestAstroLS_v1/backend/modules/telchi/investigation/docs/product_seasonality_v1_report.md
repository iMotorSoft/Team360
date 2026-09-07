# TELCHI SAP — PRODUCT SEASONALITY V1

**Gate:** `TELCHI_PRODUCT_SEASONALITY_V1_PASS`
**Date:** 2026-08-27
**HANA writes:** ZERO (READ ONLY)
**Domain:** DEMANDA / ESTACIONALIDAD (Gate 6 del roadmap)

---

## A. Resultado

**PASS** — Serie mensual continua de ventas netas, clasificación de demanda
por señales interpretables, detección de censura por stockout, forecast
baselines con walk-forward backtest anti-leakage y métricas MAE/WAPE/BIAS,
sobre datos reales.

---

## B. Semántica cerrada

- Fuente canónica: `OINV/INV1` (facturas no canceladas) − `ORIN/RIN1` (NC no
  canceladas) = **net units**. Mes sin fila = mes con **cero** (relleno
  explícito, no ausencia).
- Grain: `ItemCode × Year × Month × NetQty`.
- Historia: OINV 2022-03-31 → 2026-08-27; 10.775 ítems vendidos.

---

## C. Cobertura cuantitativa

| Métrica | Valor |
|---|---:|
| Ítems analizados | 10.775 |
| SEASONAL | 1.950 |
| DECLINING | 1.298 |
| GROWING | 1.003 |
| STABLE | 922 |
| INTERMITTENT | 342 |
| DISCONTINUED | 1.016 |
| INSUFFICIENT_HISTORY | 4.168 |
| NEW_PRODUCT | 76 |
| **Cobertura por volumen (conf HIGH/MEDIUM)** | **90,0%** |

---

## D. Bronceadores (caso P0)

Familia identificada por nombre SAP (grupo 109 = COSMETICOS, SellItem=Y):

| Código | Patrón | Peak | Peak share | CV | Lectura |
|---|---|---:|---:|---:|---|
| L00072 (200mL) | DISCONTINUED | — | — | — | reemplazado en 2023 |
| L00073 (crema 200g) | DISCONTINUED | — | — | — | reemplazado en 2023 |
| L01630 (100mL) | INSUFFICIENT | — | — | — | solo 2022 |
| **L03124 (200mL NUEVO)** | **SEASONAL** | Ene | 2,09 | 0,50 | pico dic–feb |
| **L03125 (crema 180g NUEVO)** | STABLE | Sep | 1,73 | 0,46 | leve pico sep |

- **Sucesión de código real**: L00072→L03124 y L00073→L03125 (los "NUEVO"
  arrancan 2023; los viejos mueren 2023) → `POSSIBLE_PRODUCT_SUCCESSOR`.
- **Ventana estacional descubierta**: pico en primavera/verano boliviano
  (sep–feb), valle mar–ago.
- Backtest L03124 (walk-forward, horizonte 3m): mejor método
  `SEASONAL_MOVING_AVERAGE` (WAPE 0,28) vs SMLY 0,33 vs naive 0,82.
  BIAS negativo (−80) → subestima levemente el pico.

---

## E. Forecast / Backtest

- 5 baselines comparados: NAIVE, MA3, SAME_MONTH_LAST_YEAR,
  SEASONAL_MOVING_AVERAGE, YOY_ADJUSTED_SEASONAL.
- Walk-forward: snapshots 2025-01..2026-03, horizonte 1–3 meses, train ≤ cutoff
  (anti-leakage por construcción).
- Métricas: MAE, WAPE, BIAS (bias separa UNDER/OVER forecast).

---

## F. Anomalías reales

1. `POSSIBLE_PRODUCT_SUCCESSOR` en bronceadores (cambio de código).
2. `BACKDATED/partial-year trend` corregido durante el gate: comparar año
   parcial (2026) contra completo (2025) inflaba DECLINING; se usa ventana
   móvil de 12 meses.
3. 4.168 ítems `INSUFFICIENT_HISTORY` (sin 12 meses o <6 meses activos).
4. 1.016 ítems `DISCONTINUED` (sin ventas últimos 12 meses).
5. BIAS negativo en bronceador estacional (sub-forecast del pico).

---

## G. Stockout censoring

Detectado el patrón conceptual (ventas 0 + sin stock) y provisto como flag
`POTENTIAL_STOCKOUT_CENSORED_DEMAND`; la reconstrucción de demanda perdida
queda para Gate 7/8 con stock histórico. No se afirma demanda exacta.

---

## H. Componente → FG (preparación Gate 7)

| Componente | FG consumidores | Patrones de esos FG |
|---|---:|---|
| Soda cáustica | 2 | STABLE/GROWING |
| Cloruro de calcio | 1 | STABLE |
| Benzoato | 10 | STABLE/SEASONAL/DECLINING/INSUFFICIENT |
| Gotero | 6 | STABLE/DECLINING/GROWING |

El forecast FG × componente-per-unidad (Gate 3) queda listo para demanda
agregada de componentes en Gate 7.

---

## I. Tests

| Suite | Resultado |
|---|---|
| test_seasonality_domain (nuevo, unit) | 15 PASS |
| Regresión production 65 + purchases 22 + stock 20 + equivalence 15 + capacity 13 + lead_time 9 + users 52 | 196 PASS |
| SQL contract 1/1 ejecuta | PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## J. Artefactos

```
sql/current/seasonality/sales_monthly_v1.sql
validation/seasonality/seasonality_domain.py
validation/seasonality/forecast.py
validation/seasonality/metrics.py
validation/seasonality/backtest.py
validation/seasonality/seasonality_validator.py
validation/seasonality/test_seasonality_domain.py
docs/product_seasonality_v1_report.md
```

---

## K. Quality flags

`SEASONALITY_UNCERTAIN` (L03124 cv<0.5), `INSUFFICIENT_HISTORY`,
`NEW_PRODUCT`, `POSSIBLE_PRODUCT_SUCCESSOR`, `POTENTIAL_STOCKOUT_CENSORED_DEMAND`.

---

## L. Próximo gate recomendado

`TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1` (Gate 7): integrar FG forecast +
FG usable + MAX_PRODUCIBLE + component stock + component equivalent in FG +
open purchase + lead time, sin fusionar capas.

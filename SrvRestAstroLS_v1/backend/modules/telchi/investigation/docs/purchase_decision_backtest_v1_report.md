# TELCHI SAP — PURCHASE DECISION BACKTEST V1

**Gate:** `TELCHI_PURCHASE_DECISION_BACKTEST_V1_PASS`
**Date:** 2026-08-30
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / BACKTEST (Gate 9 del roadmap de abastecimiento)

---

## A. Resultado

**PASS** — Backtest histórico del motor de cobertura/riesgo sin hindsight: para
cada snapshot se reconstruye lo que el motor "sabía" en T (stock as-of-T desde
OINM, consumo desde IGE1 ≤ T), se proyecta el mes de agotamiento y se compara
contra el consumo REAL observado después de T.

---

## B. Semántica

- **Stock as-of-T** = `SUM(OINM.InQty) − SUM(OINM.OutQty)` con `DocDate ≤ T`
  (almacenes RAW: LAB-M1/SAA-M1/MAG-M1). OINM cubre 2022-03-31 → hoy; el saldo
  de apertura de migración queda contenido en el ledger.
- **Consumo** = `IGE1.Quantity` (BaseType=202) por mes, con `DocDate`.
- **Forecast** = `SEASONAL_MOVING_AVERAGE` (misma método validado en Gate 6)
  sobre el historial ≤ T; horizonte 6 meses.
- **Anti-leakage**: la predicción solo ve datos ≤ T; el outcome solo usa
  consumo > T.
- **Veredictos** (sin causalidad empresarial):
  - `POTENTIAL_EARLY_WARNING`: predijo stockout Y el consumo real agotó.
  - `POTENTIAL_MISSED_PURCHASE`: predijo seguro Y el consumo real agotó.
  - `POTENTIAL_OVERBUY`: predijo stockout Y el consumo real no agotó.
  - `CONSISTENT`: predijo seguro Y el consumo real no agotó.

---

## C. Evidencia cuantitativa

| Métrica | Valor |
|---|---:|
| Componentes | 10 |
| Snapshots | 4 (2025-01, 2025-06, 2025-09, 2026-01) |
| Casos totales | 40 |
| `POTENTIAL_EARLY_WARNING` | 14 |
| `CONSISTENT` | 10 |
| `POTENTIAL_MISSED_PURCHASE` | 9 |
| `POTENTIAL_OVERBUY` | 7 |
| **Precisión de early warning (±1 mes)** | **12/14 (86%)** |

---

## D. Hallazgos

1. **La lógica temporal predice bien el mes de agotamiento** (86% dentro de ±1
   mes). Ejemplos exactos: soda 2026-01 → stockout real 2026-07 (predicho
   2026-07); tapa PET 2025-01/06 → 2025-02/10 exactos; frasco 1L 2025-09/2026-01
   → 2025-12/2026-04 exactos.
2. **El empaque regular es el más predecible**: tapa PET (L00219) y frasco 1L
   (L00097) tienen consumo estable → early warnings consistentes y exactos.
3. **`POTENTIAL_MISSED_PURCHASE` en gotero/tapa/contra (2025-01, 2025-06)**: el
   forecast estacional sub-estima el consumo intermitente de envases → el motor
   dijo "seguro" con stock bajo y el consumo real agotó. Limitación real del
   forecast para demanda intermitente (no es un bug, es sesgo de método).
4. **`POTENTIAL_OVERBUY` en precinto/cloruro con stock=0**: componentes con stock
   cero pero consumo real nulo → el motor habría sobre-comprado. Degenerado por
   "stock=0 sin demanda".

---

## E. Anomalías / degradaciones

1. **Vista solo almacén RAW**: la reconstrucción usa únicamente LAB-M1/SAA-M1/
   MAG-M1; las transferencias a producción/FG hacen que el saldo RAW acumulado
   pueda ser negativo (tapa/contra gotero 2026-01: -259/-242) cuando el material
   vive en otra capa (LAB-T3 granel, LAB-P1 WIP). El stock global no es negativo
   (Gate 2); la reconstrucción por almacén sí puede serlo.
2. **Forecast intermitente sub-estima** (gotero/contra): `SEASONAL_MOVING_AVERAGE`
   con muchos meses cero produce demandas bajas → `MISSED_PURCHASE`. Coherente
   con `INTERMITTENT`/`INSUFFICIENT_HISTORY` de Gate 6.
3. **Stock=0 sin demanda** (precinto L00838, cloruro L01821): casos degenerados
   que inflan `OVERBUY`.
4. Open purchase as-of-T no reconstruido (limitación declarada): el backtest
   valida la lógica temporal stock+forecast, no el efecto de órdenes en tránsito.

---

## F. Tests

| Suite | Resultado |
|---|---|
| test_backtest_domain (nuevo, unit) | 11 PASS |
| Regresión (production 65 + purchases 22 + stock 20 + equivalence 15 + capacity 13 + lead_time 9 + seasonality 15 + coverage 19 + risk 21 + users 52) | 251 PASS |
| **Total** | **262 PASS** |
| `git diff --check` | OK |
| READ ONLY (HANA_WRITES = 0) | PASS |

---

## G. Archivos modificados

```
validation/backtest/backtest_domain.py
validation/backtest/purchase_decision_backtest_v1.py
validation/backtest/test_backtest_domain.py
docs/purchase_decision_backtest_v1_report.md
```

---

## H. Qué NO cambió

| Ítem | Estado |
|---|---|
| HANA writes | 0 |
| Parquet legacy | UNCHANGED |
| Podman lifecycle | UNCHANGED |
| VPN/network | UNCHANGED |
| Git operations | NONE |
| Gates 1–8 | intactos (regresión 251 PASS) |

---

## I. Quality flags

`POTENTIAL_STOCKOUT_CENSORED_DEMAND`, `INTERMITTENT`, `INSUFFICIENT_HISTORY`,
`UOM_UNRESOLVED`, `PHYSICAL_SUPPLY_LEAD_TIME_UNRESOLVED`,
`LEAD_TIME_LOW_SAMPLE`. Backtest-specific: `RAW_WAREHOUSE_ONLY_VIEW`,
`FORECAST_UNDERESTIMATE_INTERMITTENT`, `ZERO_STOCK_NO_DEMAND`.

---

## J. Próximo gate recomendado

`TELCHI_PURCHASE_EXECUTIVE_CASES_V1` (Gate 10): casos ejecutivos entendibles por
dueño/gerencia para los trazadores (soda, cloruro, benzoato, gotero/Matriplast,
bronceador L03124), con la cadena completa QUÉ/CUÁNTO/CUÁNDO/ACCIÓN/CONFIANZA.

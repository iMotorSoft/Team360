# TELCHI SAP — PURCHASE RISK ENGINE V1

**Gate:** `TELCHI_PURCHASE_RISK_ENGINE_V1_PASS`
**Date:** 2026-08-30
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / DECISIÓN (Gate 8 del roadmap de abastecimiento)

---

## A. Resultado

**PASS** — Motor de decisión de compra que convierte las coberturas del Gate 7
en recomendaciones accionables y explicables, sin score opaco: cada decisión se
deriva de variables visibles (cobertura, mes de stockout, lead time p90, orden
abierta, confianza de suministro, estacionalidad, criticidad del componente).

---

## B. Semántica de decisión (reglas visibles)

| Decisión | Regla |
|---|---|
| `BUY_NOW` | `LATEST_SAFE_ORDER_MONTH <= mes snapshot` (ordenar/acelerar ya) |
| `BUY_SOON` | dentro de la ventana de advertencia documentada (2 meses) |
| `WATCH` | stockout futuro no urgente, o lead time sin historial |
| `SAFE` | cobertura física/abierta >= requerimiento |
| `DO_NOT_BUY` | equivalente ya transformado en PT cubre la demanda (sin doble conteo) |
| `EXCESS_STOCK` | demanda declive/discontinuada con cobertura abundante |

```
LATEST_SAFE_ORDER_MONTH = STOCKOUT_MONTH − ceil((LEAD_TIME_P90 + SAFETY_BUFFER)/30.44)
SAFETY_BUFFER (HEURÍSTICO) = 7d base + 7d forecast incierto + 7d compartido + 14d muestra baja
```

- `EQUIVALENT_IN_FG` (ya transformado) SÍ compensa la demanda futura en la
  decisión de compra (cubre demanda sin nueva producción); NUNCA se suma a
  capacidad de producción (sección 43).
- Flags coexistentes: `PRODUCTION_BLOCKED`, `IMPORT_DELAY_RISK`,
  `SUPPLIER_RISK`, `IN_TRANSIT_UNRESOLVED`.

---

## C. Evidencia cuantitativa

| Métrica | Valor |
|---|---:|
| Materiales evaluados (PURCHASED/MIXED) | 995 |
| `BUY_NOW` | 179 |
| `BUY_SOON` | 37 |
| `WATCH` | 137 |
| `SAFE` | 531 |
| `DO_NOT_BUY` | 45 |
| `EXCESS_STOCK` | 66 |
| FG con `PRODUCTION_BLOCKED` (envase limitante) | 226 |

**Hallazgo central (confirma Gate 4/5):** la urgencia de compra se concentra en
**envases/etiquetas**, no en la materia prima química. Los primeros `BUY_NOW`
son tapa PET (236 FG), caja cartón (230 FG), papel/etiqueta (109 FG), bolsa
cristal (97 FG), precinto (40 FG).

---

## D. Casos ejecutivos

### 1. Benzoato de sodio (L01785) — `BUY_NOW`
- **Qué pasa**: el benzoato (conservante) cubre hasta oct-2026 con stock físico;
  agotamiento proyectado nov-2026.
- **Cuánto tenemos**: 16.585 kg físico + 30.000 kg en orden abierta (importación).
- **Cuánto necesitamos**: ~68.000 kg en 12 meses (10–19 productos).
- **Qué tarda**: lead time p90 = 160 días (importación).
- **Cuándo aparece el riesgo**: `LATEST_SAFE_ORDER_MONTH = 2026-05` (ya vencido).
- **Acción**: ordenar/adelantar el faltante (~21 t) ya; la orden abierta de 30 t
  no alcanza.
- **Confianza**: HIGH.

### 2. Soda cáustica (L01010) — `SAFE` + `IMPORT_DELAY_RISK`
- **Qué pasa**: poco raw físico (9.373 kg), pero la demanda ya está cubierta por
  el material en PT (5.371 kg) y la orden abierta de **108.000 kg** (Hainan).
- **Acción**: NO re-comprar; **monitorear la llegada** de la importación (el
  riesgo es el retraso del ciclo, no la cantidad).
- **Confianza**: MEDIUM (`IN_TRANSIT_UNRESOLVED`).

### 3. Cloruro de calcio (L01821) — `SAFE` (baja confianza por UOM)
- **Qué pasa**: raw físico mínimo (300 kg) pero **9.226 kg ya transformados en
  PT**; la demanda está cubierta por producto terminado.
- **Action**: no comprar MP; la PO abierta de 92 t es reposición de ciclo, no de
  emergencia.
- **Nota**: `UOM_UNRESOLVED` (ratio BOM bolsa 25 kg vs producto 1 kg) → el
  requerimiento numérico es de baja confianza; `SUPPLIER_RISK` (n=3).

### 4. Empaque crítico — `PRODUCTION_BLOCKED` (226 FG)
- **Qué pasa**: la producción se bloquea por envase/etiqueta, no por MP.
- **Ejemplos**: L00219 tapa PET (lt p90 113d, 236 FG), L00189 caja cartón
  (230 FG), L00742 papel fotográfico/etiqueta (109 FG), L00216 precinto (40 FG).
- **Acción**: priorizar el reabastecimiento de envases compartidos antes que
  cualquier químico.

### 5. Bronceador L03124 — `EXCESS_STOCK`
- **Qué pasa**: cobertura a fin de temporada 1,59x y al pico 1,91x.
- **Acción**: no comprar; vigilar posible sobre-stock post-temporada.

---

## E. Anomalías / degradaciones

1. `UOM_UNRESOLVED` (cloruro): ratio BOM mezcla bolsa 25 kg vs producto 1 kg;
   baja confianza en el requerimiento.
2. `LEAD_TIME_LOW_SAMPLE` (soda n=8, cloruro n=3): percentiles inestables →
   `SUPPLIER_RISK`.
3. `PHYSICAL_SUPPLY_LEAD_TIME_UNRESOLVED` (heredado Gate 5): lead time documental
   comprimido por invoice-first/backdated; IMP con recepción real sí refleja ciclo.
4. 531 materiales `SAFE` incluyen casos cubiertos por orden abierta (riesgo de
   llegada, no de cantidad) — visibles vía `IN_TRANSIT_UNRESOLVED`.

---

## F. Tests

| Suite | Resultado |
|---|---|
| test_risk_domain (nuevo, unit) | 21 PASS |
| Regresión (production 65 + purchases 22 + stock 20 + equivalence 15 + capacity 13 + lead_time 9 + seasonality 15 + coverage 19 + users 52) | 230 PASS |
| **Total** | **251 PASS** |
| SQL contracts 1/1 ejecutan | PASS |
| `git diff --check` | OK |
| READ ONLY (HANA_WRITES = 0) | PASS |

---

## G. Archivos modificados

```
sql/current/risk/import_supply_position_v1.sql
validation/risk/risk_domain.py
validation/risk/purchase_risk_engine_v1.py
validation/risk/test_risk_domain.py
docs/purchase_risk_engine_v1_report.md
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
| Gates 1–7 | intactos (regresión 230 PASS) |

---

## I. Quality flags

`IN_TRANSIT_UNRESOLVED`, `BACKDATED_PO`, `PHYSICAL_SUPPLY_LEAD_TIME_UNRESOLVED`,
`LEAD_TIME_LOW_SAMPLE`, `SUPPLIER_HISTORY_LOW_SAMPLE`, `UOM_UNRESOLVED`,
`SHARED_COMPONENT`, `SHARED_COMPONENT_ALLOCATION_UNRESOLVED`,
`SEASONALITY_UNCERTAIN`, `POTENTIAL_STOCKOUT_CENSORED_DEMAND`,
`EXACT_PRODUCTION_LINEAGE_UNAVAILABLE`, `MULTILEVEL_EXPANSION_PARTIAL`.

---

## J. Próximo gate recomendado

`TELCHI_PURCHASE_DECISION_BACKTEST_V1` (Gate 9): reconstruir snapshots históricos
(pre-temporada, cierre de mes, picos) sin hindsight y comparar la recomendación
en T con el stockout/overstock/compra/recepción observados después
(`POTENTIAL_EARLY_WARNING` / `POTENTIAL_OVERBUY` / `POTENTIAL_MISSED_PURCHASE`).

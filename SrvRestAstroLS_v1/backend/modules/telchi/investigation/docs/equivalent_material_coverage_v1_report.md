# TELCHI SAP — EQUIVALENT MATERIAL COVERAGE V1

**Gate:** `TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_PASS`
**Date:** 2026-08-30
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / COBERTURA (Gate 7 del roadmap de abastecimiento)

---

## A. Resultado

**PASS** — Cobertura temporal mes a mes (producto por producto y componente por
componente) integrando las seis capas de material sin fusionarlas: FG usable,
stock físico de componentes, equivalente ya transformado en FG, FG adicional
producible, posición abierta de compra y forecast mensual, con contexto de lead
time y control de no doble conteo, sobre datos reales HANA.

---

## B. Semántica cerrada

```
A. USABLE_FINISHED_GOODS        = Σ(OnHand - IsCommited) en roles utilizables
   (FINISHED_GOOD/BRANCH/DISTRIBUTION/MOBILE/DISPENSING/CONSIGNMENT/RETURNS)
B. PHYSICAL_COMPONENT_STOCK     = Σ(OnHand - IsCommited) en LAB-M1/SAA-M1/MAG-M1
C. EQUIVALENT_IN_FINISHED_GOODS = material YA transformado (Gate 3, terminal)
D. ADDITIONAL_PRODUCIBLE_FG     = MAX_PRODUCIBLE (Gate 4, expansión terminal)
E. OPEN_PURCHASE_POSITION       = POR1.OpenQty en POs abiertas (DOCUMENTED_ORDER)
F. EXPECTED_FUTURE_DEMAND       = forecast mensual (Gate 6)
```

- **Waterfall FG**: mes a mes, demanda → consume FG usable → consume FG
  adicional producible → si no alcanza, STOCKOUT en ese mes.
- `C` (equivalente en FG) **nunca** se suma a `B` ni a `D` (material ya
  consumido; expresa cuánta demanda YA está cubierta, no sirve para producir).
- `E` queda fuera de disponibilidad temporal confirmada (confidence
  `DOCUMENTED_ORDER`, `IN_TRANSIT_UNRESOLVED`); se reporta por separado.

---

## C. Cobertura cuantitativa

| Métrica | Valor |
|---|---:|
| FG analizados (con supply y/o forecast) | 667 |
| FG totalmente cubiertos (12 meses) | 275 |
| FG con stockout proyectado (≤ 12 meses) | 392 |
| Componentes analizados | 1.028 |
| Componentes en zona de riesgo por lead time (gap < 0) | 220 |
| Componentes compartidos (usan ≥ 2 FG, terminal) | 647 |
| Snapshot | 2026-08 |

**Reconciliación P0.2 (OPEN_PURCHASE vs OITW.OnOrder):**

| Métrica | Valor |
|---|---:|
| Ítems con PO abierta | 263 |
| Coincidencia exacta | 152 |
| Mismatch | 111 |

`OITW.OnOrder` es un agregado del sistema en **UOM de inventario** que incluye
más que las POs abiertas (conversión de UOM y fuentes adicionales, p.ej.
benzoato OnOrder 32.450 vs open PO 30.000). La cantidad documental canónica de
pedido futuro es `OPEN_PURCHASE_POSITION` (nivel de línea, ligada a proveedor/
fecha/U_TIPOCOMPRA). **No sumar ambas.**

---

## D. Bronceador L03124 (caso P0)

| Campo | Valor |
|---|---:|
| Patrón | SEASONAL (pico ene) |
| FG usable | 327 uds |
| FG adicional producible | 4.892 uds |
| Componente limitante | L00050 |
| Forecast sep–feb | 521 / 452 / 439 / 472 / 852 / 550 |
| Demanda a fin de temporada (feb) | 3.286 uds |
| Demanda al próximo pico (ene) | 2.736 uds |
| **Cobertura a fin de temporada** | **1,59x** |
| **Cobertura al próximo pico** | **1,91x** |
| Stockout esperado | ninguno (cubierto ≥ 12 meses) |

Lectura: L03124 tiene **exceso de cobertura** para la temporada (1,59x). No
necesita compra inmediata; es candidato a `DO_NOT_BUY`/`EXCESS_STOCK` en Gate 8.

---

## E. Casos de componentes (material position + cobertura)

| Material | Físico | Equiv. en FG | Open purchase | Cobertura física | Lead time p90 | Gap |
|---|---:|---:|---:|---|---:|---:|
| Soda cáustica (L01010) | 9.373 kg | 5.371 kg | 108.000 kg | hasta 2026-11 (stockout dic) | 201d (n=8) | **-79d** |
| Cloruro de calcio (L01821) | 300 kg | 9.226 kg | 92.000 kg | ≥ 12 meses | 16d (n=3) | +380d |
| Benzoato de sodio (L01785) | 16.585 kg | 11.880 kg | 30.000 kg | hasta 2026-10 (stockout nov) | 160d (n=23) | **-69d** |
| Frasco gotero (L03427) | 96.102 | 13.019 | 40.800 | ≥ 12 meses | 128d (n=18) | +268d |
| Tapa gotero (L03428) | 85.352 | 13.224 | 40.800 | ≥ 12 meses | 128d | +268d |
| Contra-tapa gotero (L03429) | 85.866 | 12.709 | 40.800 | ≥ 12 meses | 128d | +268d |

Lecturas ejecutivas:

- **Soda cáustica**: poco raw físico (9,4 t) frente a requerimiento mensual
  ~2,8–3,7 t → agotamiento ~dic 2026, con lead time importado p90 201d →
  **ya está en zona de riesgo**; la PO abierta de 108 t (Hainan) es el rescate.
- **Cloruro de calcio**: raw físico mínimo (300 kg) pero **9.226 kg ya
  transformados en PT** → la demanda ya está cubierta por producto terminado;
  no es urgencia de compra de materia prima (el 92 t en tránsito es reposición
  de ciclo largo, no de emergencia).
- **Benzoato**: 16,6 t físicas cubren hasta oct; lead time 160d vs cobertura
  ~3 meses → **zona de riesgo**; 30 t abiertas en importación.
- **Gotero (frasco/tapa/contra)**: ~85–96 k físicos c/u + 40,8 k pedidos →
  **no limita**; cubren más de 12 meses con holgura (confirma Gate 4, ahora
  con dimensión temporal).

---

## F. Riesgo por lead time (empaque crítico)

Componentes con `LEAD_TIME_COVERAGE_GAP < 0` (cobertura física < lead time
conservador): **220** componentes. Ejemplos de empaque crítico (Gate 4/5):

| Componente | Lead time p90 | Interpretación |
|---|---:|---|
| L00219 (tapa PET) | 113d | alta dispersión; cobertura frecuentemente < 113d |
| L00097 (frasco 1L) | 110d | lead time largo en p90 |
| L00838 (precinto) | 34d | p90 elevado para un precinto |

El patrón de Gate 4 se mantiene en el tiempo: el empaque/etiqueta puede
desabastecer antes que la materia prima química.

---

## G. Anomalías / degradaciones

1. `OITW.OnOrder ≠ OPEN_PURCHASE_POSITION` (111/263 ítems): UOM + fuentes
   extra; se adopta OPEN_PURCHASE como canónica (anti doble conteo).
2. `UOM_UNRESOLVED` en cloruro: el ratio BOM `ITT1.Quantity/OITT.Qauntity`
   mezcla bolsa 25 kg vs producto 1 kg (ratio 1,0); el equivalente en FG
   (9.226 kg) y la cobertura física del componente son de **baja confianza**.
3. `PHYSICAL_SUPPLY_LEAD_TIME_UNRESOLVED` (heredado de Gate 5): el lead time
   documental de importaciones/completados locales está comprimido por
   invoice-first/backdated; solo IMP con recepción real refleja ciclo físico.
4. `LEAD_TIME_LOW_SAMPLE`: soda n=8, cloruro n=3 (percentiles poco estables).
5. Gotero/benzoato: consumidores directos (6/10) < consumidores terminales
   (15/19) por kits/promos/experimentos que embeben el envase/insumo vía semi
   (BOM multinivel, sección 11/12).

---

## H. Tests

| Suite | Resultado |
|---|---|
| test_coverage_domain (nuevo, unit) | 19 PASS |
| Regresión (production 65 + purchases 22 + stock 20 + equivalence 15 + capacity 13 + lead_time 9 + seasonality 15 + users 52) | 211 PASS |
| **Total** | **230 PASS** |
| SQL contracts 4/4 ejecutan | PASS |
| `git diff --check` | OK |
| READ ONLY (HANA_WRITES = 0) | PASS |

---

## I. Archivos modificados

```
sql/current/coverage/fg_usable_stock_v1.sql
sql/current/coverage/component_physical_stock_v1.sql
sql/current/coverage/open_purchase_position_v1.sql
sql/current/coverage/open_purchase_vs_onorder_v1.sql
validation/coverage/coverage_domain.py
validation/coverage/equivalent_material_coverage_v1.py
validation/coverage/test_coverage_domain.py
docs/equivalent_material_coverage_v1_report.md
```

---

## J. Qué NO cambió

| Ítem | Estado |
|---|---|
| HANA writes | 0 |
| Parquet legacy | UNCHANGED |
| Podman lifecycle | UNCHANGED (manual del operador) |
| VPN/network | UNCHANGED |
| Git operations | NONE |
| Gates 1–6 | intactos (regresión 211 PASS) |

---

## K. Quality flags preservados

`IN_TRANSIT_UNRESOLVED`, `BACKDATED_PO`,
`PHYSICAL_SUPPLY_LEAD_TIME_UNRESOLVED`, `LEAD_TIME_LOW_SAMPLE`,
`UOM_UNRESOLVED`, `SHARED_COMPONENT`,
`SHARED_COMPONENT_ALLOCATION_UNRESOLVED`, `SEASONALITY_UNCERTAIN`,
`POSSIBLE_PRODUCT_SUCCESSOR`, `POTENTIAL_STOCKOUT_CENSORED_DEMAND`,
`EXACT_PRODUCTION_LINEAGE_UNAVAILABLE`, `MULTILEVEL_EXPANSION_PARTIAL`.

---

## L. Próximo gate recomendado

`TELCHI_PURCHASE_RISK_ENGINE_V1` (Gate 8): convertir estas posiciones y
coberturas en decisiones accionables (`BUY_NOW`, `BUY_SOON`, `WATCH`, `SAFE`,
`DO_NOT_BUY`, `EXCESS_STOCK`, `PRODUCTION_BLOCKED`, `IMPORT_DELAY_RISK`),
derivando `LATEST_SAFE_ORDER_DATE` de `EXPECTED_STOCKOUT_DATE −
CONSERVATIVE_LEAD_TIME − SAFETY_BUFFER`.

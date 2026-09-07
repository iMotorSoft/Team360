# TELCHI SAP — MAX PRODUCIBLE BY COMPONENT V1

**Gate:** `TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_PASS`
**Date:** 2026-08-27
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / CAPACIDAD (Gate 4 del roadmap)

---

## A. Resultado

**PASS** — Capacidad máxima de producción por componente determinada sobre
stock físico utilizable real, con componente limitante y control de componentes
compartidos, sin reutilizar material ya transformado en FG.

---

## B. Semántica

```
AVAILABLE_COMPONENT_FOR_PRODUCTION = OnHand - IsCommited
                                      (solo role RAW_MATERIAL: LAB-M1, SAA-M1, MAG-M1)

COMPONENT_CAPACITY[fg][comp] = available[comp] / requirement[fg][comp]

THEORETICAL_MAX_IF_PRIORITY[fg] = MIN(component capacities)
LIMITING_COMPONENT = argmin
```

- `EQUIVALENT_IN_FG` (Gate 3) **NO** entra en capacidad: es material ya
  transformado, no utilizable para nueva producción.
- `MATERIAL_MAX_PRODUCIBLE` ≠ `OPERATIONAL_FACTORY_CAPACITY` (sin datos de
  máquina/tiempo; no se inventa capacidad industrial).
- Requirement por unidad = `HISTORICAL_PRODUCTION_RATIO` (ΣIGE1/ΣIGN1) con
  fallback `CURRENT_BOM` (ITT1.Quantity/OITT.Qauntity). **Filtrado de ruido**:
  se descartan componentes inexistentes en OITM (fantasmas M0001/R0004) y
  auto-referencias (componente == FG, patrón re-packaging).

---

## C. Evidencia cuantitativa

| Métrica | Valor |
|---|---:|
| FG con capacidad resuelta | 1.050 |
| Componentes disponibles (raw whs) | 1.287 |
| Componentes compartidos (usan ≥2 FG) | 590 |
| Stock físico utilizable (componentes) | ~6,45 M uds (LAB-M1 4,0M + SAA-M1 2,45M) |

**Hallazgo central**: el componente limitante suele ser **envase/etiqueta**, no
la materia prima química.

---

## D. Casos trazadores (Gate 4)

| Material | Físico disponible | FG que lo usan | Observación |
|---|---:|---:|---|
| Soda cáustica 25kg | 9.373 kg | 2 (L01013, L01015) | limitante = ETIQUETA (L00205), no la soda |
| Cloruro de calcio 25kg | 300 kg | 1 (L01822) | limitante = PRECINTO SUJETABLE (L00838) |
| Benzoato 25kg | 19.035 kg | 10 | L00504 limitada por ETIQUETA |
| Frasco gotero 30mL | ~95.000 | 6 | NO limita; limitantes L00130/L00900/L01166 |

**Gotero**: 6 FG lo usan (vaselina/glicerina/miel rosada/aceite ricino...),
pero con 95.000 físicos en LAB-M1 no es limitante (capacidad gotero 177k–2,5M
por FG). La tensión detectada en Gate 2 estaba en **LAB-P1 (WIP)**
(committed 10.000 > onhand 9.978), una capa separada — señal de demanda de
envases, no de escasez de material crudo.

**Alcohol L01001**: limitante = L00001 (alcohol 70% granel); el granel en
almacén RAW (SAA-M1) da capacidad 783 botellas; el granel adicional en
LAB-T3 (rol FG) es otra capa.

---

## E. Invariantes / no doble conteo

| Invariante | Resultado |
|---|---|
| MAX_PRODUCIBLE == MIN(capacidades) y limiting = argmin | PASS (test) |
| EQUIVALENT_IN_FG no reutilizado en capacidad | PASS (solo raw whs) |
| Componente compartido no asignado independientemente | PASS (mapa de competencia) |
| UOM no compatible no se divide | GUARD |
| Capacidad negativa clasificada (no silenciada a 0) | test |
| Multi-nivel: semi + raw no doble conteo | test |

---

## F. Anomalías / degradaciones

1. Componentes fantasma en IGE1/ITT1 (M0001/M0003/M0004/R0004) inexistentes en
   OITM → excluidos (sin stock ni UOM).
2. Auto-referencias (FG consume a sí mismo, re-packaging) → excluidas.
3. Granel (L00001) distribuido entre RAW (SAA-M1) y FG (LAB-T3): solo el RAW
   cuenta como inmediatamente disponible.
4. WIP (LAB-P1/P2/SAA-P1) muy comprometido (LAB-P1 committed 189k de 227k) →
   no se usa como material disponible; queda como capa separada.

---

## G. Tests

| Suite | Resultado |
|---|---|
| test_capacity_domain (nuevo, unit) | 13 PASS |
| Regresión production (65) + purchases (22) + stock (20) + equivalence (15) + users (52) | 174 PASS |
| SQL contracts 2/2 ejecutan | PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## H. Artefactos

```
sql/current/capacity/component_availability_v1.sql
sql/current/capacity/fg_component_requirement_v1.sql
validation/capacity/capacity_domain.py
validation/capacity/max_producible_by_component_v1.py
validation/capacity/test_capacity_domain.py
docs/max_producible_by_component_v1_report.md
```

---

## I. Limitaciones

1. Disponibilidad restringida a RAW_MATERIAL; transferible (branch/dispensing)
   y WIP se mantienen en capas separadas (no incorporados a capacidad).
2. Ratio histórico agregado (sin segmentación por época de receta).
3. `MATERIAL_MAX_PRODUCIBLE`, no capacidad operativa de fábrica.

---

## J. Próximo gate recomendado

`TELCHI_PURCHASE_LEAD_TIME_V1` (Gate 5): separar `SAP_DOCUMENT_LEAD_TIME`
(PO→Invoice→GR) de `PHYSICAL_SUPPLY_LEAD_TIME` (UNRESOLVED), por U_TIPOCOMPRA,
proveedor y material, con percentiles P50/P75/P90 y el flag `BACKDATED_PO`.

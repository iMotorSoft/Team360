# TELCHI SAP — PRODUCTION RECONCILIATION V1

**Gate:** `TELCHI_PRODUCTION_RECONCILIATION_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## A. Resultado

**PASS** — La reconciliación de producción quedó demostrada normalizando el
consumo esperado al output real: para lo que realmente se produjo, se verificó
cuánto se consumió, con reclasificación masiva del residual del gate anterior.

---

## B. Contratos combinados

```text
EXPECTED_FOR_PLAN            = (BaseQtyNum/BaseQtyDen) × OWOR.PlannedQty
EXPECTED_FOR_ACTUAL_OUTPUT   = (BaseQtyNum/BaseQtyDen) × NET_ACTUAL_OUTPUT_QTY
NET_ACTUAL_CONSUMPTION       = SUM(IGE1.Quantity) BT=202
NET_ACTUAL_OUTPUT_QTY        = SUM(IGN1.Quantity) BT=202
```

Tres varianzas distintas, sin mezclar:
1. OUTPUT_PLAN_VARIANCE (producción vs plan)
2. COMPONENT_PLAN_VARIANCE (consumo vs plan)
3. **NORMALIZED_CONSUMPTION_VARIANCE (consumo vs output real) ← métrica principal**

---

## C. Output normalization

| Output ratio (actual/plan) | Órdenes |
|---------------------------|--------:|
| =1 (exacto) | 18,059 |
| 0 (sin output) | 827 |
| >1 (sobre-plan) | 1,102 |
| 0-1 (parcial) | 499 |

El ejemplo fundamental quedó protegido por test: planned=1,000, actual=800,
consumo=1,620 → contra plan parecía UNDER -380; normalizado a 800 producidas:
expected=1,600 → OVER +20 (+1.25%).

---

## D. Plan vs Normalized variance (20,487 órdenes, 140,391 líneas)

| Clasificación | PLAN | NORMALIZED | Δ |
|---------------|-----:|-----------:|--:|
| EXACT | 118,281 | **122,296** | +4,015 |
| OVER | 13,273 | **8,425** | -4,848 |
| UNDER | 2,838 | 3,518 | +680 |
| EXPECTED_NOT_CONSUMED | 5,999 | 6 | -5,993 |
| EXPECTED_ZERO_ACTUAL_ZERO | — | 5,993 | nuevo |
| EXPECTED_ZERO_ACTUAL_POSITIVE | — | 153 | nuevo |

---

## E. Reclassification matrix (resultado central)

| Plan → Normalizado | Líneas | Interpretación |
|--------------------|-------:|----------------|
| OVER → EXACT | **6,088** | 46% del "sobreconsumo" era producción parcial |
| UNDER → EXACT | **2,382** | 84% del "bajo consumo" era producción sobre-plan |
| EXACT → OVER | 1,273 | parecía exacto; consume más por unidad real |
| EXACT → UNDER | 3,042 | parecía exacto; consume menos por unidad real |
| NOT_CONSUMED → ZERO_OUTPUT | 5,993 | explicado por output cero (no pérdida) |
| OVER → OVER | 6,813 | sobreconsumo real persiste |
| UNDER → UNDER | 116 | bajo consumo real persiste |

**El residual del gate anterior (OVER 11.5%, UNDER 3.2%, NOT_CONSUMED 2.2%)
queda mayormente explicado por la normalización al output real.**

---

## F. Normalized over

- 8,425 líneas (6.0%): consumo real > expected para lo producido.
- 6,813 permanecen OVER tras normalización (sobreconsumo real candidato).
- Top casos preservados con DocEntry/DocNum/componente/varianza.

---

## G. Normalized under

- 3,518 líneas (2.5%): consumo real < expected para lo producido.
- 116 permanecen UNDER tras normalización (bajo consumo real candidato).

---

## H. Zero-output / casos especiales

- 827 órdenes sin output; 5,993 líneas `EXPECTED_ZERO_ACTUAL_ZERO` (explicadas).
- 153 líneas `EXPECTED_ZERO_ACTUAL_POSITIVE` (consumo sin output — el caso
  CONSUMPTION_WITHOUT_OUTPUT del gate anterior).
- Rework (17757) y backdated receipts preservados como contexto, no contaminan
  la población estándar.

---

## I. Produced component context

- 255 produced components; en la reconciliación se incorporan como contexto
  (is_produced_component, produced_parent_count) **sin expandir la receta
  upstream** — las recetas planas se mantienen planas.

---

## J. Systematic patterns (post-normalización)

| Componente | Líneas | Exact | Over | Under | Over rate |
|-----------|-------:|------:|-----:|------:|----------:|
| **L01945** | 661 | 661 | 0 | 0 | **0.0%** |
| **L00099** | 3,004 | 2,417 | 419 | 168 | **13.9%** |
| L00001 | 441 | 388 | 2 | 51 | 0.5% |
| L02475 | 140 | 136 | 3 | 1 | 2.1% |

**Hallazgo**: el sobreconsumo de **L00099 persiste tras normalización** (13.9%
over, valores fijos +100/+200/+300/+400/+500) → `SYSTEMATIC_NORMALIZED_
OVERCONSUMPTION_CANDIDATE` real, no artefacto del plan. L01945 (semielaborado)
se consume 100% exacto. L02475 confirmado baja materialidad.

---

## K. Rework / cycles

- Rework: 1,252 líneas output-mismatch y caso 17757 preservados como contexto
  (`is_rework` flag); no distorsionan los agregados estándar.
- Ciclos del grafo de dependencia: no causan recursión (sin expansión).

---

## L. Tests

| Suite | Resultado |
|-------|-----------|
| test_production_reconciliation_domain | 13 PASS (incluye ejemplo fundamental) |
| test_produced_component_dependency_domain | 9 PASS |
| test_output_traceability_domain | 11 PASS |
| test_component_consumption_domain | 8 PASS |
| test_recipe_bom_domain | 12 PASS |
| Regresión users/attribution | 52 PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## M. Artefactos

```
validation/production/production_reconciliation_domain.py
validation/production/production_reconciliation_v1.py
validation/production/test_production_reconciliation_domain.py
docs/production_reconciliation_v1_report.md
```

---

## N. Limitaciones

1. `UOM_CONFIRMATION=EXACT` en la población analizada; se documenta el
   mecanismo para marcar UNRESOLVED si aparece una UOM incompatible.
2. `OUTPUT_UNRESOLVED` (líneas con output item ≠ parent, rework) se aíslan
   como contexto, no en la comparación estándar.
3. No se calculó costo de varianza (gate de valor posterior).
4. Los patrones L00099 (13.9% over) requieren validación de negocio: receta
   desactualizada, empaque, o emisión operativa real.
5. `PREVIOUS_CLASSIFICATION_REFINED`: los TRUE_OVER/UNDER del gate de consumo
   se refinan con la normalización; la trazabilidad previa permanece válida.

---

## O. Próximo gate

`TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1`
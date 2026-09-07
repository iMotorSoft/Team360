# TELCHI SAP — RECIPE / BOM TRACEABILITY V1

**Gate:** `TELCHI_RECIPE_BOM_TRACEABILITY_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## A. Resultado

**PASS** — La semántica de receta (maestra e histórica), el cálculo de expected
quantity, el método de emisión y la comparación expected vs actual fueron
demostrados con datos reales SAP HANA.

---

## B. Fuentes canónicas

| Entidad | Fuente | Key | Rol |
|---------|--------|-----|-----|
| RECETA MAESTRA (current) | OITT/ITT1 | Father / Father+Code | estado actual |
| RECETA HISTÓRICA (orden) | OWOR/WOR1 | DocEntry / DocEntry+LineNum | receta al crear la orden |
| CONSUMO REAL | IGE1 (BaseType=202) | BaseEntry+BaseLine+ItemCode | consumption |
| PRODUCTO TERMINADO | IGN1 (BaseType=202) | BaseEntry | output |
| MOVIMIENTO | OINM TT59/60 | BASE_REF | reconciliación secundaria |

**Regla**: para análisis histórico, **WOR1 tiene prioridad** sobre ITT1 (la orden
copia la receta al crearse).

---

## C. Fórmula expected validada

```
EXPECTED_COMPONENT_QTY = (WOR1.BaseQtyNum / WOR1.BaseQtyDen) × OWOR.PlannedQty
```

Validación masiva (140,328 líneas, Type='S'):

| Métrica | Valor |
|---------|-------|
| Exacto (abs ≤ 0.001) | 130,230 (92.8%) |
| Exacto con tolerancia relativa 0.1% | 132,550 (94.5%) |
| Diferente | 10,098 (7.2%) |

Las diferencias se explican por:
1. **Redondeo de display**: `WOR1.PlannedQty` se guarda redondeado (4 decimales)
   mientras la fórmula da precisión completa (p.ej. calc=3.333333, WOR1=3.3333).
2. **Casos reales planificados distintos**: cuando `num/den ≠ 1`, la orden puede
   planificar el componente con ajuste manual (receta override).

El campo `WOR1.BaseQty` es una versión redondeada del factor; `BaseQtyNum/BaseQtyDen`
es el factor exacto. **Usar siempre num/den.**

---

## D. Semántica IssuedQty

```
ISSUEDQTY_SEMANTICS = ACTUAL_ACCUMULATED
```

Validación masiva (140,319 líneas):

| Comparación | Conteo |
|-------------|--------|
| `WOR1.IssuedQty == SUM(IGE1.Quantity)` | 134,291 |
| Diferente | 1 (0.0007%) |
| Sin IGE1 (IssuedQty=0) | 6,027 |

- `IssuedQty` es el **acumulado de consumo real emitido** (no expected).
- El único caso discrepante (order 17757, comp L01942): dos IGE1 (docEntry 44000,
  44027) de 57.1429 cada uno; IssuedQty=57.1429 solo cuenta uno — actualización
  incompleta del acumulado. 1 en 134K.
- IGE1: 100% cantidades positivas, 0 cancelados (OIGE.CANCELED='N' en 49,160).

---

## E. Métodos de emisión

| Método | WOR1 líneas | % |
|--------|------------|---|
| M (Manual) | 95,579 | 67.5% |
| B (Backflush) | 46,058 | 32.5% |

Los componentes backflush SÍ generan IGE1 (issue materializada) — verificado
en muestra real (order 28629, M0006/R0019 qty=20).

---

## F. Fidelidad de receta

- 905 productos producidos; **898 (99.2%) tienen BOM actual** (ITT1).
- **7 producidos sin BOM actual** — receta histórica eliminada o carga manual.
- **145 BOM definidos nunca producidos**.
- OITT TreeType: P=Production (1,020), S=Sales (23).

---

## G. Recipe drift (WOR1 última orden vs ITT1 actual)

Comparación por producto (890 comparables):

| Clasificación | Productos |
|---------------|-----------|
| Misma cantidad de componentes | 544 (61%) |
| Solo en histórico (componente eliminado) | 17 |
| Solo en actual (componente añadido) | 39 |
| Ambos difieren | 290 (componentes distintos) |

Ejemplo real: producto L00235 tiene 7 componentes históricos y 7 actuales pero
`M0001` solo en histórico y `M0003/M0004` solo en actual → receta cambiada.

Estos son `RECIPE_DRIFT` (cambio de receta), no errores.

---

## H. Expected vs actual (muestra 2,000 órdenes, 16,475 líneas)

| Estado | Líneas | % |
|--------|-------:|---|
| EXACT | 13,982 | 84.9% |
| OVER_CONSUMPTION | 1,539 | 9.3% |
| UNDER_CONSUMPTION | 580 | 3.5% |
| EXPECTED_NOT_CONSUMED | 374 | 2.3% |

Ejemplos reales de over-consumption:
- Order 28538 (L01059): comp L00236 expected=1532, issued=1533 (+1).
- Order 28534 (L02927): comp L03204 expected=10.633, issued=12.333 (+1.7).

---

## I. Cobertura documental

```
WOR1 → IGE1 (EXACT_DOCUMENT_LINK via BaseEntry+BaseLine+ItemCode):
  lines with exact link: 134,291
  lines without issue:    6,027

Duplicados: WOR1 key (DocEntry+LineNum) = 0; IGE1 key = 0.
Nulls WOR1 en ItemCode/BaseQty/PlannedQty/IssuedQty/wareHouse = 0.
```

---

## J. Edge cases

| Caso | Resultado |
|------|-----------|
| BaseQtyDen=0 | 0 en la población (todos tienen factor válido) |
| Cantidades negativas IGE1 | 0 (todas positivas) |
| Cancelados OIGE | 0 |
| IssuedQty=0 sin consumo | 6,027 (expected pero no consumido) |
| Factor decimal periódico | expected con más decimales; issued redondeado 4 dec. |
| Múltiples IGE1 por línea | 1 caso (order 17757) |

---

## K. Tests

| Suite | Resultado |
|-------|-----------|
| test_recipe_bom_domain (fórmula, firma, drift, expected/actual) | 12 PASS |
| Regresión users/attribution | 52 PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## L. Artefactos

```
validation/production/recipe_bom_domain.py
validation/production/recipe_bom_traceability_v1.py
validation/production/test_recipe_bom_domain.py
docs/recipe_bom_traceability_v1_report.md
```

---

## M. Limitaciones

1. `WOR1.PlannedQty` redondeado a 4 decimales: la fórmula (num/den) da el valor
   exacto; comparaciones contra WOR1.PlannedQty requieren tolerancia.
2. 7 productos producidos sin BOM actual: reconstruibles solo desde WOR1.
3. 1 caso IssuedQty inconsistente (actualización parcial del acumulado).
4. `Expected vs actual` en muestra usa IssuedQty como proxy del consumo real
   (validado = ACTUAL_ACCUMULATED); el gate de consumo profundizará con IGE1
   completo, netting y timing.

---

## N. Próximo gate

`TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1`

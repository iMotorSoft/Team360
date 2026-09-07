# TELCHI SAP — PRODUCED COMPONENT DEPENDENCY V1

**Gate:** `TELCHI_PRODUCED_COMPONENT_DEPENDENCY_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## A. Resultado

**PASS** — La red de dependencia de componentes producidos fue reconstruida
demostrando que cada producto tiene su receta plana independiente y el Lake
conecta productos por `ItemCode`.

---

## B. Semántica validada

```text
FLAT SAP RECIPES: cada producto tiene su propia receta (OITT/ITT1 current,
OWOR/WOR1 histórico). SAP NO almacena recetas anidadas.

DERIVED LAKE DEPENDENCIES: la relación A → B (B es componente producido de A)
se deriva por identidad de ItemCode entre output de una orden y consumo de otra.
```

No se construyó ninguna BOM multinivel ficticia como verdad SAP.

---

## C. Item roles (mass validation)

| Métrica | Valor |
|---------|------:|
| Items producidos (output IGN1 real) | 900 |
| Items componentes consumidos (IGE1 real) | 1,323 |
| **Produced components (intersección)** | **255** |
| Con BOM actual (OITT) | 255 (100%) |
| Sin BOM actual | 0 |
| Con 1 parent | 124 |
| Con múltiples parents | 131 (máx 13) |

### Clasificación por roles (no excluyentes)

| Clase | Items |
|-------|------:|
| PRODUCED_AND_INTERMEDIATE | 255 |
| PRODUCED_FINAL_ONLY | 645 |
| COMPONENT_ONLY | 1,063 |
| BOM_PARENT_ONLY | 144 |
| STRUCTURALLY_PRODUCIBLE_CONSUMED | 5 |
| UNKNOWN | 109 |

Los roles son flags independientes (un item puede ser producido + componente +
vendible simultáneamente).

---

## D. Dependency edges

| Métrica | Valor |
|---------|------:|
| Total edges (parent→component, histórico) | 8,175 |
| **Edges parent→produced-component** | **514** |

Cada edge preserva: order count, consumption qty, first/last seen,
`component_has_own_bom`, `component_has_actual_production`, output order count.
Confirmación: `EXACT_DOCUMENT_LINK` (downstream WOR1→IGE1) + `EXACT_ITEM_IDENTITY`
(upstream OWOR→IGN1 por mismo ItemCode).

---

## E. Current vs Historical (dependency drift)

- Drift historical-only (componente consumido históricamente, ausente de la
  receta actual): **detectado** (lista preservada)
- Drift current-only (componente de receta actual nunca consumido históricamente):
  **detectado** (lista preservada)
- Clasificación: `DEPENDENCY_DRIFT` (no error)

---

## F. Intermediate products — TOP shared

| Componente | Parents | Órdenes downstream |
|-----------:|--------:|-------------------:|
| L00001 | 13 | 472 |
| L01945 | 8 | 683 |
| L02944 | 7 | 61 |
| L02837 | 7 | 38 |
| L01295 | 7 | 91 |
| L01129 | 6 | 44 |
| L01006 | 6 | 22 |
| L01175 | 5 | 244 |
| L01115 | 5 | 224 |

Estos son semielaborados internos de alta transversalidad: una falta de stock
de L00001 o L01945 puede afectar múltiples líneas de producción.

---

## G. Derived graph depth

| Métrica | Valor |
|---------|------:|
| Máxima profundidad derivada | **3** (A→B→C) |
| Ciclos (cycle hits) | 14 |
| Self-dependencies | 0 |

- La expansión derivada está protegida (visited set + max depth + cycle count).
- Los 14 cycle hits provienen de componentes que aparecen en su propia cadena
  (rework/receta consistente), no rompen el modelo.
- El grafo es `DERIVED_DEPENDENCY_GRAPH`, nunca `SAP_NESTED_BOM`.

---

## H. Real SAP case — L01945 (semielaborado interno)

| Dimensión | Evidencia |
|-----------|-----------|
| Receta propia | 2 componentes en ITT1 (BOM actual) |
| Producción propia | 480 órdenes, **375,811** unidades (2022-04 → 2026-08) |
| Consumido como componente | 662 órdenes, **379,248** unidades, **8 parents** |
| Upstream ejemplo | OWOR 28154 → IGN1 36867 (output 2,250, SAA-P1) |
| Downstream ejemplo | OWOR 28629 (L03267) consume L01945=1,500; OWOR 28155 (L01064) consume 2,250 |

Cadena documental demostrada: L01945 se fabrica (OWOR→IGN1) y luego se consume
en órdenes de 8 productos finales (WOR1→IGE1). La identidad es `ItemCode`
(no FK entre órdenes, como dicta SAP).

---

## I. Tests

| Suite | Resultado |
|-------|-----------|
| test_produced_component_dependency_domain | 9 PASS |
| test_output_traceability_domain | 11 PASS |
| test_component_consumption_domain | 8 PASS |
| test_recipe_bom_domain | 12 PASS |
| Regresión users/attribution | 52 PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## J. Artefactos

```
validation/production/produced_component_dependency_domain.py
validation/production/produced_component_dependency_v1.py
validation/production/test_produced_component_dependency_domain.py
docs/produced_component_dependency_v1_report.md
```

---

## K. Limitaciones

1. `MAKE_BUY_CLASSIFICATION=PARTIAL`: no se cerró la semántica de compras en
   este gate (componentes con producción Y compra no diferenciados aún).
2. La disponibilidad temporal de semielaborados (producido ≠ disponible al
   momento de la orden downstream) se resolverá con stock histórico posterior.
3. `SAME_DAY_ORDERING_UNRESOLVED` heredado: sin hora confiable en algunos
   documentos.
4. La comparación cuantitativa output vs consumido (L01945: 375K vs 379K)
   no es exacta 1:1 por UOM/inventario intermedio — no se infiere relación
   directa de lotes.

---

## L. Hallazgos para Telchi

1. **255 productos son semielaborados internos** — no son materia prima externa.
2. **L00001 se usa en 13 productos finales**; L01945 en 8 con 683 órdenes:
   un faltante de estos afecta múltiples líneas de producción.
3. La producción del semielaborado L01945 (480 órdenes) y su consumo (662
   órdenes) confirman la dependencia productiva A→B con recetas independientes.
4. 5 items son estructuralmente producibles y consumidos pero sin producción
   real observada — posible brecha de make-or-buy.

---

## M. Próximo gate

`TELCHI_PRODUCTION_RECONCILIATION_V1` (combinará expected/actual consumption
y actual output con el rol produced-component para yield y variances)
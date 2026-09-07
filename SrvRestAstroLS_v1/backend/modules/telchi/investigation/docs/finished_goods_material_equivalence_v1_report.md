# TELCHI SAP — FINISHED GOODS MATERIAL EQUIVALENCE V1

**Gate:** `TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_PASS`
**Date:** 2026-08-27
**HANA writes:** ZERO (READ ONLY)
**Domain:** COMPRAS / STOCK / EQUIVALENCIA (Gate 3 del roadmap)

---

## A. Resultado

**PASS** — El stock actual de producto terminado fue convertido a equivalentes
de materia prima, insumo y envase, con semántica de niveles, UOM, no doble
conteo y conservación por transferencias demostradas sobre datos reales.

---

## B. Semántica central

```
COMPONENT_EQUIVALENT_IN_FG = FG_STOCK_QTY × COMPONENT_QTY_PER_FG
```

- FG universe = producidos (`OWOR.Type='S'`): **896 ítems; 656 con stock**.
- Todo FG con stock tiene **historia de producción (IGN1) y BOM actual
  (ITT1.Father)** (0 sin BOM con stock; 6 sin BOM pero sin stock).
- **Niveles de equivalencia**:
  - `EXACT_PRODUCTION_LINEAGE`: UNAVAILABLE (SAP no conserva lineage unitario
    stock→orden; solo lote parcial vía U_LOTE/OBTN). No se inventa.
  - `HISTORICAL_PRODUCTION_EQUIVALENCE` (primario): `Σ(IGE1.Quantity) /
    Σ(IGN1.Quantity)` por (FG, componente) sobre órdenes reales → refleja
    consumo efectivo / producido efectivo (yield, merma, drift).
  - `CURRENT_BOM_EQUIVALENCE` (fallback): `ITT1.Quantity / OITT.Qauntity`
    (batch-normalizado; `ITT1.Uom` es NULL → UOM del componente desde
    `OITM.InvntryUom`).
  - `UNRESOLVED`: sin ratio ni BOM.

---

## C. Evidencia cuantitativa

| Métrica | Valor |
|---|---:|
| FG con stock (physical) | 656 ítems / 4.114 filas / 1.056.505 uds |
| FG usable (excl. damaged/expired/quarantine/WIP/raw/transit) | 869.600 uds |
| Líneas de equivalencia directa | 50.406 |
| Componentes directos | 1.249 (usable: 1.130) |
| Componentes terminales (multinivel expandido) | 1.109 |
| Componentes semi-elaborados (producidos) | 238 |
| Método HISTORICAL_PRODUCTION | primario (cubre todos los FG con stock) |

Distribución por rol (filas FG): BRANCH 1.979, FINISHED_GOOD 789, DAMAGED 377,
MOBILE 284, QUARANTINE 275, PRODUCTION 258, OTHER 56, RAW 43, DISPENSING 28,
CONSIGNMENT 18, TRANSIT 5, RETURNS 2. Damaged/quarantine/WIP se mantienen en
capa separada (no entran a equivalencia usable).

---

## D. Casos trazadores (equivalente en FG usable)

| Material | Equivalente directo | Equivalente terminal | FG principales |
|---|---:|---:|---|
| Soda cáustica 25kg | 5.445,6 kg | 5.511,2 kg | L01013 (1kg), L01015 (500g) |
| Cloruro de calcio 25kg | 44,0 kg | **9.226,2 kg** | L01822 (semi → multinivel) |
| Benzoato de sodio 25kg | 11.887,2 kg | 11.889,2 kg | L00504 (1kg) |
| Frasco gotero 30mL | 8.510,8 | 8.751,3 | L01086, L01072, L01601, L01041 |
| Tapa gotero | 8.570,5 | 8.811,1 | idem |
| Contra-tapa gotero | 8.342,1 | 8.582,6 | idem |

Lectura: cloruro de calcio demuestra **BOM multinivel** (consumido en el
semi-elaborado L01822, que a su vez entra en FG). La expansión terminal
reemplaza semi por sus materias primas sin doble conteo.

---

## E. Invariantes / no doble conteo

| Invariante | Resultado |
|---|---|
| FG transfer no crea material (mismo total global) | PASS (test + no-op) |
| Misma fila de stock contada una vez | PASS (grain ItemCode×WhsCode) |
| Multinivel: semi + raw NO se suman dos veces | PASS (test) |
| Componente compartido por varios FG agrega correctamente | PASS (test) |
| MP física NO mezclada con equivalente transformado | PASS (capas separadas) |
| UOM: no sumar entre UOM | GUARD + test |

---

## F. Anomalías / degradaciones

1. `EXACT_PRODUCTION_LINEAGE = unavailable` (degradado a histórico).
2. `CLORURO DE CALCIO` multinivel: directo 44 vs terminal 9.226 → requiere
   expansión para cobertura real (documentado).
3. FG en DAMAGED (377 filas) / QUARANTINE (275) / WIP (258) se excluyen de la
   capa usable; siguen en la capa física.
4. `ITT1.Uom` NULL → UOM resuelta desde `OITM.InvntryUom` (documentado).
5. Datos live (conteos pueden variar levemente entre ejecuciones).

---

## G. Tests

| Suite | Resultado |
|---|---|
| test_equivalence_domain (nuevo, unit) | 15 PASS |
| Regresión stock (20) + purchases (22) + production (65) + users (52) | 159 PASS |
| SQL contracts 4/4 ejecutan | PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## H. Artefactos

```
sql/current/equivalence/fg_stock_v1.sql
sql/current/equivalence/production_consumed_v1.sql
sql/current/equivalence/production_output_v1.sql
sql/current/equivalence/current_bom_v1.sql
validation/equivalence/equivalence_domain.py
validation/equivalence/finished_goods_material_equivalence_v1.py
validation/equivalence/test_equivalence_domain.py
docs/finished_goods_material_equivalence_v1_report.md
```

---

## I. Limitaciones

1. `EXACT_PRODUCTION_LINEAGE` no disponible (degradación explícita).
2. Ratio histórico agregado por FG-componente (no por lote/época); si existiera
   cambio estructural de receta con deriva material, Gate 4/épocas deberá
   segmentar (`RECIPE_EPOCH`).
3. Consignación/damaged/quarantine separados; no incorporados a cobertura.

---

## J. Próximo gate recomendado

`TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1` (Gate 4): capacidad máxima de
producción por componente y componente limitante, usando la posición física +
el equivalente ya transformado aquí cerrado.

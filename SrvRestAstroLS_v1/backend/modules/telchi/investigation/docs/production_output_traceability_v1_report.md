# TELCHI SAP — PRODUCTION OUTPUT TRACEABILITY V1

**Gate:** `TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## A. Resultado

**PASS** — El output real de producción fue reconstruido con evidencia
documental SAP: receipts, cantidad neta, CmpltQty, almacén, timing, lotes y
lineage.

---

## B. Cadena documental

```
OWOR (DocEntry)
  → OIGN (header: DocEntry, DocNum, DocDate, CANCELED)
      → IGN1 (BaseType=202, BaseEntry=OWOR.DocEntry, LineNum, ItemCode,
              Quantity, WhsCode, U_LOTE, U_VENCLOTE)
          → NET_ACTUAL_OUTPUT_QTY
          → OINM TT59 (reconciliación secundaria, parcial)
```

Confirmación: `EXACT_DOCUMENT_LINK` (BaseEntry).

---

## C. Actual Output Semantics — CERRADA

```text
NET_ACTUAL_OUTPUT_QTY = SUM(IGN1.Quantity) WHERE BaseType=202
```

Evidencia:
- OIGN.CANCELED: 100% 'N' (27,135 activos, **cero cancelados**)
- IGN1.Quantity: 100% positivo (21,007 líneas, **cero negativos**)
- No hay reversals de output en la población

---

## D. CmpltQty Semantics — CERRADA

| Comparación | Órdenes |
|-------------|--------:|
| `CmpltQty == SUM(IGN1)` | 19,654 |
| `CmpltQty != SUM(IGN1)` | **1** (order 17757, rework) |
| `Cmplt=0`, sin receipt | 832 |
| `Cmplt!=0`, sin receipt | 0 |

**Semántica**: `OWOR.CmpltQty = SUM(IGN1.Quantity)` — es el reflejo de las
recepciones. IGN1 es la fuente primaria; CmpltQty confirma.

---

## E. Receipt Cardinality

| Receipts por orden | Órdenes |
|--------------------|--------:|
| 0 | 842 |
| 1 | 19,588 |
| 2 | 104 |
| 3 | 42 |
| 4 | 83 |
| 5+ | 126 (hasta 22) |

Modelo 1:N soportado; 356 órdenes multi-receipt.

---

## F. Output vs Plan (mass validation, 20,487 órdenes)

| Clasificación | Órdenes | % |
|---------------|--------:|---|
| EXACT_PLANNED_OUTPUT | 17,799 | 86.9% |
| OVER_PLANNED_OUTPUT | 1,276 | 6.2% |
| PARTIAL_OUTPUT | 486 | 2.4% |
| ZERO_OUTPUT | 801 | 3.9% |
| CONSUMPTION_WITHOUT_OUTPUT | 31 | 0.15% |
| MULTIPLE_RECEIPTS (subclases) | 94 | 0.46% |

Consistente con el gate BOM (CmpltQty≈IGN1).

---

## G. Cancelaciones / Reversals

```text
CANCELED:  NOT OBSERVED (0 OIGN cancelados)
REVERSALS: NOT OBSERVED (0 IGN1 negativos)
NET_ACTUAL_OUTPUT_QTY = GROSS (sin ajustes)
```

---

## H. Product Identity — ItemCode

| Comparación | Líneas |
|-------------|-------:|
| `IGN1.ItemCode == OWOR.ItemCode` | 19,755 (94.0%) |
| `IGN1.ItemCode != OWOR.ItemCode` | 1,252 (6.0%) |

**Hallazgo**: los 1,252 mismatches reciben un ítem que ES un componente WOR1 de
la misma orden (1,254 líneas verificadas como componente de receta). Son
órdenes de **REWORK/reacondicionamiento** donde el output registrado es el
componente principal (ej. L01064 recibe L01945). Distribuidos 2022-2026
(persistente, no migración). Clasificación: `REWORK_PATTERN`.

---

## I. Warehouse Traceability

- Output ingresó principalmente en: LAB-P1 (proceso AGEMED, 8,340 órdenes),
  SAA-T1 (terminado Saavedra, 6,442), 2A-MAG (magistral, 2,478), SAA-P1 (1,770)
- **26 órdenes con output en múltiples almacenes** (preservado por warehouse)
- `OUTPUT_WAREHOUSE_OVERRIDE` aplicable cuando OWOR.Warehouse != IGN1.WhsCode

---

## J. Timing

| Receipt vs orden PostDate | Líneas |
|---------------------------|-------:|
| Same day | 10,909 (52%) |
| 1-7 días | 8,598 (41%) |
| 8-30 días | 1,340 |
| >30 días | 79 |
| **Negativo (backdating)** | **81** (0.4%) |

Los 81 negativos son **backdated receipts** (receipt fechada antes del PostDate,
diffs -27 a -364 días): órdenes creadas retroactivamente o migración.
`BACKDATED_RECEIPT` documentado, no filtrado.

---

## K. Batch Traceability

| Métrica | Valor |
|---------|-------|
| Líneas IGN1 BT=202 | 21,007 |
| Con `U_LOTE` | 8,709 (41.5%) |
| Lotes distintos | 5,228 |
| **Matcheados a `OBTN.DistNumber`** | **5,196 (99.4%)** |

Cadena: `IGN1.U_LOTE = OBTN.DistNumber` (EXACT). `U_VENCLOTE` = vencimiento.
Trazabilidad output→batch demostrada; genealogía raw→finished NO inferida
(limitación documentada).

---

## L. OINM Reconciliation (secundaria)

- `OINM TT59` vincula 10,675 de 19,944 BaseRef de IGN1 (53.5%)
- Cuando vincula, cantidades EXACT (1447=1447, etc.)
- IGN1 es la fuente primaria; OINM parcial NO bloquea (INVENTORY_LINK=PARTIAL
  ya documentado en discovery)

---

## M. Edge Cases

| Caso | Resultado |
|------|-----------|
| Rework (parent≠component) | 1,252 líneas, patrón REWORK real |
| Order 17757 | net=57.1429, cmplt=0 (diff único CmpltQty), rework |
| Backdated receipts | 81 (0.4%), no filtrado |
| Multi-warehouse | 26 órdenes |
| Zero output con consumo | 31 órdenes (candidato analítico, no pérdida) |

---

## N. Tests

| Suite | Resultado |
|-------|-----------|
| test_output_traceability_domain | 11 PASS |
| test_component_consumption_domain | 8 PASS |
| test_recipe_bom_domain | 12 PASS |
| Regresión users/attribution | 52 PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## O. Artefactos

```
validation/production/output_traceability_domain.py
validation/production/output_traceability_v1.py
validation/production/test_output_traceability_domain.py
docs/production_output_traceability_v1_report.md
```

---

## P. Limitaciones

1. `INVENTORY_LINK=PARTIAL`: OINM solo vincula 53.5% de receipts (por diseño
   de BASE_REF); IGN1 es la fuente primaria.
2. `SAME_DAY_ORDERING_UNRESOLVED`: sin hora confiable, la secuencia intra-day
   no siempre es determinable.
3. Genealogía de lotes raw→finished no disponible (solo output→batch).
4. Los 81 backdated receipts no se explican individualmente (retroactividad
   o migración); requieren validación de negocio si es material.

---

## Q. Próximo gate

`TELCHI_PRODUCTION_RECONCILIATION_V1`
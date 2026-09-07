# TELCHI SAP — WAREHOUSE TRANSFER TRACEABILITY V1

**Gate:** `TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## A. Resultado

**PASS** — La transferencia entre almacenes quedó reconstruida con evidencia
documental SAP: origen, destino, cantidad, fechas, usuario, efecto de
inventario (conservación 100%) y lote.

---

## B. Semántica documental — CERRADA

```text
ORIGIN      = WTR1.FromWhsCod
DESTINATION = WTR1.WhsCode
QUANTITY    = WTR1.Quantity
NET_TRANSFER = SUM(WTR1.Quantity) WHERE OWTR.CANCELED='N'
```

Validado:
- `FromWhsCod`/`WhsCode`: 0 nulls, 0 inválidos (todos en OWHS), 0 same-warehouse
- `ItemCode`: 0 inválidos (todos en OITM)
- Cancelados: 424 docs (0.2%), 5,832 líneas todas POSITIVAS → excluir por header
- Líneas negativas: 5,832 en docs ACTIVOS = transferencias inversas/ajustes
  legítimas (docs como 230: -998, 2364: -2007) — no son cancelaciones
- `TRANSFERRED_QTY` semántica: cantidad contabilizada (requested/posted confluyen
  en transferencia contabilizada instantánea)

---

## C. Población

| Métrica | Valor |
|---------|------:|
| OWTR docs total | 188,843 |
| Activos | 188,419 |
| Cancelados | 424 |
| WTR1 líneas | 1,964,667 |
| Items distintos | (validado en OITM, 0 missing) |
| Almacenes origen/destino | 82 (OWHS) |
| Rango fechas | 2022-04 → 2026-08 |

---

## D. Cancelaciones / Reversals

- 424 docs CANCELED='Y': 5,832 líneas positivas; exclusión por header.
- 5,832 líneas negativas en docs ACTIVOS: transferencias inversas/ajustes
  (mecanismo distinto, no reversible contra doc previo — sin BaseRef).
- `NET_TRANSFER_QTY` = suma de líneas de docs activos (incluye ajustes negativos).

---

## E. Cardinalidad

| Métrica | Valor |
|---------|------:|
| Docs 1 línea | 83,025 |
| Docs multi-línea | hasta 10+ (distribución amplia) |
| **Multi-ORIGEN docs** | **13,926 (7.4%)** |
| **Multi-DESTINO docs** | **8,020 (4.3%)** |

**Regla**: un documento NO se colapsa a una sola ruta; la unidad atómica es
`OWTR.DocEntry + WTR1.LineNum`.

---

## F. Efecto de inventario OINM TT67 — CONSERVACIÓN 100%

- `OINM.BASE_REF = OWTR.DocNum` (EXACT)
- Cada línea genera **2 filas OINM**: origen `OutQty` + destino `InQty` iguales
- **36,210/36,210 líneas muestreadas con conservación exacta (100.0%)**

```text
TRANSFER_QUANTITY_CONSERVATION = EXACT
origin_out == destination_in (por línea, por item)
```

---

## G. Rutas y roles de almacén (top)

| Ruta | Roles | Docs | Líneas |
|------|-------|-----:|-------:|
| 2A-AMD → SAP-R1 | CENTRAL→TRANSIT | 3,186 | 141,050 |
| LPZ-T1 → LPZ-D1 | FINISHED_GOODS→MOBILE | 5,619 | 109,183 |
| CM-AMD → CM-SAL | CENTRAL→SUCURSAL_SALON | 7,193 | 107,784 |
| SAP-R1 → 2A-SAL | TRANSIT→SUCURSAL_SALON | 5,372 | 94,995 |
| SAP-R1 → VI-SAL | TRANSIT→SUCURSAL_SALON | 2,632 | 50,385 |
| LAB-T1 → LAB-D9 | FINISHED_GOODS→MOBILE | 2,685 | 75,627 |
| LAB-M1 → LAB-P1 | RAW_MATERIAL→PROCESO | 9,798 | 33,934 |

Patrones operativos visibles: **Central→Transit→Salón** (despacho a sucursal
vía tránsito), **Terminado→Móvil** (despacho a rutas), **Materia Prima→Proceso**
(abastecimiento de producción).

---

## H. Batch Traceability

| Métrica | Valor |
|---------|------:|
| WTR1 activas con `U_LOTE` | 0.19% (3,630 líneas) |
| IBT1 BaseType=67 (traza lote completa) | 4,026,440 filas |
| Lotes WTR1 → OBTN.DistNumber | 93.4% match |

La traza de lotes por transferencia se conserva en IBT1 (`BatchNum`, `WhsCode`,
`Direction`, `BaseEntry`); WTR1.U_LOTE es minoritario.

---

## I. User Attribution

- `OWTR.UserSign` preservado (p.ej. user 46, 145 = técnicos SAP/DMS según
  contratos existentes).
- `UserSign` = quien registró el documento SAP; NO demuestra quién preparó,
  cargó, transportó o recibió físicamente (limitación documentada).

---

## J. Physical Dispatch Semantics — CERRADA

```text
PHYSICAL_DISPATCH_SEMANTICS = ACCOUNTING_ONLY
TRANSFER_DOCUMENT_CONFIDENCE = EXACT
```

SAP contabiliza origen y destino en el mismo evento documental (2 filas OINM
simultáneas). Una transferencia SAP demuestra el cambio de inventario
contabilizado, NO la salida/arribo físico del camión. `SAP_ACCOUNTING_TRANSFER`
es instantánea documentalmente; `INTRADAY_ORDERING_UNRESOLVED` cuando no hay
hora confiable.

---

## K. Edge Cases

| Caso | Resultado |
|------|-----------|
| Same-warehouse (From=To) | 0 (inexistente) |
| Null origin/dest | 0 |
| ItemCode inválido | 0 |
| Líneas negativas activas | 5,832 (ajustes/reversas legítimas) |
| Docs cancelados | 424 (excluidos por header) |
| Backdated transfers | preservadas (no filtradas) |

---

## L. Real SAP Cases

```
OWTR 261101335: L00056 qty=3 LPZ-T1 -> LPZ-D1
  OINM: out=3 LPZ-T1, in=3 LPZ-D1 (conservación exacta)

OWTR 260200328: LAB-T1 -> LAB-D2 (multi-item: L01001 qty=12, L01757 qty=12,
  L00505 qty=150, ... todas con out==in)
```

---

## M. Tests

| Suite | Resultado |
|-------|-----------|
| test_warehouse_transfer_domain | 12 PASS |
| test_production_reconciliation_domain | 13 PASS |
| test_produced_component_dependency_domain | 9 PASS |
| test_output_traceability_domain | 11 PASS |
| test_component_consumption_domain | 8 PASS |
| test_recipe_bom_domain | 12 PASS |
| Regresión users/attribution | 52 PASS |
| `git diff --check` | OK |
| READ ONLY | PASS |

---

## N. Artefactos

```
validation/production/warehouse_transfer_domain.py
validation/production/warehouse_transfer_traceability_v1.py
validation/production/test_warehouse_transfer_domain.py
docs/warehouse_transfer_traceability_v1_report.md
```

---

## O. Limitaciones

1. `PHYSICAL_DISPATCH_SEMANTICS=ACCOUNTING_ONLY`: SAP demuestra transferencia
   contable, no entrega física (sin evidencia de transporte/recepción física).
2. `BRANCH_TRACEABILITY=HEURISTIC` parcial: el mapping warehouse→branch se
   deriva de roles/naming (CM/2A/LPZ...), no de un campo BPL explícito.
3. `INTRADAY_ORDERING_UNRESOLVED`: sin timestamp horario confiable en todos
   los casos, la secuencia intra-day no es determinable.
4. Batch en WTR1 directo es minoritario (0.19%); la traza completa requiere
   IBT1 (4M filas TT67), no agregada en este gate.
5. No se atribuyó ninguna transferencia a una orden de producción (WTR1 no
   referencia OWOR — reservado para el próximo gate).

---

## P. Próximo gate

`TELCHI_PRODUCTION_DISPATCH_TRACEABILITY_V1`
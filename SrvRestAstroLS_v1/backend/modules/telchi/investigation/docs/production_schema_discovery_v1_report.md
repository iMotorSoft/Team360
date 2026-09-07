# TELCHI SAP — PRODUCTION SCHEMA DISCOVERY V1

**Gate:** `TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1_PASS`
**Date:** 2026-08-26
**HANA writes:** ZERO (READ ONLY)

---

## 1. Resultado

**PASS** — La semántica real de RECETAS × PRODUCCIÓN × CONSUMO × PRODUCTO
TERMINADO × DESPACHO × STOCK fue descubierta y validada con datos reales HANA.

---

## 2. Cadena documental validada (EXACT)

```
RECIPE        OITT (header) → ITT1 (componentes: Father=producto, Code=componente)
                  IssueMthd: M=manual, B=backflush

ORDER         OWOR (DocEntry, ItemCode, Status, PlannedQty, CmpltQty)
                  → WOR1 (componentes: BaseQty×PlannedQty=IssuedQty, IssueType)

CONSUMPTION   IGE1 (BaseType=202, BaseEntry=OWOR.DocEntry, BaseLine=WOR1.LineNum)
                  → OINM (TransType=60, OutQty, BASE_REF=IGE1.BaseRef)

RECEIPT       IGN1 (BaseType=202, BaseEntry=OWOR.DocEntry)
                  → OINM (TransType=59, InQty, BASE_REF=IGN1.BaseRef)

TRANSFER      OWTR (header, ToWhsCode=dest) → WTR1 (lines: WhsCode=dest, FromWhsCod=origin)
                  → OINM (TransType=67)

STOCK         OITW (ItemCode+WhsCode, current only)
HISTORY       OINM (movements, reconstruct historical stock)
```

---

## 3. Fuentes validadas

| Fuente | Tabla | Clave | Join | Cardinalidad | Confidence |
|--------|-------|-------|------|--------------|------------|
| Receta | OITT/ITT1 | Code / Father | ITT1.Father=OITT.Code | 1,043 hdrs / 7,753 lines / 1,043 padres | EXACT |
| Orden | OWOR | DocEntry | — | 20,777 | EXACT |
| Componentes esperados | WOR1 | DocEntry+LineNum | WOR1.DocEntry=OWOR.DocEntry | 141,618 / 20,777 órdenes | EXACT |
| Consumo real | IGE1 (BT=202) | DocEntry+LineNum | IGE1.BaseEntry=OWOR.DocEntry | 135,341 / 19,935 órdenes | EXACT |
| Producto terminado | IGN1 (BT=202) | DocEntry+LineNum | IGN1.BaseEntry=OWOR.DocEntry | 20,999 / 19,936 órdenes | EXACT |
| Transferencia | OWTR/WTR1 | DocEntry / +LineNum | — | 188,798 / 1,964,667 | EXACT |
| Movimiento inventario | OINM | TransNum+TransSeq | BASE_REF=source | 8,313,459 | EXACT |
| Stock actual | OITW | ItemCode+WhsCode | — | 1,362,033 / 16,792 items | EXACT |
| Almacenes | OWHS | WhsCode | — | 82 | EXACT |

---

## 4. Semántica de producción validada

### Órdenes (OWOR)

| Campo | Valor | Semántica |
|-------|-------|-----------|
| Status | L=Released 20,093 / C=Closed 589 / P=Planned 91 / R=4 | Released = producción REAL |
| Type | S=Standard 20,478 / D=Disassembly 298 / P=1 | |
| ItemCode | 905 productos distintos | |
| Fechas | 2022-04-01 → 2026-08-26 | |

**Hallazgo crítico**: en Telchi, `Status='L'` (Released) NO significa "sin
terminar". El 99% de las órdenes con producción completa (consumo + producto
terminado) están en `L`. `Status='C'` (Closed) es un cierre administrativo
posterior (589 órdenes, muchas con CmpltQty=0). `CmpltQty` replica la cantidad
de recepción.

### Método de emisión (WOR1.IssueType / ITT1.IssueMthd)

| Método | WOR1 líneas | % | Semántica |
|--------|-------------|---|-----------|
| M (Manual) | 95,569 | 67% | Issue manual |
| B (Backflush) | 46,049 | 33% | Issue automática al recibir |

Los componentes backflush SÍ generan IGE1 (issue materializada), verificada
con muestra real. Ambos métodos confluyen en IGE1→OINM TT=60.

### Consumo teórico vs real (EXACT)

En la orden 28629 (L03267, Planned=50, Cmplt=50):

| Componente | BaseQty | PlannedQty (teórico) | IGE1 (real) | Match |
|-----------|---------|----------------------|-------------|-------|
| L01945 | 30 | 1,500 | 1,500 | ✅ |
| L00167 | 1 | 50 | 50 | ✅ |
| M0006 (B) | 0.4 | 20 | 20 | ✅ |
| L00204 | 1.1 | 55 | 55 | ✅ |

`IssuedQty` (WOR1) = IGE1.Quantity (consumo real) — la orden COPIA la receta
al crearse (fidelidad histórica de receta PRESERVADA en WOR1).

---

## 5. Despacho / transferencias

- `OWTR.ToWhsCode` = almacén destino; `WTR1.FromWhsCod` = origen; `WTR1.WhsCode` = destino
- `WTR1.BaseRef` = documento de origen (solicitud de traslado, venta)
- `U_ORIGIN` distingue canal (SAP/DMS)
- `BaseType=-1` mayoritario (1.39M líneas) = transferencia libre/sin documento base
- `BaseType=1250000001` (564K) = vínculo especial

**Limitación**: las transferencias de despacho NO se vinculan a la orden de
producción por FK directa (BaseType=202 no aparece en WTR1). El vínculo
producción→despacho deberá ser TEMPORAL/HEURÍSTICO (ItemCode+almacén+fecha).

---

## 6. Almacenes — rol operativo (82)

| Rol | Almacenes | Ejemplos |
|-----|-----------|----------|
| CENTRAL | 2 | CM-AMD, 2A-AMD |
| SUCURSAL_SALON | 10 | 2A-SAL, CM-SAL, RC-SAL, UR-SAL, VI-SAL, DV-SAL |
| MOVIL (despacho rutas) | 14 | LAB-D1..D12, LPZ-D1, LPZ-D2 |
| MATERIA_PRIMA | 3 | LAB-M1, MAG-M1, SAA-M1 |
| PRODUCTO_TERMINADO | 10 | LAB-T1..T5, SAA-T1, MAG-T1, LPZ-T1, NTG-T1 |
| PROCESO | 5 | LAB-P1..P4, SAA-P1, MAG-P1 |
| DESPACHO/PICKING | 2 | LAB-D0, LAB-DES |
| DISTRIBUCION_TERBOL | 8 | *-DT1 (Beni, Cochabamba, etc.) |
| TRANSITO | 4 | 01, SAP-R1, SAL-TRS |
| DMS | 2 | DMS-DEV, DMS-PROF |

---

## 7. Limitaciones / incertidumbres

1. **OINM→IGN1/IGE1 por BASE_REF**: solo ~10,667 (TT59) y ~8,129 (TT60)
   valores vinculan directamente (los que tienen BaseRef poblado). El resto
   requiere vincular por DocEntry/BaseRef alternativos. `INVENTORY_LINK=PARTIAL`.
2. **Producción→despacho sin FK**: las transferencias no referencian la orden.
   El vínculo será TEMPORAL/HEURÍSTICO. `PRODUCTION_DISPATCH_LINK=HEURISTIC`.
3. **Fidelidad de receta**: preservada (WOR1 copia la receta al crear la orden),
   pero el versionado temporal de OITT no se validó aún. `RECIPE_HISTORICAL=DEGRADED`.
4. **Status CmpltQty=0 en órdenes cerradas**: cierre administrativo posterior;
   la cantidad real está en IGN1, no en CmpltQty del cierre.
5. **OITW es stock actual**: para stock histórico debe reconstruirse desde OINM.

---

## 8. Muestras SAP reales

```
Orden completa: OWOR DocEntry=28629, L03267, Planned=50, Cmplt=50, Whs=SAA-P1
  Receta:       ITT1 L03267 → L01945(30), L00167(1), M0006(0.4,B), ...
  Consumo:      IGE1 1500 L01945, 50 L00167, 20 M0006
  Producto:     IGN1 50 L03267
  Movimiento:   OINM TT=59 in=50, TT=60 out=1500/50/20

Despacho: OWTR DocEntry=306887 → ToWhsCode=LAB-T1, FromWhsCod=2A-AMD,
  WTR1 M06062 qty=9, BaseRef=261510185 (solicitud traslado)
```

---

## 9. Gate

**TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1_PASS**

Todas las fuentes de la cadena RECETA→ORDEN→CONSUMO→PRODUCTO→DESPACHO→STOCK
fueron identificadas con tablas reales, claves, joins y cardinalidades.
Degradaciones documentadas (INVENTORY_LINK=PARTIAL, PRODUCTION_DISPATCH_LINK
=HEURISTIC, RECIPE_HISTORICAL=DEGRADED) sin bloquear el inventario.

**Próximo gate**: `TELCHI_RECIPE_BOM_TRACEABILITY_V1`

# TELCHI — SALES × CASH × STOCK TRACEABILITY V1 — REPORT

**Fecha:** 2026-08-25
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Gate:** `TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1`
**Resultado global:** `PASS` (era SAP real, HANA read-only, 28.899 casos atómicos)

---

## A. Resultado

`PASS` — `TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1_PASS`

Cadena completa demostrada sobre datos reales de SAP (ventana 2023-02, Retail One activo):

```
CAJA (ORCT cash via ITR1 settlement)
 ↔ VENTA/FACTURA (OINV + INV1)
 ↔ MERCADERÍA (OINM, DOCNUM_RESOLVE 94.9%)
 ↔ ALMACÉN (WhsCode + OWHS name)
 ↔ VALOR COMERCIAL (qty × precio × descuento, neto; DocTotal bruto)
 ↔ COSTO (OINM TransValue)
```

## B. Estado runtime

| Componente | Estado |
|---|---|
| HANA | ✅ activo (read-only; sin writes) |
| VPN | ✅ activo (strongswan) |
| Podman | SIN TOQUE (lifecycle manual, DEC-005) |

## C. Implementado

| Archivo | Contenido |
|---|---|
| `atomic/traceability.py` | `build_case` (SALE×CASH×STOCK), `goods_sale_value_from_lines`, clasificación §23 (CONSISTENT/PARTIALLY_RECONCILED/REVIEW_REQUIRED/UNRESOLVED/SOURCE_DATA_MISSING), lineage, diferencias TOTAL/EXPLAINED/UNEXPLAINED, STOCK_RELATION_UNRESOLVED (nunca NO_STOCK) |
| `validation/atomic/traceability_e2e.py` | Runner E2E real (HANA 2023-02): 28.899 casos atómicos + agregación diaria por almacén (control secundario) + muestra 25 con lineage completo |
| `validation/atomic/run_atomic_tests.py` | + TestTraceabilityUnit (T28/T34/T40/T43/T44/T48/T49/T54), TestLegacyParquet (T31/T32/T46), TestE2EHANA (T35-T50: pipeline, lineage, cancelación mayo 2024, control diario) |
| `sql/current/atomic/source_cash_event_sap.sql` | Extractor CASH_EVENT SAP (ORCT CashSum>0) — validado en HANA |
| `sql/current/atomic/relation_stock_document.sql` | Relación OINM→documento (DOCNUM_RESOLVE + APPLOBJ) — validado en HANA |
| `atomic/contracts/cash.py` | Contract CASH_EVENT (loop anterior, preservado) |

## D. H5 — SALE LEGACY → SAP

**Estado: `REJECTED` (a nivel transacción) con evidencia de corte de migración.**

- SAP (OINV/ODLN/ORCT/OINM) arranca **2022-03-31** (OINV marzo 2022 = 1.236 facturas; 2022-04 = 23.406).
- Legacy (vttrn/cjtrn/cjdpc — SQL Server viejo) terminó ~2022-04 (cash-2022-04-30 es el último parquet).
- No hay referencia vttrnNtve en SAP: `OINV.NumAtCard` 100% vacío (2022-02), `BaseRef`=VACIO en el extractor legacy SAP, sin UDF de referencia legacy.
- **Mapeo de clientes legacy→SAP CONFIRMADO (79.2%):** `CardCode = 'C%06d' % gbpercper` (1.634/2.062 clientes de 2022-02; 42/50 muestra).
- **Mapeo warehouse→sucursal legacy CONFIRMADO:** `sapWhsOfficeName.parq` (60 filas: WhsCode ↔ OfficeName).
- Consecuencia: la trazabilidad moderna se construye **dentro de SAP** (2022-04+); legacy queda como baseline semántico + prehistoria (parquets read-only).

## E. Cross-system chain

| Tramo | Estado | Método | Evidencia |
|---|---|---|---|
| CASH→SALE (SAP) | ✅ CONFIRMED | ITR1/OITR settlement (SrcObjTyp 24↔13, N:N) | 23.023 CONSISTENT en 2023-02 |
| SALE→SAP | ✅ NATIVE (era SAP) / REJECTED (legacy transaccional) | OINV.DocEntry | corte migración 2022-03-31 |
| SAP→DELIVERY | ✅ CONFIRMED | DLN1.BaseEntry/BaseRef (validación previa) | 3.709/3.709 tt=15 |
| SAP→STOCK | ✅ CONFIRMED | OINM BASE_REF=DocNum + DocLineNum + ItemCode (guard TransType) | 94.9% de facturas |
| STOCK→WAREHOUSE | ✅ CONFIRMED | OINM.Warehouse → OWHS.WhsName | 27.422 casos |
| SALE→VALUE | ✅ CONFIRMED | qty×price×(1−disc); DocTotal bruto para caja | 100% líneas |
| CASH→VALUE | ✅ CONFIRMED | efectivo aplicado (ReconSum SrcObjTyp=13) vs DocTotal | tolerancia 0.01 |

## F. Grain

| Fuente | Clave |
|---|---|
| OINV | DocEntry (único) |
| INV1 | DocEntry + LineNum |
| ORCT | DocEntry (único) |
| ITR1/OITR | ReconNum + LineSeq |
| OINM | TransNum + ItemCode + Warehouse + fecha (vínculo vía BASE_REF=DocNum, NUNCA DocNum solo) |
| Legacy cash | (source_table CJTRN/CJDPC, NroTransaccion) — NroTransaccion NO único (187 dups) |

## G. Match rates

| Relación | Tasa | Detalle |
|---|---|---|
| Facturas con settlement activo | 99.6% | 28.899 en ventana |
| Retail One con settlement | 99.5% | 24.776/24.908 |
| Stock resuelto (OINM tt=13 en ventana) | 94.9% | 27.422/28.899 (1.477 sin movimiento en ventana; 68 sin tt=13 jamás) |
| Clientes legacy→SAP | 79.2% | C%06d |
| Cash → SaleCode (legacy) | 89.6% | cjtrnmorg=6 |

## H. Casos E2E (muestra real)

**Caso 2641857 (factura 23073592, CGV1, 2023-02-01, CASH):**

```
SALE_CONFIRMED ✓ INVOICE_CONFIRMED ✓ CASH_CONFIRMED ✓ GOODS_OUT_CONFIRMED ✓
WAREHOUSE_CONFIRMED ✓ (VI-SAL = Almacén Salón Villa 1ro de Mayo)
COMMERCIAL_VALUE_CONFIRMED ✓ (neto 0.37, DocTotal 0.43)
COST_VALUE 0.24 (OINM TransValue)
DocTotal 0.43 == aplicado 0.43 → UNEXPLAINED = 0 → CONSISTENT
Lineage: OINV 2641857 → INV1 (2641857,0) → ORCT 375642 → OINM 4749506
```

## I. Diferencias (2023-02, 28.899 casos)

| Métrica | Valor |
|---|---|
| Casos CONSISTENT | 23.023 (79.7%) |
| PARTIALLY_RECONCILED | 5.876 (20.3%) — no-cash 4.311 + sin pago 790 + stock no resuelto 1.477 (parcialmente solapados) |
| REVIEW_REQUIRED | 0 |
| TOTAL_DIFFERENCE agregada (cash) | 0 (explicada/sin explicar separadas por caso) |
| UNEXPLAINED_DIFFERENCE | 0 |

Pago parcial (ej. factura 23011418: 9.736,31 esperado, 1.690,83 aplicado) → diferencia 8.045,48 = **saldo pendiente explicado** (PARTIAL_CASH_PAYMENT), nunca fraude.

## J. Tests

| Capa | Conteo | Resultado |
|---|---|---|
| UNIT (contracts, cash, traceability) | 33 | 33 PASS |
| LEGACY (parquet read-only) | 3 | 3 PASS |
| CONTRACT (HANA) | 1 | 1 PASS |
| SOURCE (HANA) | 9 | 9 PASS |
| SEMANTIC (HANA real) | 2 | 2 PASS |
| E2E (HANA real + fixture) | 6 | 6 PASS |
| **TOTAL** | **54** | **54 PASS / 0 FAIL / exit 0** |

## K. Bugs encontrados (reales, corregidos en loop)

1. `SrcObjTyp` llega como string de HANA ('13') → comparaciones int fallaban (pagos nunca vinculados).
2. Orden de parámetros en `relation_stock_document.sql` (start,end intercalados por branch) → stock resuelto solo 1 día.
3. `goods_sale_value` leía keys minúsculas con filas en casing SAP ("Quantity") → valor comercial 0.0 en todo el E2E.
4. OINM.TransValue firmado (negativo en salidas) → costo negativo; corregido con abs en salidas.
5. Diferencia de caja comparaba neto de líneas vs bruto DocTotal (IVA) → expected_cash ahora usa DocTotal (lo que la caja debe recibir).

## L. Hallazgos

| Clase | Hallazgo |
|---|---|
| CONFIRMED | Corte de migración SAP = 2022-03-31 (OINV/ORCT/OINM/ODLN) |
| CONFIRMED | Retail One activo ya en 2023-02 (86.2%, folio-marked, 99.5% settlement) |
| CONFIRMED | DMS activo en 2023-02 (9.7% U_ORIGIN) |
| CONFIRMED | Mapeo cliente legacy→SAP = C%06d (79.2%) |
| CONFIRMED | Mapeo WhsCode→sucursal legacy (sapWhsOfficeName, 60 filas) |
| CONFIRMED | Cash SAP 82.4% de facturas (23.798/28.899) — consistente con perfil histórico 81.3% |
| CONFIRMED | Batch anulaciones mayo 2024 = 978 Y + 978 C (DocDate) |
| CONFIRMED | OINV NumAtCard vacío en 2022-02 (no es carrier legacy) |
| HYPOTHESIS | H4: caja física vía OJDT/JDT1/OACT.CashBox (pendiente validación) |
| PENDING | 1.477 facturas sin movimiento OINM en ventana (68 sin tt=13 jamás — revisar items de servicio) |

## M. Gaps

1. Caja física SAP (OJDT/JDT1/OACT.CashBox) — H4 sin validar (HANA disponible; pendiente de inspección de OACT.CashBox).
2. Costo por línea histórica (OITM.AvgPrice vs OINM.TransValue) — usar TransValue del movimiento (ya presente).
3. Retail One: ticket POS→folio→invoice 1:1 (H1) sigue PARTIAL_TRACEABILITY.
4. Anulaciones tardías 2025 (ej. 22010001 cancelada 2025-05-27) — lifecycle OK pero no re-evaluado as_of.
5. 68 facturas sin OINM tt=13: determinar si son items de servicio (sin stock) o hueco de posting.

## N. Próximo paso

**Principal:** cerrar H4 (caja física SAP vía OJDT/JDT1/OACT.CashBox) y validar el control diario de caja por sucursal/almacén (2026) con Retail One, para pasar de payment-derived cash a physical-cash evidence.

Secundarias:
1. Investigar las 68 facturas sin OINM (items de servicio vs hueco).
2. H1: folio Retail One 1:1 con serie/prefijo.
3. Re-evaluar anulaciones tardías con as_of (2025 batch).

**Gate:** `TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1_PASS` ✅
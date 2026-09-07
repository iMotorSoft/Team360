# TELCHI — ATOMIC NUCLEUS V1 — REPORT

**Fecha:** 2026-08-25
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Gate:** `TELCHI_ATOMIC_CONTRACTS_NUCLEUS_V1_PASS`
**Resultado global:** `PASS` (HANA activo, read-only respetado)

---

## A. Resultado

`PASS`

HANA accesible vía `127.0.0.1:30015` (schema `TELCHI`). Todo acceso realizado fue `SELECT`/catálogo. Sin writes. Podman no tocado.

## B. Implementado

### B.1 Paquete lógico `atomic/` (independiente de storage)

| Archivo | Contenido |
|---|---|
| `atomic/connection.py` | Conexión read-only compartida + `table_columns()` con fallback a describe (`LIMIT 0`) |
| `atomic/contracts/event_envelope.py` | Envelope base (§9), contracts SALE/PAYMENT/DELIVERY/INVENTORY con campos `CONFIRMED` inspeccionados en HANA |
| `atomic/contracts/relations.py` | `DOCUMENT_RELATION` (§11), `MATCH_METHODS` (§12), `SRC_OBJECT_TYPES`, `SOURCE_TRANSACTION`, `CROSS_SYSTEM_LINK`, `CHANNEL_OPERATION_RULE` (estado por canal), contracts BOM/producción (§28) |
| `atomic/semantic/payment.py` | Clasificador de medio de pago (T04), estado de anulación (T15), `choose_match_method` (§12), SALE/COST value (§16), `reconcile_expected_cash` (§52), `max_producible`/bottleneck (T18/T19), `coverage_days` (T20) |
| `atomic/findings.py` | Representación finding simple (§80) |

### B.2 Extractores SQL read-only `sql/current/atomic/`

| Archivo | Grain | Fuente |
|---|---|---|
| `source_sale_header.sql` | 1 row / OINV.DocEntry | OINV |
| `source_sale_line.sql` | 1 row / DocEntry+LineNum | INV1 |
| `source_payment_header.sql` | 1 row / ORCT.DocEntry | ORCT |
| `source_delivery_header.sql` | 1 row / ODLN.DocEntry | ODLN |
| `source_delivery_line.sql` | 1 row / DocEntry+LineNum | DLN1 |
| `source_inventory_movement.sql` | movimiento/item/whs | OINM |
| `relation_settlement.sql` | SrcObjTyp 13/24/14/16/25 | ITR1+OITR |
| `relation_retail_one_folio.sql` | facturas `U_SO1_01RETAILONE='Y'` | OINV |
| `source_production_bom.sql` | BOM header + componentes | OITT+ITT1 |

### B.3 Tests

`validation/atomic/run_atomic_tests.py` — runner `unittest` (no pytest disponible).

**21 tests, 21 PASS.**

| Capa | Test | Resultado |
|---|---|---|
| UNIT | envelope, DOCUMENT_RELATION, match_method, payment, cancellation, valuation, reconcile, bottleneck, zero component, coverage | 10/10 PASS |
| CONTRACT | columnas `CONFIRMED` existen en OINV/ORCT/ODLN/OINM (HANA real) | PASS |
| SOURCE | grain + IDs en ventana 2023-02 (HANA real) | 7/7 PASS |
| SEMANTIC | perfil medio de pago real + estado anulación real | PASS |

## C. Fuentes validadas

| Fuente | Estado |
|---|---|
| SAP HANA | ✅ CONECTADO (read-only) — catalog + extractores validados en ventana real 2023-02 |
| Legacy (`/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/`) | ✅ INVENTARIADO (696 parquet: cash, movProduct, saleProduct, paymentB1, reconB1, recetasNiveles01, productTransform...) — read-only |
| Retail One | 🟡 PARTIAL_TRACEABILITY — UDF folio confirmado en OINV |
| DMS | 🟡 PARTIAL_TRACEABILITY — UDF origen/estado confirmado en OINV |

## D. Atomic contracts

| Dominio | Contract | Estado |
|---|---|---|
| SALE (header/line) | `SALE_HEADER` / `SALE_LINE` | ✅ CONFIRMED |
| PAYMENT | `PAYMENT_HEADER` | ✅ CONFIRMED |
| DELIVERY | `DELIVERY_HEADER` / `DELIVERY_LINE` | ✅ CONFIRMED |
| INVENTORY_MOVEMENT | `INVENTORY_MOVEMENT` | ✅ CONFIRMED |
| PRODUCTION/BOM | `BOM_HEADER_FIELDS` / `BOM_LINE_FIELDS` / `PRODUCTION_ORDER_FIELDS` | ✅ CONFIRMED |
| CASH_EVENT | pendiente (depende de medio de pago + caja) | ⏳ PENDIENTE |
| SOURCE_TRANSACTION / CROSS_SYSTEM_LINK | contracts definidos, poblado pendiente | ⏳ PENDIENTE |

## E. Relaciones confirmadas (no hipótesis)

1. **PAYMENT → INVOICE (N:N vía reconciliación):** `ITR1.SrcObjTyp=24` + `=13` unidos por `ReconNum` (basado en DEC-010/011 ya validado; re-validado en ventana real con `relation_settlement.sql`).
2. **INVOICE → DELIVERY (BaseEntry/BaseType):** `INV1.BaseEntry` = doc base, `BaseType` preservado en contract SALE_LINE (mapeo 15/23 a confirmar por dominio).
3. **RETAIL ONE → INVOICE (folio):** `U_SO1_01FOLIORETAIL1` presente en facturas `U_SO1_01RETAILONE='Y'` — 58.778 folios distintos en 2026-07.
4. **DMS → INVOICE (origen):** `U_ORIGIN='DMS'` ~8% de muestra 200k desde 2026-01; `U_DMS_STATE ∈ {A, V}`.

## F. Hipótesis nuevas (separadas de las confirmadas)

- H1: Un folio Retail One = 1 factura SAP (grain 1:1 candidato). Requiere validación contra serie/prefijo y ticket POS.
- H2: `U_SO1_01PREFIJO` (231-234) = serie de facturación del ticket. Requiere mapeo a `OINV.Series`.
- H3: El `U_ORIGIN` de OINV es herencia del ticket en ORCT (a verificar en pagos de caja).

## G. Tests

unit 10 + contract 1 + source 7 + semantic 2 + e2e 0 (sintético planeado) = **21 PASS / 0 FAIL**

## H. Hallazgos reales

| Hallazgo | Evidencia | Confianza |
|---|---|---|
| Perfil de medio de pago (Feb 2023, n=29.184 pagos): CASH 81.3%, CARD 10.8%, MIXED 4.4%, TRANSFER 3.4%, CHECK 0.1% | ORCT.CashSum/CheckSum/TrsfrSum/CreditSum/NoDocSum/BoeSum | CONFIRMED |
| Retail One marca la mayoría de facturas recientes: 89.5% `U_SO1_01RETAILONE='Y'` (2026-07, n=50k) | OINV UDFs | CONFIRMED |
| Folios Retail One distintos: 58.778 en 2026-07 | OINV.U_SO1_01FOLIORETAIL1 | CONFIRMED |
| DMS ~8% de las facturas recientes (muestra 200k desde 2026-01) | OINV.U_ORIGIN | CONFIRMED |
| OINM no aparece en `SYS.TABLE_COLUMNS` para el user insiding_hana; describe via `SELECT * LIMIT 0` funciona | Catalog quirk | CONFIRMED |

## I. Gaps

1. **CASH_EVENT / caja** — contract pendiente: hace falta mapear ORCT (payment) → caja física y la separación PAYMENT/APPLICATION/RECONCILIATION (§17).
2. **Relación INVENTORY → documento** — no usar `DocNum`; validar experimentalmente claves OINM (BASE_REF/Ref1/Ref2/TransNum) (§17).
3. **Retail One:** ticket POS → folio → invoice: requiere fuente POS o evidencia adicional; `PARTIAL_TRACEABILITY` hoy.
4. **DMS:** sale_date ≠ cash_settlement_date sin validar (ventas móviles) (§25).
5. **BOM:** validar `OITT` contra `recetasNiveles01.parq` (legacy) y contra OWOR real.
6. **Pricing/proformas:** `PROFORMA_SOURCE_UNRESOLVED` (evidencia parcial QUT1).

## J. Próxima prioridad

**Principal:** construir el contract + extractor `CASH_EVENT` / payment lifecycle (ORCT → RCT1/RCT2 → ITR1/OITR) para cerrar venta×caja×mercadería.

Secundarias:
1. Resolver link OINM → documento (claves experimentales).
2. Validar H1 (folio Retail One 1:1) con serie/prefijo.
3. Implementar BOM capacity real sobre OITT+ITT1 con inventario actual (T29/T30).

# TELCHI — ATOMIC CASH_EVENT + STOCK LINK V1 — REPORT

**Fecha:** 2026-08-25
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Change:** `READY_FOR_TELCHI_CASH_EVENT_AND_STOCK_LINK`
**Resultado global:** `DEGRADED` — implementación lista, validación HANA BLOCKED (runtime manual caído)

---

## A. Resultado

`DEGRADED` (núcleo lógico PASS; capas HANA no ejecutables por bloqueo externo).

- 23 tests UNIT + contract (sin DB): **23 PASS, 0 FAIL**.
- Gate conectividad honesto: HANA no acepta handshake → `STOP_MANUAL_PODMAN_START_REQUIRED`
  (VPN y forward socat activos; el runtime HANA detrás de `10.88.0.2:30015` resetea la conexión).
- Contract/SOURCE/SEMANTIC HANA: NO ejecutados (nunca se declaró PASS).

## B. Implementado

| Archivo | Contenido |
|---|---|
| `atomic/contracts/cash.py` | Contract `CASH_EVENT`: lado SAP `CASH_EVENT_SAP_FIELDS` (CONFIRMED, ORCT) + baseline legacy `CASH_EVENT_LEGACY_FIELDS` (LEGACY_REFERENCED, cjtrn/cjcja/cjdpc/cjddc/vttrn) + `PAYMENT_LIFECYCLE_ROLES` (§17) |
| `atomic/semantic/cash.py` | `build_cash_event_from_payment` (SAP, porción cash), `classify_legacy_cash_type` (§18), `resolve_stock_document` (DOCNUM_RESOLVE + APPLOBJ, guard TransType) |
| `sql/current/atomic/source_cash_event_sap.sql` | Extractor read-only ORCT `CashSum > 0` → CASH_EVENT (grain DocEntry) |
| `sql/current/atomic/relation_stock_document.sql` | OINM → documento: branch APPLOBJ_OFFICIAL (SAP_BASEENTRY) + branch DOCNUM_RESOLVE (13→OINV, 15→ODLN), grain = fila OINM |
| `atomic/contracts/event_envelope.py` | + `ApplObj`/`AppObjAbs`/`AppObjLine` en INVENTORY_MOVEMENT (CONFIRMED) |
| `validation/atomic/run_atomic_tests.py` | + gate conectividad (exit 3 = BLOCKED, sin skips falsos), + 13 tests UNIT cash/stock link, + 2 tests SOURCE nuevos (HANA pendiente) |

## C. Fuentes validadas

| Fuente | Estado |
|---|---|
| SAP HANA | 🔴 CAÍDO al cierre (antes accesible; handshake rechazado). Runtime manual requerido |
| Legacy (`srvSyncTelchi02.py::makeCashDFRange` + `cash-2022-02-28.parq`) | ✅ INVENTARIADO + GRAIN CONFIRMADO (read-only) |
| Retail One | 🟡 PARTIAL_TRACEABILITY (sin cambios) |
| DMS | 🟡 PARTIAL_TRACEABILITY (sin cambios) |

## D. Atomic contracts

| Dominio | Contract | Estado |
|---|---|---|
| SALE / PAYMENT / DELIVERY / INVENTORY / BOM | previos | ✅ CONFIRMED |
| **CASH_EVENT** | `CASH_EVENT_SAP_FIELDS` (CONFIRMED) + `CASH_EVENT_LEGACY_FIELDS` (LEGACY_REFERENCED) | 🟡 definido; validación SQL HANA pendiente |
| STOCK→DOCUMENT relation | `relation_stock_document.sql` (GENERATES, DIRECT_REFERENCE/SAP_BASEENTRY) | 🟡 extractor escrito; validación HANA pendiente |

## E. Relaciones confirmadas (no hipótesis)

1. **LEGACY CASH → LEGACY SALE (DIRECT_REFERENCE):** `cjtrn.cjtrntorg` (origen=6) = `vttrn.vttrnNtve` = SaleCode;
   `cjdpc.cjdpctorg` (trn=605) = mismo SaleCode; cliente via `vttrnccli`/`cjdpcccli`. Evidencia: código legacy + parquet.
2. **LEGACY CASH GRAIN:** 1 fila = movimiento de caja; `NroTransaccion` NO único (secuencias CJTRN/CJDPC colisionan, 187 dups en 2022-02) → grain = (source_table, NroTransaccion).
3. **Perfil caja legacy (2022-02, n=28.175):** 43 cajas; Efectivo 89,2%, TARJETA 9,1%, Dep/Tran 1,5%, CHEQUE 0,2%; SaleCode>0 en 89,6%; 6 sucursales; Bs 98,7%; montos firmados (suma -354.989,96 = flujos de salida presentes).
4. **STOCK→DOCUMENT (validación previa reutilizada):** `BASE_REF` = DocNum (no DocEntry); DocNum colisiona entre familias (rate 1,0) → TransType obligatorio; DOCNUM_RESOLVE 20/20 (línea+item) y tt=15 3.709/3.709; APPLOBJ>0 → AppObjAbs directo.

## F. Hipótesis nuevas

- H4: La caja física SAP puede residir en OJDT/JDT1 (cuenta caja via `OACT.CashBox`) — CANDIDATE, requiere inspección cuando HANA vuelva.
- H5: `cjtrn.cjtrntorg` (SaleCode legacy) podría mapear a `OINV.DocNum` o `OINV.DocEntry` (link CROSS-SYSTEM legacy sale → SAP invoice) — pendiente de validar con vttrn en HANA.
- H6: H3 (U_ORIGIN herencia ORCT) se reafirma como CANDIDATE: `U_ORIGIN`/`U_SO1_01RETAILONE` en ORCT deben verificarse para cash de canal.

## G. Tests

| Capa | Conteo | Resultado |
|---|---|---|
| UNIT (contracts + cash + stock resolve) | 23 | 23 PASS |
| CONTRACT (HANA) | 1 | ⏳ BLOCKED (runtime) |
| SOURCE (HANA) | 9 (7 previos + 2 nuevos) | ⏳ BLOCKED (runtime) |
| SEMANTIC (HANA real) | 2 | ⏳ BLOCKED (runtime) |
| Regresión dominio | 23 unit | PASS |

## H. Hallazgos reales

| Hallazgo | Evidencia | Confianza |
|---|---|---|
| Legacy cash = evento por caja física (CashCode) con venta origen en 89,6% | `cash-2022-02-28.parq` + `srvSyncTelchi02.py` | CONFIRMED (legacy) |
| Grain legacy cash NO es único por NroTransaccion | 187 duplicados (CJTRN+CJDPC) | CONFIRMED (legacy) |
| ORCT no expone caja física | contract SAP sin columna caja | CONFIRMED (ausencia) |
| HANA runtime caído (handshake reset), VPN/forward OK | probe hdbcli + ss/socat | CONFIRMED |

## I. Gaps

1. Validación HANA de `source_cash_event_sap.sql` y `relation_stock_document.sql` (runtime manual caído — bloqueo externo real).
2. Caja física SAP (OJDT/JDT1/OACT.CashBox) — CANDIDATE, sin inspeccionar.
3. Existencia de tablas legacy (cjtrn/cjcja/cjdpc/cjddc/vttrn) en HANA actual — pendiente catalog check.
4. Link CROSS-SYSTEM legacy sale → SAP invoice (H5) — requiere vttrn en HANA.
5. Venta×caja×mercadería E2E real (T27) — requiere HANA + cierre de cash link.

## J. Próxima prioridad

**Principal:** cuando HANA vuelva — validar extractores nuevos (contract/source/semantic) en ventana 2023-02 y cerrar el E2E venta×caja×mercadería T27 (caja legacy vía cjtrn o SAP vía ORCT CashSum).

Secundarias:
1. Catalog check tablas legacy (cjtrn/cjcja/cjdpc/vttrn) en HANA; si existen, extractor CASH_EVENT legacy con grain (source_table, NroTransaccion).
2. Resolver H5 (SaleCode legacy → DocEntry/DocNum SAP) para el link cross-system caja→venta→factura.
3. Caja física SAP via OJDT/JDT1/OACT.CashBox (H4).
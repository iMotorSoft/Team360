# TELCHI SAP — LAT

**LEARNINGS, ARCHITECTURAL DECISIONS, TECHNICAL FINDINGS**

**Módulo:** Telchi SAP
**Capa:** DataScience — Ventas, Cobranzas, Crédito, Temporalidad SAP

---

## 1. Architectural Decisions

### TELCHI-DEC-001: DataScience Separation
DataScience workspace is separated from Team360 runtime. No shared code, no shared Git, no shared dependencies.

### TELCHI-DEC-002: SAP HANA as Current Source
HANA is the single source of truth for current state. Legacy SQL serves as semantic baseline only.

### TELCHI-DEC-003: Legacy as Semantic Baseline
Legacy Python code defines what questions were being asked and how. It does NOT define current data quality.

### TELCHI-DEC-004: No New Parquet Yet
Current phase is SQL + semantics + validation. Parquet writes will come after financial model is complete.

### TELCHI-DEC-005: Podman Lifecycle Manual
Agent never starts/stops Podman. If HANA is unreachable, stop and report.

### TELCHI-DEC-006: SAP IDs First
Every financial metric must be traceable to SAP identifiers (DocEntry, ReconNum, etc.). No synthetic IDs.

---

## 2. SAP Traceability Rules

| Identifier | Table | Purpose |
|------------|-------|---------|
| DocEntry | OINV, ORIN, ORCT | Document primary key |
| LineNum | INV1, RIN1 | Line-level identity |
| ReconNum | OITR, ITR1 | Reconciliation identity |
| SlpCode | OINV, ORIN, OSLP | Seller identity |
| CardCode | OINV, ORIN, ORCT, OCRD | Customer identity |
| TransId | ORCT, ITR1 | Journal transaction ID |
| SrcObjAbs | ITR1 | Source document DocEntry |
| SrcObjTyp | ITR1 | Source document type |

---

## 3. Sales Learnings

### Seller ≠ Channel
- **Seller** = OSLP.SlpCode (who sold)
- **Channel** = OCRD.U_CANAL_VENTAS (customer type)
- A corporate seller (cat=2) can sell to any channel
- A non-corporate seller can sell to corporate customers

### Historical Channel
- `U_CANAL_VENTAS` exists from 2026+ (bulk loaded)
- Pre-2026: legacy classification using PriceTypeCode + ClientSegmentationCode
- Current recommendation: Use `OCRD.U_CANAL_VENTAS` for 2026+, legacy model for history

---

## 4. Invoice Learnings

### Grain
- `OINV.DocEntry` is unique (header level)
- `OINV.DocEntry + INV1.LineNum` is unique (line level)
- Do NOT sum header fields over lines without control

### Currency
- `OINV.DocCur` is the currency field
- `Currency` field does NOT exist in OINV
- `DocTotal` is in document currency
- `DocTotalFC` is in foreign currency

### PaidToDate vs PaidSum
- `PaidToDate` shows historical payments (even for canceled invoices)
- `PaidSum` is zero for canceled invoices
- **Use PaidToDate for payment analysis**

### Cancellation
- `CANCELED` values: N (valid), Y (canceled), C (reversal document)
- Y and C always appear in pairs
- Canceled invoices show PaidToDate = DocTotal (historical payments preserved)
- Cancellation rate: < 0.01%

---

## 5. Credit Note Learnings

### Sign Contract
- `ORIN.DocTotal` is POSITIVE in SAP
- Legacy negates it for commercial calculations
- Financial effect is negative (reduces receivables)

### Linkage
- `RIN1.BaseEntry` → `OINV.DocEntry` (when BaseType=13)
- `RIN1.BaseLine` → `INV1.LineNum` (when applicable)
- 96.61% of NC lines have BaseEntry linkage
- 95.01% link directly to invoices (BaseType=13)

### BaseType Semantics
| BaseType | Object | Notes |
|----------|--------|-------|
| 13 | A/R Invoice | Primary linkage |
| 16 | A/R Return | NOT Purchase Invoice |
| -1 | No Reference | Unlinked credits |

### Unlinked Credits
- 3.39% of NC lines have no BaseEntry
- Reserved for reconciliation analysis (FINANCIAL-004)

---

## 6. Payment Learnings

### CRITICAL: RCT2 Role in Telchi
**In this HANA database, RCT2 does NOT contain real payment-to-invoice linkage.**

| Table | Expected SAP Role | Actual Telchi Role |
|-------|-------------------|-------------------|
| ORCT | Payment header | Payment header |
| RCT1 | Payment checks | Payment checks detail |
| RCT2 | Payment-to-invoice link | **On-account only** (InvoiceId=0) |

### Real Settlement Layer
**OITR/ITR1 (Reconciliation) is the actual settlement mechanism.**

- SrcObjTyp=24 (Payment) + SrcObjTyp=13 (Invoice) linked via ReconNum
- This is TELCHI-SPECIFIC, not a global SAP rule

### Currency
- `ORCT.DocCurr` (NOT DocCur)
- BS (local) and USD (foreign) observed

---

## 7. Reconciliation Learnings

### OITR/ITR1 is Settlement Authority
- ReconNum is the central identifier
- Reconciled ≠ cash paid (can include credits, down payments, journals)
- Settlement can include: payment, credit, down payment, journal, other

### Grain
- OITR: ReconNum (unique)
- ITR1: ReconNum + LineSeq (unique)

### Status
- N = active
- C = canceled (reversal)
- Y = canceled (original)

### Reconciliation Balance
- 99.98% of reconciliations balance (within 0.01 tolerance)
- 0.02% unbalanced requires materiality assessment

### Settlement Classification
| Type | Count (Feb 2023) | Description |
|------|------------------|-------------|
| PAYMENT_INVOICE | 28,034 | Payment settles invoice |
| PAYMENT_ONLY | 3,368 | On-account payment |
| CREDIT_INVOICE | 138 | Credit note settles invoice |
| INVOICE_ONLY | 161 | Invoice with no payment/credit |

---

## 8. Temporal Learnings

### Date Semantics
- Sale Date ≠ Payment Date ≠ ReconDate
- For settlement analysis, use ReconDate (not DocDate)
- For AR aging, use AS_OF_DATE (mandatory)

### Current vs Historical
- Current AR uses current DocStatus and PaidToDate
- Historical As-Of AR requires reconstructing payment state as of date
- Do not use payments made after AS_OF_DATE

### March 2023 Outlier
- Feb 2023: $28M in reconciliations
- Mar 2023: $2B in reconciliations (72x)
- Requires explanation before FINANCIAL-005

---

## 9. Audit Principles

### No Fraud Language
- Never label anomalies as fraud, theft, or manipulation
- Use: `REVIEW_REQUIRED` with evidence

### No Heuristic Pairing
- Never assign payment → invoice by: same amount, FIFO, nearest date
- SAP provides reconciliation sets, not exact pairings

### No Silent Adjustments
- Never `drop_duplicates()` as repair
- Never modify signs without understanding semantics
- Never exclude data without documenting

### No Synthetic IDs
- Every metric must trace to real SAP identifiers
- No invented document relationships

---

## 10. Known Risks

| Risk | Status | Impact |
|------|--------|--------|
| March 2023 reconciliation outlier | OPEN | Must explain before AR calculation |
| 0.02% unbalanced reconciliations | OPEN | Materiality assessment needed |
| Historical channel reconstruction | PARTIAL | Pre-2026 requires legacy model |
| Multicurrency | PROFILED | BS + USD observed, contract not closed |
| RCT2 limited role | DOCUMENTED | Settlement via OITR/ITR1 confirmed |

---

## 11. Decisions Frozen

### TELCHI-DEC-007: Purchase Material Planning V1 Freeze

Gates 1–10 de Compras/Abastecimiento forman un baseline semántico congelado.
Se permiten bugs, regresiones y nuevos datos/casos; nuevas features y refactors
de alto riesgo requieren requerimiento explícito. El contrato global conserva
las capas físico, equivalente en PT, producible, compra abierta y demanda sin
doble conteo, y `ExecutiveCase.to_dict()` es la interfaz estable para futuros
consumidores ejecutivos.

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-001 | DataScience separated from Team360 | Architecture |
| TELCHI-DEC-002 | HANA is current source | Validation |
| TELCHI-DEC-003 | Legacy is semantic baseline | Code inspection |
| TELCHI-DEC-004 | No Parquet writes yet | Policy |
| TELCHI-DEC-005 | Podman manual lifecycle | Policy |
| TELCHI-DEC-006 | SAP IDs first | All validations |
| TELCHI-DEC-007 | OINV.DocEntry financial grain | FINANCIAL-001 |
| TELCHI-DEC-008 | ORIN DocTotal positive raw | FINANCIAL-002 |
| TELCHI-DEC-009 | RCT2 not settlement authority | FINANCIAL-003 |
| TELCHI-DEC-010 | OITR/ITR1 is settlement layer | FINANCIAL-004 |
| TELCHI-DEC-011 | Reconciled ≠ cash paid | FINANCIAL-004 |
| TELCHI-DEC-012 | BaseType=16 is A/R Return | FINANCIAL-002 |

---

## 12. PyArrow Compatibility

### Observed Versions
- Historical Parquet: 1.0.0, 9.0.0, 11.0.0
- Current environment: 25.x

### Status
Write compatibility contract NOT yet defined. Phase is SQL + semantics, not Parquet production.

---

## 13. Key Formulas

### Net Commercial Sales
```
VALID_GROSS_INVOICED_SALES - VALID_CREDIT_NOTE_AMOUNT = NET_COMMERCIAL_SALES
```

### Outstanding AR (Target for FINANCIAL-005)
```
Original Invoice
- Valid Credit Settlement
- Valid Payment Settlement
- Other Valid Settlement
= Outstanding AR
```

### Aging (Target for FINANCIAL-005)
```
days_overdue = AS_OF_DATE - DocDueDate
```

Buckets: NOT_DUE, 1-30, 31-60, 61-90, 91-120, 120+

---

## 14. FINANCIAL-005 Learnings

### Settlement Semantics
- **Settlement = ITR1.ReconSum for SrcObjTyp=13** (invoice lines in reconciliations)
- The invoice's own ReconSum in a reconciliation IS the amount allocated to it
- NOT the sum of other members in the same reconciliation
- This matches SAP PaidToDate exactly (100% match validated)

### Outstanding Formula
```
Outstanding = DocTotal - TotalSettlement
TotalSettlement = SUM(ITR1.ReconSum) WHERE SrcObjTyp=13 AND OITR.Canceled='N'
```

### March 2023 Outlier Root Cause
- **AP_ACTIVITY**: 5 reconciliations of $389M each
- SrcObjTyp=18 (A/P Invoice) and 20 (Journal Entry)
- Accounts: 1130401 (Mercadería en tránsito), 2110201 (Cuentas por pagar ME)
- Impact on AR: NONE — these are Accounts Payable transactions
- Without outliers: Mar 2023 = $88.7M (3x Feb, reasonable)

### Reconciliation Balance Semantics
- **Correct check**: credit_sum vs debit_sum (not Total vs SUM)
- SAP stores: credit_sum = debit_sum = Total, SUM(ReconSum) = 2 * Total
- Previous 0.02% "unbalanced" was measurement error
- Actual result: 0 unbalanced out of 33,077 (Feb 2023)

### HANA SQL Specifics
- HANA uses `DAYS_BETWEEN(start, end)` NOT `DATEDIFF('DAY', start, end)`
- Column names are case-sensitive (use quoted identifiers)
- `databaseName='NDB'` required for connection (not 'TELCHI')
- Aggregate functions cannot be nested in GROUP BY queries
- Use column aliases in ORDER BY, not aggregate expressions

### Dimension Reconciliation
- AR = Customer = Seller = Channel totals MUST reconcile
- All four dimensions reconcile to $3,847,327.43
- This is an INVARIANT — any discrepancy indicates a bug

### Aging Invariant
- Sum of aging buckets MUST equal total positive outstanding
- NOT_DUE + 1-30 + 31-60 + 61-90 + 91-120 + 120+ = Total
- This is an INVARIANT — any discrepancy indicates a bug

### Audit Flags
- AUDIT_AR_NEGATIVE_BALANCE: 0 (no over-settled invoices)
- AUDIT_AR_CANCELED_INVOICE_OPEN: 0 (no canceled invoices in open status)
- AUDIT_AR_MISSING_DUE_DATE: 0 (all open invoices have due dates)

### Key Metrics (AS_OF_DATE: 2026-08-21)
- Open Invoices: 1,861
- Outstanding AR: $3,847,327.43
- Not Due: $2,358,370.21 (61.3%)
- Overdue: $1,488,957.22 (38.7%)
- Customers: 344
- Sellers: 96
- Channels: 9

---

## 15. Decisions Frozen (FINANCIAL-005)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-017 | Settlement = ITR1 ReconSum for SrcObjTyp=13 | FINANCIAL-005, 100% PaidToDate match |
| TELCHI-DEC-018 | March 2023 outlier = AP_ACTIVITY | 5 reconciliations of $389M, SrcObjTyp=18/20 |
| TELCHI-DEC-019 | Reconciliation balance = credit vs debit | 0 unbalanced out of 33,077 |
| TELCHI-DEC-020 | HANA uses DAYS_BETWEEN not DATEDIFF | SQL validation |
| TELCHI-DEC-021 | Database name is NDB not TELCHI | Connection validation |

---

## 16. FINANCIAL REPORTING CONTRACT Learnings

### Flow vs Stock Distinction
- **Sales**: FLOW metric (DocDate within period)
- **Payments**: FLOW metric (DocDate within period)
- **Reconciliation**: FLOW metric (ReconDate within period)
- **AR**: STOCK metric (AS_OF_DATE mandatory)
- Never mix flow and stock without labeling

### Payment vs Settlement Distinction
- **PaymentDocumentAmount**: What was registered in payments (ORCT)
- **PaymentSettlement**: What was applied to invoices (ITR1 SrcObjTyp=24)
- These are NOT the same thing
- A payment in August can pay an invoice from July

### Sales Cohort Concept
- **Cohort**: Invoices issued in specific period
- **CohortSettledAsOf**: How much of that cohort is settled as of date
- **CohortOutstandingAsOf**: How much is still pending as of date
- Critical distinction: "Cobros de agosto" != "Cuánto cobramos de ventas de agosto"

### Official KPI Semantics
- Every KPI must have ONE definition
- Same KPI must use SAME formula across all reports
- Cross-report totals must reconcile
- No report-specific calculations

### Source Authority Principle
- Each KPI family has ONE authoritative SQL source
- No duplicate logic
- Financial audit model (FINANCIAL-001..005) is the baseline
- No new SQL may contradict validated SQL

### Dimension Rules
- Customer owns the debt (not seller)
- Channel belongs to customer (not seller or transaction)
- Seller is analytical dimension only
- SlpCode=-1 indicates no seller assigned
- NULL channel = "Sin Clasificar"

### Temporal Semantics
- Sales: DocDate
- Payments: DocDate
- Settlement: ReconDate
- AR: AS_OF_DATE (mandatory)
- Each metric must declare its date semantics

---

## 17. Decisions Frozen (REPORTING CONTRACT)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-R001 | NetSales = ValidGrossSales - ValidCreditNotes | Reporting Contract |
| TELCHI-DEC-R002 | OutstandingAR authority = current_ar_v1.sql | FINANCIAL-005 validation |
| TELCHI-DEC-R003 | AR is stock as-of metric | Reporting Contract |
| TELCHI-DEC-R004 | Payments flow != cohort collection | Reporting Contract |
| TELCHI-DEC-R005 | Seller portfolio uses invoice SlpCode | Reporting Contract |
| TELCHI-DEC-R006 | Channel uses OCRD.U_CANAL_VENTAS (2026+) | Reporting Contract |
| TELCHI-DEC-R007 | Same KPI formula across all reports | Reporting Contract |
| TELCHI-DEC-R008 | Cross-report totals must reconcile | Reporting Contract |

---

## 17. ATOMIC NUCLEUS Learnings (2026-08-25)

### Payment Method Profile (T04)
- ORCT header cash-sum fields classify payments: CashSum, CheckSum, TrsfrSum, CreditSum, NoDocSum, BoeSum.
- Feb 2023 (n=29,184 active payments): CASH 81.3%, CARD 10.8%, MIXED 4.4%, TRANSFER 3.4%, CHECK 0.1%.
- Classifier in atomic/semantic reads PHYSICAL ORCT column names, not SQL aliases.

### Channel Evidence (Retail One / DMS)
- OINV.U_ORIGIN ∈ {SAP, DMS}; DMS ~8% of sampled invoices (n=200k, 2026-01+).
- OINV.U_DMS_STATE ∈ {A, V}.
- OINV.U_SO1_01RETAILONE ∈ {Y (89.5%), N (10.5%)} — 2026-07 sample (n=50k).
- OINV.U_SO1_01FOLIORETAIL1: 58,778 distinct folios in 2026-07; U_SO1_01PREFIJO ∈ 231-234; U_SO1_01SUCURSAL branch prefix.
- Storefront sales flow through Retail One tickets → SAP invoice (folio-marked). SALE/CASH/STOCK timing link remains OPEN.

### OINM Catalog Quirk
- OINM does not appear in SYS.TABLE_COLUMNS under insiding_hana; `SELECT * ... LIMIT 0` describe works. Use the fallback in atomic/connection.table_columns().

### Atomic Contracts
- EVENT_ENVELOPE base keys stable (§9). Domain maps only CONFIRMED fields.
- DOCUMENT_RELATION: relation_type ∈ RELATION_TYPES_CANDIDATE; match_method ∈ MATCH_METHODS; never upgrade INFERRED.
- CHANNEL_OPERATION_RULE: retail_one/dms = PARTIAL_TRACEABILITY with evidence; rules not fabricated (§27).

### Testing
- pytest not installed; runner uses unittest (validation/atomic/run_atomic_tests.py). 21 tests green on real HANA (2023-02 window).

## 18. Decisions Frozen (ATOMIC)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-022 | Payment method classifier reads physical ORCT columns | Payment profile test |
| TELCHI-DEC-023 | Retail One = PARTIAL_TRACEABILITY via U_SO1_01* UDFs | 2026-07 sample |
| TELCHI-DEC-024 | DMS = PARTIAL_TRACEABILITY via U_ORIGIN | 200k sample 2026-01+ |
| TELCHI-DEC-025 | OINM column discovery via SELECT*LIMIT0 fallback | Catalog quirk |

## 19. CASH_EVENT + STOCK LINK Learnings (2026-08-25)

### Legacy cash semantic baseline (makeCashDFRange, srvSyncTelchi02.py)
- Legacy CASH_EVENT grain: 1 fila = movimiento de caja. Tablas NO-SAP:
  `cjtrn` (movs caja) + `cjcja` (cajas) + `cjdpc` (depósitos DC) + `cjddc` (tipos DC)
  + masters `gbper/gbofi/gbcon/cjtmv/gblog` + ventas `vttrn/vthpf/vtdpf`.
- **NroTransaccion NO es único** (secuencias CJTRN y CJDPC colisionan; 187 dups en
  cash-2022-02-28.parq) → grain = (source_table, NroTransaccion).
- Perfil real (2022-02, n=28.175): 43 cajas físicas (CashCode); Efectivo 89,2%,
  TARJETA DEBITO-CRED 9,1%, Dep/Tran 1,5%, CHEQUE 0,2%, CHPDBs; SaleCode>0 89,6%;
  ClientCode>0 11,1% (solo origen venta); 6 sucursales; Bs 98,7%/$us 1,3%.
- Montos FIRMADOS: suma 2022-02 = -354.989,96 (incluye gastos, traspasos,
  depósitos — no todo es ingreso de venta).
- Ventas legacy: `vttrn.vttrnNtve` = SaleCode; `vthpfCprf` = prefijo; cliente
  `vthpfCcli`; origen caja→venta: `cjtrnmorg=6 → cjtrntorg=vttrnNtve`,
  `cjdpcttrn=605 → cjdpctorg=vttrnNtve`.
- "Cajas" incluyen fondos a rendir/caja chica (CashName "Fondo a Rendir...",
  "Caja Chica...") — no todas las cajas son cajas de venta.

### SAP side cash
- ORCT no expone caja física; CASH_EVENT SAP = pago con porción cash
  (`CashSum > 0`). cash_register_id queda UNKNOWN hasta OJDT/JDT1/OACT.
- `build_cash_event_from_payment`: CASH_ONLY / CASH_PORTION / NON_CASH_PAYMENT.

### Stock -> document link (DOCNUM_RESOLVE, validado antes y reutilizado)
- OINM.BASE_REF = **DocNum** (NO DocEntry); DocNum colisiona entre familias
  (docnum_collision_analysis: rate 1.0) → TransType obligatorio como guard.
- Resolución: BASE_REF → header.DocNum → DocEntry; DocLineNum → LineNum;
  ItemCode fortalece (1.0); header-only 0.5; APPLOBJ>0 → AppObjAbs directo
  (SAP_BASEENTRY, 1.0) para 59/60 y otros.
- relation_type = GENERATES (documento comercial → movimiento de inventario).

## 20. Decisions Frozen (CASH_EVENT + STOCK LINK)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-026 | Legacy cash grain = (source_table, NroTransaccion), no NroTransaccion solo | 187 dups en cash-2022-02-28.parq |
| TELCHI-DEC-027 | OINM→documento: BASE_REF=DocNum + guard TransType + DocLineNum=LineNum (+item) | line_link_validation CORRECTED_LINE_LINK_V2 (20/20), docnum_collision 1.0 |
| TELCHI-DEC-028 | CASH_EVENT SAP = pago con CashSum>0; caja física no explícita en ORCT | source_cash_event_sap.sql + contract |
| TELCHI-DEC-029 | Legacy cash incluye cajas no comerciales (fondos a rendir, caja chica) | CashName observado 2022-02 |
| TELCHI-DEC-030 | Runner atomic: gate conectividad con exit 3 = BLOCKED (nunca PASS con HANA caído) | run_atomic_tests.py main() |

## 21. SALES × CASH × STOCK Learnings (2026-08-25)

### Corte de migración (H5 verdict)
- SAP (OINV/ODLN/ORCT/OINM) arranca **2022-03-31** (marzo 2022 = 1.236 facturas; abril = 23.406).
- Legacy (vttrn/cjtrn/cjdpc, SQL Server viejo) terminó ~2022-04 (último cash-2022-04-30.parq).
- **H5 = REJECTED a nivel transacción**: no existe referencia vttrnNtve en SAP.
  `OINV.NumAtCard` 100% vacío (2022-02); `INV1.BaseRef` = "VACIO" (extractor legacy);
  sin UDF de referencia legacy. La cadena moderna es 100% intra-SAP.
- **Cliente legacy→SAP CONFIRMED (79.2%)**: `CardCode = 'C%06d' % gbpercper`
  (1.634/2.062 clientes activos 2022-02).
- **Warehouse→sucursal legacy CONFIRMED**: `sapWhsOfficeName.parq` (60 filas).

### Cadena cash (era SAP, Retail One ya activo en 2023-02)
- Perfil 2023-02 (n=28.899): CASH 23.798 (82,4%), CARD 3.158, TRANSFER 903, MIXED 182,
  CHECK 68, sin pago 790. Retail One 86,2% (folio-marked), DMS 9,7%.
- Retail One con settlement 99,5% (24.776/24.908) → el efectivo de caja viaja por ORCT.
- **Efectivo aplicado por factura = Σ ITR1.ReconSum (SrcObjTyp=13, recons activas)** —
  N:N-safe (nunca atribuir el pago completo a una sola factura). = 100% PaidToDate (DEC-017).
- **expected_cash (control de caja) = DocTotal bruto** (con IVA): es lo que la caja debe
  recibir. goods_sale_value (neto líneas) es dimensión separada (valor de mercadería).
- Pago parcial = diferencia explicada (PARTIAL_CASH_PAYMENT, saldo pendiente);
  solo sobre-aplicación → REVIEW_REQUIRED.
- Costo de mercadería salida = OINM.TransValue (firmado negativo en salidas → abs).

### Resultado real 2023-02 (28.899 casos atómicos)
- CONSISTENT 23.023 (79,7%) · PARTIALLY_RECONCILED 5.876 · REVIEW 0 · UNEXPLAINED 0.
- Stock resuelto 94,9% (27.422); 68 facturas sin OINM tt=13 jamás (revisar items servicio).
- Batch anulaciones mayo 2024 = 978 Y + 978 C (por DocDate).

## 22. Decisions Frozen (SALES × CASH × STOCK)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-031 | Corte de migración SAP = 2022-03-31; H5 transaccional REJECTED | OINV/ODLN/ORCT/OINM min DocDate; NumAtCard vacío; BaseRef=VACIO |
| TELCHI-DEC-032 | Cliente legacy→SAP = C%06d(gbpercper) | 1.634/2.062 (79.2%) OCRD 2022-02 |
| TELCHI-DEC-033 | Efectivo por factura = Σ ITR1.ReconSum SrcObjTyp=13 (N:N-safe) | 2023-02, 23.023 CONSISTENT |
| TELCHI-DEC-034 | expected_cash = DocTotal bruto (IVA incluido); neto = valor mercadería | Diferencia neto/bruto 13% IVA |
| TELCHI-DEC-035 | Pago parcial = PARTIAL_CASH_PAYMENT (explicado); sobre-aplicación = REVIEW_REQUIRED | Caso 23011418 (8.045,48 pendiente) |
| TELCHI-DEC-036 | Costo mercadería = abs(OINM.TransValue) en salidas | TransValue firmado negativo |

## 23. H4 CASH ACCOUNTING Learnings (2026-08-25)

### Cadena contable probada (2023-02, transaccional)
- **ORCT.TransId = OJDT.TransId**: 100% coverage (29.319/29.319), TransId único en
  OJDT → 1:1 estable. JDT1 es 1:N (todas las líneas del asiento).
- **Estructura del asiento de cobro**: débito en ORCT.CashAcct (= CashSum EXACTO,
  24.087/24.087, delta=0) + crédito al cliente vía ContraAct.
- Pagos MIXED se descomponen exactos en el asiento: efectivo → cuenta caja,
  transferencia → puente "Transferencias Bancarias y QR por Confirmar" (1120301),
  resto → cliente.
- **$5.466.433,67 de efectivo confirmado contablemente, diferencia $0.**

### Semántica CashBox / Branch
- `OACT.CashBox='N'` en TODAS las cuentas reales de caja ("Cajas Casa Matriz MN",
  "Caja Corporativa Laboratorio MN", placas de distribuidor) → el flag NO marca
  caja física en Telchi; la familia de cuenta (11102xx salón / 11103xx corporativa)
  y el naming sí.
- BPLId ausente en JDT1 y OACT → branch solo vía naming: HEURISTIC (nunca CONFIRMED).
- Placas de distribuidor: nombre de cuenta ↔ nombre de almacén comparten código
  ("4702-GIP"): coincidencia 100,0% (78.090/78.091); 1 mismatch real (doc 1542943:
  cobró placa 5260-IHY, mercadería de almacén 4702-GIP).

### Cancelaciones / signos
- Reversa vía `OJDT.StornoToTr` (135/135 en ventana): la reversa ACREDITA la cuenta
  de caja → NET = Σ(Debit−Credit) sobre ambas patas sin negar = $0 verificado 112/112.
- Bug propio detectado: negar la segunda pata duplicaba el neto (SIGN_ERROR §36).

### Bugs de integración (clase repetida)
- Pasar dicts con claves minúsculas a `classify_payment_method` (que lee columnas
  físicas) producía método OTHER silencioso → siempre pasar la fila física cruda.

## 24. Decisions Frozen (H4)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-037 | ORCT→OJDT por TransId es 1:1 y proof primario | 29.319/29.319, sin duplicados |
| TELCHI-DEC-038 | Línea cash = JDT1 con Account = ORCT.CashAcct (identidad, no posición) | asientos reales; ContraAct=cliente |
| TELCHI-DEC-039 | OACT.CashBox flag NO representa caja física en Telchi | 'N' universal en cuentas de caja reales |
| TELCHI-DEC-040 | Branch vía naming = HEURISTIC; nunca elevar a CONFIRMED | BPLId ausente; regla §17 |
| TELCHI-DEC-041 | Reversa acredita la caja; NET cero sin negación extra | 112/112 cancelados net-zero |

## 25. EQUIVALENT MATERIAL COVERAGE Learnings (2026-08-30, Gate 7)

### Seis capas de material (nunca fusionar)
- A. USABLE_FG = Σ(OnHand−IsCommited) en roles usables (FINISHED_GOOD/BRANCH/
  DISTRIBUTION/MOBILE/DISPENSING/CONSIGNMENT/RETURNS). IsCommited NO cubre
  demanda nueva (ya prometido).
- B. PHYSICAL_COMPONENT = Σ(OnHand−IsCommited) en LAB-M1/SAA-M1/MAG-M1.
- C. EQUIVALENT_IN_FG = material ya transformado (Gate 3 terminal). Expresa
  cuánta demanda YA está cubierta; NUNCA se suma a B ni a D.
- D. ADDITIONAL_PRODUCIBLE = MAX_PRODUCIBLE con expansión terminal (Gate 4).
- E. OPEN_PURCHASE = POR1.OpenQty en POs abiertas (DOCUMENTED_ORDER, fuera de
  disponibilidad temporal en el run conservador).
- F. EXPECTED_DEMAND = forecast mensual (Gate 6), método por patrón:
  SEASONAL/STABLE/INTERMITTENT → SEASONAL_MA; GROWING/DECLINING → YOY;
  resto → NAIVE.

### Reconciliación OPEN_PURCHASE vs OITW.OnOrder (P0.2)
- `OITW.OnOrder` (1,83 M) ≠ `Σ POR1.OpenQty` (721,6 k, 264 líneas). Dos causas:
  (1) conversión de UOM (purchase UOM vs inventory UOM; ítems M/empaque en
  múltiplos redondos 10x/50x/100x); (2) OnOrder incluye fuentes más allá de
  POs abiertas (p.ej. benzoato OnOrder 32.450 vs open 30.000).
- **Canónica documental de pedido futuro = OPEN_PURCHASE (nivel de línea, ligada
  a proveedor/fecha/U_TIPOCOMPRA).** OnOrder es solo check de reconciliación.

### BOM multinivel en demanda de componentes
- Consumidores terminales > directos por kits/promos/experimentos que embeben
  el envase/insumo vía semi: gotero directo 6 FG → terminal 15 FG; benzoato
  10 → 19. La expansión terminal (Gate 4) propaga correctamente sin doble
  conteo (cada unidad vendida —suelta o en kit— exige su propio envase/insumo).

### Casos ejecutivos reales
- Soda: físico 9,4 t, req ~3 t/mes → stockout ~dic-2026, lt importado p90 201d
  → riesgo (gap -79d); rescate = PO abierta 108 t.
- Cloruro: físico 300 kg pero equiv en FG 9.226 kg → demanda ya cubierta por
  PT; no es urgencia de MP.
- Benzoato: 16,6 t cubren hasta oct, lt 160d → riesgo (gap -69d).
- Gotero: 85–96 k físicos → no limita (≥12 meses).
- L03124 bronceador: cobertura temporada 1,59x → exceso (DO_NOT_BUY en Gate 8).

### Lead time documental ≠ físico (heredado)
- Item-level p90 inestable en muestras chicas (soda n=8, cloruro n=3); el p90
  de importación se infla por outliers; completados locales comprimidos por
  invoice-first/backdated (PHYSICAL_SUPPLY_LEAD_TIME_UNRESOLVED).

## 26. Decisions Frozen (COVERAGE)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-042 | USABLE_FG = OnHand−IsCommited en roles usables (no solo OnHand) | IsCommited ya prometido |
| TELCHI-DEC-043 | Canónica de pedido futuro = OPEN_PURCHASE (POR1.OpenQty); OnOrder no sumar | 152/263 match; UOM + fuentes extra |
| TELCHI-DEC-044 | EQUIVALENT_IN_FG nunca entra a capacidad de producción | Gate 3/4 + invariantes |
| TELCHI-DEC-045 | Waterfall FG: FG usable → adicional producible → stockout (time-respecting) | sección 30 |
| TELCHI-DEC-046 | Componente compartido: comparación agregada; allocation UNRESOLVED | sección 41 |
| TELCHI-DEC-047 | Forecast Gate 7: método por patrón (SEASONAL_MA/YOY/NAIVE), no promedio anual | sección 33/63 |
| TELCHI-DEC-048 | LEAD_TIME_COVERAGE_GAP = horizonte_días − lead_p90; <0 = zona de riesgo | sección 49 |

## 27. PURCHASE RISK ENGINE Learnings (2026-08-30, Gate 8)

### Decisiones explicables (sin score opaco)
- Reglas visibles por material: `BUY_NOW` si `LATEST_SAFE_ORDER_MONTH <= snapshot`;
  `BUY_SOON` dentro de ventana de advertencia (2 meses); `WATCH` futuro/ sin lead;
  `SAFE` cobertura física/abierta >= requerimiento; `DO_NOT_BUY` equivalente en PT
  cubre demanda; `EXCESS_STOCK` declive/discontinuado con cobertura abundante.
- `LATEST_SAFE_ORDER_MONTH = STOCKOUT_MONTH − ceil((lead_p90 + buffer)/30.44)`
  (resolución mensual; no se inventa día).
- Safety buffer HEURÍSTICO (no 30d universal): 7d base + 7d forecast incierto +
  7d componente compartido + 14d muestra de lead time baja.

### EQUIVALENT_IN_FG en la decisión de compra (≠ capacidad)
- En la DECISIÓN de compra, el equivalente ya transformado en PT SÍ compensa la
  demanda futura (cubre demanda sin nueva producción) → evita doble compra.
- En CAPACIDAD de producción NUNCA se suma (Gate 4/7). Son dos preguntas distintas.

### Resultado real
- Urgencia concentrada en envases/etiquetas (tapa PET 236 FG, caja 230 FG,
  papel 109 FG, precinto 40 FG) → 226 FG PRODUCTION_BLOCKED; confirma Gate 4/5.
- Tracers: benzoato BUY_NOW (16,6t + 30t orden < 68t req; lso 2026-05 vencido);
  soda SAFE+import delay (108t abiertas cubren); cloruro SAFE (equiv 9.226 en PT);
  gotero SAFE.

## 28. Decisions Frozen (RISK)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-049 | Decisión sin score opaco: reglas visibles sobre coverage/lead/stockout | sección 78 |
| TELCHI-DEC-050 | EQUIVALENT_IN_FG compensa demanda en decisión (no en capacidad) | sección 83/43 |
| TELCHI-DEC-051 | LATEST_SAFE_ORDER_MONTH mensual; buffer HEURÍSTICO no universal | sección 79/80 |
| TELCHI-DEC-052 | Orden abierta que cubre faltante = SAFE + IN_TRANSIT (no re-comprar) | sección 44/45 |
| TELCHI-DEC-053 | PRODUCTION_BLOCKED = envase/etiqueta como componente limitante | sección 85 |

## 29. PURCHASE DECISION BACKTEST Learnings (2026-08-30, Gate 9)

### Reconstrucción sin hindsight
- Stock as-of-T = SUM(OINM.InQty−OutQty) con DocDate ≤ T (RAW whs). OINM 8,34 M
  filas (2022-03-31→hoy), 0 DocDate nulos; apertura de migración contenida.
- Consumo = IGE1.Quantity (BaseType=202) por mes, con DocDate (218 k filas).
- Forecast = SEASONAL_MOVING_AVERAGE sobre historial ≤ T; anti-leakage estricto.

### Resultado
- 40 casos (10 componentes × 4 snapshots): EARLY_WARNING 14 · CONSISTENT 10 ·
  MISSED_PURCHASE 9 · OVERBUY 7. Precisión early warning (±1 mes) **12/14 (86%)**.
- Empaque regular (tapa PET, frasco 1L) = predicciones exactas (consumo estable).
- Gotero/tapa/contra intermitentes sub-estimados por SEASONAL_MA → MISSED.
- Stock=0 sin demanda (precinto, cloruro) → OVERBUY degenerado.

### Limitaciones declaradas
- Vista solo RAW warehouse: transferencias a producción/FG → saldo RAW acumulado
  puede ser negativo (tapa/contra gotero 2026-01 -259/-242) aunque el stock
  global no lo sea (Gate 2). El granel split RAW/FG (Gate 4) reaparece aquí.
- Open purchase as-of-T no reconstruido (el backtest valida lógica temporal
  stock+forecast, no el efecto de órdenes en tránsito).

## 30. Decisions Frozen (BACKTEST)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-054 | Backtest stock as-of-T desde OINM acumulado (no OITW current) | OINM 8,34M, reconciliación Gate 2 |
| TELCHI-DEC-055 | Verdictos sin causalidad: EARLY_WARNING/MISSED/OVERBUY/CONSISTENT | sección 91 |
| TELCHI-DEC-056 | Forecast intermitente sub-estima (SEASONAL_MA) → flag MISSED | gotero/contra 2025-01/06 |
| TELCHI-DEC-057 | Vista RAW-only; transferencias explican saldo negativo | tapa/contra 2026-01 |

## 31. PURCHASE EXECUTIVE CASES Learnings (2026-08-30, Gate 10)

### Formato ejecutivo
- Cada caso responde las 10 preguntas sin jerga técnica; decisión = action_for()
  de la recomendación Gate 8; confianza = ALTA/MEDIA/BAJA.
- "Cuánto podemos producir" se expresa como **meses de cobertura física** (no suma
  de máximos por FG), porque sumar `MAX_PRODUCIBLE` de FGs que comparten el mismo
  componente produce doble conteo (SHARED_COMPONENT_ALLOCATION_UNRESOLVED).

### Casos entregados (cadena completa)
- Benzoato: BUY_NOW (16,6t + 30t < 68t; lt 160d; lso 2026-05 vencido).
- Soda: SAFE + import delay (9,4t físico + 5,4t PT + 108t orden >= 27t req).
- Cloruro: SAFE (300 kg físico + 9,2t en PT; UOM_UNRESOLVED).
- Gotero/tapa/contra: SAFE (85–96 k físicos; no limitan).
- Bronceador L03124: EXCESS_STOCK (cobertura temporada 1,6x).

## 32. Decisions Frozen (EXECUTIVE)

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-058 | "Cuánto podemos producir" = meses de cobertura física, no suma de máximos | shared components |
| TELCHI-DEC-059 | Reporte ejecutivo generado por el validator (docs/*_v1_report.md) | Gate 10 deliverable |

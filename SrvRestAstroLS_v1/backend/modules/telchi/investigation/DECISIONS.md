# TELCHI SAP — DECISION LOG

Registro de decisiones importantes con evidencia.

**Módulo:** Telchi SAP
**Capa:** DataScience — Ventas, Cobranzas, Crédito, Temporalidad SAP

---

## TELCHI-DEC-001: DataScience Separation

**Date:** 2026-08-17
**Decision:** DataScience workspace is completely separated from Team360 runtime.
**Reason:** Different lifecycle, different dependencies, different risk profile.
**Evidence:** Workspace structure audit.
**Status:** FROZEN

---

## TELCHI-DEC-002: HANA as Current Source

**Date:** 2026-08-17
**Decision:** SAP HANA is the single source of truth for current data state.
**Reason:** HANA contains live business data; legacy Parquet is historical snapshot.
**Evidence:** HANA connectivity validated.
**Status:** FROZEN

---

## TELCHI-DEC-003: Legacy as Semantic Baseline

**Date:** 2026-08-17
**Decision:** Legacy Python code defines what questions were asked, not current data quality.
**Reason:** Legacy code may have bugs, workarounds, and outdated assumptions.
**Evidence:** Legacy code inspection revealed multiple bugs.
**Status:** FROZEN

---

## TELCHI-DEC-004: No Parquet Writes

**Date:** 2026-08-17
**Decision:** Current phase is SQL + semantics + validation only. No Parquet production.
**Reason:** Financial model must be complete before any data product.
**Evidence:** Project scope definition.
**Status:** FROZEN

---

## TELCHI-DEC-005: Podman Manual Lifecycle

**Date:** 2026-08-17
**Decision:** Agent never starts/stops Podman. Manual intervention required.
**Reason:** Infrastructure lifecycle is user-controlled.
**Evidence:** Project constraints.
**Status:** FROZEN

---

## TELCHI-DEC-006: SAP IDs First

**Date:** 2026-08-17
**Decision:** Every financial metric must be traceable to real SAP identifiers.
**Reason:** Auditability requires SAP traceability.
**Evidence:** All financial validations enforce this.
**Status:** FROZEN

---

## TELCHI-DEC-007: OINV.DocEntry Financial Grain

**Date:** 2026-08-20
**Decision:** Invoice financial grain is OINV.DocEntry (header level).
**Reason:** DocTotal is header-level; line-level sum may differ due to rounding/tax.
**Evidence:** FINANCIAL-001 validation: 28899/28899 unique.
**Status:** FROZEN

---

## TELCHI-DEC-008: ORIN DocTotal Positive Raw

**Date:** 2026-08-20
**Decision:** ORIN.DocTotal is positive in SAP; negate for commercial calculations.
**Reason:** SAP stores credit notes with positive DocTotal; legacy negates it.
**Evidence:** FINANCIAL-002 validation: 147/147 positive.
**Status:** FROZEN

---

## TELCHI-DEC-009: RCT2 Not Settlement Authority

**Date:** 2026-08-20
**Decision:** RCT2 is NOT the primary payment-to-invoice linkage in Telchi.
**Reason:** InvoiceId values are all small (1-5) pointing to test invoices. Real linkage via OITR/ITR1.
**Evidence:** FINANCIAL-003 investigation: 0% valid customer match via RCT2.
**Status:** FROZEN — TELCHI-SPECIFIC, not global SAP rule

---

## TELCHI-DEC-010: OITR/ITR1 is Settlement Layer

**Date:** 2026-08-20
**Decision:** OITR/ITR1 (Reconciliation) is the actual settlement mechanism in Telchi.
**Reason:** 100% valid links for Payment (24), Invoice (13), Credit Note (14).
**Evidence:** FINANCIAL-004 validation: 34105 payment links, 29514 invoice links, 146 credit note links.
**Status:** FROZEN

---

## TELCHI-DEC-011: Reconciled ≠ Cash Paid

**Date:** 2026-08-20
**Decision:** Reconciliation settlement includes payments, credits, down payments, and journals.
**Reason:** SrcObjTyp 24, 13, 14, 25, 30, 46, etc. all appear in reconciliations.
**Evidence:** FINANCIAL-004 SrcObjTyp profile.
**Status:** FROZEN

---

## TELCHI-DEC-012: BaseType=16 is A/R Return

**Date:** 2026-08-20
**Decision:** RIN1.BaseType=16 corresponds to A/R Return, NOT Purchase Invoice.
**Reason:** SAP B1 official object types: 16 = A/R Return, 18 = A/P Invoice.
**Evidence:** SAP Help Portal documentation + HANA data validation.
**Status:** FROZEN

---

## TELCHI-DEC-013: PaidToDate Authority

**Date:** 2026-08-20
**Decision:** Use PaidToDate (not PaidSum) for payment analysis.
**Reason:** PaidSum is zero for canceled invoices; PaidToDate shows historical payments.
**Evidence:** FINANCIAL-001 anomaly detection.
**Status:** FROZEN

---

## TELCHI-DEC-014: Canceled Y/C Pair Pattern

**Date:** 2026-08-20
**Decision:** CANCELED values Y and C always appear in pairs; both mean "canceled".
**Reason:** Y is original canceled document, C is reversal document.
**Evidence:** FINANCIAL-001, FINANCIAL-002, FINANCIAL-004 cancellation profiles.
**Status:** FROZEN

---

## TELCHI-DEC-015: DocCur vs DocCurrency

**Date:** 2026-08-20
**Decision:** OINV uses DocCur for currency (NOT "Currency" which doesn't exist). ORCT uses DocCurr.
**Reason:** Schema inspection revealed field names differ between tables.
**Evidence:** HANA metadata inspection.
**Status:** FROZEN

---

## TELCHI-DEC-016: No Heuristic Document Pairing

**Date:** 2026-08-20
**Decision:** Never assign payment → invoice by same amount, FIFO, or nearest date.
**Reason:** SAP provides reconciliation sets (ReconNum), not exact pairings.
**Evidence:** FINANCIAL-004 reconciliation-set semantics.
**Status:** FROZEN

---

## TELCHI-DEC-017: Settlement = ITR1 ReconSum for SrcObjTyp=13

**Date:** 2026-08-21
**Decision:** The settlement amount for an invoice is its own ReconSum in ITR1 where SrcObjTyp=13.
**Reason:** This matches SAP PaidToDate exactly (100% match for 1,861 open invoices).
**Evidence:** FINANCIAL-005 validation: 1861/1861 exact matches.
**Status:** FROZEN

---

## TELCHI-DEC-018: March 2023 Outlier = AP_ACTIVITY

**Date:** 2026-08-21
**Decision:** March 2023 reconciliation outlier ($2B) is driven by AP reconciliations, not AR.
**Reason:** 5 reconciliations of $389M each, SrcObjTyp=18 (A/P Invoice) and 20 (Journal Entry), accounts 1130401 (Mercadería en tránsito) and 2110201 (Cuentas por pagar ME).
**Evidence:** FINANCIAL-005 investigation.
**Status:** FROZEN

---

## TELCHI-DEC-019: Reconciliation Balance = Credit vs Debit

**Date:** 2026-08-21
**Decision:** The correct balance check for reconciliations is credit_sum vs debit_sum, not Total vs SUM(ReconSum).
**Reason:** SAP stores credit_sum = debit_sum = Total, so SUM(ReconSum) = 2 * Total. The previous 0.02% "unbalanced" was a measurement error.
**Evidence:** FINANCIAL-005: 0 unbalanced out of 33,077 active reconciliations.
**Status:** FROZEN

---

## TELCHI-DEC-020: HANA uses DAYS_BETWEEN

**Date:** 2026-08-21
**Decision:** HANA SQL uses `DAYS_BETWEEN(start, end)` not `DATEDIFF('DAY', start, end)`.
**Reason:** DATEDIFF is not a valid HANA function.
**Evidence:** FINANCIAL-005 SQL validation.
**Status:** FROZEN

---

## TELCHI-DEC-021: Database name is NDB

**Date:** 2026-08-21
**Decision:** The HANA database name for connection is 'NDB', not 'TELCHI'. The TELCHI schema is within the NDB database.
**Reason:** Connection with databaseName='TELCHI' fails; 'NDB' succeeds.
**Evidence:** FINANCIAL-005 connectivity validation.
**Status:** FROZEN

---

## TELCHI-DEC-R001: NetSales Official Definition

**Date:** 2026-08-21
**Decision:** NetSales = ValidGrossSales - ValidCreditNotes
**Reason:** Commercial metric that excludes canceled invoices and credit notes. Does NOT include payment status.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

---

## TELCHI-DEC-R002: OutstandingAR Official Authority

**Date:** 2026-08-21
**Decision:** OutstandingAR authority is sql/current/financial/ar/current_ar_v1.sql
**Reason:** Validated in FINANCIAL-005 with 100% match vs SAP PaidToDate.
**Evidence:** FINANCIAL-005 validation.
**Status:** FROZEN

---

## TELCHI-DEC-R003: AR is Stock As-Of

**Date:** 2026-08-21
**Decision:** AR metrics are STOCK metrics requiring AS_OF_DATE.
**Reason:** AR represents a point-in-time position, not a flow over period.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

---

## TELCHI-DEC-R004: Payments Flow != Cohort Collection

**Date:** 2026-08-21
**Decision:** Payments received during period != Settlement against sales cohort.
**Reason:** A payment in August can pay an invoice from July. These are different metrics.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

---

## TELCHI-DEC-R005: Seller Portfolio Uses Invoice SlpCode

**Date:** 2026-08-21
**Decision:** Seller portfolio analysis uses the SlpCode from the invoice, not from payment or other documents.
**Reason:** Seller dimension is analytical; debt belongs to customer.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

---

## TELCHI-DEC-R006: Channel Uses OCRD.U_CANAL_VENTAS

**Date:** 2026-08-21
**Decision:** Customer channel for 2026+ uses OCRD.U_CANAL_VENTAS.
**Reason:** Channel belongs to customer, not to seller or transaction.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

---

## TELCHI-DEC-R007: Same KPI Formula Across Reports

**Date:** 2026-08-21
**Decision:** Same KPI must use SAME formula across all reports.
**Reason:** Prevents conflicting metrics across different reports.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

---

## TELCHI-DEC-R008: Cross-Report Totals Must Reconcile

**Date:** 2026-08-21
**Decision:** Cross-report totals must reconcile: Owner = Customer = Seller = Channel.
**Reason:** Ensures consistency across all analytical dimensions.
**Evidence:** Financial Reporting Contract.
**Status:** FROZEN

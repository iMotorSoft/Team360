# FINANCIAL-005 FINAL REPORT
## Outstanding / Accounts Receivable / Aging
## 2026-08-21

---

## A. Resultado

**TEAM360_TELCHI_FINANCIAL_AUDIT_MODEL_PASS**

---

## B. FINANCIAL Gates

| Change | Gate | Status |
|--------|------|--------|
| FINANCIAL-001 Invoice Contract | `TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS` | ✅ PASS |
| FINANCIAL-002 Credit Note Linkage | `TELCHI_FINANCIAL_CREDIT_NOTE_PASS` | ✅ PASS |
| FINANCIAL-003 Payment Application | `TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS` | ✅ PASS |
| FINANCIAL-004 Reconciliation | `TELCHI_FINANCIAL_RECONCILIATION_PASS` | ✅ PASS |
| FINANCIAL-005 Outstanding / AR | `TELCHI_FINANCIAL_CURRENT_AR_PASS` | ✅ PASS |

---

## C. March 2023 Outlier

- **Root Cause:** AP_ACTIVITY
- **Amount:** $1,946,922,675 (5 reconciliations × $389M each)
- **SrcObjTyp:** 18 (A/P Invoice), 20 (Journal Entry)
- **Accounts:** 1130401 (Mercadería en tránsito), 2110201 (Cuentas por pagar ME)
- **Impact on AR:** NONE — these are Accounts Payable transactions
- **Status:** EXPLAINED

---

## D. Reconciliation Residual

- **Count:** 0 unbalanced out of 33,077
- **Difference:** $0.00
- **Materiality:** ZERO
- **Note:** Previous 0.02% figure was measurement error (compared Total vs SUM instead of credit vs debit)

---

## E. Outstanding Formula

```
Outstanding = DocTotal - TotalSettlement

Where:
  DocTotal = OINV.DocTotal (header-level invoice amount)
  TotalSettlement = SUM(ITR1.ReconSum) WHERE SrcObjTyp=13 AND OITR.Canceled='N'
```

---

## F. Source Of Truth

- **AR Authority:** RECONSTRUCTED_SETTLEMENT
- **SAP Control:** OINV.PaidToDate (100% match validated)
- **Tolerance:** 0.01

---

## G. Current AR

| Metric | Value |
|--------|-------|
| AS_OF_DATE | 2026-08-21 |
| Open Invoices | 1,861 |
| Customers | 344 |
| Outstanding | $3,847,327.43 |
| Not Due | $2,358,370.21 |
| Overdue | $1,488,957.22 |
| Credit Balance | $0.00 |

---

## H. Aging

| Bucket | Count | Amount | % |
|--------|-------|--------|---|
| NOT_DUE | 841 | $2,358,370.21 | 61.3% |
| 1-30 | 235 | $508,352.89 | 13.2% |
| 31-60 | 84 | $117,047.87 | 3.0% |
| 61-90 | 58 | $39,994.62 | 1.0% |
| 91-120 | 24 | $11,797.47 | 0.3% |
| 120+ | 619 | $811,764.37 | 21.1% |

---

## I. Customers (Top 10)

| CardCode | Outstanding | Not Due | Overdue |
|----------|-------------|---------|---------|
| S0001 | $428,328.82 | $13,943.16 | $414,385.66 |
| C000061 | $338,305.80 | $338,305.80 | $0.00 |
| C000143 | $314,625.64 | $314,325.64 | $300.00 |
| C010264 | $160,541.73 | $160,541.73 | $0.00 |
| C003450 | $142,637.17 | $107,714.26 | $34,922.91 |
| C011595 | $137,375.00 | $137,375.00 | $0.00 |
| C000010 | $116,741.24 | $116,741.24 | $0.00 |
| S0004 | $110,359.25 | $7,117.51 | $103,241.74 |
| C010341 | $93,769.76 | $4,361.90 | $89,407.86 |
| C000071 | $79,699.10 | $7,840.00 | $71,859.10 |

---

## J. Sellers (Top 10)

| SlpCode | NetSales | Outstanding |
|---------|----------|-------------|
| 11 | $1,188,885.51 | $1,154,514.11 |
| 139 | $549,355.96 | $549,355.96 |
| -1 | $468,364.47 | $465,325.36 |
| 116 | $294,634.13 | $251,959.39 |
| 13 (Luz) | $210,251.46 | $210,020.71 |
| 238 | $161,635.45 | $161,634.72 |
| 62 | $112,827.38 | $112,827.38 |
| 173 | $123,914.89 | $99,604.24 |
| 64 | $94,179.01 | $94,179.01 |
| 236 | $92,794.65 | $92,794.65 |

---

## K. Channels

| Channel | Outstanding |
|---------|-------------|
| Sin Clasificar | $980,479.94 |
| 3 (Corporativo Grande) | $830,944.72 |
| 8 (Especiales) | $797,741.81 |
| 4 (Supermercados) | $452,239.95 |
| 6 (Regional) | $304,967.25 |
| 5 (Distribuidoras) | $277,282.97 |
| 2 (Corporativo) | $124,121.87 |
| 1 (Farmacias) | $46,801.97 |
| 7 (Retail) | $32,746.95 |

---

## L. Settlement Components

| Component | Amount | % |
|-----------|--------|---|
| Payment (24, 46) | $16,049,268.51 | 93.6% |
| Other | $1,005,319.50 | 5.8% |
| Journal (30) | $159,663.85 | 0.9% |
| Credit Note (14) | $82,875.54 | 0.5% |
| **Total** | **$17,297,127.40** | **100%** |

---

## M. Audit Flags

| Flag | Count | Amount | Portfolio % | Status |
|------|-------|--------|-------------|--------|
| AUDIT_AR_NEGATIVE_BALANCE | 0 | $0.00 | 0.00% | PASS |
| AUDIT_AR_CANCELED_INVOICE_OPEN | 0 | — | — | PASS |
| AUDIT_AR_MISSING_DUE_DATE | 0 | — | — | PASS |

---

## N. SAP Crosscheck

| Metric | Result |
|--------|--------|
| Calculated vs PaidToDate | 100% exact match (1,861/1,861) |
| Calculated AR vs SAP control | MATCHED |
| OCRD Balance comparison | DEFERRED (requires OCRD investigation) |

---

## O. Historical As-Of

- **28/02/2023:** NOT_ATTEMPTED (Current AR completed first)
- **31/03/2023:** NOT_ATTEMPTED (Current AR completed first)
- **Limitations:** Historical as-of requires reconstructing payment state as of date; SAP may not retain sufficient temporal information for cancellations

---

## P. SAP Traceability

| Element | Status |
|---------|--------|
| Invoice DocEntry | ✅ PASS |
| ReconNum | ✅ PASS |
| Payment DocEntry | ✅ PASS |
| Credit Note DocEntry | ✅ PASS |
| CardCode | ✅ PASS |
| SlpCode | ✅ PASS |

---

## Q. Regression

| Change | Status |
|--------|--------|
| FINANCIAL-001 | ✅ PASS |
| FINANCIAL-002 | ✅ PASS |
| FINANCIAL-003 | ✅ PASS |
| FINANCIAL-004 | ✅ PASS |

---

## R. Files

### SQL Created
- `sql/current/financial/ar/settlement_aggregation_v1.sql`
- `sql/current/financial/ar/current_ar_v1.sql`

### Validators Created
- `validation/financial_audit/validate_financial_005_settlement.py`
- `validation/financial_audit/validate_financial_005_current_ar.py`

### Reports Created
- `validation/financial_audit/settlement_005_report.json`
- `validation/financial_audit/current_ar_005_report.json`
- `validation/financial_audit/financial_005_final_report.md`

### Documentation Updated
- `STATUS_ACTUAL.md`
- `LAT.md`
- `DECISIONS.md`
- `validation/financial_audit/financial_audit_gate.json`
- `validation/financial_audit/aging_buckets.yaml`

---

## S. SAP

**writes:** NONE

---

## T. Parquet

**writes:** NONE

---

## U. Infrastructure

**UNCHANGED**

---

## V. Team360

**GLOBAL CHANGES:** NONE

---

## W. Documentation

Updated:
- `STATUS_ACTUAL.md` → TEAM360_TELCHI_FINANCIAL_AUDIT_MODEL_PASS
- `LAT.md` → New learnings from FINANCIAL-005
- `DECISIONS.md` → New decisions DEC-017 through DEC-021
- `financial_audit_gate.json` → All gates closed
- `aging_buckets.yaml` → Validated with actual data

---

## X. Próximo paso

**READY_FOR_TELCHI_FINANCIAL_REPORTING_CONTRACT**

No implementar todavía:
- Dashboard
- Pipeline masivo
- Escritura Parquet

---

## PRINCIPIO FINAL

Al tomar `OINV.DocEntry` podemos explicar:

```
FACTURA ORIGINAL
      ↓
SETTLEMENT
   ├── PAGOS ($16,049,268.51)
   ├── NOTAS DE CRÉDITO ($82,875.54)
   ├── ANTICIPOS ($0.00)
   ├── JOURNALS ($159,663.85)
   └── OTROS ($1,005,319.50)
      ↓
SALDO ($3,847,327.43)
      ↓
VENCIMIENTO (DocDueDate)
      ↓
DÍAS DE MORA (DAYS_BETWEEN)
      ↓
AGING (NOT_DUE, 1-30, 31-60, 61-90, 91-120, 120+)
```

Y podemos agregar el MISMO saldo por:
- **CLIENTE** (344 customers, total = $3,847,327.43)
- **VENDEDOR** (96 sellers, total = $3,847,327.43)
- **CANAL** (9 channels, total = $3,847,327.43)

La pregunta **"¿Cuánto nos deben?"** produce un único total reconciliado: **$3,847,327.43**

Y ese total puede auditarse hasta:
```
Portfolio ($3,847,327.43)
→ CardCode (344 customers)
→ OINV.DocEntry (1,861 invoices)
→ ReconNum (reconciliation sets)
→ SAP document (ITR1.SrcObjAbs)
```

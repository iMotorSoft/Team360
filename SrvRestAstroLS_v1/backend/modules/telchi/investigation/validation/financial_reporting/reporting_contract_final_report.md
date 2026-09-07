# FINANCIAL REPORTING CONTRACT — FINAL REPORT
## 2026-08-21

---

## A. Resultado

**TEAM360_TELCHI_FINANCIAL_REPORTING_CONTRACT_PASS**

---

## B. Financial Model Regression

**TEAM360_TELCHI_FINANCIAL_AUDIT_MODEL_PASS: STILL PASS**

FINANCIAL-001: PASS
FINANCIAL-002: PASS
FINANCIAL-003: PASS
FINANCIAL-004: PASS
FINANCIAL-005: PASS

---

## C. KPI Dictionary

- **Total KPIs:** 41
- **Core KPIs:** 20 (validated with baseline)
- **Defined KPIs:** 21 (formula defined, pending implementation)

### By Family

| Family | Count | Status |
|--------|-------|--------|
| SALES | 7 | DEFINED |
| COLLECTION | 4 | DEFINED |
| SETTLEMENT | 6 | DEFINED |
| AR | 11 | VALIDATED |
| COHORT | 4 | DEFINED |
| AGING | 6 | VALIDATED |
| AUDIT | 3 | VALIDATED |

---

## D. Official Executive KPIs

| KPI | Business Label | Definition | Source | Date Semantics |
|-----|----------------|------------|--------|----------------|
| SALES_NET | Ventas netas | ValidGrossSales - ValidCreditNotes | OINV + ORIN | DocDate (Flow) |
| AR_OUTSTANDING | Saldo pendiente | DocTotal - TotalSettlement | OINV + ITR1 + OITR | AS_OF_DATE (Stock) |
| AR_NOT_DUE | Deuda no vencida | Outstanding WHERE DocDueDate >= AS_OF | OINV + ITR1 + OITR | AS_OF_DATE (Stock) |
| AR_OVERDUE | Deuda vencida | Outstanding WHERE DocDueDate < AS_OF | OINV + ITR1 + OITR | AS_OF_DATE (Stock) |
| AR_OVERDUE_RATE | % cartera vencida | OverdueAR / OutstandingAR | OINV + ITR1 + OITR | AS_OF_DATE (Stock) |
| AR_OPEN_INVOICES | Facturas abiertas | COUNT WHERE Outstanding > tolerance | OINV + ITR1 + OITR | AS_OF_DATE (Stock) |
| AR_CUSTOMERS_WITH_DEBT | Clientes con deuda | COUNT DISTINCT CardCode | OINV + ITR1 + OCRD | AS_OF_DATE (Stock) |

---

## E. Owner Summary

### KPIs Seleccionados

| KPI | Valor | Baseline |
|-----|-------|----------|
| Net Sales | Flow metric | Period-dependent |
| Outstanding AR | $3,847,327.43 | 2026-08-21 |
| Not Due AR | $2,358,370.21 | 61.3% |
| Overdue AR | $1,488,957.22 | 38.7% |
| Overdue Rate | 38.7% | — |
| Open Invoices | 1,861 | — |
| Customers With Debt | 344 | — |

---

## F. Sales Contract

### Gross Sales

| Campo | Valor |
|-------|-------|
| ID | SALES_GROSS |
| Fórmula | SUM(OINV.DocTotal) WHERE DocDate IN period |
| Política anulación | INCLUIR anuladas |

### Valid Gross Sales

| Campo | Valor |
|-------|-------|
| ID | SALES_VALID_GROSS |
| Fórmula | SUM(OINV.DocTotal) WHERE CANCELED = 'N' AND DocDate IN period |
| Política anulación | EXCLUIR anuladas |

### Credit Notes

| Campo | Valor |
|-------|-------|
| ID | SALES_CREDIT_NOTES |
| Fórmula | SUM(ORIN.DocTotal) WHERE CANCELED = 'N' AND DocDate IN period |
| Nota | DocTotal es POSITIVO en SAP |

### Net Sales

| Campo | Valor |
|-------|-------|
| ID | SALES_NET |
| Fórmula | SALES_VALID_GROSS - SALES_CREDIT_NOTES |
| Nota | Métrica comercial. NO incluye estado de pago. |

---

## G. Collection Contract

### Payment Documents

| Campo | Valor |
|-------|-------|
| ID | PAYMENT_DOCUMENTS_VALID |
| Fórmula | SUM(ORCT.DocTotal) WHERE Canceled = 'N' AND DocDate IN period |
| Importante | NO significa "cuánto de las ventas del mes se cobró" |

### Payment Settlement

| Campo | Valor |
|-------|-------|
| ID | SETTLEMENT_PAYMENT |
| Fórmula | SUM(ITR1.ReconSum) WHERE SrcObjTyp IN (24, 46) AND OITR.Canceled = 'N' |
| Importante | NO asumir que PaymentDocumentAmount = PaymentSettlement |

### Sales Cohort Collection

| Campo | Valor |
|-------|-------|
| ID | COHORT_COLLECTION_RATE |
| Fórmula | COHORT_SETTLED_AS_OF / COHORT_GROSS_SALES * 100 |
| Distinción | "Cobros de agosto" != "Cuánto cobramos de ventas de agosto" |

---

## H. AR Contract

### Outstanding

| Campo | Valor |
|-------|-------|
| ID | AR_OUTSTANDING |
| Fórmula | SUM(OINV.DocTotal - TotalSettlement) WHERE CANCELED = 'N' AND DocStatus = 'O' |
| Baseline | $3,847,327.43 |
| Tipo | STOCK (AS_OF_DATE obligatorio) |

### Not Due

| Campo | Valor |
|-------|-------|
| ID | AR_NOT_DUE |
| Fórmula | SUM(Outstanding) WHERE Outstanding > tolerance AND DocDueDate >= AS_OF_DATE |
| Baseline | $2,358,370.21 (61.3%) |

### Overdue

| Campo | Valor |
|-------|-------|
| ID | AR_OVERDUE |
| Fórmula | SUM(Outstanding) WHERE Outstanding > tolerance AND DocDueDate < AS_OF_DATE |
| Baseline | $1,488,957.22 (38.7%) |

### Overdue Rate

| Campo | Valor |
|-------|-------|
| ID | AR_OVERDUE_RATE |
| Fórmula | AR_OVERDUE / AR_OUTSTANDING * 100 |
| Baseline | 38.7% |

### Open Invoices

| Campo | Valor |
|-------|-------|
| ID | AR_OPEN_INVOICES |
| Fórmula | COUNT(OINV.DocEntry) WHERE CANCELED = 'N' AND DocStatus = 'O' AND Outstanding > tolerance |
| Baseline | 1,861 |

### Customers With Debt

| Campo | Valor |
|-------|-------|
| ID | AR_CUSTOMERS_WITH_DEBT |
| Fórmula | COUNT(DISTINCT CardCode) WHERE Outstanding > tolerance |
| Baseline | 344 |

---

## I. Aging

### Buckets

| Bucket | Condición | Baseline |
|--------|-----------|----------|
| NOT_DUE | DocDueDate >= AS_OF_DATE | $2,358,370.21 (841) |
| 1-30 | 0 < days_overdue <= 30 | $508,352.89 (235) |
| 31-60 | 30 < days_overdue <= 60 | $117,047.87 (84) |
| 61-90 | 60 < days_overdue <= 90 | $39,994.62 (58) |
| 91-120 | 90 < days_overdue <= 120 | $11,797.47 (24) |
| 120+ | days_overdue > 120 | $811,764.37 (619) |

### Invariante

```
NOT_DUE + 1-30 + 31-60 + 61-90 + 91-120 + 120+ = Total Positive Outstanding
```

---

## J. Customer Contract

### Métricas por Cliente

| Campo | Descripción |
|-------|-------------|
| CardCode | Identificador único |
| CardName | Nombre (display) |
| OutstandingAR | Saldo pendiente |
| NotDueAR | Deuda no vencida |
| OverdueAR | Deuda vencida |
| OldestDueDate | Fecha vencimiento más antigua |
| MaxDaysOverdue | Máximo días de mora |
| OpenInvoiceCount | Facturas abiertas |

---

## K. Seller Contract

### Métricas por Vendedor

| Campo | Descripción |
|-------|-------------|
| SlpCode | Identificador único |
| SellerName | Nombre (display) |
| NetSales | Ventas netas atribuidas |
| OutstandingAR | Cartera pendiente |
| NotDueAR | Deuda no vencida |
| OverdueAR | Deuda vencida |
| OverdueRate | Tasa de vencimiento |

### Principio

**La deuda sigue siendo del cliente.** Seller es dimensión analítica.

---

## L. Channel Contract

### Métricas por Canal

| Campo | Descripción |
|-------|-------------|
| CustomerChannelCode | Código del canal |
| CustomerChannelName | Nombre del canal |
| NetSales | Ventas netas |
| OutstandingAR | Cartera pendiente |
| NotDueAR | Deuda no vencida |
| OverdueAR | Deuda vencida |
| OverdueRate | Tasa de vencimiento |
| CustomersWithDebt | Clientes con deuda |

### Valores

| Código | Canal |
|--------|-------|
| 1 | Farmacias |
| 2 | Corporativo |
| 3 | Corporativo Grande |
| 4 | Supermercados |
| 5 | Distribuidoras |
| 6 | Regional |
| 7 | Público / Retail |
| 8 | Especiales |
| NULL | Sin Clasificar |

---

## M. Credit Contract

### Credit Limit

| Campo | Descripción |
|-------|-------------|
| CreditLine | Límite de crédito (OCRD.CreditLine) |
| CreditUtilization | OutstandingAR / CreditLine |
| AvailableCredit | CreditLine - OutstandingAR |

### Clasificación

| Estado | Condición |
|--------|-----------|
| WITHIN_LIMIT | OutstandingAR <= CreditLine |
| OVER_LIMIT | OutstandingAR > CreditLine |
| NO_LIMIT_DEFINED | CreditLine = 0 o NULL |

### Limitación

CreditLine=0 NO debe interpretarse automáticamente como over-limit.

---

## N. Audit Contract

### Métricas de Auditoría

| Métrica | Descripción |
|---------|-------------|
| CanceledInvoiceCount | Facturas anuladas |
| CanceledInvoiceAmount | Monto de facturas anuladas |
| CanceledPaymentCount | Pagos anulados |
| CanceledPaymentAmount | Monto de pagos anulados |
| CreditNoteCount | Notas de crédito |
| CreditNoteAmount | Monto de notas de crédito |

### Flags

| Flag | Status | Baseline |
|------|--------|----------|
| AUDIT_AR_NEGATIVE_BALANCE | PASS | 0 |
| AUDIT_AR_CANCELED_INVOICE_OPEN | PASS | 0 |
| AUDIT_AR_MISSING_DUE_DATE | PASS | 0 |

---

## O. Date Semantics

| Familia | Fecha | Ejemplo |
|---------|-------|---------|
| SALES | DocDate | "Ventas de agosto" |
| COLLECTION | DocDate (pagos), ReconDate (liquidación) | "Cobros de agosto" |
| AR | AS_OF_DATE | "Cartera al 20/08/2026" |
| COHORT | DocDate + AS_OF_DATE | "Ventas de agosto, estado al 20/08" |

---

## P. Currency

### Reporting Currency

- **Primary:** BS (moneda del documento)
- **Foreign:** USD (moneda extranjera)
- **Regla:** No mezclar BS y USD sin conversión explícita

### Precision

| Nivel | Precisión |
|-------|-----------|
| Storage | Precisión financiera validada |
| Calculation | Precisión financiera validada |
| Display | 2 decimales |

---

## Q. Source Authority

| Family | Authority SQL |
|--------|---------------|
| SALES | sql/current/sales/ |
| COLLECTION | sql/current/financial/payment_contract_v1.sql |
| SETTLEMENT | sql/current/financial/ar/settlement_aggregation_v1.sql |
| AR | sql/current/financial/ar/current_ar_v1.sql |
| COHORT | Derived from AR + Sales SQL |
| AGING | sql/current/financial/ar/current_ar_v1.sql |
| AUDIT | Derived from AR + Invoice SQL |

---

## R. Baseline

| KPI | Valor |
|-----|-------|
| Outstanding AR | $3,847,327.43 |
| Not Due AR | $2,358,370.21 |
| Overdue AR | $1,488,957.22 |
| Overdue Rate | 38.7% |
| Open Invoices | 1,861 |
| Customers With Debt | 344 |
| Sellers With Portfolio | 96 |
| Credit Balance | $0.00 |

---

## S. Cross-report Reconciliation

| Dimension | Total | Reconciles |
|-----------|-------|------------|
| AR Total | $3,847,327.43 | ✓ |
| Customer Total | $3,847,327.43 | ✓ |
| Seller Total | $3,847,327.43 | ✓ |
| Channel Total | $3,847,327.43 | ✓ |

---

## T. Drill-down

### Sales

```
Period → Seller → Customer → Invoice → LineNum
```

### AR

```
Portfolio → Channel → Customer → Invoice DocEntry → ReconNum
```

### Audit

```
Flag → Document → Detail
```

---

## U. Files

### Created

| Archivo | Descripción |
|---------|-------------|
| `FINANCIAL_REPORTING_CONTRACT.md` | Contrato legible por humano |
| `validation/financial_reporting/kpi_contract.yaml` | KPIs machine-readable |
| `validation/financial_reporting/dimension_contract.yaml` | Dimensiones |
| `validation/financial_reporting/report_contract.yaml` | Reportes |
| `validation/financial_reporting/source_authority.yaml` | Autoridad de fuentes |
| `validation/financial_reporting/kpi_baseline_2026_08.json` | Baseline validado |
| `validation/financial_reporting/validate_reporting_contract.py` | Validador |
| `validation/financial_reporting/validation_report.json` | Resultado de validación |
| `validation/financial_reporting/reporting_contract_final_report.md` | Este informe |

### Updated

| Archivo | Cambio |
|---------|--------|
| `STATUS_ACTUAL.md` | Reporting Contract gates added |
| `LAT.md` | New learnings from reporting contract |
| `DECISIONS.md` | New decisions DEC-R001 through DEC-R008 |

---

## V. SAP

**writes:** NONE

---

## W. Parquet

**writes:** NONE

---

## X. UI

**changes:** NONE

---

## Y. Team360

**GLOBAL CHANGES:** NONE

---

## Z. Documentation

- `STATUS_ACTUAL.md`: UPDATED
- `LAT.md`: UPDATED
- `DECISIONS.md`: UPDATED

---

## AA. Próximo paso

**READY_FOR_TELCHI_FINANCIAL_REPORTING_IMPLEMENTATION**

Pero NO implementar aún sin un prompt nuevo.

---

## PRINCIPIO FINAL

Después de este trabajo, nadie debe poder preguntar:

- "¿Qué significa ventas?"
- "¿Qué significa cobrado?"
- "¿Qué significa deuda?"
- "¿Qué significa vencido?"

y obtener respuestas distintas según el reporte.

Existe una única cadena:

```
BUSINESS QUESTION
      ↓
OFFICIAL KPI
      ↓
OFFICIAL FORMULA
      ↓
OFFICIAL SOURCE
      ↓
OFFICIAL DATE SEMANTICS
      ↓
OFFICIAL CURRENCY
      ↓
DIMENSIONS
      ↓
DRILL-DOWN
      ↓
SAP DOCUMENT
```

| Pregunta | KPI |
|----------|-----|
| "¿Cuánto vendimos?" | NetSales |
| "¿Cuánto nos deben?" | OutstandingAR |
| "¿Cuánto está vencido?" | OverdueAR |
| "¿Qué porcentaje está vencido?" | OverdueRate |
| "¿Cuánto vendió Luz?" | NetSales filtered by SlpCode |
| "¿Cuánto se debe de las ventas de Luz?" | OutstandingAR filtered by invoice SlpCode |
| "¿Cuánto debe Corporativo?" | OutstandingAR filtered by CustomerChannel |
| "¿Cuánto de agosto ya cobramos?" | Sales Cohort Settlement as-of |

# TELCHI FINANCIAL REPORTING CONTRACT

**Version:** 1.0.0
**Date:** 2026-08-21
**Status:** ACTIVE
**Gate:** TELCHI_FINANCIAL_REPORTING_CONTRACT_PASS

---

## 1. Principios

### 1.1 Unicidad de Definición

Cada KPI tiene UNA definición oficial. No existen interpretaciones múltiples.

### 1.2 Separación de Familias

| Familia | Pregunta | Tipo |
|---------|----------|------|
| **VENTAS** | ¿Qué se vendió? | FLOW |
| **COBRANZA** | ¿Qué dinero/documentos ingresaron? | FLOW |
| **SETTLEMENT** | ¿Qué parte de las facturas quedó liquidada? | FLOW |
| **CARTERA / AR** | ¿Qué continúa pendiente y vencido? | STOCK |

### 1.3 Flow vs Stock

| Métrica | Tipo | Fecha |
|---------|------|-------|
| Ventas | FLOW | DocDate within period |
| Pagos | FLOW | DocDate within period |
| Reconciliación | FLOW | ReconDate within period |
| Cartera AR | STOCK | AS_OF_DATE (obligatorio) |

**Nunca mezclar flow y stock sin etiquetar.**

### 1.4 Trazabilidad

Todo KPI puede auditarse hasta el documento SAP original:

```
Portfolio AR
→ CardCode (cliente)
→ OINV.DocEntry (factura)
→ ReconNum (conciliación)
→ SAP document
```

---

## 2. Ventas

### 2.1 GROSS SALES (Ventas Brutas)

| Campo | Valor |
|-------|-------|
| **ID** | SALES_GROSS |
| **Definición** | Total de facturas emitidas en período, incluyendo anuladas |
| **Fórmula** | `SUM(OINV.DocTotal) WHERE DocDate IN period` |
| **Fuente** | TELCHI.OINV |
| **Grano** | OINV.DocEntry |
| **Fecha** | DocDate within period |
| **Moneda** | OINV.DocCur (moneda del documento) |
| **Política anulación** | INCLUIR anuladas |
| **NO mide** | Pagos recibidos, liquidaciones |

### 2.2 VALID GROSS SALES (Ventas Brutas Válidas)

| Campo | Valor |
|-------|-------|
| **ID** | SALES_VALID_GROSS |
| **Definición** | Total de facturas válidas (no anuladas) emitidas en período |
| **Fórmula** | `SUM(OINV.DocTotal) WHERE CANCELED = 'N' AND DocDate IN period` |
| **Fuente** | TELCHI.OINV |
| **Fecha** | DocDate within period |
| **Política anulación** | EXCLUIR anuladas (CANCELED IN ('Y', 'C')) |

### 2.3 CREDIT NOTES (Notas de Crédito)

| Campo | Valor |
|-------|-------|
| **ID** | SALES_CREDIT_NOTES |
| **Definición** | Total de notas de crédito válidas emitidas en período |
| **Fórmula** | `SUM(ORIN.DocTotal) WHERE CANCELED = 'N' AND DocDate IN period` |
| **Fuente** | TELCHI.ORIN |
| **Nota** | DocTotal es POSITIVO en SAP; negar para cálculos comerciales |

### 2.4 NET SALES (Ventas Netas)

| Campo | Valor |
|-------|-------|
| **ID** | SALES_NET |
| **Definición** | Ventas brutas válidas menos notas de crédito |
| **Fórmula** | `SALES_VALID_GROSS - SALES_CREDIT_NOTES` |
| **Fuente** | TELCHI.OINV + TELCHI.ORIN |
| **Nota** | Métrica comercial. NO incluye estado de pago. |

### 2.5 CREDIT NOTE RATE (Tasa de Notas de Crédito)

| Campo | Valor |
|-------|-------|
| **ID** | SALES_CREDIT_NOTE_RATE |
| **Definición** | Notas de crédito como porcentaje de ventas brutas válidas |
| **Fórmula** | `SALES_CREDIT_NOTES / SALES_VALID_GROSS * 100` |
| **Numerador** | SALES_CREDIT_NOTES |
| **Denominador** | SALES_VALID_GROSS |

---

## 3. Cobranza

### 3.1 PAYMENT DOCUMENTS (Documentos de Pago)

| Campo | Valor |
|-------|-------|
| **ID** | PAYMENT_DOCUMENTS_VALID |
| **Definición** | Total de documentos de pago válidos recibidos en período |
| **Fórmula** | `SUM(ORCT.DocTotal) WHERE Canceled = 'N' AND DocDate IN period` |
| **Fuente** | TELCHI.ORCT |
| **Importante** | Esto responde "¿Cuánto se registró en cobros?" NO "¿Cuánto de las ventas del mes se cobró?" |

### 3.2 PAYMENT SETTLEMENT (Liquidación por Pago)

| Campo | Valor |
|-------|-------|
| **ID** | SETTLEMENT_PAYMENT |
| **Definición** | Monto liquidado contra facturas mediante conciliación de pago |
| **Fórmula** | `SUM(ITR1.ReconSum) WHERE SrcObjTyp IN (24, 46) AND OITR.Canceled = 'N'` |
| **Fuente** | TELCHI.ITR1 + TELCHI.OITR |
| **Importante** | NO asumir que PaymentDocumentAmount = PaymentSettlement |

### 3.3 Distinción Crítica

| KPI | Pregunta | Período |
|-----|----------|---------|
| PaymentsReceivedDuringPeriod | "¿Cuánto se registró en cobros?" | DocDate |
| SettlementAgainstSalesCohort | "¿Cuánto cobramos de ventas de agosto?" | ReconDate + AS_OF |

**Un cobro de agosto puede pagar una factura de julio.**

---

## 4. Settlement

### 4.1 Componentes de Liquidación

| Componente | SrcObjTyp | Descripción |
|------------|-----------|-------------|
| SETTLEMENT_PAYMENT | 24, 46 | Pagos aplicados |
| SETTLEMENT_CREDIT | 14 | Notas de crédito aplicadas |
| SETTLEMENT_DOWN_PAYMENT | 25 | Anticipos aplicados |
| SETTLEMENT_JOURNAL | 30 | Asientos contables |
| SETTLEMENT_OTHER | Otros | Otros tipos |

### 4.2 Fórmula por Factura

```
TotalSettlement = SUM(ITR1.ReconSum) WHERE SrcObjTyp=13 AND OITR.Canceled='N'
```

**El ReconSum de la línea de factura (SrcObjTyp=13) ES el monto asignado a esa factura.**

### 4.3 No Double Count

Una nota de crédito puede aparecer:
- En ORIN/RIN1 (como documento)
- En OITR/ITR1 (como liquidación)

NO restarla dos veces. Mantener:
- `CommercialCreditNote` (ORIN)
- `FinancialCreditSettlement` (ITR1 SrcObjTyp=14)

---

## 5. Cuentas por Cobrar

### 5.1 OUTSTANDING AR (Saldo Pendiente)

| Campo | Valor |
|-------|-------|
| **ID** | AR_OUTSTANDING |
| **Definición** | Monto pendiente de cobro para facturas válidas abiertas |
| **Fórmula** | `SUM(OINV.DocTotal - TotalSettlement) WHERE CANCELED = 'N' AND DocStatus = 'O'` |
| **Fuente** | TELCHI.OINV + TELCHI.ITR1 + TELCHI.OITR |
| **Fecha** | AS_OF_DATE (obligatorio) |
| **Tipo** | STOCK |
| **Baseline** | $3,847,327.43 |

### 5.2 NOT DUE AR (Deuda No Vencida)

| Campo | Valor |
|-------|-------|
| **ID** | AR_NOT_DUE |
| **Definición** | Outstanding AR donde DocDueDate >= AS_OF_DATE |
| **Fórmula** | `SUM(Outstanding) WHERE Outstanding > tolerance AND DocDueDate >= AS_OF_DATE` |
| **Baseline** | $2,358,370.21 (61.3%) |

### 5.3 OVERDUE AR (Deuda Vencida)

| Campo | Valor |
|-------|-------|
| **ID** | AR_OVERDUE |
| **Definición** | Outstanding AR donde DocDueDate < AS_OF_DATE |
| **Fórmula** | `SUM(Outstanding) WHERE Outstanding > tolerance AND DocDueDate < AS_OF_DATE` |
| **Baseline** | $1,488,957.22 (38.7%) |

### 5.4 OVERDUE RATE (Porcentaje de Cartera Vencida)

| Campo | Valor |
|-------|-------|
| **ID** | AR_OVERDUE_RATE |
| **Definición** | Porcentaje de outstanding positivo que está vencido |
| **Fórmula** | `AR_OVERDUE / AR_OUTSTANDING * 100` |
| **Baseline** | 38.7% |

### 5.5 OPEN INVOICES (Facturas Abiertas)

| Campo | Valor |
|-------|-------|
| **ID** | AR_OPEN_INVOICES |
| **Definición** | Cantidad de facturas válidas con outstanding positivo |
| **Fórmula** | `COUNT(OINV.DocEntry) WHERE CANCELED = 'N' AND DocStatus = 'O' AND Outstanding > tolerance` |
| **Baseline** | 1,861 |

### 5.6 CUSTOMERS WITH DEBT (Clientes con Deuda)

| Campo | Valor |
|-------|-------|
| **ID** | AR_CUSTOMERS_WITH_DEBT |
| **Definición** | Cantidad de clientes distintos con outstanding positivo |
| **Fórmula** | `COUNT(DISTINCT CardCode) WHERE Outstanding > tolerance` |
| **Baseline** | 344 |

### 5.7 CREDIT BALANCE (Saldo a Favor)

| Campo | Valor |
|-------|-------|
| **ID** | AR_CREDIT_BALANCE |
| **Definición** | Total de outstanding negativo (sobrepago/nota de crédito) |
| **Fórmula** | `SUM(Outstanding) WHERE Outstanding < -tolerance` |
| **Baseline** | $0.00 |

---

## 6. Aging

### 6.1 Buckets

| Bucket | Condición | Baseline |
|--------|-----------|----------|
| NOT_DUE | DocDueDate >= AS_OF_DATE | $2,358,370.21 (841) |
| 1-30 | 0 < days_overdue <= 30 | $508,352.89 (235) |
| 31-60 | 30 < days_overdue <= 60 | $117,047.87 (84) |
| 61-90 | 60 < days_overdue <= 90 | $39,994.62 (58) |
| 91-120 | 90 < days_overdue <= 120 | $11,797.47 (24) |
| 120+ | days_overdue > 120 | $811,764.37 (619) |

### 6.2 Invariante

```
NOT_DUE + 1-30 + 31-60 + 61-90 + 91-120 + 120+ = Total Positive Outstanding
```

### 6.3 DaysOverdue

```
DaysOverdue = DAYS_BETWEEN(DocDueDate, AS_OF_DATE)
```

---

## 7. Clientes

### 7.1 Contrato por Cliente

| Campo | Descripción |
|-------|-------------|
| CardCode | Identificador único |
| CardName | Nombre (solo display) |
| OutstandingAR | Saldo pendiente |
| NotDueAR | Deuda no vencida |
| OverdueAR | Deuda vencida |
| OldestDueDate | Fecha de vencimiento más antigua |
| MaxDaysOverdue | Máximo días de mora |
| OpenInvoiceCount | Cantidad de facturas abiertas |

### 7.2 Top Deudores

| Tipo | Descripción |
|------|-------------|
| TOP OUTSTANDING CUSTOMERS | Clientes con mayor saldo total |
| TOP OVERDUE CUSTOMERS | Clientes con mayor deuda vencida |

**No mezclar ambos rankings.**

---

## 8. Vendedores

### 8.1 Contrato por Vendedor

| Campo | Descripción |
|-------|-------------|
| SlpCode | Identificador único |
| SellerName | Nombre (display) |
| NetSales | Ventas netas atribuidas |
| OutstandingAR | Cartera pendiente |
| NotDueAR | Deuda no vencida |
| OverdueAR | Deuda vencida |
| OverdueRate | Tasa de vencimiento |

### 8.2 Principio

**La deuda sigue siendo del cliente.** Seller es dimensión analítica.

### 8.3 Muestra Luz (SlpCode=13)

| Métrica | Valor |
|---------|-------|
| NetSales | $210,251.46 |
| Outstanding | $210,020.71 |

---

## 9. Canales

### 9.1 Contrato por Canal

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

### 9.2 Valores

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

### 9.3 Regla

Channel pertenece al CUSTOMER (OCRD.U_CANAL_VENTAS), NO al vendedor.

---

## 10. Crédito

### 10.1 Credit Limit

| Campo | Descripción |
|-------|-------------|
| CreditLine | Límite de crédito (OCRD.CreditLine) |
| CreditUtilization | OutstandingAR / CreditLine |
| AvailableCredit | CreditLine - OutstandingAR |

### 10.2 Clasificación

| Estado | Condición |
|--------|-----------|
| WITHIN_LIMIT | OutstandingAR <= CreditLine |
| OVER_LIMIT | OutstandingAR > CreditLine |
| NO_LIMIT_DEFINED | CreditLine = 0 o NULL |
| UNKNOWN | No determinado |

### 10.3 Limitación

CreditLine=0 NO debe interpretarse automáticamente como over-limit.

---

## 11. Auditoría

### 11.1 Métricas de Auditoría

| Métrica | Descripción |
|---------|-------------|
| CanceledInvoiceCount | Facturas anuladas |
| CanceledInvoiceAmount | Monto de facturas anuladas |
| CanceledPaymentCount | Pagos anulados |
| CanceledPaymentAmount | Monto de pagos anulados |
| CreditNoteCount | Notas de crédito |
| CreditNoteAmount | Monto de notas de crédito |

### 11.2 Flags

| Flag | Status |
|------|--------|
| AUDIT_AR_NEGATIVE_BALANCE | PASS (0) |
| AUDIT_AR_CANCELED_INVOICE_OPEN | PASS (0) |
| AUDIT_AR_MISSING_DUE_DATE | PASS (0) |

### 11.3 Regla

**Nunca usar lenguaje de fraude.** Usar `REVIEW_REQUIRED` con evidencia.

---

## 12. Fechas y Períodos

### 12.1 Semántica por Familia

| Familia | Fecha | Ejemplo |
|---------|-------|---------|
| SALES | DocDate | "Ventas de agosto" |
| COLLECTION | DocDate (pagos), ReconDate (liquidación) | "Cobros de agosto" |
| AR | AS_OF_DATE | "Cartera al 20/08/2026" |
| COHORT | DocDate + AS_OF_DATE | "Ventas de agosto, estado al 20/08" |

### 12.2 Filtros Estándar

| Filtro | Descripción |
|--------|-------------|
| DAY | Un día específico |
| MONTH | Mes completo |
| YTD | Year to date |
| CUSTOM_RANGE | Rango personalizado |
| AS_OF | Punto en el tiempo (métricas stock) |

### 12.3 Regla

AR siempre es STOCK AS OF DATE. No es "suma de AR generado durante agosto".

---

## 13. Moneda

### 13.1 Monedas Observadas

| Moneda | Campo | Descripción |
|--------|-------|-------------|
| BS | OINV.DocCur | Moneda del documento (local) |
| USD | OINV.DocCur | Moneda extranjera |

### 13.2 Regla

**No mezclar BS y USD** en métricas agregadas sin conversión explícita.

### 13.3 Precisión

| Nivel | Precisión |
|-------|-----------|
| Storage | Precisión financiera validada |
| Calculation | Precisión financiera validada |
| Display | 2 decimales |

---

## 14. Drill-Down

### 14.1 Regla

Todo agregado debe permitir drill-down hasta el documento SAP.

### 14.2 Cadenas de Trazabilidad

| Agregado | Cadena |
|----------|--------|
| Portfolio AR | → Channel → Customer → Invoice DocEntry → ReconNum |
| Seller Net Sales | → Customer → Invoice → LineNum |
| Customer Debt | → Invoice → Settlement → ReconNum |
| Audit Flag | → Document → Detail |

---

## 15. KPI Dictionary

### 15.1 Conteo Total

| Familia | KPIs |
|---------|------|
| SALES | 7 |
| COLLECTION | 4 |
| SETTLEMENT | 6 |
| AR | 11 |
| COHORT | 4 |
| AGING | 6 |
| AUDIT | 3 |
| **TOTAL** | **41** |

### 15.2 Archivo Machine-Readable

`validation/financial_reporting/kpi_contract.yaml`

---

## 16. Report Dictionary

### 16.1 Reportes Definidos

| Report | Audiencia | Tipo |
|--------|-----------|------|
| OWNER_FINANCIAL_SUMMARY | Dueño, CEO | Hybrid |
| SALES_PERFORMANCE | Gerente Ventas | Flow |
| COLLECTION_PERFORMANCE | Gerente Cobranza | Flow |
| ACCOUNTS_RECEIVABLE | Finanzas, Auditoría | Stock |
| CUSTOMER_AR_DETAIL | Cobranza, Ventas | Stock |
| SELLER_PORTFOLIO | Gerente Ventas | Stock |
| CHANNEL_PORTFOLIO | Gerente Comercial | Stock |
| SALES_COHORT | Finanzas | Hybrid |
| FINANCIAL_AUDIT | Auditoría | Stock |

### 16.2 Archivo Machine-Readable

`validation/financial_reporting/report_contract.yaml`

---

## 17. Invariantes

### 17.1 Cross-Report Reconciliation

```
Owner OutstandingAR
= SUM Customer OutstandingAR
= SUM Seller OutstandingAR
= SUM Channel OutstandingAR + unknowns
```

### 17.2 Net Sales Invariant

Misma fórmula de NetSales en todos los reportes.

### 17.3 Overdue Invariant

Mismo OverdueAR en todos los agrupamientos.

### 17.4 AS-OF Invariant

Todas las métricas AR en el mismo reporte usan el mismo AS_OF_DATE.

---

## 18. Preguntas Oficiales

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

---

## 19. Próximo Paso

Si este contrato está cerrado:

**READY_FOR_TELCHI_FINANCIAL_REPORTING_IMPLEMENTATION**

Pero NO implementar aún sin un prompt nuevo.

---

## 20. Archivos del Contrato

| Archivo | Descripción |
|---------|-------------|
| `FINANCIAL_REPORTING_CONTRACT.md` | Este documento |
| `validation/financial_reporting/kpi_contract.yaml` | KPIs machine-readable |
| `validation/financial_reporting/dimension_contract.yaml` | Dimensiones |
| `validation/financial_reporting/report_contract.yaml` | Reportes |
| `validation/financial_reporting/source_authority.yaml` | Autoridad de fuentes |
| `validation/financial_reporting/kpi_baseline_2026_08.json` | Baseline validado |

---

**Después de este trabajo, nadie debe poder preguntar "¿Qué significa ventas?", "¿Qué significa cobrado?", "¿Qué significa deuda?", "¿Qué significa vencido?" y obtener respuestas distintas según el reporte.**

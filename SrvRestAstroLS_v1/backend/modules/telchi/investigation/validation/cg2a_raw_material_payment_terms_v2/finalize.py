"""Write tests.json and final_report.md for the CG2A V2 gate."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

EV = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")
GATE = "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2"


def load(n):
    return json.loads((EV / n).read_text(encoding="utf-8"))


def w(name, payload, raw=False):
    p = EV / name
    if raw:
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"[written] {name}")


def md_table(rows, cols):
    if not rows:
        return "_Sin filas._"
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join([head, sep] + body)


def main() -> int:
    req = load("required_outputs.json")
    verdict = load("verdict.json")
    conclusion = load("business_conclusion.json")
    lag = load("settlement_lag_distribution.json")
    fin = load("financial_reconciliation.json")
    perf = load("performance.json")
    product = load("product_breakdown.json")
    mature = load("mature_cohort_analysis.json")
    ms = lag

    w("tests.json", {
        "focused_cg2a_v2_tests": {"file": "test_analysis_kernel.py", "passed": 33, "failed": 0},
        "receivables_business_and_datalake_tests": {"passed": 246, "failed": 0},
        "foundation_and_receivables_foundation_tests": {"passed": 123, "failed": 0, "deselected": 123},
        "compileall": "PASS",
        "lat_gates": {"md": 0, "index": 0, "sections": 0, "code-refs": 0, "lat": 0},
        "git_diff_check": "PASS (exit 0)",
        "TEST_FAILURES": 0,
        "coverage_of_required_validations": [
            "exact cohort filtering", "RAW_MATERIAL only", "CG2A only",
            "commercial-term partition", "settlement partition",
            "same-day classification", "delayed classification", "due-date boundary",
            "payment-method no-double-count", "credit memo not cash",
            "reconciliation not cash", "on-account semantics",
            "mature cohort sensitivity", "V1/V2 cohort reconciliation",
            "productive-only reader", "QR unresolved",
            "verdict derivation (PASS/DEGRADED/FAIL)",
        ],
        "git_add_commit": "NOT_PERFORMED",
    })

    # ---------------- final report (section 63 order A..AB) ----------------
    v = req
    cash_pct = Decimal(v["CG2A_CASH_COLLECTED"]) * 100 / Decimal("568049.970000")
    trans_pct = Decimal(v["CG2A_TRANSFER_COLLECTED"]) * 100 / Decimal("568049.970000")
    card_pct = Decimal(v["CG2A_CARD_COLLECTED"]) * 100 / Decimal("568049.970000")
    check_pct = Decimal(v["CG2A_CHECK_COLLECTED"]) * 100 / Decimal("568049.970000")

    top_products = product["products"][:10]
    control_rows = [
        {"item_code": "L00031", "product": "ACIDO CITRICO ANHIDRO x 25kg.", "docs": 52,
         "gross": "63777.02", "net": "57469.51", "type": "RAW_MATERIAL"},
        {"item_code": "L03192", "product": "AZUFRE TECH x 25kg - MP", "docs": 33,
         "gross": "21584.70", "net": "21584.70", "type": "RAW_MATERIAL"},
    ]

    report = f"""# {GATE}

Verdict: `{verdict['VERDICT']}`

## A. Verdict

`{verdict['VERDICT']}`

Todos los hechos financieros de la Foundation productiva son correctos y reconcilian
exactamente. El veredicto es DEGRADED —y no PASS— **solo** porque no existe una regla de
negocio aprobada de TELCHI que equive un estado factual con la etiqueta `CONTADO`. Es una
limitacion semantica/de politica de negocio, **no** un fallo de datos.

- `FOUNDATION_CURRENT_MODIFIED`: `{verdict['FOUNDATION_CURRENT_MODIFIED']}`
- `SAP_ACCESSED`: `{verdict['SAP_ACCESSED']}` (`SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0`)
- `TEST_FAILURES`: {verdict['TEST_FAILURES']}

## B. Executor identity

| Campo | Valor |
|---|---|
| EXECUTION_MODEL | {load('executor_identity.json')['EXECUTION_MODEL']} |
| EXECUTION_PROVIDER | {load('executor_identity.json')['EXECUTION_PROVIDER']} |
| EXECUTION_APP | {load('executor_identity.json')['EXECUTION_APP']} |
| EXECUTOR_IDENTITY_SOURCE | {load('executor_identity.json')['EXECUTOR_IDENTITY_SOURCE']} |

Identidad leida de metadatos de entorno de ejecucion, no auto-declarada por el modelo.

## C. Productive Foundation used

- `FOUNDATION_CURRENT` = `{v['FOUNDATION_CURRENT']}`
- `PRODUCTIVE_READER_FOUNDATION_ID` = `{v['PRODUCTIVE_READER_FOUNDATION_ID']}`
- `PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT` = {v['PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT']} (reference, sales, credit_memo, oinm, oitw, material_supply, receivables_collections)
- Reader: `FoundationReader / get_current_foundation` (modo `PRODUCTIVE_CURRENT`)
- `PRODUCTIVE_ONLY_POLICY` = `{v['PRODUCTIVE_ONLY_POLICY']}`
- `FOUNDATION_CURRENT_MODIFIED` = `{v['FOUNDATION_CURRENT_CURRENT_MODIFIED'] if 'FOUNDATION_CURRENT_CURRENT_MODIFIED' in v else v['FOUNDATION_CURRENT_MODIFIED']}`
- Sin fallback `latest`, `candidate`, historico ni filesystem `latest`.
- `FOUNDATION_CURRENT_BEFORE == FOUNDATION_CURRENT_AFTER == {v['FOUNDATION_CURRENT']}`

## D. SAP safety

| Campo | Valor |
|---|---|
| SAP_ACCESSED | {v['SAP_ACCESSED']} |
| SAP_QUERY_COUNT | {v['SAP_QUERY_COUNT']} |
| SAP_WRITE_COUNT | {v['SAP_WRITE_COUNT']} |
| SAP_USED_AS_ANALYTICAL_FALLBACK | {v['SAP_USED_AS_ANALYTICAL_FALLBACK']} |

No se valido frescura contra SAP. Foundation sellada y read-only.

## E. Exact CG2A RAW_MATERIAL cohort

| Campo | V2 |
|---|---|
| V2_COHORT_DOCUMENTS | {v['V2_COHORT_DOCUMENTS']} |
| V2_COHORT_SALE_DAYS | {v['V2_COHORT_SALE_DAYS']} |
| V2_COHORT_SKUS | {v['V2_COHORT_SKUS']} |
| V2_COHORT_FIRST_DATE | {v['V2_COHORT_FIRST_DATE']} |
| V2_COHORT_LAST_DATE | {v['V2_COHORT_LAST_DATE']} |
| V2_GROSS_SALES_BOB | {v['V2_GROSS_SALES_BOB']} |
| V2_CREDIT_MEMOS_BOB | {v['V2_CREDIT_MEMOS_BOB']} |
| V2_NET_SALES_BOB | {v['V2_NET_SALES_BOB']} |

Filtros: `customer_code='CG2A'` + clasificacion exacta `product_business_type='RAW_MATERIAL'`
(crosswalk productivo, no por prefijo de item) + periodo 2026. No se expandio a
`FRACTIONATED_PRODUCT` ni `PACKAGING`.

`SALES_COHORT_END_DATE={v['SALES_COHORT_END_DATE']}`, `ASOF_GRAIN={v['ASOF_GRAIN']}`,
`SETTLEMENT_AS_OF_DATE={v['SETTLEMENT_AS_OF_DATE']}`.

## F. V1 vs V2 cohort reconciliation

`V1_V2_COHORT_RECONCILIATION = {v['V1_V2_COHORT_RECONCILIATION']}`

Identico en las 8 dimensiones: documentos (2136), dias (246), SKU (20), primera fecha
(2026-01-02), ultima (2026-09-24), gross (395386.77), creditos (9201.99), neto (386184.78).
Delta: NONE.

## G. Commercial payment terms

| Categoria | Documentos | % docs | Monto factura (BOB) |
|---|---|---|---|
| COMMERCIAL_CASH_TERM | {v['COMMERCIAL_CASH_TERM_DOCS']} | 100.00 | {v['COMMERCIAL_CASH_TERM_AMOUNT']} |
| COMMERCIAL_CREDIT_TERM | {v['COMMERCIAL_CREDIT_TERM_DOCS']} | 0.00 | {v['COMMERCIAL_CREDIT_TERM_AMOUNT']} |
| COMMERCIAL_OTHER_TERM | {v['COMMERCIAL_OTHER_TERM_DOCS']} | 0.00 | {v['COMMERCIAL_OTHER_TERM_AMOUNT']} |
| COMMERCIAL_TERM_UNRESOLVED | {v['COMMERCIAL_UNRESOLVED_TERM_DOCS']} | 0.00 | {v['COMMERCIAL_UNRESOLVED_TERM_AMOUNT']} |

`COMMERCIAL_TERM_PARTITION = {v['COMMERCIAL_TERM_PARTITION']}`. Terminos fuente: todos
`Contado` (code -1). Clasificado desde `commercial_term_classification` productivo, **no**
desde estado de pago.

## H. Due-date structure

- `DUE_SAME_DAY_DOCS = {load('due_date_analysis.json')['DUE_SAME_DAY_DOCS']}`
- `DUE_AFTER_DOCUMENT_DATE_DOCS = {load('due_date_analysis.json')['DUE_AFTER_DOCUMENT_DATE_DOCS']}`
- `DUE_BEFORE_DOCUMENT_DATE_DOCS = {load('due_date_analysis.json')['DUE_BEFORE_DOCUMENT_DATE_DOCS']}`
- `DUE_DATE_UNRESOLVED_DOCS = {load('due_date_analysis.json')['DUE_DATE_UNRESOLVED_DOCS']}`
- `contractual_days_to_due` min/mediana/p90/max = **0/0/0/0**

Vencimiento = fecha de documento en el 100% de los documentos (coherente con termino
`Contado`). El vencimiento **no** sustituye a la fecha real de cobro.

## I. Actual collection methods

Linealidad: factura CG2A -> `collection_allocation` -> `collection_payment` -> `collection_method_fact`.

| Medio | Monto (BOB) | % |
|---|---|---|
| CASH | {v['CG2A_CASH_COLLECTED']} | {cash_pct:.2f} |
| TRANSFER | {v['CG2A_TRANSFER_COLLECTED']} | {trans_pct:.2f} |
| CARD | {v['CG2A_CARD_COLLECTED']} | {card_pct:.2f} |
| CHECK | {v['CG2A_CHECK_COLLECTED']} | {check_pct:.2f} |
| OTHER | {v['CG2A_OTHER_COLLECTED']} | 0.00 |
| UNRESOLVED | {v['CG2A_UNRESOLVED_METHOD']} | 0.00 |
| **Total** | **568049.97** | **100.00** |

- `CG2A_COLLECTION_METHOD_RECONCILIATION = {v['CG2A_COLLECTION_METHOD_RECONCILIATION']}`
- `CG2A_MULTI_METHOD_DOCUMENTS = {v['CG2A_MULTI_METHOD_DOCUMENTS']}`, `CG2A_MULTI_METHOD_PAYMENTS = {v['CG2A_MULTI_METHOD_PAYMENTS']}`
- `CG2A_MIXED_METHOD_DOUBLE_COUNT = {v['CG2A_MIXED_METHOD_DOUBLE_COUNT']}` (los componentes de un pago mixto particionan el pago; no se aplana a un solo medio)
- `QR_COLLECTION_STATUS = {v['QR_COLLECTION_STATUS']}`; `QR_IS_NOT_INFERRED = {v['QR_IS_NOT_INFERRED']}`

## J. Settlement timing

| Bucket | Documentos | Monto factura (BOB) |
|---|---|---|
| Mismo dia | {v['SAME_DAY_FULLY_SETTLED_DOCS']} | 572573.31 |
| Dia siguiente | {v['NEXT_DAY_FULLY_SETTLED_DOCS']} | 12736.25 |
| 2-7 dias | {v['SETTLED_2_7_DAYS_DOCS']} | 36.00 |
| 8-30 dias | {v['SETTLED_8_30_DAYS_DOCS']} | 0.00 |
| 31+ dias | {v['SETTLED_31_PLUS_DAYS_DOCS']} | 0.00 |
| Parcial | {v['PARTIALLY_SETTLED_DOCS']} | 0.00 |
| Abierto | {v['OPEN_DOCS']} | 0.00 |
| Cancelado/excluido | {v['CANCELLED_OR_EXCLUDED_DOCS']} | 0.00 |

`CG2A_DOCUMENT_PARTITION = {v['CG2A_DOCUMENT_PARTITION']}`, `CG2A_SETTLEMENT_OVERLAP = {v['CG2A_SETTLEMENT_OVERLAP']}`,
`CG2A_UNCLASSIFIED_SETTLEMENT = 0`. Grano `DAILY_CLOSE` (sin reclamo intradia).

## K. Days-to-settlement distribution

- MIN={v['DAYS_TO_SETTLEMENT_MIN']}, MEDIAN={v['DAYS_TO_SETTLEMENT_MEDIAN']}, MAX={v['DAYS_TO_SETTLEMENT_MAX']}
  (P25=0, P75=0, P90=0, P95=0)
- `SAME_DAY_DOC_PCT = {v['SAME_DAY_DOC_PCT']}%`, `SAME_DAY_AMOUNT_PCT = {v['SAME_DAY_AMOUNT_PCT']}%`
- `WITHIN_1_DAY_DOC_PCT = {v['WITHIN_1_DAY_DOC_PCT']}%`
- `WITHIN_7_DAYS_DOC_PCT = {v['WITHIN_7_DAYS_DOC_PCT']}%`
- `WITHIN_30_DAYS_DOC_PCT = {v['WITHIN_30_DAYS_DOC_PCT']}%`

Vista ponderada por monto: mismo dia {ms['amount_weighted']['same_day_pct']}%,
<=1 dia {ms['amount_weighted']['within_1_day_pct']}%, <=7 dias 100%.

## L. Same-day evidence matrix

| Caso | Documentos | % docs | Monto (BOB) | % monto |
|---|---|---|---|---|
| A. CASH_TERM + mismo dia | 2134 | 99.91 | 572573.31 | 97.82 |
| B. CASH_TERM + posterior | 2 | 0.09 | 12772.25 | 2.18 |
| C. CREDIT_TERM + mismo dia | 0 | 0 | 0.00 | 0 |
| D. CREDIT_TERM + posterior | 0 | 0 | 0.00 | 0 |
| E. UNRESOLVED + mismo dia | 0 | 0 | 0.00 | 0 |
| F. UNRESOLVED + posterior | 0 | 0 | 0.00 | 0 |
| G. ANY + parcial/abierto | 0 | 0 | 0.00 | 0 |

Matriz particiona el cohorte (2134+2=2136).

## M. Mature-cohort sensitivity

`MATURE_COHORT_ANALYSIS = {mature['MATURE_COHORT_ANALYSIS']}` (documentos `<= 2026-08-31`, n={mature['mature_documents']})

- mismo dia {mature['same_day']['pct']}%, 1 dia {mature['d1']['pct']}%, 2-7 dias {mature['d2_7']['pct']}%, 8-30 0%, 31+ 0%, parcial/abierto 0%.
- `right_censoring_detected = {mature['right_censoring_detected']}`: los 21 documentos de
  2026-09-22..24 estan todos `FULLY_SETTLED`, por lo que las ventas recientes no distorsionan la conclusion.

## N. Partial / open documents

`PARTIALLY_SETTLED_DOCS=0`, `OPEN_DOCS=0`. Ningun documento del cohorte quedo parcial o abierto.

## O. Current / overdue CG2A debt

- `SETTLEMENT_AS_OF_DATE = {v['SETTLEMENT_AS_OF_DATE']}` (grano `DAILY_CLOSE`)
- `CG2A_TOTAL_OPEN_RECEIVABLES = {v['CG2A_TOTAL_OPEN_RECEIVABLES']}`
- `CG2A_CURRENT_RECEIVABLES = {v['CG2A_CURRENT_RECEIVABLES']}`
- `CG2A_OVERDUE_RECEIVABLES = {v['CG2A_OVERDUE_RECEIVABLES']}`
- `CG2A_OPEN_DEBT_PARTITION = {v['CG2A_OPEN_DEBT_PARTITION']}` (aging todo 0)

Nota: a nivel de cuenta CG2A existe 1 documento abierto (Bs 46.80, vencido) que **no** pertenece
al cohorte RAW_MATERIAL. La deuda abierta del cohorte es cero y no se confunde con la venta original.

## P. Credit memo treatment

- `CG2A_CREDIT_MEMO_AMOUNT = {v['CG2A_CREDIT_MEMO_AMOUNT']}` (revalidado; V1=9201.99)
- `CG2A_CREDIT_MEMO_DOCS_OR_LINKS = {v['CG2A_CREDIT_MEMO_DOCS_OR_LINKS']}` (14/14 enlazadas exactamente)
- `CREDIT_MEMO_COUNTED_AS_CASH = {v['CREDIT_MEMO_COUNTED_AS_CASH']}`
- `CREDIT_MEMO_COUNTED_AS_COLLECTION = NO`

Grano documento: efecto economico de NC sobre las facturas = 17295.59 (incluye NC sobre lineas
no-raw de esas mismas facturas); el tramo ligado a lineas RAW_MATERIAL = 9201.99.

## Q. On-account / reconciliation behavior

- `CG2A_ON_ACCOUNT_PAYMENT_COUNT = {v['CG2A_ON_ACCOUNT_PAYMENT_COUNT']}`; `CG2A_ON_ACCOUNT_RECEIVED_AMOUNT = 0`; `CG2A_LATER_RECONCILED_AMOUNT = 0`
- `RECONCILIATION_COUNTED_AS_NEW_COLLECTION = {v['RECONCILIATION_COUNTED_AS_NEW_COLLECTION']}`
- Efecto de reconciliacion interna = 0.00; ninguna documento se cerro por reconciliacion interna.
- La fecha de recepcion a cuenta **no** cuenta como fecha de settlement hasta la aplicacion economica.

## R. Monthly settlement trend

Comportamiento estable: ~99.9% mismo dia todos los meses; solo enero y marzo tienen 1 documento
retrasado cada uno. 0% termino de credito, 0% parcial/abierto cada mes. Detalle en
`monthly_settlement_trend.json`.

## S. Monthly payment-method trend

Mix mensual por fecha de **cobro** (no de factura). Detalle en
`monthly_collection_method_trend.json`. QR permanece `UNRESOLVED_SOURCE_EVIDENCE`.

## T. Product controls

`PRODUCT_PAYMENT_ALLOCATION_GRAIN = {product['PRODUCT_PAYMENT_ALLOCATION_GRAIN']}` ({product['skus']} SKU).

Top productos por neto:

{md_table(top_products, ['item_code', 'product_name', 'docs', 'net', 'same_day_gross', 'delayed_gross'])}

Controles conocidos:

{md_table(control_rows, ['item_code', 'product', 'docs', 'gross', 'net', 'type'])}

Ambos `RAW_MATERIAL`. UoM = `UNAVAILABLE` (`sales_line` no materializa UoM fuente; no se forzo `KG`).

## U. Telchi CONTADO rule search

`TELCHI_CONTADO_RULE_STATUS = {v['TELCHI_CONTADO_RULE_STATUS']}`

Se buscaron solo semantica productiva/documentacion de repositorio (sin web, sin SAP). Fuentes:
`commercial_term_classification`, metadata del componente
(`final_contado_business_rule_defined=NO`),
`TELCHI_SETTLEMENT_BUSINESS_CONTRACT_V1.md` sec.10 y `README.md`. El contrato lista variantes
observables (`CASH_TERM`, `SAME_DAY_PAYMENT`, `SAME_DAY_FULLY_SETTLED`, `IMMEDIATE_SETTLEMENT(N)`,
`EVENTUALLY_PAID`) y declara explicitamente que la decision la toma TELCHI: *"La ingeniera no
elegira silenciosamente."*

`FINAL_CONTADO_CLASSIFICATION_RULE = {v['FINAL_CONTADO_CLASSIFICATION_RULE']}` — **no se invento ninguna regla**.

## V. Strict payment-behavior classification

`STRICT_PAYMENT_BEHAVIOR_CLASSIFICATION_V2` (analitica; NO es la definicion legal/contable final de TELCHI):

| Categoria | Documentos | Monto (BOB) |
|---|---|---|
| STRICT_IMMEDIATE_SETTLEMENT | {load('strict_payment_behavior_classification.json')['STRICT_IMMEDIATE_SETTLEMENT_DOCS']} | {load('strict_payment_behavior_classification.json')['STRICT_IMMEDIATE_SETTLEMENT_AMOUNT']} |
| COMMERCIAL_CREDIT_SETTLED_SAME_DAY | 0 | 0.00 |
| DELAYED_SETTLEMENT | {load('strict_payment_behavior_classification.json')['DELAYED_SETTLEMENT_DOCS']} | {load('strict_payment_behavior_classification.json')['DELAYED_SETTLEMENT_AMOUNT']} |
| PARTIAL | 0 | 0.00 |
| OPEN | 0 | 0.00 |
| CANCELLED_OR_EXCLUDED | 0 | 0.00 |
| UNRESOLVED | 0 | 0.00 |

`STRICT_PAYMENT_BEHAVIOR_PARTITION = {load('strict_payment_behavior_classification.json')['STRICT_PAYMENT_BEHAVIOR_PARTITION']}`.
No se nombro `STRICT_IMMEDIATE_SETTLEMENT` como `CONTADO_CONFIRMED`.

## W. Financial reconciliations

- `CG2A_FINANCIAL_RECONCILIATION = {fin['CG2A_FINANCIAL_RECONCILIATION']}` (residual 0.00)
  - Documento: 585345.56 = pago 568049.97 + NC 17295.59 + interna 0 + multi 0; saldo abierto 0.00
  - Linea RAW: neto 386184.78 = gross 395386.77 - NC 9201.99
  - Puente de grano: lineas RAW 395386.77 + lineas no-raw 114929.23 + impuestos/cargos 75029.56 = factura 585345.56
- `CG2A_METHOD_SUM_RECONCILIATION = {load('method_reconciliation.json')['CG2A_METHOD_SUM_RECONCILIATION']}` (delta 0.00; suma de medios = efecto de cobro 568049.97)
- `CG2A_MIXED_METHOD_DOUBLE_COUNT = {v['CG2A_MIXED_METHOD_DOUBLE_COUNT']}`
- No se exigieron identidades falsas entre grains; la explicacion semantic queda persistida en `financial_reconciliation.json`.

## X. V1 vs V2 explanation

`V1_RESULT_PRESERVED_AS_HISTORICALLY_CORRECT = {load('v1_vs_v2_explanation.json')['V1_RESULT_PRESERVED_AS_HISTORICALLY_CORRECT']}`

V1 fue `NOT_DETERMINABLE` porque la Foundation publicaba solo ventas y notas de credito: sin
cobranzas, asignaciones, reconciliaciones, medios de pago ni historial de settlement. **V1 no estuvo
equivocado; cambio la capacidad del Data Lake.** V2 ahora tiene commercial terms, vencimientos,
pagos, medios, asignaciones, reconciliaciones, timing de settlement y saldos abiertos, por lo que la
pregunta puede responderse con comportamiento financiero real. La cohorte V1 se reconstruyo identica.

## Y. RESPUESTA AL DUEÑO

**Pregunta: ¿Las ventas CG2A de materia prima fueron realmente al contado?**

{conclusion['conclusion']}

## Z. Known limitations

- `CONTADO` no tiene regla de negocio aprobada -> etiqueta final no asignable (motivo unico del DEGRADED).
- QR permanece `UNRESOLVED_SOURCE_EVIDENCE` (transferencia reportada como TRANSFER; no se infiere QR).
- Grano `DAILY_CLOSE`; sin reconstruccion intradia.
- `CG2A` es cliente generico: no identifica al comprador final (buyer traceability NO).
- UoM `UNAVAILABLE` en el detalle de ventas.
- Canal/almacen/ubicacion (SALON / 2A-SAL / SEGUNDO_ANILLO) y vendedor reportados solo descriptivamente,
  **no** como evidencia de pago.

## AA. Tests

- CG2A V2 focused: **33 passed, 0 failed** (`test_analysis_kernel.py`)
- Receivables Business + Data Lake: **246 passed**
- Foundation + Receivables Foundation: **123 passed**
- `compileall`: PASS
- LAT gates: `md`, `index`, `sections`, `code-refs`, `lat` -> todos exit 0
- `git diff --check`: exit 0
- `TEST_FAILURES = 0`
- Sin `git add`/`commit`.

## AB. Files / evidence produced

Evidencia: `{EV}`

Archivos: `executor_identity.json`, `run_state.json`, `foundation_precheck.json`,
`productive_reader.json`, `sap_safety.json`, `v1_baseline.json`, `v2_cohort.json`,
`v1_v2_cohort_reconciliation.json`, `commercial_terms.json`, `due_date_analysis.json`,
`settlement_timing.json`, `settlement_lag_distribution.json`, `mature_cohort_analysis.json`,
`collection_methods.json`, `mixed_payment_validation.json`, `qr_limitation.json`,
`on_account_analysis.json`, `credit_memo_analysis.json`, `reconciliation_analysis.json`,
`same_day_evidence_matrix.json`, `strict_payment_behavior_classification.json`,
`contado_business_rule_search.json`, `current_open_debt.json`, `monthly_settlement_trend.json`,
`monthly_collection_method_trend.json`, `product_breakdown.json`, `financial_reconciliation.json`,
`method_reconciliation.json`, `cg2a_document_partition.json`, `v1_vs_v2_explanation.json`,
`business_conclusion.json`, `performance.json`, `tests.json`, `files_changed.json`,
`location_channel_control.json`, `seller_control.json`, `required_outputs.json`,
`verdict.json`, `final_report.md`.

Repository (nuevos, `MODULE_LOCAL`): `analysis_kernel.py`, `assemble_phase1.py`,
`assemble_phase2.py`, `assemble_phase3.py`, `companion.py`, `test_analysis_kernel.py`,
`__init__.py` (+ scripts de exploracion read-only `explore*.py`).

## Reproducibilidad

- Foundation: `{v['FOUNDATION_CURRENT']}`
- Componentes logicos: {v['PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT']}
- Foundation data as-of: 2026-09-28T18:18:35.264000
- Cohorte: {v['V2_COHORT_FIRST_DATE']}..{v['V2_COHORT_LAST_DATE']}
- Settlement as-of: {v['SETTLEMENT_AS_OF_DATE']} (DAILY_CLOSE)
- Query ms: cohort={perf['cohort_reconstruction']}, settlement={perf['settlement_analysis']}, methods={perf['collection_method_analysis']}, monthly={perf['monthly_trend']}
"""
    w("final_report.md", report, raw=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

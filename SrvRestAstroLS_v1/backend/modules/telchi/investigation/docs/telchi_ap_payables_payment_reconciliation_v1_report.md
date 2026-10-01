# TELCHI — AP PAYABLES / PAYMENT / RECONCILIATION V1

**Gate:** `TELCHI_AP_PAYABLES_PAYMENT_RECONCILIATION_V1_PASS`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`\
**Evidencia:** 2026-09-09T13:02:28.592290+00:00

## A. VEREDICTO EJECUTIVO

La autoridad de settlement es `OITR/ITR1`: cada OPCH nace en GL, y su cancelación se descompone por miembros de reconciliación. `VPM2` reconstruye la aplicación SAP del pago pero no se suma nuevamente al settlement. Las diferencias no explicadas se etiquetan como candidatos, nunca como retención probada.

Resultado: **PASS**. La descomposición publicada contiene 32522 facturas y 8 fichas A–H; el caso D conserva `UNUSED_PROVEN` si no aparece un anticipo AP real.

## B. UNIVERSO AP

OPCH: `{'TOTAL': 32522, 'ACTIVE': 30186, 'CANCELED': 2336, 'OPEN_STATUS': 620, 'CLOSED_STATUS': 29566, 'GROSS_TOTAL': 1186307550.53, 'PAID_TO_DATE': 1175070257.3, 'OPEN_FORMULA': 11237293.23}`; ORPC/ORPD/OVPM y reconciliaciones están en `universe` y `overview` del JSON. Fecha as-of SAP: `{'AS_OF_DATE': '2026-09-09'}`.

## C. NACIMIENTO DE LA DEUDA / CONTROL ACCOUNT

`OPCH.TransId → OJDT → JDT1` y `OCRD.DebPayAcct → JDT1.Account`, con `ShortName=CardCode`, fueron medidos. El control por proveedor se conserva por CardCode; no se sustituye por saldo agregado de OACT.

## D. PAGOS Y APLICACIONES

OVPM: `{'TOTAL': 41599, 'ACTIVE': 40266, 'CANCELED': 1333, 'DOC_TOTAL': 749496353.64, 'CASH': 153338989.12, 'CHECKS': 93202300.35, 'TRANSFERS': 3314481672.51, 'CREDIT_CARDS': 7142.49, 'NO_DOC': 509990475.0, 'WTSUM': 0.0}`. La ruta `OVPM → VPM2 → OPCH` se conserva por `VPM2.DocNum=OVPM.DocEntry`, `InvType=18`, `VPM2.DocEntry=OPCH.DocEntry`. Pagos sin documento, ausencia de VPM2 y pagos cancelados se separan.

## E. NOTAS, ANTICIPOS Y DEVOLUCIONES

ORPC se clasifica como nota de crédito, no pago. Anticipos se buscan en `VPM2.InvType=25/204` y en `ODPI/ODPO` cuando existen. ORPD se mide aparte: devolución de mercadería no se convierte automáticamente en cancelación AP.

## F. RECONCILIACIÓN

Se midieron OITR, ITR1, ReconNum/LineSeq, Canceled, SrcObjTyp, SrcObjAbs, TransId y ReconSum. Tipos AP relevantes: 18 factura, 19 NC, 46 pago, 25/204 anticipo y 30 JE. En reconciliaciones N:N los componentes se asignan proporcionalmente a la participación de la factura para no sobrecontar.

## G. SETTLEMENT Y CASH VS DEUDA

`CASH_SETTLED` representa la porción de la factura liquidada por un miembro `SrcObjTyp=46` con pago OVPM; `NON_CASH_SETTLED` separa NC, anticipo, JE y otros. El importe no es llamado retención sin una causa SAP o evidencia externa.

## H. DESCUENTOS / FX / REDONDEOS

Se midieron descuentos de OPCH y VPM2, moneda DocCur/DocTotalFC/DocRate y cuentas/memos FX. Redondeo usa tolerancia explícita de Bs 0,01; no se mezcla moneda nominal.

## I. CASOS REALES

Los casos A–H están en `cases` del JSON con proveedor, factura, DocEntry/DocNum, GL, pagos, settlement, saldo, matching y evidencia. `H_EXTERNAL_WITHHOLDING_CANDIDATE` es solo una cola de contraste documental.

## J. DEUDA ABIERTA / AGING

El saldo abierto usa `DocTotal - PaidToDate` después de validar settlement y se conserva por moneda. Aging usa `CURRENT_DATE` de SAP y buckets no vencido, 1–30, 31–60, 61–90, 91–180, 181–365 y >365 sobre saldo positivo.

## K. INVARIANTES

| Invariante | Resultado |
|---|---|
| AP01_opch_transid_exists_in_ojdt | PASS — {'orphans': 0, 'pass': True} |
| AP02_active_invoice_journals_balanced | PASS — {'rows': {'JOURNALS': 30186, 'BALANCED': 30186, 'UNBALANCED': 0, 'MAX_DIFF': 0.0}, 'pass': True} |
| AP03_valid_payment_has_gl | PASS — {'orphans': 0, 'pass': True, 'basis': 'OVPM.TransId → OJDT.'} |
| AP04_vpm2_links_valid_or_classified | PASS — {'invalid_payment_link': 0, 'invalid_target_link': 0, 'pass': True} |
| AP05_itr1_known_members_valid | PASS — {'invalid': 0, 'pass': True} |
| AP06_canceled_documents_separate | PASS — {'pass': True, 'basis': "Canceled OPCH/OVPM/OITR are profiled separately and active settlement uses OITR.Canceled='N'."} |
| AP07_no_payment_reconciliation_double_count | PASS — {'pass': True, 'basis': 'Settlement totals use ITR1 invoice members once; VPM2 is only a link/cross-check.'} |
| AP08_settlement_decomposition_reconciles | PASS — {'active_invoices': 30186, 'absolute_delta': 0.0, 'pass': True} |
| AP09_currency_separation | PASS — {'pass': True, 'basis': 'All invoice aggregates retain DocCur; FC fields are not added to local DocTotal.'} |
| AP10_sap_write_count | PASS — {'value': 0, 'pass': True} |
| AP11_reconciliation_grain | PASS — {'rows': {'LINES': 4481793, 'RECON_NUMS': 2095404, 'RECON_LINE_KEYS': 4481793}, 'pass': True} |
| AP12_control_account | PASS — {'supplier_lines': 33270, 'control_lines': 32680, 'coverage_pct': 98.2266, 'pass': True, 'basis': 'OCRD.DebPayAcct and JDT1.ShortName/Account; 95% threshold preserves historical/current account variance for review.'} |
| AP13_open_balance_nonnegative_for_active | PASS — {'negative_count': 0, 'pass': True} |
| AP14_settlement_matches_paid_to_date | PASS — {'active_invoices': 30186, 'exact_matches': 30186, 'max_difference': 0.0, 'pass': True} |

## L. PRINCIPALES PROVEEDORES AP

| Proveedor | Moneda | Facturas abiertas | Abierto | Vencido |
|---|---|---:|---:|---:|
| BANCO FIE S.A. (PL000212) | BS | 13 | 3737302.96 | 2839980.78 |
| BANCO MERCANTIL SANTA CRUZ S.A. (PL000288) | BS | 6 | 1090361.43 | 117931.64 |
| THOSCO THODE-SCOBEL (PE000011) | USD | 1 | 896104.08 | 0.0 |
| HAINAN ZHONGXIN CHEMICAL LTDA (PE000002) | USD | 2 | 830218.46 | 0.0 |
| MATRIPLAST SA (PL000063) | BS | 9 | 387578.0 | 0.0 |
| DROGUERIA INTI S.A. (PL000032) | BS | 24 | 322063.19 | 0.0 |
| Coop. Transporte German Busch Ltda. (PL000270) | BS | 12 | 253314.92 | 158639.89 |
| ANTODEN S.R.L. (PL000691) | BS | 12 | 250873.84 | 238482.15 |
| LABORATORIOS BAGO DE BOLIVIA S.A. (PL000007) | BS | 25 | 231246.0 | 0.0 |
| MERQUIMIA BOLIVIA S.R.L. (PL000461) | BS | 1 | 210000.0 | 0.0 |

## M. POSIBLES RETENCIONES EXTERNAS

La corrida detecta una masa de diferencias `deuda cancelada - cash`: `difference_analysis` conserva 154 candidatos, separados por moneda {'BS': 380679.38}, no cash no explicado por pago/NC/anticipo/JE; candidatos externos directos: 0.  En esta primera clasificación, `OTHER_SETTLED` incluye objetos SAP de compensación/reclasificación que deben contrastarse por `SrcObjTyp`; por eso no se afirma retención. Solo después de excluir esos mecanismos se etiqueta `EXTERNAL_WITHHOLDING_CANDIDATE`. El gate WHT anterior permanece degradado.

## N. LIMITACIONES

- En una reconciliación N:N SAP prueba el total asignado a la factura; el reparto por tipo de contraparte es proporcional cuando varios documentos comparten ReconNum.
- En un pago mixto, SAP registra medios en OVPM pero no necesariamente distribuye cada medio a cada factura; el JSON conserva el pago mixto como tal.
- Un asiento externo o entrega física fuera de SAP no puede demostrarse desde estas tablas.
- Reconciliación no equivale automáticamente a efectivo: NC, anticipos y JE permanecen separados.
- La cobertura histórica de `OCRD.DebPayAcct` sobre líneas AP es 98,2266%; 590 líneas conservan una cuenta distinta de la configuración actual y quedan como variación histórica, no como saldo perdido.

## O. PRÓXIMO GATE

`TELCHI_TREASURY_CASH_BANK_DEPOSIT_V1`, o `TELCHI_WITHHOLDING_TAX_EXTERNAL_RECONCILIATION_V2` antes si la cola externa presenta evidencia documental recurrente.

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/ap_payables_payment_reconciliation/ap_payables_payment_reconciliation_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/ap_payables_payment_reconciliation/ap_payables_payment_reconciliation_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

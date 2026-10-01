# TELCHI — CASH / DEPOSIT CONTROL V1

**Gate:** `TELCHI_CASH_DEPOSIT_CONTROL_V1_PASS`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`\
**Período:** `2025-09-02` → `2026-09-09`

## A. VEREDICTO EJECUTIVO

SAP permite reconstruir efectivo esperado contable por cuenta y fecha: cobros ORCT, pagos OVPM, depósitos ODPS, transferencias y ajustes. No demuestra el efectivo físico contado. El enlace ORCT-cash→ODPS no es una FK documental probada; el matching se publica como FIFO pooled entre cashboxes, AllocAcct, moneda y fecha, conservando las cuentas de ambas patas.

Resultado: **PASS**. La posición `EXPECTED_CASH` no se presenta como `PHYSICAL_CASH`.

## B. UNIVERSO CASH

Se reutilizan las 38 cuentas CASH/PETTY_CASH del gate de tesorería. El universo actual en OACT es `38`; cada saldo y movimiento conserva ActCurr, incluyendo `##`.

## C. COBROS / PAGOS / DEPÓSITOS

ORCT cash activo: `61435325.1`. OVPM cash activo: `30039638.76`. ODPS cash activo: `39958514.85`. ODPS se contabiliza como salida de caja/origen `AllocAcct` y entrada bancaria, nunca como ingreso económico nuevo.

## D. DAILY CASH ROLL-FORWARD

La fecha económica del roll-forward es OJDT.RefDate (posting date). DocDate/TaxDate/CreateDate se conservan en los universos documentales para separar operación de contabilización. El opening del rango se deriva de CurrTotal menos movimientos GL del rango; por ello el control prueba el roll-forward contable, no un arqueo histórico independiente.

Cuentas reconciliadas: `{'account_count': 38, 'all_gaps_zero': True, 'max_gap': 0.0}`.

## E. CASH → DEPOSIT

Método: `FIFO_POOLED_CASHBOX_TO_ALLOCACCT; source cashbox retained; currency and economic date preserved`. Cobertura de importe depositado explicable por esta regla: `100.0%`; mismo día `212371.45`; D+1 `284195.37`; p90 `110` días. Un match no es una identidad documental de cobro.

## F. SALDO ESPERADO / PERSISTENCIA

El saldo esperado final por cuenta es el saldo GL de la cuenta. Los saldos positivos persistentes, negativos y cohortes no depositadas quedan en `rollforward.by_account` y `cash_to_deposit.matches`; no se llaman faltantes sin evidencia física.

## G. CANCELACIONES / SUCURSAL / USUARIOS

ORCT, OVPM y ODPS cancelados se agrupan aparte y no entran en movimientos vigentes. BPLId/U_SUCURSAL/UserSign se conservan como trazabilidad SAP; no prueban custodia física ni responsabilidad personal.

## H. MONEDA `##`

`OACT.ActCurr='##'` no se reclasifica nominalmente. Para JDT1 se deriva `ECONOMIC_CURRENCY` solo cuando FCCurrency y FCDebit/FCCredit aportan evidencia; sin esa evidencia la línea permanece `##`. `BS`, `USD` y `##` no se compensan.

## I. RESIDUAL -68.668,93

El control reproduce el residual interno esperado `-68668.93` como `-68668.93`, con delta `0.0` y `336` TransIds contribuyentes. Se preservan patas ActCurr y campos JDT1 en JSON; el residual queda `ISOLATED_UNRESOLVED` a nivel semántico, no oculto mediante neteo.

## J. LIMITACIÓN FÍSICA

SAP demuestra `EXPECTED_CASH_FROM_SAP`. Sin arqueo/cuenta física externa no demuestra `PHYSICAL_CASH`, diferencias de caja ni existencia material del saldo.

## K. CASOS A–J

Se preservan diez casos end-to-end en JSON con nivel de evidencia; cuando el dato no fue demostrable se marca PARTIAL/UNRESOLVED.

## L. INVARIANTES

| Invariante | Resultado |
|---|---|
| CD01_orct_cash_gl | PASS — {'pass': True, 'basis': 'ORCT.TransId + CashAcct preaggregated JDT1'} |
| CD02_odps_cash_gl | PASS — {'pass': True, 'basis': 'ODPS.TransAbs + preaggregated JDT1; cash/check/card separated by DeposType'} |
| CD03_cash_accounts_in_oact | PASS — {'pass': True, 'count': 38} |
| CD04_daily_rollforward | PASS — {'pass': True, 'max_gap': 0.0} |
| CD05_gl_closing_reconciliation | PASS — {'pass': True} |
| CD06_orct_canceled_excluded | PASS — {'pass': True} |
| CD07_odps_canceled_excluded | PASS — {'pass': True} |
| CD08_ovpm_canceled_excluded | PASS — {'pass': True} |
| CD09_deposit_not_new_income | PASS — {'pass': True, 'basis': 'ODPS is an internal cash-to-bank movement in the roll-forward'} |
| CD10_matching_evidence_explicit | PASS — {'pass': True} |
| CD11_hash_currency_not_nominally_mixed | PASS — {'pass': True, 'basis': 'JDT1 FCCurrency/FCDebit/FCCredit retained; ## remains ## when no FC evidence'} |
| CD12_residual_isolated | PASS — {'pass': True, 'observed': -68668.93, 'baseline': -68668.93, 'contributors': 336} |
| CD13_sap_write_count | PASS — {'pass': True, 'value': 0} |
| CD14_physical_cash_not_claimed | PASS — {'pass': True, 'basis': 'No external physical count source was read'} |
| CD15_cases_preserved | PASS — {'pass': True} |

## PRÓXIMO GATE

`TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1` para aislar semántica de transferencias y `BS/##`. Forecast queda bloqueado hasta elevar la posición financiera integrada a PASS.

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/cash_deposit_control/cash_deposit_control_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/cash_deposit_control/cash_deposit_control_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

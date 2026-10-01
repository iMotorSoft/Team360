# TELCHI — FINANCIAL POSITION / CASH FLOW V1.1

**AS_OF_DATE:** `2026-09-09`

**Modo:** INVESTIGATION / READ ONLY

## A. VEREDICTO

**PASS** — `TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1_PASS`. `SAP_WRITE_COUNT=0`.

## B. PROBLEMA HEREDADO DE V1

V1 cerró opening→flow→closing con gap 0,00 y cobertura 99,8411%, pero dejó internal transfer net -68.668,93 y 14 movimientos unresolved por Bs 955.949,27.

## C. SEMÁNTICA DE `##`

En Telchi `OACT.ActCurr='##'` significa que la cuenta admite contabilización sin moneda fija única; no es una moneda. Los 286 perfiles materiales muestran líneas LC-only y, en algunos casos, FC USD. La moneda económica se obtiene de JDT1, no de OACT.

## D. ACCOUNT CURRENCY VS MOVEMENT CURRENCY

Se preservan ambos campos. Regla probada: FC no cero + FCCurrency → FC; cuenta fija USD sin FC → SC; `##` sin FC → LC/BS. LC y SC permanecen además como bases de control.

## E. UNIVERSO 336 TRANSIDS

Se materializaron 336 TransIds y 995 líneas agregadas TransId×cuenta, representando 107340 líneas JDT1 fuente. Reproducen -68668.93.

## F. ORIGEN DEL RESIDUAL

| Source | Count | Net LC | Abs LC | % abs |
|---|---:|---:|---:|---:|
| PERIOD_CLOSE | 27 | -6092793.77 | 10117676.13 | 49.814% |
| PERIOD_OPEN | 27 | 6092793.77 | 10117676.13 | 49.814% |
| ODPS | 272 | -68494.43 | 75396.29 | 0.3712% |
| JE_MANUAL | 10 | -174.5 | 174.5 | 0.0009% |

### Top 20 por contribución absoluta

| Rank | TransId | Fecha | Source | V1 contribution | V1.1 treatment |
|---:|---:|---|---|---:|---|
| 1 | 15766458 | 2025-12-31 | PERIOD_CLOSE | -3620940.0 | PERIOD_CARRYFORWARD |
| 2 | 15766459 | 2026-01-01 | PERIOD_OPEN | 3620940.0 | PERIOD_CARRYFORWARD |
| 3 | 15766480 | 2025-12-31 | PERIOD_CLOSE | -2113167.82 | PERIOD_CARRYFORWARD |
| 4 | 15766481 | 2026-01-01 | PERIOD_OPEN | 2113167.82 | PERIOD_CARRYFORWARD |
| 5 | 15766492 | 2025-12-31 | PERIOD_CLOSE | 2012441.18 | PERIOD_CARRYFORWARD |
| 6 | 15766493 | 2026-01-01 | PERIOD_OPEN | -2012441.18 | PERIOD_CARRYFORWARD |
| 7 | 15766464 | 2025-12-31 | PERIOD_CLOSE | -1113488.74 | PERIOD_CARRYFORWARD |
| 8 | 15766465 | 2026-01-01 | PERIOD_OPEN | 1113488.74 | PERIOD_CARRYFORWARD |
| 9 | 15766462 | 2025-12-31 | PERIOD_CLOSE | -310148.74 | PERIOD_CARRYFORWARD |
| 10 | 15766463 | 2026-01-01 | PERIOD_OPEN | 310148.74 | PERIOD_CARRYFORWARD |
| 11 | 15766478 | 2025-12-31 | PERIOD_CLOSE | -196424.08 | PERIOD_CARRYFORWARD |
| 12 | 15766479 | 2026-01-01 | PERIOD_OPEN | 196424.08 | PERIOD_CARRYFORWARD |
| 13 | 15766438 | 2025-12-31 | PERIOD_CLOSE | -170068.0 | PERIOD_CARRYFORWARD |
| 14 | 15766439 | 2026-01-01 | PERIOD_OPEN | 170068.0 | PERIOD_CARRYFORWARD |
| 15 | 15766392 | 2025-12-31 | PERIOD_CLOSE | -118010.7 | PERIOD_CARRYFORWARD |
| 16 | 15766393 | 2026-01-01 | PERIOD_OPEN | 118010.7 | PERIOD_CARRYFORWARD |
| 17 | 15766470 | 2025-12-31 | PERIOD_CLOSE | -115813.35 | PERIOD_CARRYFORWARD |
| 18 | 15766471 | 2026-01-01 | PERIOD_OPEN | 115813.35 | PERIOD_CARRYFORWARD |
| 19 | 15766482 | 2025-12-31 | PERIOD_CLOSE | -67897.37 | PERIOD_CARRYFORWARD |
| 20 | 15766483 | 2026-01-01 | PERIOD_OPEN | 67897.37 | PERIOD_CARRYFORWARD |

Acumulado firmado: `{'top_1': -3620940.0, 'top_5': 2012441.18, 'top_10': 0.0, 'top_20': 0.0, 'all_336': -68668.93}`. Los Top 20 son carryover cierre/apertura; al emparejar -3/+2 netean 0,00.

## G. BS COMPONENT

V1: -69688.46. Incluye comisiones de depósitos de tarjeta y patas BS de transferencias QR; no es principal interno sin contraparte.

## H. `##` COMPONENT

V1: 1019.53. Las líneas son LC-only y pasan a MovementCurrency=BS; sus pares BS netean. `##` deja de tratarse como moneda.

## I. CROSS-CURRENCY TRANSFERS

Los casos FC/MIXED se conservan en perfiles y casos reales. En los 336 el residual material no proviene de principal cross-currency: `{'residual_336_explicit_fc_lines': 8, 'treatment': 'FC principal compared in FC; LC and SC retained as control bases; FX never external cash'}`.

## J. FX / FEES / ROUNDING

Comisiones separadas del principal: 68494.43 BS. FX y rounding no se usan como plug; el carryover -2/-3 se identifica como no-cash y sus pares netean.

## K. INTERNAL TRANSFER NETTING

Después del split principal/comisión y moneda a nivel movimiento: `0.0`.

## L. 14 UNRESOLVED PREVIOS

Se trazan individualmente 14; gross V1 955949.27. La nueva semántica no los usa para cuadrar.

## M. CASH FLOW V1.1

| Currency | External in | External out | Internal net | FX | Fees | Manual | Unresolved net | All net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BS | 210061030.19 | 207327277.06 | 0.0 | 2037.39 | -68494.43 | -715760.24 | -309630.0 | 639497.51 |
| USD | 39677.81 | 39605.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | -7537.09 |

Detalle mensual 12m: `cash_flow_v1_1.monthly`. Cobertura: `{'total_movement_abs': 586090365.34, 'unresolved_count': 14, 'unresolved_amount': 831630.0, 'classified_pct': 99.8581}`. Depósitos siguen internos; fees son BANK_FEE.

## N. TREASURY RECONCILIATION

MovementCurrency: `[{'currency': 'BS', 'opening': 17033039.12, 'flow': 639497.51, 'closing': 17672536.63, 'gap': 0.0}, {'currency': 'USD', 'opening': -1700681.05, 'flow': -7537.09, 'closing': -1708218.14, 'gap': 0.0}]`. Bases LC/SC: `{'LC': {'flow': 627326.67, 'closing': 5765388.28, 'opening': 5138061.61, 'gap': 0.0}, 'SC': {'flow': 93852.85, 'closing': 841963.05, 'opening': 748110.2, 'gap': 0.0}}`.

## O. FINANCIAL POSITION

La foto V1 queda preservada en JSON. V1.1 reclasifica solo el tramo `##` demostrado:

| Currency / base | Treasury | AR | AP | Net operating position |
|---|---:|---:|---:|---:|
| BS | 2595009.35 | 4030808.24 | 9510970.69 | -2885153.1 |
| USD | 492943.69 | 0.0 | 1726322.54 | -1233378.85 |
| SC_ONLY | 2602091.9 | — | — | None |

Descomposición: `{'BS': 468602.07, 'SC_ONLY': 2602091.9, 'UNRESOLVED': 0.0}`. `SC_ONLY` no se suma nominalmente a USD ni a BS. No se denomina patrimonio.

## P. COMPARATIVA V1 VS V1.1

| Métrica | V1 | V1.1 | Δ | Motivo |
|---|---:|---:|---:|---|
| Classified coverage | 99.8411% | 99.8581% | 0.017 pp | movement-currency denominator and residual component split |
| Unresolved count | 14 | 14 | 0 | bounded individually |
| Unresolved amount | 955949.27 | 831630.0 | -124319.27 | USD rows measured in movement currency |
| Internal transfer residual | -68668.93 | 0.0 | 68668.93 | ODPS card commissions split as BANK_FEE; period carryover excluded; ## LC-only legs mapped to BS |
| `##` nominal unresolved | 3070693.97 | 0.0 | -3070693.97 | decomposed as BS / SC_ONLY |

## Q. CASOS REALES

`[{'case': 'A_HASH_IS_BS', 'status': 'PROVEN', 'evidence': {'acctcode': '1111015', 'acctname': 'BANCO GANADERO Cta. Cte. 1311270031 MN', 'account_currency': '##', 'practical_classification': 'BS_ONLY_IN_PRACTICE', 'movements': 174215, 'lc_net': 493611.04, 'sc_net': 59244.43, 'fc_net': 0.0, 'fc_lines': 0, 'lc_only_lines': 174233, 'observed_fc_currencies': [], 'first_date': '2023-09-29T00:00:00', 'last_date': '2026-09-09T00:00:00'}}, {'case': 'B_HASH_HAS_USD', 'status': 'PROVEN', 'evidence': {'acctcode': '1111016', 'acctname': 'BANK OF AMERICA - TELCHI INC.', 'account_currency': '##', 'practical_classification': 'MIXED', 'movements': 104, 'lc_net': 196424.08, 'sc_net': 28181.36, 'fc_net': 109595.0, 'fc_lines': 5, 'lc_only_lines': 92, 'observed_fc_currencies': ['USD'], 'first_date': '2023-01-01T00:00:00', 'last_date': '2026-01-01T00:00:00'}}, {'case': 'C_BS_HASH_NETS_BY_MOVEMENT', 'status': 'PROVEN', 'evidence': {'transid': 14834456, 'refdate': '2025-11-21T00:00:00', 'transtype': '30', 'baseref': '256294826', 'memo': 'Traspaso de depósito, corresponde a la cuenta Bco Ganadero por cobros de QRs venta de salones  CGCM', 'datasource': 'I', 'user': 209, 'source': 'JE_MANUAL', 'odps': None, 'old_treasury_net_lc': 0.0, 'old_by_account_currency': {'##': 38.0, 'BS': -38.0}, 'movement_by_currency': {'BS': 0.0}, 'full_journal_lc_gap': 0.0, 'full_journal_sc_gap': 0.0, 'fee_counterpart_lc': 0, 'corrected_category': 'INTERNAL_OTHER', 'corrected_internal_net': 0.0, 'corrected_other_treasury_effect': 0.0, 'accounts': 2, 'source_lines': 2}}, {'case': 'D_CROSS_CURRENCY', 'status': 'PROVEN', 'evidence': {'classification': 'CROSS_CURRENCY_TRANSFER', 'memo': 'TRASPASO DE $US.-100 COBROS CAJA SALON 2A DE  27/08/2026 (TC-11.57)', 'transids': [16283483, 16283501], 'legs': [{'TRANSID': 16283501, 'REFDATE': '2026-08-27T00:00:00', 'TRANSTYPE': '24', 'MEMO': 'TRASPASO DE $US.-100 COBROS CAJA SALON 2A DE  27/08/2026 (TC-11.57)', 'ACCOUNT': '1110401', 'ACCTNAME': 'Caja General Tesoreria ME', 'ACCOUNT_CURRENCY': 'USD', 'LC_NET': 1157.0, 'SC_NET': 100.0, 'FC_NET': 100.0, 'FCCURRENCY': 'USD', 'MOVEMENT_CURRENCY': 'USD', 'MOVEMENT_AMOUNT': 100.0, 'MOVEMENT_CURRENCY_BASIS': 'JDT1_FC'}, {'TRANSID': 16283501, 'REFDATE': '2026-08-27T00:00:00', 'TRANSTYPE': '24', 'MEMO': 'TRASPASO DE $US.-100 COBROS CAJA SALON 2A DE  27/08/2026 (TC-11.57)', 'ACCOUNT': '1111301', 'ACCTNAME': 'Compra y Venta de Divisas', 'ACCOUNT_CURRENCY': '##', 'LC_NET': -1157.0, 'SC_NET': -100.0, 'FC_NET': -100.0, 'FCCURRENCY': 'USD', 'MOVEMENT_CURRENCY': 'USD', 'MOVEMENT_AMOUNT': -100.0, 'MOVEMENT_CURRENCY_BASIS': 'JDT1_FC'}, {'TRANSID': 16283483, 'REFDATE': '2026-08-27T00:00:00', 'TRANSTYPE': '46', 'MEMO': 'TRASPASO DE $US.-100 COBROS CAJA SALON 2A DE  27/08/2026 (TC-11.57)', 'ACCOUNT': '1110101', 'ACCTNAME': 'Caja General Tesoreria MN', 'ACCOUNT_CURRENCY': 'BS', 'LC_NET': -1157.0, 'SC_NET': -100.0, 'FC_NET': 0.0, 'FCCURRENCY': None, 'MOVEMENT_CURRENCY': 'BS', 'MOVEMENT_AMOUNT': -1157.0, 'MOVEMENT_CURRENCY_BASIS': 'JDT1_LC_NO_FC'}, {'TRANSID': 16283483, 'REFDATE': '2026-08-27T00:00:00', 'TRANSTYPE': '46', 'MEMO': 'TRASPASO DE $US.-100 COBROS CAJA SALON 2A DE  27/08/2026 (TC-11.57)', 'ACCOUNT': '1111301', 'ACCTNAME': 'Compra y Venta de Divisas', 'ACCOUNT_CURRENCY': '##', 'LC_NET': 1157.0, 'SC_NET': 100.0, 'FC_NET': 0.0, 'FCCURRENCY': None, 'MOVEMENT_CURRENCY': 'BS', 'MOVEMENT_AMOUNT': 1157.0, 'MOVEMENT_CURRENCY_BASIS': 'JDT1_LC_NO_FC'}], 'treatment': 'two-document bridge through 1111301; compare each leg in its movement currency; do not count either principal as external cash'}}, {'case': 'E_REMAINS_UNRESOLVED', 'status': 'PROVEN', 'evidence': {'transid': 14683142, 'refdate': '2025-10-24T00:00:00', 'transtype': '18', 'baseref': '251902833', 'memo': 'Factura de proveedores - Cancelación - PL000288', 'cause': 'source object/cancellation or economic intent not proven; bounded and not used as balancing plug'}}]`

## R. INVARIANTES

- `FP11-01`: PASS
- `FP11-02`: PASS
- `FP11-03`: PASS
- `FP11-04`: PASS
- `FP11-05`: PASS
- `FP11-06`: PASS
- `FP11-07`: PASS
- `FP11-08`: PASS
- `FP11-09`: PASS
- `FP11-10`: PASS
- `FP11-11`: PASS
- `FP11-12`: PASS

## S. LIMITACIONES

No se consumieron estados bancarios ni arqueos físicos. Una cuenta `##` LC-only no prueba la moneda del banco fuera de SAP. El matching cash→deposit sigue HEURISTIC. Los 14 unresolved V1 continúan bounded. WHT permanece fuera de este gate.

## T. PRÓXIMO GATE

TELCHI_BALANCE_SHEET_PNL_RECONSTRUCTION_V1

## Artefactos

- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_position_cash_flow/financial_position_cash_flow_v1_1.py`
- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_position_cash_flow/financial_position_cash_flow_v1_1.json`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

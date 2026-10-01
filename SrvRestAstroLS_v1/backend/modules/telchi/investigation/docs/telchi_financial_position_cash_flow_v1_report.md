# TELCHI — FINANCIAL POSITION / CASH FLOW V1

**Gate:** `TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_DEGRADED`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`\
**AS_OF_DATE:** `2026-09-09`\
**Evidencia:** 2026-09-09T19:05:49.121414+00:00

## A. VEREDICTO EJECUTIVO

La posición es una foto contable por moneda. El cash flow se construye desde movimientos GL fechados y objetos SAP; depósitos y transferencias internas no se cuentan como entrada económica nueva. Este gate no afirma efectivo disponible, conciliación bancaria externa, patrimonio, Balance Sheet completo ni cash flow IFRS.

Resultado: **DEGRADED**. Cobertura clasificada: **99.8411%**; unresolved: **0.1589%**.

## B. POSITION POR MONEDA

`SAP_OPERATIONAL_FINANCIAL_POSITION` y `NET_OPERATING_FINANCIAL_POSITION` son nombres operativos; no equivalen a patrimonio.

| Moneda | Caja+Bancos | AR abierto | AP abierto | AR vencido | AP vencido | Net operating position |
|---|---:|---:|---:|---:|---:|---:|
| ## | 3070693.97 | 0.0 | 0.0 | 0.0 | 0.0 | 3070693.97 |
| BS | 2126407.28 | 4030808.24 | 9510970.69 | 1392313.82 | 4529313.2 | -3353755.17 |
| USD | 492943.69 | 0.0 | 1726322.54 | 0.0 | 0.0 | -1233378.85 |

## C. AR

AR reconstruido con OINV + OITR/ITR1 y cruzado contra PaidToDate: `[{'currency': 'BS', 'documents': 2047, 'open': 4030808.2399999923, 'overdue': 1392313.820000002}]`. ORIN, RCT2 y OINV→OJDT se mantienen como controles separados. Una ambigüedad de settlements o GL degrada el gate; no se fuerza PASS.

## D. AP Y TESORERÍA

AP se consume desde el gate cerrado: `PASS`. Tesorería se consume desde `SAP_ACCOUNTING_TREASURY_POSITION`, separando caja, bancos, tránsito y `##`: `PASS`.

## E. CASH FLOW DIRECTO

ORCT activo y no cancelado se clasifica como cobro externo cuando mueve tesorería; OVPM como salida según proveedor/contraparte. ODPS es `INTERNAL_CASH_TO_BANK`; no se suma como CASH_IN. Manuales se separan en comisión, interés, FX, impuesto, nómina, capex, ajuste o unresolved. El JSON conserva el detalle diario y la tabla siguiente muestra el resumen mensual.

## E BIS. TAX / OTHER LIABILITIES

Las cuentas fiscales candidatas se consultan en `known_tax_liabilities` y permanecen fuera de AP/posición salvo semántica PROVEN; retenciones no se inventan.

| Mes | Moneda | Opening | Cash In | Cash Out | Net | Internal | Other | Unresolved | Closing |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-10 | BS | 3792141.65 | 14040893.79 | 14907947.81 | -867054.02 | -6822.92 | -50730.65 | 9630.0 | 2867534.06 |
| 2025-11 | BS | 3239178.1 | 17929621.37 | 17833950.77 | 95670.6 | -5382.99 | 462675.94 | 0.0 | 3792141.65 |
| 2025-12 | BS | 4758785.53 | 18288663.9 | 14259355.15 | 4029308.75 | -5500096.08 | -48820.1 | 0.0 | 3239178.1 |
| 2026-01 | BS | 1560236.12 | 14014104.43 | 15296090.59 | -1281986.16 | 5487738.01 | -1007202.44 | 0.0 | 4758785.53 |
| 2026-02 | BS | -2841243.76 | 15057534.98 | 10635341.31 | 4422193.67 | -5591.03 | -15122.76 | 0.0 | 1560236.12 |
| 2026-03 | BS | 760266.08 | 15582539.9 | 18418145.35 | -2835605.45 | -6048.15 | -759856.24 | 0.0 | -2841243.76 |
| 2026-04 | BS | 1985175.4 | 15184513.7 | 16430865.45 | -1246351.75 | -5222.89 | 26665.32 | 0.0 | 760266.08 |
| 2026-05 | BS | 3001880.83 | 13526766.3 | 14416534.67 | -889768.37 | -4666.88 | -122270.18 | 0.0 | 1985175.4 |
| 2026-06 | BS | 1428047.39 | 15765083.55 | 13674740.79 | 2090342.76 | -5191.44 | -511317.88 | 300000.0 | 3001880.83 |
| 2026-07 | BS | 3087158.91 | 16077363.54 | 17801919.43 | -1724555.89 | -5253.85 | 70698.22 | 0.0 | 1428047.39 |
| 2026-08 | BS | 3641624.62 | 18055750.51 | 18837384.52 | -781634.01 | -5746.45 | 232914.75 | 0.0 | 3087158.91 |
| 2026-09 | BS | 2433325.5 | 4393534.64 | 3243348.82 | 1150185.82 | -1527.97 | 59641.27 | 0.0 | 3641624.62 |
| 2025-09 | USD | 478954.41 | 13989.28 | 0.0 | 13989.28 | 0.0 | 0.0 | 0.0 | 492943.69 |
| 2025-10 | USD | 469176.13 | 85618.85 | 0.0 | 85618.85 | 0.0 | -75840.57 | 0.0 | 478954.41 |
| 2025-11 | USD | 469122.95 | 53.18 | 0.0 | 53.18 | 0.0 | 0.0 | 0.0 | 469176.13 |
| 2025-12 | USD | 701849.74 | 19451.46 | 0.0 | 19451.46 | -237965.37 | -14212.88 | 0.0 | 469122.95 |
| 2026-01 | USD | 462397.13 | 34.85 | 0.0 | 34.85 | 237965.37 | 1452.39 | 1452.39 | 701849.74 |
| 2026-02 | USD | 462356.43 | 40.7 | 0.0 | 40.7 | 0.0 | 0.0 | 0.0 | 462397.13 |
| 2026-03 | USD | 462305.27 | 51.16 | 0.0 | 51.16 | 0.0 | 0.0 | 0.0 | 462356.43 |
| 2026-04 | USD | 462265.89 | 39.38 | 0.0 | 39.38 | 0.0 | 0.0 | 0.0 | 462305.27 |
| 2026-05 | USD | 462225.62 | 39.87 | 0.0 | 39.87 | 0.0 | 0.4 | 108112.48 | 462265.89 |
| 2026-06 | USD | 462165.5 | 60.12 | 0.0 | 60.12 | 0.0 | 0.0 | 14754.4 | 462225.62 |
| 2026-07 | USD | 329454.1 | 132711.4 | 0.0 | 132711.4 | 0.0 | 0.0 | 0.0 | 462165.5 |
| 2026-08 | USD | 208906.05 | 120548.05 | 0.0 | 120548.05 | 0.0 | 0.0 | 0.0 | 329454.1 |

## F. RECONCILIACIÓN DE TESORERÍA

| Moneda | Opening | External in | External out | Internal net | Other effects | Closing | Gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| ## | 336955.9 | 17598336.86 | 16625440.83 | 1019.53 | -441512.91 | 869358.55 | 0.0 |
| BS | 2433325.5 | 192289433.1 | 190839784.87 | -69688.46 | -1576168.04 | 2237117.23 | 0.0 |
| USD | 208906.05 | 372638.3 | 0.0 | 0.0 | -88600.66 | 492943.69 | -0.0 |

## G. AR/AP CONTRACTUAL SCHEDULE

| Moneda | Bucket | AR due | AP due | Gap |
|---|---|---:|---:|---:|
| BS | 0_7 | 697899.89 | 729814.81 | -31914.92 |
| BS | 16_30 | 1242920.46 | 1021367.49 | 221552.97 |
| BS | 31_60 | 232260.69 | 256645.72 | -24385.03 |
| BS | 61_90 | 43408.64 | 0.0 | 43408.64 |
| BS | 8_15 | 415281.46 | 1187327.5 | -772046.04 |
| BS | >90 | 6723.28 | 1786501.97 | -1779778.69 |
| BS | OVERDUE | 1392313.82 | 4529313.2 | -3136999.38 |
| USD | 0_7 | 0.0 | 896104.08 | -896104.08 |
| USD | 16_30 | 0.0 | 401941.8 | -401941.8 |
| USD | 8_15 | 0.0 | 428276.66 | -428276.66 |

## H. LIQUIDITY COVERAGE

Strict Treasury = caja+bancos contables / AP due del horizonte. Treasury + AR agrega AR contractual, sin asumir cobro puntual.

| Moneda | Días | AP due | Strict | Treasury + AR |
|---|---:|---:|---:|---:|
| ## | 7 | 0 | None | None |
| ## | 15 | 0 | None | None |
| ## | 30 | 0 | None | None |
| BS | 7 | 729814.81 | 2.9136 | 3.8699 |
| BS | 15 | 1917142.31 | 1.1092 | 1.6898 |
| BS | 30 | 2938509.8 | 0.7236 | 1.5254 |
| USD | 7 | 896104.08 | 0.5501 | 0.5501 |
| USD | 15 | 1324380.74 | 0.3722 | 0.3722 |
| USD | 30 | 1726322.54 | 0.2855 | 0.2855 |

## I. PRINCIPALES ENTRADAS Y SALIDAS

Top cash sources: `[{'code': 'CGCM', 'name': 'CONTROL TRIBUTARIO', 'currency': 'BS', 'amount': 11555779.9}, {'code': 'CG2A', 'name': 'CONTROL TRIBUTARIO', 'currency': 'BS', 'amount': 10262214.55}, {'code': 'CG2A', 'name': 'CONTROL TRIBUTARIO', 'currency': '##', 'amount': 4331237.85}, {'code': 'CGRC', 'name': 'CONTROL TRIBUTARIO', 'currency': 'BS', 'amount': 4305307.55}, {'code': 'S0001', 'name': 'ROBERTO ABRAHAN TELCHI ASBUN', 'currency': 'BS', 'amount': 4039723.85}, {'code': 'CGRC', 'name': 'CONTROL TRIBUTARIO', 'currency': '##', 'amount': 3434034.66}, {'code': 'CGCM', 'name': 'CONTROL TRIBUTARIO', 'currency': '##', 'amount': 3183506.27}, {'code': 'CGV1', 'name': 'CONTROL TRIBUTARIO', 'currency': 'BS', 'amount': 3038724.69}, {'code': '1111001', 'name': 'BMSC Cta.Cte. 4010608078 MN', 'currency': 'BS', 'amount': 2887000.0}, {'code': '1111015', 'name': 'BANCO GANADERO Cta. Cte. 1311270031 MN', 'currency': 'BS', 'amount': 2860732.0}, {'code': 'C000061', 'name': 'FARMACORP S.A.', 'currency': 'BS', 'amount': 2502712.43}, {'code': '1110310', 'name': 'Caja Distribuidor Placa 2725-PRC MN', 'currency': 'BS', 'amount': 2093406.17}, {'code': 'C000143', 'name': 'AVICOLA SOFIA', 'currency': 'BS', 'amount': 1741223.74}, {'code': '1110308', 'name': 'Caja Distribuidor Placa 3872-XRI MN', 'currency': 'BS', 'amount': 1727774.65}, {'code': '1111002', 'name': 'BMSC Cta. Cte. 4010707998 MN', 'currency': 'BS', 'amount': 1550000.0}, {'code': 'C010264', 'name': 'L&S S.R.L.', 'currency': 'BS', 'amount': 1549562.67}, {'code': '1111012', 'name': 'BANCO UNION Cta.Cte. 1-33418159 MN', 'currency': 'BS', 'amount': 1455500.0}, {'code': '1110304', 'name': 'Caja Distribuidor Placa 4702-GIP MN', 'currency': 'BS', 'amount': 1426754.43}, {'code': '1110305', 'name': 'Caja Distribuidor Placa 4702-GKT MN', 'currency': 'BS', 'amount': 1408203.82}, {'code': '1110307', 'name': 'Caja Distribuidor Placa 2904-ILA MN', 'currency': 'BS', 'amount': 1359030.39}]`

Top cash uses: `[{'code': 'PL000288', 'name': 'BANCO MERCANTIL SANTA CRUZ S.A.', 'currency': 'BS', 'amount': 9289832.67}, {'code': 'PE000011', 'name': 'THOSCO THODE-SCOBEL', 'currency': 'BS', 'amount': 5820737.15}, {'code': 'PE000002', 'name': 'HAINAN ZHONGXIN CHEMICAL LTDA', 'currency': 'BS', 'amount': 5357850.85}, {'code': 'PL000212', 'name': 'BANCO FIE S.A.', 'currency': 'BS', 'amount': 4102336.3}, {'code': 'PL000168', 'name': 'AGENCIA DESPACHANTE DE ADUANA URUBO S.R.L.', 'currency': 'BS', 'amount': 3994215.7}, {'code': 'PL000063', 'name': 'MATRIPLAST SA', 'currency': 'BS', 'amount': 2763248.8}, {'code': 'PL000032', 'name': 'DROGUERIA INTI S.A.', 'currency': 'BS', 'amount': 2591734.85}, {'code': 'PE000001', 'name': 'FLORAMATIC', 'currency': 'BS', 'amount': 2357369.35}, {'code': 'PL000089', 'name': 'DISTRIBUIDORA DE ALIMENTOS-DISALI', 'currency': 'BS', 'amount': 2122850.0}, {'code': 'PL000153', 'name': 'INDUSTRIA SOLUPLAST S.A.', 'currency': 'BS', 'amount': 1982786.0}, {'code': 'PL000461', 'name': 'MERQUIMIA BOLIVIA S.R.L.', 'currency': 'BS', 'amount': 1827000.0}, {'code': 'PL000007', 'name': 'LABORATORIOS BAGO DE BOLIVIA S.A.', 'currency': 'BS', 'amount': 1758548.04}, {'code': 'PL000026', 'name': 'TERBOL S.A.', 'currency': 'BS', 'amount': 1730502.06}, {'code': 'PL000179', 'name': 'ALCOHOSOL S.R.L', 'currency': 'BS', 'amount': 1615000.0}, {'code': 'PL000270', 'name': 'Coop. Transporte German Busch Ltda.', 'currency': 'BS', 'amount': 1418137.99}, {'code': 'PL000173', 'name': 'DISEÑ-AR S.R.L.', 'currency': 'BS', 'amount': 1306309.0}, {'code': 'PL000183', 'name': 'MAINES SRL', 'currency': 'BS', 'amount': 1158861.39}, {'code': 'PL000017', 'name': 'SAE (SOUTH AMERICAN EXPRESS S.A.)', 'currency': 'BS', 'amount': 1019230.32}, {'code': 'PE000003', 'name': 'LITHOS ASSOCIATION FOR CHEMICAL', 'currency': 'BS', 'amount': 1007917.76}, {'code': 'PL000202', 'name': 'Telchi Asbún Roberto Abraham', 'currency': 'BS', 'amount': 974516.41}]`

## J. CASOS END-TO-END

Los casos se conservan en JSON: cobro ORCT, pago OVPM, depósito ODPS interno, transferencia bancaria interna, comisión manual y movimiento unresolved cuando existen en el período.

## K. INVARIANTES

| Invariante | Resultado |
|---|---|
| FP01_ar_reconciles | PASS |
| FP02_ap_reused_closed_gate | PASS |
| FP03_treasury_reused_closed_gate | PASS |
| FP04_currency_separated | PASS |
| FP05_odps_not_external_cash | PASS |
| FP06_canceled_documents_excluded | PASS |
| FP07_internal_transfers_not_external | PASS |
| FP08_monthly_cash_flow | PASS |
| FP09_opening_flow_closing | PASS |
| FP10_internal_transfers_net | DEGRADED |
| FP11_unresolved_quantified | PASS |
| FP12_classification_coverage_99pct | PASS |
| FP13_contractual_schedules | PASS |
| FP14_real_cases | PASS |
| FP15_sap_write_count | PASS |

## L. TESORERÍA / VALORES EN TRÁNSITO

Valores separados, no sumados a caja/bancos: `[{'currency': '##', 'classification': 'TRANSIT_CLEARING', 'balance': -2201335.42}, {'currency': 'BS', 'classification': 'CARD_CLEARING', 'balance': 61711.19}, {'currency': 'BS', 'classification': 'CHECKS_IN_HAND', 'balance': 48923.46}, {'currency': 'BS', 'classification': 'TRANSIT_CLEARING', 'balance': 75.3}]`.

## M. CASH IN

La entrada económica directa se limita a ORCT activo clasificado `EXTERNAL_CUSTOMER_IN`; ODPS y transferencias internas quedan fuera.

## N. CASH OUT

Las salidas se separan entre proveedor, impuesto, nómina, capex, comisión bancaria y otras; la fecha usada es la del pago/asiento, no la de la factura.

## O. INTERNAL TRANSFERS

El neto observado por la dimensión monetaria es `-68668.93`. El desvío no se compensa cruzando nominalmente `BS` con `USD` o `##`; por eso puede degradar el gate.

## P. TOP SOURCES / USES

Concentración Top 10 entradas/salidas: `{'cash_in': {'total': 146111208.31, 'top10': 49898261.32, 'top10_pct': 34.1509}, 'cash_out': {'total': 89625235.64, 'top10': 40382961.67, 'top10_pct': 45.0576}}`.

## Q. CONTRACTUAL AR

Se publica por due date y moneda; es calendario contractual, no forecast probabilístico.

## R. CONTRACTUAL AP

Se consume del gate AP cerrado y se presenta en los mismos buckets, sin recalcular settlements.

## S. LIQUIDITY GAP

El gap contractual es AR due menos AP due por bucket y moneda; los vencidos no se presentan como cobro futuro.

## T. OVERDUE PRESSURE

AR vencido vs AP vencido por moneda: `[('##', 0.0, 0.0), ('BS', 1392313.82, 4529313.2), ('USD', 0.0, 0.0)]`.

## U. UNRESOLVED

Movimientos unresolved: `14`; importe: `955949.27`; porcentaje: `0.1589%`. La cobertura debe ser ≥99%; el bloqueo actual es el residual de transferencias internas.

## V. CASOS REALES

Casos observados: `[{'case': 'EXTERNAL_CUSTOMER_IN', 'status': 'FOUND', 'evidence': {'REFDATE': '2025-09-02T00:00:00', 'TRANSID': 14465967, 'TRANSTYPE': '24', 'ACCOUNT': '1110206', 'CURRENCY': 'BS', 'NET': 37.5, 'CARDCODE': 'CGRC', 'CARDNAME': 'CONTROL TRIBUTARIO', 'MEMO': 'Pagos recibidos - CGRC', 'CLASSIFICATION': 'EXTERNAL_CUSTOMER_IN'}}, {'case': 'EXTERNAL_SUPPLIER_OUT', 'status': 'FOUND', 'evidence': {'REFDATE': '2025-09-02T00:00:00', 'TRANSID': 14466023, 'TRANSTYPE': '46', 'ACCOUNT': '1111005', 'CURRENCY': 'BS', 'NET': -42648.8, 'CARDCODE': 'PL000168', 'CARDNAME': 'AGENCIA DESPACHANTE DE ADUANA URUBO S.R.L.', 'MEMO': 'Pago AGENCIA DESPACHANTE DE ADUANA URUBO S.R.L. Tributos Fiscales Bs.-42,648.80 YODO FRANMAR N. 388 // CRT N. 14658 TRAMITE N° 2025-1256 URUBO1253.Aut.YLR', 'CLASSIFICATION': 'EXTERNAL_SUPPLIER_OUT'}}, {'case': 'INTERNAL_CASH_TO_BANK', 'status': 'FOUND', 'evidence': {'REFDATE': '2025-09-02T00:00:00', 'TRANSID': 14469839, 'TRANSTYPE': '25', 'ACCOUNT': '1111001', 'CURRENCY': 'BS', 'NET': 30131.58, 'CARDCODE': '', 'CARDNAME': '', 'MEMO': 'Abono#Vta. C/tarjetas BS 30,131.58 del 01/09/2025 CM-2A-1M-RYC-LAB.', 'CLASSIFICATION': 'INTERNAL_CASH_TO_BANK'}}, {'case': 'INTERNAL_BANK_TO_BANK', 'status': 'FOUND', 'evidence': {'REFDATE': '2025-12-31T00:00:00', 'TRANSID': 15766392, 'TRANSTYPE': '-3', 'ACCOUNT': '1110101', 'CURRENCY': 'BS', 'NET': -118010.7, 'CARDCODE': '', 'CARDNAME': '', 'MEMO': 'Cierre de periodo 2025', 'CLASSIFICATION': 'INTERNAL_BANK_TO_BANK'}}, {'case': 'BANK_FEE', 'status': 'NOT_OBSERVED', 'evidence': None}, {'case': 'UNRESOLVED', 'status': 'FOUND', 'evidence': {'REFDATE': '2025-10-24T00:00:00', 'TRANSID': 14683142, 'TRANSTYPE': '18', 'ACCOUNT': '1111001', 'CURRENCY': 'BS', 'NET': -9630.0, 'CARDCODE': '', 'CARDNAME': '', 'MEMO': 'Factura de proveedores - Cancelación - PL000288', 'CLASSIFICATION': 'UNRESOLVED'}}]`.

## W. LIMITACIONES

- GL SAP no demuestra saldo bancario externo ni caja físicamente disponible.
- `##` se conserva separado y no se convierte.
- FX/revaluación se separa de cash cuando el memo permite identificarla; lo demás permanece unresolved.
- Impuestos, nómina, capex y financiación solo se incorporan cuando la evidencia textual/objeto es suficiente.
- Las cuentas fiscales candidatas están en `known_tax_liabilities` y no se mezclan con AP.

## X. PRÓXIMO GATE

Siguiente gate recomendado por evidencia: `TELCHI_CASH_DEPOSIT_CONTROL_V1`. AR ya queda separado como `PASS`; el residual de transferencias internas puede requerir control cash→deposit antes del forecast.

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_position_cash_flow/financial_position_cash_flow_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_position_cash_flow/financial_position_cash_flow_v1.py`
- HANA/SAP: SELECT-only; `SAP_WRITE_COUNT=0`.

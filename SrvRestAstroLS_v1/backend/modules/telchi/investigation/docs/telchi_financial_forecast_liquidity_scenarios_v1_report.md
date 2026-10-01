# TELCHI — FINANCIAL FORECAST / LIQUIDITY / SCENARIOS V1

**Gate:** `TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_PASS`\
**AS_OF_DATE:** `2026-09-10`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`

## A. VEREDICTO EJECUTIVO

Resultado **PASS**. Primer forecast financiero y de liquidez determinístico de Telchi, construido únicamente con documentos reales abiertos al corte, comportamiento histórico de cobro/pago y compromisos de compra. Sin ML. El forecast oficial es document-driven; el overlay de operación continua queda explícito y degradado.

## B. AS_OF_DATE Y TREASURY INICIAL

- Fecha de corte: `2026-09-10`.
- `STARTING_SAP_TREASURY_POSITION`: BS Bs 2,595,009.35, USD Bs 492,943.69, SC_ONLY (no comparable) Bs 2,602,091.90.
- Origen: `TELCHI_FINANCIAL_POSITION_CASH_FLOW_V1_1_PASS`. Control GL tesorería (LC): Bs 5,873,588.27.
- Named STARTING_SAP_TREASURY_POSITION, not AVAILABLE_CASH; no external bank reconciliation exists.

## C. METODOLOGÍA

Se separan cuatro capas: **CONTRACTUAL** (fechas e importes de OINV/OPCH), **EXPECTED** (fechas ajustadas por histogramas empíricos de mora), **FORECAST** (agregación por moneda y horizonte) y **SCENARIO** (variación deliberada de supuestos, documentada). El forecast document-driven oficial no incluye el overlay de operación continua; ese overlay se reporta aparte.

## D. AR CONTRACTUAL

Documentos 2068 · abierto Bs 4,092,786.95.

| Bucket | Docs | Abierto | Vencido |
|---|---:|---:|---:|
| OVERDUE | 963 | Bs 1,477,647.75 | Bs 1,477,647.75 |
| 0-7 | 219 | Bs 683,397.50 | Bs 0.00 |
| 8-15 | 269 | Bs 713,505.81 | Bs 0.00 |
| 16-30 | 529 | Bs 935,843.28 | Bs 0.00 |
| 31-60 | 34 | Bs 232,260.69 | Bs 0.00 |
| 61-90 | 25 | Bs 43,949.20 | Bs 0.00 |
| >90 | 29 | Bs 6,182.72 | Bs 0.00 |

## E. COMPORTAMIENTO DE COBRO

Monto ponderado histórico (24m): Bs 65,383,234.87.
Percentiles de mora respecto a vencimiento: `{'p25': -15.0, 'p50': -3.0, 'p75': 5.0, 'p90': 19.0}`.
Distribución: `{'BEFORE_DUE': 60.4786, 'ON_DUE': 4.7449, '1_7_LATE': 13.2994, '8_30_LATE': 15.5613, '31_60_LATE': 2.8686, 'OVER_60_LATE': 3.0471}`.
Curva de recuperación (deuda vencida, cohortes maduradas): `{0: 0.580364, 7: 0.69948, 15: 0.783308, 30: 0.845947, 60: 0.875983, 90: 0.896534, 180: 0.919425, 365: 0.924222}`.

## F. EXPECTED COLLECTIONS

- BS: Bs 2,985,003.70 en 90 días.
- USD: 0.00 USD en 90 días (AR es 100% BS).

## G. AP CONTRACTUAL

Documentos 636.

| Bucket | Docs | Abierto | Vencido |
|---|---:|---:|---:|
| OVERDUE | 325 | Bs 4,506,018.60 | Bs 4,506,018.60 |
| 0-7 | 102 | Bs 1,212,803.22 | Bs 0.00 |
| 8-15 | 66 | Bs 816,109.67 | Bs 0.00 |
| 16-30 | 108 | Bs 1,076,835.40 | Bs 0.00 |
| 31-60 | 31 | Bs 297,443.33 | Bs 0.00 |
| 61-90 | 0 | Bs 0.00 | Bs 0.00 |
| >90 | 4 | Bs 1,786,501.97 | Bs 0.00 |

## H. COMPORTAMIENTO DE PAGO

Monto ponderado (24m): Bs 98,467,795.44. Percentiles: `{'p25': -3.0, 'p50': 0.0, 'p75': 4.0, 'p90': 23.0}`.
Distribución: `{'BEFORE_DUE': 44.5664, 'ON_DUE': 14.0707, '1_7_LATE': 21.4347, '8_30_LATE': 12.6248, '31_60_LATE': 4.5338, 'OVER_60_LATE': 2.7697}`.
Lag factura→pago: `{'p25': 8.0, 'p50': 21.0, 'p75': 30.0, 'p90': 36.0}`.

## I. EXPECTED PAYMENTS

- BS: Bs 9,547,420.94 en 90 días.
- USD (FC, sin prefijo Bs): 148,291.25 en 90 días.
- Por categoría: `{'TRADE_PAYABLE': {'BS': 4719496.55, 'USD': 148291.25}, 'FINANCING': {'BS': 4827924.39}}` (FINANCING = proveedores bancarios).

## J. OPEN PURCHASE COMMITMENTS

Documentos PO abiertos: 27. Por moneda: `{'BS': 746590.52, 'USD': 133336.66}`. Lead times por tipo: `{'IMP': {'weighted_total': 2666.0, 'mean': 18.09152288072018, 'percentiles': {'p25': 0.0, 'p50': 1.0, 'p75': 12.0, 'p90': 78.0}}, 'LF': {'weighted_total': 47964.0, 'mean': 1.6906221332666167, 'percentiles': {'p25': 0.0, 'p50': 0.0, 'p75': 2.0, 'p90': 4.0}}, 'LP': {'weighted_total': 1482.0, 'mean': 27.972334682861, 'percentiles': {'p25': 5.0, 'p50': 12.0, 'p75': 29.0, 'p90': 70.0}}, 'SAA': {'weighted_total': 29.0, 'mean': 38.86206896551724, 'percentiles': {'p25': 8.0, 'p50': 17.0, 'p75': 55.0, 'p90': 135.0}}}`.

## K. OTHER CASH IN

No se identificó otro cash-in demostrable fuera de AR. Las transferencias internas y depósitos no son cash externo.

## L. OTHER CASH OUT

Estado `DEGRADED` / `HEURISTIC`. Mediana histórica mensual: out bruto Bs 16,997,653.95, net Bs -696,273.99. Se excluye del BASE document-driven por riesgo de doble conteo con AP. El overlay de operación continua usa el **neto** mensual (Bs 696,273.99) como diagnóstico: 90d BS proyectado Bs -5,140,516.53.

## M. BASE FORECAST

| Horiz | Cash in | Cash out | Net gap | Treasury | Min treasury |
|---|---:|---:|---:|---:|---:|
| 7d | Bs 1,025,475.76 | Bs 1,513,815.87 | Bs -488,340.11 | Bs 2,106,669.24 | Bs 2,056,482.83 |
| 15d | Bs 1,971,693.13 | Bs 3,325,001.29 | Bs -1,353,308.16 | Bs 1,241,701.19 | Bs 1,241,701.19 |
| 30d | Bs 2,674,831.86 | Bs 8,106,640.69 | Bs -5,431,808.83 | Bs -2,836,799.48 | Bs -2,836,799.48 |
| 60d | Bs 2,889,753.28 | Bs 8,568,478.84 | Bs -5,678,725.56 | Bs -3,083,716.21 | Bs -3,083,716.21 |
| 90d | Bs 2,964,070.53 | Bs 8,610,774.64 | Bs -5,646,704.11 | Bs -3,051,694.76 | Bs -3,085,957.21 |

## N. CONSERVATIVE SCENARIO

| Horiz | Cash in | Cash out | Net gap | Treasury | Min |
|---|---:|---:|---:|---:|---:|
| 7d | Bs 374,918.97 | Bs 1,814,551.56 | Bs -1,439,632.59 | Bs 1,155,376.76 | Bs 1,155,376.76 |
| 15d | Bs 956,530.66 | Bs 3,516,016.93 | Bs -2,559,486.27 | Bs 35,523.08 | Bs 12,626.25 |
| 30d | Bs 2,191,201.88 | Bs 8,199,656.61 | Bs -6,008,454.73 | Bs -3,413,445.38 | Bs -3,413,445.38 |
| 60d | Bs 2,734,071.27 | Bs 8,978,139.79 | Bs -6,244,068.52 | Bs -3,649,059.17 | Bs -3,849,770.24 |
| 90d | Bs 2,765,579.33 | Bs 9,003,665.29 | Bs -6,238,085.96 | Bs -3,643,076.61 | Bs -3,849,770.24 |

## O. UPSIDE SCENARIO

| Horiz | Cash in | Cash out | Net gap | Treasury | Min |
|---|---:|---:|---:|---:|---:|
| 7d | Bs 1,630,290.81 | Bs 830,362.88 | Bs 799,927.93 | Bs 3,394,937.28 | Bs 2,595,009.35 |
| 15d | Bs 2,281,597.95 | Bs 2,184,612.10 | Bs 96,985.85 | Bs 2,691,995.20 | Bs 2,595,009.35 |
| 30d | Bs 2,772,567.16 | Bs 7,659,496.10 | Bs -4,886,928.94 | Bs -2,291,919.59 | Bs -2,291,919.59 |
| 60d | Bs 2,941,889.04 | Bs 8,039,760.08 | Bs -5,097,871.04 | Bs -2,502,861.69 | Bs -2,535,885.21 |
| 90d | Bs 2,965,053.70 | Bs 8,210,808.59 | Bs -5,245,754.89 | Bs -2,650,745.54 | Bs -2,653,056.76 |

## P. STRESS SCENARIO

| Horiz | Cash in | Cash out | Net gap | Treasury | Min |
|---|---:|---:|---:|---:|---:|
| 7d | Bs 175,271.76 | Bs 2,683,126.01 | Bs -2,507,854.25 | Bs 87,155.10 | Bs 87,155.10 |
| 15d | Bs 466,255.50 | Bs 3,549,013.90 | Bs -3,082,758.40 | Bs -487,749.05 | Bs -487,749.05 |
| 30d | Bs 1,589,347.16 | Bs 8,229,787.68 | Bs -6,640,440.52 | Bs -4,045,431.17 | Bs -4,045,431.17 |
| 60d | Bs 2,587,229.75 | Bs 9,018,262.91 | Bs -6,431,033.16 | Bs -3,836,023.81 | Bs -4,242,712.39 |
| 90d | Bs 2,627,385.35 | Bs 9,043,788.41 | Bs -6,416,403.06 | Bs -3,821,393.71 | Bs -4,242,712.39 |

### STRESS SUPPLIER ACCELERATION

| Horiz | Cash in | Cash out | Net gap | Treasury | Min |
|---|---:|---:|---:|---:|---:|
| 7d | Bs 1,025,475.76 | Bs 2,918,440.67 | Bs -1,892,964.91 | Bs 702,044.44 | Bs 702,044.44 |
| 15d | Bs 1,971,693.13 | Bs 3,654,833.79 | Bs -1,683,140.66 | Bs 911,868.69 | Bs 604,953.06 |
| 30d | Bs 2,674,831.86 | Bs 8,243,797.68 | Bs -5,568,965.82 | Bs -2,973,956.47 | Bs -2,973,956.47 |
| 60d | Bs 2,889,753.28 | Bs 9,018,262.91 | Bs -6,128,509.63 | Bs -3,533,500.28 | Bs -3,573,415.53 |
| 90d | Bs 2,964,070.53 | Bs 9,043,788.41 | Bs -6,079,717.88 | Bs -3,484,708.53 | Bs -3,573,415.53 |

## Q. DAILY 30D (BASE, BS)

| Date | Cash in | Cash out | Net | Closing |
|---|---:|---:|---:|---:|
| 2026-09-10 | 0.00 | 0.00 | 0.00 | 2,595,009.35 |
| 2026-09-11 | 467,225.45 | 803,831.70 | -336,606.25 | 2,258,403.10 |
| 2026-09-12 | 46,552.70 | 61,249.23 | -14,696.53 | 2,243,706.57 |
| 2026-09-13 | 40,593.01 | 127,137.27 | -86,544.26 | 2,157,162.31 |
| 2026-09-14 | 225,031.40 | 325,710.88 | -100,679.48 | 2,056,482.83 |
| 2026-09-15 | 88,349.33 | 56,840.98 | 31,508.35 | 2,087,991.18 |
| 2026-09-16 | 122,228.99 | 26,687.97 | 95,541.02 | 2,183,532.20 |
| 2026-09-17 | 35,494.88 | 112,357.84 | -76,862.96 | 2,106,669.24 |
| 2026-09-18 | 65,464.21 | 343,882.85 | -278,418.64 | 1,828,250.60 |
| 2026-09-19 | 89,380.33 | 23,411.75 | 65,968.58 | 1,894,219.18 |
| 2026-09-20 | 263,074.89 | 227,729.61 | 35,345.28 | 1,929,564.46 |
| 2026-09-21 | 34,403.33 | 251,483.49 | -217,080.16 | 1,712,484.30 |
| 2026-09-22 | 193,492.33 | 22,390.94 | 171,101.39 | 1,883,585.69 |
| 2026-09-23 | 95,425.29 | 158,168.34 | -62,743.05 | 1,820,842.64 |
| 2026-09-24 | 162,986.33 | 346,797.30 | -183,810.97 | 1,637,031.67 |
| 2026-09-25 | 41,990.66 | 437,321.14 | -395,330.48 | 1,241,701.19 |
| 2026-09-26 | 11,961.14 | 19,215.75 | -7,254.61 | 1,234,446.58 |
| 2026-09-27 | 14,366.15 | 146,953.51 | -132,587.36 | 1,101,859.22 |
| 2026-09-28 | 27,803.04 | 57,704.04 | -29,901.00 | 1,071,958.22 |
| 2026-09-29 | 31,574.47 | 75,062.30 | -43,487.83 | 1,028,470.39 |
| 2026-09-30 | 4,150.45 | 57,637.54 | -53,487.09 | 974,983.30 |
| 2026-10-01 | 32,320.10 | 15,650.98 | 16,669.12 | 991,652.42 |
| 2026-10-02 | 167,531.67 | 236,449.86 | -68,918.19 | 922,734.23 |
| 2026-10-03 | 5,068.90 | 1,800.00 | 3,268.90 | 926,003.13 |
| 2026-10-04 | 11,070.02 | 58,247.42 | -47,177.40 | 878,825.73 |
| 2026-10-05 | 79,094.44 | 3,006.00 | 76,088.44 | 954,914.17 |
| 2026-10-06 | 84,028.69 | 580.00 | 83,448.69 | 1,038,362.86 |
| 2026-10-07 | 7,137.55 | 0.00 | 7,137.55 | 1,045,500.41 |
| 2026-10-08 | 38,532.93 | 7,020.90 | 31,512.03 | 1,077,012.44 |
| 2026-10-09 | 111,847.24 | 858,415.04 | -746,567.80 | 330,444.64 |
| 2026-10-10 | 76,651.94 | 3,243,896.06 | -3,167,244.12 | -2,836,799.48 |

## R. WEEKLY 90D (BASE, BS)

| Week | Days | Cash in | Cash out | Net | Closing |
|---|---:|---:|---:|---:|---:|
| W1 | 0-6 | 989,980.88 | 1,401,458.03 | -411,477.15 | 2,183,532.20 |
| W2 | 7-13 | 776,735.26 | 1,139,424.82 | -362,689.56 | 1,820,842.64 |
| W3 | 14-20 | 294,832.24 | 1,140,691.58 | -845,859.34 | 974,983.30 |
| W4 | 21-27 | 386,251.37 | 315,734.26 | 70,517.11 | 1,045,500.41 |
| W5 | 28-34 | 258,876.20 | 4,137,662.09 | -3,878,785.89 | -2,833,285.48 |
| W6 | 35-41 | 145,990.10 | 100,006.03 | 45,984.07 | -2,787,301.41 |
| W7 | 42-48 | 31,594.42 | 301,749.98 | -270,155.56 | -3,057,456.97 |
| W8 | 49-55 | 4,621.55 | 24,216.05 | -19,594.50 | -3,077,051.47 |
| W9 | 56-62 | 871.26 | 9,777.00 | -8,905.74 | -3,085,957.21 |
| W10 | 63-69 | 51,087.05 | 5,289.20 | 45,797.85 | -3,040,159.36 |
| W11 | 70-76 | 1,992.70 | 20,190.10 | -18,197.40 | -3,058,356.76 |
| W12 | 77-83 | 19,900.36 | 3,092.02 | 16,808.34 | -3,041,548.42 |
| W13 | 84-90 | 1,337.14 | 11,483.48 | -10,146.34 | -3,051,694.76 |

## S. MINIMUM TREASURY

BASE BS mínimo Bs -3,085,957.21 en día +61.

## T. FIRST DEFICIT

BASE BS primer déficit: `30` (día offset; None = sin déficit).

## U. FUNDING NEED

BASE BS necesidad máxima teórica: Bs 3,085,957.21. CONSERVATIVE: Bs 3,849,770.24. STRESS: Bs 4,242,712.39.

## V. CUSTOMER CONCENTRATION (cash in)

Top1 10.5417% · Top5 32.9737% · Top10 46.2096%.

## W. SUPPLIER CONCENTRATION (cash out)

BS: Top1 36.3056% · Top5 61.3069% · Top10 71.7435%.
USD: Top1 53.7447% · Top5 100.0%.

## X. LIQUIDITY GAP (7/15/30/60/90)

| Horiz | Net gap | Buffer | Cash coverage | AR coverage |
|---|---:|---:|---:|---:|
| 7d | Bs -488,340.11 | Bs 592,853.37 | 1.7142 | 0.6774 |
| 15d | Bs -1,353,308.16 | Bs -2,083,300.10 | 0.7805 | 0.593 |
| 30d | Bs -5,431,808.83 | Bs -10,943,440.17 | 0.3201 | 0.33 |
| 60d | Bs -5,678,725.56 | Bs -11,652,195.05 | 0.3029 | 0.3373 |
| 90d | Bs -5,646,704.11 | Bs -11,662,469.40 | 0.3014 | 0.3442 |

## Y. LIQUIDITY COVERAGE

AR esperado/abierto: 72.9333%. Unrecovered overdue AR 90d: Bs 1,107,783.34.

## Z. SENSITIVITY

`{"base_30d_projected_treasury": -2836799.48, "base_90d_projected_treasury": -3051694.76, "collection_delay_plus_7d": {"treasury_30d": -3245162.29, "treasury_90d": -3053031.9, "impact_30d": -408362.81, "impact_90d": -1337.14}, "top_customer_non_payment": {"bp": "S0001", "open_amount": 431448.13, "treasury_30d": -2855291.09, "treasury_90d": -3073385.92, "impact_30d": -18491.61, "impact_90d": -21691.16}, "supplier_acceleration_minus_7d": {"treasury_30d": -2911601.09, "treasury_90d": -3102483.88, "impact_30d": -74801.61, "impact_90d": -50789.12}, "note": "Full scenario sensitivities are in forecasts.*.per_currency.BS.coverage."}`

## AA. BACKTEST — METODOLOGÍA

En cada cutoff se reconstruye la información disponible a esa fecha y se predice el cambio de tesorería a 90 días con los documentos con vencimiento en la ventana. Los pagos/cobros posteriores solo miden el resultado. Sin leakage.

## AB. BACKTEST RESULTS

| Cutoff | Treasury start | Actual end | Modelo | Predicho Δ | Actual Δ | MAE |
|---|---:|---:|---|---:|---:|---:|
| 2026-08-11 | Bs 5,599,748.74 | Bs 5,873,588.27 | MODEL_A_DUE_DATE | Bs -1,765,625.68 | Bs 273,839.53 | Bs 2,039,465.21 |
| 2026-08-11 | Bs 5,599,748.74 | Bs 5,873,588.27 | MODEL_B_GLOBAL_P50 | Bs -2,085,074.68 | Bs 273,839.53 | Bs 2,358,914.21 |
| 2026-08-11 | Bs 5,599,748.74 | Bs 5,873,588.27 | MODEL_C_GLOBAL_P75 | Bs -1,926,984.23 | Bs 273,839.53 | Bs 2,200,823.76 |
| 2026-07-12 | Bs 6,923,338.45 | Bs 5,873,588.27 | MODEL_A_DUE_DATE | Bs -4,833,797.65 | Bs -1,049,750.18 | Bs 3,784,047.47 |
| 2026-07-12 | Bs 6,923,338.45 | Bs 5,873,588.27 | MODEL_B_GLOBAL_P50 | Bs -4,906,151.10 | Bs -1,049,750.18 | Bs 3,856,400.92 |
| 2026-07-12 | Bs 6,923,338.45 | Bs 5,873,588.27 | MODEL_C_GLOBAL_P75 | Bs -3,850,223.72 | Bs -1,049,750.18 | Bs 2,800,473.54 |
| 2026-06-12 | Bs 5,850,519.10 | Bs 5,873,588.27 | MODEL_A_DUE_DATE | Bs -3,534,249.14 | Bs 23,069.17 | Bs 3,557,318.31 |
| 2026-06-12 | Bs 5,850,519.10 | Bs 5,873,588.27 | MODEL_B_GLOBAL_P50 | Bs -3,597,836.20 | Bs 23,069.17 | Bs 3,620,905.37 |
| 2026-06-12 | Bs 5,850,519.10 | Bs 5,873,588.27 | MODEL_C_GLOBAL_P75 | Bs -1,599,373.31 | Bs 23,069.17 | Bs 1,622,442.48 |
| 2026-03-14 | Bs 8,312,560.21 | Bs 5,850,519.10 | MODEL_A_DUE_DATE | Bs -2,129,119.20 | Bs -2,462,041.11 | Bs 332,921.91 |
| 2026-03-14 | Bs 8,312,560.21 | Bs 5,850,519.10 | MODEL_B_GLOBAL_P50 | Bs -2,274,007.48 | Bs -2,462,041.11 | Bs 188,033.63 |
| 2026-03-14 | Bs 8,312,560.21 | Bs 5,850,519.10 | MODEL_C_GLOBAL_P75 | Bs -816,164.20 | Bs -2,462,041.11 | Bs 1,645,876.91 |
| 2025-09-10 | Bs 5,906,908.05 | Bs 5,758,082.06 | MODEL_A_DUE_DATE | Bs -4,518,467.81 | Bs -148,825.99 | Bs 4,369,641.82 |
| 2025-09-10 | Bs 5,906,908.05 | Bs 5,758,082.06 | MODEL_B_GLOBAL_P50 | Bs -4,807,236.18 | Bs -148,825.99 | Bs 4,658,410.19 |
| 2025-09-10 | Bs 5,906,908.05 | Bs 5,758,082.06 | MODEL_C_GLOBAL_P75 | Bs -2,029,517.94 | Bs -148,825.99 | Bs 1,880,691.95 |

Agregados:
| Modelo | Treasury MAE | Bias | MAE % | Direccional |
|---|---:|---:|---:|---:|
| MODEL_A_DUE_DATE | Bs 2,816,678.94 | Bs 2,683,510.18 | 48.2579 | 60.0 |
| MODEL_B_GLOBAL_P50 | Bs 2,936,532.86 | Bs 2,861,319.41 | 50.3163 | 60.0 |
| MODEL_C_GLOBAL_P75 | Bs 2,030,061.73 | Bs 1,371,710.96 | 34.7131 | 60.0 |

### Date accuracy (MAE en días de la fecha de cobro/pago)
| Cutoff | AR A | AR B | AR C | AP A | AP B | AP C |
|---|---:|---:|---:|---:|---:|---:|
| 2026-08-11 | 20.6096 | 19.3241 | 27.3499 | 4.838 | 4.838 | 14.8287 |
| 2026-07-12 | 20.5731 | 19.4327 | 26.6457 | 6.672 | 6.672 | 16.064 |
| 2026-06-12 | 21.9569 | 20.67 | 28.4428 | 6.8346 | 6.8346 | 16.25 |
| 2026-03-14 | 18.5926 | 17.8389 | 23.8411 | 8.0505 | 8.0505 | 16.1606 |
| 2025-09-10 | 20.581 | 18.5551 | 26.0267 | 14.7966 | 13.3983 | 15.2627 |

El modelo se seleccionó por **treasury MAE** (objetivo de liquidez). En date MAE el modelo A/B es mejor; el trade-off queda explícito y no se oculta.

**Modelo seleccionado:** `MODEL_C_GLOBAL_P75`.

## AC. MODEL SELECTION

Baselines comparados: A (DueDate contractual), B (DueDate + mediana histórica de mora p50) y C (DueDate + p75 histórico de mora). La selección se hizo por backtest de tesorería.

## AD. COVERAGE

AR docs 2068, open Bs 4,092,786.95, expected Bs 2,985,003.61. AP docs 636. PO docs 27, Bs 879,927.18.

## AE. UNRESOLVED

UNRESOLVED_FORECAST_AMOUNT (AR no recuperable en 90d): Bs 1,107,783.34. No se esconde dentro de 'otros'.

## AF. REAL CASES

| Caso | Source | DocEntry | DocNum | BP | Original | Due | Expected | Amount | Rule | Conf |
|---|---|---:|---:|---|---|---|---|---:|---|---|
| A_AR_CONTRACTUAL_ON_TIME | AR_DOCUMENT | 11466934 | 261406512 | C000143 | 2026-08-10 | 2026-09-25 | 2026-09-14 | Bs 114,800.00 | AR_NOT_DUE_CUSTOMER_P50 | HIGH |
| B_AR_COLLECTED_LATE | AR_DOCUMENT | 11495876 | 261407072 | C004755 | 2026-08-28 | 2026-08-31 | 2026-09-23 | Bs 29,091.00 | AR_OVERDUE_RECOVERY_SEGMENT_H90_P50 | MEDIUM |
| C_AR_OVERDUE_LOW_PREDICTABILITY | AR_DOCUMENT | 10818958 | 22014947 | S0001 | 2022-10-30 | 2022-10-30 | 2026-10-10 | Bs 0.00 | AR_OVERDUE_RECOVERY_CUSTOMER_H90_P50 | LOW |
| D_AP_PAID_NEAR_DUE | AP_DOCUMENT | 42098 | 252102771 | PL000288 | 2025-12-31 | 2026-12-20 | 2026-12-20 | Bs -889,179.79 | AP_NOT_DUE_CUSTOMER_P50 | CONTRACTUAL |
| E_AP_PAID_EARLY_OR_LATE | AP_DOCUMENT | 3639 | 524 | PL000212 | 2022-03-31 | 2022-03-31 | 2026-10-10 | Bs -2,058,765.91 | AP_OVERDUE_CUSTOMER_P50 | LOW |
| F_OPEN_PO_TO_FUTURE_AP | OPEN_PO | 25612 | 262001399 | PL000063 | 2026-04-25 | 2026-09-11 | 2026-10-09 | Bs -509,477.97 | OPEN_PO_LF_LEAD_P50_PAYLAG_P50 | MEDIUM |
| G_RECURRING_CASH_OUT_RULE | RECURRING_OPEX | None | None | None | None | None | 2026-10-10 | n/a | HISTORICAL_MONTHLY_OPERATING_NET | LOW |
| H_COLLECTION_DELAY_PRESSURE | SCENARIO | None | None | None | None | None | 2026-09-18 | Bs -4,242,712.39 | STRESS_COLLECTION_DELAY | LOW |
| I_BACKTEST_CORRECT | BACKTEST | None | None | None | 2026-06-12 | 2026-09-10 | None | Bs 1,622,442.48 | MODEL_C_GLOBAL_P75 | MEDIUM |
| J_BACKTEST_MATERIAL_ERROR | BACKTEST | None | None | None | 2026-07-12 | 2026-10-10 | None | Bs 2,800,473.54 | MODEL_C_GLOBAL_P75 | LOW |

## AG. INVARIANTS

| Invariante | Resultado |
|---|---|
| FC01_starting_treasury_reconciles_financial_position | PASS |
| FC02_projected_ar_open_at_cutoff | PASS |
| FC03_projected_ap_open_at_cutoff | PASS |
| FC04_no_post_cutoff_documents_in_backtest | PASS |
| FC05_no_ap_po_double_count | PASS |
| FC06_no_orct_odps_double_count | PASS |
| FC07_internal_transfers_not_external_cash | PASS |
| FC08_fx_accounting_only_not_cash | PASS |
| FC09_currencies_not_summed_nominally | PASS |
| FC10_expected_collections_reproducible | PASS |
| FC11_expected_payments_reproducible | PASS |
| FC12_scenario_assumptions_explicit | PASS |
| FC13_backtest_no_leakage | PASS |
| FC14_forecast_coverage_measured | PASS |
| FC15_unresolved_quantified | PASS |
| FC16_sap_write_count | PASS |
| FC17_ar_expected_within_open | PASS |
| FC18_ap_projected_in_full | PASS |
| FC19_currency_separation | PASS |

## AH. LIMITATIONS

- Forecast is document-driven: it projects only open AR, open AP and open PO existing at the cutoff.
- No new sales, payroll, tax or CAPEX beyond known open documents (DEGRADED per gate rules).
- STARTING_SAP_TREASURY_POSITION is an accounting position; no external bank statement reconciliation exists.
- WHT projection remains degraded and is excluded.
- SC_ONLY treasury is not nominally comparable and is excluded from consolidated liquidity.
- Recovery curves assume historical behaviour repeats; matured-cohort survivors are excluded from settled histograms.
- About half of the 90-day AP outflow is FINANCING (bank suppliers, mostly overdue); SAP stores it as open invoices without an installment schedule, so the model treats it as payable. Excluding financing, the document-driven 90-day BS position is positive.

## AI. BUSINESS INTERPRETATION

`{"can_pay_next_30d_with_current_treasury": false, "base_30d_projected_treasury": -2836799.48, "base_90d_projected_treasury": -3051694.76, "base_90d_projected_treasury_excluding_financing": 113925.98, "conservative_90d_projected_treasury": -3643076.61, "stress_90d_projected_treasury": -3821393.71, "base_first_deficit_day_offset": 30, "stress_first_deficit_day_offset": 8, "base_minimum_treasury": {"minimum_treasury": -3085957.21, "date_offset": 61, "net": -2241.0}, "risk_flag": "DEFICIT", "financing_outflow_bs_90d": 4827924.39, "trade_outflow_bs_90d": 4719496.55, "top_customer_concentration_pct": 10.5417, "top_supplier_concentration_pct_bs": 36.3056, "top_supplier_concentration_pct_usd": 53.7447}`

## AJ. NEXT GATE

`TELCHI_FINANCIAL_CONTROL_POLICIES_AND_ALERTS_V1` para convertir el forecast en controles, o `TELCHI_FINANCIAL_BUDGET_AND_PLAN_V1` para presupuesto y P&L/balance proyectado.

## Artefactos

- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_forecast_liquidity_scenarios/financial_forecast_liquidity_scenarios_v1.py`
- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_forecast_liquidity_scenarios/financial_forecast_liquidity_scenarios_v1.json`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

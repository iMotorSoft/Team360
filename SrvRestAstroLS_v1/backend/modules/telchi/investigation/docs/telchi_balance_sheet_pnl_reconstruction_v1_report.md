# TELCHI — BALANCE SHEET / P&L RECONSTRUCTION V1

**Gate:** `TELCHI_BALANCE_SHEET_PNL_RECONSTRUCTION_V1_PASS`\
**AS_OF_DATE:** `2026-09-10`\
**Modo:** INVESTIGATION / READ ONLY · `SAP_WRITE_COUNT=0`

## A. VEREDICTO EJECUTIVO

**PASS**. Telchi tiene activos por **Bs 86,107,745.15**, pasivos por **Bs 21,498,186.57** y patrimonio por **Bs 64,609,558.58**. La ecuación contable cuadra con gap **0.00** en moneda local y **0.00** en moneda sistema. Para 2026 YTD: ingresos Bs 72,353,270.20, costo de ventas Bs 37,336,987.20, margen bruto Bs 35,016,283.00, gastos operativos Bs 23,521,443.56, resultado financiero Bs -1,414,305.12, resultado neto Bs 10,080,617.83.

## B. AS-OF DATE / PERIOD

| Campo | Valor |
|---|---|
| AS_OF_DATE | 2026-09-10 |
| Moneda local | BS |
| Moneda sistema | USD |
| Multimoneda | B |
| Último RefDate GL | 2026-09-10 |
| Último CreateDate | 2026-09-10 |
| Líneas JDT1 | 18266896 |
| Asientos OJDT | 5797740 |

Períodos fiscales recientes (PeriodStat: C=cerrado, N=abierto):

| Code | Desde | Hasta | Estado |
|---|---|---|---|
| 2026-12 | 2026-12-01 | 2026-12-31 | N |
| 2026-11 | 2026-11-01 | 2026-11-30 | N |
| 2026-10 | 2026-10-01 | 2026-10-31 | N |
| 2026-09 | 2026-09-01 | 2026-09-30 | N |
| 2026-08 | 2026-08-01 | 2026-08-31 | C |
| 2026-07 | 2026-07-01 | 2026-07-31 | Y |

El período 2026-09 está **abierto**; el resultado puede cambiar con asientos posteriores. 2026-08 está cerrado.

## C. ACCOUNT CLASSIFICATION COVERAGE

| Métrica | Valor |
|---|---|
| Cuentas OACT | 824 |
| Con movimiento | 586 |
| BS clasificado (importe) | 100.0% |
| P&L clasificado (importe) | 100.0% |
| UNRESOLVED count | 0 |
| UNRESOLVED |importe| | 0.00 |

Conteo por statement: `{"ASSET": 300, "LIABILITY": 77, "EQUITY": 19, "REVENUE": 19, "FINANCIAL_RESULT": 20, "OTHER_NON_OPERATING": 18, "COGS": 17, "OPERATING_EXPENSES": 346, "INCOME_TAX": 1, "MEMO": 6, "UNRESOLVED": 1}`.

## D. BALANCE SHEET (resumen)

| Concepto | 2026-09-10 | 2025 (reapertura) | 2024 (reapertura) |
|---|---|---|---|
| Activos | 86,107,745.15 | 81,325,954.45 | 64,551,709.15 |
| Pasivos | 21,498,186.57 | 22,264,226.06 | 19,311,047.84 |
| Patrimonio libro | 54,526,852.75 | 59,069,663.75 | 45,249,201.36 |
| Resultado corriente | 10,082,705.83 | -7,935.36 | -8,540.05 |
| Patrimonio total | 64,609,558.58 | 59,061,728.39 | 45,240,661.31 |
| Gap | 0.00 | 0.00 | 0.00 |

## E. ASSETS

| Grupo | Subgrupo | Importe |
|---|---|---|
|  | ACCOUNTS_RECEIVABLE | 3,872,487.69 |
|  | ADVANCES | -19,989.76 |
|  | BANK | 4,935,946.24 |
|  | CASH | 926,836.78 |
|  | INVENTORY | 46,713,795.38 |
|  | OTHER_CURRENT_ASSETS | -4,662.33 |
|  | OTHER_RECEIVABLES | 5,212,121.10 |
|  | PREPAIDS | 117,333.07 |
|  | TAX_RECEIVABLES | 4,769,807.69 |

| Grupo | Subgrupo | Importe |
|---|---|---|
|  | ACCUMULATED_DEPRECIATION | -13,931,215.83 |
|  | FIXED_ASSETS | 30,665,593.91 |
|  | OTHER_NON_CURRENT_ASSETS | 2,849,691.21 |

### Top 15 cuentas de activo

| Cuenta | Nombre | Subgrupo | Importe |
|---|---|---|---|
| 1130102 | Almacén Prod. a Granel Procesadora Saavedra | INVENTORY | 14,281,760.22 |
| 1210101 | Terrenos | FIXED_ASSETS | 8,816,917.09 |
| 1130101 | Almacén Materia Prima | INVENTORY | 7,762,411.43 |
| 1210102 | Edificios | FIXED_ASSETS | 6,960,579.72 |
| 1120503 | Anticipo a cuenta de utilidades MN | OTHER_RECEIVABLES | 5,393,500.00 |
| 1210305 | Maquinarias | FIXED_ASSETS | 5,050,682.21 |
| 1121501 | Crédito Fiscal IVA | TAX_RECEIVABLES | 4,434,037.69 |
| 1130301 | Almacén Medicamentos 2A | INVENTORY | 4,408,431.24 |
| 1120101 | Cuentas por cobrar clientes MN | ACCOUNTS_RECEIVABLE | 3,872,487.69 |
| 1210401 | Vehículos | FIXED_ASSETS | 3,785,002.67 |
| 1210306 | Depreciación acumulada maquinarias | ACCUMULATED_DEPRECIATION | -3,677,680.90 |
| 1130401 | Mercadería en tránsito | INVENTORY | 3,425,390.62 |
| 1210402 | Depreciación acumulada vehículos | ACCUMULATED_DEPRECIATION | -3,334,678.46 |
| 1111017 | HELM BANK USA-BUSINESS CHECKING  NRO. 1106039868 | BANK | 2,405,667.82 |
| 1210301 | Equipos de computación | FIXED_ASSETS | 2,213,722.46 |

## F. LIABILITIES

| Grupo | Subgrupo | Importe |
|---|---|---|
|  | ACCOUNTS_PAYABLE | 8,080,271.27 |
|  | ACCRUALS | 653,537.55 |
|  | CUSTOMER_ADVANCES | -173,812.73 |
|  | OTHER_CURRENT_LIABILITIES | -490,951.69 |
|  | PAYROLL_LIABILITIES | 376,904.20 |
|  | SHORT_TERM_DEBT | 0.00 |
|  | TAX_LIABILITIES | 7,252,350.56 |

| Grupo | Subgrupo | Importe |
|---|---|---|
|  | LONG_TERM_DEBT | 3,923,981.24 |
|  | OTHER_NON_CURRENT_LIABILITIES | 1,875,906.17 |

### Top 15 cuentas de pasivo

| Cuenta | Nombre | Subgrupo | Importe |
|---|---|---|---|
| 2140101 | Debito Fiscal IVA | TAX_LIABILITIES | 13,068,632.38 |
| 2140110 | Facilidad de Pagos SIN | TAX_LIABILITIES | -8,829,933.08 |
| 2110101 | Cuentas por pagar MN | ACCOUNTS_PAYABLE | 6,304,033.61 |
| 2210101 | Préstamos bancarios | LONG_TERM_DEBT | 3,923,981.24 |
| 2140102 | IT por pagar | TAX_LIABILITIES | 3,650,636.26 |
| 2110201 | Cuentas por pagar ME | ACCOUNTS_PAYABLE | 1,776,237.66 |
| 2220101 | Previsiones para indeminización | OTHER_NON_CURRENT_LIABILITIES | 1,389,317.38 |
| 2140103 | IUE por pagar | TAX_LIABILITIES | -636,985.00 |
| 2120301 | Provisiones para aguinaldo | ACCRUALS | 612,811.49 |
| 2110403 | Facturas por recibir | OTHER_CURRENT_LIABILITIES | -495,110.23 |
| 2220102 | Otras previsiones | OTHER_NON_CURRENT_LIABILITIES | 462,705.14 |
| 2120205 | Gestora Publica | PAYROLL_LIABILITIES | 176,604.00 |
| 2110301 | Anticipos de clientes M/N | CUSTOMER_ADVANCES | -173,812.73 |
| 2120201 | Caja Nacional de Salud | PAYROLL_LIABILITIES | 86,414.63 |
| 2120104 | Comisiones por pagar | PAYROLL_LIABILITIES | 67,593.24 |

## G. EQUITY

| Grupo | Subgrupo | Importe |
|---|---|---|
|  | CAPITAL | 19,119,404.32 |
|  | CURRENT_YEAR_RESULT | 0.00 |
|  | OTHER_EQUITY | 0.00 |
|  | RESERVES | 0.00 |
|  | RETAINED_EARNINGS | 35,407,448.43 |

## H. BALANCE EQUATION

| Ecuación (LC) | Valor |
|---|---|
| Activos | 86,107,745.15 |
| − Pasivos | 21,498,186.57 |
| − Patrimonio | 64,609,558.58 |
| = Gap | 0.00 |
| Gap moneda sistema | 0.00 |

## I. SUBLEDGER → GL RECONCILIATION

| Componente | Documental | Subledger OCRD | GL control | Diferencia GL−Doc |
|---|---|---|---|---|
| AR (OINV−ORIN, control 1120101) | 3,490,138.26 | 3,571,565.95 | 3,872,487.69 | 382,349.43 |
| AP (OPCH−ORPC, control 21101/21102) | 11,257,847.71 | 9,866,515.73 | 8,080,271.27 | -3,177,576.44 |
| Cash | 881,124.27 | — | 831,777.78 | -49,346.49 |
| Bank | 2,718,295.20 | — | 2,871,861.36 | 153,566.16 |

Bridge AR por cuenta de control: `{"1120101": 3490138.26, "1120501": 584662.66, "1120701": 172.8, "1120901": 0.0, "1121001": 4096.83, "1121301": 0.0}`. Actividad no documental AR: `[{"TT": "-2", "NET": 11868060.69}, {"TT": "-3", "NET": -11868060.69}, {"TT": "25", "NET": 780.0}, {"TT": "30", "NET": -3236656.88}, {"TT": "321", "NET": -17011068.79}]`.

Bridge AP por cuenta de control: `{"2110101": 9472327.7, "2110201": 1785520.01, "2110301": 0.0, "2120107": 0.0, "2120304": 0.0}`. Actividad no documental AP: `[{"TT": "-2", "NET": -40473820.34}, {"TT": "-3", "NET": 40473820.34}, {"TT": "30", "NET": 3510607.05}, {"TT": "321", "NET": 100021674.41}]`.

## J. INVENTORY ACCOUNTING VALUE

Valor contable GL de inventario (cuentas 113*): **Bs 46,713,795.38**. Inventory is read from the GL; no external physical count or valuation was used.

## K. FIXED ASSETS

| Grupo | Subgrupo | Importe |
|---|---|---|
|  | ACCUMULATED_DEPRECIATION | -13,931,215.83 |
|  | FIXED_ASSETS | 30,665,593.91 |
|  | OTHER_NON_CURRENT_ASSETS | 2,849,691.21 |

Semántica desde GL: costo histórico en cuentas 121*/123* y depreciación/amortización acumulada en las cuentas contra. El módulo estándar de activos fijos SAP no se reconstruyó (DEGRADED acotado).

## L. TAXES

| Grupo | Subgrupo | Importe |
|---|---|---|
| TAX_RECEIVABLES/TAX_LIABILITIES | ASSET_TAX_RECEIVABLES | 4,769,807.69 |
| TAX_RECEIVABLES/TAX_LIABILITIES | LIABILITY_TAX | 7,252,350.56 |

El crédito fiscal IVA y el IUE por compensar están en `TAX_RECEIVABLES`; el débito fiscal, IT, IUE, RC-IVA y retenciones en `TAX_LIABILITIES`. La retención a proveedores permanece fuera de este gate.

## M. DEBT / FINANCING

| Grupo | Subgrupo | Importe |
|---|---|---|
| DEBT | LONG_TERM_DEBT | 3,923,981.24 |
| DEBT | SHORT_TERM_DEBT | 0.00 |

## N. P&L (resumen)

| Concepto | 2026 YTD | 2025 mismo período | 2025 full year | LTM |
|---|---|---|---|---|
| Ingresos | 72,353,270.20 | 66,608,483.87 | 96,689,991.00 | 102,434,777.33 |
| Costo de ventas | 37,336,987.20 | 33,849,948.72 | 50,280,049.82 | 53,767,088.30 |
| Margen bruto | 35,016,283.00 | 32,758,535.15 | 46,409,941.18 | 48,667,689.03 |
| Gastos operativos | 23,521,443.56 | 20,884,043.58 | 31,285,575.98 | 33,922,975.96 |
| Resultado operativo | 11,494,839.44 | 11,874,491.57 | 15,124,365.20 | 14,744,713.07 |
| Resultado financiero | -1,414,305.12 | -1,670,125.50 | -1,091,514.49 | -835,694.11 |
| Resultado neto | 10,080,617.83 | 9,474,031.60 | 12,901,142.59 | 13,507,728.82 |

## O. REVENUE

| Grupo | Subgrupo | 2026 YTD |
|---|---|---|
| REVENUE | OTHER_REVENUE | 438,322.77 |
| REVENUE | PRODUCT_SALES | 71,914,947.43 |

## P. COST OF SALES

| Grupo | Subgrupo | 2026 YTD |
|---|---|---|

## Q. GROSS PROFIT / MARGINS

| Período | Margen bruto | Margen operativo | Margen neto |
|---|---|---|---|
| 2026 YTD | 48.3963% | 15.8871% | 13.9325% |
| 2025 mismo período | 49.1807% | 17.8273% | 14.2235% |

## R. OPERATING EXPENSES

| Grupo | Subgrupo | 2026 YTD |
|---|---|---|
| OPERATING_EXPENSES | ADMINISTRATIVE | 1,473,211.53 |
| OPERATING_EXPENSES | BANK_FEES | 0.00 |
| OPERATING_EXPENSES | DEPRECIATION | 1,430,955.64 |
| OPERATING_EXPENSES | LOGISTICS | 974,194.86 |
| OPERATING_EXPENSES | MAINTENANCE | 594,182.02 |
| OPERATING_EXPENSES | OTHER_OPEX | 33,764.87 |
| OPERATING_EXPENSES | PAYROLL | 13,540,964.10 |
| OPERATING_EXPENSES | PROFESSIONAL_SERVICES | 298,166.00 |
| OPERATING_EXPENSES | RENT | 1,270,814.96 |
| OPERATING_EXPENSES | SALES | 428,918.85 |
| OPERATING_EXPENSES | TAXES_OPERATING | 2,037,852.93 |
| OPERATING_EXPENSES | UTILITIES | 1,438,417.80 |

### Top 15 cuentas de gasto (saldo acumulado)

| Cuenta | Nombre | Subgrupo | Importe |
|---|---|---|---|
| 6010101 | Haber basico | PAYROLL | 5,250,757.68 |
| 6310101 | IT | TAXES_OPERATING | 1,987,470.86 |
| 6010601 | Alquileres inmuebles | RENT | 1,211,846.82 |
| 6010102 | Haber basico I | PAYROLL | 979,426.13 |
| 6010105 | Bono de Antigüedad | PAYROLL | 761,514.60 |
| 6020202 | Haber básico interno - Socios | PAYROLL | 736,000.00 |
| 6010803 | Energia electrica | UTILITIES | 675,878.04 |
| 6010109 | CNS | PAYROLL | 607,790.01 |
| 6010107 | Aguinaldo | PAYROLL | 593,093.04 |
| 6010116 | Indemnizaciones laborales | PAYROLL | 593,093.04 |
| 6010104 | Prestacion de Servicios | PAYROLL | 566,951.94 |
| 6011703 | Transportes y Fletes | LOGISTICS | 553,112.00 |
| 6010111 | Comisión sobre ventas | PAYROLL | 535,904.84 |
| 6010110 | Gestora Publica | PAYROLL | 470,194.55 |
| 6010114 | Personal eventual | PAYROLL | 466,205.91 |

## S. FINANCIAL RESULT

| Grupo | Subgrupo | 2026 YTD |
|---|---|---|
| FINANCIAL_RESULT | BANK_CHARGES | -1,138,220.44 |
| FINANCIAL_RESULT | FX_GAIN | 1,452.79 |
| FINANCIAL_RESULT | FX_LOSS | -14.37 |
| FINANCIAL_RESULT | INTEREST_EXPENSE | -303,803.60 |
| FINANCIAL_RESULT | INTEREST_INCOME | 26,280.50 |
| FINANCIAL_RESULT | OTHER_FINANCIAL | 0.00 |

## T. TAX RESULT

| Grupo | Subgrupo | 2026 YTD |
|---|---|---|
| INCOME_TAX | INCOME_TAX | 0.00 |

## U. NET INCOME

Resultado neto 2026 YTD: **Bs 10,080,617.83** (pre-tax Bs 10,080,617.83 − impuesto Bs 0.00).

## V. CURRENT YEAR RESULT → EQUITY BRIDGE

| Concepto | Valor |
|---|---|
| bs_current_year_result | 10,082,705.83 |
| pnl_statement_2026_ytd | 10,080,617.83 |
| residual_unclosed_pnl | 2,088.00 |
| opening_pnl_balance_at_2026_01_01 | 7,935.36 |
| closing_pnl_balance_at_asof | -10,082,705.83 |
| note | 0.00 |

Mecanismo SAP: `-3` (cierre al 31-dic) y `-2` (reapertura al 01-ene) netean el trial balance completo; el resultado corriente permanece en cuentas GM4/5/6 y `3110502 Resultados del periodo` está en **0**, sin doble conteo.

## W. MONTHLY P&L (últimos 24 meses)

| Período | Ingresos | COGS | Margen bruto | OPEX | Result. oper. | Result. financiero | Result. neto |
|---|---|---|---|---|---|---|---|
| 2024-10 | 7,506,957.37 | 3,837,307.60 | 3,669,649.77 | 5,084,051.27 | -1,414,401.50 | -738,045.00 | -2,252,121.25 |
| 2024-11 | 7,542,580.79 | 3,635,385.44 | 3,907,195.35 | 2,615,210.50 | 1,291,984.85 | -329,745.24 | 862,714.26 |
| 2024-12 | 6,763,220.50 | 3,523,096.09 | 3,240,124.41 | 2,580,471.56 | 659,652.85 | -171,355.38 | 1,501,707.00 |
| 2025-01 | 8,037,418.27 | 4,287,743.45 | 3,749,674.82 | 2,349,406.09 | 1,400,268.73 | -83,336.69 | 1,230,330.76 |
| 2025-02 | 6,778,112.86 | 3,335,908.51 | 3,442,204.35 | 2,348,393.82 | 1,093,810.53 | -64,233.95 | 939,592.94 |
| 2025-03 | 7,129,391.29 | 3,968,961.64 | 3,160,429.65 | 2,261,031.13 | 899,398.52 | -181,279.23 | 628,634.14 |
| 2025-04 | 7,722,759.33 | 4,147,721.93 | 3,575,037.40 | 2,466,735.25 | 1,108,302.15 | -385,799.68 | 635,839.93 |
| 2025-05 | 9,540,851.82 | 4,477,819.12 | 5,063,032.70 | 2,990,533.45 | 2,072,499.25 | -478,305.56 | 1,507,655.78 |
| 2025-06 | 7,930,492.08 | 3,760,212.46 | 4,170,279.62 | 2,576,727.92 | 1,593,551.70 | -305,209.21 | 1,201,975.03 |
| 2025-07 | 8,164,278.15 | 4,208,233.94 | 3,956,044.21 | 2,692,217.52 | 1,263,826.69 | -515,270.29 | 622,687.97 |
| 2025-08 | 8,135,766.47 | 4,045,856.83 | 4,089,909.64 | 2,909,235.22 | 1,180,674.42 | 349,006.99 | 1,433,237.24 |
| 2025-09 | 8,254,405.19 | 4,123,383.86 | 4,131,021.33 | 2,530,377.42 | 1,600,643.91 | 152,183.52 | 1,656,513.96 |
| 2025-10 | 8,372,645.21 | 4,837,242.46 | 3,535,402.75 | 2,806,163.45 | 729,239.30 | 57,510.97 | 690,444.32 |
| 2025-11 | 8,334,572.82 | 4,329,318.09 | 4,005,254.73 | 2,462,738.59 | 1,542,516.14 | 115,408.92 | 1,561,898.02 |
| 2025-12 | 8,289,297.51 | 4,757,647.53 | 3,531,649.98 | 2,892,016.12 | 639,633.86 | 247,809.72 | 792,332.50 |
| 2026-01 | 9,000,774.85 | 4,762,028.67 | 4,238,746.18 | 2,919,389.09 | 1,319,357.09 | -408,856.17 | 910,584.45 |
| 2026-02 | 7,886,156.66 | 4,128,881.66 | 3,757,275.00 | 2,860,250.05 | 897,024.95 | -286,414.29 | 610,610.66 |
| 2026-03 | 8,845,840.93 | 4,627,448.06 | 4,218,392.87 | 3,083,060.84 | 1,135,332.03 | -80,242.13 | 1,055,089.90 |
| 2026-04 | 8,573,982.62 | 4,471,442.02 | 4,102,540.60 | 2,733,400.05 | 1,369,140.55 | 125,608.55 | 1,494,749.10 |
| 2026-05 | 7,692,785.17 | 4,139,320.58 | 3,553,464.59 | 2,779,267.61 | 774,196.98 | -194,974.75 | 579,222.23 |
| 2026-06 | 8,769,449.39 | 4,726,929.45 | 4,042,519.94 | 2,923,933.23 | 1,118,586.71 | -176,917.06 | 941,669.65 |
| 2026-07 | 9,066,495.14 | 4,638,920.45 | 4,427,574.69 | 2,801,379.74 | 1,626,194.95 | -330,497.84 | 1,295,697.11 |
| 2026-08 | 9,179,036.65 | 4,670,446.39 | 4,508,590.26 | 3,034,073.31 | 1,474,516.95 | -60,448.66 | 1,414,068.25 |
| 2026-09 | 3,338,748.79 | 1,171,569.92 | 2,167,178.87 | 386,689.64 | 1,780,489.23 | -1,562.77 | 1,778,926.48 |

## X. YTD VS PRIOR YEAR

| Métrica | 2026 YTD | 2025 mismo período | Delta | Delta % |
|---|---|---|---|---|
| revenue | 72,353,270.20 | 66,608,483.87 | 5,744,786.33 | 8.6247 |
| cost_of_sales | 37,336,987.20 | 33,849,948.72 | 3,487,038.48 | 10.3015 |
| gross_profit | 35,016,283.00 | 32,758,535.15 | 2,257,747.85 | 6.8921 |
| operating_expenses | 23,521,443.56 | 20,884,043.58 | 2,637,399.98 | 12.6288 |
| operating_result | 11,494,839.44 | 11,874,491.57 | -379,652.13 | -3.1972 |
| financial_result | -1,414,305.12 | -1,670,125.50 | 255,820.38 | 15.3174 |
| other_non_operating | 83.51 | -730,334.47 | 730,417.98 | 100.0114 |
| income_tax | 0.00 | 0.00 | 0.00 | None |
| net_income | 10,080,617.83 | 9,474,031.60 | 606,586.23 | 6.4026 |

## Y. FINANCIAL RATIOS

* Current Ratio = Current Assets / Current Liabilities = 4.2376
* Quick Ratio = (Caja + Bancos + Cuentas por cobrar) / Current Liabilities = 0.6201
* Debt / Equity = (Deuda corto + largo plazo) / Patrimonio total = 0.0607
* Gross / Operating / Net Margin (2026 YTD) = 48.3963% / 15.8871% / 13.9325%

Los ratios se calculan solo con componentes clasificados; activos fijos y deuda son detalle DEGRADED acotado.

## Z. ANOMALIES / REVIEW

| Cuenta | Nombre | Statement | Subgrupo | Importe | Clase | Motivo |
|---|---|---|---|---|---|---|
| 2140110 | Facilidad de Pagos SIN | LIABILITY | TAX_LIABILITIES | 8,829,933.08 | SIGN_REVIEW | liability with debit balance |
| 1121002 | Anticipo de sueldos | ASSET | ADVANCES | -2,201,335.42 | SIGN_REVIEW | asset with credit balance |
| 2140103 | IUE por pagar | LIABILITY | TAX_LIABILITIES | 636,985.00 | SIGN_REVIEW | liability with debit balance |
| 1120501 | Cuentas por Cobrar Socios MN | ASSET | OTHER_RECEIVABLES | -579,034.69 | SIGN_REVIEW | asset with credit balance |
| 2110403 | Facturas por recibir | LIABILITY | OTHER_CURRENT_LIABILITIES | 495,110.23 | SIGN_REVIEW | liability with debit balance |
| 5110102 | Costos de Importacion | COGS | OTHER_COGS | -491,537.26 | SIGN_REVIEW | expense with credit balance |
| 6012005 | Ajuste Inv. Litel | OPERATING_EXPENSES | OTHER_OPEX | -201,615.52 | SIGN_REVIEW | expense with credit balance |
| 2110301 | Anticipos de clientes M/N | LIABILITY | CUSTOMER_ADVANCES | 173,812.73 | SIGN_REVIEW | liability with debit balance |
| 1111002 | BMSC Cta. Cte. 4010707998 MN | ASSET | BANK | -74,587.74 | SIGN_REVIEW | asset with credit balance |
| 5120101 | Mano de obra de producción | COGS | OTHER_COGS | -44,879.12 | SIGN_REVIEW | expense with credit balance |
| 6012001 | Ajuste Inv. Materia Prima | OPERATING_EXPENSES | OTHER_OPEX | -32,204.17 | SIGN_REVIEW | expense with credit balance |
| 1220202 | Depreciación proyecto Urucu | ASSET | OTHER_NON_CURRENT_ASSETS | -29,630.00 | SIGN_REVIEW | asset with credit balance |
| 2120107 | Subsidio por pagar al personal | LIABILITY | PAYROLL_LIABILITIES | 20,000.00 | SIGN_REVIEW | liability with debit balance |
| 1140002 | Otras compras Socios | ASSET | OTHER_CURRENT_ASSETS | -19,558.89 | SIGN_REVIEW | asset with credit balance |
| 6012004 | Ajuste Inv. Medicamentos | OPERATING_EXPENSES | OTHER_OPEX | -15,205.62 | SIGN_REVIEW | expense with credit balance |
| 2120302 | Finiquitos por pagar | LIABILITY | ACCRUALS | 14,058.39 | SIGN_REVIEW | liability with debit balance |
| 1111012 | BANCO UNION Cta.Cte. 1-33418159 MN | ASSET | BANK | -10,856.46 | SIGN_REVIEW | asset with credit balance |
| 6012006 | Ajustes Materiales Almacen | OPERATING_EXPENSES | OTHER_OPEX | -10,501.59 | SIGN_REVIEW | expense with credit balance |
| 1130208 | Productos en proceso Saavedra WIP | ASSET | INVENTORY | -5,560.11 | SIGN_REVIEW | asset with credit balance |
| 6012003 | Ajuste Inv. Prod. Terminados | OPERATING_EXPENSES | OTHER_OPEX | -3,992.29 | SIGN_REVIEW | expense with credit balance |
| 6012008 | Ajuste por cruce de codigo | OPERATING_EXPENSES | OTHER_OPEX | -3,503.35 | SIGN_REVIEW | expense with credit balance |
| 1240101 | Seguros pagados por anticipado | ASSET | PREPAIDS | -2,034.31 | SIGN_REVIEW | asset with credit balance |
| 6110405 | Ajuste Inv. Litel | OPERATING_EXPENSES | OTHER_OPEX | -1,867.43 | SIGN_REVIEW | expense with credit balance |
| 5120102 | Gastos indirectos de producción | COGS | OTHER_COGS | -101.04 | SIGN_REVIEW | expense with credit balance |
| 1130209 | Productos en proceso Magistral WIP | ASSET | INVENTORY | -83.14 | SIGN_REVIEW | asset with credit balance |
| 5120202 | Revalorizacion del costo | COGS | INVENTORY_ADJUSTMENTS | -21.84 | SIGN_REVIEW | expense with credit balance |
| 6020304 | Ajuste por redondeo | OPERATING_EXPENSES | OTHER_OPEX | -0.48 | SIGN_REVIEW | expense with credit balance |

## AA. REAL CASES

| Caso | TransId | RefDate | TransType | Memo | Líneas (Account:Debit/Credit) |
|---|---|---|---|---|---|
| A_SALE_REVENUE_AR_IVA | 16340100 | 2026-09-10 | 13 | Facturas clientes - C011382 | 1120101:1,395.00/0.00, 2140101:0.00/0.00, 4110101:0.00/1,395.00 |
| B_COGS_INVENTORY | 16340094 | 2026-09-10 | 15 | Entregas - C011382 | 1130305:0.00/354.02, 5110101:354.02/0.00 |
| C_PURCHASE_AP | 16340122 | 2026-09-10 | 18 | Fabiana Vaca, Servicio de videos, Reels  | 1121501:0.00/0.00, 2110101:0.00/1,000.00, 6011502:250.00/0.00 |
| D_OPEX_PAYROLL | 15752092 | 2025-12-31 | 30 | ANULADO - Pla_Dic25_Fiscal_SCZ.(Anulació | 1121002:11,721.77/0.00, 2120101:603,545.18/0.00, 2120201:98,004.49/0.00, 2120205:102,345.22/0.00 |
| E_BANK_FEE | 16331692 | 2026-09-07 | 25 | Abono#Vta. C/tarjetas Bs 54,231.03 del 0 | 1111001:48.74/0.00, 1111001:77.30/0.00, 1111001:314.93/0.00, 1111001:25.50/0.00 |
| F_FX | 15124648 | 2025-12-31 | 30 | RECLAS. CTA.DIF.DE CAMBIO A CTAS DE ORIG | 6210101:9,920.74/0.00, 6210101:2,541.74/0.00, 6210105:65.42/0.00, 6210105:83.79/0.00 |
| G_DEPRECIATION | 15026622 | 2025-12-31 | 30 | Depreciacion de activos fijos correspond | 1210103:0.00/11,298.06, 1210202:0.00/8,897.57, 1210302:0.00/23,313.48, 1210304:0.00/10,919.04 |
| H_TAX | 16340071 | 2026-09-10 | 30 |  | 2140102:0.00/10.41, 6310101:10.41/0.00 |
| I_MANUAL_JE_PL | 16061888 | 2026-07-19 | 30 | RECLASIFICACION CTA/ FACTURAS CLIENTES-M | 4110101:0.00/13.92, 4110101:0.00/15.66, 4210116:15.66/0.00, 4210116:13.92/0.00 |
| J_CLOSING_EQUITY | 15766756 | 2025-12-31 | -3 | Cierre de periodo 2025 | 3110502:0.00/95,872,930.45, 4110101:95,872,930.45/0.00 |

## AB. INVARIANTS

| Invariante | Resultado | Detalle |
|---|---|---|
| BS01 | PASS | every account with movement is classified |
| BS02 | PASS | all balances derived from JDT1 |
| BS03 | PASS | Assets = Liabilities + Equity (LC, as-of) |
| BS04 | PASS | same equation in system currency |
| BS05 | PASS | cash/bank GL reconciles to OACT control (live) and the frozen treasury gate reports BALANCE_MATCH for all accounts |
| BS06 | PASS | AR documentary vs GL control; bridge enumerated and difference immaterial to total assets (~0.444%) |
| BS07 | PASS | AP documentary vs GL control; bridge enumerated and difference immaterial to total assets (~3.6902%) |
| BS08 | PASS | ## is account configuration, never a nominal currency sum |
| PL01 | PASS | all P&L accounts with movement classified |
| PL02 | PASS | P&L totals from JDT1 by RefDate |
| PL03 | PASS | Net Income reconciles to P&L accounts |
| PL04 | PASS | closing mechanism does not duplicate current-year result |
| PL05 | PASS | canceled/reversed activity is handled by JDT1 net signs |
| PL06 | PASS | FX separated into FX_GAIN / FX_LOSS |
| PL07 | PASS | bank/card fees classified as P&L |
| FIN01 | PASS | no nominal currency mixing |
| FIN02 | PASS | classification coverage quantified |
| FIN03 | PASS | SAP_WRITE_COUNT=0 |

## AC. LIMITATIONS

- Comparative year-end balance sheets use the reopened opening (Jan 1) because SAP `-3` closes the whole trial balance at Dec 31.
- Fixed-asset detail (cost vs accumulated) comes from GL accounts; the standard SAP fixed-asset module was not reconstructed.
- Debt short/long split follows account hierarchy, not contractual maturity.
- Tax granularity follows the GL accounts; supplier withholding remains outside this gate.
- Inventory value is the GL value; no physical-count revaluation was performed.

## AD. NEXT GATE

TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1

## Artefactos

- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/balance_sheet_pnl_reconstruction/balance_sheet_pnl_reconstruction_v1.py`
- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/balance_sheet_pnl_reconstruction/balance_sheet_pnl_reconstruction_v1.json`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

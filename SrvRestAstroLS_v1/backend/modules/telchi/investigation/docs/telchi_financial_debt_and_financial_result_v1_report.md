# TELCHI — FINANCIAL DEBT / INTEREST / FINANCIAL RESULT TRACEABILITY V1

**Gate:** `TELCHI_FINANCIAL_DEBT_AND_FINANCIAL_RESULT_TRACEABILITY_V1_PASS`\
**Modo:** INVESTIGATION / READ ONLY / `SAP_WRITE_COUNT=0`\
**AS_OF:** 2026-09-10\
**Evidencia:** 2026-09-10T13:36:12.863625+00:00

## A. VEREDICTO

De los **Bs 4,827,924.39** de `FINANCING`, **Bs 4,813,161.03** son **capital** de préstamos bancarios vigentes (BANCO FIE y BANCO MSC, con una comisión ACH de BANCO GANADERO), **Bs 14,503.36** son intereses devengados y **Bs 260.00** comisiones. SAP no conserva el calendario de cuotas: cada préstamo es un OPCH con el capital remanente y fecha final o marcador. El resultado financiero **−Bs 1,414,305.12** se explica en **1,138,220.44** de comisiones bancarias (77%), de las cuales Bs 1,090,697.04 son giros al exterior, y solo **Bs 303,803.60** de intereses (21%). El debt service económico a 90 días es **Bs 1,405,816.13** (capital Bs 1,342,504.89 + interés Bs 63,311.24), muy por debajo de la concentración documental del forecast V1.

**Decisión:** `PASS` — Universo FINANCING reproducido, capital/interés/comisiones separados, resultado financiero reconstruido y frontera SAP delimitada (sin calendario contractual almacenado).

## B. FINANCING UNIVERSE — LOS Bs 4.827.924,39

El bloque `FINANCING` del forecast V1 queda reproducido por **Bs 4,827,924.39** (21 documentos OPCH abiertos a proveedores cuyo nombre contiene BANCO/BANK).

| Naturaleza | Monto BS |
|---|---|
| ACCRUED_INTEREST | 14,503.36 |
| BANK_FEE | 260.00 |
| PRINCIPAL | 4,813,161.03 |

Bridge del universo:

| Componente | Monto BS |
|---|---|
| PRINCIPAL_OUTSTANDING | 4,813,161.03 |
| ACCRUED_INTEREST | 14,503.36 |
| BANK_FEES | 260.00 |
| OTHER / UNRESOLVED | 0.00 |
| **TOTAL** | **4,827,924.39** |

## C. FINANCIAL ENTITIES

| Entidad | CardCode | Docs | Principal | Interés devengado | Comisiones | Total | Evidencia |
|---|---|---|---|---|---|---|---|
| BANCO FIE S.A. | PL000212 | 13 | 3,725,671.33 | 11,631.63 | 0.00 | 3,737,302.96 | STRONG |
| BANCO MERCANTIL SANTA CRUZ S.A. | PL000288 | 7 | 1,087,489.70 | 2,871.73 | 250.00 | 1,090,611.43 | STRONG |
| BANCO GANADERO SA | PL000640 | 1 | 0.00 | 0.00 | 10.00 | 10.00 | STRONG |

Concentración de deuda: top_1 77.4% · top_3 100.0%

## D. DEBT TYPE

| Documento | Entidad | Tipo | Naturaleza | Cuenta control | Comentario |
|---|---|---|---|---|---|
| 3639 | BANCO FIE S.A. | BANK_LOAN | PRINCIPAL | 2210101 | S.I -Provision d/Prestamo N.-7018-11907 Bco.Banco Fie K.10.290.000 M/N Int. 5% a pagar en  |
| 30250 | BANCO FIE S.A. | BANK_LOAN | PRINCIPAL | 2210101 | Provision d/Prestamo N.-10010818132 Bco.Banco FIE K. 487.000.- M/N Int. 5.99% pagos en cuo |
| 30252 | BANCO FIE S.A. | CREDIT_LINE | PRINCIPAL | 2210101 | Provision d/Prestamo Bajo LC. N.-10010909156 Bco.Banco FIE K. 1.000.000.- M/N Int. 6% pago |
| 35149 | BANCO FIE S.A. | CREDIT_LINE | PRINCIPAL | 2210101 | Provision d/Prestamo Bajo LC. N.-10011872517 Bco.Banco FIE K. 1.000.000.- M/N Int. 6% pago |
| 37812 | BANCO FIE S.A. | CREDIT_LINE | PRINCIPAL | 2210101 | Provision d/Prestamo Bajo LC. N.-10012449919 Bco.Banco FIE K. 335.000.- M/N Int. 10% pagos |
| 48492 | BANCO FIE S.A. | CREDIT_LINE | PRINCIPAL | 2210101 | Provision d/Prestamo Bajo LC. N.-10014929262 Bco.Banco FIE K. 300.000.- M/N Int. 10% pagos |
| 29956 | BANCO MERCANTIL SANTA CRUZ S.A. | BANK_LOAN | PRINCIPAL | 2210101 | Provision d/Prestamo N.-6014236751 Bco.Banco MSC K. 209.200 M/N Int. 5.99% pagos en cuotas |
| 39326 | BANCO MERCANTIL SANTA CRUZ S.A. | BANK_LOAN | PRINCIPAL | 2210101 | Provision d/Prestamo N.-6014435342 Bco.Banco MSC K. 999.000 M/N Int. 10% pago del Capital  |
| 42098 | BANCO MERCANTIL SANTA CRUZ S.A. | BANK_LOAN | PRINCIPAL | 2110101 | Provision d/Prestamo N.-6014485521 Bco.Banco MSC K. 3,430,000.00 M/N Int. 10% pago del Cap |

## E. PRINCIPAL OUTSTANDING

| DocEntry | Préstamo | Entidad | Capital pendiente Bs | Cuota capital/mes | Cuotas restantes | Base |
|---|---|---|---|---|---|---|
| 3639 | 7018-11907 | BANCO FIE S.A. | 2,058,765.91 | 70,992.22 | 29 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 30250 | 10010818132 | BANCO FIE S.A. | 308,433.26 | 8,116.67 | 38 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 30252 | 10010909156 | BANCO FIE S.A. | 388,888.92 | 27,777.78 | 14 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 35149 | 10011872517 | BANCO FIE S.A. | 555,555.52 | 27,777.78 | 20 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 37812 | 10012449919 | BANCO FIE S.A. | 214,027.72 | 9,305.56 | 23 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 48492 | 10014929262 | BANCO FIE S.A. | 200,000.00 | 50,000.00 | 4 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 29956 | 6014236751 | BANCO MERCANTIL SANTA CRUZ S.A. | 115,059.91 | 3,486.67 | 33 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 39326 | 6014435342 | BANCO MERCANTIL SANTA CRUZ S.A. | 83,250.00 | 83,250.00 | 1 | LAST_OBSERVED_MONTHLY_CAPITAL |
| 42098 | 6014485521 | BANCO MERCANTIL SANTA CRUZ S.A. | 889,179.79 | 222,294.95 | 4 | FINAL_MATURITY_EVEN_SPLIT |

Total capital pendiente agendado: **Bs 4,813,161.03**.

## F. CURRENCY

Toda la deuda bancaria abierta está denominada en **BS**; no se suma deuda USD nominalmente a Bs. Los tres proveedores financieros abiertos (BANCO FIE, BANCO MSC, BANCO GANADERO) tienen DocCur='BS'.

## G. MATURITY / INSTALLMENTS

- `FINANCIAL_DEBT_SCHEDULE = HEURISTIC`
- `DEBT_MATURITY_CLASSIFICATION = DEBT_MATURITY_CLASSIFICATION_DEGRADED`
- INV6 no conserva cuotas para los OPCH de capital abiertos (0 filas para los 9 préstamos).
- Cada préstamo es UN OPCH con el capital remanente; los pagos mensuales aplican capital a 2210101 y cancelan la provisión de interés contra 2110101. La cuota económica se reconstruye desde la historia de pagos (STRONG) y se proyecta como HEURISTIC.

| DocEntry | Préstamo | Fecha vencimiento OPCH | Interpretación | Tipo de fecha |
|---|---|---|---|---|
| 3639 | 7018-11907 | 2022-03-31 | PLACEHOLDER_OR_MIGRATION_DATE | INFERRED_PATTERN |
| 30250 | 10010818132 | 2029-10-10 | FINAL_MATURITY_DOCUMENTED | DOCUMENT_DUE_DATE |
| 30252 | 10010909156 | 2027-10-11 | FINAL_MATURITY_DOCUMENTED | DOCUMENT_DUE_DATE |
| 35149 | 10011872517 | 2025-12-31 | PLACEHOLDER_OR_MIGRATION_DATE | INFERRED_PATTERN |
| 37812 | 10012449919 | 2025-12-31 | PLACEHOLDER_OR_MIGRATION_DATE | INFERRED_PATTERN |
| 48492 | 10014929262 | 2026-12-10 | FINAL_MATURITY_DOCUMENTED | DOCUMENT_DUE_DATE |
| 29956 | 6014236751 | 2024-12-31 | PLACEHOLDER_OR_MIGRATION_DATE | INFERRED_PATTERN |
| 39326 | 6014435342 | 2026-09-20 | FINAL_MATURITY_DOCUMENTED | DOCUMENT_DUE_DATE |
| 42098 | 6014485521 | 2026-12-20 | FINAL_MATURITY_DOCUMENTED | DOCUMENT_DUE_DATE |

## H. OVERDUE DOCUMENTAL VS ECONÓMICO

Documentos con vencimiento documental >90 días atrasado: **4** por **Bs 2,943,409.06**. No son cuotas vencidas: son préstamos vigentes cuyo OPCH usa la madurez final o una fecha marcador. `SAP_DOCUMENT_OVERDUE` ≠ `ECONOMIC_INSTALLMENT_OVERDUE`.

| DocEntry | Entidad | DueDate | Días atraso documental | Tratamiento V1 | Lectura económica |
|---|---|---|---|---|---|
| 3639 | BANCO FIE S.A. | 2022-03-31 | 1624 | offset +30d | cuota mensual vigente |
| 35149 | BANCO FIE S.A. | 2025-12-31 | 253 | offset +30d | cuota mensual vigente |
| 37812 | BANCO FIE S.A. | 2025-12-31 | 253 | offset +30d | cuota mensual vigente |
| 29956 | BANCO MERCANTIL SANTA CRUZ S.A. | 2024-12-31 | 618 | offset +30d | cuota mensual vigente |

## I. DEBT PAYMENTS

Pagos a bancos en 2026 YTD (OVPM activos): **210** documentos; principal de préstamos en 2210101 Bs 2,601,933.45; movimiento en cuenta control AP (interés + capital de préstamo en 2110101 + reversas) Bs 5,953,581.89; interés devengado P&L Bs 303,803.60.

Cadena: `PRINCIPAL OPCH → OVPM → 2210101/2110101 → banco`. El pago de interés no debita 6020101 en caja: cancela la provisión (2110101) creada como OPCH de interés. El movimiento de 2110101 por pagos a bancos mezcla intereses, capital del préstamo registrado en 2110101 y reversas; no se declara como interés sin separación contractual.

## J. PRINCIPAL PAYMENTS

| Período | Pagos | Capital Bs (2210101) | Movimiento AP control Bs |
|---|---|---|---|
| 2026-01 | 28 | 348,420.01 | 3,019,093.19 |
| 2026-02 | 22 | 581,753.36 | 563,187.09 |
| 2026-03 | 24 | 315,086.68 | 675,584.05 |
| 2026-04 | 43 | 315,086.68 | 528,257.32 |
| 2026-05 | 28 | 240,086.68 | 260,817.15 |
| 2026-06 | 15 | 240,086.68 | 260,766.58 |
| 2026-07 | 32 | 280,706.68 | 365,195.06 |
| 2026-08 | 18 | 280,706.68 | 280,681.45 |

## K. INTEREST

- Interés devengado 2026 YTD (`6020101`): **Bs 317,486.50**
- Ajuste `6020303 Intereses bancarios`: Bs -13,682.90
- Interés P&L neto (subgrupo `INTEREST_EXPENSE`): **Bs -303,803.60**
- Interés cobrado/pagado en caja 2026 YTD: no separable sin calendario contractual; el movimiento de 2110101 por pagos a bancos es Bs 5,953,581.89 e incluye capital del préstamo registrado en 2110101.
- `ACCOUNTING_FINANCIAL_COST_RATE = 4.2` (descriptivo, no tasa contractual)

## L. FEES

| Cuenta | Concepto | 2026 YTD Bs |
|---|---|---|
| 6020102 | Formularios y tramites bancarios | 3,850.40 |
| 6020103 | Comisión tarjetas debito/credito | 38,819.70 |
| 6020104 | Comision Bancaria | 4,957.89 |
| 6020105 | Comision Bancaria por giros al exterior | 1,090,697.04 |

El resultado financiero está dominado por comisiones, no por intereses: `6020105` (giros al exterior) explica Bs 1,090,697.04. Bs 68.494,43 de comisiones de depósitos ODPS de tarjetas NO forman parte del resultado financiero; se contabilizan en la cuenta operativa 62101xx. Se valida contra el gate de depósitos.

## M. FX

- `FX_LOSS`: Bs -14.37 · `FX_GAIN`: Bs 1,452.79 · neto Bs 1,438.42
- La deuda bancaria abierta está en Bs, por lo que no genera revaluación de deuda USD en el horizonte.

## N. FINANCIAL RESULT RECONCILIATION — LOS −Bs 1.414.305,12

- Valor congelado gate BSPNL V1: **Bs -1,414,305.12**
- Valor vivo (HANA al corte): **Bs -1,414,409.71**
- Bridge post-cierre detectado: **Bs -104.59** (Asiento(s) creados el día del corte con RefDate anterior; el gate BSPNL se generó antes.)
- Reconciliación: -1,414,409.71 − (-104.59) = -1,414,305.12

| Subgrupo | Monto Bs (congelado) |
|---|---|
| BANK_CHARGES | -1,138,220.44 |
| FX_GAIN | 1,452.79 |
| FX_LOSS | -14.37 |
| INTEREST_EXPENSE | -303,803.60 |
| INTEREST_INCOME | 26,280.50 |
| OTHER_FINANCIAL | 0.00 |
| **TOTAL** | **-1,414,305.12** |

## O. FINANCIAL RESULT PARETO

| Cuenta | Concepto | 2026 YTD Bs | Share % del resultado financiero |
|---|---|---|---|
| 6020105 | Comision Bancaria por giros al exterior | 1,090,697.04 | 77.11 |
| 6020101 | Intereses bancarios por prestamos | 317,486.50 | 22.45 |
| 6020103 | Comisión tarjetas debito/credito | 38,819.70 | 2.74 |
| 4210111 | Intereses bancarios ganados | -26,280.50 | -1.86 |
| 6020303 | Intereses bancarios | -13,682.90 | -0.97 |
| 6020104 | Comision Bancaria | 4,957.89 | 0.35 |
| 6020102 | Formularios y tramites bancarios | 3,850.40 | 0.27 |
| 4210105 | Diferencia de cambio automático propio del sistema | -1,452.79 | -0.1 |
| 6020301 | Diferencia en cambio | 14.37 | 0.0 |

El 77% del resultado financiero negativo son comisiones por giros al exterior; el interés bancario es solo ~21%. Las comisiones de tarjetas y formularios son marginales.

## P. DEBT ROLL-FORWARD

| Cuenta | Saldo apertura 2026 | Cargos (nuevo financiamiento) | Abonos (pagos/ajustes) | Saldo cierre |
|---|---|---|---|---|
| 2210101 | -6,225,914.69 | 641,963.35 | 2,943,896.80 | -3,923,981.24 |

Préstamo en cuenta comercial (DocEntry 42098, BANCO MERCANTIL SANTA CRUZ S.A.): capital original Bs 3,430,000.00, pagado Bs 2,540,820.21, saldo Bs 889,179.79. No es una cuenta de pasivo financiero separada, pero económicamente es deuda bancaria y forma parte del universo FINANCING.

Cuenta 2210101 Préstamos bancarios, ejercicio 2026: cierre = apertura − cargos (créditos: nuevo financiamiento Bs 300,000.00 y reversas de pago) + abonos (débitos: pagos de capital). El préstamo MSC 6014485521 (DocEntry 42098) está registrado en 2110101 Cuentas por pagar MN y se reporta por separado por su DocTotal/PaidToDate/Open.

## Q. DEBT SERVICE 30/60/90D

| Horizonte | Capital Bs | Interés Bs | Debt service Bs |
|---|---|---|---|
| 7d | 193,970.01 | 20,013.34 | 213,983.35 |
| 30d | 598,201.64 | 30,770.03 | 628,971.67 |
| 60d | 922,753.26 | 42,685.41 | 965,438.67 |
| 90d | 1,342,504.89 | 63,311.24 | 1,405,816.13 |
| 365d | 2,987,109.96 | 238,279.14 | 3,225,389.10 |

Cronograma **HEURÍSTICO**: capital proyectado con la última cuota mensual observada; interés con el último devengado. No es un calendario contractual. El conteo de cuotas usa el capital remanente dividido por la última cuota mensual observada; el residuo de redondeo se aplica a la última cuota. La fecha de pago usa el día del último pago observado.

## Q.1 CALENDARIO DETALLADO (primeras 12 cuotas por préstamo)

**BANCO FIE S.A. · préstamo 7018-11907 (DocEntry 3639)** — capital Bs 2,058,765.91, cuota Bs 70,992.22/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-17 | 70,992.22 | 9,150.11 | 1,987,773.69 |
| 2 | 2026-10-17 | 70,992.22 | 9,150.11 | 1,916,781.47 |
| 3 | 2026-11-17 | 70,992.22 | 9,150.11 | 1,845,789.25 |
| 4 | 2026-12-17 | 70,992.22 | 9,150.11 | 1,774,797.03 |
| 5 | 2027-01-17 | 70,992.22 | 9,150.11 | 1,703,804.81 |
| 6 | 2027-02-17 | 70,992.22 | 9,150.11 | 1,632,812.59 |
| 7 | 2027-03-17 | 70,992.22 | 9,150.11 | 1,561,820.37 |
| 8 | 2027-04-17 | 70,992.22 | 9,150.11 | 1,490,828.15 |
| 9 | 2027-05-17 | 70,992.22 | 9,150.11 | 1,419,835.93 |
| 10 | 2027-06-17 | 70,992.22 | 9,150.11 | 1,348,843.71 |
| 11 | 2027-07-17 | 70,992.22 | 9,150.11 | 1,277,851.49 |
| 12 | 2027-08-17 | 70,992.22 | 9,150.11 | 1,206,859.27 |

**BANCO FIE S.A. · préstamo 10010818132 (DocEntry 30250)** — capital Bs 308,433.26, cuota Bs 8,116.67/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-10 | 8,116.67 | 1,620.63 | 300,316.59 |
| 2 | 2026-10-10 | 8,116.67 | 1,620.63 | 292,199.92 |
| 3 | 2026-11-10 | 8,116.67 | 1,620.63 | 284,083.25 |
| 4 | 2026-12-10 | 8,116.67 | 1,620.63 | 275,966.58 |
| 5 | 2027-01-10 | 8,116.67 | 1,620.63 | 267,849.91 |
| 6 | 2027-02-10 | 8,116.67 | 1,620.63 | 259,733.24 |
| 7 | 2027-03-10 | 8,116.67 | 1,620.63 | 251,616.57 |
| 8 | 2027-04-10 | 8,116.67 | 1,620.63 | 243,499.90 |
| 9 | 2027-05-10 | 8,116.67 | 1,620.63 | 235,383.23 |
| 10 | 2027-06-10 | 8,116.67 | 1,620.63 | 227,266.56 |
| 11 | 2027-07-10 | 8,116.67 | 1,620.63 | 219,149.89 |
| 12 | 2027-08-10 | 8,116.67 | 1,620.63 | 211,033.22 |

**BANCO FIE S.A. · préstamo 10010909156 (DocEntry 30252)** — capital Bs 388,888.92, cuota Bs 27,777.78/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-11 | 27,777.78 | 2,152.78 | 361,111.14 |
| 2 | 2026-10-11 | 27,777.78 | 2,152.78 | 333,333.36 |
| 3 | 2026-11-11 | 27,777.78 | 2,152.78 | 305,555.58 |
| 4 | 2026-12-11 | 27,777.78 | 2,152.78 | 277,777.80 |
| 5 | 2027-01-11 | 27,777.78 | 2,152.78 | 250,000.02 |
| 6 | 2027-02-11 | 27,777.78 | 2,152.78 | 222,222.24 |
| 7 | 2027-03-11 | 27,777.78 | 2,152.78 | 194,444.46 |
| 8 | 2027-04-11 | 27,777.78 | 2,152.78 | 166,666.68 |
| 9 | 2027-05-11 | 27,777.78 | 2,152.78 | 138,888.90 |
| 10 | 2027-06-11 | 27,777.78 | 2,152.78 | 111,111.12 |
| 11 | 2027-07-11 | 27,777.78 | 2,152.78 | 83,333.34 |
| 12 | 2027-08-11 | 27,777.78 | 2,152.78 | 55,555.56 |

**BANCO FIE S.A. · préstamo 10011872517 (DocEntry 35149)** — capital Bs 555,555.52, cuota Bs 27,777.78/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-10 | 27,777.78 | 3,013.89 | 527,777.74 |
| 2 | 2026-10-10 | 27,777.78 | 3,013.89 | 499,999.96 |
| 3 | 2026-11-10 | 27,777.78 | 3,013.89 | 472,222.18 |
| 4 | 2026-12-10 | 27,777.78 | 3,013.89 | 444,444.40 |
| 5 | 2027-01-10 | 27,777.78 | 3,013.89 | 416,666.62 |
| 6 | 2027-02-10 | 27,777.78 | 3,013.89 | 388,888.84 |
| 7 | 2027-03-10 | 27,777.78 | 3,013.89 | 361,111.06 |
| 8 | 2027-04-10 | 27,777.78 | 3,013.89 | 333,333.28 |
| 9 | 2027-05-10 | 27,777.78 | 3,013.89 | 305,555.50 |
| 10 | 2027-06-10 | 27,777.78 | 3,013.89 | 277,777.72 |
| 11 | 2027-07-10 | 27,777.78 | 3,013.89 | 249,999.94 |
| 12 | 2027-08-10 | 27,777.78 | 3,013.89 | 222,222.16 |

**BANCO FIE S.A. · préstamo 10012449919 (DocEntry 37812)** — capital Bs 214,027.72, cuota Bs 9,305.56/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-10 | 9,305.56 | 1,923.15 | 204,722.16 |
| 2 | 2026-10-10 | 9,305.56 | 1,923.15 | 195,416.60 |
| 3 | 2026-11-10 | 9,305.56 | 1,923.15 | 186,111.04 |
| 4 | 2026-12-10 | 9,305.56 | 1,923.15 | 176,805.48 |
| 5 | 2027-01-10 | 9,305.56 | 1,923.15 | 167,499.92 |
| 6 | 2027-02-10 | 9,305.56 | 1,923.15 | 158,194.36 |
| 7 | 2027-03-10 | 9,305.56 | 1,923.15 | 148,888.80 |
| 8 | 2027-04-10 | 9,305.56 | 1,923.15 | 139,583.24 |
| 9 | 2027-05-10 | 9,305.56 | 1,923.15 | 130,277.68 |
| 10 | 2027-06-10 | 9,305.56 | 1,923.15 | 120,972.12 |
| 11 | 2027-07-10 | 9,305.56 | 1,923.15 | 111,666.56 |
| 12 | 2027-08-10 | 9,305.56 | 1,923.15 | 102,361.00 |

**BANCO FIE S.A. · préstamo 10014929262 (DocEntry 48492)** — capital Bs 200,000.00, cuota Bs 50,000.00/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-10 | 50,000.00 | 2,152.78 | 150,000.00 |
| 2 | 2026-10-10 | 50,000.00 | 2,152.78 | 100,000.00 |
| 3 | 2026-11-10 | 50,000.00 | 2,152.78 | 50,000.00 |
| 4 | 2026-12-10 | 50,000.00 | 2,152.78 | 0.00 |

**BANCO MERCANTIL SANTA CRUZ S.A. · préstamo 6014236751 (DocEntry 29956)** — capital Bs 115,059.91, cuota Bs 3,486.67/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-20 | 3,486.67 | 612.49 | 111,573.24 |
| 2 | 2026-10-20 | 3,486.67 | 612.49 | 108,086.57 |
| 3 | 2026-11-20 | 3,486.67 | 612.49 | 104,599.90 |
| 4 | 2026-12-20 | 3,486.67 | 612.49 | 101,113.23 |
| 5 | 2027-01-20 | 3,486.67 | 612.49 | 97,626.56 |
| 6 | 2027-02-20 | 3,486.67 | 612.49 | 94,139.89 |
| 7 | 2027-03-20 | 3,486.67 | 612.49 | 90,653.22 |
| 8 | 2027-04-20 | 3,486.67 | 612.49 | 87,166.55 |
| 9 | 2027-05-20 | 3,486.67 | 612.49 | 83,679.88 |
| 10 | 2027-06-20 | 3,486.67 | 612.49 | 80,193.21 |
| 11 | 2027-07-20 | 3,486.67 | 612.49 | 76,706.54 |
| 12 | 2027-08-20 | 3,486.67 | 612.49 | 73,219.87 |

**BANCO MERCANTIL SANTA CRUZ S.A. · préstamo 6014435342 (DocEntry 39326)** — capital Bs 83,250.00, cuota Bs 83,250.00/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-20 | 83,250.00 | 1,433.75 | 0.00 |

**BANCO MERCANTIL SANTA CRUZ S.A. · préstamo 6014485521 (DocEntry 42098)** — capital Bs 889,179.79, cuota Bs 222,294.95/mes.

| # | Vencimiento | Capital Bs | Interés Bs | Saldo después Bs |
|---|---|---|---|---|
| 1 | 2026-09-20 | 222,294.95 | 0.00 | 666,884.84 |
| 2 | 2026-10-20 | 222,294.95 | 0.00 | 444,589.89 |
| 3 | 2026-11-20 | 222,294.95 | 0.00 | 222,294.94 |
| 4 | 2026-12-20 | 222,294.94 | 0.00 | 0.00 |

## R. FORECAST V1 IMPACT

Forecast V1 clasificó como `FINANCING` **Bs 4,827,924.39** y colocó los documentos con vencimiento documental >90 días atrasado a ~30 días. Esa concentración artificial asciende a **Bs 2,943,409.06**.

| Horizonte | Forecast V1 (tratamiento documental) | Cronograma económico (heurístico) | Diferencia |
|---|---|---|---|
| 30d | 3,040,279.47 | 628,971.67 | -2,411,307.80 |
| 90d | 3,041,422.42 | 1,405,816.13 | -1,635,606.29 |

El forecast V1 no sobreestima el monto total de deuda, pero sí concentra el capital de préstamos con fecha documental vencida dentro de los primeros 30 días. El cronograma económico difiere en capital e interés; la comisión de giros al exterior es gasto recurrente ya devengado, no deuda.

## S. REVISED LIQUIDITY VIEW

Forecast V1 BASE 90d: **Bs -3,051,694.76**; excluyendo FINANCING: **Bs 113,925.98**. El forecast trató como pagable **Bs 3,041,422.42** de deuda financiera dentro de 90 días, concentrando **Bs 2,943,409.06** de capital con fecha documental vencida en ~30 días. Con el cronograma económico heurístico, el debt service financiero a 90 días sería **Bs 1,405,816.13**, es decir **Bs 1,635,606.29** menos de presión de caja en el horizonte. Esto sugiere que el déficit documental está dominado por la falta del calendario contractual, no por un vencimiento real concentrado. No se reemplaza el forecast V1.

Este gate **no reemplaza** el forecast V1, que permanece `PASS`: documentó correctamente el supuesto. Genera evidencia para una eventual `TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_1`.

## T. RATIOS

| Ratio | Valor |
|---|---|
| total_liabilities_to_equity | 0.3327 |
| financial_debt_to_equity | 0.0747 |
| financial_result_to_operating_result_pct | -12.3 |
| interest_expense_to_operating_result_pct | 2.64 |
| financial_expense_to_revenue_pct | 1.95 |
| financial_debt_to_annualized_operating_result | 0.42 |

## U. REAL CASES

| Caso | Entidad | Documento | Monto | Moneda | Naturaleza | Evidencia |
|---|---|---|---|---|---|---|
| A_PRINCIPAL_DOCUMENT | BANCO FIE S.A. | 3639 | 2,058,765.91 | BS | PRINCIPAL | OPCH a banco, contrapartida 2210101 Préstamos bancarios. |
| B_PRINCIPAL_PAYMENT | BANCO MERCANTIL SANTA CRUZ S.A. | 16250731 | 83,250.00 | BS | PRINCIPAL_PAYMENT | OVPM/TT46 debita 2210101 (capital). |
| C_INTEREST_PAYMENT | BANCO MERCANTIL SANTA CRUZ S.A. | 16286120 | 40.00 | BS | INTEREST_PAYMENT | OVPM/TT46 debita 2110101 cancelando la provisión de interés. |
| D_BANK_FEE | BANCO MERCANTIL SANTA CRUZ S.A. | 50929 | 250.00 | BS | BANK_FEE | Comisión ACH/mantenimiento; no es deuda. |
| E_FX_DEBT | TELCHI |  | 1,438.42 | BS | FX | Diferencia de cambio; deuda bancaria abierta en BS. |
| F_ENTITY_MULTI_DOC | BANCO FIE S.A. | 13 | 3,737,302.96 | BS | MULTIPLE_DOCUMENTS | Entidad con múltiples OPCH (capital + interés + comisión). |
| G_OVERDUE_NOT_ECONOMIC | BANCO FIE S.A. | 3639 | 2,058,765.91 | BS | PLACEHOLDER_DUE_DATE | DueDate 2022-03-31 pero préstamo 144 meses vigente; no es cuota vencida. |
| H_NEW_FINANCING | BANCO FIE S.A. | 48492 | 300,000.00 | BS | NEW_BORROWING | OPCH 48492 debita cuenta banco y acredita 2210101 (entrada de fondos). |

## V. INVARIANTS

| Invariante | Resultado | Valor |
|---|---|---|
| FD01_financing_reproduced | PASS | {"total": 4827924.39, "target": 4827924.39} |
| FD02_debt_traceable | PASS | 21 |
| FD03_principal_interest_separated | PASS | {"principal": 4813161.03, "interest": 14503.36, "fees": 260.0} |
| FD04_principal_not_expense | PASS | {"principal": 4813161.03, "interest_expense": -303803.6} |
| FD05_financial_result_reconciles | PASS | {"sum": -1414305.12, "frozen_target": -1414305.12, "bridge": -104.59} |
| FD06_fees_identified | PASS | 260.0 |
| FD07_fx_separated | PASS | {"FX_LOSS": -14.37, "FX_GAIN": 1452.79} |
| FD08_payments_trace_to_gl | PASS | {"scheduled_capital": 4813161.03, "principal": 4813161.03} |
| FD09_no_invented_installments | PASS | ["FINAL_MATURITY_EVEN_SPLIT", "LAST_OBSERVED_MONTHLY_CAPITAL"] |
| FD10_overdue_documental_vs_economic | PASS | "Placeholder due dates are flagged, not counted as economic overdue." |
| FD11_currencies_not_mixed | PASS | "FINANCING open AP is 100% BS." |
| FD12_forecast_impact_reproducible | PASS | {"30d": {"capital": 598201.64, "interest": 30770.03, "debt_service": 628971.67}, "90d": {"capital": 1342504.89, "interes |
| FD13_sap_write_count | PASS | 0 |
| FD14_loan_liability_reconciles | PASS | {"account_2210101_closing": -3923981.24, "open_principal_on_2210101": 3923981.24} |
| FD15_real_cases | PASS | "Cases A-H present." |

## W. LIMITATIONS

- SAP no conserva calendario contractual de cuotas (INV6 vacío para los OPCH de capital abiertos). El cronograma es HEURISTIC.
- El interés proyectado usa el último devengado mensual observado; puede variar con la tasa y el saldo.
- El capital proyectado asume que la última cuota mensual observada se mantiene; el residuo se aplica a la última cuota.
- Los pagos se atribuyen al préstamo mediante el número de operación del memo; errores de tipeo pueden dejar series parciales.
- La deuda está íntegramente en Bs; no hay revaluación de deuda USD en el horizonte.
- La frontera de SAP se cierra en pagos y provisiones; contratos, tasas y garantías son externos.
- No se reescribió el gate de forecast V1; este gate solo agrega evidencia.
- El resultado financiero incluye comisiones por giros al exterior (Bs 1,090,697.04) que podrían discutirse como costo de importación; se reporta la clasificación contable de Telchi, no una reclasificación.

## X. EXTERNAL DOCUMENTATION REQUIRED

SAP conserva el capital y los pagos, pero **no** el calendario contractual de cuotas. Para corregir el forecast sin heurística se requiere, por entidad/préstamo:

- Entidad financiera y número de préstamo/operación.
- Capital original desembolsado y moneda.
- Fecha de desembolso y tasa de interés contractual.
- Calendario de cuotas (número, fecha, capital, interés, seguro si aplica).
- Saldo de capital remanente a la fecha de corte.
- Próximo vencimiento y fecha de madurez final.
- Comisiones y cargos recurrentes asociados a cada préstamo.
- Garantías/seguros, si son relevantes para la clasificación.

## Y. NEXT GATE

Si Telchi entrega el calendario contractual: `TELCHI_FINANCIAL_FORECAST_LIQUIDITY_SCENARIOS_V1_1` para corregir la deuda financiera dentro del forecast. Si no: mantener el cronograma HEURISTIC y solicitar los contratos/estados de deuda antes de modificar el forecast. Luego: `TELCHI_FINANCIAL_CONTROL_POLICIES_AND_ALERTS_V1`.

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_debt_and_financial_result/financial_debt_and_financial_result_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/financial_debt_and_financial_result/financial_debt_and_financial_result_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

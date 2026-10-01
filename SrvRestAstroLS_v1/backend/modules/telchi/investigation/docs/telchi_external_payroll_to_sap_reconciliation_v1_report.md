# TELCHI — EXTERNAL PAYROLL → SAP / GL / LIABILITY / BANK RECONCILIATION V1

**Gate:** `TELCHI_EXTERNAL_PAYROLL_TO_SAP_RECONCILIATION_V1_PASS`\
**Modo:** `INVESTIGATION` / `READ ONLY` / `SAP_WRITE_COUNT=0`\
**Corte HANA:** `2026-09-10`

## A. VEREDICTO EJECUTIVO

SAP contiene el maestro OHEM y postings agregados de nómina con memos que identifican planilla, período y pagos. No conserva el detalle empleado → concepto → neto de forma reconciliable. La frontera externa queda cerrada como `EXTERNAL_PAYROLL_SOURCE_REQUIRED`; el SAP-side queda probado.

## B. DÓNDE VIVE LA NÓMINA

No se encontró archivo externo de nómina en la raíz autorizada inspeccionada ni objeto SAP con employee_id + período + importes de nómina. La evidencia disponible vive en OJDT/JDT1/OACT: asientos de devengamiento, cuentas por pagar, pagos y memos. Las tablas custom con `NOMINA` en el nombre fueron inspeccionadas por metadata y no tienen campos/filas de detalle de payroll.

## C. PAYROLL POSTING MODEL

| Clasificación | Asientos | Líneas | Débito | Crédito |
|---|---:|---:|---:|---:|
| OTHER_HR | 994 | 3159 | 17832423.76 | 2839388.55 |
| PAYROLL_ACCRUAL | 361 | 8030 | 59858595.26 | 53356737.47 |
| PAYROLL_ADJUSTMENT | 433 | 1950 | 26382806.92 | 34240164.29 |
| PAYROLL_PAYMENT | 1851 | 1889 | 41571864.09 | 1272177.71 |
| PAYROLL_PROVISION | 49 | 89 | 1848754.02 | 1590721.47 |
| PAYROLL_REVERSAL | 742 | 5830 | 62754584.06 | 55451390.19 |
| UNRESOLVED | 6939 | 13005 | 16651763.27 | 5403354.22 |

Los memos permiten identificar planillas agregadas, reversas, provisiones y pagos. `PAYROLL_PERIOD_MAPPING_DEGRADED` se mantiene para los asientos sin mes/año explícito; no se asigna período solo por RefDate.

## D. HR EXPENSE RECONCILIATION

**HR_EXPENSE_2026_YTD:** **Bs 13,600,311.25**. Bridge GL por cuentas y categorías:

| Categoría | Bs | % |
|---|---:|---:|
| BONUS_EXPENSE | 2,074,130.54 | 15.25% |
| EMPLOYER_CONTRIBUTIONS | 1,109,289.72 | 8.16% |
| OTHER_PERSONNEL_EXPENSE | 7,286.67 | 0.05% |
| SALARY_EXPENSE | 9,092,018.75 | 66.85% |
| SALES_COMMISSION | 555,340.01 | 4.08% |
| SEVERANCE_EXPENSE | 654,414.34 | 4.81% |
| VACATION_EXPENSE | 107,831.22 | 0.79% |

## E. HR EXPENSE BREAKDOWN

La suma de categorías es exacta; el detalle por cuenta, mes y ProfitCode está en el JSON. No se incluyen salarios individuales.

## F. SALARY EXPENSE

Bs 9,092,018.75.

## G. CONTRIBUTIONS

Bs 1,109,289.72 de costo patronal clasificado; no se mezcla con retenciones de empleados.

## H. BONUS / AGUINALDO / BENEFITS

Bonos/aguinaldo Bs 2,074,130.54; vacaciones e indemnizaciones quedan separadas.

## I. HR LIABILITY UNIVERSE

**Universo candidato:** **Bs -1,031,844.31**. Es un universo de cuentas candidatas, no una afirmación de obligación vigente única.

| Cuenta | Clasificación | Saldo GL | Naturaleza |
|---|---|---:|---|
| 2120101 | SALARIES_PAYABLE | -6,379.96 | PROVEN_BY_ACCOUNT_VOCABULARY |
| 2120104 | OTHER_HR_LIABILITY | -67,593.24 | UNRESOLVED_ACCOUNT_VOCABULARY |
| 2120107 | OTHER_HR_LIABILITY | 20,000.00 | UNRESOLVED_ACCOUNT_VOCABULARY |
| 2120201 | CONTRIBUTIONS_PAYABLE | -86,414.63 | PROVEN_BY_ACCOUNT_VOCABULARY |
| 2120205 | CONTRIBUTIONS_PAYABLE | -176,604.00 | PROVEN_BY_ACCOUNT_VOCABULARY |
| 2120301 | BENEFITS_PAYABLE | -612,811.49 | PROVEN_BY_ACCOUNT_VOCABULARY |
| 2120305 | VACATION_PROVISION | -54,784.45 | PROVEN_BY_ACCOUNT_VOCABULARY |
| 2120403 | OTHER_HR_LIABILITY | -47,256.54 | UNRESOLVED_ACCOUNT_VOCABULARY |

## J. HR LIABILITY ROLL-FORWARD

Se usa saldo neto GL (débito menos crédito): `opening + movements = closing`. Diferencia total: **Bs 0.00**.

## K. PAYROLL PAYMENT MODEL

Pagos identificados por TransType 46 / débito a cuenta laboral: **93 YTD** (**880 histórico**). La existencia de pagos agrupados no permite inferir empleados individuales.
Devengamientos clasificados: **361 histórico**; pagos YTD: **93**.
Timing por períodos identificados en memo: promedio **0.7 días**, mediana **0**, p90 **1.0**; períodos emparejados **23**. Se mantiene degradación para períodos sin señal explícita.

## L. BANK TRACEABILITY

La salida se traza desde pasivo laboral a cuenta contraparte. Cuentas bancarias/caja se marcan como candidatas por metadata/nombre; no se exponen números de cuenta.

| Pasivo | Contraparte | Importe | Tipo |
|---|---|---:|---|
| 2120101 | 1111001 (BMSC Cta.Cte. [BANK_ACCOUNT_REDACTED] MN) | 18,789,013.99 | BANK_OR_CASH_CANDIDATE |
| 2120205 | 1111005 (BANCO UNION CTA. CTE. [BANK_ACCOUNT_REDACTED] M/N) | 5,549,100.05 | BANK_OR_CASH_CANDIDATE |
| 2120101 | 1111004 (Fassil Cta. Cte.  [BANK_ACCOUNT_REDACTED] MN) | 5,146,774.85 | BANK_OR_CASH_CANDIDATE |
| 2120201 | 1111005 (BANCO UNION CTA. CTE. [BANK_ACCOUNT_REDACTED] M/N) | 3,499,287.87 | BANK_OR_CASH_CANDIDATE |
| 2120101 | 1111010 (BANCO FIE Cta.Cte. [BANK_ACCOUNT_REDACTED] MN) | 2,754,256.10 | BANK_OR_CASH_CANDIDATE |
| 2120203 | 1111004 (Fassil Cta. Cte.  [BANK_ACCOUNT_REDACTED] MN) | 793,879.63 | BANK_OR_CASH_CANDIDATE |
| 2120105 | 1111001 (BMSC Cta.Cte. [BANK_ACCOUNT_REDACTED] MN) | 613,763.07 | BANK_OR_CASH_CANDIDATE |
| 2120102 | 1110205 (Cajas Corporativa [BANK_ACCOUNT_REDACTED]do. Anillo MN) | 608,000.00 | BANK_OR_CASH_CANDIDATE |
| 2120202 | 1111004 (Fassil Cta. Cte.  [BANK_ACCOUNT_REDACTED] MN) | 541,933.72 | BANK_OR_CASH_CANDIDATE |
| 2120301 | 1111001 (BMSC Cta.Cte. [BANK_ACCOUNT_REDACTED] MN) | 526,910.84 | BANK_OR_CASH_CANDIDATE |
| 2120105 | 1111004 (Fassil Cta. Cte.  [BANK_ACCOUNT_REDACTED] MN) | 433,347.77 | BANK_OR_CASH_CANDIDATE |
| 2120107 | 1110205 (Cajas Corporativa [BANK_ACCOUNT_REDACTED]do. Anillo MN) | 328,000.00 | BANK_OR_CASH_CANDIDATE |
| 2120101 | 1111006 (BANCO FIE Cta.Cte. [BANK_ACCOUNT_REDACTED] MN) | 274,830.92 | BANK_OR_CASH_CANDIDATE |
| 2120105 | 1111010 (BANCO FIE Cta.Cte. [BANK_ACCOUNT_REDACTED] MN) | 77,000.00 | BANK_OR_CASH_CANDIDATE |
| 2120101 | 1120101 (Cuentas por cobrar clientes MN) | 51,628.74 | BANK_OR_CASH_CANDIDATE |

## M. HR CASH OUT

HR cash-out identificado por débito de pasivo en 2026: **Bs 7,749,365.81**. No se suma nuevamente al gasto.

## N. EXPENSE VS CASH

La diferencia mensual se explica por timing, provisiones, pagos de períodos previos y reversas; el puente empleado a banco requiere fuente externa.

| Mes | Gasto | Cash out | Delta |
|---|---:|---:|---:|
| 2026-01 | 1,726,217.66 | 931,839.69 | 794,377.97 |
| 2026-02 | 1,723,803.57 | 934,845.35 | 788,958.22 |
| 2026-03 | 1,794,361.26 | 1,000,458.86 | 793,902.40 |
| 2026-04 | 1,665,837.58 | 969,556.27 | 696,281.31 |
| 2026-05 | 1,628,964.68 | 953,615.96 | 675,348.72 |
| 2026-06 | 1,716,234.58 | 973,604.01 | 742,630.57 |
| 2026-07 | 1,646,429.52 | 987,785.21 | 658,644.31 |
| 2026-08 | 1,667,349.38 | 977,660.46 | 689,688.92 |
| 2026-09 | 31,113.02 | 20,000.00 | 11,113.02 |

## O. PROFITCODE

Cobertura observada: **99.63%**; `BPLId` no nulo: **0 líneas**. ProfitCode se interpreta como centro de costo según OOCR, no como sucursal automática.

## P. ORGANIZATIONAL ALLOCATION

El mapa OOCR/ProfitCode permite costo por centro de costo. No se divide por headcount porque OHEM no contiene un mapping probado a cada ProfitCode.

## Q. EXTERNAL PAYROLL SOURCE

Estado: **`SOURCE_REQUIRED`**. Raíz inspeccionada: `/home/issajar/Downloads, /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/docs, /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation, /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`. Archivos candidatos: `ninguno`.

## R. EXTERNAL DATA CONTRACT

`employee_id`, `employee_external_id`, `period`, `payment_date`, earnings/conceptos, deducciones, `net_pay`, employer contributions/cost, department, cost center, branch, `payroll_batch_id`, `bank_batch_id`.

## S. EMPLOYEE KEY / MATCHING

Preferencia: `external_employee_id` / código de empleado / `OHEM.empID`. No se usa nombre como clave. Matching queda `SOURCE_REQUIRED`.

## T. OHEM QUALITY

OHEM: 490 empleados; activos 465; inactivos 25.

## U. OHEM→OUSR

Se preserva el hallazgo previo: {'EMPLOYEES': 490, 'WITH_USER': 33, 'WITHOUT_USER': 457, 'VALID_USER_LINK': 33, 'SUPERUSER_LINKS': 2, 'ACTIVE_USER_LINKS': 18}.

## V. OHEM→OSLP

Se preserva el hallazgo previo: {'EMPLOYEES': 490, 'WITH_SALESPERSON': 201, 'VALID_SALESPERSON_LINK': 201}; no se interpreta como vendedor actual.

## W. REAL CASES

- **A: payroll accrual mensual** — `PROVEN`; TransId `498326`, fecha `2022-04-01`, clase `PAYROLL_ACCRUAL`.
- **B: salary/expense → liability** — `PROVEN`; TransId `498326`, fecha `2022-04-01`, clase `PAYROLL_ACCRUAL`.
- **C: liability → bank/cash** — `PROVEN`; TransId `1696876`, fecha `2022-04-01`, clase `PAYROLL_PAYMENT`.
- **D: employer contributions** — `PROVEN`; TransId `498326`, fecha `2022-04-01`, clase `PAYROLL_ACCRUAL`.
- **E: bonus/aguinaldo** — `PROVEN`; TransId `498326`, fecha `2022-04-01`, clase `PAYROLL_ACCRUAL`.
- **F: provision/reversal** — `PROVEN`; TransId `499735`, fecha `2022-04-01`, clase `PAYROLL_REVERSAL`.
- **G: ProfitCode HR** — `PROVEN`; TransId `N/A`, fecha `N/A`, clase `N/A`.
- **H: pago agrupado** — `PROVEN`; TransId `1696876`, fecha `2022-04-01`, clase `PAYROLL_PAYMENT`.
- **I: período de nómina no determinable** — `PROVEN`; TransId `1699745`, fecha `2022-04-01`, clase `PAYROLL_PAYMENT`.
- **J: fuente externa** — `SOURCE_REQUIRED`; TransId `N/A`, fecha `N/A`, clase `N/A`.

## X. RECONCILIATION MATRIX

| Capa | Fuente | Importe | Diferencia | Cobertura | Estado |
|---|---|---:|---:|---:|---|
| Payroll externo | EXTERNAL_FILES | SOURCE_REQUIRED | n/a | 0% | SOURCE_REQUIRED |
| HR Expense | OJDT/JDT1/OACT | Bs 13,600,311.25 | Bs 0.00 | 100% | PASS |
| HR Liability | OACT/JDT1 | Bs -1,031,844.31 | Bs 0.00 | 100% cuentas candidatas | PASS |
| HR Cash Out | JDT1/OVPM boundary | Bs 7,749,365.81 | n/a | payment journals | PASS/DEGRADED explicit |

## Y. INVARIANTS

| Invariante | Estado |
|---|---|
| EPR01_hr_expense_reproduces | PASS |
| EPR02_candidate_liabilities_reproduce | PASS |
| EPR03_hr_accounts_exist_in_oact | PASS |
| EPR04_hr_transids_balance | PASS |
| EPR05_accrual_payment_differentiated | PASS |
| EPR06_expense_liability_not_duplicated | PASS |
| EPR07_payment_expense_not_duplicated | PASS |
| EPR08_hr_expense_reconciles_pnl | PASS |
| EPR09_hr_liabilities_reconcile_bs | PASS |
| EPR10_hr_cash_out_treasury_boundary | PASS |
| EPR11_profitcode_coverage_reproduces | PASS |
| EPR12_bplid_zero_preserved | PASS |
| EPR13_no_employee_detail_inferred | PASS |
| EPR14_external_source_status | PASS |
| EPR15_privacy_minimized | PASS |
| EPR16_sap_write_count | PASS |

## Z. LIMITATIONS

- No se encontró la fuente externa dentro de la raíz autorizada; se requiere solicitarla a Telchi.
- SAP GL identifica conceptos y períodos agregados, no el detalle empleado → neto.
- No se demuestra atraso laboral solo por saldo GL.
- Las cuentas candidatas incluyen clasificaciones `UNRESOLVED_ACCOUNT_VOCABULARY` y deben validarse con la fuente externa.

## AA. FUTURE CONTROLS

Employee master check, payroll total vs GL, gross-to-net, net-pay vs bank batch, contributions paid, old liability, inactive employee paid y unknown ProfitCode.

## AB. NEXT GATE

Con fuente externa: `TELCHI_PAYROLL_EMPLOYEE_LEVEL_RECONCILIATION_V1`. Sin ella: `TELCHI_HR_COST_HEADCOUNT_PRODUCTIVITY_V1`. Pasivos antiguos materiales: `TELCHI_HR_LIABILITIES_BENEFITS_CONTROL_V1`.

## Artefactos

- JSON: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/external_payroll_to_sap_reconciliation/external_payroll_to_sap_reconciliation_v1.json`
- Runner: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/external_payroll_to_sap_reconciliation/external_payroll_to_sap_reconciliation_v1.py`
- SAP/HANA: SELECT-only; `SAP_WRITE_COUNT=0`.

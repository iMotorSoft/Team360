# TELCHI — CREDIT OPEN RISK × AGING × FULL USERS × DELIVERY FLOW V1

**Fecha:** 2026-09-02 (continuación de `TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS`)
**Objetivo:** separar el saldo abierto **normal (no vencido)** del **realmente vencido**,
y profundizar en los Bs 180,396.95 de Usuario FULL y los Bs 71,282.55 de Entrega previa.
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Corte (cutoff) baseline:** **2026-09-01** (inclusive) — `BASELINE_AS_OF_2026_09_01`.
**Moneda:** **BS** única (`DocCur='BS'` para las 268 y para todos los samples HANA).
**Runtime HANA:** `insiding_hana` (READ ONLY). Escrituras SAP/HANA: **0** (`SAP_WRITE_COUNT=0`).

```text
TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS
```

Gates base preservados (no reabiertos): `TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS`,
`TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS`, `TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS`.

Degradaciones heredadas (no bloquean este gate; aging y saldo demostrados):

```text
TN_SOURCE_INSPECTION=PARTIAL
HISTORICAL_AUTHORIZATION=UNAVAILABLE
CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE
DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED
MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP
```

---

## A. RESULTADO

De los **Bs 252,973.00 abiertos** (baseline 2026-09-01):

```text
Bs 175,928.88   todavía dentro del plazo normal de pago   (69.5%; 96 casos)
Bs  77,044.12   YA VENCIDOS                                (30.5%; 66 casos)
```

**Respuesta ejecutiva central: el grueso del "abierto" NO está vencido.** Sólo
un 30.5% de los Bs 252,973 está realmente vencido al corte. Y del vencido, la
mayor parte proviene de **Entrega previa**, no de Usuario FULL (que está
concentrado en ventas recientes aún dentro de plazo).

## B. BASELINE ECONÓMICO

| Concepto | Bs |
| --- | ---: |
| Bruto vendido (268) | 318,051.61 |
| Cobrado (pagos) | 63,686.61 |
| Notas de crédito | 1,392.00 |
| **Abierto** | **252,973.00** = 79.5% del bruto |
| → No vencido | 175,928.88 (69.5% del abierto) |
| → **Vencido** | **77,044.12** (30.5% del abierto) |

Reconciliación del saldo abierto (PHASE 1/2): `open(I) = DocTotal − Σ liquidaciones
activas`. El único pago en/después del corte es DocEntry 11500423 (Bs 748.30) el
2026-09-01, ya contado como cobrado en el gate económico → **OPEN(09-01) =
252,973.00 EXACTO** (Δ=0.00). `ORIGINAL ≈ PAID + CREDITED + OPEN` verificado
caso a caso (0 divergencias >0.05).

Semántica de vencimiento validada (PHASE 2/7): **INV6 = 1 cuota por factura** para
las 162 facturas abiertas (0 multi-cuota en esta instalación) → `OINV.DocDueDate`
es la fecha de vencimiento efectiva; no hay aging multi-cuota que reconstruir.
Estados posibles: FULLY_PAID (105) · OPEN_NOT_DUE (96) · OPEN_FULLY_OVERDUE (66) ·
CREDITED (1). `OPEN_PARTIALLY_OVERDUE` no aplica (sin multi-cuota; 0 casos).

## C. OPEN vs OVERDUE

| Grupo | Abierto (Bs) | No vencido | Vencido | % vencido del abierto | ¿vendedor/reciente? |
| --- | ---: | ---: | ---: | ---: | --- |
| Usuario FULL | 180,396.95 | 161,396.68 | **19,000.27** | **10.5%** | mayoría Julio-Ago, aún en plazo |
| Flujo previo (entrega/pedido) | 71,282.55 | 13,238.70 | **58,043.85** | **81.4%** | mayormente madurado/vencido |
| Cliente excepción | 1,293.50 | 1,293.50 | 0.00 | 0% | ventas 08-30→09-01, no vencidas |
| Contado Retail One | 0 | 0 | 0 | — | cobrado |
| Integración/ajuste | 0 | 0 | 0 | — | cobrado |
| **Total** | **252,973.00** | **175,928.88** | **77,044.12** | **30.5%** | |

**Hallazgo inverso al "open":** el open está dominado por Usuario FULL, pero el
**riesgo (vencido) está dominado por Entrega previa** (Bs 58,043.85 = 75.3% del
total vencido) frente a Usuario FULL (Bs 19,000.27 = 24.7%). El motivo: las
ventas FULL son recientes (jul-ago, mayoría aún dentro de su plazo 31d), mientras
que el flujo de entrega arrastra facturas de feb-jul ya maduradas.

## D. AGING (monto realmente vencido + no vencido)

Nota: los buckets de vencido usan `days_overdue = (2026-09-01 − DocDueDate)`.

| Bucket | Casos | Clientes | Monto abierto (Bs) |
| --- | ---: | ---: | ---: |
| No vencido | 96 | 34 | 175,928.88 |
| 1–15 d | 48 | 20 | 25,434.84 |
| 16–30 d | 9 | 5 | 1,005.02 |
| 31–60 d | 22 | 7 | 16,876.80 |
| 61–90 d | 14 | 4 | 16,761.63 |
| 91–180 d | 28 | 5 | 14,753.35 |
| 181+ | 9 | 5 | 2,212.48 |
| **Vencido (Σ)** | **66** | (20 uniq) | **77,044.12** |

`SUM(buckets vencido) = TOTAL_OVERDUE = 77,044.12` (exhaustivo y disjunto). El
vencido no es marginal: Bs 53,605 (≈70%) tiene más de 30 días de antigüedad.

Categorías de riesgo analíticas (§33): NO_CURRENT_RISK 106 · OPEN_NOT_DUE 96 ·
OVERDUE_LOW_AGE (1-30) 57 · OVERDUE_MEDIUM_AGE (31-90) 36 · OVERDUE_HIGH_AGE (91+) 37.
Estas son categorías **analíticas**, no política Telchi (no se inventan umbrales
de negocio).

## E. USER FULL (40 casos; Bs 180,396.95 abiertos)

```text
De los Bs 180,396.95 abiertos de Usuario FULL:
  Bs 161,396.68  todavía NO vencidos  (89.5%; 23 casos)
  Bs  19,000.27  YA vencidos          (10.5%;  9 casos, 4 clientes, 4 usuarios)
```

| Usuario | Ventas(abiertas) | Clientes | Abierto | No vencido | Vencido (Bs) | % vencido | Máx días |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| jirahola | 4 | 2 | 13,252.11 | 1,461.60 | **11,790.51** | 89.0% | 76 |
| cvallejos | 8 | 3 | 33,106.35 | 27,804.08 | **5,302.27** | 16.0% | 2 |
| soluone (técnico POS) | 2 | 1 | 963.40 | 0.00 | **963.40** | 100% | 13 |
| lzarraga | 9 | 4 | 77,437.08 | 76,492.99 | **944.09** | 1.2% | 25 |
| eroman | 1 | 1 | 2,000.00 | 2,000.00 | 0.00 | 0% | — |
| kfranco | 3 | 2 | 14,240.06 | 14,240.06 | 0.00 | 0% | — |
| yardaya | 4 | 3 | 39,280.34 | 39,280.34 | 0.00 | 0% | — |
| mtolaba | 1 | 1 | 117.61 | 117.61 | 0.00 | 0% | — |

- **El vencido FULL se concentra en jirahola (Bs 11,790.51, 62% del vencido FULL;
  cliente A3TEK C005919)** y, en menor medida, **cvallejos (Bs 5,302.27, 28%;
  cliente C011750)** y soluone (posición POS, Bs 963). lzarraga tiene el mayor
  OPEN (Bs 77k) pero casi todo **no vencido** (ventas ago, en plazo).
- **jirahola** además ejecuta parte de la Entrega previa de LA REJA (ver F): es el
  vínculo entre los dos mecanismos de riesgo.
- **Caveat FULL (§13):** `HISTORICAL_AUTHORIZATION=UNAVAILABLE`. "Usuario FULL"
  = usuario actualmente FULL en el Excel vigente y caso previamente clasificado
  bajo ese modelo; **no** es prueba de autorización FULL en la fecha histórica.
- **mtolaba (§14):** aparece "bloqueado: Sí" en el Excel vigente, pero `OUSR
  user_locked='N'` en HANA y su única venta (C010521, Bs 117.61) **no está
  vencida** y ocurrió 2026-08-11; sin fecha de bloqueo confiable →
  clasificado `BLOCK_DATE_UNRESOLVED` (se documenta, no se acusa).
- **soluone (§15):** cuenta técnica; atribución upstream vía
  `@SO1_01VENTA.U_SO1_USUARIO → OHEM.empID` (2/3 casos FULL con match POS;
  la venta en excepción sin match queda como técnico). Separado SAP vs operador
  POS.

## F. DELIVERY FLOW (140 casos; Bs 71,282.55 abiertos)

```text
De los Bs 71,282.55 abiertos del flujo de entrega:
  Bs 13,238.70  todavía en plazo  (18.6%; 61 casos)
  Bs 58,043.85  YA vencidos       (81.4%; 57 casos, 11 clientes)
```

Top clientes por vencido (flujo entrega):

| Cliente | Ventas | Abierto | Vencido | Máx días | Canal |
| --- | ---: | ---: | ---: | ---: | --- |
| **C010341 LA REJA** | 40 | 47,258.99 | **47,258.99** | 184 | R1/SAP |
| C007834 JOSE KATIMI NOSTA | 2 | 5,063.04 | 5,063.04 | 37 | R1 |
| C011644 NACIR | 2 | 1,998.70 | 1,998.70 | 39 | R1 |
| C010521 ESTER GOMER | 3 | 1,589.85 | 1,426.50 | 25 | R1 |
| C011750 | 2 | 1,322.10 | 987.30 | 2 | R1 |
| (resto, 30 clientes) | — | — | 1,310 | — | — |

- **C010341 LA REJA concentra Bs 47,258.99 del vencido de entrega = 81.4% del
  vencido del grupo y 61.3% de TODO el vencido de las 268.** Es el cliente de
  mayor riesgo único (análisis explícito en §19): 40 ventas por entrega previa,
  **todas** abiertas y **todas** vencidas (0 no vencido), con facturas desde
  fev hasta jul, máx 184 días de vencido. Usuario principal jirahola; canal
  Retail One/SAP Direct.
- **Timing entregado (PHASE 4/17):** 140/140 con fecha de entrega recuperada;
  `delivery→invoice` mediana 0 días (misma fecha) con máx 25; `invoice→due` =
  31 días (plazo estándar); 0 entregas con facturación >60 días después. O sea,
  NO se evidencia "entrega antigua facturada tarde": la factura se emite en la
  entrega y vence a 31 días; el vencido de LA REJA viene de **no pagar**, no de
  un retardo de facturación.
- **Mode DlnLimit=N (§18):** se cuantifica su efecto con evidencia económica
  (Bs 58,043.85 vencidos en el canal de entrega), pero **no** se afirma que
  `DlnLimit=N` sea incorrecto: sólo expone el saldo vencido resultante para
  evaluación de política de Telchi.

## G. CLIENTES (concentración del vencido)

Top 10 por monto vencido:

| CardCode | Cliente | Grupo | Casos | Abierto | Vencido | Viejo venc. | Máx días |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| C010341 | LA REJA | Entrega | 40 | 47,258.99 | 47,258.99 | 2026-03-01 | 184 |
| C005919 | A3TEK S.R.L. | FULL | 3 | 11,790.51 | 11,790.51 | 2026-08-27 | 76 |
| C011750 | Jacobo Martens | FULL+Entrega | 7 | 15,591.34 | 6,289.57 | 2026-08-30 | 2 |
| C007834 | Jose Katimi Nosta | Entrega | 2 | 5,063.04 | 5,063.04 | 2026-07-26 | 37 |
| C010521 | Ester Gomer | Entrega+FULL | 6 | 2,370.59 | 2,370.59 | 2026-08-25 | 25 |
| C011644 | NACIR | Entrega | 2 | 1,998.70 | 1,998.70 | 2026-07-24 | 39 |
| C007776 | Alianza Seguros | FULL | 2 | 963.40 | 963.40 | 2026-08-19 | 13 |
| C011375 | Insumos Generales | Entrega | 3 | 933.86 | 354.28 | 2026-06-04 | 89 |
| (3 clientes menores) | — | — | — | — | ~354 | — | — |

**Concentración económica (§21):** el **Top 1% = 1 cliente (LA REJA) = 61.3% del
vencido** (Bs 47,258.99). El Top 5-6 clientes (LA REJA + A3TEK + C011750 +
C007834 + C010521) ≈ **94% del vencido**. El riesgo vencido está **altamente
concentrado** en pocos clientes, no disperso: 20 clientes con vencido, de los
cuales LA REJA + A3TEK = ~77% y los 5 primeros ≈ 94%.

## H. USUARIOS (concentración del vencido — FULL)

Ver §E. Sobre el vencido FULL (Bs 19,000.27): jirahola 62.1% · cvallejos 27.9% ·
soluone 5.1% · lzarraga 5.0% · (eroman/kfranco/yardaya/mtolaba 0%).

## I. VENDEDORES (OSLP, no confundir con usuario SAP)

Top vendedores (OSLP) por saldo vencido (separado del usuario técnico):

| Vendedor (OSLP) | Casos | Clientes | Abierto (Bs) | Vencido (Bs) |
| --- | ---: | ---: | ---: | ---: |
| Mariela Irigoyen | 18 | 5 | 26,213.67 | 25,606.16 |
| Maria Frances Menacho Rivera | 17 | 6 | 12,762.72 | 12,165.29 |
| Karla Jessenia Cabello | 1 | 1 | 8,648.51 | 8,648.51 |
| Carlos Andres Vallejos Maraz | 10 | 2 | 32,934.36 | 6,289.57 |
| Luz Guzman | 10 | 3 | 6,809.76 | 6,062.78 |
| Elizabeth Pessoa | 5 | 3 | 6,262.50 | 5,063.04 |

(revela concentración comercial distinta de la autorización técnica; Mariela
Irigoyen concentra LA REJA, y Carlos Vallejos es tanto vendedor OSLP como el
usuario FULL `cvallejos` — se mantienen separados: usuario ≠ vendedor ≠ operador.)

## J. MONTHLY COHORTS

| Mes venta | Ventas | Monto (Bs) | Abierto | No vencido | Vencido | % vencido del abierto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ene-26 | 3 | 2,823.43 | 0.00 | 0 | 0 | — |
| feb-26 | 8 | 6,237.45 | 4,715.45 | 0 | 4,715.45 | 100% |
| mar-26 | 14 | 4,095.44 | 2,623.94 | 0 | 2,623.94 | 100% |
| abr-26 | 6 | 4,834.17 | 3,094.17 | 0 | 3,094.17 | 100% |
| may-26 | 13 | 16,148.75 | 13,364.75 | 0 | 13,364.75 | 100% |
| jun-26 | 11 | 19,116.40 | 18,981.10 | 0 | 18,981.10 | 100% |
| jul-26 | 38 | 42,186.10 | 21,330.22 | 0 | 21,330.22 | 100% |
| ago-26 | 168 | 215,711.90 | 182,713.70 | 169,779.21 | 12,934.49 | **7.1%** |
| sep-26 | 7 | 6,897.97 | 6,149.67 | 6,149.67 | 0 | 0% |
| **Total** | **268** | **318,051.61** | **252,973.00** | **175,928.88** | **77,044.12** | 30.5% |

**Revelación clave (§24/25): el 79.5% de abierto es alto en parte porque la
mayoría se originó en agosto, aún dentro de plazo.** Las cohortes feb-jul están
100% vencidas (maduras y sin cobro), mientras la cohorte agosto (Bs 182,713.70
abierto) está sólo 7.1% vencida. YTD: 2026 (ene-sep).

**Cohort maturity / collection rate corregido (§26/27):**
- Collection rate ingenua `paid/gross` = **20.02%**.
- Sobre deuda **madurada** (ventas cuya fecha de vencimiento < corte, que ya
  tuvieron oportunidad real de cobrarse): bruto Bs 134,907.66 → pagado
  Bs 56,471.54 → **collection rate MADURADO = 41.86%**. El 20% crudo subestima;
  gran parte del "no cobrado" aún no venció.

## K. REPEAT EXPOSURE

- **Clientes con 2+ ventas explicadas:** 35 · **3+:** 27 · **5+:** 18.
- **C010341 LA REJA:** 40 ventas, Bs 47,258.99, **39 de ellas mientras ya tenía
  saldo abierto de las anteriores** (patrón `REPEATED_CREDIT_EXPOSURE` — la
  exposición es persistente). Nota conservadora: el `open_exposure_before_sale`
  usa el abierto vigente (cota inferior; si una factura está abierta hoy, estuvo
  abierta en toda fecha anterior).
- **Repeated FULL:** C005919 A3TEK (9 ventas FULL, todas de jirahola, Bs 20,142;
  11,790 vencido) · C011750 (5 FULL, cvallejos) · C003351 (4, lzarraga) ·
  C003450 (3, kfranco/lzarraga/yardaya, Bs 78,733, aún no vencido) · C003526 (3).
- **Repeated delivery:** C010341 (40) y varios E0xxxx (clientes personales) con
  entregas→factura recurrentes.
- No se califica como indebido: son patrones analíticos de exposición repetida.

## L. CURRENT RISK vs MECHANISM (Crédito de exposición y contexto de venta)

Separado explícitamente (regla §3/§32): el *mecanismo* (por qué pasó la venta) no
es el *riesgo actual* (qué está hoy vencido).

| Grupo | Vencido en la venta (contexto histórico) | Bruto | Abierto hoy | Vencido hoy |
| --- | ---: | ---: | ---: | ---: |
| Usuario FULL | 596,396.53 | 189,700.50 | 180,396.95 | 19,000.27 |
| Entrega previa | 3,290,275.33 | 86,449.73 | 71,282.55 | 58,043.85 |

- **Credit exposure at sale:** las 40 ventas FULL se hicieron con cliente ya con
  vencido (Bs 596,396.53 acumulado al vender); las 155 de entrega con vencido aún
  mayor previo (los clientes de entrega ya arrastraban deuda). Esto describe el
  contexto de la venta, **no** el saldo abierto actual.
- **Riesgo actual** se decide por el vencido al corte: DELIVERY 58,044 > FULL
  19,000.

## M. TOP EXECUTIVE CASES (15, con DocEntry)

Prioridad: mayor vencido / más viejo / recurrente / concentración. Los 15 en
`evidence/executive_cases.json`. Top-8:

| Cliente | DocEntry | DocNum | Venta | Vence | Monto | Abierto | Vencido | Días | Grupo | Usuario | Canal |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| A3TEK S.R.L. | 11493496 | 261407002 | 08-27 | 08-27 | 8,648.51 | 8,648.51 | 8,648.51 | 5 | FULL | jirahola | SAP Direct |
| LA REJA | 11448517 | 260102056 | 07-01 | 08-01 | 6,810.00 | 6,810.00 | 6,810.00 | 31 | Entrega | jirahola | R1 |
| Jacobo Martens | 11436103 | 261907297 | 07-30 | 08-30 | 4,776.67 | 4,776.67 | 4,776.67 | 2 | FULL | cvallejos | SAP Direct |
| LA REJA | 11448522 | 260102058 | 07-25 | 08-25 | 4,335.00 | 4,335.00 | 4,335.00 | 7 | Entrega | jirahola | R1 |
| LA REJA | 11319529 | 260101690 | 06-05 | 07-05 | 3,943.94 | 3,943.94 | 3,943.94 | 58 | Entrega | jirahola | R1 |
| LA REJA | 11200827 | 261903415 | 05-04 | 06-04 | 3,619.36 | 3,619.36 | 3,619.36 | 89 | Entrega | eroman | SAP Direct |
| LA REJA | 11319517 | 260101686 | 06-01 | 07-01 | 3,446.33 | 3,446.33 | 3,446.33 | 62 | Entrega | jirahola | R1 |
| Jose Katimi Nosta | 11326775 | 261905775 | 06-26 | 07-26 | 2,531.52 | 2,531.52 | 2,531.52 | 37 | Entrega | ybravo | R1 |

## N. LIMITATIONS

1. `HISTORICAL_AUTHORIZATION=UNAVAILABLE` — FULL = vigente en Excel, no
   autorización histórica probada.
2. `DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED` — pedido-previo DMS sin operador
   humano; se usa vendedor OSLP cuando existe.
3. `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE` — sin historial del flag VENCREVENC.
4. Aging del vencido = días desde `DocDueDate` al corte (no días de cuota;
   instalación de 1 cuota validada para las 162 abiertas).
5. `open_exposure_before_sale` en repeat = cota inferior conservadora (usa el
   abierto vigente, que sólo disminuye con el tiempo).
6. No hay pagos posterior-corte relevantes (sólo 1 en 09-01, incluido); no se
   mezcla `CURRENT_AS_OF_RUN` con el baseline 09-01 (baseline intacto).
7. `TN_SOURCE_INSPECTION=PARTIAL` — el cuerpo del TN no es legible; el bloqueo
   real de venta a cliente vencido no se reproduce literalmente.

## O. TESTS / REGRESSION / READ-ONLY

- **Nuevos LOOP TEST (61-75 + §52): 29 PASS** — `validation/credit_open_risk/
  test_open_risk.py`: baseline 252,973.00 reconciliado (global, documento, grupo);
  due-split 175,928.88/77,044.12; aging exhaustivo/disjunto; USER FULL 40/
  180,396.95/19,000.27; DELIVERY 140/71,282.55/58,043.85; cohorts mensuales
  (268 / 318,051.61 / 252,973.00); temporal (sale≤due; overdue sólo si due<
  cutoff y open>0); moneda BS; usuario≠vendedor; caveat histórico; freeze de
  gates previos (268 + 19 = 287 intacto).
- **Regresión total:** 29 (open-risk) + 26 (económico) + 35 (crédito) + 26
  (credit-control) + 52 (users-audit) = **168 PASS**.
- **HANA smoke real (§52):** 13/13 verificados (5 FULL + 5 DELIVERY + 3 LA REJA
  + 3 oldest overdue): DocDueDate/INV6 single installment, open HANA
  (DocTotal−PaidToDate) = open enriquecido, DocCur='BS'. `hana_smoke_open_risk.json`.
- **Cardinalidad:** 268 casas ↔ 268 sequence rows ↔ 268 DocEntry (`NO_SILENT_FANOUT`
  True; joins OINV→INV6 1:1 en muestras).
- **READ ONLY:** `SAP_WRITE_COUNT=0`, `READ_ONLY_PASS` (`readonly_audit_open_risk.json`).

## P. FINAL GATE

```text
TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS
```

Checklist (§61):

| # | Requisito | Estado |
| --- | --- | ---: |
| 1 | 268/268 casos preservados | ✅ (268 únicos) |
| 2 | Bs 252,973 baseline reconciliados | ✅ (Δ=0.00) |
| 3 | Due-date semantics validadas | ✅ (INV6 1:1) |
| 4 | Installments tratados | ✅ (1 cuota; sin multi-cuota) |
| 5 | Open vs overdue cerrado | ✅ (175,928.88 / 77,044.12) |
| 6 | Aging reconciliado | ✅ (Σ buckets = 77,044.12) |
| 7 | USER FULL reconciliado | ✅ (40 / 180,396.95 / 19,000.27) |
| 8 | DELIVERY FLOW reconciliado | ✅ (140 / 71,282.55 / 58,043.85) |
| 9 | Concentración por cliente | ✅ (LA REJA 61.3% del vencido) |
| 10 | Concentración usuario/vendedor | ✅ (§E/H/I) |
| 11 | Monthly cohorts | ✅ (268 / 318,051.61 / 252,973.00) |
| 12 | Repeat exposure | ✅ (35/27/18 clientes 2+/3+/5+) |
| 13 | Executive cases con DocEntry | ✅ (15) |
| 14 | NO_SILENT_FANOUT | ✅ |
| 15 | Regression PASS | ✅ 168 |
| 16 | SAP_WRITE_COUNT=0 | ✅ |

**Respuesta ejecutiva (§59):**

> Analizamos los Bs 252,973 que permanecían abiertos. **Bs 175,929 todavía
> estaban dentro del plazo normal**; **Bs 77,044 ya estaban vencidos**. Del
> vencido, **Bs 58,044 correspondían al flujo de entrega previa** y **Bs 19,000 a
> ventas bajo Usuario FULL**. El cliente principal fue **LA REJA (C010341)**, con
> Bs 47,259 vencidos (entregas previas); le siguen A3TEK (Bs 11,791) y Jacobo
> Martens (Bs 6,290). Los usuarios que concentran el vencido FULL fueron
> **jirahola** (Bs 11,791) y **cvallejos** (Bs 5,302); por vendedor, **Mariela
> Irigoyen** y **Maria F. Menacho** concentran el grueso del canal de entrega. El
> vencido se concentra en pocos clientes: el 94% del vencido está en 5 clientes.

**P0 — USER FULL (§35):** de Bs 180,396.95 abiertos de FULL, Bs 161,396.68 no
están vencidos y Bs 19,000.27 sí. Usuarios: jirahola (11,790) y cvallejos
(5,302). Clientes: A3TEK (11,790). La mayor parte del open FULL (lzarraga,
yardaya, kfranco) es venta reciente aún en plazo.

**P0 — DELIVERY (§36):** de Bs 71,282.55 abiertos del flujo de entrega,
Bs 13,238.70 en plazo y Bs 58,043.85 vencidos. El cliente principal (LA REJA)
representa Bs 47,259. Sólo Bs 12,934 del vencido corresponde a ventas de agosto
(las de feb-jul están 100% vencidas).

**P0 — TOTAL (§37):** de Bs 252,973 abiertos, Bs 175,929 en plazo normal y
Bs 77,044 efectivamente vencidos = 30.5% del abierto (24.2% del bruto de las 268).

**Aclaración (§60):** tener autorización FULL no significa que la venta sea
incorrecta, y `DlnLimit=N` no significa que la configuración esté mal. Este gate
sólo cuantifica uso, exposición, aging y cobranza para que Telchi evalúe su
política.

**Siguiente paso recomendado:** llevar a Telchi la evidencia económica del flujo
de entrega (Bs 58,044 vencidos, LA REJA 61%) y el vencido FULL de jirahola/A3TEK;
evaluar gestión de cobranza sobre el saldo madurado no cobrado; cerrar
`TN_SOURCE_INSPECTION=EXACT` con cuenta con EXECUTE.

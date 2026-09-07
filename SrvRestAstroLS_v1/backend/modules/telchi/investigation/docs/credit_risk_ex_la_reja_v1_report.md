# TELCHI — CREDIT RISK EX LA REJA V1

**Gate:** `TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS`
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Baseline as-of:** 2026-09-01 (frozen)
**HANA access:** READ ONLY (`SAP_WRITE_COUNT=0`)
**Fecha:** 2026-09-03
**Dependencias:** `TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS` (LA REJA =
INTERNAL / RELATED-PARTY CONSUMPTION ACCOUNT)

---

## A. RESULTADO

> Al excluir C010341 LA REJA del universo de crédito, el **vencido pasa de
> Bs 77,044.12 a Bs 29,785.13** (−61.3%). El 61.3% del vencido inicialmente
> observado era LA REJA, cuenta interna/parte relacionada demostrada en el gate
> previo.

**El riesgo restante se invierte de mecanismo**: antes el vencido lo dominaba
el flujo de entrega (75.3%), ahora lo domina **Usuario FULL (Bs 19,000.27 =
63.8%)**. El flujo de entrega cae a Bs 10,784.86 (36.2%) — y ya **no existen
buckets de aging 91-180 / 181+**: el perfil maduro era LA REJA.

---

## B. POR QUÉ SE EXCLUYE LA REJA

Gate `TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS` demostró:

- C010341 = cuenta interna / parte relacionada (familia Telchi), **no cliente
  comercial externo**.
- NIT 1468238 compartido con S0001 (propietario); grupo OCRG 119 "Socios".
- 0 ORCT de pago en toda la historia; única NC de limpieza Bs 1,572.
- 85 facturas, Bs 93,769.76 abiertos históricos; entregas "PARA LA REJA",
  "PARA SR ROBERTO TELCHI", "MEDICAMENTOS", choferes propios.
- Precios preferenciales internos (70.8% del monto SYMBOLIC).

Regla de exclusión aplicada (EXACTA, reproducible):

```text
EXCLUDED_REASON = RELATED_PARTY_INTERNAL_ACCOUNT_C010341
filter: CardCode == 'C010341'    (nunca por nombre/grupo/NIT/heurística)
```

---

## C. UNIVERSO ORIGINAL (baseline congelado)

Fuentes: `credit_control/evidence/phase78_sale_credit_state.json` (287 prior),
`credit_exception/evidence/classified_cases.json` (2318; subconjunto 287),
`credit_exception_economic/evidence/grouped_cases.json` (268 explicadas),
`credit_open_risk/evidence/open_risk_cases.json` (268 con aging).

| Métrica | Valor |
|---|---:|
| Casos analíticos (287) | 287 = 268 explicadas + 19 UNRESOLVED |
| Explicadas | 268 |
| UNRESOLVED | 19 (auditados: C010341 count = 0) |
| UNEXPLAINED | 0 |
| Gross (268 explicadas) | Bs 318,051.61 |
| Paid | Bs 63,686.61 |
| Credited (NC) | Bs 1,392.00 |
| Open | Bs 252,973.00 |
| Not due | Bs 175,928.88 |
| **Overdue** | **Bs 77,044.12** |

### Distribución por reason code (287)

| Reason code | Original |
|---|---:|
| DELIVERY_FLOW_EXPLAINS_TIMING | 140 |
| PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK | 58 |
| SAP_FULL_AUTHORIZATION | 40 |
| ORDER_AUTHORIZED_BEFORE_OVERDUE | 15 |
| CUSTOMER_EXCEPTION_FLAG | 12 |
| TECHNICAL_INTEGRATION_PATH | 2 |
| CREDIT_NOTE_OR_RECONCILIATION | 1 |
| UNRESOLVED | 19 |

---

## D. UNIVERSO EX LA REJA

Derivado de los datasets atómicos (no hardcodeado):

| Métrica | Original | LA REJA | **EX LA REJA** |
|---|---:|---:|---:|
| Casos (287) | 287 | 40 | **247** |
| Explicadas | 268 | 40 | **228** |
| UNRESOLVED | 19 | 0 | **19** |
| UNEXPLAINED | 0 | 0 | **0** |
| Clientes | 55 | 1 | **54** |
| Gross | 318,051.61 | 47,258.99 | **270,792.62** |
| Paid | 63,686.61 | 0.00 | **63,686.61** |
| Credited | 1,392.00 | 0.00 | **1,392.00** |
| Open | 252,973.00 | 47,258.99 | **205,714.01** |
| Not due | 175,928.88 | 0.00 | **175,928.88** |
| **Overdue** | **77,044.12** | **47,258.99** | **29,785.13** |

---

## E. IMPACTO ECONÓMICO DE LA EXCLUSIÓN

**Antes / Después (tabla P0):**

| Métrica | Con LA REJA | Sin LA REJA | Diferencia |
|---|---:|---:|---:|
| Casos | 287 | 247 | **−40** |
| Monto bruto | 318,051.61 | 270,792.62 | −47,258.99 |
| Abierto | 252,973.00 | 205,714.01 | −47,258.99 |
| Vencido | 77,044.12 | 29,785.13 | **−47,258.99** |
| No vencido | 175,928.88 | 175,928.88 | 0.00 |
| Clientes con vencido | 20 | 12 | −8 |
| Top 1 concentración | 61.3% (LA REJA) | **39.6% (A3TEK)** | — |

Tolerancia usada: 0.05 Bs; todas las reconciliaciones `ALL == LA_REJA + EX`
PASS (gross/paid/credited/open/overdue/not_due, ver §V).

---

## F. OPEN vs OVERDUE

```text
OVERDUE_EX = 29,785.13 = 14.5% del open limpio (205,714.01)
NOT_DUE_EX = 175,928.88 = 85.5% del open limpio
```

El riesgo vencido del universo restante es **mucho menos concentrado en monto
absoluto que antes** (−61.3%).

Overdue share:
- LA REJA / ALL = **61.3%** (47,258.99 / 77,044.12)
- EX / ALL = 38.7% (29,785.13 / 77,044.12)

---

## G. AGING

Fuente: `evidence/aging_recalc.json`.

| Aging | Casos | Clientes | Monto |
|---|---:|---:|---:|
| NOT_YET_DUE | 202 | 34 | 175,928.88 |
| 1–15 | 16 | 10 | 21,072.94 |
| 16–30 | 3 | 2 | 888.02 |
| 31–60 | 5 | 4 | 6,122.86 |
| 61–90 | 2 | 2 | 1,701.31 |
| 91–180 | **0** | 0 | **0.00** |
| 181+ | **0** | 0 | **0.00** |

**Sin LA REJA no queda aging maduro (>90 días).** El vencido restante es
joven: 70.7% en 1–15 días; el bucket más viejo es 61–90 (Bs 1,701.31).
`SUM(buckets vencidos) = 29,785.13 = OVERDUE_EX` ✓; `OPEN == NOT_DUE + OVERDUE` ✓.

---

## H. BUSINESS GROUPS

Fuente: `evidence/economic_recalc.json`, `evidence/mechanism_risk_ex.json`.

| Mecanismo | Original | LA REJA | **EX** |
|---|---:|---:|---:|
| USER_AUTHORIZATION_FULL | 40 | 0 | **40** |
| DOCUMENT_FLOW_PREAUTHORIZED | 155 | 40 | **115** |
| CUSTOMER_EXCEPTION | 12 | 0 | **12** |
| NON_CREDIT_RETAIL_CASH | 58 | 0 | **58** |
| TECHNICAL_RECONCILIATION | 3 | 0 | **3** |
| **Total explicadas** | **268** | **40** | **228** |

Por reason code (reconciliación fila por fila):

| Reason code | Original | LA REJA | EX |
|---|---:|---:|---:|
| DELIVERY_FLOW_EXPLAINS_TIMING | 140 | 40 | **100** |
| PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK | 58 | 0 | 58 |
| SAP_FULL_AUTHORIZATION | 40 | 0 | 40 |
| ORDER_AUTHORIZED_BEFORE_OVERDUE | 15 | 0 | 15 |
| CUSTOMER_EXCEPTION_FLAG | 12 | 0 | 12 |
| TECHNICAL_INTEGRATION_PATH | 2 | 0 | 2 |
| CREDIT_NOTE_OR_RECONCILIATION | 1 | 0 | 1 |
| UNRESOLVED | 19 | 0 | 19 |

`ORIGINAL == LA_REJA + EX` fila por fila ✓ · `NO_DOUBLE_COUNT` ✓ (cada
DocEntry en un solo grupo principal).

---

## I. USER FULL

**Revalidado:** LA REJA **no** tenía casos USER FULL (sus 40 estaban en
delivery flow). USER FULL limpio = 40 casos sin cambios:

| User FULL | Casos | Clientes | Gross | Open | Overdue | Not due |
|---|---:|---:|---:|---:|---:|---:|
| TOTAL | 40 | 14 | 189,700.50 | 180,396.95 | **19,000.27** | 161,396.68 |

Detalle de vencidos USER FULL (9 casos, orden desc):

| Usuario | Cliente | DocEntry | Due | Días | Overdue | Canal |
|---|---|---|---:|---:|---:|---|
| jirahola | A3TEK (C005919) | 11493496 | 08-27 | 5 | 8,648.51 | SAP_DIRECT |
| cvallejos | C011750 | 11436103 | 08-30 | 2 | 4,776.67 | SAP_DIRECT |
| jirahola | A3TEK (C005919) | 11484582 | 08-20 | 12 | 1,750.00 | SAP_DIRECT |
| jirahola | A3TEK (C005919) | 11315660 | 06-17 | 76 | 1,392.00 | SAP_DIRECT |
| soluone | ALIANZA SEGUROS (C007776) | 11446534 | 08-19 | 13 | 896.80 | RETAIL_ONE |
| cvallejos | C011750 | 11435493 | 08-30 | 2 | 525.60 | SAP_DIRECT |
| lzarraga | C010521 ESTER GOMER | 11427139 | 08-27 | 5 | 510.21 | SAP_DIRECT |
| lzarraga | C010521 ESTER GOMER | 11361286 | 08-07 | 25 | 433.88 | SAP_DIRECT |
| soluone | ALIANZA SEGUROS (C007776) | 11452365 | 08-20 | 12 | 66.60 | RETAIL_ONE |

### Usuarios FULL prioritarios (ranking vencido EX, todos los usuarios)

| Usuario | Casos | Clientes | Open | Overdue |
|---|---:|---:|---:|---:|
| jirahola | 11 | 2 | 13,252.11 | **11,790.51** |
| ybravo | 105 | 29 | 15,807.67 | 7,667.74 |
| cvallejos | 11 | 3 | 35,324.35 | 6,289.57 |
| lzarraga | 15 | 5 | 81,185.92 | 2,370.59 |
| soluone | 50 | 10 | 2,256.90 | 963.40 |
| eroman | 7 | 4 | 3,101.26 | 354.28 |
| jheredia | 4 | 1 | 349.04 | 349.04 |
| kfranco / yardaya / mtolaba | 10 | 6 | 54,436.76 | 0.00 |

- **jirahola → A3TEK (C005919) revalidado:** Bs 11,790.51 vencidos
  (3 casos FULL + historial delivery), máx 224 días → **candidato #1**.
- **cvallejos → C011750 (25049 JACOBO MARTENS HARMS-GERHARD HAM MARTENS)
  revalidado:** Bs 6,289.57 vencidos (2 casos FULL + 1 delivery).

---

## J. DELIVERY FLOW

Original: 140 casos / gross 72,784.72 / open 71,282.55 / overdue 58,043.85.

**EX LA REJA:**

| Delivery | Valor |
|---|---:|
| Casos (reason DELIVERY_FLOW) | **100** (140 − 40 LA REJA) |
| Casos (grupo DOCUMENT_FLOW, incluye 15 order) | 115 |
| Gross (grupo) | 39,190.74 |
| Open | 24,023.56 |
| Not due | 13,238.70 |
| **Overdue** | **10,784.86** |
| Clientes con vencido | 11 |

**P0 — Reinterpretación:** el aparente «riesgo de entrega» era en su mayor
parte LA REJA. Con LA REJA fuera, el delivery pasa de Bs 58,043.85 a
Bs 10,784.86 (−81.4%) y **deja de ser el principal foco económico** del
vencido comercial: ahora lo es Usuario FULL (Bs 19,000.27 vs 10,784.86).

`DlnLimit=N` sigue siendo relevante como mecanismo de liberación de entrega,
pero **económicamente el foco del vencido pasa a la autorización FULL**.

---

## K. CUSTOMER EXCEPTION

Sin LA REJA (verificado; 0 casos LA REJA en excepción):

| Métrica | Valor |
|---|---:|
| Casos | 12 |
| Cliente | C000398 PEDIDOSYA |
| Gross / Open / Not-due | Bs 1,293.50 / 1,293.50 / 1,293.50 |
| Overdue | **0.00** |

Sin cambio vs baseline. `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE` (degradación
preservada).

---

## L. UNRESOLVED

Auditoría de los 19 UNRESOLVED vs CardCode: **C010341 count = 0** ✓.

| Métrica | Valor |
|---|---:|
| Casos | 19 (sin cambios) |
| Open (no vencido, no classable) | Bs 12,168.76 |
| Clientes | 6 (C000018, C003360, C007776, C007834, C010521, C012133) |
| Ventana | 2026-02-19 → 2026-08-28 |
| Naturaleza | microventas Retail One sin liquidación en SAP (misma causa del gate
  de excepciones; `UNRESOLVED != UNEXPLAINED`, `UNRESOLVED != necessarily overdue` — su
  open contable no ingresa al cálculo de vencido EX) |

---

## M. CLIENTES PRINCIPALES

Fuente: `evidence/customer_ranking.json`. `SUM(ranking overdue) =
29,785.13 == OVERDUE_EX` ✓.

| CardCode | Nombre | Casos | Gross | Open | Overdue | Max días | Usuario | Vendedor |
|---|---|---:|---:|---:|---:|---:|---|---|
| C005919 | A3TEK S.R.L. | 10 | 21,534.51 | 11,790.51 | **11,790.51** | 224 | jirahola | (-), K. Cabello |
| C011750 | 25049 - JACOBO MARTENS HARMS - GERHARD HAM MARTENS | 7 | 15,591.34 | 15,591.34 | **6,289.57** | 2 | cvallejos | C. A. Vallejos Maraz |
| C007834 | JOSE KATIMI NOSTA | 3 | 5,588.04 | 5,063.04 | **5,063.04** | 37 | ybravo | E. Pessoa |
| C010521 | 11932 - ESTER GOMER | 6 | 2,884.94 | 2,884.94 | **2,370.59** | 25 | lzarraga | L. Zarraga |
| C011644 | NACIR | 2 | 1,998.70 | 1,998.70 | **1,998.70** | 39 | ybravo | M. F. Menacho / M. Irigoyen |
| C007776 | ALIANZA SEGUROS S.A. | 4 | 1,117.70 | 963.40 | **963.40** | 187 | soluone | múltiples |
| C011375 | INSUMOS GENERALES | 3 | 933.86 | 933.86 | **354.28** | 89 | eroman | L. Guzman |
| C011993 | Cliente Generico Complemento | 4 | 474.49 | 349.04 | **349.04** | 7 | jheredia | M. Irigoyen / P. Méndez / S. Oly |
| E000051 | PINTO ROSMERY | 12 | 1,389.43 | 894.98 | **286.02** | 8 | ybravo | múltiples |
| E000349 | NOE PAZ MARIA FERNANDA | 5 | 340.82 | 329.12 | **198.20** | 13 | ybravo | C. Salvatierra / M. F. Menacho |
| E000076 | ROSAS RODRIGUEZ NOEMY | 11 | 1,702.36 | 549.28 | **68.14** | 5 | ybravo | B. Vargas / C. Santander / L. Merlo |
| E000453 | MENACHO ESCALANTE LUIS ANGEL | 15 | 888.44 | 739.19 | **53.64** | 36 | ybravo | B. Vargas / C. Santander / L. Merlo |

### Concentración (sobre OVERDUE_EX = 29,785.13)

| Tier | Amount | % |
|---|---:|---:|
| Top 1 (A3TEK) | 11,790.51 | **39.59%** |
| Top 5 | 27,512.41 | 92.37% |
| Top 10 | 29,663.35 | 99.59% |
| Clientes con vencido | 12 | 100% |

### Nuevo cliente #1 — `TOP_OVERDUE_CUSTOMER_EX_LA_REJA`

| Campo | Valor |
|---|---|
| CardCode / Name | C005919 / A3TEK S.R.L. |
| Overdue | Bs 11,790.51 (39.6% del vencido limpio) |
| Open | Bs 11,790.51 |
| Casos / overdue casos | 10 / 3 |
| Max days overdue | 224 (feb batches 2026) |
| Usuario | jirahola (FULL) |
| Vendedores | (-), Karla J. Cabello |
| Canal | SAP_DIRECT |
| Business group | USER_AUTHORIZATION_FULL (+ TECHNICAL_RECONCILIATION) |
| Repeat | 10 ventas mientras abierto/vencido |

**Candidato prioritario para gate atómico de identidad** (¿cliente comercial
real o relacionado? — no se concluye aquí).

---

## N. USUARIOS

Ver §I (tabla de usuarios). Invariante mantenida: `SAP USER != OSLP
SALESPERSON` (documento a documento).

---

## O. VENDEDORES

Fuente: `evidence/salesperson_ranking.json` (por OSLP, Nunca mezclado con
usuario).

| Vendedor | Casos | Clientes | Open | Overdue |
|---|---:|---:|---:|---:|
| Karla Jessenia Cabello | 1 | 1 | 8,648.51 | 8,648.51 |
| Carlos Andres Vallejos Maraz | 10 | 2 | 32,934.36 | 6,289.57 |
| Elizabeth Pessoa | 6 | 3 | 6,262.50 | 5,063.04 |
| -Ningún empleado del departament | 10 | 2 | 4,603.60 | 3,142.00 |
| Luis Zarraga | 14 | 4 | 12,254.25 | 2,370.59 |
| Maria Frances Menacho Rivera | 9 | 6 | 1,794.33 | 1,196.90 |
| Mariela Irigoyen | 6 | 5 | 1,607.51 | 1,000.00 |
| Noemy Rosas | 20 | 2 | 896.80 | 896.80 |
| Luz Guzman | 4 | 2 | 1,101.26 | 354.28 |
| Silvia Oly | 4 | 2 | 411.59 | 349.04 |

---

## P. CANALES

Fuente: `evidence/channel_ranking.json`. Classifier EXACT reutilizado
(RETAIL_ONE / DMS / SAP_DIRECT); sin reimplementación.

| Canal | Casos | Gross | Open | Overdue |
|---|---:|---:|---:|---:|
| SAP_DIRECT | 42 | 190,482.06 | 180,534.81 | **18,391.15** |
| RETAIL_ONE | 169 | 65,999.23 | 25,179.20 | 11,393.98 |
| DMS | 17 | 14,311.33 | 0.00 | 0.00 |

El vencido limpio se concentra en SAP_DIRECT (61.7%) — operaciones
autorizadas directamente en SAP (FULL), no en POS.

---

## Q. MONTHLY COHORTS

Fuente: `evidence/monthly_cohorts_ex.json`. `SUM(month gross) == CLEAN_GROSS` ✓;
`SUM(month overdue) == CLEAN_OVERDUE` ✓.

| Mes | Casos EX | Gross EX | Open EX | Overdue EX | % ven/open EX |
|---|---:|---:|---:|---:|---:|
| 2026-01 | 3 | 2,823.43 | 0.00 | 0.00 | 0.00% |
| 2026-02 | 3 | 1,522.00 | 0.00 | 0.00 | 0.00% |
| 2026-03 | 3 | 1,471.50 | 0.00 | 0.00 | 0.00% |
| 2026-04 | 2 | 1,740.00 | 0.00 | 0.00 | 0.00% |
| 2026-05 | 3 | 3,093.31 | 309.31 | 309.31 | 100.00% |
| 2026-06 | 5 | 6,635.31 | 6,500.01 | 6,500.01 | 100.00% |
| 2026-07 | 34 | 30,897.20 | 10,041.32 | 10,041.32 | 100.00% |
| 2026-08 | 168 | 215,711.90 | 182,713.70 | 12,934.49 | 7.08% |
| 2026-09 | 7 | 6,897.97 | 6,149.67 | 0.00 | 0.00% |

**Respuesta P0:** las cohortes feb-mar-abr pasan de 100% vencidas a **0.00**
sin LA REJA (eran facturas de LA REJA). Las cohortes antiguas con vencido
residual quedan en may-jun-jul (montos menores), y ago mantiene perfil
joven (7.08%), consistente con el aging sin maduro.

---

## R. COLLECTION KPI

Fuente: `evidence/collection_kpi_ex.json`. LA REJA **no aparece** en
denominador ni numerador del KPI limpio (verificado T36).

| KPI | Con LA REJA | Sin LA REJA |
|---|---:|---:|
| Collection rate bruto | 20.02% | **23.52%** |
| Matured collection rate | 20.47% (prev report 41.86% con definición cohorte) | **23.85%** |
| Open rate | 79.54% | **75.97%** |
| Overdue / open | 30.46% | **14.48%** |
| Overdue / gross | 24.22% | **11.00%** |

> Nota metodológica: el "matured collection rate 41.86%" del gate open-risk se
> calculaba con otra definición de cohorte (excluye mes más reciente). Para
> comparación homogénea WITH/EX este gate recalcula ambas con la misma
> definición (mature = excluye 2026-08): 20.47% → 23.85%. La mejora es
> modesta porque LA REJA no aportaba pagos; el efecto principal está en
> overdue/open (30.5% → 14.5%).

---

## S. TOP EXECUTIVE CASES (universo limpio)

Prioridad: overdue, días, repeat, USER FULL. DocEntry preservados (ver
`evidence/customer_ranking.json`, `user_full_detail_ex.json`,
`delivery_flow_ex.json`).

1. **C005919 A3TEK** — 11493496 (FULL jirahola, Bs 8,648.51, due 08-27) +
   11484582 (FULL, 1,750) + 11315660 (FULL, 1,392, 76d) + historial delivery.
2. **C011750 25049 JACOBO MARTENS-GERHARD HAM** — 11436103 (FULL cvallejos,
   4,776.67) + 11435493 (FULL, 525.60) + 11436112 (delivery, 987.30).
3. **C007834 JOSE KATIMI NOSTA** — 11326775 + 11326778 (delivery ybravo,
   2,531.52 c/u, 37d) + histórico (UNRESOLVED 2026-02).
4. **C010521 11932 ESTER GOMER** — 11427139 (FULL lzarraga, 510.21) +
   11427140 (delivery, 999) + 11360878 (delivery, 427.50, 25d).
5. **C011644 NACIR** — 11370307 + 11474100 (delivery ybravo, 998-1,000, 5-39d).
6. **C007776 ALIANZA SEGUROS** — 11446534 + 11452365 (FULL soluone,
   896.80+66.60, canal RETAIL_ONE) + 2 delivery; máx 187d.
7. **C011375 INSUMOS GENERALES** — 11200987 (delivery eroman, 309.31, 89d).
8. **C011993 Cliente Generico Complemento** — 11491091 (delivery jheredia,
   349.04, 7d) — **nombre genérico → candidato a verificación de identidad**.
9. **E000051 PINTO ROSMERY** — 12 casos ybravo, 286.02 vencido.
10. **E000349 / E000076 / E000453** (empleados/vendedores, ybravo) — vencidos
    menores (198.20 / 68.14 / 53.64).

---

## T. NEXT CLIENTS TO INVESTIGATE

Candidatos a gate atómico tipo LA REJA (no analizados en profundidad aquí):

1. **C005919 A3TEK S.R.L.** — Bs 11,790.51 vencido (39.6%), 224d, jirahola
   FULL → ¿cliente comercial real? Alto volumen y autorización FULL repetida.
2. **C011750 (25049 JACOBO MARTENS HARMS-GERHARD HAM MARTENS)** — Bs 6,289.57
   (21.1%), cvallejos FULL + delivery, por vencer 2d → riesgo reciente grande.
3. **C007834 JOSE KATIMI NOSTA** — Bs 5,063.04 (17.0%), ybravo delivery + 2
   UNRESOLVED de feb-2026 (mismo día, Bs 5,727.60) → doble señal.

Además: **C011993 "Cliente Generico Complemento"** (nombre genérico) y
**C007834** merecen la verificación de identidad análoga a LA REJA antes de
afirmaciones ejecutivas fuertes (regla §74).

---

## U. LIMITATIONS

1. Degradaciones preservadas: `TN_SOURCE_INSPECTION=PARTIAL`,
   `HISTORICAL_AUTHORIZATION=UNAVAILABLE`, `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE`,
   `DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED`,
   `MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP`.
2. El universo analítico es el baseline 287/268 (frozen). El universo exacto
   de 2,318 ventas con vencido en fecha NO se re-excluye aquí (fuera de scope;
   las 40 LA REJA están en ambos y la exclusión es idéntica por DocEntry).
3. Los "UNRESOLVED" (19) se auditaron por CardCode pero no se reclasificaron.
4. El aging limpio se construyó sobre las 228 explicadas (las 19 UNRESOLVED no
   aportan overdue a este corte; su open contable es 12,168.76).
5. C011993 "Cliente Generico Complemento" aparece como candidato interno
   potencial (se documenta, no se excluye sin investigación propia).
6. La comparación del matured collection rate usa una única definición de
   cohorte para WITH/EX; difiere en magnitud de la definición del gate previo.

---

## V. TESTS

**Loop tests nuevos (`test_credit_risk_ex_la_reja.py`): 45 PASS / 0 FAIL**
(cubre exclusión identity, no-leakage, universe split, unique DocEntry,
amounts ×6, baseline overdue, groups no-double-count, delivery 140→100,
USER FULL intacto, aging, ranking sum, users≠vendedores, channels, cohorts,
collection KPI, SAP_WRITE_COUNT=0, NO_SILENT_FANOUT).

**HANA smoke real (`hana_smoke.py`): 27 checks / 0 failures** (5 LA REJA
excluidos verificados en OINV, 5 clean overdue, 5 USER FULL, 5 delivery,
top-3 clientes con open de ventana == evidencia).

**Regresión (gates previos preservados):**

| Suite | Resultado |
|---|---|
| La Reja identity (`test_la_reja_identity.py`) | 23 PASS |
| La Reja smoke HANA | 60/60 |
| credit_open_risk | 29 PASS |
| credit_exception_economic | 26 PASS |
| credit_exception | 35 PASS |
| users_audit (5 suites) | 52 PASS |
| stock_domain | 20 PASS |
| inventory transtype gate | PASS |

**READ ONLY:** `SAP_WRITE_COUNT=0` (auditado). Podman lifecycle MANUAL
respetado (HANA disponible; no se inició/detuvo contenedor).

---

## W. FINAL GATE

Condiciones `TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS`:

1. ✅ 40 casos LA REJA identificados por DocEntry (y cruzados con el dataset
   atómico de identidad: coincidencia exacta)
2. ✅ Sólo C010341 excluido (`excluded_bp_distinct=[C010341]`)
3. ✅ No leakage (C010341 count = 0 en clean universe / aging / ranking /
   cohorts / mechanism)
4. ✅ Universo original = LA REJA + EX (287 = 40 + 247; 268 = 40 + 228)
5. ✅ Gross reconciliado (318,051.61 = 47,258.99 + 270,792.62)
6. ✅ Paid reconciliado (63,686.61 = 0 + 63,686.61)
7. ✅ Credits reconciliados (1,392.00 = 0 + 1,392.00)
8. ✅ Open reconciliado (252,973.00 = 47,258.99 + 205,714.01)
9. ✅ Overdue reconciliado (77,044.12 = 47,258.99 + 29,785.13)
10. ✅ Aging clean reconciliado (buckets = 29,785.13; open = not_due + overdue)
11. ✅ Business groups clean reconciliados (no double count)
12. ✅ USER FULL recalculado (40 casos, 19,000.27 vencido)
13. ✅ DELIVERY recalculado (100 casos razón / 115 grupo; 10,784.86 vencido)
14. ✅ Clientes re-rankeados (A3TEK nuevo #1)
15. ✅ Usuarios/vendedores re-rankeados (separados)
16. ✅ Channel distribution recalculada (SAP_DIRECT 61.7% del vencido)
17. ✅ Collection KPI recalculado (WITH vs EX, sin LA REJA en KPI limpio)
18. ✅ Monthly cohorts recalculadas (feb-abr 0% vencido sin LA REJA)
19. ✅ Top executive cases preservan DocEntry
20. ✅ NO_DOUBLE_COUNT
21. ✅ NO_SILENT_FANOUT
22. ✅ Regression PASS (23+60+29+26+35+52+20+transtype)
23. ✅ SAP_WRITE_COUNT=0

**Declaración:**

```text
TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS
```

**Respuesta ejecutiva:**

> Recalculamos el riesgo de crédito excluyendo C010341 LA REJA, demostrada
> previamente como cuenta interna / parte relacionada.
>
> **Antes:** Bs 77,044.12 vencidos.
> **LA REJA:** Bs 47,258.99 (61.3%).
> **Después de excluirla: Bs 29,785.13 realmente permanecen vencidos** en el
> universo restante (270,792.62 gross; 205,714.01 open; 175,928.88 no vencido).
>
> Eso implica que **el 61.3% del vencido inicialmente observado correspondía a
> LA REJA**. El riesgo restante se concentra en:
>
> 1. **A3TEK (C005919)** — Bs 11,790.51 (39.6%; jirahola FULL, 224d)
> 2. **C011750 (25049 JACOBO MARTENS HARMS-GERHARD HAM MARTENS)** — Bs 6,289.57 (21.1%; cvallejos FULL)
> 3. **C007834 JOSE KATIMI NOSTA** — Bs 5,063.04 (17.0%; ybravo delivery)
>
> Por mecanismo:
> **Usuario FULL: Bs 19,000.27 vencidos (63.8%)** · **Entrega previa:
> Bs 10,784.86 (36.2%)** · otros: 0.
>
> La prioridad de análisis pasa de LA REJA a **A3TEK / C011750 / C007834**,
> y el foco económico del vencido comercial pasa del flujo de entrega a la
> **autorización FULL** (SAP_DIRECT, usuarios jirahola/cvallejos/ybravo).
> El perfil de riesgo restante es de **vencido joven** (70.7% en 1–15 días;
> sin aging >90 días).

---

*Evidencia completa en `validation/credit_risk_ex_la_reja/evidence/`.*
*Sus scripts: `exclude_la_reja.py`, `economic_recalc.py` (universe+aging),
`customer_ranking.py`, `collection_kpi.py`, `hana_smoke.py`,
`test_credit_risk_ex_la_reja.py`.*
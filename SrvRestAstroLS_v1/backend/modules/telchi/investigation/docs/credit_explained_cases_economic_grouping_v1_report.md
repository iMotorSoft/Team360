# TELCHI — CREDIT EXPLAINED CASES ECONOMIC GROUPING V1

**Fecha:** 2026-09-02 (continuación del gate `TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS`)
**Objetivo:** transformar las 268 ventas explicadas en una lectura económica
(por mecanismo × monto × período × cobranza × clientes × usuarios).
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Rating del monto:** **BS (Bolivianos)** — `DocCur='BS'` verificado en HANA para
las 268 y para todo el universo de la ventana (moneda única, suma directa válida).
Los reportes previos de este ciclo escribían `$` como notación plana sobre los
mismos importes BS; aquí se normaliza a `Bs`.
**Runtime HANA:** `insiding_hana` (READ ONLY). Escrituras SAP/HANA: **0**
(`SAP_WRITE_COUNT=0`, `READ_ONLY_PASS`).

```text
TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS
```

Gates base preservados (no reabiertos): `TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS`,
`TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS`,
`TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS`,
`TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS`.

Degradaciones que siguen aplicando (heredadas del gate de clasificación):

```text
TN_SOURCE_INSPECTION=PARTIAL
MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP
DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED
HISTORICAL_AUTHORIZATION=UNAVAILABLE        (Excel vigente, no evidencia histórica)
CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE      (sin historial del flag VENCREVENC)
```

---

## A. RESULTADO

Las **268 ventas explicadas** se agruparon en 5 grupos de negocio (uno y sólo uno
por DocEntry, sin doble conteo), con monto, período, cobranza y saldo abierto.

```text
268 ventas explicadas
Monto total (bruto): Bs 318,051.61
Cobrado (pagos):     Bs  63,686.61   (20.0%)
Ajustado por NC:     Bs   1,392.00
Abierto hoy:         Bs 252,973.00   (79.5%)
Período:             2026-01-12 → 2026-09-01

Por mecanismo:

  Usuario FULL (autorización)        40 ventas   Bs 189,700.50   Bs 180,396.95 abiertos
  Flujo previo (entrega/pedido)     155 ventas   Bs  86,449.73   Bs  71,282.55 abiertos
    · Entrega previa (DlnLimit=N)   140 ventas   Bs  72,784.72   Bs  71,282.55 abiertos
    · Pedido previo sin vencidos     15 ventas   Bs  13,665.01   Bs       0.00
  Contado Retail One                 58 ventas   Bs  38,569.56   Bs       0.00
  Cliente exceptuado (VENCREVENC)    12 ventas   Bs   1,293.50   Bs   1,293.50 abiertos
  Integración / ajuste                3 ventas   Bs   2,038.32   Bs       0.00
```

## B. UNIVERSO — 268 EXPLICADAS

- Fuente: cruce con las 287 del gate congelado (`phase78_sale_credit_state.json`)
  ∩ `classified_cases.json` de la reconstrucción exacta, excluyendo las 19
  `UNRESOLVED` (microventas Retail One sin liquidación en SAP, DocEntry preservado).
- **268 = 287 − 19**; todas presentes con reason_code idéntico al congelado.
- Distribución por mecanismo técnico (secundario): `DELIVERY_PREVIOUS` 140 ·
  `PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK` 58 · `SAP_FULL_AUTHORIZATION` 40 ·
  `ORDER_PREVIOUS` 15 · `CUSTOMER_EXCEPTION_FLAG` 12 · `TECHNICAL_INTEGRATION_PATH`
  2 · `CREDIT_NOTE_OR_RECONCILIATION` 1 · **suma = 268**.

## C. MONTO TOTAL Y PERÍODO

| Concepto | Valor (Bs) |
| --- | ---: |
| Bruto (ventas) | 318,051.61 |
| Pagos (cobranza efectiva) | 63,686.61 |
| Ajustado por nota de crédito | 1,392.00 |
| **Saldo abierto hoy** | **252,973.00** |

Período global: **2026-01-12 → 2026-09-01**. Concentración mensual marcada en
agosto (168 ventas, Bs 215,711.90 = 67.8% del monto) y julio (38 ventas,
Bs 42,186.10); ver §L.

## D. GRUPOS DE NEGOCIO

| Grupo | Ventas | Clientes | Usuarios | Vendedores | Monto (Bs) | Cobrado | Abierto | Período | % monto | % abierto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Usuario FULL | 40 | 14 | 8 | 11 | 189,700.50 | 9,303.55 | 180,396.95 | 01-20 → 09-01 | 59.6% | 71.3% |
| Cliente con excepción | 12 | 1 | 1 | 7 | 1,293.50 | 0.00 | 1,293.50 | 08-30 → 09-01 | 0.4% | 0.5% |
| Flujo previo (entrega/pedido) | 155 | 37 | 8 | 23 | 86,449.73 | 15,167.18 | 71,282.55 | 02-01 → 09-01 | 27.2% | 28.2% |
| Contado Retail One | 58 | 20 | 3 | 24 | 38,569.56 | 38,569.56 | 0.00 | 01-12 → 08-31 | 12.1% | 0% |
| Integración / ajuste | 3 | 2 | 2 | 2 | 2,038.32 | 646.32 | 0.00 | 01-20 → 07-17 | 0.6% | 0% |
| **Total** | **268** | — | — | — | **318,051.61** | **63,686.61** | **252,973.00** | — | 100% | 100% |

Cada DocEntry pertenece a exactamente un grupo (invariante `NO_DOUBLE_COUNT`).
Monto reconciliado: suma por grupo = suma atómica de las 268.

## E. USER FULL (GRUPO A) — 40 VENTAS, Bs 189,700.50

Hallazgo dominante: **el 59.6% del monto y el 71.3% del saldo abierto** de las 268
concentrado en 40 ventas autorizadas por 8 usuarios con permiso FULL de desviación
de línea de crédito. Concentrado en **SAP Direct** (37 ventas, Bs 187,989; solo 3
ventas Retail por Bs 1,712).

| Usuario | Ventas | Clientes | Monto (Bs) | Cobrado | Abierto | Primera | Última |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| lzarraga (LUIS ZARRAGA) | 10 | 5 | 77,640.33 | 203.25 | 77,437.08 | 2026-07-07 | 2026-09-01 |
| yardaya (YERSON ARDAYA DELGADO) | 4 | 3 | 39,280.34 | 0.00 | 39,280.34 | 2026-08-11 | 2026-08-31 |
| cvallejos (Carlos Andres Vallejos M.) | 8 | 3 | 33,106.35 | 0.00 | 33,106.35 | 2026-07-30 | 2026-08-26 |
| jirahola (Alejandra Irahola) | 10 | 2 | 21,604.11 | 8,352.00 | 13,252.11 | 2026-01-20 | 2026-08-27 |
| kfranco (KALY NAOMI FRANCO CASSIA) | 3 | 2 | 14,240.06 | 0.00 | 14,240.06 | 2026-08-20 | 2026-08-28 |
| eroman (ENRIQUE ROMAN) | 1 | 1 | 2,000.00 | 0.00 | 2,000.00 | 2026-08-31 | 2026-08-31 |
| soluone *(técnico Retail, atribución POS)* | 3 | 2 | 1,711.70 | 748.30 | 963.40 | 2026-08-04 | 2026-09-01 |
| mtolaba (MARIA LAURA TOLABA ELIAS) *(bloqueado en Excel)* | 1 | 1 | 117.61 | 0.00 | 117.61 | 2026-08-11 | 2026-08-11 |

Distinción de autorización (donde es demostrable):
- `FULL_BY_GROUP`: 7 usuarios (todos con `CONFIRM_CREDIT_LINE_DEVIATION`/`...`
  autorización total en el Excel vigente, grupos Ventas/Administración/Facturación).
- `FULL_BY_TECHNICAL`: `soluone` (POS Retail One; atribución aguas arriba al
  operador de caja: pos 808 = Yessica Justiniano Vargas, pos 655 = Claudia
  Fabiola Santander Torrez, y un caso sin match previo).
- No hay ningún caso atribuido a superusuario vía `FULL_BY_SUPERUSER`
  (HISTORICAL_AUTHORIZATION=UNAVAILABLE; la clasificación se conserva según su
  confidence STRONG previa).
- Nota de gobernanza: `mtolaba` figura "bloqueado: Sí" en el Excel vigente pero
  ejecutó 1 venta FULL (Bs 117.61, C010521) el 2026-08-11 (bloqueo de Excel ≠
  bloqueo de OUSR en HANA, `user_locked='N'`).

## F. CUSTOMER EXCEPTION (GRUPO B) — 12 VENTAS, Bs 1,293.50

- Las 12 corresponden a **un solo cliente con flag**: `C000398` **PEDIDOSYA
  SERVICIOS S.A.** (`U_SO1_01VENCREVENC='Y'`, CreditLine Bs 50,000). Todas por
  canal Retail One, ejecutadas por el usuario técnico `soluone`, ventas recientes
  (2026-08-30 → 2026-09-01). Las 12 siguen **abiertas** (Bs 1,293.50).
- Revalidación del prompt "¿incluir C011358?": `C011358` YANGO mantiene el flag
  `U_SO1_01VENCREVENC='Y'` en el maestro (OCRD), pero **no tiene ventas dentro de
  la ventana 2026** (0 casos; 0 ventas de las 268). Por lo tanto en este corte el
  único cliente exceptuado con ventas explicadas es **C000398**.
- Operadores POS que atendieron las 12 ventas (atribución upstream): Rosmery
  Pinto (457), Julia Elena Sesary (760), Maria Fernanda Noe Paz (810),
  Cubre Libre 2AN (858), Karen Jhoana Arnez Medrano (983); 2 de 12 sin match VENTA.
- `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE`: no se afirma que el flag estuviera
  activo en fechas históricas; se preserva la evidencia exacta del flag actual.

## G. DOCUMENT FLOW (GRUPO C) — 155 VENTAS, Bs 86,449.73

Separación interna:

| Subtipo | Ventas | Clientes | Monto (Bs) | Cobrado | Abierto |
| --- | ---: | ---: | ---: | ---: | ---: |
| Entrega previa (`DELIVERY_FLOW_EXPLAINS_TIMING`) | 140 | 36 | 72,784.72 | 1,502.17 | 71,282.55 |
| Pedido previo sin vencidos (`ORDER_AUTHORIZED_BEFORE_OVERDUE`) | 15 | 1 | 13,665.01 | 13,665.01 | 0.00 |

- **Entrega previa = 140 ventas (Bs 72,784.72 = 22.9% del monto total; 28.2% del
  abierto).** Es el *segundo* mecanismo por riesgo económico, tras Usuario FULL.
  Mirar impacto económico del hallazgo en §L/§16: `OADM.DlnLimit='N'` + `ACB_TN_ODLN`
  no referencia crédito en el grafo → el circuito Entrega→Factura no consulta
  control. Cliente dominante: **C010341 LA REJA (40 ventas, Bs 47,258.99, todo
  abierto, CreditLine Bs 100,000)**, seguido de clientes personales `E0xxxx`
  (menachos, pinto rosmery, rosas...) por montos pequeños.
- **Pedido previo = 15 ventas (Bs 13,665.01), todas cobradas (0 abierto)**,
  todas de **C010009 GRAL CHACOS** por canal DMS (OrderLimit='Y' aprobó el pedido
  limpio; la factura es continuación). Sin riesgo abierto.
- Cadena reconstruida DELIVERY→INVOICE / ORDER→DELIVERY→INVOICE sin fanout.

## H. RETAIL ONE CASH (GRUPO D) — 58 VENTAS, Bs 38,569.56

- 58 ventas de contado Retail One (`U_SO1_CREDITO='N'`, POS) cubiertas el mismo
  día / mismo cierre (no son extensión de crédito). **100% cobradas; 0 abierto.**
- Cliente dominante: **C000018 "CODIGO GENERICO DELIVERY"** (24 ventas,
  Bs 33,668.41, todas pagadas) — código genérico de caja, no un cliente de crédito.
- 20 clientes, 24 vendedores, ejecutadas vía `soluone` (35) / `ybravo` (20) /
  `jheredia` (3). Operadores POS atribuidos vía `@SO1_01VENTA.U_SO1_USUARIO→OHEM`.
- Verificado de nuevo `U_SO1_CREDITO='N'` (semántica POS contado); sin mezcla con
  ventas realmente a crédito.

## I. TECHNICAL / RECONCILIATION (GRUPO E) — 3 VENTAS, Bs 2,038.32

Preservadas individualmente (no agregadas para no perder explicación):

| DocEntry | Cliente | Monto (Bs) | Subtipo | Estado |
| --- | --- | ---: | --- | --- |
| 11400003 | C004698 | 166.32 | `TECHNICAL_INTEGRATION_PATH` (DMS, eroman) | pagada |
| 11400009 | C004698 | 480.00 | `TECHNICAL_INTEGRATION_PATH` (DMS, eroman) | pagada |
| 11038855 | C005919 | 1,392.00 | `CREDIT_NOTE_OR_RECONCILIATION` (jirahola) | liquidada por NC |

## J. COBRANZA POR GRUPO

| Grupo | Pagadas | Parciales | Abiertas | % ops cobradas | % monto cobrado | % (pagos+NC) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Usuario FULL | 8 | 0 | 32 | 20.0% | 4.9% | 5.1% |
| Cliente excepción | 0 | 0 | 12 | 0% | 0% | 0% |
| Flujo previo | 37 | 0 | 118 | 23.9% | 17.5% | 19.2% |
| Contado Retail One | 58 | 0 | 0 | 100% | 100% | 100% |
| Integración/ajuste | 3 | 0 | 0 | 100% | 31.7% | 100% |
| **Total** | **106** | **0** | **162** | **39.6%** | **20.0%** | **20.4%** |

- **% operaciones cobradas (39.6%) ≠ % monto cobrado (20.0%):** el monto cobrado es
  inferior porque las ventas grandes (Usuario FULL) están aún abiertas.
- Tiempo hasta cobro (solo 106 pagadas; muestras pequeñas, distribución sesgada —
  no se usa solo el promedio): mediana 0 días (88 cobradas el mismo día, POS),
  p75=0, p90=3; máximo 92 días. Para Usuario FULL: n=8, mediana 41, p75=61, p90=71.
  Limitación: no se dispone de la granularidad por pago parcial en la evidencia
  guardada; `days_to_first_any` es la métrica disponible (suficiente para POS 1:1).

## K. SALDO ABIERTO

- **Total abierto: Bs 252,973.00** (79.5% del bruto). Concentrado en
  **Usuario FULL (Bs 180,396.95 = 71.3%)** y **Entrega previa (Bs 71,282.55 =
  28.2%)**. Juntos representan el 99.5% del riesgo abierto.
- Respuesta a la pregunta ejecutiva clave: **el mecanismo que concentra hoy el
  mayor riesgo económico abierto es la autorización Usuario FULL**, seguido del
  flujo de entrega con `DlnLimit=N`. Cliente exceptuado y contado Retail One
  aportan exposición mínima (0.5% y 0%).
- Aging del abierto (antigüedad desde la venta, corte 2026-09-02):

| Bucket | Monto abierto (Bs) | Casos | Clientes |
| --- | ---: | ---: | ---: |
| 0-30 d | 188,863.37 | 105 | 38 |
| 31-60 d | 14,520.22 | 15 | 7 |
| 61-90 d | 17,253.95 | 6 | 4 |
| 91-180 d | 27,503.67 | 30 | 2 |
| 180+ | 4,831.79 | 6 | 1 |

(El grueso del abierto es reciente, 0-30d, coherente con la concentración en
julio-agosto; 91-180d se concentra en pocos clientes grandes.)

## L. EVOLUCIÓN MENSUAL (TIMELINE)

Totales (268):

| Mes | Ventas | Monto (Bs) | Cobrado | Abierto |
| --- | ---: | ---: | ---: | ---: |
| 2026-01 | 3 | 2,823.43 | 1,431.43 | 0.00 |
| 2026-02 | 8 | 6,237.45 | 1,522.00 | 4,715.45 |
| 2026-03 | 14 | 4,095.44 | 1,471.50 | 2,623.94 |
| 2026-04 | 6 | 4,834.17 | 1,740.00 | 3,094.17 |
| 2026-05 | 13 | 16,148.75 | 2,784.00 | 13,364.75 |
| 2026-06 | 11 | 19,116.40 | 135.30 | 18,981.10 |
| 2026-07 | 38 | 42,186.10 | 20,855.88 | 21,330.22 |
| 2026-08 | 168 | 215,711.90 | 32,998.20 | 182,713.70 |
| 2026-09 | 7 | 6,897.97 | 748.30 | 6,149.67 |
| **Total** | **268** | **318,051.61** | **63,686.61** | **252,973.00** |

Lectura: la serie **crece** de forma pronunciada hacia **julio-agosto** (combinación
de SAP FULL directo y entregas de clientes grandes), no es estable y se concentra
en meses específicos (ago tiene 62.7% de las ventas y 67.8% del monto). La serie
mensual por grupo está en `evidence/monthly_series.json` (`USER_AUTHORIZATION_FULL`
y `DOCUMENT_FLOW_PREAUTHORIZED` concentran el grueso de agosto; `NON_CREDIT_RETAIL_CASH`
está repartido y se cobra al día).

## M. CLIENTES PRINCIPALES

Top por monto (totales de cliente sobre las 268; ver `concentration.json`):

| Cliente | Mecanismo(s) | Ventas | Monto (Bs) | Abierto (Bs) |
| --- | --- | ---: | ---: | ---: |
| C003450 (Clínica Alemana) | FULL + Entrega | 10 | 80,438.28 | 80,438.28 |
| C010341 LA REJA | Entrega previa | 40 | 47,258.99 | 47,258.99 |
| C000018 Código Genérico Delivery | Contado R1 | 24 | 33,668.41 | 0.00 |
| C003542 | FULL | 5 | 30,026.11 | 30,026.11 |
| C005919 A3TEK | FULL + 1 NC | 10 | 21,534.51 | 11,790.51 |
| C003531 | FULL | 3 | 17,343.02 | 17,343.02 |
| C011750 | FULL | 7 | 15,591.34 | 15,591.34 |
| C010009 GRAL CHACOS | Pedido previo (DMS) | 15 | 13,665.01 | 0.00 |
| C000398 PEDIDOSYA | Cliente excepción | 12 | 1,293.50 | 1,293.50 |

(Detalle top-10 por monto, abierto y casos en `evidence/concentration.json`.)

## N. USUARIOS / VENDEDORES PRINCIPALES

- Usuarios (SAP) por grupo en §E (Usuario FULL) y §I. Ejecutores técnicos
  (`soluone`, `dms`) separados de personas: `soluone`=POS Retail, `dms`=integración,
  con atribución upstream (operador OHEM / vendedor de ruta OSLP).
- Vendedores (OHEM/OSLP, no confundir con usuario): 42 vendedores únicos referenciados
  en las 268. `C010009`/C010341 y DMS se asocian a rutas `Cubre Libre-*` y vendedores
  de ruta (p.ej. Julia Eguez Costa slp 3). Detalle en `evidence/concentration.json`.
- Concentración por grupo: Usuario FULL en SAP Direct (37/40), Cliente excepción en
  Retail One (12/12), Contado Retail One en sucursales S2A/SRC (S17, R10, R07...).

## O. CANALES

| Grupo | Retail One (n/amt/abierto) | DMS (n/amt/abierto) | SAP Direct (n/amt/abierto) |
| --- | --- | --- | --- |
| Usuario FULL | 3 / 1,712 / 963 | 0 | **37 / 187,989 / 179,434** |
| Cliente excepción | **12 / 1,294 / 1,294** | 0 | 0 |
| Flujo previo | 130 / 65,975 / 64,473 | 15 / 13,665 / 0 | 10 / 6,810 / 6,810 |
| Contado Retail One | **58 / 38,570 / 0** | 0 | 0 |
| Integración/ajuste | 0 | 2 / 646 / 0 | 1 / 1,392 / 0 |
| **Total** | **203 / 107,550 / 66,730** | **17 / 14,311 / 0** | **48 / 196,191 / 186,243** |

Confirmado con datos: **FULL concentrado en SAP Direct; excepción y contado en
Retail One**; DMS sin saldo abierto (pedido previo/NC, todo pagado).

## P. EXPOSICIÓN DE CRÉDITO EN LA VENTA (USER FULL + EXCEPCIÓN)

| Grupo | Vencido en la venta (Bs) | Exposición previa (Bs) | Sobre límite previo | Abierto hoy (Bs) |
| --- | ---: | ---: | ---: | ---: |
| Usuario FULL | 596,396.53 | 1,270,420.54 | 6 | 180,396.95 |
| Cliente excepción | 469.56 | 137,267.40 | 0 | 1,293.50 |

Top exposición en Usuario FULL (detalle en `credit_exposure.json`):
- C003450 2026-08-28 DocEntry 11496068: venta Bs 68,931.67, vencido previo
  Bs 113,180.37, exposición previa Bs 147,503 (CreditLine Bs 185,000), abierto igual.
- C003450 2026-08-28 DocEntry 11495278: sobre límite previo (exposición 214,259 >
  CL 185,000), venta Bs 2,175.55.
- C000071 2026-08-31: vencido previo Bs 45,853.90 (moroso >6m), venta Bs 2,000.00.
- C010341 (no FULL): vencido previo relevante por entrega.

Severidad: sin umbral explícito de negocio documentado → **no se inventan
thresholds**; la lectura es analítica (por monto/abierto/vencido), no política Telchi.

## Q. LIMITACIONES

1. `HISTORICAL_AUTHORIZATION=UNAVAILABLE` — la autorización FULL proviene del Excel
   vigente; no se convierte en evidencia histórica absoluta. La clasificación
   cerrada se preserva con su confidence STRONG previa.
2. `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE` — no existe historial del flag
   VENCREVENC; no se afirmó que el flag estuviera activo históricamente. Revalidado:
   C011358 YANGO tiene flag pero 0 ventas en la ventana (no es "cliente exceptuado"
   con ventas explicadas en este corte).
3. `DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED` — las 15 ventas de C010009 se ejecutan
   con el usuario técnico `dms`; el operador humano no se resuelve; se usa
   vendedor de ruta (OSLP) cuando está disponible.
4. `soluone` (POS Retail): las ventas se atribuyen al operador de caja
   (`@SO1_01VENTA`→OHEM) donde hay match; 12 ventas (excepción, 10/12 match) y
   3 FULL (2/3 match). En el grupo Usuario FULL se cuenta `soluone` como usuario
   técnico separado de las personas.
5. Tiempo hasta cobro: no hay granularidad por pago parcial en la evidencia
   guardada; `days_to_first_any` es la métrica disponible (§J).
6. Aging del abierto por días desde la venta (métrica conservada del gate previo),
   no por días de vencido vencido.
7. No se reabrió la semántica de las 287; si una reconciliación económica
   detectara una inconsistencia concreta se revisaría de forma dirigida (ninguna
   detectada en este ciclo).

## R. TESTS / REGRESSION / READ-ONLY / MONEDA

- **Nuevos LOOP TEST (46-60): 26 PASS** — `validation/credit_exception_economic/
  test_economic_grouping.py`: cardinalidad 268/268 únicas; no doble conteo;
  reconciliación de monto (grupos=atómico; paid+credited+open≈total); período y
  fecha por grupo; reconciliación mensual; USER FULL preservado (40/40);
  CUSTOMER EXCEPTION preservado (12/12); estados de pago (106/0/162); moneda BS;
  mapeo grupo/secundario con fixtures; atribución FULL y desglose NC; freeze de
  gates previos (287 intactas; 19 UNRESOLVED excluidas sin pérdida).
- **Regresión**: credit-exception (35) + credit-control (26) + users/authorization
  (52) + económicos (26) = **139 PASS**.
- **HANA smoke real** (LOOP TEST §50): 3 USER FULL + 3 CUSTOMER EXCEPTION +
  3 DELIVERY + 3 RETAIL CASH = 12 DocEntry verificados contra HANA
  (monto, fecha, cliente, estado de pago, DocCur='BS', base delivery/pedido,
  VENTA retail) — **12/12 verificados** (`hana_smoke_economic.json`).
- **Moneda**: `DocCur='BS'` para las 268 y para todo el universo de la ventana
  (probe HANA GROUP BY) → suma directa válida, sin conversión.
- **READ ONLY**: `SAP_WRITE_COUNT=0`, `READ_ONLY_PASS`
  (`readonly_audit_economic.json` — scan estático del ciclo completo).

## S. FINAL GATE

```text
TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS
```

Checklist (§56):

| # | Requisito | Estado |
| --- | --- | ---: |
| 1 | 268/268 agrupadas una sola vez | ✅ (268 = 268 únicas, NO_DOUBLE_COUNT) |
| 2 | Montos reconciliados | ✅ (grupos = atómico; paid+credited+open ≈ total, Δ<0.05) |
| 3 | Período identificado | ✅ (2026-01-12 → 2026-09-01) |
| 4 | Monthly reconciliation | ✅ (suma mensual = 268 y = total monto) |
| 5 | USER FULL detallado | ✅ (40; por usuario/cliente/monto/abierto) |
| 6 | CUSTOMER EXCEPTION detallado | ✅ (12; C000398; flag UNAVAILABLE history) |
| 7 | Payment/open reconciliado | ✅ (106/0/162; 20.0% monto cobrado) |
| 8 | Clientes y usuarios principales | ✅ (C003450, C010341, C000398...; §M/N) |
| 9 | No double counting | ✅ |
| 10 | Currency semantics | ✅ (BS única, HANA verificada) |
| 11 | Regression PASS | ✅ 139 PASS |
| 12 | SAP_WRITE_COUNT=0 | ✅ |

**Siguiente paso recomendado**: (a) validar con Telchi la lectura del riesgo abierto
de Usuario FULL (Bs 180k) y del flujo de entrega `DlnLimit=N` (Bs 71k); (b) la
semántica de `U_SO1_01VENCREVENC` y del find C000398/C011358; (c) ventana con cuenta
con EXECUTE para leer la definición del TN y cerrar `TN_SOURCE_INSPECTION=EXACT`;
(d) granularidad de pagos parciales si se desea medir días-a-cobro completo.

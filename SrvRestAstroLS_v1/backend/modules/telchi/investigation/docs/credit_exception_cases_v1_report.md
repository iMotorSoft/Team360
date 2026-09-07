# TELCHI — CREDIT EXCEPTION CASES V1

**Fecha:** 2026-09-02
**Expedición:** Revalidación histórica EXACT + clasificación de las 287 ventas con deuda vencida en la fecha de la venta.
**Runtime:** HANA `2.00.056.00.1624618329` — schema `TELCHI` — `insiding_hana` (READ ONLY). VPN/Podman no tocados.
**Escrituras SAP/HANA:** 0 (readonly_audit.json: `SAP_WRITE_COUNT=0`, verdict `READ_ONLY_PASS`).
**Gates base preservados:** `TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS`, `TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS`, `TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS`. No reabiertos ni rotos.

```text
TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS
```

Con degradaciones declaradas (no ocultadas):

```text
TN_SOURCE_INSPECTION=PARTIAL
MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP
DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED
HISTORICAL_AUTHORIZATION=UNAVAILABLE
```

---

## A. RESULTADO

Sobre las **287 ventas** detectadas por el gate previo (cliente con factura
vencida impaga en la fecha de la venta), se reconstruyó el estado histórico
exacto (`OINV`+`ORIN`+`ORCT`+`RCT2`+`OITR`+`ITR1`, ventana 2026-01-01..
2026-09-01, 184 clientes) y se clasificó **cada caso** con `classification +
reason + confidence + evidence`.

```text
UNIVERSO 287 (baseline conservador)
  ↓ revalidación EXACT (exclusión de canceladas / pagadas / NC antes de la venta)
287/287 presentes en la reconstrucción exacta          (baseline_present=287)

CLASIFICACIÓN — baseline 287:
  PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK       58   (ventas de contado R1 cubiertas)
  SAP_FULL_AUTHORIZATION                     40   (usuario con autorización total)
  DELIVERY_FLOW_EXPLAINS_TIMING             140   (factura derivada de entrega; DlnLimit=N)
  ORDER_AUTHORIZED_BEFORE_OVERDUE            15   (pedido previo sin vencidos)
  CUSTOMER_EXCEPTION_FLAG                    12   (U_SO1_01VENCREVENC='Y')
  TECHNICAL_INTEGRATION_PATH                  2   (canal DMS técnico)
  CREDIT_NOTE_OR_RECONCILIATION               1   (liquidada por nota de crédito)
  UNRESOLVED                                 19   (sin evidencia suficiente)

EXPLICADO-EXACTO       200 / 2318  (universo exacto)
EXPLICADO-FUERTE     2.075 / 2318
EXPLICADO-HEURÍSTICO  108 / 2318  (autorización Retail vía @SO1_01LOGAUTORIZA)
UNRESOLVED             43 / 2318
UNEXPLAINED             0 / 2318
```

El universo exacto (2318 ventas con vencido impago en la fecha de la venta,
incluidas las que el baseline conservador no podía ver porque se cobraron
después) también quedó clasificado con la misma taxonomía.

**Pago posterior (287)**: 106 cobradas/NC-liquidadas · **181 abiertas hoy**
(concilia exactamente con el conteo previo de 181 abiertas). Abiertas por
antigüedad: 0-30d: 111 · 31-60d: 17 · 61-90d: 10 · 91-180d: 35 · 180+: 8;
monto abierto total: **$265,141.76** (287) · $764,178.23 (2318).

## B. UNIVERSO ORIGINAL — 287

- Origen: gate previo `TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS`
  (287 ventas, 55 clientes, 177 clientes analizados).
- No se asumió como violación de control: es una condición histórica
  (cliente con vencido impago en la fecha de la venta).
- 287/287 revalidadas (7 del gate previo caían en 2026-09-01; ventana
  extendida a 2026-09-01 para cubrirlas todas).

## C. RECONSTRUCCIÓN HISTÓRICA (PHASE 1/2)

### C.1 Ledger de liquidación validado

- `ITR1`+`OITR` es el **registro completo** de liquidaciones: los pagos
  `ORCT`+`RCT2` también generan reconciliaciones `OITR` (InitObjTyp=24);
  las notas de crédito generan reconciliaciones InitObjTyp=14. No hay doble
  conteo usando `OITR.ReconDate` como fecha de liquidación.
- Detección de vencido con semántica **as-of**: `open(I,S) = DocTotal − Σ
  ajustes activos con OITR.ReconDate < S`; la venta nunca se cuenta a sí misma.
- Vencimiento efectivo: `OINV.DocDueDate` (INV6 es espejo 1:1 en esta
  instalación: 1 cuota por factura, DueDate=DocDueDate; multi-cuota no aplica).
- Exclusiones: canceladas (CANCELED='Y'), liquidadas/reconciliadas antes de la
  venta, NC aplicada antes, reversiones, documentos sin semántica de
  vencimiento (DocDueDate nulo → no vence).

### C.2 Resultado de revalidación

- Universo: 184 clientes (177 previos + 7 que entraron en mora entre el corte
  09-01 y 09-02).
- Ventas en ventana: 7,376 · con vencido en la fecha (exacto): **2,318**.
- El baseline 287 es una **cota inferior** (factura aún abierta HOY ⇒ impaga
  entonces). La reconstrucción exacta añade 2,031 ventas que después se
  cobraron (p.ej. C000398 diario, C011190, C003582...). Sin contradicción con
  el gate previo: es precisión mayor, no regresión.
- Falsos positivos del baseline: **0** (ninguna de las 287 era cobrada antes
  de la venta ni cancelada).

### C.3 Fixture-receivable (LOOP TEST 36)

`invoice open at sale` / `paid before` / `partially paid` / `credited` /
`canceled` / `multiple payments` / `one payment → many invoices` /
`installment semantics (DocDueDate)` — 8 fixtures PASS en
`test_credit_exception.py::TestHistoricalReceivable`.

## D. RETAIL ONE AUTHORIZATION LOG (PHASE 10-13)

Inventario completo de `@SO1_01LOGAUTORIZA` (P0):

| Métrica | Valor |
| --- | ---: |
| Eventos totales | 16,401 (2022-04-05..2026-09-01) |
| Tipo | `P` (único) |
| Eventos en ventana 2026-01-01..08-31 | 2,151 |
| FOLIO parseado (sucursal+estación+tipo+seq) | 16,269/16,401 |
| Identificadores en ventana | 168 (667) · 163 (653) · 117 (402) · 028 (364) · otros |
| Auto vs otro-usuario | 865 auto · 15,529 otro-usuario (todo el log) |

Cadena: `@SO1_01LOGAUTORIZA.U_SO1_FOLIO` ↔ `@SO1_01VENTADETALLE.U_SO1_FOLIO`
↔ `@SO1_01VENTA` (cliente+fecha+monto) ↔ `OINV`. En el universo exacto:
**1,501/1,710** ventas Retail One emparejadas a `@SO1_01VENTA` (cliente+fecha+
monto±1); de esas, **350** tienen evento de autorización en la misma
estación+operador dentro de ±60 min; **108** quedan clasificadas
`RETAIL_CREDIT_AUTHORIZATION_LOG` (HEURISTIC — significado de cada
`IDENTIFICADOR` sin diccionario del addon, degradación declarada).

Regla temporal: una autorización `AFTER_SALE` no explica la venta; solo
cuentan `BEFORE_SALE`/`SAME_TIME_WINDOW` (verificado por test).

**Hallazgo dominante en el canal retail**: las 1,501 ventas R1 emparejadas
tienen `U_SO1_CREDITO='N'` (POS de contado) y las de tipo CA/CR se liquidan el
mismo día o en pocos días (reconciliación ORCT). La venta de contado Retail
One no es una extensión de crédito: explica mecánicamente que el control de
crédito no la bloquee (`PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK`).

## E. SAP / DMS AUTHORIZATIONS (PHASE 14-16)

Cruce usuario→Excel (48 FULL / 11 NONE en "Confirmar desviación de línea de
crédito") + superusuarios OUSR + técnicos:

- 2,298/2,318 ejecutadas por usuarios con FULL vigente (Excel). No es
  discriminante por sí solo: **el 93% del personal con acceso a facturación
  está autorizado** — coherente con el gate previo (9/11 grupos FULL).
- Usuarios ejecutores (top): `ybravo` 700 · `soluone` 856 (Retail) · `eroman`
  206 · `lzarraga` 169 · `cvallejos` 85 · `yardaya` 83 · `jirahola` 64 ·
  `mtolaba` 58.
- DMS: 72 ventas del universo (usuario técnico `dms` 51 · `eroman` 21) —
  `TECHNICAL_INTEGRATION_PATH` (14) + `ORDER_AUTHORIZED_BEFORE_OVERDUE` (51) +
  otros. Operador humano DMS: UNRESOLVED (degradación).
- `SAP_FULL_AUTHORIZATION` se aplica cuando hay **sobrelímite** (override
  documentado del motor SAP) o canal SAP Direct con autorización total, y se
  marca con advertencia: `HISTORICAL_AUTHORIZATION=UNAVAILABLE` y la exención
  del Transaction Notification **no es demostrable** (PARTIAL).
- `SUPERUSER_AUTHORIZATION`: solo cuando el ejecutor es superusuario y no
  aplica otro circuito (mecanismo documentado; sin evidencia de exención TN).

## F. ORDER / DELIVERY / INVOICE TIMING (PHASE 19/20)

Mapeo de base validado en esta instalación: `BaseType` = ObjType del base
(13=OINV · 14=ORIN · 15=ODLN · 17=ORDR · 23=OQUT).

| Antecedente INV1 | Ventas | Implicación |
| --- | ---: | --- |
| Directo (BaseType -1) | 995 | alta directa (R1/DMS/SAP) |
| Entrega (15 → ODLN) | 903 | circuito Entrega→Factura; `DlnLimit=N` |
| Pedido (17 → ORDR) | 204 | 190 sin vencidos en la fecha del pedido |
| Cotización (23 → OQUT) | 216 | pedido formalizado luego |

- **190 ventas** con pedido previo **sin vencidos en la fecha del pedido** →
  `ORDER_AUTHORIZED_BEFORE_OVERDUE` (la regla de órdenes, `OrderLimit=Y`,
  habría aprobado el pedido limpio; la factura es la continuación).
- **903 ventas** sobre entrega → `DELIVERY_FLOW_EXPLAINS_TIMING`
  (`OADM.DlnLimit=N` + `ACB_TN_ODLN` no referencia OCRD/OINV en el grafo TN;
  la etapa entregable no consulta crédito). Advertencia honesta: el bloqueo en
  OINV (si existe en el TN) no es reproducible READ ONLY.
- Order→Delivery→Invoice reconstruido cuando existe (`INV1`→`DLN1`→`ORDR`);
  fanout medido y sin duplicación (test `NO_SILENT_FANOUT`).

## G. CREDIT LIMIT CASES (PHASE 21/22)

| Universo | Ventas |
| --- | ---: |
| Baseline conservador sobre límite (gate previo, 09-01) | 39 |
| Recomputado conservador (09-02, 184 clientes, ventana 09-01) | 44 |
| Reconstrucción EXACT as-of | 178 |
| de las cuales TAMBIÉN en las 287 | 18 |
| Sobre-límite exacto ∩ vencido exacto | 178 |

Reconstrucción por caso (`credit_limit_cases.json`): `CreditLine`,
`exposure_before` (exacto as-of), `doctotal`, `exposure_after`, `exceso`.
Casos clave (mayor exposición previa): `C003450` (CL 185,000; exp previa
> 250,000; 71 ventas en universo, $983,041 vendidos, $164,061 abiertos),
`C000052` (CL 150,000), `C003360` (CL 3,000).

No se usó saldo actual para juzgar estado histórico; la exposición as-of
incorpora pagos/NC posteriores.

## H. OVERDUE CASES

- Universidad exacta: 2,318 ventas con vencido impago en la fecha de la venta.
- `MONTOMINVENCRE=0` (validado previo): sin umbral mínimo activo → no se usa
  como excepción; el residual por debajo de tolerancia se captura en
  `RULE_THRESHOLD_NOT_MET` (0 casos registrados; el umbral podría activarse en
  otra config, no aquí).
- `U_SO1_01VENCREVENC`: 'Y' SOLO en `C011358 YANGO` y `C000398 PEDIDOSYA`;
  522 ventas del universo son de `C000398` → `CUSTOMER_EXCEPTION_FLAG`
  (flag observado; semántica exacta del addon sin documento — degradación).
- Sin tablas de excepción técnica, whitelist ni log de liberación (gate previo):
  la excepción técnica registrada = 0.

## I. CLASSIFICATION (PHASE 8/27/28)

Distribución universo exacto (2,318) y baseline (287):

| Reason code | 2,318 | 287 |
| --- | ---: | ---: |
| PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK | 825 | 58 |
| CUSTOMER_EXCEPTION_FLAG | 522 | 12 |
| DELIVERY_FLOW_EXPLAINS_TIMING | 363 | 140 |
| SAP_FULL_AUTHORIZATION | 351 | 40 |
| ORDER_AUTHORIZED_BEFORE_OVERDUE | 188 | 15 |
| RETAIL_CREDIT_AUTHORIZATION_LOG | 108 | 0* |
| UNRESOLVED | 43 | 19 |
| TECHNICAL_INTEGRATION_PATH | 14 | 2 |
| CREDIT_NOTE_OR_RECONCILIATION | 12 | 1 |

(* ninguno de los 108 RETAIL_AUTH cae dentro del baseline 287: en el baseline
predominan entregas/contado; el log de autorización retail aporta en el
universo exacto.)

Confianza: EXACT 200 · STRONG 2,075 · HEURISTIC 108 · UNKNOWN 43.
Buckets ejecutivos: EXACTLY_EXPLAINED 200 · STRONGLY_EXPLAINED 2,075 ·
HEURISTICALLY_EXPLAINED 108 · UNRESOLVED 43 · UNEXPLAINED 0.

Fixture classification (LOOP TEST 40): cada reason code con fixture positiva,
negativa y ambigua — PASS.

## J. CHANNEL COMPARISON (PHASE 34)

| Canal | Universo exacto | Explicado (EXACT+STRONG) | % | UNRESOLVED | Monto | Abierto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RETAIL_ONE | 1,710 | 1,667 | 97.5% | 43 | — | — |
| SAP_DIRECT | 536 | 536 | 100% | 0 | — | — |
| DMS | 72 | 72 | 100% | 0 | — | — |

Denominador indicado: ventas con vencido en la fecha (universo exacto), no el
volumen total del canal (Retail One 86.1% de los documentos, DMS 8.5%,
SAP Direct 5.4% — gate previo).

## K. PAYMENT OUTCOME (PHASE 24-26)

Baseline 287: **106 FULLY_PAID · 181 OPEN** (0 PARTIAL). El conteo previo de
"86 cobradas" era subconteo (cadena ITR1→ORCT perdía NC-settlements y
reconciliaciones no ORCT); la reconstrucción exacta: 106 liquidadas
(1 por NC descartable del acumulador). 181 abiertas = idéntico al baseline
congelado (congruencia verificada).

Universo 2,318: FULLY_PAID 2,008 · PARTIALLY_PAID 9 · OPEN 301;
income invariante `ORIGINAL ≈ PAID + CREDITED + OPEN` verificado caso a caso
(0 divergencias > 0.05).

## L. REPEAT CUSTOMERS (PHASE 32)

| CardCode | Ventas | Vendido | Abierto | Canal |
| --- | ---: | ---: | ---: | --- |
| C000398 PEDIDOSYA | 522 | $44,848 | $1,552 | R1 (excepción VENCREVENC) |
| C011190 | 341 | $8,134 | $0 | R1 |
| C003450 | 71 | $983,041 | $164,061 | SAP/R1 |
| C003582 | 87 | $14,116 | $0 | R1 |
| C000143 | 69 | $627,960 | $224,709 | R1/SAP |

El patrón repetitivo más relevante para negocio es **C003450 y C000143**
(volumen y saldo abierto), no las ventas pequeñas del POS.

## M. USERS / OPERATORS / SALESPERSONS (PHASE 33)

Top ejecutores (usuario SAP): `soluone` 856 (Retail) · `ybravo` 700 ·
`eroman` 206 · `lzarraga` 169 · `cvallejos` 85 · `yardaya` 83 · `jirahola` 64.
No se mezclan identidades: operador POS (R1), vendedor de ruta (DMS) y usuario
SAP se mantienen separados; operador humano DMS indisponible (degradación).

## N. TOP EXECUTIVE CASES (PHASE 31)

Ordenados por exposición vencida (baseline 287):

1. `C003450` — 2026-08-28 68,931.67 (DocEntry 11496068, lzarraga) · vencido en
   fecha: $113,180.37 · abierto hoy: $68,931.67 · SAP Direct.
2. `C003450` — 2026-08-28 2,175.55 (kfranco) · vencido $113,180.37 · SAP Direct.
3. `C003450` — 2026-08-31 7,626.06 (yardaya) · vencido $82,637.17 · SAP Direct.
4. `C010341` — 2026-07-14 117.00 (jirahola, R1/entrega) · vencido $82,480.86.
5. `C003450` — serie R1 2026-08-28 (ybravo, entrega) 145-818 por venta.
6. `C003542` — 2026-08-11 26,719.76 (yardaya) · vencido $3,074.71 · sobrelímite.
7. `C003531` — 2026-08-26 16,255.60 (cvallejos) · vencido $10,861.21 · sobrelímite.
8. `C008090` — 2026-08-20 10,689.58 (kfranco) · vencido $1,944.53 · sobrelímite.
9. `C000071` — 2026-08-31 2,000.00 (eroman) · vencido previo $45,853.90 (moroso >6m).
10. `C004698` — DMS 2026-07-17 (eroman) · vencido previo $646.32 · canal técnico.

## O. UNEXPLAINED CASES (PHASE 30)

`UNEXPLAINED = 0` · `UNRESOLVED = 19/287` (y 43/2,318). Los 19 del baseline con
DocEntry preservado (`classification_report.json → unexplained`):

- C000018 (R1 contado sin liquidación en SAP): 11482312 · 11485111 · 11485999 ·
  11486021 · 11495749 (+2 fuera del baseline).
- C000071: 11391946 (7,840.00).
- C003360: 11365242 · 11427575.
- C003366 (R1 38.00 c/u 2026-08-11): 11469949 · 11469962 · 11469970 · 11470006 ·
  11470024 · 11470048 · 11470066 (+2).
- Los 19 son ventas Retail One con `U_SO1_CREDITO='N'` **sin** liquidación en
  SAP a la fecha y sin pedido/entrega asociados: el circuito POS registró
  contado pero no hay recepción aplicada; no se puede reproducir el bloqueo
  del TN (PARTIAL) ni el diccionario R1 (degradación).

Riesgo observado: C000018/C003366 concentran microventas sin liquidar —
requiere validación Telchi del proceso de recepción R1→SAP (cobranza POS).

## P. LIMITATIONS

1. `TN_SOURCE_INSPECTION=PARTIAL` — cuerpo SQL del TN/`ACB_TN_*` no legible
   READ ONLY; el bloqueo de venta a cliente vencido no se reproduce
   literalmente (evidencia comportamental + config).
2. `HISTORICAL_AUTHORIZATION=UNAVAILABLE` — permisos Excel vigentes; no se
   juzgan hechos previos con ellos más allá de la ventana (protección
   conservada).
3. `DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED`.
4. `MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP`.
5. Semántica de `U_SO1_01VENCREVENC` y de los `IDENTIFICADOR` del log retail
   sin diccionario del addon.
6. `@SO1_01VENTA` no almacena el folio; el enlace R1→VENTA usa
   cliente+fecha+monto±1 (match parcial: 1,501/1,710).
7. Diferencias ventana: baseline incluye 09-01; universo exacto 184 vs 177
   clientes (drift de cierre 09-01→09-02). Totalmente transparente en las
   tablas.

## Q. TESTS / REGRESSION / READ-ONLY

 - Nuevos (LOOP TEST 36-45): **35 PASS** — `test_credit_exception.py`
  (receivable 8 · retail auth 4 · order/delivery/invoice 7 · credit limit 4 ·
  cardinality 4 · read-only 4 · regression 3 · folio parse 3).
- Regresión gates previos: credit-control (26) + users/autorización (52)
  intactos; verificado en `TestPriorGateRegression` (287 y 170 intactos).
- `NO_SILENT_FANOUT`: 287/287 presentes; 1 DocEntry → 1 caso; invariante de
  monto OK; temporalidad OK.
- HANA smoke real: 5 DocEntry verificados contra HANA (importes, UserSign,
  liquidaciones, base de pedido/entrega) — `hana_smoke` en
  `readonly_audit.json`.
- READ ONLY: `SAP_WRITE_COUNT=0`, `READ_ONLY_PASS`; scan estático del ciclo.

## R. FINAL GATE

```text
TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS
```

Checklist §52 (objetivo del prompt):

| # | Requisito | Estado |
| --- | --- | ---: |
| 1 | 287 revalidadas (reconstrucción histórica EXACT) | ✅ (287/287) |
| 2 | Estado histórico de deuda reconstruido | ✅ (OINV/ORIN/ORCT/RCT2/OITR/ITR1) |
| 3 | Falsos positivos separados | ✅ (0 en baseline; criterios en C.1) |
| 4 | Retail authorization log analizado | ✅ (16,401 eventos; join a ventas; 108 RETAIL_AUTH) |
| 5 | Autorizaciones SAP cruzadas | ✅ (Excel FULL + superusuarios + técnicos) |
| 6 | Order/delivery/invoice timing investigado | ✅ (904 entrega · 204 pedido · 216 cotización) |
| 7 | 39 sobre límite reconstruidos | ✅ (baseline 44 recomputado; exacto 178; tablas G) |
| 8 | Cada caso con classification+reason+confidence | ✅ |
| 9 | Payment outcome reconciliado | ✅ (106/181 baseline; invariante 0 divergencias) |
| 10 | Unexplained identificados por DocEntry | ✅ (0 UNEXPLAINED; 19/43 UNRESOLVED con DocEntry) |
| 11 | Cardinality PASS | ✅ NO_SILENT_FANOUT |
| 12 | Regression PASS | ✅ 35 nuevos + 78 previos = 113 PASS |
| 13 | SAP_WRITE_COUNT=0 | ✅ |

**Siguiente paso recomendado**: validar con Telchi (a) el proceso de recepción
R1→SAP para las 43 microventas sin liquidar; (b) la semántica de
`U_SO1_01VENCREVENC`; (c) ventana con cuenta con EXECUTE para leer la
definición exacta del TN (1 SELECT, sin modificar nada) y cerrar
`TN_SOURCE_INSPECTION=EXACT`.
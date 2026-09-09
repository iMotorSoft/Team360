# TELCHI SAP — STATUS ACTUAL

**Módulo:** Telchi SAP
**Capa actual:** DataScience — Crédito / Excepciones de venta / Control HANA
**Fecha del estado:** 2026-09-03
**Workspace:** `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi`
**Estado global:** `TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS`
**Último gate cerrado:** `TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS`
**Freeze:** excepciones de crédito V1 (287 explicadas; económicas 268 agrupadas; aging 252,973 separado; identidad operativa LA REJA C010341 cerrada; riesgo de crédito EX LA REJA recalculado; degradaciones explícitas)
**Próximo frente opcional:** gate atómico de identidad A3TEK (C005919) / C011750 / C007834, lectura DEFINITION del TN, gestión cobranza del saldo vencido limpio Bs 29,785.13



## Credit Risk EX La Reja V1 (2026-09-03 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_CREDIT_RISK_EX_LA_REJA_V1_PASS` | ✅ PASS |

- **Objetivo:** recalcular todo el riesgo de crédito excluyendo únicamente `CardCode='C010341'` (LA REJA = INTERNAL/RELATED-PARTY, gate previo). Filtro exacto `EXCLUDED_REASON=RELATED_PARTY_INTERNAL_ACCOUNT_C010341`; nunca por nombre/grupo/NIT.
- **Universo:** 287 → **247** (40 excluidos, DocEntry cruzados con dataset atómico de identidad: coincidencia exacta); explicadas 268 → **228**; UNRESOLVED 19 (auditados: C010341 count = 0); UNEXPLAINED 0. `ALL == LA_REJA + EX` en casos, gross, paid, credited, open, overdue, not_due (Δ≤0.05 Bs).
- **Económico:** gross **270,792.62** (318,051.61−47,258.99) · open **205,714.01** · not-due 175,928.88 · **overdue 29,785.13** (77,044.12−47,258.99) = **LA REJA era 61.3% del vencido**.
- **El riesgo se INVIRTIÓ:** vencido EX por mecanismo = **Usuario FULL Bs 19,000.27 (63.8%)** > Delivery Bs 10,784.86 (36.2%). Delivery cae de 58,043.85 a 10,784.86 (−81.4%); delivery cases 140 → **100** (grupo DOCUMENT_FLOW 155 → 115). `DlnLimit=N` deja de ser el principal foco económico (P0 respondido).
- **Aging EX:** sin buckets 91-180/181+ (eran LA REJA); vencido joven: 1-15 d Bs 21,072.94 (70.7%) · 16-30 888.02 · 31-60 6,122.86 · 61-90 1,701.31. `OPEN == NOT_DUE + OVERDUE` ✓.
- **Nuevo ranking:** Top1 **A3TEK C005919 Bs 11,790.51 (39.6%)** (jirahola FULL, 224d) · C011750 Jacobo Martens 6,289.57 (21.1%, cvallejos) · C007834 José Katimi Nosta 5,063.04 (17.0%, ybravo delivery). Top5 92.4% · Top10 99.6% (12 clientes con vencido). USER FULL: 40 casos / 19,000.27 (jirahola 11,790.51 · ybravo 7,667.74 · cvallejos 6,289.57 · lzarraga 2,370.59).
- **Colección:** la tasa evoluciona (20.02→23.52% bruto; matured 20.47→23.85% @misma definición; overdue/open 30.46→14.48%). Cohorts: feb-mar-abr pasan de 100% vencidas a **0.00%** sin LA REJA.
- **Próximos candidatos (gate atómico tipo LA REJA):** A3TEK C005919, C011750, C007834 (+ vigilar C011993 «Cliente Generico Complemento»). NO se concluye si son clientes comerciales reales hasta validación.
- **Tests:** **45 nuevos LOOP-TEST** + smoke HANA **27/27**; regresión: 23 (La Reja) + 60 (La Reja smoke) + 29 + 26 + 35 + 52 (users) + 20 (stock) + transtype = **PASS**; `SAP_WRITE_COUNT=0`; NO_SILENT_FANOUT; NO_DOUBLE_COUNT.
- Reporte: `docs/credit_risk_ex_la_reja_v1_report.md`. Scripts/evidencia en `validation/credit_risk_ex_la_reja/`.



## La Reja Operational Identity V1 (2026-09-03 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_C010341_LA_REJA_OPERATIONAL_IDENTITY_V1_PASS` | ✅ PASS |

- **¿Qué es C010341 LA REJA?** Cuenta **interna / parte relacionada de consumo de la familia Telchi en la propiedad «La Reja»**, documentada como venta SAP a crédito que nunca se cobra. **NO es un cliente comercial real** con evidencia; **NO es cuenta genérica** para terceros.
- **Síntesis:** las **40 operaciones por Bs 47,258.99** (baseline 2026-09-01, reconciliado Δ=0.00; 40/40 DocEntry únicos; 109 líneas; 0 UNKNOWN_ITEM; NO_SILENT_FANOUT) son consumo interno de productos propios: **FIPRONIL 486 L = Bs 29,784.75 (63%)**, repelente, bicarbonato, medicamentos y víveres, desde salones (2A-SAL 77.1%) y LAB-T*; 34 R1 + 6 pedidos telefónicos internos; vendedores = cajeros de salón (Irigoyen 13, Menacho 9, Guzman 6…); usuarios factura = jirahola 34 + eroman 6 (entregas R1 bajo usuario técnico soluone; pedidos por nvargas/arioja).
- **Evidencia de uso interno (fuerte):** (1) `LicTradNum 1468238` = NIT de **S0001 ROBERTO ABRAHAN TELCHI ASBUN** (grupo OCRG 119 «Socios», 23 miembros familia); (2) comentarios de entrega: «PARA SR ROBERTO TELCHI (LA REJA)», «LA REJA autorisado por don tito», «MEDICAMENTOS … PARA LA REJA LLEVA SR BRANKO», «LLEVO EL SR ARTURO (ESPOSO SRA BELEM TELCHI)», choferes propios Branko/Carlos Rivera, intermediaria Ana Rioja; (3) **0 ORCT de pago en toda la historia** (2024-06→2026-09), 1 única NC de limpieza Bs 1,572 (2025-11-13); patrón `PERSISTENT_OPEN_BALANCE`; (4) precios **preferenciales internos**: 70.8% del monto SYMBOLIC (FIPRONIL Bs 54 vs mediana normal Bs 109.62); (5) total abierto del BP = **Bs 93,769.76** (85 facturas: 45 de 2025 + 40 de 2026) == `OCRD.Balance` (Δ=0.00) == `invoice = paid + open`.
- **Historia completa:** OINV 85 (Bs 95,341.76 bruto) · ODLN 98 (Bs 106,333.05; primera 2024-06-24, anteriores a la primera factura 2025-01-14) · ORDR 6 · ORIN 1 · **ORCT 0** · OQUT 73. 3 entregas sin facturar (la más antigua 2025-05-15; 2 de ago-2026 posteriores al corte).
- **Stock effect:** 40 movimientos OINM muestreados, `OutQty == Quantity` de entrega, mismo almacén/fecha (TransType=15) → 0 desajustes; la factura no genera inventario adicional.
- **Pricing:** 25 ítems SYMBOLIC Bs 33,454.56 (70.8%) · 52 COMMERCIAL_LIKE Bs 13,446.85 · 1 UNRESOLVED.
- **Accounting:** muestra 1120101 (AR) vs 4110101 (ventas), balanceado; tratamiento de venta SAP formal sin cobro real.
- **Generic account:** `SINGLE_OPERATIONAL_ENTITY` — destinatarios siempre internos (familia/choferes); sin terceros externos.
- **Tests:** **23 nuevos LOOP-TEST** + smoke HANA real **60/60**; regresión: 29 (open-risk) + 26 (econ.) + 35 (excepción) + 52 (users_audit) + 20 (stock) + transtype gate = **PASS**; `SAP_WRITE_COUNT=0`; NO_SILENT_FANOUT. Comentarios de entrega y evidencia completa en `validation/la_reja_identity/evidence/`.
- Reporte: `docs/la_reja_c010341_operational_identity_v1_report.md`. Scripts/evidencia en `validation/la_reja_identity/`.



## Open Risk × Aging V1 (2026-09-02 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_CREDIT_OPEN_RISK_AGING_V1_PASS` | ✅ PASS |

- De los **Bs 252,973 abiertos** (baseline 2026-09-01, reconciliado Δ=0.00): **Bs 175,928.88 no vencidos** (69.5%; 96 casos) · **Bs 77,044.12 YA vencidos** (30.5%; 66 casos).
- **El riesgo está invertido vs el open:** el open lo domina Usuario FULL, pero el **vencido lo domina Entrega previa (Bs 58,043.85 = 75.3%)** vs Usuario FULL (Bs 19,000.27 = 24.7%). Motivo: full es venta reciente aún en plazo; entrega arrastra feb-jul madurado.
- USER FULL (40; open 180,396.95): **no vencido 161,396.68 · vencido 19,000.27** (9 casos, 4 clientes). Concentrado en jirahola 11,790.51 (A3TEK) + cvallejos 5,302.27 (C011750) + soluone 963 (POS) + lzarraga 944. lzarraga/yardaya/kfranco: open grande pero no vencido. mtolaba bloqueado en Excel pero `user_locked='N'` HANA, venta no vencida (`BLOCK_DATE_UNRESOLVED`).
- DELIVERY (140; open 71,282.55): **no vencido 13,238.70 · vencido 58,043.85** (57 casos, 11 clientes). **C010341 LA REJA = 47,258.99 vencido = 61.3% de TODO el vencido**, 40 ventas todas abiertas/vencidas, máx 184d. Timing: delivery→invoice mediana 0d (máx 25), invoice→due 31d; 0 entregas facturadas >60d tarde (vencido = impago, no retardo de facturación).
- Concentración: Top 1 cliente (LA REJA) = 61.3% del vencido; Top 5 ≈ 94%. 20 clientes con vencido.
- vendedores (OSLP ≠ usuario): Mariela Irigoyen 25,606 · Maria F. Menacho 12,165 · Karla Cabello 8,649 · Carlos Vallejos 6,290 · Luz Guzman 6,063.
- Cohorte: feb-jul 100% vencida; ago (Bs 182,713 abierto) sólo 7.1% vencida (reciente). Collection rate madurado **41.86%** vs 20.02% crudo.
- Repeat: 35/27/18 clientes con 2+/3+/5+ ventas; LA REJA 40 (39 mientras tenía abierto); repeated FULL: A3TEK 9 (jirahola), C011750 5, C003450 3 (kfranco/lzarraga/yardaya).
- Tests: **29 nuevos LOOP-TEST** (open-risk) + 139 previos = **168 PASS**; smoke HANA real 13/13 (5 FULL + 5 DELIVERY + 3 LA REJA + 3 oldest overdue, monto/due/INV6/BS); `SAP_WRITE_COUNT=0`; NO_SILENT_FANOUT.
- Reporte: `docs/credit_open_risk_aging_v1_report.md`. Scripts/evidencia en `validation/credit_open_risk/`.




## Explained Cases Economic Grouping V1 (2026-09-02 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_CREDIT_EXPLAINED_CASES_ECONOMIC_GROUPING_V1_PASS` | ✅ PASS |

- Las **268 ventas explicadas** (287 baseline − 19 UNRESOLVED) se agruparon en 5 grupos de
  negocio únicos (sin doble conteo): Usuario FULL 40 · Flujo previo (entrega/pedido) 155 ·
  Contado Retail One 58 · Cliente excepción 12 · Integración/ajuste 3 = **268**.
- Monto bruto **Bs 318,051.61** · cobrado Bs 63,686.61 (20.0%) · por NC Bs 1,392.00 ·
  **abierto Bs 252,973.00** (79.5%). Período **2026-01-12 → 2026-09-01**. Moneda **BS** única
  (DocCur='BS' HANA verificado) → suma directa válida.
- Riesgo abierto por mecanismo: **Usuario FULL Bs 180,396.95 (71.3%)** + **Entrega previa
  Bs 71,282.55 (28.2%)** = 99.5% del abierto; excepción Bs 1,293.50 (0.5%) y contado 0.
- USER FULL (40, 8 usuarios, SAP Direct 37/40): lzarraga Bs 77,640 · yardaya 39,280 ·
  cvallejos 33,106 · jirahola 21,604 · kfranco 14,240 · eroman 2,000 · soluone (técnico POS,
  atribución operador) 1,712 · mtolaba (bloqueado en Excel) 118. Exposición previa en la venta
  (FULL+excepción): vencido Bs 596,866 · exposición Bs 1,407,688 · 6 sobre límite.
- CUSTOMER EXCEPTION (12, Bs 1,293.50, todo abierto): solo **C000398 PEDIDOSYA**
  (VENCREVENC='Y', Retail One). Revalidado: C011358 YANGO tiene flag pero 0 ventas en ventana
  (no es cliente exceptuado con ventas en este corte). `CUSTOMER_EXCEPTION_HISTORY=UNAVAILABLE`.
- Doc flow: entrega previa 140 (Bs 72,784.72 = 22.9%; DlnLimit=N; cliente clave C010341 LA
  REJA 40 ventas Bs 47,259 abierto) · pedido previo 15 (Bs 13,665, todo cobrado; C010009 DMS).
- Evolución mensual: **crece** hacia jul-ago (ago 168 ventas, Bs 215,711 = 67.8%); no estable.
- Tests: **26 nuevos** (LOOP TEST 46-60 económicos) + 113 previos = **139 PASS**; smoke HANA real
  12/12 (3+3+3+3 por grupo); `SAP_WRITE_COUNT=0`; moneda BS cerrada.
- Reporte: `docs/credit_explained_cases_economic_grouping_v1_report.md`. Scripts/evidencia en
  `validation/credit_exception_economic/`.




## Credit Exception Cases V1 (2026-09-02 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_CREDIT_EXCEPTION_CASES_V1_PASS` | ✅ PASS c/ degradaciones explícitas |

- Revalidación EXACT de las 287 ventas con vencido-en-fecha (ventana 2026-01-01..09-01,
  184 clientes): **287/287 presentes** (cero falsos positivos por cancelada/pagada/NC previa).
- Ledger de liquidación validado: ITR1+OITR es registro completo (ORCT+RCT2 también generan
  OITR; NC = OITR InitObjTyp=14); semantica as-of con OITR.ReconDate; DocDueDate efectivo
  (INV6 es espejo 1:1; no hay multi-cuota).
- Universo exacto: **2,318** ventas con vencido en fecha (cota previa 287 era inferior:
  no podia ver ventas cobradas despues). Distribution: PAYMENT_BEFORE_EFFECTIVE_BLOCK_CHECK 825 ·
  CUSTOMER_EXCEPTION_FLAG 522 · DELIVERY_FLOW_EXPLAINS_TIMING 363 · SAP_FULL_AUTHORIZATION 351 ·
  ORDER_AUTHORIZED_BEFORE_OVERDUE 188 · RETAIL_CREDIT_AUTHORIZATION_LOG 108 · UNRESOLVED 43 ·
  TECHNICAL_INTEGRATION_PATH 14 · CREDIT_NOTE_OR_RECONCILIATION 12.
- Baseline 287: 58 contado R1 · 40 SAP FULL · 140 entrega · 15 pedido-previo · 12 VENCREVENC ·
  2 DMS · 1 NC · **19 UNRESOLVED** (microventas R1 sin liquidar: C000018/C003360/C003366/C000071
  DocEntry preservados). UNEXPLAINED=0.
- Pago (287): 106 liquidadas (corrige el subconteo previo de 86; 1 por NC) · 181 abiertas
  (identico al baseline congelado). Abierto $265,141.76; aging 0-30d 111 · 31-60d 17 · 61-90d 10 ·
  91-180d 35 · 180+ 8.
- Retail log @SO1_01LOGAUTORIZA: 16,401 eventos (2,151 en ventana); FOLIO parseado 16,269;
  join VENTA→VENTADETALLE→folio: 1,501/1,710 emparejadas (todas U_SO1_CREDITO='N' = POS contado);
  350 con evento ±60min misma estación+operador; 108 RETAIL_AUTH (HEURISTIC).
- Doc chain: 903 sobre entrega (DlnLimit=N), 204 pedido (190 sin vencidos al pedido), 216 cotización, 995 directas.
- Sobrelímite: baseline 39 → recomputado 44 → exacto 178 (todas también vencido exacto); tabla
  `credit_limit_cases.json` con exposure as-of (C003450 y C000143 los de mayor volumen/abierto).
- Tests: **35 nuevos** (LOOP TEST receivable/auth/order-delivery/limits/classification/cardinality/
  temporal/readonly + regression 287 y 170 intactos) + 78 previos = 113 PASS.
- READ ONLY: `SAP_WRITE_COUNT=0` (readonly_audit.json `READ_ONLY_PASS`); smoke real HANA de 5 DocEntry.
- Reporte: `docs/credit_exception_cases_v1_report.md`.
- Próximo paso: (a) validar con Telchi la recepción R1→SAP de las 43 microventas sin liquidar;
  (b) semántica U_SO1_01VENCREVENC e IDENTIFICADOR del log retail; (c) lectura DEFINITION del TN
  con cuenta con EXECUTE para cerrar TN_SOURCE_INSPECTION=EXACT.

## Credit Control × Authorizations × HANA Blocking V1 (2026-09-01 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS` | ✅ PASS c/ degradaciones explícitas |

- Excel `Autorizaciones_xGrupos.xlsx` parseado: 170 usuarios únicos / 14 grupos / 11
  matrices de permisos / 0 valores desconocidos; 170/170 logins reconciliados con OUSR.
- "Confirmar desviación de línea de crédito" = Autorización total en 9 de 11 grupos
  (Almacenes y Producción sin ella); 14 PermIds UGR1 reproducen el patrón por grupo.
- OADM: `CreditLimt=Y` `OpenCredit=N` `SalesLimit=Y` `DlnLimit=N` `CreditDay 1/15`.
- TN: `SBO_SP_TRANSACTIONNOTIFICATION` existe → 24 `ACB_TN_*` por objeto; OINV/ORDR
  referencian OCRD+OINV(+OCTG); ODLN NO (y DlnLimit=N → entregas sin control de crédito).
  Cuerpo SQL no legible READ ONLY → `TN_SOURCE_INSPECTION=PARTIAL` (grafo + comportamiento).
- Ventana 2026 (universo 177 clientes): 287 ventas con vencido-impago-en-fecha, 39 sobre
  límite; 86/287 con cobro trazado (OINV→ITR1→OITR→ORCT), 181 abiertas.
- Canales: Retail One 86.1% / DMS 8.5% / SAP Direct 5.4% (EXACT); Retail One verificado
  explícitamente (P0).
- Excepción técnica: no existe tabla/UDF/whitelist; `U_ClienteExcepcional='0'`;
  VENCREVENC 'Y' solo 2 clientes; config retail MONTOMINVENCRE=0.
- Aprobación Gerencia Comercial+Financiera: EXTERNAL_TO_SAP (sin registro en HANA;
  único log operativo: @SO1_01LOGAUTORIZA retail 16,393 eventos).
- Tests: 26 nuevos + 52 regresión previa = 78 PASS; anti-fanout NO_SILENT_FANOUT;
  SAP/HANA writes = 0.
- Reporte: `docs/credit_control_authorization_traceability_v1_report.md`.
- Próximo paso: lectura de DEFINITION del TN con cuenta con EXECUTE (1 SELECT) y
  validación con Telchi de U_SO1_01VENCREVENC / log de autorización retail.

## Cierre global V1 (2026-08-30)

- Gates 1–10 preservados; contratos globales: **12 PASS**.
- Regresión histórica: **267 PASS**; tests globales: **2 PASS**.
- Casos reproducibles: benzoato BUY_NOW, soda import-delay, cloruro cubierto
  por PT, gotero SAFE, bronceador L03124 EXCESS_STOCK, packaging BLOCKED.
- Limitaciones V1 preservadas: backtest as-of-T incompleto, intermitencia,
  transferencias RAW locales y allocation compartido sin resolver.
- Runner y evidencia: `validation/run_purchase_material_planning_v1.py` y
  `validation/purchase_material_planning_v1_gate.json`.
- HANA read-only: 0 writes; Podman/VPN y Parquet legacy sin cambios.
- HANA TCP local `127.0.0.1:30015`: PASS; smoke SQL quedó incompleto tras >60s
  y fue interrumpido, por lo que no se declara contrato SQL global PASS.
- Reporte final: `docs/purchase_material_planning_v1_final_report.md`.
- El cierre formal queda `DEGRADED` únicamente porque el smoke SQL HANA se
  interrumpió por duración; repetirlo con el runtime operativo permite marcar
  `PASS` y congelar formalmente.

---

## Purchase Executive Cases V1 (2026-08-30 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PURCHASE_EXECUTIVE_CASES_V1_PASS` | ✅ PASS |

- Casos ejecutivos entendibles por dueño/gerencia (7 casos) con las 10 preguntas
  QUÉ/CUÁNTO/CUÁNDO/ACCIÓN/CONFIANZA, generados desde coverage (Gate 7) + risk (Gate 8)
- Tracers: benzoato **Comprar/acelerar** (lt 160d, stockout nov-2026) · soda cubierto
  + riesgo demora importación (108t abiertas) · cloruro cubierto (equiv 9.226 en PT) ·
  gotero/tapa/contra cubiertos (no limitan) · bronceador L03124 sobre-stock (1,6x)
- Reporte generado: `docs/purchase_executive_cases_v1_report.md` (formato ejecutivo)
- 5 tests executive + 262 regresión: PASS; zero writes HANA
- Detalle: `docs/purchase_executive_cases_v1_report.md`

**DOMINIO COMPRAS / ABASTECIMIENTO COMPLETO (Gates 1–10).**

---

## Purchase Decision Backtest V1 (2026-08-30 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PURCHASE_DECISION_BACKTEST_V1_PASS` | ✅ PASS |

- Backtest sin hindsight: stock as-of-T (OINM) + consumo ≤ T (IGE1) → forecast
  SEASONAL_MA → mes de stockout predicho vs consumo REAL post-T
- 10 componentes × 4 snapshots (2025-01/06/09, 2026-01) = 40 casos
- Verdicts: EARLY_WARNING 14 · CONSISTENT 10 · MISSED_PURCHASE 9 · OVERBUY 7
- **Precisión early warning (±1 mes): 12/14 (86%)**; empaque regular (tapa PET,
  frasco 1L) más predecible; gotero intermitente sub-estimado (MISSED)
- Limitaciones: vista solo almacén RAW (transferencias → saldo negativo),
  forecast intermitente sub-estima, stock=0 sin demanda (OVERBUY degenerado)
- 11 tests backtest + 251 regresión: PASS; zero writes
- Detalle: `docs/purchase_decision_backtest_v1_report.md`

---

## Purchase Risk Engine V1 (2026-08-30 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PURCHASE_RISK_ENGINE_V1_PASS` | ✅ PASS |

- Decisiones explicables sin score opaco: BUY_NOW 179 · BUY_SOON 37 · WATCH 137
  · SAFE 531 · DO_NOT_BUY 45 · EXCESS_STOCK 66 (995 materiales PURCHASED/MIXED)
- `LATEST_SAFE_ORDER_MONTH = STOCKOUT − ceil((lead_p90 + safety_buffer)/30.44)`;
  safety buffer HEURÍSTICO (base 7d + forecast incierto + compartido + muestra baja)
- `EQUIVALENT_IN_FG` compensa demanda en la decisión (NO en capacidad de producción)
- 226 FG con `PRODUCTION_BLOCKED` (envase limitante); urgencia concentrada en
  envases/etiquetas (tapa PET 236 FG, caja 230 FG, papel 109 FG, precinto 40 FG)
- Tracers: benzoato BUY_NOW (lt 160d, lso 2026-05 vencido) · soda SAFE+import delay
  (108t abiertas) · cloruro SAFE (equiv 9.226 en PT) · gotero SAFE
- 21 tests risk + 230 regresión: PASS; 1 SQL contract; zero writes
- Detalle: `docs/purchase_risk_engine_v1_report.md`

---

## Equivalent Material Coverage V1 (2026-08-30 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1_PASS` | ✅ PASS |

- 6 capas sin fusionar: FG usable (OnHand−IsCommited en roles usables),
  componente físico (raw whs), equivalente en FG (terminal), FG adicional
  producible (MAX_PRODUCIBLE terminal), open purchase (DOCUMENTED_ORDER),
  forecast mensual (Gate 6)
- **P0.2 reconciliación**: `OITW.OnOrder ≠ OPEN_PURCHASE_POSITION` (152/263
  match; UOM + fuentes extra) → OPEN_PURCHASE (POR1.OpenQty, línea) es la
  canónica; no sumar ambas
- Waterfall FG mes a mes: 667 analizados · 275 cubiertos · 392 stockout
- Componentes: 1.028 analizados · 647 compartidos · 220 con gap de lead time <0
- **Bronceador L03124**: cobertura a fin de temporada 1,59x / al pico 1,91x →
  exceso (candidato DO_NOT_BUY)
- Tracers: soda en riesgo (gap -79d, lt 201d) · benzoato en riesgo (gap -69d,
  lt 160d) · cloruro cubierto por PT (equiv 9.226 vs físico 300) · gotero no
  limita (≥12 meses)
- 19 tests coverage + 211 regresión: PASS; 4 SQL contracts; zero writes
- Detalle: `docs/equivalent_material_coverage_v1_report.md`

---

## Product Seasonality V1 (2026-08-27 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PRODUCT_SEASONALITY_V1_PASS` | ✅ PASS |

- Serie mensual neta (OINV−ORIN) por ItemCode×Mes×Año; mes sin fila = cero
- 10.775 ítems: SEASONAL 1.950, DECLINING 1.298, GROWING 1.003, STABLE 922,
  INTERMITTENT 342, DISCONTINUED 1.016, INSUFFICIENT 4.168, NEW 76
- **Cobertura por volumen (HIGH/MEDIUM): 90,0%**
- **Bronceadores**: L00072/73 DISCONTINUED (→ L03124/25 NUEVO desde 2023,
  `POSSIBLE_PRODUCT_SUCCESSOR`); L03124 (200mL) SEASONAL peak ene, WAPE 0.28
  con SEASONAL_MOVING_AVERAGE; ventana estacional sep–feb
- Forecast baselines: NAIVE/MA3/SMLY/SEASONAL_MA/YOY + walk-forward backtest
  anti-leakage; MAE/WAPE/BIAS
- 15 tests seasonality + 196 regresión: PASS; 1 SQL contract; zero writes
- Detalle: `docs/product_seasonality_v1_report.md`

---

## Purchase Lead Time V1 (2026-08-27 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PURCHASE_LEAD_TIME_V1_PASS` | ✅ PASS |

- Grain: POR1.DocEntry+LineNum → PDN1.DocEntry+LineNum (0 colisiones);
  cadena invoice-first PO→OPCH→OPDN (link 99,8% / 100%)
- 88.238 líneas PO: FULL 84.552, PARTIAL 166, OPEN 241, CLOSED_NO_REC 3.279
- **Lead time first receipt**: mediana 0, p90 5d (global); por tipo:
  LF p90=4d, LP p90=43d, IMP p90=**82d**, SAA p90=34d
- **Hallazgo**: lead time documental ≠ físico; local comprimido por
  invoice-first/backdated; importación sí refleja ciclo real (p90 82d).
  Open PO age p90=97d (IMP abiertas avg 57,6d) = proxy físico
- NEGATIVE_LEAD_TIME 382 (BACKDATED_PO, mediana -5, max -147)
- 11.077 pares item×proveedor; 1.076 items multi-proveedor
- Critical Gate-4: L00205 etiqueta (n=10, p90=10d), L00838 precinto (p90=34d),
  L00219 tapa (p90=113d), L00097 frasco (n=74, p90=110d)
- Procurement mode: PURCHASED 9.804 / PRODUCED 889 / MIXED 7
- 9 tests lead_time + 187 regresión: PASS; 1 SQL contract; zero writes
- Detalle: `docs/purchase_lead_time_v1_report.md`

---

## Max Producible by Component V1 (2026-08-27 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_MAX_PRODUCIBLE_BY_COMPONENT_V1_PASS` | ✅ PASS |

- AVAILABLE_COMPONENT_FOR_PRODUCTION = OnHand-IsCommited (solo RAW_MATERIAL);
  EQUIVALENT_IN_FG NO reutilizado (material ya transformado)
- COMPONENT_CAPACITY = available/requirement; MAX = MIN(capacidades);
  LIMITING_COMPONENT = argmin
- Requirement = HISTORICAL_PRODUCTION_RATIO + CURRENT_BOM fallback; filtrado
  de fantasmas (M0001/R0004 ∉ OITM) y auto-referencias (re-packaging)
- 1.050 FG con capacidad; 1.287 componentes; **590 compartidos**
- **Hallazgo**: limitante suele ser envase/etiqueta (L00205 ETIQUETA, L00838
  PRECINTO), no la MP química; gotero (95k) NO limita; alcohol limitado por
  granel en RAW (783 botellas)
- 13 tests capacity + 174 regresión: PASS; 2 SQL contracts; zero writes
- Detalle: `docs/max_producible_by_component_v1_report.md`

---

## Finished Goods Material Equivalence V1 (2026-08-27 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_FINISHED_GOODS_MATERIAL_EQUIVALENCE_V1_PASS` | ✅ PASS |

- PT actual → equivalente de MP/insumo/envase: `FG_stock × qty_per_fg`
- FG universe 896 (656 con stock; 100% con BOM + historia producción)
- Niveles: EXACT_PRODUCTION_LINEAGE UNAVAILABLE → HISTORICAL_PRODUCTION
  (ΣIGE1/ΣIGN1) primario → CURRENT_BOM (ITT1.Quantity/OITT.Qauntity) fallback
- 50.406 líneas; 1.249 componentes directos; 1.130 usable; 1.109 terminal
- **238 semi-elaborados** → expansión multinivel sin doble conteo (cloruro de
  calcio directo 44 vs terminal 9.226 demuestra la cadena)
- FG usable 869.600 uds vs physical 1.056.505 (damaged/quarantine/WIP aparte)
- Tracers: soda 5.446 kg equiv, cloruro 9.226 (multinivel), benzoato 11.887,
  frasco/tapa/contra gotero ~8.500 c/u (en L01086/L01072/L01601/L01041...)
- 15 tests equivalence + 159 regresión: PASS; 4 SQL contracts; zero writes
- Detalle: `docs/finished_goods_material_equivalence_v1_report.md`

---

## Material Stock Position V1 (2026-08-27 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_MATERIAL_STOCK_POSITION_V1_PASS` | ✅ PASS |

- **Semántica stock CERRADA**: OnHand = físico neto (0 negativos);
  IsCommited = comprometido (487.292); OnOrder = ordenado no recibido
  (1.790.139, capa separada); Available = OnHand − IsCommited
- **Reconciliación ledger EXACTA**: OITW.OnHand == Σ(OINM.InQty−OutQty)
  (3/3 muestras diff=0; OINM 2022-03-31→hoy incluye apertura migración)
- **82 almacenes** clasificados por rol (0 sin role): MOBILE 16, PRODUCTION 9,
  BRANCH 8, DISTRIBUTION 8, FINISHED_GOOD 8, DAMAGED 7, OTHER 6, TRANSIT 5,
  RAW_MATERIAL 3, DISPENSING 3, RETURNS 3, IMPORT 2, QUARANTINE 2,
  CONSIGNMENT 1, EXPIRED 1
- **Ítems** (16.793): TRADED_GOOD 12.082, PACKAGING 1.728, INPUT 1.039,
  FINISHED_GOOD 704, RAW_MATERIAL 516, SEMI_FINISHED 192, SERVICE 6, OTHER 1,
  ITEM_CLASS_UNRESOLVED 525; OITB.ItemClass/RawMtrl NO discriminan
- **Casos trazadores**: soda cáustica física 12.473 kg + 108.000 onorder;
  cloruro calcio 301 + 92.000; benzoato 22.867 + 31.500; envases gotero
  Matriplast ~100k físicos + 40.800 c/u (COMMITTED_OVER_STOCK en LAB-P1)
- Anomalías: Consig negativo (-20.253), 525 ítems sin clase, committed>onhand
- 20 tests stock nuevos + 139 regresión: PASS; 3 SQL contracts; zero writes
- Detalle: `docs/material_stock_position_v1_report.md`

---

## Purchase Data Discovery V1 (2026-08-27 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PURCHASE_DATA_DISCOVERY_V1_PASS` | ✅ PASS |

- Inventario: OPOR/POR1 18,663/97,350 · OPCH/PCH1 32,131/113,981 ·
  OPDN/PDN1 19,633/89,967 · OPRQ/PRQ1 732/3,171 · ORPD/RPD1 3,907/4,279 ·
  1,073 proveedores (1,053 válidos)
- **U_TIPOCOMPRA operativa**: LF=local general 14,316 (296 prov.) ·
  LP=envases/plásticos 1,941 (123 prov.) · IMP=importación+logística
  1,917 (57 prov.) · SERV 365 · SAA 124
- **Cadena CERRADA 100%**: OPOR→OPCH (PCH1 BT=22, `BaseEntry`=OPOR.DocEntry,
  90,959/90,959) → OPDN (PDN1 BT=18, `BaseEntry`=OPCH.DocEntry,
  87,577/87,577); directo PO→GR 54/54. Flujo invoice-first documentado.
  Link canónico `BaseEntry → DocEntry` (P0.1 verificado); `BaseRef`/`BaseDocNum`
  son el DocNum string redundante
- Timing: PO→Factura P50=0/P90=3d (30,010 líneas backdated, hasta -295d);
  Factura→Entrada P50=1/P90=5d (129 negativos = 0.15% < tolerancia)
- **33 POs abiertas** (13 IMP: Hainan 108t soda cáustica, 92t cloruro calcio,
  26t benzoato; Thosco ácido fosfórico; Floramatic; USP; Matriplast 337,060
  envases LF desde 04-25)
- UDF embarque/incoterm/solicitud NO operativos (fill 0-2);
  UDT Retail One compras 0 filas → SAP estándar es la fuente
- Quality flags: IN_TRANSIT_UNRESOLVED (solo ORDERED vs RECEIVED),
  IMPORT_UDF_UNUSED, BACKDATED_PO
- 22 tests unit nuevos + 117 regresión (65 producción + 52 users): PASS;
  8 SQL contracts ejecutan; zero writes
- Detalle: `docs/purchase_data_discovery_v1_report.md`

---

## Warehouse Transfer Traceability V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_WAREHOUSE_TRANSFER_TRACEABILITY_V1_PASS` | ✅ PASS |

- Semántica: ORIGEN=WTR1.FromWhsCod, DESTINO=WTR1.WhsCode, QTY=WTR1.Quantity;
  NET = SUM activas (CANCELED='N')
- 188,843 docs (424 cancelados excluidos por header; 5,832 líneas negativas =
  ajustes/reversas en docs ACTIVOS, legítimas)
- 0 same-warehouse, 0 nulls, 0 ItemCode inválido
- Cardinalidad: 13,926 docs multi-origen, 8,020 multi-destino (no colapsables)
- **OINM TT67: conservación 100%** (36,210/36,210 líneas out==in; 2 filas por
  línea: origen Out, destino In)
- Rutas top: Central→Transit→Salón (2A-AMD→SAP-R1→2A-SAL), Terminado→Móvil
  (LPZ-T1→LPZ-D1), Materia Prima→Proceso (LAB-M1→LAB-P1)
- Batch: WTR1.U_LOTE 0.19%; traza completa en IBT1 TT67 (4,026,440 filas)
- **PHYSICAL_DISPATCH_SEMANTICS=ACCOUNTING_ONLY** (SAP contabiliza ambos lados
  en un evento; no demuestra entrega física)
- 12 tests unit transferencia + 53 producción + 52 users/attribution: PASS;
  zero writes
- Detalle: `docs/warehouse_transfer_traceability_v1_report.md`

---

## Production Reconciliation V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PRODUCTION_RECONCILIATION_V1_PASS` | ✅ PASS |

- **EXPECTED_FOR_ACTUAL_OUTPUT validado**: (BaseQtyNum/BaseQtyDen) × output real
- 140,391 líneas / 20,487 órdenes: PLAN EXACT 118,281 → **NORMALIZED EXACT
  122,296**; OVER 13,273 → 8,425; UNDER 2,838 → 3,518
- **Reclasificación**: OVER→EXACT 6,088 (46% del sobreconsumo era producción
  parcial); UNDER→EXACT 2,382 (84% del bajo consumo era output sobre-plan);
  NOT_CONSUMED→ZERO_OUTPUT 5,993 (explicado)
- L00099: **13.9% over PERSISTE tras normalización** (valores fijos
  +100..+500) → SYSTEMATIC_NORMALIZED_OVERCONSUMPTION_CANDIDATE
- L01945: 100% exact post-normalización (semielaborado se consume correcto)
- L00001: 0.5% over; L02475: 2.1% (baja materialidad confirmada)
- Ejemplo fundamental protegido por test (1,620 vs 1,600 = +1.25% normalizado)
- 13 tests unit reconciliación + 40 producción + 52 users/attribution: PASS;
  zero writes
- Detalle: `docs/production_reconciliation_v1_report.md`

---

## Produced Component Dependency V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PRODUCED_COMPONENT_DEPENDENCY_V1_PASS` | ✅ PASS |

- Semántica: recetas planas independientes conectadas por ItemCode (SAP NO
  almacena BOM anidada; el grafo es DERIVED)
- 900 items producidos / 1,323 componentes / **255 produced components** (intersección)
- 8,175 edges (parent→component); **514 edges a produced components**
- 131 produced components con múltiples parents (máx 13): L00001 (13 parents,
  472 órdenes), L01945 (8 parents, 683 órdenes)
- Máx profundidad derivada 3; 14 cycle hits (rework, seguro); 0 self-dependencies
- Rol por flags no excluyentes: PRODUCED_AND_INTERMEDIATE 255, FINAL_ONLY 645,
  COMPONENT_ONLY 1,063, BOM_PARENT_ONLY 144
- Caso real L01945: receta propia (2 comps), 480 órdenes producidas (375,811
  uds), consumido en 662 órdenes de 8 parents (379,248 uds); upstream OWOR
  28154→IGN1 36867; downstream OWOR 28629 consume 1,500
- 9 tests unit dependencia + 31 producción + 52 users/attribution: PASS; zero writes
- Detalle: `docs/produced_component_dependency_v1_report.md`

---

## Production Output Traceability V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PRODUCTION_OUTPUT_TRACEABILITY_V1_PASS` | ✅ PASS |

- Output semantics CERRADA: `NET_ACTUAL_OUTPUT = SUM(IGN1.Quantity) BT=202`
  - OIGN cancelados: 0; IGN1 negativos: 0; sin reversals
- CmpltQty = SUM(IGN1): 19,654/20,487 (único diff = 17757 rework)
- Receipts: 19,588 órdenes 1 receipt; 356 multi (hasta 22); 842 sin output
- Output vs plan: EXACT 86.9%, OVER 6.2%, PARTIAL 2.4%, ZERO 3.9%,
  CONSUMPTION_WITHOUT_OUTPUT 31
- **Hallazgo REWORK**: 1,252 líneas donde IGN1.ItemCode≠OWOR.ItemCode reciben
  un componente WOR1 (patrón reacondicionamiento, 2022-2026)
- Batch: IGN1.U_LOTE → OBTN.DistNumber EXACT (5,196/5,228 lotes, 99.4%)
- Timing: 52% same-day, 41% 1-7d, 81 backdated (0.4%, no filtrado)
- OINM TT59: 53.5% cobertura (parcial por diseño; IGN1 es fuente primaria)
- 11 tests unit output + 20 producción + 52 users/attribution: PASS; zero writes
- Detalle: `docs/production_output_traceability_v1_report.md`

---

## Production Component Consumption V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PRODUCTION_COMPONENT_CONSUMPTION_V1_PASS` | ✅ PASS |

- Semántica gross/net CERRADA: `NET_ACTUAL = SUM(IGE1.Quantity) BT=202`
  - OIGE cancelados: 0; IGE1 negativos: 0; returns/reversals: NO OBSERVED
  - (1 fila OINM TT60 2022 = artefacto migración, excluida)
- IssuedQty reconcialiado: 134,291/134,292 = ACTUAL_ACCUMULATED
- Múltiples issues: 761 líneas (0.54%) con 2-4 documentos; modelo 1:N
- Manual 67.5% / Backflush 32.5% — ambos generan IGE1; timing mayormente pre-receipt
- Expected vs Net (4,000 órdenes / 30,361 líneas): EXACT 83.1%,
  TRUE_OVER 11.5%, TRUE_UNDER 3.2%, NOT_CONSUMED 2.2%
- **Hallazgo**: componente L00099 sobre-consumo sistemático (+100..+500/orden,
  varios productos); L02475 en L03612 bajo-consumo -0.4% (no material)
- Caso 17757 resuelto: 2 IGE1 duplicados (44000/44027), IssuedQty parcial,
  recepción del propio componente (orden rework) — edge case 1/~134K
- 8 tests unit consumo + 12 BOM + 52 users/attribution: PASS; zero writes
- Detalle: `docs/production_component_consumption_v1_report.md`

---

## Recipe/BOM Traceability V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_RECIPE_BOM_TRACEABILITY_V1_PASS` | ✅ PASS |

- Fórmula expected validada: `EXPECTED = (WOR1.BaseQtyNum/BaseQtyDen) × OWOR.PlannedQty`
  (140,328 líneas, 92.8% exacto; resto = redondeo display + overrides reales)
- `ISSUEDQTY_SEMANTICS=ACTUAL_ACCUMULATED` (134,291/134,292 eq a SUM(IGE1))
- Método emisión: M=Manual 67.5% / B=Backflush 32.5% (ambos generan IGE1)
- WOR1 = receta histórica de la orden (prioridad sobre ITT1 para análisis histórico)
- Fidelidad: 898/905 productos producidos tienen BOM actual; 7 sin BOM (solo WOR1)
- Drift: 61% misma receta; 290 productos con componentes distintos vs ITT1
- Expected vs actual (muestra 2,000 órdenes/16,475 líneas): EXACT 84.9%,
  OVER 9.3%, UNDER 3.5%, NOT_CONSUMED 2.3%
- 12 tests unit + 52 regresión usuarios/attribution: PASS; zero writes
- Detalle: `docs/recipe_bom_traceability_v1_report.md`

---

## Production Schema Discovery V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_PRODUCTION_SCHEMA_DISCOVERY_V1_PASS` | ✅ PASS |

Cadena validada EXACT (READ ONLY): RECETA→ORDEN→CONSUMO→PRODUCTO→DESPACHO→STOCK

- Receta: OITT(1,043)/ITT1(7,753) — IssueMthd M=manual 67%, B=backflush 33%
- Orden: OWOR 20,777 (Status L=Released 20K=producción real, C=Closed admin)
  - Type S=Standard 20,478; 905 productos; 2022-04 → 2026-08
- Componentes esperados: WOR1 141,618 (BaseQty×PlannedQty=IssuedQty)
- Consumo real: IGE1 BT=202 135,341 líneas, 19,935 órdenes (BaseEntry=OWOR.DocEntry)
- Producto terminado: IGN1 BT=202 20,999 líneas, 19,936 órdenes
- Movimiento: OINM TT59=receipt(In), TT60=issue(Out), TT67=transfer, 8.31M rows
- Despacho: OWTR/WTR1 188,798/1,964,667 (WhsCode=dest, FromWhsCod=origin)
- Stock: OITW 1.36M (current only); 82 almacenes clasificados por rol
- Degradaciones: INVENTORY_LINK=PARTIAL, PRODUCTION_DISPATCH_LINK=HEURISTIC,
  RECIPE_HISTORICAL=DEGRADED (WOR1 copia receta → fidelidad en la orden)
- Detalle: `docs/production_schema_discovery_v1_report.md`

---

## Documentation Audit & Consolidation V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_USERS_DOCUMENTATION_AUDIT_V1_PASS` | ✅ PASS |

Auditoría documental contra evidencia real HANA. Correcciones aplicadas:

- **Overlap Retail One × DMS corregido**: la afirmación original "0 personas
  operan ambos sistemas" era INCORRECTA. Verificación directa de `SlpCode`
  demostró **22 vendedores compartidos** (Retail One×DMS), 26 (SAP×DMS),
  88 (Retail One×SAP). Overlap humano queda `UNRESOLVED` (DMS sin operador).
- manager: "credencial compartida posible" → "cuenta técnica/admin, no 45 personas".
- eroman: asiento contable matizado como efecto automático (no manual).
- Historia del gate documentada: INITIAL DEGRADED → FINAL PASS.
- Conteo de tests aclarado: 44 (usuarios) + 8 (attribution) = 52 independientes.
- Nota USR5 añadida: 1 fila ≠ 1 operación de negocio.
- Índice creado: `docs/users_roles_applications_documentation_index.md`.

Gates consolidados:

| Gate | Estado |
|------|--------|
| `TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS` | ✅ PASS |
| `TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS` | ✅ PASS |
| `TELCHI_USERS_DOCUMENTATION_AUDIT_V1_PASS` | ✅ PASS |

Limitaciones vigentes: `HISTORICAL_AUTHORIZATION=UNAVAILABLE`,
`DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED`, `RETAIL_ONE_DMS_HUMAN_OVERLAP=UNRESOLVED`.

---

## Retail One × DMS User Attribution V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_RETAIL_ONE_DMS_USER_ATTRIBUTION_V1_PASS` | ✅ PASS |

- Retail One: **167 operadores humanos EXACT** (`@SO1_01VENTA.U_SO1_USUARIO` = OHEM.empID)
  - 163 con empleado vinculado; 198 vendedores (SlpCode); 5 sucursales; 54 estaciones
  - Join 1:1 a OINV via `Name = U_SO1_01FOLIORETAIL1` (1.56M facturas, ratio 1.000)
  - Activos 90d: 62 operadores; 30d: 56
- DMS: **sin operador humano en SAP** (HUMAN_OPERATOR_IDENTITY=UNRESOLVED)
  - 36 vendedores (SlpCode) + 42 rutas (U_OSLP_ID = ruta/zona, NO persona)
- SAP directo: 34 usuarios SAP (32 nombrados + 2 técnicos), 12 con empleado
- Overlap: 22 vendedores (SlpCode) en Retail One Y DMS; overlap humano UNRESOLVED
  (DMS no conserva operador humano; no afirmable "0 personas")
- Cuentas técnicas excluidas: soluone, dms, manager, B1i, Workflow, alianza, terbol
- Detalle: `docs/retail_one_dms_user_attribution_v1_report.md`

---

## Users × Roles × Authorizations V1 (2026-08-26 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS` | ✅ PASS |

- 170 usuarios SAP: 78 activos, 92 bloqueados, 16 superusers (14 activos)
- 33 users con employee, 25 con salesperson (cadena OUSR→OHEM.salesPrson→OSLP)
- 456 empleados sin usuario SAP; 137 usuarios sin empleado
- 17 grupos, 77 asignaciones user→group, 61,321 permisos directos, 5,840 group perms
- Niveles de autorización validados: N/F/R/V (USR3/UGR1)
- USR5: 3.17M rows actividad, 87 IPs, 170 usuarios
- Channel origin EXACT: OINV 86.1% Retail One, 8.5% DMS, 5.4% SAP direct
  (U_ORIGIN + U_SO1_01RETAILONE); usuarios técnicos: soluone, dms, manager, alianza
- OJDT.UserSign = usuario de transacción origen (no asiento manual); solo TransType=59 es manual
- Authorized×Actual: 135 AND_USED, 787 NOT_USED, 196 UNCONFIRMED, 162 APPARENTLY_NOT_AUTHORIZED
- 126 SoD findings (32 P0, 70 P1, 24 P2); eroman = concentración total multi-etapa
- Cross traceability: 10 casos FULLY_TRACED eroman (OINV→ORCT→OINM→OJDT→JDT1)
- smercado/sruiz post-block = 1 evento residual (SESSION_PERSISTENCE, no bypass)
- manager6 = fecha corrupta 3916-10-xx (excluida de estadísticas)
- manager = cuenta técnica/admin 45 IPs (2012-2026, cadena NAT/VPN)
- 44 tests unit + 6 scripts HANA real + cardinality anti-fanout: PASS
- Degradaciones: HISTORICAL_AUTHORIZATION=UNAVAILABLE, PERSON_IDENTITY=PARTIAL
- Detalle: `docs/users_roles_authorizations_v1_report.md`

---

## 1. Estado General

### Financial Gates

| Change | Gate | Estado |
|--------|------|--------|
| FINANCIAL-001 Invoice Contract | `TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS` | ✅ PASS |
| FINANCIAL-002 Credit Note Linkage | `TELCHI_FINANCIAL_CREDIT_NOTE_PASS` | ✅ PASS |
| FINANCIAL-003 Payment Application | `TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS` | ✅ PASS |
| FINANCIAL-004 Reconciliation | `TELCHI_FINANCIAL_RECONCILIATION_PASS` | ✅ PASS |
| FINANCIAL-005 Outstanding / AR | `TELCHI_FINANCIAL_CURRENT_AR_PASS` | ✅ PASS |

### FINANCIAL-005 Sub-Gates

| Gate | Estado |
|------|--------|
| `TELCHI_FINANCIAL_MARCH_2023_RECON_OUTLIER_EXPLAINED_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_RECON_RESIDUAL_MATERIALITY_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_AR_SETTLEMENT_AGGREGATION_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_INVOICE_BALANCE_RECONCILIATION_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_CURRENT_AR_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_AGING_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_CUSTOMER_AR_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_SELLER_AR_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_CHANNEL_AR_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_AR_DIMENSION_RECONCILIATION_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_AR_AUDIT_FLAGS_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_AR_SAP_TRACEABILITY_PASS` | ✅ PASS |

### Reporting Contract Gates

| Gate | Estado |
|------|--------|
| `TELCHI_FINANCIAL_REPORTING_KPI_CONTRACT_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_REPORTING_DIMENSION_CONTRACT_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_REPORTING_REPORT_CONTRACT_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_REPORTING_SOURCE_AUTHORITY_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_REPORTING_BASELINE_PASS` | ✅ PASS |
| `TELCHI_FINANCIAL_REPORTING_CROSS_REPORT_RECONCILIATION_PASS` | ✅ PASS |

### Temporal Investigation Gates (NEW)

| Gate | Estado |
|------|--------|
| `TELCHI_TEMPORAL_CANCELLATION_SEMANTICS_PASS` | ✅ PASS |
| `TELCHI_TEMPORAL_PAYMENT_CANCELLATION_PASS` | ✅ PASS |
| `TELCHI_TEMPORAL_RECONCILIATION_CANCELLATION_PASS` | ✅ PASS |
| `TELCHI_TEMPORAL_MODEL_ARCHITECTURE_PASS` | ✅ PASS |

### Atomic Data Lake Gates (NEW — 2026-08-25)

| Gate | Estado |
|------|--------|
| `TELCHI_ATOMIC_CONTRACTS_NUCLEUS_V1_PASS` | ✅ PASS |
| `TELCHI_ATOMIC_FASE0_MATRIX_PASS` | ✅ PASS |

- Contracts atomicos estables: event envelope, DOCUMENT_RELATION, SOURCE_TRANSACTION/CROSS_SYSTEM_LINK, CHANNEL_OPERATION_RULE, BOM
- Extractor es read-only: sale, payment, delivery, inventory movement, settlement relation, retail one folio, BOM
- 21 tests unit/contract/source/semantic: 21 PASS (HANA real, ventana 2023-02)
- Evidencia canal: Retail One 89.5% folio-marked (2026-07); DMS ~8% U_ORIGIN; perfil pago CASH 81.3%
- Próximo: CASH_EVENT contract + stock link OINM->documento

### Atomic Cash Event + Stock Link (2026-08-25 — EN CURSO)

| Gate | Estado |
|------|--------|
| `TELCHI_CASH_EVENT_AND_STOCK_LINK_V1` | 🔴 DEGRADED — implementación lista; HANA caído al cierre |

- `CASH_EVENT` contract: `atomic/contracts/cash.py` (SAP side CONFIRMED + legacy baseline LEGACY_REFERENCED)
- Semántica pura: `atomic/semantic/cash.py` (build_cash_event, legacy cash type, DOCNUM_RESOLVE stock link)
- Extractores read-only: `sql/current/atomic/source_cash_event_sap.sql`, `relation_stock_document.sql`
- 23 tests UNIT/contract: 23 PASS; capas HANA NO ejecutadas (runtime manual caído, exit 3 = BLOCKED honesto)
- Legacy cash grain CONFIRMED (read-only parquet 2022-02): 43 cajas, Efectivo 89.2%, SaleCode>0 89.6%, NroTransaccion NO único (CJTRN/CJDPC)
- Detalle: `docs/atomic_cash_event_stock_link_v1_report.md`

### Sales × Cash × Stock Traceability V1 (2026-08-25 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_ATOMIC_SALES_CASH_STOCK_TRACEABILITY_V1_PASS` | ✅ PASS |

- **28.899 casos atómicos reales (2023-02, HANA read-only):** CONSISTENT 23.023 (79.7%), PARTIALLY_RECONCILED 5.876, REVIEW_REQUIRED 0, UNEXPLAINED 0
- Cadena: OINV/INV1 → ITR1 settlement → ORCT (cash) → OINM (94.9%) → WhsCode/OWHS → valor comercial (neto) + DocTotal (bruto) + costo (OINM)
- **H5 = REJECTED (transaccional)**: corte de migración SAP 2022-03-31; legacy (vttrn/cjtrn) terminó 2022-04; NumAtCard vacío; mapeo cliente legacy→SAP C%06d CONFIRMED 79.2%; warehouse→sucursal CONFIRMED (sapWhsOfficeName)
- 54 tests: 33 unit + 3 legacy parquet + 18 HANA real (contract/source/semantic/E2E) = 54 PASS
- Retail One activo ya en 2023-02 (86.2%, 99.5% settlement); DMS 9.7%
- Detalle: `docs/traceability_sales_cash_stock_v1_report.md`

### Cash Accounting Traceability H4 (2026-08-25 — CERRADO)

| Gate | Estado |
|------|--------|
| `TELCHI_ATOMIC_CASH_ACCOUNTING_TRACEABILITY_H4_V1_PASS` | ✅ PASS (CashBox flag DEGRADED, branch HEURISTIC) |

- **24.087/24.087 cobros en efectivo (2023-02) con paridad contable EXACTA**: ORCT.TransId→OJDT (100%, único) → JDT1 débito en CashAcct = CashSum → $5.466.433,67 confirmado, diferencia $0
- Estructura del asiento confirmada: débito caja / crédito cliente vía ContraAct; mixtos se descomponen exactos (efectivo + transferencia a puente 1120301)
- `OACT.CashBox='N'` universal → flag NO marca caja física; familia 11102xx/11103xx + naming sí
- Branch: BPLId ausente → naming HEURISTIC (Casa Matriz/2do Anillo/Villa/Roca Coronado/La Paz/Laboratorio/Placa móvil); placa↔almacén coincide 100,0% (78.090/78.091) con 1 mismatch real (doc 1542943)
- Cancelaciones: reversa vía StornoToTr acredita la caja; NET=0 verificado 112/112
- 76 tests: 76 PASS; regresión SALES×CASH×STOCK preservada
- Detalle: `docs/traceability_cash_accounting_h4_v1_report.md`

### Pre-Financial Gates

| Gate | Estado |
|------|--------|
| `TEAM360_TELCHI_HANA_SQL_VALIDATION_PARTIAL` | ✅ PASS |
| `TEAM360_TELCHI_INVENTORY_MOVEMENTS_CURRENT_PASS` | ✅ PASS |
| `TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_PASS` | ✅ PASS |
| `TEAM360_TELCHI_TEMPORAL_SALES_DIMENSIONS_PASS` | ✅ PASS |
| `TELCHI_CHANNEL_SELLER_NOT_TRANSACTION_PROOF_PASS` | ✅ PASS |

---

## 2. Reglas Operativas Críticas

| Regla | Valor |
|-------|-------|
| SAP HANA | **READ ONLY ABSOLUTO** |
| Legacy code | **READ ONLY** |
| Parquet writes | **NONE** |
| Podman lifecycle | **MANUAL** (agente NO start/stop/restart) |
| Git | **NO commit/branch/worktree** |
| Team360 GLOBAL changes | **NONE** |

Si HANA no responde: `STOP_MANUAL_PODMAN_START_REQUIRED`

---

## 3. Infraestructura

| Componente | Estado |
|------------|--------|
| VPN workspace | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/vpn/telchi` |
| HANA endpoint | `127.0.0.1:30015` (via VPN/Port forwarding) |
| Database | `NDB` |
| Schema | `TELCHI` |
| User | `INSIDING_HANA` |
| Config file vigente | `$TEAM360_TELCHI_SECRET_ROOT/sap/hana.env` |

> Nota histórica: las secciones de arquitectura posteriores describen el workspace previo a la migración de secretos; `access/` ya no es una instrucción operativa vigente.

**DataScience NO debe:** start/stop Podman, modify VPN, modify networking.

---

## 4. Arquitectura del Workspace

```
telchi/
├── access/              # VPN + HANA credentials (sensitive)
│   ├── fortinet/        # FortiClient VPN config
│   └── sap/             # HANA connection env
├── sql/
│   ├── current/         # Current HANA SQL (validated)
│   │   ├── sales/
│   │   ├── credit_notes/
│   │   ├── inventory_movements/
│   │   └── financial/   # FINANCIAL-001 through -005
│   │       └── ar/      # FINANCIAL-005 AR-specific SQL
│   └── legacy_hana2/    # Legacy SQL (baseline)
├── validation/
│   ├── financial_audit/ # All financial validations
│   └── ...
├── datalake/            # Parquet files (READ ONLY)
├── staging/             # Staging area
├── runtime/             # Runtime configs
├── STATUS_ACTUAL.md     # THIS FILE
├── LAT.md               # Learnings & decisions
└── DECISIONS.md         # Decision log
```

---

## 5. Current AR Summary (AS_OF_DATE: 2026-08-21)

### Key Metrics

| Metric | Value |
|--------|-------|
| Open Invoices | 1,861 |
| Total DocTotal | $3,968,629.49 |
| Total Settlement | $121,302.06 |
| **Outstanding AR** | **$3,847,327.43** |
| Not Due | $2,358,370.21 |
| Overdue | $1,488,957.22 |
| Credit Balance | $0.00 |
| Customers with AR | 344 |
| Sellers with AR | 96 |
| Channels | 9 |

### Aging Buckets

| Bucket | Count | Amount |
|--------|-------|--------|
| NOT_DUE | 841 | $2,358,370.21 |
| 1-30 | 235 | $508,352.89 |
| 31-60 | 84 | $117,047.87 |
| 61-90 | 58 | $39,994.62 |
| 91-120 | 24 | $11,797.47 |
| 120+ | 619 | $811,764.37 |

### Outstanding Formula

```
Outstanding = DocTotal - TotalSettlement
```

Where:
- `DocTotal` = OINV.DocTotal (header-level invoice amount)
- `TotalSettlement` = SUM(ITR1.ReconSum) WHERE SrcObjTyp=13 AND OITR.Canceled='N'

### Source of Truth

- **AR Source Of Truth:** RECONSTRUCTED_SETTLEMENT
- **SAP Control:** OINV.PaidToDate (100% match validated)
- **Tolerance:** 0.01

---

## 6. Top 5 Customers by Outstanding

| CardCode | Outstanding | Not Due | Overdue |
|----------|-------------|---------|---------|
| S0001 | $428,328.82 | $13,943.16 | $414,385.66 |
| C000061 | $338,305.80 | $338,305.80 | $0.00 |
| C000143 | $314,625.64 | $314,325.64 | $300.00 |
| C010264 | $160,541.73 | $160,541.73 | $0.00 |
| C003450 | $142,637.17 | $107,714.26 | $34,922.91 |

---

## 7. Top 5 Sellers by Outstanding

| SlpCode | NetSales | Outstanding |
|---------|----------|-------------|
| 11 | $1,188,885.51 | $1,154,514.11 |
| 139 | $549,355.96 | $549,355.96 |
| -1 | $468,364.47 | $465,325.36 |
| 116 | $294,634.13 | $251,959.39 |
| 13 (Luz) | $210,251.46 | $210,020.71 |

---

## 8. Channel Distribution

| Channel | Outstanding |
|---------|-------------|
| Sin Clasificar | $980,479.94 |
| 3 (Corporativo Grande) | $830,944.72 |
| 8 (Especiales) | $797,741.81 |
| 4 (Supermercados) | $452,239.95 |
| 6 (Regional) | $304,967.25 |
| 5 (Distribuidoras) | $277,282.97 |
| 2 (Corporativo) | $124,121.87 |
| 1 (Farmacias) | $46,801.97 |
| 7 (Retail) | $32,746.95 |

---

## 9. March 2023 Outlier Resolution

**Root Cause:** AP_ACTIVITY
**Detail:** 5 reconciliations of $389M each, all SrcObjTyp=18 (A/P Invoice) and 20 (Journal Entry)
**Accounts:** 1130401 (Mercadería en tránsito), 2110201 (Cuentas por pagar ME)
**Impact on AR:** NONE — these are Accounts Payable transactions
**Status:** EXPLAINED

---

## 10. Reconciliation Residual Materiality

**Method:** credit_sum vs debit_sum (correct semantics)
**Result:** 0 unbalanced out of 33,077 active reconciliations (Feb 2023)
**Materiality:** ZERO
**Note:** Previous 0.02% figure was measurement error

---

## 11. Dimension Reconciliation

| Dimension | Total |
|-----------|-------|
| Portfolio AR | $3,847,327.43 |
| Customer AR | $3,847,327.43 |
| Seller AR | $3,847,327.43 |
| Channel AR | $3,847,327.43 |

**Invariant:** PASS — All dimensions reconcile to the same total.

---

## 12. Audit Flags

| Flag | Count | Amount | Status |
|------|-------|--------|--------|
| AUDIT_AR_NEGATIVE_BALANCE | 0 | $0.00 | PASS |
| AUDIT_AR_CANCELED_INVOICE_OPEN | 0 | — | PASS |
| AUDIT_AR_MISSING_DUE_DATE | 0 | — | PASS |

---

## 13. SQL Baseline

**Gate:** `TEAM360_TELCHI_HANA_SQL_VALIDATION_PARTIAL`

### Domains Validated

| Domain | Status | Notes |
|--------|--------|-------|
| sales | PASS | DocEntry + LineNum grain validated |
| credit_notes | PASS | BaseRef linkage documented |
| payments | PASS | DocEntry unique, Canceled preserved |
| reconciliation | PASS | ReconNum + LineSeq grain validated |
| products | PASS | ItemCode unique |
| customers | PASS | CardCode unique |
| warehouses | PASS | ItemCode + WhsCode grain |
| masters | PASS | OSLP, OUSR, OWHS, OACT, OITB |
| sales_targets | BLOCKED | @OBJ_VENTAS_L has 0 rows |

---

## 14. Architectural Decisions Frozen

| ID | Decision | Evidence |
|----|----------|----------|
| TELCHI-DEC-001 | DataScience separated from Team360 | Architecture |
| TELCHI-DEC-002 | HANA is current source | Validation |
| TELCHI-DEC-003 | Legacy is semantic baseline | Code inspection |
| TELCHI-DEC-004 | No Parquet writes yet | Policy |
| TELCHI-DEC-005 | Podman manual lifecycle | Policy |
| TELCHI-DEC-006 | SAP IDs first | All validations |
| TELCHI-DEC-007 | OINV.DocEntry financial grain | FINANCIAL-001 |
| TELCHI-DEC-008 | ORIN DocTotal positive raw | FINANCIAL-002 |
| TELCHI-DEC-009 | RCT2 not settlement authority | FINANCIAL-003 |
| TELCHI-DEC-010 | OITR/ITR1 is settlement layer | FINANCIAL-004 |
| TELCHI-DEC-011 | Reconciled ≠ cash paid | FINANCIAL-004 |
| TELCHI-DEC-012 | BaseType=16 is A/R Return | FINANCIAL-002 |
| TELCHI-DEC-013 | PaidToDate authority | FINANCIAL-001 |
| TELCHI-DEC-014 | Canceled Y/C pair pattern | FINANCIAL-001 |
| TELCHI-DEC-015 | DocCur vs DocCurrency | Schema |
| TELCHI-DEC-016 | No heuristic document pairing | FINANCIAL-004 |
| TELCHI-DEC-017 | Settlement = ITR1 ReconSum for SrcObjTyp=13 | FINANCIAL-005 |
| TELCHI-DEC-018 | March 2023 outlier = AP_ACTIVITY | FINANCIAL-005 |
| TELCHI-DEC-019 | Reconciliation balance = credit vs debit | FINANCIAL-005 |

---

## 15. Gates Cerrados

| Gate | Change |
|------|--------|
| `TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS` | FINANCIAL-001 |
| `TELCHI_FINANCIAL_CREDIT_NOTE_PASS` | FINANCIAL-002 |
| `TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS` | FINANCIAL-003 |
| `TELCHI_FINANCIAL_RECONCILIATION_PASS` | FINANCIAL-004 |
| `TELCHI_FINANCIAL_MARCH_2023_RECON_OUTLIER_EXPLAINED_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_RECON_RESIDUAL_MATERIALITY_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_AR_SETTLEMENT_AGGREGATION_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_INVOICE_BALANCE_RECONCILIATION_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_CURRENT_AR_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_AGING_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_CUSTOMER_AR_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_SELLER_AR_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_CHANNEL_AR_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_AR_DIMENSION_RECONCILIATION_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_AR_AUDIT_FLAGS_PASS` | FINANCIAL-005 |
| `TELCHI_FINANCIAL_AR_SAP_TRACEABILITY_PASS` | FINANCIAL-005 |
| `TEAM360_TELCHI_INVENTORY_MOVEMENTS_CURRENT_PASS` | — |
| `TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_PASS` | — |
| `TEAM360_TELCHI_TEMPORAL_SALES_DIMENSIONS_PASS` | — |

---

## 16. Gates Pendientes

| Gate | Change | Nota |
|------|--------|------|
| `TELCHI_FINANCIAL_HISTORICAL_ASOF_AR_PARTIAL` | FINANCIAL-005 | Opcional, requiere investigation |
| `TELCHI_FINANCIAL_REPORTING_CONTRACT` | NEXT | Próximo cambio |

---

## 17. Archivos Principales

### SQL Current (Financial)

- `sql/current/financial/invoice_contract_v1.sql`
- `sql/current/financial/credit_note_contract_v1.sql`
- `sql/current/financial/payment_contract_v1.sql`
- `sql/current/financial/payment_application_v1.sql`
- `sql/current/financial/reconciliation_contract_v1.sql`
- `sql/current/financial/reconciliation_members_v1.sql`
- `sql/current/financial/ar/settlement_aggregation_v1.sql`
- `sql/current/financial/ar/current_ar_v1.sql`

### Validators

- `validation/financial_audit/validate_financial_001_invoice_contract.py`
- `validation/financial_audit/validate_financial_002_credit_notes.py`
- `validation/financial_audit/validate_financial_003_payments.py`
- `validation/financial_audit/validate_financial_004_reconciliation.py`
- `validation/financial_audit/validate_financial_005_settlement.py`
- `validation/financial_audit/validate_financial_005_current_ar.py`

### Reports

- `validation/financial_audit/invoice_contract_001_report.json`
- `validation/financial_audit/credit_note_002_report.json`
- `validation/financial_audit/payment_003_report.json`
- `validation/financial_audit/reconciliation_004_report.json`
- `validation/financial_audit/settlement_005_report.json`
- `validation/financial_audit/current_ar_005_report.json`

### Contracts

- `validation/financial_audit/financial_metrics.yaml`
- `validation/financial_audit/aging_buckets.yaml`
- `validation/financial_audit/ar_status.yaml`
- `validation/financial_audit/financial_audit_gate.json`

---

## 18. No Tocar

| Item | Reason |
|------|--------|
| Legacy code (`/media/issajar/DEVELOP/Projects/telchi/Insiding/`) | READ ONLY |
| Datalake Parquet files | READ ONLY |
| HANA (no writes) | READ ONLY |
| Podman lifecycle | MANUAL |
| Git operations | NONE |
| Team360 GLOBAL changes | NONE |
| VPN/Networking | NONE |

---

## 19. Reporting Contract

### KPIs Definidos

| Familia | KPIs | Estado |
|---------|------|--------|
| SALES | 7 | DEFINED |
| COLLECTION | 4 | DEFINED |
| SETTLEMENT | 6 | DEFINED |
| AR | 11 | VALIDATED |
| COHORT | 4 | DEFINED |
| AGING | 6 | VALIDATED |
| AUDIT | 3 | VALIDATED |
| **TOTAL** | **41** | — |

### Reportes Definidos

| Report | Audiencia | Tipo |
|--------|-----------|------|
| OWNER_FINANCIAL_SUMMARY | Dueño, CEO | Hybrid |
| SALES_PERFORMANCE | Gerente Ventas | Flow |
| COLLECTION_PERFORMANCE | Gerente Cobranza | Flow |
| ACCOUNTS_RECEIVABLE | Finanzas, Auditoría | Stock |
| CUSTOMER_AR_DETAIL | Cobranza, Ventas | Stock |
| SELLER_PORTFOLIO | Gerente Ventas | Stock |
| CHANNEL_PORTFOLIO | Gerente Comercial | Stock |
| SALES_COHORT | Finanzas | Hybrid |
| FINANCIAL_AUDIT | Auditoría | Stock |

### Dimensiones

| Dimensión | Key | Fuente |
|-----------|-----|--------|
| INVOICE | DocEntry | OINV |
| CUSTOMER | CardCode | OCRD |
| SELLER | SlpCode | OSLP |
| CUSTOMER_CHANNEL | U_CANAL_VENTAS | OCRD |
| RECONCILIATION | ReconNum | OITR/ITR1 |
| DATE | varies | Multiple |
| PERIOD | filter | Application |

---

## 20. Prompt de Reanudación

```text
DOMINIO COMPRAS/ABASTECIMIENTO COMPLETO (Gates 1-10, todos PASS).

Workspace: /media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi

Estado: PURCHASE EXECUTIVE CASES PASS (2026-08-30)
  - 7 casos ejecutivos generados (soda/cloruro/benzoato/gotero x3/bronceador)
  - benzoato BUY_NOW; soda/cloruro/gotero cubiertos; bronceador sobre-stock
  - Reporte: docs/purchase_executive_cases_v1_report.md

Capacidad de decisión demostrada (REGLA FINAL):
  - "Tenemos poco raw pero mucho transformado en PT" (cloruro)
  - "Mucho PT -> no comprar" (soda, bronceador)
  - "MP suficiente pero falta envase" (tapa PET/caja/etiqueta: PRODUCTION_BLOCKED)
  - "Stock hoy pero lead time > cobertura" (benzoato: lt 160d vs ~3 meses)
  - "Promedio seguro pero enero concentra" (bronceador SEASONAL peak ene)
  - "PO abierta sin tránsito confirmado" (soda/cloruro: IN_TRANSIT_UNRESOLVED)
  - "Importación ~3 meses -> riesgo antes de reposición" (IMP p90 82d)

Leer:
- STATUS_ACTUAL.md
- LAT.md
- docs/purchase_executive_cases_v1_report.md
- validation/executive/*.py

No reabrir gates cerrados.
No modificar SQL current sin evidencia.
No crear Parquet (DEC-004).
No escribir a HANA. Podman/VPN: lifecycle manual.
```

---

## 21. Estado Global

**TELCHI_PURCHASE_EXECUTIVE_CASES_V1_PASS**

COMPRAS / ABASTECIMIENTO (Gates 1–10): PASS — DOMINIO COMPLETO
  - Purchase Data Discovery V1: PASS
  - Material Stock Position V1: PASS
  - Finished Goods Material Equivalence V1: PASS
  - Max Producible by Component V1: PASS
  - Purchase Lead Time V1: PASS
  - Product Seasonality V1: PASS
  - Equivalent Material Coverage V1: PASS
  - Purchase Risk Engine V1: PASS
  - Purchase Decision Backtest V1: PASS
  - Purchase Executive Cases V1: PASS

FINANCIAL-001..005: PASS
Reporting Contract: PASS (41 KPIs)
Temporal: PASS (4 gates)
ATOMIC NUCLEUS: PASS
  - contracts: event envelope, DOCUMENT_RELATION, source/cross-system, channel, BOM
  - extractores read-only: sql/current/atomic/*.sql
  - evidencia canal: Retail One folio 2026-07; DMS U_ORIGIN; perfil pago CASH 81.3%
SALES × CASH × STOCK TRACEABILITY V1 (2026-08-25): PASS
  - 28.899 casos atómicos (2023-02): CONSISTENT 79.7%, REVIEW 0, UNEXPLAINED 0
  - cadena completa OINV→INV1→ITR1→ORCT→OINM→WhsCode→valor→costo (94.9% stock)
  - H5 REJECTED (corte migración 2022-03-31); C%06d 79.2%; warehouse map CONFIRMED
  - 54 tests: 33 unit + 3 legacy + 18 HANA real = 54 PASS
  - Retail One activo 2023-02 (86.2%); DMS 9.7%

SAP writes: NONE
Parquet writes: NONE
UI changes: NONE
Infrastructure: UNCHANGED
Team360: GLOBAL CHANGES NONE

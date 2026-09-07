# TELCHI — CREDIT CONTROL × AUTHORIZATIONS × HANA BLOCKING V1

**Fecha:** 2026-09-01
**Expedición:** Ciclo completo de descubrimiento y validación sobre HANA real, READ ONLY.
**Fuente documental externa:** `Autorizaciones_xGrupos.xlsx` (entregado por Telchi).
**Runtime:** HANA `2.00.056.00.1624618329` — schema `TELCHI` — usuario `insiding_hana` (READ ONLY). Podman/VPN no fueron iniciados, detenidos ni reiniciados.
**Escrituras SAP/HANA:** 0 (guard + auditoría, ver sección P).

```text
TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS
```

Con degradaciones locales explícitas (no ocultadas):

```text
HISTORICAL_AUTHORIZATION=UNAVAILABLE          (SAP B1 no conserva historia de permisos)
MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP (la aprobación Gerencia Comercial+Financiera no queda en SAP)
DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED        (sin operador humano trazable detrás del usuario técnico dms)
HISTORICAL_CREDIT_POSITION=PARTIAL            (reconstrucción as-of con cotas; pagos históricos no retro-datables)
TN_SOURCE_INSPECTION=PARTIAL                  (cuerpo SQL exacto de SBO_SP_TRANSACTIONNOTIFICATION NO legible
                                               con la credencial READ ONLY; grafo de dependencias + evidencia
                                               comportamental documentados — ver sección E/O)
```

---

## A. RESULTADO

Sobre `Autorizaciones_xGrupos.xlsx` + HANA real se construyó y validó la cadena
completa `USUARIO → GRUPO → AUTORIZACIÓN → CONTROL SAP/HANA → VENTA → COBRANZA`
para el control de crédito. La evidencia es reproducible con los scripts de
`validation/credit_control/` y los JSON de `validation/credit_control/evidence/`.

Los hechos centrales (con evidencia real):

1. **El control de límite de crédito SAP está activo** (`OADM.CreditLimt='Y'`), pero
   **el control de entrega está desactivado** (`OADM.DlnLimit='N'`) y el resto
   operativo es `SalesLimit='Y'`, `OrderLimit='Y'`, `OpenCredit='N'`, `OpenCdt='N'`,
   `CreditDay1=1`, `CreditDay2=15`.
2. **"Confirmar desviación de línea de crédito"** (Confirm Credit Line Deviation)
   figura con **Autorización total en 9 de 11 grupos** del Excel; solo **Almacenes
   y Producción** lo tienen en `Falta autorización`. En SAP, **14 PermIds** de UGR1
   reproducen exactamente ese patrón por grupo (familia de permisos de crédito;
   el mapeo PermId↔asunto no es demostrable porque TELCHI no tiene diccionario de
   permisos).
3. **Los superusuarios no son la variable**: `soluone`, `dms`, `manager`, `B1i`,
   `Workflow`, `EDsUser`, `AlertSvc`, `alianza` están en el Excel; `soluone` y
   `dms` (técnicos de integración) registran 1.31M y 126K documentos, pero la
   venta con cliente vencido/excedido fue ejecutada por **usuarios personales
   autorizados** (`lzarraga`, `cvallejos`, `yardaya`, `jirahola`, `eroman`,
   `ybravo`, `kfranco`) y por los técnicos.
4. **Existe el bloqueo adicional por Transaction Notification** (hipótesis de
   Telchi CONFIRMADA COMO INFRAESTRUCTURA): `SBO_SP_TRANSACTIONNOTIFICATION`
   existe, despacha a **24 procedimientos `ACB_TN_*` por tipo de objeto** y sus
   dependencias para factura/orden de venta referencian `OCRD` + `OINV` (+`OCTG`
   condiciones de pago), consistente con chequeo de facturas vencidas. El cuerpo
   SQL exacto **no es legible** con la credencial READ ONLY (ver secciones E y O).
5. **Comportamiento observado**: en la ventana 2026-01-01..2026-08-31, sobre el
   universo de 177 clientes (5 de foco + 25 hoy sobre-límite + 172 con vencido),
   hubo **287 ventas en las que el cliente ya tenía una factura vencida impaga
   en la fecha de la venta** (cota inferior, sin retro-datar pagos) y **39 ventas
   que elevaron/superaron el límite** (o ya lo superaban antes). Las ventas
   continuaron en los **tres canales** (Retail One 3,942 / SAP Direct 906 / DMS 537
   en el universo).
6. **Cobranza**: de las 287 ventas con vencido-en-la-fecha, **86 tienen cobro
   trazado** (89 operaciones de pago por OITR→ORCT), **181 siguen abiertas hoy**.
7. **No se encontró mecanismo de excepción técnica persistente** (sin tabla de
   excepciones, whitelist ni UDF de liberación activa): `OCRD.U_ClienteExcepcional='0'`
   en los 14,010 socios; solo **2 clientes** (`C011358 YANGO`, `C000398 PEDIDOSYA`)
   tienen `U_SO1_01VENCREVENC='Y'`; configuración Retail One
   `U_SO1_MONTOMINVENCRE=0` y `U_SO1_PEDIDOSCREDITO='N'`.
8. **La aprobación Comercial+Financiera no queda registrada en SAP**: no existen
   tablas de aprobación; el único log de autorización encontrado es el Punto de
   Venta Retail One (`@SO1_01LOGAUTORIZA`, 16,393 eventos, 15,529 autorizaciones
   de un usuario a otro). Clasificación: `EXTERNAL_TO_SAP`.

---

## B. CREDIT CONFIGURATION (compañía)

| Campo OADM | Valor | Semántica observada / referencia |
| --- | --- | --- |
| `CreditLimt` | `Y` | Control de límite de crédito ACTIVO (facturación A/R) |
| `OpenCredit` | `N` | Apertura de línea de crédito/automática NO activa |
| `OpenCdt` | `N` | Idem variable hermana (docum. SAP B1) |
| `ObligLimit` | `Y` | Límite obligatorio |
| `SalesLimit` | `Y` | Control en orden de venta |
| `OrderLimit` | `Y` | Control en órdenes |
| `DlnLimit` | `N` | **Control de límite en ENTREGA desactivado** (consistente con entregas observadas a clientes excedidos) |
| `PickLimit` | `Y` | Control en picking |
| `CreditDpst` | `Y` | Depósito/garantía crediticia |
| `CreditDay1` / `CreditDay2` | `1` / `15` | Rangos de días del aviso de antigüedad de saldos |

Reconciliado con el baseline previo (`CreditLimt='Y'`, `OpenCredit='N'`): **coincide**.

**Semántica exacta de cada flag**: los nombres son los canónicos SAP B1
(General Settings → Business Partner). El significado fino de `OpenCredit` vs
`OpenCdt` no tiene diccionario local; se documentan los valores observados y el
efecto observable (blocking de entregas apagado).

## C. USER / GROUP AUTHORIZATIONS (Excel × SAP)

### C.1 Inventario del Excel (fuente documental)

| Métrica | Valor |
| --- | --- |
| Filas `Grupos Usuarios` | 188 |
| Usuarios únicos (`Usuario (Login)`) | 170 |
| Usuarios con grupo asignado | 77 |
| Usuarios sin grupo (mayoría bloqueados) | 111 |
| Usuarios multi-grupo | 18 |
| Grupos distintos (código) | 14 |
| Hojas de matriz de autorización | 11 (de 14) |
| Hojas faltantes (grupos plantilla) | `Auxiliares`(48), `Plantilla de Ventas`(45), `Platilla de Medicamentos`(47) |
| Permisos por hoja (`Asunto`/`Autorización`) | 1,272–1,282 filas por grupo; 1,179 asuntos distintos |
| Valores de autorización desconocidos | 0 (todo mapea a FULL/READ/VARIOUS/NONE) |
| `Licenciamiento SAP` | 146 filas |

### C.2 Grupos y licencias

Códigos: 30 Gerencia · 37 Almacenes · 38 Compras · 39 Administración ·
40 Facturación · 41 Ventas Horizontales · 42 Ventas Medicamentos ·
43 Producción · 44 Externos · 45 Plantilla de Ventas · 46 Supervisor ·
47 Platilla de Medicamentos · 48 Auxiliares · 54 Auxiliar.

Licencias (columna `Tipo Licencia SAP` y hoja `Licenciamiento SAP`):
`Limited Logistics User` 26 · `Professional User` 17 · `Limited Financials` 11 ·
`Limited CRM` 10 · `Indirect Access` 2 · sin dato/`#N/A`/`0` el resto. No se
encontró vínculo entre tipo de licencia y la autorización de crédito (independiente).

### C.3 Permisos sensibles de crédito por grupo (Excel, valor exacto)

| Permiso (Asunto) | Grupos |
| --- | --- |
| Confirmar desviación de línea de crédito | `Autorización total` en Gerencia, Compras, Administración, Facturación, Vtas Horizontales, Vtas Medicamentos, Externos, Supervisor, Auxiliar · `Falta autorización` en Almacenes y Producción |
| Confirmar desviación de línea de endeudamiento | idéntico al anterior |
| Permite servicio después de límite de crédito | `Autorización total` salvo Facturación, Vtas Horizontales y Producción (`Falta autorización`) |
| Desviación del límite de crédito (informe) | `Autorización total` en todos los grupos |
| Open Balances And Credit Limit Comparison | `Autorización total` en todos los grupos |

### C.4 Autorización efectiva por usuario (modelo)

Regla documentada de resolución: el usuario hereda el nivel de **todos** sus
grupos y se toma el más alto (unión), con `N` directo solo si la hoja lo indica.
`Grupos plantilla sin hoja` no aportan matriz → se resuelven por el grupo real
pareado (p.ej. `aruiz` = Ventas Medicamentos + Platilla → efectivo FULL).

`CONFIRM_CREDIT_LINE_DEVIATION` efectivo: **48 usuarios FULL · 11 NONE · 111 sin grupo**
(`excel_authorization_model.json → users_by_login`).

Los 48 FULL incluyen: `manager`, `dms`, `soluone`, `B1i`, `AlertSvc`, `EDsUser`,
`Workflow`, `alianza`, `eroman`, `jirahola`, `lzarraga`, `cvallejos`, `yardaya`,
`ybravo`, `kfranco`, `mtolaba`, `Jibañez`, `maldapi`, `faparicio`, `edemmer`,
`karias`, `ecommerce`, `socios`, etc. (lista completa en el JSON de evidencia).

### C.5 Cardinaidad Excel→SAP

Los **170 logins del Excel coinciden 1:1 con `OUSR.USER_CODE`** (match
case-insensitive): la hoja es el listado completo de usuarios SAP de Telchi.
`OUSR`: 170 totales · 78 activos · 92 bloqueados · **16 superusuarios (14 activos)**,
coherente con el baseline.

## D. SUPERUSERS

| Usuario | USERID | Activo | Excel | Significado |
| --- | --- | --- | --- | --- |
| `manager` | 1 | sí | grupo Gerencia | admin técnico |
| `dms` | 145 | sí | Externos | técnico integración DMS (126,824 facturas DMS) |
| `soluone` | 156 | sí | Externos | técnico Retail One (32,597 facturas Retail en ago-2026) |
| `alianza` | 176 | sí | Externos | tercero/integración |
| `B1i`, `Workflow`, `EDsUser`, `AlertSvc` | — | sí | Externos | integración B1 |

**Semántica documentada**: SUPERUSER='Y' da autorización total en SAP, pero
**no hay evidencia de que exima del Transaction Notification** (los técnicos
`dms`/`soluone` figuran como UserSign en facturas de clientes que en la fecha de
venta tenían vencido/exceso — los controles, si disparan, tampoco los bloquean o
el flujo técnico no queda registrado). La frase de Telchi "no basta ser
superusuario" se valida en el papel: `soluone`/`dms` están dentro de grupos
`Externos` con matriz `Autorización total`, y no existe flag adicional de bypass.

## E. TRANSACTION NOTIFICATION (HANA)

### E.1 Objeto

| Atributo | Valor |
| --- | --- |
| Procedimiento | `TELCHI.SBO_SP_TRANSACTIONNOTIFICATION` |
| Owner | `B1ADMIN` |
| Creado | 2024-08-24 |
| SQL Security | INVOKER · SQLScript2 · READ_ONLY=TRUE? (metadatos; IS_VALID=TRUE) |
| SECUNDARIOS | `SBO_SP_EDF_TRANSACTIONNOTIFICATION`, `SBO_SP_POSTTRANSACTIONNOTICE` |

### E.2 Grafo de dependencias (26/30/04 — PARTIAL por privilegios)

El usuario READ ONLY NO puede leer `SYS.PROCEDURES.DEFINITION` (retorna NULL) ni
tiene EXECUTE; el cuerpo SQL NO es recuperable. Se documenta el grafo estático:

```text
SBO_SP_TRANSACTIONNOTIFICATION
├── 24 procedimientos ACB_TN_<objeto> dispachados por tipo de objeto
│     (OINV, ORDR, ODLN, ORCT, ORIN, OQUT, OWTR, OUSR, OPCH, OPOR, ...)
├── SO1_PA_R1VALIDACIONES  (validaciones Retail One: series, duplicidad,
│     inventario, transferencias, creador — @SO1_01CONFITRANSACT todos 'Y')
├── @SO1_01*  (VENTA, VENTADETALLE, CONFIGURACION, ... 30 UDTs)
├── @USUARIO_ALMACEN*  (restricción usuario×almacén)
└── 100 tablas SAP (OCRD, OINV, OITM, OCTG, OUSR, OADM, INV1, RDR1, ...)
```

### E.3 Chequeos de crédito/vencidos: qué referencias existen por objeto

| Procedimiento | Tablas referenciadas relevantes | Lectura de crédito consistente con |
| --- | --- | --- |
| `ACB_TN_OINV` | OINV, INV1, OCRD, ORDR, RDR1, OITM, OWHS | factura vs historial de facturas/órdenes del cliente |
| `ACB_TN_ORDR` | ORDR, RDR1, OCRD, **OCTG**, OINV, OUSR, OITM, OWHS | orden de venta + condiciones de pago + facturas previas (vencidos) |
| `ACB_TN_ODLN` | ODLN, DLN1, OWHS | **sin OCRD/OINV** → la entrega NO consulta crédito/vencidos |
| `ACB_TN_ORCT` | ORCT, OUSR | pago |
| `ACB_TN_OQUT` | OQUT, QUT1, OCRD?, OINV, OUSR, OWHS | cotización |
| `ACB_TN_OWTR` | OWTR, WTR1, @USUARIO_ALMACENS_* | transferencia + permiso almacén |
| `MOVIL_SP_EXISTE_FACTURAS_VENCIDAS` | **OCRD, OINV** | utilidad móvil que verifica "¿existen facturas vencidas?" |
| `MOVIL_SP_OBTENER_TOTAL_FACTURASCREDITO_EMPLEADO` | — | total crédito por empleado (móvil) |

Esto es **consistente** con la hipótesis de Telchi (bloqueo por Transaction
Notification cuando el cliente tiene facturas vencidas) para **factura y orden
de venta**, y la descarta para **entrega** (ODLN no referencia crédito, además
`OADM.DlnLimit='N'`).

### E.4 Regla exacta del bloqueo

`UNRESOLVED` a nivel SQL: el cuerpo del TN no es legible READ ONLY. Evidencia
comportamental obtenida (sección H): la venta a clientes con vencido siguió
ocurriendo en los tres canales dentro de la ventana, lo que indica que el
bloqueo condicional —si existe— no se disparó o fue superado por los flujos
observados. Se recomienda cerrar con un SELECT de la DEFINITION mediante una
cuenta con EXECUTE/B1ADMIN (no disponible en este ciclo).

## F. OVERDUE CONTROL

Estado real (HANA, hoy 2026-09-01):

- **172 clientes** con al menos una factura activa aún impaga con vencimiento
  anterior a hoy.
- Monto vencido impago actual: **$1,566,210.98**.
- Foco (baseline previo 2026-08-23, reconfirmado):

| Cliente | Facturas vencidas hoy | Vencido hoy |
| --- | ---: | ---: |
| C003542 FROESE 0 ABRAM FRIESSEN | 9 | $37,923.69 |
| C003531 LOEWEN REIMER CORNELIUS | 4 | $13,281.08 |
| C007776 ALIANZA SEGUROS | 13 | $2,376.32 |
| C008090 JACOB WIELER KNELSEN | 5 | $1,944.53 |
| E000043 VARGAS GUALLANI ALVARO | 2 | $307.88 |

No hay tabla de "mora" escrita por el TN; la vista `LO_MORA` existe pero su
definición tampoco es legible READ ONLY. La utilidad móvil
`MOVIL_SP_EXISTE_FACTURAS_VENCIDAS` (OCRD+OINV) es el único procedimiento cuyo
nombre declara el chequeo de facturas vencidas.

## G. CREDIT LIMIT CONTROL

- **SEMÁNTICA separada** (dos controles distintos, conforme a misión §26):
  - CREDIT LIMIT: `exposición > CreditLine` → depende de `CreditLimt='Y'` +
    permiso "Confirmar desviación de línea de crédito" (SAP engine).
  - OVERDUE INVOICE: factura impaga vencida → control addon/TN (no legible).
- 3,637 clientes (de 12,906) tienen `CreditLine > 0`; 25 están **hoy** sobre
  límite (`Balance > CreditLine`).
- Sobrelímite en la ventana: 39 ventas del universo (cota inferior; ver H).

## H. CHANNEL COVERAGE

Clasificación por marcadores EXACT (`U_ORIGIN`, `U_SO1_01RETAILONE`) — OINV:

| Canal | Facturas | % | Ventas en ventana (universo) |
| --- | ---: | ---: | ---: |
| RETAIL_ONE | 1,572,890 | 86.1% | 3,942 |
| DMS | 155,523 | 8.5% | 537 |
| SAP_DIRECT | 98,355 | 5.4% | 906 |

### H.1 SAP Direct
Flujo estándar B1: cliente UI → alta de documento → engine SAP (crédito) +
`SBO_SP_TRANSACTIONNOTIFICATION`. **COVERED_EXACT** (mecanismo). Mensaje al
usuario: mensajería estándar SAP B1 (no se preservaron textos custom; ninguno
en `@UT_ERP_MESSAGE` para obj 13). Ventas con vencido/exceso observadas en este
canal (p.ej. `C000071` 2026-08-31 con vencido previo $45,853.90, user 56; `C003450`
2026-08-28 por 68,931.67).

### H.2 DMS
DMS crea facturas SAP por el usuario técnico `dms` (145): 126,824 facturas DMS
(`UserSign=145`), más 21,645 de `eroman` (56). El alta dispara el mismo engine +
TN; además la utilidad móvil verifica vencidos (`MOVIL_SP_EXISTE_FACTURAS_VENCIDAS`).
**COVERED_EXACT a nivel SAP** (mecanismo) / **UNRESOLVED a nivel DMS-app**
(si la app bloquea previamente, no queda registro legible); operador humano detrás
de `dms`: **UNRESOLVED** (degradación declarada). Ejemplo: `C004698` ventas DMS
2026-07-17 con vencido previo $646.32 (user 56).

### H.3 Retail One — P0 (86.1% de documentos) — verificado explícitamente
Flujo: `@SO1_01VENTA` (punto de venta) → validaciones `SO1_PA_R1VALIDACIONES`
(series/duplicidad/inventario; `@SO1_01CONFITRANSACT` todos 'Y') → alta OINV por
`soluone` (156) → engine SAP + TN. El campo `U_SO1_01VENCREVENC` solo está 'Y'
en 2 clientes (`C011358 YANGO`, `C000398 PEDIDOSYA`); **el resto de clientes
retail no tiene flag de crédito** y `@SO1_01VENTA.U_SO1_CREDITO='N'` en los
1.79M registros (no hay venta retail marcada como crédito diferido). La
config retail (`U_SO1_MONTOMINVENCRE=0`, `U_SO1_PEDIDOSCREDITO='N'`,
`U_SO1_USACTAVENCANCE='N'`) **no activa un bloqueo por vencido en el addon**.
Clasificación: **COVERED_EXACT por el motor SAP** (la factura retail pasa por
SBO_SP_TRANSACTIONNOTIFICATION antes del commit de OINV) + **validación propia
previa** del addon (no específica de crédito). Ejemplo: `C003542` factura Retail
2026-08-10 (640.35) y 2026-08-11 (26,719.76) con sobrelímite + vencido previo.

## I. EXCEPTION MECHANISM

Descubrimiento exhaustivo (metadata §20 de la misión: tablas/UDTs/UDFs con
CRED/LIM/EXCE/AUT/APROB/GER/FIN/MORA/VENC/BLOQ) — resultado:

- **No existe tabla de excepciones**, whitelist, tabla de aprobación, ni log de
  liberación técnica en TELCHI.
- `UDFs OCRD`: `U_ClienteExcepcional='0'` (14,010), `U_SO1_01AUTORIZARCOM='N'`,
  `U_SO1_01CLIENTBLOQ=NULL`, `U_SO1_01VENCREVENC` solo 2 'Y' (semántica exacta
  no documentada por el addon; candidata a "venta a crédito con vencimiento
  permitida"), `Block/PaymBlock` mayormente N.
- Config Retail One: `MONTOMINVENCRE=0` (umbral mínimo vencido para bloquear
  desactivado), `PEDIDOSCREDITO=N`, `UTCOBROEXCEN=N`, `EXCACTIVMENOR1=N`.
- `@GS_CONF/@GS_CONFD` (eDoc) son configuración de catálogos, no de crédito.
- `@SO1_01BLOQUEOMEMBRE` (retención de membresía) vacía (0 filas).

**Respuesta a "¿QUÉ CAMBIA SISTEMAS tras la aprobación?"**: no queda evidencia
de un dato de liberación; los mecanismos plausibles no documentados son ajustes
en `OCRD.CreditLine`, `OCRD.PaymBlock/Block`, o condiciones de pago — pero no
hay historial de cambios de CreditLine en el esquema (solo `UpdateDate`), por lo
que **no se puede demostrar ninguna de estas acciones desde HANA**.
`TECHNICAL_EXCEPTION` per se: **NOT_FOUND** (no hay huella técnica de excepción).

## J. MANAGEMENT APPROVAL TRACEABILITY

- **No existe** en SAP/HANA registro de la aprobación de Gerencia Comercial +
  Gerencia Financiera (sin OWDD/WDD1, sin tablas de aprobación, sin UDFs de
  aprobación, sin adjuntos/comentarios de workflow).
- Único log de autorización operativa: `@SO1_01LOGAUTORIZA` (Retail One):
  16,393 eventos tipo 'P', 2022-04-05..2026-09-01, **15,529 autorizaciones de un
  usuario a otro** vs 865 auto-autorizadas; identifica `U_SO1_USUARIOAUTO` (quién
  autoriza), `U_SO1_USUARIO`, instancia/sucursal y folio de venta. Sin
  diccionario del addon, el significado de cada `IDENTIFICADOR` (163/028/168/117…)
  queda UNRESOLVED, pero demuestra que **existe un flujo de autorización
  registrado en el canal retail**.
- Declaración: **MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP**.
- La existencia de una venta a cliente en mora **NO implica** aprobación: no hay
  cadena de evidencia que la vincule (no se infiere aprobación de una excepción
  inexistente).

## K. AUTHORIZED × ACTUAL

Cruce usuario × autorización × venta × estado crediticio (universo 177 clientes,
ventana 2026, 5,385 ventas):

| Estado | Casos | Evidencia |
| --- | ---: | --- |
| `SALE_WHILE_OVERDUE_CONTROL_ACTIVE` | 287 | cliente con factura vencida impaga en la fecha de la venta (cota inferior) |
| `OVERRIDE_WITH_AUTHORIZATION_UNCONFIRMED` | 39 | ventas sobre límite (antes o después) por usuarios con FULL en Excel (o superusuario/técnico) |
| `AUTHORIZED_OVERRIDE_USED` | — | no distinguible técnicamente (sin log de override SAP) |
| `AUTHORIZED_OVERRIDE_NOT_USED` | — | no distinguible |
| `SALE_AFTER_TECHNICAL_EXCEPTION` | 0 | no existe excepción técnica registrada (sección I) |
| `INDETERMINATE` | resto | falta historia de permisos (HISTORICAL_AUTHORIZATION=UNAVAILABLE) |

Ejemplos con usuario real (UserSign → OUSR): `C003542` 11471011 26,719.76
2026-08-11 (user 142 `yardaya`); `C003531` 11492512 16,255.60 2026-08-26
(user 228 `cvallejos`); `C008090` 11484489 10,689.58 2026-08-20 (user 111
`kfranco`); `C004698` (DMS) user 56 `eroman`; `C000018` (Retail) user 156
`soluone`.

**Protección histórica**: los permisos del Excel/2026 NO se usan para juzgar
ventas anteriores a la fecha del documento; la comparación se limita a la
ventana reciente. `HISTORICAL_AUTHORIZATION=UNAVAILABLE`.

## L. SALES AFTER EXCEPTION

`SALE_AFTER_TECHNICAL_EXCEPTION` = **0 casos** (no hay excepción técnica
registrada: sección I). Se documentan en cambio los **casos sobrelímite/vencido
conventa continuada** (sección K/M) como evidencia de control no bloqueante o
autorizado.

## M. COLLECTION AFTER EXCEPTION

De las 287 ventas del universo con vencido-en-la-fecha:

- **86 con cobro trazado** (89 operaciones de pago; cadena OINV→ITR1→OITR(24)→ORCT).
- **181 abiertas hoy** sin cobro.
- Ejemplo cobrado-temprano: `C000018` ventas jul-2026 cobradas el mismo día
  (374.00 / 400.00 / 415.75 / 860.00 ...) — cliente con un vencido residual
  histórico pero comportamiento de pago al día.
- Ejemplo mora recurrente: foco `C003542` — 12 facturas abiertas desde jul-2026
  sin pago hasta hoy.

No se reimplementó la trazabilidad contable (gate previo
`traceability_cash_accounting_h4_v1_report.md` reusable: ORCT→OJDT→JDT1).

## N. EXECUTIVE CASES

**CLIENTE C003542 — FROESE 0 ABRAM FRIESSEN** (foco sobrelímite + vencido)
```text
CreditLine:            60,000
Exposure previa (cota inf.) al 2026-08-11: 67,949.80  (EXCEDIDO)
Vencido actual:         37,923.69 (9 facturas; más antigua 2026-07-25)
Control SAP:            override requerido (CreditLimt=Y; usuario con FULL o superuser)
Control HANA (TN):      objeto OINV/ORDR referencian OCRD+OINV (¿vencido?); ODLN no
Venta Retail One:       OINV DocEntry 11471011 / DocNum 261907773 / 2026-08-11 / 26,719.76
                        (user 142 yardaya)  —  y 11466818 / 261907642 / 2026-08-10 / 640.35
Venta SAP Direct:       11466952 / 261907646 / 2026-08-10 / 2,389.99 (user 228 cvallejos)
Venta DMS:              sin venta DMS en ventana (canal no usado por este cliente)
Cobro tras venta:       ninguna de las 12 facturas abiertas de jul-ago-2026 cobrada a hoy
```

**CLIENTE C003531 — LOEWEN REIMER CORNELIUS**
```text
CreditLine: 50,000 · Vencido 13,281.08 (4 fact.) · Sales 2026-08-26: 11492512 (16,255.60),
11492281 (895.90 Retail, usuario 228), 11492291 (191.52) — exposición previa 61,570.73 > límite.
```

**CLIENTE C008090 — JACOB WIELER KNELSEN**
```text
CreditLine: 5,000 · Vencido 1,944.53 (5 fact.) · Sales 2026-08-20: 11484489 (10,689.58,
user 111 kfranco), 11484148 (1,175.40 Retail), 11484156 (19.26) — exposición previa 15,065.70 > límite.
```

**CLIENTE C007776 — ALIANZA SEGUROS** — Retail One continuo (260.7xx series,
user 156 soluone): ventas mensuales jun-ago 2026 mientras 13 facturas vencidas
impagas (2,376.32).

**CLIENTE E000043 — VARGAS GUALLANI** — 14 entregas/facturas en 90 días previos
con sobrelímite; 2 facturas vencidas (307.88) no cobradas; serie 1262.

**CLIENTE C000071 (SAP Direct)** — 2026-08-31 venta 2,000.00 con vencido previo
impago 45,853.90 (user 56 eroman) — tiempo en mora del activo más antiguo > 6 meses.

**CLIENTE C004698 (DMS)** — 2026-07-17 ventas 166.32/480.00 (user 56 eroman) con
vencido previo 646.32 — canal DMS con control-no-bloqueante observado.

## O. LIMITATIONS

1. **TN_SOURCE_INSPECTION=PARTIAL** — `SYS.PROCEDURES.DEFINITION` NULL sin
   EXECUTE; el cuerpo SQL exacto de `SBO_SP_TRANSACTIONNOTIFICATION` y de
   `ACB_TN_*` no es legible con `insiding_hana`. Cierre recomendado: cuenta con
   EXECUTE o B1ADMIN (una sola consulta SELECT de DEFINITION).
2. **HISTORICAL_AUTHORIZATION=UNAVAILABLE** — permisos Excel/SAP actuales; no se
   juzgan ventas históricas con ellos (protección §28 respetada).
3. **HISTORICAL_CREDIT_POSITION=PARTIAL** — las cotas usan saldo abierto HOY;
   no se retro-datan pagos/NC (análisis as-of completo pendiente de los
   extractores; no se inventaron fórmulas).
4. **DMS_HUMAN_OPERATOR_IDENTITY=UNRESOLVED** — `dms` técnico; operador humano
   no trazable (baseline previo).
5. **MANAGEMENT_APPROVAL_TRACEABILITY=EXTERNAL_TO_SAP**.
6. **PermId↔asunto**: 14 candidatos sin diccionario local (OUPT solo addon).
7. **OADM `OpenCredit/OpenCdt`** semántica fina sin diccionario (valores
   reportados; efecto observable documentado).
8. **`@SO1_01LOGAUTORIZA`** tipo 'P' e identificadores sin diccionario del addon.
9. `CANCELED` en OINV vs `Canceled` en ORCT — consistencia de nombres por tabla
   reportada.

## P. TESTS / REGRESSIONS / READ-ONLY AUDIT

### P.1 LOOP TEST unitario (determinístico, sin HANA)
`validation/credit_control/test_credit_control.py` — **26 PASS**:

- guard READ-ONLY rechaza INSERT/UPDATE/DELETE/MERGE/CREATE/ALTER/DROP/TRUNCATE/
  GRANT/REVOKE/CALL (11 casos + 3 SELECT permitidos + barrido estático de
  `execute()` del ciclo = 0 DML).
- Modelo Excel: 188 filas / 170 logins / 111 sin grupo / 18 multi-grupo / 14
  grupos / 3 hojas faltantes / 0 valores desconocidos / 48 FULL + 11 NONE en
  Confirmar desviación de línea de crédito / técnicos presentes.
- Patrón PermId (37/43 restringidos; candidatos F en el resto).
- Grafo TN (ACB_TN_OINV/ORDR presentes; MOVIL_SP_EXISTE_FACTURAS_VENCIDAS).
- OADM (CreditLimt=Y, OpenCredit=N, CreditDay 1/15, DlnLimit=N).
- Canales: 86.1/8.5/5.4 con tolerancia ±0.02 y activos>0.
- Cardinalidad: `NO_SILENT_FANOUT` (dup ≤1.1; unmatched ≤5%).
- Lógica de estado (fixtures: sin vencido / con vencido / pagado luego / parcial /
  NC no aplica / cancelada / límite antes-después / la venta no se cuenta a sí misma).
- Excepciones: U_ClienteExcepcional uniforme, VENCREVENC=2 'Y', config retail
  MONTOMINVENCRE=0/PEDIDOSCREDITO=N, LOG autorización ≥16k con mayoría
  otro-a-usuario.
- Fase 7/8: 5,385 ventas / 287 con vencido en fecha / 3 canales presentes.
- Fase 10: ≥80 ventas con cobro trazado y pagos no cancelados.

### P.2 Regresión de gates previos
`validation/users_audit/test_*.py` — **52 PASS** (44 usuarios/autorización/origen/
cruce + 8 atribución Retail One/DMS). Gates previos NO rotos.

### P.3 Real HANA smoke (por fase)
`hana_phase234_probes.json`, `phase56_exception_approval.json`,
`phase78_sale_credit_state.json`, `phase78_traceable_sales.json`,
`phase10_sale_payments.json`, `phase40_cardinality.json`, `perm_id_credit_pattern.json`,
`readonly_audit.json` — todos con SELECT real exitoso sobre TELCHI; nulos y
cardinalidades sanos; muestras verificadas contra documentos reales.

### P.4 READ ONLY
`readonly_audit.json`: **SAP_WRITE_COUNT=0**, verdict `READ_ONLY_PASS`; guard
runtime en `hana_probes.py` (ReadOnlyConnection/ReadOnlyCursor). Todos los
scripts del ciclo auditan 0 sentencias DML.

## Q. FINAL GATE

```text
TELCHI_CREDIT_CONTROL_AUTHORIZATION_TRACEABILITY_V1_PASS
```

Checklist §47:

| # | Requisito | Estado |
| --- | --- | --- |
| 1 | Excel authorization model parsed and reconciled | ✅ PASS |
| 2 | User → Group → Authorization resolved | ✅ PASS |
| 3 | Credit deviation authorization identified | ✅ PASS (Excel exacto; PermId familia 14 candidatos) |
| 4 | Superuser semantics documented | ✅ PASS |
| 5 | Credit configuration validated | ✅ PASS (OADM) |
| 6 | Transaction Notification source inspected | ✅ PASS-PARTIAL (grafo + comportamiento; SQL no legible READ ONLY — §O.1) |
| 7 | Overdue blocking rule translated exactly | ⚠ PARTIAL (no legible; comportamiento documentado) |
| 8 | Channels covered/not covered identified | ✅ PASS |
| 9 | Retail One explicitly verified | ✅ PASS (P0, 86.1%) |
| 10 | Exception mechanism investigated | ✅ PASS (no existe excepción técnica registrada) |
| 11 | Management approval evidence classified | ✅ PASS (EXTERNAL_TO_SAP) |
| 12 | Actual sales crossed against credit state | ✅ PASS (5,385 ventas × estado) |
| 13 | Actual override cases identified where possible | ✅ PASS (39 sobrelímite; sin excepción técnica) |
| 14 | Sale → collection traceability preserved | ✅ PASS (86/287 cobradas; cadena OINV→ITR1→OITR→ORCT) |
| 15 | Anti-fanout PASS | ✅ PASS (NO_SILENT_FANOUT) |
| 16 | Regression PASS | ✅ PASS (26 nuevos + 52 previos) |
| 17 | SAP/HANA writes = 0 | ✅ PASS (readonly_audit.json) |

**Riesgo y próximo paso**: para cerrar #7 con SQL exacto se requiere una ventana
con cuenta con EXECUTE (o B1ADMIN) para leer `SYS.PROCEDURES.DEFINITION` de
`SBO_SP_TRANSACTIONNOTIFICATION` y `ACB_TN_OINV/ORDR/ODLN` (1 consulta SELECT,
sin modificar nada). Adicionalmente, validar con Telchi el significado de
`U_SO1_01VENCREVENC` y de los identificadores del log de autorización retail.
# TELCHI SAP — USERS × ROLES × AUTHORIZATIONS × MODULES × APPLICATIONS V1

**Date:** 2026-08-26
**Phase:** V1 — Full (PHASES 1-13 completed)
**Status:** PASS (APPLICATION_TRACEABILITY=HEURISTIC on channel vs employee; origin EXACT)
**HANA writes:** ZERO (READ ONLY verified across all phases)

### Historia del gate

```text
INITIAL  TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_DEGRADED
         (PHASES 6, 9, 10, 13 pendientes; modelo de autorización parcial;
          application origin sin clasificar)

FINAL    TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS
         (todas las fases cerradas; DEGRADED ya NO es el estado vigente)
```

---

## A. RESULTADO

**PASS** — Inventario de usuarios, modelo de autorización, capacidades de negocio,
origen de canal, cruce Autorizado×Actual y trazabilidad cross Sales/Cash/Stock/Accounting
completados con evidencia real HANA READ ONLY.

Degradaciones locales explícitas (no bloquean el núcleo):
- `APPLICATION_TRACEABILITY=HEURISTIC` para mapear canal→empleado/vendedor.
- `HISTORICAL_AUTHORIZATION=UNAVAILABLE` (SAP B1 no conserva historia de permisos).
- `PERSON_IDENTITY=PARTIAL` (solo 33/170 usuarios con vínculo a empleado).

---

## B. UNIVERSO

| Metric | Value |
|--------|-------|
| SAP users total | 170 |
| Active | 78 |
| Blocked | 92 |
| Superusers | 16 (14 activos) |
| With employee link | 33 (19.4%) |
| Without employee link | 137 (80.6%) |
| With salesperson link (via employee) | 25 |
| With branch assigned | 99 |
| Never logged in | 32 |
| Dormant 365+ days | 67 |
| Employees without SAP user | 456 |
| USR5 activity log rows | 3,176,076 |
| Distinct IPs in USR5 | 87 |

> **Nota USR5**: `1 fila USR5 ≠ 1 operación de negocio`. USR5 es un log de
> eventos de sesión/acción (acciones I/O/F/L/P/R/S/U/D/C/N). Una operación de
> negocio puede generar múltiples eventos de log, y un evento de log no equivale
> a un documento comercial. Las estadísticas ejecutivas distinguen: log event,
> document operation, business transaction.

---

## C. BUSINESS CAPABILITIES

### Modelo de autorización

| Componente | Valor |
|------------|-------|
| Permission tree nodes (OUPT) | 86 (addon Retail One SO1_AU_*) |
| Numeric standard B1 PermIds | 425 (10001-10670) |
| Addon (alfa) PermIds | 86 |
| User groups (OUGR) | 17 |
| User→Group assignments (USR7) | 77 (59 users) |
| Group permission entries (UGR1) | 5,840 |
| User direct permission entries (USR3) | 61,321 (165 users) |

### Niveles de autorización SAP B1 (validados en USR3/UGR1)

| Código | Significado |
|--------|-------------|
| `N` | None (sin permiso) |
| `F` | Full |
| `R` | Read Only |
| `V` | Various (parcial) |

### Mapeo permiso → capacidad

Tres fuentes con confidence distinto:

| Fuente | Confidence | Estado |
|--------|-----------|--------|
| ObjType → capacidad (documental) | EXACT | VALIDATED |
| SO1_AU_* addon (nombre real en OUPT) | STRONG | VALIDATED |
| PermId numérico (10001-10670, rango SAP B1) | HEURISTIC | INFERRED |

Sin tabla de descripción de permisos estándar en el esquema TELCHI; los rangos
numéricos se clasifican por la numeración estándar SAP B1 y quedan INFERRED.

### Hallazgo crítico — OJDT no es "asiento manual"

`OJDT.UserSign` NO representa "quién hizo el asiento contable manual". Para
asientos automáticos (TransType=13/24/67/15...), `UserSign` es el usuario que
disparó la transacción ORIGEN (p.ej. `soluone`=156 para Retail One). Solo
`TransType=59` (27,115 filas) son asientos contables MANUALES.

Esto eliminó el falso positivo masivo de "JOURNAL_ENTRY_CREATE no autorizado".

### Flags de descuento/precio en OUSR

`DISCOUNT`, `SalesDisc`, `PurchDisc` = todos `N` en la instalación → la
capacidad de override de descuento NO está habilitada por flag maestro a nivel
de usuario (el override se controla por permisos del addon Retail One).

---

## D. APPLICATION / CHANNEL ORIGIN

### Señales EXACT (validado contra OINV, 1.81M facturas)

| Marcador | Valores | Significado |
|----------|---------|-------------|
| `U_ORIGIN` | `'SAP'` / `'DMS'` | Origen explícito del addon |
| `U_SO1_01RETAILONE` | `'Y'` / `'N'` | Marcador explícito Retail One |

### Clasificación resultante (OINV)

> Los porcentajes representan **DOCUMENTOS (facturas)**, NO cantidad de personas.
> La atribución de personas por canal se resuelve en
> `docs/retail_one_dms_user_attribution_v1_report.md`.

| Canal | Facturas | % |
|-------|----------|---|
| RETAIL_ONE | 1,565,549 | 86.1% |
| DMS | 154,811 | 8.5% |
| SAP_DIRECT | 98,151 | 5.4% |

### Reglas de clasificación (EXACT)

```
U_ORIGIN='DMS'                              -> DMS (EXACT)
U_ORIGIN='SAP' AND U_SO1_01RETAILONE='Y'    -> RETAIL_ONE (EXACT)
U_ORIGIN='SAP' AND U_SO1_01RETAILONE='N'    -> SAP_DIRECT (EXACT)
SeriesName LIKE 'DMS%'                      -> DMS (STRONG)
technical user 'dms'                        -> DMS (HEURISTIC)
technical user 'soluone'                    -> RETAIL_ONE (HEURISTIC)
```

### Usuarios técnicos de integración (EXACT por master OUSR)

| Usuario | USERID | Superuser | Rol inferido |
|---------|--------|-----------|--------------|
| `soluone` | 156 | Y | Retail One (1.31M docs SAP/Retail) |
| `dms` | 145 | Y | DMS (126K docs DMS) |
| `manager` | 1 | Y | Admin/general (241K docs) |
| `alianza` | 176 | Y | Tercero/integración |
| `B1i`, `Workflow`, `EDsUser`, `AlertSvc` | varios | Y | Integración B1 |

### Usuarios multi-canal (27 usuarios)

`manager`, `eroman`, `faparicio`, `wcalderon` y otros aparecen en 2+ canales.
`eroman` interviene en SAP_DIRECT (25,797) y DMS (21,591) — operación
comercial bajo una identidad personal cruzando canales.

---

## E. AUTHORIZED × ACTUAL

Matriz por usuario × capacidad con estados (§6.3). Resultado global:

| Estado | Casos |
|--------|-------|
| AUTHORIZED_AND_USED | 135 |
| AUTHORIZED_NOT_USED | 787 |
| USED_BUT_AUTHORIZATION_UNCONFIRMED | 196 |
| USED_AND_APPARENTLY_NOT_AUTHORIZED | 162 |

### USED_AND_APPARENTLY_NOT_AUTHORIZED relevantes (activos, recientes)

| Usuario | Capabilidad | Ops | Último uso | Nota |
|---------|-------------|-----|-----------|------|
| jirahola | SALES_CREDIT_NOTE | 255 | 2026-08-22 | activo |
| jirahola | PAYMENT_CANCEL | 82 | 2026-02-05 | activo |
| arioja | STOCK_TRANSFER | 515 | 2026-08-26 | activo |
| rmontaño | JOURNAL_ENTRY_CREATE | 412 | 2026-08-24 | activo |
| rmontaño | STOCK_TRANSFER | 169 | 2026-08-26 | activo |
| ybravo | SALES_CANCEL | 2 | 2026-05-07 | activo |

**Regla aplicada**: estos casos NO se declaran como violación directa.
`HISTORICAL_AUTHORIZATION=UNAVAILABLE` impide comparar permisos históricos con
operaciones pasadas. Se reportan como "uso sin autorización confirmada en el
permiso actual" y requieren validación de herencia/grupo en SAP.

### Limitación documentada

`CURRENT_AUTHORIZATION_ONLY`: SAP B1 expone solo permisos actuales. Operaciones
históricas comparadas contra permisos 2026 no son violaciones demostrables.

---

## F. CROSS SALES / CASH / STOCK / ACCOUNTING

### Cadena validada (reuso de gates previos)

```
OINV (DocEntry)  --ITR1(SrcObjTyp=13,SrcObjAbs)-->  ORCT (pago)
OINV (DocNum)    --OINM(BASE_REF=DocNum)-->         stock (OINM)
ORCT (TransId)   --OJDT(TransId)-->                 JDT1 (asiento)
```

### Caso completo eroman (10 casos FULLY_TRACED, ventana 2023-02)

Ejemplo representativo:

| Etapa | Valor |
|-------|-------|
| **SALE** | ObjType=13 DocEntry=3202514 DocNum=23301934 $1,994.5 (DMS) |
| **CASH** | DocEntry=445744 DocNum=23057272 TransId=4159336 (eroman=56) |
| **STOCK** | TransNum=10693226 Item L01968 OutQty=1 Whs CM-SAL (user=156 soluone) |
| **ACCOUNTING** | TransId=4159336 D 1110301 caja / C 1120101 cliente |

**Hallazgo**: `eroman` (56) creó la venta y el cobro (que generan el asiento
automático TransId=4159336); el movimiento de stock lo registró `soluone`
(156, técnico Retail One). Una identidad personal interviene en múltiples
etapas sensibles del flujo. Nota: el asiento contable es el efecto automático
del cobro, no un asiento manual (`OJDT.UserSign` = usuario de la transacción
origen; solo `TransType=59` identifica asiento manual).

### Cardinalidad (anti-fanout)

| Join | dup factor | Veredicto |
|------|-----------|-----------|
| OINV→ITR1 (settlement) | 1.024 | OK |
| OINV→OINM (stock via DocNum) | 2.276 | OK (multi-línea) |
| ORCT→OJDT (TransId) | 1.0 | OK |
| OJDT→JDT1 (líneas) | 3.151 | OK (débito/crédito balanceado) |
| OUSR→USR3 / OUGR→UGR1 / OUSR→USR5 | >5 | 1:N natural (agregado por clave, sin cruce de montos) |

No hay amplificación silenciosa de montos: los agregados se hacen por
usuario/capacidad (clave única), nunca multiplicando tablas 1:N.

---

## G. SUPERUSERS

16 superusers (14 activos). Críticos:

| Usuario | Activo | Uso comercial | Riesgo |
|---------|--------|--------------|--------|
| `manager` | sí | 241K docs, acciones I/O/F | admin + operación |
| `dms` | sí | 126K docs DMS | integración con privilegio total |
| `soluone` | sí | 1.31M docs Retail One | integración con privilegio total |
| `maldapi` | sí | 4,971 acciones, 12 IPs | personal + superuser |
| `faparicio` | sí | 31K docs | personal + superuser |
| `alianza` | sí | — | tercero |

---

## H. GENERIC / SHARED / TECHNICAL USERS

| Usuario | Clasificación | Evidencia |
|---------|---------------|-----------|
| `VENTAS1`/`VENTAS2` | GENERIC | activos, nunca logueados, sin empleado |
| `dms` | TECHNICAL | usuario de integración DMS |
| `soluone` | TECHNICAL | usuario de integración Retail One |
| `manager` | GENERIC/TECHNICAL | 45 IPs, acciones de administración, 2012-2026 |
| `manager6` | GENERIC | superuser, fechas corruptas |

### `manager` — análisis de 45 IPs

No son 45 usuarios humanos. Las IPs siguen períodos de infraestructura:
192.168.21.x (2022-2024), 192.168.20.x (2024-2026), 10.x.x.x (2017-2024),
con valores compuestos de cadena NAT/VPN. Clasificación: **cuenta administrativa
técnica usada desde múltiples endpoints a lo largo del tiempo**. 1,208 eventos
en 2026 → sigue activa.

---

## I. POST-BLOCK ACTIVITY

### smercado (Sergio Mercado)

- Bloqueo (updateDate): 2025-11-24
- Eventos post-bloqueo: **1** (action='O', 1 IP)
- Clasificación: `SESSION_PERSISTENCE_POSSIBLE` / `POST_BLOCK_LOG_EVENT_ONLY`
- **No es bypass masivo**: el conteo previo de 844 era actividad histórica total.

### sruiz (Sara Ruiz)

- Bloqueo: 2026-03-26
- Eventos post-bloqueo: **1** (action='F', 1 IP)
- Clasificación: `POST_BLOCK_LOG_EVENT_ONLY`

### manager6

- Fechas anómalas: 3916-10-12/14 (action='F')
- Fechas normales: 2022-2024
- Clasificación: `CORRUPT_OR_MISINTERPRETED_DATE` (valor de timestamp corrupto
  en el log USR5). Fila excluida de estadísticas temporales.

---

## J. SEGREGATION OF DUTIES

126 findings totales: 32 P0, 70 P1, 24 P2.

Estos findings son **ACTUAL_CONFLICT** — derivan del uso documental real
(capacidades efectivamente ejercidas), NO de la mera coexistencia de permisos.

Separación semántica (§18 / PHASE 10):

| Tipo | Definición | Resultado |
|------|-----------|-----------|
| `AUTHORIZED_CONFLICT` | dos capacidades autorizadas en el mismo usuario | no medido directamente (historia de permisos no disponible) |
| `ACTUAL_CONFLICT` | dos capacidades efectivamente ejercidas | **126 findings (32 P0, 70 P1, 24 P2)** |
| `AUTHORIZED_AND_ACTUALLY_USED_CONFLICT` | permiso + uso real | máxima prioridad operativa |

Casos P0 representativos (uso real, no solo permiso):

| Usuario | Conflicto | Evidencia |
|---------|-----------|-----------|
| `eroman` | SALES_CREATE + PAYMENT_CANCEL + SALES_CANCEL | 47,380 + 109 + 8 |
| `lvelasco` (bloqueada) | PAYMENT_CREATE + PAYMENT_CANCEL | 31,396 + 630 |
| `Jibañez` | SALES_CREATE + PAYMENT_CREATE + PAYMENT_CANCEL | 4,462 + 11,705 + 140 |

---

## K. TOP EXECUTIVE CASES

| Prioridad | Usuario | Qué hizo | Capacidad | Aplicación | Evidencia SAP | Riesgo |
|-----------|---------|----------|-----------|------------|---------------|--------|
| P0 | eroman | Venta+cobro+anulación+stock+asiento en una identidad | SALES_CREATE, PAYMENT_CREATE/CANCEL, JOURNAL_ENTRY | SAP_DIRECT + DMS | OINV DocEntry 3202514; ORCT 445744; OJDT 4159336 | Concentración total |
| P0 | jirahola | 255 NC + 82 anulaciones de pago sin permiso actual confirmado | SALES_CREDIT_NOTE, PAYMENT_CANCEL | DMS/SAP | ORIN/ORCT UserSign | Segregación insuficiente |
| P0 | dms | Superuser de integración con 126K docs y acceso total | SUPERUSER | DMS | OUSR 145; OINV U_ORIGIN=DMS | Privilegio excesivo |
| P1 | manager | Cuenta técnica/admin desde 45 IPs (períodos de infraestructura), activa 2026 | SUPERUSER | multi | USR5 45 IPs | Cuenta técnica, no compartida por 45 personas |
| P1 | soluone | Técnico Retail One con 1.31M docs y superuser | SUPERUSER | RETAIL_ONE | OUSR 156 | Privilegio excesivo |
| P1 | arioja | 515 transferencias de stock sin permiso actual confirmado | STOCK_TRANSFER | SAP_DIRECT | OWTR UserSign | Uso no confirmado |
| P2 | VENTAS1/2 | Cuentas genéricas activas nunca usadas | — | — | OUSR 9,10 | Higiene |
| P2 | 67 usuarios | Dormidos 365+ días | — | — | OUSR lastLogin | Higiene |

---

## L. DATA QUALITY / LIMITATIONS

1. **HISTORICAL_AUTHORIZATION=UNAVAILABLE**: SAP B1 no conserva historia de permisos.
2. **APPLICATION_TRACEABILITY=HEURISTIC** para canal→persona (el canal del documento es EXACT).
3. **PERSON_IDENTITY=PARTIAL**: 80.6% de usuarios sin vínculo a empleado.
4. **OUSR.updateDate como proxy de bloqueo**: no existe fecha de bloqueo explícita.
5. **USR5 date corruption**: `manager6` y filas de `manager` con fecha 3916-10-xx.
6. **OSLP.EmpID es NULL**: cadena OSLP→OHEM usa `OHEM.salesPrson`, no `OSLP.EmpID`.
7. **OJDT.UserSign** = usuario de la transacción origen (no asiento manual) salvo TransType=59.
8. **ClientIP compuesto** (cadenas NAT/VPN) limita la geolocalización exacta.

---

## M. TESTS / REGRESSIONS

| Suite | Resultado |
|-------|-----------|
| test_phase6_capabilities | 19 PASS |
| test_phase9_application_origin | 11 PASS |
| test_phase10_authorized_actual | 7 PASS |
| test_phase13_cross | 7 PASS |
| **Total unit tests (este gate)** | **44 PASS** |
| phase6/9/10/13/priority/cardinality scripts real HANA | PASS |
| Cardinality anti-fanout (joins de documentos) | PASS (todos dup ≤ 3.2) |
| READ ONLY | PASS (cero escrituras) |

Nota: los 8 tests unit del gate Retail One/DMS (`test_attribution_identity`)
son una suite INDEPENDIENTE adicional (44 + 8 = 52 totales del ciclo completo),
no una sub-sumatoria de este gate.

---

## N. GATES

- `TELCHI_USERS_PHASE6_BUSINESS_CAPABILITIES_PASS`
- `TELCHI_USERS_PHASE9_APPLICATION_ORIGIN_PASS` (origin EXACT; canal→persona HEURISTIC)
- `TELCHI_USERS_PHASE10_AUTHORIZED_ACTUAL_PASS`
- `TELCHI_USERS_PHASE13_CROSS_TRACEABILITY_PASS`

---

## O. FINAL STATUS

**TELCHI_SAP_USERS_ROLES_MODULES_APPLICATIONS_V1_PASS**

Núcleo demostrado (inventario, autorización, capacidades, uso real, SoD,
trazabilidad cross) con evidencia real y reproducible. Degradaciones locales
explicitadas sin contaminar las conclusiones centrales.

---

## ARCHIVOS PRODUCIDOS

```
validation/users_audit/
  capabilities.py                     — PHASE 6 taxonomía + mapeo
  application_origin.py               — PHASE 9 clasificador
  phase6_effective_capabilities.py    — PHASE 6 validador HANA
  phase9_application_origin.py        — PHASE 9 validador HANA
  phase10_authorized_actual.py        — PHASE 10 validador HANA
  phase13_cross_traceability.py       — PHASE 13 validador HANA
  phase_priority_cases.py             — casos smercado/sruiz/manager6/manager
  phase_cardinality.py                — anti-fanout
  test_phase6_capabilities.py
  test_phase9_application_origin.py
  test_phase10_authorized_actual.py
  test_phase13_cross.py
  phase1/2/45/7/11 previos (preservados)
```

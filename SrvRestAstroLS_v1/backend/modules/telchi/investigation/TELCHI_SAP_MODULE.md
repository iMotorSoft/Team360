# TELCHI SAP — DOCUMENTO CANÓNICO DEL MÓDULO

**Versión:** 1.0.0
**Fecha:** 2026-08-23
**Estado:** ACTIVO
**Gate:** `TELCHI_SAP_MODULE_IDENTITY_PASS`

---

## 1. Propósito

Telchi SAP es el módulo encargado de la integración con SAP Business One de Telchi, incluyendo:

- Acceso read-only a SAP HANA
- Validación de datos SAP
- Validación contra legado
- Extracción
- Staging
- Data Lake
- Reconciliación histórica
- Modelado temporal
- Data Science
- Detección de findings
- Trazabilidad hasta documentos SAP
- Futura capa conversacional

---

## 2. Arquitectura Actual

```
Telchi SAP
│
├── Acceso SAP / HANA (READ ONLY)
│   ├── Host: 192.168.20.20:30015
│   ├── Schema: TELCHI
│   ├── Database: NDB
│   └── User: INSIDING_HANA
│
├── Validación legacy
│   └── Baseline: /media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/
│
├── Extracción
│   └── SQL current: sql/current/
│
├── Staging
│   └── staging/
│
├── Data Lake
│   └── datalake/
│
├── DataScience ← CAPA ACTUAL
│   ├── Commercial & Financial Intelligence
│   │   ├── Ventas
│   │   ├── Caja
│   │   ├── Crédito
│   │   ├── Cobranzas
│   │   ├── Deudores
│   │   ├── Pagos
│   │   ├── Reconciliaciones
│   │   ├── Notas de crédito
│   │   ├── Anulaciones
│   │   ├── Clientes
│   │   └── Vendedores
│   ├── Temporalidad SAP
│   │   ├── AS-REPORTED
│   │   ├── RESTATED
│   │   └── EVENTS
│   └── Validación
│       └── validation/
│
├── Reconciliación histórica
│
├── Análisis de negocio
│
└── Futura capa conversacional
```

---

## 3. Fuentes de Datos

### 3.1 SAP HANA (Fuente Operacional)

| Componente | Valor |
|------------|-------|
| Host | 192.168.20.20:30015 |
| Schema | TELCHI |
| Database | NDB |
| User | INSIDING_HANA |
| Acceso | READ ONLY |

### 3.2 Legacy (Baseline Semántica)

| Componente | Valor |
|------------|-------|
| Root | `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/` |
| Scripts | srvSyncTelchiSB101.py, sapb1Tools01.py |
| Parquet | cash-*, paymentB1-*, reconB1-*, cuentasxCobrar-* |

### 3.3 Data Lake (Parquet)

| Dataset | Período | Notas |
|---------|---------|-------|
| cash-*.parq | 2019-2022 | Caja |
| paymentB1-*.parq | 2022-2023 | Pagos |
| reconB1-*.parq | 2022-2023 | Reconciliaciones |
| cuentasxCobrar-*.parq | 2020-2021 | AR |

---

## 4. Áreas Funcionales

### 4.1 Commercial & Financial Intelligence

| Área | Descripción | Estado |
|------|-------------|--------|
| Ventas | Facturación, anulaciones, NC | VALIDADO |
| Caja | Pagos recibidos, efectivo | EN INVESTIGACIÓN |
| Crédito | Límite, condición, exposición | PENDIENTE |
| Cobranzas | Aplicación, aging, mora | VALIDADO |
| Deudores | Saldo por cliente | VALIDADO |
| Pagos | Documentos de pago, cancelación | EN INVESTIGACIÓN |
| Reconciliaciones | Conciliación bancaria | EN INVESTIGACIÓN |
| Notas de crédito | NC, vinculación con factura | VALIDADO |
| Anulaciones | Cancellation lifecycle | VALIDADO |
| Clientes | Maestro de clientes | VALIDADO |
| Vendedores | Maestro de vendedores | VALIDADO |

### 4.2 Temporalidad SAP

| Vista | Pregunta | Estado |
|-------|----------|--------|
| AS-REPORTED | ¿Qué se sabía en esa fecha? | VALIDADO |
| RESTATED | ¿Cuál es el valor económico válido hoy? | VALIDADO |
| EVENTS | ¿Qué cambios ocurrieron en este período? | VALIDADO |

---

## 5. Estado de Validación

### 5.1 Gates Cerrados

| Gate | Estado | Fecha |
|------|--------|-------|
| `TELCHI_FINANCIAL_INVOICE_CONTRACT_PASS` | ✅ PASS | 2026-08-20 |
| `TELCHI_FINANCIAL_CREDIT_NOTE_PASS` | ✅ PASS | 2026-08-20 |
| `TELCHI_FINANCIAL_PAYMENT_APPLICATION_PASS` | ✅ PASS | 2026-08-20 |
| `TELCHI_FINANCIAL_RECONCILIATION_PASS` | ✅ PASS | 2026-08-20 |
| `TELCHI_FINANCIAL_CURRENT_AR_PASS` | ✅ PASS | 2026-08-21 |
| `TELCHI_TEMPORAL_CANCELLATION_SEMANTICS_PASS` | ✅ PASS | 2026-08-23 |
| `TELCHI_TEMPORAL_PAYMENT_CANCELLATION_PASS` | ✅ PASS | 2026-08-23 |
| `TELCHI_TEMPORAL_RECONCILIATION_CANCELLATION_PASS` | ✅ PASS | 2026-08-23 |
| `TELCHI_TEMPORAL_MODEL_ARCHITECTURE_PASS` | ✅ PASS | 2026-08-23 |

### 5.2 Hallazgos Confirmados

| Hallazgo | Evidencia |
|----------|-----------|
| 93.4% de anulaciones ocurren 31-90 días después | Distribución de timing |
| cancellation_date = OINV.UpdateDate | 100% cobertura |
| cancellation_time = OINV.UpdateTS | Precisión HHMMSS |
| Pares Y/C vinculados por CardCode + DocTotal | Casos reales |
| Pagos anulados existen (0.6%) | 10,689 pagos |
| Reconciliaciones anuladas existen (0.7%) | 14,849 reconciliaciones |

---

## 6. Temporalidad SAP

### 6.1 Hallazgo Crítico

```text
Filtrar o sincronizar solamente por DocDate es incorrecto.
```

Una factura de marzo puede sufrir una mutación económica relevante en junio:

```text
15/03 factura válida
31/03 aparece en los reportes
20/06 SAP la anula
```

### 6.2 Consecuencia Arquitectónica

El módulo Telchi SAP debe distinguir:

```text
fecha de negocio
fecha de modificación/evento
estado actual
estado histórico as-of
```

### 6.3 Tres Vistas Temporales

| Vista | Pregunta | Implementación |
|-------|----------|----------------|
| AS-REPORTED | ¿Qué se sabía en esa fecha? | Filtrar por DocDate, excluir anulaciones futuras |
| RESTATED | ¿Cuál es el valor económico válido hoy? | Usar cancellation_date para excluir anuladas |
| EVENTS | ¿Qué cambios ocurrieron en este período? | Incluir creaciones Y anulaciones |

---

## 7. Decisiones Arquitectónicas

| ID | Decisión | Evidencia |
|----|----------|-----------|
| TELCHI-DEC-001 | DataScience separado de Team360 | Arquitectura |
| TELCHI-DEC-002 | HANA es fuente actual | Validación |
| TELCHI-DEC-003 | Legacy es baseline semántica | Inspección de código |
| TELCHI-DEC-004 | Sin Parquet nuevos aún | Política |
| TELCHI-DEC-005 | Podman lifecycle manual | Política |
| TELCHI-DEC-006 | IDs SAP primero | Todas las validaciones |
| TELCHI-DEC-007 | OINV.DocEntry financial grain | FINANCIAL-001 |
| TELCHI-DEC-008 | ORIN DocTotal positivo raw | FINANCIAL-002 |
| TELCHI-DEC-009 | RCT2 no es authority de settlement | FINANCIAL-003 |
| TELCHI-DEC-010 | OITR/ITR1 es settlement layer | FINANCIAL-004 |
| TELCHI-DEC-011 | Reconciled ≠ cash paid | FINANCIAL-004 |
| TELCHI-DEC-012 | BaseType=16 es A/R Return | FINANCIAL-002 |
| TELCHI-DEC-013 | PaidToDate authority | FINANCIAL-001 |
| TELCHI-DEC-014 | Canceled Y/C pair pattern | FINANCIAL-001 |
| TELCHI-DEC-015 | DocCur vs DocCurrency | Schema |
| TELCHI-DEC-016 | Sin heuristic document pairing | FINANCIAL-004 |
| TELCHI-DEC-017 | Settlement = ITR1 ReconSum SrcObjTyp=13 | FINANCIAL-005 |
| TELCHI-DEC-018 | March 2023 outlier = AP_ACTIVITY | FINANCIAL-005 |
| TELCHI-DEC-019 | Reconciliation balance = credit vs debit | FINANCIAL-005 |
| TELCHI-DEC-020 | HANA usa DAYS_BETWEEN | SQL validation |
| TELCHI-DEC-021 | Database name es NDB | Connectivity |

---

## 8. Evidencia SAP

### 8.1 Trazabilidad

Todo finding debe terminar en evidencia SAP:

```
Finding
   ↓
Explicación
   ↓
Documento / operación
   ↓
SAP (DocEntry, DocNum, TransId, ReconNum, LineNum)
```

### 8.2 Identificadores SAP

| Identificador | Tabla | Propósito |
|---------------|-------|-----------|
| DocEntry | OINV, ORIN, ORCT | PK documento |
| LineNum | INV1, RIN1 | Identidad línea |
| ReconNum | OITR, ITR1 | Identidad reconciliación |
| SlpCode | OINV, ORIN, OSLP | Identidad vendedor |
| CardCode | OINV, ORIN, ORCT, OCRD | Identidad cliente |
| TransId | ORCT, ITR1 | ID transacción contable |
| SrcObjAbs | ITR1 | DocEntry objeto fuente |
| SrcObjTyp | ITR1 | Tipo objeto fuente |

---

## 9. Tests Existentes

| Test | Propósito | Estado |
|------|-----------|--------|
| T03 | Invoice cancellation March→June | PASS (parcial) |
| T04 | Late cancellation >30 days | PASS |
| T05 | Payment cancellation | PENDIENTE |
| T06 | Partial payments | PENDIENTE |
| T07 | Multi-invoice payment | PENDIENTE |
| T08 | Credit note linkage | PENDIENTE |
| T09 | Reconciliation | PENDIENTE |
| T10 | Aging as-of | PENDIENTE |

---

## 10. Limitaciones

| Limitación | Impacto | Mitigación |
|------------|---------|------------|
| Multicurrency no modelada | Bajo | Fase posterior |
| Pagos parciales no investigados | Medio | Próxima fase |
| Notas de crédito en detalle | Medio | Próxima fase |
| Cohorts no implementados | Bajo | Próxima fase |

---

## 11. Próxima Fase

Una vez corregida la identidad modular, el siguiente trabajo será:

```text
TELCHI SAP
Ventas + Caja + Crédito + Cobranzas

1. pagos parciales
2. aplicaciones/reconciliaciones
3. notas de crédito
4. crédito/deudores
5. cohorts de cobranza
6. seller metrics
7. findings combinados
```

---

## 12. Separación de Flow

```text
Flow:
módulo independiente.
No forma parte de Telchi SAP.
No se modifica en este ciclo.
```

El único motivo para mencionar Flow es aclarar el límite modular.

---

## 13. Workspace

| Componente | Valor |
|------------|-------|
| Workspace | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi` |
| Baseline legacy | `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/` |
| Git | NO commits en este ciclo |
| HANA | READ ONLY |
| Parquet | READ ONLY |

---

**Telchi SAP — Módulo de integración con SAP Business One de Telchi.**

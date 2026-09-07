# TELCHI SAP — INVESTIGACIÓN FASE 0: HALLAZGOS COMPLETOS

**Módulo:** Telchi SAP
**Capa:** DataScience — Temporalidad SAP
**Fecha:** 2026-08-23
**Estado:** INVESTIGACIÓN INICIAL COMPLETA
**Resultado:** ARQUITECTURA TEMPORAL VALIDADA

---

## 1. HALLAZGOS CRÍTICOS

### 1.1 FACTURAS ANULADAS

| Métrica | Valor |
|---------|-------|
| Total facturas | 1,814,926 |
| Facturas válidas (N) | 1,812,698 |
| Facturas anuladas (Y) | 1,114 |
| Documentos reversión (C) | 1,114 |
| Tasa anulación | 0.06% |
| Monto anulado | $609,724 |

### 1.2 TIMING DE ANULACIÓN

| Bucket | Count | % | Monto |
|--------|-------|---|-------|
| 0 días | 40 | 3.6% | $37,855 |
| 1-7 días | 3 | 0.3% | $4,367 |
| 8-30 días | 29 | 2.6% | $31,511 |
| **31-90 días** | **1,040** | **93.4%** | **$526,214** |
| 91-365 días | 2 | 0.2% | $9,777 |

**CRÍTICO:** 93.4% de anulaciones ocurren 31-90 días después de la factura original.

### 1.3 CASOS REALES DE ANULACIONES TARDÍAS

| DocEntry | Cliente | DocDate | CancelDate | Días | Importe |
|----------|---------|---------|------------|------|---------|
| 9788778 | FARMACIA MIRIAM | 2024-06-03 | 2024-10-04 | 123 | $777 |
| 10247003 | GENÉRICO MENONAS | 2024-05-14 | 2024-08-30 | 108 | $9,000 |
| 9816788 | CORI PERNOS | 2024-05-02 | 2024-07-24 | 83 | $5,761 |
| 9823420 | CORI PERNOS | 2024-05-02 | 2024-07-24 | 83 | $5,302 |
| 9795346 | SCHMITT PETERS | 2024-05-07 | 2024-07-22 | 76 | $1,272 |

### 1.4 PAGOS ANULADOS

| Métrica | Valor |
|---------|-------|
| Total pagos | 1,793,073 |
| Pagos válidos (N) | 1,782,384 |
| Pagos anulados (Y) | 10,689 |
| Tasa anulación | 0.6% |
| Monto anulado | $14,584,699 |

### 1.5 RECONCILIACIONES ANULADAS

| Métrica | Valor |
|---------|-------|
| Total reconciliaciones | 2,068,564 |
| Reconciliaciones válidas (N) | 2,038,866 |
| Reconciliaciones anuladas (Y) | 14,849 |
| Reconciliaciones reversión (C) | 14,849 |
| Tasa anulación | 0.7% |
| Monto anulado | $470,966,647 |

---

## 2. MODELO DE ANULACIÓN SAP

### 2.1 Patrón Y/C

```
FACTURA ORIGINAL (Y)
  DocEntry: 9788778
  DocDate: 2024-06-03
  UpdateDate: 2024-10-04  ← FECHA DE ANULACIÓN
  UpdateTS: 170858        ← HORA: 17:08:58
  CANCELED: Y

DOCUMENTO REVERSIÓN (C)
  DocEntry: 10324108
  DocDate: 2024-06-03     ← Misma fecha que original
  UpdateDate: 2024-10-04
  UpdateTS: 170905        ← 7 segundos después del Y
  CANCELED: C
  TransId: 12910681       ← Diferente al original
```

### 2.2 Campos Clave

| Campo | Descripción | Uso |
|-------|-------------|-----|
| `CANCELED` | N=válido, Y=anulado, C=reversión | Identificar estado |
| `UpdateDate` | Fecha última actualización | **Fecha de anulación** |
| `UpdateTS` | Timestamp HHMMSS | **Hora de anulación** |
| `TransId` | ID transacción contable | Vincular asientos |

### 2.3 Regla de Vinculación Y/C

```sql
Y."CardCode" = C."CardCode"
AND Y."DocTotal" = C."DocTotal"
AND C."CANCELED" = 'C'
AND ABS(DAYS_BETWEEN(Y."UpdateDate", C."DocDate")) <= 7
```

---

## 3. CADENA DE RECONCILIACIÓN

### 3.1 Pago Anulado

```
PAGO (DocEntry=2321506, Canceled=Y)
  ↓
RECONCILIACIÓN ORIGINAL (ReconNum=2602808, Canceled=Y)
  - Invoice (SrcObjTyp=13): +$30.90 (D)
  - Payment (SrcObjTyp=24): -$30.90 (C)
  ↓
REVERSIÓN (ReconNum=2602811, Canceled=C)
  - Invoice (SrcObjTyp=13): -$30.90
  ↓
NUEVA RECONCILIACIÓN (ReconNum=2602812, Canceled=N)
  - Invoice (SrcObjTyp=13): +$30.90
  - Payment (SrcObjTyp=24): -$30.90
```

### 3.2 Implicación

Cuando un pago es anulado:
1. La reconciliación original se marca como Y
2. Se crea una reversión (C) que deshace el efecto
3. Se crea una nueva reconciliación (N) si es necesario

---

## 4. CAMPOS DERIVADOS PARA MODELO TEMPORAL

### 4.1 Para Facturas

```sql
-- Cancellation date derivation
CASE WHEN OINV."CANCELED" = 'Y'
     THEN OINV."UpdateDate"
     ELSE NULL END AS "CancellationDate",

CASE WHEN OINV."CANCELED" = 'Y'
     THEN OINV."UpdateTS"
     ELSE NULL END AS "CancellationTimestamp",

DAYS_BETWEEN(OINV."DocDate", OINV."UpdateDate") AS "DaysToCancellation"
```

### 4.2 Para Pagos

```sql
-- Payment cancellation derivation
CASE WHEN ORCT."Canceled" = 'Y'
     THEN ORCT."UpdateDate"
     ELSE NULL END AS "CancellationDate",

CASE WHEN ORCT."Canceled" = 'Y'
     THEN ORCT."UpdateTS"
     ELSE NULL END AS "CancellationTimestamp"
```

### 4.3 Para Reconciliaciones

```sql
-- Reconciliation cancellation derivation
CASE WHEN OITR."Canceled" = 'Y'
     THEN OITR."ReconDate"
     ELSE NULL END AS "CancellationDate"
```

---

## 5. TRES VISTAS TEMPORALES

### 5.1 AS-REPORTED (Histórica)

**Pregunta:** ¿Qué sabíamos en fecha X?

```sql
-- Filtrar solo por DocDate
WHERE DocDate <= :fecha
  AND (CANCELED = 'N' OR UpdateDate > :fecha)
```

**Ejemplo:** Al 31/03/2024, la factura de junio 2024 NO existe todavía.

### 5.2 RESTATED (Verdad Económica Actual)

**Pregunta:** ¿Qué es verdad HOY?

```sql
-- Excluir anuladas conocidas
WHERE DocDate <= :fecha
  AND (CANCELED = 'N' OR UpdateDate > :fecha)
  -- Opcionalmente: excluir canceladas después
  AND NOT (CANCELED = 'Y' AND UpdateDate <= :fecha_actual)
```

**Ejemplo:** Hoy, la factura de junio 2024 ANULADA en octubre NO forma parte de ventas válidas.

### 5.3 EVENTS (Movimientos)

**Pregunta:** ¿Qué ocurrió en cada período?

```sql
-- Creaciones
SELECT 'CREATED' AS Event, DocDate AS EventDate, DocTotal AS Amount
FROM OINV WHERE DocDate BETWEEN :inicio AND :fin

UNION ALL

-- Anulaciones
SELECT 'CANCELED' AS Event, UpdateDate AS EventDate, -DocTotal AS Amount
FROM OINV WHERE CANCELED = 'Y' AND UpdateDate BETWEEN :inicio AND :fin
```

---

## 6. SQL CREADOS

| Archivo | Descripción | Grain |
|---------|-------------|-------|
| `invoice_cancellation_lifecycle_v1.sql` | Timeline facturas | DocEntry |
| `payment_cancellation_lifecycle_v1.sql` | Timeline pagos | DocEntry |
| `as_of_ar_reconstruction_v1.sql` | AR por fecha | DocEntry |
| `test_T03_invoice_cancellation.sql` | Test marzo→junio | — |

---

## 7. VALIDACIONES PENDIENTES

| Test | Descripción | Estado |
|------|-------------|--------|
| T03 | Invoice cancellation March→June | PARCIAL (no hay caso 2026) |
| T04 | Late cancellation >30 days | PASS (casos reales encontrados) |
| T05 | Payment cancellation | PENDIENTE |
| T06 | Partial payments | PENDIENTE |
| T07 | Multi-invoice payment | PENDIENTE |
| T08 | Credit note linkage | PENDIENTE |
| T09 | Reconciliation | PENDIENTE |
| T10 | Aging as-of | PENDIENTE |

---

## 8. PRÓXIMOS PASOS

### INMEDIATOS
1. Crear SQL de cohort collections
2. Crear SQL de seller + collection metrics
3. Investigar pagos parciales
4. Investigar notas de crédito en detalle

### CORTO PLAZO
1. Implementar aging histórico
2. Implementar cohort analysis
3. Implementar seller metrics
4. Implementar credit analysis

---

## 9. CRITERIO DE PASS FASE 0

- [x] Fecha de anulación derivada de SAP ✓
- [x] Anulaciones tardías detectadas ✓
- [x] Pares Y/C vinculados ✓
- [x] Pagos anulados identificados ✓
- [x] Reconciliaciones anuladas identificadas ✓
- [x] Cadena de reconciliación documentada ✓
- [x] Tres vistas temporales definidas ✓
- [ ] Cohort collections implementadas
- [ ] Seller metrics implementadas
- [ ] Aging histórico implementado

---

**Gate:** `TELCHI_TEMPORAL_CANCELLATION_SEMANTICS_PASS`

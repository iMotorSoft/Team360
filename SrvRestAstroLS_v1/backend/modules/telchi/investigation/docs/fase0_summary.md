# TELCHI SAP — RESUMEN EJECUTIVO: INVESTIGACIÓN FASE 0

**Módulo:** Telchi SAP
**Capa:** DataScience — Ventas, Cobranzas, Crédito, Temporalidad SAP
**Fecha:** 2026-08-23
**Estado:** INVESTIGACIÓN INICIAL COMPLETA
**Resultado:** HALLAZGOS CRÍTICOS CONFIRMADOS

---

## 1. HALLAZGOS PRINCIPALES

### HALLAZGO 1: 93.4% DE ANULACIONES OCURREN 31-90 DÍAS DESPUÉS

| Bucket | Count | % | Monto |
|--------|-------|---|-------|
| 0 días (mismo día) | 40 | 3.6% | $37,855 |
| 1-7 días | 3 | 0.3% | $4,367 |
| 8-30 días | 29 | 2.6% | $31,511 |
| **31-90 días** | **1,040** | **93.4%** | **$526,214** |
| 91-365 días | 2 | 0.2% | $9,777 |
| **TOTAL** | **1,114** | **100%** | **$609,724** |

**IMPLICACIÓN:** Si solo miramos `DocDate`, perdemos el 93.4% de las anulaciones.

### HALLAZGO 2: UpdateDate + UpdateTS = FECHA DE ANULACIÓN

- **UpdateDate**: Fecha de la última actualización del documento
- **UpdateTS**: Timestamp con precisión de segundos (formato HHMMSS)
- **Cobertura**: 100% de facturas anuladas

### HALLAZGO 3: PARES Y/C VINCULADOS

| Campo | Y (Original) | C (Reversión) | ¿Coincide? |
|-------|--------------|---------------|------------|
| CardCode | ✓ | ✓ | Sí |
| DocTotal | ✓ | ✓ | Sí |
| DocEntry | Diferente | Diferente | No |
| TransId | Diferente | Diferente | No |
| UpdateTS | 17:08:58 | 17:09:05 | 7 segundos diferencia |

### HALLAZGO 4: CASOS REALES DE ANULACIONES TARDÍAS

#### Caso 1: DocEntry 9788778
```
Fecha factura:    2024-06-03
Fecha anulación:  2024-10-04
Días:             123 días (4 meses!)
Cliente:          FARMACIA MIRIAM
Importe:          $777.00
Pago:             Sí (PaidToDate = DocTotal)
```

#### Caso 2: DocEntry 10247003
```
Fecha factura:    2024-05-14
Fecha anulación:  2024-08-30
Días:             108 días (3.5 meses!)
Cliente:          GENÉRICO MENONAS
Importe:          $9,000.00
Pago:             Sí (PaidToDate = DocTotal)
```

#### Caso 3: DocEntry 9816788
```
Fecha factura:    2024-05-02
Fecha anulación:  2024-07-24
Días:             83 días (2.7 meses!)
Cliente:          CORI PERNOS
Importe:          $5,760.99
Pago:             Sí (PaidToDate = DocTotal)
```

### HALLAZGO 5: PAGOS ANULADOS EXISTEN

- **Pagos válidos (N):** 1,782,379 ($495M)
- **Pagos anulados (Y):** 10,689 ($14.5M)
- **Tasa de anulación:** 0.6%

### HALLAZGO 6: RECONCILIACIONES ANULADAS EXISTEN

- **Reconciliaciones válidas (N):** 2,038,861 ($7.1B)
- **Reconciliaciones anuladas (Y):** 14,849 ($470M)
- **Tasa de anulación:** 0.7%

---

## 2. MODELO TEMPORAL VALIDADO

### Tres Vistas

```
1. AS-REPORTED (Histórica)
   - Qué sabíamos en fecha X
   - Usa DocDate para filtrar
   - NO incluye anulaciones futuras

2. RESTATED (Verdad Económica Actual)
   - Qué es verdad HOY
   - Usa cancellation_date para excluir anuladas
   - SÍ incluye anulaciones conocidas

3. EVENTS (Movimientos)
   - Qué ocurrió en cada período
   - Incluye creaciones Y anulaciones
   - Permite reconstruir timeline
```

### Campos Derivados

```sql
cancellation_date = OINV.UpdateDate (cuando CANCELED = 'Y')
cancellation_time = OINV.UpdateTS (formato HHMMSS)
cancellation_timestamp = UpdateDate + UpdateTS
```

---

## 3. SQL CREADOS

| Archivo | Descripción | Estado |
|---------|-------------|--------|
| `invoice_cancellation_lifecycle_v1.sql` | Timeline de facturas | CREADO |
| `payment_cancellation_lifecycle_v1.sql` | Timeline de pagos | CREADO |
| `as_of_ar_reconstruction_v1.sql` | AR por fecha histórica | CREADO |
| `test_T03_invoice_cancellation.sql` | Test marzo → junio | CREADO |
| `test_T03_invoice_cancellation.py` | Validación Python | CREADO |

---

## 4. PRÓXIMOS PASOS

### INMEDIATOS (Completar Fase 0)
1. Investigar reconciliaciones anuladas en detalle
2. Investigar pagos anulados en detalle
3. Crear SQL de cohort collections
4. Crear SQL de seller + collection metrics

### CORTO PLAZO (Fase 1)
1. ValidarCancellation Lifecycle completo
2. ValidarPayment Lifecycle completo
3. Crear test de late cancellation
4. Crear test de payment cancellation

### MEDIANO PLAZO (Fase 2)
1. Implementar as-of AR reconstruction
2. Implementar cohort analysis
3. Implementar seller metrics
4. Implementar aging histórico

---

## 5. CRITERIO DE ÉXITO

Para considerar PASS la Fase 0:

- [x] Fecha de anulación derivada de SAP (UpdateDate) ✓
- [x] Anulaciones tardías (>30 días) detectadas ✓
- [x] Pares Y/C vinculados ✓
- [x] Pagos anulados identificados ✓
- [x] Reconciliaciones anuladas identificadas ✓
- [ ] Reconciliaciones anuladas investigadas en detalle
- [ ] Pagos anulados investigados en detalle
- [ ] Cohort collections implementadas
- [ ] Seller metrics implementadas

---

## 6. IMPACTO EN ANÁLISIS

### Lo que CAMBIA con este hallazgo:

1. **Ventas históricas** deben usar `cancellation_date` para excluir anuladas
2. **Aging histórico** debe reconstruirse usando información disponible en cada fecha
3. **Cohorts** deben excluir facturas canceladas después del período
4. **Seller metrics** deben incluir impacto de cancelaciones tardías
5. **AR reconciliation** debe considerar cancelaciones post-reconciliación

### Lo que NO cambia:

1. La fórmula `Outstanding = DocTotal - TotalSettlement` sigue siendo válida
2. El grain `OINV.DocEntry` sigue siendo correcto
3. Los IDs SAP siguen siendo la fuente de verdad
4. El patrón Y/C sigue siendo el mecanismo de anulación

---

## 7. RIESGOS IDENTIFICADOS

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| UpdateDate no siempre = fecha anulación real | Medio | Usar C.DocDate como alternativa |
| Reconciliaciones anuladas pueden afectar AR | Alto | Investigar en detalle |
| Pagos anulados pueden afectar cobranza | Alto | Investigar en detalle |
| Multicurrency no modelada aún | Bajo | Fase posterior |

---

**Próximo gate:** `TELCHI_TEMPORAL_CANCELLATION_SEMANTICS_PASS`

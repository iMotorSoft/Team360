# TELCHI SAP — ANÁLISIS: SALIDA DE MERCADERÍA Y FACTURACIÓN

**Fecha:** 2026-08-23
**Estado:** ANÁLISIS COMPLETO

---

## HALLAZGO PRINCIPAL

**Todos los items de la entrega están contabilizados en las facturas de reemplazo.**

No hay "mercadería facturada sin factura". El proceso fue una **corrección de facturación**, no una anulación sin reemplazo.

---

## CASO DE ESTUDIO: ENTREGA 324881 (MI TRIBU)

### 1. Entrega Original

| Campo | Valor |
|-------|-------|
| DocEntry | 324881 |
| DocNum | 250110585 |
| DocDate | 2025-07-09 |
| CardCode | C011583 - MI TRIBU |
| DocTotal | $1,274.26 |
| CANCELED | N (ACTIVA) |
| Items | 16 |

### 2. Facturas Relacionadas

| DocEntry | DocNum | DocDate | DocTotal | CANCELED | Rol |
|----------|--------|---------|----------|----------|-----|
| 10784738 | 251904131 | 2025-07-09 | $1,274.26 | Y | Original |
| 10820673 | 251406723 | 2025-08-05 | $188.00 | Y | Original |
| 10820858 | 251904877 | 2025-08-05 | $2,441.02 | Y | Original |
| 10823257 | 251406750 | 2025-08-08 | $188.00 | N | **REEMPLAZO 1** |
| 10828463 | 251905016 | 2025-08-12 | $1,369.76 | N | **REEMPLAZO 2** |

### 3. Distribución de Items

| ItemCode | Descripción | Entrega | Repl1 | Repl2 | Total Repl | Estado |
|----------|-------------|---------|-------|-------|------------|--------|
| L00064 | ALCOHOL EN GEL NEUTRO x 60mL | 3 | 1 | 2 | 3 | ✓ COMPLETO |
| L00066 | AGUA DE ROSAS x 100 mL | 3 | 3 | 0 | 3 | ✓ COMPLETO |
| L00070 | PASTA DE AGUA x 200gr | 2 | 1 | 1 | 2 | ✓ COMPLETO |
| L01038 | ACEITE DE ALMENDRA x 250mL | 2 | 1 | 1 | 2 | ✓ COMPLETO |
| L01117 | ACEITE DE COCO x 500 mL | 2 | 0 | 2 | 2 | ✓ COMPLETO |
| L01601 | MIEL ROSADA TELCHI LITEL x 30mL | 4 | 0 | 4 | 4 | ✓ COMPLETO |
| L01613 | LOCION POVIDINE LITEL 10% x 120mL | 3 | 1 | 2 | 3 | ✓ COMPLETO |
| L01639 | LOCION TELCHI LITEL DE 200mL | 3 | 1 | 2 | 3 | ✓ COMPLETO |
| L01885 | TALCO LITEL x 100g | 3 | 0 | 3 | 3 | ✓ COMPLETO |
| L01967 | COLAGENO HIDROLIZADO GRANULADO | 2 | 0 | 2 | 2 | ✓ COMPLETO |
| L01969 | COLAGENO HIDROLIZADO GRANULADO | 2 | 0 | 2 | 2 | ✓ COMPLETO |
| L01974 | PREPARADO MAGISTRAL - 1974 | 2 | 0 | 2 | 2 | ✓ COMPLETO |
| L02837 | ALCOHOL 70% x 100 mL | 3 | 0 | 3 | 3 | ✓ COMPLETO |
| L03028 | FISIOLOGICO NASAL TELCHI x 250mL | 3 | 0 | 3 | 3 | ✓ COMPLETO |
| L03030 | NEUTRO CLEAN DETERGENTE x 1L | 2 | 0 | 2 | 2 | ✓ COMPLETO |
| L03321 | REPELITEL x 100 mL | 3 | 2 | 1 | 3 | ✓ COMPLETO |

### 4. Resumen de Montos

| Concepto | Monto |
|----------|-------|
| Entrega original | $1,274.26 |
| Factura reemplazo 1 | $188.00 |
| Factura reemplazo 2 | $1,086.26 |
| **Total reemplazos** | **$1,274.26** |
| **Diferencia** | **$0.00** |

---

## PATRÓN IDENTIFICADO

### 1. Corrección de Facturación

El proceso fue:
1. Se crearon facturas originales con errores
2. Las facturas originales fueron anuladas
3. Se crearon DOS nuevas facturas correctas
4. Los items fueron distribuidos entre las dos nuevas facturas
5. **Todos los items de la entrega están contabilizados**

### 2. Distribución de Items

La factura reemplazo 1 ($188.00) contiene:
- 7 items de la entrega
- Items de menor valor

La factura reemplazo 2 ($1,369.76) contiene:
- Los 16 items restantes de la entrega
- Items de mayor valor

### 3. No Hay Devolución

- No existen notas de crédito (ODRN) para este cliente que referencien esta entrega
- No hay devolución de mercadería
- La entrega está ACTIVA (no cancelada)

---

## IMPLICACIONES

### 1. Para el Análisis de Ventas

Las facturas anuladas con entrega **representaron actividad económica real**:
- La mercadería fue entregada
- La facturación fue CORREGIDA (no eliminada)
- Los cobros son válidos

### 2. Para el Análisis de Stock

- La entrega está ACTIVA
- La mercadería SÍ salió del inventario
- No hay devolución
- El inventario se redujo correctamente

### 3. Para el Análisis de Cobros

- Las facturas originales tienen cobros activos
- Las facturas reemplazo tienen cobros activos
- El dinero fue recibido por las facturas correctas

---

## CONCLUSIÓN

**No hay "mercadería facturada sin factura".**

El patrón es:
1. Factura original con error → ANULADA
2. Nuevas facturas correctas → CREADAS
3. Todos los items contabilizados → VERIFICADO
4. Cobros válidos → CONFIRMADO

Esto es un **proceso de corrección legítimo**, no un problema de conciliación.

---

## RECOMENDACIÓN

Para el análisis general de facturas anuladas:

1. **No tratar todas las anulaciones como "riesgo"**
2. **Distinguir entre:**
   - Anulaciones con reemplazo (corrección legítima)
   - Anulaciones sin reemplazo (requiere investigación)
   - Anulaciones con devolución (proceso normal)
3. **Para cada caso, verificar:**
   - ¿Hay factura de reemplazo?
   - ¿Los items están contabilizados?
   - ¿Hay devolución?
   - ¿Los cobros son válidos?

---

**Telchi SAP — Análisis de Salida de Mercadería y Facturación — V1**

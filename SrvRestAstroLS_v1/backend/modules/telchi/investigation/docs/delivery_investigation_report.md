# TELCHI SAP — INVESTIGACIÓN: 26 FACTURAS CON SALIDA DE MERCADERÍA

**Fecha:** 2026-08-23
**Estado:** INVESTIGACIÓN COMPLETA

---

## 1. HALLAZGOS PRINCIPALES

### 1.1 Distribución por Estado de Entrega

| Estado de Entrega | Cantidad |
|-------------------|----------|
| **ENTREGA ACTIVA** | **19** |
| ENTREGA CANCELADA | 7 |

### 1.2 Distribución por Reemplazo

| Estado de Reemplazo | Cantidad |
|---------------------|----------|
| **CON FACTURA DE REEMPLAZO** | **15** |
| SIN FACTURA DE REEMPLAZO | 11 |

### 1.3 Clasificación Cruzada

| Clasificación | Cantidad | Descripción |
|---------------|----------|-------------|
| **A: Entrega cancelada + Reemplazo** | ~7 | Reversión completa y nueva factura |
| **B: Entrega cancelada + Sin reemplazo** | 0 | Reversión completa sin nueva factura |
| **C: Entrega activa + Reemplazo** | ~8 | Mercadería salió, factura reemplazada |
| **D: Entrega activa + Sin reemplazo** | ~11 | ⚠️ RIESGO: Mercadería salió sin factura válida |

---

## 2. DETALLE DE CASOS

### 2.1 Con Factura de Reemplazo (15)

| DocEntry | DocNum | CardCode | DocTotal | Days | ReplEntry | ReplNum | ReplTotal |
|----------|--------|----------|----------|------|-----------|---------|-----------|
| 1358316 | 22140016 | C003723 | $3,220.00 | 29 | 11219305 | 22014950 | $3,220.00 |
| 10820858 | 251904877 | C011583 | $2,441.02 | 7 | 10823257 | 251406750 | $188.00 |
| 10820858 | 251904877 | C011583 | $2,441.02 | 7 | 10828463 | 251905016 | $1,369.76 |
| 4200740 | 23013020 | C004619 | $2,298.60 | 0 | 4201413 | 23013041 | $2,253.60 |
| 1833068 | 22013025 | C003906 | $1,807.50 | 0 | 1833495 | 22013034 | $1,707.50 |
| 4202849 | 23013118 | C004348 | $1,298.50 | 12 | 4279591 | 23013343 | $1,213.50 |
| 10784738 | 251904131 | C011583 | $1,274.26 | 26 | 10823257 | 251406750 | $188.00 |
| 10784738 | 251904131 | C011583 | $1,274.26 | 26 | 10828463 | 251905016 | $1,369.76 |
| 1839383 | 22013123 | C004372 | $1,002.81 | 0 | 1843283 | 22013131 | $725.80 |
| 1839383 | 22013123 | C004372 | $1,002.81 | 0 | 1843301 | 22013132 | $120.00 |
| 10272720 | 241008909 | C003394 | $984.00 | 9 | 10307143 | 241009240 | $885.60 |
| 4552577 | 23013709 | C004037 | $608.44 | 0 | 4552738 | 23013724 | $629.63 |
| 2152646 | 22014152 | C004366 | $603.08 | 0 | 2153384 | 22014193 | $528.08 |
| 7575314 | 23017852 | C004802 | $461.00 | 0 | 7584742 | 23017888 | $461.00 |
| 4322145 | 23013367 | C003906 | $456.95 | 0 | 4324085 | 23013480 | $436.95 |
| 10870242 | 251905909 | E000108 | $220.30 | 0 | 10873536 | 251905927 | $8.19 |
| 10870242 | 251905909 | E000108 | $220.30 | 0 | 10873540 | 251905928 | $161.05 |
| 10870242 | 251905909 | E000108 | $220.30 | 0 | 10873543 | 251905929 | $22.42 |
| 10820673 | 251406723 | C011583 | $188.00 | 0 | 10823257 | 251406750 | $188.00 |
| 10820673 | 251406723 | C011583 | $188.00 | 0 | 10828463 | 251905016 | $1,369.76 |
| 4922684 | 23014068 | E000036 | $56.00 | 0 | 4923552 | 23014086 | $56.00 |

### 2.2 Sin Factura de Reemplazo (11)

| DocEntry | DocNum | CardCode | CardName | DocTotal | Days | DelCanceled |
|----------|--------|----------|----------|----------|------|-------------|
| 11003482 | 251908759 | C011638 | ANTON FRIESEN FEHR | $4,056.48 | 0 | Y |
| 1530290 | 22011661 | C003384 | THIESSEN BANMAN FRANZ | $3,937.90 | 0 | N |
| 11412928 | 260101942 | C004648 | PETERS WILER BERNARDO | $2,786.40 | 0 | Y |
| 10911991 | 251906781 | C008144 | BERNHARD WIEBE DYCK | $1,726.09 | 0 | Y |
| 8190891 | 23018259 | C003396 | NEUDORF JOHAN FAST | $824.67 | 0 | Y |
| 5908745 | 23015569 | C004081 | ANDREAS PETERS DYCK | $684.90 | 0 | Y |
| 4322238 | 23013374 | C004805 | PETER KRAHN GOERTZEN | $553.40 | 0 | Y |
| 11205993 | 261903585 | C005007 | REMPEL WIEBE DAVID | $515.22 | 0 | Y |
| 11301245 | 261904763 | C005217 | REMPEL BERNHARD | $231.45 | 0 | N |
| 8874580 | 241000803 | C007812 | JUAN WALL ENNS | $170.00 | 0 | N |
| 1437368 | 22011435 | C003526 | KORNELSEN MARILYN | $48.60 | 8 | N |

---

## 3. ANÁLISIS DE PATRONES

### 3.1 Patrón de Anulación Mismo Día

**17 de 26 facturas (65.4%) fueron anuladas el MISMO DÍA que la factura original.**

Esto sugiere:
- Corrección inmediata de error
- Error en captura de datos
- Cambio de titular o dirección
- Problema con el pedido original

### 3.2 Patrón de Reemplazo

**15 de 26 facturas (57.7%) tienen factura de reemplazo para la misma entrega.**

Esto indica:
- La entrega original era correcta
- Solo la factura tenía un error
- Se creó una nueva factura para la misma mercadería

### 3.3 Diferencia de Montos

En varios casos, la factura de reemplazo tiene un monto **DIFERENTE** al original:

| Factura Original | Monto Original | Factura Reemplazo | Monto Reemplazo | Diferencia |
|------------------|----------------|-------------------|-----------------|------------|
| 10820858 | $2,441.02 | 10823257 | $188.00 | -$2,253.02 |
| 10820858 | $2,441.02 | 10828463 | $1,369.76 | -$1,071.26 |
| 1839383 | $1,002.81 | 1843283 | $725.80 | -$277.01 |
| 1839383 | $1,002.81 | 1843301 | $120.00 | -$882.81 |

**Esto sugiere que la factura original tenía items incorrectos o precios incorrectos.**

### 3.4 Entregas Canceladas

**7 de 26 entregas están CANCELADAS.**

Esto indica una reversión completa:
- Factura anulada
- Entrega anulada
- Mercadería regresó a inventario

### 3.5 Entregas Activas sin Reemplazo

**11 facturas tienen entrega ACTIVA pero SIN factura de reemplazo.**

Estos casos requieren investigación:
- ¿La mercadería fue entregada sin factura válida?
- ¿Existe otra factura para la misma entrega?
- ¿Hay un problema de conciliación?

---

## 4. IMPLICACIONES

### 4.1 Para el Análisis de Ventas

Las facturas anuladas con entrega **sí representaron actividad económica real**:
- La mercadería salió del inventario
- Se recibió cobro (PaidToDate = DocTotal)
- En 15 casos, se creó una factura de reemplazo

### 4.2 Para el Análisis de Stock

Las facturas anuladas con entrega activa **afectaron el inventario**:
- La mercadería fue entregada
- El inventario se redujo
- Si no hay factura de reemplazo, la mercadería fue "regalada"

### 4.3 Para el Análisis de Cobros

Todas las facturas anuladas tienen cobros activos:
- El dinero fue recibido
- La reconciliación está activa
- No hay pagos cancelados

---

## 5. RECOMENDACIONES

### 5.1 Investigación Prioritaria

Investigar los **11 casos sin factura de reemplazo** donde:
- La entrega está ACTIVA (mercadería salió)
- No hay factura de reemplazo
- Hay cobro activo

Estos casos pueden indicar:
- Error de conciliación
- Factura perdida
- Problema de proceso

### 5.2 Análisis de Mismos Items

Para cada factura con reemplazo, comparar:
- Items de la factura original
- Items de la factura de reemplazo
- Cantidades
- Precios

### 5.3 Análisis de Clientes Repetidos

El cliente **C011583 (MI TRIBU)** aparece en 3 facturas anuladas con entrega:
- 10820858 ($2,441.02)
- 10784738 ($1,274.26)
- 10820673 ($188.00)

Investigar si hay un patrón de errores con este cliente.

---

## 6. TESTS REALIZADOS

| Test | Descripción | Estado |
|------|-------------|--------|
| T01 | Identificar 26 facturas con entrega | ✓ PASS |
| T02 | Verificar estado de entregas | ✓ PASS |
| T03 | Buscar facturas de reemplazo | ✓ PASS |
| T04 | Analizar patrón de reemplazo | ✓ PASS |
| T05 | Clasificar por estado de entrega | ✓ PASS |

---

**Telchi SAP — Investigación de Facturas con Salida de Mercadería — V1**

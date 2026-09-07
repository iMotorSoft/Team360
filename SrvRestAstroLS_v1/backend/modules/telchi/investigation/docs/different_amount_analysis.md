# TELCHI SAP — ANÁLISIS: FACTURAS CON MONTOS DIFERENTES

**Fecha:** 2026-08-23
**Estado:** ANÁLISIS COMPLETO

---

## CASOS IDENTIFICADOS

### CASO 1: MI TRIBU (C011583)

| Campo | Factura Original | Factura Reemplazo |
|-------|------------------|-------------------|
| DocEntry | 10820858 | 10823257 |
| DocNum | 251904877 | 251406750 |
| DocDate | 2025-08-05 | 2025-08-08 |
| DocTotal | $2,441.02 | $188.00 |
| Líneas | 31 | 7 |
| Entregas | 2 (324881, 326367) | 1 (324881) |

**DIFERENCIA: -$2,253.02 (92.3% menos)**

### CASO 2: MI TRIBU (C011583)

| Campo | Factura Original | Factura Reemplazo |
|-------|------------------|-------------------|
| DocEntry | 10784738 | 10823257 |
| DocNum | 251904131 | 251406750 |
| DocDate | 2025-07-09 | 2025-08-08 |
| DocTotal | $1,274.26 | $188.00 |
| Líneas | 16 | 7 |
| Entregas | 1 (324881) | 1 (324881) |

**DIFERENCIA: -$1,086.26 (85.3% menos)**

### CASO 3: CHAVEZ CATACORA (C004372)

| Campo | Factura Original | Factura Reemplazo |
|-------|------------------|-------------------|
| DocEntry | 1839383 | 1843283 |
| DocNum | 22013123 | 22013131 |
| DocDate | 2022-09-29 | 2022-09-29 |
| DocTotal | $1,002.81 | $725.80 |
| Líneas | 11 | 5 |
| Entregas | 3 (9193, 9194, 9195) | 1 (9193) |

**DIFERENCIA: -$277.01 (27.6% menos)**

---

## PATRÓN IDENTIFICADO

### 1. Múltiples Entregas en Factura Original

La factura original agrupaba **múltiples entregas** en una sola factura:

| Caso | Entregas Originales | Entregas en Reemplazo |
|------|---------------------|----------------------|
| MI TRIBU (10820858) | 2 (324881, 326367) | 1 (324881) |
| MI TRIBU (10784738) | 1 (324881) | 1 (324881) |
| CHAVEZ CATACORA | 3 (9193, 9194, 9195) | 1 (9193) |

### 2. Items Eliminados en Reemplazo

La factura de reemplazo **eliminó items** que estaban en la original:

**CASO 1 (MI TRIBU):**
- Original: 31 items
- Reemplazo: 7 items
- **Items eliminados: 24 items**

**CASO 3 (CHAVEZ CATACORA):**
- Original: 11 items (de 3 entregas)
- Reemplazo: 5 items (de 1 entrega)
- **Items eliminados: 6 items**
- **Entregas eliminadas: 2 (9194, 9195)**

### 3. Misma Fecha de Anulación y Reemplazo

En el CASO 3:
- Factura original: 2022-09-29
- Factura reemplazo: 2022-09-29
- **Misma fecha**

Esto sugiere una corrección inmediata.

---

## IMPLICACIONES

### 1. Para el Análisis de Ventas

Las facturas anuladas con monto diferente representan:
- **Corrección de errores** en la facturación original
- **Eliminación de items** que no debían estar
- **Separación de entregas** que fueron agrupadas incorrectamente

### 2. Para el Análisis de Stock

Los items eliminados de la factura reemplazo:
- **No fueron facturados** en la nueva factura
- **Pero sí fueron entregados** en la entrega original
- Esto puede crear una **discrepancia entre stock y facturación**

### 3. Para el Análisis de Cobros

Todas las facturas (original y reemplazo) tienen:
- **PaidToDate = DocTotal**
- **Cobros activos**

Esto significa que el dinero fue recibido por:
- La factura original (y posiblemente devuelto)
- La factura reemplazo (y retenido)

---

## HALLAZGO CRÍTICO

**El cliente C011583 (MI TRIBU) tiene 3 facturas anuladas con entrega:**

| DocEntry | DocDate | DocTotal | Reemplazo |
|----------|---------|----------|-----------|
| 10820858 | 2025-08-05 | $2,441.02 | 10823257 ($188.00) |
| 10784738 | 2025-07-09 | $1,274.26 | 10823257 ($188.00) |
| 10820673 | 2025-08-05 | $188.00 | 10823257 ($188.00) |

**Todas apuntan a la MISMA factura de reemplazo (10823257).**

Esto sugiere:
1. El cliente MI TRIBU tuvo múltiples facturas incorrectas
2. Todas fueron anuladas
3. Se creó UNA SOLA factura de reemplazo correcta
4. La entrega original fue facturada correctamente una sola vez

---

## RECOMENDACIONES

### 1. Investigar el Cliente MI TRIBU

- ¿Por qué múltiples facturas incorrectas?
- ¿Hubo un problema de proceso?
- ¿Es un cliente con alto volumen de devoluciones?

### 2. Verificar Conciliación

- ¿El cobro de las facturas originales fue devuelto?
- ¿El cobro de la factura reemplazo es el único válido?
- ¿Hay sobrepago o subpago?

### 3. Verificar Stock

- ¿Los items eliminados de la factura reemplazo están en inventario?
- ¿Hay discrepancy entre lo entregado y lo facturado?

---

**Telchi SAP — Análisis de Facturas con Montos Diferentes — V1**

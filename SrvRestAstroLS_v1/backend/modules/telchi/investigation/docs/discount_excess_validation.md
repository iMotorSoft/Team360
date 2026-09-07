# TELCHI SAP — VALIDACIÓN: 566 CASOS DE DESCUENTO EXCEDIDO

**Fecha:** 2026-08-23
**Estado:** VALIDACIÓN COMPLETA

---

## 1. RESUMEN EJECUTIVO

| Métrica | Valor |
|---------|-------|
| Total líneas con descuento excedido | 566 |
| Monto total factura | $50,781.52 |
| Descuento promedio adicional | +6.69 pp |

---

## 2. DISTRIBUCIÓN POR AUMENTO DE DESCUENTO

| Rango | Líneas | Descripción |
|-------|--------|-------------|
| **1-10 pp** | **538** | **95.1% - Aumento menor** |
| 11-20 pp | 4 | 0.7% - Aumento moderado |
| 21-30 pp | 7 | 1.2% - Aumento alto |
| **30+ pp** | **17** | **3.0% - Aumento crítico** |

**95.1% de los casos tienen un aumento de 1-10 puntos porcentuales.**

---

## 3. TOP 10 PRODUCTOS

| ItemCode | Casos |
|----------|-------|
| L01106 | 10 |
| Coaseguro | 7 |
| M02638 | 6 |
| M04895 | 6 |
| L01001 | 6 |
| L00069 | 5 |
| M04762 | 5 |
| M01823 | 5 |
| M05981 | 4 |
| L01653 | 4 |

---

## 4. TOP 10 VENDEDORES

| SlpCode | Casos |
|---------|-------|
| 36 | 78 |
| 47 | 52 |
| 40 | 41 |
| 53 | 32 |
| 39 | 30 |
| 54 | 25 |
| 41 | 20 |
| 58 | 20 |
| 114 | 17 |
| 153 | 16 |

---

## 5. TOP 10 CLIENTES

| CardCode | Cliente | Casos |
|----------|---------|-------|
| CGCM | CONTROL TRIBUTARIO | 101 |
| CGCM | Cliente Generico CM | 78 |
| CGV1 | CONTROL TRIBUTARIO | 50 |
| CG2A | CONTROL TRIBUTARIO | 39 |
| CGRC | CONTROL TRIBUTARIO | 20 |
| CG2A | Cliente Generico 2A | 17 |
| CGCM | MARIA EMILIA DIAZ DE CONLEY | 11 |
| CGCM | INGRID EGUEZ DE NAZRALA | 11 |
| CGCM | YERSON GONZALES ROMERO | 11 |
| CGCM | JENNY MEDINA | 10 |

---

## 6. HALLAZGOS CLAVE

### 6.1 Patrón de Clientes

Los **5 primeros clientes** son todos **"CONTROL TRIBUTARIO"** o **"Cliente Generico"**:

- CGCM - CONTROL TRIBUTARIO: 101 casos
- CGCM - Cliente Generico CM: 78 casos
- CGV1 - CONTROL TRIBUTARIO: 50 casos
- CG2A - CONTROL TRIBUTARIO: 39 casos
- CGRC - CONTROL TRIBUTARIO: 20 casos

**Esto sugiere que los descuentos excedidos están concentrados en clientes genéricos/tributarios.**

### 6.2 Patrón de Vendedores

El vendedor **SlpCode 36** tiene **78 casos** (13.8% del total).

### 6.3 Patrón de Aumento

- **95.1%** tienen aumento de **1-10 pp** (menor)
- **3.0%** tienen aumento de **30+ pp** (crítico)

Los casos críticos (30+ pp) son los que requieren investigación prioritaria.

---

## 7. IMPLICACIÓN

Los 566 casos de descuento excedido representan:

1. **Un volumen bajo** (566 de 284,377 líneas proforma-factura = 0.2%)
2. **Un monto moderado** ($50,781.52)
3. **Una concentración en clientes genéricos/tributarios**
4. **Un patrón de aumento menor** (95.1% con 1-10 pp)

**No es un problema sistémico generalizado**, pero los casos con **30+ pp** deben investigarse.

---

## 8. RECOMENDACIONES

1. **Investigar los 17 casos con 30+ pp** - Podrían ser errores o excepciones legítimas
2. **Revisar el patrón de clientes genéricos** - ¿Son ventas de contado o servicio?
3. **Validar si los descuentos son autorizados** - ¿Existe política documentada?
4. **Monitorear** - Establecer alertas para descuentos >20 pp

---

**Telchi SAP — Validación: 566 Casos de Descuento Excedido — V1**

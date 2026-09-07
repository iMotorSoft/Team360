# TELCHI SAP — ANÁLISIS: CLIENTES CON CRÉDITO VENCIDO Y LÍMITE EXCEDIDO

**Fecha:** 2026-08-23
**Estado:** ANÁLISIS COMPLETO

---

## 1. RESUMEN EJECUTIVO

### 1.1 Clientes con Deuda Vencida

| Estado | Clientes | Deuda Vencida | AR Total |
|--------|----------|---------------|----------|
| DENTRO_LÍMITE | 150 | $1,244,777.15 | $1,933,765.68 |
| SIN_LÍMITE | 64 | $169,462.76 | $169,462.76 |
| **EXCEDIDO** | **5** | **$50,636.24** | **$139,190.78** |

### 1.2 Hallazgo Crítico

**5 clientes con deuda vencida EXCEDEN su límite de crédito.**

---

## 2. DETALLE DE CLIENTES EXCEDIDOS

### 2.1 C008090 - JACOB WIELER KNELSEN

| Campo | Valor |
|-------|-------|
| Deuda vencida | $1,806.53 |
| AR Total | $15,065.70 |
| Límite crédito | $5,000.00 |
| **Exceso** | **$10,065.70 (301.3%)** |
| Facturas vencidas | 2 |
| Vencimiento más antiguo | 2026-07-18 |

### 2.2 C003542 - FROESE 0 ABRAM FRIESSEN

| Campo | Valor |
|-------|-------|
| Deuda vencida | $37,923.69 |
| AR Total | $67,949.80 |
| Límite crédito | $60,000.00 |
| **Exceso** | **$7,949.80 (113.2%)** |
| Facturas vencidas | 9 |
| Vencimiento más antiguo | 2026-07-25 |

### 2.3 C003531 - LOEWEN REIMER CORNELIUS

| Campo | Valor |
|-------|-------|
| Deuda vencida | $8,338.73 |
| AR Total | $52,566.44 |
| Límite crédito | $50,000.00 |
| **Exceso** | **$2,566.44 (105.1%)** |
| Facturas vencidas | 3 |
| Vencimiento más antiguo | 2026-08-15 |

### 2.4 C007776 - ALIANZA SEGUROS S.A.

| Campo | Valor |
|-------|-------|
| Deuda vencida | $2,376.32 |
| AR Total | $2,376.32 |
| Límite crédito | $2,000.00 |
| **Exceso** | **$376.32 (118.8%)** |
| Facturas vencidas | 13 |
| Vencimiento más antiguo | **2026-02-10 (194 días)** |

### 2.5 E000043 - VARGAS GUALLANI ALVARO ROBERTO

| Campo | Valor |
|-------|-------|
| Deuda vencida | $190.97 |
| AR Total | $1,232.52 |
| Límite crédito | $1,000.00 |
| **Exceso** | **$232.52 (123.3%)** |
| Facturas vencidas | 1 |
| Vencimiento más antiguo | 2026-08-22 |

---

## 3. ENTREGAS RECIENTES (ÚLTIMOS 90 DÍAS)

### 3.1 C003542 - FROESE 0 ABRAM FRIESSEN

| DocEntry | DocDate | DocTotal |
|----------|---------|----------|
| 350547 | 2026-08-10 | $640.35 |
| 350567 | 2026-08-10 | $158.40 |
| 349104 | 2026-07-20 | $113.40 |
| 347356 | 2026-06-25 | $1,386.45 |
| 347354 | 2026-06-25 | $102.60 |
| 347355 | 2026-06-25 | $270.00 |
| 345968 | 2026-06-08 | $2,524.68 |
| 346012 | 2026-06-08 | $105.13 |
| 345736 | 2026-06-02 | $700.00 |

**9 entregas en 90 días a pesar de estar excediendo el límite.**

### 3.2 C008090 - JACOB WIELER KNELSEN

| DocEntry | DocDate | DocTotal |
|----------|---------|----------|
| 351467 | 2026-08-20 | $119.26 |
| 351465 | 2026-08-20 | $1,175.40 |
| 348002 | 2026-07-03 | $700.52 |
| 348004 | 2026-07-03 | $102.96 |
| 346286 | 2026-06-11 | $511.20 |
| 346371 | 2026-06-11 | $946.60 |

**6 entregas en 90 días a pesar de estar excediendo el límite.**

### 3.3 C003531 - LOEWEN REIMER CORNELIUS

| DocEntry | DocDate | DocTotal |
|----------|---------|----------|
| 350789 | 2026-08-12 | $490.50 |
| 350263 | 2026-08-04 | $351.00 |
| 348826 | 2026-07-15 | $162.00 |
| 346769 | 2026-06-17 | $360.00 |

**4 entregas en 90 días a pesar de estar excediendo el límite.**

### 3.4 E000043 - VARGAS GUALLANI ALVARO ROBERTO

| DocEntry | DocDate | DocTotal |
|----------|---------|----------|
| 351063 | 2026-08-14 | $47.25 |
| 350962 | 2026-08-13 | $136.77 |
| 350964 | 2026-08-13 | $174.10 |
| 350716 | 2026-08-11 | $130.96 |
| 350501 | 2026-08-05 | $482.81 |
| 349699 | 2026-07-27 | $116.91 |
| 349290 | 2026-07-21 | $190.97 |
| 348810 | 2026-07-14 | $269.04 |
| 348281 | 2026-07-07 | $136.50 |
| 348282 | 2026-07-07 | $130.41 |
| 345652 | 2026-06-02 | $11.25 |
| 345748 | 2026-06-02 | $274.64 |
| 345356 | 2026-05-28 | $8.75 |
| 344907 | 2026-05-26 | $7.02 |

**14 entregas en 90 días a pesar de estar excediendo el límite.**

---

## 4. HALLAZGOS CRÍTICOS

### 4.1 Entregas a Clientes Excedidos

**Se realizaron ENTREGAS a clientes que ya excedían su límite de crédito:**

| Cliente | Límite | AR Total | Exceso | Entregas 90 días |
|---------|--------|----------|--------|------------------|
| C003542 | $60,000 | $67,949.80 | $7,949.80 | 9 |
| C008090 | $5,000 | $15,065.70 | $10,065.70 | 6 |
| C003531 | $50,000 | $52,566.44 | $2,566.44 | 4 |
| C007776 | $2,000 | $2,376.32 | $376.32 | 0 (sin entregas recientes) |
| E000043 | $1,000 | $1,232.52 | $232.52 | 14 |

### 4.2 Implicación

**SAP no está bloqueando entregas a clientes con crédito excedido.**

Esto puede ser:
1. Configuración de SAP que no bloquea entregas
2. Excepciones manuales autorizadas
3. Falta de control de crédito en el proceso de ventas

### 4.3 Riesgo

Los clientes con crédito excedido y deuda vencida representan un **riesgo crediticio real**:
- No están pagando a tiempo
- Están recibiendo más mercadería
- El límite de crédito no está siendo respetado

---

## 5. RECOMENDACIONES

### 5.1 Inmediatas

1. **Revisar configuración de crédito en SAP** - ¿Por qué no bloquea entregas?
2. **Investigar los 5 clientes excedidos** - ¿Son excepciones autorizadas?
3. **Evaluar riesgo crediticio** - ¿Cuánto está en riesgo?

### 5.2 Corto Plazo

1. **Implementar alertas** - Notificar cuando un cliente excede su límite
2. **Revisar límites de crédito** - ¿Son adecuados para el volumen de negocio?
3. **Monitorear pagos** - Seguir la evolución de la deuda vencida

---

## 6. TESTS REALIZADOS

| Test | Descripción | Estado |
|------|-------------|--------|
| T01 | Identificar clientes con deuda vencida | ✓ PASS |
| T02 | Calcular utilización de crédito | ✓ PASS |
| T03 | Identificar clientes excedidos | ✓ PASS |
| T04 | Analizar entregas recientes | ✓ PASS |
| T05 | Verificar facturas vencidas | ✓ PASS |

---

**Telchi SAP — Análisis de Clientes con Crédito Vencido y Límite Excedido — V1**

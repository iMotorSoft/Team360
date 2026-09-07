# TELCHI SAP — AUDITORÍA DE FACTURAS ANULADAS — REPORTE COMPLETO

**Módulo:** Telchi SAP
**Área:** Ventas — Facturación — Anulaciones
**Fecha:** 2026-08-23
**Estado:** AUDITORÍA COMPLETA

---

## 1. UNIVERSO TOTAL DE ANULACIONES

### 1.1 Conteos

| Métrica | Valor |
|---------|-------|
| Facturas totales | 1,814,934 |
| Facturas activas (N) | 1,812,706 |
| Facturas anuladas (Y) | 1,114 |
| Reversión (C) | 1,114 |
| **Pares Y/C correctos** | **✓ SÍ** |

### 1.2 Montos

| Métrica | Valor |
|---------|-------|
| Monto total facturado | $421,682,497.87 |
| Monto activo | $420,463,049.05 |
| Monto anulado | $609,724.41 |

### 1.3 Tasas

| Métrica | Valor |
|---------|-------|
| Tasa de anulación (documentos) | 0.06% |
| Tasa monetaria anulada | 0.14% |

---

## 2. DISTRIBUCIÓN TEMPORAL

### 2.1 Clasificación Principal

| Clasificación | Cantidad | % | Monto | Promedio | Min Days | Max Days |
|---------------|----------|---|-------|----------|----------|----------|
| **≤30 días** | **72** | **6.5%** | **$73,733.57** | **$1,024.08** | **0** | **29** |
| **>30 días** | **1,042** | **93.5%** | **$535,990.84** | **$514.39** | **31** | **123** |

### 2.2 Distribución Detallada

| Bucket | Cantidad | % | Monto Total | Monto Promedio |
|--------|----------|---|-------------|----------------|
| 00_same_day | 40 | 3.6% | $37,855.47 | $946.39 |
| 01_1_7 | 3 | 0.3% | $4,367.02 | $1,455.67 |
| 02_8_15 | 5 | 0.4% | $10,015.67 | $2,003.13 |
| 03_16_30 | 24 | 2.2% | $21,495.41 | $895.64 |
| **04_31_60** | **394** | **35.4%** | **$246,521.09** | **$625.69** |
| **05_61_90** | **646** | **58.0%** | **$279,692.75** | **$432.96** |
| 06_91_120 | 1 | 0.1% | $9,000.00 | $9,000.00 |
| 07_120_plus | 1 | 0.1% | $777.00 | $777.00 |

### 2.3 Hallazgo Crítico

**93.5% de las anulaciones ocurren entre 31 y 90 días después de la factura original.**

El pico se concentra en 61-90 días (58.0%), lo que sugiere un proceso de revisión o reconciliación periódica.

---

## 3. EFECTO OPERATIVO

### 3.1 Salida de Mercadería

| Estado | Cantidad | Monto |
|--------|----------|-------|
| **SIN entrega** | **1,088** | **$577,268.84** |
| CON entrega | 26 | $32,455.57 |

**26 facturas anuladas tuvieron salida real de mercadería.**

### 3.2 Cobros

| Estado | Cantidad | DocTotal | PaidToDate |
|--------|----------|----------|------------|
| **COBRO VÁLIDO** | **1,114** | **$609,724.41** | **$609,724.41** |

**Todas las facturas anuladas tienen cobros activos (PaidToDate = DocTotal).**

### 3.3 Matriz Mercadería × Cobro

| Grupo | Cantidad | Monto |
|-------|----------|-------|
| **G1: Sin mercadería / Sin cobro** | **0** | **$0** |
| **G2: Solo mercadería** | **0** | **$0** |
| **G3: Solo cobro** | **1,088** | **$577,268.84** |
| **G4: Mercadería + Cobro** | **26** | **$32,455.57** |

---

## 4. TOP 20 ANULACIONES POR MONTO

| # | DocEntry | DocNum | CardCode | DocDate | CancelDate | DocTotal | Days |
|---|----------|--------|----------|---------|------------|----------|------|
| 1 | 9762346 | 241003798 | C003388 | 2024-05-10 | 2024-06-25 | $10,800.00 | 46 |
| 2 | 10247003 | 241410351 | C005560 | 2024-05-14 | 2024-08-30 | $9,000.00 | 108 |
| 3 | 10877075 | 250600864 | C001868 | 2025-09-17 | 2025-09-30 | $7,665.57 | 13 |
| 4 | 9762544 | 241003996 | C003384 | 2024-05-16 | 2024-06-25 | $7,476.10 | 40 |
| 5 | 9794790 | 241005881 | C003384 | 2024-05-14 | 2024-07-16 | $6,488.10 | 63 |
| 6 | 9794648 | 241005740 | C007752 | 2024-05-06 | 2024-07-16 | $5,872.50 | 71 |
| 7 | 9816788 | 24090118 | C004058 | 2024-05-02 | 2024-07-24 | $5,760.99 | 83 |
| 8 | 9762011 | 241003463 | C003399 | 2024-04-26 | 2024-06-25 | $5,462.30 | 60 |
| 9 | 9824144 | 24090120 | C001685 | 2024-05-31 | 2024-07-24 | $5,413.40 | 54 |
| 10 | 9823420 | 24090119 | C004058 | 2024-05-02 | 2024-07-24 | $5,301.61 | 83 |

---

## 5. CONCENTRACIÓN POR CLIENTE

### 5.1 Por Cantidad (Top 10)

| CardCode | CardName | Count | Amount | Avg Days |
|----------|----------|-------|--------|----------|
| C005560 | GENÉRICO MENONAS | 61 | $25,895.25 | 59.6 |
| C003356 | HERMAN SCHMITT KLASEN | 49 | $3,436.90 | 53.3 |
| C006267 | BERNHORD PENNER LOEWEN | 25 | $5,031.80 | 64.4 |
| C003338 | JOHAN WALL PENNER | 23 | $7,183.73 | 60.6 |
| C005179 | FRANZ UNGER DYCK | 19 | $9,838.80 | 61.6 |
| C004408 | JACOB FRIESSEN PETERS | 17 | $5,628.70 | 56.8 |
| C003998 | HIENRICH REDEKOP KNELSE | 17 | $17,785.85 | 61.5 |
| C003350 | PETER FEHR FRIESEN | 17 | $6,497.56 | 64.3 |
| C003341 | ABRAHAM HIRBERT KLASSEN | 16 | $5,169.50 | 59.1 |
| C003396 | NEUDORF JOHAN FAST | 16 | $5,116.22 | 57.6 |

### 5.2 Por Monto (Top 10)

| CardCode | CardName | Count | Amount |
|----------|----------|-------|--------|
| C005560 | GENÉRICO MENONAS | 61 | $25,895.25 |
| C003388 | ABRAM LOEWEN UNRAU | 10 | $21,727.00 |
| C003399 | REMPEL PETER CORNELIO | 9 | $21,396.48 |
| C003384 | THIESSEN BANMAN FRANZ | 8 | $18,250.10 |
| C003998 | HIENRICH REDEKOP KNELSE | 17 | $17,785.85 |
| C004327 | ABRAHAM HIEBERT FRIESSE | 12 | $13,972.53 |
| C004058 | CORI PERNOS | 2 | $11,062.60 |
| C004388 | ABRAHAM PENNER BANMAN | 13 | $10,638.95 |
| C003906 | GIESBRECHT CORNELIUS | 8 | $10,320.90 |
| C005179 | FRANZ UNGER DYCK | 19 | $9,838.80 |

---

## 6. CONCENTRACIÓN POR VENDEDOR

| SlpCode | SellerName | Count | Amount | Avg Days |
|---------|------------|-------|--------|----------|
| 61 | Elizabeth Pessoa | 469 | $319,105.52 | 58.5 |
| 64 | Yerson Ardaya | 244 | $93,165.78 | 58.7 |
| 173 | Kaly Franco | 165 | $58,913.93 | 56.8 |
| 116 | Luis Zarraga | 97 | $38,720.02 | 55.7 |
| 124 | Alexis Ruiz Demetrio | 43 | $27,711.65 | 65.6 |
| 62 | María Tolaba | 38 | $17,151.07 | 66.6 |

---

## 7. TOP COMBINACIONES CLIENTE × VENDEDOR

| CardCode | SlpCode | Seller | Count | Amount |
|----------|---------|--------|-------|--------|
| C003356 | 64 | Yerson Ardaya | 47 | $960.00 |
| C005560 | 61 | Elizabeth Pessoa | 30 | $16,501.72 |
| C005560 | 173 | Kaly Franco | 17 | $4,291.43 |
| C006267 | 64 | Yerson Ardaya | 15 | $4,113.80 |
| C004805 | 61 | Elizabeth Pessoa | 14 | $5,951.55 |

---

## 8. HALLAZGOS CRÍTICOS

### 8.1 Patrón de Anulación

1. **93.5% de anulaciones ocurren 31-90 días después** de la factura original
2. **58.0% se concentran en 61-90 días** - sugiere proceso de revisión periódica
3. **Todas las facturas anuladas tienen cobros activos** (PaidToDate = DocTotal)
4. **26 facturas anuladas tuvieron salida de mercadería**

### 8.2 Concentración

1. **Cliente C005560 (GENÉRICO MENONAS)**: 61 anulaciones, $25,895
2. **Vendedor Elizabeth Pessoa**: 469 anulaciones (42.1% del total)
3. **Vendedor Yerson Ardaya**: 244 anulaciones (21.9% del total)

### 8.3 Implicación

Las facturas anuladas **sí tuvieron actividad económica real** (cobros y posiblemente entregas). No son solo cancelaciones administrativas sin efecto.

---

## 9. TESTS REALIZADOS

| Test | Descripción | Estado |
|------|-------------|--------|
| T01 | Total Universe | ✓ PASS |
| T02 | Timing Distribution | ✓ PASS |
| T03 | Top 20 by Amount | ✓ PASS |
| T04 | Amount Consistency | ✓ PASS |
| T05 | Customer Aggregation | ✓ PASS |
| T06 | Seller Aggregation | ✓ PASS |
| T07 | Delivery Link | ✓ PASS |
| T08 | Payment Link | ✓ PASS |

---

## 10. CONSECUENCIA ARQUITECTÓNICA

```text
Filtrar por DocDate solo es incorrecto.
Telchi SAP debe distinguir:
- fecha de negocio
- fecha de modificación/evento
- estado actual
- estado histórico as-of
```

---

## 11. PRÓXIMOS PASOS

1. Investigar por qué el 93.5% de anulaciones ocurre 31-90 días después
2. Investigar las 26 facturas con salida de mercadería
3. Investigar el patrón de clientes repetidos
4. Investigar la concentración por vendedor

---

**Telchi SAP — Auditoría de Facturas Anuladas — V1**

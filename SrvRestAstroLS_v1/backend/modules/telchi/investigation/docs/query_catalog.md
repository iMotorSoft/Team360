# TELCHI SAP — CATÁLOGO DE CONSULTAS REALIZADAS

**Fecha:** 2026-08-23
**Estado:** CATÁLOGO ACTUALIZADO

---

## 1. ANÁLISIS DE FACTURAS ANULADAS

### 1.1 Universo de Anulaciones
```sql
-- Total facturas, activas, anuladas
SELECT
    COUNT(*) AS "TotalInvoices",
    SUM(CASE WHEN "CANCELED" = 'N' THEN 1 ELSE 0 END) AS "ActiveInvoices",
    SUM(CASE WHEN "CANCELED" = 'Y' THEN 1 ELSE 0 END) AS "CanceledOriginal",
    SUM(CASE WHEN "CANCELED" = 'C' THEN 1 ELSE 0 END) AS "CanceledReversal"
FROM TELCHI."OINV"
```

### 1.2 Distribución Temporal
```sql
-- Clasificación ≤30 días vs >30 días
SELECT
    CASE
        WHEN DAYS_BETWEEN("DocDate", "UpdateDate") <= 30 THEN '≤30_days'
        ELSE '>30_days'
    END AS "MainClass",
    COUNT(*) AS "Count",
    SUM("DocTotal") AS "TotalAmount"
FROM TELCHI."OINV"
WHERE "CANCELED" = 'Y'
GROUP BY 1
```

### 1.3 Anulaciones con Entrega
```sql
-- Facturas anuladas que tienen entrega asociada
SELECT COUNT(DISTINCT OINV."DocEntry")
FROM TELCHI."OINV"
WHERE OINV."CANCELED" = 'Y'
  AND EXISTS (
      SELECT 1 FROM TELCHI."INV1"
      WHERE INV1."DocEntry" = OINV."DocEntry"
        AND INV1."BaseEntry" IS NOT NULL
        AND INV1."BaseType" = 15
  )
```

### 1.4 Cobros de Facturas Anuladas
```sql
-- Estado de cobro para facturas anuladas con entrega
SELECT
    CASE
        WHEN "PaidToDate" = 0 THEN 'SIN_COBRO'
        WHEN "PaidToDate" > 0 AND "ActivePayment" = 0 THEN 'COBRO_ANULADO'
        WHEN "PaidToDate" > 0 AND "ActivePayment" >= "DocTotal" THEN 'COBRO_COMPLETO'
    END AS "PaymentStatus",
    COUNT(*) AS "Count"
FROM cancelled_with_delivery
GROUP BY 1
```

---

## 2. ANÁLISIS DE CLIENTES CON CRÉDITO VENCIDO

### 2.1 Clientes con Deuda Vencida
```sql
-- Clientes con deuda vencida y su límite de crédito
SELECT
    CA."CardCode",
    CA."CardName",
    CA."OverdueAmount",
    CA."TotalAR",
    OCRD."CreditLine" AS "CreditLimit",
    CASE
        WHEN OCRD."CreditLine" = 0 THEN 'SIN_LÍMITE'
        WHEN CA."TotalAR" > OCRD."CreditLine" THEN 'EXCEDIDO'
        ELSE 'DENTRO_LÍMITE'
    END AS "LimitStatus"
FROM customer_ar AS CA
INNER JOIN TELCHI."OCRD" ON CA."CardCode" = OCRD."CardCode"
WHERE CA."OverdueAmount" > 0
ORDER BY CA."OverdueAmount" DESC
```

### 2.2 Entregas a Clientes Excedidos
```sql
-- Entregas recientes a clientes que exceden su límite
SELECT
    ODLN."DocEntry",
    ODLN."CardCode",
    ODLN."DocDate",
    ODLN."DocTotal"
FROM TELCHI."ODLN"
WHERE ODLN."CardCode" IN (/* clientes excedidos */)
  AND ODLN."DocDate" >= ADD_DAYS(CURRENT_DATE, -90)
  AND ODLN."CANCELED" = 'N'
ORDER BY ODLN."DocDate" DESC
```

---

## 3. ANÁLISIS DE PROFORMAS Y PRICING

### 3.1 Universo de Proformas
```sql
-- Total proformas, activas, canceladas
SELECT
    COUNT(*) AS "Total",
    SUM(CASE WHEN "CANCELED" = 'N' THEN 1 ELSE 0 END) AS "Active",
    SUM(CASE WHEN "CANCELED" = 'Y' THEN 1 ELSE 0 END) AS "Canceled"
FROM TELCHI."OQUT"
```

### 3.2 Vinculación Proforma → Factura
```sql
-- Facturas que referencian proformas (BaseType=23)
SELECT
    COUNT(DISTINCT INV1."DocEntry") AS "InvoiceCount",
    COUNT(*) AS "LineCount"
FROM TELCHI."INV1"
WHERE INV1."BaseType" = 23
```

### 3.3 Distribución de Descuentos en Proformas
```sql
-- Distribución por buckets de descuento
SELECT
    CASE
        WHEN "DiscPrcnt" IS NULL OR "DiscPrcnt" = 0 THEN '0%'
        WHEN "DiscPrcnt" > 0 AND "DiscPrcnt" <= 5 THEN '1-5%'
        WHEN "DiscPrcnt" > 5 AND "DiscPrcnt" <= 10 THEN '6-10%'
        WHEN "DiscPrcnt" > 10 AND "DiscPrcnt" <= 15 THEN '11-15%'
        WHEN "DiscPrcnt" > 15 AND "DiscPrcnt" <= 20 THEN '16-20%'
        WHEN "DiscPrcnt" > 20 THEN '20%+'
    END AS "DiscountBucket",
    COUNT(*) AS "LineCount",
    SUM("GTotal") AS "TotalAmount"
FROM TELCHI."QUT1"
GROUP BY 1
```

### 3.4 Cambios de Precio Proforma → Factura
```sql
-- Comparación de precios entre proforma y factura
SELECT
    CASE
        WHEN INV1."Price" = QUT1."Price" THEN 'MISMO_PRECIO'
        WHEN INV1."Price" < QUT1."Price" THEN 'MENOR_EN_FACTURA'
        WHEN INV1."Price" > QUT1."Price" THEN 'MAYOR_EN_FACTURA'
    END AS "PriceChange",
    COUNT(*) AS "LineCount"
FROM TELCHI."INV1"
INNER JOIN TELCHI."QUT1"
    ON INV1."BaseEntry" = QUT1."DocEntry"
    AND INV1."BaseLine" = QUT1."LineNum"
WHERE INV1."BaseType" = 23
GROUP BY 1
```

### 3.5 Descuentos Excedidos
```sql
-- Líneas con mayor descuento en factura que en proforma
SELECT
    INV1."BaseEntry" AS "ProformaDocEntry",
    INV1."ItemCode",
    QUT1."DiscPrcnt" AS "ProformaDisc",
    INV1."DiscPrcnt" AS "InvoiceDisc",
    (COALESCE(INV1."DiscPrcnt", 0) - COALESCE(QUT1."DiscPrcnt", 0)) AS "DiscIncrease"
FROM TELCHI."INV1"
INNER JOIN TELCHI."QUT1"
    ON INV1."BaseEntry" = QUT1."DocEntry"
    AND INV1."BaseLine" = QUT1."LineNum"
WHERE INV1."BaseType" = 23
  AND COALESCE(INV1."DiscPrcnt", 0) > COALESCE(QUT1."DiscPrcnt", 0)
ORDER BY "DiscIncrease" DESC
```

---

## 4. ANÁLISIS DE CATEGORÍAS DE CLIENTES

### 4.1 Distribución de Categorías
```sql
-- Distribución de U_CATCLIENTE
SELECT
    COALESCE("U_CATCLIENTE", 'NULL') AS "Category",
    COUNT(*) AS "Count"
FROM TELCHI."OCRD"
WHERE "CardType" = 'C'
GROUP BY "U_CATCLIENTE"
ORDER BY 2 DESC
```

### 4.2 Distribución de Canales
```sql
-- Distribución de U_CANAL_VENTAS
SELECT
    COALESCE("U_CANAL_VENTAS", 'NULL') AS "Channel",
    COUNT(*) AS "Count"
FROM TELCHI."OCRD"
WHERE "CardType" = 'C'
GROUP BY "U_CANAL_VENTAS"
ORDER BY 2 DESC
```

### 4.3 Descuentos Permitidos
```sql
-- Distribución de descuentos configurados en clientes
SELECT
    "Discount" AS "DiscPct",
    COUNT(*) AS "Count"
FROM TELCHI."OCRD"
WHERE "CardType" = 'C'
  AND "Discount" IS NOT NULL
  AND "Discount" > 0
GROUP BY "Discount"
ORDER BY 1
```

---

## 5. ANÁLISIS DE ENTREGAS

### 5.1 Entregas para Facturas Anuladas
```sql
-- Items en entregas para facturas anuladas con entrega
SELECT
    DLN1."DocEntry" AS "DeliveryDocEntry",
    DLN1."ItemCode",
    DLN1."Quantity",
    DLN1."GTotal"
FROM TELCHI."DLN1"
WHERE DLN1."DocEntry" IN (/* delivery doc entries */)
ORDER BY DLN1."DocEntry", DLN1."LineNum"
```

### 5.2 Estado de Entregas
```sql
-- Estado de entregas (activas vs canceladas)
SELECT
    ODLN."CANCELED" AS "DeliveryCanceled",
    COUNT(*) AS "Count",
    SUM(ODLN."DocTotal") AS "TotalAmount"
FROM TELCHI."ODLN"
WHERE ODLN."DocEntry" IN (/* delivery doc entries */)
GROUP BY ODLN."CANCELED"
```

### 5.3 Facturas de Reemplazo
```sql
-- Facturas que reemplazan a otras para la misma entrega
SELECT DISTINCT
    INV1."DocEntry" AS "OriginalDocEntry",
    INV2."DocEntry" AS "ReplacementDocEntry",
    OINV2."DocTotal" AS "ReplacementTotal"
FROM TELCHI."INV1" AS INV1
INNER JOIN TELCHI."INV1" AS INV2
    ON INV1."BaseEntry" = INV2."BaseEntry"
    AND INV1."BaseType" = INV2."BaseType"
    AND INV2."DocEntry" != INV1."DocEntry"
INNER JOIN TELCHI."OINV" AS OINV2 ON INV2."DocEntry" = OINV2."DocEntry"
WHERE INV1."DocEntry" IN (/* original invoice doc entries */)
  AND INV1."BaseEntry" IS NOT NULL
  AND INV1."BaseType" = 15
  AND OINV2."CANCELED" = 'N'
```

---

## 6. ANÁLISIS DE RECONCILIACIONES

### 6.1 Estado de Reconciliaciones
```sql
-- Distribución de estados de reconciliación
SELECT
    "Canceled",
    COUNT(*) AS "Count",
    SUM("Total") AS "TotalAmount"
FROM TELCHI."OITR"
GROUP BY "Canceled"
```

### 6.2 Miembros de Reconciliación
```sql
-- Miembros de reconciliaciones anuladas
SELECT
    ITR1."ReconNum",
    ITR1."SrcObjTyp",
    ITR1."SrcObjAbs",
    ITR1."ReconSum",
    OITR."ReconDate",
    OITR."Canceled" AS "ReconCanceled"
FROM TELCHI."ITR1"
INNER JOIN TELCHI."OITR" ON ITR1."ReconNum" = OITR."ReconNum"
WHERE OITR."Canceled" = 'Y'
ORDER BY OITR."ReconDate" DESC
```

---

## 7. ANÁLISIS DE PAGOS

### 7.1 Estado de Pagos
```sql
-- Distribución de estados de pago
SELECT
    "Canceled",
    COUNT(*) AS "Count",
    SUM("DocTotal") AS "TotalAmount"
FROM TELCHI."ORCT"
GROUP BY "Canceled"
```

### 7.2 Pagos de Facturas Anuladas
```sql
-- Pagos relacionados con facturas anuladas
SELECT
    ORCT."DocEntry",
    ORCT."DocTotal",
    ORCT."Canceled",
    ITR1."ReconNum",
    OITR."ReconDate",
    OITR."Canceled" AS "ReconCanceled"
FROM TELCHI."ORCT"
INNER JOIN TELCHI."ITR1" ON ORCT."DocEntry" = ITR1."SrcObjAbs"
INNER JOIN TELCHI."OITR" ON ITR1."ReconNum" = OITR."ReconNum"
WHERE ORCT."Canceled" = 'Y'
  AND ITR1."SrcObjTyp" = 24
```

---

## 8. ANÁLISIS TEMPORAL

### 8.1 Facturas Anuladas en Mes Diferente
```sql
-- Facturas donde DocDate y cancellation month son diferentes
SELECT
    TO_CHAR("DocDate", 'YYYY-MM') AS "OriginalMonth",
    TO_CHAR("UpdateDate", 'YYYY-MM') AS "CancelMonth",
    COUNT(*) AS "Count",
    SUM("DocTotal") AS "TotalAmount"
FROM TELCHI."OINV"
WHERE "CANCELED" = 'Y'
  AND TO_CHAR("DocDate", 'YYYY-MM') != TO_CHAR("UpdateDate", 'YYYY-MM')
GROUP BY 1, 2
ORDER BY 1, 2
```

### 8.2 Facturas de Reemplazo
```sql
-- Verificación de facturas de reemplazo para facturas anuladas
SELECT
    CASE WHEN EXISTS (/* replacement check */)
         THEN 'CON_REEMPLAZO' ELSE 'SIN_REEMPLAZO' END AS "Status",
    COUNT(*) AS "Count",
    SUM("DocTotal") AS "TotalAmount"
FROM cross_month_cancelled
GROUP BY 1
```

---

## 9. ANÁLISIS DE INVENTARIO

### 9.1 Tablas SAP Identificadas

| Tabla | Descripción | Grain |
|-------|-------------|-------|
| OINV | Facturas de venta | DocEntry |
| INV1 | Líneas de factura | DocEntry + LineNum |
| ORIN | Notas de crédito | DocEntry |
| RIN1 | Líneas de NC | DocEntry + LineNum |
| ORCT | Pagos recibidos | DocEntry |
| OITR | Reconciliaciones | ReconNum |
| ITR1 | Miembros de reconciliación | ReconNum + LineSeq |
| OQUT | Proformas | DocEntry |
| QUT1 | Líneas de proforma | DocEntry + LineNum |
| ODLN | Entregas | DocEntry |
| DLN1 | Líneas de entrega | DocEntry + LineNum |
| OCRD | Clientes | CardCode |
| OSLP | Vendedores | SlpCode |

### 9.2 Campos Clave Identificados

| Campo | Tabla | Descripción |
|-------|-------|-------------|
| CANCELED | OINV, ORIN, ORCT, OITR | Estado de anulación (N/Y/C) |
| UpdateDate | OINV, ORIN, ORCT | Fecha de última actualización |
| UpdateTS | OINV, ORIN, ORCT | Timestamp de actualización |
| DocTotal | OINV, ORIN, ORCT | Total del documento |
| PaidToDate | OINV | Pagado hasta fecha |
| BaseEntry | INV1, RIN1, QUT1 | Referencia a documento base |
| BaseType | INV1, RIN1, QUT1 | Tipo de documento base |
| DiscPrcnt | INV1, QUT1 | Porcentaje de descuento |
| Price | INV1, QUT1 | Precio unitario |
| GTotal | INV1, QUT1 | Total de línea |

---

## 10. UDFs DE CLIENTES

| Campo | Descripción | Valores Observados |
|-------|-------------|-------------------|
| U_CATCLIENTE | Categoría cliente | NULL, A |
| U_CANAL_VENTAS | Canal de ventas | 1-8, NULL |
| U_TIPOCLIENTE | Tipo cliente | DMS, NULL |
| Discount | Descuento permitido | 3%, 5%, 7%, 8%, 10%, 11%, 15% |

---

## 11. REGLAS DE NEGOCIO VALIDADAS

### 11.1 Anulaciones
- `CANCELED = 'N'`: Documento válido
- `CANCELED = 'Y'`: Documento anulado (original)
- `CANCELED = 'C'`: Documento de reversión (par del Y)
- Y y C siempre aparecen en pares

### 11.2 Fechas
- `DocDate`: Fecha del documento
- `UpdateDate`: Fecha de última actualización (incluye anulación)
- `UpdateTS`: Timestamp de actualización (precisión HHMMSS)

### 11.3 Descuentos
- `DiscPrcnt`: Porcentaje de descuento
- `Price`: Precio unitario después de descuento
- `GTotal`: Total de línea (Price × Quantity)

---

## 12. LIMITACIONES IDENTIFICADAS

1. **Historial de categorías**: No se conserva historial de cambios de categoría de cliente
2. **Histórico de precios**: No se conserva historial completo de listas de precios
3. **Política de descuento**: No existe política documentada de descuento por categoría
4. **Precios especiales**: No se identificaron mecanismos de precios especiales

---

**Telchi SAP — Catálogo de Consultas Realizadas — V1**

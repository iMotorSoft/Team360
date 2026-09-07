-- =============================================================================
-- INVENTORY MOVEMENTS — Auxiliary: Delivery Context (TransType 15)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeMoveProductRange (DF15)
-- Tables: TELCHI.ODLN, TELCHI.DLN1, TELCHI.OINV
-- Purpose: Provide sale document context for delivery-based movements
-- Filters: ODLN.CANCELED='N', OINV.isIns='Y'
-- =============================================================================

SELECT
    15 AS "TransType",
    T0."DocNum",
    T2."DocNum" AS "OINV_DocNum",
    T2."CardCode" AS "OINV_CardCode",
    T2."DocDate" AS "SaleDocDate",
    T2."DocDueDate" AS "SaleDocDueDate",
    T2."SlpCode" AS "SellerCodeSB1",
    T2."DocTotal" AS "DeliverySale"
FROM TELCHI.ODLN T0
LEFT JOIN TELCHI.DLN1 T1
    ON T0."DocEntry" = T1."DocEntry"
LEFT JOIN TELCHI.OINV T2
    ON T1."BaseEntry" = T2."DocEntry"
   AND T1."BaseRef" = CAST(T2."DocNum" AS varchar)
WHERE T0."CANCELED" = 'N'
  AND T2."isIns" = 'Y'
  AND T0."DocNum" IN (
    SELECT DISTINCT OINM."BASE_REF"
    FROM TELCHI.OINM OINM
    WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
      AND OINM."DocDate" <= :end_date || ' 23:59:59'
)

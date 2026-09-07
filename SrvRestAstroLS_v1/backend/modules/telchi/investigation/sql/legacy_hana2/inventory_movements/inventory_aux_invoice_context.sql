-- =============================================================================
-- INVENTORY MOVEMENTS — Auxiliary: Invoice Context (TransType 13)
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeMoveProductRange (DF13)
-- Tables: TELCHI.OINV
-- Purpose: Provide sale document context for invoice-based movements
-- =============================================================================

SELECT
    13 AS "TransType",
    OINV."DocNum",
    OINV."DocNum" AS "OINV_DocNum",
    OINV."CardCode" AS "OINV_CardCode",
    OINV."DocDate" AS "SaleDocDate",
    OINV."DocDueDate" AS "SaleDocDueDate",
    OINV."SlpCode" AS "SellerCodeSB1",
    OINV."DocTotal" AS "OfficeSale"
FROM TELCHI.OINV OINV
WHERE OINV."DocNum" IN (
    SELECT DISTINCT OINM."BASE_REF"
    FROM TELCHI.OINM OINM
    WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
      AND OINM."DocDate" <= :end_date || ' 23:59:59'
)

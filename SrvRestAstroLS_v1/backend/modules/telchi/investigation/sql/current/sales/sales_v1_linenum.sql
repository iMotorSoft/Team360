-- =============================================================================
-- SALES — Current V1: Add LineNum for stable SAP line identity
-- =============================================================================
-- Change ID: SALES-001
-- Motivation: DocEntry+ItemCode has 34+ duplicates per month.
--   DocEntry+LineNum is 100% unique (validated 66089/66089 for Feb 2023).
--   LineNum is the native SAP line identifier in INV1.
-- Impact: Adds one column. No row count change. No semantic change.
-- Regression: All legacy columns preserved.
-- =============================================================================

SELECT
    OINV."DocEntry",
    OINV."NumAtCard",
    OINV."Series",
    OINV."DocNum",
    OINV."CardCode",
    OINV."CardName",
    OINV."DocTotal",
    OINV."DiscSum",
    OINV."PaidSum",
    OINV."SlpCode" AS "SellerCodeSB1",
    (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP
     WHERE OINV."SlpCode" = OSLP."SlpCode") AS "SellerNameSB1",
    OINV."UpdateDate",
    OINV."UpdateTS",
    OINV."DocDate",
    OINV."DocTime",
    OINV."DocStatus",
    OINV."U_ESTADOFC",
    OINV."DocSubType",
    INV1."LineNum",
    INV1."ItemCode",
    INV1."Dscription",
    INV1."GPBefDisc",
    INV1."Quantity",
    INV1."GTotal",
    INV1."U_DESCLINEA",
    INV1."WhsCode",
    INV1."U_TYPE"
FROM TELCHI.OINV AS OINV
INNER JOIN TELCHI.INV1 AS INV1
    ON OINV."DocEntry" = INV1."DocEntry"
WHERE OINV."DocDate" >= :start_date
  AND OINV."DocDate" <= :end_date

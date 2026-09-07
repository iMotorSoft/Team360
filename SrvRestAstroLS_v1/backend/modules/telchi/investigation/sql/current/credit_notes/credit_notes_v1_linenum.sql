-- =============================================================================
-- CREDIT NOTES — Current V1: Add LineNum for stable SAP line identity
-- =============================================================================
-- Change ID: CREDIT_NOTES-001
-- Motivation: Same as SALES-001. LineNum provides stable line identity.
-- Impact: Adds one column. No row count change. No semantic change.
-- Regression: All legacy columns preserved. Signs preserved.
-- =============================================================================

SELECT
    ORIN."DocEntry" AS "FDocEntry",
    ORIN."NumAtCard" AS "FNumAtCard",
    ORIN."Series" AS "FSeries",
    ORIN."DocNum" AS "FDocNum",
    ORIN."CardCode",
    ORIN."CardName",
    (ORIN."DocTotal" * -1) AS "FDocTotal",
    ORIN."DiscSum" AS "FDiscSum",
    ORIN."PaidSum" AS "FPaidSum",
    ORIN."SlpCode" AS "SellerCodeSB1",
    (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP
     WHERE ORIN."SlpCode" = OSLP."SlpCode") AS "SellerNameSB1",
    ORIN."UpdateDate",
    ORIN."UpdateTS",
    ORIN."DocDate",
    ORIN."DocTime",
    ORIN."DocStatus",
    ORIN."U_ESTADOFC" AS "FU_ESTADOFC",
    RIN1."LineNum",
    RIN1."ItemCode",
    RIN1."Dscription",
    RIN1."GPBefDisc",
    (RIN1."Quantity" * -1) AS "Quantity",
    (RIN1."GTotal" * -1) AS "GTotal",
    RIN1."U_DESCLINEA" AS "FU_DESCLINEA",
    RIN1."WhsCode",
    RIN1."U_TYPE",
    RIN1."BaseRef"
FROM TELCHI.ORIN AS ORIN
INNER JOIN TELCHI.RIN1 AS RIN1
    ON ORIN."DocEntry" = RIN1."DocEntry"
WHERE ORIN."DocDate" >= :start_date
  AND ORIN."DocDate" <= :end_date

-- =============================================================================
-- SALES — Legacy HANA2 Evolved Variant
-- =============================================================================
-- Source: sapb1Tools01.py::makeSaleDFRange
-- Tables: TELCHI.OINV, TELCHI.INV1, TELCHI.OSLP, TELCHI.OUSR
-- SAP Object: OINV (Invoice)
-- Grain: DocEntry + line
-- SAP Identifiers: DocEntry, DocNum, TransId, CardCode, ItemCode, WhsCode
-- Date Filter: OINV.DocDate
-- =============================================================================
-- LEGACY EXECUTION ADAPTATION:
--   - Removed Python string formatting (.format())
--   - Parameterized dates as :start_date and :end_date
--   - Removed TELCHI schema prefix for readability
--   - Preserved original aliases exactly
-- =============================================================================
-- EVOLUTION FROM VARIANT A:
--   + Added TransId (accounting document number)
--   + Added UserSign, UserSign2 with OUSR lookup
--   + Added DocDueDate
--   + Date filter includes time component (23:59:59)
-- =============================================================================

SELECT
    OINV."TransId",
    OINV."DocEntry",
    OINV."NumAtCard",
    OINV."Series",
    OINV."DocNum",
    OINV."CardCode",
    OINV."CardName",
    OINV."DocTotal",
    OINV."UserSign",
    (SELECT OUSR."USER_CODE" FROM TELCHI."OUSR" OUSR
     WHERE OUSR."USERID" = OINV."UserSign") AS "OUSR-USER_CODE",
    OINV."UserSign2",
    (SELECT OUSR."USER_CODE" FROM TELCHI."OUSR" OUSR
     WHERE OUSR."USERID" = OINV."UserSign2") AS "OUSR-USER_CODE2",
    OINV."DiscSum",
    OINV."PaidSum",
    OINV."SlpCode" AS "SellerCodeSB1",
    (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP
     WHERE OINV."SlpCode" = OSLP."SlpCode") AS "SellerNameSB1",
    OINV."UpdateDate",
    OINV."UpdateTS",
    OINV."DocDate",
    OINV."DocTime",
    OINV."DocDueDate",
    OINV."DocStatus",
    OINV."U_ESTADOFC",
    OINV."DocSubType",
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
  AND OINV."DocDate" <= :end_date || ' 23:59:59'

-- =============================================================================
-- SALES — Legacy HANA2 Baseline
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeSaleDFRange
--         sapb1Tools01.py::makeSaleDFRange (evolved variant)
-- Tables: TELCHI.OINV, TELCHI.INV1, TELCHI.OSLP
-- SAP Object: OINV (Invoice)
-- Grain: DocEntry + line (one row per invoice line)
-- SAP Identifiers: DocEntry, DocNum, CardCode, ItemCode, WhsCode
-- Date Filter: OINV.DocDate
-- =============================================================================
-- LEGACY EXECUTION ADAPTATION:
--   - Removed Python string formatting (.format())
--   - Parameterized dates as :start_date and :end_date
--   - Removed TELCHI schema prefix for readability (assumes TELCHI schema)
--   - Preserved original aliases exactly
-- =============================================================================

-- =============================================================================
-- VARIANT A: srvSyncTelchiSB101.py (primary production variant)
-- =============================================================================
-- This is the SQL as executed by the main production sync.
-- Note: Does NOT include LineNum, CANCELED, TransId, UserSign, DocDueDate.

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

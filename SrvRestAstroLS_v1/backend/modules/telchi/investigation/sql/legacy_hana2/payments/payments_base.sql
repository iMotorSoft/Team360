-- =============================================================================
-- PAYMENTS — Legacy HANA2 Base Query
-- =============================================================================
-- Source: sapb1Tools01.py::makePaymentRange
-- Tables: TELCHI.ORCT
-- SAP Object: ORCT (Incoming Payment)
-- Grain: DocEntry
-- SAP Identifiers: DocEntry, DocNum, TransId, CardCode
-- Date Filter: ORCT.DocDate
-- =============================================================================
-- NOTES:
--   - Canceled field is preserved (not filtered)
--   - Includes multiple payment method amounts
--   - DocTotalFC is foreign currency total
-- =============================================================================

SELECT
    ORCT."TransId",
    ORCT."CashSum",
    ORCT."TrsfrSum",
    ORCT."CreditSum",
    ORCT."CheckSum",
    ORCT."DocTotal",
    ORCT."DocTotalFC",
    ORCT."DocEntry",
    ORCT."DocNum",
    ORCT."DocType",
    ORCT."Canceled",
    ORCT."DocDate",
    ORCT."DocTime",
    ORCT."DocDueDate",
    ORCT."TaxDate",
    ORCT."CardCode" AS "ClientCode",
    ORCT."CardName" AS "ClientName",
    ORCT."Ref1",
    ORCT."Comments",
    ORCT."JrnlMemo"
FROM TELCHI."ORCT" AS ORCT
WHERE ORCT."DocDate" >= :start_date
  AND ORCT."DocDate" <= :end_date || ' 23:59:59'

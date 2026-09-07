-- =============================================================================
-- INVENTORY MOVEMENTS — Legacy HANA2 Base Query
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeMoveProductRange (active/final variant)
--         sapb1Tools01.py::makeMoveProductRange (identical)
-- Tables: TELCHI.OINM
-- SAP Object: OINM (Inventory Journal)
-- Grain: TransNum (movement transaction)
-- SAP Identifiers: TransNum, BASE_REF, DocLineNum, ItemCode, Warehouse
-- Date Filter: OINM.DocDate
-- =============================================================================
-- KNOWN ISSUES:
--   1. BASE_REF column name is uppercase in SQL but Python uses lowercase
--      'base_ref' for merge — CASE MISMATCH (LEGACY_BUG_BASE_REF_CASE_MISMATCH)
--   2. Price/0.87 formula is hardcoded — origin unknown
--   3. Does NOT include CardCode/ClientCode in this variant
--   4. Auxiliary queries (DF13, DF15, OCRD, OUSR, OSLP) are separate
-- =============================================================================

SELECT
    OINM."TransNum",
    OINM."TransType",
    OINM."BASE_REF",
    OINM."DocLineNum",
    OINM."Ref1",
    OINM."Ref2",
    OINM."Comments",
    OINM."JrnlMemo",
    OINM."DocDate",
    OINM."DocDueDate",
    OINM."DocTime",
    OINM."CardCode" AS "ClientCode",
    OINM."CardName" AS "ClientName",
    OINM."ItemCode",
    OINM."Dscription" AS "ItemName",
    OINM."InQty",
    OINM."OutQty",
    OINM."TransValue" AS "CostTotal",
    OINM."CalcPrice" AS "CostU",
    (OINM."Price" / 0.87) AS "ItemSaleU",
    OINM."Balance",
    OINM."SlpCode" AS "DManCode",
    OINM."Warehouse",
    OINM."UserSign"
FROM TELCHI.OINM OINM
WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
  AND OINM."DocDate" <= :end_date || ' 23:59:59'

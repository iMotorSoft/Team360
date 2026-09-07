-- =============================================================================
-- INVOICE CONTRACT — FINANCIAL-001
-- =============================================================================
-- Change ID: FINANCIAL-001
-- Motivation: Establish the financial invoice contract with SAP traceability.
--   Grain: OINV.DocEntry (one row per invoice, header level)
--   Purpose: Financial balance, aging, AR analysis
--   NOT for line-level product analysis (use sales_v1_linenum.sql)
-- Impact: New SQL. No modification to existing queries.
-- Regression: Independent of existing sales/credit_notes/payments queries.
-- =============================================================================
-- Fields verified against HANA schema 2026-08-20:
--   DocEntry, DocNum, CardCode, SlpCode: SAP identifiers
--   DocDate, DocDueDate: date dimensions
--   DocTotal: document total (header level)
--   DocStatus: document status (O=open, C=closed)
--   CANCELED: cancellation flag (N=no, Y=yes, C=canceled)
--   DocSubType: document subtype (IB=invoice, DN=debit note, --=standard)
--   TransId: journal transaction ID
--   PaidSum: paid sum
--   PaidToDate: paid to date
--   DocCur: document currency (NOTE: 'Currency' does NOT exist in OINV)
--   DocRate: exchange rate
--   DocTotalFC: document total in foreign currency
--   SysRate: system rate
--   DiscSum: discount sum
--   VatSum: VAT sum
--   WTSum: withholding tax sum
-- =============================================================================
-- Grain: 1 row per DocEntry
-- =============================================================================

SELECT
    OINV."DocEntry",
    OINV."DocNum",
    OINV."CardCode",
    OINV."CardName",
    OINV."SlpCode",
    (SELECT OSLP."SlpName" FROM TELCHI.OSLP AS OSLP
     WHERE OINV."SlpCode" = OSLP."SlpCode") AS "SellerName",
    OINV."DocDate",
    OINV."DocDueDate",
    OINV."DocTotal",
    OINV."DocStatus",
    OINV."CANCELED",
    OINV."DocSubType",
    OINV."TransId",
    OINV."PaidSum",
    OINV."PaidToDate",
    OINV."DocCur",
    OINV."DocRate",
    OINV."DocTotalFC",
    OINV."SysRate",
    OINV."DiscSum",
    OINV."VatSum",
    OINV."WTSum",
    OINV."UpdateDate",
    OINV."NumAtCard"
FROM TELCHI.OINV AS OINV
WHERE OINV."DocDate" >= :start_date
  AND OINV."DocDate" < :end_date

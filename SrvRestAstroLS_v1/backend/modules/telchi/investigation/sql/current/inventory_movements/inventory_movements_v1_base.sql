-- =============================================================================
-- INVENTORY MOVEMENTS — CURRENT BASE v1 (INVENTORY-001)
-- =============================================================================
-- Objective: stable OINM base contract with RAW preservation.
--   * No joins (no multiplication)
--   * No drop_duplicates
--   * No fillna bug
--   * Raw Price preserved (Price/0.87 isolated as legacy_adjusted_price)
--   * BASE_REF naming contract normalized and documented
--   * All SAP identifiers preserved
-- Source: legacy inventory_base.sql (identity preserved)
-- =============================================================================
-- CONTRACT (SOURCE_IDENTITY / DOCUMENT_LINK / ITEM / WAREHOUSE / QUANTITIES /
--           VALUES / CUSTOMER / SELLER / USER / CLASSIFICATION / LEGACY_DERIVED)
--   TransNum        : SOURCE_IDENTITY (SAP journal transaction number)
--   TransType       : SOURCE_IDENTITY (raw; never replaced by mapping)
--   BaseRef         : DOCUMENT_LINK (raw OINM.BASE_REF; case-normalized contract
--                     name, NOT renamed semantically)
--   DocLineNum      : DOCUMENT_LINK (raw)
--   Ref1            : DOCUMENT_LINK (raw)
--   Ref2            : DOCUMENT_LINK (raw)
--   Comments        : SOURCE (raw)
--   JrnlMemo        : SOURCE (raw)
--   DocDate         : DOCUMENT_LINK (raw)
--   DocDueDate      : DOCUMENT_LINK (raw)
--   DocTime         : SOURCE (raw)
--   CardCode        : CUSTOMER (raw SAP code)
--   CardName        : CUSTOMER (raw)
--   ItemCode        : ITEM (raw; no inner join to OITM, no orphan loss)
--   Dscription      : ITEM (raw description)
--   InQty           : QUANTITIES (raw)
--   OutQty          : QUANTITIES (raw)
--   TransValue      : VALUES (raw)
--   CalcPrice       : VALUES (raw)
--   Price           : VALUES (RAW — legacy Price/0.87 NOT applied here)
--   Balance         : VALUES (raw)
--   SlpCode         : SELLER (raw)
--   Warehouse       : WAREHOUSE (raw code; master enrichment separate)
--   UserSign        : USER (raw)
--   legacy_adjusted_price : LEGACY_DERIVED (Price/0.87 isolated; origin UNKNOWN)
-- =============================================================================
-- INVENTORY-001 gate: TELCHI_INVENTORY_CURRENT_BASE_PASS
-- =============================================================================

SELECT
    OINM."TransNum"                          AS "TransNum",
    OINM."TransType"                         AS "TransType",
    OINM."BASE_REF"                          AS "BaseRef",
    OINM."DocLineNum"                        AS "DocLineNum",
    OINM."Ref1"                              AS "Ref1",
    OINM."Ref2"                              AS "Ref2",
    OINM."Comments"                          AS "Comments",
    OINM."JrnlMemo"                          AS "JrnlMemo",
    OINM."DocDate"                           AS "DocDate",
    OINM."DocDueDate"                        AS "DocDueDate",
    OINM."DocTime"                           AS "DocTime",
    OINM."CardCode"                          AS "CardCode",
    OINM."CardName"                          AS "CardName",
    OINM."ItemCode"                          AS "ItemCode",
    OINM."Dscription"                        AS "Dscription",
    OINM."InQty"                             AS "InQty",
    OINM."OutQty"                            AS "OutQty",
    OINM."TransValue"                        AS "TransValue",
    OINM."CalcPrice"                         AS "CalcPrice",
    OINM."Price"                             AS "Price",
    OINM."Balance"                           AS "Balance",
    OINM."SlpCode"                           AS "SlpCode",
    OINM."Warehouse"                         AS "Warehouse",
    OINM."UserSign"                          AS "UserSign",
    (OINM."Price" / 0.87)                    AS "legacy_adjusted_price"
FROM TELCHI.OINM OINM
WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
  AND OINM."DocDate" <= :end_date || ' 23:59:59'
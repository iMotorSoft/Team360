-- =============================================================================
-- ATOMIC SOURCE — INVENTORY MOVEMENT (P0) — grain OINM (transnum,item,whs)
-- =============================================================================
-- Identity of OINM movement is (TransNum + ItemCode + Warehouse + event_date);
-- linking movements to commercial documents is validated experimentally (§17),
-- NEVER via DocNum only.
SELECT
    OINM."TransNum"    AS "source_document_id",
    OINM."TransType"   AS "trans_type",
    OINM."BASE_REF"    AS "base_ref",
    OINM."DocLineNum"  AS "doc_line_num",
    OINM."Ref1"        AS "ref1",
    OINM."Ref2"        AS "ref2",
    OINM."DocDate"     AS "event_at",
    OINM."ItemCode"    AS "item_id",
    OINM."Dscription"  AS "item_desc",
    OINM."InQty"       AS "in_qty",
    OINM."OutQty"      AS "out_qty",
    OINM."TransValue"  AS "trans_value",
    OINM."CalcPrice"   AS "calc_price",
    OINM."Price"       AS "price",
    OINM."Balance"     AS "balance",
    OINM."CardCode"    AS "customer_id",
    OINM."SlpCode"     AS "seller_id",
    OINM."Warehouse"   AS "warehouse_id",
    OINM."UserSign"    AS "user_id"
FROM TELCHI.OINM AS OINM
WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
  AND OINM."DocDate" <= :end_date || ' 23:59:59'
-- =============================================================================
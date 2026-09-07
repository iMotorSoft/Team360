-- =============================================================================
-- ATOMIC SOURCE — CASH_EVENT (SAP side, payment-derived) — grain ORCT.DocEntry
-- =============================================================================
-- Separation (§17): PAYMENT (all ORCT) vs CASH_EVENT (payments with a cash
-- portion). A CASH_EVENT is the cash portion of an incoming payment:
--   ORCT.CashSum > 0  (filter)
-- The physical cash register is NOT explicit in ORCT (cash_register_id
-- UNKNOWN); legacy cjtrn/cjcja carry the per-register grain (§18).
-- Classifier reads PHYSICAL column names (DEC-022).
SELECT
    'INCOMING_PAYMENT'  AS "source_object_type",
    ORCT."DocEntry"     AS "source_document_id",
    ORCT."DocNum"       AS "source_document_number",
    ORCT."CardCode"     AS "customer_id",
    ORCT."DocDate"      AS "business_date",
    ORCT."DocTotal"     AS "amount_document",
    ORCT."DocCurr"      AS "currency",
    ORCT."Canceled"     AS "canceled",
    ORCT."TransId"      AS "transaction_id",
    ORCT."CashSum"      AS "cash_amount",
    ORCT."CheckSum"     AS "check_sum",
    ORCT."TrsfrSum"     AS "transfer_sum",
    ORCT."CreditSum"    AS "card_sum",
    ORCT."NoDocSum"     AS "on_account_sum",
    ORCT."BoeSum"       AS "boe_sum",
    ORCT."U_ORIGIN"     AS "channel_origin",
    ORCT."U_SO1_01RETAILONE" AS "retail_one_flag"
FROM TELCHI.ORCT AS ORCT
WHERE ORCT."CashSum" > 0
  AND ORCT."DocDate" >= :start_date
  AND ORCT."DocDate" < :end_date
-- =============================================================================
-- gate: ATOMIC-002 (P0 cash event, SAP side)
-- =============================================================================
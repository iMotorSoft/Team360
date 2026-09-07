-- =============================================================================
-- ATOMIC SOURCE — PAYMENT HEADER (P0) — grain ORCT.DocEntry
-- =============================================================================
-- CONFIRMED: payment currency field is ORCT.DocCurr (DEC-015). Cash/check/
-- transfer/credit/NoDoc sums drive classify_payment_method (T04).
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
    ORCT."CashSum"      AS "cash_sum",
    ORCT."CheckSum"     AS "check_sum",
    ORCT."TrsfrSum"     AS "transfer_sum",
    ORCT."CreditSum"    AS "card_sum",
    ORCT."DdctSum"      AS "deduct_sum",
    ORCT."NoDocSum"     AS "on_account_sum",
    ORCT."BoeSum"       AS "boe_sum",
    ORCT."U_ORIGIN"     AS "channel_origin"
FROM TELCHI.ORCT AS ORCT
WHERE ORCT."DocDate" >= :start_date
  AND ORCT."DocDate" < :end_date
-- =============================================================================
-- gate: ATOMIC-001 (P0 payment header)
-- =============================================================================
-- =============================================================================
-- ATOMIC RELATION — PAYMENT -> ACCOUNTING JOURNAL CASH LINES (H4)
-- =============================================================================
-- Chain: ORCT --TransId--> OJDT (1:1, 100% coverage measured) -> JDT1 lines.
-- Cash component evidence: JDT1 rows whose Account = ORCT.CashAcct
-- (evidence-based identity, never line position). Preserves raw Debit/Credit.
SELECT
    O."DocEntry"          AS "payment_docentry",
    O."DocNum"            AS "payment_docnum",
    O."TransId"           AS "trans_id",
    G."TransId"           AS "journal_trans_id",
    O."CashAcct"          AS "cash_account_expected",
    O."CashSum"           AS "cash_sum",
    O."DocCurr"           AS "currency",
    O."Canceled"          AS "canceled",
    J."Line_ID"           AS "line_id",
    J."Account"           AS "account_actual",
    J."Debit"             AS "raw_debit",
    J."Credit"            AS "raw_credit",
    J."ContraAct"         AS "contra_act",
    J."BPLId"             AS "bpl_id",
    J."LineMemo"          AS "line_memo"
FROM TELCHI."ORCT" AS O
INNER JOIN TELCHI."OJDT" AS G ON O."TransId" = G."TransId"
LEFT JOIN TELCHI."JDT1" AS J ON J."TransId" = G."TransId"
WHERE O."DocDate" >= :start_date AND O."DocDate" < :end_date
-- =============================================================================
-- gate: H4-001 (payment accounting link)
-- =============================================================================
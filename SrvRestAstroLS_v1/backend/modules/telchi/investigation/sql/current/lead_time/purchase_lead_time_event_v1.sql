-- =============================================================================
-- PURCHASE LEAD TIME ATOMIC EVENT — TELCHI_PURCHASE_LEAD_TIME_V1
-- =============================================================================
-- Change: TELCHI-LT-001
-- Grain: one row per (PO line, receipt line) through the document chain.
-- READ ONLY.
-- =============================================================================
-- Document chain (invoice-first, validated in Gate 1):
--   PO line (POR1.DocEntry+LineNum) -> invoice line (PCH1.BaseType=22,
--   BaseEntry=POR1.DocEntry, BaseLine=POR1.LineNum) -> receipt line
--   (PDN1.BaseType=18, BaseEntry=OPCH.DocEntry, BaseLine=PCH1.LineNum).
--   Direct PO->receipt is marginal (PDN1.BaseType=22, 54 lines).
--   Linkage: PO->invoice 90,782/90,998 (99.8%); invoice->receipt 87,616/87,616
--   (100%). Receipts without PO lineage: 8 lines (excluded from lead time).
-- Order date = OPOR.DocDate (BACKDATED_PO anomaly: invoice can precede PO).
-- Receipt date = OPDN.DocDate. Canceled OPDN (C/Y) excluded.
-- =============================================================================
WITH po_lines AS (
    SELECT P."DocEntry" AS po_entry, P."LineNum" AS po_line, P."ItemCode",
           P."Quantity" AS ordered_qty, P."WhsCode" AS po_whs,
           O."DocDate" AS order_date, O."CardCode", O."CardName",
           O."U_TIPOCOMPRA", O."DocCur", O."DocStatus"
    FROM TELCHI."POR1" P
    JOIN TELCHI."OPOR" O ON O."DocEntry" = P."DocEntry"
    WHERE O."CANCELED" = 'N'
),
receipt_events AS (
    -- invoice-first chain: PO -> invoice -> receipt
    SELECT P."DocEntry" AS po_entry, P."LineNum" AS po_line,
           R."DocEntry" AS rec_entry, R."LineNum" AS rec_line,
           R."Quantity" AS rec_qty, D."DocDate" AS rec_date, R."WhsCode" AS rec_whs
    FROM TELCHI."POR1" P
    JOIN TELCHI."PCH1" I ON I."BaseType"=22 AND I."BaseEntry"=P."DocEntry" AND I."BaseLine"=P."LineNum"
    JOIN TELCHI."PDN1" R ON R."BaseType"=18 AND R."BaseEntry"=I."DocEntry" AND R."BaseLine"=I."LineNum"
    JOIN TELCHI."OPDN" D ON D."DocEntry" = R."DocEntry"
    WHERE D."CANCELED" = 'N'
    UNION ALL
    -- direct PO -> receipt (marginal)
    SELECT P."DocEntry", P."LineNum", R."DocEntry", R."LineNum",
           R."Quantity", D."DocDate", R."WhsCode"
    FROM TELCHI."POR1" P
    JOIN TELCHI."PDN1" R ON R."BaseType"=22 AND R."BaseEntry"=P."DocEntry" AND R."BaseLine"=P."LineNum"
    JOIN TELCHI."OPDN" D ON D."DocEntry" = R."DocEntry"
    WHERE D."CANCELED" = 'N'
)
SELECT
    L.po_entry, L.po_line, L."ItemCode", L.ordered_qty,
    L.order_date, L."CardCode", L."CardName", L."U_TIPOCOMPRA", L."DocCur", L."DocStatus",
    R.rec_entry, R.rec_line, R.rec_qty, R.rec_date, R.rec_whs
FROM po_lines L
LEFT JOIN receipt_events R ON R.po_entry = L.po_entry AND R.po_line = L.po_line
-- =============================================================================
-- OPEN PURCHASE vs OITW.ONORDER RECONCILIATION — TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1
-- =============================================================================
-- Change: TELCHI-COV-004
-- Grain: ItemCode (items with an open PO line)
-- READ ONLY.
-- =============================================================================
-- Anti-double-count reconciliation (P0.2). Two representations of "ordered but
-- not received" must NOT be summed:
--   OPEN_PURCHASE_QTY = SUM(POR1.OpenQty) over open POs (purchase UOM, doc-linked)
--   ONORDER_QTY       = SUM(OITW.OnOrder) (inventory UOM, system aggregate)
-- They diverge for two documented reasons:
--   (1) UOM conversion (purchase UOM != inventory UOM on traded/packaged items);
--   (2) OITW.OnOrder includes sources beyond open POs (e.g. partially-received
--       POs still flagged on-order, and production/transfer commitments).
-- Canonical documentary future order quantity = OPEN_PURCHASE_QTY (line-level,
-- supplier/date/tipo-linked). ONORDER_QTY is the reconciliation check only.
-- =============================================================================
SELECT
    P."ItemCode",
    SUM(P."OpenQty") AS "OpenPurchaseQty",
    COALESCE((SELECT SUM(T."OnOrder") FROM TELCHI."OITW" T
              WHERE T."ItemCode" = P."ItemCode"), 0) AS "OnOrderQty"
FROM TELCHI."POR1" P
JOIN TELCHI."OPOR" O ON O."DocEntry" = P."DocEntry"
WHERE O."CANCELED" = 'N' AND O."DocStatus" = 'O' AND P."OpenQty" > 0
GROUP BY P."ItemCode"
ORDER BY P."ItemCode"

-- =============================================================================
-- OPEN IMPORT PURCHASE POSITION — TELCHI_PURCHASE_RISK_ENGINE_V1
-- =============================================================================
-- Change: TELCHI-RISK-001
-- Grain: POR1.DocEntry + POR1.LineNum (open import PO lines)
-- READ ONLY.
-- =============================================================================
-- Import delay risk evidence (Gate 8): open POs classified as import
-- (U_TIPOCOMPRA='IMP'). Used to flag IMPORT_DELAY_RISK when a component's
-- physical coverage horizon is ~<= the import lead time (p90 ~82d observed).
-- Confidence = DOCUMENTED_ORDER; no physical arrival date (IN_TRANSIT_UNRESOLVED).
-- =============================================================================
SELECT
    O."DocEntry"  AS po_entry,
    O."DocNum"    AS po_docnum,
    O."DocDate"   AS po_docdate,
    O."CardCode",
    O."CardName",
    P."LineNum"   AS po_line,
    P."ItemCode",
    P."Quantity"  AS ordered_qty,
    P."OpenQty"   AS open_qty
FROM TELCHI."OPOR" O
JOIN TELCHI."POR1" P ON P."DocEntry" = O."DocEntry"
WHERE O."CANCELED" = 'N' AND O."DocStatus" = 'O' AND P."OpenQty" > 0
  AND O."U_TIPOCOMPRA" = 'IMP'
ORDER BY O."DocEntry", P."LineNum"

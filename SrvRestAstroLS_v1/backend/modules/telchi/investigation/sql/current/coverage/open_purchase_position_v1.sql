-- =============================================================================
-- OPEN PURCHASE POSITION — TELCHI_EQUIVALENT_MATERIAL_COVERAGE_V1
-- =============================================================================
-- Change: TELCHI-COV-003
-- Grain: POR1.DocEntry + POR1.LineNum (open PO lines)
-- READ ONLY.
-- =============================================================================
-- Layer E: OPEN_PURCHASE_POSITION (ordered, NOT received).
--   Canonical documentary future-order quantity = POR1.OpenQty on open POs
--   (OPOR.CANCELED='N' AND OPOR.DocStatus='O'), doc-linked via BaseEntry ->
--   DocEntry (Gate 1). Confidence = DOCUMENTED_ORDER; no physical arrival date
--   is asserted (IN_TRANSIT_UNRESOLVED). Kept OUT of temporal availability in
--   the conservative coverage run.
--   NOTE: OITW.OnOrder is a system aggregate in inventory UOM and includes
--   quantities beyond open POs (see open_purchase_vs_onorder reconciliation).
-- =============================================================================
SELECT
    O."DocEntry"    AS po_entry,
    O."DocNum"      AS po_docnum,
    O."DocDate"     AS po_docdate,
    O."CardCode",
    O."CardName",
    O."DocCur",
    O."U_TIPOCOMPRA",
    P."LineNum"     AS po_line,
    P."ItemCode",
    P."Quantity"    AS ordered_qty,
    P."OpenQty"     AS open_qty,
    P."WhsCode"
FROM TELCHI."OPOR" O
JOIN TELCHI."POR1" P ON P."DocEntry" = O."DocEntry"
WHERE O."CANCELED" = 'N' AND O."DocStatus" = 'O' AND P."OpenQty" > 0
ORDER BY O."DocEntry", P."LineNum"

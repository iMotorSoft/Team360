-- =============================================================================
-- PURCHASE DOCUMENT CHAIN — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-008
-- Grain: one row per linked purchase line across OPOR -> OPCH -> OPDN
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   Operative flow (dominant):
--     OPOR (PO) -> OPCH (AP invoice) -> OPDN (goods receipt)
--     PCH1.BaseType = 22, PCH1.BaseEntry = OPOR.DocEntry   (100% linked)
--     PDN1.BaseType = 18, PDN1.BaseEntry = OPCH.DocEntry   (100% linked)
--   Direct PO -> receipt path is marginal:
--     PDN1.BaseType = 22, PDN1.BaseEntry = OPOR.DocEntry   (100% linked)
--   SAP-canonical link is BaseEntry -> DocEntry (integer). Line tables also
--   expose BaseRef/BaseDocNum (string DocNum) and BaseAtCard (supplier doc
--   number) as redundant representations; they are NOT the relationship of
--   record.
--   Timing evidence:
--     PO -> Invoice:  P50 = 0d, P75 = 1d, P90 = 3d (30,010 lines invoiced
--       BEFORE the PO date: backdated PO pattern, magnitude mostly -1..-7d)
--     Invoice -> Receipt: P50 = 1d, P75 = 3d, P90 = 5d (129 negative)
--   Open position (compras abiertas): OPOR.DocStatus = 'O' (33 orders,
--     13 IMP incl. HAINAN ZHONGXIN, THOSCO, FLORAMATIC, USP; 20 LF incl.
--     MATRIPLAST). SAP only distinguishes ORDERED (open PO) vs RECEIVED
--     (OPDN); no customs/in-transit states available.
-- =============================================================================
SELECT
    O."DocEntry"    AS po_docentry,
    O."DocNum"      AS po_docnum,
    O."DocDate"     AS po_docdate,
    O."U_TIPOCOMPRA" AS po_typocompra,
    O."DocCur"      AS po_doccur,
    H."DocEntry"    AS invoice_docentry,
    H."DocNum"      AS invoice_docnum,
    H."DocDate"     AS invoice_docdate,
    D."DocEntry"    AS receipt_docentry,
    D."DocNum"      AS receipt_docnum,
    D."DocDate"     AS receipt_docdate
FROM TELCHI."OPOR" O
LEFT JOIN TELCHI."PCH1" P
    ON P."BaseType" = 22 AND P."BaseEntry" = O."DocEntry"
LEFT JOIN TELCHI."OPCH" H ON H."DocEntry" = P."DocEntry"
LEFT JOIN TELCHI."PDN1" N
    ON (N."BaseType" = 18 AND N."BaseEntry" = H."DocEntry")
    OR (N."BaseType" = 22 AND N."BaseEntry" = O."DocEntry")
LEFT JOIN TELCHI."OPDN" D ON D."DocEntry" = N."DocEntry"
WHERE O."CANCELED" = 'N'
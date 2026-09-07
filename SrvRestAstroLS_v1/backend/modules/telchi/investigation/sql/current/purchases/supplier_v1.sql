-- =============================================================================
-- SUPPLIER (PROVEEDOR) — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-007
-- Grain: OCRD.CardCode (one row per business partner), CardType = 'S'
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - 1,073 suppliers (1,053 valid, 20 not valid for new transactions)
--   - OCRD.Country NOT reliable for import identification: 1,062 'BO'
--     (foreign suppliers like HAINAN ZHONGXIN are stored with local codes)
--   - Import/local evidence lives in the DOCUMENTS:
--       OPOR.U_TIPOCOMPRA ('IMP' vs 'LF'/'LP'/'SERV'/'SAA')
--       supplier CardCode prefix: PL* = local, PE* = foreign (57 IMP suppliers)
--       DocCur = USD on IMP orders
--   - 296 suppliers LF, 123 LP, 57 IMP, 58 SERV, 18 SAA (by U_TIPOCOMPRA)
-- =============================================================================
SELECT
    "CardCode",
    "CardName",
    "CardType",
    "GroupCode",
    "GroupNum",
    "Currency",
    "Country",
    "Phone1",
    "Phone2",
    "Address",
    "CardValid",
    "ValidUntil",
    "VatGroup",
    "U_ESTCLIENTE",
    "U_TIPOCLIENTE"
FROM TELCHI."OCRD"
WHERE "CardType" = 'S'
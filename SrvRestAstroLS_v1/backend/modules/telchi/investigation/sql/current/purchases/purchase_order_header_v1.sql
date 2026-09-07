-- =============================================================================
-- PURCHASE ORDER HEADER — TELCHI_PURCHASE_DATA_DISCOVERY_V1
-- =============================================================================
-- Change: TELCHI-PURCHASE-001
-- Grain: OPOR.DocEntry (one row per purchase order)
-- READ ONLY.
-- =============================================================================
-- Semantics discovered (2026-08-27):
--   - DocStatus: O = open, C = closed (33 open, 18,630 closed)
--   - CANCELED: 'N' active, 'Y' canceled (723); no 'C' pair on OPOR
--   - DocType: I = items (18,200), S = services (463)
--   - DocCur: BS (18,395) / USD (268); DocRate holds FX for USD docs
--   - U_TIPOCOMPRA operative classification:
--       LF = compra local (14,316) | LP = envases/plásticos local (1,941)
--       IMP = importación + logística (1,917) | SERV = servicios (365)
--       SAA = interno (124)
--   - U_SOLCOMPRA / U_FECHEST_EMBR / U_FECHREAL_EMBR / U_FECHPRTO / U_FECHALM
--     / U_INCOTERM / U_CODPAIS / U_CTRLCALIDAD: NOT OPERATIVE (0 fill)
--   - NumAtCard = número de documento del proveedor (factura OC)
--   - DocDueDate filled 100%: promised delivery date
-- =============================================================================
SELECT
    "DocEntry",
    "DocNum",
    "ObjType",
    "DocType",
    "CANCELED",
    "DocStatus",
    "DocDate",
    "DocDueDate",
    "CreateDate",
    "UpdateDate",
    "CardCode",
    "CardName",
    "NumAtCard",
    "DocCur",
    "DocRate",
    "DocTotal",
    "DocTotalFC",
    "DocTotalSy",
    "VatSum",
    "WddStatus",
    "U_TIPOCOMPRA",
    "U_MEDTRANS",
    "U_PRIORIDAD",
    "U_SOLCOMPRA",
    "U_DESTINATARIO_COMPRA"
FROM TELCHI."OPOR"
WHERE "CANCELED" = 'N'
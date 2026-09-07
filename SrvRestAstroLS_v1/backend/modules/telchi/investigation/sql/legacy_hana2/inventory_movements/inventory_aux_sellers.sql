-- =============================================================================
-- INVENTORY MOVEMENTS — Auxiliary: Sellers
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeMoveProductRange (DFOSLP)
-- Tables: TELCHI.OSLP
-- Purpose: Full seller lookup table (used for both DManCode and SellerCodeSB1)
-- =============================================================================

SELECT DISTINCT
    OSLP."SlpCode",
    OSLP."SlpName"
FROM TELCHI.OSLP AS OSLP

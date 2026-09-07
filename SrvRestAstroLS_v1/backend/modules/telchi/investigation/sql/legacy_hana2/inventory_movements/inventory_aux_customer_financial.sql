-- =============================================================================
-- INVENTORY MOVEMENTS — Auxiliary: Customer Financial Context
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeMoveProductRange (DFOCRD)
-- Tables: TELCHI.OCRD
-- Purpose: Provide customer debt/credit info for movements
-- =============================================================================

SELECT DISTINCT
    OCRD."CardCode",
    OCRD."Balance" AS "Deuda",
    OCRD."CreditLine" AS "Limite",
    OCRD."GroupNum" AS "TCreditCode"
FROM TELCHI.OCRD OCRD
WHERE OCRD."CardCode" IN (
    SELECT DISTINCT OINM."CardCode"
    FROM TELCHI.OINM OINM
    WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
      AND OINM."DocDate" <= :end_date || ' 23:59:59'
)

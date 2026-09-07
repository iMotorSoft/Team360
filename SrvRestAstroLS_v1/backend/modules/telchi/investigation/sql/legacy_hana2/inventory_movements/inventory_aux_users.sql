-- =============================================================================
-- INVENTORY MOVEMENTS — Auxiliary: Users
-- =============================================================================
-- Source: srvSyncTelchiSB101.py::makeMoveProductRange (DFOUSR)
-- Tables: TELCHI.OUSR
-- Purpose: Resolve UserSign to USER_CODE
-- =============================================================================

SELECT DISTINCT
    OUSR.USERID AS "UserSign",
    OUSR.USER_CODE AS "User"
FROM "TELCHI".OUSR OUSR
WHERE OUSR.USERID IN (
    SELECT DISTINCT OINM."UserSign"
    FROM TELCHI.OINM OINM
    WHERE OINM."DocDate" >= :start_date || ' 00:00:00'
      AND OINM."DocDate" <= :end_date || ' 23:59:59'
)

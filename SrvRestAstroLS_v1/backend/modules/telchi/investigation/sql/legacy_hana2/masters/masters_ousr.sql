-- =============================================================================
-- MASTERS — Users (OUSR)
-- =============================================================================
-- Source: Used across multiple domains
-- Tables: TELCHI.OUSR
-- SAP Object: OUSR (Users)
-- Grain: USERID
-- =============================================================================

SELECT
    OUSR."USERID",
    OUSR."USER_CODE",
    OUSR."U_NAME"
FROM TELCHI."OUSR" OUSR

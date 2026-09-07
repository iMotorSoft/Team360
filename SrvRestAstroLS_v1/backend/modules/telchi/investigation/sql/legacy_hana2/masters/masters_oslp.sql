-- =============================================================================
-- MASTERS — Sellers (OSLP)
-- =============================================================================
-- Source: Used across multiple domains
-- Tables: TELCHI.OSLP
-- SAP Object: OSLP (Sales Employees)
-- Grain: SlpCode
-- =============================================================================

SELECT
    OSLP."SlpCode",
    OSLP."SlpName"
FROM TELCHI.OSLP AS OSLP

-- =============================================================================
-- MASTERS — Warehouse Master (OWHS)
-- =============================================================================
-- Source: sapb1Tools01.py::makeOWHS
-- Tables: TELCHI.OWHS
-- SAP Object: OWHS (Warehouses)
-- Grain: WhsCode
-- =============================================================================

SELECT
    OWHS."WhsCode",
    OWHS."WhsName",
    OWHS."BalInvntAc",
    OWHS."SaleCostAc",
    OWHS."TransferAc",
    OWHS."Locked",
    OWHS."RevenuesAc"
FROM TELCHI.OWHS OWHS

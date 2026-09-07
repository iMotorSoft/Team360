-- =============================================================================
-- MASTERS — Item Groups (OITB)
-- =============================================================================
-- Source: sapb1Tools01.py::makeOITB
-- Tables: TELCHI.OITB
-- SAP Object: OITB (Item Groups)
-- Grain: ItmsGrpCod
-- =============================================================================

SELECT
    OITB."ItmsGrpCod",
    OITB."ItmsGrpNam",
    OITB."Locked",
    OITB."DataSource",
    OITB."UserSign",
    OITB."BalInvntAc",
    OITB."SaleCostAc",
    OITB."TransferAc",
    OITB."RevenuesAc",
    OITB."userSign2",
    OITB."createDate",
    OITB."updateDate"
FROM TELCHI.OITB OITB

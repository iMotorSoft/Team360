-- =============================================================================
-- MASTERS — Chart of Accounts (OACT)
-- =============================================================================
-- Source: sapb1Tools01.py::makeOACT
-- Tables: TELCHI.OACT
-- SAP Object: OACT (Chart of Accounts)
-- Grain: AcctCode
-- =============================================================================

SELECT
    OACT."AcctCode",
    OACT."AcctName",
    OACT."CurrTotal",
    OACT."EndTotal",
    OACT."Finanse",
    OACT."Groups",
    OACT."Budget",
    OACT."Frozen",
    OACT."Postable",
    OACT."Fixed",
    OACT."Levels",
    OACT."PlngLevel",
    OACT."ExportCode",
    OACT."GrpLine",
    OACT."FatherNum",
    OACT."AccntntCod",
    OACT."CashBox",
    OACT."RateTrans"
FROM TELCHI.OACT OACT

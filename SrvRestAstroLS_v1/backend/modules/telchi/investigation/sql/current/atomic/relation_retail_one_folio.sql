-- =============================================================================
-- ATOMIC RELATION — RETAIL ONE FOLIO (channel traceability) — OINV UDFs
-- =============================================================================
-- Retail One invoices carry U_SO1_01RETAILONE in {Y,N} plus a folio
-- (U_SO1_01FOLIORETAIL1) and branch (U_SO1_01SUCURSAL + U_SO1_01PREFIJO).
-- Relation to any POS ticket is CANDIDATE; evidence is labeled FOLIO.
-- =============================================================================
SELECT
    OINV."DocEntry"       AS "sap_document_id",
    OINV."DocNum"         AS "sap_doc_num",
    OINV."DocDate"        AS "business_date",
    OINV."DocTotal"       AS "amount_document",
    OINV."CANCELED"       AS "canceled",
    OINV."U_SO1_01RETAILONE"     AS "retail_one_flag",
    OINV."U_SO1_01FOLIORETAIL1"  AS "retail_one_folio",
    OINV."U_SO1_01SUCURSAL"      AS "retail_one_sucursal",
    OINV."U_SO1_01PREFIJO"       AS "retail_one_prefijo",
    OINV."U_SO1_01FOLIOIMPRESO"  AS "retail_one_folio_print"
FROM TELCHI.OINV AS OINV
WHERE OINV."DocDate" >= :start_date
  AND OINV."DocDate" < :end_date
  AND OINV."U_SO1_01RETAILONE" = 'Y'
-- =============================================================================
-- Classification result is PARTIAL_TRACEABILITY until POS-side confirmation.
-- =============================================================================
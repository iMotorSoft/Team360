-- =============================================================================
-- ATOMIC RELATION — SETTLEMENT (PAYMENT/CREDIT -> INVOICE) — ITR1 layer
-- =============================================================================
-- OITR/ITR1 is the settlement authority (§4/§7 DEC-010/011). A reconciliation
-- member links a source object (PAYMENT or INVOICE) via SrcObjTyp/SrcObjAbs.
-- DOCUMENT_RELATION candidate: relation_type=RECONCILED_BY match_method=SAP_BASEENTRY.
SELECT
    'AR_INVOICE'          AS "to_object_type",
    ITR1."SrcObjAbs"      AS "to_document_id",
    ITR1."SrcObjTyp"      AS "src_obj_typ",
    CASE ITR1."SrcObjTyp"
        WHEN 24 THEN 'INCOMING_PAYMENT'
        WHEN 13 THEN 'AR_INVOICE'
        WHEN 14 THEN 'AR_CREDIT_NOTE'
        ELSE CONCAT('OBJTYPE_', TO_NVARCHAR(ITR1."SrcObjTyp"))
    END                   AS "from_object_type",
    (CASE WHEN ITR1."SrcObjTyp" = 24 THEN ITR1."SrcObjAbs" END) AS "payment_doc_id",
    ITR1."ReconNum"       AS "recon_num",
    ITR1."ReconSum"       AS "recon_sum",
    ITR1."LineSeq"        AS "line_seq",
    OITR."ReconDate"      AS "recon_date",
    OITR."Canceled"       AS "recon_canceled"
FROM TELCHI.ITR1 AS ITR1
INNER JOIN TELCHI.OITR AS OITR
    ON ITR1."ReconNum" = OITR."ReconNum"
WHERE ITR1."SrcObjTyp" IN (13, 24, 14, 16, 25)
  AND OITR."ReconDate" >= :start_date
  AND OITR."ReconDate" < :end_date
-- =============================================================================
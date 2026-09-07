-- =============================================================================
-- ATOMIC SOURCE — SALE HEADER (P0) — grain OINV.DocEntry
-- =============================================================================
-- Fields CONFIRMED on HANA (2026-08-25). SAP identifiers preserved (§43).
-- Channel UDFs included: U_ORIGIN (SAP/DMS), U_SO1_* Retail One folio evidence.
-- =============================================================================
SELECT
    'SAP'                       AS "source_system",
    'AR_INVOICE'                AS "source_object_type",
    OINV."DocEntry"             AS "source_document_id",
    OINV."DocNum"               AS "source_document_number",
    OINV."ObjType"              AS "obj_type",
    OINV."CardCode"             AS "customer_id",
    OINV."SlpCode"              AS "seller_id",
    OINV."DocDate"              AS "business_date",
    OINV."TaxDate"              AS "posting_date",
    OINV."DocDueDate"           AS "due_date",
    OINV."DocTotal"             AS "amount_document",
    OINV."DocCur"               AS "currency",
    OINV."PaidToDate"           AS "paid_to_date",
    OINV."CANCELED"             AS "canceled",
    OINV."DocStatus"            AS "status",
    OINV."DocSubType"           AS "doc_sub_type",
    OINV."Series"               AS "series",
    OINV."CreateDate"           AS "created_at",
    OINV."UpdateDate"           AS "updated_at",
    OINV."UpdateTS"             AS "update_ts",
    OINV."NumAtCard"            AS "num_at_card",
    OINV."U_ORIGIN"             AS "channel_origin",
    OINV."U_TIPOVENTA"          AS "tipo_venta",
    OINV."U_DMS_STATE"          AS "dms_state",
    OINV."U_SO1_01RETAILONE"    AS "retail_one_flag",
    OINV."U_SO1_01FOLIORETAIL1" AS "retail_one_folio",
    OINV."U_SO1_01SUCURSAL"     AS "retail_one_sucursal",
    OINV."U_SO1_01PREFIJO"      AS "retail_one_prefijo"
FROM TELCHI.OINV AS OINV
WHERE OINV."DocDate" >= :start_date
  AND OINV."DocDate" < :end_date
-- =============================================================================
-- gate: ATOMIC-001 (P0 sale header) — grain uniqueness validated on HANA
-- =============================================================================
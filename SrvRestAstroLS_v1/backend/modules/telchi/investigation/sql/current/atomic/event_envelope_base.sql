-- =============================================================================
-- ATOMIC EVENT ENVELOPE — CONTRACT (base)
-- =============================================================================
-- Change: ATOMIC-001
-- Purpose: Canonical logical envelope for atomic facts (TELCHI spec §9/§10/§43).
-- This file is a CONTRACT document, not an executable query.
-- Physical mapping lives in the source_*_*.sql extractors.
-- Storage-independent: the model does not depend on parquet/postgres.
-- Field confidence: CONFIRMED = inspected on HANA; LEGACY_REFERENCED = code only;
--                   CANDIDATE  = must be investigated.
-- =============================================================================
-- ENVELOPE KEYS (logical) -> source (confirmed)
--   source_system            : 'SAP' | 'DMS' | 'RETAIL_ONE' (see U_* probes)
--   source_object_type       : e.g. 'AR_INVOICE' (OINV.ObjType 13)
--   source_document_id       : OINV.DocEntry
--   source_document_number   : OINV.DocNum
--   source_line_id           : INV1.LineNum
--   business_event_type      : SALE / PAYMENT / CASH / DELIVERY / INVENTORY_MOVEMENT
--   business_date            : OINV.DocDate (business)
--   posting_date             : OINV.TaxDate
--   event_at                 : OINV.CreateDate+UpdateTS
--   created_at / updated_at  : OINV.CreateDate / OINV.UpdateDate (cancellation date)
--   ingested_at              : ingestion timestamp (extractor)
--   customer_id / seller_id / item_id / branch_id / warehouse_id : SAP identifiers
--   currency / quantity / uom / amount_document / amount_local
--   status / cancelled      : DocStatus / CANCELED
-- =============================================================================
-- TEMPORAL RULE (§10):
--   Do NOT filter/join on DocDate alone. Sales can mutate economically later
--   (late cancellations).  Keep business_date, updated_at and cancelled separate.
SQLS

echo written
cat > source_sale_header.sql <<'SQL'
-- =============================================================================
-- ATOMIC SOURCE — SALE HEADER (P0) — grain OINV.DocEntry
-- =============================================================================
-- Fields CONFIRMED on HANA schema (2026-08-25). Includes channel UDFs.
-- SAP identifiers preserved for manual validation (§43).
-- =============================================================================
SELECT
    'SAP'              AS "source_system",
    'AR_INVOICE'       AS "source_object_type",
    OINV."DocEntry"    AS "source_document_id",
    OINV."DocNum"      AS "source_document_number",
    OINV."ObjType"     AS "obj_type",
    OINV."CardCode"    AS "customer_id",
    OINV."SlpCode"     AS "seller_id",
    OINV."DocDate"     AS "business_date",
    OINV."TaxDate"     AS "posting_date",
    OINV."DocDueDate"  AS "due_date",
    OINV."DocTotal"    AS "amount_document",
    OINV."DocCur"      AS "currency",
    OINV."PaidToDate"  AS "paid_to_date",
    OINV."CANCELED"    AS "canceled",
    OINV."DocStatus"   AS "status",
    OINV."DocSubType"  AS "doc_sub_type",
    OINV."Series"      AS "series",
    OINV."CreateDate"  AS "created_at",
    OINV."UpdateDate"  AS "updated_at",
    OINV."UpdateTS"    AS "update_ts",
    OINV."NumAtCard"   AS "num_at_card",
    OINV."U_ORIGIN"    AS "channel_origin",
    OINV."U_TIPOVENTA" AS "tipo_venta",
    OINV."U_DMS_STATE" AS "dms_state",
    OINV."U_SO1_01RETAILONE"   AS "retail_one_flag",
    OINV."U_SO1_01FOLIORETAIL1" AS "retail_one_folio",
    OINV."U_SO1_01SUCURSAL"    AS "retail_one_sucursal",
    OINV."U_SO1_01PREFIJO"     AS "retail_one_prefijo"
FROM TELCHI.OINV AS OINV
WHERE OINV."DocDate" >= :start_date
  AND OINV."DocDate" < :end_date

-- TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V1
-- Executed only after FoundationReader resolves the sole productive CURRENT.
-- Placeholders are replaced by run_analysis.py with snapshot-pinned relations
-- and exact paths recorded in that Foundation's sealed manifest.

CREATE TEMP VIEW product_business_type AS
SELECT * FROM read_parquet('__PRODUCT_BUSINESS_TYPE_PATH__');

CREATE TEMP VIEW warehouse_location AS
SELECT * FROM read_parquet('__WAREHOUSE_LOCATION_PATH__');

CREATE TEMP VIEW generic_review AS
SELECT * FROM read_parquet('__GENERIC_REVIEW_PATH__');

CREATE TEMP VIEW products AS
SELECT item_code, product_name
FROM read_parquet('__PRODUCTS_PATH__')
QUALIFY row_number() OVER (
  PARTITION BY item_code
  ORDER BY CASE source_system WHEN 'SAP_HANA' THEN 0 ELSE 1 END,
           canonical_product_id
) = 1;

CREATE TEMP VIEW salespersons AS
SELECT code, name
FROM read_parquet('__SALESPERSONS_PATH__')
WHERE source_system = 'SAP_HANA'
QUALIFY row_number() OVER (PARTITION BY code ORDER BY salesperson_id) = 1;

CREATE TEMP VIEW item_uom AS
SELECT ItemCode,
       CASE WHEN count(DISTINCT uom) = 1 THEN min(uom) ELSE 'MULTIPLE' END AS uom
FROM generic_review
WHERE CardCode = 'CG2A' AND product_business_type = 'RAW_MATERIAL'
GROUP BY ItemCode;

CREATE TEMP VIEW scoped_sales AS
SELECT d.source_system,
       d.source_table,
       d.doc_entry,
       d.doc_num,
       CAST(d.doc_date AS DATE) AS document_date,
       CAST(d.doc_due_date AS DATE) AS due_date,
       d.doc_status,
       d.card_code,
       d.currency AS document_currency,
       d.sales_channel_code,
       d.sales_channel_name,
       d.slp_code AS header_seller_code,
       l.line_num,
       l.item_code,
       l.whs_code,
       try_cast(l.quantity AS DECIMAL(38,6)) AS quantity,
       try_cast(l.line_total AS DECIMAL(38,6)) AS gross_amount,
       coalesce(l.attributed_slp_code, l.slp_code, d.slp_code) AS seller_code
FROM __SALES_DOCUMENT__ d
JOIN __SALES_LINE__ l
  ON l.source_system = d.source_system
 AND l.doc_entry = d.doc_entry
JOIN product_business_type p
  ON p.ItemCode = l.item_code
 AND p.product_business_type = 'RAW_MATERIAL'
WHERE d.card_code = 'CG2A'
  AND coalesce(d.canceled, 'N') <> 'Y'
  AND CAST(d.doc_date AS DATE) >= DATE '2026-01-01'
  AND CAST(d.doc_date AS DATE) < DATE '2027-01-01';

CREATE TEMP VIEW scoped_credits AS
SELECT d.source_system,
       d.source_table,
       d.doc_entry AS credit_doc_entry,
       d.doc_num AS credit_doc_num,
       CAST(d.doc_date AS DATE) AS credit_date,
       l.line_num AS credit_line_num,
       l.item_code,
       try_cast(l.quantity AS DECIMAL(38,6)) AS credit_quantity,
       try_cast(l.line_total AS DECIMAL(38,6)) AS credit_amount,
       l.base_type,
       l.base_entry,
       l.base_line
FROM __CREDIT_DOCUMENT__ d
JOIN __CREDIT_LINE__ l
  ON l.source_system = d.source_system
 AND l.doc_entry = d.doc_entry
JOIN product_business_type p
  ON p.ItemCode = l.item_code
 AND p.product_business_type = 'RAW_MATERIAL'
WHERE d.card_code = 'CG2A'
  AND coalesce(d.canceled, 'N') <> 'Y'
  AND CAST(d.doc_date AS DATE) >= DATE '2026-01-01'
  AND CAST(d.doc_date AS DATE) < DATE '2027-01-01';

CREATE TEMP VIEW credit_by_sales_line AS
SELECT s.source_system,
       s.doc_entry,
       s.line_num,
       sum(c.credit_amount) AS credit_amount,
       sum(c.credit_quantity) AS credit_quantity,
       string_agg(DISTINCT CAST(c.credit_doc_entry AS VARCHAR), ',' ORDER BY CAST(c.credit_doc_entry AS VARCHAR)) AS credit_doc_entries,
       string_agg(DISTINCT CAST(c.credit_doc_num AS VARCHAR), ',' ORDER BY CAST(c.credit_doc_num AS VARCHAR)) AS credit_doc_nums,
       max(c.credit_date) AS latest_credit_date
FROM scoped_sales s
JOIN scoped_credits c
  ON c.source_system = s.source_system
 AND try_cast(c.base_type AS INTEGER) = 13
 AND CAST(c.base_entry AS VARCHAR) = CAST(s.doc_entry AS VARCHAR)
 AND CAST(c.base_line AS VARCHAR) = CAST(s.line_num AS VARCHAR)
 AND c.item_code = s.item_code
GROUP BY s.source_system, s.doc_entry, s.line_num;

CREATE TEMP TABLE line_detail AS
SELECT s.source_system || '|' || s.source_table || '|' || CAST(s.doc_entry AS VARCHAR) AS document_id,
       s.source_system,
       s.source_table,
       s.doc_entry,
       s.doc_num,
       s.document_date,
       s.due_date,
       s.doc_status,
       s.card_code,
       s.line_num,
       s.item_code,
       p.product_name,
       'RAW_MATERIAL' AS product_business_class,
       s.quantity,
       coalesce(iu.uom, 'UNAVAILABLE') AS uom,
       s.document_currency AS currency,
       s.gross_amount,
       coalesce(c.credit_amount, 0::DECIMAL(38,6)) AS credit_memo_amount,
       s.gross_amount - coalesce(c.credit_amount, 0::DECIMAL(38,6)) AS net_amount,
       c.credit_doc_entries,
       c.credit_doc_nums,
       c.latest_credit_date,
       s.seller_code,
       coalesce(sp.name, 'UNKNOWN') AS seller_name,
       s.whs_code AS warehouse,
       coalesce(wl.business_location_code, 'UNKNOWN') AS business_location,
       s.sales_channel_code,
       s.sales_channel_name
FROM scoped_sales s
LEFT JOIN credit_by_sales_line c
  ON c.source_system = s.source_system
 AND c.doc_entry = s.doc_entry
 AND c.line_num = s.line_num
LEFT JOIN products p ON p.item_code = s.item_code
LEFT JOIN item_uom iu ON iu.ItemCode = s.item_code
LEFT JOIN salespersons sp ON sp.code = s.seller_code
LEFT JOIN warehouse_location wl
  ON wl.warehouse_code = s.whs_code
 AND wl.source_system = 'SAP_HANA';

CREATE TEMP TABLE document_detail AS
SELECT document_id,
       any_value(source_system) AS source_system,
       any_value(source_table) AS source_table,
       any_value(doc_entry) AS doc_entry,
       any_value(doc_num) AS doc_num,
       any_value(document_date) AS document_date,
       any_value(due_date) AS due_date,
       any_value(doc_status) AS document_status,
       any_value(card_code) AS card_code,
       string_agg(DISTINCT item_code, ',' ORDER BY item_code) AS item_codes,
       string_agg(DISTINCT coalesce(product_name, item_code), ' | ' ORDER BY coalesce(product_name, item_code)) AS products,
       string_agg(DISTINCT uom, ',' ORDER BY uom) AS units_of_measure,
       sum(quantity) AS raw_material_quantity_unconverted,
       any_value(currency) AS currency,
       sum(gross_amount) AS gross_amount,
       sum(credit_memo_amount) AS associated_credit_memo_amount,
       sum(net_amount) AS net_amount,
       string_agg(DISTINCT credit_doc_entries, ',' ORDER BY credit_doc_entries)
         FILTER (WHERE credit_doc_entries IS NOT NULL) AS associated_credit_doc_entries,
       max(latest_credit_date) AS latest_credit_date,
       string_agg(DISTINCT CAST(seller_code AS VARCHAR), ',' ORDER BY CAST(seller_code AS VARCHAR)) AS seller_codes,
       string_agg(DISTINCT seller_name, ' | ' ORDER BY seller_name) AS sellers,
       string_agg(DISTINCT warehouse, ',' ORDER BY warehouse) AS warehouses,
       string_agg(DISTINCT business_location, ',' ORDER BY business_location) AS business_locations,
       string_agg(DISTINCT coalesce(sales_channel_name, sales_channel_code, 'UNKNOWN'), ',' ORDER BY coalesce(sales_channel_name, sales_channel_code, 'UNKNOWN')) AS sales_channels,
       CAST(NULL AS VARCHAR) AS payment_term_documental,
       CAST(NULL AS DATE) AS payment_date,
       CAST(NULL AS VARCHAR) AS payment_means,
       CAST(NULL AS DECIMAL(38,6)) AS paid_amount,
       CAST(NULL AS DECIMAL(38,6)) AS open_balance,
       CAST(NULL AS VARCHAR) AS reconciliation_id,
       CAST(NULL AS INTEGER) AS days_sale_to_payment,
       'NOT_DETERMINABLE' AS payment_classification,
       'Foundation CURRENT has sales and linked credit-note evidence, but no transactional payment, receipt, reconciliation, open-balance, settlement-date or payment-means dataset. Due date and document status do not prove effective payment.' AS classification_reason
FROM line_detail
GROUP BY document_id;

CREATE TEMP TABLE summary_by_modality AS
WITH grouped AS (
  SELECT payment_classification AS modality,
         count(*) AS documents,
         sum(net_amount) AS net_amount
  FROM document_detail
  GROUP BY payment_classification
), totals AS (
  SELECT count(*) AS documents, sum(net_amount) AS net_amount FROM document_detail
), categories(modality, sort_order) AS (
  VALUES ('CONTADO_CONFIRMED', 1), ('CREDIT_CONFIRMED', 2),
         ('OTHER_PAYMENT_MODE', 3), ('NOT_DETERMINABLE', 4)
)
SELECT c.modality,
       coalesce(g.documents, 0) AS documents,
       CASE WHEN t.documents = 0 THEN 0 ELSE round(100.0 * coalesce(g.documents, 0) / t.documents, 4) END AS document_percent,
       coalesce(g.net_amount, 0::DECIMAL(38,6)) AS net_amount,
       CASE WHEN t.net_amount = 0 THEN 0 ELSE round(100.0 * coalesce(g.net_amount, 0) / t.net_amount, 4) END AS net_amount_percent
FROM categories c
LEFT JOIN grouped g USING(modality)
CROSS JOIN totals t
ORDER BY c.sort_order;

CREATE TEMP TABLE summary_by_product AS
SELECT item_code,
       any_value(product_name) AS product_description,
       count(DISTINCT document_id) AS documents,
       sum(quantity) AS quantity,
       any_value(uom) AS uom,
       sum(gross_amount) AS gross_sales,
       sum(credit_memo_amount) AS credit_memos,
       sum(net_amount) AS net_sales,
       'NOT_DETERMINABLE' AS modality
FROM line_detail
GROUP BY item_code
ORDER BY net_sales DESC, item_code;

CREATE TEMP TABLE summary_by_month AS
SELECT strftime(document_date, '%Y-%m') AS month,
       count(*) AS documents,
       sum(gross_amount) AS gross_sales,
       sum(associated_credit_memo_amount) AS credit_memos,
       sum(net_amount) AS net_sales,
       count(*) FILTER (WHERE payment_classification = 'CONTADO_CONFIRMED') AS contado_confirmed,
       count(*) FILTER (WHERE payment_classification = 'CREDIT_CONFIRMED') AS credit_confirmed,
       count(*) FILTER (WHERE payment_classification = 'OTHER_PAYMENT_MODE') AS other_payment_mode,
       count(*) FILTER (WHERE payment_classification = 'NOT_DETERMINABLE') AS not_determinable
FROM document_detail
GROUP BY month
ORDER BY month;

CREATE TEMP TABLE summary_by_seller AS
SELECT seller_code,
       any_value(seller_name) AS seller_name,
       count(DISTINCT document_id) AS documents,
       sum(gross_amount) AS gross_sales,
       sum(credit_memo_amount) AS credit_memos,
       sum(net_amount) AS net_sales,
       count(DISTINCT document_id) FILTER (WHERE 'NOT_DETERMINABLE' = 'CONTADO_CONFIRMED') AS contado_confirmed,
       count(DISTINCT document_id) FILTER (WHERE 'NOT_DETERMINABLE' = 'CREDIT_CONFIRMED') AS credit_confirmed,
       count(DISTINCT document_id) FILTER (WHERE 'NOT_DETERMINABLE' = 'OTHER_PAYMENT_MODE') AS other_payment_mode,
       count(DISTINCT document_id) AS not_determinable
FROM line_detail
GROUP BY seller_code
ORDER BY net_sales DESC, seller_code;

CREATE TEMP TABLE quality_controls AS
WITH sales_control AS (
  SELECT count(DISTINCT document_id) AS documents,
         count(DISTINCT document_date) AS sale_days,
         count(DISTINCT item_code) AS skus,
         min(document_date) AS first_sale,
         max(document_date) AS last_sale,
         sum(gross_amount) AS gross_sales,
         sum(credit_memo_amount) AS credit_memos,
         sum(net_amount) AS net_sales,
         count(DISTINCT seller_code) AS sellers,
         count(DISTINCT warehouse) AS warehouses,
         count(DISTINCT business_location) AS business_locations
  FROM line_detail
), credit_control AS (
  SELECT count(*) AS credit_lines,
         count(*) FILTER (WHERE s.doc_entry IS NOT NULL) AS linked_credit_lines,
         sum(c.credit_amount) AS credit_amount,
         sum(c.credit_amount) FILTER (WHERE s.doc_entry IS NOT NULL) AS linked_credit_amount
  FROM scoped_credits c
  LEFT JOIN scoped_sales s
    ON c.source_system = s.source_system
   AND try_cast(c.base_type AS INTEGER) = 13
   AND CAST(c.base_entry AS VARCHAR) = CAST(s.doc_entry AS VARCHAR)
   AND CAST(c.base_line AS VARCHAR) = CAST(s.line_num AS VARCHAR)
   AND c.item_code = s.item_code
)
SELECT sc.*,
       cc.credit_lines,
       cc.linked_credit_lines,
       cc.credit_amount,
       cc.linked_credit_amount,
       sc.gross_sales - sc.credit_memos AS recomputed_net_sales,
       sc.net_sales - (sc.gross_sales - sc.credit_memos) AS monetary_reconciliation_delta,
       (SELECT count(*) FROM document_detail WHERE payment_classification = 'NOT_DETERMINABLE') AS not_determinable_documents,
       (SELECT count(*) FROM document_detail) AS classified_documents
FROM sales_control sc CROSS JOIN credit_control cc;

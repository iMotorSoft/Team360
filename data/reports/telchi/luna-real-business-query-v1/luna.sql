-- Exact SQL proposals from the final Luna investigation; publication/snapshot in luna.json.
-- 1. Discover published sales categories/currencies/months.
SELECT doc_month AS doc_month, currency AS currency, product_business_type AS product_business_type, COUNT(doc_entry) AS line_count, SUM(line_total) AS line_amount FROM sales_operation WHERE doc_month >= '2026-01' AND doc_month <= '2026-12' GROUP BY doc_month, currency, product_business_type ORDER BY doc_month, currency, product_business_type;

-- 2. Rank months in the business raw-material universe.
SELECT doc_month AS doc_month, sum(line_total) AS line_amount, count(doc_entry) AS line_count FROM sales_operation WHERE doc_month >= '2026-01' AND doc_month <= '2026-12' AND currency = 'BS' AND product_business_type = 'RAW_MATERIAL' GROUP BY doc_month ORDER BY line_amount DESC;

-- 3. Rank billed SAP customers in the observed winning month.
SELECT card_code, card_name, sum(line_total) AS line_amount, count(doc_entry) AS line_count FROM sales_operation WHERE doc_month = '2026-08' AND currency = 'BS' AND product_business_type = 'RAW_MATERIAL' GROUP BY card_code, card_name ORDER BY line_amount DESC LIMIT 3;

-- 4. Recheck the leading customer.
SELECT card_code AS card_code, card_name AS card_name, sum(line_total) AS line_amount, count(doc_entry) AS line_count FROM sales_operation WHERE doc_month = '2026-08' AND currency = 'BS' AND product_business_type = 'RAW_MATERIAL' GROUP BY card_code, card_name ORDER BY line_amount DESC LIMIT 1;

-- 5. Reconcile the winning month.
SELECT sum(line_total) AS total_amount_bs, count(doc_entry) AS total_line_count FROM sales_operation WHERE doc_month = '2026-08' AND currency = 'BS' AND product_business_type = 'RAW_MATERIAL';

-- 6. Recheck monthly ranking.
SELECT doc_month, sum(line_total) AS total_amount_bs, count(doc_entry) AS total_line_count FROM sales_operation WHERE doc_month >= '2026-01' AND doc_month <= '2026-12' AND currency = 'BS' AND product_business_type = 'RAW_MATERIAL' GROUP BY doc_month ORDER BY total_amount_bs DESC;

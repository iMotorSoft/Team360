"""Products analysis: 2022 vs 2026, article by article, net line amounts (Bs).

Universes:
  * LAB_FINISHED_PRODUCT (VALIDATED) = productos terminados de laboratorio
  * FRACTIONATED_PRODUCT (VALIDATED) = fraccionados, reported separately
  * TRADED_PRODUCT = reventa, explicit comparison group

Sources:
  * 2022-01-01..2022-04-05: legacy saleProduct (legacy ProductCode) mapped to SAP ItemCode
    through SAP master U_ codactive.
  * 2022-04-06..2022-09-30: SAP B1 saleSB1Product.
  * 2026-01-01..2026-09-30: pinned Foundation sales_line/sales_document.
"""
import json

import duckdb

OUT = "/tmp/opencode/telchi-hist"
BT = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/crosswalk/_versions/v2_product_business_type_f9c1130d852ccb61/product_business_type/part-00000.parquet"
if not __import__("os").path.exists(BT):
    BT = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/crosswalk/product_business_type/part-00000.parquet"

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")

con.execute(f"CREATE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
con.execute(f"CREATE VIEW fc AS SELECT * FROM read_parquet('{OUT}/extract/foundation_credit_lines.parquet')")
con.execute(f"CREATE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")
con.execute(f"CREATE VIEW lg AS SELECT * FROM read_parquet('{OUT}/extract/legacy_sales_2022.parquet')")
con.execute(f"CREATE VIEW cw AS SELECT * FROM read_parquet('{OUT}/out/crosswalk_sap_legacy.parquet')")
con.execute(f"CREATE VIEW bt AS SELECT * FROM read_parquet('{BT}')")

# 1:1 crosswalk only; ambiguous legacy codes stay separate
con.execute("""
CREATE OR REPLACE TABLE cw11 AS
SELECT legacy_product_code, any_value(sap_item_code) sap_item_code, count(DISTINCT sap_item_code) n
FROM cw WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
GROUP BY 1
""")

# 2022 Q1 legacy facts
con.execute("""
CREATE OR REPLACE TABLE p2022_q1 AS
SELECT '2022Q1' period, 'LEGACY' AS src, l.ProductCode, l.ProductName, l.OfficeName,
       l.ProductSaleCant qty, l.ProductSalePriceNet amount, l.SaleDate::DATE d, l.SaleCode doc,
       CASE WHEN c.n=1 THEN c.sap_item_code ELSE NULL END item_code,
       CASE WHEN c.legacy_product_code IS NULL THEN 'UNMAPPED'
            WHEN c.n>1 THEN 'AMBIGUOUS_1N' ELSE 'MAPPED_1_1' END map_status
FROM lg l LEFT JOIN cw11 c ON c.legacy_product_code=l.ProductCode
WHERE l.SaleCode <> 3247102
""")

# 2022 Apr-Sep SAP facts
con.execute("""
CREATE OR REPLACE TABLE p2022_sap AS
SELECT '2022SAP' period, 'SAP_B1' AS src, NULL ProductCode, ItemName ProductName, OfficeName,
       ItemSaleCant qty, ItemSale amount, DocDate::DATE d, DocEntry doc,
       ItemCode item_code, 'SAP_NATIVE' map_status
FROM ls WHERE u_estadofc<>'A' AND DocDate>='2022-04-06' AND DocDate<'2022-10-01'
""")

# 2026
con.execute("""
CREATE OR REPLACE TABLE p2026 AS
SELECT '2026' period, 'FOUNDATION' AS src, NULL ProductCode, NULL ProductName, whs_code OfficeName,
       cast(quantity AS DOUBLE) qty, cast(line_total AS DECIMAL(38,6)) amount, doc_date::DATE d,
       doc_entry doc, item_code, 'SAP_NATIVE' map_status
FROM fs WHERE canceled='N' AND doc_currency='BS'
  AND doc_date>='2026-01-01' AND doc_date<'2026-10-01'
""")

con.execute("""
CREATE OR REPLACE TABLE facts AS
SELECT * FROM p2022_q1 UNION ALL SELECT * FROM p2022_sap UNION ALL SELECT * FROM p2026
""")

# Canonical product key: SAP item when resolved, else legacy pseudo-key
con.execute("""
CREATE OR REPLACE TABLE facts2 AS
SELECT f.*, COALESCE(f.item_code, 'LEGACY:' || f.ProductCode) product_key,
       COALESCE(b.product_business_type,'UNCLASSIFIED') btype,
       COALESCE(b.status,'UNCLASSIFIED') bstatus
FROM facts f
LEFT JOIN bt b ON b.ItemCode = f.item_code
""")

# ---- totals by business type and period
tot = con.execute("""
SELECT period, btype, bstatus, count(*) lines, sum(amount) amt,
       count(DISTINCT product_key) skus
FROM facts2 WHERE period IN ('2022Q1','2022SAP','2026')
GROUP BY 1,2,3 ORDER BY 1,4 DESC
""").fetchall()
print("== totals by type")
for r in tot:
    print(r)

# ---- combined 2022 (Q1 + Apr-Sep)
con.execute("""
CREATE OR REPLACE TABLE y2022 AS
SELECT '2022' AS yr, product_key, any_value(item_code) item_code, any_value(ProductName) legacy_name,
       btype, bstatus, sum(amount) amount, sum(qty) qty, count(*) lines,
       sum(CASE WHEN map_status='UNMAPPED' THEN amount ELSE 0 END) unmapped_amt,
       count(DISTINCT doc) docs, any_value(OfficeName) any_office
FROM facts2 WHERE period IN ('2022Q1','2022SAP') GROUP BY 1,2,5,6
""")
con.execute("""
CREATE OR REPLACE TABLE y2026 AS
SELECT '2026' AS yr, product_key, any_value(item_code) item_code, NULL legacy_name,
       btype, bstatus, sum(amount) amount, sum(qty) qty, count(*) lines, 0 unmapped_amt,
       count(DISTINCT doc) docs, any_value(OfficeName) any_office
FROM facts2 WHERE period='2026' GROUP BY 1,2,5,6
""")

print("== annual totals by year/type")
for r in con.execute("""
SELECT yr, btype, sum(amount) amt, count(DISTINCT product_key) skus FROM (
 SELECT * FROM y2022 UNION ALL SELECT * FROM y2026) GROUP BY 1,2 ORDER BY 1,3 DESC""").fetchall():
    print(r)

# ---- SKU comparison for LAB_FINISHED_PRODUCT
con.execute("""
CREATE OR REPLACE TABLE cmp AS
SELECT COALESCE(a.product_key,b.product_key) product_key,
       COALESCE(a.item_code,b.item_code) item_code,
       COALESCE(b.btype,a.btype) btype,
       a.amount amt22, b.amount amt26, a.qty qty22, b.qty qty26, a.legacy_name,
       CASE WHEN a.product_key IS NULL THEN 'NEW_2026'
            WHEN b.product_key IS NULL THEN 'DROPPED_2026' ELSE 'BOTH' END status
FROM y2022 a FULL OUTER JOIN y2026 b ON a.product_key=b.product_key
WHERE COALESCE(b.btype,a.btype)='LAB_FINISHED_PRODUCT'
""")

summary = {}
summary["lab_finished"] = con.execute("""
SELECT count(*) skus,
 count(*) FILTER (WHERE status='BOTH') both_skus,
 count(*) FILTER (WHERE status='DROPPED_2026') dropped_skus,
 count(*) FILTER (WHERE status='NEW_2026') new_skus,
 sum(amt22) amt22, sum(amt26) amt26,
 sum(CASE WHEN status='BOTH' THEN amt22 ELSE 0 END) both_amt22,
 sum(CASE WHEN status='BOTH' THEN amt26 ELSE 0 END) both_amt26
FROM cmp""").fetchall()
print("== LAB_FINISHED summary", summary["lab_finished"])

print("== top growth")
for r in con.execute("""
SELECT item_code, left(any_value(legacy_name),45), amt22, amt26, amt26-COALESCE(amt22,0) delta
FROM cmp WHERE status='NEW_2026' OR status='BOTH'
GROUP BY 1,3,4 ORDER BY delta DESC NULLS LAST LIMIT 15""").fetchall():
    print(r)

print("== top drops")
for r in con.execute("""
SELECT item_code, left(any_value(legacy_name),45), amt22, amt26, amt22-COALESCE(amt26,0) delta
FROM cmp WHERE status='DROPPED_2026' OR status='BOTH'
GROUP BY 1,3,4 ORDER BY delta DESC NULLS LAST LIMIT 15""").fetchall():
    print(r)

# ---- price / volume decomposition on common SKUs with compatible UoM
con.execute("""
CREATE OR REPLACE TABLE decomp AS
SELECT c.item_code, c.legacy_name, c.amt22, c.amt26, c.qty22, c.qty26,
       c.amt22/NULLIF(c.qty22,0) p22, c.amt26/NULLIF(c.qty26,0) p26,
       (c.amt26-c.amt22) delta,
       (c.amt26/NULLIF(c.qty26,0) - c.amt22/NULLIF(c.qty22,0))*c.qty26 price_effect,
       (c.qty26-c.qty22)*(c.amt22/NULLIF(c.qty22,0)) volume_effect
FROM cmp c WHERE c.status='BOTH' AND c.qty22>0 AND c.qty26 IS NOT NULL
""")
print("== decomposition", con.execute("""
SELECT count(*) skus, sum(delta) delta, sum(price_effect) price, sum(volume_effect) volume,
       sum(delta-price_effect-volume_effect) residual, sum(amt22) a22, sum(amt26) a26 FROM decomp""").fetchall())

# ---- compat UoM check for quantities
print("== qty disaggregation guard: SKUs with qty unit change unknown")
print(con.execute("""
SELECT count(*) FROM cmp WHERE status='BOTH' AND qty22>0 AND qty26>0
 AND abs((amt26/qty26)/(amt22/qty22)) > 1000""").fetchall())

con.execute(f"COPY (SELECT * FROM cmp) TO '{OUT}/out/products_cmp.parquet' (FORMAT PARQUET)")
con.execute(f"COPY (SELECT * FROM facts2) TO '{OUT}/out/facts_all.parquet' (FORMAT PARQUET)")

json.dump({k: [list(map(str, r)) for r in v] for k, v in summary.items()}, open(f"{OUT}/out/products_summary.json", "w"), indent=1)

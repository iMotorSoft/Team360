import json

import duckdb

OUT = "/tmp/opencode/telchi-hist"
con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")

con.execute(f"CREATE OR REPLACE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
con.execute(f"CREATE OR REPLACE VIEW fc AS SELECT * FROM read_parquet('{OUT}/extract/foundation_credit_lines.parquet')")
con.execute(f"CREATE OR REPLACE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")
con.execute(f"CREATE OR REPLACE VIEW lc AS SELECT * FROM read_parquet('{OUT}/extract/sap_credit_2022_2024.parquet')")
con.execute(f"CREATE OR REPLACE VIEW lg AS SELECT * FROM read_parquet('{OUT}/extract/legacy_sales_2022.parquet')")

r = {}
r["foundation_sales"] = con.execute("""
SELECT doc_currency, canceled, count(*) lines, sum(cast(line_total AS DECIMAL(38,6))) amt,
       count(DISTINCT doc_entry) docs
FROM fs WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01' GROUP BY 1,2 ORDER BY 3 DESC""").fetchall()
r["foundation_credits"] = con.execute("""
SELECT doc_currency, canceled, count(*) lines, sum(cast(line_total AS DECIMAL(38,6))) amt
FROM fc WHERE doc_date>='2026-01-01' AND doc_date<'2026-10-01' GROUP BY 1,2 ORDER BY 3 DESC""").fetchall()
r["sap_legacy_status"] = con.execute("""
SELECT u_estadofc, DocStatus, count(*) lines, sum(ItemSale) amt, count(DISTINCT DocEntry) docs
FROM ls WHERE DocDate>='2022-04-01' AND DocDate<'2022-10-01' GROUP BY 1,2 ORDER BY 3 DESC""").fetchall()
r["sap_legacy_credit_status"] = con.execute("""
SELECT fu_estadofc, DocStatus, count(*) lines, sum(ItemSale) amt FROM lc WHERE DocDate<'2022-10-01' GROUP BY 1,2""").fetchall()
r["monthly_2022"] = con.execute("""
SELECT 'legacy' src, strftime(date_trunc('month', SaleDate),'%Y-%m') ym, count(*) lines,
       sum(ProductSalePriceNet) amt, count(DISTINCT SaleCode) docs, count(DISTINCT ProductCode) items
FROM lg GROUP BY 1,2
UNION ALL
SELECT 'sap', strftime(date_trunc('month', DocDate),'%Y-%m'), count(*), sum(ItemSale), count(DISTINCT DocEntry), count(DISTINCT ItemCode)
FROM ls WHERE DocDate<'2023-01-01' AND u_estadofc<>'A' GROUP BY 1,2
ORDER BY 2,1""").fetchall()
r["daily_april_2022"] = con.execute("""
SELECT 'legacy' s, SaleDate::DATE d, sum(ProductSalePriceNet) amt, count(*) n FROM lg WHERE SaleDate>='2022-03-25' GROUP BY 1,2
UNION ALL
SELECT 'sap', DocDate::DATE, sum(ItemSale), count(*) FROM ls WHERE DocDate>='2022-03-25' AND DocDate<'2022-04-15' AND u_estadofc<>'A' GROUP BY 1,2
ORDER BY 2,1""").fetchall()
r["monthly_2026"] = con.execute("""
SELECT strftime(date_trunc('month', doc_date::TIMESTAMP),'%Y-%m') ym, count(*) lines,
       sum(cast(line_total AS DECIMAL(38,6))) amt, count(DISTINCT doc_entry) docs,
       count(DISTINCT item_code) items
FROM fs WHERE canceled='N' AND doc_currency='BS' AND doc_date>='2026-01-01' AND doc_date<'2026-10-01'
GROUP BY 1 ORDER BY 1""").fetchall()
r["whs_2026"] = con.execute("""
SELECT whs_code, count(*) lines, sum(cast(line_total AS DECIMAL(38,6))) amt
FROM fs WHERE canceled='N' AND doc_currency='BS' AND doc_date>='2026-01-01' AND doc_date<'2026-10-01'
GROUP BY 1 ORDER BY 3 DESC""").fetchall()
for k, v in r.items():
    print("==", k)
    for row in v:
        print(row)
json.dump({k: [list(map(str, row)) for row in v] for k, v in r.items()}, open(f"{OUT}/out/coverage_probe.json", "w"), indent=1, ensure_ascii=False)

"""Credit notes (devoluciones) and anomaly sensitivities on top of the 2022 vs 2026 comparison."""
import json

import duckdb

OUT = "/tmp/opencode/telchi-hist"
BT = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/crosswalk/_versions/v2_product_business_type_f9c1130d852ccb61/product_business_type/part-00000.parquet"

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW fc AS SELECT * FROM read_parquet('{OUT}/extract/foundation_credit_lines.parquet')")
con.execute(f"CREATE VIEW sc AS SELECT * FROM read_parquet('{OUT}/extract/sap_credit_2022_2024.parquet')")
con.execute(f"CREATE VIEW lg AS SELECT * FROM read_parquet('{OUT}/extract/legacy_sales_2022.parquet')")
con.execute(f"CREATE VIEW cw AS SELECT * FROM read_parquet('{OUT}/out/crosswalk_sap_legacy.parquet')")
con.execute(f"CREATE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")
con.execute(f"CREATE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
con.execute(f"CREATE VIEW bt AS SELECT * FROM read_parquet('{BT}')")

out = {}

# ---- credits by business type
def credits(sql, params=None):
    return con.execute(sql, params or []).fetchall()


c26 = credits("""
SELECT COALESCE(b.product_business_type,'UNCLASSIFIED') btype,
       count(*) lines, count(DISTINCT c.doc_entry) docs,
       sum(cast(c.line_total AS DOUBLE)) amt
FROM fc c LEFT JOIN bt b ON b.ItemCode=c.item_code
WHERE c.canceled='N' AND c.doc_currency='BS'
  AND c.doc_date>='2026-01-01' AND c.doc_date<'2026-10-01'
GROUP BY 1 ORDER BY 4 DESC
""")
out["credits_2026"] = [{"btype": r[0], "lines": r[1], "docs": r[2], "amt": float(r[3] or 0)} for r in c26]
print("== credits 2026", out["credits_2026"])

c22 = credits("""
SELECT COALESCE(b.product_business_type,'UNCLASSIFIED') btype,
       count(*) lines, count(DISTINCT s.DocEntry) docs,
       sum(s.ItemSale) amt
FROM sc s LEFT JOIN bt b ON b.ItemCode=s.ItemCode
WHERE s.fu_estadofc<>'A' AND s.DocDate>='2022-04-06' AND s.DocDate<'2022-10-01'
GROUP BY 1 ORDER BY 4 DESC
""")
out["credits_2022_sap"] = [{"btype": r[0], "lines": r[1], "docs": r[2], "amt": float(r[3] or 0)} for r in c22]
print("== credits Apr-Sep 2022", out["credits_2022_sap"])

# legacy "Devolucion" and negative lines in Q1 2022
leg = con.execute("""
SELECT count(*) lines, sum(ProductSalePriceNet) amt
FROM lg WHERE ProductSalePriceNet<0 AND SaleCode<>3247102
""").fetchone()
out["legacy_negative_q1"] = {"lines": leg[0], "amt": float(leg[1] or 0)}
print("== legacy negative lines Q1", out["legacy_negative_q1"])

# ---- net LAB_FINISHED with and without credits
lf = con.execute("""
SELECT btype, sum(a.amount) gross22, sum(b.amount26) gross26 FROM (
  SELECT btype, sum(amount) amount, 0 amount26 FROM read_parquet('/tmp/opencode/telchi-hist/out/facts_all.parquet')
  WHERE period IN ('2022Q1','2022SAP') GROUP BY 1
) a FULL OUTER JOIN (
  SELECT btype, 0 amount, sum(amount) amount26 FROM read_parquet('/tmp/opencode/telchi-hist/out/facts_all.parquet')
  WHERE period='2026' GROUP BY 1
) b USING (btype) GROUP BY 1 ORDER BY gross26 DESC
""").fetchall()
out["lab_finished_gross"] = [{"btype": r[0], "gross22": float(r[1] or 0), "gross26": float(r[2] or 0)} for r in lf]
print("== gross by btype")
for r in out["lab_finished_gross"]:
    print(r)

# ---- anomaly sensitivity: SaleCode 3247102 (2022-02-02, ACIDO ACETICO)
an = con.execute("""
SELECT ProductCode, any_value(ProductName), sum(ProductSaleCant) qty, sum(ProductSalePriceNet) amt,
       count(*) lines, min(SaleDate) d
FROM lg WHERE SaleCode=3247102 GROUP BY 1
""").fetchall()
out["anomaly_3247102"] = [{"product_code": r[0], "name": r[1], "qty": float(r[2]),
                           "amt": float(r[3]), "lines": r[4], "date": str(r[5])} for r in an]
print("== anomaly 3247102", out["anomaly_3247102"])

# ---- tender sensitivity: L02924 ALCOHOL 70% LICITACION (2022, Lab, SOLUTESA/DISPROMED)
tnd = con.execute("""
SELECT count(DISTINCT DocEntry) docs, sum(ItemSaleCant) qty, sum(ItemSale) amt,
       count(DISTINCT CardName) clients, min(DocDate)::VARCHAR, max(DocDate)::VARCHAR
FROM ls WHERE ItemCode='L02924' AND DocDate>='2022-04-06' AND DocDate<'2022-10-01'
""").fetchone()
out["tender_L02924"] = {"docs": tnd[0], "qty": float(tnd[1]), "amt": float(tnd[2]),
                        "clients": tnd[3], "first": tnd[4], "last": tnd[5]}
print("== tender L02924", out["tender_L02924"])

json.dump(out, open(f"{OUT}/out/credits.json", "w"), indent=1, ensure_ascii=False)

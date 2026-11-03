"""Final consolidated metrics for the report (all from the read-only extracts)."""
import json

import duckdb

OUT = "/tmp/opencode/telchi-hist"
BT = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/crosswalk/_versions/v2_product_business_type_f9c1130d852ccb61/product_business_type/part-00000.parquet"

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW f AS SELECT * FROM read_parquet('{OUT}/out/facts_all.parquet')")
con.execute(f"CREATE VIEW cmp AS SELECT * FROM read_parquet('{OUT}/out/products_cmp.parquet')")
con.execute(f"CREATE VIEW cw AS SELECT * FROM read_parquet('{OUT}/out/crosswalk_sap_legacy.parquet')")

res = {}

# ---- totals per period / type
res["totals"] = [
    {"period": r[0], "btype": r[1], "amount": float(r[2]), "lines": r[3], "skus": r[4]}
    for r in con.execute("""
    SELECT period, btype, sum(amount), count(*), count(DISTINCT product_key)
    FROM f GROUP BY 1,2 ORDER BY 1,3 DESC""").fetchall()
]
print("== totals")
for r in res["totals"]:
    print(r)

# ---- period totals
res["period_total"] = [
    {"period": r[0], "amount": float(r[1]), "lines": r[2], "docs": r[3]}
    for r in con.execute("""
    SELECT period, sum(amount), count(*), count(DISTINCT doc) FROM f GROUP BY 1""").fetchall()
]

# ---- LAB_FINISHED product comparison
lab = con.execute("""
SELECT count(*) filter (WHERE status='BOTH'),
       count(*) filter (WHERE status='DROPPED_2026'),
       count(*) filter (WHERE status='NEW_2026'),
       sum(amt22), sum(amt26),
       sum(amt22) filter (WHERE status='BOTH'), sum(amt26) filter (WHERE status='BOTH'),
       sum(amt22) filter (WHERE status='DROPPED_2026'), sum(amt26) filter (WHERE status='NEW_2026')
FROM cmp WHERE btype='LAB_FINISHED_PRODUCT'
""").fetchone()
res["lab_finished"] = dict(zip(
    ["both_skus", "dropped_skus", "new_skus", "amt22", "amt26", "both_amt22", "both_amt26",
     "dropped_amt22", "new_amt26"], [float(x or 0) if i not in (0, 1, 2) else x
                                     for i, x in enumerate(lab)]))
print("== LAB_FINISHED", res["lab_finished"])

# price/volume decomposition exact
dec = con.execute("""
SELECT count(*), sum(delta), sum(price_effect), sum(volume_effect),
       sum(delta-price_effect-volume_effect), sum(amt22), sum(amt26),
       median(ratio), quantile_cont(ratio, 0.25), quantile_cont(ratio, 0.75),
       sum(amt26*ratio)/sum(amt26)
FROM (
  SELECT c.amt26-c.amt22 delta,
         (c.amt26/c.qty26 - c.amt22/c.qty22)*c.qty26 price_effect,
         (c.qty26-c.qty22)*(c.amt22/c.qty22) volume_effect,
         c.amt22, c.amt26, (c.amt26/c.qty26)/(c.amt22/c.qty22) ratio
  FROM cmp c WHERE c.btype='LAB_FINISHED_PRODUCT' AND c.status='BOTH' AND c.qty22>0 AND c.qty26>0
)
""").fetchone()
res["decomposition"] = dict(zip(
    ["skus", "delta", "price_effect", "volume_effect", "residual", "amt22", "amt26",
     "median_ratio", "p25_ratio", "p75_ratio", "weighted_ratio"],
    [float(x) if x is not None else None for x in dec]))
print("== decomposition", res["decomposition"])

# top products per period
def top(period_expr, n=12):
    return [{"item": r[0], "name": r[1], "amount": float(r[2]), "qty": float(r[3] or 0)}
            for r in con.execute(f"""
    SELECT product_key, COALESCE(any_value(ProductName), any_value(sap_name)), sum(amount), sum(qty)
    FROM (SELECT f.*, cw.sap_name FROM f LEFT JOIN
          (SELECT sap_item_code, any_value(sap_name) sap_name FROM cw GROUP BY 1) cw
          ON cw.sap_item_code=f.item_code)
    WHERE btype='LAB_FINISHED_PRODUCT' AND {period_expr}
    GROUP BY 1 ORDER BY 3 DESC LIMIT {n}""").fetchall()]

res["top_2022"] = top("period IN ('2022Q1','2022SAP')")
res["top_2026"] = top("period='2026'")
print("== top 2022")
for r in res["top_2022"]:
    print(f"{r['item']:10s} {r['amount']:>12,.0f} {str(r['name'])[:55]}")
print("== top 2026")
for r in res["top_2026"]:
    print(f"{r['item']:10s} {r['amount']:>12,.0f} {str(r['name'])[:55]}")

# biggest absolute changes among common SKUs and new/dropped
res["top_delta"] = [
    {"item": r[0], "name": r[1], "status": r[2], "amt22": float(r[3] or 0), "amt26": float(r[4] or 0),
     "delta": float((r[4] or 0) - (r[3] or 0))}
    for r in con.execute("""
    SELECT c.item_code, COALESCE(c.legacy_name, cw.sap_name), c.status, c.amt22, c.amt26
    FROM cmp c LEFT JOIN (SELECT sap_item_code, any_value(sap_name) sap_name FROM cw GROUP BY 1) cw
      ON cw.sap_item_code=c.item_code
    WHERE c.btype='LAB_FINISHED_PRODUCT'
    ORDER BY abs(COALESCE(c.amt26,0)-COALESCE(c.amt22,0)) DESC LIMIT 25""").fetchall()
]
print("== top delta")
for r in res["top_delta"]:
    print(f"{r['item']:10s} {r['status']:12s} {r['amt22']:>11,.0f} -> {r['amt26']:>11,.0f}  {str(r['name'])[:45]}")

# qty unit guard: BOTH SKUs with different legacy/sap UoM
res["uom_mismatch"] = [
    {"item": r[0], "legacy_uom": r[1], "sap_uom": r[2], "amt22": float(r[3] or 0), "amt26": float(r[4] or 0)}
    for r in con.execute("""
    SELECT c.item_code, cw.legacy_uom, cw.sap_uom, c.amt22, c.amt26
    FROM cmp c JOIN cw ON cw.sap_item_code=c.item_code AND cw.link_status='MAPPED_BY_SAP_U_CODACTIVE'
    WHERE c.status='BOTH' AND replace(cw.legacy_uom,'.','')<>replace(cw.sap_uom,'.','')
    """).fetchall()
]
print("== uom mismatches", res["uom_mismatch"])

json.dump(res, open(f"{OUT}/out/final_metrics.json", "w"), indent=1, ensure_ascii=False)

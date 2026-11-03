"""Guards for the 2022 vs 2026 product comparison.

1. UoM compatibility between legacy and SAP records (crosswalk uom columns).
2. Price-ratio outliers and presentation/size-token changes (flag only).
3. Amount not reconciled by the crosswalk / classification.
"""
import json
import re

import duckdb

OUT = "/tmp/opencode/telchi-hist"

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW cw AS SELECT * FROM read_parquet('{OUT}/out/crosswalk_sap_legacy.parquet')")
con.execute(f"CREATE VIEW cmp AS SELECT * FROM read_parquet('{OUT}/out/products_cmp.parquet')")
con.execute(f"CREATE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
con.execute(f"CREATE VIEW lg AS SELECT * FROM read_parquet('{OUT}/extract/legacy_sales_2022.parquet')")
con.execute(f"CREATE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")

res = {}

# ---------- 1. UoM distribution over mapped SAP items
uom = con.execute("""
SELECT legacy_uom, sap_uom, count(*) items
FROM cw WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
GROUP BY 1,2 ORDER BY 3 DESC
""").fetchall()
res["uom_pairs"] = [{"legacy_uom": r[0], "sap_uom": r[1], "items": r[2]} for r in uom]
print("== UoM pairs (mapped items)")
for r in res["uom_pairs"][:30]:
    print(r)

# UoM of SKUs actually compared (BOTH) weighted by amount
uom_both = con.execute("""
SELECT cw.legacy_uom, cw.sap_uom, count(*) skus, sum(c.amt22) a22, sum(c.amt26) a26
FROM cmp c JOIN cw ON cw.sap_item_code=c.item_code AND cw.link_status='MAPPED_BY_SAP_U_CODACTIVE'
WHERE c.status='BOTH' GROUP BY 1,2 ORDER BY 4 DESC
""").fetchall()
res["uom_both"] = [{"legacy_uom": r[0], "sap_uom": r[1], "skus": r[2],
                    "amt22": float(r[3] or 0), "amt26": float(r[4] or 0)} for r in uom_both]
print("== UoM pairs on BOTH SKUs (amount 2022 order)")
for r in res["uom_both"]:
    print(r)

# ---------- 2. Price ratio outliers
con.execute("""
CREATE OR REPLACE TABLE pr AS
SELECT c.item_code, c.legacy_name, cw.sap_name, cw.legacy_uom, cw.sap_uom,
       c.amt22, c.amt26, c.qty22, c.qty26,
       c.amt22/NULLIF(c.qty22,0) p22, c.amt26/NULLIF(c.qty26,0) p26,
       (c.amt26/c.qty26)/(c.amt22/c.qty22) ratio
FROM cmp c LEFT JOIN cw ON cw.sap_item_code=c.item_code AND cw.link_status='MAPPED_BY_SAP_U_CODACTIVE'
WHERE c.status='BOTH' AND c.qty22>0 AND c.qty26>0
""")
dist = con.execute("""
SELECT CASE WHEN ratio<0.5 THEN '<0.50' WHEN ratio<0.8 THEN '0.50-0.80'
            WHEN ratio<1.2 THEN '0.80-1.20' WHEN ratio<2 THEN '1.20-2.00'
            WHEN ratio<5 THEN '2.00-5.00' ELSE '>=5.00' END bucket,
       count(*) skus, sum(amt26) a26, sum(amt26-amt22) delta
FROM pr GROUP BY 1 ORDER BY 1
""").fetchall()
res["price_ratio_buckets"] = [{"bucket": r[0], "skus": r[1], "amt26": float(r[2] or 0),
                               "delta": float(r[3] or 0)} for r in dist]
print("== price ratio buckets")
for r in res["price_ratio_buckets"]:
    print(r)

SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l|lt|lts|litros?|g|gr|kg|cc|oz|un|und|unid)\b", re.I)


def sizes(text):
    if not text:
        return []
    t = text.replace(",", ".")
    return [float(a) * {"ml": 0.001, "l": 1, "lt": 1, "lts": 1, "litro": 1, "litros": 1,
                        "g": 0.001, "gr": 0.001, "kg": 1, "cc": 0.001, "oz": 0.0295735,
                        "un": 1, "und": 1, "unid": 1}.get(u.lower(), 1) * 1000
            for a, u in SIZE_RE.findall(t)]


rows = con.execute("""
SELECT item_code, legacy_name, sap_name, legacy_uom, sap_uom, amt22, amt26, qty22, qty26, ratio
FROM pr WHERE ratio>=1.5 OR ratio<=0.67 ORDER BY amt26 DESC
""").fetchall()
flagged = []
for r in rows:
    lname, sname = r[1], r[2]
    lsz, ssz = sizes(lname), sizes(sname)
    size_change = "UNKNOWN"
    if lsz and ssz:
        size_change = "SAME" if abs(lsz[0] - ssz[0]) < 1e-6 else f"CHANGED {lsz[0]:g}->{ssz[0]:g}"
    elif not lsz and not ssz:
        size_change = "NO_SIZE_TOKEN"
    flagged.append({
        "item_code": r[0], "legacy_name": lname, "sap_name": sname,
        "legacy_uom": r[3], "sap_uom": r[4], "amt22": float(r[5]), "amt26": float(r[6]),
        "qty22": float(r[7]), "qty26": float(r[8]), "ratio": float(r[9]),
        "size_change": size_change,
    })
res["price_outliers"] = flagged
print(f"== price outliers: {len(flagged)}")
for f in flagged[:25]:
    print(f"{f['item_code']} ratio={f['ratio']:.2f} {f['size_change']} amt26={f['amt26']:,.0f} | {str(f['legacy_name'])[:40]} | {str(f['sap_name'])[:40]}")

# outliers explained by a size change (comparable only if size same)
expl = [f for f in flagged if f["size_change"].startswith("CHANGED")]
res["price_outliers_size_changed"] = expl
print("== outliers with changed size token:", len(expl))

# ---------- 3. Reconciliation of amount
rec = {}
# 2022 Q1 legacy: unmapped / ambiguous share
r = con.execute("""
WITH mapped AS (SELECT DISTINCT legacy_product_code FROM cw
                WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'),
     amb AS (SELECT legacy_product_code FROM cw
             WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
             GROUP BY 1 HAVING count(DISTINCT sap_item_code)>1)
SELECT
 sum(CASE WHEN l.ProductCode NOT IN (SELECT legacy_product_code FROM mapped)
          THEN l.ProductSalePriceNet ELSE 0 END) unmapped,
 sum(CASE WHEN l.ProductCode IN (SELECT legacy_product_code FROM amb)
          THEN l.ProductSalePriceNet ELSE 0 END) ambiguous,
 sum(l.ProductSalePriceNet) total,
 count(*) lines,
 count(*) FILTER (WHERE l.ProductCode IN (SELECT legacy_product_code FROM mapped)) mapped_lines
FROM lg l WHERE l.SaleCode <> 3247102
""").fetchone()
rec["legacy_2022q1"] = {"unmapped_amt": float(r[0] or 0), "ambiguous_amt": float(r[1] or 0),
                        "total_amt": float(r[2] or 0), "lines": r[3], "mapped_lines": r[4],
                        "mapped_amt": float((r[2] or 0) - (r[0] or 0))}
print("== legacy Q1 reconciliation", rec["legacy_2022q1"])

# 2022 Apr-Sep SAP: items without legacy code
r = con.execute("""
SELECT sum(CASE WHEN c.legacy_code IS NULL THEN s.ItemSale ELSE 0 END) unmapped,
       sum(s.ItemSale) total
FROM ls s LEFT JOIN cw c ON c.legacy_product_code IS NOT NULL AND c.sap_item_code=s.ItemCode
                          AND c.link_status='MAPPED_BY_SAP_U_CODACTIVE'
WHERE s.u_estadofc<>'A' AND s.DocDate>='2022-04-06' AND s.DocDate<'2022-10-01'
""").fetchone()
rec["sap_2022"] = {"unmapped_amt": float(r[0] or 0), "total_amt": float(r[1] or 0)}
print("== SAP Apr-Sep 2022 reconciliation", rec["sap_2022"])

# 2026: items without a legacy code in the crosswalk
r = con.execute("""
SELECT sum(CASE WHEN c.legacy_code IS NULL THEN cast(f.line_total AS DOUBLE) ELSE 0 END) unmapped,
       sum(cast(f.line_total AS DOUBLE)) total
FROM fs f LEFT JOIN cw c ON c.sap_item_code=f.item_code AND c.link_status='MAPPED_BY_SAP_U_CODACTIVE'
WHERE f.canceled='N' AND f.doc_currency='BS'
  AND f.doc_date>='2026-01-01' AND f.doc_date<'2026-10-01'
""").fetchone()
rec["foundation_2026"] = {"unmapped_amt": float(r[0] or 0), "total_amt": float(r[1] or 0)}
print("== 2026 reconciliation", rec["foundation_2026"])
res["reconciliation"] = rec

json.dump(res, open(f"{OUT}/out/checks.json", "w"), indent=1, ensure_ascii=False)

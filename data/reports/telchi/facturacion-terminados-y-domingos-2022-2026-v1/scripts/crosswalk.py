"""Audit SAP ItemCode <-> legacy ProductCode correspondence for Telchi.

Evidence chain:
  * productSB1.parq (SAP OITM export) carries U_ codactive = legacy ProductCode.
  * convertActiveToSap02.py (preserved original script) documents the intended link
    via u_codactive when transforming saleProduct -> saleSB1Product.
  * product.parq is the legacy item master (numeric ProductCode + 7/8/9 digit str).

Outputs: crosswalk pairs, cardinality, conflicts, weighted coverage.
"""
import json
import os
import re
import unicodedata

import duckdb

OUT = "/tmp/opencode/telchi-hist"
LEGACY = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet"

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")

con.execute(f"""
CREATE OR REPLACE VIEW sap_master AS
SELECT ItemCode, ItemName, u_codactive, Grupo, Linea, SubGrupo, InvntryUom, ItemUN,
       U_FormaFarmac, FFName, ItmsGrpCod, LastPurPrc, frozenFor
FROM read_parquet('{LEGACY}/productSB1.parq')
""")
con.execute(f"""
CREATE OR REPLACE VIEW legacy_master AS
SELECT ProductCode, trim(ProductCodeStr) AS legacy_code_str, ProductName, ProductDesc,
       Marca, LineCode, LineName, Grupo1Name, Grupo2Name, trim(Unidad) AS unidad,
       ProductStatus, Tipo, ProductUC
FROM read_parquet('{LEGACY}/product.parq')
""")


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s.upper())
    return " ".join(s.split())


con.create_function("norm_name", norm, ["VARCHAR"], "VARCHAR")

con.execute(f"""
CREATE OR REPLACE TABLE crosswalk AS
SELECT s.ItemCode AS sap_item_code, s.ItemName AS sap_name, trim(s.u_codactive) AS legacy_code,
       l.ProductCode AS legacy_product_code, l.ProductName AS legacy_name,
       l.LineName AS legacy_line, s.Grupo AS sap_group, s.Linea AS sap_linea,
       l.unidad AS legacy_uom, s.InvntryUom AS sap_uom, s.ItemUN AS sap_item_un,
       CASE WHEN l.ProductCode IS NULL THEN 'LEGACY_CODE_NOT_IN_MASTER'
            WHEN s.u_codactive IS NULL OR trim(s.u_codactive) IN ('', '0') THEN 'SAP_ITEM_WITHOUT_LEGACY_CODE'
            ELSE 'MAPPED_BY_SAP_U_CODACTIVE' END AS link_status,
       norm_name(s.ItemName) AS sap_norm, norm_name(l.ProductName) AS legacy_norm
FROM sap_master s
LEFT JOIN legacy_master l ON cast(l.ProductCode AS VARCHAR) = trim(s.u_codactive)
""")

summary = {}
summary["sap_items"] = con.execute("SELECT count(*) FROM sap_master").fetchone()[0]
summary["legacy_items"] = con.execute("SELECT count(*) FROM legacy_master").fetchone()[0]
summary["crosswalk_rows"] = con.execute("SELECT count(*) FROM crosswalk").fetchone()[0]

summary["link_status"] = dict(con.execute("SELECT link_status, count(*) FROM crosswalk GROUP BY 1").fetchall())

# Cardinality
summary["sap_to_legacy"] = {
    "one_to_one": con.execute("""SELECT count(*) FROM (SELECT sap_item_code FROM crosswalk WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
        GROUP BY 1 HAVING count(DISTINCT legacy_code)=1)""").fetchone()[0],
    "sap_items_mapped": con.execute("SELECT count(*) FROM crosswalk WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'").fetchone()[0],
    "legacy_codes_mapped": con.execute("SELECT count(DISTINCT legacy_code) FROM crosswalk WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'").fetchone()[0],
    "legacy_codes_with_multiple_sap": con.execute("""SELECT count(*) FROM (SELECT legacy_code FROM crosswalk WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
        GROUP BY 1 HAVING count(DISTINCT sap_item_code)>1)""").fetchone()[0],
}
summary["sap_one_to_many_examples"] = con.execute("""
SELECT legacy_code, count(*) n, string_agg(sap_item_code || '=' || left(sap_name,40), ' | ') FROM crosswalk
WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
GROUP BY 1 HAVING count(DISTINCT sap_item_code)>1 ORDER BY n DESC LIMIT 15""").fetchall()

# Unmapped SAP items that were actually sold in 2026 (economically relevant)
con.execute(f"CREATE OR REPLACE VIEW f_lines AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
summary["sap_2026_unmapped_by_amount"] = con.execute("""
WITH x AS (
 SELECT l.item_code, sum(cast(l.line_total AS DECIMAL(38,6))) amt
 FROM f_lines l WHERE l.canceled='N' AND l.doc_currency='BS'
   AND l.doc_date >= '2026-01-01' AND l.doc_date < '2026-10-01'
 GROUP BY 1)
SELECT count(*) items, sum(CASE WHEN c.sap_item_code IS NULL THEN 1 ELSE 0 END) missing,
       sum(amt) total_amt, sum(CASE WHEN c.sap_item_code IS NULL THEN amt ELSE 0 END) missing_amt
FROM x LEFT JOIN crosswalk c ON c.sap_item_code = x.item_code AND c.link_status='MAPPED_BY_SAP_U_CODACTIVE'
""").fetchall()

# Legacy 2022 Q1 weighted coverage
con.execute(f"CREATE OR REPLACE VIEW l2022 AS SELECT * FROM read_parquet('{OUT}/extract/legacy_sales_2022.parquet')")
summary["legacy_2022q1_coverage"] = con.execute("""
WITH x AS (
 SELECT l.*, c.sap_item_code, c.link_status
 FROM l2022 l LEFT JOIN crosswalk c ON c.legacy_product_code = l.ProductCode AND c.link_status='MAPPED_BY_SAP_U_CODACTIVE')
SELECT count(*) lines, count(DISTINCT ProductCode) products,
       sum(CASE WHEN sap_item_code IS NOT NULL THEN 1 ELSE 0 END) mapped_lines,
       sum(ProductSalePrice) amount, sum(CASE WHEN sap_item_code IS NOT NULL THEN ProductSalePrice ELSE 0 END) mapped_amount,
       sum(ProductSaleCant) qty, sum(CASE WHEN sap_item_code IS NOT NULL THEN ProductSaleCant ELSE 0 END) mapped_qty
FROM x
""").fetchall()
summary["legacy_2022q1_unmapped_top"] = con.execute("""
SELECT ProductCode, any_value(ProductName) AS pname, sum(ProductSalePrice) amt, sum(ProductSaleCant) qty
FROM l2022 l
WHERE NOT EXISTS (SELECT 1 FROM crosswalk c WHERE c.legacy_product_code=l.ProductCode AND c.link_status='MAPPED_BY_SAP_U_CODACTIVE')
GROUP BY 1 ORDER BY amt DESC LIMIT 20""").fetchall()

# Name agreement on mapped pairs
summary["name_agreement"] = con.execute("""
SELECT
 count(*) pairs,
 sum(CASE WHEN legacy_norm = sap_norm THEN 1 ELSE 0 END) exact,
 sum(CASE WHEN legacy_norm <> sap_norm THEN 1 ELSE 0 END) different
FROM crosswalk WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE'
""").fetchall()
summary["name_conflict_examples"] = con.execute("""
SELECT sap_item_code, legacy_code, left(legacy_name,55), left(sap_name,55)
FROM crosswalk WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE' AND legacy_norm <> sap_norm
 AND length(legacy_norm)>3 AND length(sap_norm)>3
LIMIT 12""").fetchall()

# Legacy code reuse: same ProductCode with multiple ProductName across 2018-2022 sales
con.execute(f"""CREATE OR REPLACE VIEW legacy_all AS
SELECT ProductCode, ProductName, SaleDate FROM read_parquet('{LEGACY}/saleProduct-*.parq')""")
summary["legacy_code_multiple_names"] = con.execute("""
SELECT count(*) FROM (SELECT ProductCode FROM legacy_all GROUP BY 1
 HAVING count(DISTINCT norm_name(ProductName))>1)
""").fetchone()[0]
summary["legacy_reuse_examples"] = con.execute("""
SELECT ProductCode, count(DISTINCT norm_name(ProductName)) n, string_agg(DISTINCT left(ProductName,50), ' || ')
FROM legacy_all GROUP BY 1 HAVING count(DISTINCT norm_name(ProductName))>1 ORDER BY n DESC LIMIT 10""").fetchall()

# Export crosswalk
con.execute(f"""COPY (SELECT * FROM crosswalk) TO '{OUT}/out/crosswalk_sap_legacy.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")
os.makedirs(f"{OUT}/out", exist_ok=True)
con.execute(f"""COPY (SELECT * FROM crosswalk) TO '{OUT}/out/crosswalk_sap_legacy.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")

json.dump(summary, open(f"{OUT}/out/crosswalk_summary.json", "w"), indent=1, ensure_ascii=False, default=str)
print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))

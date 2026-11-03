"""Physical-volume comparison of Telchi own finished products, Jan-Sep 2022 vs 2026.

Read-only. Consumes the audited extracts already produced by extract.py/crosswalk.py
under /tmp/opencode/telchi-hist, plus the reference product master (names/UoM).

Outputs (this folder):
  volumen_skus_2022_vs_2026.csv
  volumen_familias_2022_vs_2026.csv
  volumen_migraciones_presentacion.csv
  volumen_datos_clave.json

Metric: quantity x presentation factor, expressed in ONE of four compatible
dimensions (litres, kilograms, doses, presentation units). Dimensions are never
added together.
"""
import json
import os
import re
import unicodedata

import duckdb
import numpy as np
import pandas as pd

OUT = "/tmp/opencode/telchi-hist"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = ("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/"
       "reference/_versions/v2_reference_closure_687bb2e9c034dc59/products/part-00000.parquet")
PS = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet/productSB1.parq"
LEG = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/raw/legacy/parquet/product.parq"
BT = ("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/crosswalk/"
      "_versions/v2_product_business_type_f9c1130d852ccb61/product_business_type/part-00000.parquet")

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
con.execute(f"CREATE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")
con.execute(f"CREATE VIEW lg AS SELECT * FROM read_parquet('{OUT}/extract/legacy_sales_2022.parquet')")
con.execute(f"CREATE VIEW cw AS SELECT * FROM read_parquet('{OUT}/out/crosswalk_sap_legacy.parquet')")
con.execute(f"CREATE VIEW bt AS SELECT * FROM read_parquet('{BT}')")
con.execute(f"CREATE VIEW ref AS SELECT item_code, any_value(product_name) FILTER (WHERE source_system='SAP_HANA') name26 FROM read_parquet('{REF}') GROUP BY 1")
con.execute(f"CREATE VIEW ps AS SELECT ItemCode, ItemName, InvntryUom FROM read_parquet('{PS}')")
con.execute(f"CREATE VIEW leg AS SELECT ProductCode, ProductName, Unidad, ProductUC FROM read_parquet('{LEG}')")

con.execute("""
CREATE OR REPLACE TABLE cw11 AS
SELECT legacy_product_code, any_value(sap_item_code) sap_item_code, count(DISTINCT sap_item_code) n
FROM cw WHERE link_status='MAPPED_BY_SAP_U_CODACTIVE' GROUP BY 1
""")
con.execute("""
CREATE OR REPLACE TABLE q22 AS
SELECT pkey, any_value(item_code) item_code, sum(qty) qty, sum(amt) amt, count(*) lines FROM (
  SELECT COALESCE(CASE WHEN c.n=1 THEN c.sap_item_code END,'LEGACY:'||l.ProductCode) pkey,
         CASE WHEN c.n=1 THEN c.sap_item_code END item_code, ProductSaleCant qty, ProductSalePriceNet amt
  FROM lg l LEFT JOIN cw11 c ON c.legacy_product_code=l.ProductCode WHERE l.SaleCode<>3247102
  UNION ALL
  SELECT ItemCode, ItemCode, ItemSaleCant, ItemSale FROM ls
  WHERE u_estadofc<>'A' AND DocDate>='2022-04-06' AND DocDate<'2022-10-01'
) x GROUP BY 1
""")
con.execute("""
CREATE OR REPLACE TABLE q26 AS
SELECT COALESCE(item_code,'?') pkey, any_value(item_code) item_code, sum(cast(quantity AS DOUBLE)) qty,
       sum(cast(line_total AS DECIMAL(38,6))) amt, count(*) lines
FROM fs WHERE canceled='N' AND doc_currency='BS'
  AND doc_date>='2026-01-01' AND doc_date<'2026-10-01' GROUP BY 1
""")
con.execute("""
CREATE OR REPLACE TABLE items AS
SELECT COALESCE(a.pkey,b.pkey) pkey, COALESCE(a.item_code,b.item_code) item_code,
       a.qty q22, b.qty q26, a.amt a22, b.amt a26,
       max(CASE WHEN bt.product_business_type='LAB_FINISHED_PRODUCT' THEN 1 ELSE 0 END) is_lab,
       any_value(bt.product_business_type) FILTER (WHERE bt.product_business_type IS NOT NULL) btype,
       any_value(ps.ItemName) FILTER (WHERE ps.ItemName IS NOT NULL) sap_name,
       any_value(r.name26) FILTER (WHERE r.name26 IS NOT NULL) cur_name,
       any_value(ps.InvntryUom) FILTER (WHERE ps.InvntryUom IS NOT NULL) inv_uom,
       any_value(leg.ProductName) FILTER (WHERE leg.ProductName IS NOT NULL) legmaster_name,
       any_value(leg.Unidad) FILTER (WHERE leg.Unidad IS NOT NULL) leg_uom,
       max(leg.ProductUC) uc
FROM q22 a FULL OUTER JOIN q26 b ON a.pkey=b.pkey
LEFT JOIN bt ON bt.ItemCode=COALESCE(a.item_code,b.item_code)
LEFT JOIN ps ON ps.ItemCode=COALESCE(a.item_code,b.item_code)
LEFT JOIN ref r ON r.item_code=COALESCE(a.item_code,b.item_code)
LEFT JOIN cw11 c ON c.sap_item_code=COALESCE(a.item_code,b.item_code)
LEFT JOIN leg ON leg.ProductCode=c.legacy_product_code
GROUP BY 1,2,3,4,5,6
""")

# --------------------------------------------------------------------------
# Presentation parser
# --------------------------------------------------------------------------
SIZE = re.compile(
    r"(?:x|X)\s*(\d+(?:[.,]\d+)?)\s*"
    r"(m\.?l\.?|cc|lts?|lt|litros?|l|grs?|gr(?![a-z])|g|kg|mg|oz|onzas?|"
    r"c[aá]psulas?|caps?|comprimidos?|comp|tabs?|tabletas?|sobres?|sob|"
    r"unidades?|unid|und|un|pzas?|piezas?|fcos?|frascos?|perlas?|gotas?|dosis)\b", re.I)
ANY_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m\.?l\.?|cc|lts?|lt|litros?|l|grs?|gr(?![a-z])|g|kg|oz|onzas?)\b", re.I)
DOSE_UNITS = {"caps", "cap", "capsula", "capsulas", "comprimido", "comprimidos", "comp", "tab",
              "tabs", "tableta", "tabletas", "sobre", "sobres", "sob", "perla", "perlas", "gota",
              "gotas", "dosis"}
PRES_UNITS = {"unidad", "unidades", "unid", "und", "un", "pza", "pzas", "pieza", "piezas", "fco",
              "fcos", "frasco", "frascos"}
UOM_FACTOR = {
    "LT": ("L", 1.0), "L": ("L", 1.0), "ML": ("L", 0.001),
    "KG": ("kg", 1.0), "GR": ("kg", 0.001),
    "CAPS": ("dose", 1.0), "CAP": ("dose", 1.0), "COMP": ("dose", 1.0),
    "TAB": ("dose", 1.0), "SOB": ("dose", 1.0),
}
BOX_UOM = {"CJA", "CAJA", "JUEGO", "PQTE", "PAQ", "PAQUETE", "PALLET"}
# Broad plausibility bands (Bs per base unit) used only to break UoM ambiguity.
BANDS = {"L": (0.5, 20000), "kg": (1, 50000), "dose": (0.05, 100), "pres": (0.5, 5000)}
NONCOMMERCIAL = re.compile(
    r"CAPSULAS VACIAS|PORTA/CUBRE|SPECTROPACH|BOTIQUIN|EXPERIMENTO|^COMBO|^KIT |"
    r"PREPARADO MAGISTRAL|^FORMULA |^Z\.M\.O", re.I)


def parse_size(name):
    if not isinstance(name, str):
        return None
    t = name.replace(",", ".").lower()
    m = SIZE.search(t) or ANY_SIZE.search(t)
    if not m:
        if re.search(r"\bx\s*c[aá]psula\b", t):
            return ("dose", 1.0)
        return None
    val, unit = float(m.group(1)), m.group(2).strip(".").replace(".", "")
    if unit in ("ml", "m l", "cc"):
        return ("L", val / 1000)
    if unit in ("l", "lt", "lts", "litro", "litros"):
        return ("L", val)
    if unit in ("g", "gr", "grs"):
        return ("kg", val / 1000)
    if unit == "kg":
        return ("kg", val)
    if unit == "mg":
        return ("kg", val * 1e-6)
    if unit in ("oz", "onza", "onzas"):
        return ("kg", val * 0.0283495)
    if unit in DOSE_UNITS:
        return ("dose", val)
    if unit in PRES_UNITS:
        return ("pres", val)
    return None


def candidates(row):
    uom = str(row.inv_uom or "").upper()
    if uom in UOM_FACTOR:
        yield (*UOM_FACTOR[uom], "UOM_BASE")
    if uom in BOX_UOM and row.parsed and row.uc and float(row.uc) > 0:
        yield row.parsed[0], row.parsed[1] * float(row.uc), "BOX_X_UC"
    if row.parsed:
        yield row.parsed[0], row.parsed[1], "PRESENTATION"
    if uom in UOM_FACTOR:
        yield UOM_FACTOR[uom][0], 1.0, "UOM_BASE_RAW"
    if row.parsed:
        yield row.parsed[0], 1.0, "AS_BASE_UNIT"
    if uom and uom not in ("", "NAN", "NONE"):
        yield "pres", 1.0, "UNIT_FALLBACK"


PRIO = {"UOM_BASE": 0, "BOX_X_UC": 1, "PRESENTATION": 2, "UOM_BASE_RAW": 3,
        "AS_BASE_UNIT": 4, "UNIT_FALLBACK": 5}


def choose_factor(row):
    opts = []
    for dim, factor, basis in candidates(row):
        if factor <= 0:
            continue
        lo, hi = BANDS[dim]
        plausible, seen = True, False
        for qty, amount in ((row.q22, row.a22), (row.q26, row.a26)):
            if pd.notna(qty) and qty and qty > 0 and pd.notna(amount) and amount > 0:
                price = float(amount) / (float(qty) * factor)
                plausible = plausible and (lo <= price <= hi)
                seen = True
        if seen:
            opts.append((0 if plausible else 1, dim, factor, basis))
    if not opts:
        return pd.Series({"dim": None, "factor": None, "basis": "UNCONVERTIBLE"})
    opts.sort(key=lambda x: (x[0], PRIO.get(x[3], 9)))
    if opts[0][0] == 1:
        return pd.Series({"dim": opts[0][1], "factor": opts[0][2], "basis": "PRICE_IMPLAUSIBLE"})
    return pd.Series({"dim": opts[0][1], "factor": opts[0][2], "basis": opts[0][3]})


# --------------------------------------------------------------------------
# Family normalisation (brand/product level, ignores presentation and flavour)
# --------------------------------------------------------------------------
STOP = {"x", "de", "del", "la", "el", "los", "las", "con", "para", "por", "y", "en", "al", "un",
        "una", "frasco", "fco", "bolsa", "caja", "cja", "pote", "sachet", "sobre", "tubo", "lata",
        "botella", "envase", "pack", "unidad", "unidades", "lt", "lts", "ml", "gr", "g", "kg",
        "litro", "litros", "comprimidos", "comprimido", "capsulas", "capsula", "tabletas",
        "tableta", "tab", "caps", "comp", "unid", "und", "pzas", "pieza", "piezas", "bidon",
        "granel", "licitacion", "pallet", "display", "estuche", "kit", "combo"}
OVERRIDES = [
    (r"^ALCOHOL", "ALCOHOL 70%"),
    (r"^LOCION POVIDINE|^POVIDINE|^JABON POVIDINE|^POVI", "POVIDINE"),
    (r"^COLAGENO", "COLAGENO"),
    (r"^CREOLINA", "CREOLINA"),
    (r"^CALENTA", "CALENTA"),
    (r"^PASTA DE AGUA", "PASTA DE AGUA"),
    (r"^MINOXITEL", "MINOXITEL"),
    (r"^REPELITEL", "REPELITEL"),
    (r"^TALCO", "TALCO"),
    (r"^CELINA", "CELINA"),
    (r"^ACEITE DE COCO", "ACEITE DE COCO"),
    (r"^ESENCIA", "ESENCIAS"),
    (r"^GEL ACUOSO|^ALCOHOL EN GEL|^GEL", "GELES"),
    (r"^TINTURA DE YODO|^TINTURA YODO|^SOLUCION LUGOL|^LUGOL", "TINTURA DE YODO / LUGOL"),
    (r"^AGUA BORICADA|^AGUA OXIGENADA|^AGUA DE ROSAS|^AGUA ROSAS", "AGUAS MEDICINALES"),
    (r"^POMADA NITROFURATEL|^NITROFURATEL", "NITROFURATEL"),
    (r"^POMADA PENICILINA|^PENICILINA", "PENICILINA"),
    (r"^CARBONATO (DE )?LITIO", "CARBONATO DE LITIO"),
    (r"^CITRATO DE MAGNESIO", "CITRATO DE MAGNESIO"),
    (r"^ALCANFOR", "ALCANFOR"),
    (r"^UNGUTEL", "UNGUTEL"),
    (r"^DERMATEL", "DERMATEL"),
    (r"^GLUCOTEL", "GLUCOTEL"),
    (r"^CLOREXITEL", "CLOREXITEL"),
    (r"^BRONCEADOR", "BRONCEADOR"),
    (r"^COLORANTE", "COLORANTES"),
]


def normalise(text):
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9%. ]+", " ", t)
    t = re.sub(r"\b\d+(?:[.,]\d+)?\s*(ml|m l|cc|l|lt|lts|g|gr|grs|kg|mg|oz|un|und|unid|caps|comp|tab|sobres?|pzas?)\b", " ", t)
    t = re.sub(r"\([^)]*\)", " ", t)
    return " ".join(w for w in t.split() if w and w not in STOP and not re.fullmatch(r"[\d.,]+", w))


def family_of(name):
    if isinstance(name, str) and NONCOMMERCIAL.search(name):
        return "NO COMERCIAL / MAGISTRAL"
    n = normalise(name).upper()
    for pattern, family in OVERRIDES:
        if re.search(pattern, n):
            return family
    toks = n.split()
    return " ".join(toks[:3]) if toks else "SIN NOMBRE"


# --------------------------------------------------------------------------
def prepare(base):
    base = base.copy()
    base["name"] = base.cur_name.fillna(base.legmaster_name).fillna(base.sap_name)
    renamed = base["name"].str.startswith("PREPARADO MAGISTRAL", na=False) & base.legmaster_name.notna()
    base.loc[renamed, "name"] = base.loc[renamed, "legmaster_name"]
    base["parsed"] = base.name.map(parse_size)
    fallback = base.parsed.isna() & base.legmaster_name.notna()
    base.loc[fallback, "parsed"] = base.loc[fallback, "legmaster_name"].map(parse_size)
    base = pd.concat([base, base.apply(choose_factor, axis=1)], axis=1)
    base["v22"] = base.q22.fillna(0) * base.factor
    base["v26"] = base.q26.fillna(0) * base.factor
    base["pu22"] = base.a22 / base.v22.replace(0, np.nan)
    base["pu26"] = base.a26 / base.v26.replace(0, np.nan)
    base["price_ratio"] = base.pu26 / base.pu22
    base["status"] = np.select(
        [base.q22.isna() & base.q26.notna(), base.q22.notna() & base.q26.isna(),
         base.q22.notna() & base.q26.notna()],
        ["NEW_2026", "DROPPED_2026", "BOTH"], default="OTRO")
    base["noncommercial"] = base.name.str.contains(NONCOMMERCIAL, na=False)
    base["family"] = base.name.map(family_of)
    base["size_ratio"] = np.where(
        (base.dim.isin(["L", "kg", "dose"])) & (base.factor > 0) & (base.status == "BOTH"),
        base.factor, np.nan)
    return base


rows = prepare(con.execute("SELECT * FROM items WHERE is_lab=1").fetchdf())

# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------
DIMS = ["L", "kg", "dose", "pres"]


def totals(frame):
    out = {}
    for d in DIMS:
        s = frame[frame.dim == d]
        out[d] = {"v22": float(s.v22.sum()), "v26": float(s.v26.sum()),
                  "a22": float(s.a22.sum()), "a26": float(s.a26.sum()),
                  "skus22": int((s.v22 > 0).sum()), "skus26": int((s.v26 > 0).sum())}
        out[d]["delta_pct"] = (round((out[d]["v26"] / out[d]["v22"] - 1) * 100, 1)
                               if out[d]["v22"] else None)
    return out


ALL = rows
COMMERCIAL = rows[~rows.noncommercial]
NO_TENDER = rows[rows.item_code != "L02924"]

result = {
    "generado": "2026-10-22",
    "periodos": {"2022": "2022-01-01..2022-09-30", "2026": "2026-01-01..2026-09-30"},
    "universo": "LAB_FINISHED_PRODUCT (clasificacion actual aplicada retroactivamente)",
    "totales_todos": totals(ALL),
    "totales_sin_no_comerciales": totals(COMMERCIAL),
    "totales_sin_licitacion_alcohol": totals(NO_TENDER),
    "skus": {
        "total": int(len(rows)),
        "both": int((rows.status == "BOTH").sum()),
        "new": int((rows.status == "NEW_2026").sum()),
        "dropped": int((rows.status == "DROPPED_2026").sum()),
        "no_comerciales": int(rows.noncommercial.sum()),
        "sin_conversion": int((rows.basis == "UNCONVERTIBLE").sum()),
        "precio_implausible": int((rows.basis == "PRICE_IMPLAUSIBLE").sum()),
    },
}

# decomposition by status within each dimension (commercial universe, tender included and excluded)
decomp = {}
for label, frame in (("con_licitacion", COMMERCIAL), ("sin_licitacion", COMMERCIAL[COMMERCIAL.item_code != "L02924"])):
    decomp[label] = {}
    for d in DIMS:
        s = frame[frame.dim == d]
        b = s[s.status == "BOTH"]
        n = s[s.status == "NEW_2026"]
        x = s[s.status == "DROPPED_2026"]
        decomp[label][d] = {
            "both_v22": float(b.v22.sum()), "both_v26": float(b.v26.sum()),
            "new_v26": float(n.v26.sum()), "dropped_v22": float(x.v22.sum()),
            "delta_both": float(b.v26.sum() - b.v22.sum()),
            "delta_total": float(s.v26.sum() - s.v22.sum()),
            "both_a22": float(b.a22.sum()), "both_a26": float(b.a26.sum()),
            "new_a26": float(n.a26.sum()), "dropped_a22": float(x.a22.sum()),
        }
result["descomposicion"] = decomp

# decomposition at family level (captures renames and presentation successions)
fam_status = (COMMERCIAL.groupby(["family", "dim"], dropna=False)
              .agg(v22=("v22", "sum"), v26=("v26", "sum")).reset_index())
fam_status["status"] = np.select(
    [(fam_status.v22 > 0) & (fam_status.v26 > 0), (fam_status.v22 == 0) & (fam_status.v26 > 0),
     (fam_status.v22 > 0) & (fam_status.v26 == 0)],
    ["BOTH", "NEW", "GONE"], default="ZERO")
family_decomp = {}
for d in DIMS:
    s = fam_status[fam_status.dim == d]
    g = s.groupby("status")[["v22", "v26"]].sum()
    both = g.loc["BOTH"] if "BOTH" in g.index else pd.Series({"v22": 0, "v26": 0})
    family_decomp.setdefault("con_licitacion", {})[d] = {
        "both_v22": float(both.v22), "both_v26": float(both.v26),
        "new_v26": float(g.loc["NEW", "v26"]) if "NEW" in g.index else 0.0,
        "gone_v22": float(g.loc["GONE", "v22"]) if "GONE" in g.index else 0.0,
        "delta_both_pct": (round((both.v26 / both.v22 - 1) * 100, 1) if both.v22 else None),
    }
# ex-tender family view: remove the one-off tender from the alcohol family baseline
fam_no_tender = fam_status.copy()
fam_no_tender.loc[(fam_no_tender.family == "ALCOHOL 70%") & (fam_no_tender.dim == "L"), "v22"] -= 103000
family_decomp["sin_licitacion"] = {}
for d in DIMS:
    s = fam_no_tender[fam_no_tender.dim == d]
    g = s.groupby("status")[["v22", "v26"]].sum()
    both = g.loc["BOTH"] if "BOTH" in g.index else pd.Series({"v22": 0, "v26": 0})
    family_decomp["sin_licitacion"][d] = {
        "both_v22": float(both.v22), "both_v26": float(both.v26),
        "new_v26": float(g.loc["NEW", "v26"]) if "NEW" in g.index else 0.0,
        "gone_v22": float(g.loc["GONE", "v22"]) if "GONE" in g.index else 0.0,
        "delta_both_pct": (round((both.v26 / both.v22 - 1) * 100, 1) if both.v22 else None),
    }
result["descomposicion_familias"] = family_decomp


# family table
fam = (rows.groupby(["family", "dim"], dropna=False)
       .agg(v22=("v22", "sum"), v26=("v26", "sum"), a22=("a22", "sum"), a26=("a26", "sum"),
            skus=("item_code", "count"), noncommercial=("noncommercial", "max"))
       .reset_index())
fam["delta_pct"] = np.where(fam.v22 > 0, (fam.v26 / fam.v22 - 1) * 100, np.nan)
fam = fam.sort_values("a26", ascending=False)
fam.to_csv(f"{HERE}/volumen_familias_2022_vs_2026.csv", index=False, encoding="utf-8")
result["familias_top"] = fam[fam.dim.isin(["L", "kg", "dose"])].head(25).round(2).to_dict("records")

# SKU table
sku_cols = ["item_code", "name", "family", "status", "inv_uom", "dim", "factor", "basis",
            "q22", "q26", "v22", "v26", "a22", "a26", "pu22", "pu26", "price_ratio", "noncommercial"]
sku = rows[sku_cols].copy()
sku["unidad_fisica"] = sku.dim.map({"L": "litros", "kg": "kg", "dose": "dosis", "pres": "presentacion"})
sku = sku.sort_values(["dim", "a26"], ascending=[True, False])
sku.to_csv(f"{HERE}/volumen_skus_2022_vs_2026.csv", index=False, encoding="utf-8")

# reusable per-item conversion map (consumed by sundays_2026_volume.py)
fact = rows[["item_code", "name", "family", "dim", "factor", "basis", "noncommercial", "btype"]].copy()
fact = fact[fact.item_code.notna()].drop_duplicates(subset=["item_code"], keep="first")
fact.to_csv(f"{HERE}/volumen_factores.csv", index=False, encoding="utf-8")

# same map for every catalogue item sold in 2026 (includes fractionated/traded lines),
# used only to measure branch volume on Sundays/holidays.
allrows = prepare(con.execute("SELECT * FROM items").fetchdf())
fact_all = allrows[["item_code", "name", "family", "dim", "factor", "basis", "noncommercial", "btype"]].copy()
fact_all = fact_all[fact_all.item_code.notna()].drop_duplicates(subset=["item_code"], keep="first")
fact_all.to_csv(f"{HERE}/volumen_factores_todos.csv", index=False, encoding="utf-8")

# top movers per dimension (commercial only)
top = {}
for d in ["L", "kg", "dose"]:
    s = COMMERCIAL[COMMERCIAL.dim == d].copy()
    s["delta"] = s.v26 - s.v22
    base = ["item_code", "name", "family", "status", "v22", "v26", "delta", "a22", "a26"]
    top[d] = {
        "crecen": s[s.delta > 0].sort_values("delta", ascending=False).head(10)[base].round(1).to_dict("records"),
        "caen": s[s.delta < 0].sort_values("delta").head(10)[base].round(1).to_dict("records"),
    }
result["top_movimientos"] = top

# presentation migrations: same family, average package size moved or new sizes appeared
mig = []
for (family, dim), g in COMMERCIAL[COMMERCIAL.dim.isin(["L", "kg", "dose"])].groupby(["family", "dim"]):
    if len(g) < 2 and not (g.status == "NEW_2026").any():
        continue
    sizes22 = sorted(set(g.loc[g.status != "NEW_2026", "factor"].dropna().round(4)))
    sizes26 = sorted(set(g.loc[g.status != "DROPPED_2026", "factor"].dropna().round(4)))
    if not sizes22 or not sizes26:
        continue
    if sizes22 == sizes26:
        continue
    mig.append({
        "family": family, "dim": dim,
        "tamanos_2022": ", ".join(f"{x:g}" for x in sizes22),
        "tamanos_2026": ", ".join(f"{x:g}" for x in sizes26),
        "v22": round(float(g.v22.sum()), 1), "v26": round(float(g.v26.sum()), 1),
        "delta_pct": round((g.v26.sum() / g.v22.sum() - 1) * 100, 1) if g.v22.sum() else None,
        "a22": round(float(g.a22.sum())), "a26": round(float(g.a26.sum())),
    })
mig_df = pd.DataFrame(mig).sort_values("a26", ascending=False)
mig_df.to_csv(f"{HERE}/volumen_migraciones_presentacion.csv", index=False, encoding="utf-8")
result["migraciones_presentacion"] = mig_df.head(20).to_dict("records")

# extra checks
result["checks"] = {
    "filas_sku": int(len(rows)),
    "skus_1a1_ambiguos": int(con.execute("SELECT count(*) FROM cw11 WHERE n>1").fetchone()[0]),
    "sin_factor": rows[rows.factor.isna()][["item_code", "name", "a26"]].round(2).to_dict("records"),
    "ratio_precio_fuera_de_rango": int(((rows.price_ratio < 0.5) | (rows.price_ratio > 3)).sum()),
}
result["checks"]["ratio_precio_detalle"] = rows[(rows.price_ratio < 0.5) | (rows.price_ratio > 3)][
    ["item_code", "name", "pu22", "pu26", "price_ratio", "a22", "a26"]].round(2).to_dict("records")

json.dump(result, open(f"{HERE}/volumen_datos_clave.json", "w"), indent=1, ensure_ascii=False, default=float)

print(json.dumps({k: result[k] for k in ("totales_todos", "totales_sin_no_comerciales",
                                         "totales_sin_licitacion_alcohol", "skus")}, indent=1, ensure_ascii=False))
print("\n== decomposition (sin licitacion)")
print(json.dumps(decomp["sin_licitacion"], indent=1, ensure_ascii=False))
print("\n== family decomposition (sin licitacion)")
print(json.dumps(family_decomp["sin_licitacion"], indent=1, ensure_ascii=False))
print("\n== top families")
print(fam[fam.dim.isin(["L", "kg", "dose"])].head(20)[
    ["family", "dim", "v22", "v26", "delta_pct", "a22", "a26"]].to_string(index=False))
print("\n== migrations")
print(mig_df.head(15).to_string(index=False))
print("\n== checks")
print(json.dumps(result["checks"]["ratio_precio_detalle"], indent=1, ensure_ascii=False)[:3000])

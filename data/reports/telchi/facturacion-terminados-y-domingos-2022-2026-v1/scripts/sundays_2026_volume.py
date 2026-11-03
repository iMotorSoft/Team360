"""Sunday / holiday performance by salon, Jan-Sep 2026, with physical volume.

Read-only. Reuses the same extracts as sundays.py and the per-item conversion
map exported by volume_2022_2026.py (volumen_factores.csv).

Questions answered:
  - which salon sells the most on Sundays / holidays (net Bs, tickets);
  - average sales per actually operated Sunday / holiday;
  - physical volume (L, kg, doses, presentation units) of own finished products.

Rules:
  - net line amount, active invoices only, doc_currency = BS, canceled = N;
  - a Sunday that is also a holiday is counted once, as Sunday;
  - La Paz departmental holiday (Jul 16) does not apply to Santa Cruz salons;
  - dimensions are never added together.

Outputs (this folder):
  domingos_feriados_2026_resumen_salon.csv
  domingos_feriados_2026_volumen_por_fecha.csv
  domingos_feriados_2026_top_familias.csv
  domingos_feriados_2026_top_productos.csv
  domingos_datos_clave.json
"""
import csv
import datetime as dt
import json
import os

import duckdb
import numpy as np
import pandas as pd

OUT = "/tmp/opencode/telchi-hist"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACT = f"{HERE}/volumen_factores_todos.csv"
PROPIO = ("LAB_FINISHED_PRODUCT", "FRACTIONATED_PRODUCT", "SEMI_FINISHED")

SALONS = ("CM-SAL", "2A-SAL", "RC-SAL", "VI-SAL")
LABEL = {
    "CM-SAL": "CM (Casa Matriz / Centro)",
    "2A-SAL": "2A (2do. Anillo)",
    "RC-SAL": "RC (Roca y Coronado)",
    "VI-SAL": "VI (Villa 1ro. de Mayo)",
}
DIMS = ("L", "kg", "dose", "pres")
START, END = dt.date(2026, 1, 1), dt.date(2026, 9, 30)


def easter(year: int) -> dt.date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def holidays(year: int):
    e = easter(year)
    return {
        dt.date(year, 1, 1): ("Año Nuevo", "nacional"),
        dt.date(year, 1, 22): ("Estado Plurinacional", "nacional"),
        e - dt.timedelta(days=48): ("Carnaval lunes", "nacional"),
        e - dt.timedelta(days=47): ("Carnaval martes", "nacional"),
        e - dt.timedelta(days=2): ("Viernes Santo", "nacional"),
        dt.date(year, 5, 1): ("Día del Trabajo", "nacional"),
        e + dt.timedelta(days=60): ("Corpus Christi", "nacional"),
        dt.date(year, 6, 21): ("Año Nuevo Andino", "nacional"),
        dt.date(year, 8, 6): ("Independencia de Bolivia", "nacional"),
        dt.date(year, 9, 24): ("Santa Cruz (departamental)", "SC"),
        dt.date(year, 11, 2): ("Todos Santos", "nacional"),
        dt.date(year, 12, 25): ("Navidad", "nacional"),
        dt.date(year, 7, 16): ("La Paz (departamental)", "LP"),
    }


HOL = holidays(2026)


def kinds(d: dt.date):
    """(is_sunday, is_holiday) with holiday scope applied and no double count."""
    holiday = d in HOL and HOL[d][1] != "LP"
    return d.weekday() == 6, holiday and d.weekday() != 6


def day_type(d: dt.date) -> str:
    sun, hol = kinds(d)
    if sun:
        return "domingo"
    if hol:
        return "feriado"
    if d.weekday() == 5:
        return "sabado"
    return "entresemana"


con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")

raw = con.execute("""
SELECT whs_code, doc_date::DATE d, item_code,
       sum(cast(quantity AS DOUBLE)) qty,
       sum(cast(line_total AS DECIMAL(38,6))) amount,
       count(DISTINCT doc_entry) tickets,
       count(*) lines
FROM fs
WHERE canceled='N' AND doc_currency='BS'
  AND doc_date>='2026-01-01' AND doc_date<'2026-10-01'
  AND whs_code IN ('CM-SAL','2A-SAL','RC-SAL','VI-SAL')
GROUP BY 1,2,3
""").fetchdf()
raw["d"] = pd.to_datetime(raw["d"]).dt.date
raw["amount"] = raw["amount"].astype(float)

fact = pd.read_csv(FACT, dtype={"item_code": str})
fact = fact[fact.item_code.notna()].drop_duplicates("item_code")
raw = raw.merge(fact, on="item_code", how="left")
raw["dim"] = raw["dim"].fillna("sin_factor")
raw["family"] = raw["family"].fillna("SIN CLASIFICAR")
raw["btype"] = raw["btype"].fillna("SIN CLASIFICAR")
raw["factor"] = raw["factor"].fillna(0.0)
raw["noncommercial"] = raw["noncommercial"].fillna(False).astype(bool)
raw["propio"] = raw.btype.isin(PROPIO) & (~raw.noncommercial)
raw["lab"] = raw.btype.eq("LAB_FINISHED_PRODUCT") & (~raw.noncommercial)
raw["frac"] = raw.btype.eq("FRACTIONATED_PRODUCT") & (~raw.noncommercial)
for d in DIMS:
    raw[f"v_{d}"] = np.where(raw.propio & (raw.dim == d), raw.qty * raw.factor, 0.0)
    raw[f"vlab_{d}"] = np.where(raw.lab & (raw.dim == d), raw.qty * raw.factor, 0.0)
    raw[f"vfrac_{d}"] = np.where(raw.frac & (raw.dim == d), raw.qty * raw.factor, 0.0)

# daily ticket/amount counts (distinct invoices per salon/day)
daily = con.execute("""
SELECT whs_code, doc_date::DATE d, count(DISTINCT doc_entry) tickets, count(*) lines,
       sum(cast(line_total AS DECIMAL(38,6))) amount
FROM fs
WHERE canceled='N' AND doc_currency='BS'
  AND doc_date>='2026-01-01' AND doc_date<'2026-10-01'
  AND whs_code IN ('CM-SAL','2A-SAL','RC-SAL','VI-SAL')
GROUP BY 1,2
""").fetchdf()
daily["d"] = pd.to_datetime(daily["d"]).dt.date
daily["amount"] = daily["amount"].astype(float)


# ---------------------------------------------------------------- per salon
def agg(frame, days):
    out = {
        "amount": float(days.amount.sum()),
        "tickets": int(days.tickets.sum()),
        "dias": int(days.d.nunique()),
        "lineas": int(days.lines.sum()),
        "monto_con_factor": float(frame.loc[frame.dim != "sin_factor", "amount"].sum()),
        "monto_propio": float(frame.loc[frame.propio, "amount"].sum()),
        "monto_lab": float(frame.loc[frame.lab, "amount"].sum()),
        "monto_frac": float(frame.loc[frame.frac, "amount"].sum()),
        "monto_traded": float(frame.loc[frame.btype == "TRADED_PRODUCT", "amount"].sum()),
    }
    for d in DIMS:
        out[f"v_{d}"] = float(frame[f"v_{d}"].sum())
        out[f"vlab_{d}"] = float(frame[f"vlab_{d}"].sum())
        out[f"vfrac_{d}"] = float(frame[f"vfrac_{d}"].sum())
    out["ticket_promedio"] = out["amount"] / out["tickets"] if out["tickets"] else None
    out["monto_por_dia"] = out["amount"] / out["dias"] if out["dias"] else None
    return out


DAYTYPES = ("domingo", "feriado", "sabado", "entresemana", "total")
summary, by_type, dates_rows = {}, {}, []
for s in SALONS:
    g = raw[raw.whs_code == s]
    gd = daily[daily.whs_code == s]
    summary[s] = {}
    by_type[s] = {}
    for t in DAYTYPES:
        mask = pd.Series(True, index=g.index) if t == "total" else g.d.map(day_type) == t
        dmask = pd.Series(True, index=gd.index) if t == "total" else gd.d.map(day_type) == t
        summary[s][t] = agg(g[mask], gd[dmask])
        by_type[s][t] = summary[s][t]
    for d in sorted(g.d.unique()):
        if day_type(d) in ("domingo", "feriado"):
            f = g[g.d == d]
            dd = gd[gd.d == d]
            row = {"fecha": str(d), "tipo": day_type(d),
                   "feriado": HOL[d][0] if d in HOL else "",
                   "salon": s, "amount": float(f.amount.sum()),
                   "tickets": int(dd.tickets.sum())}
            for x in DIMS:
                row[f"v_{x}"] = float(f[f"v_{x}"].sum())
            dates_rows.append(row)

# combined Sunday+holiday view
for s in SALONS:
    dom, fer = summary[s]["domingo"], summary[s]["feriado"]
    summary[s]["dom_fer"] = {
        "amount": dom["amount"] + fer["amount"],
        "tickets": dom["tickets"] + fer["tickets"],
        "dias": dom["dias"] + fer["dias"],
        "monto_por_dia": ((dom["amount"] + fer["amount"]) / (dom["dias"] + fer["dias"])
                          if dom["dias"] + fer["dias"] else None),
        "ticket_promedio": ((dom["amount"] + fer["amount"]) / (dom["tickets"] + fer["tickets"])
                            if dom["tickets"] + fer["tickets"] else None),
    }
    for d in DIMS:
        summary[s]["dom_fer"][f"v_{d}"] = dom[f"v_{d}"] + fer[f"v_{d}"]
        summary[s]["dom_fer"][f"vlab_{d}"] = dom[f"vlab_{d}"] + fer[f"vlab_{d}"]
        summary[s]["dom_fer"][f"vfrac_{d}"] = dom[f"vfrac_{d}"] + fer[f"vfrac_{d}"]

# ------------------------------------------------------- calendar consistency
cal_rows = []
d = START
while d <= END:
    cal_rows.append({"fecha": str(d), "tipo": day_type(d),
                     "domingo": d.weekday() == 6, "feriado": d in HOL and HOL[d][1] != "LP",
                     "feriado_nombre": HOL[d][0] if d in HOL else ""})
    d += dt.timedelta(days=1)
cal = pd.DataFrame(cal_rows)
n_dom_cal = int((cal.tipo == "domingo").sum())
n_fer_cal = int((cal.tipo == "feriado").sum())
assert n_dom_cal + n_fer_cal == int(((cal.tipo == "domingo") | (cal.tipo == "feriado")).sum())

# -------------------------------------------------------------- product mix
mixed = raw[raw.d.map(day_type).isin(["domingo", "feriado"])]
own = mixed[mixed.propio]
fam = (own.groupby("family")
       .agg(amount=("amount", "sum"), skus=("item_code", "nunique"),
            tickets_con_producto=("tickets", "sum"),
            dim=("dim", lambda s: s.mode().iat[0] if len(s.mode()) else "?"))
       .reset_index())
fam["amount"] = fam.amount.round(2)
for d in DIMS:
    fam[f"v_{d}"] = (own[own.dim == d].groupby("family")[f"v_{d}"].sum()
                     .reindex(fam.family).fillna(0.0).values)

fam_pivot = (own.groupby(["family", "whs_code"]).amount.sum().unstack(fill_value=0.0)
             .reindex(columns=list(SALONS), fill_value=0.0))
fam_pivot["total"] = fam_pivot.sum(axis=1)
fam_pivot = fam_pivot.sort_values("total", ascending=False).round(2)

btype_pivot = (mixed.groupby(["btype", "whs_code"]).amount.sum().unstack(fill_value=0.0)
               .reindex(columns=list(SALONS), fill_value=0.0))
btype_pivot["total"] = btype_pivot.sum(axis=1)
btype_pivot = btype_pivot.sort_values("total", ascending=False).round(2)

top_products = (mixed.groupby(["item_code", "name", "family", "dim", "btype"])
                .agg(amount=("amount", "sum"), tickets_con_producto=("tickets", "sum"))
                .reset_index().sort_values("amount", ascending=False).head(40).round(2))
per_salon_products = {}
for s in SALONS:
    f = mixed[mixed.whs_code == s]
    per_salon_products[s] = (f.groupby(["item_code", "name", "family"])
                             .agg(amount=("amount", "sum"), tickets_con_producto=("tickets", "sum"))
                             .reset_index().sort_values("amount", ascending=False)
                             .head(12).round(2).to_dict("records"))

# ---------------------------------------------------------------- outputs
flat = []
for s in SALONS:
    for t in list(DAYTYPES) + ["dom_fer"]:
        r = summary[s][t]
        row = {"salon": s, "tipo": t}
        row.update({k: v for k, v in r.items()})
        row["salon_nombre"] = LABEL[s]
        flat.append(row)
pd.DataFrame(flat).to_csv(f"{HERE}/domingos_feriados_2026_resumen_salon.csv",
                          index=False, encoding="utf-8")
pd.DataFrame(dates_rows).to_csv(f"{HERE}/domingos_feriados_2026_volumen_por_fecha.csv",
                                index=False, encoding="utf-8")
fam.to_csv(f"{HERE}/domingos_feriados_2026_top_familias.csv", index=False, encoding="utf-8")
top_products.to_csv(f"{HERE}/domingos_feriados_2026_top_productos.csv", index=False, encoding="utf-8")
btype_pivot.reset_index().to_csv(f"{HERE}/domingos_feriados_2026_tipo_producto.csv",
                                 index=False, encoding="utf-8")
fam_pivot.reset_index().to_csv(f"{HERE}/domingos_feriados_2026_familias_por_salon.csv",
                               index=False, encoding="utf-8")

ranking_dom = sorted(SALONS, key=lambda s: -summary[s]["domingo"]["amount"])
ranking_fer = sorted(SALONS, key=lambda s: -summary[s]["feriado"]["amount"])
ranking_domfer = sorted(SALONS, key=lambda s: -summary[s]["dom_fer"]["amount"])
ranking_dom_dia = sorted(SALONS, key=lambda s: -(summary[s]["domingo"]["monto_por_dia"] or 0))
ranking_fer_dia = sorted(SALONS, key=lambda s: -(summary[s]["feriado"]["monto_por_dia"] or 0))

result = {
    "generado": "2026-10-22",
    "periodo": "2026-01-01..2026-09-30",
    "universo": "salones CM/2A/RC/VI, lineas activas en Bs",
    "calendario": {
        "domingos": n_dom_cal, "feriados_no_domingo": n_fer_cal,
        "feriados_lista": [{"fecha": str(k), "nombre": v[0], "alcance": v[1]}
                           for k, v in sorted(HOL.items())
                           if START <= k <= END and v[1] != "LP"],
        "nota": "Domingo que coincide con feriado se cuenta solo como domingo; "
                "feriado departamental de La Paz excluido por alcance.",
    },
    "resumen_salon": summary,
    "ranking_domingo": ranking_dom,
    "ranking_feriado": ranking_fer,
    "ranking_domingo_feriado": ranking_domfer,
    "ranking_domingo_por_dia": ranking_dom_dia,
    "ranking_feriado_por_dia": ranking_fer_dia,
    "familias_dom_fer": fam_pivot.head(20).to_dict(orient="index"),
    "tipos_producto_dom_fer": btype_pivot.to_dict(orient="index"),
    "top_productos_dom_fer": top_products.to_dict("records"),
    "top_productos_por_salon": per_salon_products,
    "checks": {
        "lineas_totales": int(len(raw)),
        "monto_total": round(float(raw.amount.sum()), 2),
        "monto_con_factor": round(float(raw.loc[raw.dim != "sin_factor", "amount"].sum()), 2),
        "cobertura_monto_factor_pct": round(
            100 * float(raw.loc[raw.dim != "sin_factor", "amount"].sum()) / float(raw.amount.sum()), 2),
        "monto_propio": round(float(raw.loc[raw.propio, "amount"].sum()), 2),
        "cobertura_propio_pct": round(
            100 * float(raw.loc[raw.propio, "amount"].sum()) / float(raw.amount.sum()), 2),
        "items_sin_factor": sorted(raw.loc[raw.dim == "sin_factor", "item_code"].unique().tolist()),
    },
}
json.dump(result, open(f"{HERE}/domingos_datos_clave.json", "w"), indent=1,
          ensure_ascii=False, default=float)

# ---------------------------------------------------------------- console
print(f"calendario: {n_dom_cal} domingos, {n_fer_cal} feriados no domingo")
print("\n== resumen por salon (domingo / feriado / total)")
for s in SALONS:
    r = summary[s]
    print(f"{LABEL[s]:32s} dom {r['domingo']['amount']:>11,.0f} ({r['domingo']['dias']}d, "
          f"{r['domingo']['monto_por_dia']:>9,.0f}/dom, tk {r['domingo']['ticket_promedio']:>6,.0f}) | "
          f"fer {r['feriado']['amount']:>10,.0f} ({r['feriado']['dias']}d, "
          f"{r['feriado']['monto_por_dia']:>9,.0f}/fer) | "
          f"total {r['total']['amount']:>12,.0f}")
print("\nranking domingo:", ranking_dom)
print("ranking domingo / dia operado:", ranking_dom_dia)
print("ranking feriado:", ranking_fer)
print("ranking feriado / dia operado:", ranking_fer_dia)
print("ranking dom+fer:", ranking_domfer)
print("\n== volumen fisico dom+fer (propio: LAB terminado + fraccionado)")
for s in SALONS:
    r = summary[s]["dom_fer"]
    print(f"{LABEL[s]:32s} L {r['v_L']:>10,.1f} kg {r['v_kg']:>10,.1f} "
          f"dosis {r['v_dose']:>10,.0f} pres {r['v_pres']:>7,.0f} "
          f"| LAB L {r['vlab_L']:>8,.1f} | FRAC L {r['vfrac_L']:>9,.1f}")
print("\n== tipo de producto dom+fer (Bs)")
print(btype_pivot.to_string())
print("\n== top familias propias dom+fer (Bs)")
print(fam_pivot.head(15).to_string())
print("\n== checks")
print(json.dumps(result["checks"], indent=1, ensure_ascii=False)[:1500])

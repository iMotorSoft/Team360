"""Sunday / holiday performance by salon, 2026 detail plus 2022-2024 reference.

Outputs per-date tables and per-salon averages. Amount = net line amount in Bs,
active invoices only, before credit notes.
"""
import csv
import datetime as dt
import json

import duckdb

OUT = "/tmp/opencode/telchi-hist"
SALONS26 = ("CM-SAL", "2A-SAL", "RC-SAL", "VI-SAL")
OFFICE2SALON = {
    "CasaMatriz": "CM (Casa Matriz / Centro)",
    "SegundoAnillo": "2A (2do. Anillo)",
    "RocaCoronado": "RC (Roca y Coronado)",
    "Villa": "VI (Villa 1ro. de Mayo)",
    "Urubo": "UR (Urubo)",
}
SALON_LABEL = {
    "CM-SAL": "CM (Casa Matriz / Centro)",
    "2A-SAL": "2A (2do. Anillo)",
    "RC-SAL": "RC (Roca y Coronado)",
    "VI-SAL": "VI (Villa 1ro. de Mayo)",
}


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


YEARS = (2022, 2023, 2024, 2026)
HOL = {}
for y in YEARS:
    HOL.update(holidays(y))

con = duckdb.connect()
con.execute("SET threads=3")
con.execute("SET memory_limit='3GB'")
con.execute(f"CREATE VIEW fs AS SELECT * FROM read_parquet('{OUT}/extract/foundation_sales_lines.parquet')")
con.execute(f"CREATE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")

# ---------------- 2026 daily per salon
d26 = con.execute("""
SELECT whs_code, doc_date::DATE d, count(*) lines,
       sum(cast(line_total AS DECIMAL(38,6))) amount,
       count(DISTINCT doc_entry) tickets
FROM fs WHERE canceled='N' AND doc_currency='BS'
  AND doc_date>='2026-01-01' AND doc_date<'2026-10-01'
  AND whs_code IN ('CM-SAL','2A-SAL','RC-SAL','VI-SAL')
GROUP BY 1,2 ORDER BY 2,1
""").fetchall()
daily26 = {}
for whs, d, lines, amt, tk in d26:
    d = dt.date.fromisoformat(str(d)[:10])
    daily26[(whs, d)] = {"amount": float(amt), "tickets": int(tk), "lines": int(lines)}

# ---------------- 2022-2024 daily per office (salon warehouses only, where present)
whs_check = con.execute("""
SELECT DocDate::DATE d, OfficeName, WhsCode, count(*) n, sum(ItemSale) amt
FROM ls
WHERE u_estadofc<>'A' AND DocDate>='2022-04-06' AND DocDate<'2024-07-01'
  AND dayofweek(DocDate)=0
  AND OfficeName IN ('CasaMatriz','SegundoAnillo','RocaCoronado','Villa','Urubo')
GROUP BY 1,2,3 ORDER BY 1
""").fetchall()
print("== Sunday SAP 2022-2024 warehouse mix (top 30)")
for r in whs_check[:30]:
    print(r)

d_old = con.execute("""
SELECT OfficeName, DocDate::DATE d, count(*) lines, sum(ItemSale) amount,
       count(DISTINCT DocEntry) tickets
FROM ls WHERE u_estadofc<>'A' AND DocDate>='2022-04-06' AND DocDate<'2024-07-01'
  AND WhsCode LIKE '%-SAL'
GROUP BY 1,2
""").fetchall()
daily_old = {}
for off, d, lines, amt, tk in d_old:
    d = dt.date.fromisoformat(str(d)[:10])
    daily_old[(off, d)] = {"amount": float(amt), "tickets": int(tk), "lines": int(lines)}


def kinds(d):
    """Return (is_sunday, is_holiday) applying the SC/LP scope to Santa Cruz salons."""
    holiday = d in HOL
    if holiday and HOL[d][1] == "LP":
        holiday = False          # La Paz departmental holiday does not apply in Santa Cruz
    return d.weekday() == 6, holiday


def summarize_2026():
    out = {}
    totals = {}
    for whs in SALONS26:
        tot = {"amount": 0.0, "tickets": 0, "days": 0,
               "sun": {"amount": 0.0, "tickets": 0, "days": 0},
               "hol": {"amount": 0.0, "tickets": 0, "days": 0},
               "sat": {"amount": 0.0, "tickets": 0, "days": 0},
               "wd": {"amount": 0.0, "tickets": 0, "days": 0}}
        for (w, d), v in daily26.items():
            if w != whs:
                continue
            tot["amount"] += v["amount"]
            tot["tickets"] += v["tickets"]
            tot["days"] += 1
            sun, hol = kinds(d)
            key = "sun" if sun else ("hol" if hol else ("sat" if d.weekday() == 5 else "wd"))
            tot[key]["amount"] += v["amount"]
            tot[key]["tickets"] += v["tickets"]
            tot[key]["days"] += 1
        totals[whs] = tot
    out["totals"] = totals
    return out


sum26 = summarize_2026()

# per-date table for Sundays + holidays in 2026
dates = []
d = dt.date(2026, 1, 1)
while d <= dt.date(2026, 9, 30):
    sun, hol = kinds(d)
    if sun or hol:
        row = {"date": str(d), "weekday": d.strftime("%A"),
               "type": "domingo" if sun else "feriado",
               "holiday": HOL[d][0] if (d in HOL and HOL[d][1] != "LP") else None,
               "scope": HOL[d][1] if (d in HOL and HOL[d][1] != "LP") else None,
               "salons": {}}
        for whs in SALONS26:
            v = daily26.get((whs, d))
            if v:
                row["salons"][whs] = {"amount": round(v["amount"], 2), "tickets": v["tickets"],
                                      "avg_ticket": round(v["amount"] / v["tickets"], 2) if v["tickets"] else None}
            else:
                row["salons"][whs] = None
        dates.append(row)
    d += dt.timedelta(days=1)

# ---------------- 2022-2024 aggregate per office
def summarize_old(start, end):
    agg = {}
    for (off, d), v in daily_old.items():
        if not (start <= str(d) <= end) or off not in OFFICE2SALON:
            continue
        a = agg.setdefault(off, {"amount": 0.0, "tickets": 0, "days": 0,
                                 "sun": {"amount": 0.0, "tickets": 0, "days": 0},
                                 "hol": {"amount": 0.0, "tickets": 0, "days": 0},
                                 "sat": {"amount": 0.0, "tickets": 0, "days": 0},
                                 "wd": {"amount": 0.0, "tickets": 0, "days": 0}})
        a["amount"] += v["amount"]
        a["tickets"] += v["tickets"]
        a["days"] += 1
        sun, hol = kinds(d)
        key = "sun" if sun else ("hol" if hol else ("sat" if d.weekday() == 5 else "wd"))
        a[key]["amount"] += v["amount"]
        a[key]["tickets"] += v["tickets"]
        a[key]["days"] += 1
    return agg


old = {
    "2022_abr_sep": summarize_old("2022-04-06", "2022-09-30"),
    "2023": summarize_old("2023-01-01", "2023-12-31"),
    "2024_ene_jun": summarize_old("2024-01-01", "2024-06-30"),
}

res = {"salon_2026": sum26["totals"], "dates_2026": dates, "old": old}
json.dump(res, open(f"{OUT}/out/sundays.json", "w"), indent=1, ensure_ascii=False, default=str)

# csv per-date
with open(f"{OUT}/out/domingos_feriados_2026.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["fecha", "dia", "tipo", "feriado", "alcance"]
               + [f"{s}_Bs" for s in SALONS26] + [f"{s}_tickets" for s in SALONS26])
    for r in dates:
        w.writerow([r["date"], r["weekday"], r["type"], r["holiday"] or "", r["scope"] or ""]
                   + [(r["salons"][s] or {}).get("amount", "") for s in SALONS26]
                   + [(r["salons"][s] or {}).get("tickets", "") for s in SALONS26])

print("== 2026 totals per salon")
print(json.dumps({SALON_LABEL[k]: {kk: (round(vv, 2) if isinstance(vv, float) else vv)
                                   for kk, vv in v.items() if kk != "amount"}
                  for k, v in sum26["totals"].items()}, indent=1, ensure_ascii=False))
print("== 2026 per-date (domingos y feriados)")
for r in dates:
    line = f"{r['date']} {r['weekday'][:3]} {r['type']:8s} {str(r['holiday'] or ''):28s}"
    for s in SALONS26:
        v = r["salons"][s]
        line += f" | {s}: " + (f"{v['amount']:>10,.0f}/{v['tickets']:>5}" if v else "   cerrado        ")
    print(line)
print("== 2022-2024 aggregates")
for per, agg in old.items():
    print("--", per)
    for off, a in sorted(agg.items(), key=lambda x: -x[1]["sun"]["amount"]):
        print(off, {k: (round(v["amount"]), v["tickets"], v["days"]) for k, v in a.items() if isinstance(v, dict)})

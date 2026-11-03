"""Derived Sunday/holiday tables for the report."""
import datetime as dt
import json

import duckdb

OUT = "/tmp/opencode/telchi-hist"
S26 = ("2A-SAL", "CM-SAL", "VI-SAL", "RC-SAL")
LABEL = {"2A-SAL": "2A (2do. Anillo)", "CM-SAL": "CM (Casa Matriz = Centro)",
         "VI-SAL": "VI (Villa 1ro. de Mayo)", "RC-SAL": "RC (Roca y Coronado)",
         "SegundoAnillo": "2A (2do. Anillo)", "CasaMatriz": "CM (Casa Matriz = Centro)",
         "Villa": "VI (Villa 1ro. de Mayo)", "RocaCoronado": "RC (Roca y Coronado)",
         "Urubo": "UR (Urubo)"}

d = json.load(open(f"{OUT}/out/sundays.json"))
cal = {r["date"]: r for r in d["dates_2026"]}


def agg(node):
    return {"amount": node["amount"], "tickets": node["tickets"], "days": node["days"],
            "avg_day": node["amount"] / node["days"] if node["days"] else None,
            "avg_ticket": node["amount"] / node["tickets"] if node["tickets"] else None}


out = {"2026": {}, "old": {}, "dates": []}

for whs in S26:
    t = d["salon_2026"][whs]
    out["2026"][whs] = {
        "total": agg(t),
        "sunday": agg(t["sun"]),
        "holiday_weekday": agg(t["hol"]),
        "saturday": agg(t["sat"]),
        "weekday": agg(t["wd"]),
        "sunday_share": t["sun"]["amount"] / t["amount"] if t["amount"] else None,
        "holiday_share": t["hol"]["amount"] / t["amount"] if t["amount"] else None,
    }

# common Sundays between 2A and CM (both operated)
common = [r for r in d["dates_2026"] if r["type"] == "domingo"
          and r["salons"].get("2A-SAL") and r["salons"].get("CM-SAL")]
out["common_sundays"] = {
    "dates": len(common),
    "2A-SAL": {"amount": round(sum(r["salons"]["2A-SAL"]["amount"] for r in common), 2),
               "tickets": sum(r["salons"]["2A-SAL"]["tickets"] for r in common)},
    "CM-SAL": {"amount": round(sum(r["salons"]["CM-SAL"]["amount"] for r in common), 2),
               "tickets": sum(r["salons"]["CM-SAL"]["tickets"] for r in common)},
}

# holiday detail 2026 (weekday holidays only, SC scope)
hol_rows = []
for r in d["dates_2026"]:
    if r["type"] != "feriado":
        continue
    tot = sum(v["amount"] for v in r["salons"].values() if v)
    tk = sum(v["tickets"] for v in r["salons"].values() if v)
    order = sorted([(k, v) for k, v in r["salons"].items() if v], key=lambda x: -x[1]["amount"])
    hol_rows.append({"date": r["date"], "holiday": r["holiday"], "total": round(tot, 2),
                     "tickets": tk, "leader": order[0][0] if order else None,
                     "per_salon": {k: r["salons"][k] for k in S26}})
out["holidays_2026"] = hol_rows
out["holiday_2026_total"] = {"amount": round(sum(h["total"] for h in hol_rows), 2),
                             "tickets": sum(h["tickets"] for h in hol_rows),
                             "days": len(hol_rows)}

for per, offices in d["old"].items():
    out["old"][per] = {}
    for off, a in offices.items():
        out["old"][per][LABEL.get(off, off)] = {
            "sunday": agg(a["sun"]), "holiday_weekday": agg(a["hol"]),
            "saturday": agg(a["sat"]), "weekday": agg(a["wd"]), "total": agg(a),
        }

# holiday warehouse mix 2022-2024 to confirm salon-only
con = duckdb.connect()
con.execute("SET threads=2")
con.execute(f"CREATE VIEW ls AS SELECT * FROM read_parquet('{OUT}/extract/sap_sales_2022_2024.parquet')")
hol_dates = [h["date"] for h in hol_rows]
con.execute("CREATE OR REPLACE TABLE hd(d DATE)")
con.executemany("INSERT INTO hd VALUES (?)", [[x] for x in hol_dates])
out["holiday_whs_mix_old"] = [
    {"office": r[0], "whs": r[1], "amount": round(float(r[2]), 2)}
    for r in con.execute("""
    SELECT OfficeName, WhsCode, sum(ItemSale) FROM ls
    WHERE u_estadofc<>'A' AND DocDate>='2022-04-06' AND DocDate<'2024-07-01'
      AND DocDate::DATE IN (SELECT d FROM hd) GROUP BY 1,2 ORDER BY 1,3 DESC""").fetchall()
]

json.dump(out, open(f"{OUT}/out/branch_summary.json", "w"), indent=1, ensure_ascii=False)

print("== 2026 per salon (avg per operated day / avg ticket)")
for k, v in out["2026"].items():
    print(f"{k:7s} total {v['total']['amount']:>12,.0f} tk {v['total']['tickets']:>6} | "
          f"Sun {v['sunday']['amount']:>10,.0f} tk {v['sunday']['tickets']:>5} days {v['sunday']['days']:>2} "
          f"avg/day {v['sunday']['avg_day']:>8,.0f} avg/tk {v['sunday']['avg_ticket']:>6,.1f} share {v['sunday_share']*100:4.1f}% | "
          f"Hol {v['holiday_weekday']['amount']:>9,.0f} tk {v['holiday_weekday']['tickets']:>4} days {v['holiday_weekday']['days']:>2} "
          f"avg/day {v['holiday_weekday']['avg_day']:>8,.0f} | Wd avg/day {v['weekday']['avg_day']:>8,.0f} | Sat avg/day {v['saturday']['avg_day']:>8,.0f}")
print("== common Sundays (34):", out["common_sundays"])
print("== holidays 2026")
for h in hol_rows:
    print(h["date"], h["holiday"], f"{h['total']:>10,.0f}", "leader", h["leader"],
          {k: (v["amount"] if v else None) for k, v in h["per_salon"].items()})
print("== holiday whs mix 2022-2024")
for r in out["holiday_whs_mix_old"]:
    print(r)
print("== old years Sunday/holiday avg per day")
for per, v in out["old"].items():
    print("--", per)
    for k, x in v.items():
        print(f"   {k:32s} Sun {x['sunday']['amount']:>9,.0f}/{x['sunday']['days']:>3}d={x['sunday']['avg_day'] or 0:>7,.0f} "
              f"tk {x['sunday']['tickets']:>5} | Hol {x['holiday_weekday']['amount']:>9,.0f}/{x['holiday_weekday']['days']:>2}d={x['holiday_weekday']['avg_day'] or 0:>8,.0f} | "
              f"Wd/day {x['weekday']['avg_day'] or 0:>8,.0f}")

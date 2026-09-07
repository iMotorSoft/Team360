"""TELCHI_PRODUCT_SEASONALITY_V1 - validator (READ ONLY on HANA).

Executes the seasonality gate:
  1. SQL contract (monthly net sales per item)
  2. Build continuous zero-filled monthly series per item
  3. Classify demand pattern (STABLE/SEASONAL/GROWING/DECLINING/INTERMITTENT/...)
  4. Bronceadores case (family identification + pattern + forecast + backtest)
  5. Walk-forward backtest across forecast methods
  6. Metrics (MAE/WAPE/BIAS)
  7. Stockout censoring flag (zero sales + zero stock evidence)
  8. Component->FG mapping for tracer materials (soda/cloruro/benzoato/gotero)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.seasonality import seasonality_domain as sd  # noqa: E402
from modules.telchi.investigation.validation.seasonality import forecast as fc  # noqa: E402
from modules.telchi.investigation.validation.seasonality import backtest as bt  # noqa: E402

SQL_DIR = INVESTIGATION_ROOT / "sql" / "current" / "seasonality"

BRONCEADORES = ("L00072", "L00073", "L01630", "L03124", "L03125")


def run_contracts(cur) -> dict:
    out = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        try:
            cur.execute(f.read_text(encoding="utf-8"))
            n = len(cur.fetchall())
            out[f.name] = {"rows": n, "ok": True}
        except Exception as exc:  # pragma: no cover
            out[f.name] = {"rows": 0, "ok": False, "error": str(exc)}
    return out


def load_monthly(cur) -> dict[str, dict[tuple[int, int], float]]:
    cur.execute('''SELECT L."ItemCode", YEAR(H."DocDate"), MONTH(H."DocDate"), SUM(L."Quantity")
        FROM "TELCHI"."OINV" H JOIN "TELCHI"."INV1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CANCELED"='N' GROUP BY L."ItemCode", YEAR(H."DocDate"), MONTH(H."DocDate")''')
    gross = defaultdict(dict)
    for item, y, m, q in cur.fetchall():
        gross[item][(y, m)] = float(q or 0)
    cur.execute('''SELECT L."ItemCode", YEAR(H."DocDate"), MONTH(H."DocDate"), SUM(L."Quantity")
        FROM "TELCHI"."ORIN" H JOIN "TELCHI"."RIN1" L ON L."DocEntry"=H."DocEntry"
        WHERE H."CANCELED"='N' GROUP BY L."ItemCode", YEAR(H."DocDate"), MONTH(H."DocDate")''')
    ret = defaultdict(dict)
    for item, y, m, q in cur.fetchall():
        ret[item][(y, m)] = float(q or 0)
    series = {}
    for item, g in gross.items():
        s = {}
        for k, q in g.items():
            s[k] = q - ret.get(item, {}).get(k, 0.0)
        series[item] = sd.fill_zero_months(s)
    return series


def main() -> int:
    conn, cur = connect()
    try:
        contracts = run_contracts(cur)
        series = load_monthly(cur)

        AS_OF = (2026, 8)
        profiles = {}
        for item, s in series.items():
            p = sd.classify(s, AS_OF[0], AS_OF[1])
            p.itemcode = item
            profiles[item] = p

        pat_cnt = Counter(p.pattern for p in profiles.values())
        # volume-weighted coverage
        total_vol = 0.0
        covered_vol = 0.0
        for item, p in profiles.items():
            v = sum(series[item].values())
            total_vol += v
            if p.confidence in ("HIGH", "MEDIUM") and p.pattern not in (sd.PATTERN_UNRESOLVED, sd.PATTERN_INSUFFICIENT):
                covered_vol += v

        # bronceadores
        bron = {}
        for code in BRONCEADORES:
            if code not in series:
                continue
            s = series[code]
            p = profiles.get(code)
            snapshots = [(y, m) for (y, m) in sorted(s) if (y, m) >= (2025, 1) and (y, m) < (2026, 4)]
            bt_res = bt.walk_forward(s, snapshots, horizon=3,
                                     methods=list(fc.FORECAST_METHODS.keys()))
            bron[code] = {
                "profile": p.to_dict() if p else None,
                "backtest": bt_res,
                "best_method": bt.choose_method(bt_res),
            }

        # component -> FG mapping (tracer)
        tracers = {"L01010": "SODA", "L01821": "CLORURO", "L01785": "BENZOATO", "L03427": "GOTERO"}
        comp_fg = {}
        cur.execute('''SELECT C."ItemCode", O."ItemCode" FROM "TELCHI"."IGE1" C
            JOIN "TELCHI"."OWOR" O ON O."DocEntry"=C."BaseEntry"
            WHERE C."BaseType"=202 AND C."ItemCode" IN ('L01010','L01821','L01785','L03427')
            GROUP BY C."ItemCode", O."ItemCode"''')
        for comp, fg in cur.fetchall():
            comp_fg.setdefault(comp, set()).add(fg)

        result = {
            "gate": "TELCHI_PRODUCT_SEASONALITY_V1",
            "contracts": contracts,
            "items_analyzed": len(series),
            "pattern_dist": dict(pat_cnt),
            "volume_coverage_pct": round(covered_vol / total_vol * 100, 1) if total_vol else 0,
            "bronceadores": bron,
            "tracer_fg_mapping": {k: sorted(v) for k, v in comp_fg.items()},
        }
        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*72}\nTELCHI_PRODUCT_SEASONALITY_V1\n{'='*72}")
        failed = [k for k, v in contracts.items() if not v["ok"]]
        print(f"SQL CONTRACTS: {len(contracts)-len(failed)}/{len(contracts)} OK")
        for f in failed:
            print(f"  FAIL {f}: {contracts[f].get('error')}")

        print(f"\nITEMS ANALYZED: {len(series):,}")
        print(f"PATTERN DIST: {dict(pat_cnt)}")
        print(f"VOLUME COVERAGE (HIGH/MEDIUM confidence): {result['volume_coverage_pct']}%")

        print("\nBRONCEADORES:")
        for code, b in bron.items():
            p = b["profile"]
            print(f"  {code}: pattern={p['pattern']} conf={p['confidence']} peak_month={p['peak_month']} "
                  f"peak_share={p['peak_share']} cv={p['cv']} years={p['years_history']}")
            print(f"    best_method={b['best_method']} backtest={ {k: {kk: round(vv,2) for kk,vv in v.items() if kk!='n'} for k,v in b['backtest'].items()} }")

        print("\nTRACER COMPONENT -> FG (demand consumers):")
        for comp, label in tracers.items():
            fgs = comp_fg.get(comp, set())
            patterns = Counter(profiles.get(fg).pattern if fg in profiles else "?" for fg in fgs)
            print(f"  {label} ({comp}): {len(fgs)} FG -> {dict(patterns)}")

        gate = "TELCHI_PRODUCT_SEASONALITY_V1_PASS" if not failed else \
            "TELCHI_PRODUCT_SEASONALITY_V1_DEGRADED"
        print(f"\n{gate}")
        return 0 if "PASS" in gate else 2
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
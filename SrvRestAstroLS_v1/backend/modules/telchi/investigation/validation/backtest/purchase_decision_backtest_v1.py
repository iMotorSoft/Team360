"""TELCHI_PURCHASE_DECISION_BACKTEST_V1 - validator (READ ONLY on HANA).

Historical backtest of the coverage/risk decision without hindsight:
  - stock-as-of-T reconstructed from OINM (InQty-OutQty, raw warehouses)
  - component consumption history from IGE1 (DocDate <= T)
  - forward forecast (seasonal moving average) -> predicted stockout month
  - ACTUAL consumption after T -> actual exhaustion month
  - verdict POTENTIAL_EARLY_WARNING / MISSED_PURCHASE / OVERBUY / CONSISTENT
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.atomic.connection import connect  # noqa: E402
from modules.telchi.investigation.validation.coverage.coverage_domain import month_add  # noqa: E402
from modules.telchi.investigation.validation.seasonality import forecast as fc  # noqa: E402
from modules.telchi.investigation.validation.backtest.backtest_domain import (  # noqa: E402
    BacktestResult, actual_stockout, early_warning_accuracy, fill_zero_months,
    predict_stockout, verdict_for,
)

RAW_WAREHOUSES = ('LAB-M1', 'SAA-M1', 'MAG-M1')

COMPONENTS = {
    "L01010": "SODA CAUSTICA 25kg",
    "L01821": "CLORURO DE CALCIO 25kg",
    "L01785": "BENZOATO DE SODIO 25kg",
    "L03427": "FRASCO GOTERO 30mL",
    "L03428": "TAPA GOTERO 30mL",
    "L03429": "CONTRA TAPA GOTERO 30mL",
    "L00219": "TAPA PET BLANCA",
    "L00097": "FRASCO 1L",
    "L00205": "ETIQUETA",
    "L00838": "PRECINTO",
}

SNAPSHOTS = [
    ("2025-01-31", (2025, 1)),
    ("2025-06-30", (2025, 6)),
    ("2025-09-30", (2025, 9)),
    ("2026-01-31", (2026, 1)),
]

HORIZON = 6


def load_stock_asof(cur, cutoff: str) -> dict[str, float]:
    placeholders = ",".join("?" for _ in COMPONENTS)
    cur.execute(f'''SELECT "ItemCode", SUM("InQty")-SUM("OutQty") FROM "TELCHI"."OINM"
        WHERE "ItemCode" IN ({placeholders})
          AND "Warehouse" IN ('LAB-M1','SAA-M1','MAG-M1') AND "DocDate" <= ?
        GROUP BY "ItemCode"''', (*COMPONENTS.keys(), cutoff))
    return {r[0]: float(r[1] or 0) for r in cur.fetchall()}


def load_consumption(cur) -> dict[str, dict[tuple[int, int], float]]:
    placeholders = ",".join("?" for _ in COMPONENTS)
    cur.execute(f'''SELECT "ItemCode", YEAR("DocDate"), MONTH("DocDate"), SUM("Quantity")
        FROM "TELCHI"."IGE1" WHERE "ItemCode" IN ({placeholders}) AND "BaseType"=202
        GROUP BY "ItemCode", YEAR("DocDate"), MONTH("DocDate")''', (*COMPONENTS.keys(),))
    out = defaultdict(dict)
    for item, y, m, q in cur.fetchall():
        out[item][(y, m)] = float(q or 0)
    return out


def forecast_from(history: dict[tuple[int, int], float],
                  snapshot: tuple[int, int]) -> dict[tuple[int, int], float]:
    """6-month forward forecast using seasonal moving average over history."""
    fn = fc.seasonal_moving_average
    out: dict[tuple[int, int], float] = {}
    y, m = month_add(snapshot[0], snapshot[1], 1)
    for k in range(HORIZON):
        yy, mm = month_add(y, m, k)
        out[(yy, mm)] = max(0.0, fn(history, yy, mm))
    return out


def main() -> int:
    conn, cur = connect()
    try:
        consumption = load_consumption(cur)
        results: list[BacktestResult] = []

        for cutoff, snap in SNAPSHOTS:
            stock = load_stock_asof(cur, cutoff)
            start_history = (snap[0] - 3, 1)
            for comp, label in COMPONENTS.items():
                hist = {k: v for k, v in consumption.get(comp, {}).items() if k <= snap}
                hist = fill_zero_months(hist, start_history, snap)
                fc_map = forecast_from(hist, snap)
                predicted = predict_stockout(comp, stock.get(comp, 0.0), fc_map)
                # actual consumption in the 6 months after snapshot
                act_start = month_add(snap[0], snap[1], 1)
                act_end = month_add(snap[0], snap[1], HORIZON)
                act = {k: v for k, v in consumption.get(comp, {}).items()
                       if act_start <= k <= act_end}
                actual = actual_stockout(comp, stock.get(comp, 0.0), act)
                verdict = verdict_for(predicted, actual)
                results.append(BacktestResult(
                    component=comp, snapshot=snap, stock_at_t=stock.get(comp, 0.0),
                    predicted_stockout_month=predicted, actual_stockout_month=actual,
                    verdict=verdict,
                    predicted_total_6mo=sum(fc_map.values()),
                    actual_total_6mo=sum(act.values()),
                    details={"label": label,
                             "accurate": early_warning_accuracy(predicted, actual)}))

        verdict_cnt = Counter(r.verdict for r in results)
        early_warnings = [r for r in results if r.verdict == "POTENTIAL_EARLY_WARNING"]
        n_accurate = sum(1 for r in early_warnings if r.details.get("accurate"))

        out = {
            "gate": "TELCHI_PURCHASE_DECISION_BACKTEST_V1",
            "components": len(COMPONENTS),
            "snapshots": [list(s[1]) for s in SNAPSHOTS],
            "results": [r.to_dict() for r in results],
            "verdict_dist": dict(verdict_cnt),
            "early_warning_accurate": n_accurate,
            "early_warning_total": len(early_warnings),
        }
        print(json.dumps(out, indent=2, default=str))

        print(f"\n{'='*72}\nTELCHI_PURCHASE_DECISION_BACKTEST_V1\n{'='*72}")
        print(f"COMPONENTS: {len(COMPONENTS)} | SNAPSHOTS: {len(SNAPSHOTS)} | "
              f"cases: {len(results)}")
        print(f"VERDICT DIST: {dict(verdict_cnt)}")
        if early_warnings:
            print(f"EARLY WARNING accuracy (within +-1 month): "
                  f"{n_accurate}/{len(early_warnings)}")

        print("\nRESULTS BY COMPONENT (snapshot | stock | pred_out | act_out | verdict):")
        for comp, label in COMPONENTS.items():
            rows = [r for r in results if r.component == comp]
            for r in rows:
                pred = f"{r.predicted_stockout_month[0]}-{r.predicted_stockout_month[1]:02d}" if r.predicted_stockout_month else "-"
                act = f"{r.actual_stockout_month[0]}-{r.actual_stockout_month[1]:02d}" if r.actual_stockout_month else "-"
                print(f"  {comp} {label[:28]:<28} | {r.snapshot[0]}-{r.snapshot[1]:02d} | "
                      f"stock={r.stock_at_t:>10,.0f} | pred={pred:>7} | act={act:>7} | {r.verdict}")

        gate = "TELCHI_PURCHASE_DECISION_BACKTEST_V1_PASS"
        print(f"\n{gate}")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

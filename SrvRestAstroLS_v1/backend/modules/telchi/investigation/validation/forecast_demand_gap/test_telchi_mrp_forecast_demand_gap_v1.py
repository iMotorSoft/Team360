from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from modules.telchi.investigation.validation.forecast_demand_gap.telchi_mrp_forecast_demand_gap_v1 import (
    DEFAULT_SNAPSHOT,
    DEMAND_BASELINE,
    GATE,
    build_selected_cte,
    pct,
)


class ForecastDemandGapContractTests(unittest.TestCase):
    def test_gate_and_snapshot_are_explicit(self) -> None:
        self.assertEqual(GATE, "TELCHI_MRP_FORECAST_DEMAND_GAP_V1")
        self.assertEqual(DEFAULT_SNAPSHOT, date(2026, 9, 14))

    def test_demand_baseline_is_reused_without_claiming_item_mapping(self) -> None:
        self.assertEqual(DEMAND_BASELINE["analyzed_items"], 10775)
        self.assertEqual(DEMAND_BASELINE["SEASONAL"], 1950)
        self.assertEqual(DEMAND_BASELINE["GROWING"], 1003)
        self.assertEqual(DEMAND_BASELINE["STABLE"], 922)
        self.assertEqual(DEMAND_BASELINE["INTERMITTENT"], 342)

    def test_selection_sql_prioritizes_current_then_future_then_history(self) -> None:
        sql = build_selected_cte(Path("/tmp/ofct_fct1.parquet"), DEFAULT_SNAPSHOT)
        self.assertIn("ROW_NUMBER() OVER", sql)
        self.assertIn("WHEN HeaderStart <= DATE '2026-09-14'", sql)
        self.assertIn("WHEN HeaderStart > DATE '2026-09-14'", sql)
        self.assertIn("ELSE 2", sql)
        self.assertIn("PARTITION BY ItemCode, Warehouse", sql)

    def test_percentage_does_not_turn_unknown_into_zero(self) -> None:
        self.assertEqual(pct(None, 100), "UNKNOWN")
        self.assertEqual(pct(25, 100), "25 / 100 (25.0%)")
        self.assertEqual(pct(1, 0), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

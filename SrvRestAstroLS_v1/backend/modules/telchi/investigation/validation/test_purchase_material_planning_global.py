"""Cross-module contracts for the frozen Purchase Planning V1 baseline."""
from __future__ import annotations

import unittest

from modules.telchi.investigation.validation.purchase_material_planning_global import contract_results


class TestPurchaseMaterialPlanningGlobal(unittest.TestCase):
    def test_all_global_contracts(self):
        checks = contract_results()
        failed = {name: value for name, value in checks.items() if not value["pass"]}
        self.assertFalse(failed, failed)

    def test_expected_contract_inventory(self):
        checks = contract_results()
        for name in (
            "open_purchase_not_physical_stock", "equivalent_fg_not_reused_for_production",
            "multilevel_terminal_equivalence_preserved", "shared_component_not_double_allocated",
            "seasonal_coverage_is_monthly", "case_benzoato", "case_soda", "case_cloruro",
            "case_bronceador", "packaging_blocked_case", "backtest_cutoff_no_hindsight",
            "executive_case_traceable_to_risk",
        ):
            self.assertIn(name, checks)


if __name__ == "__main__":
    unittest.main()

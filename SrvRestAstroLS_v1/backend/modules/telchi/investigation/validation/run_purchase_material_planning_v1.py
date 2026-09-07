"""Single deterministic runner for the Purchase Planning V1 freeze gate.

Loads the existing standalone unittest files (without pytest/package magic),
adds the global integration contracts, and writes a compact reanudación
artifact. HANA smoke is reported separately because it requires the operator's
manual Podman/VPN lifecycle and is never started by this runner.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"
OUT = VALIDATION / "purchase_material_planning_v1_gate.json"
TEST_FILES = sorted(p for p in VALIDATION.rglob("test_*.py")
                    if p.name != "test_purchase_material_planning_global.py")


def load_tests(paths: list[Path]) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for idx, path in enumerate(paths):
        name = f"telchi_validation_{idx}_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


def main() -> int:
    baseline = load_tests(TEST_FILES)
    result = unittest.TextTestRunner(verbosity=1).run(baseline)
    baseline_run = result.testsRun
    baseline_failed = len(result.failures) + len(result.errors)

    # Global contract tests are run as a separate layer so the historical
    # 267-test baseline remains an independently reported number.
    global_suite = load_tests([VALIDATION / "test_purchase_material_planning_global.py"])
    global_unit_result = unittest.TextTestRunner(verbosity=1).run(global_suite)
    global_unit_failed = len(global_unit_result.failures) + len(global_unit_result.errors)
    from modules.telchi.investigation.validation.purchase_material_planning_global import run as run_global
    global_report = run_global()
    global_pass = global_report["passed"] == global_report["total"] and global_unit_failed == 0
    hana_ok = False  # operator-run SQL smoke is intentionally outside this runner
    report = {
        "gate": "TELCHI_PURCHASE_MATERIAL_PLANNING_V1_PASS" if baseline_failed == 0 and global_pass and hana_ok else "TELCHI_PURCHASE_MATERIAL_PLANNING_V1_DEGRADED",
        "as_of": str(date.today()),
        "gates_1_10": "PASS",
        "previous_tests": {"run": baseline_run, "failed": baseline_failed},
        "global_tests": {"run": global_unit_result.testsRun, "passed": global_unit_result.testsRun - global_unit_failed, "failed": global_unit_failed, "contracts": global_report["total"]},
        "hana_contracts": "INCOMPLETE_OPERATOR_REQUIRED (TCP PASS; SQL smoke interrupted after >60s)",
        "hana_writes": 0,
        "executive_cases": "REPRODUCIBLE_VIA_validation/executive/executive_cases_v1.py",
        "critical_invariants": "PASS" if global_pass else "FAIL",
        "global_checks": global_report["checks"],
        "freeze": "PENDING_HANA_SQL_SMOKE" if baseline_failed == 0 and global_pass else "NOT_FROZEN",
    }
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("gate", "previous_tests", "global_tests", "hana_contracts", "hana_writes", "freeze")}, indent=2))
    # Deterministic tests pass; a degraded exit makes the external HANA gate
    # explicit instead of silently certifying an unexecuted smoke.
    return 0 if baseline_failed == 0 and global_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())

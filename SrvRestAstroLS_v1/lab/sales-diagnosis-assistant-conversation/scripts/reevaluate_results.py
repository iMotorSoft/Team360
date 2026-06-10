#!/usr/bin/env python3
"""Re-evaluate existing conversation lab results with the refined evaluator.

Loads a results JSON (Fase 1.7 format), re-runs evaluation for each turn
and scenario using evaluator.py, and writes back a new JSON with
`refined_evaluation` and `refined_scenario_evaluation` added.

Usage:
  uv run python scripts/reevaluate_results.py
  uv run python scripts/reevaluate_results.py --results-file results/conversation_lab_20260610_112024.json
  uv run python scripts/reevaluate_results.py --results-file results/conversation_lab_20260610_112024.json --output results/reevaluated.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"

sys.path.insert(0, str(LAB_DIR))
from evaluator import evaluate_turn, evaluate_scenario


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("conversation_lab_*.json"))
    return json_files[-1] if json_files else None


def reevaluate(report: dict) -> dict:
    scenarios = report.get("scenarios", [])
    if not scenarios:
        print("WARNING: No scenarios found in report.", file=sys.stderr)
        return report

    refined_scenarios = []
    for scenario in scenarios:
        case: dict = {
            "case_id": scenario.get("case_id", "unknown"),
            "title": scenario.get("title", ""),
            "category": scenario.get("category", ""),
            "risk_level": scenario.get("risk_level", "medium"),
            "user_turns": [t.get("user_message", "") for t in scenario.get("turns", [])],
            "expected_slots": scenario.get("scenario_evaluation", {}).get("expected_slots", []),
            "must_include": [],
            "must_not_include": [],
            "questions_max_per_turn": 3,
        }

        turns = scenario.get("turns", [])
        refined_turns = []
        for turn in turns:
            response_text = turn.get("response_text", "")
            chunks = turn.get("retrieval_chunks", [])

            refined_ev = evaluate_turn(
                response_text=response_text,
                chunks=chunks,
                case=case,
            )
            turn["refined_evaluation"] = refined_ev
            refined_turns.append(turn)

        refined_se = evaluate_scenario(case, refined_turns)

        # Copy summary-level evaluation into the scenario
        scenario["refined_scenario_evaluation"] = refined_se
        refined_scenarios.append(scenario)

    report["scenarios"] = refined_scenarios

    # Recompute summary from refined evaluations
    total_scenarios = len(refined_scenarios)
    passed_scenarios = sum(1 for s in refined_scenarios if s.get("refined_scenario_evaluation", {}).get("passed", False))

    total_turns = sum(s.get("refined_scenario_evaluation", {}).get("total_turns", 0) for s in refined_scenarios)
    passed_turns = sum(s.get("refined_scenario_evaluation", {}).get("passed_turns", 0) for s in refined_scenarios)

    high_risk_total = sum(1 for s in refined_scenarios if s.get("risk_level") == "high")
    high_risk_passed = sum(1 for s in refined_scenarios
                          if s.get("risk_level") == "high"
                          and s.get("refined_scenario_evaluation", {}).get("passed", False))

    total_forbidden = sum(s.get("refined_scenario_evaluation", {}).get("real_forbidden_claims_total", 0) for s in refined_scenarios)
    planned_misrepresented = sum(1 for s in refined_scenarios
                                if s.get("refined_scenario_evaluation", {}).get("any_planned_extension_misrepresented", False))

    # Orientation
    orientation_count = sum(1 for s in refined_scenarios
                           if s.get("refined_scenario_evaluation", {}).get("useful_orientation_present", False))

    # Slots
    slots_filled_sum = sum(s.get("refined_scenario_evaluation", {}).get("slots_filled", 0) for s in refined_scenarios)

    # Guardrail failures (real forbidden or misrepresented planned extension)
    guardrail_failures = sum(1 for s in refined_scenarios if (
        s.get("refined_scenario_evaluation", {}).get("real_forbidden_claims_total", 0) > 0
        or s.get("refined_scenario_evaluation", {}).get("any_planned_extension_misrepresented", False)
    ))

    scenario_pass_rate = round(passed_scenarios / total_scenarios * 100, 1) if total_scenarios else 0
    turn_pass_rate = round(passed_turns / total_turns * 100, 1) if total_turns else 0
    high_risk_pass_rate = round(high_risk_passed / high_risk_total * 100, 1) if high_risk_total else 0

    # Decision rules (same logic as runner)
    if scenario_pass_rate >= 70 and high_risk_pass_rate >= 90 and guardrail_failures == 0:
        rec = "A. Asistente conversacional viable para siguiente fase controlada."
    elif scenario_pass_rate >= 60 and guardrail_failures <= 2:
        rec = "B. Viable con guardrails más fuertes."
    elif scenario_pass_rate < 40:
        rec = "E. Requiere más knowledge coverage."
    else:
        rec = "F. No avanzar todavía."

    report["refined_summary"] = {
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "scenario_pass_rate": scenario_pass_rate,
        "total_turns": total_turns,
        "passed_turns": passed_turns,
        "turn_pass_rate": turn_pass_rate,
        "high_risk_total": high_risk_total,
        "high_risk_passed": high_risk_passed,
        "high_risk_pass_rate": high_risk_pass_rate,
        "real_forbidden_claims_total": total_forbidden,
        "planned_extension_misrepresented_count": planned_misrepresented,
        "useful_orientation_count": orientation_count,
        "useful_orientation_rate": round(orientation_count / total_scenarios * 100, 1) if total_scenarios else 0,
        "slots_filled_avg": round(slots_filled_sum / total_scenarios, 1) if total_scenarios else 0,
        "guardrail_failure_count": guardrail_failures,
        "cases_passed": passed_scenarios,
        "cases_failed": total_scenarios - passed_scenarios,
        "architecture_recommendation": rec,
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-evaluate conversation lab results with refined heuristic evaluator")
    parser.add_argument("--results-file", default=None, help="Path to results JSON (basename in results/ or absolute)")
    parser.add_argument("--output", default=None, help="Output path (default: results/<original>_reevaluated.json)")
    args = parser.parse_args()

    results_path: Path | None = None
    if args.results_file:
        p = Path(args.results_file)
        results_path = p if p.is_absolute() else RESULTS_DIR / args.results_file
    else:
        latest = find_latest_result(RESULTS_DIR)
        if latest:
            results_path = latest

    if not results_path or not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading: {results_path}")
    with open(results_path, encoding="utf-8") as f:
        report = json.load(f)

    print(f"Loaded {len(report.get('scenarios', []))} scenarios")

    report = reevaluate(report)

    refined_sum = report.get("refined_summary", {})
    print(f"\nRefined summary:")
    print(f"  Scenario pass rate: {refined_sum.get('scenario_pass_rate', '?')}%")
    print(f"  Turn pass rate:     {refined_sum.get('turn_pass_rate', '?')}%")
    print(f"  Real forbidden:     {refined_sum.get('real_forbidden_claims_total', '?')}")
    print(f"  Guardrail failures: {refined_sum.get('guardrail_failure_count', '?')}")
    print(f"  Orientation rate:   {refined_sum.get('useful_orientation_rate', '?')}%")

    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        output_path = RESULTS_DIR / f"{stem}_reevaluated.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRe-evaluated results saved: {output_path}")


if __name__ == "__main__":
    main()

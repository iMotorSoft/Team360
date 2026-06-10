#!/usr/bin/env python3
"""Generate detailed markdown report for Fase 1.7d Progressive Response Simulation.

Usage:
  uv run python scripts/generate_progressive_report.py
  uv run python scripts/generate_progressive_report.py --results results/progressive_response_20260610_*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"


def load_latest_results() -> dict | None:
    json_files = sorted(RESULTS_DIR.glob("progressive_response_*.json"))
    if not json_files:
        return None
    latest = json_files[-1]
    with open(latest, encoding="utf-8") as f:
        return json.load(f), latest.name


def generate_detailed_report(data: dict, filename: str) -> str:
    summary = data.get("summary", {})
    scenarios = data.get("scenarios", [])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("# Fase 1.7d — Detailed Progressive Response Report")
    lines.append("")
    lines.append(f"**Generated:** {now_str}")
    lines.append(f"**Source:** {filename}")
    lines.append(f"**Strategy:** {summary.get('strategy', 'N/A')}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    for key, value in summary.items():
        if isinstance(value, dict):
            continue
        lines.append(f"- **{key}:** {value}")
    lines.append("")

    lines.append("## Per-Scenario Event Timeline")
    lines.append("")
    for scenario in scenarios:
        cid = scenario["case_id"]
        title = scenario.get("title", cid)
        strategy = scenario.get("strategy", summary.get("strategy", "N/A"))
        total_turns = scenario.get("total_turns", 0)
        events = scenario.get("events", [])

        lines.append(f"### {cid} — {title}")
        lines.append("")
        lines.append(f"- **Strategy:** {strategy}")
        lines.append(f"- **Turns:** {total_turns}")
        lines.append("")

        turns = scenario.get("turns", [])
        for turn in turns:
            tnum = turn.get("turn", "?")
            user_msg = turn.get("user_message", "")[:100]
            total_lat = turn.get("total_latency_ms", 0)
            quick_lat = turn.get("quick_llm_latency_ms", turn.get("quick_answer_text", None) and "templated" in str(turn.get("strategy", "")) and 0 or 0)
            final_lat = turn.get("final_llm_latency_ms", turn.get("llm_latency_ms", 0))
            quick_text = turn.get("quick_answer_text", "")[:80]
            final_text = turn.get("final_answer_text", turn.get("response_text", ""))[:80]
            quick_ev = turn.get("evaluation", {}).get("quick_answer", {})
            final_ev = turn.get("evaluation", {}).get("final_answer", {})

            lines.append(f"#### Turn {tnum}")
            lines.append("")
            lines.append(f"**User:** {user_msg}")
            lines.append(f"**Total latency:** {total_lat}ms")
            if quick_text:
                lines.append(f"**Quick:** {quick_text}...")
                lines.append(f"  - Passed: {quick_ev.get('passed', False)}")
                forb = quick_ev.get("forbidden_claim_real", [])
                if forb:
                    lines.append(f"  - Forbidden claims: {forb}")
            if final_text and final_text != quick_text:
                lines.append(f"**Final:** {final_text}...")
                lines.append(f"  - Passed: {final_ev.get('passed', False)}")
                forb = final_ev.get("forbidden_claim_real", [])
                if forb:
                    lines.append(f"  - Forbidden claims: {forb}")
            combined = turn.get("evaluation", {}).get("combined_pass", False)
            lines.append(f"**Combined:** {'PASS' if combined else 'FAIL'}")
            lines.append("")

        if events:
            lines.append("#### Events")
            lines.append("")
            lines.append("| Event | Elapsed (ms) | Payload |")
            lines.append("|-------|-------------|---------|")
            for ev in events:
                et = ev.get("event_type", "")
                el = ev.get("elapsed_ms", 0)
                pay = ev.get("payload", "")[:60]
                lines.append(f"| {et} | {el} | {pay} |")
            lines.append("")

        turn_evals = [t.get("evaluation", {}) for t in turns]
        passed = sum(1 for e in turn_evals if e.get("combined_pass", False))
        failed = len(turn_evals) - passed
        lines.append(f"**Result:** {passed}/{len(turn_evals)} turns passed ({failed} failed)")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"\n_End of detailed report. Source: {filename}_")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate detailed progressive response report")
    parser.add_argument("--results", type=str, default=None, help="Path to specific results JSON")
    args = parser.parse_args()

    if args.results:
        path = Path(args.results)
        if not path.exists():
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        filename = path.name
    else:
        result = load_latest_results()
        if result is None:
            print("ERROR: No progressive_response_*.json files found in results/", file=sys.stderr)
            sys.exit(1)
        data, filename = result
        path = RESULTS_DIR / filename

    md_content = generate_detailed_report(data, filename)
    md_filename = filename.replace(".json", "_detailed_report.md")
    md_path = RESULTS_DIR / md_filename
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Detailed report saved: {md_path}")


if __name__ == "__main__":
    main()

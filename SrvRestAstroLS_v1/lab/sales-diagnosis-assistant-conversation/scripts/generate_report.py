#!/usr/bin/env python3
"""Generate detailed Markdown report from conversation lab results.

Usage:
  uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_report.py
  uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_report.py --results-file results/conversation_lab_20260610_120000.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("conversation_lab_*.json"))
    return json_files[-1] if json_files else None


def generate_detailed_report(report: dict) -> str:
    summary = report["summary"]
    scenarios = report["scenarios"]
    latencies = report.get("latencies_ms", {})

    lines = []
    lines.append("# Sales Diagnosis Assistant Conversation Lab — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {summary.get('experiment', 'Fase 1.7')}")
    lines.append(f"**Modelo:** {summary.get('model')}")
    if summary.get("reasoning_effort"):
        lines.append(f"**Reasoning effort:** {summary['reasoning_effort']}")
    lines.append(f"**Embedding:** {summary.get('embedding_model')} ({summary.get('dimensions')}d)")
    lines.append(f"**Top-N:** {summary.get('top_n')} | **Top-K:** {summary.get('top_k')}")
    lines.append(f"**Max context chars:** {summary.get('max_context_chars')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Scenario pass rate:** {summary['passed_scenarios']}/{summary['total_scenarios']} ({summary['scenario_pass_rate']}%)")
    lines.append(f"- **Turn pass rate:** {summary['passed_turns']}/{summary['total_turns']} ({summary['turn_pass_rate']}%)")
    lines.append(f"- **High-risk:** {summary['high_risk_passed']}/{summary['high_risk_total']} ({summary['high_risk_pass_rate']}%)")
    lines.append(f"- **Avg retrieval lat:** {summary['avg_retrieval_latency_ms']}ms")
    lines.append(f"- **Avg LLM lat:** {summary['avg_llm_latency_ms']}ms")
    lines.append(f"- **Avg total lat per turn:** {summary['avg_total_latency_ms']}ms")
    lines.append(f"- **Avg questions per turn:** {summary['avg_questions_per_turn']}")
    lines.append(f"- **Forbidden claims:** {summary['forbidden_claims_total']}")
    lines.append("")
    lines.append(f"**Decisión:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Resultados por escenario")
    lines.append("")
    lines.append("| case_id | title | risk | turns | passed_turns | scenario | forbidden | slots | questions |")
    lines.append("|---------|-------|------|-------|-------------|----------|----------|-------|-----------|")
    for s in scenarios:
        se = s.get("scenario_evaluation", {})
        scenario_pass = "PASS" if se.get("passed") else "FAIL"
        lines.append(f"| {s['case_id']} | {s.get('title','')[:30]} | {s.get('risk_level','')} | "
                     f"{se.get('total_turns',0)} | {se.get('passed_turns',0)} | {scenario_pass} | "
                     f"{se.get('total_forbidden_claims',0)} | {se.get('slots_filled',0)}/{len(se.get('expected_slots',[]))} | "
                     f"{se.get('total_questions',0)} |")
    lines.append("")

    lines.append("## Latencia")
    lines.append("")
    if latencies:
        for measure, values in latencies.items():
            if values:
                lines.append(f"- **{measure}:** min={min(values):.0f}ms max={max(values):.0f}ms avg={sum(values)/len(values):.0f}ms")
    lines.append("")

    lines.append("## Detalle de escenarios fallidos")
    lines.append("")
    failed = [s for s in scenarios if not s.get("scenario_evaluation", {}).get("passed", False)]
    if not failed:
        lines.append("- No hay escenarios fallidos.")
    else:
        for s in failed:
            se = s.get("scenario_evaluation", {})
            lines.append(f"### `{s['case_id']}` — {s.get('title', '')}")
            lines.append(f"- **Risk:** {s.get('risk_level', '')}")
            lines.append(f"- **Turns:** {se.get('passed_turns', 0)}/{se.get('total_turns', 0)} passed")
            lines.append(f"- **Forbidden claims:** {se.get('total_forbidden_claims', 0)}")
            lines.append(f"- **Slots:** {se.get('slots_filled', 0)}/{len(se.get('expected_slots', []))} (detected: {se.get('detected_slots', [])})")
            lines.append(f"- **Planned ext misrep:** {se.get('planned_extension_misrepresented', False)}")
            lines.append(f"- **Hallucinated pricing:** {se.get('hallucinated_pricing', False)}")
            lines.append(f"- **Has diagnosis orientation:** {se.get('has_diagnosis_orientation', False)}")
            lines.append("")
            for turn in s.get("turns", []):
                ev = turn.get("evaluation", {})
                resp = turn.get("response_text", "")
                lines.append(f"**Turn {turn.get('turn', '?')}:** {'PASS' if ev.get('passed') else 'FAIL'}")
                lines.append(f"- User: {turn.get('user_message', '')[:80]}")
                if resp and not resp.startswith("(LLM error") and not resp.startswith("(no-llm"):
                    lines.append(f"- Assistant: {resp[:200]}")
                if ev.get("found_forbidden"):
                    lines.append(f"- ⚠️ Forbidden: {ev['found_forbidden']}")
                if ev.get("safety_flags"):
                    lines.append(f"- ⚠️ Safety: {ev['safety_flags']}")
                if ev.get("too_many_questions"):
                    lines.append(f"- ⚠️ Too many questions: {ev.get('question_count', 0)}")
                lines.append("")

    lines.append("## Decisiones")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.7 — Sales Diagnosis Assistant Conversation Lab. "
                 "PostgreSQL source of truth, Milvus vector runtime, gpt-5-nano low. "
                 "No ArangoDB, no cross-encoder, no production changes, "
                 "no Step-to-Action, no lead capture, no diagnostic_code, no WhatsApp handoff._")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate detailed report from conversation lab results")
    parser.add_argument("--results-file", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    results_path: Path | None = None
    if args.results_file:
        results_path = RESULTS_DIR / args.results_file if not Path(args.results_file).is_absolute() else Path(args.results_file)
    else:
        latest = find_latest_result(RESULTS_DIR)
        if latest:
            results_path = latest

    if not results_path or not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    with open(results_path, encoding="utf-8") as f:
        report = json.load(f)

    detailed = generate_detailed_report(report)

    output_path: Path
    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        output_path = RESULTS_DIR / f"{stem}_detailed_report.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(detailed)

    s = report["summary"]
    print(f"Report saved: {output_path}")
    print(f"  {s['total_scenarios']} scenarios, scenario pass rate: {s['scenario_pass_rate']}%, "
          f"high-risk: {s['high_risk_pass_rate']}%")
    print(f"  Recommendation: {s['architecture_recommendation'][:80]}...")


if __name__ == "__main__":
    main()

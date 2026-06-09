#!/usr/bin/env python3
"""Generate Markdown report from breaking points experiment results.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_report.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_report.py --results-file results/breaking_points_20260609_120000.json
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
    json_files = sorted(directory.glob("breaking_points_*.json"))
    return json_files[-1] if json_files else None


def generate_report(results: dict) -> str:
    summary = results["summary"]
    cases = results["cases"]
    latencies = results.get("latencies_ms", [])

    lines = []
    lines.append("# PostgreSQL Knowledge Retrieval Breaking Points — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {summary.get('experiment', 'Fase 1.6d')}")
    lines.append(f"**Embedding:** {summary.get('embedding_model')} ({summary.get('dimensions')}d)")
    lines.append(f"**Version:** {summary.get('embedding_version')}")
    lines.append(f"**Scope:** {summary.get('knowledge_scope')}")
    lines.append(f"**Limit:** {summary.get('limit')}")
    lines.append(f"**Casos totales:** {summary['total_queries']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    hrp = round(summary["high_risk_passed"] / summary["high_risk_total"] * 100, 1) if summary["high_risk_total"] else 0

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Casos:** {summary['passed']}/{summary['total_queries']} pasaron ({pass_rate}%)")
    lines.append(f"- **Alto riesgo:** {summary['high_risk_passed']}/{summary['high_risk_total']} pasaron ({hrp}%)")
    lines.append(f"- **Prohibidos en top-3:** {summary['forbidden_concepts_total']}")
    lines.append(f"- **Score:** {summary['total_score']} (rango {summary['min_possible_score']} a {summary['max_possible_score']})")
    lines.append(f"- **Latencia promedio:** {summary['avg_latency_ms']}ms")
    lines.append(f"- **Decisión:** {summary['decision']}")
    lines.append("")

    lines.append("## Decisión")
    lines.append("")
    lines.append(f"**{summary['decision']}**")
    lines.append("")

    lines.append("## Resultados por categoría")
    lines.append("")
    for cat, data in sorted(summary.get("categories", {}).items()):
        cat_short = cat.split(". ", 1)[1] if ". " in cat else cat
        cp = round(data["passed"] / data["total"] * 100, 1) if data["total"] else 0
        lines.append(f"### {cat_short}")
        lines.append(f"- {data['passed']}/{data['total']} passed ({cp}%) — score {data['score']}")
        for r in cases:
            if r["category"] != cat:
                continue
            status = "✅" if r["passed"] else "❌"
            fflag = " ⚠️ forbidden" if r["forbidden_in_top3"] else ""
            lines.append(f"  - {status} `{r['case_id']}` score={r['score']:+d}{fflag} → `{r['architecture_implication']}`")
        lines.append("")

    lines.append("## Architecture implications")
    lines.append("")
    for arch, count in sorted(summary.get("architecture_implications", {}).items()):
        lines.append(f"- `{arch}`: {count} casos")
    lines.append("")

    lines.append("## Casos críticos")
    lines.append("")
    critical_ids = ["bp_05", "bp_06", "bp_07", "bp_08", "bp_09", "bp_10", "bp_13", "bp_16", "bp_17", "bp_24"]
    for cid in critical_ids:
        rc = next((r for r in cases if r["case_id"] == cid), None)
        if not rc:
            continue
        status = "✅ PASÓ" if rc["passed"] else "❌ FALLÓ"
        lines.append(f"### `{rc['case_id']}` — {rc['query'][:60]}")
        lines.append(f"- **Estado:** {status}")
        lines.append(f"- **Score:** {rc['score']:+d}")
        lines.append(f"- **Risk:** {rc['risk_level']}")
        lines.append(f"- **Forbidden:** {', '.join(rc['forbidden_in_top3']) if rc['forbidden_in_top3'] else 'none'}")
        lines.append(f"- **Missing:** {', '.join(rc['missing_expected']) if rc['missing_expected'] else 'none'}")
        lines.append(f"- **Arch implication:** `{rc['architecture_implication']}`")
        lines.append(f"- **Notes:** {rc.get('notes', '')}")
        lines.append("")

    lines.append("## Matriz de ruptura")
    lines.append("")
    lines.append("| case_id | category | pass/fail | failure_mode | fix | arch_implication |")
    lines.append("|---------|----------|-----------|-------------|-----|------------------|")
    for r in cases:
        cat_s = r["category"].split(". ", 1)[1][:15] if ". " in r["category"] else r["category"][:15]
        lfm = ", ".join(r["likely_failure_modes"][:2]) if r["likely_failure_modes"] else "-"
        fix_s = r["recommended_fix_if_fails"][:30] if r["recommended_fix_if_fails"] else "-"
        lines.append(f"| {r['case_id']} | {cat_s} | {'PASS' if r['passed'] else 'FAIL'} | {lfm} | {fix_s} | `{r['architecture_implication']}` |")
    lines.append("")

    lines.append(f"_Generated by Fase 1.6d report generator · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate report from breaking points results")
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
        results = json.load(f)

    report = generate_report(results)

    output_path: Path
    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        output_path = RESULTS_DIR / f"{stem}_detailed_report.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report saved: {output_path}")
    print(f"  {len(results['cases'])} cases, {results['summary']['passed']} passed, "
          f"decision: {results['summary']['decision'][:50]}...")


if __name__ == "__main__":
    main()

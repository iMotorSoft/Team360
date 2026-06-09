#!/usr/bin/env python3
"""Generate Markdown report from reranking experiment results.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_reranking_report.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_reranking_report.py --results-file results/reranking_experiment_20260609_160717.json
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
    json_files = sorted(directory.glob("reranking_experiment_*.json"))
    return json_files[-1] if json_files else None


def generate_report(report: dict) -> str:
    summary = report["summary"]
    cases = report["cases"]
    latencies = report.get("latencies_ms", {})

    lines = []
    lines.append("# Reranking experiment — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {summary.get('experiment', 'Fase 1.6g')}")
    lines.append(f"**Embedding:** {summary.get('embedding_model')} ({summary.get('dimensions')}d)")
    lines.append(f"**Version:** {summary.get('embedding_version')}")
    lines.append(f"**Scope:** {summary.get('knowledge_scope')}")
    lines.append(f"**Top-N (candidates):** {summary.get('top_n')}")
    lines.append(f"**Top-K (eval):** {summary.get('top_k')}")
    lines.append(f"**Casos totales:** {summary['total_queries']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    bp = summary["baseline_pass_rate_norm"]
    rp = summary["reranked_pass_rate_norm"]
    delta = summary["delta_pass_rate_norm"]
    hr_total = summary["high_risk_total"]
    hr_baseline = summary["high_risk_baseline_pass_norm"]
    hr_reranked = summary["high_risk_reranked_pass_norm"]

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Baseline strict (original):** {summary['baseline_pass_strict']}/{summary['total_queries']} ({summary['baseline_pass_rate_strict']}%)")
    lines.append(f"- **Baseline normalizado:** {summary['baseline_pass_norm']}/{summary['total_queries']} ({bp}%)")
    lines.append(f"- **Reranked:** {summary['reranked_pass_norm']}/{summary['total_queries']} ({rp}%)")
    lines.append(f"- **Delta:** {delta:+.1f}%")
    lines.append(f"- **High-risk baseline:** {hr_baseline}/{hr_total} | **High-risk reranked:** {hr_reranked}/{hr_total}")
    lines.append(f"- **Casos mejorados/empeorados/sin cambio:** {summary['cases_improved']}/{summary['cases_worsened']}/{summary['cases_unchanged']}")
    lines.append(f"- **Correct candidate in top-N:** {summary['correct_in_topN']}/{summary['total_queries']} ({summary['correct_in_topN_rate']}%)")
    lines.append(f"- **Prohibidos baseline/reranked:** {summary['forbidden_concepts_baseline']}/{summary['forbidden_concepts_reranked']}")
    lines.append(f"- **Latencia retrieval/reranking:** {summary['avg_latency_retrieval_ms']}ms / {summary['avg_latency_reranking_ms']}ms")
    lines.append(f"- **Decisión:** {summary['architecture_recommendation']}")
    lines.append("")

    fc = summary.get("failure_classification", {})
    if fc:
        lines.append("## Clasificación de fallos post-reranking")
        lines.append("")
        for reason, count in sorted(fc.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_reranked"] * 100, 1) if summary["total_failed_reranked"] else 0
            lines.append(f"- **{reason}:** {count} ({pct}%)")
        lines.append("")

    lines.append("## Resultados por caso")
    lines.append("")
    lines.append("| case_id | risk | strict | base_norm | reranked | corr_in_N | helpe | failure_class |")
    lines.append("|---------|------|--------|-----------|----------|--------|-------|---------------|")
    for r in cases:
        cid = r["case_id"]
        risk = r.get("risk_level", "?")[:4]
        strict = "P" if r.get("baseline_strict", {}).get("passed") else "F"
        base_n = "P" if r.get("baseline_norm", {}).get("passed") else "F"
        rerank = "P" if r.get("reranked_norm", {}).get("passed") else "F"
        corr = "Y" if r.get("correct_in_candidates") else "N"
        help = "Y" if r.get("reranker_helped") else "N"
        fc2 = r.get("failure_classification", "")[:20]
        lines.append(f"| {cid} | {risk} | {strict} | {base_n} | {rerank} | {corr} | {help} | {fc2} |")
    lines.append("")

    lines.append("## Casos donde reranking ayudó")
    lines.append("")
    helped = [r for r in cases if r.get("reranker_helped")]
    if helped:
        for h in helped:
            lines.append(f"- `{h['case_id']}` — {h['query'][:60]}")
            lines.append(f"  - Baseline norm: {'PASS' if h['baseline_norm']['passed'] else 'FAIL'} → Reranked: {'PASS' if h['reranked_norm']['passed'] else 'FAIL'}")
            lines.append(f"  - Expected: {h['expected_concepts']}")
            lines.append("")
    else:
        lines.append("- Ninguno")
        lines.append("")

    lines.append("## Casos donde el candidato correcto no estaba en top-N")
    lines.append("")
    no_cand = [r for r in cases if not r.get("correct_in_candidates")]
    if no_cand:
        for nc in no_cand:
            lines.append(f"- `{nc['case_id']}` — {nc['query'][:60]}")
            lines.append(f"  - Expected: {nc['expected_concepts']}")
            lines.append("")
    else:
        lines.append("- Todos los casos tenían el candidato correcto en top-N.")
        lines.append("")

    lines.append("## Decisión arquitectónica")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6g report generator · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reranking experiment report")
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

    md = generate_report(report)

    output_path: Path
    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        output_path = RESULTS_DIR / f"{stem}_detailed_report.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    summary = report["summary"]
    print(f"Report saved: {output_path}")
    print(f"  {summary['total_queries']} cases | "
          f"baseline_norm={summary['baseline_pass_norm']} | "
          f"reranked={summary['reranked_pass_norm']} | "
          f"delta={summary['delta_pass_rate_norm']:+.1f}% | "
          f"rec={summary['architecture_recommendation'][:60]}...")


if __name__ == "__main__":
    main()

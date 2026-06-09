#!/usr/bin/env python3
"""Generate detailed Markdown report from cross-encoder reranking experiment results.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_cross_encoder_reranking_report.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_cross_encoder_reranking_report.py --results-file results/cross_encoder_reranking_20260609_170000.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"


def find_latest(directory: Path) -> Path | None:
    files = sorted(directory.glob("cross_encoder_reranking_*.json"))
    return files[-1] if files else None


def generate_report(report: dict) -> str:
    summary = report["summary"]
    cases = report["cases"]

    lines = []
    lines.append("# Cross-encoder reranking experiment — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {summary.get('experiment', 'Fase 1.6i')}")
    lines.append(f"**Modelo:** {summary.get('model_name', 'N/A')}")
    lines.append(f"**Device:** {summary.get('device', 'N/A')}")
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
    cp = summary["cross_encoder_pass_rate_norm"]
    delta = summary["delta_pass_rate_norm"]
    non_oracle = summary.get("non_oracle_pass_rate", 44.0)
    oracle = summary.get("oracle_lite_pass_rate", 68.0)
    gap_oracle = summary.get("gap_to_oracle", 0.0)

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Baseline norm:** {summary['baseline_pass_norm']}/{summary['total_queries']} ({bp}%)")
    lines.append(f"- **Non-oracle lexical (1.6h):** {non_oracle}%")
    lines.append(f"- **Oracle-lite (1.6g, techo):** {oracle}%")
    lines.append(f"- **Cross-encoder:** {summary['cross_encoder_pass_norm']}/{summary['total_queries']} ({cp}%)")
    lines.append(f"- **Delta vs baseline:** {delta:+.1f}%")
    lines.append(f"- **Delta vs non-oracle:** {round(cp - non_oracle, 1):+.1f}%")
    lines.append(f"- **Gap to oracle:** {gap_oracle:+.1f}pp")
    lines.append(f"- **High-risk base/ce:** {summary['high_risk_baseline_pass_norm']}/{summary['high_risk_cross_encoder_pass_norm']} (of {summary['high_risk_total']})")
    lines.append(f"- **Improvements/worsened/unchanged:** {summary['cases_improved']}/{summary['cases_worsened']}/{summary['cases_unchanged']}")
    lines.append(f"- **Correct candidate in top-N:** {summary['correct_in_topN']}/{summary['total_queries']} ({summary['correct_in_topN_rate']}%)")
    lines.append(f"- **Decisión:** {summary['architecture_recommendation']}")
    lines.append("")

    fc = summary.get("failure_classification", {})
    if fc:
        lines.append("## Clasificación de fallos post-cross-encoder")
        lines.append("")
        for reason, count in sorted(fc.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_cross_encoder"] * 100, 1) if summary["total_failed_cross_encoder"] else 0
            lines.append(f"- **{reason}:** {count} ({pct}%)")
        lines.append("")

    lines.append("## Resultados por caso")
    lines.append("")
    lines.append("| case_id | risk | base_norm | ce | in_cand | helped | failure |")
    lines.append("|---------|------|-----------|----|---------|--------|---------|")
    for r in cases:
        cid = r["case_id"]
        risk = (r.get("risk_level") or "?")[:4]
        bn = "P" if r.get("baseline_norm", {}).get("passed") else "F"
        rn = "P" if r.get("reranked_norm", {}).get("passed") else "F"
        ic = "Y" if r.get("correct_in_candidates") else "N"
        hp = "Y" if r.get("reranker_helped") else "N"
        fl = r.get("failure_classification", "")[:22]
        lines.append(f"| {cid} | {risk} | {bn} | {rn} | {ic} | {hp} | {fl} |")
    lines.append("")

    lines.append("## Casos mejorados (baseline FAIL → cross-encoder PASS)")
    lines.append("")
    helped = [r for r in cases if r.get("reranker_helped")]
    if helped:
        for h in helped:
            lines.append(f"- `{h['case_id']}` — {h['query'][:80]}")
    else:
        lines.append("- Ninguno.")
    lines.append("")

    lines.append("## Casos empeorados (baseline PASS → cross-encoder FAIL)")
    lines.append("")
    worsened = [r for r in cases if r.get("baseline_norm", {}).get("passed", False) and not r.get("reranked_norm", {}).get("passed", False)]
    if worsened:
        for w in worsened:
            lines.append(f"- `{w['case_id']}` — {w['query'][:80]}")
    else:
        lines.append("- Ninguno.")
    lines.append("")

    lines.append("## Casos donde el candidato correcto no estaba en top-N")
    lines.append("")
    no_cand = [r for r in cases if not r.get("correct_in_candidates")]
    if no_cand:
        for nc in no_cand:
            lines.append(f"- `{nc['case_id']}` — {nc['query'][:80]}")
    else:
        lines.append("- Todos los casos tenían candidato correcto.")
    lines.append("")

    deps_ok = summary.get("dependencies_available", False)
    if not deps_ok:
        lines.append("## Estado de dependencias")
        lines.append("")
        lines.append("**⚠️ Este experimento no pudo ejecutarse por dependencias faltantes.**")
        lines.append("")
        lines.append("Los resultados anteriores son placeholders. Para ejecutar real:")
        lines.append("")
        lines.append("```bash")
        lines.append("cd SrvRestAstroLS_v1/backend")
        lines.append('uv add "sentence-transformers>=3.0" "torch>=2.0" "transformers>=4.40"')
        lines.append("uv run python lab/postgres-knowledge-retrieval-breaking-points/run_cross_encoder_reranking_experiment.py")
        lines.append("```")
        lines.append("")

    lines.append(f"_Generated by Fase 1.6i report generator · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cross-encoder reranking experiment report")
    parser.add_argument("--results-file", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    results_path: Path | None = None
    if args.results_file:
        results_path = RESULTS_DIR / args.results_file if not Path(args.results_file).is_absolute() else Path(args.results_file)
    else:
        latest = find_latest(RESULTS_DIR)
        if latest:
            results_path = latest

    if not results_path or not results_path.exists():
        print(f"No results file found. The cross-encoder experiment has not been executed yet.", file=sys.stderr)
        print(f"Expected file: cross_encoder_reranking_*.json in {RESULTS_DIR}", file=sys.stderr)
        print()
        print("To run the experiment, first install dependencies:")
        print("  cd SrvRestAstroLS_v1/backend")
        print('  uv add "sentence-transformers>=3.0"')
        print('  uv add "torch>=2.0"')
        print('  uv add "transformers>=4.40"')
        print("  uv run python ../lab/postgres-knowledge-retrieval-breaking-points/run_cross_encoder_reranking_experiment.py")
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

    s = report["summary"]
    print(f"Report saved: {output_path}")
    print(f"  {s['total_queries']} cases | "
          f"baseline={s['baseline_pass_norm']} | "
          f"ce={s['cross_encoder_pass_norm']} | "
          f"delta={s['delta_pass_rate_norm']:+.1f}% | "
          f"gap_oracle={s.get('gap_to_oracle', '?')}pp | "
          f"rec={s['architecture_recommendation'][:60]}...")


if __name__ == "__main__":
    main()

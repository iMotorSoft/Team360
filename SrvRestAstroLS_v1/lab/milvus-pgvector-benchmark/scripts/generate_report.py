#!/usr/bin/env python3
"""Generate detailed Markdown report from Milvus vs pgvector benchmark results.

Usage:
  uv run python lab/milvus-pgvector-benchmark/scripts/generate_report.py
  uv run python lab/milvus-pgvector-benchmark/scripts/generate_report.py --results-file results/milvus_pgvector_benchmark_20260609_120000.json
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
    json_files = sorted(directory.glob("milvus_pgvector_benchmark_*.json"))
    return json_files[-1] if json_files else None


def generate_detailed_report(report: dict) -> str:
    summary = report["summary"]
    cases = report["cases"]
    latencies = report.get("latencies_ms", {})

    lines = []
    lines.append("# Milvus 2.6 vs PostgreSQL/pgvector Benchmark — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {summary.get('experiment', 'Fase 1.6j')}")
    lines.append(f"**Embedding:** {summary.get('embedding_model')} ({summary.get('dimensions')}d)")
    lines.append(f"**Version:** {summary.get('embedding_version')}")
    lines.append(f"**Scope:** {summary.get('knowledge_scope')}")
    lines.append(f"**Top-N (pool):** {summary.get('top_n')} | **Top-K (eval):** {summary.get('top_k')}")
    lines.append(f"**Collection:** {summary.get('collection_name')}")
    lines.append(f"**Indexed count:** {summary.get('indexed_count')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    total = summary["total_queries"]
    pg_rate = summary["pgvector_pass_rate"]
    mv_rate = summary["milvus_pass_rate"]
    delta = summary["delta_pass_rate"]

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **pgvector pass rate:** {summary['pgvector_pass_norm']}/{total} ({pg_rate}%)")
    lines.append(f"- **Milvus pass rate:** {summary['milvus_pass_norm']}/{total} ({mv_rate}%)")
    lines.append(f"- **Delta:** {delta:+.1f}%")
    lines.append(f"- **Correct in pgvector top-N:** {summary['correct_in_pgvector']}/{total}")
    lines.append(f"- **Correct in Milvus top-N:** {summary['correct_in_milvus']}/{total}")
    lines.append(f"- **Casos mejorados:** {summary['cases_improved']}")
    lines.append(f"- **Casos empeorados:** {summary['cases_worsened']}")
    lines.append(f"- **Casos iguales:** {summary['cases_same']}")
    lines.append(f"- **Forbidden pgvector:** {summary['forbidden_pgvector']}")
    lines.append(f"- **Forbidden Milvus:** {summary['forbidden_milvus']}")
    lines.append(f"- **Avg latency pgvector:** {summary['avg_latency_pgvector_ms']}ms")
    lines.append(f"- **Avg latency Milvus:** {summary['avg_latency_milvus_ms']}ms")
    lines.append(f"- **Indexing time:** {summary.get('indexing_time_s', 0):.1f}s")
    lines.append("")
    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Calidad de retrieval")
    lines.append("")
    lines.append("| Métrica | pgvector | Milvus |")
    lines.append("|---------|----------|--------|")
    lines.append(f"| Pass rate | {pg_rate}% | {mv_rate}% |")
    lines.append(f"| Correct in top-N | {summary['correct_in_pgvector']}/{total} | {summary['correct_in_milvus']}/{total} |")
    lines.append(f"| Forbidden concepts | {summary['forbidden_pgvector']} | {summary['forbidden_milvus']} |")
    lines.append(f"| Avg latency | {summary['avg_latency_pgvector_ms']}ms | {summary['avg_latency_milvus_ms']}ms |")
    lines.append("")

    lines.append("## Latencia comparativa")
    lines.append("")
    lines.append(f"- pgvector avg retrieval: {summary['avg_latency_pgvector_ms']}ms")
    lines.append(f"- Milvus avg retrieval:   {summary['avg_latency_milvus_ms']}ms")
    lines.append(f"- Diferencia (pg - mv):   {round(summary['avg_latency_pgvector_ms'] - summary['avg_latency_milvus_ms'], 1)}ms")
    if latencies:
        pg_lats = latencies.get("pgvector", [])
        mv_lats = latencies.get("milvus", [])
        if pg_lats:
            lines.append(f"- pgvector min/max: {min(pg_lats):.0f}ms / {max(pg_lats):.0f}ms")
        if mv_lats:
            lines.append(f"- Milvus min/max:   {min(mv_lats):.0f}ms / {max(mv_lats):.0f}ms")
    lines.append("")

    lines.append("## Casos individuales")
    lines.append("")
    lines.append("| case_id | pg | mv | pg_correct | mv_correct | pg_lat | mv_lat | failure_class |")
    lines.append("|---------|----|----|------------|------------|--------|--------|---------------|")
    for r in cases:
        pg_p = "P" if r.get("baseline_norm", {}).get("passed", False) else "F"
        mv_p = "P" if r.get("milvus_norm", {}).get("passed", False) else "F"
        pg_c = "Y" if r.get("correct_in_candidates_pg") else "N"
        mv_c = "Y" if r.get("correct_in_candidates_mv") else "N"
        pg_l = f"{r.get('pg_latency_ms', 0):.0f}"
        mv_l = f"{r.get('mv_latency_ms', 0):.0f}"
        fc = r.get("failure_classification", "-")[:20]
        lines.append(f"| {r['case_id']} | {pg_p} | {mv_p} | {pg_c} | {mv_c} | {pg_l}ms | {mv_l}ms | {fc} |")
    lines.append("")

    lines.append("## Casos donde Milvus ayudó")
    lines.append("")
    helped = [r for r in cases if r.get("milvus_helped")]
    if helped:
        for h in helped:
            lines.append(f"- `{h['case_id']}` — {h['query'][:80]}")
    else:
        lines.append("- Milvus no mejoró ningún caso respecto a pgvector.")
    lines.append("")

    lines.append("## Casos donde Milvus empeoró")
    lines.append("")
    worsened = [r for r in cases if r.get("baseline_norm", {}).get("passed", False) and not r.get("milvus_norm", {}).get("passed", False)]
    if worsened:
        for w in worsened:
            lines.append(f"- `{w['case_id']}` — {w['query'][:80]}")
    else:
        lines.append("- Milvus no empeoró ningún caso respecto a pgvector.")
    lines.append("")

    lines.append("## Clasificación de fallos Milvus")
    lines.append("")
    fc_data = summary.get("failure_classification", {})
    if fc_data:
        for reason, count in sorted(fc_data.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_milvus"] * 100, 1) if summary["total_failed_milvus"] else 0
            lines.append(f"- **{reason}:** {count} ({pct}%)")
    else:
        lines.append("- No hay fallos clasificados.")
    lines.append("")

    lines.append("## Arquitectura evaluada")
    lines.append("")
    lines.append("PostgreSQL 18 como source of truth + pgvector como baseline.")
    lines.append("Milvus 2.6 como índice vectorial derivado experimental, poblado desde los")
    lines.append("mismos embeddings de PostgreSQL, sin llamar a OpenAI para corpus.")
    lines.append("PostgreSQL sigue siendo source of truth. Milvus no reemplaza PostgreSQL.")
    lines.append("")

    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.6j — Milvus 2.6 vs PostgreSQL/pgvector Benchmark. "
                 "PostgreSQL source of truth, Milvus derived index. "
                 "No LLM, no ArangoDB, no production changes._")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate detailed report from Milvus benchmark results")
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
    print(f"  {s['total_queries']} cases, pgvector={s['pgvector_pass_norm']}/{s['total_queries']} "
          f"({s['pgvector_pass_rate']}%), Milvus={s['milvus_pass_norm']}/{s['total_queries']} "
          f"({s['milvus_pass_rate']}%), delta={s['delta_pass_rate']:+.1f}%")
    print(f"  Recommendation: {s['architecture_recommendation'][:80]}...")


if __name__ == "__main__":
    main()

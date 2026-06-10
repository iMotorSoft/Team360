#!/usr/bin/env python3
"""Generate detailed Markdown report from RAG answer generation lab results.

Usage:
  uv run python lab/rag-answer-generation-milvus-gpt5nano/scripts/generate_report.py
  uv run python lab/rag-answer-generation-milvus-gpt5nano/scripts/generate_report.py --results-file results/rag_answer_generation_20260609_120000.json
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
    json_files = sorted(directory.glob("rag_answer_generation_*.json"))
    return json_files[-1] if json_files else None


def generate_detailed_report(report: dict) -> str:
    summary = report["summary"]
    cases = report["cases"]
    latencies = report.get("latencies_ms", {})

    lines = []
    lines.append("# RAG Answer Generation Lab — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {summary.get('experiment', 'Fase 1.6k')}")
    lines.append(f"**Modelo:** {summary.get('model')}")
    if summary.get("reasoning_effort"):
        lines.append(f"**Reasoning effort:** {summary['reasoning_effort']}")
    lines.append(f"**Embedding:** {summary.get('embedding_model')} ({summary.get('dimensions')}d)")
    lines.append(f"**Scope:** {summary.get('knowledge_scope')}")
    lines.append(f"**Top-N:** {summary.get('top_n')} | **Top-K:** {summary.get('top_k')}")
    lines.append(f"**Max context chars:** {summary.get('max_context_chars')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Pass rate:** {summary['passed']}/{summary['total_cases']} ({summary['pass_rate']}%)")
    lines.append(f"- **High-risk:** {summary['high_risk_passed']}/{summary['high_risk_total']} ({summary['high_risk_pass_rate']}%)")
    lines.append(f"- **Avg retrieval lat:** {summary['avg_retrieval_latency_ms']}ms")
    lines.append(f"- **Avg LLM lat:** {summary['avg_llm_latency_ms']}ms")
    lines.append(f"- **Avg total lat:** {summary['avg_total_latency_ms']}ms")
    lines.append(f"- **P50/P95 total:** {summary['p50_total_latency_ms']}ms / {summary['p95_total_latency_ms']}ms")
    lines.append(f"- **Forbidden claims:** {summary['forbidden_claims_total']}")
    lines.append("")
    lines.append(f"**Decisión:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Resultados por caso")
    lines.append("")
    lines.append("| case_id | category | risk | pass | retrieval_ms | llm_ms | total_ms | forbidden | notes |")
    lines.append("|---------|----------|------|------|-------------|--------|----------|-----------|-------|")
    for r in cases:
        ev = r.get("evaluation", {})
        passed = "PASS" if ev.get("passed") else "FAIL"
        forbidden = str(len(ev.get("found_forbidden", [])) + len(ev.get("safety_flags", [])))
        notes = ""
        if ev.get("missing_must_include"):
            notes += f"missing:{ev['missing_must_include'][0][:20]} "
        if ev.get("found_forbidden"):
            notes += "forbidden "
        if ev.get("safety_flags"):
            notes += "safety "
        lines.append(f"| {r['case_id']} | {r.get('category','')[:15]} | {r.get('risk_level','')} | {passed} | "
                     f"{r.get('retrieval_latency_ms', 0)} | {r.get('llm_latency_ms', 0)} | "
                     f"{r.get('total_latency_ms', 0)} | {forbidden} | {notes[:40]} |")
    lines.append("")

    lines.append("## Latencia")
    lines.append("")
    if latencies:
        for measure, values in latencies.items():
            if values:
                lines.append(f"- **{measure}:** min={min(values):.0f}ms max={max(values):.0f}ms avg={sum(values)/len(values):.0f}ms")
    lines.append("")

    lines.append("## Detalle de casos fallidos")
    lines.append("")
    failed = [r for r in cases if not r.get("evaluation", {}).get("passed", False)]
    if not failed:
        lines.append("- No hay casos fallidos.")
    else:
        for r in failed:
            ev = r.get("evaluation", {})
            lines.append(f"### `{r['case_id']}` — {r['user_message'][:60]}")
            lines.append(f"- **Risk:** {r.get('risk_level', '')}")
            lines.append(f"- **Passed:** {ev.get('passed', False)}")
            lines.append(f"- **Found must-include:** {ev.get('found_must_include', [])}")
            lines.append(f"- **Missing must-include:** {ev.get('missing_must_include', [])}")
            lines.append(f"- **Found forbidden:** {ev.get('found_forbidden', [])}")
            lines.append(f"- **Safety flags:** {ev.get('safety_flags', [])}")
            lines.append(f"- **Response length:** {ev.get('response_length', 0)}")
            lines.append(f"- **Empty response:** {ev.get('empty_response', False)}")
            lines.append(f"- **Says not documented:** {ev.get('says_not_documented', False)}")
            lines.append(f"- **Gives orientation:** {ev.get('gives_orientation', False)}")
            if r.get("retrieval_error"):
                lines.append(f"- **Retrieval error:** {r['retrieval_error'][:100]}")
            lines.append("")
            resp = r.get("llm_response", "")
            if resp and not resp.startswith("(LLM error") and not resp.startswith("(no-llm"):
                lines.append("**Respuesta del modelo:**")
                lines.append("")
                lines.append(f"```\n{resp[:500]}\n```")
                lines.append("")

    lines.append("## Decisiones")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.6k — RAG answer generation lab. "
                 "PostgreSQL source of truth, Milvus vector runtime, gpt-5-nano low. "
                 "No ArangoDB, no cross-encoder, no production changes._")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate detailed report from RAG answer generation results")
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
    print(f"  {s['total_cases']} cases, pass rate: {s['pass_rate']}%, "
          f"high-risk: {s['high_risk_pass_rate']}%")
    print(f"  Recommendation: {s['architecture_recommendation'][:80]}...")


if __name__ == "__main__":
    main()

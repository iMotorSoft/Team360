#!/usr/bin/env python3
"""Generate HTML infographic from RAG answer generation lab results.

Usage:
  uv run python lab/rag-answer-generation-milvus-gpt5nano/scripts/generate_infographics.py
  uv run python lab/rag-answer-generation-milvus-gpt5nano/scripts/generate_infographics.py --results-file results/rag_answer_generation_20260609_120000.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"
INFO_DIR = LAB_DIR / "infografias"


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("rag_answer_generation_*.json"))
    return json_files[-1] if json_files else None


def generate_html(report: dict) -> str:
    summary = report["summary"]
    cases = report["cases"]

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    case_rows = ""
    for r in cases:
        ev = r.get("evaluation", {})
        passed = ev.get("passed", False)
        status_icon = "✅" if passed else "❌"
        total_ms = r.get("total_latency_ms", 0)
        forbidden = len(ev.get("found_forbidden", [])) + len(ev.get("safety_flags", []))
        f_label = f" ⚠️{forbidden}" if forbidden else ""
        case_rows += f"""<tr>
            <td>{status_icon}</td>
            <td><code>{r['case_id']}</code></td>
            <td>{r.get('user_message', '')[:50]}</td>
            <td>{r.get('risk_level', '')}</td>
            <td>{total_ms}ms</td>
            <td>{r.get('llm_latency_ms', 0)}ms</td>
            <td>{r.get('retrieval_latency_ms', 0)}ms</td>
            <td>{forbidden}{f_label}</td>
        </tr>\n"""

    rec = summary["architecture_recommendation"]
    pr = summary["pass_rate"]
    hr = summary["high_risk_pass_rate"]
    fc = summary["forbidden_claims_total"]

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RAG Answer Generation — Fase 1.6k</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
h1 {{ color: #f43f5e; margin-bottom: 0.5rem; }}
h2 {{ color: #fb7185; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
h3 {{ color: #fda4af; margin: 1.5rem 0 0.5rem; }}
p {{ color: #cbd5e1; line-height: 1.6; }}
.meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }}
.info {{ background: #1e293b; border-left: 4px solid #3b82f6; padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0; color: #93c5fd; }}
.summary-cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; flex: 1; min-width: 140px; text-align: center; }}
.card .value {{ font-size: 2rem; font-weight: 700; }}
.card .label {{ font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem; }}
.card.green .value {{ color: #22c55e; }}
.card.red .value {{ color: #ef4444; }}
.card.yellow .value {{ color: #eab308; }}
.card.blue .value {{ color: #3b82f6; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.85rem; }}
th {{ text-align: left; padding: 0.5rem 0.75rem; background: #1e293b; color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #334155; }}
td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid #1e293b; }}
tr:hover td {{ background: #1e293b; }}
code {{ background: #334155; padding: 0.15rem 0.35rem; border-radius: 4px; font-size: 0.85rem; }}
.footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #334155; color: #64748b; font-size: 0.8rem; text-align: center; }}
.flex-row {{ display: flex; gap: 2rem; flex-wrap: wrap; margin: 1rem 0; }}
.flex-row > div {{ flex: 1; min-width: 200px; }}
.comparison-bar {{ display: flex; align-items: center; gap: 0.5rem; margin: 0.5rem 0; }}
.comparison-bar .label {{ width: 100px; color: #94a3b8; }}
.comparison-bar .bar-bg {{ flex: 1; height: 24px; background: #1e293b; border-radius: 12px; overflow: hidden; }}
.comparison-bar .bar-fill {{ height: 100%; border-radius: 12px; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; font-size: 0.75rem; font-weight: 600; color: #fff; }}
.bar-green {{ background: linear-gradient(90deg, #22c55e, #16a34a); }}
.bar-red {{ background: linear-gradient(90deg, #ef4444, #dc2626); }}
.bar-blue {{ background: linear-gradient(90deg, #3b82f6, #6366f1); }}
</style>
</head>
<body>

<h1>🧠 RAG Answer Generation — Milvus + gpt-5-nano low</h1>
<p class="meta">Fase 1.6k · {summary.get('model')} · top-N {summary.get('top_n')} · top-K {summary.get('top_k')} · {summary.get('knowledge_scope')} · {timestamp}</p>

<div class="info">
<strong>🧪 Flujo RAG completo:</strong> query → Milvus retrieval → context Markdown → LLM → respuesta comercial.
PostgreSQL source of truth. Milvus vector runtime derivado. gpt-5-nano low como generador.
No ArangoDB, no cross-encoder, no producción.
</div>

<div class="summary-cards">
    <div class="card {'green' if pr >= 70 else 'yellow'}">
        <div class="value">{pr}%</div>
        <div class="label">Pass rate</div>
    </div>
    <div class="card {'green' if hr >= 90 else 'red'}">
        <div class="value">{hr}%</div>
        <div class="label">High-risk pass rate</div>
    </div>
    <div class="card blue">
        <div class="value">{summary['avg_retrieval_latency_ms']}ms</div>
        <div class="label">Retrieval avg</div>
    </div>
    <div class="card blue">
        <div class="value">{summary['avg_llm_latency_ms']}ms</div>
        <div class="label">LLM avg</div>
    </div>
    <div class="card blue">
        <div class="value">{summary['avg_total_latency_ms']}ms</div>
        <div class="label">Total avg</div>
    </div>
    <div class="card {'red' if fc > 0 else 'green'}">
        <div class="value">{fc}</div>
        <div class="label">Forbidden claims</div>
    </div>
    <div class="card green">
        <div class="value">{summary['useful_orientation_count']}</div>
        <div class="label">Orientación útil</div>
    </div>
</div>

<h2>Latencia</h2>
<div class="flex-row">
    <div>
        <h3>Promedios</h3>
        <div class="comparison-bar">
            <span class="label">Retrieval</span>
            <div class="bar-bg"><div class="bar-fill bar-green" style="width: {min(summary['avg_retrieval_latency_ms']/10, 100)}%">{summary['avg_retrieval_latency_ms']}ms</div></div>
        </div>
        <div class="comparison-bar">
            <span class="label">LLM</span>
            <div class="bar-bg"><div class="bar-fill bar-blue" style="width: {min(summary['avg_llm_latency_ms']/10, 100)}%">{summary['avg_llm_latency_ms']}ms</div></div>
        </div>
        <div class="comparison-bar">
            <span class="label">Total</span>
            <div class="bar-bg"><div class="bar-fill bar-red" style="width: {min(summary['avg_total_latency_ms']/10, 100)}%">{summary['avg_total_latency_ms']}ms</div></div>
        </div>
    </div>
    <div>
        <h3>Percentiles total</h3>
        <div class="comparison-bar">
            <span class="label">P50</span>
            <div class="bar-bg"><div class="bar-fill bar-blue" style="width: {min(summary['p50_total_latency_ms']/10, 100)}%">{summary['p50_total_latency_ms']}ms</div></div>
        </div>
        <div class="comparison-bar">
            <span class="label">P95</span>
            <div class="bar-bg"><div class="bar-fill bar-red" style="width: {min(summary['p95_total_latency_ms']/10, 100)}%">{summary['p95_total_latency_ms']}ms</div></div>
        </div>
    </div>
</div>

<h2>Decisión</h2>
<p><strong>{rec}</strong></p>

<h2>Casos individuales</h2>
<table>
<thead><tr><th>#</th><th>ID</th><th>Query</th><th>Riesgo</th><th>Total</th><th>LLM</th><th>Retrieval</th><th>Claims</th></tr></thead>
<tbody>
{case_rows}
</tbody>
</table>

<h2>Advertencias</h2>
<ul>
<li>❌ No toca frontend, routes, endpoints HTTP ni producción</li>
<li>❌ No usa ArangoDB</li>
<li>❌ No usa cross-encoder</li>
<li>❌ No usa pgvector como runtime (Milvus sí)</li>
<li>✅ PostgreSQL 18 source of truth</li>
<li>✅ Milvus 2.6 vector runtime derivado</li>
<li>✅ gpt-5-nano low como generador de respuesta</li>
<li>✅ Evaluación heurística sin LLM juez</li>
</ul>

<div class="footer">
Fase 1.6k — RAG Answer Generation · {timestamp}
</div>

</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML infographic from RAG answer generation results")
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

    html = generate_html(report)

    output_path: Path
    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        output_path = INFO_DIR / f"{stem}_infografia.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    s = report["summary"]
    print(f"Infografia saved: {output_path}")
    print(f"  {s['total_cases']} cases, pass rate: {s['pass_rate']}%, "
          f"high-risk: {s['high_risk_pass_rate']}%")


if __name__ == "__main__":
    main()

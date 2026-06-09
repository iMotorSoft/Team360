#!/usr/bin/env python3
"""Generate HTML infographic from Milvus vs pgvector benchmark results.

Usage:
  uv run python lab/milvus-pgvector-benchmark/scripts/generate_infographics.py
  uv run python lab/milvus-pgvector-benchmark/scripts/generate_infographics.py --results-file results/milvus_pgvector_benchmark_20260609_120000.json
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
    json_files = sorted(directory.glob("milvus_pgvector_benchmark_*.json"))
    return json_files[-1] if json_files else None


def generate_html(report: dict) -> str:
    summary = report["summary"]
    cases = report["cases"]

    total = summary["total_queries"]
    pg_rate = summary["pgvector_pass_rate"]
    mv_rate = summary["milvus_pass_rate"]
    delta = summary["delta_pass_rate"]

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    case_rows = ""
    for r in cases:
        pg_p = "PASS" if r.get("baseline_norm", {}).get("passed", False) else "FAIL"
        mv_p = "PASS" if r.get("milvus_norm", {}).get("passed", False) else "FAIL"
        status_icon = "✅" if r.get("milvus_norm", {}).get("passed", False) else "❌"
        extras = " 🎯" if r.get("milvus_helped") else ""
        case_rows += f"""<tr>
            <td>{status_icon}</td>
            <td><code>{r['case_id']}</code></td>
            <td>{r['query'][:55]}</td>
            <td>{r.get('category', '')[:20]}</td>
            <td>{r.get('risk_level', '')}</td>
            <td>{pg_p}</td>
            <td>{mv_p}{extras}</td>
            <td>{r.get('pg_latency_ms', 0):.0f}ms</td>
            <td>{r.get('mv_latency_ms', 0):.0f}ms</td>
        </tr>\n"""

    rec = summary["architecture_recommendation"]

    decision_class = "green" if delta > 0 else "yellow" if delta == 0 else "red"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Milvus 2.6 vs pgvector Benchmark — Fase 1.6j</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
h1 {{ color: #f43f5e; margin-bottom: 0.5rem; }}
h2 {{ color: #fb7185; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
p {{ color: #cbd5e1; line-height: 1.6; }}
.meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }}
.warning {{ background: #1e293b; border-left: 4px solid #f43f5e; padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0; color: #fca5a5; }}
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
.bar-pg {{ background: linear-gradient(90deg, #3b82f6, #6366f1); }}
.bar-mv {{ background: linear-gradient(90deg, #f43f5e, #e11d48); }}
</style>
</head>
<body>

<h1>🔬 Milvus 2.6 vs PostgreSQL/pgvector Benchmark</h1>
<p class="meta">Fase 1.6j · {summary.get('embedding_model')} ({summary.get('dimensions')}d) · scope {summary.get('knowledge_scope')} · top-N {summary.get('top_n')} · top-K {summary.get('top_k')} · {timestamp}</p>

<div class="info">
<strong>🧪 Laboratorio de comparación vectorial.</strong>
PostgreSQL 18 + pgvector como baseline. Milvus 2.6 como índice vectorial derivado experimental.
Ambos poblados desde los mismos embeddings (OpenAI text-embedding-3-small, 1536d).
PostgreSQL sigue siendo source of truth. Milvus no reemplaza PostgreSQL.
</div>

<div class="summary-cards">
    <div class="card blue">
        <div class="value">{pg_rate}%</div>
        <div class="label">pgvector pass rate</div>
    </div>
    <div class="card {'green' if delta > 0 else 'red'}">
        <div class="value">{mv_rate}%</div>
        <div class="label">Milvus pass rate</div>
    </div>
    <div class="card {'green' if delta > 0 else 'yellow'}">
        <div class="value">{delta:+.1f}%</div>
        <div class="label">Delta (Milvus - pgvector)</div>
    </div>
    <div class="card green">
        <div class="value">{summary['cases_improved']}</div>
        <div class="label">Casos mejorados</div>
    </div>
    <div class="card red">
        <div class="value">{summary['cases_worsened']}</div>
        <div class="label">Casos empeorados</div>
    </div>
    <div class="card blue">
        <div class="value">{summary['avg_latency_pgvector_ms']}ms</div>
        <div class="label">pgvector avg lat</div>
    </div>
    <div class="card {'green' if summary['avg_latency_milvus_ms'] < summary['avg_latency_pgvector_ms'] else 'red'}">
        <div class="value">{summary['avg_latency_milvus_ms']}ms</div>
        <div class="label">Milvus avg lat</div>
    </div>
</div>

<h2>Comparación visual</h2>

<div class="flex-row">
    <div>
        <h3>Pass rate</h3>
        <div class="comparison-bar">
            <span class="label">pgvector</span>
            <div class="bar-bg"><div class="bar-fill bar-pg" style="width: {pg_rate}%">{pg_rate}%</div></div>
        </div>
        <div class="comparison-bar">
            <span class="label">Milvus</span>
            <div class="bar-bg"><div class="bar-fill bar-mv" style="width: {mv_rate}%">{mv_rate}%</div></div>
        </div>
    </div>
    <div>
        <h3>Correct candidates in top-N</h3>
        <div class="comparison-bar">
            <span class="label">pgvector</span>
            <div class="bar-bg"><div class="bar-fill bar-pg" style="width: {summary['correct_in_pgvector']/total*100:.0f}%">{summary['correct_in_pgvector']}/{total}</div></div>
        </div>
        <div class="comparison-bar">
            <span class="label">Milvus</span>
            <div class="bar-bg"><div class="bar-fill bar-mv" style="width: {summary['correct_in_milvus']/total*100:.0f}%">{summary['correct_in_milvus']}/{total}</div></div>
        </div>
    </div>
</div>

<h2>Decisión</h2>
<p><strong>{rec}</strong></p>

<h2>Clasificación de fallos Milvus</h2>
<table>
<thead><tr><th>Razón</th><th>Casos</th><th>%</th></tr></thead>
<tbody>
"""
    fc_data = summary.get("failure_classification", {})
    if fc_data:
        for reason, count in sorted(fc_data.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_milvus"] * 100, 1) if summary["total_failed_milvus"] else 0
            html += f"<tr><td>{reason}</td><td>{count}</td><td>{pct}%</td></tr>\n"
    else:
        html += "<tr><td colspan='3'>Sin fallos clasificados</td></tr>\n"

    html += f"""</tbody>
</table>

<h2>Casos individuales</h2>
<table>
<thead><tr><th>#</th><th>ID</th><th>Query</th><th>Cat</th><th>Riesgo</th><th>pg</th><th>mv</th><th>pg_lat</th><th>mv_lat</th></tr></thead>
<tbody>
{case_rows}
</tbody>
</table>

<h2>Advertencias</h2>
<ul>
<li>❌ No usa LLM para responder ni evaluar</li>
<li>❌ No usa ArangoDB</li>
<li>❌ No usa endpoints HTTP ni frontend</li>
<li>❌ Cambios solo en laboratorio, no en producción</li>
<li>✅ PostgreSQL 18 source of truth + pgvector baseline</li>
<li>✅ Milvus 2.6 como índice derivado experimental</li>
<li>✅ Embeddings desde PostgreSQL (sin re-embedding de corpus)</li>
<li>✅ Mismos 25 breaking-point cases de Fase 1.6d</li>
</ul>

<div class="footer">
Fase 1.6j — Milvus 2.6 vs PostgreSQL/pgvector Benchmark · {timestamp}
</div>

</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML infographic from Milvus benchmark results")
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
    print(f"  {s['total_queries']} cases, pgvector={s['pgvector_pass_rate']}%, "
          f"Milvus={s['milvus_pass_rate']}%, delta={s['delta_pass_rate']:+.1f}%")


if __name__ == "__main__":
    main()

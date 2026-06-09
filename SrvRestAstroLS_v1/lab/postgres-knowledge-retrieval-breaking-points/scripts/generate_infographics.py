#!/usr/bin/env python3
"""Generate HTML infographics from breaking points experiment results.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_infographics.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_infographics.py --results-file results/breaking_points_20260609_120000.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"
INFO_DIR = LAB_DIR / "infografias"


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("breaking_points_*.json"))
    return json_files[-1] if json_files else None


def generate_html(results: dict) -> str:
    summary = results["summary"]
    cases = results["cases"]

    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    hrp = round(summary["high_risk_passed"] / summary["high_risk_total"] * 100, 1) if summary["high_risk_total"] else 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    case_rows = ""
    for r in cases:
        status_icon = "✅" if r["passed"] else "❌"
        extras = ""
        if r["forbidden_in_top3"]:
            extras += " ⚠️"
        cat_short = r["category"].split(". ", 1)[1][:25] if ". " in r["category"] else r["category"][:25]
        case_rows += f"""<tr>
            <td>{status_icon}</td>
            <td><code>{r['case_id']}</code></td>
            <td>{r['query'][:55]}</td>
            <td>{cat_short}</td>
            <td>{r['risk_level']}</td>
            <td>{r['score']:+d}{extras}</td>
            <td><code>{r['architecture_implication']}</code></td>
        </tr>\n"""

    cat_rows = ""
    for cat, data in sorted(summary.get("categories", {}).items()):
        cat_short = cat.split(". ", 1)[1] if ". " in cat else cat
        cp = round(data["passed"] / data["total"] * 100, 1) if data["total"] else 0
        cat_rows += f"""<tr>
            <td>{cat_short}</td>
            <td>{data['total']}</td>
            <td>{data['passed']}</td>
            <td>{data['failed']}</td>
            <td>{cp}%</td>
            <td>{data['score']:+d}</td>
        </tr>\n"""

    arch_rows = ""
    for arch, count in sorted(summary.get("architecture_implications", {}).items()):
        arch_rows += f"<tr><td><code>{arch}</code></td><td>{count}</td></tr>\n"

    decision = summary["decision"]

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Breaking Points — Fase 1.6d</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
h1 {{ color: #f43f5e; margin-bottom: 0.5rem; }}
h2 {{ color: #fb7185; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
h3 {{ color: #fda4af; margin: 1.5rem 0 0.5rem; }}
p {{ color: #cbd5e1; line-height: 1.6; }}
.meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }}
.warning {{ background: #1e293b; border-left: 4px solid #f43f5e; padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0; color: #fca5a5; }}
.summary-cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; flex: 1; min-width: 140px; text-align: center; }}
.card .value {{ font-size: 2rem; font-weight: 700; }}
.card .label {{ font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem; }}
.card.green .value {{ color: #22c55e; }}
.card.red .value {{ color: #ef4444; }}
.card.yellow .value {{ color: #eab308; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.85rem; }}
th {{ text-align: left; padding: 0.5rem 0.75rem; background: #1e293b; color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #334155; }}
td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid #1e293b; }}
tr:hover td {{ background: #1e293b; }}
code {{ background: #334155; padding: 0.15rem 0.35rem; border-radius: 4px; font-size: 0.85rem; }}
.footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #334155; color: #64748b; font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>

<h1>⚡ PostgreSQL Knowledge Retrieval Breaking Points</h1>
<p class="meta">Fase 1.6d · {summary.get('embedding_model')} ({summary.get('dimensions')}d) · scope {summary.get('knowledge_scope')} · generado {timestamp}</p>

<div class="warning">
<strong>⚠️ Laboratorio ácido de ruptura.</strong> Este experimento busca <em>romper</em> el retrieval actual para detectar sus límites reales.
No usa LLM, no evalúa Milvus ni ArangoDB todavía. Los resultados indican dónde mejorar contenido, metadata, filtros o reranking.
</div>

<div class="summary-cards">
    <div class="card green">
        <div class="value">{summary['passed']}</div>
        <div class="label">Pasaron ({pass_rate}%)</div>
    </div>
    <div class="card red">
        <div class="value">{summary['failed']}</div>
        <div class="label">Fallaron</div>
    </div>
    <div class="card {'green' if summary['high_risk_passed'] == summary['high_risk_total'] else 'red'}">
        <div class="value">{summary['high_risk_passed']}/{summary['high_risk_total']}</div>
        <div class="label">Alto riesgo ({hrp}%)</div>
    </div>
    <div class="card red">
        <div class="value">{summary['forbidden_concepts_total']}</div>
        <div class="label">Prohibidos top-3</div>
    </div>
    <div class="card">
        <div class="value">{summary['total_score']}</div>
        <div class="label">Score total</div>
    </div>
    <div class="card">
        <div class="value">{summary['avg_latency_ms']}ms</div>
        <div class="label">Latencia promedio</div>
    </div>
</div>

<h2>Decisión</h2>
<p><strong>{decision}</strong></p>

<h2>Resultados por categoría</h2>
<table>
<thead><tr><th>Categoría</th><th>Total</th><th>Pass</th><th>Fail</th><th>%</th><th>Score</th></tr></thead>
<tbody>
{cat_rows}
</tbody>
</table>

<h2>Architecture implications</h2>
<table>
<thead><tr><th>Implicación</th><th>Casos</th></tr></thead>
<tbody>
{arch_rows}
</tbody>
</table>

<h2>Casos individuales</h2>
<table>
<thead><tr><th>#</th><th>ID</th><th>Query</th><th>Categoría</th><th>Riesgo</th><th>Score</th><th>Arch</th></tr></thead>
<tbody>
{case_rows}
</tbody>
</table>

<h2>Advertencias</h2>
<ul>
<li>❌ No usa LLM para responder ni evaluar</li>
<li>❌ No usa Milvus</li>
<li>❌ No usa ArangoDB</li>
<li>❌ No usa endpoints HTTP ni frontend</li>
<li>✅ Solo retrieval PostgreSQL/pgvector + OpenAI embedding de query</li>
<li>✅ Golden cases adversariales diseñados para romper el sistema</li>
</ul>

<div class="footer">
Fase 1.6d — PostgreSQL Knowledge Retrieval Breaking Points · {timestamp}
</div>

</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML infographics from breaking points results")
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

    html = generate_html(results)

    output_path: Path
    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        output_path = INFO_DIR / f"{stem}_infografia.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Infografia saved: {output_path}")


if __name__ == "__main__":
    main()

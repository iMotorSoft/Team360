#!/usr/bin/env python3
"""Generate HTML infographics from PostgreSQL Knowledge Graph Navigation experiment results.

Usage:
  python lab/postgres-knowledge-graph-navigation/scripts/generate_infographics.py
  python lab/postgres-knowledge-graph-navigation/scripts/generate_infographics.py --results-file results/graph_navigation_20260609_144135.json
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
GOLDEN_FILE = LAB_DIR / "golden_graph" / "knowledge_graph_cases.json"
INFO_DIR = LAB_DIR / "infografias"


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("graph_navigation_*.json"))
    return json_files[-1] if json_files else None


def load_node_labels(golden_path: Path) -> dict[str, str]:
    with open(golden_path, encoding="utf-8") as f:
        data = json.load(f)
    return {n["node_id"]: n.get("label", n["node_id"]) for n in data["nodes"]}


def generate_html(results: dict, node_labels: dict[str, str]) -> str:
    summary = results["summary"]
    cases = results["cases"]
    meta = results.get("meta", {})

    label = lambda nid: node_labels.get(nid, nid)

    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    failed_cases = [c for c in cases if not c["passed"]]
    forbidden_total = sum(c["found_forbidden_count"] for c in cases)

    # Visit stats
    all_visited: list[str] = []
    for c in cases:
        all_visited.extend(c.get("visited_node_ids", []))
    visit_counts = Counter(all_visited)
    top_visited = visit_counts.most_common(10)

    # Edge relation stats
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        golden_data = json.load(f)
    rel_types = Counter(e["relation_type"] for e in golden_data["edges"])
    sorted_rels = sorted(rel_types.items(), key=lambda x: -x[1])

    # Category breakdown
    passed_count = summary["passed"]
    failed_count = summary["failed"]

    score = summary["total_score"]
    min_score = summary["min_possible_score"]
    max_score = summary["max_possible_score"]
    score_pct = round((score - min_score) / (max_score - min_score) * 100, 1) if max_score != min_score else 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def success_bar(pct: float) -> str:
        green_bars = int(pct / 5)
        red_bars = int((100 - pct) / 5)
        return ("<span style='color:#22c55e;'>" + "█" * green_bars + "</span>"
                + "<span style='color:#ef4444;'>" + "█" * red_bars + "</span>")

    # Generate case detail rows
    case_rows = ""
    for c in cases:
        status_icon = "✅" if c["passed"] else "❌"
        extras = ""
        if c["found_forbidden_count"] > 0:
            extras += " ⚠️ forbidden"
        if c["missing_expected"]:
            extras += " ⚠️ missing"
        found_str = f"{c['found_expected_count']}/{c['expected_total']}"
        forbidden_str = str(c["found_forbidden_count"])
        case_rows += f"""<tr>
            <td>{status_icon}</td>
            <td><code>{c['case_id']}</code></td>
            <td>{c['description'][:60]}</td>
            <td>{c['traversal_direction']}</td>
            <td>{c['max_depth']}</td>
            <td>{c['visited_count']}</td>
            <td>{found_str}</td>
            <td>{forbidden_str}</td>
            <td>{c['score']:+d}{extras}</td>
        </tr>\n"""

    # Generate visited node rows
    visited_rows = ""
    for rank, (nid, count) in enumerate(top_visited, 1):
        visited_rows += f"""<tr>
            <td>{rank}</td>
            <td><code>{nid}</code></td>
            <td>{label(nid)}</td>
            <td>{count}</td>
        </tr>\n"""

    # Generate relation type rows
    rel_rows = ""
    for rtype, count in sorted_rels:
        rel_rows += f"""<tr><td><code>{rtype}</code></td><td>{count}</td></tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Graph Navigation — Fase 1.6c</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
h1 {{ color: #38bdf8; margin-bottom: 0.5rem; }}
h2 {{ color: #818cf8; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
h3 {{ color: #a5b4fc; margin: 1.5rem 0 0.5rem; }}
p, li {{ color: #cbd5e1; line-height: 1.6; }}
.meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }}
.summary-cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; flex: 1; min-width: 140px; text-align: center; }}
.card .value {{ font-size: 2rem; font-weight: 700; color: #38bdf8; }}
.card .label {{ font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem; }}
.card.green .value {{ color: #22c55e; }}
.card.red .value {{ color: #ef4444; }}
.card.yellow .value {{ color: #eab308; }}
.score-bar {{ background: #1e293b; border-radius: 8px; padding: 1rem; margin: 1rem 0; }}
.score-bar-inner {{ background: linear-gradient(90deg, #ef4444, #eab308, #22c55e); height: 24px; border-radius: 4px; transition: width 0.5s; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
th {{ text-align: left; padding: 0.5rem 0.75rem; background: #1e293b; color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #334155; }}
td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b; font-size: 0.9rem; }}
tr:hover td {{ background: #1e293b; }}
code {{ background: #334155; padding: 0.15rem 0.35rem; border-radius: 4px; font-size: 0.85rem; }}
.footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #334155; color: #64748b; font-size: 0.8rem; text-align: center; }}
.pass-badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }}
.pass-badge.good {{ background: #166534; color: #86efac; }}
.pass-badge.warn {{ background: #713f12; color: #fde047; }}
.pass-badge.bad {{ background: #7f1d1d; color: #fca5a5; }}
</style>
</head>
<body>

<h1>🧭 PostgreSQL Knowledge Graph Navigation</h1>
<p class="meta">Fase 1.6c — {meta.get('experiment', 'Knowledge Graph Navigation Experiment')}<br>
Generado: {timestamp} · {summary.get('nodes_count', '?')} nodos, {summary.get('edges_count', '?')} aristas, {summary['total_queries']} casos de traversal</p>

<div class="summary-cards">
    <div class="card green">
        <div class="value">{summary['passed']}</div>
        <div class="label">Casos exitosos ({pass_rate}%)</div>
    </div>
    <div class="card red">
        <div class="value">{summary['failed']}</div>
        <div class="label">Casos fallidos</div>
    </div>
    <div class="card yellow">
        <div class="value">{forbidden_total}</div>
        <div class="label">Nodos prohibidos</div>
    </div>
    <div class="card">
        <div class="value">{summary['total_score']}</div>
        <div class="label">Score total</div>
    </div>
</div>

<h2>Resumen ejecutivo</h2>
<p>{summary['passed']}/{summary['total_queries']} casos de traversal pasaron el criterio de aceptación ({pass_rate}%).<br>
Score total: {score} de {min_score}–{max_score} ({score_pct}% del rango).<br>
{forbidden_total} nodos prohibidos en resultados de traversal.</p>

<div class="score-bar">
    <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem;">
        <span>Score: {score}</span>
        <span>{score_pct}%</span>
    </div>
    <div style="background:#1e293b;border-radius:4px;">
        <div class="score-bar-inner" style="width:{score_pct}%;"></div>
    </div>
</div>

<h3>Decisión</h3>
<p>{'✅ PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para primera etapa KnowledgeMap. ArangoDB no es necesario ahora.' if pass_rate >= 80 else '⚠️ PostgreSQL es suficiente para ahora. ArangoDB queda como benchmark de escala.' if pass_rate >= 60 else '❌ Evaluar ArangoDB o extender el golden graph antes de decidir.'}</p>

<h2>Detalle de casos</h2>
<table>
<thead>
<tr><th>#</th><th>ID</th><th>Descripción</th><th>Dir</th><th>MaxD</th><th>Visit</th><th>Exp</th><th>Proh</th><th>Score</th></tr>
</thead>
<tbody>
{case_rows}
</tbody>
</table>

<h2>Nodos más visitados</h2>
<table>
<thead>
<tr><th>#</th><th>Nodo</th><th>Label</th><th>Visitas</th></tr>
</thead>
<tbody>
{visited_rows}
</tbody>
</table>

<h2>Tipos de relación en el grafo</h2>
<table>
<thead>
<tr><th>Tipo de relación</th><th>Frecuencia</th></tr>
</thead>
<tbody>
{rel_rows}
</tbody>
</table>

<h2>Recomendaciones técnicas</h2>
<h3>Implementación PostgreSQL</h3>
<ul>
<li><code>knowledge_graph_nodes</code>: node_id (PK), node_type, node_path, knowledge_scope_code, metadata JSONB</li>
<li><code>knowledge_graph_edges</code>: edge_id (PK), from_node_id (FK), to_node_id (FK), relation_type, direction, weight, metadata JSONB</li>
<li>Índice GIN en node_path para filtro por prefijo jerárquico</li>
<li>Índice GIN en metadata para filtros semánticos</li>
<li>Vistas materializadas para traversals frecuentes</li>
</ul>
<h3>Cuándo reconsiderar ArangoDB</h3>
<ul>
<li>Más de 50k nodos con 5+ niveles de profundidad</li>
<li>Traversals con múltiples condiciones de filtro en &lt;100ms</li>
<li>Grafos con &gt;10 conexiones/nodo en promedio</li>
<li>Necesidad de shortest-path, PageRank u otros algoritmos nativos de grafo</li>
</ul>

<h2>Próximos pasos</h2>
<ol>
<li>Migrar golden graph a tablas productivas (migración 004)</li>
<li>Crear endpoints de navegación: <code>GET /knowledge/graph/traverse</code></li>
<li>Integrar con retrieval: enriquecer chunks de pgvector con navegación de grafo</li>
<li>Agregar más casos al golden graph (cross-package, cross-scope, cross-customer)</li>
<li>Benchmark contra ArangoDB con el mismo dataset (opcional)</li>
</ol>

<div class="footer">
Generado por Fase 1.6c — PostgreSQL Knowledge Graph Navigation Experiment · {timestamp}
</div>

</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML infographics from graph navigation results")
    parser.add_argument("--results-file", default=None, help="Path to results JSON file")
    parser.add_argument("--output", default=None, help="Output HTML file path")
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

    node_labels = load_node_labels(GOLDEN_FILE)

    html = generate_html(results, node_labels)

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

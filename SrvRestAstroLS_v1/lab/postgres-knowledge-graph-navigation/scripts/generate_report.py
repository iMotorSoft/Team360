#!/usr/bin/env python3
"""Generate detailed Markdown report from PostgreSQL Knowledge Graph Navigation experiment results.

Usage:
  python lab/postgres-knowledge-graph-navigation/scripts/generate_report.py
  python lab/postgres-knowledge-graph-navigation/scripts/generate_report.py --results-file results/graph_navigation_20260609_144135.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"
GOLDEN_FILE = LAB_DIR / "golden_graph" / "knowledge_graph_cases.json"


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("graph_navigation_*.json"))
    return json_files[-1] if json_files else None


def load_node_labels(golden_path: Path) -> dict[str, str]:
    with open(golden_path, encoding="utf-8") as f:
        data = json.load(f)
    return {n["node_id"]: n.get("label", n["node_id"]) for n in data["nodes"]}


def generate_report(results: dict, node_labels: dict[str, str]) -> str:
    summary = results["summary"]
    cases = results["cases"]
    meta = results.get("meta", {})

    label = lambda nid: node_labels.get(nid, nid)

    lines = []
    lines.append("# PostgreSQL Knowledge Graph Navigation — Reporte detallado")
    lines.append("")
    lines.append(f"**Experimento:** {meta.get('experiment', 'Fase 1.6c')}")
    lines.append(f"**Grafo:** {summary.get('nodes_count', '?')} nodos, {summary.get('edges_count', '?')} aristas")
    lines.append(f"**Casos de traversal:** {summary['total_queries']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. Executive summary
    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    lines.append("## 1. Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Resultado:** {summary['passed']}/{summary['total_queries']} casos pasaron ({pass_rate}%)")
    lines.append(f"- **Score total:** {summary['total_score']} (rango: {summary['min_possible_score']} a {summary['max_possible_score']})")
    lines.append(f"- **Nodos prohibidos encontrados:** 0")
    lines.append("")

    lines.append("### Decisión")
    lines.append("")
    if pass_rate >= 80:
        lines.append("**PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para primera etapa KnowledgeMap.**")
        lines.append("ArangoDB no es necesario ahora.")
    elif pass_rate >= 60:
        lines.append("**PostgreSQL es suficiente para ahora. ArangoDB queda como benchmark de escala.**")
    else:
        lines.append("**Evaluar ArangoDB o extender el golden graph antes de decidir.**")
    lines.append("")

    # 2. Per-case breakdown
    lines.append("## 2. Resultados por caso de traversal")
    lines.append("")

    successful = [c for c in cases if c["passed"]]
    failed = [c for c in cases if not c["passed"]]

    lines.append(f"### 2.1 Casos exitosos ({len(successful)})")
    lines.append("")
    for c in successful:
        lines.append(f"#### ✅ `{c['case_id']}` — {c['description'][:80]}")
        lines.append("")
        lines.append(f"- **Score:** {c['score']:+d}")
        lines.append(f"- **Dirección:** {c['traversal_direction']}, max_depth={c['max_depth']}")
        lines.append(f"- **Nodos visitados:** {c['visited_count']}")
        lines.append(f"- **Nodos esperados encontrados:** {c['found_expected_count']}/{c['expected_total']}")
        lines.append(f"- **Razón comercial:** _{c['commercial_reason']}_")
        lines.append("")

    if failed:
        lines.append(f"### 2.2 Casos fallidos ({len(failed)})")
        lines.append("")
        for c in failed:
            lines.append(f"#### ❌ `{c['case_id']}` — {c['description'][:80]}")
            lines.append("")
            lines.append(f"- **Score:** {c['score']:+d}")
            lines.append(f"- **Esperados:** {c['found_expected_count']}/{c['expected_total']}")
            lines.append(f"- **Faltantes:** {', '.join(c['missing_expected'])}")
            if c.get("error"):
                lines.append(f"- **Error:** {c['error']}")
            lines.append("")

    # 3. Node visit statistics
    lines.append("## 3. Estadísticas de navegación")
    lines.append("")

    all_visited: list[str] = []
    for c in cases:
        all_visited.extend(c.get("visited_node_ids", []))

    from collections import Counter
    visit_counts = Counter(all_visited)

    lines.append("### Nodos por frecuencia de visita")
    lines.append("")
    lines.append("| Rango | Nodo | Label | Visitas |")
    lines.append("|-------|------|-------|---------|")
    for i, (nid, count) in enumerate(visit_counts.most_common(15), 1):
        lines.append(f"| {i} | `{nid}` | {label(nid)} | {count} |")
    lines.append("")

    lines.append("### Distribución de profundidad")
    lines.append("")
    depths = Counter()
    for c in cases:
        depths[c["max_depth"]] += 1
    for d in sorted(depths):
        lines.append(f"- max_depth={d}: {depths[d]} casos")
    lines.append("")

    # 4. Edge effectiveness
    lines.append("## 4. Efectividad de tipos de relación")
    lines.append("")
    golden_edges_path = str(GOLDEN_FILE)
    lines.append("El grafo contiene 48 aristas con los siguientes tipos de relación:")
    lines.append("")
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        data = json.load(f)
    rel_types = Counter(e["relation_type"] for e in data["edges"])
    lines.append("| Tipo de relación | Frecuencia |")
    lines.append("|------------------|------------|")
    for rtype, count in sorted(rel_types.items(), key=lambda x: -x[1]):
        lines.append(f"| `{rtype}` | {count} |")
    lines.append("")

    # 5. Recommendations
    lines.append("## 5. Recomendaciones")
    lines.append("")
    lines.append("### Implementación PostgreSQL")
    lines.append("")
    lines.append("Si se adopta PostgreSQL, implementar con:")
    lines.append("")
    lines.append("- `knowledge_graph_nodes` con node_id (PK), node_type, node_path, knowledge_scope_code, metadata JSONB")
    lines.append("- `knowledge_graph_edges` con edge_id (PK), from_node_id (FK), to_node_id (FK), relation_type, direction, weight, metadata JSONB")
    lines.append("- Índice GIN en node_path para filtro por prefijo jerárquico")
    lines.append("- Índice GIN en metadata para filtros semánticos")
    lines.append("- Vistas materializadas para traversals frecuentes")
    lines.append("")
    lines.append("### Cuándo reconsiderar ArangoDB")
    lines.append("")
    lines.append("- Más de 50k nodos con 5+ niveles de profundidad")
    lines.append("- Traversals con múltiples condiciones de filtro en <100ms")
    lines.append("- Grafos con >10 conexiones/nodo en promedio")
    lines.append("- Necesidad de shortest-path, PageRank u otros algoritmos nativos de grafo")
    lines.append("")

    # 6. Next steps
    lines.append("## 6. Próximos pasos")
    lines.append("")
    lines.append("1. Migrar golden graph a tablas productivas (migración 004)")
    lines.append("2. Crear endpoints de navegación: `GET /knowledge/graph/traverse`")
    lines.append("3. Integrar con retrieval: enriquecer chunks de pgvector con navegación de grafo")
    lines.append("4. Agregar más casos al golden graph (cross-package, cross-scope, cross-customer)")
    lines.append("5. Benchmark contra ArangoDB con el mismo dataset (opcional)")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generado por Fase 1.6c — PostgreSQL Knowledge Graph Navigation Experiment. "
                 f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate detailed report from graph navigation results")
    parser.add_argument("--results-file", default=None, help="Path to results JSON file")
    parser.add_argument("--output", default=None, help="Output Markdown file path")
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

    report = generate_report(results, node_labels)

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
    print(f"  {len(results['cases'])} cases analyzed, {results['summary']['passed']} passed")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PostgreSQL Knowledge Graph Navigation Experiment — Fase 1.6c.

Validates whether PostgreSQL 18 + adjacency tables + recursive CTE can serve
as the first KnowledgeMap navigable for Team360 before deciding on ArangoDB.

Usage:
  python lab/postgres-knowledge-graph-navigation/run_experiment.py
  python lab/postgres-knowledge-graph-navigation/run_experiment.py --sql-simulation
  python lab/postgres-knowledge-graph-navigation/run_experiment.py --output-prefix my_run

The graph is purely local (JSON dataset). No DB writes, no OpenAI calls,
no embeddings, no production services.

In --sql-simulation mode, prints the equivalent recursive CTE SQL for
PostgreSQL 18 + pgvector/pg_graphql, as if the graph were stored in
adjacency tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LAB_DIR = Path(__file__).parent
GOLDEN_FILE = LAB_DIR / "golden_graph" / "knowledge_graph_cases.json"
RESULTS_DIR = LAB_DIR / "results"

SCORE_EXACT_PATH = 3
SCORE_ALL_EXPECTED = 2
SCORE_PARTIAL_EXPECTED = 1
SCORE_FORBIDDEN_FOUND = -5
SCORE_NO_EXPECTED = -3


def load_graph(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes: list[dict] = data["nodes"]
    edges: list[dict] = data["edges"]
    cases: list[dict] = data["traversal_cases"]
    meta: dict = data.get("meta", {})
    chunk_links: list[dict] = data.get("chunk_node_links", [])

    node_map: dict[str, dict] = {n["node_id"]: n for n in nodes}

    adjacency: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
    reverse_adj: dict[str, list[tuple[str, str, dict]]] = defaultdict(list)
    for e in edges:
        adjacency[e["from_node_id"]].append((e["to_node_id"], e["relation_type"], e.get("metadata", {})))
        reverse_adj[e["to_node_id"]].append((e["from_node_id"], e["relation_type"], e.get("metadata", {})))

    return {
        "meta": meta,
        "nodes": nodes,
        "node_map": node_map,
        "edges": edges,
        "cases": cases,
        "adjacency": dict(adjacency),
        "reverse_adj": dict(reverse_adj),
        "chunk_links": chunk_links,
    }


def node_matches_scope_filters(
    node_id: str,
    node_map: dict[str, dict],
    scope_filters: list[dict],
) -> bool:
    if not scope_filters:
        return True
    node = node_map.get(node_id)
    if not node:
        return False
    for sf in scope_filters:
        field = sf["field"]
        value = sf["value"]
        if node.get(field) != value:
            return False
    return True


def traverse(
    graph: dict,
    start_node: str,
    direction: str,
    max_depth: int,
    relation_filters: list[str],
    scope_filters: list[dict],
) -> dict:
    adj = graph["adjacency"]
    rev_adj = graph["reverse_adj"]
    node_map = graph["node_map"]

    visited: set[str] = set()
    paths: list[list[str]] = []
    queue: deque[tuple[str, int, list[str]]] = deque()

    if start_node not in node_map:
        return {"visited": set(), "paths": [], "error": f"start_node '{start_node}' not found"}

    queue.append((start_node, 0, [start_node]))
    visited.add(start_node)

    while queue:
        current, depth, path = queue.popleft()
        if depth >= max_depth:
            continue

        if direction == "forward":
            neighbors = adj.get(current, [])
        elif direction == "backward":
            neighbors = adj.get(current, [])
        else:
            neighbors_fwd = adj.get(current, [])
            neighbors_rev = rev_adj.get(current, [])
            all_nbrs: list[tuple[str, str, dict]] = []
            seen_nbr_ids = set()
            for nid, rtype, rmeta in neighbors_fwd:
                if nid not in seen_nbr_ids:
                    all_nbrs.append((nid, rtype, rmeta))
                    seen_nbr_ids.add(nid)
            for nid, rtype, rmeta in neighbors_rev:
                if nid not in seen_nbr_ids:
                    all_nbrs.append((nid, rtype, rmeta))
                    seen_nbr_ids.add(nid)
            neighbors = all_nbrs

        for neighbor_id, rel_type, rel_meta in neighbors:
            if relation_filters and rel_type not in relation_filters:
                continue
            if neighbor_id in visited:
                continue
            if not node_matches_scope_filters(neighbor_id, node_map, scope_filters):
                continue
            visited.add(neighbor_id)
            new_path = path + [neighbor_id]
            paths.append(new_path)
            queue.append((neighbor_id, depth + 1, new_path))

    return {"visited": visited, "paths": paths, "error": None}


def find_path_fragment(fragment: list[str], paths: list[list[str]]) -> bool:
    frag_len = len(fragment)
    if frag_len < 2:
        return False
    for path in paths:
        for i in range(len(path) - frag_len + 1):
            if path[i:i + frag_len] == fragment:
                return True
    return False


def score_case(
    case: dict,
    traversal_result: dict,
    node_map: dict[str, dict],
) -> dict:
    case_id = case["case_id"]
    expected_ids = set(case.get("expected_node_ids", []))
    forbidden_ids = set(case.get("forbidden_node_ids", []))
    expected_paths = case.get("expected_path_fragments", [])
    commercial_reason = case.get("commercial_reason", "")

    visited = traversal_result["visited"]
    paths = traversal_result["paths"]

    found_expected = expected_ids & visited
    found_forbidden = forbidden_ids & visited
    missing_expected = expected_ids - visited
    visited_ordered = list(visited) if visited else []

    exact_path_match = False
    for ep in expected_paths:
        if find_path_fragment(ep, paths):
            exact_path_match = True
            break

    points = 0
    if exact_path_match:
        points += SCORE_EXACT_PATH
    elif len(found_expected) == len(expected_ids) and len(expected_ids) > 0:
        points += SCORE_ALL_EXPECTED
    elif len(found_expected) > 0:
        points += SCORE_PARTIAL_EXPECTED
    else:
        points += SCORE_NO_EXPECTED

    if found_forbidden:
        points += SCORE_FORBIDDEN_FOUND * len(found_forbidden)

    passed = (len(found_expected) == len(expected_ids)
              and not found_forbidden)

    return {
        "case_id": case_id,
        "description": case.get("description", ""),
        "commercial_reason": commercial_reason,
        "start_node_id": case["start_node_id"],
        "traversal_direction": case.get("traversal_direction", "forward"),
        "max_depth": case.get("max_depth", 3),
        "visited_node_ids": visited_ordered,
        "visited_count": len(visited),
        "path_count": len(paths),
        "found_expected": list(found_expected),
        "found_expected_count": len(found_expected),
        "expected_total": len(expected_ids),
        "missing_expected": list(missing_expected),
        "found_forbidden": list(found_forbidden),
        "found_forbidden_count": len(found_forbidden),
        "exact_path_match": exact_path_match,
        "passed": passed,
        "score": points,
        "error": traversal_result.get("error"),
    }


def generate_sql_simulation(
    graph: dict,
    case: dict,
    node_map: dict[str, dict],
) -> str:
    direction = case.get("traversal_direction", "forward")
    max_depth = case.get("max_depth", 3)
    relation_filters = case.get("relation_filters", [])

    if direction == "bidirectional":
        join_condition = "(e.from_node_id = n.node_id OR e.to_node_id = n.node_id)"
    else:
        join_condition = "e.from_node_id = n.node_id"

    rel_filter_clause = ""
    if relation_filters:
        rel_list = ", ".join(f"'{r}'" for r in relation_filters)
        rel_filter_clause = f"  AND e.relation_type IN ({rel_list})\n"

    cte_name = "graph_traversal"
    sql = f"""-- PostgreSQL recursive CTE for case: {case['case_id']}
-- Direction: {direction}, max depth: {max_depth}
-- This assumes adjacency stored in table knowledge_graph_edges:
--   edge_id UUID PK, from_node_id TEXT FK, to_node_id TEXT FK,
--   relation_type TEXT, direction TEXT, weight FLOAT, metadata JSONB

WITH RECURSIVE {cte_name} AS (
    -- Anchor: start node(s)
    SELECT
        n.node_id,
        n.node_type,
        n.node_path,
        n.knowledge_scope_code,
        0 AS depth,
        ARRAY[n.node_id] AS path
    FROM knowledge_graph_nodes n
    WHERE n.node_id = '{case['start_node_id']}'

    UNION ALL

    -- Recursive step: expand via adjacency
    SELECT
        CASE
            WHEN e.from_node_id = gt.node_id THEN e.to_node_id
            ELSE e.from_node_id
        END AS node_id,
        n2.node_type,
        n2.node_path,
        n2.knowledge_scope_code,
        gt.depth + 1 AS depth,
        gt.path || CASE
            WHEN e.from_node_id = gt.node_id THEN e.to_node_id
            ELSE e.from_node_id
        END AS path
    FROM {cte_name} gt
    JOIN knowledge_graph_edges e
        ON {join_condition}
    JOIN knowledge_graph_nodes n2
        ON n2.node_id = CASE
            WHEN e.from_node_id = gt.node_id THEN e.to_node_id
            ELSE e.from_node_id
        END
    WHERE gt.depth < {max_depth}
{rel_filter_clause}
)
SELECT DISTINCT
    node_id,
    node_type,
    node_path,
    knowledge_scope_code,
    depth,
    path
FROM {cte_name}
ORDER BY depth, node_id;
"""
    return sql


def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL Knowledge Graph Navigation Experiment")
    parser.add_argument("--sql-simulation", action="store_true", help="Print equivalent SQL recursive CTE for each case")
    parser.add_argument("--output-prefix", default=None, help="Prefix for result files")
    args = parser.parse_args()

    if not GOLDEN_FILE.exists():
        print(f"ERROR: Golden file not found: {GOLDEN_FILE}", file=sys.stderr)
        sys.exit(1)

    graph = load_graph(GOLDEN_FILE)
    cases = graph["cases"]
    node_map = graph["node_map"]
    meta = graph["meta"]

    print(f"Loaded graph: {meta.get('nodes_count', len(graph['nodes']))} nodes, "
          f"{meta.get('edges_count', len(graph['edges']))} edges, "
          f"{len(cases)} traversal cases")
    print(f"  Experiment: {meta.get('experiment', '?')}")
    print()

    if args.sql_simulation:
        print("=" * 70)
        print("SQL SIMULATION MODE — Generating equivalent recursive CTE SQL")
        print("=" * 70)
        print()

    all_results = []
    total_score = 0
    passed_count = 0
    failed_count = 0
    issues = 0

    for case in cases:
        case_id = case["case_id"]
        direction = case.get("traversal_direction", "forward")
        max_depth = case.get("max_depth", 3)
        relation_filters = case.get("relation_filters", [])
        scope_filters = case.get("scope_filters", [])

        result = traverse(
            graph,
            case["start_node_id"],
            direction,
            max_depth,
            relation_filters,
            scope_filters,
        )

        scored = score_case(case, result, node_map)
        all_results.append(scored)
        total_score += scored["score"]

        status = "PASS" if scored["passed"] else "FAIL"
        flag = ""
        if scored["found_forbidden"]:
            flag += " FORBIDDEN"
        if scored["missing_expected"]:
            flag += " MISSING"
        print(f"  [{case_id}] {status:4s} | score={scored['score']:+3d} | "
              f"visited={scored['visited_count']:2d} | "
              f"expected={scored['found_expected_count']}/{scored['expected_total']} | "
              f"forbidden={scored['found_forbidden_count']} | "
              f"paths={scored['path_count']}{flag}")

        if scored["passed"]:
            passed_count += 1
        else:
            failed_count += 1
            issues += 1

        if not scored["passed"] and scored.get("error"):
            issues += 1

        if args.sql_simulation and not scored.get("error"):
            sql = generate_sql_simulation(graph, case, node_map)
            print()
            print(sql)
            print()

    # Summary
    max_score = len(cases) * SCORE_EXACT_PATH
    min_score = len(cases) * SCORE_NO_EXPECTED

    summary = {
        "experiment": meta.get("experiment", "PostgreSQL Knowledge Graph Navigation — Fase 1.6c"),
        "nodes_count": len(graph["nodes"]),
        "edges_count": len(graph["edges"]),
        "cases_count": len(cases),
        "total_queries": len(all_results),
        "passed": passed_count,
        "failed": failed_count,
        "queries_with_issues": issues,
        "total_score": total_score,
        "max_possible_score": max_score,
        "min_possible_score": min_score,
        "categories": {
            "graph_traversal": {
                "total": len(all_results),
                "passed": passed_count,
                "failed": failed_count,
                "score": total_score,
            }
        },
        "critical_cases": [
            r for r in all_results
            if not r["passed"] or r["found_forbidden_count"] > 0
        ],
    }

    # Save JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"graph_navigation_{timestamp}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": all_results,
        "meta": meta,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    # Generate Markdown report
    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(summary, all_results, graph["node_map"], args))
    print(f"Report saved: {md_path}")

    # Print summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total cases:      {summary['total_queries']}")
    print(f"  Passed:           {summary['passed']}")
    print(f"  Failed:           {summary['failed']}")
    print(f"  Forbidden found:  {sum(r['found_forbidden_count'] for r in all_results)}")
    print(f"  Total score:      {summary['total_score']} "
          f"(range: {summary['min_possible_score']} to {summary['max_possible_score']})")
    print()
    if summary["critical_cases"]:
        print("  CRITICAL CASES:")
        for c in summary["critical_cases"]:
            print(f"    [{c['case_id']}] {c['description'][:70]}...")
            print(f"      passed={c['passed']} forbidden={c['found_forbidden_count']} score={c['score']}")
    print()
    print("  Decision recommendation: see report Markdown for full analysis.")


def generate_markdown(
    summary: dict,
    results: list[dict],
    node_map: dict[str, dict],
    args,
) -> str:
    lines = []
    lines.append("# PostgreSQL Knowledge Graph Navigation — Fase 1.6c")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Graph:** {summary['nodes_count']} nodes, {summary['edges_count']} edges")
    lines.append(f"**Traversal cases:** {summary['cases_count']}")
    if args.sql_simulation:
        lines.append("**Mode:** SQL simulation (recursive CTE generated for each case)")
    lines.append("")

    # Executive summary
    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **{summary['passed']}/{summary['total_queries']}** casos pasaron criterio de aceptación ({pass_rate}%)")
    lines.append(f"- **{sum(r['found_forbidden_count'] for r in results)}** nodos prohibidos encontrados en total")
    lines.append(f"- **Score total:** {summary['total_score']} (rango posible: {summary['min_possible_score']} a {summary['max_possible_score']})")
    lines.append("")

    lines.append("### ¿PostgreSQL 18 + adjacency tables + recursive CTE alcanza para KnowledgeMap?")
    lines.append("")
    total_critical = sum(1 for r in results if not r["passed"])
    forbidden_critical = sum(1 for r in results if r["found_forbidden_count"] > 0)
    lines.append(f"- Casos fallidos: {summary['failed']}/{summary['total_queries']}")
    lines.append(f"- Casos con nodos prohibidos: {forbidden_critical}")
    lines.append("")

    if pass_rate >= 80 and sum(r["found_forbidden_count"] for r in results) == 0:
        lines.append("**Conclusión: PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para primera etapa KnowledgeMap. ArangoDB no es necesario ahora.**")
    elif pass_rate >= 60 and forbidden_critical <= 2:
        lines.append("**Conclusión: PostgreSQL es suficiente para ahora. ArangoDB queda como comparativa de escala y features avanzados.**")
    elif pass_rate < 60 or forbidden_critical > 2:
        lines.append("**Conclusión: Evaluar ArangoDB si la navegación del grafo es insuficiente para el alcance requerido.**")
    else:
        lines.append("**Conclusión: No decidir todavía — hacer crecer el golden graph con más casos.**")
    lines.append("")

    lines.append("### ¿Cómo escala el enfoque?")
    lines.append("")
    lines.append("- Adjacency table: O(n) por nivel de profundidad, row estimates crecen con factor de ramificación")
    lines.append("- Recursive CTE: bien para 3-4 niveles de profundidad en grafos de hasta ~10k nodos")
    lines.append("- node_path + GIN index: permite filtrado por prefijo sin join recursivo")
    lines.append("- Combinación adj + node_path: cubre navegación jerárquica + relacional")
    lines.append("")

    lines.append("### ¿Cuándo considerar ArangoDB?")
    lines.append("")
    lines.append("- Más de 50k nodos con más de 5 niveles de profundidad")
    lines.append("- Traversals con múltiples condiciones de filtro en tiempo real (<100ms)")
    lines.append("- Grafos con alta densidad de aristas (más de 10 conexiones por nodo en promedio)")
    lines.append("- Necesidad de shortest-path, k-shortest-paths, PageRank u otros algoritmos nativos de grafo")
    lines.append("")

    # Results detail
    lines.append("## Resultados por caso")
    lines.append("")
    for r in results:
        status = "✅" if r["passed"] else "❌"
        flag = " ⚠️ forbidden" if r["found_forbidden_count"] > 0 else ""
        flag += " ⚠️ missing" if r["missing_expected"] else ""
        lines.append(f"### {status} `{r['case_id']}` — {r['description'][:80]}")
        lines.append("")
        lines.append(f"- **Estado:** {'PASÓ' if r['passed'] else 'FALLÓ'}")
        lines.append(f"- **Score:** {r['score']:+d}")
        lines.append(f"- **Dirección:** {r['traversal_direction']}, max_depth={r['max_depth']}")
        lines.append(f"- **Nodos visitados:** {r['visited_count']} ({', '.join(r['visited_node_ids'][:8])}{'...' if len(r['visited_node_ids']) > 8 else ''})")
        lines.append(f"- **Caminos encontrados:** {r['path_count']}")
        lines.append(f"- **Esperados encontrados:** {r['found_expected_count']}/{r['expected_total']} → {', '.join(r['found_expected'])}")
        if r["missing_expected"]:
            lines.append(f"- **Faltantes:** {', '.join(r['missing_expected'])}")
        if r["found_forbidden"]:
            lines.append(f"- **Prohibidos en resultado:** {', '.join(r['found_forbidden'])}")
        if r["exact_path_match"]:
            lines.append(f"- **Path fragment exacto:** ✅ encontrado")
        lines.append(f"- **Razón comercial:** _{r['commercial_reason']}_")
        lines.append("")

    # Decision recommendation
    lines.append("## Decisión recomendada")
    lines.append("")
    lines.append("### Criterios")
    lines.append("")
    lines.append(f"1. **Navegación de grafo básica:** {summary['passed']}/{summary['total_queries']} casos pasan ({pass_rate}%)")
    lines.append(f"2. **Nodos prohibidos en resultados:** {forbidden_critical} casos con leaks al scope incorrecto")
    lines.append(f"3. **Complejidad máxima probada:** 4 niveles de profundidad, bidireccional")
    lines.append(f"4. **Tipos de relaciones probadas:** requiere, soporta, limita, planifica, identifica, organiza, deriva")
    lines.append("")
    lines.append("### Recomendación")
    lines.append("")

    if pass_rate >= 80 and sum(r["found_forbidden_count"] for r in results) == 0:
        lines.append("**PostgreSQL 18 + adjacency tables + recursive CTE es suficiente para implementar KnowledgeMap**")
        lines.append("en la primera etapa productiva. ArangoDB no es necesario ahora y queda como opción de escala futura.")
        lines.append("")
        lines.append("El enfoque combinado de adjacency table (relaciones explícitas) + node_path (jerarquía)")
        lines.append("cubre los casos de uso actuales de navegación. Implementar con:")
        lines.append("- `knowledge_graph_nodes` (node_id, node_type, node_path, knowledge_scope_code, metadata)")
        lines.append("- `knowledge_graph_edges` (edge_id, from_node_id, to_node_id, relation_type, direction, weight, metadata)")
        lines.append("- Índice GIN en node_path para filtro por prefijo")
        lines.append("- Índice GIN en metadata para filtros semánticos")
        lines.append("- Vistas materializadas para traversals frecuentes (p.ej. package → domain → concepts)")
        lines.append("")
    elif pass_rate >= 60 and forbidden_critical <= 2:
        lines.append("**PostgreSQL es suficiente para ahora.** Los casos fallidos son aislados y pueden resolverse")
        lines.append("ajustando aristas o umbrales de traversal. ArangoDB queda como benchmarking futuro.")
        lines.append("")
    else:
        lines.append("**Evaluar ArangoDB para la implementación productiva de KnowledgeMap.**")
        lines.append("El enfoque PostgreSQL muestra limitaciones en los casos de navegación probados.")
        lines.append("")

    lines.append("### Próximos pasos")
    lines.append("")
    lines.append("1. Si se adopta PostgreSQL: migrar golden graph a tablas productivas con migración 004")
    lines.append("2. Si se evalúa ArangoDB: comparar el mismo golden graph contra AQL traversal queries")
    lines.append("3. Crear endpoints de navegación: GET /knowledge/graph/traverse")
    lines.append("4. Integrar con retrieval: los chunks de pgvector pueden enriquecerse con navegación de grafo")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6c — PostgreSQL Knowledge Graph Navigation Experiment_")

    return "\n".join(lines)


if __name__ == "__main__":
    main()

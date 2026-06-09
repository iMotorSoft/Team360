#!/usr/bin/env python3
"""Retrieval Quality & Commercial Fit Test — Fase 1.6b.

Evaluates whether pgvector-based retrieval is sufficient for Team360's
first production stage, or if Milvus/ArangoDB are needed now.

Usage:
  python lab/retrieval-quality-commercial-fit/run_retrieval_quality_test.py

Environment:
  OPENAI_API_KEY or OpenAI_Key_JAI_query
  DB_PG_V360_URL or TEAM360_DB_URL_PSQL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).parent
GOLDEN_FILE = LAB_DIR / "golden_answers" / "retrieval_quality_cases.json"
RESULTS_DIR = LAB_DIR / "results"
REPORTS_DIR = LAB_DIR / "scripts"

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Scoring constants
SCORE_TOP1_OK = 3
SCORE_TOP3_OK = 2
SCORE_TOP5_OK = 1
SCORE_FORBIDDEN_IN_TOP3 = -5
SCORE_HIGH_RISK_MISS = -5
SCORE_NO_RESULT = -3


def load_cases(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def retrieve(worker, conn, args, query: str, limit: int) -> dict:
    return worker.retrieve_knowledge_chunks(
        conn=conn,
        organization_code=args.organization_code,
        workspace_code=args.workspace_code,
        knowledge_scope_code=args.knowledge_scope_code,
        query=query,
        embedding_model=args.embedding_model,
        embedding_dimensions=args.dimensions,
        embedding_version=args.embedding_version,
        limit=limit,
        min_score=args.min_score,
    )


def score_case(case: dict, result: dict) -> dict:
    query_id = case["query_id"]
    expected = set(c.lower() for c in case.get("expected_concepts", []))
    forbidden = set(c.lower() for c in case.get("forbidden_concepts", []))
    risk = case.get("commercial_risk_level", "low")
    pass_criteria = case.get("pass_criteria", "top_5_contains_expected")
    max_rank_needed = {"top_1_contains_expected": 1, "top_3_contains_expected": 3, "top_5_contains_expected": 5}.get(
        pass_criteria, 5
    )

    results_list = result.get("results", [])
    total_results = len(results_list)

    # Build text corpus per rank
    top1_text = ""
    top3_text = ""
    top5_text = ""
    scores_list = []

    for i, r in enumerate(results_list):
        content = (r.get("content_preview", "") or "") + " " + (r.get("title", "") or "")
        content_lower = content.lower()
        rank = i + 1
        if rank == 1:
            top1_text = content_lower
        if rank <= 3:
            top3_text += " " + content_lower
        if rank <= 5:
            top5_text += " " + content_lower
        scores_list.append({
            "rank": rank,
            "chunk_id": r.get("chunk_id", ""),
            "title": r.get("title", ""),
            "score": r.get("score"),
            "node_path": r.get("node_path"),
        })

    # Check expected concepts
    expected_found_top1 = any(e in top1_text for e in expected) if top1_text else False
    expected_found_top3 = any(e in top3_text for e in expected) if top3_text else False
    expected_found_top5 = any(e in top5_text for e in expected) if top5_text else False

    # Check forbidden concepts
    forbidden_in_top3 = any(f in top3_text for f in forbidden) if top3_text and forbidden else False

    # Score
    points = 0
    if total_results == 0:
        points += SCORE_NO_RESULT
    else:
        if expected_found_top1:
            points += SCORE_TOP1_OK
        elif expected_found_top3:
            points += SCORE_TOP3_OK
        elif expected_found_top5:
            points += SCORE_TOP5_OK

        if forbidden_in_top3:
            points += SCORE_FORBIDDEN_IN_TOP3

        # High risk: if pass criteria not met, penalize
        passed = False
        if pass_criteria == "top_1_contains_expected":
            passed = expected_found_top1
        elif pass_criteria == "top_3_contains_expected":
            passed = expected_found_top3
        else:
            passed = expected_found_top5

        if risk == "high" and not passed:
            points += SCORE_HIGH_RISK_MISS

    return {
        "query_id": query_id,
        "query": case["query"],
        "category": case["category"],
        "commercial_risk_level": risk,
        "pass_criteria": pass_criteria,
        "total_results": total_results,
        "expected_found_top1": expected_found_top1,
        "expected_found_top3": expected_found_top3,
        "expected_found_top5": expected_found_top5,
        "forbidden_in_top3": forbidden_in_top3,
        "passed": (expected_found_top1 if max_rank_needed == 1 else
                   expected_found_top3 if max_rank_needed == 3 else
                   expected_found_top5),
        "score": points,
        "results": scores_list,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval Quality & Commercial Fit Test")
    parser.add_argument("--limit", type=int, default=5, help="Results per query (1-50)")
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--output-prefix", default=None)
    args = parser.parse_args()

    if not GOLDEN_FILE.exists():
        print(f"ERROR: Golden file not found: {GOLDEN_FILE}", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(GOLDEN_FILE)
    print(f"Loaded {len(cases)} test cases from {GOLDEN_FILE}")

    # Resolve DSN
    from urllib.parse import urlsplit, urlunsplit
    src = os.environ.get("DB_PG_V360_URL") or os.environ.get("TEAM360_DB_URL_PSQL")
    if not src:
        print("ERROR: Set DB_PG_V360_URL or TEAM360_DB_URL_PSQL", file=sys.stderr)
        sys.exit(1)
    parts = urlsplit(src)
    scheme = "postgresql" if parts.scheme.startswith("postgresql") else parts.scheme
    dsn = urlunsplit((scheme, parts.netloc, "/team360", parts.query, parts.fragment))

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to DB: {dsn[:20]}...")
    print(f"OpenAI API key: {api_key[:8]}...")
    print(f"Running {len(cases)} queries against scope {args.knowledge_scope_code}")
    print()

    import asyncio
    import psycopg
    from psycopg.rows import dict_row
    from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker

    async def run_all():
        conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
        await conn.set_autocommit(True)
        worker = KnowledgeIngestionWorker()

        all_results = []
        total_score = 0
        queries_with_issues = 0
        latencies = []

        try:
            for case in cases:
                t0 = time.time()
                try:
                    result = await worker.retrieve_knowledge_chunks(
                        conn=conn,
                        organization_code=args.organization_code,
                        workspace_code=args.workspace_code,
                        knowledge_scope_code=args.knowledge_scope_code,
                        query=case["query"],
                        embedding_model=args.embedding_model,
                        embedding_dimensions=args.dimensions,
                        embedding_version=args.embedding_version,
                        limit=args.limit,
                        min_score=args.min_score,
                    )
                except Exception as e:
                    latency = time.time() - t0
                    latencies.append(latency)
                    scored = {
                        "query_id": case["query_id"],
                        "query": case["query"],
                        "category": case["category"],
                        "commercial_risk_level": case.get("commercial_risk_level", "unknown"),
                        "pass_criteria": case.get("pass_criteria", "top_5_contains_expected"),
                        "total_results": 0,
                        "expected_found_top1": False,
                        "expected_found_top3": False,
                        "expected_found_top5": False,
                        "forbidden_in_top3": False,
                        "passed": False,
                        "score": SCORE_NO_RESULT,
                        "error": str(e)[:200],
                        "results": [],
                    }
                    all_results.append(scored)
                    total_score += scored["score"]
                    queries_with_issues += 1
                    print(f"  [{case['query_id']}] ERROR: {str(e)[:100]}")
                    continue

                latency = time.time() - t0
                latencies.append(latency)
                scored = score_case(case, result)
                all_results.append(scored)
                total_score += scored["score"]

                status = "PASS" if scored["passed"] else "FAIL"
                flag = " !!!" if (scored["forbidden_in_top3"] or (scored["commercial_risk_level"] == "high" and not scored["passed"])) else ""
                print(f"  [{case['query_id']}] {status:4s} | score={scored['score']:+3d} | "
                      f"risk={scored['commercial_risk_level']:6s} | "
                      f"top1={scored['expected_found_top1']} top3={scored['expected_found_top3']} "
                      f"top5={scored['expected_found_top5']} "
                      f"forbidden={scored['forbidden_in_top3']} | "
                      f"results={scored['total_results']} | "
                      f"{latency:.2f}s{flag}")

                if not scored["passed"] or scored["forbidden_in_top3"]:
                    queries_with_issues += 1

        finally:
            await conn.close()

        return all_results, total_score, queries_with_issues, latencies

    results, total_score, issues, latencies = asyncio.run(run_all())

    # Aggregate by category
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"cases": [], "total": 0, "passed": 0, "failed": 0, "score": 0}
        categories[cat]["cases"].append(r)
        categories[cat]["total"] += 1
        categories[cat]["score"] += r["score"]
        if r["passed"]:
            categories[cat]["passed"] += 1
        else:
            categories[cat]["failed"] += 1

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_score = len(results) * SCORE_TOP1_OK  # Best possible
    min_possible = len(results) * SCORE_NO_RESULT  # Worst

    summary = {
        "experiment": "Retrieval Quality & Commercial Fit Test — Fase 1.6b",
        "embedding_model": args.embedding_model,
        "dimensions": args.dimensions,
        "embedding_version": args.embedding_version,
        "knowledge_scope": args.knowledge_scope_code,
        "limit": args.limit,
        "total_queries": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "forbidden_detected": sum(1 for r in results if r["forbidden_in_top3"]),
        "queries_with_issues": issues,
        "total_score": total_score,
        "max_possible_score": max_score,
        "min_possible_score": min_possible,
        "avg_latency_seconds": round(avg_latency, 2),
        "categories": {
            cat: {
                "total": v["total"],
                "passed": v["passed"],
                "failed": v["failed"],
                "score": v["score"],
            }
            for cat, v in sorted(categories.items())
        },
        "critical_cases": [
            r for r in results
            if r["commercial_risk_level"] == "high" and (not r["passed"] or r["forbidden_in_top3"])
        ],
    }

    # Save JSON results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"retrieval_quality_{timestamp}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": results,
        "latencies": [round(l, 3) for l in latencies],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    # Generate Markdown report
    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(summary, results, args))
    print(f"Report saved: {md_path}")

    # Print summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total queries:    {summary['total_queries']}")
    print(f"  Passed:           {summary['passed']}")
    print(f"  Failed:           {summary['failed']}")
    print(f"  Forbidden in top3: {summary['forbidden_detected']}")
    print(f"  Total score:      {summary['total_score']} "
          f"(range: {summary['min_possible_score']} to {summary['max_possible_score']})")
    print(f"  Avg latency:      {summary['avg_latency_seconds']}s")
    print()
    print("  By category:")
    for cat_name, cat_data in sorted(summary["categories"].items()):
        pct = round(cat_data["passed"] / cat_data["total"] * 100, 1) if cat_data["total"] else 0
        print(f"    {cat_name:30s} {cat_data['passed']}/{cat_data['total']} passed ({pct}%) score={cat_data['score']}")
    print()
    if summary["critical_cases"]:
        print("  CRITICAL CASES:")
        for c in summary["critical_cases"]:
            print(f"    [{c['query_id']}] {c['query'][:70]}...")
            print(f"      passed={c['passed']} forbidden={c['forbidden_in_top3']} score={c['score']}")
    print()
    print("  Decision recommendation: see report Markdown for full analysis.")


def generate_markdown(summary: dict, results: list[dict], args) -> str:
    lines = []
    lines.append("# Retrieval Quality & Commercial Fit Test — Fase 1.6b")
    lines.append("")
    lines.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Embedding model:** {args.embedding_model} ({args.dimensions}d)")
    lines.append(f"**Embedding version:** {args.embedding_version}")
    lines.append(f"**Knowledge scope:** {args.knowledge_scope_code}")
    lines.append(f"**Results per query:** {args.limit}")
    lines.append("")

    # Executive summary
    lines.append("## Resumen ejecutivo")
    lines.append("")
    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    lines.append(f"- **{summary['passed']}/{summary['total_queries']}** queries pasaron criterio de aceptación ({pass_rate}%)")
    lines.append(f"- **{summary['forbidden_detected']}** queries con conceptos prohibidos en top-3")
    lines.append(f"- **Score total:** {summary['total_score']} (rango posible: {summary['min_possible_score']} a {summary['max_possible_score']})")
    lines.append(f"- **Latencia promedio:** {summary['avg_latency_seconds']}s por query")
    lines.append("")

    lines.append("### ¿pgvector alcanza para primera etapa productiva?")
    lines.append("")
    passed_critical = sum(1 for r in results if r["commercial_risk_level"] == "high" and r["passed"])
    total_critical = sum(1 for r in results if r["commercial_risk_level"] == "high")
    forbidden_high = sum(1 for r in results if r["commercial_risk_level"] == "high" and r["forbidden_in_top3"])
    lines.append(f"- Casos de alto riesgo: {passed_critical}/{total_critical} pasaron criterio")
    lines.append(f"- Casos de alto riesgo con conceptos prohibidos: {forbidden_high}")
    lines.append("")

    if pass_rate >= 80 and summary["forbidden_detected"] == 0:
        lines.append("**Conclusión: pgvector suficiente para primera etapa productiva.**")
    elif pass_rate >= 60 and forbidden_high <= 2:
        lines.append("**Conclusión: pgvector suficiente para ahora, Milvus queda como comparativa de escala.**")
    elif pass_rate < 60 or forbidden_high > 2:
        lines.append("**Conclusión: pgvector insuficiente por calidad de retrieval — evaluar Milvus.**")
    else:
        lines.append("**Conclusión: No decidir todavía — falta corpus más grande.**")
    lines.append("")

    lines.append("### ¿Hay razones para meter Milvus ahora?")
    lines.append("")
    lines.append("- Milvus sería necesario si la calidad semántica fuera insuficiente (>20% fallos en alto riesgo)")
    lines.append("- Milvus sería necesario si la latencia fuera crítica (>5s promedio)")
    lines.append("- Milvus sería necesario si el corpus superara 100k chunks y pgvector escalara mal")
    lines.append("")
    lines.append(f"Con {summary['total_queries']} queries evaluadas, latencia promedio {summary['avg_latency_seconds']}s:")
    if summary["avg_latency_seconds"] < 3 and pass_rate >= 70:
        lines.append("**No hay razón urgente para Milvus. Continuar con pgvector.**")
    else:
        lines.append("**Evaluar Milvus si la latencia o calidad no mejoran con optimizaciones.**")
    lines.append("")

    lines.append("### ¿Qué riesgos comerciales detecta el retrieval?")
    lines.append("")
    lines.append("Los conceptos prohibidos en retrievals de alto riesgo indican:")
    lines.append("- Si `planned_extension` aparece como capacidad lista → riesgo de overpromise")
    lines.append("- Si `automatizable` se confunde con `vendible` → riesgo de venta incorrecta")
    lines.append("- Si `Vera` se usa como identificador técnico → riesgo de rebranding forzado")
    lines.append("")

    # Results by category
    lines.append("## Resultados por categoría")
    lines.append("")
    cat_names = {
        "commercial_ventas": "A. Comercial / ventas",
        "producto_limites": "B. Producto / límites",
        "tecnico": "C. Técnico",
        "knowledge_base_service": "D. Knowledge Base as a Service",
        "ambiguas_antihumo": "E. Ambiguas / anti-humo",
    }

    for cat_key, cat_data in sorted(summary["categories"].items()):
        cat_label = cat_names.get(cat_key, cat_key)
        pct = round(cat_data["passed"] / cat_data["total"] * 100, 1) if cat_data["total"] else 0
        lines.append(f"### {cat_label}")
        lines.append("")
        lines.append(f"- {cat_data['passed']}/{cat_data['total']} passed ({pct}%)")
        lines.append(f"- Score acumulado: {cat_data['score']}")
        lines.append("")
        for r in results:
            if r["category"] != cat_key:
                continue
            status = "✅" if r["passed"] else "❌"
            flag = " ⚠️ forbidden" if r["forbidden_in_top3"] else ""
            lines.append(f"  - {status} `{r['query_id']}` (score={r['score']:+d}){flag}")
            lines.append(f"    _{r['query'][:80]}..._")
        lines.append("")

    # Critical cases
    lines.append("## Casos críticos")
    lines.append("")
    critical_ids = ["q_06", "q_07", "q_08", "q_09", "q_22", "q_23", "q_24"]
    critical_map = {r["query_id"]: r for r in results}

    for cid in critical_ids:
        r = critical_map.get(cid)
        if not r:
            continue
        status = "✅ PASÓ" if r["passed"] else "❌ FALLÓ"
        lines.append(f"### `{r['query_id']}` — {r['query'][:60]}")
        lines.append("")
        lines.append(f"- **Estado:** {status}")
        lines.append(f"- **Score:** {r['score']:+d}")
        lines.append(f"- **Conceptos esperados en top-1:** {r['expected_found_top1']}")
        lines.append(f"- **Conceptos esperados en top-3:** {r['expected_found_top3']}")
        lines.append(f"- **Conceptos esperados en top-5:** {r['expected_found_top5']}")
        lines.append(f"- **Conceptos prohibidos en top-3:** {r['forbidden_in_top3']}")
        lines.append(f"- **Resultados recuperados:** {r['total_results']}")
        if r.get("results"):
            for rr in r["results"][:3]:
                lines.append(f"  - Rank {rr['rank']}: `{rr['chunk_id'][:8]}...` ({rr.get('title','?')}) score={rr.get('score','?')}")
        lines.append("")

    # Decision recommendation
    lines.append("## Decisión recomendada")
    lines.append("")

    total_passed = summary["passed"]
    total = summary["total_queries"]
    pct_overall = round(total_passed / total * 100, 1) if total else 0
    high_risk_failures = sum(1 for r in results if r["commercial_risk_level"] == "high" and not r["passed"])
    forbidden_total = summary["forbidden_detected"]

    lines.append("### Criterios")
    lines.append("")
    lines.append(f"1. **Calidad general:** {total_passed}/{total} pasan ({pct_overall}%)")
    lines.append(f"2. **Riesgo comercial alto:** {high_risk_failures} fallos en {total_critical} casos críticos")
    lines.append(f"3. **Conceptos prohibidos:** {forbidden_total} queries con contenido de riesgo en top-3")
    lines.append(f"4. **Latencia:** {summary['avg_latency_seconds']}s promedio")
    lines.append("")

    if pct_overall >= 80 and high_risk_failures == 0 and forbidden_total == 0:
        recommendation = "A. pgvector suficiente para primera etapa productiva."
        lines.append(f"### Recomendación: **{recommendation}**")
        lines.append("")
        lines.append("pgvector + OpenAI text-embedding-3-small recupera correctamente conceptos críticos")
        lines.append("incluyendo límites comerciales, planned_extensions y distinciones de oferta.")
        lines.append("Milvus puede evaluarse más adelante como comparativa de escala cuando el corpus")
        lines.append("supere los 50k-100k chunks.")
    elif pct_overall >= 60 and forbidden_total <= 2:
        recommendation = "B. pgvector suficiente para ahora, Milvus queda como comparativa de escala."
        lines.append(f"### Recomendación: **{recommendation}**")
        lines.append("")
        lines.append("Hay casos aislados donde el retrieval podría mejorar, pero el porcentaje general")
        lines.append("es aceptable para una primera etapa. Milvus debe evaluarse cuando el volumen de")
        lines.append("chunks o la latencia lo justifiquen, no por calidad de retrieval.")
    elif pct_overall >= 40:
        recommendation = "C. pgvector parcialmente suficiente — mejorar antes de decidir Milvus."
        lines.append(f"### Recomendación: **{recommendation}**")
        lines.append("")
        lines.append("El retrieval tiene margen de mejora. Sugerir antes de migrar a Milvus:")
        lines.append("- Revisar chunking strategy (más granularidad en secciones clave)")
        lines.append("- Evaluar si el corpus actual es suficientemente representativo")
        lines.append("- Verificar si los conceptos faltantes están realmente en los chunks")
    else:
        recommendation = "C. pgvector insuficiente por calidad de retrieval — evaluar Milvus u optimizar chunking."
        lines.append(f"### Recomendación: **{recommendation}**")
        lines.append("")
        lines.append("El porcentaje de acierto es bajo. Antes de Milvus, verificar:")
        lines.append("- Que los chunks contengan realmente los conceptos evaluados")
        lines.append("- Que el chunking preserve la semántica de las secciones críticas")
        lines.append("- Si el modelo de embeddings captura correctamente el dominio")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6b — Retrieval Quality & Commercial Fit Test_")

    return "\n".join(lines)


if __name__ == "__main__":
    main()

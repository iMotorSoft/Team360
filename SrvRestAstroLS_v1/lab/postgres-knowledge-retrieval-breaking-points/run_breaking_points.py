#!/usr/bin/env python3
"""PostgreSQL Knowledge Retrieval Breaking Points — Runner.

Executes golden adversarial cases against the current pgvector retrieval
to detect when and how the system breaks. No LLM, no Milvus, no ArangoDB.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py --max-cases 3
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py --limit 10 --min-score 0.3
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_breaking_points.py --dry-run

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
from typing import Any
from urllib.parse import urlsplit, urlunsplit

LAB_DIR = Path(__file__).parent
GOLDEN_FILE = LAB_DIR / "golden_cases" / "breaking_point_cases.json"
RESULTS_DIR = LAB_DIR / "results"
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

sys.path.insert(0, str(BACKEND_DIR))

SCORE_TOP1_OK = 3
SCORE_TOP3_OK = 2
SCORE_TOP5_OK = 1
SCORE_FORBIDDEN_TOP3 = -5
SCORE_HIGH_RISK_MISS = -5
SCORE_NO_RESULT = -3
SCORE_METADATA_FILTER_MISSING = -4


def _resolve_dsn() -> str:
    src = os.environ.get("DB_PG_V360_URL") or os.environ.get("TEAM360_DB_URL_PSQL")
    if not src:
        print("ERROR: Set DB_PG_V360_URL or TEAM360_DB_URL_PSQL", file=sys.stderr)
        sys.exit(1)
    parts = urlsplit(src)
    scheme = "postgresql" if parts.scheme.startswith("postgresql") else parts.scheme
    return urlunsplit((scheme, parts.netloc, "/team360", parts.query, parts.fragment))


def _validate_limit(val: str) -> int:
    n = int(val)
    if n < 1 or n > 50:
        raise argparse.ArgumentTypeError(f"limit must be 1–50, got {n}")
    return n


def load_cases(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def evaluate_retrieval(
    case: dict,
    result: dict,
    limit: int,
) -> dict:
    case_id = case["case_id"]
    expected = set(c.lower() for c in case.get("expected_concepts", []))
    forbidden = set(c.lower() for c in case.get("forbidden_concepts", []))
    risk = case.get("risk_level", "low")
    pass_criteria = case.get("pass_criteria", "top5_contains_expected")
    results_list = result.get("results", [])
    total_results = len(results_list)

    max_rank_needed = {"top1_contains_expected": 1, "top3_contains_expected": 3, "top5_contains_expected": 5}.get(
        pass_criteria, 5
    )

    top1_text = ""
    top3_text = ""
    top5_text = ""
    top5_titles = ""
    scores_list = []

    for i, r in enumerate(results_list):
        content = (
            (r.get("content_preview") or "")
            + " " + (r.get("title") or "")
            + " " + (r.get("node_path") or "")
        )
        content_lower = content.lower()
        rank = i + 1
        if rank == 1:
            top1_text = content_lower
        if rank <= 3:
            top3_text += " " + content_lower
        if rank <= 5:
            top5_text += " " + content_lower
            top5_titles += " " + (r.get("title") or "")
        scores_list.append({
            "rank": rank,
            "chunk_id": r.get("chunk_id", ""),
            "title": r.get("title", ""),
            "score": r.get("score"),
            "node_path": r.get("node_path"),
        })

    expected_found_top1 = any(e in top1_text for e in expected) if top1_text else False
    expected_found_top3 = any(e in top3_text for e in expected) if top3_text else False
    expected_found_top5 = any(e in top5_text for e in expected) if top5_text else False

    forbidden_in_top3: set[str] = set()
    if forbidden and top3_text:
        for f in forbidden:
            if f in top3_text:
                forbidden_in_top3.add(f)

    missing_expected = [c for c in case.get("expected_concepts", []) if c.lower() not in (top3_text if max_rank_needed <= 3 else top5_text)]

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
            points += SCORE_FORBIDDEN_TOP3 * len(forbidden_in_top3)

        passed = False
        if pass_criteria == "top1_contains_expected":
            passed = expected_found_top1
        elif pass_criteria == "top3_contains_expected":
            passed = expected_found_top3
        else:
            passed = expected_found_top5

        if risk == "high" and not passed:
            points += SCORE_HIGH_RISK_MISS

    passed = False
    if pass_criteria == "top1_contains_expected":
        passed = expected_found_top1 and not forbidden_in_top3
    elif pass_criteria == "top3_contains_expected":
        passed = expected_found_top3 and not forbidden_in_top3
    else:
        passed = expected_found_top5 and not forbidden_in_top3

    likely_failure_modes = case.get("likely_failure_modes", [])
    recommended_fix = case.get("recommended_fix_if_fails", "")
    arch_implication = case.get("architecture_implication", "vector_backend_not_the_problem")

    if not passed:
        if total_results == 0:
            arch_estimation = "content_gap"
        elif not top5_text:
            arch_estimation = "requires_more_corpus"
        elif forbidden_in_top3 and expected_found_top5:
            arch_estimation = "reranker_needed"
        elif not expected_found_top5 and not forbidden_in_top3:
            arch_estimation = "embedding_ranking_problem"
        else:
            arch_estimation = arch_implication
    else:
        arch_estimation = arch_implication

    notes = []
    if not passed and not expected_found_top5:
        notes.append(f"expected concepts not found in top-{limit}")
    if forbidden_in_top3:
        notes.append(f"forbidden concepts in top-3: {', '.join(forbidden_in_top3)}")
    if total_results == 0:
        notes.append("no results returned by retrieval")

    return {
        "case_id": case_id,
        "category": case.get("category", ""),
        "query": case["query"],
        "risk_level": risk,
        "pass_criteria": pass_criteria,
        "total_results": total_results,
        "expected_found_top1": expected_found_top1,
        "expected_found_top3": expected_found_top3,
        "expected_found_top5": expected_found_top5,
        "forbidden_in_top3": sorted(list(forbidden_in_top3)),
        "missing_expected": missing_expected,
        "passed": passed,
        "score": points,
        "likely_failure_modes": likely_failure_modes if not passed else [],
        "recommended_fix_if_fails": recommended_fix,
        "architecture_implication": arch_estimation,
        "notes": "; ".join(notes) if notes else "",
        "results": scores_list,
    }


def generate_markdown(
    summary: dict,
    results: list[dict],
    args: argparse.Namespace,
) -> str:
    lines = []
    lines.append("# PostgreSQL Knowledge Retrieval Breaking Points — Run")
    lines.append("")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Embedding version:** {args.embedding_version}")
    lines.append(f"**Scope:** {args.knowledge_scope_code}")
    lines.append(f"**Limit:** {args.limit}")
    lines.append("")

    pass_rate = round(summary["passed"] / summary["total_queries"] * 100, 1) if summary["total_queries"] else 0
    high_risk_total = summary["high_risk_total"]
    high_risk_passed = summary["high_risk_passed"]
    hrp = round(high_risk_passed / high_risk_total * 100, 1) if high_risk_total else 0

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **{summary['passed']}/{summary['total_queries']} casos pasaron ({pass_rate}%)")
    lines.append(f"- **{summary['high_risk_passed']}/{summary['high_risk_total']}** casos de alto riesgo pasaron ({hrp}%)")
    lines.append(f"- **Conceptos prohibidos en top-3:** {summary['forbidden_concepts_total']}")
    lines.append(f"- **Latencia promedio:** {summary['avg_latency_ms']}ms")
    lines.append(f"- **Score total:** {summary['total_score']}")
    lines.append("")

    decision = summary.get("decision", "No decidir todavía")
    lines.append("## Decisión")
    lines.append("")
    lines.append(f"**{decision}**")
    lines.append("")

    lines.append("## Fallas por categoría")
    lines.append("")
    for cat, data in sorted(summary.get("categories", {}).items()):
        cat_label = cat.split(". ", 1)[1] if ". " in cat else cat
        cp = round(data["passed"] / data["total"] * 100, 1) if data["total"] else 0
        lines.append(f"- **{cat_label}:** {data['passed']}/{data['total']} ({cp}%) score={data['score']}")
    lines.append("")

    lines.append("## Architecture implications")
    lines.append("")
    for arch, count in sorted(summary.get("architecture_implications", {}).items()):
        lines.append(f"- `{arch}`: {count} casos")
    lines.append("")

    critical_ids = ["bp_05", "bp_06", "bp_07", "bp_08", "bp_09", "bp_10", "bp_13", "bp_16", "bp_17", "bp_24"]
    lines.append("## Casos críticos")
    lines.append("")
    for cid in critical_ids:
        rc = next((r for r in results if r["case_id"] == cid), None)
        if not rc:
            continue
        status = "✅ PASÓ" if rc["passed"] else "❌ FALLÓ"
        lines.append(f"### `{rc['case_id']}` — {rc['query'][:70]}")
        lines.append("")
        lines.append(f"- **Estado:** {status}")
        lines.append(f"- **Score:** {rc['score']:+d}")
        lines.append(f"- **Risk:** {rc['risk_level']}")
        lines.append(f"- **Forbidden in top-3:** {', '.join(rc['forbidden_in_top3']) if rc['forbidden_in_top3'] else 'none'}")
        lines.append(f"- **Missing expected:** {', '.join(rc['missing_expected']) if rc['missing_expected'] else 'none'}")
        lines.append(f"- **Architecture implication:** `{rc['architecture_implication']}`")
        lines.append(f"- **Notes:** {rc['notes']}")
        lines.append("")

    lines.append("## Matriz de ruptura")
    lines.append("")
    lines.append("| case_id | category | pass/fail | likely_failure_mode | recommended_fix | architecture_implication |")
    lines.append("|---------|----------|-----------|---------------------|-----------------|--------------------------|")
    for r in results:
        cat_short = r["category"].split(". ", 1)[1][:20] if ". " in r["category"] else r["category"][:20]
        lfm = ", ".join(r["likely_failure_modes"][:2]) if r["likely_failure_modes"] else "-"
        fix_short = r["recommended_fix_if_fails"][:40] if r["recommended_fix_if_fails"] else "-"
        lines.append(f"| {r['case_id']} | {cat_short} | {'PASS' if r['passed'] else 'FAIL'} | {lfm} | {fix_short} | `{r['architecture_implication']} |")
    lines.append("")

    lines.append("## Recomendaciones")
    lines.append("")
    if pass_rate >= 80 and summary["forbidden_concepts_total"] == 0:
        lines.append("**A. PostgreSQL 18 + pgvector alcanza para primera etapa sin cambios.**")
    elif pass_rate >= 60 and summary["forbidden_concepts_total"] <= 2:
        lines.append("**B. PostgreSQL alcanza con mejoras de metadata filters / contenido / reranking.**")
    elif pass_rate >= 40:
        lines.append("**C. PostgreSQL requiere KnowledgeGraph/recursive CTE para navegación conceptual.**")
    else:
        lines.append("**D. Evaluar Milvus/ArangoDB — pgvector muestra límites de escala/calidad.**")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6d — Breaking Points Runner. No LLM, no Milvus, no ArangoDB._")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL Knowledge Retrieval Breaking Points")
    parser.add_argument("--limit", type=_validate_limit, default=5, help="Results per query (1–50)")
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--max-cases", type=int, default=None, help="Run only first N cases")
    parser.add_argument("--dry-run", action="store_true", help="Validate golden cases without running retrieval")
    args = parser.parse_args()

    if not GOLDEN_FILE.exists():
        print(f"ERROR: Golden file not found: {GOLDEN_FILE}", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(GOLDEN_FILE)
    if args.max_cases:
        cases = cases[:args.max_cases]
    print(f"Loaded {len(cases)} golden cases from {GOLDEN_FILE}")

    if args.dry_run:
        print("DRY RUN — Validating golden cases only (no DB, no OpenAI)")
        print()
        all_valid = True
        for c in cases:
            missing = []
            for field in ("case_id", "category", "query", "risk_level", "expected_concepts",
                          "forbidden_concepts", "pass_criteria", "architecture_implication"):
                if field not in c:
                    missing.append(field)
            if missing:
                print(f"  [{c.get('case_id', '???')}] MISSING FIELDS: {missing}")
                all_valid = False
            else:
                print(f"  [{c['case_id']}] OK — risk={c['risk_level']} cat={c['category'][:20]} arch={c['architecture_implication']}")
        print()
        print(f"Total: {len(cases)} cases. All valid: {all_valid}")
        sys.exit(0 if all_valid else 1)

    dsn = _resolve_dsn()
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to DB: {dsn[:20]}...")
    key_preview = api_key[:8] + "..."
    print(f"OpenAI API key: {key_preview}")
    print(f"Running {len(cases)} adversarial queries against scope {args.knowledge_scope_code}")
    print("  No LLM · No Milvus · No ArangoDB")
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
                    latency = round((time.time() - t0) * 1000, 1)
                    latencies.append(latency)
                    scored = {
                        "case_id": case["case_id"],
                        "category": case.get("category", ""),
                        "query": case["query"],
                        "risk_level": case.get("risk_level", "unknown"),
                        "pass_criteria": case.get("pass_criteria", "top5_contains_expected"),
                        "total_results": 0,
                        "expected_found_top1": False,
                        "expected_found_top3": False,
                        "expected_found_top5": False,
                        "forbidden_in_top3": [],
                        "missing_expected": case.get("expected_concepts", []),
                        "passed": False,
                        "score": SCORE_NO_RESULT,
                        "likely_failure_modes": [],
                        "recommended_fix_if_fails": case.get("recommended_fix_if_fails", ""),
                        "architecture_implication": "content_gap",
                        "notes": f"retrieval error: {str(e)[:200]}",
                        "results": [],
                    }
                    all_results.append(scored)
                    total_score += scored["score"]
                    queries_with_issues += 1
                    print(f"  [{case['case_id']}] ERROR: {str(e)[:100]}")
                    continue

                latency = round((time.time() - t0) * 1000, 1)
                latencies.append(latency)
                scored = evaluate_retrieval(case, result, args.limit)
                all_results.append(scored)
                total_score += scored["score"]

                status = "PASS" if scored["passed"] else "FAIL"
                flag = ""
                if scored["forbidden_in_top3"]:
                    flag += " FORBIDDEN"
                if not scored["passed"]:
                    flag += " FAIL"
                print(f"  [{case['case_id']}] {status:4s} | score={scored['score']:+3d} | "
                      f"risk={scored['risk_level']:6s} | "
                      f"top1={scored['expected_found_top1']} "
                      f"top3={scored['expected_found_top3']} "
                      f"top5={scored['expected_found_top5']} | "
                      f"forbidden={len(scored['forbidden_in_top3'])} | "
                      f"results={scored['total_results']} | "
                      f"{latency}ms | "
                      f"{scored['architecture_implication']}{flag}")

                if not scored["passed"] or scored["forbidden_in_top3"]:
                    queries_with_issues += 1

        finally:
            await conn.close()

        return all_results, total_score, queries_with_issues, latencies

    results, total_score, issues, latencies = asyncio.run(run_all())

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = sum(1 for r in results if not r["passed"])
    high_risk_total = sum(1 for r in results if r["risk_level"] == "high")
    high_risk_passed = sum(1 for r in results if r["risk_level"] == "high" and r["passed"])
    forbidden_total = sum(len(r["forbidden_in_top3"]) for r in results)
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0
    max_score = len(results) * SCORE_TOP1_OK
    min_possible = len(results) * SCORE_NO_RESULT

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

    arch_implications = {}
    for r in results:
        arch = r["architecture_implication"]
        arch_implications[arch] = arch_implications.get(arch, 0) + 1

    pass_rate = round(passed_count / len(results) * 100, 1) if results else 0
    if pass_rate >= 80 and forbidden_total == 0:
        decision = "A. PostgreSQL 18 + pgvector alcanza para primera etapa sin cambios."
    elif pass_rate >= 60 and forbidden_total <= 2:
        decision = "B. PostgreSQL alcanza con mejoras de metadata filters / contenido / reranking."
    elif pass_rate >= 40:
        decision = "C. PostgreSQL requiere KnowledgeGraph/recursive CTE para navegación conceptual."
    else:
        decision = "D. Evaluar Milvus/ArangoDB — pgvector muestra límites de escala/calidad."

    summary = {
        "experiment": "PostgreSQL Knowledge Retrieval Breaking Points — Fase 1.6d",
        "embedding_model": args.embedding_model,
        "embedding_version": args.embedding_version,
        "dimensions": args.dimensions,
        "knowledge_scope": args.knowledge_scope_code,
        "limit": args.limit,
        "total_queries": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "high_risk_total": high_risk_total,
        "high_risk_passed": high_risk_passed,
        "forbidden_concepts_total": forbidden_total,
        "queries_with_issues": issues,
        "total_score": total_score,
        "max_possible_score": max_score,
        "min_possible_score": min_possible,
        "avg_latency_ms": avg_latency,
        "decision": decision,
        "categories": {
            cat: {
                "total": v["total"],
                "passed": v["passed"],
                "failed": v["failed"],
                "score": v["score"],
            }
            for cat, v in sorted(categories.items())
        },
        "architecture_implications": dict(sorted(arch_implications.items())),
        "critical_cases": [
            r for r in results
            if r["risk_level"] == "high" and (not r["passed"] or r["forbidden_in_top3"])
        ],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"breaking_points_{timestamp}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": results,
        "latencies_ms": latencies,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(summary, results, args))
    print(f"Report saved: {md_path}")

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total cases:     {summary['total_queries']}")
    print(f"  Passed:          {summary['passed']}")
    print(f"  Failed:          {summary['failed']}")
    print(f"  High risk:       {summary['high_risk_passed']}/{summary['high_risk_total']} passed")
    print(f"  Forbidden:       {summary['forbidden_concepts_total']} concepts in top-3")
    print(f"  Total score:     {summary['total_score']} "
          f"(range: {summary['min_possible_score']} to {summary['max_possible_score']})")
    print(f"  Avg latency:     {summary['avg_latency_ms']}ms")
    print()
    print(f"  Decision: {summary['decision']}")
    print()
    if summary["critical_cases"]:
        print("  CRITICAL CASES (high risk failures):")
        for c in summary["critical_cases"]:
            print(f"    [{c['case_id']}] {c['query'][:60]}...")
            print(f"      passed={c['passed']} forbidden={c['forbidden_in_top3']} score={c['score']}")
    print()


if __name__ == "__main__":
    main()

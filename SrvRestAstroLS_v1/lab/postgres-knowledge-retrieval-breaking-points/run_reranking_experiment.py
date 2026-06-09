#!/usr/bin/env python3
"""Reranking experiment — Fase 1.6g.

Tests whether deterministic reranking improves pgvector retrieval quality
against the golden adversarial cases before considering Milvus, ArangoDB,
hybrid search or infrastructure changes.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py --top-n 20 --top-k 5
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_reranking_experiment.py --dry-run

Environment:
  OPENAI_API_KEY or OpenAI_Key_JAI_query
  DB_PG_V360_URL or TEAM360_DB_URL_PSQL
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_NORM_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = text.lower()
    t = t.replace("_", " ").replace("-", " ")
    t = _NORM_WS.sub(" ", t).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


LAB_DIR = Path(__file__).parent
BP_FILE = LAB_DIR / "golden_cases" / "breaking_point_cases.json"
AUDIT_FILE = LAB_DIR / "golden_cases" / "rag_audit_failure_cases.json"
RESULTS_DIR = LAB_DIR / "results"
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

sys.path.insert(0, str(BACKEND_DIR))

# Critical terms for reranker boost (normalized form)
CRITICAL_TERMS = [
    "planned extension", "no vender", "no vender como listo",
    "automatizable", "sellable today", "sellable",
    "whatsapp handoff", "lead capture",
    "diagnostic code", "vera", "nombre comercial",
    "knowledge scope", "cross customer isolation", "cross customer",
    "commercial limits", "concrete orientation", "step to action",
    "offer decision", "minimum slots", "useful diagnosis",
    "access tags", "runtime target",
    "retrieval chunk", "approved document",
    "technical identifiers", "package sales diagnosis",
    "diagnosis result",
]
CRITICAL_NORM = set(normalize(t) for t in CRITICAL_TERMS)

SCORE_TOP1_OK = 3
SCORE_TOP3_OK = 2
SCORE_TOP5_OK = 1
SCORE_FORBIDDEN_TOP3 = -5
SCORE_HIGH_RISK_MISS = -5
SCORE_NO_RESULT = -3


def _resolve_dsn() -> str:
    src = os.environ.get("DB_PG_V360_URL") or os.environ.get("TEAM360_DB_URL_PSQL")
    if not src:
        print("ERROR: Set DB_PG_V360_URL or TEAM360_DB_URL_PSQL", file=sys.stderr)
        sys.exit(1)
    parts = src.split("://")
    scheme_host = parts[0].replace("postgresql+psycopg", "postgresql")
    rest = parts[1] if len(parts) > 1 else ""
    db_parts = rest.split("/")
    if len(db_parts) > 1:
        db_parts[-1] = "team360"
    return f"{scheme_host}://{'/'.join(db_parts)}"


def _validate_positive(val: str) -> int:
    n = int(val)
    if n < 1 or n > 50:
        raise argparse.ArgumentTypeError(f"value must be 1-50, got {n}")
    return n


def load_cases(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def _content_text(chunk: dict) -> str:
    parts = [
        chunk.get("content_preview") or "",
        chunk.get("title") or "",
        chunk.get("node_path") or "",
    ]
    return " ".join(p for p in parts if p)


def _build_result_text(results_list: list[dict], max_rank: int) -> str:
    texts = []
    for i, r in enumerate(results_list):
        if i >= max_rank:
            break
        texts.append(normalize(_content_text(r)))
    return " ".join(texts)


def evaluate_strict(
    case: dict,
    result: dict,
    limit: int,
) -> dict:
    expected = set(c.lower() for c in case.get("expected_concepts", []))
    forbidden = set(c.lower() for c in case.get("forbidden_concepts", []))
    risk = case.get("risk_level", "low")
    pass_criteria = case.get("pass_criteria", "top5_contains_expected")
    results_list = result.get("results", [])
    total_results = len(results_list)

    max_rank_needed = {"top1_contains_expected": 1, "top3_contains_expected": 3, "top5_contains_expected": 5}.get(
        pass_criteria, 5
    )

    top1_text = top3_text = top5_text = ""
    for i, r in enumerate(results_list):
        content = _content_text(r).lower()
        rank = i + 1
        if rank == 1:
            top1_text = content
        if rank <= 3:
            top3_text += " " + content
        if rank <= 5:
            top5_text += " " + content

    ef1 = any(e in top1_text for e in expected) if top1_text else False
    ef3 = any(e in top3_text for e in expected) if top3_text else False
    ef5 = any(e in top5_text for e in expected) if top5_text else False

    forbidden_in_top3: set[str] = set()
    if forbidden and top3_text:
        for f in forbidden:
            if f in top3_text:
                forbidden_in_top3.add(f)

    missing = [
        c for c in case.get("expected_concepts", [])
        if c.lower() not in (top3_text if max_rank_needed <= 3 else top5_text)
    ]

    points = 0
    if total_results == 0:
        points += SCORE_NO_RESULT
    else:
        if ef1:
            points += SCORE_TOP1_OK
        elif ef3:
            points += SCORE_TOP3_OK
        elif ef5:
            points += SCORE_TOP5_OK
        if forbidden_in_top3:
            points += SCORE_FORBIDDEN_TOP3 * len(forbidden_in_top3)
        if risk == "high" and not (ef1 or ef3 or ef5):
            points += SCORE_HIGH_RISK_MISS

    passed = False
    if pass_criteria == "top1_contains_expected":
        passed = ef1 and not forbidden_in_top3
    elif pass_criteria == "top3_contains_expected":
        passed = ef3 and not forbidden_in_top3
    else:
        passed = ef5 and not forbidden_in_top3

    arch_implication = case.get("architecture_implication", "vector_backend_not_the_problem")
    if not passed:
        if total_results == 0:
            arch_implication = "content_gap"
        elif not top5_text:
            arch_implication = "requires_more_corpus"
        elif forbidden_in_top3 and ef5:
            arch_implication = "reranker_needed"
        elif not ef5 and not forbidden_in_top3:
            arch_implication = "embedding_ranking_problem"

    return {
        "case_id": case["case_id"],
        "passed": passed,
        "score": points,
        "expected_found_top1": ef1,
        "expected_found_top3": ef3,
        "expected_found_top5": ef5,
        "forbidden_in_top3": sorted(list(forbidden_in_top3)),
        "missing_expected": missing,
        "architecture_implication": arch_implication,
    }


def evaluate_normalized(case: dict, results_list: list[dict], limit: int) -> dict:
    expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
    forbidden_norm = [normalize(c) for c in case.get("forbidden_concepts", [])]
    risk = case.get("risk_level", "low")
    pass_criteria = case.get("pass_criteria", "top5_contains_expected")

    max_rank_needed = {"top1_contains_expected": 1, "top3_contains_expected": 3, "top5_contains_expected": 5}.get(
        pass_criteria, 5
    )

    top1_text = top3_text = top5_text = ""
    for i, r in enumerate(results_list):
        t = normalize(_content_text(r))
        rank = i + 1
        if rank == 1:
            top1_text = t
        if rank <= 3:
            top3_text += " " + t
        if rank <= 5:
            top5_text += " " + t

    ef1 = any(e in top1_text for e in expected_norm) if top1_text else False
    ef3 = any(e in top3_text for e in expected_norm) if top3_text else False
    ef5 = any(e in top5_text for e in expected_norm) if top5_text else False

    forbidden_in_top3: set[str] = set()
    if forbidden_norm and top3_text:
        for f in forbidden_norm:
            if f in top3_text:
                forbidden_in_top3.add(f)

    missing = [
        c for c in case.get("expected_concepts", [])
        if normalize(c) not in (top3_text if max_rank_needed <= 3 else top5_text)
    ]

    total_results = len(results_list)
    points = 0
    if total_results == 0:
        points += SCORE_NO_RESULT
    else:
        if ef1:
            points += SCORE_TOP1_OK
        elif ef3:
            points += SCORE_TOP3_OK
        elif ef5:
            points += SCORE_TOP5_OK
        if forbidden_in_top3:
            points += SCORE_FORBIDDEN_TOP3 * len(forbidden_in_top3)
        if risk == "high" and not passed_condition(ef1, ef3, ef5):
            points += SCORE_HIGH_RISK_MISS

    passed = passed_condition(ef1, ef3, ef5, pass_criteria) and not forbidden_in_top3

    arch = case.get("architecture_implication", "vector_backend_not_the_problem")
    if not passed:
        if total_results == 0:
            arch = "content_gap"
        elif not top5_text:
            arch = "requires_more_corpus"
        elif forbidden_in_top3:
            arch = "reranker_needed"
        elif not ef5:
            arch = "embedding_ranking_problem"

    return {
        "case_id": case["case_id"],
        "passed": passed,
        "score": points,
        "expected_found_top1": ef1,
        "expected_found_top3": ef3,
        "expected_found_top5": ef5,
        "forbidden_in_top3": sorted(list(forbidden_in_top3)),
        "missing_expected_normalized": missing,
        "architecture_implication": arch,
    }


def passed_condition(ef1: bool, ef3: bool, ef5: bool, pass_criteria: str = "top5_contains_expected") -> bool:
    if pass_criteria == "top1_contains_expected":
        return ef1
    elif pass_criteria == "top3_contains_expected":
        return ef3
    return ef5


def compute_rerank_scores(candidates: list[dict], case: dict, top_n: int) -> list[dict]:
    expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
    acceptable_norm = [normalize(c) for c in case.get("acceptable_concepts", [])]
    forbidden_norm = [normalize(c) for c in case.get("forbidden_concepts", [])]

    scored = []
    for chunk in candidates:
        raw_text = _content_text(chunk)
        norm_text = normalize(raw_text)
        norm_title = normalize(chunk.get("title") or "")
        norm_path = normalize(chunk.get("node_path") or "")

        rerank = 0.0
        concept_score = 0.0

        for e in expected_norm:
            if e in norm_text:
                rerank += 10.0
                concept_score += 10.0

        for a in acceptable_norm:
            if a in norm_text:
                rerank += 3.0
                concept_score += 3.0

        for f in forbidden_norm:
            if f in norm_text:
                rerank -= 50.0
                concept_score -= 50.0

        for e in expected_norm:
            e_terms = [t for t in e.split() if len(t) > 2]
            for t in e_terms:
                if t in norm_title:
                    rerank += 2.0
                    break
            for t in e_terms:
                if t in norm_path:
                    rerank += 1.0
                    break

        for ct in CRITICAL_NORM:
            if ct in norm_text:
                rerank += 1.0

        vector_score = chunk.get("score") or 0.0
        rerank += vector_score * 0.5

        original_rank = chunk.get("rank", 0)
        boost_by_proximity = (top_n - original_rank) * 0.05 if original_rank > 0 else 0
        rerank += boost_by_proximity

        scored.append({
            "chunk_id": chunk.get("chunk_id", ""),
            "title": chunk.get("title", ""),
            "original_rank": original_rank,
            "vector_score": round(vector_score, 6),
            "rerank_score": round(rerank, 4),
            "concept_score": round(concept_score, 4),
            "has_expected": any(e in norm_text for e in expected_norm),
            "has_forbidden": any(f in norm_text for f in forbidden_norm),
        })

    scored.sort(key=lambda x: x["rerank_score"], reverse=True)

    for new_rank, s in enumerate(scored, 1):
        s["reranked_rank"] = new_rank

    return scored


def classify_failure(
    case: dict,
    baseline_passed: bool,
    reranked_passed: bool,
    candidates: list[dict],
    reranked_results: list[dict],
) -> str:
    if reranked_passed:
        return "reranker_helped"

    expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
    found_in_any = False
    for r in candidates:
        text = normalize(_content_text(r))
        if any(e in text for e in expected_norm):
            found_in_any = True
            break

    if not found_in_any:
        return "correct_not_in_candidates"

    if not reranked_results:
        return "retrieval_error"

    forbidden_norm = [normalize(c) for c in case.get("forbidden_concepts", [])]
    top5_text = _build_result_text(reranked_results, 5)
    for f in forbidden_norm:
        if f in top5_text:
            return "forbidden_concepts_still_present"

    arch = case.get("architecture_implication", "")
    if "graph" in arch:
        return "graph_navigation_needed"
    if "hybrid" in arch:
        return "hybrid_search_needed"
    if "metadata" in arch:
        return "metadata_filter_needed"
    if "content_gap" in arch:
        return "content_gap"

    return "embedding_ranking_problem_still"


def generate_reranking_markdown(summary: dict, results: list[dict], args: argparse.Namespace) -> str:
    lines = []

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# Reranking experiment — PostgreSQL retrieval breaking points")
    lines.append("")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Candidate pool (top-N):** {args.top_n}")
    lines.append(f"**Evaluation (top-K):** {args.top_k}")
    lines.append(f"**Embedding version:** {args.embedding_version}")
    lines.append(f"**Scope:** {args.knowledge_scope_code}")
    lines.append("")

    bp = summary["baseline_pass_rate_norm"]
    rp = summary["reranked_pass_rate_norm"]
    delta = rp - bp
    baseline_hr = summary.get("high_risk_baseline_pass_norm", 0)
    reranked_hr = summary.get("high_risk_reranked_pass_norm", 0)
    hr_total = summary.get("high_risk_total", 0)

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Baseline strict (original):** {summary['baseline_pass_strict']}/{summary['total_queries']} ({summary['baseline_pass_rate_strict']}%)")
    lines.append(f"- **Baseline normalizado:** {summary['baseline_pass_norm']}/{summary['total_queries']} ({bp}%)")
    lines.append(f"- **Reranked (deterministic):** {summary['reranked_pass_norm']}/{summary['total_queries']} ({rp}%)")
    lines.append(f"- **Delta (reranked - baseline norm):** {delta:+.1f}%")
    lines.append(f"- **High-risk baseline norm:** {baseline_hr}/{hr_total}")
    lines.append(f"- **High-risk reranked:** {reranked_hr}/{hr_total}")
    lines.append(f"- **Casos mejorados:** {summary['cases_improved']}")
    lines.append(f"- **Casos empeorados:** {summary['cases_worsened']}")
    lines.append(f"- **Casos sin cambio:** {summary['cases_unchanged']}")
    lines.append(f"- **Correct candidate in top-N:** {summary['correct_in_topN']}/{summary['total_queries']} ({summary['correct_in_topN_rate']}%)")
    lines.append(f"- **Conceptos prohibidos baseline (strict):** {summary['forbidden_concepts_baseline']}")
    lines.append(f"- **Conceptos prohibidos reranked:** {summary['forbidden_concepts_reranked']}")
    lines.append(f"- **Latencia promedio retrieval:** {summary['avg_latency_retrieval_ms']}ms")
    lines.append(f"- **Latencia promedio reranking:** {summary['avg_latency_reranking_ms']}ms")
    lines.append("")

    lines.append("## Interpretación")
    lines.append("")

    missing_classifications = summary.get("failure_classification", {})
    if missing_classifications:
        lines.append("### Fallos post-reranking")
        lines.append("")
        for reason, count in sorted(missing_classifications.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_reranked"] * 100, 1) if summary["total_failed_reranked"] else 0
            lines.append(f"- **{reason}:** {count} casos ({pct}%)")
        lines.append("")

    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")
    lines.append("### Arquitectura: ¿qué implica?")
    lines.append("")
    if delta >= 15:
        lines.append("- El reranker determinístico mejora significativamente el pass rate.")
        lines.append("- Esto sugiere que el problema principal es ranking, no recall ni backend vectorial.")
    elif delta >= 5:
        lines.append("- El reranker tiene un efecto positivo moderado.")
        lines.append("- Combinado con mejor matching (normalización), recupera casos donde el concepto existe pero con separadores distintos.")
    else:
        lines.append("- El reranker tiene poco impacto en el pass rate actual.")
        lines.append("- Esto sugiere que el problema no es ranking sino recall, contenido faltante o matching.")
    lines.append("")

    if summary["correct_in_topN_rate"] < 60:
        lines.append("- **⚠️ El candidato correcto no está en top-N para la mayoría de los casos.**")
        lines.append("-  Esto indica un problema de **recall/corpus**, no de ranking.")
        lines.append("-  No se debe invertir en reranker productivo sin antes resolver content gap o corpus coverage.")
        lines.append("")

    rec = summary.get("architecture_recommendation", "")
    if "reranker" in rec.lower() and "Milvus" not in rec and "Arango" not in rec:
        lines.append("- 📉 **No hay evidencia que justifique Milvus o ArangoDB** para resolver los fallos actuales.")
        lines.append("")

    lines.append("## Casos donde reranking ayudó")
    lines.append("")
    helped = [r for r in results if r.get("reranker_helped")]
    if helped:
        for h in helped:
            bn_pass = h.get("baseline_norm", {}).get("passed", False)
            rn_pass = h.get("reranked_norm", {}).get("passed", False)
            lines.append(f"- `{h['case_id']}` — {h['query'][:60]}")
            lines.append(f"  - Baseline (norm): {'PASS' if bn_pass else 'FAIL'} → Reranked: {'PASS' if rn_pass else 'FAIL'}")
            lines.append(f"  - Expected: {h.get('expected_concepts', [])}")
            lines.append("")
    else:
        lines.append("- Ningún caso mejoró con reranking.")
        lines.append("")

    lines.append("## Casos donde reranking no ayudó")
    lines.append("")
    not_helped = [r for r in results if not r.get("reranker_helped") and not r.get("baseline_norm", {}).get("passed", False)]
    if not_helped:
        for nh in not_helped:
            lines.append(f"- `{nh['case_id']}` — {nh['query'][:60]}")
            lines.append(f"  - Motivo: {nh.get('failure_classification', 'unknown')}")
            lines.append(f"  - Candidato correcto en top-N: {nh.get('correct_in_candidates', False)}")
            lines.append("")
    else:
        lines.append("- Todos los casos mejoraron o ya pasaban en baseline.")
        lines.append("")

    lines.append("## Casos donde el candidato correcto no estaba en top-N")
    lines.append("")
    no_candidate = [r for r in results if not r.get("correct_in_candidates")]
    if no_candidate:
        for nc in no_candidate:
            top1_title = nc.get("reranker_details", [{}])[0].get("title", "N/A") if nc.get("reranker_details") else "N/A"
            lines.append(f"- `{nc['case_id']}` — {nc['query'][:60]}")
            lines.append(f"  - Top-1 candidate: {top1_title}")
            lines.append(f"  - Expected: {nc.get('expected_concepts', [])}")
            lines.append("")
    else:
        lines.append("- El candidato correcto estuvo en top-N para todos los casos.")
        lines.append("")

    lines.append("## Decisión arquitectónica")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")

    if "reranker" in rec.lower():
        lines.append("### Siguiente paso recomendado:")
        lines.append("1. Implementar reranker controlado (cross-encoder ligero) en runtime sin cambiar backend vectorial.")
        lines.append("2. Validar con los mismos golden cases que este experimento antes de pasar a producción.")
        lines.append("3. No evaluar Milvus ni ArangoDB hasta que el reranker muestre límites de escala/latencia.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6g — Reranking Experiment. Deterministic oracle-lite reranker. "
                 f"No LLM, no Milvus, no ArangoDB, no production changes._")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reranking experiment — Fase 1.6g")
    parser.add_argument("--top-n", type=_validate_positive, default=20, help="Candidate pool size (1-50)")
    parser.add_argument("--top-k", type=_validate_positive, default=5, help="Evaluation window (1-50)")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--with-audit", action="store_true", help="Also run on rag_audit_failure_cases.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.top_n < args.top_k:
        print(f"ERROR: --top-n ({args.top_n}) must be >= --top-k ({args.top_k})", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(BP_FILE)
    if args.with_audit:
        audit_cases = load_cases(AUDIT_FILE)
        cases.extend(audit_cases)
        print(f"Loaded {len(load_cases(BP_FILE))} breaking point + {len(audit_cases)} audit cases")
    else:
        print(f"Loaded {len(cases)} breaking point cases from {BP_FILE}")

    if args.max_cases:
        cases = cases[:args.max_cases]
        print(f"Limited to {len(cases)} cases")

    if args.dry_run:
        print("DRY RUN — Validating cases and reranker logic (no DB, no OpenAI)")
        for c in cases:
            rerank_scores = compute_rerank_scores(
                [{"content_preview": "test", "title": "test", "node_path": "/test", "score": 0.5, "rank": 1}],
                c, args.top_n
            )
            e_norm = [normalize(e) for e in c.get("expected_concepts", [])]
            print(f"  [{c['case_id']}] expected={e_norm}")
        print(f"Total: {len(cases)} cases. Dry run OK.")
        sys.exit(0)

    dsn = _resolve_dsn()
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to DB: {dsn[:20]}...")
    key_preview = api_key[:8] + "..."
    print(f"OpenAI API key: {key_preview}")
    print(f"Running {len(cases)} cases against scope {args.knowledge_scope_code}")
    print(f"  Candidate pool: top-{args.top_n} | Evaluate: top-{args.top_k}")
    print("  Deterministic reranker · No LLM · No Milvus · No ArangoDB")
    print()

    import asyncio
    import psycopg
    from psycopg.rows import dict_row
    from modules.knowledge_ingestion.worker import KnowledgeIngestionWorker

    async def run_all():
        conn = await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row)
        await conn.set_autocommit(True)
        worker = KnowledgeIngestionWorker()

        case_results = []
        retrieval_latencies = []
        reranking_latencies = []

        try:
            for case in cases:
                case_id = case["case_id"]
                print(f"  [{case_id}] Retrieving top-{args.top_n}...", end=" ", flush=True)

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
                        limit=args.top_n,
                    )
                except Exception as e:
                    retrieval_latency = round((time.time() - t0) * 1000, 1)
                    retrieval_latencies.append(retrieval_latency)
                    print(f"ERROR: {str(e)[:80]}")
                    case_results.append({
                        "case_id": case_id,
                        "query": case["query"],
                        "category": case.get("category", ""),
                        "risk_level": case.get("risk_level", "unknown"),
                        "expected_concepts": case.get("expected_concepts", []),
                        "acceptable_concepts": case.get("acceptable_concepts", []),
                        "forbidden_concepts": case.get("forbidden_concepts", []),
                        "candidates": [],
                        "candidate_count": 0,
                        "retrieval_error": str(e)[:200],
                        "baseline_strict": {"passed": False, "score": SCORE_NO_RESULT},
                        "baseline_norm": {"passed": False, "score": SCORE_NO_RESULT},
                        "reranked_norm": {"passed": False, "score": SCORE_NO_RESULT},
                        "reranker_helped": False,
                        "correct_in_candidates": False,
                        "failure_classification": "retrieval_error",
                    })
                    continue

                retrieval_latency = round((time.time() - t0) * 1000, 1)
                retrieval_latencies.append(retrieval_latency)
                candidates = result.get("results", [])

                if not candidates:
                    print("0 results", flush=True)
                    case_results.append({
                        "case_id": case_id,
                        "query": case["query"],
                        "category": case.get("category", ""),
                        "risk_level": case.get("risk_level", "unknown"),
                        "expected_concepts": case.get("expected_concepts", []),
                        "acceptable_concepts": case.get("acceptable_concepts", []),
                        "forbidden_concepts": case.get("forbidden_concepts", []),
                        "candidates": [],
                        "candidate_count": 0,
                        "baseline_strict": evaluate_strict(case, {"results": []}, args.top_n),
                        "baseline_norm": evaluate_normalized(case, [], args.top_n),
                        "reranked_norm": evaluate_normalized(case, [], args.top_n),
                        "reranker_helped": False,
                        "correct_in_candidates": False,
                        "failure_classification": "no_results",
                    })
                    continue

                print(f"{len(candidates)} candidates", flush=True)

                t_rerank = time.time()
                rerank_scores = compute_rerank_scores(candidates, case, args.top_n)
                reranked_candidates = []
                for rs in rerank_scores:
                    original_rank = rs["original_rank"]
                    orig = next((c for c in candidates if c.get("rank") == original_rank), None)
                    if orig:
                        reranked_candidates.append(orig)

                reranked_order = reranked_candidates[:args.top_k] if len(reranked_candidates) >= args.top_k else reranked_candidates
                reranking_latency = round((time.time() - t_rerank) * 1000, 1)
                reranking_latencies.append(reranking_latency)

                baseline_top_k = candidates[:args.top_k] if len(candidates) >= args.top_k else candidates

                eval_strict = evaluate_strict(case, {"results": baseline_top_k}, args.top_n)
                eval_baseline_norm = evaluate_normalized(case, baseline_top_k, args.top_n)
                eval_reranked_norm = evaluate_normalized(case, reranked_order, args.top_n)

                correct_in_candidates = False
                expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
                for cand in candidates:
                    text = normalize(_content_text(cand))
                    if any(e in text for e in expected_norm):
                        correct_in_candidates = True
                        break

                reranker_helped = (not eval_baseline_norm["passed"]) and eval_reranked_norm["passed"]
                failure_classification = classify_failure(
                    case,
                    eval_baseline_norm["passed"],
                    eval_reranked_norm["passed"],
                    candidates,
                    reranked_order,
                ) if not eval_reranked_norm["passed"] else ""

                case_results.append({
                    "case_id": case_id,
                    "query": case["query"],
                    "category": case.get("category", ""),
                    "risk_level": case.get("risk_level", ""),
                    "pass_criteria": case.get("pass_criteria", "top5_contains_expected"),
                    "expected_concepts": case.get("expected_concepts", []),
                    "acceptable_concepts": case.get("acceptable_concepts", []),
                    "forbidden_concepts": case.get("forbidden_concepts", []),
                    "candidate_count": len(candidates),
                    "correct_in_candidates": correct_in_candidates,
                    "retrieval_latency_ms": retrieval_latency,
                    "reranking_latency_ms": reranking_latency,
                    "baseline_strict": eval_strict,
                    "baseline_norm": eval_baseline_norm,
                    "reranked_norm": eval_reranked_norm,
                    "reranker_helped": reranker_helped,
                    "reranker_details": rerank_scores,
                    "failure_classification": failure_classification,
                })

                status_strict = "PASS" if eval_strict["passed"] else "FAIL"
                status_norm_b = "PASS" if eval_baseline_norm["passed"] else "FAIL"
                status_norm_r = "PASS" if eval_reranked_norm["passed"] else "FAIL"
                flag = ""
                if reranker_helped:
                    flag = " 🎯 RERANKER HELPED"
                print(f"    strict={status_strict} base_norm={status_norm_b} reranked_norm={status_norm_r} | "
                      f"correct_in_candidates={correct_in_candidates} | "
                      f"candidates={len(candidates)} | {retrieval_latency}ms | {reranking_latency}ms{flag}")

        finally:
            await conn.close()

        return case_results, retrieval_latencies, reranking_latencies

    results, retrieval_latencies, reranking_latencies = asyncio.run(run_all())

    passed_strict = sum(1 for r in results if r.get("baseline_strict", {}).get("passed", False))
    passed_baseline_norm = sum(1 for r in results if r.get("baseline_norm", {}).get("passed", False))
    passed_reranked_norm = sum(1 for r in results if r.get("reranked_norm", {}).get("passed", False))

    high_risk_total = sum(1 for r in results if r.get("risk_level") == "high")
    high_risk_baseline_norm = sum(1 for r in results if r.get("risk_level") == "high" and r.get("baseline_norm", {}).get("passed", False))
    high_risk_reranked_norm = sum(1 for r in results if r.get("risk_level") == "high" and r.get("reranked_norm", {}).get("passed", False))

    improved = sum(1 for r in results if r.get("reranker_helped"))
    worsened = sum(1 for r in results if r.get("baseline_norm", {}).get("passed", False) and not r.get("reranked_norm", {}).get("passed", False))
    unchanged = len(results) - improved - worsened

    correct_in_topN = sum(1 for r in results if r.get("correct_in_candidates"))
    forbidden_baseline = sum(len(r.get("baseline_strict", {}).get("forbidden_in_top3", [])) for r in results)
    forbidden_reranked = sum(len(r.get("reranked_norm", {}).get("forbidden_in_top3", [])) for r in results)

    avg_retrieval_latency = round(sum(retrieval_latencies) / len(retrieval_latencies), 1) if retrieval_latencies else 0
    avg_reranking_latency = round(sum(reranking_latencies) / len(reranking_latencies), 1) if reranking_latencies else 0

    total_queries = len(results)
    total_failed_reranked = total_queries - passed_reranked_norm

    failure_classification: dict[str, int] = {}
    for r in results:
        fc = r.get("failure_classification", "")
        if fc:
            failure_classification[fc] = failure_classification.get(fc, 0) + 1

    baseline_rate_strict = round(passed_strict / total_queries * 100, 1) if total_queries else 0
    baseline_rate_norm = round(passed_baseline_norm / total_queries * 100, 1) if total_queries else 0
    reranked_rate_norm = round(passed_reranked_norm / total_queries * 100, 1) if total_queries else 0
    correct_in_topN_rate = round(correct_in_topN / total_queries * 100, 1) if total_queries else 0

    delta = reranked_rate_norm - baseline_rate_norm
    high_risk_delta = (high_risk_reranked_norm - high_risk_baseline_norm) if high_risk_total else 0

    if delta >= 15 and correct_in_topN_rate >= 80:
        rec = "A. pgvector + reranker es el próximo paso recomendado."
    elif delta >= 5 and correct_in_topN_rate >= 60:
        rec = "B. pgvector + reranker experimental debe evaluarse en runtime."
    elif correct_in_topN_rate < 60:
        rec = "C. El problema principal es recall/content gap. Agregar contenido y re-evaluar antes de decidir reranker."
    elif delta > 0:
        rec = "D. pgvector + reranker tiene efecto positivo marginal. Evaluar con más datos."
    else:
        rec = "E. pgvector sin reranker por ahora. El problema no es ranking sino recall o contenido."

    summary = {
        "experiment": "Reranking experiment — Fase 1.6g",
        "embedding_model": args.embedding_model,
        "embedding_version": args.embedding_version,
        "dimensions": args.dimensions,
        "knowledge_scope": args.knowledge_scope_code,
        "top_n": args.top_n,
        "top_k": args.top_k,
        "total_queries": total_queries,
        "baseline_pass_strict": passed_strict,
        "baseline_pass_rate_strict": baseline_rate_strict,
        "baseline_pass_norm": passed_baseline_norm,
        "baseline_pass_rate_norm": baseline_rate_norm,
        "reranked_pass_norm": passed_reranked_norm,
        "reranked_pass_rate_norm": reranked_rate_norm,
        "delta_pass_rate_norm": round(delta, 1),
        "high_risk_total": high_risk_total,
        "high_risk_baseline_pass_norm": high_risk_baseline_norm,
        "high_risk_reranked_pass_norm": high_risk_reranked_norm,
        "high_risk_delta": high_risk_delta,
        "cases_improved": improved,
        "cases_worsened": worsened,
        "cases_unchanged": unchanged,
        "correct_in_topN": correct_in_topN,
        "correct_in_topN_rate": correct_in_topN_rate,
        "forbidden_concepts_baseline": forbidden_baseline,
        "forbidden_concepts_reranked": forbidden_reranked,
        "avg_latency_retrieval_ms": avg_retrieval_latency,
        "avg_latency_reranking_ms": avg_reranking_latency,
        "total_failed_reranked": total_failed_reranked,
        "failure_classification": dict(sorted(failure_classification.items(), key=lambda x: -x[1])),
        "architecture_recommendation": rec,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"reranking_experiment_{timestamp}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": results,
        "latencies_ms": {
            "retrieval": retrieval_latencies,
            "reranking": reranking_latencies,
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_reranking_markdown(summary, results, args))
    print(f"Report saved: {md_path}")

    print()
    print("=" * 70)
    print("RERANKING EXPERIMENT SUMMARY")
    print("=" * 70)
    print(f"  Total cases:               {total_queries}")
    print(f"  Baseline strict:           {passed_strict}/{total_queries} ({baseline_rate_strict}%)")
    print(f"  Baseline norm:             {passed_baseline_norm}/{total_queries} ({baseline_rate_norm}%)")
    print(f"  Reranked norm:             {passed_reranked_norm}/{total_queries} ({reranked_rate_norm}%)")
    print(f"  Delta (reranked - norm):   {delta:+.1f}%")
    print(f"  High-risk baseline norm:   {high_risk_baseline_norm}/{high_risk_total}")
    print(f"  High-risk reranked:        {high_risk_reranked_norm}/{high_risk_total}")
    print(f"  Cases improved:            {improved}")
    print(f"  Cases worsened:            {worsened}")
    print(f"  Correct in top-N:          {correct_in_topN}/{total_queries} ({correct_in_topN_rate}%)")
    print(f"  Forbidden baseline:        {forbidden_baseline}")
    print(f"  Forbidden reranked:        {forbidden_reranked}")
    print(f"  Avg retrieval latency:     {avg_retrieval_latency}ms")
    print(f"  Avg reranking latency:     {avg_reranking_latency}ms")
    print()
    print(f"  Recommendation: {rec}")
    print()

    if summary["failure_classification"]:
        print("  Failure classification (post-reranking):")
        for reason, count in summary["failure_classification"].items():
            print(f"    {reason}: {count}")
    print()


if __name__ == "__main__":
    main()

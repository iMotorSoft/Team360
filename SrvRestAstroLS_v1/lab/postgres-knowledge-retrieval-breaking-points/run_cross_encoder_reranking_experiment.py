#!/usr/bin/env python3
"""Cross-encoder reranking experiment — Fase 1.6i.

Tests whether a real cross-encoder reranker (semantic, not oracle, not lexical)
can close the gap between pgvector baseline (44%) and oracle-lite (68%).

This experiment compares:
  A. Baseline pgvector top-5
  B. Non-oracle lexical reranker (Fase 1.6h, 44%)
  C. Cross-encoder reranker (pgvector top-N + cross-encoder scoring)

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_cross_encoder_reranking_experiment.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_cross_encoder_reranking_experiment.py --top-n 20 --top-k 5

Dependencies (optional lab):
  sentence-transformers, torch, transformers
  Install with: uv add sentence-transformers torch transformers
  Only needed to actually run the experiment; the script fails gracefully otherwise.

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

# ---------------------------------------------------------------------------
# Dependencies detection — fail early with clear message
# ---------------------------------------------------------------------------
CROSS_ENCODER_DEPS = {
    "sentence_transformers": "sentence-transformers",
    "torch": "torch",
    "transformers": "transformers",
}

_missing_deps: list[str] = []
for import_name, package_name in CROSS_ENCODER_DEPS.items():
    try:
        __import__(import_name)
    except ImportError:
        _missing_deps.append(package_name)

CROSS_ENCODER_AVAILABLE = len(_missing_deps) == 0

# ---------------------------------------------------------------------------
# Shared imports from oracle-lite / non-oracle experiments
# ---------------------------------------------------------------------------
LAB_DIR = Path(__file__).parent
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
BP_FILE = LAB_DIR / "golden_cases" / "breaking_point_cases.json"
RESULTS_DIR = LAB_DIR / "results"

sys.path.insert(0, str(BACKEND_DIR))

from run_reranking_experiment import (
    normalize, _content_text, _build_result_text,
    evaluate_strict, evaluate_normalized,
    passed_condition, _resolve_dsn, _validate_positive, load_cases,
    SCORE_NO_RESULT,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_CANDIDATE_CHARS = 1600

_NORM_WS = re.compile(r"\s+")
_RE_ACCENT = re.compile(r"[\u0300-\u036f]")


def normalize_light(text: str) -> str:
    t = text.lower()
    t = t.replace("_", " ").replace("-", " ")
    t = _NORM_WS.sub(" ", t).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    return _RE_ACCENT.sub("", nfkd)


STOPWORDS = {
    "a", "ante", "bajo", "cabe", "con", "contra", "de", "del", "desde",
    "durante", "el", "en", "entre", "hacia", "hasta", "la", "las", "le",
    "lo", "los", "me", "mediante", "mi", "mis", "nos", "o", "os", "para",
    "por", "porque", "que", "se", "segun", "sin", "so", "sobre", "su",
    "sus", "te", "tras", "tu", "tus", "un", "una", "unas", "unos", "y",
    "ya", "no", "si", "al", "este", "esta", "esto", "estos", "estas",
    "ese", "esa", "eso", "esos", "esas", "aquel", "aquella", "aquello",
    "a", "bien", "mas", "muy", "cada", "todo", "toda", "tanto", "cual",
    "quien", "cuando", "donde", "como", "cuan", "the", "is", "are", "to",
    "in", "it", "of", "and", "or", "for", "with", "on", "at", "by",
    "an", "be", "do", "does", "did", "has", "have", "been", "was", "were",
    "can", "will", "would", "could", "should", "may", "might", "shall",
}


def tokenize(text: str) -> list[str]:
    t = normalize_light(text)
    tokens = re.findall(r"[a-zA-Z0-9\xc0-\xff]+", t)
    return [tok for tok in tokens if tok not in STOPWORDS and len(tok) > 1]


# ---------------------------------------------------------------------------
# Lexical overlap (used for tiebreaking and baseline comparison)
# ---------------------------------------------------------------------------
def lexical_overlap(query: str, candidate_text: str) -> float:
    q_tokens = set(tokenize(query))
    c_tokens = set(tokenize(candidate_text))
    if not q_tokens or not c_tokens:
        return 0.0
    intersect = q_tokens & c_tokens
    union = q_tokens | c_tokens
    jaccard = len(intersect) / len(union) if union else 0.0
    coverage = len(intersect & q_tokens) / len(q_tokens) if q_tokens else 0.0
    return (jaccard + coverage) / 2.0


# ---------------------------------------------------------------------------
# Cross-encoder scoring
# ---------------------------------------------------------------------------
def _build_candidate_text(chunk: dict, max_chars: int) -> str:
    title = chunk.get("title") or ""
    node_path = chunk.get("node_path") or ""
    content = chunk.get("content_preview") or ""
    parts = [title, node_path, content]
    text = " | ".join(p for p in parts if p)
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    return text


def compute_cross_encoder_scores(
    query: str,
    candidates: list[dict],
    model: Any,
    max_chars: int = _DEFAULT_CANDIDATE_CHARS,
    batch_size: int = 32,
) -> list[dict]:
    texts = [_build_candidate_text(c, max_chars) for c in candidates]
    pairs = [[query, t] for t in texts]
    scores = model.predict(pairs, batch_size=batch_size).tolist()

    scored = []
    for i, chunk in enumerate(candidates):
        ce_score = float(scores[i])
        original_rank = chunk.get("rank", 0)
        vector_score = chunk.get("score") or 0.0
        scored.append({
            "chunk_id": chunk.get("chunk_id", ""),
            "title": chunk.get("title", ""),
            "original_rank": original_rank,
            "vector_score": round(vector_score, 6),
            "cross_encoder_score": round(ce_score, 6),
        })

    scored.sort(key=lambda x: x["cross_encoder_score"], reverse=True)

    for new_rank, s in enumerate(scored, 1):
        s["reranked_rank"] = new_rank

    return scored


# ---------------------------------------------------------------------------
# Failure classification (same classification as non-oracle)
# ---------------------------------------------------------------------------
def classify_cross_encoder_failure(
    case: dict,
    query: str,
    candidates: list[dict],
    reranked_results: list[dict],
) -> str:
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

    return "reranker_not_powerful_enough"


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def generate_cross_encoder_markdown(summary: dict, results: list[dict], args: argparse.Namespace) -> str:
    lines = []

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# Cross-encoder reranking experiment — Fase 1.6i")
    lines.append("")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Candidate pool (top-N):** {args.top_n}")
    lines.append(f"**Evaluation (top-K):** {args.top_k}")
    lines.append(f"**Cross-encoder model:** {args.model_name}")
    lines.append(f"**Device:** {args.device}")
    lines.append(f"**Max candidate chars:** {args.max_candidate_chars}")
    lines.append(f"**Embedding version:** {args.embedding_version}")
    lines.append(f"**Scope:** {args.knowledge_scope_code}")
    lines.append("")

    bp = summary["baseline_pass_rate_norm"]
    cp = summary["cross_encoder_pass_rate_norm"]
    delta_ce = round(cp - bp, 1)
    non_oracle_rate = summary.get("non_oracle_pass_rate", 44.0)
    oracle_rate = summary.get("oracle_lite_pass_rate", 68.0)
    gap_to_oracle = round(oracle_rate - cp, 1)

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Baseline normalizado:** {summary['baseline_pass_norm']}/{summary['total_queries']} ({bp}%)")
    lines.append(f"- **Non-oracle lexical (1.6h):** {non_oracle_rate}%")
    lines.append(f"- **Oracle-lite (1.6g, techo):** {oracle_rate}%")
    lines.append(f"- **Cross-encoder reranked:** {summary['cross_encoder_pass_norm']}/{summary['total_queries']} ({cp}%)")
    lines.append(f"- **Delta (cross-encoder - baseline):** {delta_ce:+.1f}%")
    lines.append(f"- **Delta (cross-encoder - non-oracle):** {round(cp - non_oracle_rate, 1):+.1f}%")
    lines.append(f"- **Gap to oracle:** {gap_to_oracle:+.1f}%")
    lines.append(f"- **High-risk baseline norm:** {summary['high_risk_baseline_pass_norm']}/{summary['high_risk_total']}")
    lines.append(f"- **High-risk cross-encoder:** {summary['high_risk_cross_encoder_pass_norm']}/{summary['high_risk_total']}")
    lines.append(f"- **Casos mejorados (vs baseline):** {summary['cases_improved']}")
    lines.append(f"- **Casos empeorados (vs baseline):** {summary['cases_worsened']}")
    lines.append(f"- **Casos sin cambio:** {summary['cases_unchanged']}")
    lines.append(f"- **Correct candidate in top-N:** {summary['correct_in_topN']}/{summary['total_queries']} ({summary['correct_in_topN_rate']}%)")
    lines.append(f"- **Conceptos prohibidos baseline:** {summary['forbidden_concepts_baseline']}")
    lines.append(f"- **Conceptos prohibidos cross-encoder:** {summary['forbidden_concepts_cross_encoder']}")
    lines.append(f"- **Latencia retrieval / cross-encoder:** {summary['avg_latency_retrieval_ms']}ms / {summary['avg_latency_cross_encoder_ms']}ms")
    lines.append("")

    lines.append("## Comparación con experiments anteriores")
    lines.append("")
    lines.append("| Experimento | Pass rate | Usa golden answers? | Tipo de reranker |")
    lines.append("|------------|-----------|---------------------|------------------|")
    lines.append(f"| Baseline pgvector | {bp}% | — | — |")
    lines.append(f"| Non-oracle lexical (1.6h) | {non_oracle_rate}% | No | Léxico (6 señales) |")
    lines.append(f"| Oracle-lite (1.6g) | {oracle_rate}% | **Sí** (expected/concepts) | Determinístico-oráculo |")
    lines.append(f"| Cross-encoder (1.6i) | {cp}% | No | Semántico (modelo) |")
    lines.append("")
    lines.append(f"El gap de **{gap_to_oracle}pp** entre cross-encoder y oracle-lite")
    lines.append("representa lo que aún falta: un cross-encoder exclusivo de producción o")
    lines.append("más candidates en el pool.")
    lines.append("")

    fc = summary.get("failure_classification", {})
    if fc:
        lines.append("## Clasificación de fallos post-cross-encoder")
        lines.append("")
        for reason, count in sorted(fc.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_cross_encoder"] * 100, 1) if summary["total_failed_cross_encoder"] else 0
            lines.append(f"- **{reason}:** {count} ({pct}%)")
        lines.append("")

    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Casos mejorados")
    lines.append("")
    helped = [r for r in results if r.get("reranker_helped")]
    if helped:
        for h in helped:
            bn_pass = h.get("baseline_norm", {}).get("passed", False)
            rn_pass = h.get("reranked_norm", {}).get("passed", False)
            lines.append(f"- `{h['case_id']}` — {h['query'][:60]}")
            lines.append(f"  - Baseline: {'PASS' if bn_pass else 'FAIL'} → Cross-encoder: {'PASS' if rn_pass else 'FAIL'}")
            lines.append("")
    else:
        lines.append("- Ningún caso mejoró con cross-encoder.")
        lines.append("")

    lines.append("## Casos empeorados")
    lines.append("")
    worsened = [r for r in results if r.get("baseline_norm", {}).get("passed", False) and not r.get("reranked_norm", {}).get("passed", False)]
    if worsened:
        for w in worsened:
            lines.append(f"- `{w['case_id']}` — {w['query'][:60]}")
            lines.append("")
    else:
        lines.append("- Ningún caso empeoró.")
        lines.append("")

    lines.append("## Casos donde el candidato correcto no estaba en top-N")
    lines.append("")
    no_cand = [r for r in results if not r.get("correct_in_candidates")]
    if no_cand:
        for nc in no_cand:
            lines.append(f"- `{nc['case_id']}` — {nc['query'][:60]}")
            lines.append("")
    else:
        lines.append("- Todos los casos tenían candidato correcto en top-N.")
        lines.append("")

    lines.append("## Latencia y costo operativo")
    lines.append("")
    lines.append(f"- **Retrieval pgvector (avg):** {summary['avg_latency_retrieval_ms']}ms")
    lines.append(f"- **Cross-encoder por caso (avg):** {summary['avg_latency_cross_encoder_ms']}ms")
    lines.append(f"- **Total por query:** {round(summary['avg_latency_retrieval_ms'] + summary['avg_latency_cross_encoder_ms'], 1)}ms")
    lines.append(f"- **Device:** {args.device}")
    lines.append(f"- **Modelo:** {args.model_name}")
    lines.append("")
    lines.append("El cross-encoder es más lento que el reranker léxico pero más rápido que")
    lines.append("un LLM. Se puede bajar latencia con batch, GPU o modelo más liviano.")
    lines.append("No usa API paga (inferencia local).")
    lines.append("")

    lines.append("## Decisión arquitectónica")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")
    lines.append("### Implicaciones")
    lines.append("")
    lines.append("- No se justifica Milvus ni ArangoDB para resolver ranking fino.")
    lines.append("- Si hay contenido faltante (correct_not_in_candidates), ni el cross-encoder lo resuelve.")
    lines.append("- El límite actual es coverage del corpus (8/25 casos), no el backend de ranking.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6i — Cross-encoder Reranking Experiment. "
                 f"Model: {args.model_name}. "
                 f"No LLM, no Milvus, no ArangoDB, no production changes._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dependency check helper
# ---------------------------------------------------------------------------
def print_blocked_status(args: argparse.Namespace) -> None:
    print("=" * 70)
    print("CROSS-ENCODER RERANKING EXPERIMENT — Fase 1.6i")
    print("=" * 70)
    print()
    print("  STATUS: BLOCKED")
    print()
    print(f"  Missing dependencies: {', '.join(_missing_deps)}")
    print()
    print("  The cross-encoder experiment requires optional ML packages")
    print("  that are not installed in the current environment.")
    print()
    print("  To install them, run:")
    print()
    print("    cd SrvRestAstroLS_v1/backend")
    print('    uv add "sentence-transformers>=3.0"')
    print('    uv add "torch>=2.0"')
    print('    uv add "transformers>=4.40"')
    print()
    print("  These packages add ~1-3GB to the environment (torch + models).")
    print("  They are NOT required for production. They are lab-only dependencies.")
    print()
    print("  Once installed, run:")
    print(f"    uv run python lab/postgres-knowledge-retrieval-breaking-points/{Path(__file__).name} \\")
    print("      --top-n {args.top_n} --top-k {args.top_k} --model-name {args.model_name}")
    print()
    print("  Parameters (all prepared, just need the deps):")
    print(f"    --top-n:                {args.top_n}")
    print(f"    --top-k:                {args.top_k}")
    print(f"    --model-name:           {args.model_name}")
    print(f"    --max-candidate-chars:  {args.max_candidate_chars}")
    print(f"    --device:               {args.device}")
    print(f"    --max-cases:            {args.max_cases}")
    print(f"    --output-prefix:        {args.output_prefix}")
    print()
    print("  The experiment runner and report generator are ready.")
    print("  No changes to pyproject.toml were made.")
    print("  No models were downloaded.")
    print("  No secrets were hardcoded.")
    print()
    print("  Note: BAAI/bge-reranker-v2-m3 is ~1.1GB.")
    print("  First run will download it automatically via sentence-transformers.")
    print("  To avoid download at runtime, pre-download with:")
    print("    uv run python -c \"from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')\"")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-encoder reranking experiment — Fase 1.6i")
    parser.add_argument("--top-n", type=_validate_positive, default=20, help="Candidate pool size (1-50)")
    parser.add_argument("--top-k", type=_validate_positive, default=5, help="Evaluation window (1-50)")
    parser.add_argument("--model-name", default="BAAI/bge-reranker-v2-m3",
                        help="Cross-encoder model name (default: BAAI/bge-reranker-v2-m3)")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"],
                        help="Device for cross-encoder inference")
    parser.add_argument("--max-candidate-chars", type=int, default=_DEFAULT_CANDIDATE_CHARS,
                        help="Max characters per candidate text sent to cross-encoder")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--output-prefix", default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.top_n < args.top_k:
        print(f"ERROR: --top-n ({args.top_n}) must be >= --top-k ({args.top_k})", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------
    if not CROSS_ENCODER_AVAILABLE:
        print_blocked_status(args)
        sys.exit(0)

    # ------------------------------------------------------------------
    # Import cross-encoder only if available
    # ------------------------------------------------------------------
    from sentence_transformers import CrossEncoder

    cases = load_cases(BP_FILE)
    print(f"Loaded {len(cases)} breaking point cases from {BP_FILE}")

    if args.max_cases:
        cases = cases[:args.max_cases]
        print(f"Limited to {len(cases)} cases")

    if args.dry_run:
        print("DRY RUN — Validating cross-encoder logic (no DB, no OpenAI)")
        dummy_candidates = [
            {"content_preview": "planned extension step to action test", "title": "Test",
             "node_path": "/objeciones", "score": 0.65, "rank": 1},
        ]
        model = CrossEncoder(args.model_name)
        scores = compute_cross_encoder_scores(
            cases[0]["query"], dummy_candidates, model,
            max_chars=args.max_candidate_chars,
        )
        top = scores[0] if scores else None
        ce = top["cross_encoder_score"] if top else 0
        print(f"  [{cases[0]['case_id']}] query={cases[0]['query'][:40]}... ce_score={ce}")
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
    print(f"  Cross-encoder model: {args.model_name} | Device: {args.device}")
    print(f"  No LLM · No Milvus · No ArangoDB")
    print()

    print("Loading cross-encoder model...", flush=True)
    t_model = time.time()
    model = CrossEncoder(args.model_name, device=args.device)
    model_load_latency = round((time.time() - t_model) * 1000, 1)
    print(f"  Model loaded in {model_load_latency}ms")
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
                query = case["query"]
                print(f"  [{case_id}] Retrieving top-{args.top_n}...", end=" ", flush=True)

                t0 = time.time()
                try:
                    result = await worker.retrieve_knowledge_chunks(
                        conn=conn,
                        organization_code=args.organization_code,
                        workspace_code=args.workspace_code,
                        knowledge_scope_code=args.knowledge_scope_code,
                        query=query,
                        embedding_model=args.embedding_model,
                        embedding_dimensions=args.dimensions,
                        embedding_version=args.embedding_version,
                        limit=args.top_n,
                    )
                except Exception as e:
                    lat = round((time.time() - t0) * 1000, 1)
                    retrieval_latencies.append(lat)
                    print(f"ERROR: {str(e)[:80]}")
                    case_results.append({
                        "case_id": case_id, "query": query,
                        "category": case.get("category", ""),
                        "risk_level": case.get("risk_level", "unknown"),
                        "expected_concepts": case.get("expected_concepts", []),
                        "candidate_count": 0, "retrieval_error": str(e)[:200],
                        "baseline_strict": {"passed": False, "score": SCORE_NO_RESULT},
                        "baseline_norm": {"passed": False, "score": SCORE_NO_RESULT},
                        "reranked_norm": {"passed": False, "score": SCORE_NO_RESULT},
                        "reranker_helped": False, "correct_in_candidates": False,
                        "failure_classification": "retrieval_error",
                    })
                    continue

                retrieval_latency = round((time.time() - t0) * 1000, 1)
                retrieval_latencies.append(retrieval_latency)
                candidates = result.get("results", [])

                if not candidates:
                    print("0 results", flush=True)
                    case_results.append({
                        "case_id": case_id, "query": query,
                        "category": case.get("category", ""),
                        "risk_level": case.get("risk_level", "unknown"),
                        "expected_concepts": case.get("expected_concepts", []),
                        "candidate_count": 0,
                        "baseline_strict": evaluate_strict(case, {"results": []}, args.top_n),
                        "baseline_norm": evaluate_normalized(case, [], args.top_n),
                        "reranked_norm": evaluate_normalized(case, [], args.top_n),
                        "reranker_helped": False, "correct_in_candidates": False,
                        "failure_classification": "no_results",
                    })
                    continue

                print(f"{len(candidates)} candidates", flush=True)

                t_rerank = time.time()
                ce_scores = compute_cross_encoder_scores(
                    query, candidates, model,
                    max_chars=args.max_candidate_chars,
                )
                reranked = []
                for rs in ce_scores:
                    orig = next((c for c in candidates if c.get("rank") == rs["original_rank"]), None)
                    if orig:
                        reranked.append(orig)
                reranked_order = reranked[:args.top_k] if len(reranked) >= args.top_k else reranked
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
                failure_classification = ""
                if not eval_reranked_norm["passed"]:
                    failure_classification = classify_cross_encoder_failure(
                        case, query, candidates, reranked_order,
                    )

                case_results.append({
                    "case_id": case_id, "query": query,
                    "category": case.get("category", ""),
                    "risk_level": case.get("risk_level", ""),
                    "pass_criteria": case.get("pass_criteria", "top5_contains_expected"),
                    "expected_concepts": case.get("expected_concepts", []),
                    "candidate_count": len(candidates),
                    "correct_in_candidates": correct_in_candidates,
                    "retrieval_latency_ms": retrieval_latency,
                    "reranking_latency_ms": reranking_latency,
                    "baseline_strict": eval_strict,
                    "baseline_norm": eval_baseline_norm,
                    "reranked_norm": eval_reranked_norm,
                    "reranker_helped": reranker_helped,
                    "reranker_details": ce_scores,
                    "failure_classification": failure_classification,
                })

                status_s = "PASS" if eval_strict["passed"] else "FAIL"
                status_b = "PASS" if eval_baseline_norm["passed"] else "FAIL"
                status_r = "PASS" if eval_reranked_norm["passed"] else "FAIL"
                flag = " 🎯" if reranker_helped else ""
                print(f"    strict={status_s} base={status_b} ce={status_r} | "
                      f"in_candidates={correct_in_candidates} | "
                      f"candidates={len(candidates)} | {retrieval_latency}ms | {reranking_latency}ms{flag}")

        finally:
            await conn.close()
        return case_results, retrieval_latencies, reranking_latencies

    results, retrieval_latencies, reranking_latencies = asyncio.run(run_all())

    passed_strict = sum(1 for r in results if r.get("baseline_strict", {}).get("passed", False))
    passed_baseline_norm = sum(1 for r in results if r.get("baseline_norm", {}).get("passed", False))
    passed_reranked_norm = sum(1 for r in results if r.get("reranked_norm", {}).get("passed", False))

    high_risk_total = sum(1 for r in results if r.get("risk_level") == "high")
    high_risk_base = sum(1 for r in results if r.get("risk_level") == "high" and r.get("baseline_norm", {}).get("passed", False))
    high_risk_rerank = sum(1 for r in results if r.get("risk_level") == "high" and r.get("reranked_norm", {}).get("passed", False))

    improved = sum(1 for r in results if r.get("reranker_helped"))
    worsened = sum(1 for r in results if r.get("baseline_norm", {}).get("passed", False) and not r.get("reranked_norm", {}).get("passed", False))
    unchanged = len(results) - improved - worsened

    correct_in_topN = sum(1 for r in results if r.get("correct_in_candidates"))
    forbidden_base = sum(len(r.get("baseline_strict", {}).get("forbidden_in_top3", [])) for r in results)
    forbidden_rerank = sum(len(r.get("reranked_norm", {}).get("forbidden_in_top3", [])) for r in results)

    avg_ret_lat = round(sum(retrieval_latencies) / len(retrieval_latencies), 1) if retrieval_latencies else 0
    avg_rer_lat = round(sum(reranking_latencies) / len(reranking_latencies), 1) if reranking_latencies else 0

    total = len(results)
    total_failed = total - passed_reranked_norm

    failure_classification: dict[str, int] = {}
    for r in results:
        fc = r.get("failure_classification", "")
        if fc:
            failure_classification[fc] = failure_classification.get(fc, 0) + 1

    bp_rate = round(passed_baseline_norm / total * 100, 1) if total else 0
    cp_rate = round(passed_reranked_norm / total * 100, 1) if total else 0
    delta_ce = cp_rate - bp_rate
    correct_rate = round(correct_in_topN / total * 100, 1) if total else 0

    non_oracle_rate = 44.0
    oracle_lite_rate = 68.0

    gap_to_non_oracle = round(cp_rate - non_oracle_rate, 1)
    gap_to_oracle = round(oracle_lite_rate - cp_rate, 1)

    # Decision rules
    if cp_rate >= 60 and gap_to_oracle <= 10:
        rec = "B. Diseñar cross-encoder runtime experimental — el cross-encoder se acerca al techo oracle (gap <=10pp)."
    elif cp_rate >= 55 and high_risk_rerank >= high_risk_base:
        rec = "H. Cross-encoder mejora significativamente — diseñar reranker runtime controlado."
    elif cp_rate > non_oracle_rate + 5:
        rec = "C. Probar modelo más liviano — cross-encoder mejora pero deja margen; optimizar latencia/costo."
    elif cp_rate > bp_rate:
        rec = "D. Cross-encoder tiene efecto positivo marginal — evaluar con más datos o content coverage."
    elif correct_rate < 60:
        rec = "E. Mejorar content coverage primero — el candidato correcto no está en top-N."
    else:
        rec = "A. No usar reranker todavía — cross-encoder no mejora significativamente sobre baseline."

    if correct_rate < 60:
        rec += " Milvus no justificado por ranking fino. ArangoDB no justificado por ranking fino."
    elif "B" in rec or "H" in rec:
        rec += " Milvus no es necesario para ranking fino (se resuelve con cross-encoder). ArangoDB no es necesario para ranking."

    summary = {
        "experiment": "Cross-encoder reranking experiment — Fase 1.6i",
        "model_name": args.model_name,
        "device": args.device,
        "max_candidate_chars": args.max_candidate_chars,
        "embedding_model": args.embedding_model,
        "embedding_version": args.embedding_version,
        "dimensions": args.dimensions,
        "knowledge_scope": args.knowledge_scope_code,
        "top_n": args.top_n,
        "top_k": args.top_k,
        "total_queries": total,
        "baseline_pass_strict": passed_strict,
        "baseline_pass_rate_strict": round(passed_strict / total * 100, 1) if total else 0,
        "baseline_pass_norm": passed_baseline_norm,
        "baseline_pass_rate_norm": bp_rate,
        "cross_encoder_pass_norm": passed_reranked_norm,
        "cross_encoder_pass_rate_norm": cp_rate,
        "delta_pass_rate_norm": round(delta_ce, 1),
        "non_oracle_pass_rate": non_oracle_rate,
        "oracle_lite_pass_rate": oracle_lite_rate,
        "gap_to_non_oracle": gap_to_non_oracle,
        "gap_to_oracle": gap_to_oracle,
        "high_risk_total": high_risk_total,
        "high_risk_baseline_pass_norm": high_risk_base,
        "high_risk_cross_encoder_pass_norm": high_risk_rerank,
        "cases_improved": improved,
        "cases_worsened": worsened,
        "cases_unchanged": unchanged,
        "correct_in_topN": correct_in_topN,
        "correct_in_topN_rate": correct_rate,
        "forbidden_concepts_baseline": forbidden_base,
        "forbidden_concepts_cross_encoder": forbidden_rerank,
        "avg_latency_retrieval_ms": avg_ret_lat,
        "avg_latency_cross_encoder_ms": avg_rer_lat,
        "model_load_latency_ms": model_load_latency if 'model_load_latency' in dir() else 0,
        "total_failed_cross_encoder": total_failed,
        "failure_classification": dict(sorted(failure_classification.items(), key=lambda x: -x[1])),
        "architecture_recommendation": rec,
        "dependencies_available": True,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"cross_encoder_reranking_{ts}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": results,
        "latencies_ms": {"retrieval": retrieval_latencies, "cross_encoder": reranking_latencies},
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_cross_encoder_markdown(summary, results, args))
    print(f"Report saved: {md_path}")

    print()
    print("=" * 70)
    print("CROSS-ENCODER RERANKING EXPERIMENT SUMMARY")
    print("=" * 70)
    print(f"  Total cases:                  {total}")
    print(f"  Baseline strict:              {passed_strict}/{total} ({summary['baseline_pass_rate_strict']}%)")
    print(f"  Baseline norm:                {passed_baseline_norm}/{total} ({bp_rate}%)")
    print(f"  Non-oracle lexical (1.6h):    {non_oracle_rate}%")
    print(f"  Oracle-lite (1.6g, techo):    {oracle_lite_rate}%")
    print(f"  Cross-encoder reranked:       {passed_reranked_norm}/{total} ({cp_rate}%)")
    print(f"  Delta vs baseline:            {delta_ce:+.1f}%")
    print(f"  Delta vs non-oracle:          {gap_to_non_oracle:+.1f}%")
    print(f"  Gap to oracle:                {gap_to_oracle:+.1f}pp")
    print(f"  High-risk base/ce:            {high_risk_base}/{high_risk_rerank} (of {high_risk_total})")
    print(f"  Cases improved/worsened:      {improved}/{worsened}")
    print(f"  Correct in top-N:             {correct_in_topN}/{total} ({correct_rate}%)")
    print(f"  Forbidden base/ce:            {forbidden_base}/{forbidden_rerank}")
    print(f"  Avg retrieval/ce:             {avg_ret_lat}ms / {avg_rer_lat}ms")
    print(f"  Model:                        {args.model_name} on {args.device}")
    print()
    print(f"  Recommendation: {rec}")
    print()
    if failure_classification:
        print("  Failure classification (post-cross-encoder):")
        for reason, count in failure_classification.items():
            print(f"    {reason}: {count}")
    print()


if __name__ == "__main__":
    main()

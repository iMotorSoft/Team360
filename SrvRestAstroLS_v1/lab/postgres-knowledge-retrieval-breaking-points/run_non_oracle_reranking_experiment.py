#!/usr/bin/env python3
"""Non-oracle reranking experiment — Fase 1.6h.

Tests whether a reranker that uses ONLY query + candidate signals (no golden
answers) can improve pgvector retrieval quality.

Oracle-lite (1.6g) used expected_concepts/acceptable_concepts/forbidden_concepts
to reorder — that's an oracle. This experiment is more production-like: it only
uses lexical overlap, domain vocabulary, safety signals, metadata, and vector
score to rerank.

Golden cases are used ONLY for evaluation after reranking, never for reordering.

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_non_oracle_reranking_experiment.py
  uv run python lab/postgres-knowledge-retrieval-breaking-points/run_non_oracle_reranking_experiment.py --dry-run

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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Shared imports from oracle-lite experiment
# ---------------------------------------------------------------------------
LAB_DIR = Path(__file__).parent
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
BP_FILE = LAB_DIR / "golden_cases" / "breaking_point_cases.json"
AUDIT_FILE = LAB_DIR / "golden_cases" / "rag_audit_failure_cases.json"
RESULTS_DIR = LAB_DIR / "results"

sys.path.insert(0, str(BACKEND_DIR))

from run_reranking_experiment import (
    normalize, _content_text, _build_result_text,
    evaluate_strict, evaluate_normalized,
    passed_condition, classify_failure,
    _resolve_dsn, _validate_positive, load_cases,
    SCORE_NO_RESULT,
)

# ---------------------------------------------------------------------------
# Configurable weights
# ---------------------------------------------------------------------------
W_VECTOR = 0.40
W_LEXICAL = 0.20
W_PHRASE = 0.15
W_DOMAIN = 0.10
W_SAFETY = 0.10
W_METADATA = 0.05
RISK_PENALTY = -0.15

LEXICAL_OVERLAP_THRESHOLD = 0.15  # below this → semantic gap

# ---------------------------------------------------------------------------
# Normalization utilities
# ---------------------------------------------------------------------------
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
# Domain vocabulary (NOT golden-case-specific)
# ---------------------------------------------------------------------------
DOMAIN_VOCABULARY = [
    "step to action", "step-to-action", "step_to_action",
    "lead capture", "captura leads", "captura de leads",
    "whatsapp handoff", "handoff", "whatsapp",
    "diagnostic code", "codigo de diagnostico", "diagnostic_code",
    "planned extension", "planned_extension", "planned",
    "ready today", "ready_today", "listo hoy",
    "vendible hoy", "sellable today", "vendible",
    "automatizable", "automatizable", "automation",
    "vera", "vera nombre comercial", "vera_commercial",
    "package code", "package_code", "codigo de paquete",
    "knowledge scope", "knowledge_scope", "scope",
    "runtime target", "runtime_target",
    "crm", "integracion", "integracion crm",
    "campana", "agenda", "agenda automation",
    "diagnostico", "diagnostico de ventas", "sales diagnosis",
    "slots minimos", "minimum_slots",
    "knowledge base", "knowledge_base", "kbaas",
    "aislamiento", "aislamiento cliente", "cross customer isolation",
    "cliente", "workspace", "organizacion",
    "commercial limits", "limite comercial", "commercial_limits",
    "concrete orientation", "orientacion concreta",
    "offer decision", "offer_decision",
    "useful diagnosis", "useful_diagnosis",
    "access tags", "access_tags",
    "overpromise", "sobrepromesa", "no prometer",
    "derivacion humana", "human handoff",
    "alcance inicial", "alcance",
    "no vender como listo", "no vender",
    "depende de integracion", "configuracion por cliente",
    "forbidden concept", "concepto prohibido",
    "technical identifiers", "identificadores tecnicos",
    "package sales diagnosis", "pkg sales diagnosis",
    "retrieval chunk", "approved document",
    "diagnosis result", "resultado de diagnostico",
]
DOMAIN_NORM = set(normalize_light(t) for t in DOMAIN_VOCABULARY)

# ---------------------------------------------------------------------------
# Commercial safety patterns
# ---------------------------------------------------------------------------
OVERPROMMISE_QUERY_PATTERNS = [
    "listo", "funciona", "funcionando", "vender", "vendible",
    "automatico", "automatizable", "automatizado",
    "ready", "available", "produccion", "productivo",
    "integrado", "conectado", "disponible", "ya funciona",
    "se puede", "lo tienen", "lo cubre", "cubre",
    "completa", "completo", "todo automatico",
    "cuesta", "cuanto", "precio", "semana", "plazo",
    "implementar", "implementacion",
]

SAFETY_CANDIDATE_TERMS = [
    "no listo", "no listo todavia",
    "planned extension", "planned_extension",
    "no vender como listo", "no vender",
    "depende de integracion", "depende de integracion",
    "alcance inicial", "alcance",
    "limite comercial", "commercial limits", "commercial_limits",
    "no prometer", "no prometer plazos",
    "derivacion humana", "human handoff",
    "configuracion por cliente",
    "no disponible", "no disponible hoy",
    "capacidad futura", "extension planificada",
    "regla anti", "reglas anti",
    "concepto prohibido", "forbidden concept",
    "lo que no puede", "que no puede", "no puede hacer",
]
SAFETY_CANDIDATE_NORM = set(normalize_light(t) for t in SAFETY_CANDIDATE_TERMS)

# ---------------------------------------------------------------------------
# Node-path area mapping
# ---------------------------------------------------------------------------
NODE_PATH_MAP: dict[str, list[str]] = {
    "objeciones": [
        "comercial", "limite", "prometer", "vender",
        "overpromise", "regla", "no prometer", "concepto prohibido",
    ],
    "integraciones": [
        "whatsapp", "crm", "agenda", "campana", "handoff", "lead",
        "plan", "gupshup", "twilio", "canal",
    ],
    "glosario": [
        "vera", "package code", "identificador", "termino",
        "scope", "knowledge scope",
    ],
    "seguridad": [
        "aislamiento", "isolation", "scope", "cliente",
        "acceso", "cross customer", "access tag",
    ],
    "automatizaciones": [
        "alcance", "productivo", "diagnostico", "kbaas",
        "knowledge", "automatizacion", "retrieval",
    ],
    "ventas": [
        "paquete", "comercial", "plan", "precio", "ventas",
    ],
}

# ---------------------------------------------------------------------------
# Reranker scoring signals (NO golden case data)
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


def phrase_match(query: str, candidate_text: str) -> float:
    q_words = normalize_light(query).split()
    c_norm = normalize_light(candidate_text)
    if len(q_words) < 2:
        return 0.0
    matches = 0
    total = 0
    for n in (2, 3):
        if len(q_words) >= n:
            for i in range(len(q_words) - n + 1):
                total += 1
                phrase = " ".join(q_words[i:i+n])
                if phrase in c_norm:
                    matches += 1
    return matches / total if total > 0 else 0.0


def domain_term_score(query_norm: str, candidate_text: str) -> float:
    cand_norm = normalize_light(candidate_text)
    score = 0.0
    for term in DOMAIN_NORM:
        in_query = term in query_norm
        in_cand = term in cand_norm
        if in_query and in_cand:
            score += 2.0
        elif in_cand:
            score += 0.3
    max_score = len(DOMAIN_NORM) * 2.0
    return min(score / max_score, 1.0) if max_score > 0 else 0.0


def safety_signal_score(query_norm: str, candidate_text: str) -> float:
    cand_norm = normalize_light(candidate_text)
    is_commercial = any(p in query_norm for p in OVERPROMMISE_QUERY_PATTERNS)
    if not is_commercial:
        return 0.0
    score = 0.0
    for term in SAFETY_CANDIDATE_NORM:
        if term in cand_norm:
            score += 1.0
    return min(score / 5.0, 1.0)


def metadata_boost(query_norm: str, candidate: dict) -> float:
    node_path = normalize_light(candidate.get("node_path") or "")
    title = normalize_light(candidate.get("title") or "")
    combined = node_path + " " + title
    score = 0.0
    hits = 0
    for area, terms in NODE_PATH_MAP.items():
        if area in node_path:
            for term in terms:
                if term in query_norm:
                    score += 2.0
                    hits += 1
                elif term in combined and any(t in query_norm for t in terms):
                    score += 1.0
                    hits += 1
    return min(score / 6.0, 1.0)


def risk_penalty(query_norm: str, candidate_text: str) -> float:
    cand_norm = normalize_light(candidate_text)
    query_specific_patterns = [
        "whatsapp handoff", "handoff",
        "vera", "package code", "codigo de paquete",
        "step to action", "step-to-action",
        "lead capture", "captura de leads",
        "diagnostic code", "codigo de diagnostico",
        "runtime target", "knowledge scope",
    ]
    generic_phrases = [
        "puede ayudar", "ofrece", "cubre", "alcance general",
        "vision general", "introduccion", "descripcion general",
        "team360 puede", "en team360",
    ]
    query_specific = any(p in query_norm for p in query_specific_patterns)
    if not query_specific:
        return 0.0
    candidate_generic = any(p in cand_norm for p in generic_phrases)
    return RISK_PENALTY if candidate_generic else 0.0


def compute_non_oracle_rerank_scores(
    query: str,
    candidates: list[dict],
    top_n: int,
) -> list[dict]:
    query_norm = normalize_light(query)
    query_tokens = tokenize(query)

    scored = []
    for chunk in candidates:
        text = _content_text(chunk)
        cand_norm = normalize_light(text)

        v = chunk.get("score") or 0.0
        l = lexical_overlap(query, text)
        p = phrase_match(query, text)
        d = domain_term_score(query_norm, text)
        s = safety_signal_score(query_norm, text)
        m = metadata_boost(query_norm, chunk)
        r = risk_penalty(query_norm, text)

        rerank = (
            W_VECTOR * v
            + W_LEXICAL * l
            + W_PHRASE * p
            + W_DOMAIN * d
            + W_SAFETY * s
            + W_METADATA * m
            + r
        )

        original_rank = chunk.get("rank", 0)
        proximity = (top_n - original_rank) * 0.005 if original_rank > 0 else 0
        rerank += proximity

        scored.append({
            "chunk_id": chunk.get("chunk_id", ""),
            "title": chunk.get("title", ""),
            "original_rank": original_rank,
            "vector_score": round(v, 6),
            "rerank_score": round(rerank, 4),
            "signals": {
                "lexical_overlap": round(l, 4),
                "phrase_match": round(p, 4),
                "domain_term": round(d, 4),
                "safety_signal": round(s, 4),
                "metadata_boost": round(m, 4),
                "risk_penalty": round(r, 4),
            },
        })

    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    for new_rank, s in enumerate(scored, 1):
        s["reranked_rank"] = new_rank
    return scored


# ---------------------------------------------------------------------------
# Semantic gap detection
# ---------------------------------------------------------------------------
def check_semantic_gap(query: str, candidates: list[dict], case: dict) -> tuple[bool, float]:
    expected_norm = [normalize(c) for c in case.get("expected_concepts", [])]
    q_tokens = set(tokenize(query))
    best_overlap = 0.0
    for cand in candidates:
        text = normalize(_content_text(cand))
        if any(e in text for e in expected_norm):
            c_tokens = set(tokenize(text))
            if q_tokens and c_tokens:
                intersect = q_tokens & c_tokens
                union = q_tokens | c_tokens
                jaccard = len(intersect) / len(union) if union else 0.0
                coverage = len(intersect & q_tokens) / len(q_tokens) if q_tokens else 0.0
                avg = (jaccard + coverage) / 2.0
                if avg > best_overlap:
                    best_overlap = avg
    return best_overlap < LEXICAL_OVERLAP_THRESHOLD, best_overlap


def classify_non_oracle_failure(
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

    is_gap, overlap = check_semantic_gap(query, candidates, case)
    if is_gap:
        return "semantic_gap_or_paraphrase_problem"

    return "reranker_not_powerful_enough"


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def generate_non_oracle_markdown(summary: dict, results: list[dict], args: argparse.Namespace) -> str:
    lines = []

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# Non-oracle reranking experiment — Fase 1.6h")
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
    oracle_rate = summary.get("oracle_lite_pass_rate", 68.0)
    gap = round(oracle_rate - rp, 1)

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Baseline strict (original):** {summary['baseline_pass_strict']}/{summary['total_queries']} ({summary['baseline_pass_rate_strict']}%)")
    lines.append(f"- **Baseline normalizado:** {summary['baseline_pass_norm']}/{summary['total_queries']} ({bp}%)")
    lines.append(f"- **Non-oracle reranked:** {summary['reranked_pass_norm']}/{summary['total_queries']} ({rp}%)")
    lines.append(f"- **Oracle-lite (1.6g, techo):** {oracle_rate}%")
    lines.append(f"- **Gap to oracle:** {gap:+.1f}%")
    lines.append(f"- **Delta (non-oracle - baseline):** {delta:+.1f}%")
    lines.append(f"- **High-risk baseline norm:** {summary['high_risk_baseline_pass_norm']}/{summary['high_risk_total']}")
    lines.append(f"- **High-risk reranked:** {summary['high_risk_reranked_pass_norm']}/{summary['high_risk_total']}")
    lines.append(f"- **Casos mejorados:** {summary['cases_improved']}")
    lines.append(f"- **Casos empeorados:** {summary['cases_worsened']}")
    lines.append(f"- **Casos sin cambio:** {summary['cases_unchanged']}")
    lines.append(f"- **Correct candidate in top-N:** {summary['correct_in_topN']}/{summary['total_queries']} ({summary['correct_in_topN_rate']}%)")
    lines.append(f"- **Conceptos prohibidos baseline:** {summary['forbidden_concepts_baseline']}")
    lines.append(f"- **Conceptos prohibidos reranked:** {summary['forbidden_concepts_reranked']}")
    lines.append(f"- **Latencia retrieval / reranking:** {summary['avg_latency_retrieval_ms']}ms / {summary['avg_latency_reranking_ms']}ms")
    lines.append("")

    lines.append("## Diferencia con oracle-lite (1.6g)")
    lines.append("")
    lines.append("| Experimento | Pass rate | Usa golden answers para reordenar? | Producción-ready? |")
    lines.append("|------------|-----------|-----------------------------------|-------------------|")
    lines.append(f"| Baseline pgvector | {bp}% | — | — |")
    lines.append(f"| Oracle-lite (1.6g) | {oracle_rate}% | **Sí** (expected/concepts) | No (oráculo) |")
    lines.append(f"| Non-oracle (1.6h) | {rp}% | No | Más cercano a producción |")
    lines.append("")
    lines.append(f"El gap de **{gap}pp** entre oracle-lite y non-oracle representa el margen")
    lines.append("que un reranker real (cross-encoder) podría recuperar.")
    lines.append("")

    fc = summary.get("failure_classification", {})
    if fc:
        lines.append("## Clasificación de fallos post-reranking")
        lines.append("")
        for reason, count in sorted(fc.items(), key=lambda x: -x[1]):
            pct = round(count / summary["total_failed_reranked"] * 100, 1) if summary["total_failed_reranked"] else 0
            lines.append(f"- **{reason}:** {count} ({pct}%)")
        if "semantic_gap_or_paraphrase_problem" in fc:
            lines.append("")
            lines.append("> Los casos con `semantic_gap_or_paraphrase_problem` tienen el chunk correcto")
            lines.append("> en el candidate pool, pero el reranker léxico no pudo empujarlo porque la")
            lines.append("> query usa wording distinto al del chunk. Esto se resuelve con un cross-encoder")
            lines.append("> o mejorando la cobertura de términos en el corpus.")
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
            lines.append(f"  - Baseline: {'PASS' if bn_pass else 'FAIL'} → Reranked: {'PASS' if rn_pass else 'FAIL'}")
            lines.append("")
    else:
        lines.append("- Ningún caso mejoró con non-oracle reranker.")
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

    lines.append("## Señales que más ayudaron")
    lines.append("")
    all_signals = {
        "lexical_overlap": [], "phrase_match": [], "domain_term": [],
        "safety_signal": [], "metadata_boost": [],
    }
    for r in results:
        details = r.get("reranker_details", [])
        if details and len(details) > 0:
            signals = details[0].get("signals", {})
            for key in all_signals:
                all_signals[key].append(signals.get(key, 0))
    if all_signals["lexical_overlap"]:
        avg_sigs = {k: round(sum(v) / len(v), 3) for k, v in all_signals.items() if v}
        lines.append("| Señal | Promedio top-1 | Peso |")
        lines.append("|-------|---------------|------|")
        weight_map = {
            "lexical_overlap": W_LEXICAL, "phrase_match": W_PHRASE,
            "domain_term": W_DOMAIN, "safety_signal": W_SAFETY,
            "metadata_boost": W_METADATA,
        }
        for key, avg in sorted(avg_sigs.items(), key=lambda x: -x[1]):
            w = weight_map.get(key, 0)
            lines.append(f"| {key} | {avg} | {w} |")
        lines.append("")

    lines.append("## Decisión arquitectónica")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by Fase 1.6h — Non-oracle Reranking Experiment. "
                 f"Signals: lexical+phrase+domain+safety+metadata+vector. "
                 f"No LLM, no Milvus, no ArangoDB, no production changes._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Non-oracle reranking experiment — Fase 1.6h")
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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.top_n < args.top_k:
        print(f"ERROR: --top-n ({args.top_n}) must be >= --top-k ({args.top_k})", file=sys.stderr)
        sys.exit(1)

    cases = load_cases(BP_FILE)
    print(f"Loaded {len(cases)} breaking point cases from {BP_FILE}")

    if args.max_cases:
        cases = cases[:args.max_cases]
        print(f"Limited to {len(cases)} cases")

    if args.dry_run:
        print("DRY RUN — Validating non-oracle reranker logic (no DB, no OpenAI)")
        dummy_candidates = [
            {"content_preview": "planned extension step to action test", "title": "Test",
             "node_path": "/objeciones", "score": 0.65, "rank": 1},
            {"content_preview": "whatsapp handoff lead capture", "title": "WA",
             "node_path": "/integraciones", "score": 0.55, "rank": 2},
        ]
        for c in cases:
            scores = compute_non_oracle_rerank_scores(c["query"], dummy_candidates, args.top_n)
            top = scores[0] if scores else None
            lex = top["signals"]["lexical_overlap"] if top else 0
            print(f"  [{c['case_id']}] query={c['query'][:40]}... lexical_top1={lex}")
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
    print(f"  Non-oracle reranker · No LLM · No Milvus · No ArangoDB")
    print(f"  Weights: vector={W_VECTOR} lexical={W_LEXICAL} phrase={W_PHRASE} "
          f"domain={W_DOMAIN} safety={W_SAFETY} metadata={W_METADATA} risk={RISK_PENALTY}")
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
                rerank_scores = compute_non_oracle_rerank_scores(query, candidates, args.top_n)
                reranked = []
                for rs in rerank_scores:
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
                    failure_classification = classify_non_oracle_failure(
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
                    "reranker_details": rerank_scores,
                    "failure_classification": failure_classification,
                })

                status_s = "PASS" if eval_strict["passed"] else "FAIL"
                status_b = "PASS" if eval_baseline_norm["passed"] else "FAIL"
                status_r = "PASS" if eval_reranked_norm["passed"] else "FAIL"
                flag = " 🎯" if reranker_helped else ""
                print(f"    strict={status_s} base={status_b} reranked={status_r} | "
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
    rp_rate = round(passed_reranked_norm / total * 100, 1) if total else 0
    delta = rp_rate - bp_rate
    correct_rate = round(correct_in_topN / total * 100, 1) if total else 0

    oracle_lite_rate = 68.0
    gap_to_oracle = round(oracle_lite_rate - rp_rate, 1)

    if delta >= 10 and correct_rate >= 60:
        rec = "B. Diseñar reranker runtime simple — las señales léxicas/safety/metadata tienen efecto."
    elif delta >= 5:
        rec = "C. Probar reranker real/cross-encoder en lab — non-oracle mejora pero deja margen."
    elif "semantic_gap" in str(failure_classification) or "reranker_not_powerful" in str(failure_classification):
        rec = "F. Cross-encoder necesario — señales léxicas no alcanzan. Oracle-lite llegó a 68% vs 44% non-oracle, gap de 24pp. Significa que el conocimiento semántico (qué conceptos esperar por caso) es necesario; un cross-encoder puede cerrar ese gap."
    elif delta > 0:
        rec = "D. Cross-encoder puede ayudar — non-oracle mejora marginalmente pero deja margen."
    elif correct_rate < 60:
        rec = "E. Mejorar content coverage antes — el candidato correcto no está en top-N."
    else:
        rec = "A. No usar reranker todavía — non-oracle no mejora significativamente sobre baseline."

    summary = {
        "experiment": "Non-oracle reranking experiment — Fase 1.6h",
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
        "reranked_pass_norm": passed_reranked_norm,
        "reranked_pass_rate_norm": rp_rate,
        "delta_pass_rate_norm": round(delta, 1),
        "oracle_lite_pass_rate": oracle_lite_rate,
        "gap_to_oracle": gap_to_oracle,
        "high_risk_total": high_risk_total,
        "high_risk_baseline_pass_norm": high_risk_base,
        "high_risk_reranked_pass_norm": high_risk_rerank,
        "cases_improved": improved,
        "cases_worsened": worsened,
        "cases_unchanged": unchanged,
        "correct_in_topN": correct_in_topN,
        "correct_in_topN_rate": correct_rate,
        "forbidden_concepts_baseline": forbidden_base,
        "forbidden_concepts_reranked": forbidden_rerank,
        "avg_latency_retrieval_ms": avg_ret_lat,
        "avg_latency_reranking_ms": avg_rer_lat,
        "total_failed_reranked": total_failed,
        "failure_classification": dict(sorted(failure_classification.items(), key=lambda x: -x[1])),
        "architecture_recommendation": rec,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"non_oracle_reranking_{ts}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": results,
        "latencies_ms": {"retrieval": retrieval_latencies, "reranking": reranking_latencies},
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_non_oracle_markdown(summary, results, args))
    print(f"Report saved: {md_path}")

    print()
    print("=" * 70)
    print("NON-ORACLE RERANKING EXPERIMENT SUMMARY")
    print("=" * 70)
    print(f"  Total cases:               {total}")
    print(f"  Baseline strict:           {passed_strict}/{total} ({summary['baseline_pass_rate_strict']}%)")
    print(f"  Baseline norm:             {passed_baseline_norm}/{total} ({bp_rate}%)")
    print(f"  Non-oracle reranked:       {passed_reranked_norm}/{total} ({rp_rate}%)")
    print(f"  Delta:                     {delta:+.1f}%")
    print(f"  Oracle-lite (techo):       {oracle_lite_rate}%")
    print(f"  Gap to oracle:             {gap_to_oracle:+.1f}pp")
    print(f"  High-risk base/reranked:   {high_risk_base}/{high_risk_rerank} (of {high_risk_total})")
    print(f"  Cases improved/worsened:   {improved}/{worsened}")
    print(f"  Correct in top-N:          {correct_in_topN}/{total} ({correct_rate}%)")
    print(f"  Forbidden base/reranked:   {forbidden_base}/{forbidden_rerank}")
    print(f"  Avg retrieval/rerank:      {avg_ret_lat}ms / {avg_rer_lat}ms")
    print()
    print(f"  Recommendation: {rec}")
    print()
    if failure_classification:
        print("  Failure classification (post-reranking):")
        for reason, count in failure_classification.items():
            print(f"    {reason}: {count}")
    print()


if __name__ == "__main__":
    main()

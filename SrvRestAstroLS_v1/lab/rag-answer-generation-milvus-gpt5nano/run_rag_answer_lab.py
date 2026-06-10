#!/usr/bin/env python3
"""RAG answer generation lab — Milvus + gpt-5-nano low — Fase 1.6k.

Evaluates the end-to-end RAG flow:
  user query → embedding → Milvus retrieval → Markdown context → LLM → answer

Usage:
  uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py
  uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py --model gpt-5-nano --reasoning-effort low
  uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py --no-llm --limit-cases 3
  uv run python lab/rag-answer-generation-milvus-gpt5nano/run_rag_answer_lab.py --dry-run

Environment:
  OPENAI_API_KEY or OpenAI_Key_JAI_query  (for both embeddings and LLM)
  DB_PG_V360_URL or TEAM360_DB_URL_PSQL  (PostgreSQL DSN — only for scope resolution)
  MILVUS_URI (optional, default: http://localhost:19530)
  TEAM360_LITELLM_BASE_URL (optional — if set, routes LLM calls through LiteLLM proxy)
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
# Dependency detection
# ---------------------------------------------------------------------------
try:
    import pymilvus
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LAB_DIR = Path(__file__).parent
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
CASES_FILE = LAB_DIR / "cases" / "rag_answer_cases.json"
RESULTS_DIR = LAB_DIR / "results"
BP_LAB_DIR = LAB_DIR.parent / "postgres-knowledge-retrieval-breaking-points"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BP_LAB_DIR))

from run_reranking_experiment import normalize, _resolve_dsn, _validate_positive

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLLECTION_NAME = "team360_lab_pgvector_benchmark_openai_small_1536"
DEFAULT_EMBEDDING_DIMS = 1536

SYSTEM_PROMPT = """Sos el asistente de diagnóstico comercial de Team360.

Tu tarea es orientar, no prometer capacidades no listas.
Usá únicamente el contexto recuperado.
Si el contexto no alcanza, decilo y pedí la mínima información necesaria.

No vendas como listo:
- Step-to-Action
- lead capture
- diagnostic_code
- WhatsApp handoff automático

Si aparecen como future/planned_extension, aclará que son extensiones planificadas.

Diferenciá:
- automatable (se puede automatizar en teoría)
- sellable today (está listo para vender hoy)
- planned extension (extensión planificada, no disponible)

Respondé en español claro, breve y comercial.
Hacé máximo 1 a 3 preguntas necesarias.
Dá orientación concreta.
No inventes precios, plazos, SLA ni integraciones no documentadas."""

_FORBIDDEN_TERMS_NORM = [
    "precio", "cuesta", "cotiza", "ars", "usd",
    "semanas", "meses", "días_hábiles",
    "sla", "acuerdo_nivel_servicio",
]

_NORM_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    t = text.lower()
    t = t.replace("_", " ").replace("-", " ")
    t = _NORM_WS.sub(" ", t).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def embed_query(query: str, api_key: str, model: str = "text-embedding-3-small", dims: int = 1536) -> list[float]:
    import httpx
    resp = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"input": [query], "model": model, "dimensions": dims},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Milvus search
# ---------------------------------------------------------------------------
def search_milvus(client: Any, collection_name: str, query_embedding: list[float], top_k: int) -> list[dict]:
    results = client.search(
        collection_name=collection_name,
        data=[query_embedding],
        limit=top_k,
        output_fields=["chunk_id", "title", "content_preview", "node_path", "document_id", "knowledge_scope_id"],
        search_params={"metric_type": "COSINE", "params": {"ef": 100}},
    )
    if not results:
        return []
    out = []
    for i, hit in enumerate(results[0]):
        ent = hit.get("entity", {})
        out.append({
            "rank": i + 1,
            "chunk_id": hit.get("id", ""),
            "title": ent.get("title", ""),
            "content_preview": ent.get("content_preview", ""),
            "node_path": ent.get("node_path", ""),
            "document_id": ent.get("document_id", ""),
            "score": round(hit.get("distance", 0.0), 6),
            "source": "milvus",
        })
    return out


# ---------------------------------------------------------------------------
# Call LLM (OpenAI-compatible with reasoning_effort support)
# ---------------------------------------------------------------------------
def call_llm(
    model: str,
    messages: list[dict],
    api_key: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 600,
    reasoning_effort: str | None = None,
    base_url: str | None = None,
) -> dict:
    import httpx
    url = f"{base_url.rstrip('/')}/chat/completions" if base_url else "https://api.openai.com/v1/chat/completions"
    body: dict = {
        "model": model,
        "messages": messages,
    }
    # o-series / nano models use max_completion_tokens instead of max_tokens
    if model.startswith("o") or model.startswith("gpt-5"):
        body["max_completion_tokens"] = max_tokens
    else:
        body["temperature"] = temperature
        body["max_tokens"] = max_tokens
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    if model.startswith("gpt-4") or model.startswith("gpt-3"):
        body["temperature"] = temperature
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    t0 = time.time()
    resp = httpx.post(url, headers=headers, json=body, timeout=60.0)
    latency_ms = round((time.time() - t0) * 1000, 1)
    resp.raise_for_status()
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = data.get("usage", {})
    return {
        "content": message.get("content", ""),
        "finish_reason": choice.get("finish_reason", ""),
        "model_returned": data.get("model", model),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# Build context from retrieved chunks
# ---------------------------------------------------------------------------
def build_context(chunks: list[dict], max_chars: int = 6000) -> tuple[str, int]:
    parts = []
    total = 0
    for c in chunks:
        title = c.get("title", "").strip()
        content = c.get("content_preview", "").strip()
        node_path = c.get("node_path", "").strip()
        entry = ""
        if title:
            entry += f"## {title}\n"
        if node_path:
            entry += f"Ruta: {node_path}\n"
        if content:
            entry += f"{content}\n"
        if not entry:
            continue
        if total + len(entry) > max_chars:
            remaining = max_chars - total
            if remaining > 50:
                parts.append(entry[:remaining])
                total += remaining
            break
        parts.append(entry)
        total += len(entry)
    return "\n".join(parts), total


# ---------------------------------------------------------------------------
# Heuristic evaluation
# ---------------------------------------------------------------------------
def evaluate_answer(case: dict, response_text: str, chunks: list[dict]) -> dict:
    norm_response = normalize_text(response_text)
    norm_chunks_text = normalize_text(" ".join(c.get("content_preview", "") for c in chunks))

    must_include = [normalize_text(m) for m in case.get("must_include", [])]
    must_not_include = [normalize_text(m) for m in case.get("must_not_include", [])]

    found_include = [m for m in must_include if m in norm_response]
    missing_include = [m for m in must_include if m not in norm_response]
    found_forbidden = [m for m in must_not_include if m in norm_response]

    safety_flags = []
    for ft in _FORBIDDEN_TERMS_NORM:
        if ft in norm_response:
            safety_flags.append(f"hallucinated_pricing_sla_{ft}")

    empty_response = not response_text.strip()
    too_long = len(response_text) > 2000

    has_context = len(chunks) > 0
    context_retrieved = len(chunks)

    makes_question = any(m in norm_response for m in ["?"])

    says_not_documented = any(p in norm_response for p in [
        "no documentado", "no disponible", "no confirmado",
        "planned extension", "extensión planificada", "no está listo",
        "no listo", "no lo vendemos", "no puedo",
    ])

    gives_orientation = any(p in norm_response for p in [
        "diagnóstico", "orientación", "concreto", "paso",
        "empezar", "sugiero", "recomiendo", "podemos",
    ])

    forbidden_claims = len(found_forbidden) + len(safety_flags)

    passed = (
        len(found_include) >= max(1, len(must_include) // 2)
        and not found_forbidden
        and not empty_response
        and not too_long
        and (makes_question or gives_orientation or says_not_documented)
    )

    return {
        "passed": passed,
        "found_must_include": found_include,
        "missing_must_include": missing_include,
        "found_forbidden": found_forbidden,
        "safety_flags": safety_flags,
        "empty_response": empty_response,
        "too_long": too_long,
        "has_context": has_context,
        "context_chunks_retrieved": context_retrieved,
        "makes_question": makes_question,
        "says_not_documented": says_not_documented,
        "gives_orientation": gives_orientation,
        "forbidden_claims_count": forbidden_claims,
        "response_length": len(response_text),
    }


# ---------------------------------------------------------------------------
# Load cases
# ---------------------------------------------------------------------------
def load_cases(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: Cases file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


# ---------------------------------------------------------------------------
# Blocked status
# ---------------------------------------------------------------------------
def print_blocked(reason: str) -> None:
    print("=" * 70)
    print("RAG ANSWER GENERATION LAB — Fase 1.6k")
    print("=" * 70)
    print()
    print(f"  STATUS: BLOCKED")
    print(f"  Reason: {reason}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="RAG answer generation lab — Fase 1.6k")
    parser.add_argument("--model", default="gpt-5-nano", help="LLM model (default: gpt-5-nano)")
    parser.add_argument("--reasoning-effort", default=None, help="Reasoning effort: low/medium/high")
    parser.add_argument("--top-n", type=_validate_positive, default=20, help="Candidate pool size (1-50)")
    parser.add_argument("--top-k", type=_validate_positive, default=5, help="Context chunks for LLM (1-50)")
    parser.add_argument("--collection-name", default=COLLECTION_NAME)
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_EMBEDDING_DIMS)
    parser.add_argument("--embedding-version", default="team360-openai-small-1536-v1")
    parser.add_argument("--organization-code", default="team360_live")
    parser.add_argument("--workspace-code", default="team360_public_site")
    parser.add_argument("--knowledge-scope-code", default="ks_team360_sales_diagnosis")
    parser.add_argument("--max-context-chars", type=int, default=6000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=600)
    parser.add_argument("--limit-cases", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm", action="store_true", help="Only run retrieval, skip LLM calls")
    args = parser.parse_args()

    if args.top_n < args.top_k:
        print(f"ERROR: --top-n ({args.top_n}) must be >= --top-k ({args.top_k})", file=sys.stderr)
        sys.exit(1)

    if not PYMILVUS_AVAILABLE:
        print_blocked("pymilvus is not installed.")
        sys.exit(0)

    global MilvusClient, DataType
    from pymilvus import MilvusClient, DataType

    cases = load_cases(CASES_FILE)
    print(f"Loaded {len(cases)} RAG answer cases from {CASES_FILE}")

    if args.limit_cases:
        cases = cases[:args.limit_cases]
        print(f"Limited to {len(cases)} cases")

    dsn = _resolve_dsn()
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print_blocked("OPENAI_API_KEY not found")
        sys.exit(1)

    milvus_uri = os.environ.get("MILVUS_URI", "http://localhost:19530")
    llm_base_url = os.environ.get("TEAM360_LITELLM_BASE_URL") or None

    print(f"PostgreSQL: {dsn[:20]}...")
    print(f"Milvus:     {milvus_uri}")
    print(f"Scope:      {args.knowledge_scope_code}")
    print(f"Model:      {args.model}")
    if args.reasoning_effort:
        print(f"Reasoning:  {args.reasoning_effort}")
    print(f"Top-N:      {args.top_n} | Top-K: {args.top_k}")
    print(f"Context:    {args.max_context_chars} chars max")
    print()

    if args.dry_run:
        print("DRY RUN — Validating connectivity (no retrieval, no LLM)")
        client = MilvusClient(uri=milvus_uri)
        existing = client.list_collections()
        print(f"  Milvus collections: {existing}")
        print(f"  Cases loaded: {len(cases)}")
        if args.model and not args.no_llm:
            print(f"  LLM model: {args.model}")
            if args.reasoning_effort:
                print(f"  Reasoning: {args.reasoning_effort}")
        print("  Dry run OK.")
        print()
        print("Required env: OPENAI_API_KEY, DB_PG_V360_URL or TEAM360_DB_URL_PSQL")
        sys.exit(0)

    # Validate Milvus collection
    client = MilvusClient(uri=milvus_uri)
    existing = client.list_collections()
    if args.collection_name not in existing:
        print_blocked(f"Milvus collection '{args.collection_name}' not found. Run Fase 1.6j first.")
        sys.exit(0)

    stats = client.get_collection_stats(args.collection_name)
    row_count = stats.get("row_count", 0)
    print(f"Milvus collection '{args.collection_name}' has {row_count} rows")
    print()

    case_results = []
    retrieval_latencies: list[float] = []
    llm_latencies: list[float] = []
    total_latencies: list[float] = []

    for case in cases:
        case_id = case["case_id"]
        user_msg = case["user_message"]
        print(f"  [{case_id}] Processing...", end=" ", flush=True)

        # Embed query
        t_start = time.time()
        try:
            query_emb = embed_query(user_msg, api_key, model=args.embedding_model, dims=args.dimensions)
        except Exception as e:
            print(f"EMBED ERROR: {str(e)[:60]}", flush=True)
            retrieval_latencies.append(0)
            total_latencies.append(0)
            case_results.append({
                "case_id": case_id, "user_message": user_msg,
                "category": case.get("category", ""),
                "risk_level": case.get("risk_level", ""),
                "retrieval_error": str(e)[:200],
                "retrieval_chunks": [],
                "context_chars": 0,
                "llm_response": "",
                "llm_error": str(e)[:200],
                "retrieval_latency_ms": 0,
                "llm_latency_ms": 0,
                "total_latency_ms": 0,
                "evaluation": {"passed": False, "empty_response": True},
            })
            continue

        # Milvus retrieval
        t_ret = time.time()
        try:
            chunks = search_milvus(client, args.collection_name, query_emb, args.top_n)
        except Exception as e:
            print(f"MILVUS ERROR: {str(e)[:60]}", flush=True)
            retrieval_latencies.append(0)
            total_latencies.append(0)
            case_results.append({
                "case_id": case_id, "user_message": user_msg,
                "category": case.get("category", ""),
                "risk_level": case.get("risk_level", ""),
                "retrieval_error": str(e)[:200],
                "retrieval_chunks": [],
                "context_chars": 0,
                "llm_response": "",
                "retrieval_latency_ms": round((time.time() - t_ret) * 1000, 1),
                "llm_latency_ms": 0,
                "total_latency_ms": round((time.time() - t_start) * 1000, 1),
                "evaluation": {"passed": False, "empty_response": True},
            })
            continue

        retrieval_lat = round((time.time() - t_ret) * 1000, 1)
        retrieval_latencies.append(retrieval_lat)

        top_k_chunks = chunks[:args.top_k]
        context, context_chars = build_context(top_k_chunks, args.max_context_chars)

        result = {
            "case_id": case_id,
            "user_message": user_msg,
            "category": case.get("category", ""),
            "risk_level": case.get("risk_level", ""),
            "retrieval_chunks": [
                {"rank": c["rank"], "chunk_id": c["chunk_id"],
                 "title": c.get("title", ""),
                 "content_preview": (c.get("content_preview") or "")[:200],
                 "score": c["score"]}
                for c in chunks[:args.top_k]
            ],
            "context_chars": context_chars,
            "retrieval_latency_ms": retrieval_lat,
        }

        if args.no_llm:
            print(f"retrieval={len(chunks)} chunks ({retrieval_lat}ms)", flush=True)
            result["llm_response"] = "(no-llm mode)"
            result["llm_latency_ms"] = 0
            result["total_latency_ms"] = round((time.time() - t_start) * 1000, 1)
            result["evaluation"] = evaluate_answer(case, "", chunks)
            case_results.append(result)
            total_latencies.append(result["total_latency_ms"])
            continue

        # LLM call
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"## Contexto recuperado\n\n{context}\n\n## Consulta del usuario\n\n{user_msg}"},
        ]

        t_llm = time.time()
        try:
            llm_result = call_llm(
                model=args.model,
                messages=messages,
                api_key=api_key,
                temperature=args.temperature,
                max_tokens=args.max_output_tokens,
                reasoning_effort=args.reasoning_effort,
                base_url=llm_base_url,
            )
        except Exception as e:
            print(f"LLM ERROR: {str(e)[:80]}", flush=True)
            llm_lat = round((time.time() - t_llm) * 1000, 1)
            llm_latencies.append(llm_lat)
            total_lat = round((time.time() - t_start) * 1000, 1)
            total_latencies.append(total_lat)
            result["llm_response"] = f"(LLM error: {str(e)[:200]})"
            result["llm_error"] = str(e)[:200]
            result["llm_latency_ms"] = llm_lat
            result["total_latency_ms"] = total_lat
            result["evaluation"] = evaluate_answer(case, "", chunks)
            case_results.append(result)
            continue

        llm_lat = llm_result["latency_ms"]
        llm_latencies.append(llm_lat)
        total_lat = round((time.time() - t_start) * 1000, 1)
        total_latencies.append(total_lat)

        response_text = llm_result["content"]
        evaluation = evaluate_answer(case, response_text, chunks)

        result["llm_response"] = response_text
        result["llm_model"] = llm_result.get("model_returned", args.model)
        result["llm_latency_ms"] = llm_lat
        result["total_latency_ms"] = total_lat
        result["llm_usage"] = llm_result.get("usage", {})
        result["evaluation"] = evaluation

        case_results.append(result)

        passed_str = "P" if evaluation["passed"] else "F"
        flags = ""
        if evaluation["found_forbidden"]:
            flags += " F"
        if evaluation["safety_flags"]:
            flags += " S"
        print(f"retrieval={len(chunks)} ctx={context_chars}c llm={llm_lat}ms total={total_lat}ms {passed_str}{flags}", flush=True)

    # Summary
    total = len(case_results)
    if total == 0:
        print("\nNo cases executed.")
        sys.exit(0)

    passed = sum(1 for r in case_results if r.get("evaluation", {}).get("passed", False))
    high_risk_total = sum(1 for r in case_results if r.get("risk_level") == "high")
    high_risk_passed = sum(1 for r in case_results if r.get("risk_level") == "high" and r.get("evaluation", {}).get("passed", False))
    forbidden_claims_total = sum(len(r.get("evaluation", {}).get("found_forbidden", [])) + len(r.get("evaluation", {}).get("safety_flags", [])) for r in case_results)
    avg_retrieval_lat = round(sum(retrieval_latencies) / len(retrieval_latencies), 1) if retrieval_latencies else 0
    avg_llm_lat = round(sum(llm_latencies) / len(llm_latencies), 1) if llm_latencies else 0
    avg_total_lat = round(sum(total_latencies) / len(total_latencies), 1) if total_latencies else 0

    sorted_total = sorted(total_latencies)
    p50_total = sorted_total[len(sorted_total) // 2] if sorted_total else 0
    p95_total = sorted_total[int(len(sorted_total) * 0.95)] if sorted_total else sorted_total[-1] if sorted_total else 0

    avg_context_chars = round(sum(r.get("context_chars", 0) for r in case_results) / total, 1) if total else 0
    must_include_ok = sum(1 for r in case_results if r.get("evaluation", {}).get("found_must_include"))
    missing_context_handled = sum(1 for r in case_results if r.get("evaluation", {}).get("says_not_documented", False))
    useful_orientation = sum(1 for r in case_results if r.get("evaluation", {}).get("gives_orientation", False))
    minimal_questions = sum(1 for r in case_results if r.get("evaluation", {}).get("makes_question", False))

    pass_rate = round(passed / total * 100, 1) if total else 0
    high_risk_rate = round(high_risk_passed / high_risk_total * 100, 1) if high_risk_total else 0

    if pass_rate >= 70 and high_risk_rate >= 90:
        rec = "A. gpt-5-nano low viable para primera etapa conversacional."
    elif pass_rate >= 60:
        rec = "B. gpt-5-nano low viable con guardrails adicionales."
    elif not args.no_llm and avg_llm_lat > 0 and pass_rate < 50 and avg_context_chars > 0:
        rec = "C. Probar gpt-5-mini / medium en siguiente lab."
    elif args.no_llm:
        rec = "(no-llm mode — solo validación de retrieval)"
    elif pass_rate < 30:
        rec = "D. Mejorar content coverage antes de modelo."
    else:
        rec = "F. No avanzar a runtime todavía."

    if avg_total_lat > 15000:
        rec += " Reducir contexto/top-k para latencia."

    missing_context_count = sum(1 for r in case_results if not r.get("retrieval_chunks"))
    if missing_context_count > total * 0.3:
        rec += " Retrieval no trae evidencia frecuentemente."

    forbidden_claims_detected = forbidden_claims_total > 0

    summary = {
        "experiment": "RAG answer generation — Milvus + gpt-5-nano low — Fase 1.6k",
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "embedding_model": args.embedding_model,
        "dimensions": args.dimensions,
        "knowledge_scope": args.knowledge_scope_code,
        "collection": args.collection_name,
        "top_n": args.top_n,
        "top_k": args.top_k,
        "max_context_chars": args.max_context_chars,
        "total_cases": total,
        "passed": passed,
        "pass_rate": pass_rate,
        "high_risk_total": high_risk_total,
        "high_risk_passed": high_risk_passed,
        "high_risk_pass_rate": high_risk_rate,
        "avg_retrieval_latency_ms": avg_retrieval_lat,
        "avg_llm_latency_ms": avg_llm_lat,
        "avg_total_latency_ms": avg_total_lat,
        "p50_total_latency_ms": p50_total,
        "p95_total_latency_ms": p95_total,
        "avg_context_chars": avg_context_chars,
        "forbidden_claims_total": forbidden_claims_total,
        "missing_context_handled_count": missing_context_handled,
        "useful_orientation_count": useful_orientation,
        "minimal_questions_count": minimal_questions,
        "must_include_ok": must_include_ok,
        "forbidden_claims_detected": forbidden_claims_detected,
        "missing_context_count": missing_context_count,
        "no_llm_mode": args.no_llm,
        "architecture_recommendation": rec,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = f"rag_answer_generation_{ts}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "cases": case_results,
        "latencies_ms": {
            "retrieval": retrieval_latencies,
            "llm": llm_latencies,
            "total": total_latencies,
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_content = generate_markdown(summary, case_results, args)
    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Report saved: {md_path}")

    print()
    print("=" * 70)
    print("RAG ANSWER GENERATION LAB — SUMMARY")
    print("=" * 70)
    print(f"  Total cases:             {total}")
    print(f"  Pass rate:               {passed}/{total} ({pass_rate}%)")
    print(f"  High-risk pass rate:     {high_risk_passed}/{high_risk_total} ({high_risk_rate}%)")
    print(f"  Avg retrieval latency:   {avg_retrieval_lat}ms")
    print(f"  Avg LLM latency:         {avg_llm_lat}ms")
    print(f"  Avg total latency:       {avg_total_lat}ms")
    print(f"  P50/P95 total:           {p50_total}ms / {p95_total}ms")
    print(f"  Avg context chars:       {avg_context_chars}")
    print(f"  Forbidden claims:        {forbidden_claims_total}")
    print(f"  Missing context handled: {missing_context_handled}")
    print(f"  Useful orientation:      {useful_orientation}")
    print(f"  Recommendation: {rec}")


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def generate_markdown(summary: dict, case_results: list[dict], args: argparse.Namespace) -> str:
    lines = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# RAG answer generation lab — Milvus + gpt-5-nano low")
    lines.append("")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Model:** {args.model}")
    if args.reasoning_effort:
        lines.append(f"**Reasoning effort:** {args.reasoning_effort}")
    lines.append(f"**Embedding:** {args.embedding_model} ({args.dimensions}d)")
    lines.append(f"**Top-N (retrieval):** {args.top_n} | **Top-K (context):** {args.top_k}")
    lines.append(f"**Max context chars:** {args.max_context_chars}")
    lines.append(f"**Scope:** {args.knowledge_scope_code}")
    lines.append("")

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Pass rate:** {summary['passed']}/{summary['total_cases']} ({summary['pass_rate']}%)")
    lines.append(f"- **High-risk pass rate:** {summary['high_risk_passed']}/{summary['high_risk_total']} ({summary['high_risk_pass_rate']}%)")
    lines.append(f"- **Avg retrieval latency:** {summary['avg_retrieval_latency_ms']}ms")
    lines.append(f"- **Avg LLM latency:** {summary['avg_llm_latency_ms']}ms")
    lines.append(f"- **Avg total latency:** {summary['avg_total_latency_ms']}ms")
    lines.append(f"- **P50 total latency:** {summary['p50_total_latency_ms']}ms")
    lines.append(f"- **P95 total latency:** {summary['p95_total_latency_ms']}ms")
    lines.append(f"- **Forbidden claims:** {summary['forbidden_claims_total']}")
    lines.append(f"- **Missing context handled:** {summary['missing_context_handled_count']}")
    lines.append(f"- **Useful orientation given:** {summary['useful_orientation_count']}")
    lines.append("")
    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Arquitectura evaluada")
    lines.append("")
    lines.append("PostgreSQL 18 source of truth + Milvus 2.6 vector runtime derivado + ")
    lines.append("Markdown context chunks + gpt-5-nano low como generador de respuesta.")
    lines.append("PGVector como baseline/fallback. No ArangoDB. No cross-encoder.")
    lines.append("")

    lines.append("## Calidad de respuestas")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| Pass rate | {summary['pass_rate']}% |")
    lines.append(f"| High-risk pass rate | {summary['high_risk_pass_rate']}% |")
    lines.append(f"| Forbidden claims | {summary['forbidden_claims_total']} |")
    lines.append(f"| Missing context handled | {summary['missing_context_handled_count']} |")
    lines.append(f"| Useful orientation | {summary['useful_orientation_count']} |")
    lines.append(f"| Must-include OK | {summary['must_include_ok']} |")
    lines.append("")

    lines.append("## Seguridad comercial")
    lines.append("")
    if summary['forbidden_claims_detected']:
        lines.append("⚠️ Se detectaron claims prohibidos (precios/plazos/SLA) en algunas respuestas.")
    else:
        lines.append("✅ No se detectaron claims prohibidos.")
    lines.append("")

    lines.append("## Latencia end-to-end")
    lines.append("")
    lines.append(f"- Retrieval avg: {summary['avg_retrieval_latency_ms']}ms")
    lines.append(f"- LLM avg:       {summary['avg_llm_latency_ms']}ms")
    lines.append(f"- Total avg:     {summary['avg_total_latency_ms']}ms")
    lines.append(f"- P50 total:     {summary['p50_total_latency_ms']}ms")
    lines.append(f"- P95 total:     {summary['p95_total_latency_ms']}ms")
    lines.append("")

    lines.append("## Casos aprobados")
    lines.append("")
    passed_cases = [r for r in case_results if r.get("evaluation", {}).get("passed", False)]
    if passed_cases:
        for r in passed_cases:
            lines.append(f"- `{r['case_id']}` — {r['user_message'][:60]}")
    else:
        lines.append("- Ningún caso aprobado.")
    lines.append("")

    lines.append("## Casos fallidos")
    lines.append("")
    failed_cases = [r for r in case_results if not r.get("evaluation", {}).get("passed", False)]
    if failed_cases:
        for r in failed_cases:
            ev = r.get("evaluation", {})
            reasons = []
            if ev.get("missing_must_include"):
                reasons.append(f"missing: {ev['missing_must_include'][:2]}")
            if ev.get("found_forbidden"):
                reasons.append(f"forbidden: {ev['found_forbidden']}")
            if ev.get("empty_response"):
                reasons.append("empty_response")
            if ev.get("too_long"):
                reasons.append("too_long")
            r_str = ", ".join(reasons) if reasons else "unknown"
            lines.append(f"- `{r['case_id']}` — {r['user_message'][:60]} → {r_str}")
    else:
        lines.append("- No hay casos fallidos.")
    lines.append("")

    lines.append("## Hallazgos")
    lines.append("")
    if summary["missing_context_count"] > 0:
        lines.append(f"- {summary['missing_context_count']} casos sin chunks recuperados.")
    if summary["forbidden_claims_detected"]:
        lines.append("- El modelo generó claims prohibidos en algunos casos.")
    if summary["avg_retrieval_latency_ms"] < 50:
        lines.append("- Retrieval en Milvus es rápido (Media < 50ms).")
    if summary["avg_llm_latency_ms"] < 3000:
        lines.append("- Latencia LLM aceptable para flujo conversacional.")
    if summary["avg_total_latency_ms"] < 5000:
        lines.append("- Latencia end-to-end viable para primera etapa.")
    else:
        lines.append("- Latencia end-to-end alta. Revisar max_context_chars o proveedor LLM.")
    lines.append("")

    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.6k — RAG answer generation lab. "
                 "PostgreSQL source of truth, Milvus vector runtime, gpt-5-nano low generator. "
                 "No ArangoDB, no cross-encoder, no production changes._")
    return "\n".join(lines)


if __name__ == "__main__":
    main()

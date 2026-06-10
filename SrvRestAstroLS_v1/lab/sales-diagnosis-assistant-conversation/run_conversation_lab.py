#!/usr/bin/env python3
"""Sales Diagnosis Assistant Conversation Lab — Fase 1.7.

Tests multi-turn conversational diagnosis with Milvus retrieval + gpt-5-nano low.

Usage:
  uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py
  uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --no-llm --limit-cases 2
  uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --dry-run
  uv run python lab/sales-diagnosis-assistant-conversation/run_conversation_lab.py --model gpt-5-nano --reasoning-effort low

Environment:
  OPENAI_API_KEY or OpenAI_Key_JAI_query
  DB_PG_V360_URL or TEAM360_DB_URL_PSQL
  MILVUS_URI (optional, default: http://localhost:19530)
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
CASES_FILE = LAB_DIR / "cases" / "conversation_cases.json"
RESULTS_DIR = LAB_DIR / "results"
BP_LAB_DIR = LAB_DIR.parents[1] / "lab" / "postgres-knowledge-retrieval-breaking-points"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BP_LAB_DIR))

from run_reranking_experiment import normalize, _resolve_dsn, _validate_positive

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLLECTION_NAME = "team360_lab_pgvector_benchmark_openai_small_1536"
DEFAULT_EMBEDDING_DIMS = 1536

SYSTEM_PROMPT = """Sos el asistente de diagnóstico comercial de Team360.
Tu tarea es orientar, diagnosticar y ayudar a descubrir oportunidades de automatización.
No sos un vendedor de humo.
Usá únicamente el contexto recuperado y el historial de la conversación.
Si falta información, hacé pocas preguntas concretas.
No hagas más de 3 preguntas por turno. Preferí 1 pregunta si alcanza.

No prometas capacidades no listas. No vendas como listo:
- Step-to-Action
- lead capture
- diagnostic_code
- WhatsApp handoff automático
- CRM real

Si aparecen como future/planned_extension, aclará que son extensiones planificadas.
Diferenciá: automatable, vendible hoy (sellable today), extensión planificada (planned extension).
No inventes precios, plazos, SLA ni integraciones no documentadas.
No menciones detalles internos técnicos salvo que el usuario pregunte.

Respondé en español claro, breve y comercial.
Cada respuesta debe tener:
1. una comprensión del caso
2. una orientación concreta
3. como máximo 1 a 3 preguntas útiles
4. límites claros cuando aplique"""

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
# Call LLM
# ---------------------------------------------------------------------------
def call_llm(
    model: str,
    messages: list[dict],
    api_key: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 500,
    reasoning_effort: str | None = None,
    base_url: str | None = None,
) -> dict:
    import httpx
    url = f"{base_url.rstrip('/')}/chat/completions" if base_url else "https://api.openai.com/v1/chat/completions"
    body: dict = {
        "model": model,
        "messages": messages,
    }
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
# Build conversation history string
# ---------------------------------------------------------------------------
def build_history(history: list[dict[str, str]], max_chars: int = 2000) -> str:
    parts = []
    total = 0
    for entry in history:
        role = entry["role"]
        content = entry["content"]
        line = f"{role}: {content}\n"
        if total + len(line) > max_chars:
            remaining = max_chars - total
            if remaining > 30:
                parts.append(line[:remaining])
            break
        parts.append(line)
        total += len(line)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Build slot state string
# ---------------------------------------------------------------------------
def build_slot_state(slots: dict[str, str]) -> str:
    if not slots:
        return "Slots detectados: ninguno todavía."
    items = [f"  - {k}: {v}" for k, v in slots.items()]
    return "Slots detectados:\n" + "\n".join(items)


# ---------------------------------------------------------------------------
# Parse assistant response for slots, questions, orientation
# ---------------------------------------------------------------------------
def parse_response(response_text: str) -> dict:
    norm = normalize_text(response_text)
    question_count = norm.count("¿") + norm.count("?")
    questions_found = max(0, question_count)

    orientation_markers = [
        "diagnóstico", "orientación", "concreto", "paso",
        "empezar", "sugiero", "recomiendo", "podemos",
        "te sugiero", "te recomiendo", "podría", "sugeriría",
    ]
    gives_orientation = any(p in norm for p in orientation_markers)

    says_not_documented = any(p in norm for p in [
        "no documentado", "no disponible", "no confirmado",
        "planned extension", "extensión planificada", "no está listo",
        "no listo", "no lo vendemos", "no puedo",
        "planned_extension",
    ])

    slot_markers = {
        "business_type": ["rubro", "empresa", "negocio", "sector", "industria", "giro"],
        "current_channel": ["canal", "facebook", "instagram", "whatsapp", "web", "página", "tienda"],
        "inquiry_volume": ["volumen", "consultas", "mensajes", "leads", "clientes", "cuántos"],
        "main_pain": ["dolor", "problema", "pérdida", "lento", "difícil", "complicado", "repetitivo"],
        "current_process": ["proceso", "planilla", "excel", "manual", "sistema", "herramienta"],
        "urgency": ["urgencia", "prioridad", "ya", "rápido", "semana", "mes"],
        "integration_need": ["integración", "conectar", "crm", "sistema", "api", "plataforma"],
        "whatsapp_interest": ["whatsapp", "wsp", "wasap"],
        "crm_interest": ["crm", "cliente", "base", "contacto"],
        "automation_maturity": ["madurez", "etapa", "nivel", "proceso", "automatización"],
    }

    detected_slots = {}
    for slot, markers in slot_markers.items():
        for m in markers:
            if m in norm:
                detected_slots[slot] = True
                break

    return {
        "question_count": questions_found,
        "gives_orientation": gives_orientation,
        "says_not_documented": says_not_documented,
        "detected_slots": detected_slots,
        "response_length": len(response_text),
    }


# ---------------------------------------------------------------------------
# Heuristic evaluation per turn
# ---------------------------------------------------------------------------
def evaluate_turn(
    case: dict,
    response_text: str,
    chunks: list[dict],
    parsed: dict,
) -> dict:
    norm_response = normalize_text(response_text)

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
    question_count = parsed["question_count"]
    too_many_questions = question_count > case.get("questions_max_per_turn", 3)
    forbidden_claims = len(found_forbidden) + len(safety_flags)

    passed = (
        not empty_response
        and not too_long
        and not too_many_questions
        and not found_forbidden
        and not safety_flags
    )

    return {
        "passed": passed,
        "found_must_include": found_include,
        "missing_must_include": missing_include,
        "found_forbidden": found_forbidden,
        "safety_flags": safety_flags,
        "empty_response": empty_response,
        "too_long": too_long,
        "too_many_questions": too_many_questions,
        "has_context": has_context,
        "context_chunks_retrieved": len(chunks),
        "question_count": question_count,
        "forbidden_claims_count": forbidden_claims,
        "gives_orientation": parsed["gives_orientation"],
        "says_not_documented": parsed["says_not_documented"],
        "response_length": len(response_text),
    }


# ---------------------------------------------------------------------------
# Evaluate full scenario
# ---------------------------------------------------------------------------
def evaluate_scenario(case: dict, turn_results: list[dict], conversation_state: dict) -> dict:
    total_turns = len(turn_results)
    passed_turns = sum(1 for t in turn_results if t.get("evaluation", {}).get("passed", False))
    all_passed = passed_turns == total_turns

    total_forbidden = sum(t.get("evaluation", {}).get("forbidden_claims_count", 0) for t in turn_results)
    all_safety = [t.get("evaluation", {}).get("safety_flags", []) for t in turn_results]
    flat_safety = [item for sublist in all_safety for item in sublist]

    total_questions = sum(t.get("evaluation", {}).get("question_count", 0) for t in turn_results)

    has_diagnosis_orientation = any(t.get("evaluation", {}).get("gives_orientation", False) for t in turn_results)
    has_says_not_documented = any(t.get("evaluation", {}).get("says_not_documented", False) for t in turn_results)

    expected_slots = case.get("expected_slots", [])
    detected_slots_set = set()
    for t in turn_results:
        parsed = t.get("parsed", {})
        detected_slots_set.update(parsed.get("detected_slots", {}).keys())
    slots_filled = len(expected_slots) if all(s in detected_slots_set for s in expected_slots) else len([s for s in expected_slots if s in detected_slots_set])
    all_slots_detected = slots_filled >= len(expected_slots)

    planned_extension_misrepresented = False
    if "planned_extension" in case.get("must_include", []):
        planned_markers = ["planned_extension", "extensión planificada", "planned extension"]
        has_extension_ref = any(
            any(p in normalize_text(t.get("response_text", "")) for p in planned_markers)
            for t in turn_results
        )
        planned_extension_misrepresented = not has_extension_ref

    hallucinated_pricing = len(flat_safety) > 0

    passed = (
        all_passed
        and all_slots_detected
        and not total_forbidden > 0
    )

    return {
        "passed": passed,
        "total_turns": total_turns,
        "passed_turns": passed_turns,
        "turn_pass_rate": round(passed_turns / total_turns * 100, 1) if total_turns else 0,
        "total_forbidden_claims": total_forbidden,
        "safety_flags": flat_safety,
        "total_questions": total_questions,
        "avg_questions_per_turn": round(total_questions / total_turns, 1) if total_turns else 0,
        "has_diagnosis_orientation": has_diagnosis_orientation,
        "has_says_not_documented": has_says_not_documented,
        "expected_slots": expected_slots,
        "detected_slots": list(detected_slots_set),
        "slots_filled": slots_filled,
        "all_slots_detected": all_slots_detected,
        "planned_extension_misrepresented": planned_extension_misrepresented,
        "hallucinated_pricing": hallucinated_pricing,
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
    print("SALES DIAGNOSIS ASSISTANT CONVERSATION LAB — Fase 1.7")
    print("=" * 70)
    print()
    print(f"  STATUS: BLOCKED")
    print(f"  Reason: {reason}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Sales Diagnosis Assistant Conversation Lab — Fase 1.7")
    parser.add_argument("--model", default="gpt-5-nano", help="LLM model (default: gpt-5-nano)")
    parser.add_argument("--reasoning-effort", default=None, help="Reasoning effort: low/medium/high")
    parser.add_argument("--top-n", type=_validate_positive, default=20, help="Candidate pool size (1-50)")
    parser.add_argument("--top-k", type=_validate_positive, default=5, help="Context chunks for LLM (1-50)")
    parser.add_argument("--collection-name", default=COLLECTION_NAME)
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_EMBEDDING_DIMS)
    parser.add_argument("--max-context-chars", type=int, default=6000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=800)
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
    print(f"Loaded {len(cases)} conversation scenarios from {CASES_FILE}")

    if args.limit_cases:
        cases = cases[:args.limit_cases]
        print(f"Limited to {len(cases)} scenarios")

    dsn = _resolve_dsn()
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key:
        print_blocked("OPENAI_API_KEY not found")
        sys.exit(1)

    milvus_uri = os.environ.get("MILVUS_URI", "http://localhost:19530")
    llm_base_url = os.environ.get("TEAM360_LITELLM_BASE_URL") or None

    print(f"PostgreSQL: {dsn[:20]}...")
    print(f"Milvus:     {milvus_uri}")
    print(f"Model:      {args.model}")
    if args.reasoning_effort:
        print(f"Reasoning:  {args.reasoning_effort}")
    print(f"Top-N:      {args.top_n} | Top-K: {args.top_k}")
    print(f"Max context: {args.max_context_chars} chars")
    print(f"Max output:  {args.max_output_tokens} tokens")
    print()

    if args.dry_run:
        print("DRY RUN — Validating connectivity")
        client = MilvusClient(uri=milvus_uri)
        existing = client.list_collections()
        print(f"  Milvus collections: {existing}")
        print(f"  Scenarios loaded: {len(cases)}")
        if args.model and not args.no_llm:
            print(f"  LLM model: {args.model}")
        print("  Dry run OK.")
        sys.exit(0)

    client = MilvusClient(uri=milvus_uri)
    existing = client.list_collections()
    if args.collection_name not in existing:
        print_blocked(f"Milvus collection '{args.collection_name}' not found.")
        sys.exit(0)

    stats = client.get_collection_stats(args.collection_name)
    row_count = stats.get("row_count", 0)
    print(f"Milvus collection '{args.collection_name}' has {row_count} rows")
    print()

    scenario_results = []
    retrieval_latencies: list[float] = []
    llm_latencies: list[float] = []
    total_latencies: list[float] = []

    for case in cases:
        case_id = case["case_id"]
        title = case.get("title", case_id)
        user_turns = case.get("user_turns", [])
        risk_level = case.get("risk_level", "medium")
        print(f"\n{'='*60}")
        print(f"  [{case_id}] {title} ({risk_level} risk, {len(user_turns)} turns)")
        print(f"{'='*60}")

        conversation_state = {
            "slots": {},
            "history": [],
            "turn_count": 0,
            "total_questions_asked": 0,
        }

        turn_results = []

        for turn_idx, user_msg in enumerate(user_turns):
            turn_num = turn_idx + 1
            print(f"\n  --- Turn {turn_num}/{len(user_turns)} ---")
            print(f"  User: {user_msg[:80]}")

            t_start = time.time()

            # Embed query
            try:
                query_emb = embed_query(user_msg, api_key, model=args.embedding_model, dims=args.dimensions)
            except Exception as e:
                print(f"  EMBED ERROR: {str(e)[:60]}")
                retrieval_latencies.append(0)
                total_latencies.append(0)
                turn_results.append({
                    "turn": turn_num,
                    "user_message": user_msg,
                    "retrieval_error": str(e)[:200],
                    "retrieval_chunks": [],
                    "context_chars": 0,
                    "response_text": "",
                    "response_error": str(e)[:200],
                    "retrieval_latency_ms": 0,
                    "llm_latency_ms": 0,
                    "total_latency_ms": 0,
                    "parsed": {"question_count": 0, "gives_orientation": False, "says_not_documented": False, "detected_slots": {}, "response_length": 0},
                    "evaluation": {"passed": False, "empty_response": True, "forbidden_claims_count": 0},
                })
                continue

            # Milvus retrieval
            t_ret = time.time()
            try:
                chunks = search_milvus(client, args.collection_name, query_emb, args.top_n)
            except Exception as e:
                print(f"  MILVUS ERROR: {str(e)[:60]}")
                retrieval_latencies.append(0)
                total_latencies.append(0)
                turn_results.append({
                    "turn": turn_num,
                    "user_message": user_msg,
                    "retrieval_error": str(e)[:200],
                    "retrieval_chunks": [],
                    "context_chars": 0,
                    "response_text": "",
                    "retrieval_latency_ms": round((time.time() - t_ret) * 1000, 1),
                    "llm_latency_ms": 0,
                    "total_latency_ms": round((time.time() - t_start) * 1000, 1),
                    "parsed": {"question_count": 0, "gives_orientation": False, "says_not_documented": False, "detected_slots": {}, "response_length": 0},
                    "evaluation": {"passed": False, "empty_response": True, "forbidden_claims_count": 0},
                })
                continue

            retrieval_lat = round((time.time() - t_ret) * 1000, 1)
            retrieval_latencies.append(retrieval_lat)

            top_k_chunks = chunks[:args.top_k]
            context, context_chars = build_context(top_k_chunks, args.max_context_chars)

            turn_result = {
                "turn": turn_num,
                "user_message": user_msg,
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

            # Build prompt
            history_str = build_history(conversation_state["history"], max_chars=2000)
            slot_str = build_slot_state(conversation_state["slots"])

            prompt_parts = [f"## Contexto recuperado\n\n{context}\n" if context else ""]
            if history_str.strip():
                prompt_parts.append(f"## Historial de conversación\n\n{history_str}\n")
            prompt_parts.append(f"## Estado de slots\n\n{slot_str}\n")
            prompt_parts.append(f"## Mensaje del usuario\n\n{user_msg}")

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ]

            if args.no_llm:
                print(f"  retrieval={len(chunks)} chunks ({retrieval_lat}ms)", flush=True)
                no_llm_text = "(no-llm mode)"
                turn_result["response_text"] = no_llm_text
                turn_result["llm_latency_ms"] = 0
                turn_result["total_latency_ms"] = round((time.time() - t_start) * 1000, 1)
                parsed = parse_response(no_llm_text)
                turn_result["parsed"] = parsed
                turn_result["evaluation"] = evaluate_turn(case, no_llm_text, chunks, parsed)
                total_latencies.append(turn_result["total_latency_ms"])
                turn_results.append(turn_result)
                continue

            # LLM call
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
                print(f"  LLM ERROR: {str(e)[:80]}", flush=True)
                llm_lat = round((time.time() - t_llm) * 1000, 1)
                llm_latencies.append(llm_lat)
                total_lat = round((time.time() - t_start) * 1000, 1)
                total_latencies.append(total_lat)
                error_text = f"(LLM error: {str(e)[:200]})"
                turn_result["response_text"] = error_text
                turn_result["llm_latency_ms"] = llm_lat
                turn_result["total_latency_ms"] = total_lat
                parsed = parse_response(error_text)
                turn_result["parsed"] = parsed
                turn_result["evaluation"] = evaluate_turn(case, error_text, chunks, parsed)
                turn_results.append(turn_result)
                continue

            llm_lat = llm_result["latency_ms"]
            llm_latencies.append(llm_lat)
            total_lat = round((time.time() - t_start) * 1000, 1)
            total_latencies.append(total_lat)

            response_text = llm_result["content"]
            parsed = parse_response(response_text)
            evaluation = evaluate_turn(case, response_text, chunks, parsed)

            # Update conversation state
            conversation_state["turn_count"] += 1
            conversation_state["history"].append({"role": "user", "content": user_msg})
            conversation_state["history"].append({"role": "assistant", "content": response_text})
            conversation_state["total_questions_asked"] += parsed["question_count"]

            for slot_key in parsed.get("detected_slots", {}):
                conversation_state["slots"][slot_key] = "detected"

            # Truncate history if too long
            if len(conversation_state["history"]) > 20:
                conversation_state["history"] = conversation_state["history"][-20:]

            turn_result["response_text"] = response_text
            turn_result["llm_model"] = llm_result.get("model_returned", args.model)
            turn_result["llm_latency_ms"] = llm_lat
            turn_result["total_latency_ms"] = total_lat
            turn_result["llm_usage"] = llm_result.get("usage", {})
            turn_result["parsed"] = parsed
            turn_result["evaluation"] = evaluation

            turn_results.append(turn_result)

            passed_str = "P" if evaluation["passed"] else "F"
            flags = ""
            if evaluation.get("found_forbidden"):
                flags += " F"
            if evaluation.get("safety_flags"):
                flags += " S"
            if evaluation.get("too_many_questions"):
                flags += " Q"
            print(f"  retrieval={len(chunks)} ctx={context_chars}c llm={llm_lat}ms total={total_lat}ms {passed_str}{flags}", flush=True)
            response_preview = response_text[:120].replace("\n", " ")
            print(f"  Assistant: {response_preview}...")

        # Evaluate full scenario
        scenario_eval = evaluate_scenario(case, turn_results, conversation_state)
        scenario_result = {
            "case_id": case_id,
            "title": title,
            "category": case.get("category", ""),
            "risk_level": risk_level,
            "total_turns": len(user_turns),
            "conversation_state": {
                "slots_filled": list(conversation_state["slots"].keys()),
                "total_questions_asked": conversation_state["total_questions_asked"],
                "total_turns_processed": conversation_state["turn_count"],
            },
            "scenario_evaluation": scenario_eval,
            "turns": turn_results,
        }
        scenario_results.append(scenario_result)

        scenario_pass = "PASS" if scenario_eval["passed"] else "FAIL"
        print(f"\n  >>> Scenario {scenario_pass} | turns={scenario_eval['passed_turns']}/{scenario_eval['total_turns']} "
              f"forbidden={scenario_eval['total_forbidden_claims']} slots={scenario_eval['slots_filled']}/{len(scenario_eval['expected_slots'])}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total = len(scenario_results)
    if total == 0:
        print("\nNo scenarios executed.")
        sys.exit(0)

    passed_scenarios = sum(1 for r in scenario_results if r.get("scenario_evaluation", {}).get("passed", False))
    high_risk_total = sum(1 for r in scenario_results if r.get("risk_level") == "high")
    high_risk_passed = sum(1 for r in scenario_results if r.get("risk_level") == "high"
                          and r.get("scenario_evaluation", {}).get("passed", False))

    total_turns_executed = sum(r.get("total_turns", 0) for r in scenario_results)
    total_turns_passed = sum(r.get("scenario_evaluation", {}).get("passed_turns", 0) for r in scenario_results)

    forbidden_claims_total = sum(r.get("scenario_evaluation", {}).get("total_forbidden_claims", 0) for r in scenario_results)
    planned_misrepresented_total = sum(1 for r in scenario_results if r.get("scenario_evaluation", {}).get("planned_extension_misrepresented", False))
    hallucinated_pricing_total = sum(1 for r in scenario_results if r.get("scenario_evaluation", {}).get("hallucinated_pricing", False))

    avg_retrieval_lat = round(sum(retrieval_latencies) / len(retrieval_latencies), 1) if retrieval_latencies else 0
    avg_llm_lat = round(sum(llm_latencies) / len(llm_latencies), 1) if llm_latencies else 0
    avg_total_lat = round(sum(total_latencies) / len(total_latencies), 1) if total_latencies else 0

    sorted_total = sorted(total_latencies)
    p95_total = sorted_total[int(len(sorted_total) * 0.95)] if sorted_total else sorted_total[-1] if sorted_total else 0

    total_questions_sum = sum(r.get("scenario_evaluation", {}).get("total_questions", 0) for r in scenario_results)
    avg_questions_per_turn = round(total_questions_sum / total_turns_executed, 1) if total_turns_executed else 0
    max_questions_in_turn = max(
        (t.get("evaluation", {}).get("question_count", 0) for r in scenario_results for t in r.get("turns", [])),
        default=0,
    )

    slots_filled_sum = sum(r.get("scenario_evaluation", {}).get("slots_filled", 0) for r in scenario_results)
    slots_filled_avg = round(slots_filled_sum / total, 1) if total else 0

    diagnosis_orientation_count = sum(1 for r in scenario_results if r.get("scenario_evaluation", {}).get("has_diagnosis_orientation", False))
    useful_orientation_rate = round(diagnosis_orientation_count / total * 100, 1) if total else 0

    guardrail_failures = sum(1 for r in scenario_results if (
        r.get("scenario_evaluation", {}).get("total_forbidden_claims", 0) > 0
        or r.get("scenario_evaluation", {}).get("planned_extension_misrepresented", False)
        or r.get("scenario_evaluation", {}).get("hallucinated_pricing", False)
    ))

    scenario_pass_rate = round(passed_scenarios / total * 100, 1) if total else 0
    turn_pass_rate = round(total_turns_passed / total_turns_executed * 100, 1) if total_turns_executed else 0
    high_risk_rate = round(high_risk_passed / high_risk_total * 100, 1) if high_risk_total else 0

    # Decision rules
    if scenario_pass_rate >= 70 and high_risk_rate >= 90 and guardrail_failures == 0:
        rec = "A. Asistente conversacional viable para siguiente fase controlada."
    elif scenario_pass_rate >= 60 and guardrail_failures <= 2:
        rec = "B. Viable con guardrails más fuertes."
    elif avg_total_lat > 5000:
        rec = "C. Viable pero requiere respuesta progresiva/SSE."
    elif scenario_pass_rate < 40 and avg_retrieval_lat < 100:
        rec = "D. Requiere modelo alternativo."
    elif scenario_pass_rate < 40 and avg_retrieval_lat < 50:
        rec = "E. Requiere más knowledge coverage."
    else:
        rec = "F. No avanzar todavía."

    if avg_total_lat > 5000:
        rec += " (Reducir contexto/max-tokens para latencia.)"

    summary = {
        "experiment": "Sales Diagnosis Assistant Conversation Lab — Fase 1.7",
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "embedding_model": args.embedding_model,
        "dimensions": args.dimensions,
        "collection": args.collection_name,
        "top_n": args.top_n,
        "top_k": args.top_k,
        "max_context_chars": args.max_context_chars,
        "max_output_tokens": args.max_output_tokens,
        "total_scenarios": total,
        "passed_scenarios": passed_scenarios,
        "scenario_pass_rate": scenario_pass_rate,
        "total_turns": total_turns_executed,
        "passed_turns": total_turns_passed,
        "turn_pass_rate": turn_pass_rate,
        "high_risk_total": high_risk_total,
        "high_risk_passed": high_risk_passed,
        "high_risk_pass_rate": high_risk_rate,
        "avg_retrieval_latency_ms": avg_retrieval_lat,
        "avg_llm_latency_ms": avg_llm_lat,
        "avg_total_latency_ms": avg_total_lat,
        "p95_turn_latency_ms": p95_total,
        "avg_questions_per_turn": avg_questions_per_turn,
        "max_questions_in_turn": max_questions_in_turn,
        "slots_filled_avg": slots_filled_avg,
        "forbidden_claims_total": forbidden_claims_total,
        "planned_extension_misrepresented_count": planned_misrepresented_total,
        "hallucinated_pricing_count": hallucinated_pricing_total,
        "useful_orientation_rate": useful_orientation_rate,
        "diagnosis_orientation_count": diagnosis_orientation_count,
        "guardrail_failure_count": guardrail_failures,
        "no_llm_mode": args.no_llm,
        "architecture_recommendation": rec,
        "cases_passed": passed_scenarios,
        "cases_failed": total - passed_scenarios,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = f"conversation_lab_{ts}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "scenarios": scenario_results,
        "latencies_ms": {
            "retrieval": retrieval_latencies,
            "llm": llm_latencies,
            "total": total_latencies,
        },
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    md_content = generate_markdown(summary, scenario_results, args)
    md_path = RESULTS_DIR / f"{prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Report saved: {md_path}")

    print()
    print("=" * 70)
    print("SALES DIAGNOSIS ASSISTANT CONVERSATION LAB — SUMMARY")
    print("=" * 70)
    print(f"  Total scenarios:             {total}")
    print(f"  Scenario pass rate:          {passed_scenarios}/{total} ({scenario_pass_rate}%)")
    print(f"  Turn pass rate:              {total_turns_passed}/{total_turns_executed} ({turn_pass_rate}%)")
    print(f"  High-risk pass rate:         {high_risk_passed}/{high_risk_total} ({high_risk_rate}%)")
    print(f"  Avg retrieval latency:       {avg_retrieval_lat}ms")
    print(f"  Avg LLM latency:             {avg_llm_lat}ms")
    print(f"  Avg total latency:           {avg_total_lat}ms")
    print(f"  P95 turn latency:            {p95_total}ms")
    print(f"  Avg questions per turn:      {avg_questions_per_turn}")
    print(f"  Max questions in turn:       {max_questions_in_turn}")
    print(f"  Slots filled avg:            {slots_filled_avg}")
    print(f"  Forbidden claims:            {forbidden_claims_total}")
    print(f"  Planned ext misrepresented:  {planned_misrepresented_total}")
    print(f"  Hallucinated pricing:        {hallucinated_pricing_total}")
    print(f"  Useful orientation rate:     {useful_orientation_rate}%")
    print(f"  Guardrail failures:          {guardrail_failures}")
    print(f"  Cases passed:                {summary['cases_passed']}")
    print(f"  Cases failed:                {summary['cases_failed']}")
    print(f"  Recommendation: {rec}")


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def generate_markdown(summary: dict, scenario_results: list[dict], args: argparse.Namespace) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("# Sales Diagnosis Assistant Conversation Lab — Fase 1.7")
    lines.append("")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Model:** {args.model}")
    if args.reasoning_effort:
        lines.append(f"**Reasoning effort:** {args.reasoning_effort}")
    lines.append(f"**Embedding:** {args.embedding_model} ({args.dimensions}d)")
    lines.append(f"**Top-N:** {args.top_n} | **Top-K:** {args.top_k}")
    lines.append(f"**Max context chars:** {args.max_context_chars}")
    lines.append(f"**Max output tokens:** {args.max_output_tokens}")
    lines.append("")

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Scenario pass rate:** {summary['passed_scenarios']}/{summary['total_scenarios']} ({summary['scenario_pass_rate']}%)")
    lines.append(f"- **Turn pass rate:** {summary['passed_turns']}/{summary['total_turns']} ({summary['turn_pass_rate']}%)")
    lines.append(f"- **High-risk pass rate:** {summary['high_risk_passed']}/{summary['high_risk_total']} ({summary['high_risk_pass_rate']}%)")
    lines.append(f"- **Avg retrieval latency:** {summary['avg_retrieval_latency_ms']}ms")
    lines.append(f"- **Avg LLM latency:** {summary['avg_llm_latency_ms']}ms")
    lines.append(f"- **Avg total per turn:** {summary['avg_total_latency_ms']}ms")
    lines.append(f"- **P95 turn latency:** {summary['p95_turn_latency_ms']}ms")
    lines.append(f"- **Avg questions per turn:** {summary['avg_questions_per_turn']}")
    lines.append(f"- **Slots filled avg:** {summary['slots_filled_avg']}")
    lines.append(f"- **Forbidden claims:** {summary['forbidden_claims_total']}")
    lines.append(f"- **Planned ext misrepresented:** {summary['planned_extension_misrepresented_count']}")
    lines.append(f"- **Hallucinated pricing/SLA:** {summary['hallucinated_pricing_count']}")
    lines.append(f"- **Guardrail failures:** {summary['guardrail_failure_count']}")
    lines.append(f"- **Cases passed/failed:** {summary['cases_passed']}/{summary['cases_failed']}")
    lines.append("")
    lines.append(f"**Decisión recomendada:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Arquitectura evaluada")
    lines.append("")
    lines.append("PostgreSQL 18 source of truth + Milvus 2.6 vector runtime derivado + ")
    lines.append("Markdown context chunks + gpt-5-nano low + conversation state gestionado en memoria.")
    lines.append("PGVector como baseline/fallback. No ArangoDB. No cross-encoder. No producción.")
    lines.append("")

    lines.append("## Calidad conversacional")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| Scenario pass rate | {summary['scenario_pass_rate']}% |")
    lines.append(f"| Turn pass rate | {summary['turn_pass_rate']}% |")
    lines.append(f"| High-risk pass rate | {summary['high_risk_pass_rate']}% |")
    lines.append(f"| Avg questions per turn | {summary['avg_questions_per_turn']} |")
    lines.append(f"| Max questions in turn | {summary['max_questions_in_turn']} |")
    lines.append(f"| Useful orientation rate | {summary['useful_orientation_rate']}% |")
    lines.append("")

    lines.append("## Slots y diagnóstico")
    lines.append("")
    lines.append(f"- Slots filled avg: {summary['slots_filled_avg']}")
    lines.append(f"- Diagnosis/orientation given: {summary['diagnosis_orientation_count']}/{summary['total_scenarios']} ({summary['useful_orientation_rate']}%)")
    lines.append("")

    lines.append("## Seguridad comercial / anti-overpromise")
    lines.append("")
    lines.append(f"- Forbidden claims total: {summary['forbidden_claims_total']}")
    lines.append(f"- Planned extension misrepresented: {summary['planned_extension_misrepresented_count']}")
    lines.append(f"- Hallucinated pricing/SLA: {summary['hallucinated_pricing_count']}")
    lines.append(f"- Guardrail failures: {summary['guardrail_failure_count']}")
    if summary['forbidden_claims_total'] > 0 or summary['guardrail_failure_count'] > 0:
        lines.append("⚠️ Se detectaron fallos de guardrail comercial.")
    else:
        lines.append("✅ Guardrails comerciales respetados.")
    lines.append("")

    lines.append("## Latencia")
    lines.append("")
    lines.append(f"- Retrieval avg: {summary['avg_retrieval_latency_ms']}ms")
    lines.append(f"- LLM avg:       {summary['avg_llm_latency_ms']}ms")
    lines.append(f"- Total avg:     {summary['avg_total_latency_ms']}ms")
    lines.append(f"- P95 turn:      {summary['p95_turn_latency_ms']}ms")
    lines.append("")

    lines.append("## Casos aprobados")
    lines.append("")
    passed_cases = [r for r in scenario_results if r.get("scenario_evaluation", {}).get("passed", False)]
    if passed_cases:
        for r in passed_cases:
            lines.append(f"- `{r['case_id']}` — {r.get('title', '')} ({r.get('risk_level', '')})")
    else:
        lines.append("- Ningún caso aprobado.")
    lines.append("")

    lines.append("## Casos fallidos")
    lines.append("")
    failed_cases = [r for r in scenario_results if not r.get("scenario_evaluation", {}).get("passed", False)]
    if failed_cases:
        for r in failed_cases:
            se = r.get("scenario_evaluation", {})
            reasons = []
            if se.get("passed_turns", 0) < se.get("total_turns", 0):
                reasons.append(f"turns: {se['passed_turns']}/{se['total_turns']}")
            if se.get("total_forbidden_claims", 0) > 0:
                reasons.append(f"forbidden: {se['total_forbidden_claims']}")
            if not se.get("all_slots_detected", False):
                reasons.append(f"slots: {se['slots_filled']}/{len(se.get('expected_slots', []))}")
            if se.get("planned_extension_misrepresented", False):
                reasons.append("planned_ext_misrep")
            if se.get("hallucinated_pricing", False):
                reasons.append("hallucinated_pricing")
            r_str = ", ".join(reasons) if reasons else "unknown"
            lines.append(f"- `{r['case_id']}` — {r.get('title', '')} → {r_str}")
    else:
        lines.append("- No hay casos fallidos.")
    lines.append("")

    lines.append("## Hallazgos")
    lines.append("")
    if summary["avg_retrieval_latency_ms"] < 50:
        lines.append("- Retrieval en Milvus es rápido (< 50ms).")
    if summary["avg_llm_latency_ms"] > 0 and summary["avg_llm_latency_ms"] < 3000:
        lines.append("- Latencia LLM aceptable para flujo conversacional.")
    elif summary["avg_llm_latency_ms"] >= 3000:
        lines.append("- Latencia LLM elevada. Considerar reducir max_output_tokens.")
    if summary["avg_total_latency_ms"] > 5000:
        lines.append("- Latencia por turno > 5s. Probar prompt más corto/modelo alternativo/streaming.")
    if summary["forbidden_claims_total"] > 0:
        lines.append("- El modelo generó claims prohibidos. Reforzar guardrails en prompt.")
    if summary["planned_extension_misrepresented_count"] > 0:
        lines.append("- Algunas capacidades planned_extension se representaron incorrectamente.")
    if summary["hallucinated_pricing_count"] > 0:
        lines.append("- El modelo inventó precios/SLA. Crítico: no avanzar a runtime.")
    if summary["guardrail_failure_count"] > 0:
        lines.append("- Fallos de guardrail detectados. No avanzar sin resolver.")
    if summary["avg_questions_per_turn"] > 3:
        lines.append("- Demasiadas preguntas por turno. Ajustar prompt para 1 pregunta principal.")
    lines.append("")

    lines.append("## Decisión recomendada")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.7 — Sales Diagnosis Assistant Conversation Lab. "
                 "PostgreSQL source of truth, Milvus vector runtime, gpt-5-nano low generator, "
                 "conversation state in memory. No ArangoDB, no cross-encoder, no production changes, "
                 "no Step-to-Action, no lead capture, no diagnostic_code, no WhatsApp handoff._")
    return "\n".join(lines)


if __name__ == "__main__":
    main()

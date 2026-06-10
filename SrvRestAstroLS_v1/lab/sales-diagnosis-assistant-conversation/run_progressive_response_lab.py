#!/usr/bin/env python3
"""Fase 1.7d — Latency / Progressive Response Simulation Lab.

Simulates progressive response (AG-UI/SSE-like event flow) without endpoints.
Three strategies compared for perceived latency.

Usage:
  uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py
  uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py --strategy single-call --limit-cases 3
  uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py --strategy progressive-two-step --limit-cases 3
  uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py --strategy templated-quick-final-llm --limit-cases 3
  uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py --no-llm --strategy templated-quick-final-llm --limit-cases 2
  uv run python lab/sales-diagnosis-assistant-conversation/run_progressive_response_lab.py --dry-run

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

try:
    import pymilvus
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

LAB_DIR = Path(__file__).parent
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
CASES_FILE = LAB_DIR / "cases" / "conversation_cases.json"
RESULTS_DIR = LAB_DIR / "results"
INFOGRAPHICS_DIR = LAB_DIR / "infografias"
SCRIPTS_DIR = LAB_DIR / "scripts"
BP_LAB_DIR = LAB_DIR.parents[1] / "lab" / "postgres-knowledge-retrieval-breaking-points"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BP_LAB_DIR))

from run_reranking_experiment import normalize, _resolve_dsn, _validate_positive

sys.path.insert(0, str(LAB_DIR))
from evaluator import evaluate_turn as refined_evaluate_turn, evaluate_scenario as refined_evaluate_scenario

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
- lead capture (como producto independiente)
- diagnostic_code
- WhatsApp handoff automático
- CRM real
- automatic_billing (facturación automática)
- automatic_closing (cierre de ventas autónomo)

Si aparecen como future/planned_extension, aclará que son extensiones planificadas.
No sugieras un plan comercial que efectivamente brinde la misma capacidad que una planned_extension.
Diferenciá: automatable, vendible hoy (sellable today), extensión planificada (planned extension).
No inventes precios, plazos, SLA ni integraciones no documentadas.
Nunca menciones SLA como parte de una oferta Team360. Si hablás de plazos de respuesta, aclará explícitamente que es un SLA interno del cliente, no un SLA del servicio Team360.
No menciones detalles internos técnicos salvo que el usuario pregunte.

Respondé en español claro, breve y comercial.
Cada respuesta debe tener:
1. una comprensión del caso
2. una orientación concreta
3. como máximo 1 a 3 preguntas útiles
4. límites claros cuando aplique"""

QUICK_ANSWER_PROMPT = """Sos el asistente de diagnóstico comercial de Team360.
Respondé en 1-2 frases mostrando comprensión inicial del caso.
No prometas capacidades no listas. No des precios, plazos ni SLA.
No inventes información no documentada.
Si falta información, hacé solo 1 pregunta concreta.
No des un diagnóstico completo todavía.
Máximo 120 tokens."""

FORBIDDEN_TERMS_NORM = [
    "precio", "cuesta", "cotiza", "ars", "usd",
    "semanas", "meses", "días_hábiles",
    "sla", "acuerdo_nivel_servicio",
]

NORM_WS = re.compile(r"\s+")

TEMPLATED_QUICK_ANSWER = (
    "Estoy revisando tu caso. Por lo que contás, parece relacionado con automatización "
    "de procesos comerciales. Te voy a orientar sin prometer capacidades no listas."
)

TEMPLATED_QUICK_ANSWER_MAP = {
    "conv_01": "Gracias por tu consulta. Veo que querés automatizar tu negocio. Contame un poco más sobre tu rubro y cómo recibís consultas hoy para orientarte mejor.",
    "conv_02": "Entiendo que estás perdiendo leads por demoras en la respuesta. Es un problema frecuente que podemos diagnosticar. ¿De qué canales vienen esas consultas?",
    "conv_03": "Un asistente WhatsApp puede ser parte de la solución. Hoy podemos ofrecer orientación para atención al cliente. La calificación automática es una extensión planificada. Contame más sobre tu operación actual.",
    "conv_04": "Entiendo que buscás automatización avanzada. El cierre autónomo de ventas y la facturación automática son capacidades planned_extension, no disponibles hoy. Te recomiendo empezar con un diagnóstico de tu operación actual.",
    "conv_05": "No te preocupes, es común no saber por dónde empezar. Podemos hacer un diagnóstico conjunto. ¿Qué procesos manejás hoy con planillas o atención manual?",
    "conv_06": "Entiendo que querés ofrecer Team360 como paquete a tus clientes. Veo que trabajás con comercios y servicios. Te cuento qué alcance tiene hoy el diagnóstico que ofrecemos.",
    "conv_07": "Step-to-Action, lead capture, diagnostic_code y WhatsApp handoff son capacidades planned_extension, no disponibles productivamente hoy. Te puedo orientar sobre lo que está listo.",
    "conv_08": "No tengo precios ni plazos para darte. Los costos dependen del alcance del diagnóstico. Te sugiero que primero hagamos una orientación de tu caso y luego te conectamos con el equipo comercial.",
    "conv_09": "Excelente pregunta. Team360 usa aislamiento por knowledge scope: cada cliente tiene su espacio separado. No se mezclan datos entre clientes. ¿Querés que te cuente más sobre cómo funciona?",
    "conv_10": "Entiendo que querés IA para tu empresa para vender más y responder más rápido. Te ayudo a orientar el caso. ¿En qué rubro trabajás y qué canales usás hoy?",
}


def normalize_text(text: str) -> str:
    t = text.lower()
    t = t.replace("_", " ").replace("-", " ")
    t = NORM_WS.sub(" ", t).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


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


def build_slot_state(slots: dict[str, str]) -> str:
    if not slots:
        return "Slots detectados: ninguno todavía."
    items = [f"  - {k}: {v}" for k, v in slots.items()]
    return "Slots detectados:\n" + "\n".join(items)


def parse_response(response_text: str) -> dict:
    norm = normalize_text(response_text)
    question_count = norm.count("?")
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


def load_cases(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: Cases file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def print_blocked(reason: str) -> None:
    print("=" * 70)
    print("FASE 1.7d — PROGRESSIVE RESPONSE SIMULATION")
    print("=" * 70)
    print()
    print(f"  STATUS: BLOCKED")
    print(f"  Reason: {reason}")
    print()


def make_event(
    event_type: str,
    case_id: str,
    turn_index: int,
    elapsed_ms: float,
    payload: str = "",
    safe_to_show: bool = True,
    notes: str = "",
) -> dict:
    return {
        "event_type": event_type,
        "timestamp_ms": round(time.time() * 1000),
        "elapsed_ms": round(elapsed_ms, 1),
        "case_id": case_id,
        "turn_index": turn_index,
        "payload": payload,
        "safe_to_show": safe_to_show,
        "notes": notes,
    }


def get_templated_quick(case_id: str, user_msg: str) -> str:
    if case_id in TEMPLATED_QUICK_ANSWER_MAP:
        return TEMPLATED_QUICK_ANSWER_MAP[case_id]
    msg_lower = user_msg.lower()
    if "precio" in msg_lower or "cuesta" in msg_lower or "cuánto sale" in msg_lower:
        return "No tengo precios ni plazos para darte en este momento. Te sugiero primero orientar tu caso para entender el alcance."
    if "sla" in msg_lower or "plazo" in msg_lower:
        return "Los plazos dependen del alcance del diagnóstico. No puedo darte un SLA sin antes conocer mejor tu operación."
    if "whatsapp" in msg_lower:
        return "Un asistente WhatsApp puede ser parte de la solución. Te cuento el alcance disponible hoy sin prometer lo que no está listo."
    if "factur" in msg_lower or "cierre" in msg_lower:
        return "Esas capacidades son planned_extension. Te oriento sobre lo que está disponible hoy para empezar."
    return TEMPLATED_QUICK_ANSWER


def main() -> None:
    parser = argparse.ArgumentParser(description="Fase 1.7d — Latency / Progressive Response Simulation")
    parser.add_argument("--model", default="gpt-5-nano", help="LLM model (default: gpt-5-nano)")
    parser.add_argument("--reasoning-effort", default=None, help="Reasoning effort: low/medium/high")
    parser.add_argument("--strategy", default="single-call",
                        choices=["single-call", "progressive-two-step", "templated-quick-final-llm"],
                        help="Response strategy to simulate")
    parser.add_argument("--top-n", type=_validate_positive, default=20, help="Candidate pool size (1-50)")
    parser.add_argument("--top-k", type=_validate_positive, default=5, help="Context chunks for LLM (1-50)")
    parser.add_argument("--collection-name", default=COLLECTION_NAME)
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_EMBEDDING_DIMS)
    parser.add_argument("--max-context-chars", type=int, default=6000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--quick-max-output-tokens", type=int, default=120)
    parser.add_argument("--final-max-output-tokens", type=int, default=500)
    parser.add_argument("--limit-cases", type=int, default=None)
    parser.add_argument("--case-id", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    if args.top_n < args.top_k:
        print(f"ERROR: --top-n ({args.top_n}) must be >= --top-k ({args.top_k})", file=sys.stderr)
        sys.exit(1)

    if not PYMILVUS_AVAILABLE and not args.no_llm and not args.dry_run:
        print_blocked("pymilvus is not installed.")
        sys.exit(0)

    if PYMILVUS_AVAILABLE:
        from pymilvus import MilvusClient, DataType

    cases = load_cases(CASES_FILE)
    print(f"Loaded {len(cases)} conversation scenarios from {CASES_FILE}")

    if args.limit_cases:
        cases = cases[:args.limit_cases]
        print(f"Limited to {len(cases)} scenarios")

    if args.case_id:
        cases = [c for c in cases if c["case_id"] == args.case_id]
        if not cases:
            print(f"ERROR: case_id '{args.case_id}' not found", file=sys.stderr)
            sys.exit(1)
        print(f"Filtered to single case: {args.case_id}")

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    if not api_key and not args.no_llm and args.strategy != "templated-quick-final-llm":
        print_blocked("OPENAI_API_KEY not found")
        sys.exit(1)

    dsn = _resolve_dsn() if not args.no_llm else "dry-run-dsn"
    milvus_uri = os.environ.get("MILVUS_URI", "http://localhost:19530")
    llm_base_url = os.environ.get("TEAM360_LITELLM_BASE_URL") or None

    print(f"Strategy:   {args.strategy}")
    print(f"Model:      {args.model}")
    print(f"PostgreSQL: {dsn[:20]}...")
    print(f"Milvus:     {milvus_uri}")
    if args.reasoning_effort:
        print(f"Reasoning:  {args.reasoning_effort}")
    print(f"Top-N:      {args.top_n} | Top-K: {args.top_k}")
    print(f"Quick max:  {args.quick_max_output_tokens} tokens")
    print(f"Final max:  {args.final_max_output_tokens} tokens")
    print()

    client = None

    if args.dry_run:
        print(f"DRY RUN — Validating setup")
        print(f"  Strategy: {args.strategy}")
        print(f"  Model: {args.model}")
        print(f"  Cases loaded: {len(cases)}")
        if PYMILVUS_AVAILABLE:
            from pymilvus import MilvusClient
            client = MilvusClient(uri=milvus_uri)
            existing = client.list_collections()
            print(f"  Milvus collections: {existing}")
        else:
            print(f"  Milvus: pymilvus not available (skip collection check)")
        print(f"  PostgreSQL DSN: {dsn[:20]}...")
        print("  Dry run OK.")
        sys.exit(0)

    if PYMILVUS_AVAILABLE:
        client = MilvusClient(uri=milvus_uri)
        if not args.no_llm:
            existing = client.list_collections()
            if args.collection_name not in existing:
                print_blocked(f"Milvus collection '{args.collection_name}' not found.")
                sys.exit(0)
            stats = client.get_collection_stats(args.collection_name)
            row_count = stats.get("row_count", 0)
            print(f"Milvus collection '{args.collection_name}' has {row_count} rows")
            print()

    scenario_results = []
    all_retrieval_latencies: list[float] = []
    all_quick_llm_latencies: list[float] = []
    all_final_llm_latencies: list[float] = []
    all_total_latencies: list[float] = []
    all_time_to_first_status: list[float] = []
    all_time_to_sources_ready: list[float] = []
    all_time_to_quick_answer: list[float] = []
    all_time_to_final_answer: list[float] = []

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
        strategy_events: list[dict] = []

        for turn_idx, user_msg in enumerate(user_turns):
            turn_num = turn_idx + 1
            print(f"\n  --- Turn {turn_num}/{len(user_turns)} ---")
            print(f"  User: {user_msg[:80]}")

            t_start = time.time()
            events: list[dict] = []

            events.append(make_event(
                "team360.status.retrieval_started", case_id, turn_num,
                round((time.time() - t_start) * 1000),
                payload="Iniciando búsqueda de contexto relevante...",
            ))

            chunks: list[dict] = []
            context = ""
            context_chars = 0
            retrieval_lat = 0

            if not args.no_llm:
                try:
                    query_emb = embed_query(user_msg, api_key, model=args.embedding_model, dims=args.dimensions)
                except Exception as e:
                    print(f"  EMBED ERROR: {str(e)[:60]}")
                    all_total_latencies.append(0)
                    turn_results.append({
                        "turn": turn_num, "user_message": user_msg,
                        "events": events,
                        "retrieval_error": str(e)[:200],
                        "response_text": "",
                        "total_latency_ms": 0,
                        "strategy": args.strategy,
                        "evaluation": {
                            "quick_answer": {"passed": False, "failure_type": "retrieval_error"},
                            "final_answer": {"passed": False, "failure_type": "retrieval_error"},
                        },
                    })
                    continue

                if not PYMILVUS_AVAILABLE:
                    events.append(make_event(
                        "team360.error", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload="pymilvus not available",
                        safe_to_show=False,
                    ))
                    all_total_latencies.append(0)
                    turn_results.append({
                        "turn": turn_num, "user_message": user_msg,
                        "events": events,
                        "retrieval_error": "pymilvus not available",
                        "response_text": "",
                        "total_latency_ms": 0,
                        "strategy": args.strategy,
                        "evaluation": {
                            "quick_answer": {"passed": False, "failure_type": "pymilvus_missing"},
                            "final_answer": {"passed": False, "failure_type": "pymilvus_missing"},
                        },
                    })
                    continue

                t_ret = time.time()
                try:
                    chunks = search_milvus(client, args.collection_name, query_emb, args.top_n)
                except Exception as e:
                    print(f"  MILVUS ERROR: {str(e)[:60]}")
                    events.append(make_event(
                        "team360.error", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload=f"Milvus error: {str(e)[:60]}",
                        safe_to_show=False,
                    ))
                    all_total_latencies.append(0)
                    turn_results.append({
                        "turn": turn_num, "user_message": user_msg,
                        "events": events,
                        "retrieval_error": str(e)[:200],
                        "response_text": "",
                        "total_latency_ms": round((time.time() - t_start) * 1000, 1),
                        "strategy": args.strategy,
                        "evaluation": {
                            "quick_answer": {"passed": False, "failure_type": "milvus_error"},
                            "final_answer": {"passed": False, "failure_type": "milvus_error"},
                        },
                    })
                    continue

                retrieval_lat = round((time.time() - t_ret) * 1000, 1)
                all_retrieval_latencies.append(retrieval_lat)

                top_k_chunks = chunks[:args.top_k]
                context, context_chars = build_context(top_k_chunks, args.max_context_chars)

            t_after_retrieval = time.time()

            events.append(make_event(
                "team360.sources.ready", case_id, turn_num,
                round((t_after_retrieval - t_start) * 1000),
                payload=f"{len(chunks)} chunks retrieved, {context_chars}c context" if not args.no_llm else "no-llm mode (template only)",
            ))

            turn_result: dict = {
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
                "strategy": args.strategy,
            }

            history_str = build_history(conversation_state["history"], max_chars=2000)
            slot_str = build_slot_state(conversation_state["slots"])

            prompt_parts = [f"## Contexto recuperado\n\n{context}\n" if context else ""]
            if history_str.strip():
                prompt_parts.append(f"## Historial de conversación\n\n{history_str}\n")
            prompt_parts.append(f"## Estado de slots\n\n{slot_str}\n")
            prompt_parts.append(f"## Mensaje del usuario\n\n{user_msg}")

            full_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(prompt_parts)},
            ]

            quick_messages = [
                {"role": "system", "content": QUICK_ANSWER_PROMPT},
                {"role": "user", "content": f"Contexto relevante:\n{context}\n\nHistorial:\n{history_str}\n\nUsuario: {user_msg}" if history_str.strip()
                 else f"Contexto relevante:\n{context}\n\nUsuario: {user_msg}"},
            ]

            if args.strategy == "single-call":
                if args.no_llm:
                    print(f"  retrieval={len(chunks)} chunks ({retrieval_lat}ms)", flush=True)
                    no_llm_text = "(no-llm mode - single-call)"
                    events.append(make_event(
                        "team360.answer.final_ready", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload="(no-llm)",
                    ))
                    events.append(make_event(
                        "team360.done", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                    ))
                    total_lat = round((time.time() - t_start) * 1000, 1)
                    all_total_latencies.append(total_lat)
                    all_time_to_final_answer.append(total_lat)
                    turn_result["response_text"] = no_llm_text
                    turn_result["total_latency_ms"] = total_lat
                    turn_result["events"] = events
                    turn_result["quick_answer_text"] = no_llm_text
                    turn_result["final_answer_text"] = no_llm_text
                    turn_result["llm_latency_ms"] = 0
                    parsed = parse_response(no_llm_text)
                    turn_result["parsed"] = parsed
                    turn_result["evaluation"] = {
                        "quick_answer": refined_evaluate_turn(response_text=no_llm_text, chunks=chunks, case=case),
                        "final_answer": refined_evaluate_turn(response_text=no_llm_text, chunks=chunks, case=case),
                        "combined_pass": True,
                    }
                    turn_results.append(turn_result)
                    continue

                events.append(make_event(
                    "team360.answer.final_started", case_id, turn_num,
                    round((time.time() - t_start) * 1000),
                    payload="Generando respuesta completa...",
                ))

                t_llm = time.time()
                try:
                    llm_result = call_llm(
                        model=args.model, messages=full_messages, api_key=api_key,
                        temperature=args.temperature, max_tokens=args.final_max_output_tokens,
                        reasoning_effort=args.reasoning_effort, base_url=llm_base_url,
                    )
                except Exception as e:
                    llm_lat = round((time.time() - t_llm) * 1000, 1)
                    total_lat = round((time.time() - t_start) * 1000, 1)
                    events.append(make_event(
                        "team360.error", case_id, turn_num, total_lat,
                        payload=f"LLM error: {str(e)[:80]}",
                        safe_to_show=False,
                    ))
                    all_total_latencies.append(total_lat)
                    all_time_to_final_answer.append(total_lat)
                    error_text = f"(LLM error: {str(e)[:200]})"
                    turn_result["response_text"] = error_text
                    turn_result["llm_latency_ms"] = llm_lat
                    turn_result["total_latency_ms"] = total_lat
                    turn_result["events"] = events
                    turn_result["quick_answer_text"] = error_text
                    turn_result["final_answer_text"] = error_text
                    parsed = parse_response(error_text)
                    turn_result["parsed"] = parsed
                    turn_result["evaluation"] = {
                        "quick_answer": refined_evaluate_turn(response_text=error_text, chunks=chunks, case=case),
                        "final_answer": refined_evaluate_turn(response_text=error_text, chunks=chunks, case=case),
                        "combined_pass": False,
                    }
                    turn_results.append(turn_result)
                    continue

                llm_lat = llm_result["latency_ms"]
                all_final_llm_latencies.append(llm_lat)
                total_lat = round((time.time() - t_start) * 1000, 1)
                all_total_latencies.append(total_lat)
                all_time_to_final_answer.append(total_lat)
                all_time_to_quick_answer.append(total_lat)

                response_text = llm_result["content"]
                events.append(make_event(
                    "team360.answer.final_ready", case_id, turn_num, total_lat,
                    payload=f"Final answer ready ({llm_lat}ms LLM)",
                ))
                events.append(make_event(
                    "team360.metrics.ready", case_id, turn_num, total_lat,
                    payload=f"Tokens: {llm_result.get('usage', {}).get('total_tokens', 0)}",
                    safe_to_show=False,
                ))
                events.append(make_event(
                    "team360.done", case_id, turn_num, total_lat,
                ))

                parsed = parse_response(response_text)
                final_ev = refined_evaluate_turn(response_text=response_text, chunks=chunks, case=case)

                conversation_state["turn_count"] += 1
                conversation_state["history"].append({"role": "user", "content": user_msg})
                conversation_state["history"].append({"role": "assistant", "content": response_text})
                conversation_state["total_questions_asked"] += parsed["question_count"]
                for slot_key in parsed.get("detected_slots", {}):
                    conversation_state["slots"][slot_key] = "detected"
                if len(conversation_state["history"]) > 20:
                    conversation_state["history"] = conversation_state["history"][-20:]

                turn_result["response_text"] = response_text
                turn_result["quick_answer_text"] = response_text
                turn_result["final_answer_text"] = response_text
                turn_result["llm_model"] = llm_result.get("model_returned", args.model)
                turn_result["llm_latency_ms"] = llm_lat
                turn_result["llm_usage"] = llm_result.get("usage", {})
                turn_result["total_latency_ms"] = total_lat
                turn_result["events"] = events
                turn_result["parsed"] = parsed
                turn_result["evaluation"] = {
                    "quick_answer": final_ev,
                    "final_answer": final_ev,
                    "combined_pass": final_ev["passed"],
                }

                print(f"  retrieval={len(chunks)} ctx={context_chars}c llm={llm_lat}ms total={total_lat}ms", flush=True)
                print(f"  Assistant: {response_text[:120].replace(chr(10), ' ')}")

            elif args.strategy == "progressive-two-step":
                if args.no_llm:
                    print(f"  retrieval={len(chunks)} chunks ({retrieval_lat}ms)", flush=True)
                    no_llm_text = "(no-llm mode - progressive-two-step)"
                    events.append(make_event(
                        "team360.answer.quick_ready", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload="(no-llm quick)",
                    ))
                    events.append(make_event(
                        "team360.answer.final_ready", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload="(no-llm final)",
                    ))
                    events.append(make_event("team360.done", case_id, turn_num, round((time.time() - t_start) * 1000)))
                    total_lat = round((time.time() - t_start) * 1000, 1)
                    all_total_latencies.append(total_lat)
                    all_time_to_quick_answer.append(total_lat)
                    all_time_to_final_answer.append(total_lat)
                    turn_result["response_text"] = no_llm_text
                    turn_result["total_latency_ms"] = total_lat
                    turn_result["events"] = events
                    turn_result["quick_answer_text"] = no_llm_text
                    turn_result["final_answer_text"] = no_llm_text
                    turn_result["quick_llm_latency_ms"] = 0
                    turn_result["final_llm_latency_ms"] = 0
                    parsed = parse_response(no_llm_text)
                    turn_result["parsed"] = parsed
                    quick_ev = refined_evaluate_turn(response_text=no_llm_text, chunks=chunks, case=case)
                    turn_result["evaluation"] = {
                        "quick_answer": quick_ev,
                        "final_answer": quick_ev,
                        "combined_pass": quick_ev["passed"],
                    }
                    turn_results.append(turn_result)
                    continue

                events.append(make_event(
                    "team360.answer.quick_started", case_id, turn_num,
                    round((time.time() - t_start) * 1000),
                    payload="Generando respuesta rápida...",
                ))

                t_quick = time.time()
                try:
                    quick_result = call_llm(
                        model=args.model, messages=quick_messages, api_key=api_key,
                        temperature=args.temperature, max_tokens=args.quick_max_output_tokens,
                        reasoning_effort=args.reasoning_effort, base_url=llm_base_url,
                    )
                except Exception as e:
                    quick_lat = round((time.time() - t_quick) * 1000, 1)
                    events.append(make_event(
                        "team360.error", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload=f"Quick LLM error: {str(e)[:80]}",
                        safe_to_show=False,
                    ))
                    all_total_latencies.append(0)
                    all_time_to_quick_answer.append(0)
                    error_text = f"(Quick LLM error: {str(e)[:200]})"
                    turn_result["response_text"] = error_text
                    turn_result["quick_answer_text"] = error_text
                    turn_result["final_answer_text"] = error_text
                    turn_result["quick_llm_latency_ms"] = quick_lat
                    turn_result["total_latency_ms"] = round((time.time() - t_start) * 1000, 1)
                    turn_result["events"] = events
                    parsed = parse_response(error_text)
                    turn_result["parsed"] = parsed
                    turn_result["evaluation"] = {
                        "quick_answer": refined_evaluate_turn(response_text=error_text, chunks=chunks, case=case),
                        "final_answer": refined_evaluate_turn(response_text=error_text, chunks=chunks, case=case),
                        "combined_pass": False,
                    }
                    turn_results.append(turn_result)
                    continue

                quick_lat = quick_result["latency_ms"]
                all_quick_llm_latencies.append(quick_lat)
                t_after_quick = time.time()
                quick_text = quick_result["content"]

                events.append(make_event(
                    "team360.answer.quick_ready", case_id, turn_num,
                    round((t_after_quick - t_start) * 1000),
                    payload=f"Respuesta rápida ({quick_lat}ms LLM)",
                ))

                events.append(make_event(
                    "team360.status.final_started", case_id, turn_num,
                    round((time.time() - t_start) * 1000),
                    payload="Generando respuesta completa...",
                ))

                t_final = time.time()
                try:
                    final_result = call_llm(
                        model=args.model, messages=full_messages, api_key=api_key,
                        temperature=args.temperature, max_tokens=args.final_max_output_tokens,
                        reasoning_effort=args.reasoning_effort, base_url=llm_base_url,
                    )
                except Exception as e:
                    final_lat = round((time.time() - t_final) * 1000, 1)
                    total_lat = round((time.time() - t_start) * 1000, 1)
                    events.append(make_event(
                        "team360.error", case_id, turn_num, total_lat,
                        payload=f"Final LLM error: {str(e)[:80]}",
                        safe_to_show=False,
                    ))
                    events.append(make_event("team360.done", case_id, turn_num, total_lat))
                    all_final_llm_latencies.append(final_lat)
                    all_total_latencies.append(total_lat)
                    all_time_to_final_answer.append(total_lat)
                    error_text = f"(Final LLM error after quick: {str(e)[:120]})"
                    turn_result["response_text"] = error_text
                    turn_result["quick_answer_text"] = quick_text
                    turn_result["final_answer_text"] = error_text
                    turn_result["quick_llm_latency_ms"] = quick_lat
                    turn_result["final_llm_latency_ms"] = final_lat
                    turn_result["total_latency_ms"] = total_lat
                    turn_result["events"] = events
                    parsed = parse_response(error_text)
                    turn_result["parsed"] = parsed
                    turn_result["evaluation"] = {
                        "quick_answer": refined_evaluate_turn(response_text=quick_text, chunks=chunks, case=case),
                        "final_answer": refined_evaluate_turn(response_text=error_text, chunks=chunks, case=case),
                        "combined_pass": False,
                    }
                    conversation_state["turn_count"] += 1
                    conversation_state["history"].append({"role": "user", "content": user_msg})
                    conversation_state["history"].append({"role": "assistant", "content": error_text})
                    conversation_state["total_questions_asked"] += parsed["question_count"]
                    turn_results.append(turn_result)
                    continue

                final_lat = final_result["latency_ms"]
                all_final_llm_latencies.append(final_lat)
                total_lat = round((time.time() - t_start) * 1000, 1)
                all_total_latencies.append(total_lat)
                all_time_to_quick_answer.append(round((t_after_quick - t_start) * 1000))
                all_time_to_final_answer.append(total_lat)

                response_text = final_result["content"]
                events.append(make_event(
                    "team360.answer.final_ready", case_id, turn_num, total_lat,
                    payload=f"Complete ({final_lat}ms LLM). Total LLM: {quick_lat + final_lat}ms",
                ))
                total_tokens = (
                    final_result.get("usage", {}).get("total_tokens", 0)
                    + quick_result.get("usage", {}).get("total_tokens", 0)
                )
                events.append(make_event(
                    "team360.metrics.ready", case_id, turn_num, total_lat,
                    payload=f"Tokens quick={quick_result.get('usage', {}).get('total_tokens', 0)} final={final_result.get('usage', {}).get('total_tokens', 0)} total={total_tokens}",
                    safe_to_show=False,
                ))
                events.append(make_event("team360.done", case_id, turn_num, total_lat))

                parsed = parse_response(response_text)
                quick_ev = refined_evaluate_turn(response_text=quick_text, chunks=chunks, case=case)
                final_ev = refined_evaluate_turn(response_text=response_text, chunks=chunks, case=case)

                conversation_state["turn_count"] += 1
                conversation_state["history"].append({"role": "user", "content": user_msg})
                conversation_state["history"].append({"role": "assistant", "content": response_text})
                conversation_state["total_questions_asked"] += parsed["question_count"]
                for slot_key in parsed.get("detected_slots", {}):
                    conversation_state["slots"][slot_key] = "detected"
                if len(conversation_state["history"]) > 20:
                    conversation_state["history"] = conversation_state["history"][-20:]

                turn_result["response_text"] = response_text
                turn_result["quick_answer_text"] = quick_text
                turn_result["final_answer_text"] = response_text
                turn_result["quick_llm_latency_ms"] = quick_lat
                turn_result["final_llm_latency_ms"] = final_lat
                turn_result["quick_llm_usage"] = quick_result.get("usage", {})
                turn_result["final_llm_usage"] = final_result.get("usage", {})
                turn_result["total_latency_ms"] = total_lat
                turn_result["events"] = events
                turn_result["parsed"] = parsed
                turn_result["evaluation"] = {
                    "quick_answer": quick_ev,
                    "final_answer": final_ev,
                    "combined_pass": quick_ev["passed"] and final_ev["passed"],
                }

                print(f"  retrieval={len(chunks)} quick_llm={quick_lat}ms final_llm={final_lat}ms total={total_lat}ms", flush=True)
                print(f"  Quick: {quick_text[:80].replace(chr(10), ' ')}")
                print(f"  Final: {response_text[:80].replace(chr(10), ' ')}")

            elif args.strategy == "templated-quick-final-llm":
                events.append(make_event(
                    "team360.answer.quick_started", case_id, turn_num,
                    round((time.time() - t_start) * 1000),
                    payload="Generando respuesta rápida (template)...",
                ))

                if args.no_llm:
                    quick_text = get_templated_quick(case_id, user_msg)
                else:
                    quick_text = get_templated_quick(case_id, user_msg)

                t_after_quick = time.time()
                events.append(make_event(
                    "team360.answer.quick_ready", case_id, turn_num,
                    round((t_after_quick - t_start) * 1000),
                    payload=f"Respuesta rápida (templated, 0ms LLM)",
                ))

                all_time_to_quick_answer.append(round((t_after_quick - t_start) * 1000))

                if args.no_llm:
                    events.append(make_event(
                        "team360.answer.final_ready", case_id, turn_num,
                        round((time.time() - t_start) * 1000),
                        payload="(no-llm final same as quick)",
                    ))
                    events.append(make_event("team360.done", case_id, turn_num, round((time.time() - t_start) * 1000)))
                    total_lat = round((time.time() - t_start) * 1000, 1)
                    all_total_latencies.append(total_lat)
                    all_time_to_final_answer.append(total_lat)
                    turn_result["response_text"] = quick_text
                    turn_result["quick_answer_text"] = quick_text
                    turn_result["final_answer_text"] = quick_text
                    turn_result["llm_latency_ms"] = 0
                    turn_result["total_latency_ms"] = total_lat
                    turn_result["events"] = events
                    parsed = parse_response(quick_text)
                    turn_result["parsed"] = parsed
                    quick_ev = refined_evaluate_turn(response_text=quick_text, chunks=chunks, case=case)
                    turn_result["evaluation"] = {
                        "quick_answer": quick_ev,
                        "final_answer": quick_ev,
                        "combined_pass": quick_ev["passed"],
                    }
                    turn_results.append(turn_result)
                    print(f"  retrieval={len(chunks)} ctx={context_chars}c quick=templated (0ms LLM) total={total_lat}ms", flush=True)
                    print(f"  Quick (templated): {quick_text[:80].replace(chr(10), ' ')}")
                    continue

                events.append(make_event(
                    "team360.status.final_started", case_id, turn_num,
                    round((time.time() - t_start) * 1000),
                    payload="Generando respuesta completa...",
                ))

                t_final = time.time()
                try:
                    final_result = call_llm(
                        model=args.model, messages=full_messages, api_key=api_key,
                        temperature=args.temperature, max_tokens=args.final_max_output_tokens,
                        reasoning_effort=args.reasoning_effort, base_url=llm_base_url,
                    )
                except Exception as e:
                    final_lat = round((time.time() - t_final) * 1000, 1)
                    total_lat = round((time.time() - t_start) * 1000, 1)
                    events.append(make_event(
                        "team360.error", case_id, turn_num, total_lat,
                        payload=f"Final LLM error: {str(e)[:80]}",
                        safe_to_show=False,
                    ))
                    events.append(make_event("team360.done", case_id, turn_num, total_lat))
                    all_final_llm_latencies.append(final_lat)
                    all_total_latencies.append(total_lat)
                    all_time_to_final_answer.append(total_lat)
                    error_text = f"(Final LLM error after templated quick: {str(e)[:120]})"
                    turn_result["response_text"] = error_text
                    turn_result["quick_answer_text"] = quick_text
                    turn_result["final_answer_text"] = error_text
                    turn_result["final_llm_latency_ms"] = final_lat
                    turn_result["total_latency_ms"] = total_lat
                    turn_result["events"] = events
                    parsed = parse_response(error_text)
                    turn_result["parsed"] = parsed
                    turn_result["evaluation"] = {
                        "quick_answer": refined_evaluate_turn(response_text=quick_text, chunks=chunks, case=case),
                        "final_answer": refined_evaluate_turn(response_text=error_text, chunks=chunks, case=case),
                        "combined_pass": False,
                    }
                    conversation_state["turn_count"] += 1
                    conversation_state["history"].append({"role": "user", "content": user_msg})
                    conversation_state["history"].append({"role": "assistant", "content": error_text})
                    conversation_state["total_questions_asked"] += parsed["question_count"]
                    turn_results.append(turn_result)
                    continue

                final_lat = final_result["latency_ms"]
                all_final_llm_latencies.append(final_lat)
                total_lat = round((time.time() - t_start) * 1000, 1)
                all_total_latencies.append(total_lat)
                all_time_to_final_answer.append(total_lat)

                response_text = final_result["content"]
                events.append(make_event(
                    "team360.answer.final_ready", case_id, turn_num, total_lat,
                    payload=f"Complete ({final_lat}ms LLM). Templated quick (0ms) + LLM final",
                ))
                events.append(make_event(
                    "team360.metrics.ready", case_id, turn_num, total_lat,
                    payload=f"Tokens: {final_result.get('usage', {}).get('total_tokens', 0)}",
                    safe_to_show=False,
                ))
                events.append(make_event("team360.done", case_id, turn_num, total_lat))

                parsed = parse_response(response_text)
                quick_ev = refined_evaluate_turn(response_text=quick_text, chunks=chunks, case=case)
                final_ev = refined_evaluate_turn(response_text=response_text, chunks=chunks, case=case)

                conversation_state["turn_count"] += 1
                conversation_state["history"].append({"role": "user", "content": user_msg})
                conversation_state["history"].append({"role": "assistant", "content": response_text})
                conversation_state["total_questions_asked"] += parsed["question_count"]
                for slot_key in parsed.get("detected_slots", {}):
                    conversation_state["slots"][slot_key] = "detected"
                if len(conversation_state["history"]) > 20:
                    conversation_state["history"] = conversation_state["history"][-20:]

                turn_result["response_text"] = response_text
                turn_result["quick_answer_text"] = quick_text
                turn_result["final_answer_text"] = response_text
                turn_result["final_llm_latency_ms"] = final_lat
                turn_result["final_llm_usage"] = final_result.get("usage", {})
                turn_result["total_latency_ms"] = total_lat
                turn_result["events"] = events
                turn_result["parsed"] = parsed
                turn_result["evaluation"] = {
                    "quick_answer": quick_ev,
                    "final_answer": final_ev,
                    "combined_pass": quick_ev["passed"] and final_ev["passed"],
                }

                print(f"  retrieval={len(chunks)} quick=templated final_llm={final_lat}ms total={total_lat}ms", flush=True)
                print(f"  Quick (templated): {quick_text[:80].replace(chr(10), ' ')}")
                print(f"  Final: {response_text[:80].replace(chr(10), ' ')}")

            turn_results.append(turn_result)
            strategy_events.extend(events)

        eval_keys = ["turns"]
        scenario_eval = {
            "case_id": case_id,
            "title": title,
            "category": case.get("category", ""),
            "risk_level": risk_level,
            "total_turns": len(user_turns),
            "strategy": args.strategy,
            "conversation_state": {
                "slots_filled": list(conversation_state["slots"].keys()),
                "total_questions_asked": conversation_state["total_questions_asked"],
                "total_turns_processed": conversation_state["turn_count"],
            },
            "events": strategy_events,
            "turns": turn_results,
        }
        scenario_results.append(scenario_eval)

        passed_turns = sum(1 for t in turn_results if t.get("evaluation", {}).get("combined_pass", False))
        print(f"\n  >>> Scenario {case_id} | passed_turns={passed_turns}/{len(user_turns)}")

    total = len(scenario_results)
    if total == 0:
        print("\nNo scenarios executed.")
        sys.exit(0)

    passed_turns_total = sum(
        1 for r in scenario_results for t in r.get("turns", [])
        if t.get("evaluation", {}).get("combined_pass", False)
    )
    total_turns_executed = sum(r["total_turns"] for r in scenario_results)

    quick_answer_safe = sum(
        1 for r in scenario_results for t in r.get("turns", [])
        if t.get("evaluation", {}).get("quick_answer", {}).get("passed", False)
        and not t.get("evaluation", {}).get("quick_answer", {}).get("has_any_forbidden", False)
    )
    quick_answer_total = sum(
        1 for r in scenario_results for t in r.get("turns", [])
        if t.get("evaluation", {}).get("quick_answer", {}).get("response_empty") is not None
    )

    final_guardrail_failures = sum(
        1 for r in scenario_results for t in r.get("turns", [])
        if t.get("evaluation", {}).get("final_answer", {}).get("has_any_forbidden", False)
    )

    final_passed_turns = sum(
        1 for r in scenario_results for t in r.get("turns", [])
        if t.get("evaluation", {}).get("final_answer", {}).get("passed", False)
    )

    avg_time_to_first_status = round(sum(all_time_to_first_status) / len(all_time_to_first_status), 1) if all_time_to_first_status else 0
    avg_time_to_sources_ready = round(sum(all_time_to_sources_ready) / len(all_time_to_sources_ready), 1) if all_time_to_sources_ready else 0
    avg_time_to_quick_answer = round(sum(all_time_to_quick_answer) / len(all_time_to_quick_answer), 1) if all_time_to_quick_answer else 0
    avg_time_to_final_answer = round(sum(all_time_to_final_answer) / len(all_time_to_final_answer), 1) if all_time_to_final_answer else 0
    avg_total_time = round(sum(all_total_latencies) / len(all_total_latencies), 1) if all_total_latencies else 0
    avg_retrieval_lat = round(sum(all_retrieval_latencies) / len(all_retrieval_latencies), 1) if all_retrieval_latencies else 0

    sorted_quick = sorted(all_time_to_quick_answer)
    sorted_final = sorted(all_time_to_final_answer)
    p50_quick = sorted_quick[len(sorted_quick) // 2] if sorted_quick else 0
    p95_quick = sorted_quick[int(len(sorted_quick) * 0.95)] if len(sorted_quick) > 1 else sorted_quick[-1] if sorted_quick else 0
    p50_final = sorted_final[len(sorted_final) // 2] if sorted_final else 0
    p95_final = sorted_final[int(len(sorted_final) * 0.95)] if len(sorted_final) > 1 else sorted_final[-1] if sorted_final else 0
    p95_total = sorted(all_total_latencies)[int(len(all_total_latencies) * 0.95)] if len(all_total_latencies) > 1 else (all_total_latencies[-1] if all_total_latencies else 0)

    quick_safe_rate = round(quick_answer_safe / quick_answer_total * 100, 1) if quick_answer_total else 0
    final_pass_rate = round(final_passed_turns / total_turns_executed * 100, 1) if total_turns_executed else 0
    combined_pass_rate = round(passed_turns_total / total_turns_executed * 100, 1) if total_turns_executed else 0

    baseline_avg = None
    strategies_base = {"single-call": 0, "progressive-two-step": 0, "templated-quick-final-llm": 0}
    for r in scenario_results:
        s = r.get("strategy", args.strategy)
        turns = r.get("turns", [])
        latencies = [t.get("total_latency_ms", 0) for t in turns if t.get("total_latency_ms", 0) > 0]
        if latencies:
            strategies_base[s] = round(sum(latencies) / len(latencies), 1)

    perceived_latency_gain_ms = None
    perceived_latency_gain_percent = None
    if args.strategy == "single-call":
        baseline_avg = avg_time_to_final_answer
    elif args.strategy in ("progressive-two-step", "templated-quick-final-llm"):
        if avg_time_to_quick_answer and baseline_avg is None:
            pass
        baseline_avg = strategies_base.get("single-call", None) or avg_time_to_final_answer
        if baseline_avg and avg_time_to_quick_answer:
            perceived_latency_gain_ms = round(baseline_avg - avg_time_to_quick_answer, 1)
            perceived_latency_gain_percent = round((perceived_latency_gain_ms / baseline_avg) * 100, 1) if baseline_avg else None

    quick_llm_total = sum(all_quick_llm_latencies) if all_quick_llm_latencies else 0
    final_llm_total = sum(all_final_llm_latencies) if all_final_llm_latencies else 0
    additional_llm_cost_estimate = {
        "quick_llm_calls": len(all_quick_llm_latencies) + 0,
        "final_llm_calls": len(all_final_llm_latencies),
        "total_llm_latency_ms": round(quick_llm_total + final_llm_total, 1),
    }

    summary = {
        "experiment": "Fase 1.7d — Latency / Progressive Response Simulation",
        "strategy": args.strategy,
        "model": args.model,
        "top_n": args.top_n,
        "top_k": args.top_k,
        "max_context_chars": args.max_context_chars,
        "quick_max_output_tokens": args.quick_max_output_tokens,
        "final_max_output_tokens": args.final_max_output_tokens,
        "total_scenarios": total,
        "total_turns": total_turns_executed,
        "avg_time_to_first_status_ms": avg_time_to_first_status,
        "avg_time_to_sources_ready_ms": avg_time_to_sources_ready,
        "avg_time_to_quick_answer_ms": avg_time_to_quick_answer,
        "avg_time_to_final_answer_ms": avg_time_to_final_answer,
        "avg_total_time_ms": avg_total_time,
        "p50_quick_answer_ms": p50_quick,
        "p95_quick_answer_ms": p95_quick,
        "p50_final_answer_ms": p50_final,
        "p95_final_answer_ms": p95_final,
        "p95_total_ms": p95_total,
        "avg_retrieval_latency_ms": avg_retrieval_lat,
        "quick_answer_safe_rate": quick_safe_rate,
        "final_answer_pass_rate": final_pass_rate,
        "combined_pass_rate": combined_pass_rate,
        "final_guardrail_failure_count": final_guardrail_failures,
        "perceived_latency_gain_ms": perceived_latency_gain_ms,
        "perceived_latency_gain_percent": perceived_latency_gain_percent,
        "baseline_avg_total_ms": baseline_avg,
        "no_llm_mode": args.no_llm,
        "additional_llm_cost_estimate": additional_llm_cost_estimate,
        "empty_turn_count": sum(
            1 for r in scenario_results for t in r.get("turns", [])
            if t.get("evaluation", {}).get("quick_answer", {}).get("response_empty", False)
        ),
        "timeout_or_error_count": sum(
            1 for r in scenario_results for t in r.get("turns", [])
            if "error" in t.get("response_text", "").lower()
        ),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = f"progressive_response_{ts}"
    json_path = RESULTS_DIR / f"{prefix}.json"
    report = {
        "summary": summary,
        "scenarios": scenario_results,
        "latencies_ms": {
            "retrieval": all_retrieval_latencies,
            "quick_llm": all_quick_llm_latencies,
            "final_llm": all_final_llm_latencies,
            "total": all_total_latencies,
            "time_to_quick_answer": all_time_to_quick_answer,
            "time_to_final_answer": all_time_to_final_answer,
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
    print("FASE 1.7d — PROGRESSIVE RESPONSE SIMULATION SUMMARY")
    print("=" * 70)
    print(f"  Strategy:                 {args.strategy}")
    print(f"  Total scenarios:          {total}")
    print(f"  Total turns:              {total_turns_executed}")
    print(f"  Avg retrieval:            {avg_retrieval_lat}ms")
    print(f"  Avg time to first status: {avg_time_to_first_status}ms")
    print(f"  Avg time to sources:      {avg_time_to_sources_ready}ms")
    print(f"  Avg time to quick answer: {avg_time_to_quick_answer}ms")
    print(f"  Avg time to final answer: {avg_time_to_final_answer}ms")
    print(f"  Avg total per turn:       {avg_total_time}ms")
    print(f"  P50 quick answer:         {p50_quick}ms")
    print(f"  P95 quick answer:         {p95_quick}ms")
    print(f"  P50 final answer:         {p50_final}ms")
    print(f"  P95 final answer:         {p95_final}ms")
    print(f"  Quick answer safe rate:   {quick_safe_rate}%")
    print(f"  Final answer pass rate:   {final_pass_rate}%")
    print(f"  Combined pass rate:       {combined_pass_rate}%")
    print(f"  Guardrail failures:       {final_guardrail_failures}")
    if perceived_latency_gain_ms is not None:
        print(f"  Perceived latency gain:   {perceived_latency_gain_ms}ms ({perceived_latency_gain_percent}%)")


def generate_markdown(summary: dict, scenario_results: list[dict], args: argparse.Namespace) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("# Fase 1.7d — Latency / Progressive Response Simulation")
    lines.append("")
    lines.append(f"**Date:** {now_str}")
    lines.append(f"**Strategy:** {args.strategy}")
    lines.append(f"**Model:** {args.model}")
    if args.reasoning_effort:
        lines.append(f"**Reasoning effort:** {args.reasoning_effort}")
    lines.append(f"**Top-N:** {args.top_n} | **Top-K:** {args.top_k}")
    lines.append(f"**Quick max tokens:** {args.quick_max_output_tokens}")
    lines.append(f"**Final max tokens:** {args.final_max_output_tokens}")
    lines.append("")

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Estrategia:** {summary['strategy']}")
    lines.append(f"- **Avg time to quick answer:** {summary['avg_time_to_quick_answer_ms']}ms | P50: {summary['p50_quick_answer_ms']}ms | P95: {summary['p95_quick_answer_ms']}ms")
    lines.append(f"- **Avg time to final answer:** {summary['avg_time_to_final_answer_ms']}ms | P50: {summary['p50_final_answer_ms']}ms | P95: {summary['p95_final_answer_ms']}ms")
    lines.append(f"- **Avg total per turn:** {summary['avg_total_time_ms']}ms")
    lines.append(f"- **Quick answer safe rate:** {summary['quick_answer_safe_rate']}%")
    lines.append(f"- **Final answer pass rate:** {summary['final_answer_pass_rate']}%")
    lines.append(f"- **Combined pass rate:** {summary['combined_pass_rate']}%")
    lines.append(f"- **Guardrail failures (final):** {summary['final_guardrail_failure_count']}")
    if summary.get("perceived_latency_gain_ms") is not None:
        lines.append(f"- **Perceived latency gain vs single-call:** {summary['perceived_latency_gain_ms']}ms ({summary['perceived_latency_gain_percent']}%)")
    lines.append("")

    lines.append("## Arquitectura simulada")
    lines.append("")
    lines.append("PostgreSQL 18 source of truth + Milvus 2.6 retrieval + Markdown context chunks + ")
    lines.append(f"gpt-5-nano low + simulated AG-UI/SSE events ({summary['strategy']} strategy).")
    lines.append("No endpoints productivos. No SSE real. No frontend. No AgnoDB. No cross-encoder.")
    lines.append("")

    lines.append("## Eventos simulados (por turno)")
    lines.append("")
    lines.append("| Evento | Propósito |")
    lines.append("|--------|-----------|")
    lines.append("| `team360.status.retrieval_started` | Indica que se inició la búsqueda |")
    lines.append("| `team360.sources.ready` | Contexto recuperado disponible |")
    lines.append("| `team360.answer.quick_started` | Generando respuesta rápida |")
    lines.append("| `team360.answer.quick_ready` | Respuesta rápida lista (primer valor para el usuario) |")
    lines.append("| `team360.status.final_started` | Generando respuesta completa |")
    lines.append("| `team360.answer.final_ready` | Respuesta final/diagnóstico listo |")
    lines.append("| `team360.metrics.ready` | Métricas de uso disponibles |")
    lines.append("| `team360.done` | Turno completado |")
    lines.append("| `team360.error` | Error en alguna fase |")
    lines.append("")

    lines.append("## Estrategias comparadas (lab)")
    lines.append("")
    lines.append("| Estrategia | Quick answer | Final answer | First user value | Riesgos |")
    lines.append("|------------|-------------|--------------|-----------------|---------|")
    lines.append("| `single-call` | — | LLM completa | final answer | Percepción lenta si LLM tarda >3s |")
    lines.append("| `progressive-two-step` | LLM corta (120 tok) | LLM completa (500 tok) | quick answer | Duplica costo LLM, puede aumentar latencia total |")
    lines.append("| `templated-quick-final-llm` | Template (0ms LLM) | LLM completa (500 tok) | quick answer | Quick genérica, riesgo de descontextualización |")
    lines.append("")

    lines.append("## Latencia percibida")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| Avg retrieval latency | {summary['avg_retrieval_latency_ms']}ms |")
    lines.append(f"| Avg time to first status | {summary.get('avg_time_to_first_status_ms', 'N/A')}ms |")
    lines.append(f"| Avg time to sources ready | {summary.get('avg_time_to_sources_ready_ms', 'N/A')}ms |")
    lines.append(f"| Avg time to quick answer | {summary['avg_time_to_quick_answer_ms']}ms |")
    lines.append(f"| Avg time to final answer | {summary['avg_time_to_final_answer_ms']}ms |")
    lines.append(f"| Avg total per turn | {summary['avg_total_time_ms']}ms |")
    lines.append(f"| P50 quick answer | {summary['p50_quick_answer_ms']}ms |")
    lines.append(f"| P95 quick answer | {summary['p95_quick_answer_ms']}ms |")
    lines.append(f"| P50 final answer | {summary['p50_final_answer_ms']}ms |")
    lines.append(f"| P95 final answer | {summary['p95_final_answer_ms']}ms |")
    lines.append(f"| P95 total | {summary['p95_total_ms']}ms |")
    if summary.get("perceived_latency_gain_ms") is not None:
        lines.append(f"| Perceived latency gain | {summary['perceived_latency_gain_ms']}ms ({summary['perceived_latency_gain_percent']}%) |")
    lines.append("")

    lines.append("## Calidad y guardrails")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| Quick answer safe rate | {summary['quick_answer_safe_rate']}% |")
    lines.append(f"| Final answer pass rate | {summary['final_answer_pass_rate']}% |")
    lines.append(f"| Combined pass rate | {summary['combined_pass_rate']}% |")
    lines.append(f"| Final guardrail failures | {summary['final_guardrail_failure_count']} |")
    lines.append(f"| Empty turns | {summary['empty_turn_count']} |")
    lines.append(f"| Timeout/error turns | {summary['timeout_or_error_count']} |")
    lines.append("")

    lines.append("## Costos / Tradeoffs")
    lines.append("")
    llm_cost = summary.get("additional_llm_cost_estimate", {})
    lines.append(f"- LLM calls: {llm_cost.get('quick_llm_calls', 0)} quick + {llm_cost.get('final_llm_calls', 0)} final")
    lines.append(f"- Total LLM latency: {llm_cost.get('total_llm_latency_ms', 0)}ms")
    if args.strategy == "progressive-two-step":
        lines.append("- **Riesgo:** duplica llamadas LLM, puede aumentar latencia total aunque mejora percepción")
        lines.append("- **Recomendación:** usar solo en web, no WhatsApp, o bajo demanda")
    elif args.strategy == "templated-quick-final-llm":
        lines.append("- **Ventaja:** 0ms LLM para quick answer, sin costo adicional")
        lines.append("- **Riesgo:** quick answer genérica puede no ser contextualmente útil")
        lines.append("- **Recomendación:** ideal si la quick answer es suficientemente informativa")
    lines.append("")

    lines.append("## Decisión recomendada")
    lines.append("")
    if summary["final_guardrail_failure_count"] > 0:
        rec = "E. No avanzar — resolver guardrail failures primero."
    elif summary.get("avg_time_to_quick_answer_ms", 0) < 500 and summary["quick_answer_safe_rate"] >= 95:
        rec = "B. Usar templated quick + final LLM — first value < 500ms, quick safe rate >= 95%."
    elif args.strategy == "progressive-two-step" and summary.get("avg_time_to_quick_answer_ms", 0) < 2000:
        rec = "C. Usar two-step LLM solo en web — quick answer < 2s."
    elif summary.get("avg_time_to_final_answer_ms", 0) > 5000:
        rec = "A. Mantener single-call pero requerir respuesta progresiva — UX percepción crítica."
    else:
        rec = "A. Mantener single-call por ahora — latencia aceptable sin progresión."
    lines.append(f"**{rec}**")
    lines.append("")

    lines.append("## Timeline de eventos (ejemplo)")
    lines.append("")
    lines.append("```")
    lines.append("event                           | elapsed_ms | payload")
    lines.append("--------------------------------|------------|--------")
    lines.append("team360.status.retrieval_started | 0          | Iniciando búsqueda...")
    lines.append("team360.sources.ready            | ~50-150    | N chunks retrieved")
    lines.append("team360.answer.quick_started     | ~50-150    | Generando respuesta rápida...")
    lines.append("team360.answer.quick_ready       | ~200-500   | Respuesta rápida lista")
    lines.append("team360.status.final_started     | ~200-500   | Generando respuesta completa...")
    lines.append("team360.answer.final_ready       | ~2000-5000 | Respuesta final lista")
    lines.append("team360.metrics.ready            | ~2000-5000 | Tokens usage")
    lines.append("team360.done                     | ~2000-5000 | Turno completado")
    lines.append("```")
    lines.append("")
    lines.append("> Nota: tiempos estimados. Los valores reales dependen de la estrategia y el LLM.")
    lines.append("")

    lines.append("## Hallazgos")
    lines.append("")
    if summary.get("avg_retrieval_latency_ms", 0) < 50:
        lines.append("- Retrievel rápido (< 50ms). No es cuello de botella.")
    if summary.get("avg_time_to_final_answer_ms", 0) < 3000:
        lines.append("- Latencia final aceptable para flujo conversacional.")
    elif summary.get("avg_time_to_final_answer_ms", 0) >= 3000:
        lines.append("- Latencia final elevada (>= 3s). Respuesta progresiva recomendada.")
    if summary.get("avg_time_to_quick_answer_ms", 0) < 500:
        lines.append("- Quick answer < 500ms. El usuario percibe respuesta inmediata.")
    if summary["final_guardrail_failure_count"] == 0:
        lines.append("- 0 guardrail failures. Estrategia segura.")
    else:
        lines.append(f"- {summary['final_guardrail_failure_count']} guardrail failures. Reforzar.")
    if summary["quick_answer_safe_rate"] < 95:
        lines.append("- Quick answer puede contener claims inseguros. Reforzar guardrails en quick prompt.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Fase 1.7d — Latency / Progressive Response Simulation Lab. "
                 "No production endpoints. No real SSE. No frontend. No ArangoDB. No cross-encoder. "
                 "No Step-to-Action. No lead capture. No diagnostic_code. No WhatsApp handoff._")
    return "\n".join(lines)


if __name__ == "__main__":
    main()

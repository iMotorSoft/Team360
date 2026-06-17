#!/usr/bin/env python3
"""Benchmark Vera conversation: single-model vs staged-models strategy."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, stdev
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, OpenAIError


BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
REQUEST_TIMEOUT_SECONDS = 60.0

SYSTEM_PROMPT_BASE = (
    "Sos Vera, diagnosticadora de automatizaciones de Team360. "
    "Conversás con usuarios no técnicos. Respondés en español natural.\n\n"
    "Durante la entrevista:\n"
    "- Una sola pregunta principal por turno.\n"
    "- Respuestas breves.\n"
    "- No repetir preguntas.\n"
    "- No convertir la conversación en formulario.\n"
    "- Demostrar comprensión sin repetir todo.\n"
    "- No prometer integraciones no validadas.\n\n"
    "Cuando haya información suficiente:\n"
    "- Entregar diagnóstico inicial profesional.\n"
    "- Resumir proceso.\n"
    "- Identificar oportunidad.\n"
    "- Mencionar sistemas e integración.\n"
    "- Señalar riesgos.\n"
    "- Proponer próximo paso.\n\n"
    "Distinguir factibilidad técnica de disponibilidad comercial.\n\n"
    "No activar lead capture, WhatsApp handoff, diagnostic_code ni Step-to-Action.\n\n"
    "No inventar pricing, SLA o ROI.\n\n"
    "Cierre del diagnóstico:\n"
    "- Cuando el usuario responda \"no\" al turno de aprobación humana, significa que NO requiere aprobación humana.\n"
    "- Ese es el momento de cerrar el diagnóstico con la respuesta final.\n"
    "- No hacer más preguntas salvo bloqueo crítico real.\n"
    "- La respuesta final debe: resumir el proceso, reconocer el volumen diario, identificar los canales, "
    "recomendar automatización o semi-automatización, mencionar necesidad de validar integración, "
    "no prometer implementación cerrada y dar un próximo paso concreto."
)

ACTION_INSTRUCTIONS = {
    "reflect_and_ask": (
        "Acción obligatoria de este turno: continuar el diagnóstico. "
        "No generes todavía el diagnóstico final. "
        "Respondé brevemente y hacé una sola pregunta principal que avance el caso."
    ),
    "diagnose": (
        "Acción obligatoria de este turno: generar ahora el diagnóstico inicial completo. "
        "No hagas nuevas preguntas salvo que exista un bloqueo crítico real."
    ),
}

CONVERSATION_TURNS = [
    "quiero responder a mensajes de venta",
    "web",
    "chat en vivo",
    "correo electrónico",
    "100",
    "gmail",
    "información de productos",
    "no",
]

INTERMEDIATE_MAX_TOKENS = 120
FINAL_MAX_TOKENS = 500
TEMPERATURE = 0.2


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def sanitize_message(message: str, secret: str | None = None) -> str:
    sanitized = message or ""
    if secret:
        sanitized = sanitized.replace(secret, "[REDACTED_GEMINI_API_KEY]")
    return sanitized


def object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    return {}


def extract_usage(usage: Any) -> tuple[dict[str, Any], int | None, int | None, int | None]:
    data = object_to_dict(usage)
    prompt_tokens = data.get("prompt_tokens")
    completion_tokens = data.get("completion_tokens")
    total_tokens = data.get("total_tokens")
    return data, prompt_tokens, completion_tokens, total_tokens


def load_prices(prices_path: Path | None) -> dict[str, dict[str, float | None]]:
    if prices_path and prices_path.exists():
        with open(prices_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("models", {})
    return {}


def estimate_cost(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    model: str,
    prices: dict[str, dict[str, float | None]],
) -> tuple[float | None, bool]:
    if prompt_tokens is None or completion_tokens is None:
        return None, False
    model_prices = prices.get(model)
    if not model_prices:
        return None, False
    input_price = model_prices.get("input_per_1m")
    output_price = model_prices.get("output_per_1m")
    if input_price is None or output_price is None:
        return None, True
    cost = (prompt_tokens / 1_000_000 * input_price) + (completion_tokens / 1_000_000 * output_price)
    return round(cost, 8), True


def count_questions(text: str) -> int:
    return len(re.findall(r"\?", text))


QUESTION_INTENTS: dict[str, list[str]] = {
    "canal_entrada": ["canal", "por dónde", "cómo te llegan", "a través de", "plataforma", "por qué medio",
                      "whatsapp", "instagram", "web", "correo", "chat", "formulario"],
    "herramienta_sistema": ["qué herramienta", "qué sistema", "qué plataforma", "cuál es tu", "estás usando",
                            "utilizás", "qué proveedor", "software", "crm", "aplicación"],
    "volumen": ["cuántos", "volumen", "cantidad", "mensajes por día", "consulta", "frecuencia", "diario",
                "al día", "por día", "al mes", "promedio"],
    "fuente_informacion": ["información de producto", "catálogo", "base de conocimiento", "dónde está",
                           "fuente", "de dónde sacás", "base de datos", "inventario"],
    "aprobacion_humana": ["aprobación humana", "revise", "apruebe", "revisión manual", "automática",
                          "intervención humana", "autorización", "humano lo revise", "alguien lo revise",
                          "que una persona", "que un humano", "que alguien", "automático o",
                          "necesita revisión", "preferís que se envíe", "revisar antes"],
    "forma_respuesta_actual": ["cómo respondés", "cómo contestás", "qué hacés", "proceso actual",
                                "cómo gestionás", "cómo manejás", "qué haces"],
    "integracion_disponible": ["integración", "conectado", "api", "webhook", "integrados", "conexión",
                               "sistema actual", "herramienta usás", "exportación"],
}


def classify_question_intent(question_text: str) -> str | None:
    lower = question_text.lower()
    for intent, patterns in QUESTION_INTENTS.items():
        for pat in patterns:
            if pat in lower:
                return intent
    return None


def extract_questions(text: str) -> list[str]:
    return [q.strip() for q in re.findall(r"[^.!?]*\?", text)]


def get_repeated_question_details(text: str, history: list[str]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    if not history:
        return details
    questions = extract_questions(text)
    past_intents: list[tuple[str, str, str]] = []
    for h in history:
        for pq in extract_questions(h):
            intent = classify_question_intent(pq)
            if intent:
                past_intents.append((intent, pq, pq[:80]))
    for q in questions:
        intent = classify_question_intent(q)
        if intent:
            for past_intent, past_q, past_q_short in past_intents:
                if past_intent == intent and q.lower() != past_q.lower():
                    details.append({
                        "intent": intent,
                        "original_question": past_q_short,
                        "repeated_question": q[:80],
                        "confidence": "semantic_match",
                    })
    return details


def contains_repeated_question(text: str, history: list[str]) -> bool:
    return len(get_repeated_question_details(text, history)) > 0


def check_diagnosis_completeness(
    text: str,
    completion_tokens: int | None,
    finish_reason: str | None,
    words: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "diagnosis_complete": False,
        "diagnosis_truncated": False,
        "diagnosis_too_short": False,
        "diagnosis_missing_sections": [],
        "final_finish_reason": finish_reason,
        "final_completion_tokens": completion_tokens,
        "final_response_chars": len(text),
        "final_response_words": words,
    }
    lower = text.lower()
    sections_found: list[str] = []
    section_checks = [
        ("proceso", ["resumen", "proceso", "flujo", "actualmente", "actuality"]),
        ("oportunidad", ["oportunidad", "factibilidad", "automatizaci", "beneficio"]),
        ("integracion", ["integraci", "api", "webhook", "sistema", "conexión", "gmail", "make", "zapier"]),
        ("riesgo", ["riesgo", "validar", "validación", "alucinaci", "precisión", "seguridad", "desafío"]),
        ("proximo_paso", ["próximo", "siguiente paso", "recomiendo", "sugiero", "agendar", "coordinar"]),
    ]
    for section_name, keywords in section_checks:
        if any(kw in lower for kw in keywords):
            sections_found.append(section_name)
    result["diagnosis_missing_sections"] = [s for s, _ in section_checks if s not in sections_found]
    has_process = "proceso" in sections_found
    has_opportunity = "oportunidad" in sections_found or "integracion" in sections_found
    words_ok = words >= 80
    toks_ok = (completion_tokens or 0) >= 60
    is_truncated = finish_reason == "length"
    is_too_short = (words < 60 and toks_ok) or (words < 30 and not toks_ok)
    is_complete = (has_process or has_opportunity) and words_ok and not is_truncated and not is_too_short
    result["diagnosis_complete"] = is_complete
    result["diagnosis_truncated"] = is_truncated
    result["diagnosis_too_short"] = is_too_short
    return result


def contains_markdown_noise(text: str) -> bool:
    patterns = [
        r"``",
        r"(?<!\*)\*\*(?!\*)|(?<!\*)\*(?!\*)",
        r"(?<!\s)~~(?!\s)",
        r"(?<!\w)\|(?!\w)",
    ]
    return any(re.search(p, text) for p in patterns)


def contains_internal_codes(text: str) -> bool:
    patterns = [r"\bdiagnostic_code\b", r"\bstep_to_action\b", r"\blead_capture\b", r"\bwhatsapp_handoff\b"]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def contains_unvalidated_promise(text: str) -> bool:
    patterns = [r"(puedo|vamos a|te prometo|garantizamos)\s+(integrar|conectar|implementar)"]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def response_is_brief(text: str, words: int, turn_index: int, total_turns: int) -> bool:
    if turn_index < total_turns - 1:
        return words <= 80
    return words <= 350


def has_diagnosis_generated(text: str) -> bool:
    indicators = [
        r"\bdiagn[oó]stico\b",
        r"\bautomatizaci[oó]n\b",
        r"\boportunidad\b",
        r"\bfactibilidad\b",
        r"\bintegraci[oó]n\b",
        r"\bpr[oó]ximo\b",
    ]
    return sum(1 for p in indicators if re.search(p, text, re.IGNORECASE)) >= 3


def check_model_switch_context(
    final_text: str,
) -> dict[str, Any]:
    lower = final_text.lower()
    context_items = {
        "web": "web" in lower or "sitio" in lower,
        "chat": "chat" in lower,
        "correo": "correo" in lower or "gmail" in lower or "email" in lower,
        "gmail": "gmail" in lower,
        "volumen_100": "100" in lower,
        "productos": "producto" in lower,
        "sin_aprobacion": "no requiere" in lower or "sin aprobación" in lower or "automática" in lower,
    }
    found = sum(1 for v in context_items.values() if v)
    integrity_score = round(found / len(context_items), 2)
    return {
        "model_switch_context_items": context_items,
        "model_switch_context_found": found,
        "model_switch_context_total": len(context_items),
        "model_switch_context_integrity": integrity_score,
    }


def run_conversation(
    *,
    strategy: str,
    stream: bool,
    temperature: float,
    system_prompt: str,
    turns: list[str],
    prices: dict[str, dict[str, float | None]],
    api_key: str,
    run_id: str,
    repetition_index: int,
) -> list[dict[str, Any]]:
    client: OpenAI | None = None
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    turn_records: list[dict[str, Any]] = []
    history_for_repeat_check: list[str] = []
    last_model: str | None = None

    for turn_idx, user_msg in enumerate(turns):
        is_final = turn_idx == len(turns) - 1
        action = "diagnose" if is_final else "reflect_and_ask"

        if strategy == "single_model":
            model = "gemini-3.1-flash-lite"
            reff = "minimal"
            role_in_strategy = "conversation" if not is_final else "final_diagnosis"
        elif strategy == "staged_models":
            if is_final:
                model = "gemini-3.5-flash"
                reff = "minimal"
                role_in_strategy = "final_diagnosis"
            else:
                model = "gemini-3.1-flash-lite"
                reff = "minimal"
                role_in_strategy = "conversation"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        max_tok = FINAL_MAX_TOKENS if is_final else INTERMEDIATE_MAX_TOKENS
        action_instr = ACTION_INSTRUCTIONS[action]

        augmented_user_msg = f"[{action_instr}]\n\n{user_msg}"

        messages.append({"role": "user", "content": augmented_user_msg})

        if model != last_model:
            client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS)
            last_model = model

        record: dict[str, Any] = {
            "run_id": run_id,
            "strategy": strategy,
            "role_in_strategy": role_in_strategy,
            "action": action,
            "model": model,
            "reasoning_effort": reff,
            "repetition_index": repetition_index,
            "turn_index": turn_idx,
            "user_message": user_msg,
            "assistant_message": None,
            "assistant_message_chars": None,
            "assistant_message_words": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "time_to_first_event_ms": None,
            "time_to_first_visible_text_ms": None,
            "total_latency_ms": None,
            "chunks_count": 0,
            "finish_reason": None,
            "success": False,
            "error_type": None,
            "error_message": None,
            "question_count": 0,
            "contains_repeated_question": False,
            "contains_repeated_question_intent": False,
            "repeated_question_intent": None,
            "contains_markdown_noise": False,
            "contains_internal_codes": False,
            "contains_unvalidated_promise": False,
            "response_is_brief": False,
            "diagnosis_generated": False,
            "diagnosis_complete": False,
            "diagnosis_truncated": False,
            "diagnosis_too_short": False,
            "diagnosis_missing_sections": [],
            "final_finish_reason": None,
            "final_completion_tokens": None,
            "final_response_chars": 0,
            "final_response_words": 0,
            "model_switch_context_items": {},
            "model_switch_context_found": 0,
            "model_switch_context_total": 0,
            "model_switch_context_integrity": None,
            "estimated_input_cost_usd": None,
            "estimated_output_cost_usd": None,
            "estimated_total_cost_usd": None,
            "cost_estimated": False,
        }

        start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "temperature": temperature,
                "max_tokens": max_tok,
            }
            if reff is not None:
                kwargs["reasoning_effort"] = reff
            if stream:
                kwargs["stream_options"] = {"include_usage": True}

            response = client.chat.completions.create(**kwargs)

            if stream:
                text_parts: list[str] = []
                usage = None
                finish_reason = None
                first_event_ms = None
                first_visible_text_ms = None
                chunk_count = 0

                for chunk in response:
                    chunk_count += 1
                    event_ms = elapsed_ms(start)
                    if first_event_ms is None:
                        first_event_ms = event_ms
                    chunk_dict = object_to_dict(chunk)
                    if chunk_dict.get("usage"):
                        usage = chunk_dict.get("usage")
                    choices = chunk_dict.get("choices") or []
                    if choices:
                        finish_reason = choices[0].get("finish_reason") or finish_reason
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            if first_visible_text_ms is None:
                                first_visible_text_ms = event_ms
                            text_parts.append(content)

                text = "".join(text_parts)
                usage_data, prompt_tokens, completion_tokens, total_tokens = extract_usage(usage)
                total_latency = elapsed_ms(start)
                words = len(text.split())
                input_cost, output_cost, total_cost, cost_est = None, None, None, False
                if prompt_tokens is not None and completion_tokens is not None:
                    inp_c, inp_est = estimate_cost(prompt_tokens, 0, model, prices)
                    out_c, out_est = estimate_cost(0, completion_tokens, model, prices)
                    if inp_c is not None and out_c is not None:
                        input_cost = round(inp_c, 8)
                        output_cost = round(out_c, 8)
                        total_cost = round(inp_c + out_c, 8)
                        cost_est = True
                    elif inp_est or out_est:
                        cost_est = True

                record.update({
                    "success": True,
                    "assistant_message": text,
                    "assistant_message_chars": len(text),
                    "assistant_message_words": words,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "time_to_first_event_ms": first_event_ms,
                    "time_to_first_visible_text_ms": first_visible_text_ms,
                    "total_latency_ms": total_latency,
                    "chunks_count": chunk_count,
                    "finish_reason": finish_reason,
                    "question_count": count_questions(text),
                    "contains_repeated_question": contains_repeated_question(text, history_for_repeat_check),
                    "contains_repeated_question_intent": len(get_repeated_question_details(text, history_for_repeat_check)) > 0,
                    "repeated_question_intent": (get_repeated_question_details(text, history_for_repeat_check) or [None])[0],
                    "contains_markdown_noise": contains_markdown_noise(text),
                    "contains_internal_codes": contains_internal_codes(text),
                    "contains_unvalidated_promise": contains_unvalidated_promise(text),
                    "response_is_brief": response_is_brief(text, words, turn_idx, len(turns)),
                    "diagnosis_generated": has_diagnosis_generated(text),
                    "estimated_input_cost_usd": input_cost,
                    "estimated_output_cost_usd": output_cost,
                    "estimated_total_cost_usd": total_cost,
                    "cost_estimated": cost_est,
                })
                if is_final:
                    diag_check = check_diagnosis_completeness(text, completion_tokens, finish_reason, words)
                    record.update(diag_check)
                    context_check = check_model_switch_context(text)
                    record.update(context_check)
            else:
                response_dict = object_to_dict(response)
                choice = (response_dict.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = message.get("content") or ""
                usage_data, prompt_tokens, completion_tokens, total_tokens = extract_usage(
                    response_dict.get("usage")
                )
                total_latency = elapsed_ms(start)
                words = len(text.split())
                input_cost, output_cost, total_cost, cost_est = None, None, None, False
                if prompt_tokens is not None and completion_tokens is not None:
                    inp_c, inp_est = estimate_cost(prompt_tokens, 0, model, prices)
                    out_c, out_est = estimate_cost(0, completion_tokens, model, prices)
                    if inp_c is not None and out_c is not None:
                        input_cost = round(inp_c, 8)
                        output_cost = round(out_c, 8)
                        total_cost = round(inp_c + out_c, 8)
                        cost_est = True
                    elif inp_est or out_est:
                        cost_est = True

                record.update({
                    "success": True,
                    "assistant_message": text,
                    "assistant_message_chars": len(text),
                    "assistant_message_words": words,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "time_to_first_event_ms": 0,
                    "time_to_first_visible_text_ms": None,
                    "total_latency_ms": total_latency,
                    "chunks_count": 0,
                    "finish_reason": choice.get("finish_reason"),
                    "question_count": count_questions(text),
                    "contains_repeated_question": contains_repeated_question(text, history_for_repeat_check),
                    "contains_repeated_question_intent": len(get_repeated_question_details(text, history_for_repeat_check)) > 0,
                    "repeated_question_intent": (get_repeated_question_details(text, history_for_repeat_check) or [None])[0],
                    "contains_markdown_noise": contains_markdown_noise(text),
                    "contains_internal_codes": contains_internal_codes(text),
                    "contains_unvalidated_promise": contains_unvalidated_promise(text),
                    "response_is_brief": response_is_brief(text, words, turn_idx, len(turns)),
                    "diagnosis_generated": has_diagnosis_generated(text),
                    "estimated_input_cost_usd": input_cost,
                    "estimated_output_cost_usd": output_cost,
                    "estimated_total_cost_usd": total_cost,
                    "cost_estimated": cost_est,
                })
                if is_final:
                    diag_check = check_diagnosis_completeness(text, completion_tokens, choice.get("finish_reason"), words)
                    record.update(diag_check)
                    context_check = check_model_switch_context(text)
                    record.update(context_check)

            messages.append({"role": "assistant", "content": text})
            history_for_repeat_check.append(text)
            turn_records.append(record)

        except APIStatusError as exc:
            record.update({
                "error_type": exc.__class__.__name__,
                "error_message": sanitize_message(str(exc), api_key),
                "total_latency_ms": elapsed_ms(start),
            })
            turn_records.append(record)
            break
        except (APIConnectionError, OpenAIError, Exception) as exc:
            record.update({
                "error_type": exc.__class__.__name__,
                "error_message": sanitize_message(str(exc), api_key),
                "total_latency_ms": elapsed_ms(start),
            })
            turn_records.append(record)
            break

    return turn_records


def compute_conversation_metrics(
    turns: list[dict[str, Any]],
    strategy: str,
    repetition_index: int,
) -> dict[str, Any]:
    total_turns = len([t for t in turns if t["success"]])
    if total_turns == 0:
        return {
            "strategy": strategy,
            "repetition_index": repetition_index,
            "total_turns": 0,
            "passed": False,
            "notes": "All turns failed",
        }

    prompt_toks = [t["prompt_tokens"] for t in turns if t["success"] and t["prompt_tokens"] is not None]
    completion_toks = [t["completion_tokens"] for t in turns if t["success"] and t["completion_tokens"] is not None]
    total_toks = [t["total_tokens"] for t in turns if t["success"] and t["total_tokens"] is not None]
    ttfv = [t["time_to_first_visible_text_ms"] for t in turns if t["success"] and t["time_to_first_visible_text_ms"] is not None]
    latencies = [t["total_latency_ms"] for t in turns if t["success"] and t["total_latency_ms"] is not None]
    costs = [t["estimated_total_cost_usd"] for t in turns if t["success"] and t["estimated_total_cost_usd"] is not None]
    intermediate_turns = [t for t in turns if t["success"] and t["turn_index"] < 7 and t["completion_tokens"] is not None]
    final_turns = [t for t in turns if t["success"] and t["turn_index"] == 7 and t["completion_tokens"] is not None]
    repeated_q = [t["contains_repeated_question"] for t in turns if t["success"]]

    total_ttfv = sum(ttfv) if ttfv else 0
    avg_ttfv = round(sum(ttfv) / len(ttfv)) if ttfv else None
    p50_ttfv = round(median(ttfv)) if len(ttfv) >= 1 else None
    p95_ttfv = sorted(ttfv)[int(len(ttfv) * 0.95)] if len(ttfv) >= 20 else (sorted(ttfv)[-1] if ttfv else None)

    avg_latency = round(sum(latencies) / len(latencies)) if latencies else None
    p50_latency = round(median(latencies)) if len(latencies) >= 1 else None

    avg_intermediate_output = round(sum(t["completion_tokens"] for t in intermediate_turns) / len(intermediate_turns)) if intermediate_turns else None
    final_output = final_turns[0]["completion_tokens"] if final_turns else None
    final_text = final_turns[0]["assistant_message"] if final_turns else None
    final_diagnosis = final_turns[0]["diagnosis_generated"] if final_turns else False
    final_complete = final_turns[0].get("diagnosis_complete", False) if final_turns else False
    final_truncated = final_turns[0].get("diagnosis_truncated", False) if final_turns else False
    final_too_short = final_turns[0].get("diagnosis_too_short", False) if final_turns else False
    final_missing = final_turns[0].get("diagnosis_missing_sections", []) if final_turns else []
    final_finish = final_turns[0].get("final_finish_reason") if final_turns else None
    repeated_q_intents = [t.get("repeated_question_intent") for t in turns if t["success"] and t.get("repeated_question_intent")]
    intermediate_ended_length = sum(1 for t in intermediate_turns if t.get("finish_reason") == "length")
    model_switch_count = sum(1 for i in range(1, len(turns)) if turns[i].get("model") != turns[i-1].get("model"))
    model_switch_integrity = final_turns[0].get("model_switch_context_integrity") if final_turns else None

    # intermediate TTFT (turns 1-7) vs final TTFT (turn 8)
    inter_ttfv = [t["time_to_first_visible_text_ms"] for t in turns if t["success"] and t["turn_index"] < 7 and t["time_to_first_visible_text_ms"] is not None]
    final_ttfv_record = [t["time_to_first_visible_text_ms"] for t in turns if t["success"] and t["turn_index"] == 7 and t["time_to_first_visible_text_ms"] is not None]

    return {
        "strategy": strategy,
        "repetition_index": repetition_index,
        "total_turns": total_turns,
        "total_prompt_tokens": sum(prompt_toks) if prompt_toks else None,
        "total_completion_tokens": sum(completion_toks) if completion_toks else None,
        "total_tokens": sum(total_toks) if total_toks else None,
        "total_time_to_first_visible_text_ms": total_ttfv,
        "avg_time_to_first_visible_text_ms": avg_ttfv,
        "p50_time_to_first_visible_text_ms": p50_ttfv,
        "p95_time_to_first_visible_text_ms": p95_ttfv,
        "avg_intermediate_ttfv_ms": round(sum(inter_ttfv) / len(inter_ttfv)) if inter_ttfv else None,
        "final_ttfv_ms": final_ttfv_record[0] if final_ttfv_record else None,
        "total_latency_ms": sum(latencies) if latencies else None,
        "avg_latency_ms": avg_latency,
        "p50_latency_ms": p50_latency,
        "total_cost_usd": round(sum(costs), 8) if costs else None,
        "diagnosis_generated": final_diagnosis,
        "diagnosis_complete": final_complete,
        "diagnosis_truncated": final_truncated,
        "diagnosis_too_short": final_too_short,
        "diagnosis_missing_sections": final_missing,
        "final_finish_reason": final_finish,
        "repeated_questions_count": sum(1 for r in repeated_q if r),
        "repeated_question_intents": list(set(rq.get("intent") for rq in repeated_q_intents if rq)),
        "intermediate_truncated_count": intermediate_ended_length,
        "average_output_tokens_per_intermediate_turn": avg_intermediate_output,
        "final_diagnosis_output_tokens": final_output,
        "final_diagnosis_text": final_text,
        "model_switch_count": model_switch_count,
        "model_switch_context_integrity": model_switch_integrity,
        "quality_score": None,
        "passed": all(t["success"] for t in turns) and total_turns == 8,
        "notes": "",
    }


def score_conversation(
    conv: dict[str, Any],
    turns: list[dict[str, Any]],
) -> dict[str, float | None]:
    if not turns or not conv["passed"]:
        return {"naturalidad": None, "comprension_acumulativa": None, "calidad_preguntas": None,
                "no_repeticion": None, "brevedad": None, "diagnostico_final": None,
                "prudencia_tecnica": None, "profesionalismo": None,
                "cumplimiento_action": None,
                "score_tecnico": None, "score_calidad_manual": None, "score_total": None}

    intermediate = [t for t in turns if t["success"] and t["turn_index"] < 7]
    final_t = [t for t in turns if t["success"] and t["turn_index"] == 7]

    naturalidad = 3.0
    compromiso_entendimiento = sum(1 for t in intermediate if t["contains_repeated_question"])
    if compromiso_entendimiento == 0:
        naturalidad = 4.0
    if any(t["contains_markdown_noise"] for t in turns):
        naturalidad -= 1.0
    naturalidad = max(0.0, min(5.0, naturalidad))

    comprension = 4.0
    key_terms_found = 0
    if final_t:
        ft = final_t[0]["assistant_message"] or ""
        for term in ["web", "chat", "correo", "gmail", "producto", "volumen", "100"]:
            if term.lower() in ft.lower():
                key_terms_found += 1
    comprension = min(5.0, 2.0 + key_terms_found * 0.4)

    calidad_preguntas = 4.0
    q_counts = [t["question_count"] for t in intermediate if t["question_count"] > 0]
    avg_q = sum(q_counts) / len(q_counts) if q_counts else 0
    if avg_q <= 1.0:
        calidad_preguntas = 4.5
    elif avg_q > 1.5:
        calidad_preguntas = 3.0

    no_repeticion = 5.0
    if any(t["contains_repeated_question"] for t in intermediate):
        no_repeticion = 2.0

    brevedad = 4.0
    brief_ratio = sum(1 for t in intermediate if t["response_is_brief"]) / len(intermediate) if intermediate else 0
    if brief_ratio >= 0.8:
        brevedad = 4.5
    elif brief_ratio < 0.5:
        brevedad = 2.5

    diagnostico_final = 3.0
    if final_t:
        ft = final_t[0]
        text = ft["assistant_message"] or ""
        indicators = 0
        for keyword in ["factibilidad", "automatizaci", "integraci", "api", "webhook", "próximo", "oportunidad", "riesgo"]:
            if keyword.lower() in text.lower():
                indicators += 1
        if ft["diagnosis_generated"]:
            diagnostico_final = min(5.0, 2.5 + indicators * 0.3)
        if any(p in text.lower() for p in ["precio", "costo del servicio", "sla garantizado", "roi de"]):
            diagnostico_final = max(0.0, diagnostico_final - 2.0)

    prudencia_tecnica = 4.0
    if any(t["contains_unvalidated_promise"] for t in turns):
        prudencia_tecnica = 2.0
    if any(t["contains_internal_codes"] for t in turns):
        prudencia_tecnica = 1.0

    profesionalismo = 4.0
    if any(t["contains_markdown_noise"] for t in turns):
        profesionalismo -= 1.0
    if any(t["contains_internal_codes"] for t in turns):
        profesionalismo -= 2.0
    profesionalismo = max(0.0, min(5.0, profesionalismo))

    # cumplimiento de action: no diagnosis in intermediate, diagnosis in final
    premature_diag = sum(1 for t in intermediate if t.get("diagnosis_generated") and t.get("action") == "reflect_and_ask")
    cumplimiento = 5.0
    if premature_diag > 0:
        cumplimiento = max(1.0, 5.0 - premature_diag)

    # model switch context integrity bonus/penalty
    integ = conv.get("model_switch_context_integrity")
    context_score = (integ * 5) if integ is not None else 3.0

    score_tecnico = round(
        naturalidad * 0.20
        + calidad_preguntas * 0.15
        + no_repeticion * 0.15
        + brevedad * 0.10
        + prudencia_tecnica * 0.10
        + profesionalismo * 0.10
        + cumplimiento * 0.20,
        2,
    )

    score_calidad = round(comprension * 0.30 + diagnostico_final * 0.50 + context_score * 0.20, 2)

    ttfv = [t["time_to_first_visible_text_ms"] for t in turns if t["success"] and t["time_to_first_visible_text_ms"] is not None]
    avg_ttfv = sum(ttfv) / len(ttfv) if ttfv else 5000
    ttfv_score = max(0, min(5, 5 - (avg_ttfv - 500) / 1000)) if avg_ttfv > 500 else 5.0

    cost = conv["total_cost_usd"]
    cost_score = 5.0 if cost is None else max(0, min(5, 5 - cost * 100))

    stdout_stability = 0.0
    if all(t["success"] for t in turns):
        toks = [t["completion_tokens"] for t in turns if t["success"] and t["completion_tokens"] is not None]
        if len(toks) >= 2 and stdev(toks) < 20:
            stdout_stability = 5.0
        elif len(toks) >= 2:
            stdout_stability = max(0, 5 - stdev(toks) / 20)
        else:
            stdout_stability = 3.0

    formato_score = 5.0
    if any(t["contains_markdown_noise"] for t in turns):
        formato_score = 3.0
    if any(t["contains_internal_codes"] for t in turns):
        formato_score = 1.0

    score_total = round(
        score_tecnico * 0.25
        + score_calidad * 0.25
        + ttfv_score * 0.15
        + cost_score * 0.10
        + stdout_stability * 0.10
        + formato_score * 0.05
        + cumplimiento * 0.10,
        2,
    )

    return {
        "naturalidad": round(naturalidad, 1),
        "comprension_acumulativa": round(comprension, 1),
        "calidad_preguntas": round(calidad_preguntas, 1),
        "no_repeticion": round(no_repeticion, 1),
        "brevedad": round(brevedad, 1),
        "diagnostico_final": round(diagnostico_final, 1),
        "prudencia_tecnica": round(prudencia_tecnica, 1),
        "profesionalismo": round(profesionalismo, 1),
        "cumplimiento_action": round(cumplimiento, 1),
        "model_switch_context_integrity": round(context_score, 1),
        "score_tecnico": score_tecnico,
        "score_calidad_manual": score_calidad,
        "score_total": score_total,
    }


def fmt_ms(value: Any) -> str:
    if value is None:
        return "-"
    return f"{int(value)} ms"


def fmt_usd(value: Any) -> str:
    if value is None:
        return "-"
    return f"${value:.8f}"


def fmt_tokens(value: Any) -> str:
    return "-" if value is None else str(int(value))


def build_report(
    summary: dict[str, list[dict[str, Any]]],
    all_turns: list[dict[str, Any]],
    config: dict[str, Any],
    prices_loaded: bool,
) -> str:
    lines: list[str] = []
    lines.append("# Vera Gemini Strategy Benchmark Report")
    lines.append("")
    lines.append(f"Timestamp: `{now_iso()}`")
    lines.append(f"Conversation turns: {len(CONVERSATION_TURNS)}")
    lines.append(f"Repeats per strategy: {config.get('repeat', 5)}")
    lines.append(f"Streaming: {config.get('stream', True)}")
    lines.append(f"Temperature: {config.get('temperature', TEMPERATURE)}")
    lines.append(f"Prices file loaded: {prices_loaded}")
    lines.append("")

    lines.append("## Strategies Tested")
    lines.append("")
    lines.append("| Strategy | Repetitions | Turns OK | Passed | Score Total |")
    lines.append("|---|---:|---:|---:|---:|")
    for key in sorted(summary.keys()):
        convs = summary[key]
        for c in convs:
            lines.append(
                f"| `{c['strategy']}` | {c['repetition_index']} | {c['total_turns']} | "
                f"{c['passed']} | {c.get('quality_score') or '-'} |"
            )

    lines.append("")
    lines.append("## Strategy Comparison")
    lines.append("")

    for key in sorted(summary.keys()):
        convs = summary[key]
        passed = [c for c in convs if c["passed"]]
        failed = [c for c in convs if not c["passed"]]
        strategy_label = convs[0]["strategy"] if convs else "?"
        ttfv_vals = [c["avg_time_to_first_visible_text_ms"] for c in passed if c["avg_time_to_first_visible_text_ms"] is not None]
        lat_vals = [c["avg_latency_ms"] for c in passed if c["avg_latency_ms"] is not None]
        cost_vals = [c["total_cost_usd"] for c in passed if c["total_cost_usd"] is not None]
        diag_count = sum(1 for c in passed if c["diagnosis_generated"])
        diag_complete_count = sum(1 for c in passed if c.get("diagnosis_complete"))
        repeat_q = sum(c["repeated_questions_count"] for c in passed)
        scores = [c.get("quality_score") for c in convs if c.get("quality_score") is not None]
        inter_ttfv = [c["avg_intermediate_ttfv_ms"] for c in passed if c.get("avg_intermediate_ttfv_ms") is not None]
        final_ttfv = [c["final_ttfv_ms"] for c in passed if c.get("final_ttfv_ms") is not None]
        inter_trunc = sum(c.get("intermediate_truncated_count", 0) for c in passed)
        premature = sum(1 for t in all_turns if t.get("strategy") == strategy_label and t.get("action") == "reflect_and_ask" and t.get("diagnosis_generated"))
        integrity_vals = [c.get("model_switch_context_integrity") for c in passed if c.get("model_switch_context_integrity") is not None]

        lines.append(f"### Strategy: {strategy_label}")
        lines.append("")
        if strategy_label == "single_model":
            lines.append("> Conversation & diagnosis: `gemini-3.1-flash-lite` + minimal")
        elif strategy_label == "staged_models":
            lines.append("> Turns 1-7: `gemini-3.1-flash-lite` + minimal · Turn 8: `gemini-3.5-flash` + minimal")
        lines.append("")
        lines.append(f"- Repetitions: {len(convs)} ({len(passed)} passed, {len(failed)} failed)")
        lines.append(f"- Avg TTFT (all turns): {fmt_ms(sum(ttfv_vals) / len(ttfv_vals)) if ttfv_vals else '-'}")
        lines.append(f"- Avg intermediate TTFT: {fmt_ms(sum(inter_ttfv) / len(inter_ttfv)) if inter_ttfv else '-'}")
        lines.append(f"- Avg final diagnosis TTFT: {fmt_ms(sum(final_ttfv) / len(final_ttfv)) if final_ttfv else '-'}")
        lines.append(f"- Avg total latency: {fmt_ms(sum(lat_vals) / len(lat_vals)) if lat_vals else '-'}")
        lines.append(f"- Diagnosis generated: {diag_count}/{len(passed)}")
        lines.append(f"- Diagnosis complete: {diag_complete_count}/{len(passed)}")
        if inter_trunc:
            lines.append(f"- Intermediate turns truncated (finish=length): {inter_trunc} total")
        lines.append(f"- Premature diagnoses (reflect_and_ask but diagnosed): {premature}")
        lines.append(f"- Repeated questions total: {repeat_q}")
        if integrity_vals:
            lines.append(f"- Model switch context integrity: {round(sum(integrity_vals) / len(integrity_vals), 2)}")
        lines.append(f"- Total cost: {fmt_usd(sum(cost_vals)) if cost_vals else 'No prices configured'}")
        if scores:
            lines.append(f"- Score range: {min(scores)} - {max(scores)}")
            lines.append(f"- Score avg: {round(sum(scores) / len(scores), 2)}")
        lines.append("")

    lines.append("## Time to First Visible Text")
    lines.append("")
    lines.append("| Strategy | Avg All | Avg Intermed | Final Diag |")
    lines.append("|---|---:|---:|---:|")
    for key in sorted(summary.keys()):
        convs = [c for c in summary[key] if c["avg_time_to_first_visible_text_ms"] is not None]
        if not convs:
            continue
        all_v = [c["avg_time_to_first_visible_text_ms"] for c in convs]
        inter_v = [c["avg_intermediate_ttfv_ms"] for c in convs if c.get("avg_intermediate_ttfv_ms") is not None]
        final_v = [c["final_ttfv_ms"] for c in convs if c.get("final_ttfv_ms") is not None]
        lines.append(
            f"| `{key}` | {fmt_ms(sum(all_v) / len(all_v))} | "
            f"{fmt_ms(sum(inter_v) / len(inter_v)) if inter_v else '-'} | "
            f"{fmt_ms(sum(final_v) / len(final_v)) if final_v else '-'} |"
        )

    lines.append("")
    lines.append("## Total Latency")
    lines.append("")
    lines.append("| Strategy | Avg Latency |")
    lines.append("|---|---:|")
    for key in sorted(summary.keys()):
        convs = [c for c in summary[key] if c["avg_latency_ms"] is not None]
        if not convs:
            continue
        v = [c["avg_latency_ms"] for c in convs]
        lines.append(f"| `{key}` | {fmt_ms(sum(v) / len(v))} |")

    lines.append("")
    lines.append("## Token Usage")
    lines.append("")
    lines.append("| Strategy | Avg Input | Avg Output | Avg Total |")
    lines.append("|---|---:|---:|---:|")
    for key in sorted(summary.keys()):
        convs = [c for c in summary[key] if c["total_prompt_tokens"] is not None]
        if not convs:
            continue
        avg_in = sum(c["total_prompt_tokens"] for c in convs) / len(convs)
        avg_out = sum(c["total_completion_tokens"] for c in convs) / len(convs)
        avg_tot = sum(c["total_tokens"] for c in convs) / len(convs)
        lines.append(f"| `{key}` | {fmt_tokens(avg_in)} | {fmt_tokens(avg_out)} | {fmt_tokens(avg_tot)} |")

    lines.append("")
    lines.append("## Intermediate Turn Output")
    lines.append("")
    lines.append("| Strategy | Avg Tokens per Turn |")
    lines.append("|---|---:|")
    for key in sorted(summary.keys()):
        convs = [c for c in summary[key] if c["average_output_tokens_per_intermediate_turn"] is not None]
        if not convs:
            continue
        avg = sum(c["average_output_tokens_per_intermediate_turn"] for c in convs) / len(convs)
        lines.append(f"| `{key}` | {fmt_tokens(avg)} |")

    lines.append("")
    lines.append("## Final Diagnosis Output")
    lines.append("")
    lines.append("| Strategy | Tokens | Complete | TooShort | Finish | Missing Sections | Context Integrity |")
    lines.append("|---|---:|---:|---:|---:|---|---|")
    for key in sorted(summary.keys()):
        for c in summary[key]:
            if c["final_diagnosis_output_tokens"] is not None:
                missing = ", ".join(c.get("diagnosis_missing_sections", [])) or "-"
                integ = c.get("model_switch_context_integrity", "-")
                lines.append(
                    f"| `{key}` rep {c['repetition_index']} | {c['final_diagnosis_output_tokens']} | "
                    f"{c.get('diagnosis_complete', '?')} | {c.get('diagnosis_too_short', '?')} | "
                    f"{c.get('final_finish_reason', '?')} | {missing} | {integ} |"
                )

    lines.append("")
    lines.append("## Cost Estimate")
    lines.append("")
    lines.append("| Strategy | Total Cost |")
    lines.append("|---|---:|")
    for key in sorted(summary.keys()):
        convs = [c for c in summary[key] if c["total_cost_usd"] is not None]
        if convs:
            total = sum(c["total_cost_usd"] for c in convs)
            lines.append(f"| `{key}` | {fmt_usd(total)} |")
        else:
            lines.append(f"| `{key}` | No prices configured |")

    lines.append("")
    lines.append("## Premature Diagnoses & Repeated Questions")
    lines.append("")
    lines.append("| Strategy | Premature Diag | Repeated Qs | Repeated Intents |")
    lines.append("|---|---:|---:|---|")
    for key in sorted(summary.keys()):
        prem = sum(1 for t in all_turns if t.get("strategy") == key and t.get("action") == "reflect_and_ask" and t.get("diagnosis_generated"))
        rq = sum(c["repeated_questions_count"] for c in summary[key])
        intents = set()
        for c in summary[key]:
            for ri in c.get("repeated_question_intents", []):
                intents.add(ri)
        lines.append(f"| `{key}` | {prem} | {rq} | {', '.join(sorted(intents)) if intents else '-'} |")

    lines.append("")
    lines.append("## Errors")
    lines.append("")
    error_turns = [t for t in all_turns if not t["success"]]
    if error_turns:
        lines.append("| Run | Strategy | Turn | Error |")
        lines.append("|---|---:|---:|---|")
        for et in error_turns:
            lines.append(f"| {et['run_id']} | {et['strategy']} | {et['turn_index']} | {et.get('error_type', '?')} |")
    else:
        lines.append("No errors recorded.")
    lines.append("")

    lines.append("## Quality Scores")
    lines.append("")
    for key in sorted(summary.keys()):
        for c in summary[key]:
            if c.get("quality_score") is not None:
                lines.append(f"- `{key}` rep {c['repetition_index']}: score={c['quality_score']}")
    lines.append("")

    lines.append("## Representative Transcripts")
    lines.append("")
    for key in sorted(summary.keys()):
        convs = [c for c in summary[key] if c["passed"]]
        if not convs:
            lines.append(f"### {key}: no passed runs")
            lines.append("")
            continue
        best_rep = max(convs, key=lambda c: c.get("quality_score") or 0)
        rep = best_rep["repetition_index"]
        lines.append(f"### {key} (rep {rep}, score={best_rep.get('quality_score', '?')})")
        lines.append("")
        rep_turns = [t for t in all_turns if t.get("repetition_index") == rep and t.get("strategy") == key]
        rep_turns.sort(key=lambda x: x["turn_index"])
        for t in rep_turns:
            action_tag = f"[{t.get('action', '?')}]"
            model_tag = t.get("model", "?")
            lines.append(f"**Turn {t['turn_index'] + 1} — User:** {t['user_message']}")
            lines.append("")
            lines.append(f"**Vera** ({model_tag} {action_tag}): {t['assistant_message']}")
            lines.append("")
            lines.append(f"*(TTFT: {fmt_ms(t['time_to_first_visible_text_ms'])}, "
                        f"tokens: {fmt_tokens(t['completion_tokens'])})*")
            lines.append("")
    lines.append("")

    lines.append("## Conclusions")
    lines.append("")
    lines.append("* This lab compares single-model vs staged-models strategy for Vera conversation.")
    lines.append("* Action instructions (`reflect_and_ask` / `diagnose`) are injected per turn.")
    lines.append("* Full history is preserved when switching models in staged strategy.")
    lines.append("* All results are generated from the Gemini OpenAI-compatible endpoint directly.")
    lines.append("")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5, help="Repetitions per strategy (default: 5)")
    parser.add_argument("--stream", action="store_true", default=True, help="Use streaming (default: True)")
    parser.add_argument("--no-stream", action="store_false", dest="stream", help="Disable streaming")
    parser.add_argument("--temperature", type=float, default=TEMPERATURE, help=f"Temperature (default: {TEMPERATURE})")
    parser.add_argument("--output-dir", type=Path, help="Output directory (default: lab/results/<timestamp>)")
    parser.add_argument("--prices-file", type=Path, help="Path to model_prices.local.json")
    parser.add_argument(
        "--strategy",
        choices=["single_model", "staged_models"],
        help="Run only one strategy (default: both)",
    )
    parser.add_argument("--case", default="main", help="Conversation case to run (default: main)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    branch = os.popen("git branch --show-current 2>/dev/null").read().strip()
    head = os.popen("git rev-parse --short HEAD 2>/dev/null").read().strip()
    status = os.popen("git status --short 2>/dev/null").read().strip()

    print(f"Branch: {branch}")
    print(f"HEAD: {head}")
    print(f"Worktree clean: {status == ''}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set.", file=sys.stderr)
        return 1
    print("GEMINI_API_KEY: OK")

    prices = load_prices(args.prices_file)
    prices_loaded = bool(prices)

    strategies: list[str] = []
    if args.strategy:
        strategies.append(args.strategy)
    else:
        strategies.extend(["single_model", "staged_models"])

    print(f"Strategies to run: {strategies}")
    for s in strategies:
        print(f"  {s} x {args.repeat}")

    if args.output_dir:
        out_dir = args.output_dir
    else:
        lab_dir = Path(__file__).resolve().parent
        out_dir = lab_dir / "results" / now_slug()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    all_turns: list[dict[str, Any]] = []
    summary: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for strategy in strategies:
        for rep_idx in range(1, args.repeat + 1):
            run_id = f"{strategy}_rep{rep_idx}_{now_slug()}"
            print(f"\nRun: {run_id}")
            sys.stdout.flush()

            turns = run_conversation(
                strategy=strategy,
                stream=args.stream,
                temperature=args.temperature,
                system_prompt=SYSTEM_PROMPT_BASE,
                turns=CONVERSATION_TURNS,
                prices=prices,
                api_key=api_key,
                run_id=run_id,
                repetition_index=rep_idx,
            )

            conv = compute_conversation_metrics(turns, strategy, rep_idx)
            scores = score_conversation(conv, turns)
            conv["quality_score"] = scores.get("score_total")
            conv["scores_detail"] = scores

            key = strategy
            summary[key].append(conv)
            all_turns.extend(turns)

            print(f"  Turns: {conv['total_turns']}, Passed: {conv['passed']}, "
                  f"Score: {conv['quality_score']}, Cost: {conv['total_cost_usd']}")
            sys.stdout.flush()

    turns_path = out_dir / "turns.jsonl"
    with open(turns_path, "w", encoding="utf-8") as f:
        for t in all_turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"\nWrote {turns_path}")

    turns_csv_path = out_dir / "turns.csv"
    if all_turns:
        fieldnames = list(all_turns[0].keys())
        with open(turns_csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_turns)
    print(f"Wrote {turns_csv_path}")

    convs_path = out_dir / "conversations.json"
    with open(convs_path, "w", encoding="utf-8") as f:
        json.dump(dict(summary), f, indent=2, ensure_ascii=False)
    print(f"Wrote {convs_path}")

    summary_flat = []
    for key, convs in summary.items():
        for c in convs:
            c_copy = {k: v for k, v in c.items() if k != "final_diagnosis_text" and k != "scores_detail"}
            c_copy["strategy_key"] = key
            summary_flat.append(c_copy)

    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_flat, f, indent=2, ensure_ascii=False)
    print(f"Wrote {summary_path}")

    report_text = build_report(summary, all_turns, {
        "repeat": args.repeat,
        "stream": args.stream,
        "temperature": args.temperature,
    }, prices_loaded)
    report_path = out_dir / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Wrote {report_path}")

    print("\n--- DONE ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())

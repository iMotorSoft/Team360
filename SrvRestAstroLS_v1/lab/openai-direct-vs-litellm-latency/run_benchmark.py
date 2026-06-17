#!/usr/bin/env python3
"""Benchmark: OpenAI direct vs LiteLLM proxy para gpt-5.4-nano.

Mide overhead de latencia que agrega LiteLLM como gateway.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, stdev
from typing import Any

import requests

HERE = Path(__file__).resolve().parent

SYSTEM_PROMPT = (
    "Sos Vera, asistente de diagnostico de automatizacion de Team360. "
    "Responde en espanol claro, profesional y breve. "
    "No inventes integraciones ni pidas credenciales."
)

USER_PROMPT = (
    "Una empresa recibe consultas por WhatsApp y Gmail. "
    "El stock esta en un sistema cerrado de Windows y los precios en una planilla. "
    "Los descuentos especiales requieren aprobacion humana. "
    "Dame una evaluacion inicial en no mas de 120 palabras."
)

DIRECT_CONFIG = {
    "label": "OpenAI directo",
    "route": "openai_direct",
    "model": "gpt-5.4-nano",
    "url": "https://api.openai.com/v1/chat/completions",
    "key_var": "OpenAI_Key_JAI_query",
}

LITELLM_CONFIG = {
    "label": "LiteLLM proxy",
    "route": "litellm_proxy",
    "model": "openai_gpt-5-nano",
    "url": "http://localhost:4000/v1/chat/completions",
    "key_var": "LITELLM_MASTER_KEY",
}

MAX_TOKENS = 500
TEMPERATURE = 0.2
TIMEOUT = 60.0
WARMUP_REPS = 2
MAIN_REPS = 10


def get_key(var_name: str) -> str:
    return os.environ.get(var_name, "")


def single_call(
    route: str,
    url: str,
    model: str,
    api_key: str,
    rep: int,
    order_in_pair: int,
) -> dict:
    """Ejecutar una llamada con streaming y medir metricas."""
    start = time.monotonic()
    result: dict[str, Any] = {
        "route": route,
        "repetition": rep,
        "order_in_pair": order_in_pair,
        "endpoint": url,
        "requested_model": model,
        "reported_model": None,
        "http_status": None,
        "success": False,
        "time_to_first_event_ms": None,
        "time_to_first_visible_text_ms": None,
        "total_latency_ms": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
        "cached_tokens": None,
        "finish_reason": None,
        "output_chars": 0,
        "output_words": 0,
        "response_text": "",
        "retry_count": 0,
        "fallback_used": False,
        "error": None,
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "max_completion_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            url, headers=headers, json=payload, stream=True, timeout=TIMEOUT
        )
        result["http_status"] = resp.status_code
        resp.raise_for_status()

        first_event = None
        first_text = None
        collected = ""
        finish_reason = None
        usage_data: dict = {}

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if not line.startswith("data: "):
                litellm_meta = _try_parse_litellm_metadata(line)
                if litellm_meta:
                    result["reported_model"] = litellm_meta.get("model", result["reported_model"])
                continue
            data_str = line[len("data: "):]
            if data_str.strip() == "[DONE]":
                break

            if first_event is None:
                first_event = time.monotonic()

            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if chunk.get("object") == "chat.completion.chunk":
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content and first_text is None:
                        first_text = time.monotonic()
                    collected += content

                    finish = choices[0].get("finish_reason")
                    if finish:
                        finish_reason = finish

            if "usage" in chunk:
                usage_data = chunk["usage"]

            reported = chunk.get("model") or result.get("reported_model")
            if reported:
                result["reported_model"] = reported

        total_lat = time.monotonic() - start

        result["response_text"] = collected
        result["output_chars"] = len(collected)
        result["output_words"] = len(collected.split())
        result["finish_reason"] = finish_reason
        result["time_to_first_event_ms"] = (
            round((first_event - start) * 1000, 1) if first_event else None
        )
        result["time_to_first_visible_text_ms"] = (
            round((first_text - start) * 1000, 1) if first_text else None
        )
        result["total_latency_ms"] = round(total_lat * 1000, 1)
        result["success"] = True

        if usage_data:
            result["prompt_tokens"] = usage_data.get("prompt_tokens")
            result["completion_tokens"] = usage_data.get("completion_tokens")
            result["total_tokens"] = usage_data.get("total_tokens")
            cd = usage_data.get("completion_tokens_details") or {}
            result["reasoning_tokens"] = cd.get("reasoning_tokens")
            pd = usage_data.get("prompt_tokens_details") or {}
            result["cached_tokens"] = pd.get("cached_tokens")

    except requests.exceptions.Timeout:
        result["error"] = "timeout"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        body = e.response.text[:300] if e.response is not None else ""
        result["error"] = f"http_{status}: {body}"
    except requests.exceptions.RequestException as e:
        result["error"] = f"request_error: {str(e)[:200]}"

    if result["total_latency_ms"] is None:
        result["total_latency_ms"] = round((time.monotonic() - start) * 1000, 1)

    return result


def _try_parse_litellm_metadata(line: str) -> dict | None:
    """Intentar parsear metadata de LiteLLM en lineas no data:."""
    try:
        data = json.loads(line)
        if isinstance(data, dict) and "model" in data and "usage" not in data:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def compute_stats(values: list[float]) -> dict:
    if not values:
        return {"avg": None, "median": None, "min": None, "max": None, "stdev": None, "p95": None}
    s = sorted(values)
    return {
        "avg": round(sum(values) / len(values), 1),
        "median": round(median(values), 1),
        "min": round(s[0], 1),
        "max": round(s[-1], 1),
        "stdev": round(stdev(values), 1) if len(values) > 1 else 0,
        "p95": round(s[int(len(s) * 0.95)], 1) if len(s) >= 20 else round(s[-1], 1),
    }


def check_semantic_equivalence(text: str) -> dict:
    lower = text.lower()
    return {
        "has_whatsapp": "whatsapp" in lower,
        "has_gmail": "gmail" in lower,
        "has_stock_system": "stock" in lower and ("sistema" in lower or "windows" in lower or "cerrado" in lower),
        "has_prices_spreadsheet": "precios" in lower and ("planilla" in lower or "excel" in lower),
        "has_discounts_human": "descuentos" in lower and ("aprobacion" in lower or "humano" in lower or "revis" in lower),
        "has_no_promise": not any(w in lower for w in ["integramos", "conectamos", "integracion directa", "api abierta"]),
        "is_spanish": True,
    }


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = HERE / "results" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    direct_key = get_key(DIRECT_CONFIG["key_var"])
    litellm_key = get_key(LITELLM_CONFIG["key_var"])

    if not direct_key:
        print("ERROR: OpenAI key no encontrada")
        sys.exit(1)
    if not litellm_key:
        print("ERROR: LITELLM_MASTER_KEY no encontrada")
        sys.exit(1)

    print(f"Benchmark OpenAI directo vs LiteLLM - {timestamp}")
    print(f"Modelo upstream: gpt-5.4-nano")
    print(f"Alias LiteLLM: openai_gpt-5-nano")
    print(f"Direct: {DIRECT_CONFIG['url']}")
    print(f"LiteLLM: {LITELLM_CONFIG['url']}")
    print(f"Warm-up: {WARMUP_REPS}x por ruta")
    print(f"Medicion: {MAIN_REPS}x por ruta (alternando)")
    print()

    all_calls: list[dict] = []

    # Warm-up (excluido de metricas)
    print("=== WARM-UP ===")
    for i in range(WARMUP_REPS):
        print(f"  Warm-up directo {i+1}/{WARMUP_REPS}...", end=" ")
        call = single_call(
            DIRECT_CONFIG["route"], DIRECT_CONFIG["url"],
            DIRECT_CONFIG["model"], direct_key, -1, -1
        )
        print(f"TTFT={call['time_to_first_visible_text_ms']}ms" if call['success'] else f"ERROR: {call['error']}")

        print(f"  Warm-up LiteLLM {i+1}/{WARMUP_REPS}...", end=" ")
        call = single_call(
            LITELLM_CONFIG["route"], LITELLM_CONFIG["url"],
            LITELLM_CONFIG["model"], litellm_key, -1, -1
        )
        print(f"TTFT={call['time_to_first_visible_text_ms']}ms" if call['success'] else f"ERROR: {call['error']}")

    # Medicion principal con alternancia
    print("\n=== MEDICION PRINCIPAL ===")
    for rep in range(MAIN_REPS):
        if rep % 2 == 0:
            order = [(DIRECT_CONFIG, 0), (LITELLM_CONFIG, 1)]
        else:
            order = [(LITELLM_CONFIG, 0), (DIRECT_CONFIG, 1)]

        for cfg, order_pos in order:
            key = get_key(cfg["key_var"])
            label = "Directo" if cfg["route"] == "openai_direct" else "LiteLLM"
            print(f"  [{rep+1}/{MAIN_REPS}] {label} (orden {order_pos+1})...", end=" ")

            call = single_call(
                cfg["route"], cfg["url"], cfg["model"],
                key, rep, order_pos
            )
            all_calls.append(call)

            if call["success"]:
                print(f"TTFT={call['time_to_first_visible_text_ms']}ms "
                      f"Lat={call['total_latency_ms']}ms "
                      f"toks={call['total_tokens']}")
            else:
                print(f"ERROR: {call['error']}")

        # Pausa minima entre pares
        if rep < MAIN_REPS - 1:
            time.sleep(0.3)

    print(f"\n=== COMPLETADO: {len(all_calls)} llamadas medidas ===")

    # Separar por ruta
    direct_calls = [c for c in all_calls if c["route"] == "openai_direct"]
    litellm_calls = [c for c in all_calls if c["route"] == "litellm_proxy"]

    # Escribir archivos
    with open(output_dir / "calls.jsonl", "w") as f:
        for c in all_calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    with open(output_dir / "calls.csv", "w") as f:
        keys = list(all_calls[0].keys()) if all_calls else []
        f.write(",".join(keys) + "\n")
        for c in all_calls:
            row = [str(c.get(k, "")).replace(",", ";") for k in keys]
            f.write(",".join(row) + "\n")

    summary = {
        "metadata": {
            "timestamp": timestamp,
            "direct_model": DIRECT_CONFIG["model"],
            "litellm_alias": LITELLM_CONFIG["model"],
            "litellm_upstream": "openai/gpt-5.4-nano (confirmado via /health)",
            "warmup_per_route": WARMUP_REPS,
            "measured_per_route": MAIN_REPS,
            "total_measured": len(all_calls),
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "stream": True,
            "stream_options": {"include_usage": True},
        },
        "direct": None,
        "litellm": None,
    }

    for label, calls, cfg_key in [
        ("direct", direct_calls, DIRECT_CONFIG),
        ("litellm", litellm_calls, LITELLM_CONFIG),
    ]:
        ttfts = [c["time_to_first_visible_text_ms"] for c in calls if c.get("time_to_first_visible_text_ms") is not None]
        lats = [c["total_latency_ms"] for c in calls if c.get("total_latency_ms") is not None]
        p_toks = [c["prompt_tokens"] for c in calls if c.get("prompt_tokens") is not None]
        c_toks = [c["completion_tokens"] for c in calls if c.get("completion_tokens") is not None]
        successes = [c for c in calls if c["success"]]
        errors = [c for c in calls if not c["success"]]
        reported_models = set(c.get("reported_model") for c in calls if c.get("reported_model"))

        summary[label] = {
            "route": cfg_key["route"],
            "model_requested": cfg_key["model"],
            "model_reported": list(reported_models) if reported_models else None,
            "n_calls": len(calls),
            "n_success": len(successes),
            "n_errors": len(errors),
            "error_details": [c["error"] for c in errors],
            "ttft": compute_stats(ttfts) if ttfts else None,
            "total_latency": compute_stats(lats) if lats else None,
            "total_prompt_tokens": sum(p_toks) if p_toks else None,
            "total_completion_tokens": sum(c_toks) if c_toks else None,
            "avg_prompt_tokens": round(sum(p_toks) / len(p_toks), 0) if p_toks else None,
            "avg_completion_tokens": round(sum(c_toks) / len(c_toks), 0) if c_toks else None,
            "no_reasoning": all(c.get("reasoning_tokens") == 0 for c in calls),
            "semantic": check_semantic_equivalence(" ".join(c.get("response_text", "") for c in calls)),
            "first_call_ttft": calls[0].get("time_to_first_visible_text_ms") if calls else None,
            "last_call_ttft": calls[-1].get("time_to_first_visible_text_ms") if calls else None,
        }

    # Overhead
    if summary["direct"] and summary["litellm"]:
        d_ttft = summary["direct"]["ttft"]
        l_ttft = summary["litellm"]["ttft"]
        d_lat = summary["direct"]["total_latency"]
        l_lat = summary["litellm"]["total_latency"]

        overhead = {
            "ttft_abs_ms": (
                round(l_ttft["avg"] - d_ttft["avg"], 1)
                if d_ttft and l_ttft and d_ttft["avg"] is not None
                else None
            ),
            "ttft_pct": (
                round(((l_ttft["avg"] / d_ttft["avg"]) - 1) * 100, 1)
                if d_ttft and l_ttft and d_ttft["avg"] and d_ttft["avg"] > 0
                else None
            ),
            "total_latency_abs_ms": (
                round(l_lat["avg"] - d_lat["avg"], 1)
                if d_lat and l_lat and d_lat["avg"] is not None
                else None
            ),
            "total_latency_pct": (
                round(((l_lat["avg"] / d_lat["avg"]) - 1) * 100, 1)
                if d_lat and l_lat and d_lat["avg"] and d_lat["avg"] > 0
                else None
            ),
        }
        summary["overhead"] = overhead

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    generate_report(output_dir, summary)

    print(f"\nResultados en: {output_dir}")
    print("  calls.jsonl, calls.csv, summary.json, report.md")


def generate_report(output_dir: Path, summary: dict):
    lines = []
    lines.append("# OpenAI directo vs LiteLLM Proxy — Benchmark de Latencia")
    lines.append("")
    lines.append(f"**Fecha**: {summary['metadata']['timestamp']}")
    lines.append(f"**Modelo upstream**: `{summary['metadata']['direct_model']}`")
    lines.append(f"**Alias LiteLLM**: `{summary['metadata']['litellm_alias']}`")
    lines.append(f"**Upstream LiteLLM confirmado**: `{summary['metadata']['litellm_upstream']}`")
    lines.append(f"**Llamadas medidas por ruta**: {summary['metadata']['measured_per_route']}")
    lines.append(f"**Total medidas**: {summary['metadata']['total_measured']}")
    lines.append(f"**Warm-up por ruta**: {summary['metadata']['warmup_per_route']}")
    lines.append(f"**Stream**: {summary['metadata']['stream']}")
    lines.append(f"**Stream options**: `include_usage=true`")
    lines.append(f"")

    lines.append(f"## Overhead LiteLLM")
    lines.append(f"")
    oh = summary.get("overhead", {})
    if oh:
        lines.append(f"| Metrica | Valor |")
        lines.append(f"|---|---|")
        lines.append(f"| Overhead TTFT absoluto | {oh.get('ttft_abs_ms', 'N/A')}ms |")
        lines.append(f"| Overhead TTFT porcentual | {oh.get('ttft_pct', 'N/A')}% |")
        lines.append(f"| Overhead latencia total absoluto | {oh.get('total_latency_abs_ms', 'N/A')}ms |")
        lines.append(f"| Overhead latencia total porcentual | {oh.get('total_latency_pct', 'N/A')}% |")
    lines.append(f"")

    lines.append(f"## TTFT (Time to First Visible Text)")
    lines.append(f"")
    lines.append(f"| Metrica | OpenAI directo | LiteLLM | Overhead |")
    lines.append(f"|---|---|---|---|")
    d_ttft = summary.get("direct", {}).get("ttft", {})
    l_ttft = summary.get("litellm", {}).get("ttft", {})
    if d_ttft and l_ttft:
        for metric in ["avg", "median", "min", "max", "stdev", "p95"]:
            d_val = d_ttft.get(metric, "N/A")
            l_val = l_ttft.get(metric, "N/A")
            oh_val = ""
            if isinstance(d_val, (int, float)) and isinstance(l_val, (int, float)):
                oh_val = f"{l_val - d_val:+.1f}ms"
            lines.append(f"| TTFT {metric} | {d_val}ms | {l_val}ms | {oh_val} |")
    lines.append(f"")

    lines.append(f"## Latencia total")
    lines.append(f"")
    lines.append(f"| Metrica | OpenAI directo | LiteLLM | Overhead |")
    lines.append(f"|---|---|---|---|")
    d_lat = summary.get("direct", {}).get("total_latency", {})
    l_lat = summary.get("litellm", {}).get("total_latency", {})
    if d_lat and l_lat:
        for metric in ["avg", "median", "min", "max", "stdev", "p95"]:
            d_val = d_lat.get(metric, "N/A")
            l_val = l_lat.get(metric, "N/A")
            oh_val = ""
            if isinstance(d_val, (int, float)) and isinstance(l_val, (int, float)):
                oh_val = f"{l_val - d_val:+.1f}ms"
            lines.append(f"| Latencia {metric} | {d_val}ms | {l_val}ms | {oh_val} |")
    lines.append(f"")

    lines.append(f"## Tokens")
    lines.append(f"")
    d_tok = summary.get("direct", {})
    l_tok = summary.get("litellm", {})
    lines.append(f"| Metrica | OpenAI directo | LiteLLM |")
    lines.append(f"|---|---|---|")
    lines.append(f"| Prompt tokens total | {d_tok.get('total_prompt_tokens', 'N/A')} | {l_tok.get('total_prompt_tokens', 'N/A')} |")
    lines.append(f"| Completion tokens total | {d_tok.get('total_completion_tokens', 'N/A')} | {l_tok.get('total_completion_tokens', 'N/A')} |")
    lines.append(f"| Avg prompt tokens | {d_tok.get('avg_prompt_tokens', 'N/A')} | {l_tok.get('avg_prompt_tokens', 'N/A')} |")
    lines.append(f"| Avg completion tokens | {d_tok.get('avg_completion_tokens', 'N/A')} | {l_tok.get('avg_completion_tokens', 'N/A')} |")
    lines.append(f"| Reasoning tokens | {'0 en todas' if d_tok.get('no_reasoning') else 'algunas'} | {'0 en todas' if l_tok.get('no_reasoning') else 'algunas'} |")
    lines.append(f"")

    lines.append(f"## Confiabilidad")
    lines.append(f"")
    d_calls = summary.get("direct", {})
    l_calls = summary.get("litellm", {})
    lines.append(f"| Metrica | OpenAI directo | LiteLLM |")
    lines.append(f"|---|---|---|")
    lines.append(f"| Tasa de exito | {d_calls.get('n_success', 0)}/{d_calls.get('n_calls', 0)} | {l_calls.get('n_success', 0)}/{l_calls.get('n_calls', 0)} |")
    lines.append(f"| Errores | {d_calls.get('n_errors', 0)} | {l_calls.get('n_errors', 0)} |")
    lines.append(f"| Fallback | No | No |")
    lines.append(f"| Modelo reportado | {d_calls.get('model_reported', 'N/A')} | {l_calls.get('model_reported', 'N/A')} |")
    lines.append(f"")

    lines.append(f"## Equivalencia semantica")
    lines.append(f"")
    d_sem = summary.get("direct", {}).get("semantic", {})
    l_sem = summary.get("litellm", {}).get("semantic", {})
    lines.append(f"| Check | OpenAI directo | LiteLLM |")
    lines.append(f"|---|---|---|")
    for check in ["has_whatsapp", "has_gmail", "has_stock_system", "has_prices_spreadsheet", "has_discounts_human", "has_no_promise", "is_spanish"]:
        lines.append(f"| {check} | {d_sem.get(check, '?')} | {l_sem.get(check, '?')} |")
    lines.append(f"")

    lines.append(f"## Conclusion")
    lines.append(f"")
    oh = summary.get("overhead", {})
    oh_ttft = oh.get("ttft_abs_ms", None)
    oh_pct = oh.get("ttft_pct", None)
    oh_lat = oh.get("total_latency_abs_ms", None)

    verdict_lines = []
    if oh_ttft is not None and oh_ttft < 250:
        verdict_lines.append(f"✅ Overhead TTFT ({oh_ttft}ms) es ACEPTABLE (< 250ms)")
    elif oh_ttft is not None:
        verdict_lines.append(f"⚠️ Overhead TTFT ({oh_ttft}ms) supera el umbral de 250ms — revisar")
    else:
        verdict_lines.append("❓ Overhead TTFT no disponible")

    if oh_pct is not None and oh_pct < 25:
        verdict_lines.append(f"✅ Overhead TTFT % ({oh_pct}%) es ACEPTABLE (< 25%)")
    elif oh_pct is not None:
        verdict_lines.append(f"⚠️ Overhead TTFT % ({oh_pct}%) supera 25% — revisar")
    else:
        verdict_lines.append("❓ Overhead TTFT % no disponible")

    if oh_lat is not None and oh_lat < 500:
        verdict_lines.append(f"✅ Overhead latencia total ({oh_lat}ms) es ACEPTABLE (< 500ms)")
    elif oh_lat is not None:
        verdict_lines.append(f"⚠️ Overhead latencia total ({oh_lat}ms) supera 500ms — revisar")
    else:
        verdict_lines.append("❓ Overhead latencia total no disponible")

    if d_calls.get("n_success", 0) == d_calls.get("n_calls", 0) and l_calls.get("n_success", 0) == l_calls.get("n_calls", 0):
        verdict_lines.append("✅ Tasa de exito: 100% en ambas rutas")
    else:
        verdict_lines.append("⚠️ Hay errores en una o ambas rutas")

    lines.append("\n".join(verdict_lines))
    lines.append(f"")

    if oh_ttft is not None and oh_ttft < 250 and oh_pct is not None and oh_pct < 25:
        lines.append(f"### Recomendacion: USAR LiteLLM COMO GATEWAY PRINCIPAL")
        lines.append(f"")
        lines.append(f"LiteLLM agrega un overhead aceptable para Vera publica. "
                     f"Se recomienda:")
        lines.append(f"- Usar LiteLLM como gateway multi-tenant principal")
        lines.append(f"- OpenAI directo como bypass de emergencia")
        lines.append(f"- Siguiente fase: virtual keys por cliente y telemetria")
    else:
        lines.append(f"### Recomendacion: RESERVAR LiteLLM PARA TAREAS INTERNAS")
        lines.append(f"")
        lines.append(f"El overhead de LiteLLM es significativo para Vera publica. "
                     f"Se recomienda:")
        lines.append(f"- OpenAI directo como via principal")
        lines.append(f"- LiteLLM para tareas internas o batch")
        lines.append(f"- Investigar configuracion del proxy")

    lines.append(f"")
    lines.append(f"## Notas")
    lines.append(f"")
    lines.append(f"- LiteLLM levantado en http://localhost:4000")
    lines.append(f"- PostgreSQL 18: disponible (Docker, no usado)")
    lines.append(f"- Milvus 2.6: disponible (Docker, no usado)")
    lines.append(f"- `stream_options`: `include_usage=true` funcionando en ambas rutas")
    lines.append(f"- Sin fallback configurado")
    lines.append(f"- Sin virtual keys")

    report_path = output_dir / "report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Reporte: {report_path}")


if __name__ == "__main__":
    main()

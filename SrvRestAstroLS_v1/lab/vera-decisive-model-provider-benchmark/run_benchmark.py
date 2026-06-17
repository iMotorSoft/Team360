#!/usr/bin/env python3
"""Benchmark decisivo de modelos/proveedores para Vera.

Ejecuta una conversacion fija contra cada combinacion modelo+proveedor,
mide metricas por turno y por conversacion, genera reportes.

USO:
    uv run python SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py
    uv run python SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py --repeat 3
    uv run python SrvRestAstroLS_v1/lab/vera-decisive-model-provider-benchmark/run_benchmark.py --provider gemini --no-stream
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from adapters import PROVIDER_CONFIGS, create_adapter
from conversation import (
    ACTION_INSTRUCTIONS,
    CONVERSATION_TURNS,
    SYSTEM_PROMPT,
    GOLDEN_ANSWER_SEMANTIC,
)
from rag_context import (
    RAG_CHUNKS,
    RETRIEVAL_MODE,
    RETRIEVAL_NOTE,
    RETRIEVAL_QUERY_CANONICAL,
)
from scoring import auto_score_turn, compute_conversation_score

HERE = Path(__file__).resolve().parent
DEFAULT_REPEAT = 5
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT = 60.0
DEFAULT_OUTPUT_DIR = HERE / "results"


def load_prices(path: str | None = None) -> dict:
    """Cargar precios desde model_prices.local.json."""
    if path:
        p = Path(path)
    else:
        p = HERE / "model_prices.local.json"
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}


def build_messages(
    turn_index: int, action: str, user_message: str, history: list[dict]
) -> list[dict]:
    """Construir lista de mensajes para la API.

    Sistema + contexto RAG + accion + historial + mensaje actual.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    rag_text = "\n\n".join(
        f"[Fuente: {c['source']} (score: {c['score']})]\n{c['content']}"
        for c in RAG_CHUNKS
    )
    if rag_text:
        messages.append({
            "role": "developer" if turn_index == 0 else "system",
            "content": f"Contexto de conocimiento:\n{rag_text}",
        })

    action_instruction = ACTION_INSTRUCTIONS.get(action, "")
    if action_instruction:
        messages.append({
            "role": "developer",
            "content": action_instruction,
        })

    for h in history:
        messages.append({"role": "user", "content": h["user"]})
        if h["assistant"]:
            messages.append({"role": "assistant", "content": h["assistant"]})

    messages.append({"role": "user", "content": user_message})
    return messages


def run_single_turn(
    adapter, turn_index: int, action: str, user_message: str, history: list[dict]
) -> dict:
    """Ejecutar un turno y devolver metricas."""
    messages = build_messages(turn_index, action, user_message, history)
    start = time.monotonic()
    result = adapter.chat_completion(messages)
    total_latency = time.monotonic() - start

    turn_data: dict[str, Any] = {
        "run_id": None,
        "repetition": None,
        "provider": adapter.__class__.__name__.replace("Adapter", "").lower(),
        "model": adapter.model,
        "turn_index": turn_index,
        "action": action,
        "user_message": user_message,
        "assistant_message": result.get("response_text", ""),
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "total_tokens": result.get("total_tokens"),
        "reasoning_tokens": result.get("reasoning_tokens"),
        "cached_tokens": result.get("cached_tokens"),
        "ttft_ms": result.get("ttft_ms"),
        "total_latency_ms": result.get("total_latency_ms"),
        "finish_reason": result.get("finish_reason"),
        "success": result.get("success", False),
        "error": result.get("error"),
    }
    return turn_data


def run_conversation(
    adapter, run_id: str, repetition: int
) -> list[dict]:
    """Ejecutar conversacion completa. Retorna lista de turnos con metricas."""
    history: list[dict] = []
    turn_results: list[dict] = []

    for i, turn in enumerate(CONVERSATION_TURNS):
        turn_data = run_single_turn(
            adapter, i, turn["action"], turn["user_message"], history
        )
        turn_data["run_id"] = run_id
        turn_data["repetition"] = repetition
        turn_data["response_words"] = len(turn_data["assistant_message"].split())
        turn_data["response_chars"] = len(turn_data["assistant_message"])

        scoring = auto_score_turn(
            turn_data,
            [h["assistant"] or "" for h in history],
        )
        turn_data.update(scoring)

        turn_results.append(turn_data)

        history.append({
            "user": turn["user_message"],
            "assistant": turn_data["assistant_message"],
        })

    return turn_results


def compute_conversation_metrics(turns: list[dict]) -> dict:
    """Calcular metricas agregadas por conversacion."""
    ttfts = [t["ttft_ms"] for t in turns if t.get("ttft_ms") is not None]
    latencies = [
        t["total_latency_ms"] for t in turns if t.get("total_latency_ms") is not None
    ]
    prompt_toks = [t["prompt_tokens"] for t in turns if t.get("prompt_tokens") is not None]
    completion_toks = [
        t["completion_tokens"] for t in turns if t.get("completion_tokens") is not None
    ]

    return {
        "total_turns": len(turns),
        "total_prompt_tokens": sum(prompt_toks) if prompt_toks else None,
        "total_completion_tokens": sum(completion_toks) if completion_toks else None,
        "total_tokens": (
            sum(prompt_toks) + sum(completion_toks)
            if prompt_toks and completion_toks
            else None
        ),
        "total_reasoning_tokens": sum(
            t.get("reasoning_tokens") or 0 for t in turns
        ) or None,
        "ttft_avg": round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
        "ttft_median": round(median(ttfts), 1) if ttfts else None,
        "ttft_p95_approx": (
            round(sorted(ttfts)[int(len(ttfts) * 0.95)], 1)
            if len(ttfts) >= 20
            else None
        ),
        "total_latency_ms": sum(latencies) if latencies else None,
        "total_words": sum(t.get("response_words", 0) for t in turns),
        "repeated_questions": sum(
            1 for t in turns if t.get("repeated_question")
        ),
        "premature_diagnoses": sum(
            1 for t in turns if t.get("diagnosis_premature")
        ),
        "complete_diagnosis": any(t.get("diagnosis_complete") for t in turns),
        "total_error_turns": sum(1 for t in turns if not t.get("success")),
        "errors": [t.get("error") for t in turns if t.get("error")],
    }


def calculate_cost(
    provider: str, model: str, prompt_tokens: int | None,
    completion_tokens: int | None, prices: dict
) -> dict:
    """Calcular costo estimado."""
    model_prices = prices.get("models", {}).get(model, {})
    if not model_prices:
        return {"cost": None, "cost_estimated": False}

    input_price = model_prices.get("input_per_1m")
    output_price = model_prices.get("output_per_1m")

    if input_price is None or output_price is None:
        return {"cost": None, "cost_estimated": False}

    cost = 0.0
    if prompt_tokens:
        cost += (prompt_tokens / 1_000_000) * input_price
    if completion_tokens:
        cost += (completion_tokens / 1_000_000) * output_price

    return {"cost": round(cost, 6), "cost_estimated": True}


def format_model_label(provider: str, model: str) -> str:
    for cfg in PROVIDER_CONFIGS:
        if cfg["provider"] == provider and cfg["model"] == model:
            return cfg["label"]
    return f"{provider}/{model}"


def main():
    parser = argparse.ArgumentParser(description="Benchmark decisivo de modelos Vera")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--provider", choices=["gemini", "openai", "requesty", "all"], default="all")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--stream", action="store_true", default=True)
    parser.add_argument("--no-stream", action="store_false", dest="stream")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--prices-file", type=str, default=None)
    parser.add_argument("--smoke", action="store_true", help="Ejecutar solo 1 repeticion por provider (smoke test)")
    args = parser.parse_args()

    repeat = 1 if args.smoke else args.repeat
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_tag = f"{timestamp}"

    prices = load_prices(args.prices_file)
    enabled_providers = [p for p in PROVIDER_CONFIGS if args.provider in ("all", p["provider"])]
    enabled_providers = [p for p in enabled_providers if p["key_found"]]

    print(f"Benchmark decisivo Vera - {run_tag}")
    print(f"Repeticiones: {repeat}")
    print(f"Proveedores habilitados: {len(enabled_providers)}")
    for p in enabled_providers:
        print(f"  [{p['key_var']}] {p['label']} ({p['provider']}/{p['model']})")

    configured = [p for p in enabled_providers if p["key_found"]]
    not_configured = [p for p in PROVIDER_CONFIGS if p not in configured and args.provider in ("all", p["provider"])]

    if not_configured:
        print(f"\nProveedores NO configurados (key no encontrada):")
        for p in not_configured:
            print(f"  {p['label']} -> necesita env var: {p['key_var']}")

    if not configured:
        print("\nERROR: Ningun proveedor configurado. Saliendo.")
        sys.exit(1)

    print(f"\nModo RAG: {RETRIEVAL_MODE}")
    print(f"Chunks: {len(RAG_CHUNKS)}")
    print(f"Turnos: {len(CONVERSATION_TURNS)}")
    print()

    all_turns: list[dict] = []
    all_conversations: list[dict] = []

    run_counter = 0
    for cfg in configured:
        print(f"\n{'='*60}")
        print(f"PROVEEDOR: {cfg['label']}")
        print(f"Modelo: {cfg['model']}")
        print(f"{'='*60}")

        for rep in range(repeat):
            run_id = f"{cfg['provider']}_{cfg['model'].replace('/', '_')}_{run_tag}_rep{rep:03d}"
            run_counter += 1

            print(f"\n  Repeticion {rep+1}/{repeat} [run_id: {run_id[:50]}...]")

            adapter = create_adapter(
                cfg["provider"],
                cfg["model"],
                temperature=args.temperature,
                timeout=args.timeout,
                stream=args.stream,
            )

            if not adapter.configured:
                print(f"    SKIP: adapter no configurado")
                continue

            turns = run_conversation(adapter, run_id, rep)

            conv_metrics = compute_conversation_metrics(turns)
            cost_info = calculate_cost(
                cfg["provider"], cfg["model"],
                conv_metrics["total_prompt_tokens"],
                conv_metrics["total_completion_tokens"],
                prices,
            )
            score_info = compute_conversation_score(turns, cfg["provider"], cfg["model"])

            conversation = {
                "run_id": run_id,
                "provider": cfg["provider"],
                "model": cfg["model"],
                "label": cfg["label"],
                "repetition": rep,
                "timestamp": timestamp,
                "temperature": args.temperature,
                "stream": args.stream,
                **conv_metrics,
                **cost_info,
                **score_info,
                "retrieval_mode": RETRIEVAL_MODE,
            }
            all_conversations.append(conversation)
            all_turns.extend(turns)

            ttft_avg = conv_metrics.get("ttft_avg", "N/A")
            lat_total = conv_metrics.get("total_latency_ms", "N/A")
            score = score_info.get("auto_score", "N/A")
            passed = score_info.get("passed", False)
            print(f"    TTFT avg: {ttft_avg}ms | Lat total: {lat_total}ms | Score: {score} | Pass: {passed}")

    print(f"\n{'='*60}")
    print(f"BENCHMARK COMPLETADO: {run_counter} corridas")
    print(f"{'='*60}")

    results = {
        "metadata": {
            "timestamp": timestamp,
            "repeat": repeat,
            "temperature": args.temperature,
            "stream": args.stream,
            "retrieval_mode": RETRIEVAL_MODE,
            "retrieval_note": RETRIEVAL_NOTE,
            "retrieval_query": RETRIEVAL_QUERY_CANONICAL,
            "num_chunks": len(RAG_CHUNKS),
            "num_turns": len(CONVERSATION_TURNS),
            "not_configured": [
                {"label": p["label"], "key_var": p["key_var"]}
                for p in not_configured
            ],
        },
        "conversations": all_conversations,
    }

    base = output_dir / run_tag
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "turns.jsonl", "w") as f:
        for t in all_turns:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    with open(base / "conversations.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if all_turns:
        with open(base / "turns.csv", "w", newline="", encoding="utf-8") as f:
            fieldnames = list(all_turns[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_turns)

    summary_rows = []
    for conv in all_conversations:
        row = {k: v for k, v in conv.items() if k != "errors"}
        if isinstance(row.get("errors"), list):
            row["errors"] = "; ".join(
                str(e) for e in conv.get("errors", []) if e
            )
        summary_rows.append(row)

    with open(base / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_rows, f, ensure_ascii=False, indent=2)

    generate_report(base, all_conversations, all_turns, timestamp, prices, not_configured, repeat)

    print(f"\nResultados en: {base}")
    print("  turns.jsonl")
    print("  turns.csv")
    print("  conversations.json")
    print("  summary.json")
    print("  report.md")

    return results


def generate_report(
    base: Path,
    conversations: list[dict],
    all_turns: list[dict],
    timestamp: str,
    prices: dict,
    not_configured: list,
    repeat: int = 5,
):
    """Generar reporte markdown con resultados."""
    lines = []
    lines.append(f"# Reporte Benchmark Decisivo Vera")
    lines.append(f"")
    lines.append(f"**Fecha**: {timestamp}")
    num_reps = len(set(c.get('repetition', 0) for c in conversations)) if conversations else 1
    lines.append(f"**Repeticiones por combinacion**: {num_reps}")
    lines.append(f"**Turnos por conversacion**: {len(CONVERSATION_TURNS)}")
    lines.append(f"**Modo RAG**: {RETRIEVAL_MODE}")
    lines.append(f"**Chunks estaticos**: {len(RAG_CHUNKS)}")
    lines.append(f"")

    lines.append(f"## Proveedores Configurados")
    lines.append(f"")
    lines.append(f"| Proveedor | Modelo | Key |")
    lines.append(f"|---|---|---|")
    for p in PROVIDER_CONFIGS:
        status = "OK" if p["key_found"] else "FALTA"
        lines.append(f"| {p['label']} | `{p['model']}` | `{p['key_var']}`={status} |")
    lines.append(f"")

    if not_configured:
        lines.append(f"### Proveedores no disponibles")
        lines.append(f"")
        for p in not_configured:
            lines.append(f"- {p['label']}: falta `{p['key_var']}`")
        lines.append(f"")

    lines.append(f"## Resultados por Proveedor/Modelo")
    lines.append(f"")

    by_combo = defaultdict(list)
    for conv in conversations:
        key = (conv["provider"], conv["model"], conv.get("label", ""))
        by_combo[key].append(conv)

    lines.append(f"| Combo | Runs | Avg Score | Avg TTFT | Avg Lat | Cost | Diagnoses | Pass/Fail |")
    lines.append(f"|---|---|---|---|---|---|---|---|")

    best_score = -1
    best_label = ""
    fastest_label = ""
    fastest_ttft = float("inf")
    cheapest_label = ""
    cheapest_cost = float("inf")

    for (prov, model, label), convs in sorted(by_combo.items()):
        n = len(convs)
        avg_score = sum(c.get("auto_score", 0) or 0 for c in convs) / n
        ttfts = [c.get("ttft_avg") for c in convs if c.get("ttft_avg") is not None]
        avg_ttft = sum(ttfts) / len(ttfts) if ttfts else 0
        lats = [c.get("total_latency_ms") for c in convs if c.get("total_latency_ms") is not None]
        avg_lat = sum(lats) / len(lats) if lats else 0
        costs = [c.get("cost") for c in convs if c.get("cost") is not None]
        avg_cost = sum(costs) / len(costs) if costs else 0
        diagnoses = sum(1 for c in convs if c.get("complete_diagnosis"))
        passed = sum(1 for c in convs if c.get("passed"))

        cost_str = f"${avg_cost:.6f}" if costs else "N/A"
        lines.append(f"| {label} | {n} | {avg_score:.1f} | {avg_ttft:.0f}ms | {avg_lat:.0f}ms | {cost_str} | {diagnoses}/{n} | {passed}/{n} |")

        if avg_score > best_score:
            best_score = avg_score
            best_label = label
        if avg_ttft < fastest_ttft and ttfts:
            fastest_ttft = avg_ttft
            fastest_label = label
        if costs and avg_cost < cheapest_cost:
            cheapest_cost = avg_cost
            cheapest_label = label

    lines.append(f"")

    lines.append(f"### Mejor calidad: {best_label} ({best_score:.1f})")
    lines.append(f"### Mas rapido: {fastest_label} ({fastest_ttft:.0f}ms avg TTFT)")
    if cheapest_label:
        lines.append(f"### Menor costo: {cheapest_label} (${cheapest_cost:.6f} avg)")

    lines.append(f"")

    lines.append(f"## Mediciones por Turno")
    lines.append(f"")
    lines.append(f"| Turno | Accion | Palabras | Preguntas | TTFT avg | Lat avg |")
    lines.append(f"|---|---|---|---|---|---|")
    turn_stats = defaultdict(list)
    for turn in all_turns:
        idx = turn.get("turn_index")
        turn_stats[idx].append({
            "words": turn.get("response_words", 0),
            "questions": turn.get("question_count", 0),
            "ttft": turn.get("ttft_ms"),
            "lat": turn.get("total_latency_ms"),
            "action": turn.get("action", ""),
        })
    for idx in sorted(turn_stats.keys()):
        stats = turn_stats[idx]
        avg_w = sum(s["words"] for s in stats) / len(stats)
        avg_q = sum(s["questions"] for s in stats) / len(stats)
        ttfts_t = [s["ttft"] for s in stats if s["ttft"]]
        avg_ttft_t = sum(ttfts_t) / len(ttfts_t) if ttfts_t else 0
        lats_t = [s["lat"] for s in stats if s["lat"]]
        avg_lat_t = sum(lats_t) / len(lats_t) if lats_t else 0
        action = stats[0]["action"] if stats else ""
        lines.append(f"| {idx+1} | {action} | {avg_w:.0f} | {avg_q:.1f} | {avg_ttft_t:.0f}ms | {avg_lat_t:.0f}ms |")
    lines.append(f"")

    lines.append(f"## Fallos Automaticos")
    lines.append(f"")
    fail_counts = defaultdict(int)
    for conv in conversations:
        for reason in conv.get("fail_reasons", []):
            fail_counts[reason] += 1
    if fail_counts:
        lines.append(f"| Falla | Conteo |")
        lines.append(f"|---|---|")
        for reason, count in sorted(fail_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append(f"No se detectaron fallos automaticos.")
    lines.append(f"")

    lines.append(f"## Scores por Componente")
    lines.append(f"")
    lines.append(f"| Combo | Conv. Entend. | Diag. Calidad | Velocidad | Costo | Estabilidad | Formato | Ponderado |")
    lines.append(f"|---|---|---|---|---|---|---|---|")
    for (prov, model, label), convs in sorted(by_combo.items()):
        details_list = [c.get("auto_details", {}) for c in convs]
        avg_comp = {}
        for key in ["conversation_understanding", "diagnosis_quality", "speed_latency", "cost", "stability", "language_format"]:
            vals = [d.get(key, 0) or 0 for d in details_list if d]
            avg_comp[key] = sum(vals) / len(vals) if vals else 0
        avg_score = sum(c.get("auto_score", 0) or 0 for c in convs) / len(convs)
        lines.append(
            f"| {label} | {avg_comp['conversation_understanding']:.0f} | "
            f"{avg_comp['diagnosis_quality']:.0f} | {avg_comp['speed_latency']:.0f} | "
            f"{avg_comp['cost']:.0f} | {avg_comp['stability']:.0f} | "
            f"{avg_comp['language_format']:.0f} | {avg_score:.1f} |"
        )
    lines.append(f"")

    lines.append(f"## Transcripcion Representativa (mejor corrida)")
    lines.append(f"")
    best_conv = max(conversations, key=lambda c: c.get("auto_score", 0) or 0) if conversations else None
    if best_conv:
        best_run_id = best_conv.get("run_id", "")
        best_turns = [t for t in all_turns if t.get("run_id") == best_run_id]
        lines.append(f"**Mejor corrida**: {best_conv.get('label', '')} (run_id={best_run_id[:60]}, score={best_conv.get('auto_score', 'N/A')})")
        lines.append(f"")
        best_turns.sort(key=lambda t: t.get("turn_index", 0))
        for turn in best_turns:
                lines.append(f"### Turno {turn.get('turn_index', 0)+1}: {turn.get('action', '')}")
                lines.append(f"")
                lines.append(f"**Usuario**: {turn.get('user_message', '')}")
                lines.append(f"")
                lines.append(f"**Asistente**: {turn.get('assistant_message', '')}")
                lines.append(f"")
                lines.append(f"- TTFT: {turn.get('ttft_ms', 'N/A')}ms | Latencia: {turn.get('total_latency_ms', 'N/A')}ms")
                lines.append(f"- Tokens: p={turn.get('prompt_tokens', '?')} + c={turn.get('completion_tokens', '?')}")
                lines.append(f"- Preguntas: {turn.get('question_count', 0)} | Diag. prematuro: {turn.get('diagnosis_premature', False)}")
                lines.append(f"")

    lines.append(f"## Recomendacion")
    lines.append(f"")
    lines.append(f"Segun los datos recopilados:")
    lines.append(f"")
    lines.append(f"- **Mejor calidad**: {best_label}")
    lines.append(f"- **Mas rapido**: {fastest_label}")
    if cheapest_label:
        lines.append(f"- **Menor costo**: {cheapest_label}")
    lines.append(f"- **Ganador preliminar**: Pendiente de revision manual de transcripciones.")
    lines.append(f"")

    lines.append(f"## Notas")
    lines.append(f"")
    lines.append(f"- LiteLLM: no levantado durante este benchmark.")
    lines.append(f"- PostgreSQL 18: disponible (Docker).")
    lines.append(f"- Milvus 2.6: disponible (Docker), coleccion `team360_sales_diagnosis_knowledge_v1` existe.")
    lines.append(f"- Retrieval: modo estatico (pymilvus no instalado en el entorno de ejecucion).")
    lines.append(f"- Precios: ver `model_prices.local.json` (no versionado).")
    lines.append(f"- Resultados en `results/` (ignorado por .gitignore).")

    report_path = base / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Reporte: {report_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run Gemini OpenAI-compatible configuration probes and write lab results."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_gemini_openai_compat import BASE_URL, MODELS, retrieve_model, run_completion


LAB_DIR = Path(__file__).resolve().parent
RESULTS_DIR = LAB_DIR / "results"
PROMPT_OK = "Respondé exactamente: OK"
LEVELS: tuple[str | None, ...] = (None, "minimal", "low", "medium", "high")


def now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def label_level(level: str | None) -> str:
    return "default" if level is None else level


def add(results: list[dict[str, Any]], **kwargs: Any) -> None:
    results.append(run_completion(prompt=PROMPT_OK, **kwargs))


def run_all() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    model_retrievals = [retrieve_model(model) for model in MODELS]

    for model in MODELS:
        add(results, scenario="smoke_basic", model=model, reasoning_effort=None, stream=False, max_tokens=256)

    for model in MODELS:
        for level in LEVELS:
            add(
                results,
                scenario="thinking_level",
                model=model,
                reasoning_effort=level,
                stream=False,
                max_tokens=256,
            )

    for model in MODELS:
        for level in (None, "minimal", "medium"):
            add(
                results,
                scenario="streaming",
                model=model,
                reasoning_effort=level,
                stream=True,
                max_tokens=256,
            )

    for model in MODELS:
        add(
            results,
            scenario="output_control_max_tokens_short",
            model=model,
            reasoning_effort="minimal",
            stream=False,
            max_tokens=1,
        )
        add(
            results,
            scenario="output_control_max_tokens_medium",
            model=model,
            reasoning_effort="minimal",
            stream=False,
            max_tokens=64,
        )
        add(
            results,
            scenario="output_control_temperature_low",
            model=model,
            reasoning_effort="minimal",
            stream=False,
            max_tokens=48,
            temperature=0.1,
        )
        add(
            results,
            scenario="output_control_temperature_default",
            model=model,
            reasoning_effort="minimal",
            stream=False,
            max_tokens=48,
        )

    results.append(
        run_completion(
            scenario="negative_model_inexistent",
            model="gemini-model-does-not-exist",
            reasoning_effort=None,
            stream=False,
            max_tokens=16,
            prompt=PROMPT_OK,
        )
    )
    results.append(
        run_completion(
            scenario="negative_reasoning_effort_invalid",
            model=MODELS[0],
            reasoning_effort="invalid-effort",
            stream=False,
            max_tokens=16,
            prompt=PROMPT_OK,
        )
    )
    results.append(
        run_completion(
            scenario="negative_missing_key_simulated",
            model=MODELS[0],
            reasoning_effort="minimal",
            stream=False,
            max_tokens=16,
            prompt=PROMPT_OK,
            api_key="",
        )
    )
    results.append(
        run_completion(
            scenario="negative_max_tokens_invalid",
            model=MODELS[0],
            reasoning_effort="minimal",
            stream=False,
            max_tokens=-1,
            prompt=PROMPT_OK,
        )
    )
    results.append(
        run_completion(
            scenario="negative_unsupported_parameter_probe",
            model=MODELS[0],
            reasoning_effort="minimal",
            stream=False,
            max_tokens=16,
            prompt=PROMPT_OK,
            extra_body={"unsupported_parameter_probe": True},
        )
    )
    results.append(
        run_completion(
            scenario="negative_reasoning_effort_with_thinking_budget",
            model=MODELS[0],
            reasoning_effort="minimal",
            stream=False,
            max_tokens=16,
            prompt=PROMPT_OK,
            extra_body={
                "extra_body": {
                    "google": {
                        "thinking_config": {
                            "thinking_budget": 1024,
                        }
                    }
                }
            },
        )
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": BASE_URL,
        "model_retrievals": model_retrievals,
        "results": results,
    }


def fmt_ms(value: Any) -> str:
    if value is None:
        return "-"
    return f"{value} ms"


def fmt_tokens(value: Any) -> str:
    return "-" if value is None else str(value)


def summarize_observation(row: dict[str, Any]) -> str:
    if row["success"]:
        notes = []
        if row.get("finish_reason"):
            notes.append(f"finish={row['finish_reason']}")
        if row.get("response_text") != "OK":
            notes.append(f"text={row.get('response_text')!r}")
        return "; ".join(notes) or "OK"
    parts = []
    if row.get("http_status") is not None:
        parts.append(f"HTTP {row['http_status']}")
    if row.get("error_type"):
        parts.append(str(row["error_type"]))
    if row.get("error_message"):
        parts.append(str(row["error_message"]).replace("\n", " ")[:160])
    return "; ".join(parts)


def build_report(payload: dict[str, Any]) -> str:
    results = payload["results"]
    lines: list[str] = []
    lines.append("# Gemini OpenAI-compatible model configuration report")
    lines.append("")
    lines.append(f"Timestamp: `{payload['timestamp']}`")
    lines.append(f"Endpoint: `{payload['endpoint']}`")
    lines.append("")
    lines.append("## Model retrieval")
    lines.append("")
    lines.append("| Requested model | Success | Returned id | Notes |")
    lines.append("|---|---:|---|---|")
    for item in payload["model_retrievals"]:
        lines.append(
            f"| `{item['model']}` | {item['success']} | `{item.get('id') or '-'}` | "
            f"{(item.get('error') or '').replace('|', '/') or '-'} |"
        )

    lines.append("")
    lines.append("## Matrix")
    lines.append("")
    lines.append(
        "| Modelo | Thinking | Streaming | Exito | Primer texto | Tiempo total | "
        "Input tokens | Output tokens | Reasoning tokens | Observaciones |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in results:
        lines.append(
            f"| `{row['model']}` | `{label_level(row['reasoning_effort_requested'])}` | "
            f"{row['streaming']} | {row['success']} | {fmt_ms(row['time_to_first_visible_text_ms'])} | "
            f"{fmt_ms(row['latency_ms'])} | {fmt_tokens(row['prompt_tokens'])} | "
            f"{fmt_tokens(row['completion_tokens'])} | {fmt_tokens(row['reasoning_tokens'])} | "
            f"{summarize_observation(row).replace('|', '/')} |"
        )

    lines.append("")
    lines.append("## Thinking support observed")
    lines.append("")
    lines.append("| Modelo | default | minimal | low | medium | high |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    by_model: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in results:
        if row["scenario"] == "thinking_level":
            by_model[row["model"]][label_level(row["reasoning_effort_requested"])] = bool(row["success"])
    for model in MODELS:
        values = by_model[model]
        lines.append(
            f"| `{model}` | {values.get('default')} | {values.get('minimal')} | "
            f"{values.get('low')} | {values.get('medium')} | {values.get('high')} |"
        )

    lines.append("")
    lines.append("## Negative probes")
    lines.append("")
    lines.append("| Scenario | Success | HTTP | Error type | Sanitized error |")
    lines.append("|---|---:|---:|---|---|")
    for row in results:
        if row["scenario"].startswith("negative_"):
            error = (row.get("error_message") or "").replace("\n", " ").replace("|", "/")
            lines.append(
                f"| `{row['scenario']}` | {row['success']} | {row.get('http_status') or '-'} | "
                f"`{row.get('error_type') or '-'}` | {error[:220] or '-'} |"
            )

    lines.append("")
    lines.append("## Conclusions")
    lines.append("")
    lines.append("* This lab only validates Gemini API execution through the OpenAI-compatible endpoint.")
    lines.append("* It does not exercise Vera, diagnosis prompts, Milvus, PostgreSQL, LiteLLM, frontend, or `/t360`.")
    lines.append("* Use `results.json` as the source of truth for raw per-run metadata.")
    return "\n".join(lines) + "\n"


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = run_all()
    timestamp = now_slug()
    json_path = RESULTS_DIR / "results.json"
    md_path = RESULTS_DIR / "report.md"
    timestamped_json_path = RESULTS_DIR / f"{timestamp}_results.json"
    timestamped_md_path = RESULTS_DIR / f"{timestamp}_report.md"
    json_text = json.dumps(payload, indent=2, ensure_ascii=False)
    report_text = build_report(payload)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    md_path.write_text(report_text, encoding="utf-8")
    timestamped_json_path.write_text(json_text + "\n", encoding="utf-8")
    timestamped_md_path.write_text(report_text, encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

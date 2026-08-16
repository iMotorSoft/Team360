"""Reproducible online benchmark for Team360 Flow model evaluation.

Reuses the REAL Flow interpreter adapters (same system prompt, same schema,
same parsing, same temperature) for every model alias. No production code is
modified; LiteLLM is consumed through the existing client only.

Usage (from SrvRestAstroLS_v1/backend):

    uv run python -m modules.flow.model_eval.benchmark --all
    uv run python -m modules.flow.model_eval.benchmark --model openai_gpt-5.4-nano
    uv run python -m modules.flow.model_eval.benchmark --all --consistency 1
    uv run python -m modules.flow.model_eval.benchmark --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from modules.automation_diagnosis.litellm_client import LiteLLMClient
from modules.flow.intake.ai import LiteLLMFlowIntakeInterpreter
from modules.flow.operational_ai import LiteLLMOperationalInterpreter
from modules.messaging.domain import InboundMessage

from .contracts import INTAKE_CONTRACT, MODEL_ALIASES, OPERATIONAL_CONTRACT, PRIMARY_COMPARISON
from .dataset import consistency_subset, load_cases
from .evaluator import (
    CaseEvaluation,
    aggregate_metrics,
    classify_failure,
    escalation_from_evaluations,
    evaluate_case,
    magnitude_label,
    recommend,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
BENCHMARK_NAME = "team360-flow-model-eval"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_info() -> dict[str, str | None]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=10, check=True
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    return {
        "branch": run("git", "branch", "--show-current"),
        "head": run("git", "rev-parse", "HEAD"),
    }


def _message(case: dict[str, Any]) -> InboundMessage:
    return InboundMessage(
        provider="eval",
        channel="email",
        external_message_id=f"model-eval-{case['id']}",
        external_thread_id=f"model-eval-{case['id']}",
        sender="vecina.eval@example.com",
        recipients=("mesaentrada@alquimiablue.com",),
        subject=case.get("subject", ""),
        text_body=case["message"],
        received_at=datetime.now(timezone.utc),
    )


def _build_raw(contract: str, result: Any) -> dict[str, Any]:
    if contract == "operational":
        return {"action": result.action.value, "summary": result.summary}
    return {
        "requests": [request.as_dict() for request in result.requests],
        "clarification_question": result.clarification_question,
    }


def preflight_alias(client: LiteLLMClient, alias: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.chat_completion(
            alias,
            [{"role": "user", "content": "Respondé SOLO con la palabra OK en mayúsculas, sin razonar."}],
            temperature=0.0,
            max_tokens=300,
            correlation_id=f"model-eval-preflight-{alias}",
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "status": "PASS" if response.content.strip() else "WARN",
            "latency_ms": latency_ms,
            "content_non_empty": bool(response.content.strip()),
            "provider_model": response.model,
            "detail": "empty content" if not response.content.strip() else "",
        }
    except Exception as exc:
        failure_type, detail = classify_failure(exc)
        return {
            "status": "FAIL",
            "latency_ms": None,
            "content_non_empty": False,
            "provider_model": None,
            "detail": f"{failure_type}: {detail}",
        }


def run_case_once(
    case: dict[str, Any],
    alias: str,
    client: LiteLLMClient,
) -> CaseEvaluation:
    timestamp = _iso_now()
    raw: dict[str, Any] | None = None
    contract_valid = True
    provider_model: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] = {}
    error_type: str | None = None
    error_detail: str | None = None
    success = True

    try:
        message = _message(case)
        if case["contract"] == "operational":
            result = LiteLLMOperationalInterpreter(client=client, model=alias).interpret(
                message
            )
        else:
            result = LiteLLMFlowIntakeInterpreter(client=client, model=alias).interpret_initial(
                message
            )
        raw = _build_raw(case["contract"], result)
        provider_model = result.model
        latency_ms = result.latency_ms
        usage = dict(result.usage or {})
    except Exception as exc:
        success = False
        contract_valid = False
        error_type, error_detail = classify_failure(exc)

    checks, score = evaluate_case(
        case, raw, contract_valid=contract_valid
    )
    return CaseEvaluation(
        case_id=case["id"],
        contract=case["contract"],
        category=case["category"],
        model_alias=alias,
        timestamp=timestamp,
        success=success,
        error_type=error_type,
        error_detail=error_detail,
        raw_result=raw,
        contract_valid=contract_valid,
        checks=tuple(checks),
        score=score,
        weight=case["weight"],
        expected_checks_total=len(checks),
        latency_ms=latency_ms,
        usage=usage,
        provider_model=provider_model,
    )


def decision_signature(case: dict[str, Any], raw: dict[str, Any] | None) -> str:
    """Stable signature of the model decision for consistency measurement."""
    if raw is None:
        return "error"
    if case["contract"] == "operational":
        return f"action={raw.get('action')}"
    requests = raw.get("requests") or []
    sectors = [
        ("alumbrado" if resolve_sector_id_safe(r.get("tentative_category")) else "none")
        for r in requests
        if isinstance(r, dict)
    ]
    return f"count={len(requests)} sectors={sectors} clarification={bool(raw.get('clarification_question'))}"


def resolve_sector_id_safe(category: Any) -> str | None:
    try:
        from modules.flow.domain.routing import resolve_sector_id

        return resolve_sector_id(category)
    except Exception:
        return None


def _write_jsonl(path: Path, evaluations: Sequence[CaseEvaluation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for evaluation in evaluations:
            handle.write(json.dumps(evaluation.to_line(), ensure_ascii=False) + "\n")


def _format_report(
    metrics: dict[str, dict[str, Any]],
    order: Sequence[str],
) -> str:
    header = (
        "| Modelo | Score | JSON válido | Corrección | Escalamiento | Datos faltantes | "
        "Errores | Latencia | Tokens | Costo |"
    )
    separator = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    rows = [header, separator]
    for alias in order:
        metric = metrics[alias]
        escalation = metric["escalation"]
        missing = metric["missing_info"]
        latency = metric["latency"]
        tokens = metric["tokens"]
        rows.append(
            f"| {alias} | {metric['score']} | {metric['json_valid_rate']} | "
            f"{metric['score']} | "
            f"{escalation.get('error_rate') if escalation else 'N/A'} "
            f"(FP {escalation.get('fp', 'N/A')}/FN {escalation.get('fn', 'N/A')}) | "
            f"{missing.get('coverage_rate') if missing else 'N/A'} | "
            f"{metric['errors'] or '0'} | "
            f"p50 {latency['p50']}ms/p95 {latency['p95']}ms | "
            f"{tokens['total']} | {metric['cost']} |"
        )
    return "\n".join(rows)


def _write_summary(
    path: Path,
    *,
    metadata: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    failures: list[dict[str, str]],
    nano_vs_luna: dict[str, Any],
    deepseek: dict[str, Any],
    recommendation: dict[str, Any],
    consistency: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "benchmark": BENCHMARK_NAME,
        "timestamp_utc": _iso_now(),
        "metadata": metadata,
        "models": metrics,
        "nano_vs_luna": nano_vs_luna,
        "deepseek": deepseek,
        "consistency": consistency,
        "failures": failures,
        "recommendation": recommendation,
    }
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=BENCHMARK_NAME)
    parser.add_argument(
        "--model",
        action="append",
        choices=MODEL_ALIASES,
        help="Alias LiteLLM a evaluar (repetible). Por defecto: par principal Nano vs Luna.",
    )
    parser.add_argument(
        "--all", action="store_true", help="Evaluar los cuatro aliases registrados."
    )
    parser.add_argument(
        "--consistency",
        type=int,
        default=0,
        metavar="N",
        help="Repetir N veces el subconjunto de consistencia por modelo (default 0).",
    )
    parser.add_argument("--outdir", default=None, help="Directorio de resultados.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validar dataset y plan sin llamar modelos."
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    cases = load_cases()
    intake_cases = [case for case in cases if case["contract"] == "intake"]
    operational_cases = [case for case in cases if case["contract"] == "operational"]
    subset = consistency_subset(cases)

    if args.all:
        selected = list(MODEL_ALIASES)
    elif args.model:
        selected = list(dict.fromkeys(args.model))
    else:
        selected = list(PRIMARY_COMPARISON)

    outdir = Path(args.outdir) if args.outdir else RESULTS_DIR

    if args.dry_run:
        print(f"Dataset OK: {len(intake_cases)} intake, {len(operational_cases)} operational, "
              f"{len(subset)} consistency subset cases.")
        print(f"Models: {', '.join(selected)}")
        print(f"Consistency repeats: {args.consistency}")
        print(f"Estimated real requests: {len(selected) * len(cases) + args.consistency * len(selected) * len(subset)}")
        print("DRY_RUN_OK")
        return 0

    client = LiteLLMClient()
    preflight = {alias: preflight_alias(client, alias) for alias in selected}
    blocked = [alias for alias, result in preflight.items() if result["status"] == "FAIL"]
    if blocked:
        for alias, result in preflight.items():
            print(f"PREFLIGHT {alias}: {result['status']} {result['detail']}")
        if all(result["status"] == "FAIL" for result in preflight.values()):
            print("TEAM360_FLOW_MODEL_EVAL_BLOCKED: all selected aliases failed preflight")
            return 2
        print(f"WARN: skipping blocked aliases {blocked}")
        selected = [alias for alias in selected if alias not in blocked]

    evaluations: list[CaseEvaluation] = []
    failures: list[dict[str, str]] = []
    for alias in selected:
        print(f"\n=== {alias} ===")
        for index, case in enumerate(cases, start=1):
            evaluation = run_case_once(case, alias, client)
            evaluations.append(evaluation)
            status = "OK" if evaluation.success else f"{evaluation.error_type}"
            marker = "!" if not evaluation.success else ""
            print(
                f"  [{index:02d}/{len(cases)}] {case['id']:>18} {case['contract'][:6]:<7} "
                f"score={evaluation.score:.2f} {status} {marker}"
            )
            if not evaluation.success:
                failures.append(
                    {
                        "case_id": case["id"],
                        "model_alias": alias,
                        "type": evaluation.error_type or "MODEL_EVAL_CODE_FAILURE",
                        "description": evaluation.error_detail or "",
                    }
                )

    consistency_report: dict[str, Any] = {"enabled": False}
    if args.consistency > 0 and subset:
        consistency_report = _run_consistency(
            client, selected, subset, cases, args.consistency
        )

    metrics: dict[str, dict[str, Any]] = {}
    for alias in selected:
        alias_evals = [e for e in evaluations if e.model_alias == alias]
        escalation = escalation_from_evaluations(alias_evals, cases)
        metrics[alias] = aggregate_metrics(
            alias, alias_evals, escalation=escalation
        )
        if consistency_report.get("enabled"):
            metrics[alias]["consistency_rate"] = consistency_report.get("models", {}).get(
                alias, {}
            ).get("rate")

    nano_vs_luna, deepseek, recommendation = _build_comparison(metrics, selected)

    metadata = {
        "git": _git_info(),
        "dataset": {
            "intake_cases": len(intake_cases),
            "operational_cases": len(operational_cases),
            "total_cases": len(cases),
            "consistency_subset": len(subset),
            "source": "synthetic",
        },
        "params": {
            "contracts": {"intake": INTAKE_CONTRACT, "operational": OPERATIONAL_CONTRACT},
            "preflight": preflight,
            "consistency_repeats": args.consistency,
        },
        "models_selected": selected,
    }

    _write_jsonl(outdir / "per_case.jsonl", evaluations)
    _write_summary(
        outdir / "summary.json",
        metadata=metadata,
        metrics=metrics,
        failures=failures,
        nano_vs_luna=nano_vs_luna,
        deepseek=deepseek,
        recommendation=recommendation,
        consistency=consistency_report,
    )
    print(
        "\n\n"
        + _format_report(metrics, [a for a in selected if a in metrics])
    )
    print("\nResults written to:", outdir)
    return 0


def _run_consistency(
    client: LiteLLMClient,
    selected: Sequence[str],
    subset: Sequence[dict[str, Any]],
    all_cases: Sequence[dict[str, Any]],
    repeats: int,
) -> dict[str, Any]:
    report: dict[str, Any] = {"enabled": True, "repeats": repeats, "cases": [c["id"] for c in subset]}
    per_model: dict[str, dict[str, Any]] = {}
    for alias in selected:
        signatures: dict[str, list[str]] = {case["id"]: [] for case in subset}
        for _round in range(repeats):
            for case in subset:
                evaluation = run_case_once(case, alias, client)
                signatures[case["id"]].append(
                    decision_signature(case, evaluation.raw_result)
                )
        consistent_cases = 0
        for case_id, signature_list in signatures.items():
            if len(set(signature_list)) <= 1:
                consistent_cases += 1
        rate = consistent_cases / len(subset) if subset else None
        per_model[alias] = {
            "rate": round(rate, 4) if rate is not None else None,
            "consistent_cases": consistent_cases,
            "total_cases": len(subset),
        }
    report["models"] = per_model
    return report


def _build_comparison(
    metrics: dict[str, dict[str, Any]],
    selected: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    nano = metrics.get("openai_gpt-5.4-nano")
    luna = metrics.get("openai_gpt-5.6-luna-medium")
    nano_vs_luna: dict[str, Any] = {"computed": False}
    if nano is not None and luna is not None:
        delta = (luna["score"] or 0.0) - (nano["score"] or 0.0)
        label = magnitude_label(delta)
        nano_esc = nano["escalation"].get("error_rate")
        luna_esc = luna["escalation"].get("error_rate")
        nano_vs_luna = {
            "computed": True,
            "score_nano": nano["score"],
            "score_luna": luna["score"],
            "delta": round(delta, 4),
            "magnitude": label,
            "quality": {
                "nano": nano["score"],
                "luna": luna["score"],
                "delta": round(delta, 4),
            },
            "json_valid": {
                "nano": nano["json_valid_rate"],
                "luna": luna["json_valid_rate"],
            },
            "ambiguity_cases": _subset_metrics(metrics, {"flow_eval_002", "flow_eval_007", "flow_eval_010", "flow_eval_017"}),
            "classification": {
                "nano": nano["classification_accuracy"],
                "luna": luna["classification_accuracy"],
            },
            "escalation": {"nano_error_rate": nano_esc, "luna_error_rate": luna_esc},
            "missing_info": {
                "nano": nano["missing_info"].get("coverage_rate"),
                "luna": luna["missing_info"].get("coverage_rate"),
            },
            "hallucination": {
                "nano": nano["hallucination"].get("violations"),
                "luna": luna["hallucination"].get("violations"),
            },
            "consistency": {
                "nano": nano.get("consistency_rate"),
                "luna": luna.get("consistency_rate"),
            },
            "latency": {"nano_p50": nano["latency"]["p50"], "luna_p50": luna["latency"]["p50"]},
            "tokens": {
                "nano_total": nano["tokens"]["total"],
                "luna_total": luna["tokens"]["total"],
            },
            "cost": "N/A",
        }
    recommendation_alias, recommendation_magnitude = recommend(nano, luna) if nano and luna else ("openai_gpt-5.4-nano", "inexistente")
    deepseek: dict[str, Any] = {"computed": False}
    flash = metrics.get("deepseek_deepseek_4_flash")
    pro = metrics.get("deepseek_deepseek_4_pro")
    if flash is not None and pro is not None:
        deepseek = {
            "computed": True,
            "flash": {key: flash[key] for key in ("score", "score_intake", "score_operational", "json_valid_rate", "classification_accuracy")},
            "pro": {key: pro[key] for key in ("score", "score_intake", "score_operational", "json_valid_rate", "classification_accuracy")},
            "flash_escalation_error_rate": flash["escalation"].get("error_rate"),
            "pro_escalation_error_rate": pro["escalation"].get("error_rate"),
            "flash_latency_p50": flash["latency"]["p50"],
            "pro_latency_p50": pro["latency"]["p50"],
        }
    recommendation = {
        "alias": recommendation_alias,
        "magnitude": recommendation_magnitude,
        "rationale": (
            "Luna only recommended when score delta >= 0.05 (material) with escalation "
            "error rate not worse than Nano. Otherwise Nano stays as the productive baseline."
        ),
    }
    return nano_vs_luna, deepseek, recommendation


def _subset_metrics(
    metrics: dict[str, dict[str, Any]], case_ids: set[str]
) -> dict[str, Any]:
    # Per-case scores for the named cases are in per_case.jsonl; this helper
    # exposes the aggregate proxy (overall scores) for the report.
    return {
        "note": "detailed per-case scores in per_case.jsonl",
        "nano_score": metrics.get("openai_gpt-5.4-nano", {}).get("score"),
        "luna_score": metrics.get("openai_gpt-5.6-luna-medium", {}).get("score"),
    }


if __name__ == "__main__":
    sys.exit(main())

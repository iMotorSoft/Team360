#!/usr/bin/env python3
"""Lab runner for model evaluation in Sales Diagnosis.

This script runs the existing backend evaluator as a subprocess for each
model defined in models.json, captures timing and quality metrics, and
writes sanitized results to JSONL.

It does NOT call models directly -- it relies on the product adapter
endpoint via the backend evaluator script.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVALUATOR_SCRIPT = (
    PROJECT_ROOT
    / "SrvRestAstroLS_v1/backend/scripts/evaluate_sales_diagnosis_headless_responses.py"
)
DEFAULT_MODELS_CONFIG = Path(__file__).resolve().parent.parent / "config/models.json"
DEFAULT_RUN_MATRIX = Path(__file__).resolve().parent.parent / "config/run_matrix.example.json"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

RESULTS_DIR_ENV = "TEAM360_LAB_EVALUATION_RESULTS_DIR"
LAB_RUN_ID_ENV = "TEAM360_LAB_EVALUATION_RUN_ID"

PRODUCT_ROUTE_ENABLED = "TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED"
PRODUCT_STATE_REPOSITORY = "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY"
PRODUCT_LLM_PROVIDER = "TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER"
PRODUCT_RETRIEVAL_PROVIDER = "TEAM360_SALES_DIAGNOSIS_PRODUCT_RETRIEVAL_PROVIDER"
DEV_LLM_PROVIDER = "TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER"

ENV_LITELLM_BASE_URL = "TEAM360_LITELLM_BASE_URL"
ENV_LITELLM_MODEL_ALIAS = "TEAM360_LITELLM_MODEL_ALIAS"


@dataclass
class ModelResult:
    model_id: str
    provider_mode: str
    model: str
    retrieval_mode: str
    state_repository: str
    total_cases: int = 0
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    fallback_count: int = 0
    duration_seconds: float = 0.0
    avg_seconds_per_case: float = 0.0
    notes: str = ""
    run_id: str = ""
    dataset_version: str = ""
    timestamp: str = ""
    litellm_alias: str = ""


def _resolve_project_root() -> Path:
    return PROJECT_ROOT


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_models(path: Path | None) -> list[dict[str, Any]]:
    config_path = path or DEFAULT_MODELS_CONFIG
    data = _load_json(config_path)
    return data["models"]


def _load_run_matrix(path: Path | None) -> dict[str, Any]:
    matrix_path = path or DEFAULT_RUN_MATRIX
    return _load_json(matrix_path)


def _build_evaluator_args(run_matrix: dict[str, Any], endpoint: str) -> list[str]:
    args = [
        sys.executable,
        str(EVALUATOR_SCRIPT),
        "--endpoint",
        endpoint,
        "--timeout",
        str(run_matrix.get("timeout", 45)),
    ]
    dataset_path = run_matrix.get("dataset_path")
    if dataset_path:
        resolved = Path(dataset_path)
        if not resolved.is_absolute():
            resolved = (Path(__file__).resolve().parent.parent / dataset_path).resolve()
        if resolved.exists():
            args.extend(["--dataset", str(resolved)])

    backend_url = run_matrix.get("backend_base_url", "http://127.0.0.1:8018")
    args.extend(["--backend-url", backend_url])

    if run_matrix.get("allow_fallback", False):
        args.append("--allow-fallback")

    return args


def _build_env_for_model(
    model: dict[str, Any],
    run_matrix: dict[str, Any],
    current_env: dict[str, str],
) -> dict[str, str]:
    env = dict(current_env)
    provider_mode = model["provider_mode"]
    endpoint = run_matrix.get("endpoint", "product")

    if endpoint == "product":
        env[PRODUCT_ROUTE_ENABLED] = "1"
        env[PRODUCT_STATE_REPOSITORY] = run_matrix.get("state_repository", "inmemory_test")
        env[PRODUCT_RETRIEVAL_PROVIDER] = run_matrix.get("retrieval_provider", "fake")

        if provider_mode == "openai":
            env[PRODUCT_LLM_PROVIDER] = "openai"
            if "TEAM360_OPENAI_MODEL" not in env:
                env["TEAM360_OPENAI_MODEL"] = model.get("model", "gpt-5-nano")
        elif provider_mode == "litellm":
            env[PRODUCT_LLM_PROVIDER] = "litellm"
            litellm_alias = model.get("litellm_alias", "")
            if litellm_alias:
                env[ENV_LITELLM_MODEL_ALIAS] = litellm_alias
        else:
            env[PRODUCT_LLM_PROVIDER] = provider_mode
    else:
        if provider_mode == "litellm":
            env[DEV_LLM_PROVIDER] = "litellm"
            litellm_alias = model.get("litellm_alias", "")
            if litellm_alias:
                env[ENV_LITELLM_MODEL_ALIAS] = litellm_alias
        else:
            env[DEV_LLM_PROVIDER] = "fake"

    return env


def _parse_evaluator_output(
    output: str,
) -> tuple[int, int, int, int, int]:
    total = 0
    passed = 0
    warned = 0
    failed = 0
    skipped = 0
    fallback_count = 0

    for line in output.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("Results:"):
            # Example: "Results: 18/20 pass, 1 warn, 1 fail, 0 skip"
            parts = line_stripped.split()
            for i, part in enumerate(parts):
                if part == "pass":
                    try:
                        passed = int(parts[i - 1].split("/")[0])
                        total_part = parts[i - 1].split("/")
                        if len(total_part) > 1:
                            total = int(total_part[1])
                        else:
                            total = passed
                    except (ValueError, IndexError):
                        pass
                elif part == "warn":
                    try:
                        warned = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                elif part == "fail":
                    try:
                        failed = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
                elif part == "skip":
                    try:
                        skipped = int(parts[i - 1])
                    except (ValueError, IndexError):
                        pass
        if "fallback" in line_stripped.lower() and "detected" in line_stripped.lower():
            try:
                fallback_count += 1
            except (ValueError, IndexError):
                pass

    if "skip" in output.lower() and "PRINT" not in output:
        if not total:
            total = passed + warned + failed + skipped

    return total, passed, warned, failed, skipped, fallback_count


def _run_evaluator(
    env: dict[str, str],
    args: list[str],
    timeout: float,
) -> tuple[str, float, int]:
    start = time.monotonic()
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout * len(args) * 0.5 + 120,
            env=env,
            cwd=str(_resolve_project_root() / "SrvRestAstroLS_v1/backend"),
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        stderr_text = getattr(exc, "stderr", b"").decode("utf-8", errors="replace") if isinstance(
            getattr(exc, "stderr", b""), bytes
        ) else str(getattr(exc, "stderr", ""))
        return stderr_text, elapsed, -1

    elapsed = time.monotonic() - start
    output = result.stdout + "\n" + result.stderr
    return output, elapsed, result.returncode


def _run_single_model(
    model: dict[str, Any],
    run_matrix: dict[str, Any],
    current_env: dict[str, str],
    evaluator_args: list[str],
    *,
    dry_run: bool,
    no_write_results: bool,
    results_dir: Path,
    run_id: str,
    dataset_version: str,
) -> ModelResult | None:
    model_id = model["id"]
    provider_mode = model["provider_mode"]
    model_name = model.get("model", model.get("litellm_alias", model_id))
    litellm_alias = model.get("litellm_alias", "")
    retrieval_mode = run_matrix.get("retrieval_provider", "fake")
    state_repo = run_matrix.get("state_repository", "inmemory_test")
    endpoint = run_matrix.get("endpoint", "product")

    env = _build_env_for_model(model, run_matrix, current_env)

    if dry_run:
        print(f"[DRY-RUN] Model: {model_id}")
        print(f"  Provider mode: {provider_mode}")
        print(f"  Model: {model_name}")
        print(f"  Endpoint: {endpoint}")
        print(f"  State: {state_repo}")
        print(f"  Retrieval: {retrieval_mode}")
        litellm_info = f" (alias: {litellm_alias})" if litellm_alias else ""
        print(f"  LiteLLM alias: {litellm_alias or 'N/A'}{litellm_info}")
        print(f"  Env overrides:")
        for key in sorted(env.keys()):
            old_val = current_env.get(key, "")
            new_val = env[key]
            if old_val != new_val:
                print(f"    {key}={new_val}")
        print(f"  Command: {' '.join(evaluator_args)}")
        print()
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[EVAL] Running model: {model_id} ...", end=" ", flush=True)

    output, elapsed, returncode = _run_evaluator(env, evaluator_args, run_matrix.get("timeout", 45))

    if returncode == -1:
        result = ModelResult(
            model_id=model_id,
            provider_mode=provider_mode,
            model=model_name,
            retrieval_mode=retrieval_mode,
            state_repository=state_repo,
            total_cases=0,
            pass_count=0,
            warn_count=0,
            fail_count=0,
            skip_count=0,
            fallback_count=0,
            duration_seconds=elapsed,
            avg_seconds_per_case=0.0,
            notes=f"TIMEOUT after {elapsed:.1f}s",
            run_id=run_id,
            dataset_version=dataset_version,
            timestamp=timestamp,
            litellm_alias=litellm_alias,
        )
        print("TIMEOUT")
        return result

    total, passed, warned, failed, skipped, fallback_count = _parse_evaluator_output(output)

    notes_parts: list[str] = []
    if returncode != 0:
        notes_parts.append(f"exit_code={returncode}")
    if "SKIP" in output and "Results:" not in output:
        notes_parts.append("evaluator_skipped")
    if fallback_count > 0:
        notes_parts.append(f"{fallback_count}_fallbacks")
    if total == 0:
        notes_parts.append("no_cases_evaluated")

    avg = elapsed / total if total > 0 else 0.0

    result = ModelResult(
        model_id=model_id,
        provider_mode=provider_mode,
        model=model_name,
        retrieval_mode=retrieval_mode,
        state_repository=state_repo,
        total_cases=total,
        pass_count=passed,
        warn_count=warned,
        fail_count=failed,
        skip_count=skipped,
        fallback_count=fallback_count,
        duration_seconds=elapsed,
        avg_seconds_per_case=round(avg, 2),
        notes="; ".join(notes_parts) if notes_parts else "ok",
        run_id=run_id,
        dataset_version=dataset_version,
        timestamp=timestamp,
        litellm_alias=litellm_alias,
    )

    print(f"done ({elapsed:.1f}s, {total} cases, {passed}/{total} pass)")

    if not no_write_results:
        result_path = results_dir / f"run_{run_id}.jsonl"
        with result_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")
        print(f"  [SAVED] {result_path.name}")

    return result


def _run_models(
    models: list[dict[str, Any]],
    run_matrix: dict[str, Any],
    current_env: dict[str, str],
    *,
    model_filter: set[str] | None,
    dry_run: bool,
    no_write_results: bool,
    results_dir: Path,
    run_id: str,
    dataset_version: str,
) -> list[ModelResult]:
    endpoint = run_matrix.get("endpoint", "product")
    evaluator_args = _build_evaluator_args(run_matrix, endpoint)
    results: list[ModelResult] = []

    for model in models:
        model_id = model["id"]
        if model_filter is not None and model_id not in model_filter:
            continue

        result = _run_single_model(
            model,
            run_matrix,
            current_env,
            evaluator_args,
            dry_run=dry_run,
            no_write_results=no_write_results,
            results_dir=results_dir,
            run_id=run_id,
            dataset_version=dataset_version,
        )
        if result is not None:
            results.append(result)

    return results


def _print_summary(results: list[ModelResult]) -> None:
    if not results:
        print("\nNo results to summarize.")
        return

    print("\n=== Lab Evaluation Summary ===\n")
    print(f"{'Model ID':40s} {'Pass':>5s} {'Warn':>5s} {'Fail':>5s} {'Skip':>5s}  {'Time':>7s} {'Avg/case':>9s} {'Notes'}")
    print("-" * 100)
    for r in results:
        if r.total_cases > 0:
            avg_str = f"{r.avg_seconds_per_case:.1f}s"
        else:
            avg_str = "N/A"
        print(
            f"{r.model_id:40s} {r.pass_count:5d} {r.warn_count:5d} {r.fail_count:5d} "
            f"{r.skip_count:5d}  {r.duration_seconds:6.1f}s {avg_str:>9s}  {r.notes}"
        )
    print()


def _gen_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _list_models(models: list[dict[str, Any]]) -> None:
    print("Available models:")
    print(f"{'ID':45s} {'Mode':12s} {'Model/Label':40s}")
    print("-" * 100)
    for m in models:
        label = m.get("model") or m.get("litellm_alias", "")
        print(f"{m['id']:45s} {m['provider_mode']:12s} {label:40s}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lab runner for Sales Diagnosis model evaluation."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=f"Path to run matrix JSON (default: {DEFAULT_RUN_MATRIX})",
    )
    parser.add_argument(
        "--models-config",
        type=str,
        default=None,
        help=f"Path to models JSON (default: {DEFAULT_MODELS_CONFIG})",
    )
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated list of model IDs to run (default: all from run matrix)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print environment and command for each model without running",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models and exit",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for results JSONL (default: results/run_<timestamp>.jsonl)",
    )
    parser.add_argument(
        "--no-write-results",
        action="store_true",
        help="Skip writing results to disk",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID (default: auto-generated timestamp)",
    )

    args = parser.parse_args()

    models = _load_models(
        Path(args.models_config) if args.models_config else DEFAULT_MODELS_CONFIG
    )

    if args.list_models:
        _list_models(models)
        return

    run_matrix = _load_run_matrix(Path(args.config) if args.config else None)

    if args.models:
        model_filter = {m.strip() for m in args.models.split(",")}
    else:
        model_filter = set(run_matrix.get("models", [m["id"] for m in models]))

    current_env = dict(os.environ)
    run_id = args.run_id or _gen_run_id()
    dataset_version = run_matrix.get("dataset_version", "unknown")
    results_dir_str = os.environ.get(RESULTS_DIR_ENV, str(DEFAULT_RESULTS_DIR))
    results_dir = Path(results_dir_str)
    results_dir.mkdir(parents=True, exist_ok=True)

    results = _run_models(
        models=models,
        run_matrix=run_matrix,
        current_env=current_env,
        model_filter=model_filter,
        dry_run=args.dry_run,
        no_write_results=args.no_write_results,
        results_dir=results_dir,
        run_id=run_id,
        dataset_version=dataset_version,
    )

    if not args.dry_run:
        _print_summary(results)

        if not args.no_write_results:
            summary_path = results_dir / f"summary_{run_id}.json"
            with summary_path.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "run_id": run_id,
                        "dataset_version": dataset_version,
                        "timestamp": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        "results": [r.__dict__ for r in results],
                    },
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
            print(f"Summary saved: {summary_path}")

        failures = [r for r in results if r.fail_count > 0]
        if failures:
            print(f"WARNING: {len(failures)} model(s) had FAIL cases.")
            sys.exit(0)


if __name__ == "__main__":
    main()
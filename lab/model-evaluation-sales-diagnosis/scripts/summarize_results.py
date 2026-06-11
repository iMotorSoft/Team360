#!/usr/bin/env python3
"""Summarize model evaluation results from JSONL or JSON files.

Reads one or more result files (JSONL lines or JSON array/object) and
prints a formatted summary table with PASS/WARN/FAIL/SKIP counts per model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_results(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()

    if raw.strip()[:1] == b"[":
        return json.loads(raw)

    if raw.strip()[:1] == b"{":
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "results" in data:
                    return data["results"]
                return [data]
        except json.JSONDecodeError:
            pass
        # Fall through to JSONL parsing

    lines = [
        json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
    ]
    return lines


def _display_summary(
    results: list[dict[str, Any]],
    *,
    verbose: bool,
) -> None:
    if not results:
        print("No results found.")
        return

    run_ids = sorted({r.get("run_id", "?") for r in results})
    dataset_versions = sorted(
        {r.get("dataset_version", "?") for r in results if r.get("dataset_version")}
    )

    print(f"Total evaluations: {len(results)}")
    if run_ids and run_ids != ["?"]:
        print(f"Run IDs: {', '.join(run_ids)}")
    if dataset_versions:
        print(f"Dataset versions: {', '.join(dataset_versions)}")
    print()

    header = (
        f"{'Model ID':40s} {'Provider':12s} {'Retrieval':10s} "
        f"{'Total':>6s} {'PASS':>5s} {'WARN':>5s} {'FAIL':>5s} "
        f"{'SKIP':>5s} {'Pass%':>7s} {'Fallback':>4s} {'Time':>7s} {'Avg/case':>9s}"
    )
    print(header)
    print("-" * (len(header) + 20))

    for r in sorted(results, key=lambda x: x.get("model_id", "")):
        model_id = r.get("model_id", "?")
        provider = r.get("provider_mode", "?")
        retrieval = r.get("retrieval_mode", "fake")
        total = r.get("total_cases", 0)
        passed = r.get("pass_count", 0)
        warned = r.get("warn_count", 0)
        failed = r.get("fail_count", 0)
        skipped = r.get("skip_count", 0)
        fallbacks = r.get("fallback_count", 0)
        duration = r.get("duration_seconds", 0.0)
        avg = r.get("avg_seconds_per_case", 0.0)
        pass_rate = r.get("pass_rate")
        notes = r.get("notes", "")

        if total and isinstance(total, (int, float)) and total > 0:
            avg_str = f"{avg:.1f}s" if avg else f"{duration / total:.1f}s"
            pass_rate_value = float(pass_rate) if pass_rate is not None else (passed / total) * 100
        else:
            avg_str = "N/A"
            pass_rate_value = 0.0

        print(
            f"{model_id:40s} {provider:12s} {retrieval:10s} "
            f"{int(total):6d} {int(passed):5d} {int(warned):5d} {int(failed):5d} "
            f"{int(skipped):5d} {pass_rate_value:6.1f}% {int(fallbacks):4d} "
            f"{duration:6.1f}s {avg_str:>9s}"
        )

        if notes and notes != "ok":
            print(f"  Notes: {notes}")
        if verbose:
            litellm_alias = r.get("litellm_alias", "")
            if litellm_alias:
                print(f"  LiteLLM alias: {litellm_alias}")
            run_id = r.get("run_id", "")
            if run_id:
                print(f"  Run ID: {run_id}")
            ts = r.get("timestamp", "")
            if ts:
                print(f"  Timestamp: {ts}")
            state_repo = r.get("state_repository", "")
            if state_repo:
                print(f"  State repo: {state_repo}")
            print()

    passed_total = sum(r.get("pass_count", 0) for r in results)
    warned_total = sum(r.get("warn_count", 0) for r in results)
    failed_total = sum(r.get("fail_count", 0) for r in results)
    skipped_total = sum(r.get("skip_count", 0) for r in results)
    fallback_total = sum(r.get("fallback_count", 0) for r in results)
    cases_total = sum(r.get("total_cases", 0) for r in results)

    print()
    print(f"Totals: {cases_total} cases | "
          f"PASS {passed_total} | WARN {warned_total} | "
          f"FAIL {failed_total} | SKIP {skipped_total} | "
          f"Fallback {fallback_total}")


def _build_json_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [r for r in results if r.get("total_cases", 0) > 0]
    fastest = min(evaluated, key=lambda r: r.get("avg_seconds_per_case", 0.0), default=None)
    best_pass_rate = max(
        evaluated,
        key=lambda r: (
            r.get("pass_rate")
            if r.get("pass_rate") is not None
            else (r.get("pass_count", 0) / r.get("total_cases", 1) * 100),
            -r.get("fail_count", 0),
            -r.get("fallback_count", 0),
        ),
        default=None,
    )
    return {
        "total_evaluations": len(results),
        "total_cases": sum(r.get("total_cases", 0) for r in results),
        "total_pass": sum(r.get("pass_count", 0) for r in results),
        "total_warn": sum(r.get("warn_count", 0) for r in results),
        "total_fail": sum(r.get("fail_count", 0) for r in results),
        "total_skip": sum(r.get("skip_count", 0) for r in results),
        "total_fallback": sum(r.get("fallback_count", 0) for r in results),
        "comparison": {
            "fastest_model_id": fastest.get("model_id", "") if fastest else "",
            "best_pass_rate_model_id": best_pass_rate.get("model_id", "") if best_pass_rate else "",
            "models_with_failures": [
                r.get("model_id", "?")
                for r in results
                if r.get("fail_count", 0) > 0 or r.get("quality_status") == "failed"
            ],
            "models_with_fallback": [
                r.get("model_id", "?") for r in results if r.get("fallback_count", 0) > 0
            ],
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize model evaluation results from JSONL/JSON files."
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=str,
        help="One or more result files (JSONL or JSON) to summarize",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show additional metadata per model",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as JSON instead of table",
    )

    args = parser.parse_args()

    all_results: list[dict[str, Any]] = []
    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        try:
            results = _load_results(path)
            all_results.extend(results)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Error reading {file_path}: {exc}", file=sys.stderr)
            sys.exit(1)

    if not all_results:
        print("No results found in provided files.")
        sys.exit(0)

    if args.json:
        json.dump(_build_json_summary(all_results), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        _display_summary(all_results, verbose=args.verbose)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compare embedding model results from the last experiment run.

Reads the most recent JSON results file and prints a comparison table.

Usage:
  python lab/embedding-model-comparison/scripts/compare_results.py
  python lab/embedding-model-comparison/scripts/compare_results.py --latest
  python lab/embedding-model-comparison/scripts/compare_results.py --file results/20260609_mock_embedding-comparison.json
"""

import argparse
import json
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = EXPERIMENT_DIR / "results"


def find_latest_json(directory: Path):
    json_files = sorted(directory.glob("*_embedding-comparison.json"))
    if not json_files:
        print("ERROR: No result files found in", directory)
        sys.exit(1)
    return json_files[-1]


def load_results(filepath: Path):
    with open(filepath) as f:
        return json.load(f)


def print_header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def print_table(rows, headers):
    col_widths = [
        max(len(str(row[i])) for row in rows + [headers])
        for i in range(len(headers))
    ]
    header_line = " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    sep = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    print(f"| {header_line} |")
    print(f"| {sep} |")
    for row in rows:
        line = " | ".join(
            str(row[i]).ljust(col_widths[i]) for i in range(len(headers))
        )
        print(f"| {line} |")


def main():
    parser = argparse.ArgumentParser(description="Compare embedding model results")
    parser.add_argument("--file", type=str, help="Path to specific results JSON file")
    parser.add_argument("--latest", action="store_true", help="Use latest results file")
    args = parser.parse_args()

    if args.file:
        filepath = Path(args.file)
        if not filepath.is_absolute():
            filepath = EXPERIMENT_DIR / filepath
    elif args.latest or True:
        filepath = find_latest_json(RESULTS_DIR)

    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    data = load_results(filepath)
    models = data.get("models", [])

    print_header(f"Experiment: {data['experiment']}")
    print(f"  Timestamp: {data['timestamp']}")
    print(f"  Mode:      {data['mode']}")
    print(f"  Dataset:   {data['dataset']['total_chunks']} chunks, "
          f"{data['dataset']['total_queries']} queries")

    active = [m for m in models if not m.get("skipped") and not m.get("error")]
    skipped_or_error = [m for m in models if m.get("skipped") or m.get("error")]

    print_header("Model metadata")
    rows = []
    for m in models:
        err = (m.get("error") or "—")[:40]
        compat = "✓" if m.get("api_compatible") else "✗"
        actual = m.get("actual_dimensions") or "—"
        requested = m.get("requested_dimensions") or "—"
        rows.append([m["provider"], m["model"], str(requested), str(actual),
                     m.get("encoding_format", "—"), compat, err])
    print_table(rows, ["Provider", "Model", "Req Dims", "Act Dims", "Format", "OK", "Error"])

    if active:
        print_header("Retrieval performance")
        rows = []
        for m in sorted(active, key=lambda x: x["top3_hits"], reverse=True):
            rows.append([m["provider"], m["model"],
                         str(m["top1_hits"]),
                         str(m["top3_hits"]),
                         str(m["top5_hits"]),
                         str(m["total_queries"])])
        print_table(rows, ["Provider", "Model", "Top-1", "Top-3", "Top-5", "Total"])

        print_header("Latency comparison")
        rows = []
        for m in sorted(active, key=lambda x: x.get("latency_ms", {}).get("batch_chunks", 0)):
            chunk_ms = m.get("latency_ms", {}).get("batch_chunks", "—")
            query_ms = m.get("latency_ms", {}).get("batch_queries", "—")
            rows.append([m["provider"], m["model"], str(chunk_ms), str(query_ms)])
        print_table(rows, ["Provider", "Model", "Chunks (ms)", "Queries (ms)"])

    if skipped_or_error:
        print_header("Skipped / Error")
        for m in skipped_or_error:
            print(f"  {m['provider']} / {m['model']}: {m.get('error', 'skipped')}")

    print(f"\nSource: {filepath}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Forensic audit of real guardrail failures in conversation lab results.

Exports:
  - results/guardrail_failure_audit_<timestamp>.md
  - results/guardrail_failure_audit_<timestamp>.json

Usage:
  uv run python scripts/audit_guardrail_failures.py
  uv run python scripts/audit_guardrail_failures.py --results-file results/conversation_lab_<ts>_reevaluated.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"


def find_latest_reevaluated(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("*_reevaluated.json"))
    return json_files[-1] if json_files else None


def audit_failures(report: dict) -> tuple[list[dict], dict]:
    scenarios = report.get("scenarios", [])
    failures: list[dict] = []

    metrics_before: dict[str, Any] = {
        "total_scenarios": len(scenarios),
        "total_turns": 0,
        "real_forbidden_scenarios": 0,
        "real_forbidden_claims_total": 0,
        "planned_ext_misrepresented_scenarios": 0,
        "guardrail_failure_count": 0,
        "passed_scenarios": 0,
        "passed_turns": 0,
        "empty_response_turns": 0,
        "pricing_correctly_declined_total": 0,
        "sla_correctly_declined_total": 0,
        "timeline_correctly_declined_total": 0,
        "planned_ext_correctly_explained_total": 0,
        "useful_orientation_count": 0,
    }

    for s in scenarios:
        se = s.get("refined_scenario_evaluation") or s.get("scenario_evaluation", {})
        case_id = s["case_id"]
        title = s.get("title", "")
        risk = s.get("risk_level", "")

        metrics_before["total_turns"] += se.get("total_turns", 0)
        metrics_before["passed_turns"] += se.get("passed_turns", 0)
        if se.get("passed"):
            metrics_before["passed_scenarios"] += 1
        metrics_before["real_forbidden_claims_total"] += se.get("real_forbidden_claims_total", 0)
        if se.get("real_forbidden_claims_total", 0) > 0:
            metrics_before["real_forbidden_scenarios"] += 1
        if se.get("any_planned_extension_misrepresented", False):
            metrics_before["planned_ext_misrepresented_scenarios"] += 1
        if se.get("real_forbidden_claims_total", 0) > 0 or se.get("any_planned_extension_misrepresented", False):
            metrics_before["guardrail_failure_count"] += 1
        metrics_before["empty_response_turns"] += se.get("empty_response_turns", 0)
        metrics_before["pricing_correctly_declined_total"] += se.get("pricing_correctly_declined_count", 0)
        metrics_before["sla_correctly_declined_total"] += se.get("sla_correctly_declined_count", 0)
        metrics_before["timeline_correctly_declined_total"] += se.get("timeline_correctly_declined_count", 0)
        if se.get("any_planned_extension_correctly_explained", False):
            metrics_before["planned_ext_correctly_explained_total"] += 1
        if se.get("useful_orientation_present", se.get("has_diagnosis_orientation", False)):
            metrics_before["useful_orientation_count"] += 1

        is_guardrail_failure = (
            se.get("real_forbidden_claims_total", 0) > 0
            or se.get("any_planned_extension_misrepresented", False)
        )
        if not is_guardrail_failure:
            continue

        for t in s.get("turns", []):
            turn_num = t.get("turn", 0)
            re = t.get("refined_evaluation") or t.get("evaluation", {})
            user_msg = t.get("user_message", "")
            resp = t.get("response_text", "")

            is_failure_turn = (
                re.get("unsupported_pricing_claim", False)
                or re.get("unsupported_sla_claim", False)
                or re.get("unsupported_timeline_claim", False)
                or re.get("any_misrepresented", False)
                or re.get("response_empty", False)
            )
            if not is_failure_turn:
                continue

            # Determine probable cause
            probable_cause = None
            if re.get("unsupported_pricing_claim", False) or re.get("unsupported_sla_claim", False) or re.get("unsupported_timeline_claim", False):
                # Check if pricing/sla/timeline was used meta-contextually
                if re.get("pricing_correctly_declined", False) or re.get("sla_correctly_declined", False) or re.get("timeline_correctly_declined", False):
                    probable_cause = "mixed_decline_and_real"
                else:
                    # Check if negation exists AFTER the term (forward negation)
                    probable_cause = "evaluator_negation_backward_only"
            if re.get("any_misrepresented", False):
                if re.get("any_correctly_explained", False):
                    probable_cause = "evaluator_plural_not_matching"
                else:
                    probable_cause = "prompt_hardening_needed"

            chunks_info = []
            for c in t.get("retrieval_chunks", [])[:5]:
                chunks_info.append({
                    "rank": c.get("rank"),
                    "title": c.get("title", ""),
                    "content_preview": (c.get("content_preview") or "")[:200],
                })

            failure_entry = {
                "case_id": case_id,
                "title": title,
                "risk_level": risk,
                "turn_index": turn_num,
                "user_message": user_msg,
                "assistant_response": resp,
                "flags": {
                    "unsupported_pricing_claim": re.get("unsupported_pricing_claim", False),
                    "unsupported_sla_claim": re.get("unsupported_sla_claim", False),
                    "unsupported_timeline_claim": re.get("unsupported_timeline_claim", False),
                    "any_misrepresented": re.get("any_misrepresented", False),
                    "response_empty": re.get("response_empty", False),
                },
                "matched_terms": {
                    "forbidden_claim_real": re.get("forbidden_claim_real", []),
                    "forbidden_claim_negated": re.get("forbidden_claim_negated", []),
                    "misrepresented_caps": re.get("misrepresented_caps", []),
                    "correctly_explained_caps": re.get("correctly_explained_caps", []),
                },
                "negation_detected": {
                    "pricing_negated": re.get("pricing_correctly_declined", False) or bool(re.get("forbidden_claim_negated", [])),
                    "sla_negated": re.get("sla_correctly_declined", False),
                    "timeline_negated": re.get("timeline_correctly_declined", False),
                    "planned_extension_correctly_explained": re.get("any_correctly_explained", False),
                },
                "retrieved_chunks": chunks_info,
                "probable_cause": probable_cause,
            }
            failures.append(failure_entry)

    metrics = metrics_before
    metrics["real_guardrail_failure_count"] = len(failures)

    return failures, metrics


def generate_markdown(failures: list[dict], metrics: dict, before_max_turns: int) -> str:
    lines = []
    lines.append("# Fase 1.7c — Guardrail Failure Audit")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Total failures found:** {len(failures)}")
    lines.append(f"**Total scenarios:** {metrics['total_scenarios']}")
    lines.append(f"**Total turns:** {before_max_turns}")
    lines.append("")
    lines.append("## Metrics before fix")
    lines.append("")
    lines.append(f"- Real guardrail failures: {metrics['real_guardrail_failure_count']}")
    lines.append(f"- Real forbidden claims total: {metrics['real_forbidden_claims_total']}")
    lines.append(f"- Real forbidden scenarios: {metrics['real_forbidden_scenarios']}")
    lines.append(f"- Planned ext misrepresented scenarios: {metrics['planned_ext_misrepresented_scenarios']}")
    lines.append(f"- Passed scenarios: {metrics['passed_scenarios']}/{metrics['total_scenarios']} ({round(metrics['passed_scenarios']/metrics['total_scenarios']*100,1) if metrics['total_scenarios'] else 0}%)")
    lines.append(f"- Passed turns: {metrics['passed_turns']}/{metrics['total_turns']} ({round(metrics['passed_turns']/metrics['total_turns']*100,1) if metrics['total_turns'] else 0}%)")
    lines.append(f"- Pricing correctly declined: {metrics['pricing_correctly_declined_total']}")
    lines.append(f"- SLA correctly declined: {metrics['sla_correctly_declined_total']}")
    lines.append(f"- Timeline correctly declined: {metrics['timeline_correctly_declined_total']}")
    lines.append(f"- Planned ext correctly explained scenarios: {metrics['planned_ext_correctly_explained_total']}")
    lines.append(f"- Empty response turns: {metrics['empty_response_turns']}")
    lines.append(f"- Useful orientation scenarios: {metrics['useful_orientation_count']}/{metrics['total_scenarios']}")
    lines.append("")
    lines.append("## Failure Details")
    lines.append("")

    for f in failures:
        lines.append(f"### {f['case_id']} — Turn {f['turn_index']}")
        lines.append(f"**Risk:** {f['risk_level']}")
        lines.append(f"**Probable cause:** {f['probable_cause']}")
        lines.append("")
        lines.append(f"**User:** {f['user_message'][:200]}")
        lines.append("")
        lines.append(f"**Assistant:**")
        lines.append("```")
        lines.append(f["assistant_response"][:600])
        lines.append("```")
        lines.append("")
        lines.append("**Triggered flags:**")
        for flag, val in f["flags"].items():
            if val:
                lines.append(f"- ⚠️ {flag}")
        lines.append("")
        lines.append("**Matched terms:**")
        for k, v in f["matched_terms"].items():
            if v:
                lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("**Negation detected:**")
        for k, v in f["negation_detected"].items():
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("**Retrieved chunks (first 3):**")
        for c in f["retrieved_chunks"][:3]:
            lines.append(f"- Rank {c['rank']}: {c['title']}")
            lines.append(f"  `{c['content_preview'][:120]}`")
        lines.append("")

    lines.append("## Probable Cause Classification")
    lines.append("")
    causes: dict[str, int] = {}
    for f in failures:
        c = f["probable_cause"]
        causes[c] = causes.get(c, 0) + 1
    for cause, count in sorted(causes.items(), key=lambda x: -x[1]):
        lines.append(f"- **{cause}**: {count} failure(s)")
    lines.append("")
    lines.append("### Cause definitions")
    lines.append("")
    causes_def = {
        "evaluator_plural_not_matching": "Planned extension correct markers use singular forms (está/listo/disponible) but the assistant uses plural (están/listos/disponibles). Also 'no disponible' vs 'no están disponibles'.",
        "evaluator_negation_backward_only": "Negation detection looks backward from the forbidden term, but the assistant often states the user's question first (containing 'precio') then negates it afterward.",
        "mixed_decline_and_real": "Response both correctly declines and asserts unsupported claims in different parts.",
        "prompt_hardening_needed": "The model genuinely presents a planned extension capability as available/sellable today.",
    }
    for cause in sorted(causes.keys()):
        if cause in causes_def:
            lines.append(f"- **{cause}**: {causes_def[cause]}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit real guardrail failures in conversation lab results")
    parser.add_argument("--results-file", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    results_path: Path | None = None
    if args.results_file:
        p = Path(args.results_file)
        results_path = p if p.is_absolute() else RESULTS_DIR / args.results_file
    else:
        results_path = find_latest_reevaluated(RESULTS_DIR)

    if not results_path or not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    with open(results_path, encoding="utf-8") as f:
        report = json.load(f)

    failures, metrics = audit_failures(report)

    total_turns = report.get("refined_summary", {}).get("total_turns", 0)

    md = generate_markdown(failures, metrics, total_turns)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"guardrail_failure_audit_{ts}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    json_path = output_dir / f"guardrail_failure_audit_{ts}.json"
    audit_data = {
        "timestamp": ts,
        "failures": failures,
        "metrics_before": metrics,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)

    print(f"Audit saved: {md_path}")
    print(f"Audit data: {json_path}")
    print(f"  Failures found: {len(failures)}")
    for f in failures:
        print(f"  - {f['case_id']} turn {f['turn_index']}: {f['probable_cause']}")


if __name__ == "__main__":
    main()

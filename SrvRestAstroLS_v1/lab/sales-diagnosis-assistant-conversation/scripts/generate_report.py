#!/usr/bin/env python3
"""Generate detailed Markdown report from conversation lab results.

Usage:
  uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_report.py
  uv run python lab/sales-diagnosis-assistant-conversation/scripts/generate_report.py --results-file results/conversation_lab_20260610_120000.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"


def find_latest_result(directory: Path) -> Path | None:
    json_files = sorted(directory.glob("conversation_lab_*.json"))
    return json_files[-1] if json_files else None


def _get_eval(turn: dict) -> dict:
    """Return refined_evaluation if available, fall back to original evaluation."""
    return turn.get("refined_evaluation") or turn.get("evaluation", {})


def _get_scenario_eval(scenario: dict) -> dict:
    """Return refined_scenario_evaluation if available, fall back to scenario_evaluation."""
    return scenario.get("refined_scenario_evaluation") or scenario.get("scenario_evaluation", {})


def generate_detailed_report(report: dict) -> str:
    summary = report.get("refined_summary") or report["summary"]
    scenarios = report["scenarios"]
    latencies = report.get("latencies_ms", {})
    has_refined = "refined_summary" in report

    lines = []
    lines.append("# Sales Diagnosis Assistant Conversation Lab — Reporte detallado")
    lines.append("")
    title = "Fase 1.7b (evaluación refinada)" if has_refined else "Fase 1.7"
    lines.append(f"**Experimento:** {title}")
    lines.append(f"**Modelo:** {summary.get('model', summary.get('experiment', '?'))}")
    lines.append("")
    if has_refined:
        lines.append("> ℹ️ Este reporte usa la evaluación refinada (Fase 1.7b): detección con word boundaries, negación contextual, clasificación correct_decline vs hallucination, y planned-extension tracking detallado.")
        lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- **Scenario pass rate:** {summary['passed_scenarios']}/{summary['total_scenarios']} ({summary['scenario_pass_rate']}%)")
    lines.append(f"- **Turn pass rate:** {summary['passed_turns']}/{summary['total_turns']} ({summary['turn_pass_rate']}%)")
    if summary.get('high_risk_total', 0) > 0:
        lines.append(f"- **High-risk:** {summary['high_risk_passed']}/{summary['high_risk_total']} ({summary['high_risk_pass_rate']}%)")
    if summary.get('avg_retrieval_latency_ms'):
        lines.append(f"- **Avg retrieval lat:** {summary['avg_retrieval_latency_ms']}ms")
    if summary.get('avg_llm_latency_ms'):
        lines.append(f"- **Avg LLM lat:** {summary['avg_llm_latency_ms']}ms")
    if summary.get('avg_total_latency_ms'):
        lines.append(f"- **Avg total lat per turn:** {summary['avg_total_latency_ms']}ms")
    if summary.get('avg_questions_per_turn'):
        lines.append(f"- **Avg questions per turn:** {summary['avg_questions_per_turn']}")
    if summary.get('forbidden_claims_total'):
        lines.append(f"- **Forbidden claims:** {summary['forbidden_claims_total']}")
    if summary.get('real_forbidden_claims_total') is not None:
        lines.append(f"- **Real forbidden claims (refined):** {summary['real_forbidden_claims_total']}")
    if summary.get('guardrail_failure_count') is not None:
        lines.append(f"- **Guardrail failures:** {summary['guardrail_failure_count']}")
    if summary.get('useful_orientation_rate') is not None:
        lines.append(f"- **Useful orientation rate:** {summary['useful_orientation_rate']}%")
    lines.append("")
    lines.append(f"**Decisión:** {summary['architecture_recommendation']}")
    lines.append("")

    lines.append("## Resultados por escenario")
    lines.append("")
    if has_refined:
        lines.append("| case_id | title | risk | turns | passed | scenario_ref | real_forbidden | correctly_declined | slots | caps_correct | caps_misrep |")
        lines.append("|---------|-------|------|-------|--------|-------------|----------------|-------------------|-------|-------------|-------------|")
        for s in scenarios:
            se = _get_scenario_eval(s)
            scenario_pass = "PASS" if se.get("passed") else "FAIL"
            pricing_dec = se.get("pricing_correctly_declined_count", 0)
            sla_dec = se.get("sla_correctly_declined_count", 0)
            timeline_dec = se.get("timeline_correctly_declined_count", 0)
            decl_str = f"P{pricing_dec}/S{sla_dec}/T{timeline_dec}" if (pricing_dec or sla_dec or timeline_dec) else "-"
            caps_correct = ",".join(se.get("correctly_explained_caps", []))[:20] or "-"
            caps_misrep = ",".join(se.get("misrepresented_caps", []))[:20] or "-"
            lines.append(f"| {s['case_id']} | {s.get('title','')[:30]} | {s.get('risk_level','')} | "
                         f"{se.get('total_turns',0)} | {se.get('passed_turns',0)}/{se.get('total_turns',0)} | {scenario_pass} | "
                         f"{se.get('real_forbidden_claims_total',0)} | {decl_str} | "
                         f"{se.get('slots_filled',0)}/{len(se.get('expected_slots',[]))} | {caps_correct} | {caps_misrep} |")
    else:
        lines.append("| case_id | title | risk | turns | passed_turns | scenario | forbidden | slots | questions |")
        lines.append("|---------|-------|------|-------|-------------|----------|----------|-------|-----------|")
        for s in scenarios:
            se = s.get("scenario_evaluation", {})
            scenario_pass = "PASS" if se.get("passed") else "FAIL"
            lines.append(f"| {s['case_id']} | {s.get('title','')[:30]} | {s.get('risk_level','')} | "
                         f"{se.get('total_turns',0)} | {se.get('passed_turns',0)} | {scenario_pass} | "
                         f"{se.get('total_forbidden_claims',0)} | {se.get('slots_filled',0)}/{len(se.get('expected_slots',[]))} | "
                         f"{se.get('total_questions',0)} |")
    lines.append("")

    lines.append("## Latencia")
    lines.append("")
    if latencies:
        for measure, values in latencies.items():
            if values:
                lines.append(f"- **{measure}:** min={min(values):.0f}ms max={max(values):.0f}ms avg={sum(values)/len(values):.0f}ms")
    lines.append("")

    lines.append("## Detalle de escenarios fallidos")
    lines.append("")
    failed = [s for s in scenarios if not _get_scenario_eval(s).get("passed", False)]
    if not failed:
        lines.append("- No hay escenarios fallidos.")
    else:
        for s in failed:
            se = _get_scenario_eval(s)
            lines.append(f"### `{s['case_id']}` — {s.get('title', '')}")
            lines.append(f"- **Risk:** {s.get('risk_level', '')}")
            lines.append(f"- **Turns:** {se.get('passed_turns', 0)}/{se.get('total_turns', 0)} passed")
            lines.append(f"- **Real forbidden claims:** {se.get('real_forbidden_claims_total', 0)}")
            lines.append(f"- **Pricing correctly declined:** {se.get('pricing_correctly_declined_count', 0)}")
            lines.append(f"- **SLA correctly declined:** {se.get('sla_correctly_declined_count', 0)}")
            lines.append(f"- **Timeline correctly declined:** {se.get('timeline_correctly_declined_count', 0)}")
            lines.append(f"- **Slots:** {se.get('slots_filled', 0)}/{len(se.get('expected_slots', []))} (detected: {se.get('detected_slots', [])})")
            lines.append(f"- **Planned ext correct:** {se.get('correctly_explained_caps', [])}")
            lines.append(f"- **Planned ext misrep:** {se.get('misrepresented_caps', [])}")
            lines.append(f"- **Has diagnosis orientation:** {se.get('useful_orientation_present', se.get('has_diagnosis_orientation', False))}")
            if se.get("empty_response_turns", 0) > 0:
                lines.append(f"- **Empty response turns:** {se['empty_response_turns']}")
            lines.append("")
            for turn in s.get("turns", []):
                ev = _get_eval(turn)
                resp = turn.get("response_text", "")
                turn_pass = "PASS" if ev.get("passed") else "FAIL"
                ft = ev.get("failure_type", "")
                ft_suffix = f" [{ft}]" if ft else ""
                lines.append(f"**Turn {turn.get('turn', '?')}:** {turn_pass}{ft_suffix}")
                lines.append(f"- User: {turn.get('user_message', '')[:80]}")
                if resp and not resp.startswith("(LLM error") and not resp.startswith("(no-llm"):
                    lines.append(f"- Assistant: {resp[:200]}")
                if ev.get("response_empty"):
                    lines.append(f"- ⚠️ Empty response")
                if ev.get("too_many_questions"):
                    lines.append(f"- ⚠️ Too many questions: {ev.get('question_count', 0)}")
                if ev.get("unsupported_pricing_claim"):
                    lines.append(f"- ⚠️ Unsupported pricing claim: {ev.get('forbidden_claim_real', [])}")
                if ev.get("pricing_correctly_declined"):
                    lines.append(f"- ✅ Pricing correctly declined: {ev.get('forbidden_claim_negated', [])}")
                if ev.get("unsupported_sla_claim"):
                    lines.append(f"- ⚠️ Unsupported SLA claim: real terms present without negation")
                if ev.get("sla_correctly_declined"):
                    lines.append(f"- ✅ SLA correctly declined")
                if ev.get("unsupported_timeline_claim"):
                    lines.append(f"- ⚠️ Unsupported timeline claim")
                if ev.get("timeline_correctly_declined"):
                    lines.append(f"- ✅ Timeline correctly declined")
                if ev.get("any_misrepresented"):
                    lines.append(f"- ⚠️ Planned extension misrepresented: {ev.get('misrepresented_caps', [])}")
                if ev.get("any_correctly_explained"):
                    lines.append(f"- ✅ Planned extension correctly explained: {ev.get('correctly_explained_caps', [])}")
                if ev.get("says_not_documented_when_missing"):
                    lines.append(f"- ✅ Says not documented when missing context")
                if ev.get("invents_undocumented_detail"):
                    lines.append(f"- ⚠️ Invents undocumented detail")
                lines.append("")

    lines.append("## Taxonomía de evaluación refinada")
    lines.append("")
    lines.append("| Categoría | Descripción |")
    lines.append("|-----------|-------------|")
    lines.append("| `empty_response` | Respuesta vacía (sin procesar por LLM) |")
    lines.append("| `response_too_long` | Respuesta excede 2000 caracteres |")
    lines.append("| `too_many_questions` | Más de 3 preguntas en un turno |")
    lines.append("| `unsupported_pricing_claim` | El modelo genera precio/costo/ARS/USD sin negación |")
    lines.append("| `pricing_correctly_declined` | El modelo menciona precio pero lo declina explícitamente |")
    lines.append("| `unsupported_sla_claim` | El modelo menciona SLA sin negación |")
    lines.append("| `sla_correctly_declined` | El modelo menciona SLA pero lo declina |")
    lines.append("| `unsupported_timeline_claim` | El modelo da plazos no documentados |")
    lines.append("| `timeline_correctly_declined` | El modelo menciona plazos pero los declina |")
    lines.append("| `planned_extension_correct` | El modelo explica que una capacidad es extensión planificada |")
    lines.append("| `planned_extension_misrep` | El modelo vende como lista una capacidad planned_extension |")
    lines.append("| `no_orientation` | La respuesta no orienta ni diagnostica |")
    lines.append("| `says_not_documented` | El modelo reconoce falta de información documentada |")
    lines.append("| `invents_detail` | El modelo inventa detalles no documentados |")
    lines.append("")

    lines.append("## Decisiones")
    lines.append("")
    lines.append(f"**{summary['architecture_recommendation']}**")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by Sales Diagnosis Assistant Conversation Lab. "
                 "PostgreSQL source of truth, Milvus vector runtime. "
                 "No ArangoDB, no cross-encoder, no production changes, "
                 "no Step-to-Action, no lead capture, no diagnostic_code, no WhatsApp handoff._")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate detailed report from conversation lab results")
    parser.add_argument("--results-file", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    results_path: Path | None = None
    if args.results_file:
        results_path = RESULTS_DIR / args.results_file if not Path(args.results_file).is_absolute() else Path(args.results_file)
    else:
        latest = find_latest_result(RESULTS_DIR)
        if latest:
            results_path = latest

    if not results_path or not results_path.exists():
        print(f"ERROR: Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    with open(results_path, encoding="utf-8") as f:
        report = json.load(f)

    detailed = generate_detailed_report(report)
    has_refined = "refined_summary" in report

    output_path: Path
    if args.output:
        output_path = Path(args.output)
    else:
        stem = results_path.stem.replace(".json", "")
        suffix = "_refined_report.md" if has_refined else "_detailed_report.md"
        output_path = RESULTS_DIR / f"{stem}{suffix}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(detailed)

    s = report.get("refined_summary") or report["summary"]
    label = "Refined report" if has_refined else "Report"
    print(f"{label} saved: {output_path}")
    print(f"  {s['total_scenarios']} scenarios, scenario pass rate: {s['scenario_pass_rate']}%, "
          f"high-risk: {s.get('high_risk_pass_rate', 0)}%")
    print(f"  Recommendation: {s['architecture_recommendation'][:80]}...")


if __name__ == "__main__":
    main()

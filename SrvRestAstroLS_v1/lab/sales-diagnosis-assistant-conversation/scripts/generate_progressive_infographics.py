#!/usr/bin/env python3
"""Generate infographics for Fase 1.7d Progressive Response Simulation.

Usage:
  uv run python scripts/generate_progressive_infographics.py
  uv run python scripts/generate_progressive_infographics.py --results results/progressive_response_20260610_*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = LAB_DIR / "results"
INFOGRAPHICS_DIR = LAB_DIR / "infografias"


def load_latest_results() -> dict | None:
    json_files = sorted(RESULTS_DIR.glob("progressive_response_*.json"))
    if not json_files:
        return None
    latest = json_files[-1]
    with open(latest, encoding="utf-8") as f:
        return json.load(f), latest.name


def generate_infographics(data: dict) -> str:
    summary = data.get("summary", {})
    scenarios = data.get("scenarios", [])
    latencies = data.get("latencies_ms", {})
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    time_to_quick = latencies.get("time_to_quick_answer", [])
    time_to_final = latencies.get("time_to_final_answer", [])
    totals = latencies.get("total", [])
    retrievals = latencies.get("retrieval", [])

    def pct(lst, p):
        s = sorted(lst)
        if not s:
            return 0
        idx = min(int(len(s) * p / 100), len(s) - 1)
        return s[idx]

    p50_q = pct(time_to_quick, 50) if time_to_quick else 0
    p95_q = pct(time_to_quick, 95) if time_to_quick else 0
    p50_f = pct(time_to_final, 50) if time_to_final else 0
    p95_f = pct(time_to_final, 95) if time_to_final else 0
    p50_t = pct(totals, 50) if totals else 0
    p95_t = pct(totals, 95) if totals else 0

    scenario_pass_data = ""
    for s in scenarios:
        cid = s["case_id"]
        turns = s.get("turns", [])
        passed = sum(1 for t in turns if t.get("evaluation", {}).get("combined_pass", False))
        total = len(turns)
        bar = "█" * passed + "░" * (total - passed)
        scenario_pass_data += f"        <tr><td>{cid}</td><td>{passed}/{total}</td><td><span class='bar'>{bar}</span></td></tr>\n"

    quick_pass_data = ""
    for s in scenarios:
        cid = s["case_id"]
        turns = s.get("turns", [])
        for t in turns:
            tnum = t.get("turn", "?")
            ev = t.get("evaluation", {}).get("quick_answer", {})
            passed = ev.get("passed", False)
            color = "pass" if passed else "fail"
            quick_pass_data += f"        <tr><td>{cid}</td><td>Turn {tnum}</td><td class='{color}'>{'PASS' if passed else 'FAIL'}</td></tr>\n"

    final_pass_data = ""
    for s in scenarios:
        cid = s["case_id"]
        turns = s.get("turns", [])
        for t in turns:
            tnum = t.get("turn", "?")
            ev = t.get("evaluation", {}).get("final_answer", {})
            passed = ev.get("passed", False)
            color = "pass" if passed else "fail"
            final_pass_data += f"        <tr><td>{cid}</td><td>Turn {tnum}</td><td class='{color}'>{'PASS' if passed else 'FAIL'}</td></tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fase 1.7d — Progressive Response Simulation</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; }}
  h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 8px; }}
  h2 {{ color: #16213e; margin-top: 32px; }}
  .summary {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin: 16px 0; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }}
  .metric {{ background: #f8f9fa; border-radius: 8px; padding: 12px 16px; border-left: 4px solid #0f3460; }}
  .metric .value {{ font-size: 24px; font-weight: 700; color: #0f3460; }}
  .metric .label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric.good {{ border-left-color: #2ecc71; }}
  .metric.warn {{ border-left-color: #f39c12; }}
  .metric.bad {{ border-left-color: #e74c3c; }}
  .metric.neutral {{ border-left-color: #3498db; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); margin: 12px 0; }}
  th {{ background: #16213e; color: white; padding: 10px 12px; text-align: left; font-size: 13px; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 13px; }}
  tr:hover td {{ background: #f0f4ff; }}
  .bar {{ font-size: 14px; letter-spacing: 1px; }}
  .pass {{ color: #2ecc71; font-weight: 700; }}
  .fail {{ color: #e74c3c; font-weight: 700; }}
  .footer {{ margin-top: 48px; text-align: center; color: #999; font-size: 11px; border-top: 1px solid #ddd; padding-top: 16px; }}
</style>
</head>
<body>
<h1>Fase 1.7d — Progressive Response Simulation</h1>
<p><strong>Strategy:</strong> {summary.get('strategy', 'N/A')} | <strong>Model:</strong> {summary.get('model', 'N/A')} | <strong>Date:</strong> {now_str}</p>
<p><em>No production endpoints. No real SSE. No frontend. No ArangoDB. No cross-encoder.</em></p>

<div class="summary">
  <h2>Latencia percibida</h2>
  <div class="metric-grid">
    <div class="metric neutral"><div class="value">{summary.get('avg_time_to_quick_answer_ms', 'N/A')}ms</div><div class="label">Avg Time to Quick Answer</div></div>
    <div class="metric neutral"><div class="value">{summary.get('avg_time_to_final_answer_ms', 'N/A')}ms</div><div class="label">Avg Time to Final Answer</div></div>
    <div class="metric neutral"><div class="value">{summary.get('avg_total_time_ms', 'N/A')}ms</div><div class="label">Avg Total per Turn</div></div>
    <div class="metric neutral"><div class="value">{summary.get('avg_retrieval_latency_ms', 'N/A')}ms</div><div class="label">Avg Retrieval Latency</div></div>
    <div class="metric neutral"><div class="value">{p50_q}ms</div><div class="label">P50 Quick Answer</div></div>
    <div class="metric neutral"><div class="value">{p95_q}ms</div><div class="label">P95 Quick Answer</div></div>
    <div class="metric neutral"><div class="value">{p50_f}ms</div><div class="label">P50 Final Answer</div></div>
    <div class="metric neutral"><div class="value">{p95_f}ms</div><div class="label">P95 Final Answer</div></div>
    <div class="metric neutral"><div class="value">{p50_t}ms</div><div class="label">P50 Total</div></div>
    <div class="metric neutral"><div class="value">{p95_t}ms</div><div class="label">P95 Total</div></div>
  </div>
</div>

<div class="summary">
  <h2>Calidad y seguridad</h2>
  <div class="metric-grid">
    <div class="metric {'good' if summary.get('quick_answer_safe_rate', 0) >= 95 else 'warn'}"><div class="value">{summary.get('quick_answer_safe_rate', 'N/A')}%</div><div class="label">Quick Answer Safe Rate</div></div>
    <div class="metric {'good' if summary.get('final_answer_pass_rate', 0) >= 70 else 'warn'}"><div class="value">{summary.get('final_answer_pass_rate', 'N/A')}%</div><div class="label">Final Answer Pass Rate</div></div>
    <div class="metric {'good' if summary.get('combined_pass_rate', 0) >= 70 else 'warn'}"><div class="value">{summary.get('combined_pass_rate', 'N/A')}%</div><div class="label">Combined Pass Rate</div></div>
    <div class="metric {'good' if summary.get('final_guardrail_failure_count', 0) == 0 else 'bad'}"><div class="value">{summary.get('final_guardrail_failure_count', 'N/A')}</div><div class="label">Guardrail Failures</div></div>
  </div>
</div>

<div class="summary">
  <h2>Per-Scenario Combined Pass Rate</h2>
  <table>
    <tr><th>Scenario</th><th>Passed/Turns</th><th>Bar</th></tr>
{scenario_pass_data}  </table>
</div>

<div class="summary">
  <h2>Quick Answer Safety per Turn</h2>
  <table>
    <tr><th>Scenario</th><th>Turn</th><th>Quick Answer</th></tr>
{quick_pass_data}  </table>
</div>

<div class="summary">
  <h2>Final Answer Pass per Turn</h2>
  <table>
    <tr><th>Scenario</th><th>Turn</th><th>Final Answer</th></tr>
{final_pass_data}  </table>
</div>

<div class="footer">
  <p>Fase 1.7d — Progressive Response Simulation Lab | Team360</p>
  <p>Generated: {now_str}</p>
</div>
</body>
</html>"""

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate progressive response infographics")
    parser.add_argument("--results", type=str, default=None, help="Path to specific results JSON")
    parser.add_argument("--output", type=str, default=None, help="Output HTML path")
    args = parser.parse_args()

    if args.results:
        path = Path(args.results)
        if not path.exists():
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        prefix = path.stem.replace("progressive_response_", "")
    else:
        result = load_latest_results()
        if result is None:
            print("ERROR: No progressive_response_*.json files found in results/", file=sys.stderr)
            sys.exit(1)
        data, filename = result
        prefix = filename.replace("progressive_response_", "").replace(".json", "")

    html = generate_infographics(data)

    INFOGRAPHICS_DIR.mkdir(parents=True, exist_ok=True)
    html_filename = f"progressive_response_{prefix}_infografia.html"
    html_path = INFOGRAPHICS_DIR / html_filename
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Infographics saved: {html_path}")


if __name__ == "__main__":
    main()

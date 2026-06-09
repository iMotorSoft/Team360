#!/usr/bin/env python3
"""Generate HTML infographic from embedding comparison results.

Usage:
  python lab/embedding-model-comparison/scripts/generate_infographics.py
  python lab/embedding-model-comparison/scripts/generate_infographics.py --file results/20260609_mock_embedding-comparison.json
"""

import argparse
import json
import sys
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
INFOGRAPHICS_DIR = EXPERIMENT_DIR / "infografias"


def find_latest_json(directory: Path):
    json_files = sorted(directory.glob("*_embedding-comparison.json"))
    if not json_files:
        print("ERROR: No result files found in", directory)
        sys.exit(1)
    return json_files[-1]


def load_results(filepath: Path):
    with open(filepath) as f:
        return json.load(f)


def html_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_html(data):
    models = data.get("models", [])
    active = [m for m in models if not m.get("skipped") and not m.get("error")]
    mode = data["mode"]
    timestamp = data["timestamp"]

    model_bars = ""
    for i, m in enumerate(active):
        t3 = m["top3_hits"]
        total = m["total_queries"]
        pct = round(t3 / total * 100) if total else 0
        color = "#22c55e" if pct >= 70 else ("#eab308" if pct >= 40 else "#ef4444")
        model_bars += f"""
        <div style="margin-bottom:1.5rem">
          <div style="display:flex;justify-content:space-between;margin-bottom:0.25rem">
            <span><strong>{html_escape(m['provider'])}</strong> / {html_escape(m['model'])}</span>
            <span>{t3}/{total} ({pct}%)</span>
          </div>
          <div style="background:#e5e7eb;border-radius:8px;overflow:hidden;height:24px">
            <div style="width:{pct}%;background:{color};height:100%;border-radius:8px;display:flex;align-items:center;justify-content:center;color:white;font-weight:bold;font-size:0.8rem">
              {pct}%
            </div>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Embedding Model Comparison - Team360</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; background: #f8fafc; color: #1e293b; }}
  h1 {{ color: #0f172a; border-bottom: 3px solid #3b82f6; padding-bottom: 0.5rem; }}
  h2 {{ color: #334155; margin-top: 2rem; }}
  .card {{ background: white; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 1.5rem; }}
  .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }}
  .mock-badge {{ background: #fef3c7; color: #92400e; }}
  .real-badge {{ background: #dbeafe; color: #1e40af; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
  th {{ background: #f1f5f9; font-weight: 600; }}
  .ok {{ color: #16a34a; }}
  .err {{ color: #dc2626; }}
  .skip {{ color: #ca8a04; }}
  footer {{ margin-top: 3rem; text-align: center; color: #94a3b8; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>🧪 Embedding Model Comparison</h1>
<div style="margin-bottom:1rem">
  <span class="badge {'mock-badge' if mode == 'mock' else 'real-badge'}">{mode.upper()}</span>
  <span style="color:#64748b;margin-left:0.5rem">{timestamp}</span>
</div>

<div class="card">
  <h2>Top-3 Retrieval Rate</h2>
  {model_bars}
</div>

<div class="card">
  <h2>Model Details</h2>
  <table>
    <tr>
      <th>Provider</th>
      <th>Model</th>
      <th>Requested Dims</th>
      <th>Actual Dims</th>
      <th>Format</th>
      <th>Status</th>
    </tr>
    {''.join(f'''<tr>
      <td>{html_escape(m['provider'])}</td>
      <td>{html_escape(m['model'])}</td>
      <td>{html_escape(m.get('requested_dimensions') or '—')}</td>
      <td>{html_escape(m.get('actual_dimensions') or '—')}</td>
      <td>{html_escape(m.get('encoding_format') or '—')}</td>
      <td class="{'ok' if not m.get('error') and not m.get('skipped') else 'err' if m.get('error') else 'skip'}">
        {html_escape(m.get('error') or ('✓' if not m.get('skipped') else '⏭'))}
      </td>
    </tr>''' for m in models)}
  </table>
</div>

<div class="card">
  <h2>Latency</h2>
  <table>
    <tr>
      <th>Provider</th>
      <th>Model</th>
      <th>Chunks (ms)</th>
      <th>Queries (ms)</th>
    </tr>
    {''.join(f'''<tr>
      <td>{html_escape(m['provider'])}</td>
      <td>{html_escape(m['model'])}</td>
      <td>{html_escape(m.get('latency_ms', {}).get('batch_chunks', '—'))}</td>
      <td>{html_escape(m.get('latency_ms', {}).get('batch_queries', '—'))}</td>
    </tr>''' for m in active)}
  </table>
</div>

<footer>
  Team360 · lab/embedding-model-comparison · Generated {timestamp}
</footer>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate HTML infographic from results")
    parser.add_argument("--file", type=str, help="Path to specific results JSON file")
    parser.add_argument("--output", type=str, help="Output HTML path (default: infografias/index.html)")
    args = parser.parse_args()

    if args.file:
        filepath = Path(args.file)
        if not filepath.is_absolute():
            filepath = EXPERIMENT_DIR / filepath
    else:
        filepath = find_latest_json(RESULTS_DIR)

    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    data = load_results(filepath)
    html = build_html(data)

    INFOGRAPHICS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) if args.output else INFOGRAPHICS_DIR / "index.html"
    if not out_path.is_absolute():
        out_path = EXPERIMENT_DIR / out_path

    with open(out_path, "w") as f:
        f.write(html)

    print(f"Infographic saved: {out_path}")


if __name__ == "__main__":
    main()

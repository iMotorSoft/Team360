#!/usr/bin/env python3
"""Generate RAG failure case inventory from rag_audit_failure_cases.json.

No APIs, no DB, no retrieval — purely static analysis of the golden cases.
Output: results/rag_failure_case_inventory.md

Usage:
  uv run python lab/postgres-knowledge-retrieval-breaking-points/scripts/generate_failure_case_report.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]
GOLDEN_FILE = LAB_DIR / "golden_cases" / "rag_audit_failure_cases.json"
RESULTS_DIR = LAB_DIR / "results"


def main() -> None:
    if not GOLDEN_FILE.exists():
        print(f"ERROR: Golden file not found: {GOLDEN_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(GOLDEN_FILE, encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    meta = data.get("meta", {})

    cat_counts: Counter = Counter()
    risk_counts: Counter = Counter()
    milvus = 0
    arangodb = 0
    reranker = 0
    hybrid = 0
    content_patch = 0
    arch_implications: Counter = Counter()
    risk_by_cat: dict[str, Counter] = {}
    reranker_by_cat: Counter = Counter()
    content_patch_by_cat: Counter = Counter()

    for c in cases:
        cat = c["failure_category"]
        risk = c["risk_level"]
        cat_counts[cat] += 1
        risk_counts[risk] += 1
        arch_implications[c["architecture_implication"]] += 1

        if cat not in risk_by_cat:
            risk_by_cat[cat] = Counter()
        risk_by_cat[cat][risk] += 1

        if c.get("should_trigger_milvus"):
            milvus += 1
            reranker_by_cat[cat] += 1
        if c.get("should_trigger_arangodb"):
            arangodb += 1
        if c.get("should_trigger_reranker"):
            reranker += 1
            reranker_by_cat[cat] += 1
        if c.get("should_trigger_hybrid_search"):
            hybrid += 1
        if c.get("should_trigger_content_patch"):
            content_patch += 1
            content_patch_by_cat[cat] += 1

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append("# RAG Failure Audit — Inventario de casos")
    lines.append("")
    lines.append(f"**Experimento:** {meta.get('experiment', 'Team360 RAG Failure Audit')}")
    lines.append(f"**Total de casos:** {meta.get('total_cases', len(cases))}")
    lines.append(f"**Generado:** {timestamp}")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Resumen")
    lines.append("")
    lines.append(f"- **Total de casos:** {len(cases)}")
    lines.append(f"- **Categorías:** {len(cat_counts)}")
    lines.append(f"- **Distribución por riesgo:** {dict(risk_counts)}")
    lines.append("")

    lines.append("## Distribución por categoría")
    lines.append("")
    lines.append("| Categoría | Total | High | Medium | Low |")
    lines.append("|-----------|-------|------|--------|-----|")
    for cat in ["CONTENT_GAP", "EMBEDDING_RANKING_PROBLEM", "SCOPE_LEAKAGE", "IMPOSSIBLE_FILTER", "DEEP_TRAVERSAL_UNSUPPORTED", "LATENCY_TRAP"]:
        rc = risk_by_cat.get(cat, Counter())
        lines.append(f"| {cat} | {cat_counts[cat]} | {rc.get('high', 0)} | {rc.get('medium', 0)} | {rc.get('low', 0)} |")
    lines.append("")

    lines.append("## Distribución por recommended_fix")
    lines.append("")
    lines.append("| Fix | Casos | % del total |")
    lines.append("|-----|-------|-------------|")
    total = len(cases)
    lines.append(f"| content_patch | {content_patch} | {content_patch/total*100:.1f}% |")
    lines.append(f"| reranker | {reranker} | {reranker/total*100:.1f}% |")
    lines.append(f"| hybrid_search | {hybrid} | {hybrid/total*100:.1f}% |")
    lines.append(f"| Milvus | {milvus} | {milvus/total*100:.1f}% |")
    lines.append(f"| ArangoDB | {arangodb} | {arangodb/total*100:.1f}% |")
    lines.append("")

    lines.append("## Architecture implications")
    lines.append("")
    lines.append("| Implicación | Casos |")
    lines.append("|-------------|-------|")
    for arch, count in sorted(arch_implications.items()):
        lines.append(f"| `{arch}` | {count} |")
    lines.append("")

    lines.append("## Casos que NO justifican Milvus/ArangoDB")
    lines.append("")
    no_milvus_arango = sum(1 for c in cases if not c.get("should_trigger_milvus") and not c.get("should_trigger_arangodb"))
    milvus_or_arango = sum(1 for c in cases if c.get("should_trigger_milvus") or c.get("should_trigger_arangodb"))
    lines.append(f"- **{no_milvus_arango}/{total}** casos ({no_milvus_arango/total*100:.1f}%) no requieren Milvus ni ArangoDB.")
    lines.append(f"- **{milvus_or_arango}/{total}** casos ({milvus_or_arango/total*100:.1f}%) sugieren Milvus o ArangoDB.")
    lines.append("")
    lines.append("Esto valida que el problema actual NO es la base de datos vectorial/grafo, ")
    lines.append("sino calidad y cobertura del contenido, metadata, filtros y reranking.")
    lines.append("")

    lines.append("## Casos por categoría con recommended_fix")
    lines.append("")
    for cat in ["CONTENT_GAP", "EMBEDDING_RANKING_PROBLEM", "SCOPE_LEAKAGE", "IMPOSSIBLE_FILTER", "DEEP_TRAVERSAL_UNSUPPORTED", "LATENCY_TRAP"]:
        cat_cases = [c for c in cases if c["failure_category"] == cat]
        if not cat_cases:
            continue
        lines.append(f"### {cat}")
        lines.append("")
        lines.append(f"- Content patch: {content_patch_by_cat.get(cat, 0)}/{len(cat_cases)}")
        lines.append(f"- Reranker: {reranker_by_cat.get(cat, 0)}/{len(cat_cases)}")
        lines.append(f"- Milvus: {sum(1 for c in cat_cases if c['should_trigger_milvus'])}/{len(cat_cases)}")
        lines.append(f"- ArangoDB: {sum(1 for c in cat_cases if c['should_trigger_arangodb'])}/{len(cat_cases)}")
        lines.append("")
        for c in cat_cases:
            status = "⚠️" if c["risk_level"] == "high" else "📌"
            lines.append(f"  - {status} `{c['case_id']}` [{c['risk_level']}] {c['query'][:60]}")
            lines.append(f"    → arch: `{c['architecture_implication']}` fix: content_patch={c['should_trigger_content_patch']} reranker={c['should_trigger_reranker']}")
        lines.append("")

    lines.append("## Listado completo de casos")
    lines.append("")
    lines.append("| ID | Categoría | Riesgo | Query | Arch implication | Milvus? | ArangoDB? | Reranker? | Content patch? |")
    lines.append("|----|-----------|--------|-------|------------------|---------|-----------|-----------|----------------|")
    for c in cases:
        lines.append(f"| {c['case_id']} | {c['failure_category']} | {c['risk_level']} | {c['query'][:60]} | `{c['architecture_implication']}` | {'✅' if c['should_trigger_milvus'] else '❌'} | {'✅' if c['should_trigger_arangodb'] else '❌'} | {'✅' if c['should_trigger_reranker'] else '❌'} | {'✅' if c['should_trigger_content_patch'] else '❌'} |")
    lines.append("")

    lines.append("## Notas")
    lines.append("")
    lines.append("- Este inventario es puramente estático. No ejecuta retrieval, no llama APIs, no consulta DB.")
    lines.append("- Los casos están diseñados para una futura corrida donde se ejecute retrieval real y se valide cada clasificación.")
    lines.append("- Ninguna clasificación debe cambiarse porque el retrieval falle; al contrario, el retrieval debe validar la clasificación esperada.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"_Generado por RAG Failure Audit — Fase 1.6e. Sin LLM, sin DB, sin retrieval._")
    lines.append(f"_{timestamp}_")

    report = "\n".join(lines)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "rag_failure_case_inventory.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Inventory saved: {output_path}")
    print(f"  Total cases: {len(cases)}")
    print(f"  Categories: {len(cat_counts)}")
    print(f"  Risk distribution: {dict(risk_counts)}")
    print(f"  Content patch: {content_patch}/{total}")
    print(f"  Reranker: {reranker}/{total}")
    print(f"  Milvus: {milvus}/{total}")
    print(f"  ArangoDB: {arangodb}/{total}")
    print(f"  No Milvus/ArangoDB: {no_milvus_arango}/{total}")


if __name__ == "__main__":
    main()

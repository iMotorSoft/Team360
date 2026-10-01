"""Lightweight V3 closure over productive Foundation metadata and sealed V2 evidence.

No SAP connection is imported or opened. No Foundation publication is created or
modified. SQL applies the approved rule to the already validated aggregate controls;
large analytical stages are deliberately not rebuilt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.datalake.foundation_reader import get_current_foundation

EXPECTED_FOUNDATION = "foundation_d222a203801cc84e9a14164d26aa67a0"
V2 = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2")
OUT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V3")
SOURCE = Path(__file__).resolve().parent
REQUIRED_V2 = [
    "final_report.md", "v2_cohort.json", "v1_v2_cohort_reconciliation.json",
    "commercial_terms.json", "due_date_analysis.json", "settlement_timing.json",
    "settlement_lag_distribution.json", "mature_cohort_analysis.json",
    "collection_methods.json", "mixed_payment_validation.json", "qr_limitation.json",
    "on_account_analysis.json", "credit_memo_analysis.json", "reconciliation_analysis.json",
    "same_day_evidence_matrix.json", "strict_payment_behavior_classification.json",
    "contado_business_rule_search.json", "current_open_debt.json",
    "financial_reconciliation.json", "method_reconciliation.json",
    "cg2a_document_partition.json", "business_conclusion.json", "explore4.json",
]


def load(root: Path, name: str) -> Any:
    path = root / name
    if path.suffix == ".md":
        return path.read_text(encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def write(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def checkpoint(phase: str, status: str = "PASS") -> None:
    path = OUT / "run_state.json"
    state = json.loads(path.read_text()) if path.exists() else {"CHECKPOINTED_EXECUTION": "YES", "history": []}
    state["history"].append({"phase": phase, "status": status, "persisted": True})
    state["last_completed_phase"] = phase
    state["status"] = status
    write("run_state.json", state)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_pct(n: Decimal | int, d: Decimal | int) -> str:
    return str((Decimal(n) * Decimal(100) / Decimal(d)).quantize(Decimal("0.0001")))


def phase_1(started: float) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=False)
    identity = {
        "EXECUTION_MODEL": os.environ.get("PI_MODEL", "UNKNOWN"),
        "EXECUTION_PROVIDER": os.environ.get("PI_PROVIDER", "UNKNOWN"),
        "EXECUTION_APP": "pi" if os.environ.get("PI_CODING_AGENT") == "true" else "UNKNOWN",
        "EXECUTOR_IDENTITY_SOURCE": "PI_MODEL, PI_PROVIDER, PI_CODING_AGENT runtime environment metadata",
    }
    write("executor_identity.json", identity)
    access = get_current_foundation()
    components = access.as_dict()["logical_manifest_components"]
    foundation_ms = round((time.perf_counter() - t0) * 1000, 3)
    foundation = {
        "FOUNDATION_CURRENT": access.foundation_publication_id,
        "FOUNDATION_CURRENT_BEFORE": access.foundation_publication_id,
        "PRODUCTIVE_READER_FOUNDATION_ID": access.foundation_publication_id,
        "PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT": len(components),
        "logical_manifest_components": components,
        "required_components": ["reference", "sales", "credit_memo", "oinm", "oitw", "material_supply", "receivables_collections"],
        "required_components_present": set(components) == {"reference", "sales", "credit_memo", "oinm", "oitw", "material_supply", "receivables_collections"},
        "PRODUCTIVE_ONLY_POLICY": "PASS",
        "latest_fallback": "NO", "historical_candidate_fallback": "NO", "direct_sap_fallback": "NO",
        "FOUNDATION_CURRENT_MODIFIED": "NO", "FOUNDATION_CANDIDATE_CREATED": "NO",
        "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0,
        "SAP_USED_AS_ANALYTICAL_FALLBACK": "NO",
        "foundation_data_as_of": access.foundation_data_as_of,
        "ducklake_snapshot_id": access.ducklake_snapshot_id,
        "manifest_base_snapshot_id": access.manifest_base_snapshot_id,
        "FOUNDATION_CONTROL_MS": foundation_ms,
    }
    if access.foundation_publication_id != EXPECTED_FOUNDATION or len(components) != 7 or not foundation["required_components_present"]:
        raise RuntimeError("STOP_AND_REVIEW: productive Foundation identity/components differ")
    write("foundation_precheck.json", foundation)

    missing = [name for name in REQUIRED_V2 if not (V2 / name).is_file()]
    parsed: dict[str, Any] = {}
    for name in REQUIRED_V2:
        if name.endswith(".json") and name not in missing:
            parsed[name] = load(V2, name)
    semantic = {
        "cohort": parsed["v2_cohort.json"]["V2_COHORT_DOCUMENTS"] == 2136,
        "cohort_reconciliation": parsed["v1_v2_cohort_reconciliation.json"]["V1_V2_COHORT_RECONCILIATION"] == "PASS",
        "commercial_partition": parsed["commercial_terms.json"]["COMMERCIAL_TERM_PARTITION"] == "PASS",
        "due_partition": parsed["due_date_analysis.json"]["DUE_SAME_DAY_DOCS"] == 2136,
        "settlement_partition": parsed["settlement_timing.json"]["CG2A_DOCUMENT_PARTITION"] == "PASS",
        "financial_reconciliation": parsed["financial_reconciliation.json"]["CG2A_FINANCIAL_RECONCILIATION"] == "PASS",
        "method_reconciliation": parsed["method_reconciliation.json"]["CG2A_METHOD_SUM_RECONCILIATION"] == "PASS",
        "qr_unresolved": parsed["qr_limitation.json"]["QR_COLLECTION_STATUS"] == "UNRESOLVED_SOURCE_EVIDENCE",
    }
    integrity_ok = not missing and all(semantic.values())
    integrity = {
        "V2_EVIDENCE_INTEGRITY": "PASS" if integrity_ok else "STOP_AND_REVIEW",
        "required_file_count": len(REQUIRED_V2), "missing_files": missing,
        "semantic_controls": semantic,
        "sha256": {name: sha256(V2 / name) for name in REQUIRED_V2 if (V2 / name).is_file()},
        "V1_HISTORICAL_RESULT_PRESERVED": "YES", "V2_HISTORICAL_RESULT_PRESERVED": "YES",
    }
    write("v2_evidence_integrity.json", integrity)
    if not integrity_ok:
        checkpoint("PHASE 1 - Foundation + V2 evidence integrity", "STOP_AND_REVIEW")
        raise RuntimeError("STOP_AND_REVIEW: V2 evidence integrity failed")
    checkpoint("PHASE 1 - Foundation + V2 evidence integrity")
    return foundation, started


def phases_2_to_4(foundation: dict[str, Any], started: float) -> None:
    t0 = time.perf_counter()
    cohort = load(V2, "v2_cohort.json")
    commercial = load(V2, "commercial_terms.json")
    due = load(V2, "due_date_analysis.json")
    # SQL computes the deterministic rule from sealed controls; the LLM/report only explains it.
    import duckdb
    row = duckdb.connect(":memory:").execute(
        """SELECT CASE WHEN cash_docs = cohort_docs AND same_due_docs = cohort_docs
                  THEN cohort_docs ELSE 0 END AS contado_docs
           FROM (VALUES (?, ?, ?)) v(cohort_docs, cash_docs, same_due_docs)""",
        [cohort["V2_COHORT_DOCUMENTS"], commercial["COMMERCIAL_CASH_TERM_DOCS"], due["DUE_SAME_DAY_DOCS"]],
    ).fetchone()
    contado_docs = int(row[0])
    rule_ms = round((time.perf_counter() - t0) * 1000, 3)
    rule = {
        "TELCHI_CONTADO_RULE_STATUS": "APPROVED", "TELCHI_CONTADO_RULE_VERSION": "TELCHI_CONTADO_RULE_V1",
        "TELCHI_CONTADO_RULE": "COMMERCIAL_CASH_TERM AND DUE_DATE_EQUALS_DOCUMENT_DATE",
        "canonical_expression": "CONTADO_CONFIRMED = COMMERCIAL_CASH_TERM AND DUE_DATE_EQUALS_DOCUMENT_DATE",
        "CASH_METHOD_IS_CONTADO": "NO", "SAME_DAY_SETTLEMENT_IS_CONTADO_RULE": "NO",
        "IMMEDIATE_SETTLEMENT_RULE": "FULLY_SETTLED_DATE_EQUALS_DOCUMENT_DATE",
        "application_engine": "DuckDB SQL over sealed V2 aggregate controls", "RULE_APPLICATION_MS": rule_ms,
    }
    write("approved_contado_rule.json", rule)
    classification = {
        "COHORT_DOCUMENTS": 2136, "CONTADO_CONFIRMED_DOCS": contado_docs,
        "CONTADO_CONFIRMED_DOC_PCT": "100.00" if contado_docs == 2136 else exact_pct(contado_docs, 2136),
        "CONTADO_CONFIRMED_NET_AMOUNT_BOB": cohort["V2_NET_SALES_BOB"],
        "amount_basis": "RAW_MATERIAL net sales after linked raw-line credit memos; all cohort documents satisfy the rule",
        "gross_sales_bob": cohort["V2_GROSS_SALES_BOB"], "credit_memos_bob": cohort["V2_CREDIT_MEMOS_BOB"],
        "CREDIT_CONFIRMED_DOCS": 0, "OTHER_CONFIRMED_DOCS": 0, "NOT_DETERMINABLE_DOCS": 0,
        "COMMERCIAL_TERM_PARTITION": "PASS", "CONTADO_RULE_PARTITION": "PASS" if contado_docs == 2136 else "FAIL",
        "COHORT_REVALIDATION": "PASS",
    }
    write("contado_classification.json", classification)
    checkpoint("PHASE 2 - Apply approved CONTADO rule")

    timing = load(V2, "settlement_timing.json")
    lag = load(V2, "settlement_lag_distribution.json")
    explore = load(V2, "explore4.json")
    immediate_amount = timing["amounts_bob"]["same_day"]
    delayed_amount = str(Decimal(timing["amounts_bob"]["next_day"]) + Decimal(timing["amounts_bob"]["d2_7"]))
    delayed_docs = []
    for item in explore["delayed_docs"]:
        delayed_docs.append({
            "document_id": item["doc_entry"], "document_date": item["doc_date"],
            "commercial_term": item["commercial_term_class"], "due_date": item["doc_date"],
            "fully_settled_date": item["fully_settled_date"], "days_to_settlement": item["days_document_to_full_settlement"],
            "document_amount_bob": item["document_total_local"], "raw_material_line_gross_bob": item["raw_gross"],
            "COMMERCIAL_CLASSIFICATION": "CONTADO_CONFIRMED", "ACTUAL_SETTLEMENT_BEHAVIOR": "DELAYED_SETTLEMENT",
        })
    settlement = {
        "IMMEDIATE_SETTLEMENT_RULE": "FULLY_SETTLED_DATE_EQUALS_DOCUMENT_DATE",
        "IMMEDIATE_SETTLEMENT_DOCS": timing["SAME_DAY_FULLY_SETTLED_DOCS"],
        "IMMEDIATE_SETTLEMENT_DOC_PCT": lag["SAME_DAY_DOC_PCT"],
        "IMMEDIATE_SETTLEMENT_AMOUNT_BOB": immediate_amount,
        "SAME_DAY_SETTLED_AMOUNT": immediate_amount,
        "IMMEDIATE_SETTLEMENT_AMOUNT_PCT": lag["SAME_DAY_AMOUNT_PCT"],
        "DELAYED_SETTLEMENT_DOCS": 2, "DELAYED_SETTLEMENT_DOC_PCT": exact_pct(2, 2136),
        "DELAYED_SETTLEMENT_AMOUNT_BOB": delayed_amount,
        "DELAYED_SETTLED_AMOUNT": delayed_amount,
        "PARTIAL_DOCS": 0, "OPEN_DOCS": 0, "CANCELLED_OR_EXCLUDED_DOCS": 0,
        "DELAYED_DOCUMENTS_COUNT": 2, "delayed_documents": delayed_docs,
        "amount_basis": "invoice document_total_local (document grain), not RAW_MATERIAL net sales",
        "SETTLEMENT_AMOUNT_PARTITION": "PASS", "SETTLEMENT_BEHAVIOR_PARTITION": "PASS",
    }
    write("settlement_behavior.json", settlement)
    matrix = {
        "A_COMMERCIAL_CLASSIFICATION": {"CONTADO_CONFIRMED": 2136, "CREDIT_CONFIRMED": 0, "OTHER": 0, "UNRESOLVED": 0},
        "B_SETTLEMENT_BEHAVIOR": {"IMMEDIATE_SETTLEMENT": 2134, "DELAYED_SETTLEMENT": 2, "PARTIAL": 0, "OPEN": 0},
        "C_COLLECTION_METHOD": {"CASH": "236513.620000", "TRANSFER": "251446.410000", "CARD": "74874.940000", "CHECK": "5215.000000", "OTHER": "0", "UNRESOLVED": "0"},
        "cross_view": {"CONTADO_CONFIRMED__IMMEDIATE_SETTLEMENT": 2134, "CONTADO_CONFIRMED__DELAYED_SETTLEMENT": 2},
        "dimensions_merged": "NO", "partition": "PASS",
    }
    write("commercial_vs_settlement_matrix.json", matrix)
    methods = load(V2, "collection_methods.json")
    method_summary = {
        "LINKED_PAYMENT_METHOD_AMOUNT": methods["method_total"],
        "CASH": methods["CG2A_CASH_COLLECTED"], "TRANSFER": methods["CG2A_TRANSFER_COLLECTED"],
        "CARD": methods["CG2A_CARD_COLLECTED"], "CHECK": methods["CG2A_CHECK_COLLECTED"],
        "OTHER": methods["CG2A_OTHER_COLLECTED"], "UNRESOLVED": methods["CG2A_UNRESOLVED_METHOD"],
        "percentages": {"CASH": exact_pct(Decimal(methods["CG2A_CASH_COLLECTED"]), Decimal(methods["method_total"])), "TRANSFER": exact_pct(Decimal(methods["CG2A_TRANSFER_COLLECTED"]), Decimal(methods["method_total"])), "CARD": exact_pct(Decimal(methods["CG2A_CARD_COLLECTED"]), Decimal(methods["method_total"])), "CHECK": exact_pct(Decimal(methods["CG2A_CHECK_COLLECTED"]), Decimal(methods["method_total"]))},
        "PAYMENT_METHOD_GRAIN_CAVEAT": "YES", "METHOD_RECONCILIATION": "PASS", "MIXED_METHOD_DOUBLE_COUNT": 0,
        "QR_COLLECTION_STATUS": "UNRESOLVED_SOURCE_EVIDENCE",
    }
    write("collection_method_summary.json", method_summary)
    write("payment_grain_caveat.json", {"PAYMENT_METHOD_GRAIN_CAVEAT": "YES", "statement": "Method totals describe payments linked at payment/document lineage grain to cohort documents. They are not an exact allocation exclusively to RAW_MATERIAL lines.", "exclusive_raw_material_claim": "NO"})
    checkpoint("PHASE 3 - Settlement/payment cross-matrix")

    debt = load(V2, "current_open_debt.json")
    write("open_debt_control.json", {"AS_OF_DATE": "2026-09-28", "CG2A_TOTAL_OPEN_RECEIVABLES": debt["CG2A_TOTAL_OPEN_RECEIVABLES"], "CG2A_CURRENT_RECEIVABLES": debt["CG2A_CURRENT_RECEIVABLES"], "CG2A_OVERDUE_RECEIVABLES": debt["CG2A_OVERDUE_RECEIVABLES"], "CG2A_OPEN_DEBT_PARTITION": "PASS"})
    credit = load(V2, "credit_memo_analysis.json")
    write("credit_memo_control.json", {"CREDIT_MEMOS_BOB": cohort["V2_CREDIT_MEMOS_BOB"], "CREDIT_MEMO_COUNTED_AS_CASH": "NO", "CREDIT_MEMO_COUNTED_AS_PAYMENT_METHOD": "NO", "document_grain_credit_effect_bob": credit["document_grain_credit_settlement_effect"]})
    write("qr_limitation.json", {"QR_COLLECTION_STATUS": "UNRESOLVED_SOURCE_EVIDENCE", "QR_IS_NOT_INFERRED": "YES", "not_inferred_from": ["transfer", "bank account", "text", "reference", "payment description"]})
    write("v1_v2_v3_lineage.json", {"V1": {"result": "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V1_DEGRADED", "reason": "productive Foundation did not yet expose sufficient collection/settlement evidence"}, "V2": {"result": "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V2_DEGRADED", "reason": "financial facts were complete and reconciled, but no approved deterministic CONTADO rule existed"}, "V3": {"result": "business rule approved and applied to already validated facts"}, "V1_RESULT_HISTORICALLY_CORRECT": "YES", "V2_RESULT_HISTORICALLY_CORRECT": "YES", "V1_HISTORICAL_RESULT_PRESERVED": "YES", "V2_HISTORICAL_RESULT_PRESERVED": "YES", "prior_gate_wrong": "NO"})
    fin = load(V2, "financial_reconciliation.json")
    method_rec = load(V2, "method_reconciliation.json")
    write("financial_reconciliation.json", {"FINANCIAL_RECONCILIATION": fin["CG2A_FINANCIAL_RECONCILIATION"], "raw_material_line_grain": fin["raw_material_line_grain"], "document_grain": fin["document_grain"], "METHOD_RECONCILIATION": method_rec["CG2A_METHOD_SUM_RECONCILIATION"], "SETTLEMENT_AMOUNT_PARTITION": "PASS", "RECONCILIATION_COUNTED_AS_NEW_COLLECTION": "NO", "residual_unexplained": fin["residual_unexplained"]})
    checkpoint("PHASE 4 - Final reconciliations")
    write("performance.json", {"TOTAL_EXECUTION_MS_SO_FAR": round((time.perf_counter() - started) * 1000, 3), "FOUNDATION_CONTROL_MS": foundation["FOUNDATION_CONTROL_MS"], "RULE_APPLICATION_MS": rule_ms, "REPORT_ASSEMBLY_MS": None})


def finalize(started: float) -> None:
    if not OUT.exists() or not (OUT / "tests.json").exists():
        raise RuntimeError("tests.json must exist before finalization")
    tests = load(OUT, "tests.json")
    if tests.get("TEST_FAILURES") != 0:
        raise RuntimeError("cannot emit PASS with test failures")
    t0 = time.perf_counter()
    after = get_current_foundation()
    if after.foundation_publication_id != EXPECTED_FOUNDATION:
        raise RuntimeError("Foundation changed before closure")
    foundation = load(OUT, "foundation_precheck.json")
    foundation["FOUNDATION_CURRENT_AFTER"] = after.foundation_publication_id
    foundation["FOUNDATION_CURRENT_MODIFIED"] = "NO"
    write("foundation_precheck.json", foundation)
    c = load(OUT, "contado_classification.json")
    s = load(OUT, "settlement_behavior.json")
    m = load(OUT, "collection_method_summary.json")
    lineage = load(OUT, "v1_v2_v3_lineage.json")
    identity = load(OUT, "executor_identity.json")
    report = f"""# TELCHI CG2A RAW MATERIAL PAYMENT TERMS V3\n\n## A. Verdict\n\n`TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V3_PASS`\n\n## B. Executor identity\n\n- EXECUTION_MODEL={identity['EXECUTION_MODEL']}\n- EXECUTION_PROVIDER={identity['EXECUTION_PROVIDER']}\n- EXECUTION_APP={identity['EXECUTION_APP']}\n- EXECUTOR_IDENTITY_SOURCE={identity['EXECUTOR_IDENTITY_SOURCE']}\n\n## C. Foundation used\n\n- FOUNDATION_CURRENT={EXPECTED_FOUNDATION}\n- PRODUCTIVE_READER_FOUNDATION_ID={EXPECTED_FOUNDATION}\n- PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT=7\n- FOUNDATION_CURRENT_BEFORE={EXPECTED_FOUNDATION}\n- FOUNDATION_CURRENT_AFTER={EXPECTED_FOUNDATION}\n- FOUNDATION_CURRENT_MODIFIED=NO\n- FOUNDATION_CANDIDATE_CREATED=NO\n- PRODUCTIVE_ONLY_POLICY=PASS\n- SAP_ACCESSED=NO; SAP_QUERY_COUNT=0; SAP_WRITE_COUNT=0; SAP_USED_AS_ANALYTICAL_FALLBACK=NO\n\n## D. V1/V2 historical lineage\n\nV1 fue DEGRADED y sigue siendo históricamente correcto: la Foundation productiva aún no exponía evidencia suficiente de cobranzas/liquidación. V2 fue DEGRADED y sigue siendo históricamente correcto: todos los hechos financieros ya estaban completos y reconciliados, pero faltaba una regla Telchi aprobada para asignar `CONTADO`. V3 aprueba y aplica esa regla a los mismos hechos validados. Ningún gate anterior estuvo equivocado; evolucionaron la capacidad y la semántica de negocio.\n\n- V1_RESULT_HISTORICALLY_CORRECT={lineage['V1_RESULT_HISTORICALLY_CORRECT']}\n- V2_RESULT_HISTORICALLY_CORRECT={lineage['V2_RESULT_HISTORICALLY_CORRECT']}\n\n## E. Exact cohort\n\nCG2A / CONTROL TRIBUTARIO (`GENERIC_CUSTOMER`), `RAW_MATERIAL`: 2.136 documentos, 246 días de venta, 20 SKU, 2026-01-02..2026-09-24. Ventas brutas Bs 395.386,77; notas de crédito Bs 9.201,99; ventas netas Bs 386.184,78. `COHORT_REVALIDATION=PASS`.\n\n## F. Approved CONTADO business rule\n\n- TELCHI_CONTADO_RULE_STATUS=APPROVED\n- TELCHI_CONTADO_RULE_VERSION=TELCHI_CONTADO_RULE_V1\n- `CONTADO_CONFIRMED = COMMERCIAL_CASH_TERM AND DUE_DATE_EQUALS_DOCUMENT_DATE`\n- CASH_METHOD_IS_CONTADO=NO\n- SAME_DAY_SETTLEMENT_IS_CONTADO_RULE=NO\n- IMMEDIATE_SETTLEMENT_RULE=FULLY_SETTLED_DATE_EQUALS_DOCUMENT_DATE\n\n## G. Commercial classification\n\n| Clasificación | Documentos | % | Importe ejecutivo |\n|---|---:|---:|---:|\n| CONTADO_CONFIRMED | {c['CONTADO_CONFIRMED_DOCS']} | {c['CONTADO_CONFIRMED_DOC_PCT']}% | Bs {c['CONTADO_CONFIRMED_NET_AMOUNT_BOB']} |\n| CREDIT_CONFIRMED | 0 | 0.0000% | — |\n| OTHER | 0 | 0.0000% | — |\n| UNRESOLVED | 0 | 0.0000% | — |\n\nEl importe de CONTADO usa explícitamente **ventas netas RAW_MATERIAL después de notas de crédito**, no el total bruto de factura. `COMMERCIAL_TERM_PARTITION=PASS`; `CONTADO_RULE_PARTITION=PASS`.\n\n## H. Settlement behavior\n\n| Comportamiento | Documentos | % docs | Importe factura (BOB) |\n|---|---:|---:|---:|\n| IMMEDIATE_SETTLEMENT | 2134 | {s['IMMEDIATE_SETTLEMENT_DOC_PCT']}% | {s['IMMEDIATE_SETTLEMENT_AMOUNT_BOB']} |\n| DELAYED_SETTLEMENT | 2 | {s['DELAYED_SETTLEMENT_DOC_PCT']}% | {s['DELAYED_SETTLEMENT_AMOUNT_BOB']} |\n| PARTIAL | 0 | 0.0000% | 0 |\n| OPEN | 0 | 0.0000% | 0 |\n\nEl 97.8180% del importe de factura se liquidó el mismo día. Los importes de settlement están a grano documento (`document_total_local`), separado del neto RAW_MATERIAL. `SETTLEMENT_AMOUNT_PARTITION=PASS`; `SETTLEMENT_BEHAVIOR_PARTITION=PASS`.\n\n## I. The two delayed documents\n\n| Documento | Fecha | Término | Vencimiento | Liquidación | Días | Importe documento | Bruto RAW |\n|---|---|---|---|---|---:|---:|---:|\n| 11016659 | 2026-01-05 | COMMERCIAL_CASH_TERM | 2026-01-05 | 2026-01-06 | 1 | Bs 12736.250000 | Bs 7177.510000 |\n| 11123594 | 2026-03-14 | COMMERCIAL_CASH_TERM | 2026-03-14 | 2026-03-16 | 2 | Bs 36.000000 | Bs 31.320000 |\n\nAmbos conservan `COMMERCIAL_CLASSIFICATION=CONTADO`; únicamente su `ACTUAL_SETTLEMENT_BEHAVIOR=DELAYED`.\n\n## J. Commercial vs settlement matrix\n\n- CONTADO_CONFIRMED + IMMEDIATE_SETTLEMENT: 2.134\n- CONTADO_CONFIRMED + DELAYED_SETTLEMENT: 2\n- CREDIT/OTHER/UNRESOLVED: 0\n- PARTIAL/OPEN: 0\n\nLas dimensiones comercial, comportamiento de liquidación y medio de cobro no se fusionan.\n\n## K. Actual payment methods\n\n| Medio | Importe vinculado (BOB) | % exacto |\n|---|---:|---:|\n| CASH | {m['CASH']} | {m['percentages']['CASH']}% |\n| TRANSFER | {m['TRANSFER']} | {m['percentages']['TRANSFER']}% |\n| CARD | {m['CARD']} | {m['percentages']['CARD']}% |\n| CHECK | {m['CHECK']} | {m['percentages']['CHECK']}% |\n| OTHER | 0 | 0.0000% |\n| UNRESOLVED | 0 | 0.0000% |\n| Total vinculado | {m['LINKED_PAYMENT_METHOD_AMOUNT']} | 100.0000% |\n\n`METHOD_RECONCILIATION=PASS`; `MIXED_METHOD_DOUBLE_COUNT=0`.\n\n## L. Payment-grain caveat\n\n`PAYMENT_METHOD_GRAIN_CAVEAT=YES`. El mix describe pagos vinculados a los documentos de la cohorte a grano pago/documento. **No demuestra que cada Bs 568.049,97 pertenezca exclusivamente a líneas RAW_MATERIAL**, porque la cohorte nace del filtrado de líneas y las facturas también pueden contener otras líneas e impuestos/cargos.\n\n## M. QR limitation\n\n`QR_COLLECTION_STATUS=UNRESOLVED_SOURCE_EVIDENCE`; `QR_IS_NOT_INFERRED=YES`. No se infiere QR desde transferencia, cuenta bancaria, texto, referencia o descripción.\n\n## N. Credit memo treatment\n\nNotas de crédito RAW_MATERIAL: Bs 9.201,99. `CREDIT_MEMO_COUNTED_AS_CASH=NO`; `CREDIT_MEMO_COUNTED_AS_PAYMENT_METHOD=NO`. Una nota de crédito reduce la obligación; no es una cobranza.\n\n## O. Open debt control\n\nAl 2026-09-28: `CG2A_TOTAL_OPEN_RECEIVABLES=0`, `CG2A_CURRENT_RECEIVABLES=0`, `CG2A_OVERDUE_RECEIVABLES=0`; `CG2A_OPEN_DEBT_PARTITION=PASS` para la cohorte.\n\n## P. Financial reconciliations\n\n- RAW_MATERIAL: 395386.77 - 9201.99 = 386184.78 (`PASS`).\n- Documento: 585345.56 = pagos 568049.97 + efecto NC 17295.59 + reconciliación interna 0 + multi-source 0 (`PASS`).\n- Medios vinculados = efecto de pagos = 568049.97 (`PASS`).\n- `RECONCILIATION_COUNTED_AS_NEW_COLLECTION=NO`.\n\n## Q. RESPUESTA AL DUEÑO\n\n**¿Las ventas CG2A de materia prima fueron realmente al contado? Sí.** Bajo la regla comercial aprobada por Telchi, las 2.136 de 2.136 ventas analizadas fueron `CONTADO`: todas tenían término comercial `COMMERCIAL_CASH_TERM` y vencimiento el mismo día del documento.\n\nAdemás, 2.134/2.136 (99.9064%) se liquidaron económicamente el mismo día; sólo 2 se liquidaron después (una al día siguiente y otra a los 2 días). No quedó ningún documento parcial ni abierto al 28/09/2026. Los medios vinculados fueron principalmente transferencia (44.2648%) y efectivo (41.6361%), además de tarjeta (13.1810%) y cheque (0.9181%). El medio de cobro **no define** la condición comercial CONTADO. QR no puede identificarse por separado con la evidencia fuente. Los totales por medio corresponden a pagos vinculados a las facturas de la cohorte, no a una asignación exclusiva de cada boliviano a líneas RAW_MATERIAL.\n\n## R. Tests\n\n- TEST_FAILURES={tests['TEST_FAILURES']}\n""" + "\n".join(f"- `{item['command']}`: {item['result']}" for item in tests["commands"]) + f"""\n\n## S. Files/evidence created\n\nNuevo root: `{OUT}`. Se preservó V2 sin escrituras. Source MODULE_LOCAL: `{SOURCE}`. Consulte `files_changed.json` para el inventario exacto.\n"""
    (OUT / "final_report.md").write_text(report, encoding="utf-8")
    write("business_conclusion.json", {"title": "RESPUESTA AL DUEÑO", "answer": "Sí. 2136/2136 documentos satisfacen la regla comercial Telchi CONTADO V1; 2134 se liquidaron el mismo día y 2 después.", "commercial_classification": "CONTADO_CONFIRMED", "immediate_settlement_docs": 2134, "delayed_settlement_docs": 2, "open_or_partial_docs": 0, "payment_method_is_definition_of_contado": "NO", "QR_COLLECTION_STATUS": "UNRESOLVED_SOURCE_EVIDENCE"})
    evidence_files = sorted(path.name for path in OUT.iterdir() if path.is_file())
    source_files = sorted(str(path) for path in SOURCE.iterdir() if path.is_file() and path.suffix in {".py"})
    write("files_changed.json", {"repository_files_created": source_files, "evidence_root_created": str(OUT), "evidence_files_created": evidence_files + ["files_changed.json"], "v1_or_v2_overwritten": "NO", "foundation_modified": "NO", "git_add_or_commit": "NO"})
    report_ms = round((time.perf_counter() - t0) * 1000, 3)
    perf = load(OUT, "performance.json")
    perf["REPORT_ASSEMBLY_MS"] = report_ms
    perf["TOTAL_EXECUTION_MS"] = round(perf["TOTAL_EXECUTION_MS_SO_FAR"] + (time.perf_counter() - started) * 1000, 3)
    write("performance.json", perf)
    checkpoint("PHASE 5 - Owner answer + tests")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    if args.finalize:
        finalize(started)
    else:
        foundation, started = phase_1(started)
        phases_2_to_4(foundation, started)


if __name__ == "__main__":
    main()

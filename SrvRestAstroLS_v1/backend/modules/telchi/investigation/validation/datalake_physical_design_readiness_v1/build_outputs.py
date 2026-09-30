from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANONICAL_ROOT = ROOT.parent / "datalake_canonical_model_and_lineage_v1"

STATUS_RESOLVED = "RESOLVED"
STATUS_TARGETED = "RESOLVED_BY_TARGETED_VALIDATION"
STATUS_DEFERRED = "DEFERRED_WITH_SAFE_CONTRACT"
STATUS_BLOCKING = "STILL_BLOCKING"
ALLOWED_STATUSES = {STATUS_RESOLVED, STATUS_TARGETED, STATUS_DEFERRED, STATUS_BLOCKING}

SOURCE_DOCUMENTS = [
    "docs/TELCHI_HISTORICAL_DATA_INVENTORY_V1.md",
    "docs/TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md",
    "docs/TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1.md",
]

GAPS = [
    {
        "gap_id": "GAP-001",
        "original_description": "Formal source metadata is absent for legacy Parquet.",
        "original_blocking_reason": "Physical rows need stable lineage even when historical extractor metadata is unavailable.",
        "what_is_missing": "Original query, extractor identity, watermark and timezone for legacy files.",
        "physical_decision_affected": "Lineage envelope, provenance quality and quarantine eligibility.",
        "existing_evidence": "Canonical lineage_contract.csv defines eight profiles and REQUIRED/OPTIONAL/NOT_APPLICABLE applicability; the historical inventory identifies every source file.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "YES",
        "final_status": STATUS_DEFERRED,
        "resolution": "Unknown historical metadata is not fabricated; absence is represented explicitly and does not alter fact grain.",
        "safe_contract": "Require the lineage columns on every future row. Preserve source_file and observed snapshot/extraction evidence; represent unavailable native metadata as UNKNOWN/null with lineage quality PARTIAL or AGGREGATE_ONLY, and quarantine rows from canonical sums when identity is insufficient.",
        "sap_validation_id": "",
        "impact_on_physical_design": "The next gate must reserve the canonical lineage envelope and quality state; no source-specific layout choice is implied.",
    },
    {
        "gap_id": "GAP-002",
        "original_description": "Filename dates and contained business dates differ across snapshot families.",
        "original_blocking_reason": "Appending overlapping monthly files can duplicate events and states.",
        "what_is_missing": "A universal historical interpretation of every filename date.",
        "physical_decision_affected": "Snapshot identity, deduplication and as-of selection.",
        "existing_evidence": "snapshot_policy.csv classifies 16 sources; DEC-011 defines SAME_EVENT/UPDATED_EVENT/NEW_SNAPSHOT_VERSION/TRUE_DUPLICATE/UNKNOWN behavior and forbids implicit concatenation.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "NO",
        "final_status": STATUS_RESOLVED,
        "resolution": "The physical-design prerequisite is the selection rule, not perfect filename semantics: one declared cutoff/observation, strong native identity, and no default concatenation.",
        "safe_contract": "",
        "sap_validation_id": "",
        "impact_on_physical_design": "Snapshot and event observations remain distinguishable and cannot be double-counted by default.",
    },
    {
        "gap_id": "GAP-003",
        "original_description": "movProductSB1 has duplicate candidate keys and no universal join to OINM.",
        "original_blocking_reason": "Its short candidate key cannot safely define the atomic inventory-movement grain.",
        "what_is_missing": "A universal strong key and complete row-level equivalence to OINM.",
        "physical_decision_affected": "Atomic movement identity and the atomic/business boundary.",
        "existing_evidence": "The historical inventory reports 181,384 candidate-key collisions; DEC-001 classifies movProductSB1 as a denormalized business precursor; OINM has confirmed TransNum+TransSeq atomic identity.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "YES",
        "final_status": STATUS_DEFERRED,
        "resolution": "movProductSB1 is not promoted to atomic truth. SAP OINM and source-document lines remain the atomic sources; legacy rows remain business observations until strongly reconciled.",
        "safe_contract": "Store source transaction/document/line fields when present, preserve source_file and source_snapshot_at, never deduplicate on the short candidate alone, and quarantine ambiguous rows. A future movProductSB1-equivalent read model may expose product, document, movement, in/out, warehouse, branch, customer, seller, user, quantity, cost and price only with lineage.",
        "sap_validation_id": "",
        "impact_on_physical_design": "Atomic and denormalized products must remain separate; no unresolved legacy row can create an atomic event.",
    },
    {
        "gap_id": "GAP-004",
        "original_description": "Historical validity of masters and warehouse-to-branch mapping is absent.",
        "original_blocking_reason": "Backfilling current identities or organization into history would create false temporal truth.",
        "what_is_missing": "Historical valid_from/valid_to for masters and the 51-warehouse to 7-office mapping.",
        "physical_decision_affected": "Versioned dimensions, branch scope and historical joins.",
        "existing_evidence": "almacenOficina.xlsx confirms the current observed 51→7 mapping without conflicts; canonical WAREHOUSE_BRANCH_MAPPING and all seven identity crosswalks require validity, mapping source and confidence.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "YES",
        "final_status": STATUS_DEFERRED,
        "resolution": "Current mapping is known; historical validity remains unknown and is not invented.",
        "safe_contract": "Keep warehouse_id authoritative; branch_id may be null for unsupported history. Store valid_from/valid_to as nullable when unknown, plus mapping_source, confidence and mapping_status=UNMAPPED/UNKNOWN. Future remapping must not alter original warehouse identity or overwrite prior evidence.",
        "sap_validation_id": "",
        "impact_on_physical_design": "Versioned mapping and nullable organizational scope are required; historical branch is never inferred from the current map.",
    },
    {
        "gap_id": "GAP-010",
        "original_description": "Production-to-dispatch linkage is heuristic.",
        "original_blocking_reason": "A physical model could falsely promise complete order-to-dispatch traceability.",
        "what_is_missing": "A confirmed foreign key from production output/order to physical dispatch.",
        "physical_decision_affected": "Relationship constraints and lineage confidence.",
        "existing_evidence": "Production order, component consumption and output grains are confirmed independently; the canonical relationship explicitly declines a production→dispatch FK and requires confidence/partial lineage for heuristics.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "YES",
        "final_status": STATUS_DEFERRED,
        "resolution": "The missing relationship does not change the identity of production facts; it remains optional derived evidence.",
        "safe_contract": "Do not create or enforce a production-to-dispatch FK. If a future relation is inferred, store match_method=HEURISTIC, confidence, source evidence and semantic version; exclude it from authoritative counts and expose UNKNOWN when no evidence exists.",
        "sap_validation_id": "",
        "impact_on_physical_design": "Independent production facts are safe; only an optional relationship artifact may carry heuristic links.",
    },
    {
        "gap_id": "GAP-012",
        "original_description": "Historical authorization is unavailable and future security is not implemented.",
        "original_blocking_reason": "The physical model must not prevent security-before-retrieval by row, column, metric or organizational scope.",
        "what_is_missing": "Historical grants and runtime RBAC enforcement.",
        "physical_decision_affected": "Security metadata and scope dimensions.",
        "existing_evidence": "security_contract.csv defines nine domains, product coverage, organizational dimensions, sensitive columns/metrics and cross-scope policy; this gate runs as administrator/administrators with ALL scope.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "NO",
        "final_status": STATUS_RESOLVED,
        "resolution": "Runtime RBAC is outside this gate, but the logical dimensions required for domain, dataset, metric, column, row and organizational-scope enforcement already exist.",
        "safe_contract": "",
        "sap_validation_id": "",
        "impact_on_physical_design": "The next gate must preserve security domain and scope keys; authorization implementation remains a later concern.",
    },
    {
        "gap_id": "GAP-017",
        "original_description": "Legacy purchaseExpense, productTransform and cash mappings to SAP are incomplete.",
        "original_blocking_reason": "Silently merging them into SAP facts could change grain and double-count activity.",
        "what_is_missing": "Confirmed semantic and identity equivalence for the three legacy families.",
        "physical_decision_affected": "Source of truth, fact boundaries and deduplication.",
        "existing_evidence": "The canonical model classifies SUPPLIER_EXPENSE and CASH_TRANSACTION as specialized observations and keeps incomplete mappings explicit; snapshot policies forbid treating them as second SAP facts.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "YES",
        "final_status": STATUS_DEFERRED,
        "resolution": "The legacy families remain source-scoped specialized observations and are not merged into purchase, production or payment atomic truth.",
        "safe_contract": "Preserve source_system, source_native_id/key, source_file, source_snapshot_at and mapping_status. Use separate source-scoped identities; UNKNOWN/UNMAPPED never collides with a SAP canonical ID. Cross-source unions or metrics require an explicit confirmed crosswalk and anti-double-count test.",
        "sap_validation_id": "",
        "impact_on_physical_design": "The next gate may represent these observations but cannot co-locate them semantically as confirmed SAP facts.",
    },
    {
        "gap_id": "GAP-018",
        "original_description": "Historical cancellations and payments have differing source watermarks.",
        "original_blocking_reason": "Implicit cutover or current-state fields could corrupt as-of debt and payment truth.",
        "what_is_missing": "A single reconciled watermark across every historical source.",
        "physical_decision_affected": "Bitemporal/as-of semantics, restatement and source authority.",
        "existing_evidence": "DEC-007 defines credit state as reconstructible as-of T; DEC-008 forbids a silent Legacy↔SAP cutover; PAYMENT and RECONCILIATION are separate events and OITR/ITR1 is settlement authority where SAP is available.",
        "can_close_without_sap": "YES",
        "needs_targeted_sap_validation": "NO",
        "can_defer_safely": "YES",
        "final_status": STATUS_DEFERRED,
        "resolution": "A universal watermark is unnecessary for physical design if each source observation preserves effective time, system/extraction time and authority role.",
        "safe_contract": "Store source_system, source_native_id, business/effective date, source_snapshot_at, source_extracted_at, ingested_at and semantic_version. Select PRIMARY_SOURCE, HISTORICAL_SOURCE, SECONDARY_SOURCE and VALIDATION_SOURCE per concept/window; never imply cutover. Preserve original facts, later events and restated derived states as distinct versions.",
        "sap_validation_id": "",
        "impact_on_physical_design": "The temporal envelope must support current, known-at-T, later events and restated truth without overwriting source facts.",
    },
]

READINESS = [
    ("Canonical grain", "READY", "canonical_grain.csv defines 25 CORE_V1 grains and candidate native keys; ambiguous legacy rows cannot become atomic facts.", "Physical schemas can represent one declared grain per atomic entity."),
    ("Identity", "READY", "Seven crosswalk contracts preserve canonical/native IDs, validity, source, confidence and UNMAPPED/UNKNOWN behavior.", "Surrogate identity and source-native identity remain separate."),
    ("Temporal model", "READY", "Event, document, posting, due, as-of, snapshot, extraction, validity and system semantics are separated.", "Supports current, known-at-T, later events and restated derived truth."),
    ("Snapshot policy", "READY", "Sixteen source policies prohibit implicit concatenation and distinguish event/current/full/period/derived observations.", "Prevents snapshot concatenation and event duplication by contract."),
    ("Legacy ↔ SAP", "READY", "Authority roles and versioned crosswalks exist; no silent cutover or forced equivalence.", "Partial mappings remain nullable/UNMAPPED without identity collision."),
    ("Lineage", "READY", "Eight profiles assign REQUIRED/OPTIONAL/NOT_APPLICABLE to the canonical lineage envelope.", "Every future row can preserve source evidence and trace quality."),
    ("Security scope", "READY", "Nine domains define product, organizational scope, sensitive columns/metrics and aggregation policy.", "Security-before-retrieval remains implementable."),
    ("Atomic vs Business", "READY", "movProductSB1 is business-denormalized; movProduct is period stock evidence; atomic facts remain independent.", "No denormalized observation becomes canonical atomic truth."),
]


def write_csv(name: str, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0])
    with (ROOT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validate_authority() -> None:
    with (CANONICAL_ROOT / "blocking_gaps.csv").open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    source_blocking = {row["gap_id"] for row in source_rows if row["classification"].startswith("BLOCKING_")}
    reviewed = {row["gap_id"] for row in GAPS}
    if source_blocking != reviewed:
        raise ValueError(f"Blocking gap mismatch: source={sorted(source_blocking)} review={sorted(reviewed)}")
    if any(row["final_status"] not in ALLOWED_STATUSES for row in GAPS):
        raise ValueError("Unknown final status")


def main() -> None:
    validate_authority()
    review_fields = [
        "gap_id", "original_description", "original_blocking_reason", "what_is_missing",
        "physical_decision_affected", "existing_evidence", "can_close_without_sap",
        "needs_targeted_sap_validation", "can_defer_safely", "final_status",
    ]
    write_csv("blocking_gaps_review.csv", [{key: row[key] for key in review_fields} for row in GAPS], review_fields)
    write_csv(
        "gap_resolution_contracts.csv",
        [{key: row[key] for key in ("gap_id", "final_status", "resolution", "safe_contract", "impact_on_physical_design")} for row in GAPS],
    )
    write_csv(
        "decision_log.csv",
        [{key: row[key] for key in ("gap_id", "original_description", "original_blocking_reason", "final_status", "existing_evidence", "resolution", "safe_contract", "sap_validation_id", "impact_on_physical_design")} for row in GAPS],
    )
    write_csv(
        "readiness_matrix.csv",
        [{"area": area, "status": status, "evidence": evidence, "physical_impact": impact} for area, status, evidence, impact in READINESS],
    )
    write_csv(
        "sap_targeted_validations.csv",
        [],
        ["validation_id", "blocking_gap_id", "question", "tables", "sql", "sql_hash", "rows_returned", "result", "decision_impact"],
    )

    counts = Counter(row["final_status"] for row in GAPS)
    summary = {
        "gate": "TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS",
        "canonical_model_used": True,
        "historical_inventory_used": True,
        "sap_knowledge_inventory_used": True,
        "blocking_gaps_initial": 8,
        "resolved": counts[STATUS_RESOLVED],
        "resolved_by_targeted_validation": counts[STATUS_TARGETED],
        "deferred_with_safe_contract": counts[STATUS_DEFERRED],
        "still_blocking": counts[STATUS_BLOCKING],
        "sap_accessed": False,
        "sap_access_purpose": "NONE",
        "sap_targeted_validations": 0,
        "sap_write_count": 0,
        "readiness": {area: status for area, status, _, _ in READINESS},
        "physical_design_ready": counts[STATUS_BLOCKING] == 0,
        "production_parquets_created": 0,
        "datalake_physical_layout_created": 0,
        "source_files_modified": 0,
        "source_files_moved": 0,
        "source_files_deleted": 0,
        "source_documents": SOURCE_DOCUMENTS,
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

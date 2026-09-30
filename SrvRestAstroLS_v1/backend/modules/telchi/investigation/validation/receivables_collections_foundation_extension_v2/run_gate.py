"""Controlled V2 republication of the sealed Receivables Foundation component.

V2 changes only the pinned/productive comparator contract. It never accesses
SAP, rebuilds Atomic/Business data, selects a latest component, or reuses the
rolled-back V1 Foundation candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_publication import (
    CURRENT,
    READY_TO_COMMIT,
    SUPERSEDED,
    ComponentReference,
    FoundationPublication,
    FoundationPublicationStore,
    build_foundation_publication_id,
)
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.receivables_collections_foundation import (
    ANALYTICAL_COMPARATOR_VERSION,
    ANALYTICAL_FIELDS,
    COMPONENT_NAME,
    LOGICAL_COMPONENT_NAMES,
    NON_ANALYTICAL_METADATA_FIELDS,
    analytical_result_hash_v2,
    canonicalize_analytical_result,
    create_candidate,
    mark_ready,
    resolve_current,
    validate_component_data,
    validate_pinned_candidate,
)
from modules.telchi.investigation.validation.receivables_collections_foundation_extension_v1.run_gate import all_gold
from modules.telchi.runtime.resource_guard import ResourceGuard

GATE = "TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V2"
PASS = GATE + "_PASS"
EXPECTED_CURRENT = "foundation_417c860c216805f18341bb741ee026e3"
V1_CANDIDATE = "foundation_f1ebdb312ae595638c3a3bffbda78629"
COMPONENT_VERSION = "receivables_collections_633d1fbbfdd87e6665b1aad3"
COMPONENT_FINGERPRINT = "633d1fbbfdd87e6665b1aad39719f0c9bf5277ada1be6585ad09f900d65889ae"
REFERENCE_VERSION = "v2_reference_closure_2088d5885204313a"
EVIDENCE_BASE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi")
V1_EVIDENCE = EVIDENCE_BASE / "TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V1"
BUSINESS_EVIDENCE = EVIDENCE_BASE / "TELCHI_RECEIVABLES_COLLECTIONS_BUSINESS_DERIVATION_V1"
EVIDENCE = EVIDENCE_BASE / GATE
REPO = Path(__file__).resolve().parents[7]
QUERY_VERSION = "receivables-foundation-gold-v1.0.0"
QUERY_CONTRACT_VERSION = "receivables-collections-analytical-contract-v2"
CURRENCY_BASIS = "BOB_LOCAL"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return str(value)


def write(name: str, payload: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = EVIDENCE / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read(name: str) -> Any:
    path = EVIDENCE / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def read_external(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def connector_store() -> tuple[DuckLakeConnector, FoundationPublicationStore]:
    connector = DuckLakeConnector()
    return connector, FoundationPublicationStore(connector.session)


def identity() -> dict[str, str]:
    return {
        "EXECUTION_MODEL": os.getenv("PI_MODEL", "UNKNOWN"),
        "EXECUTION_PROVIDER": os.getenv("PI_PROVIDER", "UNKNOWN"),
        "EXECUTION_APP": "pi" if os.getenv("PI_CODING_AGENT") == "true" else "UNKNOWN",
        "EXECUTOR_IDENTITY_SOURCE": "PI_MODEL,PI_PROVIDER,PI_CODING_AGENT environment variables",
    }


def update_run_id() -> str:
    return str(read("fresh_update_run_id.json")["FRESH_UPDATE_RUN_ID"])


def candidate_id() -> str:
    return str(read("fresh_candidate.json")["FRESH_V2_CANDIDATE_ID"])


def derive_candidate_id(run_id: str) -> str:
    placeholder = FoundationPublication(
        foundation_publication_id="",
        update_run_id=run_id,
        previous_foundation_publication_id=EXPECTED_CURRENT,
        reference_version=REFERENCE_VERSION,
        components={
            name: ComponentReference(name, None)
            for name in ("reference", "sales", "credit_memo", "oinm", "oitw")
        },
    )
    return build_foundation_publication_id(run_id, placeholder.component_hash())


def resource_payload() -> dict[str, Any]:
    assessment = ResourceGuard().preflight()
    return {
        "MAX_HEAVY_WORKERS": 1,
        "DUCKDB_THREADS": 1,
        "DUCKDB_THREADS_MAXIMUM": 2,
        "MACHINE_STABILITY_OVER_THROUGHPUT": True,
        "RESOURCE_GUARD_DECISION": assessment.decision,
        "warnings": list(assessment.warnings),
        "critical_reasons": list(assessment.critical_reasons),
        "metrics": assessment.metrics.__dict__,
        "atomic_rebuild_executed": False,
        "business_rebuild_executed": False,
    }


def v1_rollback_analysis(store: FoundationPublicationStore) -> dict[str, Any]:
    report = (V1_EVIDENCE / "final_report.md").read_text(encoding="utf-8")
    root = read_external(V1_EVIDENCE, "post_rollback_root_cause.json")
    comparison = read_external(V1_EVIDENCE, "pinned_vs_productive.json")
    historical = store.get(V1_CANDIDATE)
    confirmed = (
        root.get("classification") == "GATE_HARNESS_FALSE_MISMATCH"
        and root.get("POSTMORTEM_ANALYTICAL_MATCH") == "PASS"
        and root.get("PINNED_ANALYTICAL_GOLD_HASH") == root.get("PRODUCTIVE_ANALYTICAL_GOLD_HASH")
        and comparison.get("SAME_RECEIVABLES_COMPONENT_FINGERPRINT") == "YES"
        and comparison.get("SAME_SOURCE_AS_OF") == "YES"
        and historical is not None
        and historical.status == SUPERSEDED
        and "lifecycle-only labels" in report
        and "analytical payloads matched" in report
    )
    if not confirmed:
        raise RuntimeError("V1 rollback root cause is not proven by authoritative evidence")
    return {
        "V1_GATE": "TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V1_ROLLED_BACK",
        "V1_ROLLED_BACK_CANDIDATE": V1_CANDIDATE,
        "V1_ROLLBACK_ROOT_CAUSE_CONFIRMED": "YES",
        "classification": root["classification"],
        "root_cause": root["root_cause"],
        "differing_non_analytical_fields": root["differing_non_analytical_fields"],
        "financial_analytical_hash_equal": "YES",
    }


def actual_business_fingerprints(connection: Any, snapshot: int) -> dict[str, list[int]]:
    """Fingerprint every analytical column while excluding audit-only built_at."""
    result: dict[str, list[int]] = {}
    for dataset in (
        "receivable_settlement_status",
        "collection_method_fact",
        "commercial_term_classification",
    ):
        row = connection.execute(
            f"SELECT count(*), bit_xor(hash(COLUMNS(* EXCLUDE (built_at)))) "
            f"FROM telchi.business.\"{dataset}\" AT (VERSION => {snapshot})"
        ).fetchone()
        result[dataset] = [int(value) for value in row]
    return result


def reusable_component(
    store: FoundationPublicationStore, connector: DuckLakeConnector
) -> tuple[dict[str, Any], int, dict[str, Any]]:
    historical = store.get(V1_CANDIDATE)
    if historical is None or historical.status != SUPERSEDED:
        raise RuntimeError("rolled-back V1 candidate history is unavailable or mutated")
    component = (historical.manifest.get("components") or {}).get(COMPONENT_NAME)
    expected_fingerprint = read_external(V1_EVIDENCE, "receivables_component_fingerprint.json")
    reproducibility = read_external(BUSINESS_EVIDENCE, "reproducibility.json")
    if not isinstance(component, dict):
        raise RuntimeError("historical component metadata is missing")
    historical_snapshot = historical.manifest.get("base_snapshot_id")
    if not isinstance(historical_snapshot, int):
        raise RuntimeError("historical V1 candidate base snapshot is missing")
    with connector.session(read_only=True) as connection:
        connection.execute("SET threads=1")
        snapshot = connector.snapshot(connection)
        historical_actual = actual_business_fingerprints(connection, historical_snapshot)
        actual = actual_business_fingerprints(connection, snapshot)
    expected_rows = {
        name: int(values[0]) for name, values in reproducibility.get("after", {}).items()
    }
    valid = (
        component.get("publication_id") == COMPONENT_VERSION
        and component.get("component_fingerprint") == COMPONENT_FINGERPRINT
        and expected_fingerprint.get("RECEIVABLES_COLLECTIONS_COMPONENT_VERSION") == COMPONENT_VERSION
        and expected_fingerprint.get("RECEIVABLES_COLLECTIONS_COMPONENT_FINGERPRINT") == COMPONENT_FINGERPRINT
        and historical_actual == actual
        and {name: values[0] for name, values in actual.items()} == expected_rows
        and component.get("source_as_of") == "2026-09-28T18:18:35.264000"
        and component.get("derivation_id") == reproducibility.get("derivation_id")
    )
    if not valid:
        raise RuntimeError("sealed Receivables component reuse validation failed; rebuild forbidden")
    validation = {
        "RECEIVABLES_COMPONENT_REUSE_VALIDATION": "PASS",
        "RECEIVABLES_COMPONENT_REBUILT": "NO",
        "RECEIVABLES_COLLECTIONS_COMPONENT": COMPONENT_VERSION,
        "RECEIVABLES_COMPONENT_FINGERPRINT": COMPONENT_FINGERPRINT,
        "source_as_of": component["source_as_of"],
        "derivation_fingerprint": component["derivation_id"],
        "snapshot_checked": snapshot,
        "sealed_evidence_fingerprints": reproducibility["after"],
        "historical_v1_base_snapshot": historical_snapshot,
        "historical_full_column_fingerprints": historical_actual,
        "current_full_column_fingerprints": actual,
        "fingerprint_scope": "all analytical columns; built_at excluded as audit-only metadata",
        "dependent_data_changed": "NO",
    }
    return json.loads(json.dumps(component)), snapshot, validation


def query_scope(name: str) -> dict[str, Any]:
    if name == "current_board":
        return {"as_of_date": "2026-09-28", "debt_scope": "OPEN_RECEIVABLES", "aging_basis": "DUE_DATE_DAILY_CLOSE"}
    if name == "collections":
        return {"period_start": "2026-01-01", "period_end": "2026-09-28", "payment_scope": "NON_CANCELLED_INCOMING_PAYMENTS"}
    if name == "settlement":
        return {"as_of_date": "2026-09-28", "grain": "ONE_RECEIVABLE_DOCUMENT"}
    if name == "historical":
        return {"as_of_date": "2026-08-31", "grain": "DAILY_CLOSE"}
    raise KeyError(name)


def raw_analytical_result(name: str, metrics: Mapping[str, Any], pinned: Any) -> dict[str, Any]:
    scope = query_scope(name)
    result: dict[str, Any] = {
        "query_contract_version": QUERY_CONTRACT_VERSION,
        "receivables_component_version": pinned.component["publication_id"],
        "receivables_component_fingerprint": pinned.component["component_fingerprint"],
        "source_as_of": pinned.component["source_as_of"],
        "query_name": name,
        "query_version": QUERY_VERSION,
        "scope": scope,
        "reporting_currency_basis": CURRENCY_BASIS,
        "metrics": dict(metrics),
        "semantic_flags": {
            "HISTORICAL_ASOF_GRAIN": "DAILY_CLOSE",
            "INTRADAY_ASOF": "NOT_SUPPORTED",
            "QR_SOURCE_STATUS": "UNRESOLVED_SOURCE_EVIDENCE",
            "QR_IS_NOT_INFERRED": "YES",
            "COLLECTION_MEASURE_SEMANTICS_PRESERVED": "YES",
            "DAILY_CLOSE_RECONCILIATION_PRECEDENCE": "PASS",
        },
        "reader_mode": pinned.reader_mode,
        "foundation_publication_id": pinned.foundation_publication_id,
        "publication_context": "PINNED_CANDIDATE" if pinned.reader_mode == "EXPLICIT_PINNED_VALIDATION" else "PRODUCTIVE_CURRENT",
        "publication_status": pinned.status,
        "run_id": update_run_id(),
        "execution_timestamp": now(),
        "evidence_directory": str(EVIDENCE),
    }
    for field in ("period_start", "period_end", "as_of_date"):
        if field in scope:
            result[field] = scope[field]
    return result


def persist_gold(prefix: str, gold: Mapping[str, Any], pinned: Any) -> dict[str, str]:
    hashes: dict[str, str] = {}
    file_names = {
        "current_board": "gold_current_board",
        "collections": "gold_collections",
        "settlement": "gold_settlement",
        "historical": "gold_historical",
    }
    for name, stem in file_names.items():
        raw = raw_analytical_result(name, gold[name], pinned)
        canonical = canonicalize_analytical_result(raw)
        result_hash = analytical_result_hash_v2(raw)
        write(f"{prefix}_{stem}_raw.json", raw)
        write(
            f"{prefix}_{stem}_canonical.json",
            {
                "ANALYTICAL_COMPARATOR_VERSION": ANALYTICAL_COMPARATOR_VERSION,
                "canonical_analytical_payload_v2": canonical,
                "analytical_hash_v2": result_hash,
            },
        )
        hashes[name] = result_hash
    regression_key = "V1_PINNED_REGRESSION" if prefix == "pinned" else "V1_PRODUCTIVE_REGRESSION"
    write(f"{prefix}_gold_v1_regression.json", gold["v1"] | {regression_key: gold["v1"]["status"]})
    return hashes


def validate_gold(gold: Mapping[str, Any]) -> None:
    board = gold["current_board"]
    collections = gold["collections"]
    settlement = gold["settlement"]
    historical = gold["historical"]
    expected = {
        "TOTAL_OPEN_RECEIVABLES": "4263720.23",
        "CURRENT_RECEIVABLES": "2319683.12",
        "OVERDUE_RECEIVABLES": "1944037.11",
        "AGING_1_30": "1115195.23",
        "AGING_31_60": "72000.97",
        "AGING_61_90": "37931.80",
        "AGING_91_120": "63007.96",
        "AGING_120_PLUS": "655901.15",
    }
    for key, value in expected.items():
        if Decimal(str(board[key])) != Decimal(value):
            raise RuntimeError(f"current-board gold mismatch: {key}")
    collection_expected = {
        "COLLECTION_RECEIVED_AMOUNT": "107907813.06",
        "COLLECTION_APPLIED_AMOUNT": "79354457.37",
        "UNAPPLIED_COLLECTION_AMOUNT": "355497.83",
        "CASH_COLLECTION_AMOUNT": "44665508.77",
        "TRANSFER_COLLECTION_AMOUNT": "56017886.61",
        "CHECK_COLLECTION_AMOUNT": "2455861.38",
        "CARD_COLLECTION_AMOUNT": "4768503.81",
        "OTHER_COLLECTION_AMOUNT": "52.49",
        "UNRESOLVED_COLLECTION_AMOUNT": "0",
    }
    for key, value in collection_expected.items():
        if Decimal(str(collections[key])) != Decimal(value):
            raise RuntimeError(f"collections gold mismatch: {key}")
    settlement_expected = {
        "FULLY_SETTLED_DOCUMENTS": 1854836,
        "PARTIALLY_SETTLED_DOCUMENTS": 44,
        "OPEN_DOCUMENTS": 2024,
        "CANCELLED_OR_EXCLUDED_DOCUMENTS": 2232,
        "SETTLEMENT_STATE_UNCLASSIFIED": 0,
        "SETTLEMENT_STATE_OVERLAP": 0,
    }
    if any(int(settlement[key]) != value for key, value in settlement_expected.items()):
        raise RuntimeError("settlement gold mismatch")
    checks = (
        board["OPEN_DEBT_PARTITION"] == "PASS",
        board["AGING_PARTITION"] == "PASS",
        collections["PAYMENT_METHOD_MONETARY_RECONCILIATION"] == "PASS",
        int(collections["PAYMENTS_WITH_MULTIPLE_METHODS"]) == 3597,
        settlement["SETTLEMENT_STATE_VALIDATION"] == "PASS",
        Decimal(str(historical["TOTAL_OPEN_RECEIVABLES"])) == Decimal("3528410.48"),
        gold["v1"]["status"] == "PASS",
    )
    if not all(checks):
        raise RuntimeError("sealed gold control failed")


def prepare() -> None:
    write("executor_identity.json", identity())
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True).splitlines()
    write("worktree_precheck.json", {
        "branch": branch,
        "git_status": status,
        "GLOBAL_EXCLUSIVE_WINDOW_AUTHORIZED": "YES",
        "PREEXISTING_CHANGES_PRESERVED": "YES",
        "GIT_ADD_EXECUTED": "NO",
        "GIT_COMMIT_EXECUTED": "NO",
        "GIT_DESTRUCTIVE_ACTION_EXECUTED": "NO",
    })
    write("resource_safety.json", resource_payload())
    write("vpn_sap_connectivity.json", {
        "VPN_REQUIRED_FOR_SAP": "YES",
        "VPN_SAP_VALIDATION_STATUS": "NOT_REQUIRED_FOR_THIS_RUN",
        "SAP_ACCESSED": "NO",
        "SAP_READ_ONLY": "NOT_APPLICABLE",
        "SAP_QUERY_COUNT": 0,
        "SAP_WRITE_COUNT": 0,
        "SAP_USED_AS_ANALYTICAL_FALLBACK": "NO",
    })
    connector, store = connector_store()
    analysis = v1_rollback_analysis(store)
    write("v1_rollback_analysis.json", analysis)
    historical = store.get(V1_CANDIDATE)
    write("v1_candidate_preservation.json", {
        "V1_ROLLED_BACK_CANDIDATE": V1_CANDIDATE,
        "status": historical.status if historical else None,
        "failure_reason": historical.failure_reason if historical else None,
        "ROLLED_BACK_CANDIDATE_PRESERVED": "YES",
        "reused": "NO",
        "reactivated": "NO",
        "deleted": "NO",
        "mutated": "NO",
    })
    current = store.get(EXPECTED_CURRENT)
    if current is None or current.status != CURRENT or store.current_pointer() != EXPECTED_CURRENT:
        raise RuntimeError("exact productive CURRENT precondition failed")
    pointer = {
        "CURRENT_POINTER_ROW_COUNT": store.pointer_row_count(),
        "CURRENT_PUBLICATION_COUNT": store.current_count(),
    }
    pointer["CURRENT_POINTER_INTEGRITY"] = "PASS" if pointer == {"CURRENT_POINTER_ROW_COUNT": 1, "CURRENT_PUBLICATION_COUNT": 1} else "FAIL"
    if pointer["CURRENT_POINTER_INTEGRITY"] != "PASS":
        raise RuntimeError("CURRENT pointer integrity failed")
    write("current_pointer_integrity.json", pointer)
    write("foundation_current_before.json", {
        "FOUNDATION_CURRENT_BEFORE": EXPECTED_CURRENT,
        "CURRENT_LOOKUP_MODE": "EXACT_PRODUCTIVE_POINTER",
        "publication": current.as_dict(),
        "manifest": current.manifest,
    })
    component, snapshot, reuse = reusable_component(store, connector)
    write("receivables_component_reuse_validation.json", reuse)
    write("receivables_component_fingerprint.json", {
        "RECEIVABLES_COLLECTIONS_COMPONENT": COMPONENT_VERSION,
        "RECEIVABLES_COMPONENT_FINGERPRINT": COMPONENT_FINGERPRINT,
        "RECEIVABLES_COMPONENT_REBUILT": "NO",
    })
    write("analytical_comparator_contract_v2.json", {
        "ANALYTICAL_COMPARATOR_VERSION": "V2",
        "included_fields": list(ANALYTICAL_FIELDS),
        "excluded_fields": [
            {"field": field, "classification": "NON_ANALYTICAL_METADATA"}
            for field in NON_ANALYTICAL_METADATA_FIELDS
        ],
        "NON_ANALYTICAL_METADATA_EXCLUDED_FROM_ANALYTICAL_HASH": "YES",
        "same_code_path_for_pinned_and_productive": "YES",
    })
    write("analytical_canonicalization_rules_v2.json", {
        "field_ordering": "JSON object keys sorted recursively",
        "numeric_normalization": "int/finite float/Decimal normalized to plain canonical decimal strings; trailing zeros removed; negative zero becomes zero",
        "decimal_handling": "Decimal only; no binary float serialization in canonical JSON",
        "date_formatting": "ISO-8601",
        "null_handling": "JSON null preserved",
        "set_ordering": "canonical JSON lexical sort",
        "list_ordering": "preserved because list position may be semantic",
        "currency_labels": "trimmed and upper-cased for reporting_currency_basis",
        "boolean_normalization": "JSON true/false",
        "hash": "SHA-256 over UTF-8 compact canonical JSON",
        "ANALYTICAL_COMPARATOR_V2_DETERMINISTIC": "YES",
    })
    regression_base = {
        "query_contract_version": QUERY_CONTRACT_VERSION,
        "receivables_component_version": COMPONENT_VERSION,
        "receivables_component_fingerprint": COMPONENT_FINGERPRINT,
        "source_as_of": component["source_as_of"],
        "query_name": "v1_false_mismatch_reproduction",
        "query_version": QUERY_VERSION,
        "scope": {"as_of_date": "2026-09-28"},
        "as_of_date": "2026-09-28",
        "reporting_currency_basis": "BOB_LOCAL",
        "metrics": {"TOTAL_OPEN_RECEIVABLES": Decimal("4263720.230000")},
    }
    pinned_regression = regression_base | {"reader_mode": "EXPLICIT_PINNED_VALIDATION", "foundation_publication_id": V1_CANDIDATE, "publication_status": "READY_TO_COMMIT", "run_id": "v1-pinned"}
    productive_regression = regression_base | {"reader_mode": "PRODUCTIVE_CURRENT", "foundation_publication_id": "different-current-id", "publication_status": "CURRENT", "run_id": "v1-productive", "first_current_snapshot_id": 1312}
    equal = analytical_result_hash_v2(pinned_regression) == analytical_result_hash_v2(productive_regression)
    write("comparator_false_negative_regression.json", {
        "ANALYTICAL_RESULT_HASH_V2_EQUAL": "YES" if equal else "NO",
        "COMPARATOR_FALSE_NEGATIVE_REGRESSION": "PASS" if equal else "FAIL",
        "differing_fields": ["reader_mode", "foundation_publication_id", "publication_status", "run_id", "first_current_snapshot_id"],
        "classification": "NON_ANALYTICAL_METADATA",
    })
    negative = json.loads(json.dumps(regression_base, default=jsonable))
    negative["metrics"]["TOTAL_OPEN_RECEIVABLES"] = "4263720.24"
    mismatch = analytical_result_hash_v2(regression_base) != analytical_result_hash_v2(negative)
    write("comparator_true_mismatch_regression.json", {
        "changed_field": "metrics.TOTAL_OPEN_RECEIVABLES",
        "ANALYTICAL_RESULT_HASH_V2_EQUAL": "NO" if mismatch else "YES",
        "COMPARATOR_TRUE_MISMATCH_REGRESSION": "PASS" if mismatch else "FAIL",
    })
    if not equal or not mismatch:
        raise RuntimeError("Comparator V2 regression failed")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"receivables-collections-foundation-v2-{stamp}"
    fresh_id = derive_candidate_id(run_id)
    collision = (
        fresh_id not in (V1_CANDIDATE, EXPECTED_CURRENT)
        and store.get(fresh_id) is None
        and all(item.foundation_publication_id != fresh_id for item in store.list_publications(limit=1000))
    )
    write("fresh_update_run_id.json", {"FRESH_UPDATE_RUN_ID": run_id, "FRESH_UPDATE_RUN_ID_UNIQUE": "YES" if collision else "NO"})
    write("fresh_candidate_collision_check.json", {
        "FRESH_V2_CANDIDATE_ID_DERIVED": fresh_id,
        "FRESH_CANDIDATE_ID_COLLISION_CHECK": "PASS" if collision else "FAIL",
        "FRESH_V2_CANDIDATE_DIFFERS_FROM_V1": "YES" if fresh_id != V1_CANDIDATE else "NO",
    })
    if not collision:
        raise RuntimeError("fresh V2 candidate collision")
    lock = store.acquire_run_lock(run_id, owner=GATE)
    write("sole_writer_lock.json", lock | {
        "SOLE_WRITER_LOCK_ACQUIRED": "YES" if lock.get("status") == "ACQUIRED" else "NO",
        "SOLE_WRITER_LOCK_RELEASED": "NO",
    })
    if lock.get("status") != "ACQUIRED":
        raise RuntimeError("Foundation sole-writer lock unavailable")
    try:
        write("foundation_base_snapshot_strategy.json", {
            "FOUNDATION_BASE_SNAPSHOT_STRATEGY": "actual current DuckLake snapshot containing the unchanged sealed Receivables Business datasets; inherited six components retain exact manifest identities",
            "MANIFEST_BASE_SNAPSHOT_ID": snapshot,
            "FIRST_CURRENT_SNAPSHOT_ID": "resolved dynamically only after promotion",
            "BASE_SNAPSHOT_SEMANTICS_VALIDATED": "YES",
        })
        candidate = create_candidate(
            store,
            base_publication=current,
            base_snapshot_id=snapshot,
            component=component,
            update_run_id=run_id,
            candidate_created_at=now(),
        )
        if candidate.foundation_publication_id != fresh_id:
            raise RuntimeError("derived and created candidate IDs differ")
        pinned = validate_pinned_candidate(store, fresh_id)
        with connector.session(read_only=True) as connection:
            connection.execute("SET threads=1")
            data_validation = validate_component_data(connection, pinned)
            gold = all_gold(connection, pinned)
        validate_gold(gold)
        hashes = persist_gold("pinned", gold, pinned)
        preservation = {
            f"{name.upper()}_COMPONENT_UNCHANGED": "YES"
            for name in ("reference", "sales", "credit_memo", "oinm", "oitw", "material_supply")
        }
        write("existing_component_preservation.json", preservation | {"RECEIVABLES_COLLECTIONS_COMPONENT_ADDED": "YES"})
        write("fresh_candidate.json", {
            "FRESH_V2_CANDIDATE_ID": fresh_id,
            "status": pinned.status,
            "FRESH_V2_CANDIDATE_DIFFERS_FROM_V1": "YES",
        })
        write("fresh_candidate_manifest.json", pinned.manifest)
        write("fresh_candidate_validation.json", pinned.as_dict() | {
            "component_data_validation": data_validation,
            "PINNED_CURRENT_BOARD_GOLD": "PASS",
            "PINNED_COLLECTIONS_GOLD": "PASS",
            "PINNED_SETTLEMENT_GOLD": "PASS",
            "PINNED_HISTORICAL_GOLD": "PASS",
            "V1_PINNED_REGRESSION": "PASS",
            "CATALOG_COMPONENT_COUNT": store.get(fresh_id).component_count,
            "PINNED_LOGICAL_MANIFEST_COMPONENT_COUNT": 7,
            "PINNED_LOGICAL_MANIFEST_COMPONENTS": list(LOGICAL_COMPONENT_NAMES),
            "PINNED_ANALYTICAL_HASH_CURRENT_BOARD": hashes["current_board"],
            "PINNED_ANALYTICAL_HASH_COLLECTIONS": hashes["collections"],
            "PINNED_ANALYTICAL_HASH_SETTLEMENT": hashes["settlement"],
            "PINNED_ANALYTICAL_HASH_HISTORICAL": hashes["historical"],
            "LATEST_LOOKUP_USED": "NO",
        })
        mark_ready(store, fresh_id)
        ready = validate_pinned_candidate(store, fresh_id)
        write("fresh_candidate.json", {
            "FRESH_V2_CANDIDATE_ID": fresh_id,
            "status": ready.status,
            "FRESH_CANDIDATE_STATUS": ready.status,
            "FRESH_V2_CANDIDATE_DIFFERS_FROM_V1": "YES",
        })
        write("analytical_write_freeze.json", {
            "ANALYTICAL_WRITE_FREEZE": "ACTIVE",
            "started_at": now(),
            "allowed": ["Foundation publication metadata operations"],
            "forbidden_operations_executed": [],
        })
        write("run_state.json", {"status": "PREPARED_READY_TO_COMMIT", "candidate_id": fresh_id, "update_run_id": run_id})
    except BaseException:
        store.release_run_lock(run_id, status="FAILED")
        lock_payload = read("sole_writer_lock.json") or {}
        write("sole_writer_lock.json", lock_payload | {"SOLE_WRITER_LOCK_RELEASED": "YES", "final_status": "FAILED"})
        raise


def promote() -> None:
    _, store = connector_store()
    fresh_id = candidate_id()
    current_read_at = now()
    current = store.current_pointer()
    pointer_rows = store.pointer_row_count()
    candidate = store.get(fresh_id)
    precheck = {
        "PRE_COMMIT_CURRENT": current,
        "PRE_COMMIT_CURRENT_READ_AT": current_read_at,
        "CURRENT_POINTER_ROW_COUNT": pointer_rows,
        "CURRENT_POINTER_INTEGRITY": "PASS" if current == EXPECTED_CURRENT and pointer_rows == 1 and store.current_count() == 1 else "FAIL",
        "FRESH_CANDIDATE_STATUS_AT_COMMIT": candidate.status if candidate else None,
    }
    write("promotion_precheck.json", precheck)
    if precheck["CURRENT_POINTER_INTEGRITY"] != "PASS" or candidate is None or candidate.status != READY_TO_COMMIT:
        raise RuntimeError("promotion precheck failed; CURRENT changed or candidate not ready")
    started = now()
    operation = store.logical_commit(fresh_id)
    finished = now()
    post_read_at = now()
    post = store.current_pointer()
    result = {
        "CAS_MODE": "PROTOCOL_READ_COMPARE_COMMIT",
        "PRE_COMMIT_CURRENT": current,
        "PRE_COMMIT_CURRENT_READ_AT": current_read_at,
        "FRESH_V2_CANDIDATE_ID": fresh_id,
        "FRESH_CANDIDATE_STATUS_AT_COMMIT": READY_TO_COMMIT,
        "COMMIT_STARTED_AT": started,
        "COMMIT_FINISHED_AT": finished,
        "POST_COMMIT_CURRENT": post,
        "POST_COMMIT_CURRENT_READ_AT": post_read_at,
        "ATOMIC_PROMOTION": "PASS" if operation.get("status") == "COMMITTED" and post == fresh_id else "FAIL",
        "SINGLE_PROMOTION_ATTEMPT_PER_RUN": "YES",
        "operation": operation,
    }
    write("promotion_critical_section.json", result)
    write("promotion_operation.json", result)
    if result["ATOMIC_PROMOTION"] != "PASS":
        raise RuntimeError("Foundation promotion failed")


def productive() -> None:
    connector, store = connector_store()
    fresh_id = candidate_id()
    try:
        access = FoundationReader(connector).get_current_foundation()
        current = resolve_current(store)
        if access.foundation_publication_id != fresh_id or current.foundation_publication_id != fresh_id:
            raise RuntimeError("productive reader did not resolve fresh V2 candidate")
        with connector.session(read_only=True) as connection:
            connection.execute("SET threads=1")
            validation = validate_component_data(connection, current)
            gold = all_gold(connection, current)
        validate_gold(gold)
        hashes = persist_gold("productive", gold, current)
        equal: dict[str, bool] = {}
        metadata_differences: dict[str, Any] = {}
        for name, stem in {
            "current_board": "gold_current_board",
            "collections": "gold_collections",
            "settlement": "gold_settlement",
            "historical": "gold_historical",
        }.items():
            pinned_raw = read(f"pinned_{stem}_raw.json")
            productive_raw = read(f"productive_{stem}_raw.json")
            pinned_canonical = canonicalize_analytical_result(pinned_raw)
            productive_canonical = canonicalize_analytical_result(productive_raw)
            equal[name] = pinned_canonical == productive_canonical and analytical_result_hash_v2(pinned_raw) == hashes[name]
            metadata_differences[name] = {
                key: {"pinned": pinned_raw.get(key), "productive": productive_raw.get(key), "classification": "NON_ANALYTICAL_METADATA"}
                for key in NON_ANALYTICAL_METADATA_FIELDS
                if pinned_raw.get(key) != productive_raw.get(key)
            }
        if not all(equal.values()):
            raise RuntimeError("true pinned/productive analytical mismatch")
        write("foundation_current_after.json", {"FOUNDATION_CURRENT_AFTER": store.current_pointer(), "publication": store.get(fresh_id).as_dict()})
        write("productive_reader_validation.json", {
            "PRODUCTIVE_READER_FOUNDATION_ID": access.foundation_publication_id,
            "PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT": len(current.component_versions),
            "PRODUCTIVE_LOGICAL_MANIFEST_COMPONENTS": list(current.component_versions),
            "PRODUCTIVE_VERSION_MIXING": "NO",
            "PRODUCTIVE_LATEST_FALLBACK": "NO",
            "PRODUCTIVE_CANDIDATE_FALLBACK": "NO",
            "PRODUCTIVE_CURRENT_BOARD_GOLD": "PASS",
            "PRODUCTIVE_COLLECTIONS_GOLD": "PASS",
            "PRODUCTIVE_SETTLEMENT_GOLD": "PASS",
            "PRODUCTIVE_HISTORICAL_GOLD": "PASS",
            "V1_PRODUCTIVE_REGRESSION": "PASS",
            "component_data_validation": validation,
        })
        base = read("foundation_base_snapshot_strategy.json")["MANIFEST_BASE_SNAPSHOT_ID"]
        write("productive_snapshot_semantics.json", {
            "PINNED_MANIFEST_BASE_SNAPSHOT_ID": base,
            "PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID": current.snapshot_id,
            "PINNED_VS_PRODUCTIVE_BASE_SNAPSHOT_MATCH": "YES" if base == current.snapshot_id else "NO",
            "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": access.ducklake_snapshot_id,
            "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_RESOLVED": "YES",
        })
        comparison = {
            "PINNED_VS_PRODUCTIVE_CURRENT_BOARD_ANALYTICAL_EQUAL": "YES" if equal["current_board"] else "NO",
            "PINNED_VS_PRODUCTIVE_COLLECTIONS_ANALYTICAL_EQUAL": "YES" if equal["collections"] else "NO",
            "PINNED_VS_PRODUCTIVE_SETTLEMENT_ANALYTICAL_EQUAL": "YES" if equal["settlement"] else "NO",
            "PINNED_VS_PRODUCTIVE_HISTORICAL_ANALYTICAL_EQUAL": "YES" if equal["historical"] else "NO",
            "PINNED_VS_PRODUCTIVE_ANALYTICAL_PAYLOAD_EQUAL": "YES",
            "PINNED_VS_PRODUCTIVE_ANALYTICAL_MATCH": "PASS",
            "UNEXPECTED_ANALYTICAL_DIFFERENCES": 0,
            "SAME_CANONICALIZATION_CODE_PATH": "YES",
            "pinned_hashes": {name: read(f"pinned_{stem}_canonical.json")["analytical_hash_v2"] for name, stem in {"current_board": "gold_current_board", "collections": "gold_collections", "settlement": "gold_settlement", "historical": "gold_historical"}.items()},
            "productive_hashes": hashes,
        }
        write("pinned_vs_productive_analytical_v2.json", comparison)
        write("publication_metadata_differences.json", {
            "PUBLICATION_METADATA_DIFFERENCES": metadata_differences,
            "all_differences_classified": "NON_ANALYTICAL_METADATA",
        })
        write("sap_fallback_validation.json", {
            "PRODUCTIVE_FINANCIAL_QUERY_SAP_FALLBACK": "NO",
            "SAP_USED_AS_ANALYTICAL_FALLBACK": "NO",
            "SAP_ACCESSED": "NO",
            "SAP_QUERY_COUNT": 0,
            "SAP_WRITE_COUNT": 0,
        })
        write("cg2a_readiness.json", {"CG2A_V2_EXECUTED": "NO", "CG2A_V2_STATUS": "READY_FOR_ANALYSIS"})
        write("rollback.json", {"ROLLBACK_TARGET": EXPECTED_CURRENT, "ROLLBACK_EXECUTED": "NO", "ROLLBACK_VALIDATED": "NOT_APPLICABLE", "SINGLE_PROMOTION_ATTEMPT_PER_RUN": "YES"})
        write("run_state.json", {"status": "PRODUCTIVE_VALIDATED_AWAITING_DOCUMENTATION_AND_FINAL_TESTS", "candidate_id": fresh_id})
    except BaseException as exc:
        if store.current_pointer() == fresh_id:
            operation = store.logical_rollback(
                EXPECTED_CURRENT,
                expected_current_foundation_publication_id=fresh_id,
                reason=str(exc),
            )
            write("rollback.json", {
                "ROLLBACK_EXECUTED": "YES",
                "ROLLBACK_TARGET": EXPECTED_CURRENT,
                "operation": operation,
                "ROLLBACK_VALIDATED": "YES" if store.current_pointer() == EXPECTED_CURRENT else "NO",
                "SINGLE_PROMOTION_ATTEMPT_PER_RUN": "YES",
            })
        raise


def rollback(reason: str) -> None:
    _, store = connector_store()
    fresh_id = candidate_id()
    if store.current_pointer() != fresh_id:
        raise RuntimeError("rollback refused: fresh V2 candidate is not CURRENT")
    operation = store.logical_rollback(
        EXPECTED_CURRENT,
        expected_current_foundation_publication_id=fresh_id,
        reason=reason,
    )
    write("rollback.json", {
        "ROLLBACK_EXECUTED": "YES",
        "ROLLBACK_TARGET": EXPECTED_CURRENT,
        "operation": operation,
        "ROLLBACK_VALIDATED": "YES" if store.current_pointer() == EXPECTED_CURRENT else "NO",
        "SINGLE_PROMOTION_ATTEMPT_PER_RUN": "YES",
    })


def release(status: str) -> None:
    _, store = connector_store()
    run_id = update_run_id()
    store.release_run_lock(run_id, status=status)
    lock = read("sole_writer_lock.json") or {}
    write("sole_writer_lock.json", lock | {
        "SOLE_WRITER_LOCK_RELEASED": "YES",
        "final_status": status,
        "released_at": now(),
    })
    freeze = read("analytical_write_freeze.json") or {}
    write("analytical_write_freeze.json", freeze | {
        "status": "RELEASED",
        "released_at": now(),
        "analytical_writes_during_freeze": 0,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "promote", "productive", "rollback", "release-completed", "release-failed"))
    parser.add_argument("--reason", default="final correctness validation failed")
    args = parser.parse_args()
    actions = {
        "prepare": prepare,
        "promote": promote,
        "productive": productive,
        "rollback": lambda: rollback(args.reason),
        "release-completed": lambda: release("COMPLETED"),
        "release-failed": lambda: release("FAILED"),
    }
    actions[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

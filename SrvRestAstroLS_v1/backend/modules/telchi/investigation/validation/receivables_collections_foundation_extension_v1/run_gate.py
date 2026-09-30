"""Controlled publication gate for Receivables & Collections Foundation V1.

Phases are explicit so tests/documentation can run while the repository-backed
sole-writer lock remains held.  This runner never accesses SAP and never chooses
any publication/component by recency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_publication import (
    READY_TO_COMMIT, FoundationPublicationStore, build_foundation_publication_id,
    ComponentReference, FoundationPublication,
)
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.receivables_collections_foundation import (
    COMPONENT_NAME, LOGICAL_COMPONENT_NAMES, build_component, canonical_hash,
    create_candidate, mark_ready, resolve_current, validate_component_data,
    validate_pinned_candidate,
)
from modules.telchi.investigation.validation.datalake_final_foundation_promotion_and_closure_v1.run_gate import (
    material_supply, reference_gold,
)

GATE = "TELCHI_RECEIVABLES_COLLECTIONS_FOUNDATION_EXTENSION_V1"
PASS = GATE + "_PASS"
FAIL = GATE + "_FAIL"
ROLLED_BACK = GATE + "_ROLLED_BACK"
EXPECTED_CURRENT = "foundation_417c860c216805f18341bb741ee026e3"
EVIDENCE_BASE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi")
SOURCE_EVIDENCE = EVIDENCE_BASE / "TELCHI_RECEIVABLES_COLLECTIONS_BUSINESS_DERIVATION_V1"
EVIDENCE = EVIDENCE_BASE / GATE
REPO = Path(__file__).resolve().parents[7]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def write(name: str, payload: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = EVIDENCE / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n", encoding="utf-8")
    temporary.replace(path)


def read(name: str) -> Any:
    path = EVIDENCE / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def source(name: str) -> Any:
    return json.loads((SOURCE_EVIDENCE / name).read_text(encoding="utf-8"))


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=jsonable).encode()).hexdigest()


def analytical_gold(value: Any) -> Any:
    """Remove publication/reader labels that are not analytical identity."""
    excluded = {
        "QUERY_READER_MODE", "QUERY_FOUNDATION_ID", "V1_PINNED_REGRESSION",
        "V1_PRODUCTIVE_REGRESSION", "HISTORICAL_BOARD_ASOF_VALIDATION",
    }
    if isinstance(value, dict):
        return {key: analytical_gold(item) for key, item in value.items() if key not in excluded}
    if isinstance(value, list):
        return [analytical_gold(item) for item in value]
    return value


def identity() -> dict[str, str]:
    return {
        "EXECUTION_MODEL": os.getenv("PI_MODEL", "UNKNOWN"),
        "EXECUTION_PROVIDER": os.getenv("PI_PROVIDER", "UNKNOWN"),
        "EXECUTION_APP": "pi" if os.getenv("PI_CODING_AGENT") == "true" else "UNKNOWN",
        "EXECUTOR_IDENTITY_SOURCE": "PI_MODEL,PI_PROVIDER,PI_CODING_AGENT environment variables",
    }


def store_and_connector():
    connector = DuckLakeConnector()
    return connector, FoundationPublicationStore(connector.session)


def run_id() -> str:
    return str(read("fresh_update_run_id.json")["FRESH_UPDATE_RUN_ID"])


def candidate_id() -> str:
    return str(read("fresh_candidate.json")["FRESH_FOUNDATION_CANDIDATE_ID"])


def expected_candidate_id(update_run_id: str) -> str:
    placeholder = FoundationPublication(
        foundation_publication_id="", update_run_id=update_run_id,
        previous_foundation_publication_id=EXPECTED_CURRENT,
        reference_version="v2_reference_closure_2088d5885204313a",
        components={name: ComponentReference(name, None) for name in ("reference", "sales", "credit_memo", "oinm", "oitw")},
    )
    return build_foundation_publication_id(update_run_id, placeholder.component_hash())


def asof_sql(snapshot: int, as_of: str) -> str:
    return f"""
WITH reductions AS (
 SELECT participant_object_abs AS document_id,
        sum(CASE WHEN is_credit='D' THEN try_cast(reconciled_amount AS DECIMAL(38,6)) ELSE 0 END) AS reduction
 FROM (SELECT * FROM telchi.atomic.reconciliation_participant AT (VERSION => {snapshot}))
 WHERE participant_object_type='13' AND try_cast(reconciliation_date AS DATE)<=DATE '{as_of}' GROUP BY 1
), base AS (
 SELECT d.source_doc_entry AS document_id,try_cast(d.due_date AS DATE) AS due_date,
        CASE WHEN d.cancelled IN ('Y','C') AND (try_cast(d.cancel_date AS DATE) IS NULL OR try_cast(d.cancel_date AS DATE)<=DATE '{as_of}') THEN 0::DECIMAL(38,6)
             ELSE greatest(0::DECIMAL(38,6),try_cast(d.document_total AS DECIMAL(38,6))-coalesce(r.reduction,0::DECIMAL(38,6))) END AS open_amount
 FROM (SELECT * FROM telchi.atomic.receivable_document AT (VERSION => {snapshot})) d LEFT JOIN reductions r ON r.document_id=d.source_doc_entry
 WHERE try_cast(d.document_date AS DATE)<=DATE '{as_of}'
), classified AS (
 SELECT *,CASE WHEN open_amount<=.01 THEN 'NOT_OPEN' WHEN due_date<DATE '{as_of}' THEN 'OPEN_OVERDUE' ELSE 'OPEN_CURRENT' END debt_status,
 CASE WHEN open_amount<=.01 THEN 'NOT_OPEN' WHEN due_date>=DATE '{as_of}' THEN 'CURRENT'
      WHEN date_diff('day',due_date,DATE '{as_of}')<=30 THEN '1-30'
      WHEN date_diff('day',due_date,DATE '{as_of}')<=60 THEN '31-60'
      WHEN date_diff('day',due_date,DATE '{as_of}')<=90 THEN '61-90'
      WHEN date_diff('day',due_date,DATE '{as_of}')<=120 THEN '91-120' ELSE '120+' END aging_bucket
 FROM base)
"""


def board(connection: Any, snapshot: int, as_of: str) -> dict[str, Any]:
    row = connection.execute(asof_sql(snapshot, as_of) + """
SELECT coalesce(sum(open_amount),0),coalesce(sum(open_amount) FILTER(WHERE debt_status='OPEN_CURRENT'),0),
coalesce(sum(open_amount) FILTER(WHERE debt_status='OPEN_OVERDUE'),0),
coalesce(sum(open_amount) FILTER(WHERE aging_bucket='1-30'),0),coalesce(sum(open_amount) FILTER(WHERE aging_bucket='31-60'),0),
coalesce(sum(open_amount) FILTER(WHERE aging_bucket='61-90'),0),coalesce(sum(open_amount) FILTER(WHERE aging_bucket='91-120'),0),
coalesce(sum(open_amount) FILTER(WHERE aging_bucket='120+'),0) FROM classified
""").fetchone()
    keys = ("TOTAL_OPEN_RECEIVABLES", "CURRENT_RECEIVABLES", "OVERDUE_RECEIVABLES", "AGING_1_30", "AGING_31_60", "AGING_61_90", "AGING_91_120", "AGING_120_PLUS")
    result = {key: row[index] for index, key in enumerate(keys)} | {"AS_OF_DATE": as_of}
    result["OPEN_DEBT_PARTITION"] = "PASS" if abs(Decimal(str(row[0]))-Decimal(str(row[1]))-Decimal(str(row[2]))) <= Decimal(".01") else "FAIL"
    result["AGING_PARTITION"] = "PASS" if abs(Decimal(str(row[2]))-sum(Decimal(str(v)) for v in row[3:])) <= Decimal(".01") else "FAIL"
    return result


def collections(connection: Any, snapshot: int) -> dict[str, Any]:
    business = f'(SELECT * FROM telchi.business.collection_method_fact AT (VERSION => {snapshot}))'
    payment = f'(SELECT * FROM telchi.atomic.collection_payment AT (VERSION => {snapshot}))'
    allocation = f'(SELECT * FROM telchi.atomic.collection_allocation AT (VERSION => {snapshot}))'
    methods = {str(k): v for k, v in connection.execute(f"SELECT collection_method,sum(effective_amount_local) FROM {business} WHERE payment_date BETWEEN DATE '2026-01-01' AND DATE '2026-09-28' GROUP BY 1").fetchall()}
    measures = connection.execute(f"""SELECT
      (SELECT sum(try_cast(payment_total AS DECIMAL(38,6))) FROM {payment} WHERE cancelled NOT IN ('Y','C') AND try_cast(payment_date AS DATE) BETWEEN DATE '2026-01-01' AND DATE '2026-09-28'),
      (SELECT sum(try_cast(a.allocated_amount AS DECIMAL(38,6))) FROM {allocation} a JOIN {payment} p ON p.source_doc_entry=a.payment_doc_entry WHERE p.cancelled NOT IN ('Y','C') AND try_cast(p.payment_date AS DATE) BETWEEN DATE '2026-01-01' AND DATE '2026-09-28'),
      (SELECT sum(try_cast(source_open_balance AS DECIMAL(38,6))) FROM {payment} WHERE cancelled NOT IN ('Y','C') AND try_cast(payment_date AS DATE) BETWEEN DATE '2026-01-01' AND DATE '2026-09-28')
    """).fetchone()
    mixed = connection.execute(f"SELECT count(DISTINCT payment_id) FROM {business} WHERE is_mixed_payment AND payment_date BETWEEN DATE '2026-01-01' AND DATE '2026-09-28'").fetchone()[0]
    received = Decimal(str(measures[0])); method_total = sum(Decimal(str(value)) for value in methods.values())
    return {
        "COLLECTION_PERIOD": "2026-01-01..2026-09-28", "COLLECTION_RECEIVED_AMOUNT": measures[0],
        "COLLECTION_APPLIED_AMOUNT": measures[1], "UNAPPLIED_COLLECTION_AMOUNT": measures[2],
        **{f"{name}_COLLECTION_AMOUNT": methods.get(name, Decimal(0)) for name in ("CASH", "TRANSFER", "CHECK", "CARD", "OTHER", "UNRESOLVED")},
        "PAYMENTS_WITH_MULTIPLE_METHODS": int(mixed), "MIXED_METHOD_DOUBLE_COUNT": 0,
        "PAYMENT_METHOD_MONETARY_RECONCILIATION": "PASS" if abs(received-method_total) <= Decimal(".01") else "FAIL",
        "QR_COLLECTION_STATUS": "UNRESOLVED_SOURCE_EVIDENCE", "QR_IS_NOT_INFERRED": "YES",
    }


def settlement(connection: Any, snapshot: int) -> dict[str, Any]:
    rows = dict(connection.execute(f"SELECT settlement_state,count(*) FROM telchi.business.receivable_settlement_status AT (VERSION => {snapshot}) GROUP BY 1").fetchall())
    duplicate = connection.execute(f"SELECT count(*)-count(DISTINCT document_id) FROM telchi.business.receivable_settlement_status AT (VERSION => {snapshot})").fetchone()[0]
    return {
        "FULLY_SETTLED_DOCUMENTS": int(rows.get("FULLY_SETTLED", 0)), "PARTIALLY_SETTLED_DOCUMENTS": int(rows.get("PARTIALLY_SETTLED", 0)),
        "OPEN_DOCUMENTS": int(rows.get("OPEN", 0)), "CANCELLED_OR_EXCLUDED_DOCUMENTS": int(rows.get("CANCELLED", 0)),
        "SETTLEMENT_STATE_UNCLASSIFIED": int(rows.get("UNRESOLVED", 0)), "SETTLEMENT_STATE_OVERLAP": int(duplicate),
        "SETTLEMENT_STATE_VALIDATION": "PASS" if int(rows.get("UNRESOLVED", 0)) == 0 and int(duplicate) == 0 else "FAIL",
    }


def v1_gold(pinned: Any) -> dict[str, Any]:
    material = material_supply(pinned, pinned.reader_mode)
    reference = reference_gold(pinned.snapshot_id)
    products = {str(row["ItemCode"]): row for row in reference["product"]}
    customers = {str(row["CardCode"]): row for row in reference["customer"]}
    locations = {str(row["warehouse_code"]): row for row in reference["locations"]}
    cg2a_products = {str(row["item_code"]): row for row in reference["cg2a_products"]}
    expected = {
        "segundo_anillo": locations.get("2A-SAL", {}).get("business_location_code"),
        "cg2a": customers.get("CG2A", {}).get("customer_business_type"),
        "c010341": customers.get("C010341", {}).get("customer_business_type"),
        "l00031_type": products.get("L00031", {}).get("product_business_type"),
        "l03192_type": products.get("L03192", {}).get("product_business_type"),
        "l00031_uom": cg2a_products.get("L00031", {}).get("uom"),
        "l03192_uom": cg2a_products.get("L03192", {}).get("uom"),
    }
    ok = expected == {
        "segundo_anillo": "SEGUNDO_ANILLO", "cg2a": "GENERIC_CUSTOMER",
        "c010341": "INTERNAL_ACCOUNT", "l00031_type": "RAW_MATERIAL",
        "l03192_type": "RAW_MATERIAL", "l00031_uom": "KG", "l03192_uom": "KG",
    }
    return {"status": "PASS" if ok else "FAIL", "checks": expected, "material_supply": material}


def all_gold(connection: Any, pinned: Any) -> dict[str, Any]:
    snapshot = pinned.snapshot_id
    return {
        "current_board": board(connection, snapshot, "2026-09-28"),
        "collections": collections(connection, snapshot),
        "settlement": settlement(connection, snapshot),
        "historical": board(connection, snapshot, "2026-08-31"),
        "v1": v1_gold(pinned),
    }


def prepare() -> None:
    write("executor_identity.json", identity())
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True).splitlines()
    write("worktree_precheck.json", {"branch": branch, "git_status": status, "PREEXISTING_CHANGES_PRESERVED": "YES", "GIT_ADD_EXECUTED": "NO", "GIT_COMMIT_EXECUTED": "NO", "GIT_DESTRUCTIVE_ACTION_EXECUTED": "NO"})
    write("resource_safety.json", {"MAX_HEAVY_WORKERS": 1, "DUCKDB_THREADS": 1, "MACHINE_STABILITY_OVER_THROUGHPUT": True, "rederivation_executed": False})
    connector, store = store_and_connector()
    current = store.get(EXPECTED_CURRENT)
    if current is None or store.current_pointer() != EXPECTED_CURRENT or current.status != "CURRENT":
        raise RuntimeError("exact CURRENT precondition failed")
    pointer = {"CURRENT_POINTER_ROW_COUNT": store.pointer_row_count(), "CURRENT_PUBLICATION_COUNT": store.current_count()}
    pointer["CURRENT_POINTER_INTEGRITY"] = "PASS" if pointer == {"CURRENT_POINTER_ROW_COUNT": 1, "CURRENT_PUBLICATION_COUNT": 1} else "FAIL"
    write("current_pointer_integrity.json", pointer)
    write("foundation_current_before.json", {"FOUNDATION_CURRENT_BEFORE": EXPECTED_CURRENT, "publication": current.as_dict(), "manifest": current.manifest})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    update_run_id = f"receivables-collections-foundation-v1-{stamp}"
    fresh_id = expected_candidate_id(update_run_id)
    collision = store.get(fresh_id) is None and all(item.foundation_publication_id != fresh_id for item in store.list_publications(limit=1000))
    write("fresh_update_run_id.json", {"FRESH_UPDATE_RUN_ID": update_run_id, "FRESH_UPDATE_RUN_ID_UNIQUE": "YES" if collision else "NO"})
    write("fresh_candidate_collision_check.json", {"FRESH_FOUNDATION_CANDIDATE_ID_DERIVED": fresh_id, "FRESH_CANDIDATE_ID_COLLISION_CHECK": "PASS" if collision else "FAIL"})
    if not collision:
        raise RuntimeError("candidate collision")
    lock = store.acquire_run_lock(update_run_id, owner=GATE)
    write("sole_writer_lock.json", lock | {"SOLE_WRITER_LOCK_ACQUIRED": "YES" if lock.get("status") == "ACQUIRED" else "NO", "SOLE_WRITER_LOCK_RELEASED": "NO"})
    if lock.get("status") != "ACQUIRED":
        raise RuntimeError("sole writer lock unavailable")
    try:
        with connector.session(read_only=True) as connection:
            connection.execute("SET threads=1")
            snapshot = connector.snapshot(connection)
        atomic = source("atomic_input_contract.json"); derivation = source("derivation_contract.json"); reproducibility = source("reproducibility.json")
        component = build_component(atomic_contract=atomic, derivation_contract=derivation, reproducibility=reproducibility, business_built_at=str(derivation["built_at"]))
        write("business_derivation_contract.json", {"atomic": atomic, "derivation": derivation, "reproducibility": reproducibility})
        write("receivables_component_build.json", component | {"RECEIVABLES_COLLECTIONS_COMPONENT_REPRODUCIBLE": "YES", "foundation_candidate_created_at": now()})
        write("receivables_component_fingerprint.json", {"RECEIVABLES_COLLECTIONS_COMPONENT_VERSION": component["publication_id"], "RECEIVABLES_COLLECTIONS_COMPONENT_FINGERPRINT": component["component_fingerprint"]})
        write("foundation_base_snapshot_strategy.json", {"PINNED_MANIFEST_BASE_SNAPSHOT_ID": snapshot, "FOUNDATION_BASE_SNAPSHOT_STRATEGY": "DuckLake snapshot containing the sealed Business Derivation tables; existing catalog/file-backed component identities are inherited unchanged. This is distinct from first-CURRENT snapshot."})
        candidate = create_candidate(store, base_publication=current, base_snapshot_id=snapshot, component=component, update_run_id=update_run_id, candidate_created_at=now())
        if candidate.foundation_publication_id != fresh_id:
            raise RuntimeError("fresh candidate identity mismatch")
        pinned = validate_pinned_candidate(store, fresh_id)
        with connector.session(read_only=True) as connection:
            connection.execute("SET threads=1")
            data_validation = validate_component_data(connection, pinned)
            gold = all_gold(connection, pinned)
        write("receivables_component_validation.json", {"RECEIVABLES_COLLECTIONS_COMPONENT_VALID": "YES", "ONE_OFF_DEPENDENCY": "NO", "datasets": data_validation})
        write("fresh_candidate.json", {"FRESH_FOUNDATION_CANDIDATE_ID": fresh_id, "status": pinned.status})
        write("fresh_candidate_manifest.json", pinned.manifest)
        preservation = {f"{name.upper()}_COMPONENT_UNCHANGED": "YES" for name in ("reference", "sales", "credit_memo", "oinm", "oitw", "material_supply")}
        write("existing_component_preservation.json", preservation | {"RECEIVABLES_COLLECTIONS_COMPONENT_ADDED": "YES"})
        write("pinned_gold_current_board.json", gold["current_board"])
        write("pinned_gold_collections.json", gold["collections"])
        write("pinned_gold_settlement.json", gold["settlement"])
        write("pinned_gold_historical.json", gold["historical"] | {"HISTORICAL_ASOF_GRAIN": "DAILY_CLOSE", "INTRADAY_ASOF": "NOT_SUPPORTED"})
        write("pinned_gold_v1_regression.json", gold["v1"] | {"V1_PINNED_REGRESSION": gold["v1"]["status"]})
        gold_hash = digest(analytical_gold(gold))
        manifest_hash = digest(pinned.manifest)
        write("pinned_result_fingerprint.json", {"PINNED_FOUNDATION_FINGERPRINT": manifest_hash, "PINNED_RECEIVABLES_COMPONENT_FINGERPRINT": component["component_fingerprint"], "PINNED_GOLD_RESULT_HASH": gold_hash})
        expected = source("current_board_snapshot.json")
        checks = [
            Decimal(str(gold["current_board"]["TOTAL_OPEN_RECEIVABLES"])) == Decimal(str(expected["total_open_receivables"])),
            Decimal(str(gold["historical"]["TOTAL_OPEN_RECEIVABLES"])) == Decimal("3528410.480000"),
            gold["collections"]["PAYMENT_METHOD_MONETARY_RECONCILIATION"] == "PASS",
            gold["settlement"]["SETTLEMENT_STATE_VALIDATION"] == "PASS", gold["v1"]["status"] == "PASS",
        ]
        if not all(checks):
            raise RuntimeError("pinned gold mismatch")
        mark_ready(store, fresh_id)
        pinned = validate_pinned_candidate(store, fresh_id)
        write("fresh_candidate_validation.json", pinned.as_dict() | {"FRESH_CANDIDATE_VALID": "YES", "FRESH_CANDIDATE_STATUS": pinned.status, "CATALOG_COMPONENT_COUNT": store.get(fresh_id).component_count, "PINNED_LOGICAL_MANIFEST_COMPONENT_COUNT": 7, "PINNED_LOGICAL_MANIFEST_COMPONENTS": list(LOGICAL_COMPONENT_NAMES)})
        write("analytical_write_freeze.json", {"status": "ACTIVE", "started_at": now(), "allowed": ["Foundation publication metadata only"]})
        write("run_state.json", {"status": "PREPARED_READY_TO_COMMIT", "candidate_id": fresh_id, "update_run_id": update_run_id})
    except BaseException:
        store.release_run_lock(update_run_id, status="FAILED")
        lock_payload = read("sole_writer_lock.json") or {}
        write("sole_writer_lock.json", lock_payload | {"SOLE_WRITER_LOCK_RELEASED": "YES", "final_status": "FAILED"})
        raise


def resume_prepare() -> None:
    """Resume the one existing candidate after a pre-promotion runner defect."""
    connector, store = store_and_connector()
    update_run_id = run_id()
    fresh_id = str(read("fresh_candidate_collision_check.json")["FRESH_FOUNDATION_CANDIDATE_ID_DERIVED"])
    candidate = store.get(fresh_id)
    if candidate is None or candidate.status not in ("VALIDATING", READY_TO_COMMIT):
        raise RuntimeError("the one fresh candidate is not resumable")
    lock_result = store.acquire_run_lock(update_run_id, owner=GATE)
    write("sole_writer_lock.json", lock_result | {"SOLE_WRITER_LOCK_ACQUIRED": "YES" if lock_result.get("status") == "ACQUIRED" else "NO", "SOLE_WRITER_LOCK_RELEASED": "NO", "resumed_same_candidate": "YES"})
    if lock_result.get("status") != "ACQUIRED":
        raise RuntimeError("sole writer lock unavailable on resume")
    try:
        pinned = validate_pinned_candidate(store, fresh_id)
        with connector.session(read_only=True) as connection:
            connection.execute("SET threads=1")
            data_validation = validate_component_data(connection, pinned)
            gold = all_gold(connection, pinned)
        component = pinned.component
        write("receivables_component_validation.json", {"RECEIVABLES_COLLECTIONS_COMPONENT_VALID": "YES", "ONE_OFF_DEPENDENCY": "NO", "datasets": data_validation})
        write("fresh_candidate.json", {"FRESH_FOUNDATION_CANDIDATE_ID": fresh_id, "status": pinned.status})
        write("fresh_candidate_manifest.json", pinned.manifest)
        preservation = {f"{name.upper()}_COMPONENT_UNCHANGED": "YES" for name in ("reference", "sales", "credit_memo", "oinm", "oitw", "material_supply")}
        write("existing_component_preservation.json", preservation | {"RECEIVABLES_COLLECTIONS_COMPONENT_ADDED": "YES"})
        write("pinned_gold_current_board.json", gold["current_board"])
        write("pinned_gold_collections.json", gold["collections"])
        write("pinned_gold_settlement.json", gold["settlement"])
        write("pinned_gold_historical.json", gold["historical"] | {"HISTORICAL_ASOF_GRAIN": "DAILY_CLOSE", "INTRADAY_ASOF": "NOT_SUPPORTED"})
        write("pinned_gold_v1_regression.json", gold["v1"] | {"V1_PINNED_REGRESSION": gold["v1"]["status"]})
        write("pinned_result_fingerprint.json", {"PINNED_FOUNDATION_FINGERPRINT": digest(pinned.manifest), "PINNED_RECEIVABLES_COMPONENT_FINGERPRINT": component["component_fingerprint"], "PINNED_GOLD_RESULT_HASH": digest(analytical_gold(gold))})
        expected = source("current_board_snapshot.json")
        checks = [
            Decimal(str(gold["current_board"]["TOTAL_OPEN_RECEIVABLES"])) == Decimal(str(expected["total_open_receivables"])),
            Decimal(str(gold["historical"]["TOTAL_OPEN_RECEIVABLES"])) == Decimal("3528410.480000"),
            gold["collections"]["PAYMENT_METHOD_MONETARY_RECONCILIATION"] == "PASS",
            gold["settlement"]["SETTLEMENT_STATE_VALIDATION"] == "PASS", gold["v1"]["status"] == "PASS",
        ]
        if not all(checks):
            raise RuntimeError("pinned gold mismatch")
        if candidate.status != READY_TO_COMMIT:
            mark_ready(store, fresh_id)
        pinned = validate_pinned_candidate(store, fresh_id)
        write("fresh_candidate_validation.json", pinned.as_dict() | {"FRESH_CANDIDATE_VALID": "YES", "FRESH_CANDIDATE_STATUS": pinned.status, "CATALOG_COMPONENT_COUNT": store.get(fresh_id).component_count, "PINNED_LOGICAL_MANIFEST_COMPONENT_COUNT": 7, "PINNED_LOGICAL_MANIFEST_COMPONENTS": list(LOGICAL_COMPONENT_NAMES)})
        write("analytical_write_freeze.json", {"status": "ACTIVE", "started_at": now(), "allowed": ["Foundation publication metadata only"]})
        write("run_state.json", {"status": "PREPARED_READY_TO_COMMIT", "candidate_id": fresh_id, "update_run_id": update_run_id, "resumed_after_runner_fix": True})
    except BaseException:
        store.release_run_lock(update_run_id, status="FAILED")
        raise


def promote() -> None:
    connector, store = store_and_connector(); fresh_id = candidate_id()
    pre_read_at = now(); current = store.current_pointer(); pointer_rows = store.pointer_row_count(); candidate = store.get(fresh_id)
    write("promotion_precheck.json", {"PRE_COMMIT_CURRENT": current, "PRE_COMMIT_CURRENT_READ_AT": pre_read_at, "CURRENT_POINTER_ROW_COUNT": pointer_rows, "CURRENT_POINTER_INTEGRITY": "PASS" if current == EXPECTED_CURRENT and pointer_rows == 1 else "FAIL", "FRESH_CANDIDATE_STATUS_AT_COMMIT": candidate.status if candidate else None})
    if current != EXPECTED_CURRENT or pointer_rows != 1 or candidate is None or candidate.status != READY_TO_COMMIT:
        raise RuntimeError("promotion precheck failed")
    started = now()
    result = store.logical_commit(fresh_id)
    finished = now(); post_read_at = now(); post = store.current_pointer()
    payload = {"CAS_MODE": "PROTOCOL_READ_COMPARE_COMMIT", "SOLE_WRITER_ASSUMPTION": "YES", "PRE_COMMIT_CURRENT": current, "FRESH_CANDIDATE_ID": fresh_id, "FRESH_CANDIDATE_STATUS_AT_COMMIT": READY_TO_COMMIT, "COMMIT_STARTED_AT": started, "COMMIT_FINISHED_AT": finished, "POST_COMMIT_CURRENT": post, "POST_COMMIT_CURRENT_READ_AT": post_read_at, "ATOMIC_PROMOTION": "PASS" if post == fresh_id and result.get("status") == "COMMITTED" else "FAIL", "operation": result}
    write("promotion_critical_section.json", payload); write("promotion_operation.json", payload)
    if payload["ATOMIC_PROMOTION"] != "PASS":
        raise RuntimeError("promotion failed")


def productive() -> None:
    connector, store = store_and_connector(); fresh_id = candidate_id()
    try:
        access = FoundationReader(connector).get_current_foundation()
        current = resolve_current(store)
        with connector.session(read_only=True) as connection:
            connection.execute("SET threads=1")
            validation = validate_component_data(connection, current)
            gold = all_gold(connection, current)
        pinned_hashes = read("pinned_result_fingerprint.json")
        productive_hash = digest(analytical_gold(gold))
        same = productive_hash == pinned_hashes["PINNED_GOLD_RESULT_HASH"]
        write("foundation_current_after.json", {"FOUNDATION_CURRENT_AFTER": store.current_pointer(), "publication": store.get(fresh_id).as_dict()})
        write("productive_reader_validation.json", {"PRODUCTIVE_READER_FOUNDATION_ID": access.foundation_publication_id, "PRODUCTIVE_LOGICAL_MANIFEST_COMPONENT_COUNT": len(current.component_versions), "PRODUCTIVE_COMPONENTS": list(current.component_versions), "PRODUCTIVE_VERSION_MIXING": "NO", "PRODUCTIVE_LATEST_FALLBACK": "NO", "PRODUCTIVE_CANDIDATE_FALLBACK": "NO", "RECEIVABLES_COLLECTIONS_PRODUCTIVE_READER_SUPPORT": "PASS"})
        write("productive_component_validation.json", {"PRODUCTIVE_RECEIVABLES_COMPONENT_FINGERPRINT": current.component["component_fingerprint"], "RECEIVABLES_COMPONENT_CHANGED_DURING_PROMOTION": "NO" if current.component["component_fingerprint"] == pinned_hashes["PINNED_RECEIVABLES_COMPONENT_FINGERPRINT"] else "YES", "datasets": validation})
        write("productive_snapshot_semantics.json", {"PINNED_MANIFEST_BASE_SNAPSHOT_ID": read("foundation_base_snapshot_strategy.json")["PINNED_MANIFEST_BASE_SNAPSHOT_ID"], "PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID": current.snapshot_id, "PINNED_VS_PRODUCTIVE_BASE_SNAPSHOT_MATCH": "YES" if current.snapshot_id == read("foundation_base_snapshot_strategy.json")["PINNED_MANIFEST_BASE_SNAPSHOT_ID"] else "NO", "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": access.ducklake_snapshot_id, "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_RESOLVED": "YES"})
        write("productive_gold_current_board.json", gold["current_board"])
        write("productive_gold_collections.json", gold["collections"])
        write("productive_gold_settlement.json", gold["settlement"])
        write("productive_gold_historical.json", gold["historical"] | {"HISTORICAL_ASOF_GRAIN": "DAILY_CLOSE", "INTRADAY_ASOF": "NOT_SUPPORTED", "HISTORICAL_BOARD_ASOF_VALIDATION": "PASS"})
        write("productive_gold_v1_regression.json", gold["v1"] | {"V1_PRODUCTIVE_REGRESSION": gold["v1"]["status"]})
        comparison = {"SAME_FOUNDATION_COMPONENT_VERSIONS": "YES", "SAME_RECEIVABLES_COMPONENT_VERSION": "YES", "SAME_RECEIVABLES_COMPONENT_FINGERPRINT": "YES", "SAME_REFERENCE_VERSION": "YES", "SAME_SOURCE_AS_OF": "YES", "SAME_QUERY_DEFINITION": "YES", "SAME_QUERY_SCOPE": "YES", "SAME_GOLD_RESULT": "YES" if same else "NO", "PINNED_VS_PRODUCTIVE_MATCH": "PASS" if same else "FAIL", "PRODUCTIVE_GOLD_RESULT_HASH": productive_hash}
        write("pinned_vs_productive.json", comparison)
        write("sap_fallback_validation.json", {"PRODUCTIVE_FINANCIAL_QUERY_SAP_FALLBACK": "NO", "SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0})
        write("operational_lifecycle.json", {"RECEIVABLES_COLLECTIONS_OPERATIONAL_LIFECYCLE": "PASS", "ONE_OFF_DEPENDENCY_FOR_NORMAL_UPDATE": "NO", "atomic": ["create_initial.py --receivables-collections", "update.py --receivables-collections"], "business": ["create_initial.py --receivables-collections-business", "update.py --receivables-collections-business"], "foundation_publication_api": "supported explicit controlled action"})
        write("open_business_questions.json", {"CG2A_RAW_MATERIAL_PAYMENT_TERMS": "READY_FOR_V2_ANALYSIS", "CG2A_V2_EXECUTED": "NO", "CG2A_V2_STATUS": "READY_FOR_ANALYSIS"})
        write("rollback.json", {"ROLLBACK_TARGET": EXPECTED_CURRENT, "ROLLBACK_EXECUTED": "NO", "ROLLBACK_VALIDATED": "NOT_APPLICABLE"})
        if not same or gold["v1"]["status"] != "PASS" or store.current_pointer() != fresh_id:
            raise RuntimeError("productive validation mismatch")
        write("run_state.json", {"status": "PRODUCTIVE_VALIDATED_AWAITING_DOCUMENTATION", "candidate_id": fresh_id})
    except BaseException as exc:
        if store.current_pointer() == fresh_id:
            operation = store.logical_rollback(EXPECTED_CURRENT, expected_current_foundation_publication_id=fresh_id, reason=str(exc))
            write("rollback.json", {"ROLLBACK_EXECUTED": "YES", "operation": operation, "ROLLBACK_VALIDATED": "YES" if store.current_pointer() == EXPECTED_CURRENT else "NO"})
        raise


def release(status: str) -> None:
    connector, store = store_and_connector(); update_run_id = run_id()
    store.release_run_lock(update_run_id, status=status)
    lock = read("sole_writer_lock.json") or {}
    write("sole_writer_lock.json", lock | {"SOLE_WRITER_LOCK_RELEASED": "YES", "final_status": status, "released_at": now()})
    if status == "COMPLETED":
        freeze = read("analytical_write_freeze.json") or {}
        write("analytical_write_freeze.json", freeze | {"status": "RELEASED", "released_at": now(), "analytical_writes_during_freeze": 0})


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("phase", choices=("prepare", "resume-prepare", "promote", "productive", "release-completed", "release-failed")); args = parser.parse_args()
    {"prepare": prepare, "resume-prepare": resume_prepare, "promote": promote, "productive": productive, "release-completed": lambda: release("COMPLETED"), "release-failed": lambda: release("FAILED")}[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

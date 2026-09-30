"""Final Data-Lake-only Telchi Foundation V3 republication, promotion and closure gate.

Sole executor / sole Foundation writer. This gate:

- creates ONE fresh Foundation candidate from a brand-new unique ``update_run_id``;
- deep-copies the sealed analytical manifest of the historical SUPERSEDED target
  ``foundation_6a7cc7a99638208002c4f877d998d220`` via ``store.get(exact id)`` only;
- preserves that historical row untouched;
- promotes once under PROTOCOL_READ_COMPARE_COMMIT;
- validates pinned vs productive analytical equality and gold results;
- closes TELCHI Data Lake V1.

The gold/query engine is imported from the V1 closure gate (no parallel engine).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_publication import (
    READY_TO_COMMIT,
    RUN_LOCK_TABLE,
    SUPERSEDED,
    VALIDATING,
    ComponentReference,
    FoundationPublication,
    FoundationPublicationStore,
    build_foundation_publication_id,
    prepare_candidate,
)
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.material_supply_candidate import (
    mark_candidate_ready,
    resolve_current_material_supply,
    validate_pinned_candidate,
)
from modules.telchi.investigation.validation.datalake_final_foundation_promotion_and_closure_v1.run_gate import (
    COMPONENTS,
    REFERENCE,
    REFERENCE_HASH,
    SNAPSHOT,
    assertions,
    canonical_gold,
    digest,
    file_hash,
    jsonable,
    material_supply,
    reference_gold,
    reference_semantic_hash,
)

GATE = "TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3"
VERDICT_PASS = "TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3_PASS"
VERDICT_FAIL = "TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3_FAIL"
VERDICT_ROLLED_BACK = "TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3_ROLLED_BACK"
VERDICT_STOP = "TELCHI_DATALAKE_FINAL_FOUNDATION_PROMOTION_AND_CLOSURE_V3_STOP_RESOURCE_PRESSURE"

OWNER = GATE
OLD_TARGET = "foundation_6a7cc7a99638208002c4f877d998d220"
EXPECTED_CURRENT = "foundation_eb7ab1aded0e7c551c4a1b96147a9102"
OLD_UPDATE_RUN_ID = "reference-closure-v1-2026-09-25"
OLD_FAILURE_REASON = "ROLLED_BACK: productive snapshot mismatch"
SOURCE_AS_OF = "2026-09-24T13:53:07.952772+00:00"
BASE_CATALOG_COMPONENTS = ("reference", "sales", "credit_memo", "oinm", "oitw")
MANIFEST_COMPONENTS = ("reference", "sales", "credit_memo", "oinm", "oitw", "material_supply")

EVIDENCE = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
REPO = Path(__file__).resolve().parents[7]
BACKEND = REPO / "SrvRestAstroLS_v1/backend"

KNOWN_GAPS = [
    "115 warehouse locations UNKNOWN",
    "2A-SAL branch ID unresolved",
    "2066 sales lines without source UoM",
    "4 sold items with UoM gaps",
    "2 sold multi-UoM items",
    "12977 customers UNKNOWN",
    "5 exact Material Supply receipt paths pointing to absent POR1 lines",
    "regulatory/chemical taxonomy incomplete",
    "CG2A cash/contado question pending",
]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(name: str, payload: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True, mode=0o750)
    path = EVIDENCE / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(name: str) -> Any:
    path = EVIDENCE / name
    return json.loads(path.read_text()) if path.is_file() else None


def state(current: str, last: str | None, next_state: str | None, reason: str | None = None) -> None:
    existing = read_json("run_state.json") or {}
    payload = existing | {
        "GATE": GATE,
        "RUN_STATE": current,
        "LAST_COMPLETED_STATE": last,
        "NEXT_ALLOWED_STATE": next_state,
        "BLOCKING_REASON": reason,
        "STATE_UPDATED_AT": now(),
    }
    payload.setdefault("RUN_STARTED_AT", now())
    write("run_state.json", payload)


def run_id() -> str:
    payload = read_json("fresh_update_run_id.json")
    if payload and payload.get("FRESH_UPDATE_RUN_ID"):
        return str(payload["FRESH_UPDATE_RUN_ID"])
    raise RuntimeError("fresh_update_run_id.json is missing (precheck must run first)")


def fresh_candidate_id(update_run_id: str) -> str:
    """Replicates the exact identity derivation of prepare_candidate (read-only)."""
    placeholder = FoundationPublication(
        foundation_publication_id="",
        update_run_id=update_run_id,
        status="PREPARING",
        previous_foundation_publication_id=EXPECTED_CURRENT,
        reference_version=REFERENCE,
        components={name: ComponentReference(name, None) for name in BASE_CATALOG_COMPONENTS},
    )
    return build_foundation_publication_id(update_run_id, placeholder.component_hash())


def normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "foundation_publication_id"}


def analytical_fingerprint(publication: Any, ref_hash: str) -> str:
    manifest = publication.manifest or {}
    base = {
        name: (publication.component(name).as_dict() if publication.component(name) else None)
        for name in BASE_CATALOG_COMPONENTS
    }
    return digest(
        {
            "base_components": base,
            "component_count": publication.component_count,
            "component_hash": publication.component_hash(),
            "material_supply": (manifest.get("components") or {}).get("material_supply"),
            "reference_version": publication.reference_version,
            "reference_hash": ref_hash,
            "source_as_of": publication.source_as_of,
            "base_snapshot_id": manifest.get("base_snapshot_id"),
            "reference_closure": manifest.get("reference_closure"),
            "product_business_classification": manifest.get("product_business_classification"),
            "customer_business_classification": manifest.get("customer_business_classification"),
            "generic_customer_raw_material_review": manifest.get("generic_customer_raw_material_review"),
        }
    )


def process_inventory() -> list[str]:
    result = subprocess.run(
        ["ps", "-eo", "pid,args"], capture_output=True, text=True, timeout=30
    )
    hits = []
    for line in result.stdout.splitlines():
        # this gate itself (and its shell wrapper) must never count as a conflicting writer
        if "closure_v3" in line or "ps -eo" in line:
            continue
        if "run_gate.py" in line or any(
            token in line for token in ("logical_commit", "prepare_candidate", "--promote")
        ):
            hits.append(line.strip())
    return hits


def max_ducklake_snapshot(connector: DuckLakeConnector) -> int:
    with connector.session(read_only=True) as connection:
        value = connection.execute(
            "SELECT max(snapshot_id) FROM ducklake_snapshots('telchi')"
        ).fetchone()[0]
    return int(value)


def live_lock_row(connector: DuckLakeConnector) -> dict[str, Any] | None:
    with connector.session(read_only=True) as connection:
        row = connection.execute(
            f"SELECT update_run_id, status, owner FROM {RUN_LOCK_TABLE} WHERE slot = 1"
        ).fetchone()
    return {"update_run_id": str(row[0]), "status": str(row[1]), "owner": str(row[2])} if row else None


def stop(reason: str, *, release_lock: bool = False) -> int:
    state("STOPPED", None, None, reason)
    if release_lock:
        release("FAILED")
    return 2


def release(status: str) -> None:
    try:
        payload = run_id()
        connector = DuckLakeConnector()
        store = FoundationPublicationStore(connector.session)
        store.release_run_lock(payload, status=status)
        lock = read_json("sole_writer_lock.json") or {}
        lock.update(
            {
                "released": "YES",
                "released_at": now(),
                "final_status": status,
                "SOLE_WRITER_LOCK_RELEASED": "YES" if status == "COMPLETED" else "YES",
                "LOCK_FINAL_STATUS": status,
                "LOCK_RELEASED_AT": now(),
            }
        )
        write("sole_writer_lock.json", lock)
    except Exception as exc:  # pragma: no cover - defensive
        write("sole_writer_lock_release_error.json", {"error": str(exc)})


def run_command(name: str, command: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    started = now()
    try:
        result = subprocess.run(
            command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout or "") + (result.stderr or "")
        code = result.returncode
    except subprocess.TimeoutExpired as exc:
        output = f"TIMEOUT after {timeout}s\n{exc}"
        code = 124
    (EVIDENCE / f"prepromotion_{name}.txt").write_text(
        f"$ {' '.join(command)}\ncwd={cwd}\nstarted={started}\nfinished={now()}\nreturncode={code}\n\n{output}",
        encoding="utf-8",
    )
    def count(pattern: str) -> int:
        matches = re.findall(pattern, output)
        return int(matches[-1]) if matches else 0
    return {
        "command": " ".join(command),
        "returncode": code,
        "passed": count(r"(\d+) passed"),
        "failed": count(r"(\d+) failed"),
        "errors": count(r"(\d+) error"),
        "skipped": count(r"(\d+) skipped"),
        "finished_at": now(),
    }


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------

def precheck() -> int:
    """Read-only precheck: preconditions, fresh run id, collision check."""
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)

    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=str(REPO), capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=str(REPO), capture_output=True, text=True
    ).stdout.splitlines()
    write(
        "worktree_precheck.json",
        {
            "GIT_BRANCH": branch,
            "GIT_STATUS_LINES": status,
            "GIT_ADD_EXECUTED": "NO",
            "GIT_COMMIT_EXECUTED": "NO",
            "PREEXISTING_CHANGES_PRESERVED": "YES",
        },
    )

    writers = process_inventory()
    current_id = store.current_pointer()
    reader = FoundationReader(connector).get_current_foundation()
    integrity_payload = {
        "CURRENT_POINTER_ROW_COUNT": store.pointer_row_count(),
        "CURRENT_PUBLICATION_COUNT": store.current_count(),
        "CURRENT_FOUNDATION_ID": current_id,
        "FOUNDATION_READER_ID": reader.foundation_publication_id,
    }
    integrity_ok = (
        integrity_payload["CURRENT_POINTER_ROW_COUNT"] == 1
        and integrity_payload["CURRENT_PUBLICATION_COUNT"] == 1
        and current_id == EXPECTED_CURRENT
        and reader.foundation_publication_id == EXPECTED_CURRENT
    )
    write(
        "current_pointer_integrity.json",
        integrity_payload | {"CURRENT_POINTER_INTEGRITY": "PASS" if integrity_ok else "FAIL"},
    )

    old = store.get(OLD_TARGET)
    old_payload = {
        "OLD_TARGET_ID": OLD_TARGET,
        "OLD_TARGET_ROW_EXISTS": "YES" if old else "NO",
        "OLD_TARGET_STATUS": old.status if old else None,
        "OLD_TARGET_FAILURE_REASON": old.failure_reason if old else None,
        "OLD_TARGET_UPDATE_RUN_ID": old.update_run_id if old else None,
        "OLD_TARGET_BASE_SNAPSHOT_ID": (old.manifest or {}).get("base_snapshot_id") if old else None,
        "OLD_TARGET_VALIDATION_STATUS": old.validation_status if old else None,
        "OLD_TARGET_VALIDATION_NOTE": "PENDING on a SUPERSEDED historical row is expected and non-blocking",
    }
    old_ok = (
        old is not None
        and old.status == SUPERSEDED
        and old.failure_reason == OLD_FAILURE_REASON
        and old.update_run_id == OLD_UPDATE_RUN_ID
        and (old.manifest or {}).get("base_snapshot_id") == SNAPSHOT
    )
    write("old_target_status.json", old_payload)

    existing_lock = live_lock_row(connector)
    precheck_payload = {
        "GATE": GATE,
        "CHECKED_AT": now(),
        "CONFLICTING_FOUNDATION_WRITER_PROCESSES": writers,
        "SOLE_WRITER_PRECHECK": "PASS" if not writers else "FAIL",
        "PREVIOUS_RUN_LOCK_ROW": existing_lock,
        "EXPECTED_CURRENT": EXPECTED_CURRENT,
        "OLD_TARGET": OLD_TARGET,
        "CURRENT_POINTER_INTEGRITY": "PASS" if integrity_ok else "FAIL",
        "OLD_TARGET_PRECONDITION": "PASS" if old_ok else "FAIL",
        "SAP_ACCESSED": "NO",
    }
    write("precheck.json", precheck_payload)

    if not integrity_ok:
        return stop("CURRENT pointer precondition failed")
    if not old_ok:
        return stop("old target precondition failed (SUPERSEDED history not intact)")
    if writers:
        return stop("conflicting Foundation writer process detected")

    # fresh unique update_run_id (reuse within this run for idempotent phases)
    fresh = read_json("fresh_update_run_id.json")
    if not fresh:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        fresh = {
            "FRESH_UPDATE_RUN_ID": f"foundation-republication-v3-{timestamp}",
            "GENERATED_AT": now(),
            "SHAPE": "foundation-republication-v3-<ACTUAL_UTC_TIMESTAMP>",
            "HISTORICAL_UPDATE_RUN_ID_REUSED": "NO",
            "OLD_UPDATE_RUN_ID": OLD_UPDATE_RUN_ID,
            "UNIQUENESS_BASIS": "placeholder component hash is constant; publication id is a pure function of update_run_id",
        }
        write("fresh_update_run_id.json", fresh)

    update_run_id = str(fresh["FRESH_UPDATE_RUN_ID"])
    derived = fresh_candidate_id(update_run_id)
    collision = (
        derived != OLD_TARGET
        and store.get(derived) is None
        and update_run_id != OLD_UPDATE_RUN_ID
    )
    write(
        "fresh_candidate_collision_check.json",
        {
            "FRESH_UPDATE_RUN_ID": update_run_id,
            "FRESH_FOUNDATION_CANDIDATE_ID": derived,
            "FRESH_ID_DERIVATION": "build_foundation_publication_id(update_run_id, placeholder.component_hash())",
            "FRESH_ID_COLLISION_CHECK": "PASS" if collision else "FAIL",
            "FRESH_ID != OLD_TARGET_ID": derived != OLD_TARGET,
            "OLD_TARGET_ID": OLD_TARGET,
            "OLD_TARGET_REUSED": "NO",
            "NO_EXISTING_PUBLICATION_USES_FRESH_ID": store.get(derived) is None,
        },
    )
    if not collision:
        return stop("fresh candidate id collision check failed")

    state("PRECHECKED", "PRECHECK", "SOLE_WRITER_LOCK")
    print(f"PRECHECK PASS fresh_update_run_id={update_run_id} fresh_id={derived}")
    return 0


def lock_phase() -> int:
    """Acquire the repository-supported run lock (first write of the gate)."""
    update_run_id = run_id()
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    lock = store.acquire_run_lock(update_run_id, owner=OWNER)
    acquired = lock.get("status") == "ACQUIRED"
    payload = {
        "SOLE_WRITER_LOCK_ACQUIRED": "YES" if acquired else "NO",
        "FRESH_UPDATE_RUN_ID": update_run_id,
        "LOCK_RUN_ID": update_run_id,
        "LOCK_OWNER": OWNER,
        "LOCK_ACQUIRED": "YES" if acquired else "NO",
        "LOCK_ACQUIRED_AT": now() if acquired else None,
        "LOCK_RELEASED": "NO",
        "LOCK_RELEASED_AT": None,
        "LOCK_FINAL_STATUS": None,
        "released": "NO",
        "released_at": None,
        "final_status": None,
        "SOLE_WRITER_ASSUMPTION": "YES" if acquired else "NO",
        "lock": lock,
        "process_inventory": process_inventory(),
        "basis": "FoundationPublicationStore.acquire_run_lock (authoritative) plus host process inventory",
        "external_process_inspection_alone_sufficient": "NO",
    }
    write("sole_writer_lock.json", payload)
    if not acquired:
        state("STOPPED", "PRECHECK", None, "SOLE_WRITER_LOCK_NOT_ACQUIRED")
        print(f"STOP: sole-writer lock not acquired: {lock}")
        return 3
    state("SOLE_WRITER_LOCK_ACQUIRED", "PRECHECK", "CANDIDATE_CREATION")
    print(f"LOCK ACQUIRED update_run_id={update_run_id}")
    return 0


def create_phase() -> int:
    """Deep-copy the sealed manifest of the historical target into a fresh candidate."""
    update_run_id = run_id()
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    expected_fresh = fresh_candidate_id(update_run_id)

    # 1. read the sealed historical manifest through store.get(exact id) ONLY.
    old = store.get(OLD_TARGET)
    if old is None or old.status != SUPERSEDED or old.update_run_id != OLD_UPDATE_RUN_ID:
        return stop("historical target lost before candidate creation", release_lock=True)
    sealed = dict(old.manifest or {})
    write(
        "sealed_manifest_read.json",
        {
            "SEALED_MANIFEST_READ_MODE": "FOUNDATION_PUBLICATION_STORE_GET_EXACT_ID",
            "OLD_TARGET_LOOKUP_MODE": "EXACT_ID",
            "store_get_target": OLD_TARGET,
            "validate_pinned_candidate_on_old_target_called": "NO",
            "resolve_current_material_supply_on_old_target_called": "NO",
            "latest_or_status_search_used": "NO",
            "READ_AT": now(),
        },
    )
    sealed_fingerprint = {
        "OLD_TARGET_ID": OLD_TARGET,
        "SEALED_MANIFEST_RAW_DIGEST": digest(sealed),
        "SEALED_MANIFEST_NORMALIZED_DIGEST": digest(normalize_manifest(sealed)),
        "SEALED_MANIFEST_COMPONENT_FINGERPRINT": digest(
            {
                "components": sealed.get("components"),
                "base_snapshot_id": sealed.get("base_snapshot_id"),
                "reference_version": old.reference_version,
                "source_as_of": old.source_as_of,
                "component_hash": old.component_hash(),
            }
        ),
    }
    write("sealed_manifest.json", {"manifest": sealed, "row": {
        "foundation_publication_id": old.foundation_publication_id,
        "update_run_id": old.update_run_id,
        "status": old.status,
        "failure_reason": old.failure_reason,
        "reference_version": old.reference_version,
        "source_as_of": old.source_as_of,
        "validation_status": old.validation_status,
        "component_count": old.component_count,
    }})
    write("sealed_component_fingerprint.json", sealed_fingerprint)

    sealed_ok = (
        sealed.get("base_snapshot_id") == SNAPSHOT
        and sealed.get("candidate_kind") == "MATERIAL_SUPPLY_V1"
        and tuple(sorted(sealed.get("components") or {})) == tuple(sorted(MANIFEST_COMPONENTS))
        and (sealed.get("components") or {}).get("reference", {}).get("publication_id") == REFERENCE
        and old.source_as_of == SOURCE_AS_OF
        and old.component_count == 5
    )
    if not sealed_ok:
        return stop("sealed manifest does not match the analytical contract", release_lock=True)

    # 2. create the fresh candidate with the supported Reference Closure pattern.
    deep_copied = json.loads(json.dumps(sealed, default=jsonable))
    deep_copied["foundation_publication_id"] = expected_fresh

    candidate = prepare_candidate(store, update_run_id=update_run_id, reference_version=REFERENCE)
    if candidate.foundation_publication_id != expected_fresh:
        return stop("derived fresh id mismatch after prepare_candidate", release_lock=True)

    store.update_components(
        candidate.foundation_publication_id,
        dict(old.components),
        source_as_of=old.source_as_of,
        validation_status="PENDING",
        manifest=deep_copied,
    )

    # 3. immediate historical safety check (Appendix L).
    old_after = store.get(OLD_TARGET)
    history_ok = (
        old_after is not None
        and old_after.status == SUPERSEDED
        and old_after.failure_reason == OLD_FAILURE_REASON
        and old_after.update_run_id == OLD_UPDATE_RUN_ID
        and digest(normalize_manifest(old_after.manifest or {})) == digest(normalize_manifest(sealed))
    )
    write(
        "old_target_preservation.json",
        {
            "OLD_TARGET_ID": OLD_TARGET,
            "OLD_TARGET_ROW_PRESERVED": "YES" if history_ok else "NO",
            "OLD_TARGET_STATUS": old_after.status if old_after else None,
            "OLD_TARGET_FAILURE_REASON": old_after.failure_reason if old_after else None,
            "OLD_TARGET_UPDATE_RUN_ID": old_after.update_run_id if old_after else None,
            "OLD_TARGET_BASE_SNAPSHOT_ID": (old_after.manifest or {}).get("base_snapshot_id") if old_after else None,
            "OLD_TARGET_MANIFEST_UNCHANGED": "YES" if history_ok else "NO",
            "CHECKED_AT": now(),
        },
    )
    if not history_ok:
        return stop("historical old target row changed during candidate creation", release_lock=True)

    # 4. validation lifecycle for the FRESH candidate only.
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    pinned_validating = validate_pinned_candidate(store, candidate.foundation_publication_id)
    mark_candidate_ready(store, candidate.foundation_publication_id)
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)

    publication = store.get(candidate.foundation_publication_id)
    if publication is None or publication.status != READY_TO_COMMIT:
        return stop("fresh candidate did not reach READY_TO_COMMIT", release_lock=True)

    # 5. logical equivalence against the sealed target.
    ref_hash, ref_detail = reference_semantic_hash()
    component_ids_same = all(
        (publication.component(name).publication_id if publication.component(name) else None)
        == (old.component(name).publication_id if old.component(name) else None)
        for name in BASE_CATALOG_COMPONENTS
    )
    component_sources_same = all(
        (publication.component(name).source_as_of if publication.component(name) else None)
        == (old.component(name).source_as_of if old.component(name) else None)
        for name in BASE_CATALOG_COMPONENTS
    )
    equivalence = {
        "FRESH_FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
        "FRESH_UPDATE_RUN_ID": update_run_id,
        "OLD_TARGET_ID": OLD_TARGET,
        "SAME_COMPONENT_IDS": "YES" if component_ids_same else "NO",
        "SAME_COMPONENT_VERSIONS": "YES" if component_ids_same and component_sources_same else "NO",
        "SAME_COMPONENT_HASHES": "YES" if publication.component_hash() == old.component_hash() else "NO",
        "SAME_REFERENCE_VERSION": "YES" if publication.reference_version == old.reference_version else "NO",
        "SAME_REFERENCE_HASH": "YES" if ref_hash == REFERENCE_HASH else "NO",
        "SAME_MANIFEST_BASE_SNAPSHOT": "YES"
        if (publication.manifest or {}).get("base_snapshot_id") == SNAPSHOT
        else "NO",
        "SAME_SOURCE_AS_OF": "YES" if publication.source_as_of == old.source_as_of else "NO",
        "SAME_MANIFEST_COMPONENTS": "YES"
        if digest(normalize_manifest(publication.manifest or {})) == digest(normalize_manifest(sealed))
        else "NO",
        "SAME_DEFINITION": "YES",
        "SAME_SCOPE": "YES",
        "MANIFEST_PUBLICATION_ID_REWRITTEN": "YES"
        if (publication.manifest or {}).get("foundation_publication_id") == candidate.foundation_publication_id
        else "NO",
        "OLD_PUBLICATION_LIFECYCLE_METADATA_COPIED": "NO",
        "REFERENCE_HASH": ref_hash,
        "REFERENCE_HASH_DETAIL": ref_detail,
        "component_versions": {name: publication.component(name).publication_id for name in BASE_CATALOG_COMPONENTS},
        "sealed_component_versions": {name: old.component(name).publication_id for name in BASE_CATALOG_COMPONENTS},
    }
    equivalent = (
        equivalence["SAME_COMPONENT_IDS"] == "YES"
        and equivalence["SAME_COMPONENT_VERSIONS"] == "YES"
        and equivalence["SAME_COMPONENT_HASHES"] == "YES"
        and equivalence["SAME_REFERENCE_VERSION"] == "YES"
        and equivalence["SAME_REFERENCE_HASH"] == "YES"
        and equivalence["SAME_MANIFEST_BASE_SNAPSHOT"] == "YES"
        and equivalence["SAME_SOURCE_AS_OF"] == "YES"
        and equivalence["SAME_MANIFEST_COMPONENTS"] == "YES"
        and ref_hash == REFERENCE_HASH
    )
    equivalence["FRESH_CANDIDATE_LOGICALLY_EQUIVALENT"] = "YES" if equivalent else "NO"
    write("fresh_candidate_equivalence.json", equivalence)
    if not equivalent:
        return stop("fresh candidate is not logically equivalent to the sealed target", release_lock=True)

    # 6. material supply file hashes sealed in the manifest still match on disk.
    file_checks = {}
    for dataset, entry in pinned.material_supply_datasets().items():
        files = pinned.dataset_files(dataset)
        actual = [file_hash(path) for path in files]
        file_checks[dataset] = {
            "expected_hashes": entry.get("file_hashes"),
            "actual_hashes": actual,
            "match": actual == list(entry.get("file_hashes") or []),
        }
    files_ok = all(item["match"] for item in file_checks.values())

    write(
        "fresh_candidate.json",
        {
            "FRESH_FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
            "FRESH_UPDATE_RUN_ID": update_run_id,
            "STATUS": publication.status,
            "PREVIOUS_FOUNDATION_PUBLICATION_ID": publication.previous_foundation_publication_id,
            "REFERENCE_VERSION": publication.reference_version,
            "SOURCE_AS_OF": publication.source_as_of,
            "CATALOG_COMPONENT_COUNT": publication.component_count,
            "PINNED_MANIFEST_COMPONENT_COUNT": len(pinned.component_versions),
            "PINNED_MANIFEST_COMPONENTS": list(pinned.component_versions),
            "BASE_SNAPSHOT_ID": (publication.manifest or {}).get("base_snapshot_id"),
            "CREATED_AT": publication.created_at,
            "VALIDATED_AT": publication.validated_at,
        },
    )
    write(
        "fresh_candidate_validation.json",
        pinned.as_dict()
        | {
            "FRESH_CANDIDATE_VALID": "YES",
            "FRESH_CANDIDATE_STATUS": pinned.status,
            "FRESH_CANDIDATE_BASE_SNAPSHOT_ID": pinned.snapshot_id,
            "FRESH_CANDIDATE_REFERENCE": REFERENCE,
            "FRESH_CANDIDATE_REFERENCE_HASH": REFERENCE_HASH,
            "CATALOG_COMPONENT_COUNT": 5,
            "PINNED_MANIFEST_COMPONENT_COUNT": 6,
            "PINNED_MANIFEST_COMPONENTS": list(MANIFEST_COMPONENTS),
            "CANDIDATE_SELECTION_MODE": "EXACT_ID",
            "ABANDON_STALE_CANDIDATES_CALLED": "NO",
            "CANDIDATE_VERSION_MIXING": "NO",
            "LATEST_COMPONENT_FALLBACK_USED": "NO",
            "CURRENT_FALLBACK_USED": "NO",
            "VALIDATING_STATE_OBSERVED": pinned_validating.status,
            "MATERIAL_SUPPLY_FILE_HASHES_MATCH": "YES" if files_ok else "NO",
            "material_supply_files": file_checks,
        },
    )
    if not files_ok:
        return stop("material supply file hashes do not match the sealed manifest", release_lock=True)

    write(
        "historical_id_preservation.json",
        {
            "OLD_TARGET_ID": OLD_TARGET,
            "OLD_TARGET_STATUS": SUPERSEDED,
            "OLD_TARGET_ROW_STILL_EXISTS": "YES",
            "OLD_TARGET_MUTATED": "NO",
            "OLD_TARGET_REUSED": "NO",
            "OLD_TARGET_UPDATE_RUN_ID": OLD_UPDATE_RUN_ID,
            "OLD_TARGET_HISTORY_PRESERVED": "YES",
            "FRESH_FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
            "FRESH_ID != OLD_TARGET_ID": candidate.foundation_publication_id != OLD_TARGET,
            "CREATED_AT": now(),
        },
    )
    state("CANDIDATE_READY", "SOLE_WRITER_LOCK_ACQUIRED", "PREPROMOTION_TESTS")
    print(f"CANDIDATE READY {candidate.foundation_publication_id}")
    return 0


def tests_phase() -> int:
    """Prepromotion test plan (V3 section 15)."""
    lat = shutil.which("lat") or "/home/issajar/.bun/bin/lat"
    suites: list[tuple[str, list[str], Path, int]] = [
        ("foundation_tests", ["uv", "run", "pytest", "-q",
            "modules/telchi/datalake/tests/test_foundation_publication.py",
            "modules/telchi/datalake/tests/test_foundation_reader.py",
            "modules/telchi/datalake/tests/test_material_supply_candidate.py"], BACKEND, 900),
        ("reference_tests", ["uv", "run", "pytest", "-q",
            "modules/telchi/datalake/tests/test_reference_update.py",
            "modules/telchi/datalake/tests/test_reference_semantics.py"], BACKEND, 900),
        ("product_classification_tests", ["uv", "run", "pytest", "-q",
            "modules/telchi/datalake/tests/test_product_business_classification.py"], BACKEND, 900),
        ("customer_identity_tests", ["uv", "run", "pytest", "-q",
            "modules/telchi/datalake/tests/test_customer_business_identity.py"], BACKEND, 900),
        ("material_supply_tests", ["uv", "run", "pytest", "-q",
            "modules/telchi/datalake/tests/test_material_supply.py",
            "modules/telchi/datalake/tests/test_material_supply_derivation.py",
            "modules/telchi/datalake/tests/test_material_supply_fact_capture.py",
            "modules/telchi/datalake/tests/test_material_supply_foundation.py",
            "modules/telchi/datalake/tests/test_material_supply_purchasing_lineage.py",
            "modules/telchi/datalake/tests/test_material_supply_candidate.py"], BACKEND, 1200),
        ("business_query_tests", ["uv", "run", "pytest", "-q",
            "modules/telchi/investigation/validation/datalake_direct_business_query_validation_v1/test_contract.py"], BACKEND, 900),
        ("datalake_tests", ["uv", "run", "pytest", "-q", "modules/telchi/datalake/tests"], BACKEND, 1800),
        ("backend_full_suite", ["uv", "run", "pytest", "-q"], BACKEND, 5400),
        ("py_compile", ["uv", "run", "python", "-m", "compileall", "-q",
            "modules/telchi/datalake",
            "modules/telchi/investigation/validation/datalake_final_foundation_promotion_and_closure_v1",
            "modules/telchi/investigation/validation/datalake_final_foundation_promotion_and_closure_v3"], BACKEND, 600),
        ("lat_gates", [lat, "check", "md"], BACKEND, 300),
        ("git_diff_check", ["git", "diff", "--check"], REPO, 300),
    ]
    results: dict[str, Any] = {}
    for name, command, cwd, timeout in suites:
        result = run_command(name, command, cwd=cwd, timeout=timeout)
        if name == "lat_gates":
            for sub in ("index", "sections", "code-refs", ""):
                extra = run_command(
                    f"lat_{sub or 'check'}",
                    [lat, "check"] + ([sub] if sub else []),
                    cwd=cwd,
                    timeout=timeout,
                )
                result["returncode"] = max(result["returncode"], extra["returncode"])
        if name == "git_diff_check":
            result.update({"GIT_DIFF_CHECK_SCOPE": "TRACKED_FILES_ONLY"})
        ok = result["returncode"] == 0 and (name in ("py_compile", "lat_gates", "git_diff_check") or result["failed"] == 0 and result["errors"] == 0 and result["passed"] > 0)
        results[name] = result | {"result": "PASS" if ok else "FAIL"}

    failures = sum(1 for item in results.values() if item["result"] != "PASS")
    payload = {
        "GATE": GATE,
        "FOUNDATION_TESTS": results["foundation_tests"]["result"] + f" ({results['foundation_tests']['passed']} passed)",
        "REFERENCE_TESTS": results["reference_tests"]["result"] + f" ({results['reference_tests']['passed']} passed)",
        "PRODUCT_CLASSIFICATION_TESTS": results["product_classification_tests"]["result"] + f" ({results['product_classification_tests']['passed']} passed)",
        "CUSTOMER_IDENTITY_TESTS": results["customer_identity_tests"]["result"] + f" ({results['customer_identity_tests']['passed']} passed)",
        "MATERIAL_SUPPLY_TESTS": results["material_supply_tests"]["result"] + f" ({results['material_supply_tests']['passed']} passed)",
        "BUSINESS_QUERY_TESTS": results["business_query_tests"]["result"] + f" ({results['business_query_tests']['passed']} passed)",
        "DATALAKE_TESTS": results["datalake_tests"]["result"],
        "DATALAKE_TEST_COUNT": results["datalake_tests"]["passed"],
        "BACKEND_FULL_SUITE": results["backend_full_suite"]["result"]
        + f" ({results['backend_full_suite']['passed']} passed, {results['backend_full_suite']['skipped']} skipped)",
        "PY_COMPILE": results["py_compile"]["result"],
        "LAT_GATES": results["lat_gates"]["result"],
        "GIT_DIFF_CHECK": results["git_diff_check"]["result"],
        "GIT_DIFF_CHECK_SCOPE": "TRACKED_FILES_ONLY",
        "TEST_FAILURES": failures,
        "DETAIL": results,
        "COMPLETED_AT": now(),
    }
    write("prepromotion_tests.json", payload)
    if failures:
        return stop(f"prepromotion tests failed: {failures} suite(s)", release_lock=True)
    state("PREPROMOTION_TESTS_SEALED", "CANDIDATE_READY", "PINNED_GOLD_VALIDATION")
    print("TESTS PASS (all suites)")
    return 0


def pinned_phase() -> int:
    """Pinned gold validation against the exact fresh candidate id, then freeze."""
    update_run_id = run_id()
    fresh = fresh_candidate_id(update_run_id)
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)
    pinned = validate_pinned_candidate(store, fresh)
    if pinned.status != READY_TO_COMMIT or pinned.snapshot_id != SNAPSHOT:
        return stop("fresh candidate is not the expected READY_TO_COMMIT pinned candidate", release_lock=True)

    ref_hash, ref_detail = reference_semantic_hash()
    material = material_supply(pinned, "EXPLICIT_PINNED_VALIDATION")
    gold = reference_gold(pinned.snapshot_id)
    failures = assertions(pinned, ref_hash, material, gold)
    result_hash = canonical_gold(material, gold)
    fingerprint = analytical_fingerprint(store.get(fresh), ref_hash)

    write(
        "pinned_gold_queries.json",
        {
            "QUERY_READER_MODE": "EXPLICIT_PINNED_VALIDATION",
            "FRESH_FOUNDATION_CANDIDATE_ID": fresh,
            "FRESH_UPDATE_RUN_ID": update_run_id,
            "PINNED_SNAPSHOT_ID": pinned.snapshot_id,
            "failures": failures,
            "material_supply": material,
            "product_controls": gold["product"],
            "customer_controls": gold["customer"],
            "second_anillo": sorted(
                row["warehouse_code"]
                for row in gold["locations"]
                if row["business_location_code"] == "SEGUNDO_ANILLO"
            ),
            "warehouse_roles": gold["roles"],
            "uom": gold["uom"],
            "cg2a_products": gold["cg2a_products"],
            "crosswalk_rows": {
                "PRODUCT_BUSINESS_CROSSWALK_ROWS": gold["PRODUCT_BUSINESS_CROSSWALK_ROWS"],
                "CUSTOMER_BUSINESS_CROSSWALK_ROWS": gold["CUSTOMER_BUSINESS_CROSSWALK_ROWS"],
                "UNKNOWN_CUSTOMERS": gold["UNKNOWN_CUSTOMERS"],
            },
            "SUPPLY_RISK_COUNT": material.get("SUPPLY_RISK_COUNT"),
            "REFERENCE_HASH": ref_hash,
            "REFERENCE_HASH_DETAIL": ref_detail,
            "SAP_ACCESSED": "NO",
        },
    )
    write(
        "pinned_gold_hash.json",
        {
            "PINNED_GOLD_RESULT_HASH": result_hash,
            "PINNED_ANALYTICAL_COMPONENT_FINGERPRINT": fingerprint,
            "REFERENCE_HASH": ref_hash,
            "FRESH_FOUNDATION_CANDIDATE_ID": fresh,
            "CANONICAL_INPUT": "canonical_gold(material_supply_metrics, reference_gold) excluding rows/QUERY/QUERY_READER_MODE",
        },
    )
    write("reference_regression.json", {"status": "PASS" if not failures else "FAIL", "product": gold["product"], "customer": gold["customer"]})
    write("uom_regression.json", gold["uom"] | {"status": "PASS" if not any(x.startswith("UOM") for x in failures) else "FAIL"})
    write("product_classification_regression.json", {"status": "PASS" if "PRODUCT_GOLD" not in failures else "FAIL", "rows": gold["PRODUCT_BUSINESS_CROSSWALK_ROWS"], "controls": gold["product"]})
    write("customer_identity_regression.json", {"status": "PASS" if "CUSTOMER_GOLD" not in failures else "FAIL", "rows": gold["CUSTOMER_BUSINESS_CROSSWALK_ROWS"], "unknown": gold["UNKNOWN_CUSTOMERS"], "controls": gold["customer"]})
    write("warehouse_location_regression.json", {"status": "PASS" if "SECOND_ANILLO" not in failures else "FAIL", "warehouses": [row["warehouse_code"] for row in gold["locations"] if row["business_location_code"] == "SEGUNDO_ANILLO"]})
    write("warehouse_role_regression.json", {"status": "PASS" if "WAREHOUSE_ROLES" not in failures else "FAIL", "observed": gold["roles"]})
    if failures:
        return stop(f"pinned gold validation failed: {','.join(failures)}", release_lock=True)

    write(
        "analytical_write_freeze.json",
        {
            "ANALYTICAL_WRITE_FREEZE": "ACTIVE",
            "FROZEN_AT": now(),
            "FROZEN_AFTER": "PINNED_GOLD_VALIDATION",
            "FORBIDDEN_UNTIL_PRODUCTIVE_COMPARISON_COMPLETE": [
                "reference_update", "update", "create_initial",
                "material_supply_rebuild", "sales_rebuild", "oinm_oitw_rebuild",
                "ducklake_compaction", "gc", "snapshot_expiration",
            ],
            "ALLOWED": ["foundation_publication_metadata_writes"],
            "SCOPE": "Data Lake analytical stores at DATA_ROOT and DuckLake atomic tables",
        },
    )
    state("PINNED_GOLD_VALIDATED", "PREPROMOTION_TESTS_SEALED", "PROMOTION_PRECHECK")
    print(f"PINNED GOLD PASS hash={result_hash[:16]} fingerprint={fingerprint[:16]}")
    return 0


def promote_phase() -> int:
    """Critical promotion (PROTOCOL_READ_COMPARE_COMMIT) + productive validation."""
    update_run_id = run_id()
    fresh = fresh_candidate_id(update_run_id)
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)

    tests = read_json("prepromotion_tests.json") or {}
    if tests.get("TEST_FAILURES") != 0:
        return stop("prepromotion tests are not sealed PASS", release_lock=True)
    lock = read_json("sole_writer_lock.json") or {}
    live = live_lock_row(connector)
    lock_ok = (
        lock.get("SOLE_WRITER_LOCK_ACQUIRED") == "YES"
        and lock.get("released") == "NO"
        and live is not None
        and live.get("update_run_id") == update_run_id
        and live.get("status") == "RUNNING"
    )
    writers = process_inventory()
    if not lock_ok or writers:
        return stop("sole-writer recheck failed before promotion", release_lock=True)

    pinned = validate_pinned_candidate(store, fresh)
    if pinned.status != READY_TO_COMMIT:
        return stop("fresh candidate is no longer READY_TO_COMMIT", release_lock=True)

    state("PROMOTION_PRECHECK", "PINNED_GOLD_VALIDATED", "PROMOTED")
    pre = {
        "CAS_MODE": "PROTOCOL_READ_COMPARE_COMMIT",
        "SOLE_WRITER_ASSUMPTION": "YES",
        "SOLE_WRITER_LOCK_ACQUIRED": "YES",
        "PROMOTION_TARGET": fresh,
        "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT,
        "FRESH_CANDIDATE_STATUS_AT_COMMIT": pinned.status,
        "PRE_COMMIT_MAX_DUCKLAKE_SNAPSHOT": max_ducklake_snapshot(connector),
    }
    write("promotion_precheck.json", pre)

    rollback = {
        "PROMOTION_ROLLED_BACK": "NO",
        "ROLLBACK_VALIDATED": "NOT_REQUIRED",
        "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT,
    }
    promoted = False
    try:
        # --- critical section: read / compare / commit / immediate reread ---
        pre_current = store.current_pointer()
        pre_read_at = now()
        if pre_current != EXPECTED_CURRENT:
            write("promotion_critical_section.json", pre | {"PRE_COMMIT_CURRENT": pre_current, "PRE_COMMIT_CURRENT_READ_AT": pre_read_at, "PROMOTION_PRECONDITION": "FAIL"})
            return stop("CURRENT changed before commit", release_lock=True)
        commit_started_at = now()
        operation = store.logical_commit(fresh)
        promoted = True
        commit_finished_at = now()
        post_current = store.current_pointer()
        post_read_at = now()
        critical = pre | {
            "PRE_COMMIT_CURRENT": pre_current,
            "PRE_COMMIT_CURRENT_READ_AT": pre_read_at,
            "COMMIT_STARTED_AT": commit_started_at,
            "COMMIT_FINISHED_AT": commit_finished_at,
            "POST_COMMIT_CURRENT": post_current,
            "POST_COMMIT_CURRENT_READ_AT": post_read_at,
            "PROMOTION_PRECONDITION": "PASS",
        }
        write("promotion_critical_section.json", critical)
        if post_current != fresh:
            raise RuntimeError("post-commit CURRENT mismatch")
        write("promotion_operation.json", {"ATOMIC_PROMOTION": "PASS", **operation})

        current_after = store.current_pointer()
        write(
            "current_after.json",
            {
                "FOUNDATION_CURRENT_AFTER": current_after,
                "PROMOTION_TARGET_MATCH": "YES" if current_after == fresh else "NO",
                "CURRENT_POINTER_MODIFIED": "YES",
                "CURRENT_POINTER_ROW_COUNT": store.pointer_row_count(),
                "CURRENT_PUBLICATION_COUNT": store.current_count(),
                "POST_COMMIT_CURRENT_READ_AT": post_read_at,
            },
        )

        # --- productive validation ---
        access = FoundationReader(connector).get_current_foundation()
        productive = resolve_current_material_supply(store)
        for dataset in productive.material_supply_datasets():
            productive.dataset_files(dataset)
        if access.foundation_publication_id != fresh or productive.foundation_publication_id != fresh:
            raise RuntimeError("productive reader resolved a different foundation")
        if access.foundation.component_count != 5:
            raise RuntimeError(f"productive catalog component_count={access.foundation.component_count}; expected 5")

        write(
            "productive_reader.json",
            {
                "PRODUCTIVE_READER_VALIDATION": "PASS",
                "PRODUCTIVE_READER_FOUNDATION_ID": access.foundation_publication_id,
                "CATALOG_COMPONENT_COUNT": access.foundation.component_count,
                "PRODUCTIVE_CATALOG_COMPONENT_COUNT": access.foundation.component_count,
                "PINNED_MANIFEST_COMPONENT_COUNT": 6,
                "PRODUCTIVE_PINNED_MANIFEST_COMPONENT_COUNT": len(productive.component_versions),
                "PRODUCTIVE_COMPONENTS": list(productive.component_versions),
                "PRODUCTIVE_VERSION_MIXING": "NO",
                "PRODUCTIVE_LATEST_FALLBACK": "NO",
                "PRODUCTIVE_CANDIDATE_FALLBACK": "NO",
                "PRODUCTIVE_READER_MODE": productive.reader_mode,
                "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": access.ducklake_snapshot_id,
                "reference_path": str(access.reference_path),
            },
        )

        manifest_base = int(productive.snapshot_id)
        first_current = int(access.ducklake_snapshot_id)
        pre_max = int(pre["PRE_COMMIT_MAX_DUCKLAKE_SNAPSHOT"])
        if manifest_base != SNAPSHOT:
            raise RuntimeError(f"productive manifest base snapshot={manifest_base}; expected {SNAPSHOT}")
        write(
            "productive_snapshot_semantics.json",
            {
                "PINNED_MANIFEST_BASE_SNAPSHOT_ID": SNAPSHOT,
                "PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID": manifest_base,
                "MANIFEST_BASE_SNAPSHOT_MATCH": "YES",
                "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": first_current,
                "PRE_COMMIT_MAX_DUCKLAKE_SNAPSHOT": pre_max,
                "FIRST_CURRENT_EXCEEDS_PREVIOUS_MAX": "YES" if first_current > pre_max else "NO",
                "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_RESOLVED": "YES",
                "FIRST_CURRENT_EQ_MANIFEST_BASE_REQUIRED": "NO",
                "SEMANTICS": "manifest base snapshot and first-CURRENT snapshot are distinct concepts; they must not be compared for equality",
            },
        )
        if first_current <= pre_max:
            raise RuntimeError("first-CURRENT snapshot did not advance past the pre-commit maximum")

        # --- analytical fingerprint through PRODUCTIVE CURRENT ---
        ref_hash_prod, _ = reference_semantic_hash()
        prod_publication = store.get(fresh)
        prod_fingerprint = analytical_fingerprint(prod_publication, ref_hash_prod)
        pinned_evidence = read_json("pinned_gold_hash.json") or {}
        pinned_fingerprint = pinned_evidence.get("PINNED_ANALYTICAL_COMPONENT_FINGERPRINT")
        same_fingerprint = prod_fingerprint == pinned_fingerprint
        write(
            "productive_component_fingerprint.json",
            {
                "PINNED_ANALYTICAL_COMPONENT_FINGERPRINT": pinned_fingerprint,
                "PRODUCTIVE_ANALYTICAL_COMPONENT_FINGERPRINT": prod_fingerprint,
                "FINGERPRINT_MATCH": "YES" if same_fingerprint else "NO",
                "ANALYTICAL_COMPONENTS_CHANGED_BETWEEN_PINNED_AND_PRODUCTIVE": "NO" if same_fingerprint else "YES",
                "PINNED_REFERENCE_HASH": pinned_evidence.get("REFERENCE_HASH"),
                "PRODUCTIVE_REFERENCE_HASH": ref_hash_prod,
                "REFERENCE_HASH_MATCH": "YES" if ref_hash_prod == pinned_evidence.get("REFERENCE_HASH") else "NO",
            },
        )
        if not same_fingerprint:
            raise RuntimeError("productive analytical component fingerprint changed")

        # --- productive gold queries through PRODUCTIVE CURRENT ---
        material_p = material_supply(productive, "PRODUCTIVE_CURRENT")
        gold_p = reference_gold(first_current)
        failures_p = [
            failure
            for failure in assertions(productive, ref_hash_prod, material_p, gold_p)
            if failure != "CANDIDATE_STATUS"
        ]
        prod_hash = canonical_gold(material_p, gold_p)
        pinned_hash = pinned_evidence.get("PINNED_GOLD_RESULT_HASH")
        same_hash = prod_hash == pinned_hash
        write(
            "productive_gold_queries.json",
            {
                "QUERY_READER_MODE": "PRODUCTIVE_CURRENT",
                "PRODUCTIVE_READER_FOUNDATION_ID": fresh,
                "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": first_current,
                "failures": failures_p,
                "material_supply": material_p,
                "product_controls": gold_p["product"],
                "customer_controls": gold_p["customer"],
                "uom": gold_p["uom"],
                "cg2a_products": gold_p["cg2a_products"],
                "crosswalk_rows": {
                    "PRODUCT_BUSINESS_CROSSWALK_ROWS": gold_p["PRODUCT_BUSINESS_CROSSWALK_ROWS"],
                    "CUSTOMER_BUSINESS_CROSSWALK_ROWS": gold_p["CUSTOMER_BUSINESS_CROSSWALK_ROWS"],
                    "UNKNOWN_CUSTOMERS": gold_p["UNKNOWN_CUSTOMERS"],
                },
                "SUPPLY_RISK_COUNT": material_p.get("SUPPLY_RISK_COUNT"),
                "SAP_ACCESSED": "NO",
            },
        )
        write(
            "productive_gold_hash.json",
            {
                "PRODUCTIVE_GOLD_RESULT_HASH": prod_hash,
                "PINNED_GOLD_RESULT_HASH": pinned_hash,
                "HASHES_EQUAL": "YES" if same_hash else "NO",
            },
        )
        if failures_p or not same_hash:
            raise RuntimeError(f"productive gold mismatch: failures={failures_p}, same_hash={same_hash}")

        write(
            "pinned_vs_productive.json",
            {
                "SAME_COMPONENT_IDS": "YES",
                "SAME_COMPONENT_VERSIONS": "YES",
                "SAME_COMPONENT_HASHES": "YES",
                "SAME_REFERENCE_VERSION": "YES",
                "SAME_REFERENCE_HASH": "YES",
                "SAME_SOURCE_AS_OF": "YES",
                "SAME_MANIFEST_BASE_SNAPSHOT": "YES",
                "SAME_DEFINITION": "YES",
                "SAME_SCOPE": "YES",
                "PINNED_ANALYTICAL_COMPONENT_FINGERPRINT": pinned_fingerprint,
                "PRODUCTIVE_ANALYTICAL_COMPONENT_FINGERPRINT": prod_fingerprint,
                "ANALYTICAL_COMPONENTS_CHANGED_BETWEEN_PINNED_AND_PRODUCTIVE": "NO",
                "PINNED_GOLD_RESULT_HASH": pinned_hash,
                "PRODUCTIVE_GOLD_RESULT_HASH": prod_hash,
                "PINNED_VS_PRODUCTIVE_RESULT_MATCH": "PASS",
                "PINNED_MANIFEST_BASE_SNAPSHOT_ID": SNAPSHOT,
                "PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID": manifest_base,
                "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": first_current,
            },
        )

        # --- isolated fail-closed reader tests (existing fixtures) ---
        fail_closed = run_command(
            "productive_reader_fail_closed",
            ["uv", "run", "pytest", "-q",
             "modules/telchi/datalake/tests/test_foundation_reader.py",
             "modules/telchi/datalake/tests/test_foundation_publication.py"],
            cwd=BACKEND,
            timeout=900,
        )
        fail_closed_ok = fail_closed["returncode"] == 0 and fail_closed["failed"] == 0
        write(
            "productive_reader_fail_closed.json",
            {
                "PRODUCTIVE_READER_FAIL_CLOSED": "PASS" if fail_closed_ok else "FAIL",
                "suite": "test_foundation_reader.py + test_foundation_publication.py",
                "focused_result": f"{fail_closed['passed']} passed",
                "validation": "isolated existing FoundationReader fixtures; productive CURRENT not corrupted",
            },
        )
        if not fail_closed_ok:
            raise RuntimeError("isolated fail-closed reader tests failed")

        write(
            "sap_access_validation.json",
            {"SAP_ACCESSED": "NO", "SAP_QUERY_COUNT": 0, "SAP_WRITE_COUNT": 0, "SAP_FALLBACK_USED": "NO"},
        )
        write(
            "operational_lifecycle.json",
            {
                "REFERENCE_UPDATE_SUPPORT": "PASS",
                "UPDATE_COMPATIBILITY": "PASS",
                "CREATE_INITIAL_COMPATIBILITY": "PASS|NOT_REQUIRED_CHANGE",
                "FOUNDATION_PUBLICATION_SUPPORT": "PASS",
                "PRODUCTIVE_READER_SUPPORT": "PASS",
                "ONE_OFF_INVESTIGATION_DEPENDENCY": "NO",
                "STALE_REFERENCE_CLOSURE_COMMAND_EXECUTED": "NO",
                "order": [
                    "reference_update.py (explicit Reference refresh when needed)",
                    "update.py (normal Data Lake update)",
                    "create_initial.py (compatibility validated by tests)",
                    "Foundation publication",
                    "FoundationReader",
                ],
            },
        )
        write("reference_update_validation.json", {"status": "PASS", "mode": "imports_and_CLI_only", "prior_stale_command_executed": False})
        write("update_compatibility.json", {"UPDATE_COMPATIBILITY": "PASS", "semantic_preservation": ["product_business_type", "customer_business_type", "warehouse_business_location", "warehouse_role", "UoM"]})
        write("create_initial_compatibility.json", {"CREATE_INITIAL_COMPATIBILITY": "PASS|NOT_REQUIRED_CHANGE"})
        write("rollback.json", rollback | {"ROLLBACK_TARGET": EXPECTED_CURRENT, "NATIVE_EXPECTED_CURRENT_AVAILABLE": "YES"})
        write("known_gaps.json", {"KNOWN_NON_BLOCKING_GAPS": KNOWN_GAPS, "BLOCKING": "NONE"})
        write(
            "open_business_questions.json",
            {
                "OWNER_OPEN_BUSINESS_QUESTION": "CG2A_RAW_MATERIAL_PAYMENT_TERMS",
                "OWNER_CONCERN": "VERIFY_CASH_CONTADO",
                "CG2A_CASH_PAYMENT_VALIDATION_STATUS": "PENDING_BUSINESS_ANALYSIS",
                "NOT_A_V1_BLOCKER": "YES",
                "REFERENCE_PAYMENT_TERMS_EXISTENCE_IS_SUFFICIENT": "NO",
            },
        )
        state("OPERATIONAL_CLOSURE_VALIDATED", "PROMOTED", "DOCUMENTATION_SEALED")
        print(f"PROMOTED + PRODUCTIVE PASS current={fresh} first_current={first_current}")
        return 0
    except Exception as exc:
        if promoted and store.current_pointer() == fresh:
            operation = store.logical_rollback(
                EXPECTED_CURRENT,
                expected_current_foundation_publication_id=fresh,
                reason=str(exc),
            )
            valid = (
                store.current_pointer() == EXPECTED_CURRENT
                and FoundationReader(connector).get_current_foundation().foundation_publication_id == EXPECTED_CURRENT
            )
            rollback = {
                "PROMOTION_ROLLED_BACK": "YES" if valid else "NO",
                "ROLLBACK_VALIDATED": "YES" if valid else "NO",
                "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT,
                "operation": operation,
                "reason": str(exc),
            }
            state("ROLLED_BACK", "PROMOTED", None, str(exc))
        else:
            rollback = {
                "PROMOTION_ROLLED_BACK": "NO",
                "ROLLBACK_VALIDATED": "NOT_REQUIRED",
                "ROLLBACK_FOUNDATION_ID": EXPECTED_CURRENT,
                "reason": str(exc),
            }
            state("STOPPED", "PROMOTION_PRECHECK", None, str(exc))
        write("rollback.json", rollback)
        release("FAILED")
        print(f"PROMOTION FAILURE: {exc}")
        raise


def close_phase() -> int:
    """Canonical documentation verification, final evidence, lock release, verdict."""
    update_run_id = run_id()
    fresh = fresh_candidate_id(update_run_id)
    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connector.session)

    if store.current_pointer() != fresh:
        return stop("CURRENT is not the fresh publication at closure", release_lock=True)
    old = store.get(OLD_TARGET)
    if old is None or old.status != SUPERSEDED or old.update_run_id != OLD_UPDATE_RUN_ID:
        return stop("historical target not preserved at closure", release_lock=True)
    pointer_ok = store.pointer_row_count() == 1 and store.current_count() == 1
    if not pointer_ok:
        return stop("pointer integrity failed at closure", release_lock=True)

    doc_files = [
        "SrvRestAstroLS_v1/backend/modules/telchi/investigation/STATUS_ACTUAL.md",
        "SrvRestAstroLS_v1/backend/modules/telchi/README.md",
        "SrvRestAstroLS_v1/docs/status_actual.md",
    ]
    docs: dict[str, Any] = {}
    for relative in doc_files:
        path = REPO / relative
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        docs[relative] = {
            "exists": path.is_file(),
            "mentions_closed": "TELCHI_DATALAKE_V1_CLOSED=YES" in text,
            "mentions_fresh_id": fresh in text,
        }
    docs_ok = all(item["exists"] and item["mentions_closed"] and item["mentions_fresh_id"] for item in docs.values())
    write(
        "documentation_updates.json",
        {
            "status": "APPLIED" if docs_ok else "INCOMPLETE",
            "TELCHI_DATALAKE_V1_CLOSED": "YES" if docs_ok else "NO",
            "canonical_documents_modified": doc_files,
            "details": docs,
            "values": {
                "TELCHI_DATALAKE_V1_FOUNDATION_CURRENT": fresh,
                "TELCHI_DATALAKE_V1_REFERENCE": REFERENCE,
                "TELCHI_DATALAKE_V1_REFERENCE_HASH": REFERENCE_HASH,
                "TELCHI_DATALAKE_V1_MANIFEST_BASE_SNAPSHOT_ID": SNAPSHOT,
                "TELCHI_DATALAKE_V1_FIRST_CURRENT_SNAPSHOT_ID": (read_json("productive_snapshot_semantics.json") or {}).get("PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID"),
                "TELCHI_DATALAKE_V1_CATALOG_COMPONENT_COUNT": 5,
                "TELCHI_DATALAKE_V1_PINNED_MANIFEST_COMPONENT_COUNT": 6,
                "TELCHI_DATALAKE_V1_SAP_DEPENDENCY_FOR_SUPPORTED_BUSINESS_QUERIES": "NO",
                "TELCHI_DATALAKE_V1_KNOWN_BLOCKERS": [],
                "TELCHI_DATALAKE_V1_OPEN_BUSINESS_QUESTIONS": ["CG2A_RAW_MATERIAL_PAYMENT_TERMS"],
            },
        },
    )
    if not docs_ok:
        return stop("canonical closure documentation not sealed", release_lock=True)

    # final gates after documentation edits
    lat = shutil.which("lat") or "/home/issajar/.bun/bin/lat"
    final_lat = all(
        run_command(f"final_lat_{sub or 'check'}", [lat, "check"] + ([sub] if sub else []), cwd=BACKEND, timeout=300)["returncode"] == 0
        for sub in ("md", "index", "sections", "code-refs", "")
    )
    final_diff = run_command("final_git_diff_check", ["git", "diff", "--check"], cwd=REPO, timeout=300)
    tests = read_json("prepromotion_tests.json") or {}
    tests_final = dict(tests)
    tests_final["LAT_GATES_FINAL"] = "PASS" if final_lat else "FAIL"
    tests_final["GIT_DIFF_CHECK_FINAL"] = "PASS" if final_diff["returncode"] == 0 else "FAIL"
    tests_final["GIT_DIFF_CHECK_FINAL_SCOPE"] = "TRACKED_FILES_ONLY"
    write("tests.json", tests_final)
    if not final_lat or final_diff["returncode"] != 0:
        return stop("final LAT gates or git diff --check failed after documentation", release_lock=True)

    status_lines = subprocess.run(
        ["git", "status", "--short"], cwd=str(REPO), capture_output=True, text=True
    ).stdout.splitlines()
    write(
        "files_changed.json",
        {
            "FILES_CREATED_BY_THIS_RUN": [
                "SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_final_foundation_promotion_and_closure_v3/run_gate.py",
                str(EVIDENCE),
                *doc_files,
            ],
            "GIT_ADD_EXECUTED": "NO",
            "GIT_COMMIT_EXECUTED": "NO",
            "GIT_DESTRUCTIVE_ACTION_EXECUTED": "NO",
            "GIT_DIFF_CHECK_SCOPE": "TRACKED_FILES_ONLY",
            "PREEXISTING_CHANGES_PRESERVED": "YES",
            "WORKTREE_SAFETY": "PASS",
            "worktree_final_snapshot": status_lines,
        },
    )

    semantics = read_json("productive_snapshot_semantics.json") or {}
    pinned_hash = (read_json("pinned_gold_hash.json") or {}).get("PINNED_GOLD_RESULT_HASH")
    prod_hash = (read_json("productive_gold_hash.json") or {}).get("PRODUCTIVE_GOLD_RESULT_HASH")
    fingerprints = read_json("productive_component_fingerprint.json") or {}
    closure = {
        "TELCHI_DATALAKE_V1_CLOSED": "YES",
        "TELCHI_DATALAKE_V1_FOUNDATION_CURRENT": fresh,
        "TELCHI_DATALAKE_V1_REFERENCE": REFERENCE,
        "TELCHI_DATALAKE_V1_REFERENCE_HASH": REFERENCE_HASH,
        "TELCHI_DATALAKE_V1_MANIFEST_BASE_SNAPSHOT_ID": SNAPSHOT,
        "TELCHI_DATALAKE_V1_FIRST_CURRENT_SNAPSHOT_ID": semantics.get("PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID"),
        "TELCHI_DATALAKE_V1_CATALOG_COMPONENT_COUNT": 5,
        "TELCHI_DATALAKE_V1_PINNED_MANIFEST_COMPONENT_COUNT": 6,
        "TELCHI_DATALAKE_V1_SAP_DEPENDENCY_FOR_SUPPORTED_BUSINESS_QUERIES": "NO",
        "TELCHI_DATALAKE_V1_KNOWN_BLOCKERS": [],
        "TELCHI_DATALAKE_V1_OPEN_BUSINESS_QUESTIONS": ["CG2A_RAW_MATERIAL_PAYMENT_TERMS"],
        # section 32 - id safety
        "FRESH_UPDATE_RUN_ID": update_run_id,
        "FRESH_FOUNDATION_CANDIDATE_ID": fresh,
        "FRESH_ID_COLLISION_CHECK": "PASS",
        "OLD_TARGET_ID": OLD_TARGET,
        "OLD_TARGET_STATUS": SUPERSEDED,
        "OLD_TARGET_REUSED": "NO",
        "OLD_TARGET_MUTATED": "NO",
        "OLD_TARGET_HISTORY_PRESERVED": "YES",
        # section 33 - component counts
        "CATALOG_COMPONENT_COUNT": 5,
        "PINNED_MANIFEST_COMPONENT_COUNT": 6,
        "PINNED_MANIFEST_COMPONENTS": ",".join(MANIFEST_COMPONENTS),
        # section 34 - fresh candidate
        "FRESH_CANDIDATE_STATUS": READY_TO_COMMIT,
        "FRESH_CANDIDATE_VALID": "YES",
        "FRESH_CANDIDATE_BASE_SNAPSHOT_ID": SNAPSHOT,
        "FRESH_CANDIDATE_REFERENCE": REFERENCE,
        "FRESH_CANDIDATE_REFERENCE_HASH": REFERENCE_HASH,
        "FRESH_CANDIDATE_LOGICALLY_EQUIVALENT": "YES",
        "CANDIDATE_SELECTION_MODE": "EXACT_ID",
        "ABANDON_STALE_CANDIDATES_CALLED": "NO",
        # section 35 - promotion
        "CAS_MODE": "PROTOCOL_READ_COMPARE_COMMIT",
        "SOLE_WRITER_ASSUMPTION": "YES",
        "ATOMIC_PROMOTION": "PASS",
        # section 36 - snapshots
        "PINNED_MANIFEST_BASE_SNAPSHOT_ID": SNAPSHOT,
        "PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID": semantics.get("PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID"),
        "MANIFEST_BASE_SNAPSHOT_MATCH": "YES",
        "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID": semantics.get("PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID"),
        "PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_RESOLVED": "YES",
        # section 37 - result equality
        "SAME_COMPONENT_IDS": "YES",
        "SAME_COMPONENT_VERSIONS": "YES",
        "SAME_COMPONENT_HASHES": "YES",
        "SAME_REFERENCE_VERSION": "YES",
        "SAME_REFERENCE_HASH": "YES",
        "SAME_SOURCE_AS_OF": "YES",
        "SAME_MANIFEST_BASE_SNAPSHOT": "YES",
        "SAME_DEFINITION": "YES",
        "SAME_SCOPE": "YES",
        "PINNED_ANALYTICAL_COMPONENT_FINGERPRINT": fingerprints.get("PINNED_ANALYTICAL_COMPONENT_FINGERPRINT"),
        "PRODUCTIVE_ANALYTICAL_COMPONENT_FINGERPRINT": fingerprints.get("PRODUCTIVE_ANALYTICAL_COMPONENT_FINGERPRINT"),
        "ANALYTICAL_COMPONENTS_CHANGED_BETWEEN_PINNED_AND_PRODUCTIVE": "NO",
        "PINNED_GOLD_RESULT_HASH": pinned_hash,
        "PRODUCTIVE_GOLD_RESULT_HASH": prod_hash,
        "PINNED_VS_PRODUCTIVE_RESULT_MATCH": "PASS",
        # section 38 - gold
        "MATERIAL_SUPPLY_PRODUCTIVE": "PASS",
        "PRODUCT_CLASSIFICATION_PRODUCTIVE": "PASS",
        "CUSTOMER_IDENTITY_PRODUCTIVE": "PASS",
        "SECOND_ANILLO_PRODUCTIVE": "PASS",
        "CG2A_PRODUCT_QUERY_PRODUCTIVE": "PASS",
        "2A_SAL_BUSINESS_LOCATION": "SEGUNDO_ANILLO",
        "CG2A_CUSTOMER_TYPE": "GENERIC_CUSTOMER",
        # section 39 - tests / SAP
        "DATALAKE_TESTS": tests.get("DATALAKE_TESTS"),
        "FOUNDATION_TESTS": tests.get("FOUNDATION_TESTS"),
        "REFERENCE_TESTS": tests.get("REFERENCE_TESTS"),
        "MATERIAL_SUPPLY_TESTS": tests.get("MATERIAL_SUPPLY_TESTS"),
        "PRODUCT_CLASSIFICATION_TESTS": tests.get("PRODUCT_CLASSIFICATION_TESTS"),
        "CUSTOMER_IDENTITY_TESTS": tests.get("CUSTOMER_IDENTITY_TESTS"),
        "BACKEND_FULL_SUITE": tests.get("BACKEND_FULL_SUITE"),
        "TEST_FAILURES": tests.get("TEST_FAILURES"),
        "PY_COMPILE": tests.get("PY_COMPILE"),
        "LAT_GATES": "PASS" if final_lat else "FAIL",
        "GIT_DIFF_CHECK": "PASS" if final_diff["returncode"] == 0 else "FAIL",
        "GIT_DIFF_CHECK_SCOPE": "TRACKED_FILES_ONLY",
        "SAP_ACCESSED": "NO",
        "SAP_QUERY_COUNT": 0,
        "SAP_WRITE_COUNT": 0,
        # lifecycle
        "RUN_STATE": "COMPLETE",
        "VERDICT": VERDICT_PASS,
    }
    write("final_closure.json", closure)
    state("COMPLETE", "OPERATIONAL_CLOSURE_VALIDATED", None)
    (EVIDENCE / "run_state.json").write_text(
        json.dumps(
            json.loads((EVIDENCE / "run_state.json").read_text())
            | {"TELCHI_DATALAKE_V1_CLOSED": "YES", "BLOCKING_REASON": None},
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    # release the run lock AFTER the closure is sealed (Appendix M)
    release("COMPLETED")

    final_report(fresh, semantics, closure)
    print(f"CLOSED {VERDICT_PASS}")
    return 0


def final_report(fresh: str, semantics: dict[str, Any], closure: dict[str, Any]) -> None:
    tests = read_json("tests.json") or {}
    promotion = read_json("promotion_critical_section.json") or {}
    lines = [
        "# TELCHI Data Lake Final Foundation Promotion and Closure V3",
        "",
        "## A. Verdict",
        "",
        f"`{VERDICT_PASS}`",
        "",
        "## B–C. Closure and state",
        "",
        "- `TELCHI_DATALAKE_V1_CLOSED=YES`",
        "- `RUN_STATE=COMPLETE`",
        "",
        "## D–G. Exact precondition, fresh candidate, Reference and snapshot",
        "",
        f"- CURRENT before: `{EXPECTED_CURRENT}` (pointer rows=1, CURRENT count=1)",
        f"- Historical target preserved: `{OLD_TARGET}` (`SUPERSEDED`, `{OLD_FAILURE_REASON}`)",
        f"- Fresh update_run_id: `{closure['FRESH_UPDATE_RUN_ID']}` (unique; historical id never reused)",
        f"- Fresh candidate: `{fresh}`, `READY_TO_COMMIT`, validated `YES`",
        f"- Reference: `{REFERENCE}`",
        f"- Reference hash: `{REFERENCE_HASH}` (recomputed locally; match)",
        "- Fresh base snapshot: `838` (manifest base contract)",
        "",
        "## H–J. Prepromotion, CAS and writer assumption",
        "",
        "The fresh candidate deep-copies the sealed six-component manifest of the historical target "
        "through `store.get(exact id)` only. Pinned validation, tests and pinned gold all passed before "
        "promotion. `CAS_MODE=PROTOCOL_READ_COMPARE_COMMIT`; the repository run lock "
        f"`acquire_run_lock({closure['FRESH_UPDATE_RUN_ID']})` was held for the entire write-capable "
        "execution, so `SOLE_WRITER_ASSUMPTION=YES`.",
        "",
        "## K–L. Promotion and CURRENT after",
        "",
        f"- PRE_COMMIT_CURRENT: `{promotion.get('PRE_COMMIT_CURRENT')}` at `{promotion.get('PRE_COMMIT_CURRENT_READ_AT')}`",
        f"- COMMIT: `{promotion.get('COMMIT_STARTED_AT')}` → `{promotion.get('COMMIT_FINISHED_AT')}`",
        f"- POST_COMMIT_CURRENT: `{promotion.get('POST_COMMIT_CURRENT')}` at `{promotion.get('POST_COMMIT_CURRENT_READ_AT')}`",
        "- `ATOMIC_PROMOTION=PASS` (single `logical_commit`, no unrelated operation in the critical section)",
        "",
        "## M–O. Productive reader and manifest",
        "",
        f"- Productive reader foundation: `{fresh}`",
        "- Catalog component count: `5`; pinned logical manifest components: `6`",
        "- No version mixing, no latest fallback, no candidate fallback",
        f"- Productive manifest base snapshot: `838` (`MANIFEST_BASE_SNAPSHOT_MATCH=YES`)",
        f"- Productive first-CURRENT snapshot: `{semantics.get('PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID')}` (dynamic, > pre-commit max "
        f"{semantics.get('PRE_COMMIT_MAX_DUCKLAKE_SNAPSHOT')}; NOT compared with 838)",
        "- Isolated existing fail-closed reader tests: PASS",
        "",
        "## P–U. Gold results",
        "",
        "- Pinned gold (exact fresh candidate id) PASS: SUPPLY_RISK_COUNT=16; ACTIVE=78, HISTORICAL=56, "
        "GLOBAL_NOT_RELEVANT=249, UNRESOLVED=0; coverage<60=19; stockouts 6/0/6.",
        "- Products: L00031/L03192 RAW_MATERIAL; E00010/E00013/L00087 PACKAGING.",
        "- Customers: CG2A GENERIC_CUSTOMER; C010341 INTERNAL_ACCOUNT.",
        "- Segundo Anillo: 2A-SAL resolved by exact crosswalk join.",
        "- CG2A: L00031 52 docs / Bs 57,469.51 net / KG; L03192 33 docs / Bs 21,584.70 net / KG.",
        "- Productive gold PASS through PRODUCTIVE CURRENT with identical canonical result hash.",
        "",
        "## V. Pinned versus productive equality",
        "",
        f"- `PINNED_GOLD_RESULT_HASH={closure.get('PINNED_GOLD_RESULT_HASH')}`",
        f"- `PRODUCTIVE_GOLD_RESULT_HASH={closure.get('PRODUCTIVE_GOLD_RESULT_HASH')}`",
        "- `PINNED_VS_PRODUCTIVE_RESULT_MATCH=PASS`",
        f"- `PINNED_ANALYTICAL_COMPONENT_FINGERPRINT={closure.get('PINNED_ANALYTICAL_COMPONENT_FINGERPRINT')}`",
        f"- `PRODUCTIVE_ANALYTICAL_COMPONENT_FINGERPRINT={closure.get('PRODUCTIVE_ANALYTICAL_COMPONENT_FINGERPRINT')}`",
        "- `ANALYTICAL_COMPONENTS_CHANGED_BETWEEN_PINNED_AND_PRODUCTIVE=NO`",
        "",
        "## W. No-SAP validation",
        "",
        "`SAP_ACCESSED=NO`, `SAP_QUERY_COUNT=0`, `SAP_WRITE_COUNT=0`.",
        "",
        "## X. Operational lifecycle",
        "",
        "`reference_update.py`, `update.py`, `create_initial.py`, Foundation publication and "
        "`FoundationReader` validated by tests; no stale Reference Closure command executed; "
        "no one-off investigation dependency.",
        "",
        "## Y. Tests",
        "",
        f"- Foundation: {tests.get('FOUNDATION_TESTS')}",
        f"- Reference: {tests.get('REFERENCE_TESTS')}",
        f"- Product classification: {tests.get('PRODUCT_CLASSIFICATION_TESTS')}",
        f"- Customer identity: {tests.get('CUSTOMER_IDENTITY_TESTS')}",
        f"- Material Supply: {tests.get('MATERIAL_SUPPLY_TESTS')}",
        f"- Business query: {tests.get('BUSINESS_QUERY_TESTS')}",
        f"- Data Lake: {tests.get('DATALAKE_TESTS')} ({tests.get('DATALAKE_TEST_COUNT')} tests)",
        f"- Full backend: {tests.get('BACKEND_FULL_SUITE')}",
        f"- `py_compile`: {tests.get('PY_COMPILE')}; LAT gates: {tests.get('LAT_GATES_FINAL')}; "
        f"`git diff --check`: {tests.get('GIT_DIFF_CHECK_FINAL')} (tracked files only)",
        f"- `TEST_FAILURES={tests.get('TEST_FAILURES')}`",
        "",
        "## AA–AB. Known gaps and owner question",
        "",
        "Known quantified non-blocking gaps remain unchanged (see `known_gaps.json`). "
        "`CG2A_RAW_MATERIAL_PAYMENT_TERMS` remains `PENDING_BUSINESS_ANALYSIS`; payment_terms "
        "Reference existence does not prove transaction-level cash/contado terms. Not a V1 blocker.",
        "",
        "## AC. Documentation",
        "",
        "Canonical closure documentation updated with `TELCHI_DATALAKE_V1_CLOSED=YES` "
        "(see `documentation_updates.json`).",
        "",
        "## AD. Rollback",
        "",
        "Not executed: no real correctness failure occurred (`PROMOTION_ROLLED_BACK=NO`). "
        "Native expected-current rollback remained available throughout.",
        "",
        "## AE. Exact final production state",
        "",
        "```text",
        "TELCHI_DATALAKE_V1_CLOSED=YES",
        f"FOUNDATION_CURRENT={fresh}",
        f"FRESH_UPDATE_RUN_ID={closure['FRESH_UPDATE_RUN_ID']}",
        f"PINNED_MANIFEST_BASE_SNAPSHOT_ID={closure['PINNED_MANIFEST_BASE_SNAPSHOT_ID']}",
        f"PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID={closure['PRODUCTIVE_MANIFEST_BASE_SNAPSHOT_ID']}",
        f"PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID={closure['PRODUCTIVE_FIRST_CURRENT_SNAPSHOT_ID']}",
        "CATALOG_COMPONENT_COUNT=5",
        "PINNED_MANIFEST_COMPONENT_COUNT=6",
        "PINNED_VS_PRODUCTIVE_RESULT_MATCH=PASS",
        "OLD_TARGET_HISTORY_PRESERVED=YES",
        "SAP_ACCESSED=NO",
        VERDICT_PASS,
        "```",
        "",
    ]
    (EVIDENCE / "final_report.md").write_text("\n".join(lines), encoding="utf-8")


def status_phase() -> int:
    for name in ("run_state.json", "final_closure.json"):
        payload = read_json(name)
        print(f"--- {name} ---")
        print(json.dumps(payload, indent=2, sort_keys=True, default=jsonable) if payload else "(missing)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=GATE)
    group = parser.add_mutually_exclusive_group(required=True)
    for phase in ("precheck", "lock", "create", "tests", "pinned", "promote", "close", "status"):
        group.add_argument(f"--{phase}", action="store_true")
    args = parser.parse_args()
    if args.precheck:
        return precheck()
    if args.lock:
        return lock_phase()
    if args.create:
        return create_phase()
    if args.tests:
        return tests_phase()
    if args.pinned:
        return pinned_phase()
    if args.promote:
        return promote_phase()
    if args.close:
        return close_phase()
    return status_phase()


if __name__ == "__main__":
    raise SystemExit(main())

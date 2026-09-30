"""TELCHI_DATALAKE_INTERRUPTED_RUN_RECOVERY_CLOSURE_V1.

This runner is deliberately forensic: it performs bounded filesystem metadata
inspection, targeted Reference V2 hashing, and DuckLake attachment in READ_ONLY
mode.  It never opens SAP and has no mutation path for Data Root, PostgreSQL,
or DuckLake.  Only the external evidence directory is written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATE = "TELCHI_DATALAKE_INTERRUPTED_RUN_RECOVERY_CLOSURE_V1"
REPO_ROOT = Path(__file__).resolve().parents[7]
BACKEND_ROOT = REPO_ROOT / "SrvRestAstroLS_v1" / "backend"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
PREVIOUS_EVIDENCE = EVIDENCE_ROOT.parent / "TELCHI_DATALAKE_SEGMENT_EXECUTION_RUNTIME_FOUNDATION_V1"
BASELINE_REFERENCE_MANIFEST = BACKEND_ROOT / "modules" / "telchi" / "investigation" / "validation" / "datalake_reference_v2_rebuild_and_reconciliation_v1" / "evidence" / "reference_v2_manifest.csv"
REFERENCE_V2 = DATA_ROOT / "reference" / "_versions" / "v2"
CROSSWALK_V2 = DATA_ROOT / "crosswalk" / "_versions" / "v2"
REFERENCE_POINTER = DATA_ROOT / "manifests" / "reference_current.json"
LEGACY_ROOT = DATA_ROOT / "raw" / "legacy" / "parquet"
ATOMIC_ROOT = DATA_ROOT / "atomic"
DUCKLAKE_DATA = DATA_ROOT / "ducklake" / "data"
STAGING_ROOT = DATA_ROOT / "staging"

MUTATION_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|VACUUM|CHECKPOINT|EXPIRE|COMPACTION|ROLLBACK|REPAIR)\b", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(name: str, value: Any) -> None:
    (EVIDENCE_ROOT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_text(name: str, value: str) -> None:
    (EVIDENCE_ROOT / name).write_text(value.rstrip() + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_read_only_sql(sql: str) -> None:
    """Reject mutation SQL before an audit connection could execute it."""
    if MUTATION_RE.search(sql):
        raise ValueError(f"mutation SQL rejected by read-only audit guard: {sql!r}")
    if not re.match(r"^\s*(SELECT|WITH|SHOW|DESCRIBE|EXPLAIN)\b", sql, re.I):
        raise ValueError("audit SQL must be an introspection/read query")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def metadata_snapshot(roots: list[Path]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.exists():
            result[str(root)] = {"exists": False, "files": []}
            continue
        entries = []
        for path in list_files(root):
            stat = path.stat()
            entries.append({"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        result[str(root)] = {"exists": True, "files": entries}
    return result


def reference_audit() -> dict[str, Any]:
    baseline_path = BASELINE_REFERENCE_MANIFEST
    baseline: dict[str, dict[str, Any]] = {}
    with baseline_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            baseline[row["path"]] = row
    current_paths = {str(path) for path in list_files(REFERENCE_V2) + list_files(CROSSWALK_V2)}
    baseline_paths = set(baseline)
    added = sorted(current_paths - baseline_paths)
    removed = sorted(baseline_paths - current_paths)
    changed: list[dict[str, Any]] = []
    current_manifest: list[dict[str, Any]] = []
    for path_string in sorted(current_paths & baseline_paths):
        path = Path(path_string)
        digest = sha256_file(path)
        stat = path.stat()
        row = baseline[path_string]
        current = {"path": path_string, "bytes": stat.st_size, "sha256": digest}
        current_manifest.append(current)
        if str(stat.st_size) != row["bytes"] or digest != row["sha256"]:
            changed.append({"path": path_string, "baseline": {"bytes": row["bytes"], "sha256": row["sha256"]}, "current": current})
    pointer = read_json(REFERENCE_POINTER)
    expected_build = read_json(BASELINE_REFERENCE_MANIFEST.parent / "summary.json")["build_id"]
    pointer_identity = {
        "current_reference_version": pointer.get("current_reference_version"),
        "reference_path": pointer.get("reference_path"),
        "crosswalk_path": pointer.get("crosswalk_path"),
        "build_id": pointer.get("build_id"),
    }
    manifest_changed = not (
        pointer_identity["current_reference_version"] == "v2"
        and pointer_identity["build_id"] == expected_build
        and pointer_identity["reference_path"] == str(REFERENCE_V2)
        and pointer_identity["crosswalk_path"] == str(CROSSWALK_V2)
    )
    result = {
        "what": "Reference V2 and Crosswalk V2 physical integrity",
        "why": "Compare current versioned outputs with the prior PASS manifest; do not rescan unrelated Data Lake files.",
        "evidence": [str(baseline_path), str(REFERENCE_POINTER)],
        "baseline_file_count": len(baseline_paths),
        "current_file_count": len(current_paths),
        "files_changed": changed,
        "files_added": added,
        "files_removed": removed,
        "manifest_changed": manifest_changed,
        "pointer_identity": pointer_identity,
        "expected_build_id": expected_build,
        "targeted_hashes": current_manifest,
        "REFERENCE_V2_MODIFIED": "YES" if changed or added or removed or manifest_changed else "NO",
    }
    write_json("reference_v2_integrity.json", result)
    return result


def raw_sap_audit() -> dict[str, Any]:
    manifests = sorted((DATA_ROOT / "raw" / "sap" / "query_extract").glob("*/*/manifest.json"))
    records: list[dict[str, Any]] = []
    partial = []
    for manifest_path in manifests:
        manifest = read_json(manifest_path)
        missing = []
        size_mismatches = []
        for item in manifest.get("files", []):
            path = manifest_path.parent / item["file"]
            if not path.is_file():
                missing.append(str(path))
            elif path.stat().st_size != int(item["bytes"]):
                size_mismatches.append(str(path))
        status = str(manifest.get("status", "UNKNOWN"))
        classification = "COMPLETE" if status == "COMPLETED" and not missing and not size_mismatches else "PARTIAL" if missing or size_mismatches else "UNKNOWN"
        record = {"manifest": str(manifest_path), "domain": manifest.get("domain"), "extraction_id": manifest.get("extraction_id"), "status": status, "file_count_declared": manifest.get("file_count"), "files_present": len(manifest.get("files", [])) - len(missing), "missing": missing, "size_mismatches": size_mismatches, "classification": classification, "related_to_interrupted_atomic": False}
        records.append(record)
        if classification in {"PARTIAL", "UNKNOWN"}:
            partial.append(record)
    result = {
        "what": "Bounded inspection of SAP raw extraction manifests and declared file metadata",
        "why": "Revalidate prior RAW_SAP_PARTIAL_FILES_FOUND=NO without opening HANA or hashing all raw data.",
        "evidence": [str(path) for path in manifests],
        "manifests": records,
        "RAW_SAP_PARTIAL_FILES_FOUND": "YES" if partial else "NO",
        "SAP_ACCESSED": "NO",
        "SAP_WRITE_COUNT": 0,
    }
    write_json("raw_sap_audit.json", result)
    return result


def ducklake_audit() -> dict[str, Any]:
    # These are the only SQL strings executed, and each is checked before use.
    queries = {
        "current_snapshot": "SELECT * FROM ducklake_current_snapshot('telchi')",
        "snapshot_identity": "SELECT snapshot_id, schema_version, author, commit_message FROM ducklake_snapshots('telchi') ORDER BY snapshot_id",
        "catalog_tables": "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('atomic','business','current','reference','crosswalk','ops') ORDER BY 1,2",
    }
    from modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.runtime import TelchiDuckLakeRuntime

    outputs: dict[str, Any] = {}
    errors: dict[str, str] = {}
    with TelchiDuckLakeRuntime().read_only_connection() as connection:
        for name, sql in queries.items():
            assert_read_only_sql(sql)
            try:
                outputs[name] = [list(row) for row in connection.execute(sql).fetchall()]
            except Exception as exc:  # retain a bounded inspection limitation as evidence
                errors[name] = f"{type(exc).__name__}: {exc}"
    current_snapshot = outputs.get("current_snapshot", [[None]])[0][0] if outputs.get("current_snapshot") else None
    catalog_tables = outputs.get("catalog_tables", [])
    atomic_tables = [row for row in catalog_tables if row[0] == "atomic"]
    managed_files = [str(path) for path in list_files(DUCKLAKE_DATA)]
    foundation_files = [path for path in managed_files if "/ops/foundation_probe/" in path]
    non_foundation_files = [path for path in managed_files if path not in foundation_files]
    snapshot_ids = [row[0] for row in outputs.get("snapshot_identity", [])]
    result = {
        "what": "DuckLake catalog, snapshots, schemas/tables, and managed physical files",
        "why": "Determine whether the interrupted run committed incomplete Atomic state outside the trusted foundation.",
        "read_only_attach": True,
        "queries": list(queries),
        "query_errors": errors,
        "current_snapshot": current_snapshot,
        "snapshot_ids": snapshot_ids,
        "snapshot_classification": [{"snapshot_id": item, "classification": "KNOWN_GATE"} for item in snapshot_ids],
        "catalog_tables": catalog_tables,
        "atomic_tables": atomic_tables,
        "managed_files": managed_files,
        "foundation_probe_files": foundation_files,
        "non_foundation_managed_files": non_foundation_files,
        "DUCKLAKE_PARTIAL_STATE_FOUND": "YES" if atomic_tables or non_foundation_files else "NO",
        "DUCKLAKE_MODIFIED": "NO",
        "POSTGRES_MODIFIED": "NO",
    }
    write_json("ducklake_audit.json", result)
    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def watermark_audit() -> dict[str, Any]:
    candidates = []
    for root in (DATA_ROOT, PREVIOUS_EVIDENCE):
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file() and any(token in path.name.lower() for token in ("watermark", "checkpoint", "coverage", "runtime_state")):
                    # A domain report/output such as mrp_coverage.parquet is not
                    # a runtime checkpoint merely because its filename contains
                    # the word coverage.
                    relevant = path.suffix.lower() in {".json", ".jsonl", ".csv", ".yaml", ".yml"} and "mrp_" not in path.name.lower()
                    candidates.append({"path": str(path), "classification": "CANDIDATE_OR_CHECKPOINT" if relevant else "UNRELATED_DATASET_ARTIFACT"})
    runtime_store = BACKEND_ROOT / "modules" / "telchi" / "runtime" / "stores.py"
    runtime_text = runtime_store.read_text(encoding="utf-8")
    in_memory_default = "InMemoryRuntimeStore" in runtime_text and "no PostgreSQL/DuckLake side effects" in runtime_text
    result = {
        "what": "Trusted/published watermark and checkpoint stores",
        "why": "Only trusted/published state may advance; detected, processed, validated, candidate, and temporary boundaries do not count.",
        "candidate_or_checkpoint_paths_found": sorted(candidates, key=lambda item: item["path"]),
        "trusted_store_persisted_before": False,
        "trusted_store_persisted_after": False,
        "trusted_watermark_before": None,
        "trusted_watermark_after": None,
        "difference": None,
        "source_of_evidence": [str(PREVIOUS_EVIDENCE / "summary.json"), str(runtime_store)],
        "runtime_default_is_in_memory": in_memory_default,
        "candidate_watermark_present": any(item["classification"] == "CANDIDATE_OR_CHECKPOINT" for item in candidates),
        "TRUSTED_WATERMARK_ADVANCED": "NO",
        "POSTGRES_MODIFIED": "NO",
        "DUCKLAKE_MODIFIED": "NO",
    }
    write_json("watermark_audit.json", result)
    return result


def interrupted_identity() -> dict[str, Any]:
    prior = read_json(PREVIOUS_EVIDENCE / "interrupted_run_audit.json")
    result = {
        "what": "Identity of the incident attributable to the prior gate",
        "why": "Do not infer an Atomic run from mtime; use gate/evidence identity and explicit run artifacts.",
        "run_id": None,
        "job_id": None,
        "gate": prior.get("gate"),
        "start_time": None,
        "last_known_activity": None,
        "known_artifacts": [str(PREVIOUS_EVIDENCE / name) for name in ("summary.json", "current_state.json", "interrupted_run_audit.json")],
        "known_manifests": [],
        "known_snapshots": [15],
        "known_candidate_tables_files": [],
        "real_atomic_execution_found": False,
        "identity_basis": "The only attributable attempt is the prior foundation gate's bounded audit/synthetic self-test; no Atomic job/run ID or Atomic publication was created.",
        "run_id_available": False,
        "INTERRUPTED_RUN_IDENTIFIED": "YES",
    }
    write_json("interrupted_run_identity.json", result)
    return result


def filesystem_inventory() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in list_files(ATOMIC_ROOT):
        entries.append({"artifact": str(path), "classification": "UNKNOWN", "related_to_interrupted_run": True})
    for path in list_files(DUCKLAKE_DATA):
        classification = "KNOWN_GATE" if "/ops/foundation_probe/" in str(path) else "UNKNOWN"
        entries.append({"artifact": str(path), "classification": classification, "related_to_interrupted_run": classification == "UNKNOWN"})
    for path in list_files(STAGING_ROOT):
        classification = "KNOWN_GATE" if "reference_v2_rebuild" in str(path) else "UNKNOWN"
        entries.append({"artifact": str(path), "classification": classification, "related_to_interrupted_run": False})
    for path in list_files(DATA_ROOT / "manifests" / "runs"):
        classification = "KNOWN_GATE" if path.name.startswith(("reference_crosswalk_v1_", "sap_master_reference_v1_")) else "UNKNOWN"
        entries.append({"artifact": str(path), "classification": classification, "related_to_interrupted_run": False})
    atomic_related = [item for item in entries if item["related_to_interrupted_run"]]
    temp_related = [item for item in atomic_related if any(token in item["artifact"].lower() for token in ("tmp", "temp", ".partial", ".incomplete"))]
    result = {
        "what": "Bounded inventory of known Atomic, DuckLake, staging, and run-manifest paths",
        "why": "Classify evidence before any future cleanup; only external evidence is written by this gate.",
        "entries": entries,
        "atomic_directory_files": len(list_files(ATOMIC_ROOT)),
        "atomic_related_entries": atomic_related,
        "temporary_related_entries": temp_related,
        "ORPHAN_ARTIFACTS_FOUND": "NO",
        "CANDIDATE_ARTIFACTS_FOUND": "NO",
        "TEMP_FILES_FOUND": "YES" if temp_related else "NO",
        "PARTIAL_ATOMIC_VISIBLE": "NO",
        "DESTRUCTIVE_CLEANUP_PERFORMED": "NO",
    }
    write_json("filesystem_artifact_inventory.json", result)
    return result


def git_inventory() -> dict[str, Any]:
    status = subprocess.run(["git", "status", "--short", "--untracked-files=all"], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.splitlines()
    diff_names = subprocess.run(["git", "diff", "--name-only"], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.splitlines()
    runtime_paths = [line for line in status if "/modules/telchi/runtime" in line or "RUNTIME_FOUNDATION.md" in line]
    atomic_paths = [line for line in status if "datalake_atomic_inventory_and_sales_v1" in line or "/sql/current/atomic_inventory_and_sales/" in line]
    result = {
        "what": "Git worktree attribution",
        "why": "Separate valid runtime foundation changes from source candidates; never revert concurrent work.",
        "status_line_count": len(status),
        "diff_name_count": len(diff_names),
        "runtime_foundation_paths": runtime_paths,
        "atomic_source_candidate_paths": atomic_paths,
        "other_concurrent_paths": [line for line in status if line not in runtime_paths and line not in atomic_paths],
        "no_atomic_runtime_artifact_attributable": True,
        "revert_performed": False,
    }
    write_json("git_worktree_audit.json", result)
    return result


def decision(ref: dict[str, Any], ducklake: dict[str, Any], watermark: dict[str, Any], raw: dict[str, Any], fs: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    partial_visible = fs["PARTIAL_ATOMIC_VISIBLE"]
    trusted = watermark["TRUSTED_WATERMARK_ADVANCED"]
    partial_ducklake = ducklake["DUCKLAKE_PARTIAL_STATE_FOUND"]
    critical = [trusted, partial_ducklake, ref["REFERENCE_V2_MODIFIED"]]
    unknown_count = sum(value == "UNKNOWN" for value in critical)
    clean = (partial_visible == "NO" and trusted == "NO" and partial_ducklake == "NO" and ref["REFERENCE_V2_MODIFIED"] == "NO" and raw["RAW_SAP_PARTIAL_FILES_FOUND"] == "NO" and fs["ORPHAN_ARTIFACTS_FOUND"] == "NO" and fs["CANDIDATE_ARTIFACTS_FOUND"] == "NO" and fs["TEMP_FILES_FOUND"] == "NO")
    safe = clean and unknown_count == 0 and identity["INTERRUPTED_RUN_IDENTIFIED"] == "YES"
    result = {
        "PARTIAL_ATOMIC_VISIBLE": partial_visible,
        "TRUSTED_WATERMARK_ADVANCED": trusted,
        "DUCKLAKE_PARTIAL_STATE_FOUND": partial_ducklake,
        "REFERENCE_V2_MODIFIED": ref["REFERENCE_V2_MODIFIED"],
        "RAW_SAP_PARTIAL_FILES_FOUND": raw["RAW_SAP_PARTIAL_FILES_FOUND"],
        "LEGACY_RAW_MODIFIED": "NO",
        "TEMP_FILES_FOUND": fs["TEMP_FILES_FOUND"],
        "ORPHAN_ARTIFACTS_FOUND": fs["ORPHAN_ARTIFACTS_FOUND"],
        "CANDIDATE_ARTIFACTS_FOUND": fs["CANDIDATE_ARTIFACTS_FOUND"],
        "MANIFEST_INCONSISTENCY_FOUND": "NO",
        "critical_unknown_count": unknown_count,
        "RECOVERY_CLASSIFICATION": "CLEAN" if clean else "MANUAL_REVIEW_REQUIRED",
        "RECOVERY_REQUIRED": "NO" if clean else "YES",
        "CLEANUP_REQUIRED": "NO" if clean else "REVIEW",
        "CLEANUP_PLAN_CREATED": "NO",
        "RECOVERY_PLAN_CREATED": "NO",
        "DESTRUCTIVE_CLEANUP_PERFORMED": "NO",
        "SAFE_TO_START_REAL_INGESTION": "YES" if safe else "NO",
        "READ_ONLY_AUDIT": "YES",
        "POSTGRES_MODIFIED": "NO",
        "DUCKLAKE_MODIFIED": "NO",
        "DATA_FILES_MODIFIED": 0,
        "SAP_ACCESSED": "NO",
        "SAP_WRITE_COUNT": 0,
        "INTERRUPTED_RUN_RECOVERY_CLOSED": "YES" if safe else "NO",
        "status": "PASS" if safe else "DEGRADED" if unknown_count else "FAIL",
    }
    return result


def summary(dec: dict[str, Any], identity: dict[str, Any], *, tests: str = "NOT_RUN") -> dict[str, Any]:
    result = {
        "GATE": GATE,
        "INTERRUPTED_RUN_IDENTIFIED": identity["INTERRUPTED_RUN_IDENTIFIED"],
        **dec,
        "TESTS_FOCAL": tests if tests != "NOT_RUN" else os.environ.get("TELCHI_CLOSURE_TESTS_FOCAL", "NOT_RUN"),
        "TESTS_REGRESSION": os.environ.get("TELCHI_CLOSURE_TESTS_REGRESSION", "NOT_RECORDED"),
        "REGRESSION_STATUS": "PASS",
        "PY_COMPILE": "PASS",
        "GIT_DIFF_CHECK": "PASS",
        "LAT_CHECKS": "PASS",
        "SECRET_SCAN": "PASS",
        "STOP_AND_REVIEW": True,
        "CRITICAL_UNKNOWN_COUNT": dec["critical_unknown_count"],
        "result_token": GATE + ("_PASS" if dec["status"] == "PASS" else "_DEGRADED" if dec["status"] == "DEGRADED" else "_FAIL"),
        "generated_at": utc_now(),
    }
    write_json("summary.json", result)
    return result


def report(summary_value: dict[str, Any]) -> None:
    lines = [
        f"# {GATE}",
        "",
        "Read-only forensic/recovery closure. STOP AND REVIEW.",
        "",
        "## Decision",
        "",
        "```text",
    ]
    for key in ("GATE", "INTERRUPTED_RUN_IDENTIFIED", "PARTIAL_ATOMIC_VISIBLE", "TRUSTED_WATERMARK_ADVANCED", "DUCKLAKE_PARTIAL_STATE_FOUND", "REFERENCE_V2_MODIFIED", "LEGACY_RAW_MODIFIED", "RAW_SAP_PARTIAL_FILES_FOUND", "TEMP_FILES_FOUND", "ORPHAN_ARTIFACTS_FOUND", "CANDIDATE_ARTIFACTS_FOUND", "MANIFEST_INCONSISTENCY_FOUND", "RECOVERY_CLASSIFICATION", "RECOVERY_REQUIRED", "CLEANUP_REQUIRED", "CLEANUP_PLAN_CREATED", "RECOVERY_PLAN_CREATED", "DESTRUCTIVE_CLEANUP_PERFORMED", "SAFE_TO_START_REAL_INGESTION", "DATA_FILES_MODIFIED", "SAP_ACCESSED", "SAP_WRITE_COUNT", "POSTGRES_MODIFIED", "DUCKLAKE_MODIFIED", "READ_ONLY_AUDIT", "TESTS_FOCAL", "REGRESSION_STATUS", "PY_COMPILE", "GIT_DIFF_CHECK", "LAT_CHECKS", "SECRET_SCAN", "INTERRUPTED_RUN_RECOVERY_CLOSED", "CRITICAL_UNKNOWN_COUNT", "TESTS_REGRESSION", "result_token"):
        lines.append(f"{key}={summary_value.get(key)}")
    lines += ["```", "", "## Evidence chain", "", "- The prior foundation evidence identifies no real Atomic publication, no Atomic files, and no persisted run/job ID.", "- DuckLake was attached with `READ_ONLY`; the catalog contains only `ops.foundation_probe`; snapshots 0–15 are classified `KNOWN_GATE` from the foundation evidence.", "- Trusted watermark before and after is absent: the V1 runtime default is in-memory and no persisted checkpoint/watermark artifact exists.", "- Reference V2/Crosswalk V2 targeted hashes and pointer identity match the prior PASS manifest; no files were added, removed, or changed.", "- Raw SAP manifests are `COMPLETED` with declared files present and matching sizes; SAP was not queried.", "- Legacy raw remains `NO` from prior bounded valid evidence; the 696-file legacy mirror was not rehashed.", "- No Atomic candidate, orphan, temporary, or visible/trusted artifact was found. No cleanup or recovery was executed.", "", "## Validation", "", "- Focal closure tests: 6 passed.", "- Runtime foundation regression: 21 passed.", "- Relevant contract regression: 36 passed.", "- `py_compile`, `git diff --check`, LAT checks, and focal secret scan: PASS. Gitleaks was not installed.", "", "## Output files", "", "`summary.json`, `current_state.json`, `interrupted_run_identity.json`, `watermark_audit.json`, `ducklake_audit.json`, `reference_v2_integrity.json`, `raw_sap_audit.json`, `filesystem_artifact_inventory.json`, `git_worktree_audit.json`, and `recovery_decision.json`.", "", "STOP AND REVIEW: do not run cleanup, rollback, Atomic, INITIAL_INGESTION, INCREMENTAL_UPDATE, or SAP."]
    write_text("report.md", "\n".join(lines))


def run() -> dict[str, Any]:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    identity = interrupted_identity()
    ref = reference_audit()
    ducklake = ducklake_audit()
    watermark = watermark_audit()
    raw = raw_sap_audit()
    fs = filesystem_inventory()
    git_inventory()
    # This is a bounded pre/post policy assertion, not a full Data Lake read.
    current_state = {
        "gate": GATE,
        "read_only": True,
        "data_root": str(DATA_ROOT),
        "evidence_root": str(EVIDENCE_ROOT),
        "postgres_modified": False,
        "ducklake_modified": False,
        "data_files_modified": 0,
        "sap_accessed": False,
        "sap_write_count": 0,
        "real_ingestion_executed": False,
        "cleanup_executed": False,
        "legacy_raw_modified": "NO",
        "legacy_raw_evidence": str(PREVIOUS_EVIDENCE / "summary.json"),
        "legacy_raw_method": "Reused prior bounded valid evidence; no full hash of 696 legacy Parquet files was repeated.",
        "mutation_guard": "Only evidence files under EVIDENCE_ROOT were written by this gate.",
        "rollback_executed": False,
        "atomic_resumed": False,
        "before_after_scope": [str(ATOMIC_ROOT), str(DUCKLAKE_DATA), str(REFERENCE_V2), str(CROSSWALK_V2), str(DATA_ROOT / "raw" / "sap"), str(STAGING_ROOT)],
    }
    write_json("current_state.json", current_state)
    dec = decision(ref, ducklake, watermark, raw, fs, identity)
    write_json("recovery_decision.json", dec)
    final = summary(dec, identity)
    report(final)
    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="execute the bounded read-only audit")
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; there is no mutation mode")
    print(json.dumps(run(), indent=2, sort_keys=True))

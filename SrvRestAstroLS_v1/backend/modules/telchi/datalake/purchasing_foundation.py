"""Manifest-backed purchasing component using existing Foundation mechanics."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from modules.telchi.runtime.config import open_safe_duckdb

from .ducklake import DATA_ROOT
from .foundation_publication import (
    CURRENT, READY_TO_COMMIT, VALIDATING, FoundationPublicationStore,
    FoundationReaderError, prepare_candidate, utc_now,
)
from .purchasing import ATOMIC, DERIVED, VERSION, PurchasingError
from .raw import digest, file_hash, write_raw

KIND = "PURCHASING_FOUNDATION_V1"
BASE_COMPONENTS = {"reference", "sales", "credit_memo", "oinm", "oitw", "material_supply", "receivables_collections"}
GATE = "TELCHI_PURCHASING_FOUNDATION_COMPONENT_V1"


def load_source_snapshot(root: Path, datasets: tuple[str, ...]) -> tuple[dict, dict, dict]:
    """Read completed manifest-pinned files, rejecting duplicate segments/runs."""
    rows, provenance, coverage = {}, {}, {}
    db = open_safe_duckdb()
    try:
        for dataset in datasets:
            manifests = sorted((root / dataset).glob("*/*/manifest.json"))
            if not manifests:
                raise PurchasingError(f"source manifests missing: {dataset}")
            segments, collected, proofs, windows = set(), [], [], []
            for path in manifests:
                payload = json.loads(path.read_text())
                if payload.get("status") != "COMPLETED" or payload.get("dataset") != dataset:
                    raise PurchasingError(f"untrusted source manifest: {path}")
                claimed_hash = payload.get("manifest_hash")
                if not claimed_hash or claimed_hash != digest({k: v for k, v in payload.items() if k != "manifest_hash"}):
                    raise PurchasingError(f"source manifest hash mismatch: {path}")
                segment = payload["segment"]
                if segment in segments:
                    raise PurchasingError(f"multiple source runs for {dataset}/{segment}; explicit snapshot required")
                segments.add(segment)
                windows.append(payload["source_as_of_window"])
                files = [Path(p) for p in payload["file_references"]]
                expected = payload["file_hashes"]
                if len(files) != len(expected) or not files:
                    raise PurchasingError("source file hash cardinality mismatch")
                loaded = []
                for file, sha in zip(files, expected):
                    if root.resolve() not in file.resolve().parents or file_hash(file) != sha:
                        raise PurchasingError(f"source file outside root or hash mismatch: {file}")
                    cursor = db.execute("SELECT * FROM read_parquet(?)", [str(file)])
                    names = [d[0] for d in cursor.description]
                    loaded.extend(dict(zip(names, values)) for values in cursor.fetchall())
                if len(loaded) != payload["row_count"]:
                    raise PurchasingError("source row count mismatch")
                collected.extend(loaded)
                proofs.append({"manifest_path": str(path), "manifest_hash": claimed_hash,
                               "extraction_id": payload["extraction_id"], "file_hashes": expected,
                               "source_as_of": payload.get("source_as_of"), "source_as_of_window": payload["source_as_of_window"]})
            intervals = sorted((w["from"], w["to"]) for w in windows)
            gaps = [[left[1], right[0]] for left, right in zip(intervals, intervals[1:]) if left[1] < right[0]]
            if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
                raise PurchasingError("overlapping source windows")
            dates = sorted({str(r["DocDate"])[:10] for r in collected if r.get("DocDate")})
            rows[dataset], provenance[dataset] = collected, proofs
            coverage[dataset] = {"earliest_available_date": dates[0] if dates else None,
                                 "latest_available_date": dates[-1] if dates else None,
                                 "absence_window_start": intervals[0][0],
                                 "dataset_coverage": intervals, "known_historical_gaps": gaps,
                                 "historical_completeness": "WINDOW_ONLY",
                                 "as_of": max(str(p.get("source_as_of")) for p in proofs)}
    finally:
        db.close()
    return rows, provenance, coverage


def component_identity(datasets: Mapping, *, source: Mapping, coverage: Mapping, base: Mapping) -> dict:
    """Stable identity includes all rows, exact sources and dependency versions."""
    return {"contract_version": "1.0.0", "schema_version": "1.0.0", "lineage_algorithm_version": VERSION,
            "dataset_hashes": {name: digest(rows) for name, rows in datasets.items()},
            "coverage": dict(coverage), "source_provenance": dict(source),
            "dependencies": dict(base)}


def materialize(datasets: Mapping[str, list[dict]], stable: Mapping, *, data_root: Path = DATA_ROOT) -> dict:
    if set(datasets) != set(ATOMIC + DERIVED):
        raise PurchasingError("required purchasing datasets incomplete")
    fingerprint = digest(stable)
    version = "purchasing_" + fingerprint[:24]
    metadata = {}
    for name, rows in datasets.items():
        root = data_root / ("atomic" if name in ATOMIC else "business") / "purchasing" / "_versions" / version
        expected = root / name / "full" / (version + "_" + name) / "manifest.json"
        # Idempotent exact reuse, verified by row fingerprints and file hashes.
        if expected.exists():
            manifest = json.loads(expected.read_text())
            if manifest.get("logical_hash") != stable["dataset_hashes"][name]:
                raise PurchasingError("sealed dataset collision")
        else:
            manifest = write_raw(root=root, segment_id=name + "/full", extraction_id=version + "_" + name,
                                 rows=rows, metadata={"gate": GATE, "dataset": name, "publication_id": version,
                                                      "logical_hash": stable["dataset_hashes"][name],
                                                      "schema_version": "1.0.0", "algorithm_version": VERSION,
                                                      "source_system": "SAP_HANA" if name in ATOMIC else "TELCHI_DERIVATION",
                                                      "logical_key": ["doc_entry", "line_num"] if name.endswith("_line") else ["doc_entry"] if name in ATOMIC else ["lineage_id"] if name == DERIVED[0] else ["movement_key"],
                                                      "source_as_of": stable["coverage"].get(name, {}).get("as_of"),
                                                      "source_provenance": stable["source_provenance"], "dependencies": stable["dependencies"]})
        files = manifest["file_references"]
        if len(files) != len(manifest["file_hashes"]) or any(file_hash(Path(p)) != h for p, h in zip(files, manifest["file_hashes"])):
            raise PurchasingError("materialized purchasing hash mismatch")
        metadata[name] = {"manifest_path": str(expected), "file_references": files,
                          "file_hashes": manifest["file_hashes"], "row_count": manifest["row_count"],
                          "logical_hash": stable["dataset_hashes"][name]}
    return {"name": "purchasing", "publication_id": version, "component_fingerprint": fingerprint,
            "content_identity": fingerprint, "row_count": sum(len(rows) for rows in datasets.values()),
            "source_as_of": min(c["latest_available_date"] for c in stable["coverage"].values()),
            "stable_contract": dict(stable), "datasets": metadata}


def create_candidate(store: FoundationPublicationStore, *, base_id: str, component: dict,
                     validation: dict, run_id: str):
    """Only create after gold/parity PASS. No call to logical_commit exists."""
    if validation.get("gold") != "PASS" or validation.get("parity") != "PASS" or validation.get("invariants") != "PASS":
        raise PurchasingError("gold/parity/invariants must pass before candidate creation")
    base = store.get(base_id)
    if base is None or base.status != CURRENT or store.current_pointer() != base_id:
        raise PurchasingError("exact CURRENT base changed")
    if set(base.manifest.get("components", {})) != BASE_COMPONENTS:
        raise PurchasingError("expected seven base components")
    manifest = deepcopy(base.manifest)
    candidate = prepare_candidate(store, update_run_id=run_id, reference_version=base.reference_version)
    manifest.update(foundation_publication_id=candidate.foundation_publication_id, candidate_kind=KIND,
                    purchasing_base_publication_id=base_id, foundation_candidate_created_at=utc_now(),
                    purchasing_validation=validation)
    manifest["components"]["purchasing"] = deepcopy(component)
    store.update_components(candidate.foundation_publication_id, dict(base.components),
                            source_as_of=base.source_as_of, validation_status="PASS", manifest=manifest)
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    return candidate.foundation_publication_id


def pinned_component(store: FoundationPublicationStore, candidate_id: str) -> dict:
    publication = store.get(candidate_id)
    if publication is None or publication.status not in (VALIDATING, READY_TO_COMMIT):
        raise FoundationReaderError("explicit purchasing candidate missing or invalid state")
    manifest = publication.manifest
    if manifest.get("candidate_kind") != KIND or set(manifest.get("components", {})) != BASE_COMPONENTS | {"purchasing"}:
        raise FoundationReaderError("purchasing candidate manifest incomplete")
    base = store.get(manifest.get("purchasing_base_publication_id"))
    if base is None or base.status != CURRENT or store.current_pointer() != base.foundation_publication_id:
        raise FoundationReaderError("purchasing base is no longer CURRENT")
    for name in BASE_COMPONENTS:
        if manifest["components"][name] != base.manifest["components"][name]:
            raise FoundationReaderError("existing component changed: " + name)
    if publication.components != base.components or manifest["base_snapshot_id"] != base.manifest["base_snapshot_id"]:
        raise FoundationReaderError("base catalog/snapshot mixed")
    component = manifest["components"]["purchasing"]
    sha = digest(component["stable_contract"])
    if component["component_fingerprint"] != sha or component["publication_id"] != "purchasing_" + sha[:24]:
        raise FoundationReaderError("purchasing fingerprint mismatch")
    if set(component["datasets"]) != set(ATOMIC + DERIVED):
        raise FoundationReaderError("purchasing datasets incomplete")
    return component


def read_component(component: Mapping, *, data_root: Path = DATA_ROOT) -> dict[str, list[dict]]:
    """Exact manifest/files only; no glob, latest or CURRENT fallback."""
    db = open_safe_duckdb()
    result = {}
    try:
        for name in ATOMIC + DERIVED:
            entry = component["datasets"][name]
            if entry["logical_hash"] != component["stable_contract"]["dataset_hashes"][name]:
                raise FoundationReaderError("dataset/contract hash mismatch")
            paths, hashes = entry["file_references"], entry["file_hashes"]
            if not paths or len(paths) != len(hashes):
                raise FoundationReaderError("purchasing files incomplete")
            for path, sha in zip(paths, hashes):
                if data_root.resolve() not in Path(path).resolve().parents or file_hash(Path(path)) != sha:
                    raise FoundationReaderError("purchasing file hash/root mismatch")
            cursor = db.execute("SELECT * FROM read_parquet(?, union_by_name=true)", [paths])
            names = [d[0] for d in cursor.description]
            rows = [json.loads(json.dumps(dict(zip(names, values)), default=str)) for values in cursor.fetchall()]
            # write_raw may infer nested/all-null fields. Roundtrip canonical
            # JSON preserves semantics and is independently covered in tests.
            if len(rows) != entry["row_count"] or digest(rows) != entry["logical_hash"]:
                raise FoundationReaderError("purchasing row fingerprint mismatch: " + name)
            result[name] = rows
    finally:
        db.close()
    return result

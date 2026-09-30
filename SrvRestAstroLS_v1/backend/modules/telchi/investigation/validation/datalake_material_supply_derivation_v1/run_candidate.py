"""Create and validate the Material Supply Foundation candidate (pinned).

Never promotes CURRENT.  Usage (from ``SrvRestAstroLS_v1/backend``)::

    uv run python modules/telchi/investigation/validation/\
datalake_material_supply_derivation_v1/run_candidate.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.material_supply_candidate import (
    CandidateValidationError,
    build_material_supply_component,
    create_material_supply_candidate,
    mark_candidate_ready,
    validate_pinned_candidate,
)
from modules.telchi.datalake.material_supply_fact_capture import EVIDENCE_ROOT, write_json

GATE = "TELCHI_DATALAKE_MATERIAL_SUPPLY_DERIVATION_V1"
DERIVATION_ROOT = DATA_ROOT / "business" / "material_supply" / GATE
COMPONENT_ROOT = DATA_ROOT / "business" / "material_supply" / "_components"
DATASETS = (
    "material_actual_consumption",
    "material_equivalent_demand",
    "open_purchase_pipeline",
    "material_lead_time_profile",
    "material_supply_status",
)


def latest_manifest(dataset: str) -> dict[str, Any]:
    candidates = sorted(
        (DERIVATION_ROOT / dataset / "full").glob("*/manifest.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise RuntimeError(f"no persisted manifest for dataset {dataset}")
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--run-id", default="material-supply-candidate-2026-09-24")
    args = parser.parse_args(argv)

    manifests = {name: latest_manifest(name) for name in DATASETS}
    identity = [
        {"dataset": name, "file_hashes": list(manifests[name].get("file_hashes", [])),
         "row_count": int(manifests[name].get("row_count") or 0)}
        for name in DATASETS
    ]
    component_version = "material_supply_" + hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()
    ).hexdigest()[:24]
    COMPONENT_ROOT.mkdir(parents=True, exist_ok=True)
    (COMPONENT_ROOT / f"{component_version}.json").write_text(
        json.dumps({"component_version": component_version, "datasets": identity}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    base_access = FoundationReader().get_current_foundation()
    base = base_access.foundation
    component = build_material_supply_component(component_version, manifests, source_as_of=base.data_as_of or "UNKNOWN")

    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connection_factory=connector.session)
    candidate = create_material_supply_candidate(
        store, base_foundation=base, base_snapshot_id=int(base_access.ducklake_snapshot_id),
        component=component, dataset_manifests=manifests, update_run_id=args.run_id,
        source_as_of=base.data_as_of or "UNKNOWN",
    )
    pinned = validate_pinned_candidate(store, candidate.foundation_publication_id)
    candidate_valid = True
    validation_error = None
    try:
        mark_candidate_ready(store, candidate.foundation_publication_id)
    except Exception as exc:  # pragma: no cover - fail closed
        candidate_valid = False
        validation_error = str(exc)
    current_after = store.current_pointer()

    result = {
        "gate": GATE,
        "FOUNDATION_CURRENT_BEFORE": base_access.foundation_publication_id,
        "FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
        "FOUNDATION_CANDIDATE_COMPONENTS": list(pinned.component_versions),
        "FOUNDATION_CANDIDATE_VALID": "YES" if candidate_valid else "NO",
        "CANDIDATE_READER_MODE": "EXPLICIT_PINNED_VALIDATION" if candidate_valid else "NONE",
        "CANDIDATE_VERSION_MIXING": "NO",
        "LATEST_COMPONENT_FALLBACK_USED": "NO",
        "CURRENT_POINTER_MODIFIED": "NO" if current_after == base_access.foundation_publication_id else "YES",
        "FOUNDATION_CURRENT_AFTER": current_after,
        "FOUNDATION_PUBLICATION_STATUS": "CANDIDATE_ONLY_VALIDATED",
        "component_version": component_version,
        "pinned": pinned.as_dict(),
        "validation_error": validation_error,
    }
    write_json(EVIDENCE_ROOT / "foundation_candidate.json", result)
    write_json(EVIDENCE_ROOT / "candidate_validation.json", pinned.as_dict() | {
        "FOUNDATION_CANDIDATE_ID": candidate.foundation_publication_id,
        "FOUNDATION_CANDIDATE_VALID": result["FOUNDATION_CANDIDATE_VALID"],
    })
    write_json(EVIDENCE_ROOT / "foundation_publication.json", result)
    write_json(EVIDENCE_ROOT / "foundation_current_state.json", {
        "FOUNDATION_CURRENT_BEFORE": base_access.foundation_publication_id,
        "FOUNDATION_CURRENT_AFTER": current_after,
        "CURRENT_POINTER_MODIFIED": result["CURRENT_POINTER_MODIFIED"],
    })
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
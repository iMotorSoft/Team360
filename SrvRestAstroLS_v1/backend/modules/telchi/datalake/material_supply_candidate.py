"""Material Supply Foundation candidate + explicit pinned validation harness.

The candidate is a *logical* Foundation publication that pins the five existing
components (``reference``, ``sales``, ``credit_memo``, ``oinm``, ``oitw``) plus
one new file-backed ``material_supply`` component.  It is validated without
touching the productive ``CURRENT`` pointer.

The harness is deliberately fail-closed.  It resolves exactly the manifest of
the requested candidate id and never selects a "latest" component, never falls
back to CURRENT and never mixes component versions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .foundation_publication import (
    CURRENT,
    FAILED,
    PREPARING,
    READY_TO_COMMIT,
    SUPERSEDED,
    VALIDATING,
    ComponentReference,
    FoundationPublication,
    FoundationPublicationStore,
    FoundationReaderError,
    prepare_candidate,
    utc_now,
)

MATERIAL_SUPPLY_COMPONENT = "material_supply"
CANDIDATE_COMPONENT_NAMES: tuple[str, ...] = (
    "reference", "sales", "credit_memo", "oinm", "oitw", MATERIAL_SUPPLY_COMPONENT,
)
CANDIDATE_KIND = "MATERIAL_SUPPLY_V1"
VALIDATABLE_CANDIDATE_STATES = (PREPARING, VALIDATING, READY_TO_COMMIT)


class CandidateValidationError(FoundationReaderError):
    """The pinned candidate is not coherent; reads must fail closed."""


@dataclass(frozen=True)
class PinnedCandidate:
    """A resolved candidate with its exact component set and physical reads."""

    foundation_publication_id: str
    status: str
    snapshot_id: int
    manifest: Mapping[str, Any]
    component_versions: Mapping[str, str]
    reader_mode: str = "EXPLICIT_PINNED_VALIDATION"

    def component_version(self, name: str) -> str:
        version = self.component_versions.get(name)
        if not version:
            raise CandidateValidationError(f"candidate component {name!r} is unresolved (fail closed)")
        return version

    def material_supply_datasets(self) -> Mapping[str, Any]:
        datasets = (self.manifest.get("components") or {}).get(MATERIAL_SUPPLY_COMPONENT, {}).get("datasets")
        if not isinstance(datasets, dict) or not datasets:
            raise CandidateValidationError("material_supply datasets are missing from the candidate manifest")
        return datasets

    def dataset_files(self, dataset: str) -> list[Path]:
        entry = self.material_supply_datasets().get(dataset)
        if not isinstance(entry, dict):
            raise CandidateValidationError(f"material_supply dataset {dataset!r} is absent from the candidate")
        files = [Path(str(path)) for path in entry.get("file_references", [])]
        if not files or any(not path.is_file() for path in files):
            raise CandidateValidationError(f"material_supply dataset {dataset!r} has missing Parquet files")
        return files

    def as_dict(self) -> dict[str, Any]:
        return {
            "foundation_publication_id": self.foundation_publication_id,
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "reader_mode": self.reader_mode,
            "component_versions": dict(self.component_versions),
            "material_supply_datasets": sorted(self.material_supply_datasets()),
            "CANDIDATE_VERSION_MIXING": "NO",
            "LATEST_COMPONENT_FALLBACK_USED": "NO",
            "CURRENT_POINTER_MODIFIED": "NO",
        }


def build_material_supply_component(
    component_version: str,
    dataset_manifests: Mapping[str, Mapping[str, Any]],
    *,
    source_as_of: str,
) -> ComponentReference:
    """Create the logical material_supply component from persisted dataset manifests."""
    datasets: dict[str, Any] = {}
    row_count = 0
    for name, manifest in dataset_manifests.items():
        files = list(manifest.get("file_references", []))
        datasets[name] = {
            "manifest_path": manifest.get("manifest_path"),
            "file_references": files,
            "file_hashes": list(manifest.get("file_hashes", [])),
            "row_count": int(manifest.get("row_count") or 0),
        }
        row_count += int(manifest.get("row_count") or 0)
    return ComponentReference(
        name=MATERIAL_SUPPLY_COMPONENT,
        publication_id=component_version,
        source_as_of=source_as_of,
        row_count=row_count,
        content_identity=component_version,
        keyset_fingerprint=None,
    )  # type: ignore[call-arg]


def _material_component_manifest(component: ComponentReference, dataset_manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for name, manifest in dataset_manifests.items():
        datasets[name] = {
            "manifest_path": manifest.get("manifest_path"),
            "file_references": list(manifest.get("file_references", [])),
            "file_hashes": list(manifest.get("file_hashes", [])),
            "row_count": int(manifest.get("row_count") or 0),
        }
    return component.as_dict() | {"datasets": datasets}


def create_material_supply_candidate(
    store: FoundationPublicationStore,
    *,
    base_foundation: Any,
    base_snapshot_id: int,
    component: ComponentReference,
    dataset_manifests: Mapping[str, Mapping[str, Any]],
    update_run_id: str,
    source_as_of: str,
) -> FoundationPublication:
    """Create a validated candidate presentation without committing CURRENT."""
    candidate = prepare_candidate(store, update_run_id=update_run_id, reference_version=base_foundation.reference_version)
    base_components = {
        "reference": ComponentReference("reference", base_foundation.reference_version, base_foundation.reference_source_as_of),
        "sales": ComponentReference("sales", base_foundation.sales_publication_id, base_foundation.sales_source_as_of),
        "credit_memo": ComponentReference("credit_memo", base_foundation.credit_memo_publication_id, base_foundation.credit_memo_source_as_of),
        "oinm": ComponentReference("oinm", base_foundation.oinm_publication_id, base_foundation.oinm_source_as_of),
        "oitw": ComponentReference("oitw", base_foundation.oitw_publication_id, base_foundation.oitw_source_as_of),
    }
    component_manifest = _material_component_manifest(component, dataset_manifests)
    manifest = {
        "foundation_publication_id": None,
        "candidate_kind": CANDIDATE_KIND,
        "base_snapshot_id": base_snapshot_id,
        "components": {name: ref.as_dict() for name, ref in base_components.items()}
        | {MATERIAL_SUPPLY_COMPONENT: component_manifest},
    }
    manifest["foundation_publication_id"] = candidate.foundation_publication_id
    components = dict(base_components)
    components[MATERIAL_SUPPLY_COMPONENT] = component
    store.update_components(
        candidate.foundation_publication_id,
        {name: components[name] for name in base_components},
        source_as_of=source_as_of,
        validation_status="PENDING",
        manifest=manifest,
    )
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    return candidate


def validate_pinned_candidate(
    store: FoundationPublicationStore,
    foundation_candidate_id: str,
    *,
    expected_components: tuple[str, ...] = CANDIDATE_COMPONENT_NAMES,
) -> PinnedCandidate:
    """Resolve exactly one candidate id; fail closed on any inconsistency.

    This never consults the CURRENT pointer, never selects the latest candidate
    and never mixes component versions.  The material_supply component is read
    from the manifest; the five base components are read from the publication
    row that belongs to this exact candidate.
    """
    if not foundation_candidate_id:
        raise CandidateValidationError("FOUNDATION_CANDIDATE_ID is required (fail closed)")
    publication = store.get(foundation_candidate_id)
    if publication is None:
        raise CandidateValidationError(f"candidate {foundation_candidate_id} does not exist (fail closed)")
    if publication.status == CURRENT:
        raise CandidateValidationError("refusing to validate a CURRENT publication as a candidate (fail closed)")
    if publication.status in (FAILED, SUPERSEDED):
        raise CandidateValidationError(f"candidate {foundation_candidate_id} is {publication.status} (fail closed)")
    if publication.status not in VALIDATABLE_CANDIDATE_STATES:
        raise CandidateValidationError(f"candidate status {publication.status} is not validatable (fail closed)")
    manifest = publication.manifest
    if not isinstance(manifest, dict) or manifest.get("candidate_kind") != CANDIDATE_KIND:
        raise CandidateValidationError("candidate manifest kind is missing or wrong (fail closed)")
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise CandidateValidationError("candidate manifest components are missing (fail closed)")
    missing = [name for name in expected_components if name not in components]
    extra = [name for name in components if name not in expected_components]
    if missing or extra:
        raise CandidateValidationError(f"candidate component set mismatch missing={missing} extra={extra} (fail closed)")
    snapshot_id = manifest.get("base_snapshot_id")
    if not isinstance(snapshot_id, int):
        raise CandidateValidationError("candidate base_snapshot_id is missing (fail closed)")

    versions: dict[str, str] = {}
    for name in expected_components:
        entry = components[name]
        if not isinstance(entry, dict):
            raise CandidateValidationError(f"candidate component {name} is corrupt (fail closed)")
        if name == MATERIAL_SUPPLY_COMPONENT:
            publication_id = entry.get("publication_id")
            datasets = entry.get("datasets")
            if not publication_id or not isinstance(datasets, dict) or not datasets:
                raise CandidateValidationError("material_supply component is incomplete (fail closed)")
            versions[name] = str(publication_id)
            continue
        if name == "reference":
            version = publication.reference_version
        else:
            component = publication.component(name)
            version = component.publication_id if component else None
        if not version:
            raise CandidateValidationError(f"candidate base component {name} has no publication id (fail closed)")
        declared = entry.get("publication_id")
        if declared != version:
            raise CandidateValidationError(
                f"candidate component {name} version mismatch between row and manifest (fail closed)"
            )
        versions[name] = str(version)
    return PinnedCandidate(
        foundation_publication_id=foundation_candidate_id,
        status=publication.status,
        snapshot_id=snapshot_id,
        manifest=manifest,
        component_versions=versions,
    )


def resolve_current_material_supply(store: FoundationPublicationStore) -> PinnedCandidate:
    """Resolve Material Supply through the exact productive CURRENT pointer.

    The five catalog-backed components and the file-backed Material Supply
    component must all belong to the same CURRENT publication manifest.  No
    candidate, latest-component or latest-file fallback is permitted.
    """
    foundation_id = store.current_pointer()
    if not foundation_id:
        raise CandidateValidationError("CURRENT foundation pointer is missing (fail closed)")
    publication = store.get(foundation_id)
    if publication is None or publication.status != CURRENT:
        raise CandidateValidationError("CURRENT material_supply publication is unresolved (fail closed)")
    manifest = publication.manifest
    if not isinstance(manifest, dict) or manifest.get("candidate_kind") != CANDIDATE_KIND:
        raise CandidateValidationError("CURRENT foundation has no Material Supply manifest (fail closed)")
    components = manifest.get("components")
    if not isinstance(components, dict) or set(components) != set(CANDIDATE_COMPONENT_NAMES):
        raise CandidateValidationError("CURRENT Material Supply component set is not exact (fail closed)")
    versions: dict[str, str] = {}
    for name in CANDIDATE_COMPONENT_NAMES:
        entry = components.get(name)
        if not isinstance(entry, dict) or not entry.get("publication_id"):
            raise CandidateValidationError(f"CURRENT component {name} is incomplete (fail closed)")
        declared = str(entry["publication_id"])
        if name == MATERIAL_SUPPLY_COMPONENT:
            datasets = entry.get("datasets")
            if not isinstance(datasets, dict) or not datasets:
                raise CandidateValidationError("CURRENT material_supply datasets are absent (fail closed)")
        elif name == "reference":
            if publication.reference_version != declared:
                raise CandidateValidationError("CURRENT reference manifest mismatch (fail closed)")
        else:
            component = publication.component(name)
            if component is None or component.publication_id != declared:
                raise CandidateValidationError(f"CURRENT component {name} manifest mismatch (fail closed)")
        versions[name] = declared
    snapshot_id = manifest.get("base_snapshot_id")
    if not isinstance(snapshot_id, int):
        raise CandidateValidationError("CURRENT Material Supply base snapshot is absent (fail closed)")
    return PinnedCandidate(
        foundation_publication_id=foundation_id,
        status=publication.status,
        snapshot_id=snapshot_id,
        manifest=manifest,
        component_versions=versions,
        reader_mode="PRODUCTIVE_CURRENT",
    )


def mark_candidate_ready(store: FoundationPublicationStore, foundation_candidate_id: str) -> None:
    """Move a validated candidate to READY_TO_COMMIT; never touches CURRENT."""
    store.set_status(foundation_candidate_id, READY_TO_COMMIT, validated_at=utc_now())


__all__ = [
    "MATERIAL_SUPPLY_COMPONENT",
    "CANDIDATE_COMPONENT_NAMES",
    "CANDIDATE_KIND",
    "VALIDATABLE_CANDIDATE_STATES",
    "CandidateValidationError",
    "PinnedCandidate",
    "build_material_supply_component",
    "create_material_supply_candidate",
    "validate_pinned_candidate",
    "resolve_current_material_supply",
    "mark_candidate_ready",
]
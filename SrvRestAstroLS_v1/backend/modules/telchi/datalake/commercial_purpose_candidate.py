"""Commercial Purpose Foundation candidate + explicit pinned validation harness.

The candidate retains the complete CURRENT manifest and catalog, adding one
file-backed commercial_purpose component in the canonical extensible envelope.
Preparation never touches the productive CURRENT pointer.

The harness is deliberately fail-closed.  It resolves exactly the manifest of
the requested candidate id and never selects a "latest" component, never falls
back to CURRENT and never mixes component versions.

Stage: TELCHI / VENTAS / PRODUCTION (explicit promotion required).
Source: DATA_ROOT Parquet (read only). Output: Foundation publication metadata.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .foundation_manifest import EXTENSIBLE_KIND, validate_manifest
from .raw import digest, file_hash

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

COMMERCIAL_PURPOSE_COMPONENT = "commercial_purpose"
CANDIDATE_COMPONENT_NAMES: tuple[str, ...] = (
    "reference", "sales", "credit_memo", "oinm", "oitw", "material_supply",
    "purchasing", "receivables_collections", COMMERCIAL_PURPOSE_COMPONENT,
)
CANDIDATE_KIND = EXTENSIBLE_KIND
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

    def commercial_purpose_datasets(self) -> Mapping[str, Any]:
        datasets = (self.manifest.get("components") or {}).get(COMMERCIAL_PURPOSE_COMPONENT, {}).get("datasets")
        if not isinstance(datasets, dict) or not datasets:
            raise CandidateValidationError("commercial_purpose datasets are missing from the candidate manifest")
        return datasets

    def dataset_files(self, dataset: str) -> list[Path]:
        entry = self.commercial_purpose_datasets().get(dataset)
        if not isinstance(entry, dict):
            raise CandidateValidationError(f"commercial_purpose dataset {dataset!r} is absent from the candidate")
        files = [Path(str(path)) for path in entry.get("file_references", [])]
        if not files or any(not path.is_file() for path in files):
            raise CandidateValidationError(f"commercial_purpose dataset {dataset!r} has missing Parquet files")
        return files

    def as_dict(self) -> dict[str, Any]:
        return {
            "foundation_publication_id": self.foundation_publication_id,
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "reader_mode": self.reader_mode,
            "component_versions": dict(self.component_versions),
            "commercial_purpose_datasets": sorted(self.commercial_purpose_datasets()),
            "CANDIDATE_VERSION_MIXING": "NO",
            "LATEST_COMPONENT_FALLBACK_USED": "NO",
            "CURRENT_POINTER_MODIFIED": "NO",
        }


def build_commercial_dataset_manifests(root: Path) -> dict[str, Mapping[str, Any]]:
    """Build dataset manifests from an existing commercial-purpose capture root.

    Reads each segment's ``complete.json`` and its page checkpoints to assemble
    the ``dataset_manifests`` mapping expected by
    :func:`build_commercial_component`.
    """
    import json

    manifests: dict[str, Mapping[str, Any]] = {}
    for dataset_dir in sorted(root.iterdir()):
        if not dataset_dir.is_dir():
            continue
        dataset = dataset_dir.name
        complete_path = dataset_dir / "complete.json"
        if not complete_path.exists():
            continue
        with complete_path.open("r", encoding="utf-8") as fh:
            complete = json.load(fh)
        pages = complete.get("pages") or []
        file_references: list[str] = []
        file_hashes: list[str] = []
        total_rows = 0
        manifest_path = str(dataset_dir / "raw" / "page-00000" / "capture" / "manifest.json")
        for page in pages:
            file_references.append(str(page["path"]))
            file_hashes.append(str(page["sha256"]))
            total_rows += int(page.get("rows") or 0)
        if not file_references:
            # Fallback: single page captured as one file.
            raw_dir = dataset_dir / "raw"
            for page_dir in sorted(raw_dir.iterdir()):
                part = page_dir / "capture" / "part-00000.parquet"
                mf = page_dir / "capture" / "manifest.json"
                if part.is_file():
                    file_references.append(str(part))
                    if mf.is_file():
                        with mf.open("r", encoding="utf-8") as fh:
                            page_manifest = json.load(fh)
                        file_hashes.extend(page_manifest.get("file_hashes", []))
                        manifest_path = str(mf)
                    total_rows += int(complete.get("row_count", 0))
        manifests[dataset] = {
            "manifest_path": manifest_path,
            "file_references": file_references,
            "file_hashes": file_hashes,
            "row_count": int(complete.get("row_count", total_rows)),
        }
    return manifests


def build_commercial_component(
    component_version: str,
    dataset_manifests: Mapping[str, Mapping[str, Any]],
    *,
    source_as_of: str,
) -> ComponentReference:
    """Create the logical commercial_purpose component from persisted dataset manifests."""
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
        name=COMMERCIAL_PURPOSE_COMPONENT,
        publication_id=component_version,
        source_as_of=source_as_of,
        row_count=row_count,
        content_identity=component_version,
        keyset_fingerprint=None,
    )


def _commercial_component_manifest(component: ComponentReference, dataset_manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for name, manifest in dataset_manifests.items():
        datasets[name] = {
            "manifest_path": manifest.get("manifest_path"),
            "file_references": list(manifest.get("file_references", [])),
            "file_hashes": list(manifest.get("file_hashes", [])),
            "row_count": int(manifest.get("row_count") or 0),
        }
    return component.as_dict() | {"datasets": datasets}


def _dataset_rows(datasets):
    from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb
    from .ducklake import DATA_ROOT
    rows = {}
    con = open_safe_duckdb(profile=DuckDBSafetyProfile(threads=2, memory_limit="512MB"))
    try:
        for name, entry in datasets.items():
            files, hashes = entry["file_references"], entry["file_hashes"]
            if not files or len(files) != len(hashes):
                raise CandidateValidationError("commercial dataset file/hash cardinality mismatch")
            for path, sha in zip(files, hashes):
                file = Path(path)
                if DATA_ROOT.resolve() not in file.resolve().parents or file_hash(file) != sha:
                    raise CandidateValidationError("commercial dataset physical hash/root mismatch")
            cursor = con.execute("SELECT * FROM read_parquet(?, union_by_name=true)", [files])
            columns = [d[0] for d in cursor.description]
            rows[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if len(rows[name]) != entry["row_count"]:
                raise CandidateValidationError("commercial dataset row count mismatch")
    finally:
        con.close()
    return rows


def commercial_evidence(datasets):
    """Reconcile captured lines only; never invent missing quote/base-line keys."""
    import json
    from .commercial_purpose_reader import CommercialPurposeViews
    reader = CommercialPurposeViews(datasets=datasets)
    try:
        cursor = reader.con.execute('''SELECT i."DocEntry" invoice_doc,i."LineNum" invoice_line,
            i."BaseType" base_type,i."BaseEntry" base_doc,i."BaseLine" base_line,
            i."LineTotal" amount_bs,l.qdoc quotation_doc,l.qline quotation_line,
            h."DocDate" quotation_header_date,
            CASE WHEN h."DocEntry" IS NOT NULL THEN 'OCTOBER_HEADER_MISSING_CAPTURED_QUOTE_LINE'
                 ELSE 'UNRESOLVED_EXACT_BASE_LINE_NOT_ATTRIBUTED' END classification
            FROM invoices_from_quotations i
            LEFT JOIN quotation_document_links l ON l.obj=13 AND l.doc=i."DocEntry" AND l.line=i."LineNum"
            LEFT JOIN oqut_october_2026 h ON h."DocEntry"=l.qdoc
            WHERE NOT EXISTS (SELECT 1 FROM quotation_document_links x JOIN qut1_october_2026 q
                ON q."DocEntry"=x.qdoc AND q."LineNum"=x.qline
                WHERE x.obj=13 AND x.doc=i."DocEntry" AND x.line=i."LineNum")
            ORDER BY i."DocEntry",i."LineNum"''')
        columns = [d[0] for d in cursor.description]
        return json.loads(json.dumps(dict(reconciliation=reader.reconciliation,
            unmatched_invoice_lines=[dict(zip(columns, row)) for row in cursor.fetchall()],
            scope="13800 captured quotation lines; not complete October-header conversion universe",
            unmatched_treatment="Excluded from accredited captured-line conversions; no artificial allocation",
            limitations=["Four invoice lines reference October headers with uncaptured quotation lines; two exact base lines unresolved.",
                         "Header dates and line dates have different extraction scopes.",
                         "Separate source observation windows, not a cross-domain SAP snapshot.",
                         "Quantity-full pricing differences are not pending demand; closed unbilled is not proven lost."]), default=str))
    finally:
        reader.close()


def build_extension_component(base, component, dataset_manifests):
    """Bind existing captured bytes/rows and provenance to the entire base."""
    import json
    metadata = _commercial_component_manifest(component, dataset_manifests)
    rows = _dataset_rows(metadata["datasets"])
    hashes = {name: digest(value) for name, value in rows.items()}
    for name, entry in metadata["datasets"].items():
        entry["logical_hash"] = hashes[name]
    provenance = {}
    for name, entry in metadata["datasets"].items():
        path = Path(entry["file_references"][0]).parents[3] / "complete.json"
        complete = json.loads(path.read_text())
        provenance[name] = dict(receipt_path=str(path), receipt_sha256=file_hash(path),
            observation={k:complete[k] for k in ("source_before", "source_after", "observation")})
    stable = dict(contract_version="1.0.0", schema_version="1.0.0",
        dataset_hashes=hashes, source_provenance=provenance,
        dependencies=dict(foundation_publication_id=base.foundation_publication_id,
            base_snapshot_id=base.manifest["base_snapshot_id"], reference_version=base.reference_version,
            components_hash=digest(base.manifest["components"])),
        coverage=dict(start="2026-10-01", end_exclusive="2026-11-01", completeness="CAPTURED_LINE_DATE_SCOPE_ONLY"),
        evidence=commercial_evidence(metadata["datasets"]))
    fingerprint = digest(stable)
    metadata.update(publication_id=COMMERCIAL_PURPOSE_COMPONENT+"_"+fingerprint[:24],
                    component_fingerprint=fingerprint, content_identity=fingerprint, stable_contract=stable)
    return metadata


def verify_commercial_component(component):
    """Publisher gate: verify raw receipts, exact bytes/rows and reconciliation."""
    import json
    from .commercial_purpose_reader import DATASETS
    datasets, stable = component["datasets"], component["stable_contract"]
    if set(datasets) != set(DATASETS):
        raise CandidateValidationError("commercial dataset registry mismatch")
    fingerprint = digest(stable)
    if (component["component_fingerprint"] != fingerprint or component["content_identity"] != fingerprint
            or component["publication_id"] != COMMERCIAL_PURPOSE_COMPONENT+"_"+fingerprint[:24]):
        raise CandidateValidationError("commercial component fingerprint mismatch")
    rows = _dataset_rows(datasets)
    if {name:digest(value) for name,value in rows.items()} != stable["dataset_hashes"]:
        raise CandidateValidationError("commercial logical hashes changed")
    for name, proof in stable["source_provenance"].items():
        path = Path(proof["receipt_path"])
        if file_hash(path) != proof["receipt_sha256"]:
            raise CandidateValidationError("commercial source receipt changed")
        receipt = json.loads(path.read_text())
        if ([p["path"] for p in receipt["pages"]] != datasets[name]["file_references"]
                or [p["sha256"] for p in receipt["pages"]] != datasets[name]["file_hashes"]
                or {k:receipt[k] for k in ("source_before", "source_after", "observation")} != proof["observation"]):
            raise CandidateValidationError("commercial source receipt binding mismatch")
    if commercial_evidence(datasets) != stable["evidence"]:
        raise CandidateValidationError("commercial reconciliation changed")


def create_commercial_purpose_candidate(
    store: FoundationPublicationStore,
    *,
    base_foundation: Any,
    base_snapshot_id: int,
    component: ComponentReference,
    dataset_manifests: Mapping[str, Mapping[str, Any]],
    update_run_id: str,
    source_as_of: str,
) -> FoundationPublication:
    """Prepare the exact eight-plus-one successor using existing metadata APIs."""
    if (base_foundation.status != CURRENT
            or store.current_pointer() != base_foundation.foundation_publication_id
            or base_snapshot_id != base_foundation.manifest.get("base_snapshot_id")
            or set(base_foundation.manifest.get("components", {})) != set(CANDIDATE_COMPONENT_NAMES) - {COMMERCIAL_PURPOSE_COMPONENT}):
        raise CandidateValidationError("exact eight-component CURRENT/snapshot required")
    validate_manifest(store, base_foundation)
    component_manifest = build_extension_component(base_foundation, component, dataset_manifests)
    candidate = prepare_candidate(store, update_run_id=update_run_id, reference_version=base_foundation.reference_version)
    manifest = deepcopy(base_foundation.manifest)
    manifest.update(foundation_publication_id=candidate.foundation_publication_id,
                    candidate_kind=CANDIDATE_KIND, manifest_schema_version="1.0.0",
                    base_foundation_publication_id=base_foundation.foundation_publication_id,
                    update_run_id=update_run_id)
    manifest["components"][COMMERCIAL_PURPOSE_COMPONENT] = component_manifest
    store.update_components(
        candidate.foundation_publication_id, dict(base_foundation.components),
        source_as_of=base_foundation.source_as_of,
        validation_status="PENDING", manifest=manifest,
    )
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    return candidate


def validate_pinned_candidate(
    store: FoundationPublicationStore,
    foundation_candidate_id: str,
    *,
    expected_components: tuple[str, ...] = CANDIDATE_COMPONENT_NAMES,
) -> PinnedCandidate:
    """Resolve exactly one candidate id; fail closed on any inconsistency."""
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
    # A candidate-only shape check must never bypass Foundation's canonical
    # extension/provenance contracts (including inherited non-commercial domains).
    validate_manifest(store, publication)
    components = manifest.get("components")
    if not isinstance(components, dict):
        raise CandidateValidationError("candidate components are missing (fail closed)")
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
        if name == COMMERCIAL_PURPOSE_COMPONENT:
            publication_id = entry.get("publication_id")
            datasets = entry.get("datasets")
            if not publication_id or not isinstance(datasets, dict) or not datasets:
                raise CandidateValidationError("commercial_purpose component is incomplete (fail closed)")
            versions[name] = str(publication_id)
            continue
        if name == "reference":
            version = publication.reference_version
        else:
            component = publication.component(name)
            version = component.publication_id if component else entry.get("publication_id")
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


def mark_candidate_ready(store: FoundationPublicationStore, foundation_candidate_id: str) -> None:
    """Move a canonically validated candidate to READY; never touches CURRENT."""
    candidate = validate_pinned_candidate(store, foundation_candidate_id)
    from .commercial_purpose_reader import CommercialPurposeViews
    verify_commercial_component(candidate.manifest["components"][COMMERCIAL_PURPOSE_COMPONENT])
    store.set_status(foundation_candidate_id, READY_TO_COMMIT, validated_at=utc_now())

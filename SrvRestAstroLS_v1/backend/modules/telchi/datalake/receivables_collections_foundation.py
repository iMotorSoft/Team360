"""Pinned Receivables & Collections component for the Telchi Foundation.

The component is manifest-backed and snapshot-pinned.  The publication catalog
continues to store its five historical SQL columns; logical components beyond
those columns live in the immutable Foundation manifest.  No function in this
module queries SAP or selects a latest publication/component.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from .foundation_manifest import validate_manifest

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

COMPONENT_NAME = "receivables_collections"
COMPONENT_KIND = "RECEIVABLES_COLLECTIONS_FOUNDATION_V1"
LOGICAL_COMPONENT_NAMES = (
    "reference", "sales", "credit_memo", "oinm", "oitw", "material_supply",
    COMPONENT_NAME,
)
DATASET_NAMES = (
    "receivable_settlement_status",
    "collection_method_fact",
    "commercial_term_classification",
)
VALIDATABLE_STATES = (PREPARING, VALIDATING, READY_TO_COMMIT)
ANALYTICAL_COMPARATOR_VERSION = "V3"
DECIMAL_CANONICALIZATION_VERSION = "V3"
ANALYTICAL_FIELDS = (
    "query_contract_version",
    "receivables_component_version",
    "receivables_component_fingerprint",
    "source_as_of",
    "query_name",
    "query_version",
    "scope",
    "period_start",
    "period_end",
    "as_of_date",
    "reporting_currency_basis",
    "metrics",
    "semantic_flags",
)
NON_ANALYTICAL_METADATA_FIELDS = (
    "reader_mode",
    "foundation_publication_id",
    "foundation_candidate_id",
    "publication_context",
    "publication_status",
    "run_id",
    "execution_id",
    "execution_timestamp",
    "commit_timestamp",
    "first_current_snapshot_id",
    "evidence_directory",
    "temporary_path",
    "debug_labels",
)


class ReceivablesComponentError(FoundationReaderError):
    """The exact component/candidate cannot be proven coherent."""


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ReceivablesComponentError("non-finite analytical numeric value")
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _canonical_analytical_value(
    value: Any,
    *,
    field_name: str | None = None,
    normalize_numeric_strings: bool = False,
) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if field_name == "reporting_currency_basis":
            return value.strip().upper()
        if normalize_numeric_strings:
            try:
                return _canonical_decimal(Decimal(value))
            except InvalidOperation:
                pass
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReceivablesComponentError("non-finite analytical float")
        try:
            return _canonical_decimal(Decimal(str(value)))
        except InvalidOperation as exc:
            raise ReceivablesComponentError("invalid analytical float") from exc
    if isinstance(value, Mapping):
        child_numeric_strings = normalize_numeric_strings or field_name == "metrics"
        return {
            str(key): _canonical_analytical_value(
                value[key],
                field_name=str(key),
                normalize_numeric_strings=child_numeric_strings,
            )
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (set, frozenset)):
        items = [
            _canonical_analytical_value(
                item, normalize_numeric_strings=normalize_numeric_strings
            )
            for item in value
        ]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    if isinstance(value, (list, tuple)):
        return [
            _canonical_analytical_value(
                item, normalize_numeric_strings=normalize_numeric_strings
            )
            for item in value
        ]
    raise ReceivablesComponentError(
        f"unsupported analytical value type: {type(value).__name__}"
    )


def canonicalize_analytical_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return only semantic query identity and values for pinned/current equality.

    Publication and execution context is deliberately retained in the raw
    result but cannot enter this payload.  Unknown top-level fields are not
    silently admitted: callers must place financial values in ``metrics`` and
    supported semantic qualifiers in ``semantic_flags``.
    """
    if not isinstance(result, Mapping):
        raise ReceivablesComponentError("analytical result must be a mapping")
    canonical = {
        field: _canonical_analytical_value(result[field], field_name=field)
        for field in ANALYTICAL_FIELDS
        if field in result
    }
    required = {
        "query_contract_version",
        "receivables_component_version",
        "receivables_component_fingerprint",
        "source_as_of",
        "query_name",
        "query_version",
        "scope",
        "reporting_currency_basis",
        "metrics",
    }
    missing = sorted(required - set(canonical))
    if missing:
        raise ReceivablesComponentError(
            f"canonical analytical result is missing required fields: {missing}"
        )
    return canonical


def canonical_analytical_json(result: Mapping[str, Any]) -> str:
    """Serialize the one canonical analytical payload without lossy numerics."""
    payload = canonicalize_analytical_result(result)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def analytical_result_hash_v3(result: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_analytical_json(result).encode("utf-8")).hexdigest()


def analytical_result_hash_v2(result: Mapping[str, Any]) -> str:
    """Compatibility alias for evidence produced by the closed V2 gate."""
    return analytical_result_hash_v3(result)


def build_component(
    *,
    atomic_contract: Mapping[str, Any],
    derivation_contract: Mapping[str, Any],
    reproducibility: Mapping[str, Any],
    business_built_at: str,
) -> dict[str, Any]:
    """Build deterministic component metadata from sealed stable inputs.

    ``business_built_at`` is retained as audit metadata but is excluded from
    both logical identity and component fingerprint.
    """
    datasets: dict[str, Any] = {}
    stable_fingerprints = reproducibility.get("after")
    if not isinstance(stable_fingerprints, Mapping):
        raise ReceivablesComponentError("sealed reproducibility fingerprints are missing")
    declared = derivation_contract.get("datasets")
    if not isinstance(declared, list):
        raise ReceivablesComponentError("sealed derivation datasets are missing")
    for item in declared:
        if not isinstance(item, Mapping) or item.get("DATASET") not in DATASET_NAMES:
            continue
        name = str(item["DATASET"])
        fingerprint = stable_fingerprints.get(name)
        if not isinstance(fingerprint, list) or len(fingerprint) != 2:
            raise ReceivablesComponentError(f"sealed fingerprint missing for {name}")
        datasets[name] = {
            "dataset_id": f"{derivation_contract['derivation_id']}:{name}",
            "row_count": int(item["ROW_COUNT"]),
            "logical_fingerprint": str(fingerprint[1]),
            "fingerprint_method": "sealed_business_reproducibility_v1",
            "ducklake_schema": "business",
            "ducklake_table": name,
        }
    if set(datasets) != set(DATASET_NAMES):
        raise ReceivablesComponentError("required Receivables datasets are incomplete")
    stable = {
        "component_name": COMPONENT_NAME,
        "atomic_derivation_id": atomic_contract["derivation_id"],
        "atomic_discovery_fingerprint": atomic_contract["discovery_fingerprint"],
        "derivation_id": derivation_contract["derivation_id"],
        "derivation_version": derivation_contract["derivation_version"],
        "aging_config_version": atomic_contract["aging_config_version"],
        "source_as_of": derivation_contract["source_as_of"],
        "currency_reporting_basis": "SAP_LOCAL_CURRENCY_BOB",
        "historical_asof_grain": "DAILY_CLOSE",
        "intraday_asof": "NOT_SUPPORTED",
        "qr_source_status": "UNRESOLVED_SOURCE_EVIDENCE",
        "final_contado_business_rule_defined": "NO",
        "datasets": datasets,
    }
    fingerprint = canonical_hash(stable)
    return stable | {
        "name": COMPONENT_NAME,
        "publication_id": "receivables_collections_" + fingerprint[:24],
        "content_identity": fingerprint,
        "component_fingerprint": fingerprint,
        "row_count": sum(int(item["row_count"]) for item in datasets.values()),
        "business_derivation_built_at": business_built_at,
        "known_non_blocking_gaps": [
            "QR_UNRESOLVED_SOURCE_EVIDENCE", "INTRADAY_ASOF_NOT_SUPPORTED",
            "FINAL_CONTADO_NOT_DEFINED", "PRODUCT_LEVEL_DEBT_NOT_MATERIALIZED",
        ],
    }


def component_reference(component: Mapping[str, Any]) -> ComponentReference:
    return ComponentReference(
        COMPONENT_NAME,
        str(component["publication_id"]),
        str(component["source_as_of"]),
        int(component["row_count"]),
        str(component["component_fingerprint"]),
        canonical_hash(component["datasets"]),
    )


def create_candidate(
    store: FoundationPublicationStore,
    *,
    base_publication: FoundationPublication,
    base_snapshot_id: int,
    component: Mapping[str, Any],
    update_run_id: str,
    candidate_created_at: str,
) -> FoundationPublication:
    """Deep-copy one exact CURRENT manifest and add only this component."""
    if base_publication.status != CURRENT:
        raise ReceivablesComponentError("exact base publication is not CURRENT")
    base_manifest = json.loads(json.dumps(base_publication.manifest))
    base_components = base_manifest.get("components")
    expected_base = set(LOGICAL_COMPONENT_NAMES) - {COMPONENT_NAME}
    if not isinstance(base_components, dict) or set(base_components) != expected_base:
        raise ReceivablesComponentError("exact base logical component set is not the sealed six")
    candidate = prepare_candidate(
        store,
        update_run_id=update_run_id,
        reference_version=base_publication.reference_version,
    )
    manifest = base_manifest
    manifest.update({
        "foundation_publication_id": candidate.foundation_publication_id,
        "candidate_kind": COMPONENT_KIND,
        "base_snapshot_id": int(base_snapshot_id),
        "foundation_candidate_created_at": candidate_created_at,
    })
    manifest["components"][COMPONENT_NAME] = dict(component)
    catalog_components = {
        name: base_publication.component(name)
        for name in ("reference", "sales", "credit_memo", "oinm", "oitw")
    }
    if any(value is None or not value.publication_id for value in catalog_components.values()):
        raise ReceivablesComponentError("base catalog components are incomplete")
    store.update_components(
        candidate.foundation_publication_id,
        {name: value for name, value in catalog_components.items() if value is not None},
        source_as_of=str(component["source_as_of"]),
        validation_status="PENDING",
        manifest=manifest,
    )
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    return store.get(candidate.foundation_publication_id) or candidate


@dataclass(frozen=True)
class PinnedReceivablesCandidate:
    foundation_publication_id: str
    status: str
    snapshot_id: int
    manifest: Mapping[str, Any]
    component_versions: Mapping[str, str]
    reader_mode: str

    @property
    def component(self) -> Mapping[str, Any]:
        return self.manifest["components"][COMPONENT_NAME]

    def relation(self, dataset: str) -> str:
        if dataset not in DATASET_NAMES or dataset not in self.component.get("datasets", {}):
            raise ReceivablesComponentError(f"Receivables dataset {dataset!r} is not pinned")
        quoted = dataset.replace('"', '""')
        return f'(SELECT * FROM telchi.business."{quoted}" AT (VERSION => {self.snapshot_id}))'

    def material_supply_datasets(self) -> Mapping[str, Any]:
        datasets = (self.manifest.get("components") or {}).get("material_supply", {}).get("datasets")
        if not isinstance(datasets, dict) or not datasets:
            raise ReceivablesComponentError("material_supply datasets are missing")
        return datasets

    def dataset_files(self, dataset: str) -> list[Path]:
        entry = self.material_supply_datasets().get(dataset)
        if not isinstance(entry, dict):
            raise ReceivablesComponentError(f"material_supply dataset {dataset!r} is absent")
        files = [Path(str(value)) for value in entry.get("file_references", [])]
        if not files or any(not path.is_file() for path in files):
            raise ReceivablesComponentError(f"material_supply dataset {dataset!r} has missing files")
        return files

    def as_dict(self) -> dict[str, Any]:
        return {
            "foundation_publication_id": self.foundation_publication_id,
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "reader_mode": self.reader_mode,
            "component_versions": dict(self.component_versions),
            "CANDIDATE_VERSION_MIXING": "NO",
            "LATEST_COMPONENT_FALLBACK_USED": "NO",
            "CURRENT_FALLBACK_USED": "NO" if self.reader_mode == "EXPLICIT_PINNED_VALIDATION" else "NOT_APPLICABLE",
        }


def _resolve(publication: FoundationPublication, *, reader_mode: str, store: FoundationPublicationStore) -> PinnedReceivablesCandidate:
    manifest = publication.manifest
    try:
        components = validate_manifest(store, publication)
    except FoundationReaderError as exc:
        raise ReceivablesComponentError(str(exc)) from exc
    if not set(LOGICAL_COMPONENT_NAMES).issubset(components):
        raise ReceivablesComponentError("Receivables required component set is incomplete")
    from .receivables_collections_succession import snapshot_for
    snapshot = snapshot_for(manifest)
    if not isinstance(snapshot, int):
        raise ReceivablesComponentError("Receivables Foundation base snapshot is missing")
    versions: dict[str, str] = {}
    for name in LOGICAL_COMPONENT_NAMES:
        entry = components.get(name)
        if not isinstance(entry, dict) or not entry.get("publication_id"):
            raise ReceivablesComponentError(f"component {name} is incomplete")
        declared = str(entry["publication_id"])
        if name == "reference":
            actual = publication.reference_version
        elif name in {"sales", "credit_memo", "oinm", "oitw"}:
            ref = publication.component(name)
            actual = ref.publication_id if ref else None
        else:
            actual = declared
        if actual != declared:
            raise ReceivablesComponentError(f"component {name} row/manifest mismatch")
        versions[name] = declared
    component = components[COMPONENT_NAME]
    if component.get("derivation_version") not in {"1.0.0", "receivables-collections-business-v1.0.0"}:
        raise ReceivablesComponentError("Receivables derivation version incompatible")
    datasets = component.get("datasets")
    if not isinstance(datasets, dict) or set(datasets) != set(DATASET_NAMES):
        raise ReceivablesComponentError("Receivables datasets are incomplete")
    for name, metadata in datasets.items():
        if (not isinstance(metadata, dict)
                or metadata.get("dataset_id") != f"{component.get('derivation_id')}:{name}"
                or type(metadata.get("row_count")) is not int or metadata["row_count"] < 0
                or not isinstance(metadata.get("logical_fingerprint"), str) or not metadata["logical_fingerprint"]
                or metadata.get("fingerprint_method") != "sealed_business_reproducibility_v1"
                or metadata.get("ducklake_schema") != "business" or metadata.get("ducklake_table") != name):
            raise ReceivablesComponentError("Receivables dataset contract is malformed: " + name)
    stable_fields = (
        "component_name", "atomic_derivation_id", "atomic_discovery_fingerprint",
        "derivation_id", "derivation_version", "aging_config_version", "source_as_of",
        "currency_reporting_basis", "historical_asof_grain", "intraday_asof",
        "qr_source_status", "final_contado_business_rule_defined", "datasets",
    )
    if any(key not in component for key in stable_fields):
        raise ReceivablesComponentError("Receivables stable contract is incomplete")
    stable = {
        key: component[key]
        for key in stable_fields
    }
    if canonical_hash(stable) != component.get("component_fingerprint"):
        raise ReceivablesComponentError("Receivables component fingerprint mismatch")
    fingerprint = component["component_fingerprint"]
    if (component["publication_id"] != "receivables_collections_" + fingerprint[:24]
            or component.get("content_identity") != fingerprint):
        raise ReceivablesComponentError("Receivables publication identity/fingerprint mismatch")
    return PinnedReceivablesCandidate(
        publication.foundation_publication_id,
        publication.status,
        snapshot,
        manifest,
        versions,
        reader_mode,
    )


def validate_pinned_candidate(store: FoundationPublicationStore, candidate_id: str) -> PinnedReceivablesCandidate:
    publication = store.get(candidate_id)
    if publication is None:
        raise ReceivablesComponentError("exact candidate does not exist")
    if publication.status in (CURRENT, FAILED, SUPERSEDED) or publication.status not in VALIDATABLE_STATES:
        raise ReceivablesComponentError(f"candidate status {publication.status} is not validatable")
    return _resolve(publication, reader_mode="EXPLICIT_PINNED_VALIDATION", store=store)


def resolve_current(store: FoundationPublicationStore) -> PinnedReceivablesCandidate:
    foundation_id = store.current_pointer()
    if not foundation_id:
        raise ReceivablesComponentError("CURRENT pointer is missing")
    publication = store.get(foundation_id)
    if publication is None or publication.status != CURRENT:
        raise ReceivablesComponentError("CURRENT Receivables Foundation is unresolved")
    return _resolve(publication, reader_mode="PRODUCTIVE_CURRENT", store=store)


def validate_component_data(connection: Any, pinned: PinnedReceivablesCandidate) -> dict[str, Any]:
    """Validate exact snapshot tables against sealed component metadata."""
    results: dict[str, Any] = {}
    component = pinned.component
    for name, expected in component["datasets"].items():
        relation = pinned.relation(name)
        row = connection.execute(
            f"SELECT count(*), min(derivation_id), max(derivation_id), "
            f"min(derivation_version), max(derivation_version), min(source_as_of), max(source_as_of) FROM {relation}"
        ).fetchone()
        actual = {
            "row_count": int(row[0]), "derivation_id_min": row[1], "derivation_id_max": row[2],
            "derivation_version_min": row[3], "derivation_version_max": row[4],
            "source_as_of_min": row[5], "source_as_of_max": row[6],
        }
        valid = (
            actual["row_count"] == int(expected["row_count"])
            and actual["derivation_id_min"] == actual["derivation_id_max"] == component["derivation_id"]
            and actual["derivation_version_min"] == actual["derivation_version_max"] == component["derivation_version"]
            and actual["source_as_of_min"] == actual["source_as_of_max"] == component["source_as_of"]
        )
        results[name] = actual | {"sealed_logical_fingerprint": expected["logical_fingerprint"], "valid": valid}
    if not all(item["valid"] for item in results.values()):
        raise ReceivablesComponentError("snapshot-backed Receivables dataset validation failed")
    return results


def mark_ready(store: FoundationPublicationStore, candidate_id: str) -> None:
    store.set_status(candidate_id, READY_TO_COMMIT, validated_at=utc_now())


__all__ = [
    "COMPONENT_NAME", "COMPONENT_KIND", "LOGICAL_COMPONENT_NAMES", "DATASET_NAMES",
    "ReceivablesComponentError", "PinnedReceivablesCandidate", "canonical_hash",
    "ANALYTICAL_COMPARATOR_VERSION", "ANALYTICAL_FIELDS",
    "NON_ANALYTICAL_METADATA_FIELDS", "DECIMAL_CANONICALIZATION_VERSION",
    "canonicalize_analytical_result", "canonical_analytical_json",
    "analytical_result_hash_v2", "analytical_result_hash_v3", "build_component", "component_reference",
    "create_candidate", "validate_pinned_candidate", "resolve_current",
    "validate_component_data", "mark_ready",
]

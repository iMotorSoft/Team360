"""Extensible envelopes with immutable base contracts; no publication writes."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .foundation_publication import FoundationReaderError
from .verification_cache import verification_scope

EXTENSIBLE_KIND = "FOUNDATION_EXTENSIBLE_V1"
SCHEMA_VERSION = "1.0.0"
LEGACY_KINDS = {"MATERIAL_SUPPLY_V1", "RECEIVABLES_COLLECTIONS_FOUNDATION_V1"}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@verification_scope
def validate_manifest(store: Any, publication: Any, *, seen: frozenset[str] = frozenset()) -> dict:
    """Validate global structure separately from each consumer's required set.

    Legacy candidate kinds describe the builder, not a global schema. The
    purchasing envelope is a legacy extension adapter. Future builders use the
    versioned general envelope and an exact base id, never an implicit CURRENT.
    Extra components must have a stable contract binding all base identities.
    """
    def fail(message: str) -> None:
        raise FoundationReaderError(message)

    identity = publication.foundation_publication_id
    if identity in seen or len(seen) >= 32:
        fail("Foundation extension ancestry is cyclic or too deep")
    manifest = publication.manifest
    if not isinstance(manifest, dict) or manifest.get("foundation_publication_id") != identity:
        fail("Foundation manifest publication identity mismatch")
    kind = manifest.get("candidate_kind", "FOUNDATION_BASE_V1")
    from .reference_compatibility import KIND as REFRESH_KIND, reference_projection
    from .sales_facts_transition import KIND as SALES_FACTS_KIND
    from .independent_facts_succession import KIND as INDEPENDENT_KIND
    if not isinstance(kind, str) or kind not in LEGACY_KINDS | {"PURCHASING_FOUNDATION_V1", EXTENSIBLE_KIND, REFRESH_KIND, SALES_FACTS_KIND, INDEPENDENT_KIND, "FOUNDATION_BASE_V1"}:
        fail("Foundation manifest kind is missing or wrong")
    if manifest.get("manifest_schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        fail("Foundation manifest schema version incompatible")
    if kind == EXTENSIBLE_KIND and manifest.get("manifest_schema_version") != SCHEMA_VERSION:
        fail("Foundation extensible manifest schema version missing")
    components = manifest.get("components")
    snapshot = manifest.get("base_snapshot_id")
    if not isinstance(components, dict) or not components:
        fail("Foundation components are malformed")
    if type(snapshot) is not int or snapshot < 0:
        fail("Foundation base snapshot is invalid")
    ids = set()
    for name, entry in components.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("publication_id"), str) or not entry["publication_id"]:
            fail(f"component {name} is incomplete")
        if (not isinstance(name, str) or not name
                or entry.get("name") != name or entry.get("component_name", name) != name):
            fail("Foundation logical component identity is malformed or duplicated")
        if entry["publication_id"] in ids:
            fail("Foundation duplicate logical component publication")
        ids.add(entry["publication_id"])
    for name in ("reference", "sales", "credit_memo", "oinm", "oitw"):
        component = publication.component(name)
        if component is None or components.get(name, {}).get("publication_id") != component.publication_id:
            fail("Foundation catalog/manifest component mismatch: " + name)
    if kind == "FOUNDATION_BASE_V1":
        if set(components) != {"reference", "sales", "credit_memo", "oinm", "oitw"}:
            fail("Foundation base component registry mismatch")
        return components
    if kind in LEGACY_KINDS:
        # These immutable historical formats have no extension provenance.
        expected = {"reference", "sales", "credit_memo", "oinm", "oitw", "material_supply"}
        if kind == "RECEIVABLES_COLLECTIONS_FOUNDATION_V1":
            expected.add("receivables_collections")
        if set(components) != expected:
            fail("Legacy Foundation additions require a versioned extension envelope")
        return components
    base_key = "purchasing_base_publication_id" if kind == "PURCHASING_FOUNDATION_V1" else "base_foundation_publication_id"
    base_id = manifest.get(base_key)
    if not isinstance(base_id, str) or not base_id:
        fail("Foundation extension base provenance is missing")
    base = store.get(base_id)
    if base is None or base.status not in {"CURRENT", "SUPERSEDED"}:
        fail("Foundation extension base publication is unresolved")
    base_components = validate_manifest(store, base, seen=seen | {identity})
    if kind == INDEPENDENT_KIND:
        from .independent_facts_succession import validate_transition
        return validate_transition(store, publication, base, base_components)
    if kind == SALES_FACTS_KIND:
        from .sales_facts_transition import validate_transition
        return validate_transition(publication, base, base_components)
    if base.manifest.get('candidate_kind') == SALES_FACTS_KIND and kind != REFRESH_KIND:
        fail('Sales facts transition inheritance requires an explicit reader-compatible adapter')
    if kind == REFRESH_KIND:
        if snapshot != base.manifest["base_snapshot_id"] or set(components) != set(base_components):
            fail("Reference refresh changed component registry/snapshot")
        for name, entry in base_components.items():
            if name != "reference" and components.get(name) != entry:
                fail("Reference refresh changed sealed component: " + name)
        if any(publication.component(name) != base.component(name) for name in base.components if name != "reference"):
            fail("Reference refresh changed catalog components")
        data_snapshot = manifest.get('reference_data_snapshot_id')
        if type(data_snapshot) is not int or data_snapshot < snapshot:
            fail('Reference refresh data snapshot is missing or invalid')
        if (base.manifest.get('candidate_kind') == REFRESH_KIND
                and data_snapshot != base.manifest.get('reference_data_snapshot_id')):
            fail('Reference refresh changed pinned data snapshot')
        # A Reference successor retains the sales envelope, including the
        # independently pinned Atomic snapshot and the exact coverage/proof.
        # Copying only component IDs would otherwise redirect sealed sales to
        # old Atomic tables when the builder kind changes to Reference refresh.
        for field in ('sales_facts_revalidation', 'sales_coverage', 'facts_base_snapshot_id'):
            if manifest.get(field) != base.manifest.get(field):
                fail('Reference refresh changed sales provenance: ' + field)
        from .sales_facts_transition import uses_sealed_sales
        if uses_sealed_sales(base.manifest) and data_snapshot != base.manifest['facts_base_snapshot_id']:
            fail('Reference refresh changed sales data snapshot')
        reference = components["reference"]
        if reference.get("publication_id") != publication.reference_version:
            fail("Reference refresh row/manifest mismatch")
        proof = manifest.get("reference_compatibility")
        if not isinstance(proof, dict):
            fail("Reference refresh compatibility proof missing")
        from pathlib import Path
        old_path = Path(proof.get("previous_reference_path", ""))
        new_path = Path(proof.get("reference_path", ""))
        if old_path.name != base.reference_version or new_path.name != publication.reference_version:
            fail("Reference refresh compatibility version mismatch")
        if reference.get("content_identity") != str(new_path):
            fail("Reference refresh path binding mismatch")
        adapter = manifest.get('reference_compatibility_adapter')
        if adapter is None:
            expected_proof = reference_projection(old_path, new_path)
        else:
            from .full_refresh_reference import ADAPTER
            from .sales_reference_release import append_proof
            if adapter != ADAPTER:
                fail('Reference compatibility adapter unsupported')
            from .sales_incremental import DATA_ROOT
            if (old_path != DATA_ROOT/'reference/_versions'/base.reference_version
                    or new_path != DATA_ROOT/'reference/_versions'/publication.reference_version
                    or publication.previous_foundation_publication_id != base_id):
                fail('Reference append canonical lineage/path mismatch')
            expected_proof = append_proof(old_path, new_path, proof.get('master_capture_root', ''))
            if (reference.get('source_as_of') != expected_proof['source_as_of']
                    or publication.component('reference').source_as_of != expected_proof['source_as_of']):
                fail('Reference append observation binding mismatch')
            # Append may not reinterpret a single old business/permission field.
            mutable = {'foundation_publication_id', 'update_run_id', 'candidate_kind',
                       'manifest_schema_version', 'base_foundation_publication_id',
                       'reference_version', 'components', 'reference_compatibility',
                       'reference_compatibility_adapter', 'reference_data_snapshot_id',
                       'precommit_validation'}
            if ({k:v for k,v in manifest.items() if k not in mutable} !=
                    {k:v for k,v in base.manifest.items() if k not in mutable}):
                fail('Reference append changed inherited business contract or permissions')
        if proof != expected_proof:
            fail("Reference refresh compatibility proof mismatch")
        return components
    if (publication.components != base.components
            or publication.reference_version != base.reference_version
            or snapshot != base.manifest["base_snapshot_id"]):
        fail("Foundation extension base catalog/snapshot version mixing")
    for name, entry in base_components.items():
        if components.get(name) != entry:
            fail("Foundation required base component changed: " + name)
    extras = set(components) - set(base_components)
    if not extras or (kind == "PURCHASING_FOUNDATION_V1" and extras != {"purchasing"}):
        fail("Foundation extension component registry mismatch")
    dependencies = {
        "foundation_publication_id": base_id,
        "base_snapshot_id": snapshot,
        "reference_version": base.reference_version,
        "components_hash": _hash(base_components),
    }
    for name in extras:
        entry = components[name]
        stable = entry.get("stable_contract")
        if (not isinstance(stable, dict) or stable.get("contract_version") != SCHEMA_VERSION
                or stable.get("schema_version") != SCHEMA_VERSION
                or stable.get("dependencies") != dependencies
                or not isinstance(stable.get("source_provenance"), dict) or not stable["source_provenance"]):
            fail("Foundation extra component contract/provenance/version mixing: " + name)
        fingerprint = _hash(stable)
        if (entry.get("component_fingerprint") != fingerprint
                or entry.get("content_identity") != fingerprint
                or entry["publication_id"] != name + "_" + fingerprint[:24]):
            fail("Foundation extra component fingerprint mismatch: " + name)
        datasets = entry.get("datasets")
        hashes = stable.get("dataset_hashes")
        if not isinstance(datasets, dict) or not datasets or not isinstance(hashes, dict) or set(datasets) != set(hashes):
            fail("Foundation extra component datasets are malformed: " + name)
        for dataset, metadata in datasets.items():
            if (not isinstance(metadata, dict) or metadata.get("logical_hash") != hashes[dataset]
                    or not isinstance(metadata.get("file_references"), list)
                    or not metadata["file_references"]
                    or not isinstance(metadata.get("file_hashes"), list)
                    or len(metadata["file_hashes"]) != len(metadata["file_references"])
                    or any(not isinstance(path, str) or not path for path in metadata["file_references"])
                    or type(metadata.get("row_count")) is not int or metadata["row_count"] < 0):
                fail("Foundation extra dataset hash/provenance is malformed: " + dataset)
            for value in [hashes[dataset], *metadata["file_hashes"]]:
                if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                    fail("Foundation extra dataset hash is invalid: " + dataset)
    return components

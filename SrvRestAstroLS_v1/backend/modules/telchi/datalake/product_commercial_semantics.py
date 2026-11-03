"""Durable product semantics, independent of inventory rankings and thresholds.

Classifications describe the declared evidence window, never all future uses.
No SAP access, name/prefix inference, or implicit unit conversion is permitted.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Mapping

from .ducklake import DATA_ROOT
from .foundation_manifest import EXTENSIBLE_KIND, SCHEMA_VERSION, validate_manifest
from .foundation_publication import CURRENT, VALIDATING, FoundationPublicationStore, prepare_candidate
from .raw import digest, file_hash, write_raw
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb

COMPONENT = "product_commercial_semantics"
VERSION = "1.0.0"
PURPOSES = {"COMMERCIAL_ONLY", "INTERNAL_ONLY", "MIXED", "UNKNOWN"}
COMMERCIAL_CLASSES = {"TRADED_PRODUCT", "LAB_FINISHED_PRODUCT", "FRACTIONATED_PRODUCT"}
INPUT_CLASSES = {"RAW_MATERIAL", "PACKAGING", "OTHER_INPUT"}
RESOLVED_UOM = {"UOM_RESOLVED_EXACT", "UOM_RESOLVED_SUPPORTED"}
DATASETS = {"product_purpose", "product_sales_uom"}


def row_digest(rows: list[dict]) -> str:
    """Same canonical JSON hash as raw.digest without a giant JSON buffer."""
    h = hashlib.sha256()
    h.update(b"[")
    for index, row in enumerate(rows):
        if index:
            h.update(b",")
        h.update(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode())
    h.update(b"]")
    return h.hexdigest()


def classify_purpose(*, sell_item: str | None, business_class: str | None,
                     class_status: str | None, classification_basis: str | None,
                     sales_documents: int, production_issue_lines: int,
                     bom_lines: int = 0) -> dict[str, Any]:
    """Require positive evidence; absence is bounded by source coverage.

    Two observed invoices establish recurring commerce. Validated commercial
    classification together with an enabled sell flag supports intended commerce.
    One invoice requires independently validated commercial classification. Production issues linked
    to an order (BaseType=202) establish operational use. BOM plus a disabled
    sell flag and validated input classification supports intended internal use;
    BOM alone never establishes consumption or purpose.
    """
    validated = class_status in {"VALIDATED", "SUPPORTED"} and classification_basis != "NAME_BASED"
    observed_commercial = sales_documents >= 2 or (sales_documents > 0 and validated and business_class in COMMERCIAL_CLASSES)
    commercial = observed_commercial or (validated and business_class in COMMERCIAL_CLASSES and sell_item == "Y")
    operational = production_issue_lines > 0
    intended_internal = sell_item == "N" and validated and business_class in INPUT_CLASSES and bom_lines > 0
    evidence = {"sap_sell_item": sell_item, "business_class": business_class,
                "classification_status": class_status, "classification_basis": classification_basis,
                "sales_documents": sales_documents, "production_issue_lines": production_issue_lines,
                "bom_lines": bom_lines, "commercial_evidence": commercial,
                "operational_evidence": operational, "intended_internal_evidence": intended_internal}
    if observed_commercial and operational:
        purpose, provenance, confidence = "MIXED", "DERIVED_STRONG", "HIGH"
    elif commercial and operational:
        purpose, provenance, confidence = "UNKNOWN", "DERIVED_PARTIAL", "LOW"
    elif commercial:
        # A BOM is contrary evidence of potential use; unresolved meaning is not
        # erased merely because no actual issue was seen in the captured window.
        if bom_lines:
            purpose, provenance, confidence = "UNKNOWN", "DERIVED_PARTIAL", "LOW"
        else:
            purpose, provenance, confidence = "COMMERCIAL_ONLY", "DERIVED_PARTIAL", "MEDIUM"
    elif (operational or intended_internal) and sell_item == "N" and sales_documents == 0:
        purpose, provenance, confidence = "INTERNAL_ONLY", "DERIVED_STRONG", "HIGH"
    else:
        purpose, provenance, confidence = "UNKNOWN", "DERIVED_PARTIAL" if operational or bom_lines or sales_documents else "UNKNOWN", "LOW"
    return {"commercial_purpose": purpose, "commercial_purpose_provenance": provenance,
            "commercial_purpose_confidence": confidence,
            "commercial_purpose_evidence": evidence,
            "commercially_observed": observed_commercial,
            "commercially_supported": commercial, "operationally_observed": operational}


def number(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def convert_quantity(quantity: Any, *, inventory_uom_id: str | None,
                     source_uom: str | None, factor: Any,
                     proof: str | None, incompatible: bool = False) -> dict[str, Any]:
    """Use only a verified source-native factor to the item's inventory unit.

    Master names, invoice base links and equal strings never supply a factor.
    A dimension conflict without an explicit source-native item factor is blocked.
    """
    q, f = number(quantity), number(factor)
    status = "UOM_INCOMPATIBLE" if incompatible else "UOM_UNRESOLVED"
    base = None
    if not incompatible and q is not None and f is not None and f > 0 and inventory_uom_id and source_uom and source_uom.strip() and proof in {"EXACT_LINEAGE", "MATCHED_HISTORICAL_SOURCE"}:
        status = "UOM_RESOLVED_EXACT" if proof == "EXACT_LINEAGE" else "UOM_RESOLVED_SUPPORTED"
        with localcontext() as ctx:
            ctx.prec = 80
            base = str(q * f)
    return {"uom_status": status, "base_qty": base, "inventory_uom_id": inventory_uom_id,
            "source_uom": source_uom, "conversion_factor": str(f) if f is not None else None,
            "conversion_proof": proof}


def net_quantity(lines: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Fail closed at product + inventory UoM grain; never drop invalid lines."""
    keys = {(r["source_system"], r["doc_entry"], r["line_num"], r["document_kind"]) for r in lines}
    if len(keys) != len(lines):
        raise ValueError("duplicate sales line: fanout")
    if any(r["uom_status"] == "UOM_INCOMPATIBLE" for r in lines):
        return {"status": "UOM_INCOMPATIBLE", "net_sales_base_qty": None}
    if any(r["uom_status"] not in RESOLVED_UOM for r in lines):
        return {"status": "UOM_UNRESOLVED", "net_sales_base_qty": None}
    if len({(r["item_code"], r["inventory_uom_id"]) for r in lines}) > 1:
        return {"status": "UOM_INCOMPATIBLE", "net_sales_base_qty": None}
    with localcontext() as ctx:
        ctx.prec = 80
        gross = sum((Decimal(r["base_qty"]) for r in lines if r["document_kind"] == "INVOICE"), Decimal(0))
        credit = sum((Decimal(r["base_qty"]) for r in lines if r["document_kind"] == "CREDIT_MEMO"), Decimal(0))
        return {"status": "PASS", "invoice_base_qty": str(gross), "credit_memo_base_qty": str(credit),
                "net_sales_base_qty": str(gross - credit)}


def available_stock(on_hand: Any, committed: Any) -> Decimal | None:
    physical, reserved = number(on_hand), number(committed)
    with localcontext() as ctx:
        ctx.prec = 80
        return physical - reserved if physical is not None and reserved is not None else None


def materialize(datasets: Mapping[str, list[dict]], *, dependencies: Mapping,
                provenance: Mapping, contracts: Mapping, data_root: Path = DATA_ROOT,
                reuse_datasets: Mapping[str, Mapping] | None = None) -> dict:
    """Only small semantic crosswalks; no copies of source-native large facts."""
    reuse_datasets = reuse_datasets or {}
    if set(datasets) & set(reuse_datasets) or set(datasets) | set(reuse_datasets) != DATASETS:
        raise ValueError("semantic datasets incomplete")
    stable = {"contract_version": VERSION, "schema_version": VERSION,
              "algorithm_version": VERSION, "dependencies": dict(dependencies),
              "source_provenance": dict(provenance), "contracts": dict(contracts),
              "dataset_hashes": {name: row_digest(rows) for name, rows in datasets.items()} |
              {name: entry["logical_hash"] for name, entry in reuse_datasets.items()}}
    fingerprint = digest(stable)
    identity = COMPONENT + "_" + fingerprint[:24]
    metadata = deepcopy(dict(reuse_datasets))
    for entry in metadata.values():
        paths, hashes = entry["file_references"], entry["file_hashes"]
        if not paths or len(paths) != len(hashes) or any(data_root.resolve() not in Path(p).resolve().parents or file_hash(Path(p)) != h for p, h in zip(paths, hashes, strict=True)):
            raise ValueError("reused semantic file hash/root mismatch")
    for name, rows in datasets.items():
        root = data_root / "business" / COMPONENT / "_versions" / identity
        path = root / name / "full" / (identity + "_" + name) / "manifest.json"
        if path.exists():
            manifest = json.loads(path.read_text())
            if manifest.get("logical_hash") != stable["dataset_hashes"][name]:
                raise ValueError("sealed semantic dataset collision")
        else:
            manifest = write_raw(root=root, segment_id=name + "/full", extraction_id=identity + "_" + name,
                                 rows=rows, profile=DuckDBSafetyProfile(threads=2, memory_limit="1GB"),
                                 metadata={"dataset": name, "source_system": "TELCHI_DERIVATION",
                                           "logical_hash": stable["dataset_hashes"][name],
                                           "contract_version": VERSION, "dependencies": dict(dependencies)})
        if any(file_hash(Path(p)) != h for p, h in zip(manifest["file_references"], manifest["file_hashes"], strict=True)):
            raise ValueError("semantic file hash mismatch")
        metadata[name] = {"manifest_path": str(path), "file_references": manifest["file_references"],
                          "file_hashes": manifest["file_hashes"], "logical_hash": stable["dataset_hashes"][name],
                          "row_count": len(rows)}
    return {"name": COMPONENT, "publication_id": identity, "component_fingerprint": fingerprint,
            "content_identity": fingerprint, "stable_contract": stable, "datasets": metadata,
            "row_count": sum(v["row_count"] for v in metadata.values())}


def create_candidate(store: FoundationPublicationStore, *, base_id: str, component: dict, run_id: str) -> str:
    """Official candidate metadata mechanism, without changing CURRENT."""
    base = store.get(base_id)
    if base is None or base.status != CURRENT or store.current_pointer() != base_id:
        raise ValueError("exact CURRENT changed")
    validate_manifest(store, base)
    dependencies = {"foundation_publication_id": base_id, "base_snapshot_id": base.manifest["base_snapshot_id"],
                    "reference_version": base.reference_version, "components_hash": digest(base.manifest["components"])}
    if component["stable_contract"]["dependencies"] != dependencies:
        raise ValueError("semantic dependencies mismatch")
    candidate = prepare_candidate(store, update_run_id=run_id, reference_version=base.reference_version)
    manifest = deepcopy(base.manifest)
    manifest.update(foundation_publication_id=candidate.foundation_publication_id,
                    candidate_kind=EXTENSIBLE_KIND, manifest_schema_version=SCHEMA_VERSION,
                    base_foundation_publication_id=base_id)
    manifest["components"][COMPONENT] = deepcopy(component)
    store.update_components(candidate.foundation_publication_id, dict(base.components), source_as_of=base.source_as_of,
                            validation_status="PENDING_PRODUCT_SEMANTICS_VALIDATION", manifest=manifest)
    store.set_status(candidate.foundation_publication_id, VALIDATING)
    validate_manifest(store, store.get(candidate.foundation_publication_id))
    return candidate.foundation_publication_id


def read_component(component: Mapping, *, data_root: Path = DATA_ROOT) -> dict[str, list[dict]]:
    """Pinned file/hash access, usable for an explicit candidate or CURRENT."""
    import json
    fingerprint = digest(component["stable_contract"])
    if component.get("component_fingerprint") != fingerprint or component.get("publication_id") != COMPONENT + "_" + fingerprint[:24]:
        raise ValueError("semantic component identity mismatch")
    if set(component["datasets"]) != DATASETS:
        raise ValueError("semantic dataset registry mismatch")
    db = open_safe_duckdb(profile=DuckDBSafetyProfile(threads=2, memory_limit="1GB"))
    result = {}
    try:
        for name, entry in component["datasets"].items():
            paths, hashes = entry["file_references"], entry["file_hashes"]
            if not paths or len(paths) != len(hashes):
                raise ValueError("semantic files incomplete")
            for path, sha in zip(paths, hashes, strict=True):
                if data_root.resolve() not in Path(path).resolve().parents or file_hash(Path(path)) != sha:
                    raise ValueError("semantic file hash/root mismatch")
            cur = db.execute("SELECT * FROM read_parquet(?, union_by_name=true)", [paths])
            names = [d[0] for d in cur.description]
            rows = [json.loads(json.dumps(dict(zip(names, r)), default=str)) for r in cur.fetchall()]
            if len(rows) != entry["row_count"] or row_digest(rows) != entry["logical_hash"] or entry["logical_hash"] != component["stable_contract"]["dataset_hashes"][name]:
                raise ValueError("semantic row fingerprint mismatch")
            result[name] = rows
    finally:
        db.close()
    return result


def dataset_relation(component: Mapping, dataset: str, *, data_root: Path = DATA_ROOT) -> str:
    """Hash-verified SQL relation without loading every line into Python."""
    if dataset not in DATASETS:
        raise ValueError("unknown semantic dataset")
    fingerprint = digest(component["stable_contract"])
    if component.get("component_fingerprint") != fingerprint or component.get("publication_id") != COMPONENT + "_" + fingerprint[:24]:
        raise ValueError("semantic component identity mismatch")
    entry = component["datasets"][dataset]
    if entry["logical_hash"] != component["stable_contract"]["dataset_hashes"][dataset]:
        raise ValueError("semantic dataset fingerprint mismatch")
    paths, hashes = entry["file_references"], entry["file_hashes"]
    if not paths or len(paths) != len(hashes):
        raise ValueError("semantic files incomplete")
    for path, sha in zip(paths, hashes, strict=True):
        if data_root.resolve() not in Path(path).resolve().parents or file_hash(Path(path)) != sha:
            raise ValueError("semantic file hash/root mismatch")
    sql_files = ",".join("'" + str(p).replace("'", "''") + "'" for p in paths)
    return f"(SELECT * FROM read_parquet([{sql_files}],union_by_name=true))"

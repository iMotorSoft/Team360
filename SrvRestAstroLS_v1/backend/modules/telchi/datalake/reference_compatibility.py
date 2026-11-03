"""Offline, fail-closed compatibility proof for sealed Foundation consumers."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib

from .foundation_publication import FoundationReaderError
from .reference_update import PHYSICAL_FIELDS, digest, read_parquet_rows, validate_identity, validate_physical_rows

KIND = "FOUNDATION_REFERENCE_REFRESH_V1"
VOLATILE = {"_source_extracted_at", "_ingested_at"}


def reference_projection(previous: Path, candidate: Path, *, _include_crosswalk: bool = True) -> dict[str, Any]:
    """Preserve every old dataset/column/row except the new physical attributes.

    This deliberately rejects other changed master attributes: sealed business
    components must be rebuilt or get their own explicit compatibility adapter.
    Added or removed rows also require explicit dependent-component revalidation.
    No effectiveness date or commercial reinterpretation is asserted.
    """
    previous, candidate = Path(previous), Path(candidate)
    paths = sorted(previous.rglob("*.parquet"))
    if not paths or not candidate.is_dir():
        raise FoundationReaderError("Reference compatibility requires complete immutable roots")
    if {p.relative_to(previous) for p in paths} != {p.relative_to(candidate) for p in candidate.rglob("*.parquet")}:
        raise FoundationReaderError("Reference dataset/part registry incompatible")
    proof = {}
    for path in paths:
        relative = path.relative_to(previous)
        target = candidate / relative
        if not target.is_file():
            raise FoundationReaderError(f"Reference enriched dataset removed: {relative}")
        columns, types, old = read_parquet_rows(path)
        # A physical-only successor copies nearly every part byte-for-byte.
        # Exact content equality proves both schema and rows; avoid decoding
        # that same unchanged part twice, without caching unverified results.
        same_bytes = hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest()
        new_columns, new_types, new = (columns, types, old) if same_bytes else read_parquet_rows(target)
        if relative.parts[0] == "products":
            try:
                validate_physical_rows(new)
            except RuntimeError as exc:
                raise FoundationReaderError(str(exc)) from exc
        new_schema = dict(zip(new_columns, new_types))
        if any(new_schema.get(column) != typ for column, typ in zip(columns, types)):
            raise FoundationReaderError(f"Reference schema incompatible: {relative}")
        excluded = VOLATILE | (set(PHYSICAL_FIELDS) if relative.parts[0] == "products" else set())
        selected = [column for column in columns if column not in excluded]
        def project(rows: list[dict]) -> list[str]:
            return sorted(digest({column: row.get(column) for column in selected}) for row in rows)
        from .verification_cache import verified_projection
        projection_contract = 'reference-preserved-v1:' + digest(selected)
        before = verified_projection(path, projection_contract, lambda: project(old))
        after = before if same_bytes else verified_projection(target, projection_contract, lambda: project(new))
        # Strict multiset equality prevents dropped, duplicated or reinterpreted rows.
        if before != after:
            raise FoundationReaderError(f"Reference contract incompatible: {relative}; dependent components require revalidation")
        proof[str(relative)] = digest({"schema": list(zip(columns, types)), "projection": before})
    result = {"contract_version": "1.0.0", "previous_reference_path": str(previous),
              "reference_path": str(candidate), "preserved_projections": proof}
    if _include_crosswalk:
        old_crosswalk = previous.parents[2] / "crosswalk" / "_versions" / previous.name
        new_crosswalk = candidate.parents[2] / "crosswalk" / "_versions" / candidate.name
        result["crosswalk"] = reference_projection(old_crosswalk, new_crosswalk, _include_crosswalk=False)
        def rows(root: Path, dataset: str) -> list[dict]:
            files = sorted((root / dataset).glob("*.parquet"))
            if not files:
                raise FoundationReaderError("Reference identity dataset missing: " + dataset)
            return [row for file in files for row in read_parquet_rows(file)[2]]
        try:
            validate_identity("product", rows(candidate, "products"), rows(new_crosswalk, "product_crosswalk"),
                              rows(previous, "products"), rows(old_crosswalk, "product_crosswalk"))
        except RuntimeError as exc:
            raise FoundationReaderError(str(exc)) from exc
    return result

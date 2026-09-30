"""Safe, bounded rebuild and physical-audit controls for create_initial V1.

The module intentionally separates three ownership models:

* DuckLake Atomic rows are replaced in the publication transaction.
* DuckLake-managed Parquet is metadata-audited but never unlinked here.
* ``raw/sap`` is external evidence and may only be purged under an explicit,
  gate-owned, dependency-free scope.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .ducklake import DATA_ROOT, DuckLakeConnector
from .raw import digest

RAW_GATE_NAME = "TELCHI_DATALAKE_CREATE_INITIAL_V1"
LEGACY_RAW_PURGE_ALLOWED = False
MANAGED_PARQUET_DIRECT_DELETE_ALLOWED = False


@dataclass(frozen=True)
class ScopeKeySet:
    domain: str
    keys: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if self.domain not in {"sales", "inventory"}:
            raise ValueError("domain must be sales or inventory")
        if not self.keys:
            raise ValueError("destructive operations require a non-empty exact source keyset")
        expected = 2
        if any(len(key) != expected or any(value in {"", "None"} for value in key) for key in self.keys):
            raise ValueError("source keys must be exact two-part non-empty identities")
        if len(set(self.keys)) != len(self.keys):
            raise ValueError("source keyset contains duplicates")

    @property
    def identity(self) -> str:
        return digest({"domain": self.domain, "keys": self.keys})


@dataclass(frozen=True)
class DestructivePlan:
    operation: str
    domain: str
    scope: str
    keyset: ScopeKeySet
    current_snapshot: int | None
    atomic_tables: tuple[str, ...]
    rows_to_replace: dict[str, int]
    raw_files: tuple[str, ...] = ()
    estimated_bytes: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "domain": self.domain,
            "scope": self.scope,
            "source_key_scope": [list(key) for key in self.keyset.keys],
            "source_keyset_identity": self.keyset.identity,
            "current_snapshot": self.current_snapshot,
            "atomic_tables_affected": list(self.atomic_tables),
            "rows_to_replace": dict(self.rows_to_replace),
            "raw_files_affected": list(self.raw_files),
            "estimated_bytes": self.estimated_bytes,
            "managed_parquet_direct_filesystem_delete": "FORBIDDEN",
            "snapshot_preservation_default": "YES",
        }


def _atomic_names(domain: str, table_names: dict[str, str | None]) -> tuple[str, ...]:
    if domain == "sales":
        names = (table_names.get("sales_document"), table_names.get("sales_line"))
    else:
        names = (table_names.get("inventory_balance_snapshot"),)
    if any(not name for name in names):
        raise ValueError(f"Atomic contract is incomplete for {domain}")
    return tuple(name for name in names if name)


def _placeholders(size: int) -> str:
    if size <= 0:
        raise ValueError("empty keyset is not a safe SQL scope")
    return ",".join("?" for _ in range(size))


def _plan_where(domain: str, keyset: ScopeKeySet, table: str) -> tuple[str, list[str]]:
    if domain == "sales":
        doc_entries = sorted({key[0] for key in keyset.keys})
        return f"doc_entry IN ({_placeholders(len(doc_entries))})", doc_entries
    items = [value for value, _ in keyset.keys]
    warehouses = [value for _, value in keyset.keys]
    return (
        "(item_code, whs_code) IN (" + ",".join("(?,?)" for _ in keyset.keys) + ")",
        [value for pair in zip(items, warehouses) for value in pair],
    )


def plan_atomic_rebuild(
    connector: DuckLakeConnector,
    *,
    domain: str,
    scope: str,
    keyset: ScopeKeySet,
    table_names: dict[str, str | None],
    raw_files: Iterable[str] = (),
) -> DestructivePlan:
    """Build a read-only plan from exact source identities."""
    if keyset.domain != domain:
        raise ValueError("domain and keyset domain must match")
    tables = _atomic_names(domain, table_names)
    with connector.session(read_only=True) as connection:
        snapshot = connector.snapshot(connection)
        counts: dict[str, int] = {}
        estimated = 0
        for table in tables:
            where, params = _plan_where(domain, keyset, table)
            counts[table] = int(connection.execute(
                f"SELECT count(*) FROM telchi.atomic.\"{table.replace(chr(34), chr(34) * 2)}\" WHERE {where}", params
            ).fetchone()[0])
            # This is a catalog-level average, not a row scan or a promise of
            # the exact replacement size.
            try:
                info = connection.execute(
                    "SELECT file_count, file_size_bytes FROM ducklake_table_info('telchi') "
                    "WHERE table_name=?", [table]
                ).fetchone()
                if info and info[0]:
                    estimated += int(float(info[1] or 0) * counts[table] / int(info[0]))
            except Exception:
                pass
    return DestructivePlan(
        operation="ATOMIC_REBUILD",
        domain=domain,
        scope=scope,
        keyset=keyset,
        current_snapshot=snapshot,
        atomic_tables=tables,
        rows_to_replace=counts,
        raw_files=tuple(raw_files),
        estimated_bytes=max(0, estimated),
    )


def require_destructive_confirmation(
    plan: DestructivePlan,
    *,
    confirm_destructive: bool,
    plan_was_shown: bool,
) -> None:
    """Fail closed unless scope, plan and explicit confirmation are present."""
    if not plan.domain or not plan.scope or not plan.keyset.keys:
        raise ValueError("destructive operation requires explicit domain and scope")
    if not plan_was_shown:
        raise PermissionError("destructive operation requires a previously shown plan")
    if not confirm_destructive:
        raise PermissionError("destructive operation requires --confirm-destructive")


def read_raw_rows(path: Path) -> list[dict[str, Any]]:
    """Read an existing immutable raw Parquet without rewriting it."""
    from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb

    resolved = path.resolve()
    allowed_root = (DATA_ROOT / "raw" / "sap" / RAW_GATE_NAME).resolve()
    if allowed_root != resolved and allowed_root not in resolved.parents:
        raise PermissionError("raw reuse is limited to gate-owned raw/sap evidence")
    if resolved.suffix.lower() != ".parquet":
        raise ValueError("raw reuse requires a Parquet file")
    db = open_safe_duckdb(":memory:", profile=DuckDBSafetyProfile.from_runtime_config())
    try:
        rows = db.execute("SELECT * FROM read_parquet(?)", [str(resolved)])
        columns = [str(item[0]) for item in rows.description or ()]
        return [dict(zip(columns, row)) for row in rows.fetchall()]
    finally:
        db.close()


def raw_scope_files(root: Path, *, domain: str, segment_id: str) -> list[Path]:
    """Return only gate-owned raw Parquet files for one exact segment."""
    root = root.resolve()
    allowed_root = (DATA_ROOT / "raw" / "sap" / RAW_GATE_NAME).resolve()
    if root != allowed_root and allowed_root not in root.parents:
        raise PermissionError("raw purge is limited to this implementation's raw/sap scope")
    if domain not in {"sales", "inventory"} or not segment_id or Path(segment_id).name != segment_id:
        raise ValueError("raw purge requires a bounded domain and segment_id")
    segment_root = root / segment_id
    if not segment_root.is_dir():
        return []
    return sorted(path for path in segment_root.rglob("*.parquet") if path.is_file())


def raw_manifest_audit(root: Path, *, domain: str, segment_id: str) -> list[dict[str, Any]]:
    """Expose hashes and extraction identities before any external purge."""
    segment_root = (root / segment_id).resolve()
    if not segment_root.is_dir():
        return []
    output: list[dict[str, Any]] = []
    for manifest_path in sorted(segment_root.rglob("manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        output.append({
            "manifest_path": str(manifest_path),
            "extraction_id": manifest.get("extraction_id"),
            "file_hashes": list(manifest.get("file_hashes", [])),
            "files": list(manifest.get("files", [])),
            "operation": manifest.get("operation", "UNKNOWN"),
            "domain": domain,
            "segment_id": segment_id,
        })
    return output


def raw_dependency_audit(
    connector: DuckLakeConnector,
    *,
    extraction_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Find trusted publications that still cite an extraction."""
    wanted = {str(item) for item in extraction_ids if item}
    if not wanted:
        return []
    with connector.session(read_only=True) as connection:
        try:
            rows = connection.execute(
                "SELECT publication_id, segment_id, source_identity, status "
                "FROM telchi.ops.initial_publications_v1"
            ).fetchall()
        except Exception:
            return []
    return [
        {"publication_id": row[0], "segment_id": row[1], "source_identity": row[2], "status": row[3]}
        for row in rows if any(extraction in str(row[2] or "") for extraction in wanted)
    ]


def purge_raw_scope(
    root: Path,
    *,
    domain: str,
    segment_id: str,
    confirm_destructive: bool,
    dependency_references: Iterable[dict[str, Any]] = (),
    legacy: bool = False,
) -> dict[str, Any]:
    """Purge external raw evidence only after all safety checks pass."""
    if legacy or "legacy" in root.parts:
        raise PermissionError("LEGACY_RAW_PURGE_ALLOWED=NO")
    files = raw_scope_files(root, domain=domain, segment_id=segment_id)
    if not confirm_destructive:
        raise PermissionError("raw purge requires --confirm-destructive")
    dependencies = list(dependency_references)
    if dependencies:
        raise PermissionError("raw extraction is referenced by trusted publication")
    deleted: list[str] = []
    for path in files:
        if path.is_symlink():
            raise PermissionError("refusing to purge a symlink from raw evidence")
        path.unlink()
        deleted.append(str(path))
    # Remove only now-empty directories below this exact segment scope.
    segment_root = (root / segment_id).resolve()
    if segment_root.is_dir() and not any(segment_root.iterdir()):
        segment_root.rmdir()
    return {
        "operation": "RAW_PURGE",
        "domain": domain,
        "segment_id": segment_id,
        "files": deleted,
        "file_count": len(deleted),
        "legacy_raw_purge_allowed": "NO",
        "dependency_check": "PASS",
    }


def classify_tiny_files(sizes: Iterable[int], *, rows_per_file: Iterable[int] = ()) -> dict[str, Any]:
    values = sorted(int(value) for value in sizes if int(value) >= 0)
    if not values:
        return {"status": "NO_TINY_FILE_PROBLEM", "reason": "no live files"}
    p50 = values[len(values) // 2]
    p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
    rows = [int(value) for value in rows_per_file if int(value) >= 0]
    # These thresholds are diagnostics, not physical policy.  File count alone
    # is deliberately insufficient: row density and query behavior are inputs.
    if p50 >= 64 * 1024 and p95 >= 128 * 1024:
        status = "NO_TINY_FILE_PROBLEM"
    elif p50 >= 8 * 1024:
        status = "MILD_TINY_FILE_PROBLEM"
    elif p50 >= 1024:
        status = "MATERIAL_TINY_FILE_PROBLEM"
    else:
        status = "SEVERE_TINY_FILE_PROBLEM"
    return {
        "status": status,
        "min_bytes": values[0],
        "p50_bytes": p50,
        "p95_bytes": p95,
        "max_bytes": values[-1],
        "rows_per_file_available": bool(rows),
        "rows_per_file_median": sorted(rows)[len(rows) // 2] if rows else None,
        "criteria": "live size + rows/file when available + pruning/query overhead; file count alone is not decisive",
    }

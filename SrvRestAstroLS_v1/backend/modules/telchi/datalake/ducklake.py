"""Minimal DuckLake connection adapter for the explicit V1 builder."""
from __future__ import annotations

import contextlib
import os
import shlex
import threading
from pathlib import Path
from statistics import median
from typing import Any, Iterator

from .query_profile import measured, span

CATALOG_ALIAS = "telchi"
CATALOG_DATABASE = "team360_telchi_ducklake"
RUNTIME_ROLE = "team360_telchi_ducklake"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
PRIVATE_CONFIG = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/ducklake/postgres.env")


def _env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            parsed = shlex.split(value, posix=True)
            if len(parsed) == 1:
                result[key.strip()] = parsed[0]
    return result


class DuckLakeConnector:
    def __init__(self) -> None:
        private = measured('private_config_read', _env_file, Path(os.getenv("TEAM360_TELCHI_DUCKLAKE_PRIVATE_CONFIG", str(PRIVATE_CONFIG))))
        self.host = os.getenv("TELCHI_DUCKLAKE_PG_HOST", private.get("TELCHI_DUCKLAKE_PG_HOST", "localhost"))
        self.port = int(os.getenv("TELCHI_DUCKLAKE_PG_PORT", private.get("TELCHI_DUCKLAKE_PG_PORT", "5432")))
        self.database = os.getenv("TELCHI_DUCKLAKE_PG_DATABASE", private.get("TELCHI_DUCKLAKE_PG_DATABASE", CATALOG_DATABASE))
        self.user = os.getenv("TELCHI_DUCKLAKE_PG_USER", private.get("TELCHI_DUCKLAKE_PG_USER", RUNTIME_ROLE))
        self.password = os.getenv("TELCHI_DUCKLAKE_PG_PASSWORD", private.get("TELCHI_DUCKLAKE_PG_PASSWORD", ""))
        self.data_path = Path(os.getenv("TELCHI_DUCKLAKE_DATA_PATH", private.get("TELCHI_DUCKLAKE_DATA_PATH", str(DATA_ROOT / "ducklake" / "data"))))
        if not self.password:
            raise RuntimeError("DuckLake private PostgreSQL password is not configured")
        if not self.data_path.is_absolute() or DATA_ROOT.resolve() not in self.data_path.resolve().parents:
            raise ValueError("DuckLake data path must remain under Telchi DATA_ROOT")

    @contextlib.contextmanager
    def session(self, *, read_only: bool = False) -> Iterator[object]:
        with span('duckdb_import'):
            import duckdb
        self.data_path.mkdir(parents=True, exist_ok=True, mode=0o750)
        previous = os.environ.get("PGPASSWORD")
        os.environ["PGPASSWORD"] = self.password
        connection = measured('duckdb_connect', duckdb.connect)
        try:
            measured('load_ducklake', connection.execute, "LOAD ducklake")
            measured('load_postgres', connection.execute, "LOAD postgres")
            options = "READ_ONLY" if read_only else "DATA_INLINING_ROW_LIMIT 0"
            measured('attachment_open_including_catalog_session', connection.execute,
                f"ATTACH 'ducklake:postgres:dbname={self.database} host={self.host} port={self.port} user={self.user}' "
                f"AS {CATALOG_ALIAS} (DATA_PATH '{self.data_path.resolve()}', {options})"
            )
            yield connection
        finally:
            measured('attachment_connection_close', connection.close)
            if previous is None:
                os.environ.pop("PGPASSWORD", None)
            else:
                os.environ["PGPASSWORD"] = previous

    def table_names(self, connection: object) -> set[str]:
        return {str(row[0]) for row in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='atomic'").fetchall()}

    def resolve_atomic_tables(self, connection: object) -> dict[str, str | None]:
        names = self.table_names(connection)
        required = {
            "sales_document": "sales_document" if "sales_document" in names else None,
            "sales_line": "sales_line" if "sales_line" in names else None,
            "credit_memo_document": "credit_memo_document" if "credit_memo_document" in names else None,
            "credit_memo_line": "credit_memo_line" if "credit_memo_line" in names else None,
            "inventory_balance_snapshot": "inventory_balance_snapshot" if "inventory_balance_snapshot" in names else ("inventory_balance" if "inventory_balance" in names else None),
            "inventory_movement": "inventory_movement" if "inventory_movement" in names else ("inventory_movements" if "inventory_movements" in names else None),
        }
        return required

    def physical_stats(self) -> dict[str, object]:
        """Return filesystem stats only; it is not a DuckLake live-file audit."""
        files = sorted(path for path in self.data_path.rglob("*.parquet") if path.is_file())
        sizes = sorted(path.stat().st_size for path in files)
        return {
            "number_of_parquet_files": len(files),
            "total_parquet_bytes": sum(sizes),
            "min_file_size": min(sizes) if sizes else 0,
            "max_file_size": max(sizes) if sizes else 0,
            "median_file_size": int(median(sizes)) if sizes else 0,
            "data_path": str(self.data_path),
            "ownership": "FILESYSTEM_OBSERVATION_ONLY",
        }

    @staticmethod
    def _ducklake_file_rows(connection: Any, table: str, schema: str, snapshot_id: int) -> list[dict[str, Any]]:
        """Read DuckLake's file metadata, never the rows in every Parquet file."""
        result = connection.execute(
            "SELECT data_file, data_file_size_bytes, data_file_footer_size, "
            "delete_file, delete_file_size_bytes "
            "FROM ducklake_list_files(?, ?, schema := ?, snapshot_version := ?)",
            [CATALOG_ALIAS, table, schema, snapshot_id],
        )
        return [
            {
                "data_file": row[0],
                "data_file_size_bytes": int(row[1] or 0),
                "data_file_footer_size": int(row[2] or 0),
                "delete_file": row[3],
                "delete_file_size_bytes": int(row[4] or 0),
                "table": table,
                "schema": schema,
                "snapshot_id": snapshot_id,
            }
            for row in result.fetchall()
        ]

    def managed_file_inventory(self, *, include_history: bool = True) -> dict[str, Any]:
        """Audit live/history through DuckLake metadata.

        This deliberately does not glob the filesystem to decide ownership and
        never deletes or rewrites a managed file.  History is the union of file
        metadata observed at catalog snapshots; a file only present in an old
        snapshot is classified as retention storage, not current live data.
        """
        with self.session(read_only=True) as connection:
            current_snapshot = self.snapshot(connection)
            table_rows = connection.execute(
                "SELECT schema_name, table_name FROM duckdb_tables() "
                "WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name",
                [CATALOG_ALIAS],
            ).fetchall()
            tables = [(str(row[0]), str(row[1])) for row in table_rows]
            current: list[dict[str, Any]] = []
            for schema, table in tables:
                try:
                    current.extend(self._ducklake_file_rows(connection, table, schema, current_snapshot))
                except Exception:
                    # A table may have been created after an historical snapshot;
                    # current metadata remains authoritative for the present.
                    continue
            historical: list[dict[str, Any]] = []
            snapshot_ids: list[int] = []
            if include_history:
                snapshot_ids = [int(row[0]) for row in connection.execute(
                    "SELECT snapshot_id FROM ducklake_snapshots('telchi')"
                ).fetchall()]
                # Do not repeat the current snapshot.  This keeps the audit
                # bounded while preserving exact catalog accounting.
                for snapshot_id in snapshot_ids:
                    if snapshot_id == current_snapshot:
                        continue
                    for schema, table in tables:
                        try:
                            historical.extend(self._ducklake_file_rows(connection, table, schema, snapshot_id))
                        except Exception:
                            continue
        current_by_path = {str(item["data_file"]): item for item in current}
        historical_by_path = {str(item["data_file"]): item for item in historical}
        historical_only = [item for path, item in historical_by_path.items() if path not in current_by_path]
        catalog_paths = set(current_by_path) | set(historical_by_path)
        filesystem_files = [path for path in self.data_path.rglob("*.parquet") if path.is_file()]
        orphan_files = [
            {"data_file": str(path), "bytes": path.stat().st_size, "classification": "DUCKLAKE_PATH_NOT_REFERENCED_BY_OBSERVED_SNAPSHOT"}
            for path in filesystem_files if str(path) not in catalog_paths
        ]
        table_stats: list[dict[str, Any]] = []
        with self.session(read_only=True) as connection:
            for schema, table in tables:
                live = [item for item in current_by_path.values() if item["schema"] == schema and item["table"] == table]
                try:
                    quoted_schema = schema.replace(chr(34), chr(34) * 2)
                    quoted_table = table.replace(chr(34), chr(34) * 2)
                    row_count = int(connection.execute(f'SELECT count(*) FROM {CATALOG_ALIAS}."{quoted_schema}"."{quoted_table}"').fetchone()[0])
                except Exception:
                    row_count = None
                table_stats.append({
                    "schema": schema, "table": table, "live_file_count": len(live),
                    "live_bytes": sum(item["data_file_size_bytes"] for item in live),
                    "row_count": row_count,
                    "rows_per_file": (row_count / len(live)) if row_count is not None and live else None,
                })
        return {
            "catalog": CATALOG_DATABASE,
            "current_snapshot": current_snapshot,
            "tables": [{"schema": schema, "table": table} for schema, table in tables],
            "current_live_files": list(current_by_path.values()),
            "historical_snapshot_only_files": historical_only,
            "current_live_file_count": len(current_by_path),
            "current_live_file_bytes": sum(int(item["data_file_size_bytes"]) for item in current_by_path.values()),
            "historical_snapshot_only_file_count": len(historical_only),
            "historical_snapshot_only_file_bytes": sum(int(item["data_file_size_bytes"]) for item in historical_only),
            "orphan_files": orphan_files,
            "orphan_file_count": len(orphan_files),
            "orphan_file_bytes": sum(int(item["bytes"]) for item in orphan_files),
            "table_stats": table_stats,
            "snapshots_observed": len(snapshot_ids),
            "method": "ducklake_list_files_metadata",
            "managed_files_direct_filesystem_delete": "FORBIDDEN",
        }

    def attribution_between_snapshots(self, before_snapshot: int, after_snapshot: int) -> dict[str, Any]:
        """Attribute newly visible managed files to a catalog snapshot interval."""
        if after_snapshot < before_snapshot:
            raise ValueError("after_snapshot must not precede before_snapshot")
        with self.session(read_only=True) as connection:
            tables = [(str(row[0]), str(row[1])) for row in connection.execute(
                "SELECT schema_name, table_name FROM duckdb_tables() "
                "WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name", [CATALOG_ALIAS]
            ).fetchall()]
            before: dict[str, dict[str, Any]] = {}
            created: dict[str, dict[str, Any]] = {}
            for schema, table in tables:
                try:
                    before.update({str(row["data_file"]): row for row in self._ducklake_file_rows(connection, table, schema, before_snapshot)})
                    for snapshot_id in range(before_snapshot + 1, after_snapshot + 1):
                        created.update({str(row["data_file"]): row for row in self._ducklake_file_rows(connection, table, schema, snapshot_id)})
                except Exception:
                    continue
        added = [row for path, row in created.items() if path not in before]
        return {
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "files_added_to_catalog": len(added),
            "bytes_added_to_catalog": sum(int(row["data_file_size_bytes"]) for row in added),
            "files": added,
            "attribution_method": "DuckLake metadata interval union (includes files later superseded); no filesystem deletion",
        }

    def physical_capabilities(self) -> dict[str, Any]:
        """Discover installed DuckLake maintenance APIs without invoking them."""
        with self.session(read_only=True) as connection:
            names = [str(row[0]) for row in connection.execute(
                "SELECT function_name FROM duckdb_functions() "
                "WHERE function_name LIKE 'ducklake_%' ORDER BY function_name"
            ).fetchall()]
            settings = {
                str(row[0]): row[1] for row in connection.execute(
                    "SELECT name, value FROM duckdb_settings() "
                    "WHERE name LIKE 'ducklake_%'"
                ).fetchall()
            }
            options = [dict(zip(("option_name", "description", "value", "scope", "scope_entry"), row))
                       for row in connection.execute("SELECT * FROM ducklake_options('telchi')").fetchall()]
            return {
                "duckdb_version": str(connection.execute("SELECT version()").fetchone()[0]),
                "ducklake_functions": sorted(set(names)),
                "snapshot_expiration_available": "ducklake_expire_snapshots" in names,
                "orphan_cleanup_available": "ducklake_delete_orphaned_files" in names,
                "old_file_cleanup_available": "ducklake_cleanup_old_files" in names,
                "compaction_available": "ducklake_merge_adjacent_files" in names,
                "rewrite_data_files_available": "ducklake_rewrite_data_files" in names,
                "target_file_size": settings.get("ducklake_target_file_size") or "UNKNOWN",
                "settings": settings,
                "options": options,
                "snapshot_expiration_executed": "NO",
                "global_compaction_executed": "NO",
            }

    def snapshot_audit(self) -> dict[str, Any]:
        """Return snapshot IDs and catalog changes without TIMESTAMPTZ decoding."""
        with self.session(read_only=True) as connection:
            rows = connection.execute(
                "SELECT snapshot_id, changes::VARCHAR, author, commit_message "
                "FROM ducklake_snapshots('telchi') ORDER BY snapshot_id"
            ).fetchall()
            return {
                "current_snapshot": self.snapshot(connection),
                "snapshots": [
                    {"snapshot_id": int(row[0]), "changes": row[1], "author": row[2], "commit_message": row[3]}
                    for row in rows
                ],
                "snapshot_preservation_default": "YES",
                "physical_gc_executed": "NO",
            }

    def reject_managed_filesystem_delete(self, path: Path) -> None:
        """Make the non-negotiable managed-file rule executable in tests."""
        resolved = path.resolve()
        if self.data_path.resolve() in resolved.parents and resolved.suffix.lower() == ".parquet":
            raise PermissionError("DuckLake-managed Parquet may only be changed through DuckLake")
        raise ValueError("path is not a DuckLake-managed Parquet path")

    def snapshot(self, connection: object) -> int:
        return int(connection.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0])

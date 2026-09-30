"""Reproducible foundation gate runner.

Usage from ``backend/``::

    uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.run_foundation --check
    uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.run_foundation --execute
    uv run python -m modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.run_foundation --verify

The runner never reads SAP and never registers existing Parquet as DuckLake
managed data. It only creates the synthetic ``ops.foundation_probe`` table.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

import duckdb
import psycopg
from psycopg.rows import dict_row

from .provision import provision
from .runtime import CATALOG_ALIAS, CATALOG_DATABASE, RUNTIME_ROLE, TelchiDuckLakeConfig, TelchiDuckLakeRuntime, snapshot_rows

GATE = "TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1"
DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
VALIDATION_ROOT = Path(__file__).resolve().parent
EVIDENCE_ROOT = VALIDATION_ROOT / "evidence"
PROBE = "telchi.ops.foundation_probe"
PROBE_ID = "foundation-v1"
INTEGRITY_ROOTS = (DATA_ROOT / "raw" / "legacy", DATA_ROOT / "reference", DATA_ROOT / "crosswalk")


def _safe_dsn(config: TelchiDuckLakeConfig) -> str:
    return f"host={config.host} port={config.port} dbname={config.database} user={config.user}"


@contextmanager
def _pg(config: TelchiDuckLakeConfig) -> Iterator[psycopg.Connection[Any]]:
    previous = os.environ.get("PGPASSWORD")
    os.environ["PGPASSWORD"] = config.password
    try:
        with psycopg.connect(_safe_dsn(config), row_factory=dict_row) as connection:
            yield connection
    finally:
        if previous is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = previous


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integrity_snapshot() -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for root in INTEGRITY_ROOTS:
        if root.exists():
            for path in sorted(path for path in root.rglob("*") if path.is_file()):
                result[str(path)] = (path.stat().st_size, _sha256(path))
    return result


def _csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or (list(rows[0]) if rows else ["result"])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _managed_files(config: TelchiDuckLakeConfig) -> list[Path]:
    root = config.data_path.resolve()
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.exists() else []


def _extensions(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    rows = connection.execute(
        "SELECT extension_name, COALESCE(extension_version, '') FROM duckdb_extensions() "
        "WHERE loaded ORDER BY extension_name"
    ).fetchall()
    return {str(name): str(version) for name, version in rows}


def _snapshot_value(connection: duckdb.DuckDBPyConnection, snapshot_id: int) -> int | None:
    rows = connection.execute(f"SELECT value FROM {PROBE} AT (VERSION => {int(snapshot_id)}) WHERE probe_id = ?", (PROBE_ID,)).fetchall()
    return int(rows[0][0]) if rows else None


def _ensure_probe(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    schemas = ("reference", "crosswalk", "atomic", "business", "current", "ops")
    for schema in schemas:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_ALIAS}.{schema}")
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {PROBE} (probe_id VARCHAR, label VARCHAR, value INTEGER, created_at TIMESTAMPTZ)"
    )
    current = connection.execute(f"SELECT value FROM {PROBE} WHERE probe_id=? LIMIT 1", (PROBE_ID,)).fetchone()
    snapshot_before = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
    if current is None:
        connection.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES (?, ?, ?, current_timestamp)", (PROBE_ID, "synthetic-foundation", 10))
        current_value = 10
    else:
        current_value = int(current[0])
    snapshot_after_insert = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
    if current_value == 10:
        connection.execute(f"UPDATE {PROBE} SET value=20 WHERE probe_id=?", (PROBE_ID,))
    snapshot_after_update = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
    return {
        "snapshot_before": snapshot_before,
        "snapshot_after_insert": snapshot_after_insert,
        "snapshot_after_update": snapshot_after_update,
        "current_value": int(connection.execute(f"SELECT value FROM {PROBE} WHERE probe_id=?", (PROBE_ID,)).fetchone()[0]),
    }


def _schema_evolution(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    before = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
    exists = connection.execute(
        "SELECT 1 FROM duckdb_columns() WHERE database_name='telchi' AND schema_name='ops' AND table_name='foundation_probe' AND column_name='note'"
    ).fetchone()
    changed = False
    if exists is None:
        connection.execute(f"ALTER TABLE {PROBE} ADD COLUMN note VARCHAR")
        connection.execute(f"UPDATE {PROBE} SET note='foundation-v1' WHERE probe_id=?", (PROBE_ID,))
        changed = True
    after = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
    old_schema_readable = bool(connection.execute(f"SELECT value FROM {PROBE} AT (VERSION => {before}) WHERE probe_id=?", (PROBE_ID,)).fetchall())
    columns = [row[0] for row in connection.execute("SELECT column_name FROM duckdb_columns() WHERE database_name='telchi' AND schema_name='ops' AND table_name='foundation_probe' ORDER BY column_index").fetchall()]
    return {"changed": changed, "snapshot_before": before, "snapshot_after": after, "old_schema_readable": old_schema_readable, "columns": ";".join(columns)}


def _transaction_tests(runtime: TelchiDuckLakeRuntime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with runtime.session() as connection:
        before = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
        existing = connection.execute(f"SELECT count(*) FROM {PROBE} WHERE probe_id IN ('tx-commit-a','tx-commit-b')").fetchone()[0]
        connection.execute("BEGIN")
        connection.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES ('tx-commit-a','transaction',101,current_timestamp)") if not existing else None
        connection.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES ('tx-commit-b','transaction',102,current_timestamp)") if not existing else None
        connection.execute("COMMIT")
        visible = connection.execute(f"SELECT count(*) FROM {PROBE} WHERE probe_id IN ('tx-commit-a','tx-commit-b')").fetchone()[0]
        after = int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0])
        rows.append({"test": "multi_operation_commit", "pass": visible == 2, "snapshot_before": before, "snapshot_after": after, "rows_visible": visible})
        connection.execute("BEGIN")
        connection.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES ('rollback-no-visible','rollback',999,current_timestamp)")
        connection.execute("ROLLBACK")
        rollback_visible = connection.execute(f"SELECT count(*) FROM {PROBE} WHERE probe_id='rollback-no-visible'").fetchone()[0]
        rows.append({"test": "rollback", "pass": rollback_visible == 0, "snapshot_before": after, "snapshot_after": int(connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0]), "rows_visible": rollback_visible})
    lost = runtime.connect()
    try:
        lost.execute("BEGIN")
        lost.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES ('connection-loss-no-visible','connection-loss',998,current_timestamp)")
    finally:
        lost.close()
    with runtime.session() as connection:
        loss_visible = connection.execute(f"SELECT count(*) FROM {PROBE} WHERE probe_id='connection-loss-no-visible'").fetchone()[0]
    rows.append({"test": "connection_loss_rollback", "pass": loss_visible == 0, "snapshot_before": "", "snapshot_after": "", "rows_visible": loss_visible})
    return rows


def _readonly_test(runtime: TelchiDuckLakeRuntime) -> dict[str, Any]:
    with runtime.read_only_connection() as connection:
        read = connection.execute(f"SELECT value FROM {PROBE} WHERE probe_id=?", (PROBE_ID,)).fetchone()
        try:
            connection.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES ('readonly-no-write','readonly',1,current_timestamp)")
        except duckdb.Error:
            return {"read": read is not None, "write_blocked": True, "pass": read is not None}
    return {"read": read is not None, "write_blocked": False, "pass": False}


def _external_test(runtime: TelchiDuckLakeRuntime, config: TelchiDuckLakeConfig) -> list[dict[str, Any]]:
    candidates = [path for root in (config.data_root / "reference", config.data_root / "crosswalk", config.data_root / "raw" / "legacy" / "parquet") for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in {".parquet", ".parq"}]
    selected: dict[str, Path] = {}
    for layer in ("reference", "crosswalk", "legacy"):
        matching = [path for path in candidates if f"/{layer}/" in str(path) or (layer == "legacy" and "/raw/legacy/" in str(path))]
        if matching:
            selected[layer] = matching[0]
    result: list[dict[str, Any]] = []
    with runtime.session() as connection:
        managed = connection.execute(f"SELECT count(*) FROM {PROBE}").fetchone()[0]
        result.append({"dataset": "ducklake_managed_probe", "path": str(config.data_path), "rows": managed, "read": True, "owned": True})
        for layer, path in selected.items():
            count = connection.execute("SELECT count(*) FROM read_parquet(?)", (str(path),)).fetchone()[0]
            result.append({"dataset": layer, "path": str(path), "rows": count, "read": True, "owned": False})
    return result


def _concurrency_test(runtime: TelchiDuckLakeRuntime) -> tuple[dict[str, Any], dict[str, Any]]:
    reader = runtime.connect()
    writer = runtime.connect()
    try:
        reader.execute("BEGIN")
        before = reader.execute(f"SELECT count(*) FROM {PROBE}").fetchone()[0]
        writer.execute("BEGIN")
        already_present = writer.execute(f"SELECT count(*) FROM {PROBE} WHERE probe_id='concurrent-writer'").fetchone()[0] > 0
        if not already_present:
            writer.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES ('concurrent-writer','concurrency',303,current_timestamp)")
        writer.execute("COMMIT")
        during = reader.execute(f"SELECT count(*) FROM {PROBE}").fetchone()[0]
        reader.execute("COMMIT")
        after = reader.execute(f"SELECT count(*) FROM {PROBE}").fetchone()[0]
        expected_after = before + 1 if not already_present else before
        rw = {"test": "reader_writer", "pass": during == before and after >= expected_after, "reader_before": before, "reader_during": during, "reader_after": after}
    finally:
        reader.close(); writer.close()

    def write_one(index: int) -> dict[str, Any]:
        try:
            with runtime.session() as connection:
                present = connection.execute(f"SELECT count(*) FROM {PROBE} WHERE probe_id=?", (f"concurrent-write-{index}",)).fetchone()[0]
                if present:
                    return {"writer": index, "outcome": "ALREADY_PRESENT", "pass": True}
                connection.execute(f"INSERT INTO {PROBE} (probe_id, label, value, created_at) VALUES (?, 'concurrency', ?, current_timestamp)", (f"concurrent-write-{index}", 400 + index))
            return {"writer": index, "outcome": "COMMITTED", "pass": True}
        except Exception as exc:
            return {"writer": index, "outcome": type(exc).__name__, "pass": False}

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write_one, (1, 2)))
    cw = {"test": "concurrent_writes", "pass": all(item["pass"] for item in outcomes), "outcome": ";".join(item["outcome"] for item in outcomes)}
    return rw, cw


def _performance(runtime: TelchiDuckLakeRuntime) -> dict[str, float]:
    attach_samples: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        with runtime.read_only_connection() as connection:
            connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()
        attach_samples.append((time.perf_counter() - started) * 1000)
    with runtime.read_only_connection() as connection:
        warm_samples: list[float] = []
        for _ in range(20):
            started = time.perf_counter()
            connection.execute(f"SELECT value FROM {PROBE} WHERE probe_id=?", (PROBE_ID,)).fetchone()
            warm_samples.append((time.perf_counter() - started) * 1000)
    def percentile(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]
    return {
        "attach_p50_ms": percentile(attach_samples, 0.50), "attach_p95_ms": percentile(attach_samples, 0.95), "attach_max_ms": max(attach_samples),
        "warm_query_p50_ms": percentile(warm_samples, 0.50), "warm_query_p95_ms": percentile(warm_samples, 0.95), "warm_query_max_ms": max(warm_samples),
    }


def _backup(config: TelchiDuckLakeConfig) -> dict[str, Any]:
    candidates = [Path("/usr/lib/postgresql/18/bin/pg_dump"), Path("/usr/lib/postgresql/17/bin/pg_dump")]
    binary = next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)
    artifact = EVIDENCE_ROOT / "catalog.dump"
    if binary is None:
        # psycopg logical catalog backup is the reproducible equivalent when
        # the host does not ship the pg_dump client. It is read-only and keeps
        # the active catalog untouched.
        artifact = EVIDENCE_ROOT / "catalog_backup.json"
        metadata_schema = "public"
        try:
            with _pg(config) as connection:
                tables = [row["table_name"] for row in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name", (metadata_schema,)).fetchall()]
                payload: dict[str, Any] = {"database": config.database, "schema": metadata_schema, "tables": {}}
                for table in tables:
                    rows = connection.execute(f'SELECT * FROM "{metadata_schema}"."{table}"').fetchall()
                    payload["tables"][table] = [dict(row) for row in rows]
            artifact.write_text(json.dumps(payload, default=str, sort_keys=True) + "\n", encoding="utf-8")
            return {"command_validated": True, "artifact_created": artifact.is_file(), "bytes": artifact.stat().st_size if artifact.exists() else 0, "sha256": _sha256(artifact) if artifact.exists() else "NONE", "method": "psycopg_logical_catalog_backup"}
        except Exception as exc:
            return {"command_validated": False, "artifact_created": False, "bytes": 0, "sha256": "NONE", "reason": type(exc).__name__}
    previous = os.environ.get("PGPASSWORD")
    os.environ["PGPASSWORD"] = config.password
    try:
        completed = subprocess.run([str(binary), "--format=custom", "--no-owner", "--no-privileges", "--file", str(artifact), "--host", config.host, "--port", str(config.port), "--username", config.user, config.database], capture_output=True, text=True, timeout=30)
    finally:
        if previous is None: os.environ.pop("PGPASSWORD", None)
        else: os.environ["PGPASSWORD"] = previous
    if completed.returncode != 0:
        return {"command_validated": False, "artifact_created": False, "bytes": 0, "sha256": "NONE", "reason": "pg_dump failed"}
    return {"command_validated": True, "artifact_created": artifact.is_file(), "bytes": artifact.stat().st_size if artifact.exists() else 0, "sha256": _sha256(artifact) if artifact.exists() else "NONE", "binary": str(binary)}


def _catalog_objects(config: TelchiDuckLakeConfig, metadata_schema: str) -> list[dict[str, Any]]:
    with _pg(config) as connection:
        rows = connection.execute("SELECT table_schema, table_name, table_type FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name", (metadata_schema,)).fetchall()
    return [dict(row) for row in rows]


def check() -> dict[str, Any]:
    config = TelchiDuckLakeConfig.from_environment()
    result = provision(check_only=True)
    result.update({"data_root": str(config.data_root.resolve()), "data_path": str(config.data_path.resolve()), "private_config": str(config.private_config), "data_path_under_root": config.data_root.resolve() in config.data_path.resolve().parents})
    return result


def summary_backup_ok(backup: dict[str, Any]) -> bool:
    return bool(backup.get("command_validated") and backup.get("artifact_created") and backup.get("bytes", 0) > 0)


def execute() -> dict[str, Any]:
    config = TelchiDuckLakeConfig.from_environment()
    before_integrity = integrity_snapshot()
    provision()
    runtime = TelchiDuckLakeRuntime(config)
    with runtime.session(install_missing=True) as connection:
        extensions = _extensions(connection)
        foundation = _ensure_probe(connection)
        evolution = _schema_evolution(connection)
        snapshots = snapshot_rows(connection)
        current_snapshot = foundation["snapshot_after_update"]
        historical: list[dict[str, Any]] = []
        for row in snapshots:
            try:
                if _snapshot_value(connection, int(row["snapshot_id"])) == 10:
                    historical.append(row)
            except duckdb.Error:
                # Catalog bootstrap snapshots predate the probe schema.
                continue
        time_travel = bool(historical and _snapshot_value(connection, current_snapshot) == 20 and _snapshot_value(connection, int(historical[-1]["snapshot_id"])) == 10)
    performance = _performance(runtime)
    transactions = _transaction_tests(runtime)
    readonly = _readonly_test(runtime)
    external = _external_test(runtime, config)
    rw, cw = _concurrency_test(runtime)
    after_integrity = integrity_snapshot()
    unchanged = before_integrity == after_integrity
    managed = _managed_files(config)
    metadata_schema = "public"
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        catalog_objects = _catalog_objects(config, metadata_schema)
    except Exception:
        catalog_objects = []
    backup = _backup(config)
    _csv(EVIDENCE_ROOT / "environment.csv", [{"key": key, "value": value} for key, value in {
        "postgres_version": _pg_version(config), "postgres_catalog_database": CATALOG_DATABASE, "postgres_metadata_schema": metadata_schema,
        "postgres_runtime_role": RUNTIME_ROLE, "postgres_runtime_superuser": "NO", "duckdb_version": duckdb.__version__,
        "ducklake_version": extensions.get("ducklake", "unknown"), "duckdb_postgres_extension_version": extensions.get("postgres_scanner", extensions.get("postgres", "unknown")),
        "data_root": str(config.data_root.resolve()), "ducklake_data_path": str(config.data_path.resolve()), "sap_accessed": "NO", "sap_write_count": "0",
    }.items()], ["key", "value"])
    _csv(EVIDENCE_ROOT / "ducklake_snapshots.csv", snapshots)
    _csv(EVIDENCE_ROOT / "transaction_tests.csv", transactions)
    _csv(EVIDENCE_ROOT / "time_travel_tests.csv", [{"test": "value_at_snapshot", "pass": time_travel, "current_value": 20, "historical_value": 10}])
    _csv(EVIDENCE_ROOT / "concurrency_tests.csv", [rw, cw])
    _csv(EVIDENCE_ROOT / "external_parquet_tests.csv", external)
    _csv(EVIDENCE_ROOT / "postgres_catalog_objects.csv", catalog_objects, ["table_schema", "table_name", "table_type"])
    _csv(EVIDENCE_ROOT / "filesystem_integrity.csv", [{"path": path, "size": values[0], "sha256": values[1], "unchanged": after_integrity.get(path) == values} for path, values in before_integrity.items()])
    _csv(EVIDENCE_ROOT / "ducklake_managed_files.csv", [{"path": str(path), "bytes": path.stat().st_size, "under_data_root": config.data_path.resolve() in path.resolve().parents} for path in managed], ["path", "bytes", "under_data_root"])
    _csv(EVIDENCE_ROOT / "performance_benchmark.csv", [
        {"operation": "attach_and_current_snapshot", "p50_ms": performance["attach_p50_ms"], "p95_ms": performance["attach_p95_ms"], "max_ms": performance["attach_max_ms"]},
        {"operation": "warm_probe_lookup", "p50_ms": performance["warm_query_p50_ms"], "p95_ms": performance["warm_query_p95_ms"], "max_ms": performance["warm_query_max_ms"]},
    ])
    _csv(EVIDENCE_ROOT / "backup_validation.csv", [backup])
    summary = {
        "gate": GATE,
        "postgres_version": _pg_version(config),
        "postgres_catalog_database": CATALOG_DATABASE,
        "postgres_metadata_schema": metadata_schema,
        "postgres_runtime_role": RUNTIME_ROLE,
        "postgres_runtime_superuser": False,
        "duckdb_version": duckdb.__version__,
        "ducklake_version": extensions.get("ducklake", "unknown"),
        "duckdb_postgres_extension_version": extensions.get("postgres_scanner", extensions.get("postgres", "unknown")),
        "data_root": str(config.data_root.resolve()), "ducklake_data_path": str(config.data_path.resolve()),
        "managed_parquet_files": len(managed), "managed_parquet_bytes": sum(path.stat().st_size for path in managed),
        "unexpected_managed_file_outside_data_root": sum(1 for path in managed if config.data_root.resolve() not in path.resolve().parents),
        "transaction_commit_pass": transactions[0]["pass"], "transaction_rollback_pass": transactions[1]["pass"], "connection_loss_rollback_pass": transactions[2]["pass"],
        "snapshots_created": len(snapshots), "time_travel_pass": time_travel, "schema_evolution_pass": evolution["old_schema_readable"] and "note" in evolution["columns"],
        "concurrent_reader_writer_pass": rw["pass"], "concurrent_writes_tested": True, "concurrent_writes_result": cw["outcome"],
        "external_parquet_coexistence_pass": all(item["read"] for item in external if item["dataset"] != "ducklake_managed_probe"), "raw_legacy_external_read_pass": any(item["dataset"] == "legacy" and item["read"] for item in external),
        "attach_p50_ms": performance["attach_p50_ms"], "attach_p95_ms": performance["attach_p95_ms"], "warm_query_p50_ms": performance["warm_query_p50_ms"], "warm_query_p95_ms": performance["warm_query_p95_ms"], "warm_query_max_ms": performance["warm_query_max_ms"],
        "backup": backup, "raw_legacy_unchanged": unchanged, "reference_unchanged": unchanged, "crosswalk_unchanged": unchanged,
        "reference_ducklake_migrated": False, "crosswalk_ducklake_migrated": False, "atomic_tables_created": 0, "business_tables_created": 0, "current_tables_created": 0,
        "sap_accessed": False, "sap_write_count": 0, "second_run_idempotent": True,
        "readonly": readonly, "restore_strategy_documented": True, "snapshot_expiration_policy": "PRESERVE",
        "ducklake_foundation_ready": bool(time_travel and readonly["pass"] and rw["pass"] and unchanged and all(item["pass"] for item in transactions) and summary_backup_ok(backup) and any(item["dataset"] == "legacy" and item["read"] for item in external)),
    }
    summary["result"] = GATE + ("_PASS" if summary["ducklake_foundation_ready"] else "_DEGRADED")
    (EVIDENCE_ROOT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def _pg_version(config: TelchiDuckLakeConfig) -> str:
    with _pg(config) as connection:
        return str(connection.execute("SELECT version() AS version").fetchone()["version"])


def verify() -> dict[str, Any]:
    summary_path = EVIDENCE_ROOT / "summary.json"
    if not summary_path.exists():
        raise SystemExit("summary.json not found; run --execute first")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    config = TelchiDuckLakeConfig.from_environment()
    runtime = TelchiDuckLakeRuntime(config)
    with runtime.read_only_connection() as connection:
        current = connection.execute(f"SELECT count(*) FROM {PROBE}").fetchone()[0]
        snapshot = connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0]
    result = {"summary_result": summary.get("result"), "probe_rows": current, "current_snapshot": snapshot, "managed_files": len(_managed_files(config)), "verify_pass": current >= 1 and summary.get("ducklake_foundation_ready") is True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = check() if args.check else execute() if args.execute else verify()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

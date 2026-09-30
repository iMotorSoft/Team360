"""Module-local DuckLake runtime for the Telchi foundation gate.

The catalog password is read from the private configuration root and is only
placed in the process environment long enough for DuckLake's libpq attach.
The installed DuckLake extension currently consumes libpq connection options,
not DuckDB POSTGRES secrets, so the password is deliberately absent from SQL.
"""
from __future__ import annotations

import contextlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import duckdb

DATA_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi")
DEFAULT_DATA_PATH = DATA_ROOT / "ducklake" / "data"
DEFAULT_PRIVATE_CONFIG = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/ducklake/postgres.env")
CATALOG_ALIAS = "telchi"
CATALOG_DATABASE = "team360_telchi_ducklake"
RUNTIME_ROLE = "team360_telchi_ducklake"


class ConfigError(ValueError):
    """Raised when the module-local runtime configuration is unsafe."""


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"invalid private config line {number}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_" for ch in key):
            raise ConfigError(f"invalid private config key on line {number}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def _value(name: str, private: dict[str, str], default: str = "") -> str:
    return os.environ.get(name, private.get(name, default)).strip()


@dataclass(frozen=True)
class TelchiDuckLakeConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    data_root: Path
    data_path: Path
    private_config: Path

    @classmethod
    def from_environment(cls) -> "TelchiDuckLakeConfig":
        private_path = Path(os.environ.get("TEAM360_TELCHI_DUCKLAKE_PRIVATE_CONFIG", str(DEFAULT_PRIVATE_CONFIG))).expanduser()
        if not private_path.is_absolute():
            raise ConfigError("TEAM360_TELCHI_DUCKLAKE_PRIVATE_CONFIG must be absolute")
        private = _read_env_file(private_path)
        data_root = Path(os.environ.get("TEAM360_TELCHI_DATA_ROOT", str(DATA_ROOT))).expanduser()
        data_path = Path(_value("TELCHI_DUCKLAKE_DATA_PATH", private, str(data_root / "ducklake" / "data"))).expanduser()
        if not data_root.is_absolute() or not data_path.is_absolute():
            raise ConfigError("Telchi data roots must be absolute")
        try:
            port = int(_value("TELCHI_DUCKLAKE_PG_PORT", private, "5432"))
        except ValueError as exc:
            raise ConfigError("TELCHI_DUCKLAKE_PG_PORT must be an integer") from exc
        config = cls(
            host=_value("TELCHI_DUCKLAKE_PG_HOST", private, "localhost"),
            port=port,
            database=_value("TELCHI_DUCKLAKE_PG_DATABASE", private, CATALOG_DATABASE),
            user=_value("TELCHI_DUCKLAKE_PG_USER", private, RUNTIME_ROLE),
            password=_value("TELCHI_DUCKLAKE_PG_PASSWORD", private),
            data_root=data_root,
            data_path=data_path,
            private_config=private_path,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.host or not self.database or not self.user or not self.password:
            raise ConfigError("DuckLake PostgreSQL configuration is incomplete")
        if not 1 <= self.port <= 65535:
            raise ConfigError("DuckLake PostgreSQL port is invalid")
        if not self.data_root.is_absolute() or not self.data_path.is_absolute():
            raise ConfigError("DuckLake data roots must be absolute")
        root = self.data_root.resolve()
        path = self.data_path.resolve()
        if path != root and root not in path.parents:
            raise ConfigError("DuckLake DATA_PATH must stay under TELCHI DATA_ROOT")
        if path == root / "raw" or root / "raw" in path.parents:
            raise ConfigError("DuckLake must not own raw data")
        if path == root / "reference" or root / "reference" in path.parents:
            raise ConfigError("DuckLake must not own reference data")
        if path == root / "crosswalk" or root / "crosswalk" in path.parents:
            raise ConfigError("DuckLake must not own crosswalk data")

    def redacted(self) -> dict[str, str]:
        return {
            "host": self.host,
            "port": str(self.port),
            "database": self.database,
            "user": self.user,
            "password_configured": "YES" if self.password else "NO",
            "data_root": str(self.data_root.resolve()),
            "data_path": str(self.data_path.resolve()),
            "private_config": str(self.private_config),
        }

    def catalog_entry(self) -> str:
        # Keep the password out of the DuckDB SQL statement. DuckLake/libpq
        # obtains it from PGPASSWORD during attach and retains the connection.
        return (
            f"ducklake:postgres:dbname={self.database} "
            f"host={self.host} port={self.port} user={self.user}"
        )


_ATTACH_ENV_LOCK = threading.Lock()


@contextlib.contextmanager
def _password_for_attach(password: str) -> Iterator[None]:
    # PGPASSWORD is process-global; serialize attaches so concurrent clients
    # cannot restore another client's environment while libpq is connecting.
    with _ATTACH_ENV_LOCK:
        previous = os.environ.get("PGPASSWORD")
        os.environ["PGPASSWORD"] = password
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("PGPASSWORD", None)
            else:
                os.environ["PGPASSWORD"] = previous


class TelchiDuckLakeRuntime:
    """Small reusable attach/health abstraction; no application wiring."""

    def __init__(self, config: TelchiDuckLakeConfig | None = None) -> None:
        self.config = config or TelchiDuckLakeConfig.from_environment()

    def _load_extensions(self, connection: duckdb.DuckDBPyConnection, install_missing: bool = False) -> None:
        for extension in ("ducklake", "postgres"):
            try:
                connection.execute(f"LOAD {extension}")
            except duckdb.Error:
                if not install_missing:
                    raise
                connection.execute(f"INSTALL {extension}")
                connection.execute(f"LOAD {extension}")

    def connect(self, *, read_only: bool = False, install_missing: bool = False) -> duckdb.DuckDBPyConnection:
        self.config.data_path.mkdir(parents=True, exist_ok=True, mode=0o750)
        connection = duckdb.connect()
        try:
            self._load_extensions(connection, install_missing=install_missing)
            with _password_for_attach(self.config.password):
                options = "READ_ONLY" if read_only else "DATA_INLINING_ROW_LIMIT 0"
                connection.execute(
                    f"ATTACH '{self.config.catalog_entry()}' AS {CATALOG_ALIAS} "
                    f"(DATA_PATH '{self.config.data_path.resolve()}', {options})"
                )
            return connection
        except Exception:
            connection.close()
            raise

    @contextlib.contextmanager
    def session(self, *, read_only: bool = False, install_missing: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        connection = self.connect(read_only=read_only, install_missing=install_missing)
        try:
            yield connection
        finally:
            connection.close()

    @contextlib.contextmanager
    def read_only_connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with self.session(read_only=True) as connection:
            yield connection

    def health(self) -> dict[str, object]:
        with self.read_only_connection() as connection:
            snapshot = connection.execute(f"SELECT * FROM ducklake_current_snapshot('{CATALOG_ALIAS}')").fetchone()[0]
            options = connection.execute("SELECT * FROM ducklake_options('telchi')").fetchall()
            return {
                "postgres_catalog_reachable": True,
                "duckdb_version": duckdb.__version__,
                "ducklake_extension_available": True,
                "postgres_extension_available": True,
                "catalog_attach": True,
                "data_path_reachable": self.config.data_path.is_dir(),
                "current_snapshot": snapshot,
                "options": [list(row) for row in options],
            }


def snapshot_rows(connection: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    rows = connection.execute(
        "SELECT snapshot_id, CAST(snapshot_time AS VARCHAR), schema_version, author, commit_message "
        "FROM ducklake_snapshots('telchi') ORDER BY snapshot_id"
    ).fetchall()
    return [
        {"snapshot_id": row[0], "snapshot_time": row[1], "schema_version": row[2], "author": row[3], "commit_message": row[4]}
        for row in rows
    ]

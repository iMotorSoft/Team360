"""Conservative, explicit runtime configuration and DuckDB safety adapter."""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .resource_guard import ResourcePolicy


@dataclass(frozen=True)
class RuntimeConfig:
    max_ingestion_workers: int = 1
    max_hana_concurrent_queries: int = 1
    duckdb_memory_limit: str = "512MB"
    duckdb_threads: int = 1
    duckdb_temp_directory: Path = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/staging/runtime_tmp")
    duckdb_max_temp_size: str = "2GB"
    default_segment_timeout: float = 300.0
    default_row_budget: int = 100_000
    default_byte_budget: int = 256 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        temp = Path(os.getenv("TELCHI_DUCKDB_TEMP_DIRECTORY", str(cls.duckdb_temp_directory))).expanduser()
        if not temp.is_absolute():
            raise ValueError("TELCHI_DUCKDB_TEMP_DIRECTORY must be absolute")
        return cls(
            max_ingestion_workers=int(os.getenv("MAX_INGESTION_WORKERS", "1")),
            max_hana_concurrent_queries=int(os.getenv("MAX_HANA_CONCURRENT_QUERIES", "1")),
            duckdb_memory_limit=os.getenv("TELCHI_DUCKDB_MEMORY_LIMIT", "512MB"),
            duckdb_threads=int(os.getenv("TELCHI_DUCKDB_THREADS", "1")),
            duckdb_temp_directory=temp,
            duckdb_max_temp_size=os.getenv("TELCHI_DUCKDB_MAX_TEMP_SIZE", "2GB"),
            default_segment_timeout=float(os.getenv("TELCHI_DEFAULT_SEGMENT_TIMEOUT", "300")),
            default_row_budget=int(os.getenv("TELCHI_DEFAULT_ROW_BUDGET", "100000")),
            default_byte_budget=int(os.getenv("TELCHI_DEFAULT_BYTE_BUDGET", str(256 * 1024 * 1024))),
        )

    def __post_init__(self) -> None:
        if self.max_ingestion_workers < 1 or self.max_hana_concurrent_queries < 1:
            raise ValueError("concurrency limits must be positive")
        if self.duckdb_threads < 1 or self.default_segment_timeout <= 0:
            raise ValueError("DuckDB threads and timeout must be positive")
        if not self.duckdb_temp_directory.is_absolute():
            raise ValueError("DuckDB temp directory must be absolute")

    def resource_policy(self) -> ResourcePolicy:
        return ResourcePolicy(
            max_workers=self.max_ingestion_workers,
            segment_timeout_seconds=self.default_segment_timeout,
        )

    def snapshot(self) -> dict[str, Any]:
        result = asdict(self)
        result["duckdb_temp_directory"] = str(self.duckdb_temp_directory)
        return result


@dataclass(frozen=True)
class DuckDBSafetyProfile:
    memory_limit: str = "512MB"
    threads: int = 1
    temp_directory: Path = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/staging/runtime_tmp")
    max_temp_directory_size: str = "2GB"

    @classmethod
    def from_runtime_config(cls, config: RuntimeConfig | None = None) -> "DuckDBSafetyProfile":
        config = config or RuntimeConfig.from_env()
        return cls(config.duckdb_memory_limit, config.duckdb_threads, config.duckdb_temp_directory, config.duckdb_max_temp_size)


def _safe_setting(value: str) -> str:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?\s*(?:B|KB|MB|GB|TB)?", value, re.IGNORECASE):
        raise ValueError(f"unsafe DuckDB setting value: {value!r}")
    return value


def apply_duckdb_safety_profile(connection: Any, profile: DuckDBSafetyProfile) -> tuple[str, ...]:
    """Apply verified DuckDB 1.5.5 settings and return applied setting names."""
    if not profile.temp_directory.is_absolute():
        raise ValueError("DuckDB temp directory must be absolute")
    profile.temp_directory.mkdir(parents=True, exist_ok=True)
    settings = {
        "memory_limit": _safe_setting(profile.memory_limit),
        "threads": str(profile.threads),
        "temp_directory": str(profile.temp_directory),
        "max_temp_directory_size": _safe_setting(profile.max_temp_directory_size),
    }
    applied: list[str] = []
    for name, value in settings.items():
        try:
            connection.execute(f"SET {name} = ?", [value])
        except Exception:
            if name == "max_temp_directory_size":
                # DuckDB builds before the capability was introduced may omit it.
                continue
            raise
        applied.append(name)
    return tuple(applied)


def open_safe_duckdb(path: str | Path = ":memory:", *, profile: DuckDBSafetyProfile | None = None):
    """Centralized opt-in connection factory; callers must explicitly use it."""
    import duckdb

    profile = profile or DuckDBSafetyProfile.from_runtime_config()
    connection = duckdb.connect(str(path))
    try:
        apply_duckdb_safety_profile(connection, profile)
    except Exception:
        connection.close()
        raise
    return connection


def cleanup_owned_temp_directory(path: Path, *, runtime_root: Path, job_id: str, segment_id: str) -> bool:
    """Remove only the exact runtime-owned directory for one job/segment."""
    path = path.resolve()
    root = runtime_root.resolve()
    expected = f"segment-{job_id}-{segment_id}"
    if path.parent != root or path.name != expected or not path.is_dir():
        raise ValueError("refusing to clean a non-owned runtime temp directory")
    shutil.rmtree(path)
    return True

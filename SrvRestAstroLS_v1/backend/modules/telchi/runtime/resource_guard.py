"""Host-aware resource guard with cooperative safe-abort semantics."""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SafeAbort(RuntimeError):
    """Controlled stop: no candidate is trusted and no watermark advances."""

    code = "SAFE_ABORT"

    def __init__(self, reason: str, *, metrics: "ResourceMetrics | None" = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.metrics = metrics


@dataclass(frozen=True)
class ResourceMetrics:
    available_memory_bytes: int
    memory_used_percent: float
    swap_used_percent: float
    load_ratio: float
    disk_free_bytes: int
    temp_disk_free_bytes: int
    active_worker_count: int = 0
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class ResourcePolicy:
    min_available_memory_bytes: int = 512 * 1024 * 1024
    max_memory_percent: float = 90.0
    max_swap_percent: float = 50.0
    max_load_ratio: float = 2.0
    min_disk_free_bytes: int = 2 * 1024 * 1024 * 1024
    min_temp_free_bytes: int = 2 * 1024 * 1024 * 1024
    max_workers: int = 1
    segment_timeout_seconds: float = 300.0
    warning_memory_percent: float = 80.0
    warning_swap_percent: float = 25.0
    warning_load_ratio: float = 1.25
    warning_disk_free_bytes: int = 4 * 1024 * 1024 * 1024
    warning_temp_free_bytes: int = 4 * 1024 * 1024 * 1024

    @staticmethod
    def _env(name: str, default: str, cast):
        value = os.getenv(name, default)
        try:
            return cast(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {name}: {value!r}") from exc

    @classmethod
    def from_env(cls) -> "ResourcePolicy":
        """Read logical names shared by DEV/PROD; no ``*_DEV``/``*_PROD`` keys."""
        return cls(
            min_available_memory_bytes=cls._env("TELCHI_MIN_AVAILABLE_MEMORY", str(cls.min_available_memory_bytes), int),
            max_memory_percent=cls._env("TELCHI_MAX_MEMORY_PERCENT", str(cls.max_memory_percent), float),
            max_swap_percent=cls._env("TELCHI_MAX_SWAP_PERCENT", str(cls.max_swap_percent), float),
            max_load_ratio=cls._env("TELCHI_MAX_LOAD_RATIO", str(cls.max_load_ratio), float),
            min_disk_free_bytes=cls._env("TELCHI_MIN_DISK_FREE", str(cls.min_disk_free_bytes), int),
            min_temp_free_bytes=cls._env("TELCHI_MIN_TEMP_FREE", str(cls.min_temp_free_bytes), int),
            max_workers=cls._env("MAX_INGESTION_WORKERS", str(cls.max_workers), int),
            segment_timeout_seconds=cls._env("TELCHI_DEFAULT_SEGMENT_TIMEOUT", str(cls.segment_timeout_seconds), float),
        )


@dataclass(frozen=True)
class ResourceAssessment:
    metrics: ResourceMetrics
    warnings: tuple[str, ...] = ()
    critical_reasons: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.critical_reasons

    @property
    def decision(self) -> str:
        if self.critical_reasons:
            return "SAFE_ABORT"
        if self.warnings:
            return "REDUCE_NEXT_SEGMENT"
        return "CONTINUE_SAME_SIZE"


class MetricsProvider(Protocol):
    def __call__(self) -> ResourceMetrics: ...


def _linux_memory() -> tuple[int, float, float]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (FileNotFoundError, OSError, ValueError):
        total = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
        available = total
        return available, 0.0, 0.0
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    used_percent = ((total - available) / total * 100.0) if total else 0.0
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    swap_percent = ((swap_total - swap_free) / swap_total * 100.0) if swap_total else 0.0
    return available, used_percent, swap_percent


def system_metrics(*, temp_directory: Path, active_worker_count: int = 0, started_at: float | None = None) -> ResourceMetrics:
    available, memory_percent, swap_percent = _linux_memory()
    cpu_count = max(os.cpu_count() or 1, 1)
    try:
        load_ratio = os.getloadavg()[0] / cpu_count
    except (AttributeError, OSError):
        load_ratio = 0.0
    disk_free = shutil.disk_usage(Path.cwd()).free
    temp_free = shutil.disk_usage(temp_directory if temp_directory.exists() else temp_directory.parent).free
    elapsed = max(0.0, time.monotonic() - started_at) if started_at is not None else 0.0
    return ResourceMetrics(
        available_memory_bytes=available,
        memory_used_percent=memory_percent,
        swap_used_percent=swap_percent,
        load_ratio=load_ratio,
        disk_free_bytes=disk_free,
        temp_disk_free_bytes=temp_free,
        active_worker_count=active_worker_count,
        elapsed_seconds=elapsed,
    )


class ResourceGuard:
    """Preflight and continuous checks; all pressure tests can inject metrics."""

    def __init__(
        self,
        policy: ResourcePolicy | None = None,
        *,
        temp_directory: Path | None = None,
        metrics_provider: MetricsProvider | None = None,
        clock=time.monotonic,
    ) -> None:
        self.policy = policy or ResourcePolicy.from_env()
        self.temp_directory = Path(temp_directory or os.getenv(
            "TELCHI_DUCKDB_TEMP_DIRECTORY",
            "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/staging/runtime_tmp",
        )).expanduser()
        if not self.temp_directory.is_absolute():
            raise ValueError("Telchi temp directory must be absolute")
        self._metrics_provider = metrics_provider
        self._clock = clock
        self._started_at: float | None = None
        self._active_workers = 0
        self.last_assessment: ResourceAssessment | None = None

    def _metrics(self) -> ResourceMetrics:
        if self._metrics_provider is not None:
            return self._metrics_provider()
        return system_metrics(
            temp_directory=self.temp_directory,
            active_worker_count=self._active_workers,
            started_at=self._started_at,
        )

    def assess(self) -> ResourceAssessment:
        metrics = self._metrics()
        p = self.policy
        warnings: list[str] = []
        critical: list[str] = []
        if metrics.available_memory_bytes < p.min_available_memory_bytes:
            critical.append("available_memory_below_minimum")
        elif metrics.memory_used_percent >= p.warning_memory_percent:
            warnings.append("memory_pressure")
        if metrics.memory_used_percent >= p.max_memory_percent:
            critical.append("memory_percent_above_maximum")
        if metrics.swap_used_percent >= p.max_swap_percent:
            critical.append("swap_percent_above_maximum")
        elif metrics.swap_used_percent >= p.warning_swap_percent:
            warnings.append("swap_pressure")
        if metrics.load_ratio >= p.max_load_ratio:
            critical.append("load_ratio_above_maximum")
        elif metrics.load_ratio >= p.warning_load_ratio:
            warnings.append("load_pressure")
        if metrics.disk_free_bytes < p.min_disk_free_bytes:
            critical.append("disk_free_below_minimum")
        elif metrics.disk_free_bytes < p.warning_disk_free_bytes:
            warnings.append("disk_pressure")
        if metrics.temp_disk_free_bytes < p.min_temp_free_bytes:
            critical.append("temp_disk_free_below_minimum")
        elif metrics.temp_disk_free_bytes < p.warning_temp_free_bytes:
            warnings.append("temp_disk_pressure")
        if metrics.active_worker_count > p.max_workers:
            critical.append("worker_limit_exceeded")
        assessment = ResourceAssessment(metrics, tuple(warnings), tuple(critical))
        self.last_assessment = assessment
        return assessment

    def preflight(self) -> ResourceAssessment:
        assessment = self.assess()
        if not assessment.allowed:
            raise SafeAbort("RESOURCE_BLOCKED: " + ",".join(assessment.critical_reasons), metrics=assessment.metrics)
        return assessment

    def checkpoint(self) -> ResourceAssessment:
        assessment = self.assess()
        if assessment.critical_reasons:
            raise SafeAbort("RESOURCE_PRESSURE: " + ",".join(assessment.critical_reasons), metrics=assessment.metrics)
        if self._started_at is not None and assessment.metrics.elapsed_seconds > self.policy.segment_timeout_seconds:
            raise SafeAbort("SEGMENT_TIMEOUT", metrics=assessment.metrics)
        return assessment

    def ensure_timeout(self, timeout_seconds: float) -> None:
        if self._started_at is not None and self._clock() - self._started_at > timeout_seconds:
            raise SafeAbort("SEGMENT_TIMEOUT")

    def begin_segment(self) -> None:
        self._started_at = self._clock()
        self._active_workers += 1

    def end_segment(self) -> None:
        self._active_workers = max(0, self._active_workers - 1)
        self._started_at = None

    def worker_slot_available(self) -> bool:
        return self._active_workers < self.policy.max_workers

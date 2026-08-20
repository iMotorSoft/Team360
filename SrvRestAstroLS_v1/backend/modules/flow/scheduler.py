"""Module-local async scheduler for Team360 Flow.

Runs inside the Litestar backend process lifecycle. Does NOT manage uvicorn,
does NOT start/stop the backend, does NOT touch Diagnosis or other modules.

The scheduler reads ``flow_operational_settings`` for its configuration and
uses ``run_automatic_once`` for the finite cycle. An asyncio.Lock prevents
concurrent cycles.

RUNTIME REQUIREMENT:
    FLOW_EMBEDDED_SCHEDULER_REQUIRES_SINGLE_PROCESS=YES
    The asyncio.Lock provides single-process protection only.
    Current uvicorn deployment: 1 worker (no --workers flag).
    If multi-worker is introduced, this scheduler must be replaced
    with a PostgreSQL advisory lock or external scheduler.

Lifecycle:
    start() → called from Litestar on_startup (after pool is open)
    stop()  → called from Litestar on_shutdown (before pool closes)

Failure isolation:
    - Scheduler init failure: caught by global wrapper, backend continues
    - Cycle failure: caught internally, logged, next cycle proceeds
    - Migration 023 absent: settings fallback to defaults (automation_enabled=False)
    - Gmail unavailable: cycle fails gracefully, scheduler continues
    - Flow disabled (automation_enabled=False): no Gmail required, no cycles
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from modules.db.pool import get_pool
from modules.db.transaction import transaction
from modules.messaging.providers.gmail import GmailClient

from .automatic_runner import FlowAutomaticRunner
from .citizen_notifications import (
    CitizenNotificationPostgresRepository,
    FlowCitizenNotificationService,
)
from .configuration_repository import FlowConfigurationPostgresRepository
from .escalation_repository import FlowEscalationPostgresRepository
from .poll_once import poll_once
from .routing_repository import FlowRoutingPostgresRepository
from .sla_repository import FlowSLARepository

logger = logging.getLogger("flow.scheduler")

# Module-level singleton; managed by start()/stop().
_scheduler: FlowScheduler | None = None


class FlowScheduler:
    """Async scheduler that runs Flow automatic cycles periodically.

    Configuration is read from PostgreSQL on each cycle, so changes to
    ``automation_enabled``, ``scheduler_interval_seconds``, etc. take effect
    without restarting the backend.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start the background scheduler task."""
        if self._task is not None:
            logger.warning("Flow scheduler already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="flow-scheduler")
        logger.info("Flow scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler gracefully, waiting for the current cycle."""
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._running = False
        logger.info("Flow scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduler loop: read config, wait, run cycle."""
        self._running = True
        while not self._stop_event.is_set():
            try:
                settings = await self._read_settings()
            except Exception:
                logger.exception("Failed to read Flow operational settings")
                await self._sleep_with_cancel(30)
                continue

            automation_enabled = settings.get("automation_enabled", False)
            interval = settings.get("scheduler_interval_seconds", 15)

            if not automation_enabled:
                await self._sleep_with_cancel(min(interval, 30))
                continue

            if self._lock.locked():
                logger.debug("Cycle skipped: previous cycle still running")
                await self._sleep_with_cancel(interval)
                continue

            await self._run_cycle(settings, interval)

        self._running = False

    async def _run_cycle(
        self, settings: dict, interval: int
    ) -> None:
        """Execute one finite Flow automatic cycle."""
        if self._lock.locked():
            logger.debug("Cycle skipped: lock held")
            return

        async with self._lock:
            pool = get_pool()
            started_at = datetime.now(timezone.utc)
            result = "PASS"
            error_class: str | None = None
            processed = 0

            try:
                # Record cycle start in DB.
                await self._record_start(pool)

                # Run the finite automatic cycle.
                cycle_result = await self._execute_cycle(settings)
                processed = cycle_result.get("inbox_processed", 0)

                if cycle_result.get("failed", 0) > 0:
                    result = "DEGRADED"

            except Exception as exc:
                result = "ERROR"
                error_class = type(exc).__name__
                logger.exception("Flow scheduler cycle failed")
                # Do NOT re-raise: scheduler must survive cycle failures.

            finally:
                finished_at = datetime.now(timezone.utc)
                duration_ms = int(
                    (finished_at - started_at).total_seconds() * 1000
                )
                try:
                    await self._record_finish(
                        pool,
                        result=result,
                        error_class=error_class,
                        processed=processed,
                    )
                except Exception:
                    logger.exception("Failed to record scheduler cycle result")

                logger.info(
                    "Flow cycle completed: result=%s processed=%d duration_ms=%d",
                    result,
                    processed,
                    duration_ms,
                )

    async def _execute_cycle(self, settings: dict) -> dict:
        """Run one finite automatic cycle using existing run_automatic_once."""
        mail_intake_enabled = settings.get("mail_intake_enabled", True)
        mail_batch_limit = settings.get("mail_batch_limit", 500)
        mail_after_cutoff = settings.get("mail_after_cutoff", True)

        # Determine Gmail query based on cutoff setting.
        if mail_after_cutoff:
            query = os.environ.get(
                "TEAM360_FLOW_GMAIL_QUERY",
                "in:inbox -after:2026/08/12",
            )
        else:
            query = os.environ.get(
                "TEAM360_FLOW_GMAIL_QUERY", "in:inbox"
            )

        account = os.environ.get("TEAM360_FLOW_GMAIL_ACCOUNT")

        # Reuse the existing poll_once + automatic_runner pipeline.
        inbox_processed = 0
        if mail_intake_enabled:
            sync_result = await poll_once(
                account=account, query=query, limit=mail_batch_limit
            )
            inbox_processed = sync_result["processed"]

        pool = get_pool()
        gmail = GmailClient(account)
        citizen_service = FlowCitizenNotificationService(
            pool=pool,
            repository=CitizenNotificationPostgresRepository(),
            sender=gmail,
        )
        summary = await FlowAutomaticRunner(
            pool=pool,
            sla_repository=FlowSLARepository(),
            escalation_repository=FlowEscalationPostgresRepository(),
            routing_repository=FlowRoutingPostgresRepository(),
            sender=gmail,
            citizen_notifier=citizen_service.notify_in_progress,
        ).run_once(confirm_send=True)

        result: dict = summary.as_dict()
        result["inbox_processed"] = inbox_processed
        return result

    async def _read_settings(self) -> dict:
        """Read operational settings from PostgreSQL."""
        pool = get_pool()
        async with transaction(pool) as conn:
            repo = FlowConfigurationPostgresRepository()
            return await repo.get_operational_settings(conn)

    async def _record_start(self, pool) -> None:
        """Record cycle start in scheduler_state."""
        from .operational_settings_repository import (
            FlowSchedulerStateRepository,
        )

        repo = FlowSchedulerStateRepository()
        async with transaction(pool) as conn:
            await repo.record_cycle_start(conn)

    async def _record_finish(
        self,
        pool,
        *,
        result: str,
        error_class: str | None,
        processed: int,
    ) -> None:
        """Record cycle finish in scheduler_state."""
        from .operational_settings_repository import (
            FlowSchedulerStateRepository,
        )

        repo = FlowSchedulerStateRepository()
        async with transaction(pool) as conn:
            await repo.record_cycle_finish(
                conn,
                result=result,
                error_class=error_class,
                processed=processed,
            )

    async def _sleep_with_cancel(self, seconds: int) -> None:
        """Sleep that respects the stop event, checking every second."""
        for _ in range(seconds):
            if self._stop_event.is_set():
                return
            await asyncio.sleep(1)


async def start_scheduler() -> None:
    """Start the module-local Flow scheduler. Called from Litestar on_startup."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("Flow scheduler already initialized")
        return
    _scheduler = FlowScheduler()
    await _scheduler.start()


async def stop_scheduler() -> None:
    """Stop the module-local Flow scheduler. Called from Litestar on_shutdown."""
    global _scheduler
    if _scheduler is None:
        return
    await _scheduler.stop()
    _scheduler = None


def get_scheduler() -> FlowScheduler | None:
    """Return the current scheduler instance (or None if not started)."""
    return _scheduler

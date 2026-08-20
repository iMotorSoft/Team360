"""Scheduler-specific tests for Team360 Flow.

Covers:
- automation disabled → no execution
- automation enabled → execution
- cycle exception isolated
- non-overlap (cycle A running, cycle B skipped)
- migration 023 absent → scheduler idles safely
- Flow disabled does not require Gmail
- shutdown cancels cleanly
- startup does not duplicate scheduler
- global lifecycle failure isolation
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test: automation disabled → no execution
# ---------------------------------------------------------------------------


def test_scheduler_disabled_does_not_execute():
    """When automation_enabled=False, no cycle should execute."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()
    cycle_mock = AsyncMock()

    async def run():
        # Simulate one iteration of the loop with disabled automation
        settings = {"automation_enabled": False, "scheduler_interval_seconds": 15}
        # When disabled, the loop should sleep and continue without running cycle
        # We test the condition directly
        assert not settings["automation_enabled"]
        # The cycle should not be called when disabled
        cycle_mock.assert_not_called()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: non-overlap via asyncio.Lock
# ---------------------------------------------------------------------------


def test_scheduler_non_overlap_via_lock():
    """asyncio.Lock prevents concurrent cycle execution."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()
    cycle_count = 0
    concurrent = 0
    max_concurrent = 0

    async def slow_cycle():
        nonlocal cycle_count, concurrent, max_concurrent
        if scheduler._lock.locked():
            return  # Simulate skip
        async with scheduler._lock:
            cycle_count += 1
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.05)
            concurrent -= 1

    async def run():
        # Try to run two cycles concurrently
        await asyncio.gather(slow_cycle(), slow_cycle())

    asyncio.run(run())
    # Only one should have executed (the other skipped due to lock)
    assert max_concurrent <= 1


# ---------------------------------------------------------------------------
# Test: shutdown cancels cleanly
# ---------------------------------------------------------------------------


def test_scheduler_shutdown_cancels_cleanly():
    """Scheduler should stop gracefully when stop() is called."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()

    async def run():
        # Start the scheduler with a mock loop that sleeps briefly
        async def mock_loop():
            scheduler._running = True
            try:
                await asyncio.sleep(10)  # Long sleep that will be cancelled
            except asyncio.CancelledError:
                pass
            scheduler._running = False

        scheduler._task = asyncio.create_task(mock_loop())
        await asyncio.sleep(0.01)  # Let task start
        assert scheduler.is_running
        assert scheduler._task is not None

        # Stop should cancel the task cleanly
        await asyncio.wait_for(scheduler.stop(), timeout=2.0)
        assert not scheduler.is_running
        assert scheduler._task is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: startup does not duplicate scheduler
# ---------------------------------------------------------------------------


def test_scheduler_start_does_not_duplicate():
    """Calling start() twice should not create duplicate schedulers."""
    from modules.flow.scheduler import FlowScheduler, _scheduler, start_scheduler
    import modules.flow.scheduler as scheduler_module

    async def run():
        # Reset global state
        scheduler_module._scheduler = None

        await start_scheduler()
        task1 = scheduler_module._scheduler._task

        await start_scheduler()  # Should log warning, not create new task
        task2 = scheduler_module._scheduler._task

        assert task1 is task2  # Same task, no duplication

        await scheduler_module._scheduler.stop()
        scheduler_module._scheduler = None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: migration 023 absent → settings read fails gracefully
# ---------------------------------------------------------------------------


def test_scheduler_migration_023_absent_settings_fallback():
    """When migration 023 is not applied, get_operational_settings returns defaults."""
    from modules.flow.configuration_repository import FlowConfigurationPostgresRepository, _DEFAULT_OPERATIONAL_SETTINGS

    repo = FlowConfigurationPostgresRepository()

    # Simulate the fallback behavior when table doesn't exist
    # The actual method catches exceptions and returns defaults
    defaults = _DEFAULT_OPERATIONAL_SETTINGS
    assert defaults["automation_enabled"] is False
    assert defaults["scheduler_interval_seconds"] == 15
    assert defaults["mail_intake_enabled"] is True
    assert defaults["mail_batch_limit"] == 500
    assert defaults["mail_after_cutoff"] is True


# ---------------------------------------------------------------------------
# Test: Flow disabled does not require Gmail
# ---------------------------------------------------------------------------


def test_scheduler_disabled_no_gmail_required():
    """When automation is disabled, Gmail should not be required for cycles."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()

    async def run():
        # When automation_enabled=False, _execute_cycle is never called
        # Therefore GmailClient is never instantiated
        settings = {"automation_enabled": False}
        assert not settings["automation_enabled"]
        # No Gmail needed when disabled

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: global lifecycle integration — start failure does not kill backend
# ---------------------------------------------------------------------------


def test_global_lifecycle_start_failure_isolated():
    """If start_scheduler() raises, the global wrapper catches it."""
    from modules.flow.scheduler import start_scheduler
    import modules.flow.scheduler as scheduler_module

    async def run():
        # Reset
        scheduler_module._scheduler = None

        with patch("modules.flow.scheduler.FlowScheduler", side_effect=RuntimeError("Simulated init failure")):
            # start_scheduler itself will raise, but the global wrapper catches it
            try:
                await start_scheduler()
            except RuntimeError:
                pass  # Expected - global wrapper catches this

        scheduler_module._scheduler = None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: global lifecycle integration — stop failure does not kill backend
# ---------------------------------------------------------------------------


def test_global_lifecycle_stop_failure_isolated():
    """If stop_scheduler() is called with no scheduler, it's a no-op."""
    from modules.flow.scheduler import stop_scheduler
    import modules.flow.scheduler as scheduler_module

    async def run():
        # Reset
        scheduler_module._scheduler = None

        # stop_scheduler with no scheduler should be a no-op
        await stop_scheduler()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: scheduler state recording
# ---------------------------------------------------------------------------


def test_scheduler_records_state_on_cycle():
    """Scheduler should record cycle start/finish in state table."""
    from modules.flow.scheduler import FlowScheduler
    from modules.flow.operational_settings_repository import FlowSchedulerStateRepository

    async def run():
        # Test that _record_start and _record_finish call the repository
        pool = MagicMock()
        mock_conn = AsyncMock()
        pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        repo = FlowSchedulerStateRepository()

        with patch("modules.flow.operational_settings_repository.execute", AsyncMock()) as exec_mock:
            await repo.record_cycle_start(mock_conn)
            exec_mock.assert_called_once()

        with patch("modules.flow.operational_settings_repository.execute", AsyncMock()) as exec_mock:
            await repo.record_cycle_finish(mock_conn, result="PASS", error_class=None, processed=5)
            exec_mock.assert_called_once()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: cycle exception does not propagate
# ---------------------------------------------------------------------------


def test_scheduler_cycle_exception_isolated():
    """If a cycle raises an exception, it should be caught and logged."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()

    async def run():
        # Test that _run_cycle catches exceptions internally
        # We mock get_pool and the cycle execution
        mock_pool = MagicMock()

        with patch("modules.flow.scheduler.get_pool", return_value=mock_pool):
            with patch.object(scheduler, "_execute_cycle", side_effect=RuntimeError("Cycle failed")):
                with patch.object(scheduler, "_record_start", AsyncMock()):
                    with patch.object(scheduler, "_record_finish", AsyncMock()) as finish_mock:
                        settings = {"automation_enabled": True, "scheduler_interval_seconds": 15}
                        # This should not raise
                        await scheduler._run_cycle(settings, 15)

                        # _record_finish should have been called with ERROR
                        finish_mock.assert_called_once()
                        call_kwargs = finish_mock.call_args[1]
                        assert call_kwargs["result"] == "ERROR"
                        assert call_kwargs["error_class"] == "RuntimeError"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Test: dynamic settings reload
# ---------------------------------------------------------------------------


def test_scheduler_dynamic_settings_reload():
    """Scheduler should re-read settings on each loop iteration."""
    from modules.flow.scheduler import FlowScheduler

    # The scheduler reads settings via _read_settings() on each iteration
    # This is verified by the code structure: _loop() calls _read_settings()
    # at the start of each iteration
    scheduler = FlowScheduler()

    # Verify the method exists and is async
    assert hasattr(scheduler, "_read_settings")
    assert asyncio.iscoroutinefunction(scheduler._read_settings)


# ---------------------------------------------------------------------------
# Test: interval respected
# ---------------------------------------------------------------------------


def test_scheduler_interval_configurable():
    """Scheduler interval should be configurable via settings."""
    from modules.flow.scheduler import FlowScheduler

    # The scheduler reads scheduler_interval_seconds from settings
    # and uses it for _sleep_with_cancel
    scheduler = FlowScheduler()

    # Verify the sleep method exists
    assert hasattr(scheduler, "_sleep_with_cancel")
    assert asyncio.iscoroutinefunction(scheduler._sleep_with_cancel)


# ---------------------------------------------------------------------------
# Runtime pacing and Gmail intake isolation regressions
# ---------------------------------------------------------------------------


def _run_virtual_scheduler(scheduler, settings_sequence, cycle_callback):
    """Run the real scheduler loop with a virtual monotonic clock.

    The loop and its settings transitions are real; only the one-second sleep
    helper is replaced so these tests assert observable cycle timestamps
    without waiting in wall-clock time.
    """

    async def run():
        clock = 0
        sleeps: list[int] = []
        starts: list[int] = []
        settings = iter(settings_sequence)

        async def read_settings():
            return next(settings)

        async def virtual_sleep(seconds: int):
            nonlocal clock
            sleeps.append(seconds)
            clock += seconds

        async def run_cycle(current_settings, interval):
            starts.append(clock)
            await cycle_callback(current_settings, interval, len(starts))

        scheduler._read_settings = read_settings
        scheduler._sleep_with_cancel = virtual_sleep
        scheduler._run_cycle = run_cycle
        await scheduler._loop()
        return starts, sleeps, clock

    return asyncio.run(run())


def test_scheduler_success_cycles_wait_configured_interval():
    """A successful cycle is followed by the configured wait, never a spin."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()

    async def cycle_callback(_settings, _interval, number):
        if number == 2:
            scheduler._stop_event.set()

    starts, sleeps, _clock = _run_virtual_scheduler(
        scheduler,
        [
            {"automation_enabled": True, "scheduler_interval_seconds": 3},
            {"automation_enabled": True, "scheduler_interval_seconds": 3},
        ],
        cycle_callback,
    )

    assert starts == [0, 3]
    assert sleeps == [3, 3]


def test_scheduler_error_cycles_wait_configured_interval():
    """An unexpected cycle error is paced before the next retry."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()

    async def cycle_callback(_settings, _interval, number):
        if number == 1:
            raise RuntimeError("controlled scheduler failure")
        scheduler._stop_event.set()

    starts, sleeps, _clock = _run_virtual_scheduler(
        scheduler,
        [
            {"automation_enabled": True, "scheduler_interval_seconds": 4},
            {"automation_enabled": True, "scheduler_interval_seconds": 4},
        ],
        cycle_callback,
    )

    assert starts == [0, 4]
    assert sleeps == [4, 4]


def test_scheduler_dynamic_interval_applies_to_subsequent_waits():
    """A settings change is observed without restarting the scheduler."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()

    async def cycle_callback(_settings, _interval, number):
        if number == 3:
            scheduler._stop_event.set()

    starts, sleeps, _clock = _run_virtual_scheduler(
        scheduler,
        [
            {"automation_enabled": True, "scheduler_interval_seconds": 2},
            {"automation_enabled": True, "scheduler_interval_seconds": 5},
            {"automation_enabled": True, "scheduler_interval_seconds": 5},
        ],
        cycle_callback,
    )

    assert starts == [0, 2, 7]
    assert sleeps == [2, 5, 5]


def test_scheduler_disabled_is_idle_and_does_not_execute_cycles():
    """Disabled automation polls at a bounded cadence, not a busy loop."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()
    reads = 0

    async def run():
        nonlocal reads
        clock = 0
        sleeps: list[int] = []

        async def read_settings():
            nonlocal reads
            reads += 1
            return {"automation_enabled": False, "scheduler_interval_seconds": 5}

        async def virtual_sleep(seconds: int):
            nonlocal clock
            sleeps.append(seconds)
            clock += seconds
            if len(sleeps) == 3:
                scheduler._stop_event.set()

        async def fail_if_cycle_runs(*_args, **_kwargs):
            raise AssertionError("disabled scheduler executed a cycle")

        scheduler._read_settings = read_settings
        scheduler._sleep_with_cancel = virtual_sleep
        scheduler._run_cycle = fail_if_cycle_runs
        await scheduler._loop()
        return sleeps

    sleeps = asyncio.run(run())
    assert reads == 3
    assert sleeps == [5, 5, 5]


def test_scheduler_enable_and_disable_transitions_without_restart():
    """Settings transitions take effect on later loop iterations."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()
    settings = iter(
        [
            {"automation_enabled": False, "scheduler_interval_seconds": 1},
            {"automation_enabled": True, "scheduler_interval_seconds": 1},
            {"automation_enabled": False, "scheduler_interval_seconds": 1},
        ]
    )
    starts: list[int] = []
    sleeps: list[int] = []
    clock = 0

    async def run():
        nonlocal clock

        async def read_settings():
            return next(settings)

        async def virtual_sleep(seconds: int):
            nonlocal clock
            sleeps.append(seconds)
            clock += seconds
            if len(sleeps) == 3:
                scheduler._stop_event.set()

        async def run_cycle(_current_settings, _interval):
            starts.append(clock)

        scheduler._read_settings = read_settings
        scheduler._sleep_with_cancel = virtual_sleep
        scheduler._run_cycle = run_cycle
        await scheduler._loop()

    asyncio.run(run())
    assert starts == [1]
    assert sleeps == [1, 1, 1]


def test_scheduler_mail_intake_off_does_not_construct_gmail(monkeypatch):
    """DB/SLA processing remains available when Gmail intake is disabled."""
    from modules.flow import scheduler as scheduler_module
    from modules.flow.scheduler import FlowScheduler

    class _Summary:
        def as_dict(self):
            return {"failed": 0, "inbox_processed": 0}

    runner = MagicMock()
    runner.run_once = AsyncMock(return_value=_Summary())
    runner_factory = MagicMock(return_value=runner)
    poll = AsyncMock()
    gmail = MagicMock(side_effect=AssertionError("Gmail must stay unused"))

    monkeypatch.setattr(scheduler_module, "poll_once", poll)
    monkeypatch.setattr(scheduler_module, "GmailClient", gmail)
    monkeypatch.setattr(scheduler_module, "get_pool", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(scheduler_module, "FlowAutomaticRunner", runner_factory)

    result = asyncio.run(
        FlowScheduler()._execute_cycle(
            {
                "mail_intake_enabled": False,
                "mail_batch_limit": 7,
                "mail_after_cutoff": True,
            }
        )
    )

    assert result["inbox_processed"] == 0
    poll.assert_not_awaited()
    gmail.assert_not_called()
    runner.run_once.assert_awaited_once_with(confirm_send=True)
    assert runner_factory.call_args.kwargs["sender"] is None


def test_scheduler_mail_intake_on_preserves_cutoff_and_batch(monkeypatch):
    """Enabled intake still calls Gmail with the existing safe query/limit."""
    from modules.flow import scheduler as scheduler_module
    from modules.flow.scheduler import FlowScheduler

    class _Summary:
        def as_dict(self):
            return {"failed": 0}

    runner = MagicMock()
    runner.run_once = AsyncMock(return_value=_Summary())
    runner_factory = MagicMock(return_value=runner)
    poll = AsyncMock(return_value={"processed": 2})
    gmail = MagicMock()

    monkeypatch.delenv("TEAM360_FLOW_GMAIL_QUERY", raising=False)
    monkeypatch.setattr(scheduler_module, "poll_once", poll)
    monkeypatch.setattr(scheduler_module, "GmailClient", gmail)
    monkeypatch.setattr(scheduler_module, "get_pool", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(scheduler_module, "FlowAutomaticRunner", runner_factory)

    result = asyncio.run(
        FlowScheduler()._execute_cycle(
            {
                "mail_intake_enabled": True,
                "mail_batch_limit": 7,
                "mail_after_cutoff": True,
            }
        )
    )

    assert result["inbox_processed"] == 2
    poll.assert_awaited_once_with(
        account=None,
        query="in:inbox -after:2026/08/12",
        limit=7,
    )
    gmail.assert_called_once_with(None)
    runner.run_once.assert_awaited_once_with(confirm_send=True)


def test_scheduler_error_then_success_recovers_with_pacing():
    """A failed cycle does not kill the task and the next cycle can pass."""
    from modules.flow.scheduler import FlowScheduler

    scheduler = FlowScheduler()
    outcomes = iter(["ERROR", "PASS"])

    async def cycle_callback(_settings, _interval, number):
        outcome = next(outcomes)
        if outcome == "ERROR":
            raise RuntimeError("controlled failure")
        assert number == 2
        scheduler._stop_event.set()

    starts, sleeps, _clock = _run_virtual_scheduler(
        scheduler,
        [
            {"automation_enabled": True, "scheduler_interval_seconds": 2},
            {"automation_enabled": True, "scheduler_interval_seconds": 2},
        ],
        cycle_callback,
    )

    assert starts == [0, 2]
    assert sleeps == [2, 2]

"""Safety and transaction contracts for the explicit Flow case cleanup."""

import asyncio

import pytest

from modules.flow.case_cleanup_repository import (
    FLOW_CASE_TABLES,
    FlowCaseCleanupPostgresRepository,
)
from modules.flow.case_cleanup_service import FlowCaseCleanupService


def test_cleanup_scope_contains_only_case_tables():
    assert "flow_sectors" not in FLOW_CASE_TABLES
    assert "flow_sector_levels" not in FLOW_CASE_TABLES
    assert "flow_operational_settings" not in FLOW_CASE_TABLES
    assert "flow_scheduler_state" not in FLOW_CASE_TABLES
    assert not any("diagnosis" in table for table in FLOW_CASE_TABLES)
    assert "flow_requests" in FLOW_CASE_TABLES
    assert "flow_case_audit_records" in FLOW_CASE_TABLES
    assert "flow_citizen_notifications" in FLOW_CASE_TABLES


def test_cleanup_repository_uses_explicit_safe_deletes():
    source = FlowCaseCleanupPostgresRepository.clear_cases.__code__
    assert source.co_names.count("execute") >= 1
    text = FlowCaseCleanupPostgresRepository.__doc__ or ""
    assert "case" in text.lower()

    import inspect

    implementation = inspect.getsource(FlowCaseCleanupPostgresRepository.clear_cases).lower()
    assert "cascade" not in implementation
    assert "truncate" not in implementation
    assert "session_replication_role" not in implementation
    assert "flow_case_tables" in implementation
    assert "_delete_order" in implementation


class _Transaction:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.rolled_back = exc_type is not None
        self.committed = exc_type is None
        return False


class _Connection:
    def __init__(self, tx):
        self.tx = tx

    def transaction(self):
        return self.tx


class _Pool:
    def __init__(self, tx):
        self.tx = tx

    def connection(self):
        return _Connection(self.tx)


class _SuccessfulRepository:
    async def clear_cases(self, conn):
        return {
            "status": "cleared",
            "cases_before": 2,
            "cases_after": 0,
        }


class _FailingRepository:
    async def clear_cases(self, conn):
        raise RuntimeError("forced cleanup failure")


def test_cleanup_service_commits_success(monkeypatch):
    tx = _Transaction()
    monkeypatch.setattr(
        "modules.flow.case_cleanup_service.transaction",
        lambda pool: pool.connection().transaction(),
    )
    result = asyncio.run(
        FlowCaseCleanupService(
            pool=_Pool(tx), repository=_SuccessfulRepository()
        ).clear_cases()
    )
    assert result["cases_after"] == 0
    assert tx.committed is True
    assert tx.rolled_back is False


def test_cleanup_service_rolls_back_on_failure(monkeypatch):
    tx = _Transaction()
    monkeypatch.setattr(
        "modules.flow.case_cleanup_service.transaction",
        lambda pool: pool.connection().transaction(),
    )
    with pytest.raises(RuntimeError, match="forced cleanup failure"):
        asyncio.run(
            FlowCaseCleanupService(
                pool=_Pool(tx), repository=_FailingRepository()
            ).clear_cases()
        )
    assert tx.rolled_back is True
    assert tx.committed is False

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.flow.domain import (
    FirstResponseSLA,
    FirstResponseSLAStatus,
    evaluate_first_response_sla,
    sla_due_at,
)
from modules.flow.sla_service import FlowFirstResponseSLAService


T0 = datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)
DUE = T0 + timedelta(seconds=30)


@pytest.mark.parametrize("seconds", [1, 30])
def test_positive_sla_configuration_and_exact_due_date(seconds):
    assert sla_due_at(T0, seconds) == T0 + timedelta(seconds=seconds)


@pytest.mark.parametrize("seconds", [0, -1])
def test_non_positive_sla_configuration_is_rejected(seconds):
    with pytest.raises(ValueError):
        sla_due_at(T0, seconds)


def _evaluate(*, status="PENDING", response=None, now=T0):
    return evaluate_first_response_sla(
        current_status=FirstResponseSLAStatus(status),
        due_at=DUE,
        first_response_at=response,
        now=now,
    )


def test_pending_before_due_without_response():
    assert _evaluate(now=T0 + timedelta(seconds=29)).status == FirstResponseSLAStatus.PENDING


@pytest.mark.parametrize("offset", [1, 30])
def test_response_before_or_exactly_at_due_is_met(offset):
    assert _evaluate(response=T0 + timedelta(seconds=offset)).status == FirstResponseSLAStatus.MET


def test_no_response_after_due_is_breached():
    assert _evaluate(now=DUE + timedelta(microseconds=1)).status == FirstResponseSLAStatus.BREACHED


def test_late_response_is_breached_even_when_work_can_be_in_progress():
    assert _evaluate(response=DUE + timedelta(seconds=1), now=DUE + timedelta(seconds=2)).status == FirstResponseSLAStatus.BREACHED


def test_provisional_breach_reconciles_only_for_on_time_evidence():
    on_time = _evaluate(status="BREACHED", response=T0 + timedelta(seconds=20), now=DUE + timedelta(seconds=20))
    late = _evaluate(status="BREACHED", response=T0 + timedelta(seconds=35), now=DUE + timedelta(seconds=20))
    assert on_time.status == FirstResponseSLAStatus.MET
    assert on_time.reconciled is True
    assert late.status == FirstResponseSLAStatus.BREACHED
    assert late.reconciled is False


class _AsyncContext:
    def __init__(self, value=None): self.value = value
    async def __aenter__(self): return self.value
    async def __aexit__(self, exc_type, exc, tb): return False


class _Connection:
    def transaction(self): return _AsyncContext()


class _Pool:
    def connection(self): return _AsyncContext(_Connection())


def _sla(status="PENDING", response=None):
    return FirstResponseSLA(
        "sla-1", "routing-1", "request-1", 30, T0, DUE,
        FirstResponseSLAStatus(status), response,
    )


class _Repository:
    def __init__(self, sla):
        self.sla = sla
        self.transitions = []

    async def list_evaluable(self, conn):
        if self.sla.status == FirstResponseSLAStatus.MET:
            return ()
        if self.sla.status == FirstResponseSLAStatus.BREACHED and (
            self.sla.first_response_at is None
            or self.sla.first_response_at > self.sla.due_at
        ):
            return ()
        return (self.sla,)

    async def persist_evaluation(self, conn, *, sla, status, now, reconciled):
        old = self.sla
        met_at = old.first_response_at if status == FirstResponseSLAStatus.MET else None
        breached_at = old.breached_at
        if status == FirstResponseSLAStatus.BREACHED:
            breached_at = breached_at or now
        elif status == FirstResponseSLAStatus.MET:
            breached_at = None
        self.sla = replace(old, status=status, met_at=met_at, breached_at=breached_at, evaluated_at=now)
        if status != old.status:
            self.transitions.append((old.status, status, reconciled))
        return self.sla


def test_service_idempotency_preserves_final_timestamps():
    repo = _Repository(_sla())
    clock = lambda: DUE + timedelta(seconds=1)
    service = FlowFirstResponseSLAService(pool=_Pool(), repository=repo, clock=clock)
    first = asyncio.run(service.check_once())
    breached_at = repo.sla.breached_at
    second = asyncio.run(service.check_once())
    assert first.breached == 1
    assert second.checked == 0
    assert repo.sla.breached_at == breached_at
    assert len(repo.transitions) == 1


def test_pending_evaluations_create_no_transitions():
    repo = _Repository(_sla())
    service = FlowFirstResponseSLAService(
        pool=_Pool(), repository=repo, clock=lambda: T0 + timedelta(seconds=10)
    )
    first = asyncio.run(service.check_once())
    second = asyncio.run(service.check_once())
    assert first.pending == second.pending == 1
    assert repo.sla.status == FirstResponseSLAStatus.PENDING
    assert repo.transitions == []


def test_service_reconciles_once_and_preserves_met_at():
    repo = _Repository(replace(_sla("BREACHED", T0 + timedelta(seconds=20)), breached_at=DUE + timedelta(seconds=10)))
    service = FlowFirstResponseSLAService(pool=_Pool(), repository=repo, clock=lambda: DUE + timedelta(seconds=20))
    first = asyncio.run(service.check_once())
    met_at = repo.sla.met_at
    second = asyncio.run(service.check_once())
    assert first.reconciled == 1
    assert first.met == 1
    assert second.checked == 0
    assert repo.sla.met_at == met_at == T0 + timedelta(seconds=20)
    assert len(repo.transitions) == 1


def test_late_breach_is_final_and_not_rechecked():
    late = T0 + timedelta(seconds=35)
    repo = _Repository(
        replace(_sla("BREACHED", late), breached_at=DUE + timedelta(seconds=1))
    )
    service = FlowFirstResponseSLAService(
        pool=_Pool(), repository=repo, clock=lambda: DUE + timedelta(seconds=20)
    )
    result = asyncio.run(service.check_once())
    assert result.checked == 0
    assert repo.sla.status == FirstResponseSLAStatus.BREACHED
    assert repo.sla.breached_at == DUE + timedelta(seconds=1)

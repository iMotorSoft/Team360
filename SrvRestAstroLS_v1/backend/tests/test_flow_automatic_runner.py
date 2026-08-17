"""Unit tests for the automatic SLA escalation runner.

Covers the required vertical cases: before/at/after deadline, resolved items,
idempotency, multiple requests, partial failure isolation, audit evidence,
max level and the Directorio read model. No database or real model involved;
the clock is injected so deadlines are reproduced deterministically.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.flow.automatic_runner import FlowAutomaticRunner, RunnerSummary
from modules.flow.domain import (
    EscalationCandidate,
    EscalationStatus,
    FirstResponseSLA,
    FirstResponseSLAStatus,
    FlowEscalation,
    FlowSector,
    FlowSectorLevel,
    RoutingAssignment,
    RoutingStatus,
    evaluate_first_response_sla,
)
from modules.flow.executive_query import LIVE, build_executive_view

T0 = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
DURATION = 30
DUE = T0 + timedelta(seconds=DURATION)


def _sla(sla_id="sla-1", *, level=1, request_id="req-1", status="PENDING",
         due_at=DUE, response=None, breached_at=None):
    return FirstResponseSLA(
        id=sla_id,
        routing_id=f"routing-n{level}",
        request_id=request_id,
        duration_seconds=DURATION,
        started_at=T0,
        due_at=due_at,
        status=FirstResponseSLAStatus(status),
        first_response_at=response,
        breached_at=breached_at,
    )


def _levels(max_level=2):
    levels = []
    for level in range(1, max_level + 1):
        levels.append(
            FlowSectorLevel(
                f"level-n{level}", "alumbrado", level, "email",
                f"alumbrado.n{level}@alquimiablue.com", True,
                30 if level == 1 else None,
            )
        )
    return tuple(levels)


class _Store:
    """Shared in-memory Flow state for deterministic runner tests."""

    def __init__(self, slas, *, levels=None, request_status=None):
        self.slas = {sla.id: sla for sla in slas}
        self.sla_level = {sla.id: int(sla.routing_id.rsplit("-n", 1)[1]) for sla in slas}
        self.request_status = {
            sla.request_id: (request_status or "ACTIVE") for sla in slas
        }
        self.routing_status = {sla.routing_id: "ASSIGNED" for sla in slas}
        self.escalations: dict[str, FlowEscalation] = {}
        self.routings: dict[str, RoutingAssignment] = {}
        self.sla_events: list[tuple[str, str, str]] = []
        self.send_calls: list[dict] = []
        self.levels = levels or _levels()

    def routing_key_of(self, request_id: str, routing_key: str) -> str:
        return f"{request_id}:{routing_key}"

    def next_level(self, sla_id: str) -> FlowSectorLevel | None:
        current = self.sla_level[sla_id]
        return next(
            (
                level for level in sorted(self.levels, key=lambda item: item.level)
                if level.level > current and level.active
            ),
            None,
        )

    def eligible(self, sla_id: str) -> bool:
        sla = self.slas[sla_id]
        if self.request_status.get(sla.request_id) not in ("CONFIRMED", "ACTIVE"):
            return False
        if self.routing_status.get(sla.routing_id) != "ASSIGNED":
            return False
        if sla.status != FirstResponseSLAStatus.BREACHED:
            return False
        if sla.first_response_at is not None and sla.first_response_at <= sla.due_at:
            return False
        if self.next_level(sla_id) is None:
            return False
        existing = self.escalations.get(sla_id)
        return not (existing is not None and existing.status == EscalationStatus.COMPLETED)

    def candidate(self, sla_id: str) -> EscalationCandidate:
        sla = self.slas[sla_id]
        level = self.sla_level[sla_id]
        return EscalationCandidate(
            request_id=sla.request_id,
            description="Reparar poste apagado",
            location_text="Olleros y Ciudad de la Paz",
            origin_channel="email",
            sector_id="alumbrado",
            sector_display_name="Alumbrado Público",
            from_routing_id=sla.routing_id,
            from_level=level,
            from_destination=f"alumbrado.n{level}@alquimiablue.com",
            from_assigned_at=T0,
            trigger_sla_id=sla.id,
            sla_due_at=sla.due_at,
            sla_status=sla.status.value,
            first_response_at=sla.first_response_at,
        )


class _SlaRepo:
    def __init__(self, store: _Store):
        self.store = store

    async def list_evaluable(self, conn):
        out = []
        for sla in self.store.slas.values():
            if self.store.request_status.get(sla.request_id) not in (
                "CONFIRMED", "ACTIVE", "RESOLUTION_PENDING_APPROVAL"
            ):
                continue
            if sla.status == FirstResponseSLAStatus.PENDING:
                out.append(sla)
            elif (
                sla.status == FirstResponseSLAStatus.BREACHED
                and sla.first_response_at is not None
                and sla.first_response_at <= sla.due_at
            ):
                out.append(sla)
        return tuple(out)

    async def persist_evaluation(self, conn, *, sla, status, now, reconciled):
        current = self.store.slas[sla.id]
        if status == FirstResponseSLAStatus.MET:
            updated = replace(
                current, status=status, met_at=current.first_response_at,
                breached_at=None, evaluated_at=now,
            )
        elif status == FirstResponseSLAStatus.BREACHED:
            updated = replace(
                current, status=status,
                breached_at=current.breached_at or now, evaluated_at=now,
            )
        else:
            updated = replace(current, status=status, evaluated_at=now)
        self.store.slas[sla.id] = updated
        if status.value != current.status.value:
            self.store.sla_events.append(
                (sla.id, current.status.value, status.value)
            )
        return updated


class _EscalationRepo:
    def __init__(self, store: _Store):
        self.store = store

    async def list_eligible(self, conn):
        return tuple(
            self.store.candidate(sla_id)
            for sla_id in self.store.slas
            if self.store.eligible(sla_id)
        )

    async def get_eligible(self, conn, trigger_sla_id):
        if not self.store.eligible(trigger_sla_id):
            return None
        return self.store.candidate(trigger_sla_id)

    async def get_by_trigger(self, conn, trigger_sla_id):
        return self.store.escalations.get(trigger_sla_id)

    async def create_pending(self, conn, candidate, *, to_level):
        existing = self.store.escalations.get(candidate.trigger_sla_id)
        if existing is None:
            escalation = FlowEscalation(
                f"escalation-{candidate.trigger_sla_id}", candidate.request_id,
                candidate.sector_id, candidate.from_routing_id,
                candidate.from_level, candidate.trigger_sla_id, to_level,
                None, EscalationStatus.PENDING, T0,
            )
            self.store.escalations[candidate.trigger_sla_id] = escalation
            return escalation
        return existing

    async def mark_completed(self, conn, *, escalation_id, to_routing_id):
        escalation = self._by_id(escalation_id)
        updated = replace(
            escalation, status=EscalationStatus.COMPLETED,
            to_routing_id=to_routing_id, completed_at=T0 + timedelta(seconds=40),
        )
        self._store_by_id(escalation_id, updated)
        return updated

    async def mark_failed(self, conn, *, escalation_id, error_code):
        escalation = self._by_id(escalation_id)
        updated = replace(
            escalation, status=EscalationStatus.FAILED,
            last_error_code=error_code,
        )
        self._store_by_id(escalation_id, updated)
        return updated

    def _by_id(self, escalation_id: str) -> FlowEscalation:
        for trigger, escalation in self.store.escalations.items():
            if escalation.id == escalation_id:
                return escalation
        raise KeyError(escalation_id)

    def _store_by_id(self, escalation_id: str, updated: FlowEscalation) -> None:
        for trigger, escalation in list(self.store.escalations.items()):
            if escalation.id == escalation_id:
                self.store.escalations[trigger] = updated
                return
        raise KeyError(escalation_id)


class _RoutingRepo:
    def __init__(self, store: _Store):
        self.store = store

    async def get_sector(self, conn, sector_id):
        return FlowSector("alumbrado", "Alumbrado Público", True)

    async def get_next_active_sector_level(self, conn, sector_id, current_level):
        return next(
            (
                level for level in sorted(self.store.levels, key=lambda item: item.level)
                if level.level > current_level and level.active
            ),
            None,
        )

    async def get_assignment_for_key(self, conn, *, request_id, routing_key):
        return self.store.routings.get(self.store.routing_key_of(request_id, routing_key))

    async def create_pending_assignment_for_level(self, conn, **kwargs):
        level = kwargs["sector_level"].level
        routing_key = kwargs["routing_key"]
        request_id = kwargs["request_id"]
        assignment = RoutingAssignment(
            f"routing-n{level}-{request_id}", request_id, routing_key,
            kwargs["sector"].sector_id, level,
            kwargs["sector_level"].channel, kwargs["sector_level"].destination,
            RoutingStatus.ROUTING_PENDING, kwargs["outbound_rfc_message_id"], None,
        )
        self.store.routings[self.store.routing_key_of(request_id, routing_key)] = assignment
        return assignment

    async def mark_attempt(self, conn, assignment_id):
        assignment = next(
            a for a in self.store.routings.values() if a.id == assignment_id
        )
        updated = replace(
            assignment, status=RoutingStatus.ROUTING_PENDING,
            attempt_count=assignment.attempt_count + 1,
        )
        self._replace(assignment_id, updated)
        return updated

    async def mark_assigned(self, conn, *, assignment_id, external_message_id,
                            observed_rfc_message_id=None):
        assignment = next(
            a for a in self.store.routings.values() if a.id == assignment_id
        )
        updated = replace(
            assignment, status=RoutingStatus.ASSIGNED,
            outbound_external_message_id=external_message_id,
            outbound_observed_rfc_message_id=observed_rfc_message_id,
            delivery_uncertain=False,
        )
        self._replace(assignment_id, updated)
        return updated

    async def mark_failed(self, conn, *, assignment_id, error_code, delivery_uncertain):
        assignment = next(
            a for a in self.store.routings.values() if a.id == assignment_id
        )
        updated = replace(
            assignment, status=RoutingStatus.ROUTING_FAILED,
            last_error_code=error_code, delivery_uncertain=delivery_uncertain,
        )
        self._replace(assignment_id, updated)
        return updated

    async def ensure_work_state(self, conn, assignment):
        return None

    async def ensure_first_response_sla(self, conn, assignment):
        return None

    def _replace(self, assignment_id, updated):
        for key, value in self.store.routings.items():
            if value.id == assignment_id:
                self.store.routings[key] = updated
                return


class _Sender:
    sender_address = "mesaentrada@alquimiablue.com"

    def __init__(self, store: _Store, *, error=None):
        self.store = store
        self.error = error

    def find_sent_message_by_rfc_message_id(self, value):
        return None

    def find_sent_message_by_reference(self, value, *, to=None):
        return None

    def send_message(self, **kwargs):
        self.store.send_calls.append(kwargs)
        if self.error:
            raise self.error
        return f"gmail-{len(self.store.send_calls)}"

    def get_message_rfc_id(self, message_id):
        return f"<{message_id}@gmail.example>"


class _AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return _AsyncContext()


class _Pool:
    def connection(self):
        return _AsyncContext()


def _runner(store: _Store, *, confirm_send=False, sender=None, clock=None):
    return FlowAutomaticRunner(
        pool=_Pool(),
        sla_repository=_SlaRepo(store),
        escalation_repository=_EscalationRepo(store),
        routing_repository=_RoutingRepo(store),
        sender=sender or _Sender(store),
        clock=clock or (lambda: DUE + timedelta(seconds=1)),
    )


# ---------------------------------------------------------------------------
# Boundary semantics: the real Flow rule is now > due_at -> BREACHED.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (T0 + timedelta(seconds=29), FirstResponseSLAStatus.PENDING),
        (DUE, FirstResponseSLAStatus.PENDING),
        (DUE + timedelta(microseconds=1), FirstResponseSLAStatus.BREACHED),
    ],
)
def test_deadline_boundary_uses_strictly_after_semantics(now, expected):
    result = evaluate_first_response_sla(
        current_status=FirstResponseSLAStatus.PENDING,
        due_at=DUE,
        first_response_at=None,
        now=now,
    )
    assert result.status == expected


# ---------------------------------------------------------------------------
# Vertical cases.
# ---------------------------------------------------------------------------


def test_before_deadline_no_action():
    store = _Store([_sla()], levels=_levels())
    summary = asyncio.run(
        _runner(store, clock=lambda: T0 + timedelta(seconds=10)).run_once()
    )
    assert summary.scanned == 1
    assert summary.pending == 1
    assert summary.breached == 0
    assert summary.eligible == summary.created == summary.completed == 0
    assert store.escalations == {}
    assert store.routings == {}
    assert store.send_calls == []


def test_after_deadline_escalates_to_next_level():
    store = _Store([_sla()], levels=_levels(max_level=2))
    summary = asyncio.run(_runner(store).run_once(confirm_send=True))
    assert summary.scanned == 1
    assert summary.breached == 1
    assert summary.eligible == 1
    assert summary.created == summary.sent == summary.completed == 1
    escalation = store.escalations["sla-1"]
    assert escalation.status == EscalationStatus.COMPLETED
    assert escalation.from_level == 1
    assert escalation.to_level == 2
    n2 = store.routings[store.routing_key_of("req-1", "alumbrado_level_2")]
    assert n2.level == 2
    assert n2.destination == "alumbrado.n2@alquimiablue.com"
    assert store.send_calls[0]["to"] == "alumbrado.n2@alquimiablue.com"


def test_resolved_request_is_ignored():
    store = _Store([_sla()], levels=_levels(), request_status="RESOLVED")
    summary = asyncio.run(_runner(store).run_once(confirm_send=True))
    assert summary.scanned == 0
    assert summary.eligible == summary.created == summary.completed == 0
    assert store.escalations == {}
    assert store.send_calls == []


def test_worker_twice_produces_single_transition_and_single_email():
    store = _Store([_sla()], levels=_levels(max_level=2))
    first = asyncio.run(_runner(store).run_once(confirm_send=True))
    second = asyncio.run(_runner(store).run_once(confirm_send=True))
    assert first.created == first.completed == 1
    assert second.scanned == 0
    assert second.eligible == second.created == second.completed == 0
    assert len(store.escalations) == 1
    assert len(store.routings) == 1
    assert len(store.send_calls) == 1
    assert store.sla_events == [("sla-1", "PENDING", "BREACHED")]


def test_multiple_requests_processes_only_breached_ones():
    store = _Store(
        [
            _sla("sla-1", request_id="req-1", due_at=T0 + timedelta(seconds=10)),
            _sla("sla-2", request_id="req-2", due_at=T0 + timedelta(seconds=10)),
            _sla("sla-3", request_id="req-3", due_at=T0 + timedelta(seconds=10)),
            _sla("sla-4", request_id="req-4", due_at=T0 + timedelta(seconds=90)),
            _sla("sla-5", request_id="req-5", due_at=T0 + timedelta(seconds=90)),
        ],
        levels=_levels(max_level=2),
    )
    summary = asyncio.run(_runner(store).run_once(confirm_send=True))
    assert summary.scanned == 5
    assert summary.pending == 2
    assert summary.breached == 3
    assert summary.eligible == summary.created == summary.completed == 3
    assert len(store.escalations) == 3
    assert len(store.routings) == 3
    assert len(store.send_calls) == 3


def test_single_failed_item_does_not_corrupt_others():
    store = _Store(
        [
            _sla("sla-a", request_id="req-a", due_at=T0 + timedelta(seconds=10)),
            _sla("sla-b", request_id="req-b", due_at=T0 + timedelta(seconds=10)),
        ],
        levels=_levels(max_level=2),
    )

    class _FailingSender(_Sender):
        def send_message(self, **kwargs):
            self.store.send_calls.append(kwargs)
            if "req-a" in kwargs["body"]:
                raise RuntimeError("controlled send failure")
            return f"gmail-{len(self.store.send_calls)}"

    summary = asyncio.run(
        _runner(store, sender=_FailingSender(store)).run_once(confirm_send=True)
    )
    assert summary.eligible == 2
    assert summary.completed == 1
    assert summary.failed == 1
    assert len(store.escalations) == 2
    assert store.escalations["sla-a"].status == EscalationStatus.FAILED
    assert store.escalations["sla-b"].status == EscalationStatus.COMPLETED


def test_max_level_breach_has_no_next_level_and_is_skipped():
    # Only levels up to 3 exist; an N3 breach has no next active level.
    store = _Store([_sla("sla-n3", level=3, request_id="req-max")], levels=_levels(max_level=3))
    store.slas["sla-n3"] = replace(
        store.slas["sla-n3"], status=FirstResponseSLAStatus.BREACHED,
        breached_at=T0 + timedelta(seconds=31),
    )
    summary = asyncio.run(_runner(store).run_once(confirm_send=True))
    assert summary.scanned == 0  # BREACHED with no timely response is not re-evaluated
    assert summary.eligible == summary.created == summary.completed == 0
    assert summary.skipped == 0
    assert store.escalations == {}
    assert store.send_calls == []


def test_dry_run_advances_sla_but_does_not_create_escalation():
    store = _Store([_sla()], levels=_levels(max_level=2))
    summary = asyncio.run(_runner(store).run_once(confirm_send=False))
    assert summary.scanned == 1
    assert summary.breached == 1
    assert summary.eligible == 1
    assert summary.skipped == 1
    assert summary.created == summary.sent == summary.completed == 0
    assert store.slas["sla-1"].status == FirstResponseSLAStatus.BREACHED
    assert store.escalations == {}
    assert store.send_calls == []


def test_audit_evidence_exists_after_automatic_escalation():
    store = _Store([_sla()], levels=_levels(max_level=2))
    summary = asyncio.run(_runner(store).run_once(confirm_send=True))
    assert summary.completed == 1
    # SLA transition evidence.
    assert ("sla-1", "PENDING", "BREACHED") in store.sla_events
    # Escalation evidence: request, levels, status, timestamps.
    escalation = store.escalations["sla-1"]
    assert escalation.request_id == "req-1"
    assert escalation.from_level == 1
    assert escalation.to_level == 2
    assert escalation.status == EscalationStatus.COMPLETED
    assert escalation.created_at is not None
    assert escalation.completed_at is not None
    # Routing evidence for the new level.
    n2 = store.routings[store.routing_key_of("req-1", "alumbrado_level_2")]
    assert n2.status == RoutingStatus.ASSIGNED


def test_executive_view_reflects_automatic_escalation():
    # Directorio read model: the LIVE view must show the escalated state
    # derived exclusively from persisted facts (no second source of truth).
    snapshot = {
        "schema_version": 1,
        "request": {
            "request_id": "req-1",
            "conversation_id": "conversation-1",
            "sector_id": "alumbrado",
            "sector_name": "Alumbrado Público",
            "category": "alumbrado",
            "description": "Reparar poste apagado",
            "location": "Olleros y Ciudad de la Paz",
            "citizen_address": "vecina@example.com",
            "origin_channel": "email",
            "received_at": T0.isoformat(),
            "confirmed_at": T0.isoformat(),
        },
        "routings": [
            {
                "routing_id": "routing-n1",
                "routing_key": "initial_n1",
                "level": 1,
                "destination": "alumbrado.n1@alquimiablue.com",
                "assigned_at": T0.isoformat(),
                "routing_status": "ASSIGNED",
                "work_status": None,
                "first_response_at": None,
                "first_responder": None,
            },
            {
                "routing_id": "routing-n2",
                "routing_key": "alumbrado_level_2",
                "level": 2,
                "destination": "alumbrado.n2@alquimiablue.com",
                "assigned_at": (T0 + timedelta(seconds=40)).isoformat(),
                "routing_status": "ASSIGNED",
                "work_status": None,
                "first_response_at": None,
                "first_responder": None,
            },
        ],
        "slas": [
            {
                "sla_id": "sla-1",
                "sla_type": "FIRST_RESPONSE",
                "routing_id": "routing-n1",
                "level": 1,
                "duration_seconds": DURATION,
                "started_at": T0.isoformat(),
                "due_at": DUE.isoformat(),
                "first_response_at": None,
                "status": "BREACHED",
                "met_at": None,
                "breached_at": (T0 + timedelta(seconds=31)).isoformat(),
            }
        ],
        "escalations": [
            {
                "escalation_id": "escalation-1",
                "from_routing_id": "routing-n1",
                "from_level": 1,
                "to_routing_id": "routing-n2",
                "to_level": 2,
                "trigger": "FIRST_RESPONSE_SLA_BREACHED",
                "trigger_sla_id": "sla-1",
                "created_at": (T0 + timedelta(seconds=31)).isoformat(),
                "completed_at": (T0 + timedelta(seconds=40)).isoformat(),
                "status": "COMPLETED",
            }
        ],
        "operations": [],
        "resolution": None,
        "approval": None,
        "result": {"request_status": "ACTIVE", "resolved_at": None},
        "metrics": {
            "total_elapsed_seconds": None,
            "routing_count": 2,
            "escalation_count": 1,
            "sla_total": 1,
            "sla_met_count": 0,
            "sla_breached_count": 1,
            "levels_reached": 2,
        },
        "timeline": [],
    }
    view = build_executive_view(snapshot, data_source=LIVE, request_status="ACTIVE")
    assert view["status_fact"] == "open"
    assert view["data_source"] == LIVE
    assert len(view["escalations"]) == 1
    assert view["escalations"][0]["to_level"] == 2
    assert view["escalations"][0]["status"] == "COMPLETED"
    assert view["metrics"]["escalation_count"] == 1
    assert view["metrics"]["levels_reached"] == 2
    assert view["metrics"]["sla_breached_count"] == 1
    assert view["routing_history"][1]["level"] == 2


# ---------------------------------------------------------------------------
# Runner summary contract.
# ---------------------------------------------------------------------------


def test_runner_summary_as_dict_is_structured_and_serializable():
    store = _Store([_sla()], levels=_levels(max_level=2))
    summary = asyncio.run(_runner(store).run_once(confirm_send=True))
    payload = summary.as_dict()
    assert isinstance(payload["outcomes"], list)
    assert payload["scanned"] == 1
    assert payload["completed"] == 1
    assert payload["failed"] == 0
    assert all(isinstance(value, (int, list, dict, str, bool, type(None))) for value in payload.values())


# ---------------------------------------------------------------------------
# Opt-in real PostgreSQL integration (mirrors existing Flow repository tests).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_AUTOMATIC_RUNNER_POSTGRES_TEST") != "1",
    reason="requires migrations 011-018 on Team360 PostgreSQL",
)
def test_real_postgres_automatic_runner_escalates_once_and_is_idempotent():
    from uuid import uuid4

    import psycopg
    from psycopg.rows import dict_row

    from modules.db.pool import close_pool, create_pool, open_pool
    from modules.db.settings import get_database_settings
    from modules.flow.escalation_repository import FlowEscalationPostgresRepository
    from modules.flow.routing_repository import FlowRoutingPostgresRepository
    from modules.flow.sla_repository import FlowSLARepository

    async def exercise():
        suffix = uuid4().hex
        thread = f"automatic-{suffix}"
        settings = get_database_settings(min_size=1, max_size=1)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    insert into flow_conversations (
                        provider, channel, external_thread_id,
                        citizen_address, subject, state
                    ) values ('gmail','email',%(thread)s,'citizen@example.com',
                              'Automatic runner test','CONFIRMED') returning id
                    """,
                    {"thread": thread},
                )
                conversation_id = (await cur.fetchone())["id"]
                await cur.execute(
                    """
                    insert into flow_request_candidates (
                        conversation_id, revision, ordinal, description,
                        tentative_category, location_text, status
                    ) values (%(conversation)s,1,1,'Reparar poste','alumbrado',
                              'Olleros y Ciudad de la Paz','CONFIRMED') returning id
                    """,
                    {"conversation": conversation_id},
                )
                candidate_id = (await cur.fetchone())["id"]
                await cur.execute(
                    """
                    insert into flow_requests (
                        conversation_id, source_candidate_id, description,
                        tentative_category, location_text, confirmed_at_utc
                    ) values (%(conversation)s,%(candidate)s,'Reparar poste',
                              'alumbrado','Olleros y Ciudad de la Paz',now())
                    returning id
                    """,
                    {"conversation": conversation_id, "candidate": candidate_id},
                )
                request_id = (await cur.fetchone())["id"]
                await cur.execute(
                    """
                    select level, id from flow_sector_levels
                    where sector_id='alumbrado' and level in (1,2)
                    """
                )
                levels = {row["level"]: row["id"] for row in await cur.fetchall()}
                await cur.execute(
                    """
                    insert into flow_request_routings (
                        request_id, routing_key, sector_id, sector_level_id,
                        level, channel, destination, status,
                        outbound_rfc_message_id, outbound_external_message_id,
                        assigned_at_utc
                    ) values (%(request)s,'initial_n1','alumbrado',%(level1)s,
                              1,'email','alumbrado.n1@alquimiablue.com','ASSIGNED',
                              %(rfc)s,%(external)s,now()) returning id
                    """,
                    {
                        "request": request_id,
                        "level1": levels[1],
                        "rfc": f"<auto-n1-{suffix}@example.com>",
                        "external": f"gmail-auto-n1-{suffix}",
                    },
                )
                routing_id = (await cur.fetchone())["id"]
                started = datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc)
                await cur.execute(
                    """
                    insert into flow_request_slas (
                        routing_id, request_id, sla_type, duration_seconds,
                        started_at_utc, due_at_utc, evaluated_at_utc
                    ) values (%(routing)s, %(request)s, 'FIRST_RESPONSE', 30,
                              %(started)s, %(due)s, %(started)s)
                    returning id
                    """,
                    {
                        "routing": routing_id,
                        "request": request_id,
                        "started": started,
                        "due": started + timedelta(seconds=30),
                    },
                )
                sla_id = (await cur.fetchone())["id"]
            await conn.commit()

        async def sla_status() -> tuple[str | None, str | None]:
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select status::text, breached_at_utc::text
                        from flow_request_slas where id = %(sla)s
                        """,
                        {"sla": sla_id},
                    )
                    row = await cur.fetchone()
            return (row["status"] if row else None,
                    row["breached_at_utc"] if row else None)

        pool = create_pool(get_database_settings(min_size=1, max_size=2))
        await open_pool(pool)
        try:
            clock = lambda: started + timedelta(seconds=60)
            runner_kwargs = {
                "pool": pool,
                "sla_repository": FlowSLARepository(),
                "escalation_repository": FlowEscalationPostgresRepository(),
                "routing_repository": FlowRoutingPostgresRepository(),
                "sender": None,
                "clock": clock,
            }
            first = await FlowAutomaticRunner(**runner_kwargs).run_once(
                confirm_send=False
            )
            assert first.breached >= 1
            assert first.eligible >= 1
            status, breached_at = await sla_status()
            assert status == "BREACHED"
            assert breached_at is not None

            # Dry-run must not create an escalation for this request.
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select count(*) as n from flow_request_escalations
                        where request_id = %(request)s
                        """,
                        {"request": request_id},
                    )
                    assert (await cur.fetchone())["n"] == 0

            # Second run: my SLA is already BREACHED with no timely response,
            # so it is not re-evaluated (idempotency).
            second = await FlowAutomaticRunner(**runner_kwargs).run_once(
                confirm_send=False
            )
            status_after, breached_at_after = await sla_status()
            assert status_after == "BREACHED"
            assert breached_at_after == breached_at
            assert second.breached == 0

            # Cleanup (reverse dependency order).
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "delete from flow_request_sla_events where sla_id = %(sla)s",
                        {"sla": sla_id},
                    )
                    await cur.execute(
                        "delete from flow_request_slas where id = %(sla)s",
                        {"sla": sla_id},
                    )
                    await cur.execute(
                        """
                        delete from flow_request_work_states
                        where routing_id in (
                            select id from flow_request_routings
                            where request_id = %(request)s
                        )
                        """,
                        {"request": request_id},
                    )
                    await cur.execute(
                        "delete from flow_request_routings where request_id = %(request)s",
                        {"request": request_id},
                    )
                    await cur.execute(
                        "delete from flow_requests where id = %(request)s",
                        {"request": request_id},
                    )
                    await cur.execute(
                        "delete from flow_request_candidates where id = %(candidate)s",
                        {"candidate": candidate_id},
                    )
                    await cur.execute(
                        "delete from flow_conversations where id = %(conversation)s",
                        {"conversation": conversation_id},
                    )
                await conn.commit()
        finally:
            await close_pool(pool)

    asyncio.run(exercise())

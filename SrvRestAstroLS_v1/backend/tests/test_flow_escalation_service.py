import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from modules.flow.domain import (
    EscalationCandidate,
    EscalationStatus,
    FlowEscalation,
    FlowSector,
    FlowSectorLevel,
    RoutingAssignment,
    RoutingStatus,
)
from modules.flow.escalation_service import FlowEscalationService, build_escalation_email


T0 = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)


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


def _candidate(first_response_at=None, sla_status="BREACHED"):
    return EscalationCandidate(
        request_id="11111111-1111-4111-8111-111111111111",
        description="Reparar poste apagado",
        location_text="Olleros y Ciudad de la Paz",
        origin_channel="email",
        sector_id="alumbrado",
        sector_display_name="Alumbrado Público",
        from_routing_id="routing-n1",
        from_level=1,
        from_destination="alumbrado.n1@alquimiablue.com",
        from_assigned_at=T0,
        trigger_sla_id="sla-n1",
        sla_due_at=T0 + timedelta(seconds=30),
        sla_status=sla_status,
        first_response_at=first_response_at,
    )


class _EscalationRepo:
    def __init__(self, candidate=None):
        self.candidate = _candidate() if candidate is None else candidate
        self.escalation = None
        self.create_calls = 0

    async def list_eligible(self, conn):
        if self.escalation and self.escalation.status == EscalationStatus.COMPLETED:
            return ()
        return (self.candidate,) if self._eligible() else ()

    async def get_eligible(self, conn, trigger_sla_id):
        return self.candidate if self._eligible() else None

    def _eligible(self):
        return bool(
            self.candidate
            and self.candidate.sla_status == "BREACHED"
            and (
                self.candidate.first_response_at is None
                or self.candidate.first_response_at > self.candidate.sla_due_at
            )
        )

    async def get_by_trigger(self, conn, trigger_sla_id):
        return self.escalation

    async def create_pending(self, conn, candidate):
        if self.escalation is None:
            self.create_calls += 1
            self.escalation = FlowEscalation(
                "escalation-1", candidate.request_id, candidate.sector_id,
                candidate.from_routing_id, 1, candidate.trigger_sla_id, 2,
                None, EscalationStatus.PENDING, T0,
            )
        return self.escalation

    async def mark_completed(self, conn, *, escalation_id, to_routing_id):
        self.escalation = replace(
            self.escalation, status=EscalationStatus.COMPLETED,
            to_routing_id=to_routing_id, completed_at=T0 + timedelta(seconds=40),
            last_error_code=None,
        )
        return self.escalation

    async def mark_failed(self, conn, *, escalation_id, error_code):
        self.escalation = replace(
            self.escalation, status=EscalationStatus.FAILED,
            last_error_code=error_code,
        )
        return self.escalation


class _RoutingRepo:
    def __init__(self, *, level_active=True, level_exists=True):
        self.sector = FlowSector("alumbrado", "Alumbrado Público", True)
        self.level = (
            FlowSectorLevel(
                "level-n2", "alumbrado", 2, "email",
                "alumbrado.n2@alquimiablue.com", level_active, None,
            )
            if level_exists else None
        )
        self.assignment = None
        self.sla_ensures = []

    async def get_sector(self, conn, sector_id):
        return self.sector

    async def get_sector_level(self, conn, sector_id, level):
        return self.level

    async def get_assignment_for_key(self, conn, *, request_id, routing_key):
        return self.assignment

    async def create_pending_assignment_for_level(self, conn, **kwargs):
        self.assignment = RoutingAssignment(
            "routing-n2", kwargs["request_id"], kwargs["routing_key"],
            kwargs["sector"].sector_id, kwargs["sector_level"].level,
            kwargs["sector_level"].channel, kwargs["sector_level"].destination,
            RoutingStatus.ROUTING_PENDING, kwargs["outbound_rfc_message_id"], None,
        )
        return self.assignment

    async def mark_attempt(self, conn, assignment_id):
        self.assignment = replace(
            self.assignment, status=RoutingStatus.ROUTING_PENDING,
            attempt_count=self.assignment.attempt_count + 1,
        )
        return self.assignment

    async def mark_assigned(self, conn, *, assignment_id, external_message_id, observed_rfc_message_id=None):
        self.assignment = replace(
            self.assignment, status=RoutingStatus.ASSIGNED,
            outbound_external_message_id=external_message_id,
            outbound_observed_rfc_message_id=observed_rfc_message_id,
            delivery_uncertain=False,
        )
        return self.assignment

    async def mark_failed(self, conn, *, assignment_id, error_code, delivery_uncertain):
        self.assignment = replace(
            self.assignment, status=RoutingStatus.ROUTING_FAILED,
            last_error_code=error_code, delivery_uncertain=delivery_uncertain,
        )
        return self.assignment

    async def ensure_work_state(self, conn, assignment):
        return None

    async def ensure_first_response_sla(self, conn, assignment):
        self.sla_ensures.append(assignment.id)


class _Sender:
    sender_address = "mesaentrada@alquimiablue.com"

    def __init__(self, error=None, recovered=None):
        self.error = error
        self.recovered = recovered
        self.send_calls = []

    def find_sent_message_by_rfc_message_id(self, value):
        return self.recovered

    def find_sent_message_by_reference(self, value, *, to=None):
        return None

    def send_message(self, **kwargs):
        self.send_calls.append(kwargs)
        if self.error:
            raise self.error
        return "gmail-n2"

    def get_message_rfc_id(self, message_id):
        return f"<{message_id}@gmail.example>"


def _service(escalation_repo, routing_repo, sender=None):
    return FlowEscalationService(
        pool=_Pool(), repository=escalation_repo,
        routing_repository=routing_repo, sender=sender,
    )


def test_breached_n1_sends_one_clear_n2_assignment_and_is_idempotent():
    escalations = _EscalationRepo()
    routings = _RoutingRepo()
    sender = _Sender()
    first = asyncio.run(_service(escalations, routings, sender).escalate_once(confirm_send=True))
    second = asyncio.run(_service(escalations, routings, sender).escalate_once(confirm_send=True))
    assert first.eligible == first.created == first.sent == first.completed == 1
    assert second.eligible == second.sent == second.created == 0
    assert len(sender.send_calls) == 1
    call = sender.send_calls[0]
    assert call["to"] == "alumbrado.n2@alquimiablue.com"
    assert "[ESCALADO]" in call["subject"]
    assert "[R:alumbrado_level_2]" in call["subject"]
    for expected in (
        escalations.candidate.request_id, "Nivel actual: 2", "Reparar poste apagado",
        "Olleros y Ciudad de la Paz", "SLA de primera respuesta de Nivel 1 vencido",
        "alumbrado.n1@alquimiablue.com", "Sin respuesta", "BREACHED",
    ):
        assert expected in call["body"]
    assert routings.assignment.level == 2
    assert routings.assignment.routing_key == "alumbrado_level_2"
    assert routings.sla_ensures == ["routing-n2"]


def test_dry_run_resolves_n2_without_creating_or_sending():
    escalations = _EscalationRepo()
    routings = _RoutingRepo()
    sender = _Sender()
    result = asyncio.run(
        _service(escalations, routings, sender).escalate_once(confirm_send=False)
    )
    assert result.eligible == 1
    assert result.created == result.sent == 0
    assert result.outcomes[0].status == "DRY_RUN"
    assert result.outcomes[0].destination == "alumbrado.n2@alquimiablue.com"
    assert escalations.escalation is None
    assert routings.assignment is None
    assert sender.send_calls == []


def test_met_pending_or_timely_reconciliable_sla_never_sends():
    for candidate in (
        _candidate(sla_status="MET"),
        _candidate(sla_status="PENDING"),
        _candidate(first_response_at=T0 + timedelta(seconds=20)),
    ):
        repo = _EscalationRepo(candidate=candidate)
        sender = _Sender()
        result = asyncio.run(_service(repo, _RoutingRepo(), sender).escalate_once(confirm_send=True))
        assert result.sent == 0
        assert sender.send_calls == []


def test_missing_or_inactive_n2_is_typed_and_does_not_send():
    for routing_repo in (_RoutingRepo(level_exists=False), _RoutingRepo(level_active=False)):
        sender = _Sender()
        result = asyncio.run(
            _service(_EscalationRepo(), routing_repo, sender).escalate_once(confirm_send=True)
        )
        assert result.outcomes[0].reason_code == "NEXT_LEVEL_UNAVAILABLE"
        assert sender.send_calls == []


def test_late_n1_response_is_reported_and_does_not_block_escalation():
    candidate = _candidate(first_response_at=T0 + timedelta(seconds=35))
    email = build_escalation_email(candidate, "alumbrado.n2@alquimiablue.com")
    assert candidate.first_response_at.isoformat() in email.body
    assert "Primera respuesta N1: Sin respuesta" not in email.body


def test_uncertain_gmail_failure_does_not_blindly_resend():
    escalations = _EscalationRepo()
    routings = _RoutingRepo()
    sender = _Sender(error=TimeoutError("uncertain"))
    first = asyncio.run(_service(escalations, routings, sender).escalate_once(confirm_send=True))
    sender.error = None
    second = asyncio.run(_service(escalations, routings, sender).escalate_once(confirm_send=True))
    assert first.failed == 1
    assert second.failed == 1
    assert second.created == 0
    assert second.outcomes[0].reason_code == "DELIVERY_UNCERTAIN_NOT_RECONCILED"
    assert len(sender.send_calls) == 1


def test_reconciliation_finds_accepted_n2_without_resending():
    escalations = _EscalationRepo()
    routings = _RoutingRepo()
    sender = _Sender(recovered="gmail-recovered")
    result = asyncio.run(_service(escalations, routings, sender).escalate_once(confirm_send=True))
    assert result.completed == 1
    assert result.outcomes[0].reconciled is True
    assert sender.send_calls == []
    assert routings.sla_ensures == ["routing-n2"]


def test_already_assigned_historical_n2_is_not_backfilled_with_sla():
    escalations = _EscalationRepo()
    routings = _RoutingRepo()
    routings.assignment = RoutingAssignment(
        "routing-n2", escalations.candidate.request_id, "alumbrado_level_2",
        "alumbrado", 2, "email", "alumbrado.n2@alquimiablue.com",
        RoutingStatus.ASSIGNED, "<n2@example.com>", "gmail-existing",
    )
    result = asyncio.run(
        _service(escalations, routings, _Sender()).escalate_once(confirm_send=True)
    )
    assert result.completed == 1
    assert result.outcomes[0].idempotent is True
    assert routings.sla_ensures == []

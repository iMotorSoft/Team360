import asyncio
from dataclasses import replace

import pytest

from modules.flow.domain import (
    ConfirmedFlowRequest,
    FlowRequestNotConfirmedError,
    FlowRequestNotFoundError,
    FlowSector,
    FlowSectorLevel,
    RoutingAssignment,
    RoutingStatus,
    resolve_sector_id,
)
from modules.flow.routing_service import FlowRoutingService


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def transaction(self):
        return _AsyncContext()


class _Pool:
    def connection(self):
        return _AsyncContext(_Connection())


def _request(*, status="CONFIRMED", category="alumbrado"):
    return ConfirmedFlowRequest(
        id="11111111-1111-4111-8111-111111111111",
        conversation_id="conversation-1",
        status=status,
        description="Reparar poste de luz apagado.",
        tentative_category=category,
        location_text="Olleros y Ciudad de la Paz",
        origin_channel="email",
        citizen_address="vecina@example.com",
        external_thread_id="gmail-thread-1",
    )


def _sector(active=True):
    return FlowSector("alumbrado", "Alumbrado Público", active)


def _level(active=True):
    return FlowSectorLevel(
        "level-1",
        "alumbrado",
        1,
        "email",
        "alumbrado.n1@alquimiablue.com",
        active,
    )


_DEFAULT = object()


class _Repository:
    def __init__(self, request=_DEFAULT, sector=_DEFAULT, level=_DEFAULT):
        self.request = _request() if request is _DEFAULT else request
        self.sector = _sector() if sector is _DEFAULT else sector
        self.level = _level() if level is _DEFAULT else level
        self.assignment = None
        self.create_calls = 0

    async def get_request(self, conn, request_id):
        return self.request

    async def get_assignment(self, conn, request_id):
        return self.assignment

    async def get_sector(self, conn, sector_id):
        return self.sector

    async def get_sector_level(self, conn, sector_id, level):
        return self.level

    async def create_pending_assignment(
        self, conn, *, request_id, sector, sector_level, outbound_rfc_message_id
    ):
        self.create_calls += 1
        if self.assignment is None:
            self.assignment = RoutingAssignment(
                "routing-1",
                request_id,
                "initial_n1",
                sector.sector_id,
                sector_level.level,
                sector_level.channel,
                sector_level.destination,
                RoutingStatus.ROUTING_PENDING,
                outbound_rfc_message_id,
                None,
            )
        return self.assignment

    async def create_unresolved_assignment(
        self, conn, *, request_id, sector_id, error_code
    ):
        if self.assignment is None:
            self.assignment = RoutingAssignment(
                "routing-1",
                request_id,
                "initial_n1",
                sector_id,
                1,
                None,
                None,
                RoutingStatus.ROUTING_UNRESOLVED,
                None,
                None,
                last_error_code=error_code,
            )
        return self.assignment

    async def mark_attempt(self, conn, assignment_id):
        self.assignment = replace(
            self.assignment,
            status=RoutingStatus.ROUTING_PENDING,
            attempt_count=self.assignment.attempt_count + 1,
        )
        return self.assignment

    async def mark_assigned(
        self,
        conn,
        *,
        assignment_id,
        external_message_id,
        observed_rfc_message_id=None,
    ):
        self.assignment = replace(
            self.assignment,
            status=RoutingStatus.ASSIGNED,
            outbound_external_message_id=external_message_id,
            outbound_observed_rfc_message_id=observed_rfc_message_id,
            delivery_uncertain=False,
            last_error_code=None,
        )
        return self.assignment

    async def record_observed_rfc_message_id(
        self, conn, *, assignment_id, observed_rfc_message_id
    ):
        self.assignment = replace(
            self.assignment,
            outbound_observed_rfc_message_id=observed_rfc_message_id,
        )
        return self.assignment

    async def ensure_work_state(self, conn, assignment):
        return None

    async def mark_failed(
        self, conn, *, assignment_id, error_code, delivery_uncertain
    ):
        self.assignment = replace(
            self.assignment,
            status=RoutingStatus.ROUTING_FAILED,
            last_error_code=error_code,
            delivery_uncertain=delivery_uncertain,
        )
        return self.assignment


class _Sender:
    sender_address = "mesaentrada@alquimiablue.com"

    def __init__(self, *, error=None, found=None, reference_found=None, find_error=None):
        self.error = error
        self.found = found
        self.reference_found = reference_found
        self.find_error = find_error
        self.send_calls = []
        self.find_calls = []
        self.reference_find_calls = []

    def find_sent_message_by_rfc_message_id(self, rfc_message_id):
        self.find_calls.append(rfc_message_id)
        if self.find_error:
            raise self.find_error
        return self.found

    def find_sent_message_by_reference(self, reference, *, to=None):
        self.reference_find_calls.append((reference, to))
        return self.reference_found

    def send_message(self, **kwargs):
        self.send_calls.append(kwargs)
        if self.error:
            raise self.error
        return "gmail-out-1"

    def get_message_rfc_id(self, message_id):
        return f"<{message_id}@gmail.example>"


def _service(repo, sender=None):
    return FlowRoutingService(pool=_Pool(), repository=repo, sender=sender)


@pytest.mark.parametrize(
    "category",
    [
        "alumbrado",
        "Alumbrado público",
        "luminaria",
        "poste_luz",
        "street_lighting",
        "Reparación de alumbrado público",
    ],
)
def test_sector_resolver_maps_known_categories(category):
    assert resolve_sector_id(category) == "alumbrado"


def test_sector_resolver_unknown_category_is_unresolved():
    assert resolve_sector_id("arbolado") is None


def test_confirmed_request_routes_and_builds_useful_n1_email():
    repo = _Repository()
    sender = _Sender()
    result = asyncio.run(
        _service(repo, sender).route_confirmed_request(
            repo.request.id, confirm_send=True
        )
    )
    call = sender.send_calls[0]
    assert result.status == "ASSIGNED"
    assert result.sent is True
    assert result.assignment.sector_id == "alumbrado"
    assert result.assignment.level == 1
    assert result.assignment.outbound_observed_rfc_message_id == (
        "<gmail-out-1@gmail.example>"
    )
    assert call["to"] == "alumbrado.n1@alquimiablue.com"
    assert call["subject"].startswith("[Team360 Flow] Nueva solicitud #")
    assert repo.request.id in call["subject"]
    assert repo.request.id in call["body"]
    assert repo.request.description in call["body"]
    assert repo.request.location_text in call["body"]
    assert "Nivel 1" in call["body"]


def test_route_twice_creates_one_assignment_and_sends_once():
    repo = _Repository()
    sender = _Sender()
    service = _service(repo, sender)
    first = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    second = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert first.sent is True
    assert second.idempotent is True
    assert second.status == "ASSIGNED"
    assert repo.create_calls == 1
    assert len(sender.send_calls) == 1


def test_dry_run_does_not_create_assignment_or_send():
    repo = _Repository()
    result = asyncio.run(
        _service(repo).route_confirmed_request(repo.request.id, confirm_send=False)
    )
    assert result.status == "DRY_RUN"
    assert result.email.destination == "alumbrado.n1@alquimiablue.com"
    assert repo.assignment is None


def test_missing_request_raises_typed_error():
    repo = _Repository(request=None)
    with pytest.raises(FlowRequestNotFoundError):
        asyncio.run(
            _service(repo).route_confirmed_request("missing", confirm_send=False)
        )


def test_unconfirmed_request_is_rejected():
    repo = _Repository(request=_request(status="PENDING"))
    with pytest.raises(FlowRequestNotConfirmedError):
        asyncio.run(
            _service(repo).route_confirmed_request(repo.request.id, confirm_send=False)
        )


@pytest.mark.parametrize(
    ("sector", "level", "reason"),
    [(_sector(False), _level(), "SECTOR_INACTIVE"), (_sector(), _level(False), "LEVEL_INACTIVE")],
)
def test_inactive_catalog_entry_is_unresolved_without_send(sector, level, reason):
    repo = _Repository(sector=sector, level=level)
    sender = _Sender()
    result = asyncio.run(
        _service(repo, sender).route_confirmed_request(
            repo.request.id, confirm_send=True
        )
    )
    assert result.status == "ROUTING_UNRESOLVED"
    assert result.reason_code == reason
    assert sender.send_calls == []


def test_missing_level_destination_is_unresolved_without_send():
    repo = _Repository(level=None)
    sender = _Sender()
    result = asyncio.run(
        _service(repo, sender).route_confirmed_request(
            repo.request.id, confirm_send=True
        )
    )
    assert result.status == "ROUTING_UNRESOLVED"
    assert result.reason_code == "LEVEL_NOT_FOUND"
    assert sender.send_calls == []


def test_unknown_category_is_persisted_unresolved_without_send():
    repo = _Repository(request=_request(category="arbolado"))
    sender = _Sender()
    result = asyncio.run(
        _service(repo, sender).route_confirmed_request(
            repo.request.id, confirm_send=True
        )
    )
    assert result.status == "ROUTING_UNRESOLVED"
    assert result.reason_code == "CATEGORY_UNRESOLVED"
    assert sender.send_calls == []


def test_timeout_is_failed_uncertain_then_reconciled_without_second_send():
    repo = _Repository()
    sender = _Sender(error=TimeoutError("controlled timeout"))
    service = _service(repo, sender)
    failed = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert failed.status == "ROUTING_FAILED"
    assert failed.assignment.delivery_uncertain is True
    assert len(sender.send_calls) == 1

    sender.error = None
    sender.reference_found = "gmail-accepted-before-timeout"
    recovered = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert recovered.status == "ASSIGNED"
    assert recovered.reconciled is True
    assert recovered.idempotent is True
    assert len(sender.send_calls) == 1


def test_reconciliation_search_failure_is_persisted_without_sending():
    repo = _Repository()
    sender = _Sender(find_error=RuntimeError("controlled search failure"))
    failed = asyncio.run(
        _service(repo, sender).route_confirmed_request(
            repo.request.id, confirm_send=True
        )
    )
    assert failed.status == "ROUTING_FAILED"
    assert failed.reason_code == "RuntimeError"
    assert sender.send_calls == []


def test_uncertain_delivery_remains_uncertain_when_reconciliation_fails():
    repo = _Repository()
    sender = _Sender(error=TimeoutError("controlled timeout"))
    service = _service(repo, sender)
    first = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert first.assignment.delivery_uncertain is True

    sender.error = None
    sender.find_error = RuntimeError("controlled search failure")
    second = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert second.status == "ROUTING_FAILED"
    assert second.assignment.delivery_uncertain is True
    assert len(sender.send_calls) == 1


@pytest.mark.parametrize("error", [RuntimeError("api error"), ValueError("send rejected")])
def test_known_send_failure_persists_failed_and_can_retry(error):
    repo = _Repository()
    sender = _Sender(error=error)
    service = _service(repo, sender)
    failed = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert failed.status == "ROUTING_FAILED"
    assert failed.assignment.delivery_uncertain is False
    sender.error = None
    retried = asyncio.run(
        service.route_confirmed_request(repo.request.id, confirm_send=True)
    )
    assert retried.status == "ASSIGNED"
    assert len(sender.send_calls) == 2

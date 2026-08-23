"""Regression tests for the automatic CONFIRMED -> N1 routing trigger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from modules.flow import poll_once as poll_once_module
from modules.flow.domain import (
    CandidateRequest,
    ConversationState,
    InitialInterpretation,
    ReplyInterpretation,
)
from modules.flow.repository import ClaimedInbound, StoredCandidate
from modules.flow.service import FlowIntakeService
from modules.messaging.domain import InboundMessage, OutboundMessageReceipt


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


class _IntakeRepository:
    def __init__(self):
        self.conversation_id = "conversation-1"
        self.state = ConversationState.RECEIVED
        self.revision = 0
        self.message_ids = set()
        self.candidates = ()
        self.confirmed = ()

    async def claim_inbound(self, conn, message):
        is_new = message.external_message_id not in self.message_ids
        self.message_ids.add(message.external_message_id)
        return ClaimedInbound(
            is_new=is_new,
            message_id=message.external_message_id if is_new else None,
            conversation_id=self.conversation_id,
            state=self.state,
            revision=self.revision,
        )

    async def add_interpretation(self, conn, **kwargs):
        return None

    async def replace_candidates(self, conn, *, conversation_id, revision, requests):
        self.revision = revision + 1
        self.candidates = tuple(
            StoredCandidate(f"candidate-{index}", index, request)
            for index, request in enumerate(requests, start=1)
        )
        return self.revision

    async def active_candidates(self, conn, conversation_id):
        return self.candidates

    async def update_state(self, conn, conversation_id, state):
        self.state = state

    async def record_outbound(self, conn, **kwargs):
        return None

    async def confirm_active_candidates(self, conn, conversation_id):
        self.confirmed = ("request-1",)
        return len(self.confirmed)

    async def confirmed_request_ids(self, conn, conversation_id):
        return self.confirmed


class _IntakeInterpreter:
    def interpret_initial(self, message):
        return InitialInterpretation(
            requests=(
                CandidateRequest(
                    "Se cayó un poste de luz en la intersección de Olleros y Cabildo.",
                    "alumbrado",
                    "Olleros y Cabildo",
                    confidence=0.99,
                ),
            )
        )

    def interpret_reply(self, message, current_requests):
        return ReplyInterpretation("confirm_all")


class _IntakeSender:
    sender_address = "mesaentrada@example.com"

    def send_reply(self, **kwargs):
        return OutboundMessageReceipt("outbound-1", kwargs["thread_id"])


def _inbound(message_id, body, *, thread_id="thread-1"):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender="vecino@example.com",
        recipients=("mesaentrada@example.com",),
        subject="Solicitud de alumbrado",
        text_body=body,
        received_at=datetime.now(timezone.utc),
        metadata={"rfc_message_id": f"<{message_id}@example.com>"},
    )


def test_confirmed_request_is_handed_to_existing_idempotent_router(monkeypatch):
    calls = []

    class _Repository:
        async def confirmed_request_ids(self, conn, conversation_id):
            assert conversation_id == "conversation-1"
            return ("request-1",)

    class _RoutingResult:
        status = "ASSIGNED"
        assignment = type("Assignment", (), {"sector_id": "alumbrado", "level": 1})()
        idempotent = False
        reason_code = None

    class _RoutingService:
        def __init__(self, *, pool, repository, sender):
            assert isinstance(repository, poll_once_module.FlowRoutingPostgresRepository)
            calls.append((pool, sender))

        async def route_confirmed_request(self, request_id, *, confirm_send):
            assert request_id == "request-1"
            assert confirm_send is True
            calls.append(request_id)
            return _RoutingResult()

    monkeypatch.setattr(poll_once_module, "FlowPostgresRepository", _Repository)
    monkeypatch.setattr(poll_once_module, "FlowRoutingService", _RoutingService)

    statuses = asyncio.run(
        poll_once_module._route_confirmed_requests(
            pool=_Pool(), sender=object(), conversation_id="conversation-1"
        )
    )

    assert statuses == ("ASSIGNED",)
    assert calls[1] == "request-1"


def test_exact_demo_confirmation_flows_into_automatic_n1_trigger(monkeypatch):
    repository = _IntakeRepository()
    intake = FlowIntakeService(
        pool=_Pool(),
        repository=repository,
        interpreter=_IntakeInterpreter(),
        reply_sender=_IntakeSender(),
    )

    initial = asyncio.run(
        intake.process(
            _inbound(
                "message-1",
                "Se cayó un poste de luz en la intersección de Olleros y Cabildo.",
            )
        )
    )
    confirmed = asyncio.run(intake.process(_inbound("message-2", "si")))

    assert initial.state == ConversationState.PENDING_CONFIRMATION
    assert confirmed.state == ConversationState.CONFIRMED
    assert confirmed.confirmed_count == 1
    assert repository.candidates[0].request.tentative_category == "alumbrado"

    monkeypatch.setattr(
        poll_once_module, "FlowPostgresRepository", lambda: repository
    )

    class _RoutingService:
        def __init__(self, *, pool, repository, sender):
            return None

        async def route_confirmed_request(self, request_id, *, confirm_send):
            assert request_id == "request-1"
            assert confirm_send is True
            return type(
                "RoutingResult",
                (),
                {
                    "status": "ASSIGNED",
                    "assignment": type(
                        "Assignment", (), {"sector_id": "alumbrado", "level": 1}
                    )(),
                    "idempotent": False,
                    "reason_code": None,
                },
            )()

    monkeypatch.setattr(poll_once_module, "FlowRoutingService", _RoutingService)
    statuses = asyncio.run(
        poll_once_module._route_confirmed_requests(
            pool=_Pool(), sender=object(), conversation_id=confirmed.conversation_id
        )
    )
    assert statuses == ("ASSIGNED",)

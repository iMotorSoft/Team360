import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from modules.flow.domain import (
    OperationalAction,
    OperationalInterpretation,
    OperationalRoutingContext,
    OperationalStatus,
    OperationalWorkState,
)
from modules.flow.operational_service import FlowOperationalReplyService
from modules.messaging.domain import InboundMessage


REQUEST_ID = "656977af-cc29-43d6-b78c-53464818f06a"
OTHER_REQUEST_ID = "818126f6-84ad-4c40-bbef-480ccfc0387b"
OBSERVED_RFC = "<gmail-real-id@mail.gmail.com>"


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


def _context(request_id=REQUEST_ID):
    return OperationalRoutingContext(
        routing_id=f"routing-{request_id[:8]}",
        request_id=request_id,
        conversation_id="conversation-1",
        routing_status="ASSIGNED",
        destination="alumbrado.n1@alquimiablue.com",
        outbound_external_message_id="gmail-out-1",
        outbound_rfc_message_id=f"<intended-{request_id}@alquimiablue.com>",
        outbound_observed_rfc_message_id=OBSERVED_RFC,
    )


def _message(
    *,
    message_id="reply-1",
    subject=None,
    in_reply_to="",
    references="",
    received_at=None,
    sender="mario.rojas@alquimiablue.com",
    thread_id="different-mailbox-thread",
):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender=sender,
        recipients=("mesaentrada@alquimiablue.com",),
        subject=subject or f"Re: [Team360 Flow] Nueva solicitud #{REQUEST_ID}",
        text_body="Recibido. Lo estamos verificando.",
        received_at=received_at or datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
        metadata={"in_reply_to": in_reply_to, "references": references},
    )


class _Repository:
    def __init__(self):
        self.contexts = {REQUEST_ID: _context(), OTHER_REQUEST_ID: _context(OTHER_REQUEST_ID)}
        self.messages = {}
        self.events = {}
        self.state = OperationalWorkState(
            REQUEST_ID,
            _context().routing_id,
            OperationalStatus.ASSIGNED,
            None,
            None,
        )

    async def find_by_rfc_reference(self, conn, references):
        if OBSERVED_RFC in references:
            return self.contexts[REQUEST_ID]
        return None

    async def find_by_request_id(self, conn, request_id):
        return self.contexts.get(request_id)

    async def claim_message(self, conn, *, context, message):
        key = (message.provider, message.external_message_id)
        if key in self.messages:
            return None
        self.messages[key] = "source-1"
        return "source-1"

    async def ensure_work_state(self, conn, context):
        return self.state

    async def record_event(self, conn, **kwargs):
        message = kwargs["message"]
        self.events[message.external_message_id] = kwargs
        return f"event-{len(self.events)}"

    async def mark_in_progress(self, conn, *, context, message):
        self.state = replace(
            self.state,
            status=OperationalStatus.IN_PROGRESS,
            first_response_at=self.state.first_response_at or message.received_at,
            first_responder=self.state.first_responder or message.sender,
        )
        return self.state

    async def event_for_message(self, conn, provider, external_message_id):
        event = self.events.get(external_message_id)
        if not event:
            return None
        return {
            "event_id": "event-1",
            "interpretation_action": event["interpretation"].action.value,
            "correlation_method": event["correlation_method"],
        }


class _Interpreter:
    def __init__(self, action=OperationalAction.ACK_OR_PROGRESS):
        self.action = action
        self.calls = 0

    def interpret(self, message):
        self.calls += 1
        return OperationalInterpretation(
            self.action, "clasificado", "mock", "mock", {}, 1
        )


def _service(repo, interpreter):
    return FlowOperationalReplyService(
        pool=_Pool(), repository=repo, interpreter=interpreter
    )


@pytest.mark.parametrize(
    ("message", "method"),
    [
        (_message(in_reply_to=OBSERVED_RFC), "in_reply_to_rfc"),
        (_message(references=f"<root@example.com> {OBSERVED_RFC}"), "references_rfc"),
        (_message(), "subject_request_token"),
        (_message(thread_id="totally-different-thread"), "subject_request_token"),
    ],
)
def test_correlates_reply_using_persisted_evidence_not_thread_id(message, method):
    result = asyncio.run(
        _service(_Repository(), _Interpreter()).process_if_operational(message)
    )
    assert result.matched is True
    assert result.request_id == REQUEST_ID
    assert result.correlation_method == method


def test_sender_alone_without_routing_evidence_is_not_technical_identity():
    repo = _Repository()
    interpreter = _Interpreter()
    message = _message(subject="Hola", sender="mario.rojas@alquimiablue.com")
    result = asyncio.run(_service(repo, interpreter).process_if_operational(message))
    assert result.matched is False
    assert interpreter.calls == 0


def test_original_routing_delivery_is_not_misclassified_as_reply():
    repo = _Repository()
    interpreter = _Interpreter()
    original = InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id="routing-copy",
        external_thread_id="sender-thread",
        sender="mesaentrada@alquimiablue.com",
        recipients=("alumbrado.n1@alquimiablue.com",),
        subject=f"[Team360 Flow] Nueva solicitud #{REQUEST_ID}",
        text_body="Nueva solicitud confirmada.",
        received_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
    )
    result = asyncio.run(
        _service(repo, interpreter).process_if_operational(original)
    )
    assert result.matched is False
    assert interpreter.calls == 0


def test_unknown_request_or_missing_routing_is_not_matched():
    message = _message(
        subject="Re: solicitud #aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    )
    result = asyncio.run(
        _service(_Repository(), _Interpreter()).process_if_operational(message)
    )
    assert result.matched is False


def test_other_routing_token_does_not_contaminate_request():
    message = _message(subject=f"Re: solicitud #{OTHER_REQUEST_ID}")
    result = asyncio.run(
        _service(_Repository(), _Interpreter()).process_if_operational(message)
    )
    assert result.request_id == OTHER_REQUEST_ID
    assert result.routing_id == _context(OTHER_REQUEST_ID).routing_id


def test_assigned_ack_transitions_to_in_progress_using_received_timestamp():
    repo = _Repository()
    timestamp = datetime(2026, 8, 12, 15, 5, tzinfo=timezone.utc)
    result = asyncio.run(
        _service(repo, _Interpreter()).process_if_operational(
            _message(in_reply_to=OBSERVED_RFC, received_at=timestamp)
        )
    )
    assert result.status == OperationalStatus.IN_PROGRESS
    assert result.first_response_at == timestamp
    assert repo.state.first_responder == "mario.rojas@alquimiablue.com"


def test_later_progress_reply_does_not_change_first_response_at():
    repo = _Repository()
    service = _service(repo, _Interpreter())
    first = _message(message_id="reply-1", in_reply_to=OBSERVED_RFC)
    second = _message(
        message_id="reply-2",
        in_reply_to=OBSERVED_RFC,
        received_at=first.received_at + timedelta(hours=1),
    )
    asyncio.run(service.process_if_operational(first))
    asyncio.run(service.process_if_operational(second))
    assert repo.state.status == OperationalStatus.IN_PROGRESS
    assert repo.state.first_response_at == first.received_at
    assert len(repo.events) == 2


def test_duplicate_message_has_one_event_and_no_second_interpretation():
    repo = _Repository()
    interpreter = _Interpreter()
    service = _service(repo, interpreter)
    message = _message(in_reply_to=OBSERVED_RFC)
    first = asyncio.run(service.process_if_operational(message))
    second = asyncio.run(service.process_if_operational(message))
    assert first.processed is True
    assert second.processed is False
    assert interpreter.calls == 1
    assert len(repo.events) == 1
    assert repo.state.first_response_at == message.received_at


@pytest.mark.parametrize(
    "action",
    [
        OperationalAction.AMBIGUOUS,
        OperationalAction.UNRELATED,
        OperationalAction.UNSUPPORTED_OPERATIONAL_ACTION,
    ],
)
def test_non_progress_actions_are_audited_without_transition(action):
    repo = _Repository()
    result = asyncio.run(
        _service(repo, _Interpreter(action)).process_if_operational(_message())
    )
    assert result.action == action
    assert result.status == OperationalStatus.ASSIGNED
    assert repo.state.first_response_at is None
    assert len(repo.events) == 1

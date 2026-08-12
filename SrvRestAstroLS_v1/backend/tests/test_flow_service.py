import asyncio
from datetime import datetime, timezone

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
    def __init__(self):
        self.conn = _Connection()

    def connection(self):
        return _AsyncContext(self.conn)


class _Repository:
    def __init__(self):
        self.conversations = {}
        self.message_ids = set()
        self.candidates = {}
        self.interpretations = 0
        self.outbound = 0
        self.confirmed = {}

    async def claim_inbound(self, conn, message):
        conversation = self.conversations.setdefault(
            message.external_thread_id,
            {"id": f"c{len(self.conversations) + 1}", "state": ConversationState.RECEIVED, "revision": 0},
        )
        is_new = message.external_message_id not in self.message_ids
        if is_new:
            self.message_ids.add(message.external_message_id)
        return ClaimedInbound(
            is_new=is_new,
            message_id=message.external_message_id if is_new else None,
            conversation_id=conversation["id"],
            state=conversation["state"],
            revision=conversation["revision"],
        )

    def _conversation(self, conversation_id):
        return next(item for item in self.conversations.values() if item["id"] == conversation_id)

    async def add_interpretation(self, conn, **kwargs):
        self.interpretations += 1

    async def replace_candidates(self, conn, *, conversation_id, revision, requests):
        new_revision = revision + 1
        self.candidates[conversation_id] = [
            StoredCandidate(f"candidate-{new_revision}-{index}", index, request)
            for index, request in enumerate(requests, start=1)
        ]
        self._conversation(conversation_id)["revision"] = new_revision
        return new_revision

    async def update_state(self, conn, conversation_id, state):
        self._conversation(conversation_id)["state"] = state

    async def record_outbound(self, conn, **kwargs):
        self.outbound += 1

    async def active_candidates(self, conn, conversation_id):
        return tuple(self.candidates.get(conversation_id, []))

    async def confirm_active_candidates(self, conn, conversation_id):
        items = self.candidates.get(conversation_id, [])
        self.confirmed[conversation_id] = list(items)
        return len(items)


class _Interpreter:
    def __init__(self, initial, replies=()):
        self.initial = initial
        self.replies = list(replies)
        self.initial_calls = 0
        self.reply_calls = 0

    def interpret_initial(self, message):
        self.initial_calls += 1
        return self.initial

    def interpret_reply(self, message, current_requests):
        self.reply_calls += 1
        return self.replies.pop(0)


class _Sender:
    sender_address = "mesaentrada@example.com"

    def __init__(self):
        self.calls = []

    def send_reply(self, **kwargs):
        self.calls.append(kwargs)
        return OutboundMessageReceipt(f"out-{len(self.calls)}", kwargs["thread_id"])


def _message(message_id, body, thread_id="thread-1"):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender="vecina@example.com",
        recipients=("mesaentrada@example.com",),
        subject="Solicitud vecinal",
        text_body=body,
        received_at=datetime.now(timezone.utc),
        metadata={"rfc_message_id": f"<{message_id}@example.com>"},
    )


def _request(description, category, location):
    return CandidateRequest(description, category, location, confidence=0.9)


def _service(repository, interpreter, sender):
    return FlowIntakeService(
        pool=_Pool(),
        repository=repository,
        interpreter=interpreter,
        reply_sender=sender,
    )


def test_same_gmail_message_is_idempotent_for_interpretation_and_confirmation_send():
    repository = _Repository()
    sender = _Sender()
    interpreter = _Interpreter(
        InitialInterpretation((_request("Reparar luminaria", "alumbrado", "Olleros"),))
    )
    service = _service(repository, interpreter, sender)
    message = _message("m1", "Hay un poste sin luz")

    first = asyncio.run(service.process(message))
    second = asyncio.run(service.process(message))

    assert first.processed is True
    assert second.processed is False
    assert repository.interpretations == 1
    assert repository.outbound == 1
    assert interpreter.initial_calls == 1
    assert len(sender.calls) == 1


def test_multi_request_creates_two_independent_confirmed_requests_only_after_reply():
    repository = _Repository()
    sender = _Sender()
    requests = (
        _request("Reparar poste", "alumbrado", "Olleros y Ciudad de la Paz"),
        _request("Retirar árbol caído", "arbolado", "en la misma cuadra"),
    )
    interpreter = _Interpreter(
        InitialInterpretation(requests),
        replies=(ReplyInterpretation("confirm_all"),),
    )
    service = _service(repository, interpreter, sender)

    pending = asyncio.run(service.process(_message("m1", "poste y árbol")))
    assert pending.state == ConversationState.PENDING_CONFIRMATION
    assert pending.candidate_count == 2
    assert repository.confirmed == {}
    assert "1. Reparar poste" in sender.calls[0]["body"]
    assert "2. Retirar árbol caído" in sender.calls[0]["body"]

    confirmed = asyncio.run(service.process(_message("m2", "Sí, los dos")))
    assert confirmed.state == ConversationState.CONFIRMED
    assert confirmed.confirmed_count == 2
    assert len(repository.confirmed[confirmed.conversation_id]) == 2

    duplicate = asyncio.run(service.process(_message("m2", "Sí, los dos")))
    assert duplicate.processed is False
    assert confirmed.confirmed_count == 2


def test_correction_replaces_candidates_and_requests_new_confirmation():
    repository = _Repository()
    sender = _Sender()
    original = (_request("Reparar poste", "alumbrado", "Olleros"),)
    corrected = (_request("Reparar poste", "alumbrado", "Ciudad de la Paz y Maure"),)
    interpreter = _Interpreter(
        InitialInterpretation(original),
        replies=(ReplyInterpretation("correction", corrected),),
    )
    service = _service(repository, interpreter, sender)

    asyncio.run(service.process(_message("m1", "poste en Olleros")))
    result = asyncio.run(service.process(_message("m2", "No, es Ciudad de la Paz y Maure")))

    assert result.state == ConversationState.PENDING_CONFIRMATION
    assert repository.confirmed == {}
    active = repository.candidates[result.conversation_id]
    assert active[0].request.location_text == "Ciudad de la Paz y Maure"
    assert len(sender.calls) == 2


def test_clear_confirmation_after_ambiguity_confirms_existing_candidates():
    repository = _Repository()
    sender = _Sender()
    requests = (_request("Reparar poste", "alumbrado", "Olleros"),)
    interpreter = _Interpreter(
        InitialInterpretation(requests),
        replies=(
            ReplyInterpretation("ambiguous", clarification_question="¿Confirmás?"),
            ReplyInterpretation("confirm_all"),
        ),
    )
    service = _service(repository, interpreter, sender)

    asyncio.run(service.process(_message("m1", "poste")))
    clarification = asyncio.run(service.process(_message("m2", "puede ser")))
    confirmed = asyncio.run(service.process(_message("m3", "sí, correcto")))

    assert clarification.state == ConversationState.PENDING_CLARIFICATION
    assert confirmed.state == ConversationState.CONFIRMED
    assert confirmed.confirmed_count == 1

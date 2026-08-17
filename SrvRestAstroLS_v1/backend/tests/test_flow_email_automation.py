"""Deterministic email automation, sender authorization and handler isolation.

Covers the real-email loop hardening: RFC 3834 auto-replies and bounces never
produce a first response / work transition / SLA MET, correlated replies
require an internal-domain sender, and the operational and closure approval
handlers never steal each other's messages. No real Gmail, no LLM.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from modules.flow.closure_service import FlowClosureService
from modules.flow.domain import (
    OperationalAction,
    OperationalInterpretation,
    OperationalRoutingContext,
    OperationalStatus,
    OperationalWorkState,
    is_automated_message,
    operational_sender_authorized,
)
from modules.flow.operational_service import FlowOperationalReplyService
from modules.messaging.domain import InboundMessage


REQUEST_ID = "656977af-cc29-43d6-b78c-53464818f06a"
OBSERVED_RFC = "<gmail-real-id@mail.gmail.com>"
# Real approval token format: letter-first, "a" + 15 hex (approval_token_for).
APPROVAL_TOKEN = "a3f9c21e8d4b6a0f"


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


def _context(*, request_status="CONFIRMED", level=1):
    return OperationalRoutingContext(
        routing_id=f"routing-n{level}",
        request_id=REQUEST_ID,
        conversation_id="conversation-1",
        routing_key=f"alumbrado_level_{level}",
        level=level,
        routing_status="ASSIGNED",
        destination=f"alumbrado.n{level}@alquimiablue.com",
        outbound_external_message_id="gmail-out-1",
        outbound_rfc_message_id="<intended@alquimiablue.com>",
        outbound_observed_rfc_message_id=OBSERVED_RFC,
        request_status=request_status,
    )


def _message(
    *,
    message_id="reply-1",
    sender="mario.rojas@alquimiablue.com",
    in_reply_to=OBSERVED_RFC,
    references="",
    subject=None,
    metadata=None,
    received_at=None,
):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id="thread-1",
        sender=sender,
        recipients=("mesaentrada@alquimiablue.com",),
        subject=subject or f"Re: [Team360 Flow] Nueva solicitud #{REQUEST_ID}",
        text_body="Recibido. Lo estamos verificando.",
        received_at=received_at or datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
        metadata=metadata
        or {"in_reply_to": in_reply_to, "references": references},
    )


def _automated(**markers):
    """Build an automated-marker metadata dict over the correlation headers."""
    base = {"in_reply_to": OBSERVED_RFC, "references": ""}
    base.update(markers)
    return base


class _OperationalRepo:
    def __init__(self, contexts=None):
        self.contexts = contexts or [_context()]
        self.messages = {}
        self.events = {}
        self.states = {
            c.routing_id: OperationalWorkState(
                c.request_id, c.routing_id, OperationalStatus.ASSIGNED, None, None
            )
            for c in self.contexts
        }

    async def find_by_rfc_reference(self, conn, references):
        for context in self.contexts:
            if context.outbound_observed_rfc_message_id in references:
                return context
        return None

    async def find_unambiguous_by_request_id(self, conn, request_id):
        matches = [c for c in self.contexts if c.request_id == request_id]
        return matches[0] if len(matches) == 1 else None

    async def find_by_request_routing_key(self, conn, *, request_id, routing_key):
        return next(
            (
                c for c in self.contexts
                if c.request_id == request_id and c.routing_key == routing_key
            ),
            None,
        )

    async def claim_message(self, conn, *, context, message):
        key = (message.provider, message.external_message_id)
        if key in self.messages:
            return None
        self.messages[key] = "source-1"
        return "source-1"

    async def ensure_work_state(self, conn, context):
        return self.states[context.routing_id]

    async def record_event(self, conn, **kwargs):
        self.events[kwargs["message"].external_message_id] = kwargs
        return f"event-{len(self.events)}"

    async def mark_in_progress(self, conn, *, context, message):
        state = self.states[context.routing_id]
        self.states[context.routing_id] = replace(
            state,
            status=OperationalStatus.IN_PROGRESS,
            first_response_at=state.first_response_at or message.received_at,
            first_responder=state.first_responder or message.sender,
        )
        return self.states[context.routing_id]

    async def event_for_message(self, conn, provider, external_message_id):
        return None


class _Interpreter:
    def __init__(self, action=OperationalAction.ACK_OR_PROGRESS):
        self.action = action
        self.calls = 0

    def interpret(self, message):
        self.calls += 1
        return OperationalInterpretation(
            self.action, "clasificado", "mock", "mock", {}, 1
        )


def _operational_service(repo, interpreter=None):
    return FlowOperationalReplyService(
        pool=_Pool(), repository=repo, interpreter=interpreter or _Interpreter()
    )


class _ClosureRepo:
    """Minimal closure repository: nothing correlates for isolation tests."""

    async def find_approval_by_rfc_reference(self, conn, references):
        return None

    async def find_approval_by_token(self, conn, token):
        return None


def _closure_service(repo=None):
    return FlowClosureService(
        pool=_Pool(),
        repository=repo or _ClosureRepo(),
        audit_repository=None,  # type: ignore[arg-type]
        interpreter=None,  # type: ignore[arg-type]
        sender=None,
    )


# ---------------------------------------------------------------------------
# Deterministic auto-reply / bounce detection (pure).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("markers", "expected"),
    [
        ({"auto_submitted": "auto-replied"}, True),
        ({"auto_submitted": "auto-generated"}, True),
        ({"auto_submitted": "no"}, False),
        ({"precedence": "auto_reply"}, True),
        ({"precedence": "bulk"}, False),  # conservative: lists are not auto-replies
        ({"x_autoreply": "yes"}, True),
        ({"x_autoreply": "true"}, True),
        ({"x_autoreply": "no"}, False),
        ({"x_autorespond": "out of office"}, True),
        ({"content_type": "multipart/report"}, True),
        ({"content_type": "message/delivery-status"}, True),
        ({"content_type": "text/plain"}, False),
        ({"x_failed_recipients": "unknown@example.com"}, True),
    ],
)
def test_is_automated_message_detects_markers(markers, expected):
    message = _message(metadata=_automated(**markers))
    assert is_automated_message(message) is expected


@pytest.mark.parametrize(
    "sender",
    [
        "mailer-daemon@googlemail.com",
        "postmaster@alquimiablue.com",
        "MAILER-DAEMON@alquimiablue.com",
    ],
)
def test_is_automated_message_detects_bounce_senders(sender):
    assert is_automated_message(_message(sender=sender)) is True


def test_is_automated_message_plain_reply_is_false():
    assert is_automated_message(_message()) is False
    # No metadata at all must be treated as a normal message.
    message = InboundMessage(
        provider="gmail", channel="email", external_message_id="m",
        external_thread_id="t", sender="tech@alquimiablue.com",
        recipients=("mesa@alquimiablue.com",), subject="Re: caso",
        text_body="ok", received_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        metadata={},
    )
    assert is_automated_message(message) is False


# ---------------------------------------------------------------------------
# Sender authorization (pure).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sender", "destination", "expected"),
    [
        ("mario.rojas@alquimiablue.com", "alumbrado.n1@alquimiablue.com", True),
        ("alumbrado.n1@alquimiablue.com", "alumbrado.n1@alquimiablue.com", True),
        ("vecina@example.com", "alumbrado.n1@alquimiablue.com", False),
        ("attacker@gmail.com", "alumbrado.n1@alquimiablue.com", False),
        ("", "alumbrado.n1@alquimiablue.com", False),
        ("no-domain", "alumbrado.n1@alquimiablue.com", False),
    ],
)
def test_operational_sender_authorized_domain_boundary(sender, destination, expected):
    assert operational_sender_authorized(sender, destination) is expected


# ---------------------------------------------------------------------------
# Service-level rejection: auto-reply/bounce never acts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "markers",
    [
        {"auto_submitted": "auto-replied"},
        {"precedence": "auto_reply"},
        {"content_type": "multipart/report"},
    ],
)
def test_automated_reply_is_matched_but_ignored_without_effects(markers):
    repo = _OperationalRepo()
    interpreter = _Interpreter()
    message = _message(message_id="auto-1", metadata=_automated(**markers))
    result = asyncio.run(_operational_service(repo, interpreter).process_if_operational(message))
    assert result.matched is True
    assert result.processed is False
    assert result.ignored == "AUTOMATED_MESSAGE"
    assert result.first_response_at is None
    assert interpreter.calls == 0
    assert repo.events == {}
    assert repo.states["routing-n1"].status == OperationalStatus.ASSIGNED
    assert repo.states["routing-n1"].first_response_at is None


def test_bounce_reply_is_ignored_without_first_response():
    repo = _OperationalRepo()
    message = _message(
        message_id="bounce-1",
        sender="mailer-daemon@googlemail.com",
        metadata=_automated(content_type="multipart/report"),
    )
    result = asyncio.run(_operational_service(repo).process_if_operational(message))
    assert result.matched is True
    assert result.ignored == "AUTOMATED_MESSAGE"
    assert repo.states["routing-n1"].first_response_at is None


# ---------------------------------------------------------------------------
# Sender authorization at the service boundary.
# ---------------------------------------------------------------------------


def test_citizen_sender_correlating_to_thread_is_unauthorized():
    repo = _OperationalRepo()
    interpreter = _Interpreter()
    message = _message(message_id="citizen-1", sender="vecina@example.com")
    result = asyncio.run(_operational_service(repo, interpreter).process_if_operational(message))
    assert result.matched is True
    assert result.processed is False
    assert result.authorized is False
    assert result.first_response_at is None
    assert interpreter.calls == 0
    assert repo.messages == {}  # not claimed


def test_internal_sender_is_accepted_and_records_first_response():
    repo = _OperationalRepo()
    interpreter = _Interpreter()
    message = _message(sender="mario.rojas@alquimiablue.com")
    result = asyncio.run(_operational_service(repo, interpreter).process_if_operational(message))
    assert result.matched is True
    assert result.processed is True
    assert result.authorized is True
    assert result.first_response_at == message.received_at
    assert interpreter.calls == 1
    assert repo.states["routing-n1"].status == OperationalStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# Handler isolation: approval vs operational replies never steal each other.
# ---------------------------------------------------------------------------


def test_approval_reply_is_not_operational():
    # Subject carries the letter-first approval token, not a routing token.
    message = _message(
        message_id="approval-1",
        in_reply_to="<closure-obs@mail.gmail.com>",
        subject=f"Re: [Team360 Flow][CIERRE][R:{APPROVAL_TOKEN}][{REQUEST_ID}] Aprobación de cierre",
    )
    repo = _OperationalRepo()
    result = asyncio.run(_operational_service(repo).process_if_operational(message))
    assert result.matched is False


def test_operational_reply_is_not_approval():
    message = _message(in_reply_to=OBSERVED_RFC)
    result = asyncio.run(_closure_service().process_approval_reply(message))
    assert result.matched is False


def test_approval_reply_with_real_token_is_not_operational():
    # Regression guard: the closure gate made approval tokens letter-first and
    # routing-key-shaped so the operational correlator resolves the subject
    # token to a routing key that never matches and short-circuits to None
    # instead of falling through to the request-id fallback.
    from modules.flow.domain import approval_token_for, routing_key_from_subject

    token = approval_token_for("gmail", "approval-msg-1")
    assert token[0].isalpha()  # letter-first (the closure gate fix)
    assert len(token) == 16
    subject = f"Re: [Team360 Flow][CIERRE][R:{token}][{REQUEST_ID}] Aprobación"
    # The token is routing-key-shaped, so the routing-key branch fires...
    assert routing_key_from_subject(subject) == token
    # ...and since no routing owns that key, the operational handler must not
    # match the approval reply.
    repo = _OperationalRepo()
    result = asyncio.run(
        _operational_service(repo).process_if_operational(
            _message(
                message_id="approval-real",
                subject=subject,
                in_reply_to="<closure-obs@mail.gmail.com>",
            )
        )
    )
    assert result.matched is False


# ---------------------------------------------------------------------------
# poll_once automated gate (deterministic filter, no DB).
# ---------------------------------------------------------------------------


def test_automated_detection_is_usable_at_poll_boundary():
    # poll_once rejects automated messages before any handler; the same pure
    # predicate used there must be the one the services honor.
    automated = _message(message_id="a1", metadata=_automated(auto_submitted="auto-replied"))
    normal = _message(message_id="n1")
    assert is_automated_message(automated) is True
    assert is_automated_message(normal) is False


# ---------------------------------------------------------------------------
# Opt-in real PostgreSQL integration (mirrors existing Flow repository tests).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_EMAIL_AUTOMATION_POSTGRES_TEST") != "1",
    reason="requires migrations 011-018 on Team360 PostgreSQL",
)
def test_real_postgres_automated_reply_is_ignored_and_metadata_persists():
    from uuid import uuid4

    import psycopg
    from psycopg.rows import dict_row

    from modules.db.pool import close_pool, create_pool, open_pool
    from modules.db.settings import get_database_settings
    from modules.flow.operational_repository import FlowOperationalPostgresRepository

    async def exercise():
        suffix = uuid4().hex
        thread = f"email-auto-{suffix}"
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
                    ) values ('gmail', 'email', %(thread)s,
                              'citizen@example.com', 'Email automation test',
                              'CONFIRMED') returning id
                    """,
                    {"thread": thread},
                )
                conversation_id = (await cur.fetchone())["id"]
                await cur.execute(
                    """
                    insert into flow_request_candidates (
                        conversation_id, revision, ordinal, description,
                        tentative_category, status
                    ) values (%(conversation)s, 1, 1, 'Reparar poste',
                              'alumbrado', 'CONFIRMED') returning id
                    """,
                    {"conversation": conversation_id},
                )
                candidate_id = (await cur.fetchone())["id"]
                await cur.execute(
                    """
                    insert into flow_requests (
                        conversation_id, source_candidate_id, description,
                        tentative_category, confirmed_at_utc
                    ) values (%(conversation)s, %(candidate)s,
                              'Reparar poste', 'alumbrado', now())
                    returning id
                    """,
                    {"conversation": conversation_id, "candidate": candidate_id},
                )
                request_id = str((await cur.fetchone())["id"])
                await cur.execute(
                    """
                    select id from flow_sector_levels
                    where sector_id='alumbrado' and level=1
                    """
                )
                level_id = (await cur.fetchone())["id"]
                observed_rfc = f"<{suffix}@mail.gmail.com>"
                await cur.execute(
                    """
                    insert into flow_request_routings (
                        request_id, sector_id, sector_level_id, level,
                        channel, destination, status,
                        outbound_rfc_message_id,
                        outbound_observed_rfc_message_id,
                        outbound_external_message_id, assigned_at_utc
                    ) values (%(request)s, 'alumbrado', %(level_id)s, 1,
                              'email', 'alumbrado.n1@alquimiablue.com',
                              'ASSIGNED', %(intended)s, %(observed)s,
                              %(external)s, now()) returning id
                    """,
                    {
                        "request": request_id,
                        "level_id": level_id,
                        "intended": f"<intended-{suffix}@example.com>",
                        "observed": observed_rfc,
                        "external": f"gmail-out-{suffix}",
                    },
                )
                routing_id = str((await cur.fetchone())["id"])
            await conn.commit()

        pool = create_pool(get_database_settings(min_size=1, max_size=2))
        await open_pool(pool)
        try:
            repo = FlowOperationalPostgresRepository()

            class _FakeInterpreter:
                calls = 0

                def interpret(self, message):
                    self.calls += 1
                    return OperationalInterpretation(
                        OperationalAction.ACK_OR_PROGRESS, "ok", "mock", "mock", {}, 1
                    )

            interpreter = _FakeInterpreter()
            service = FlowOperationalReplyService(
                pool=pool, repository=repo, interpreter=interpreter  # type: ignore[arg-type]
            )

            # Automated reply correlating to the routing thread.
            automated = InboundMessage(
                provider="gmail", channel="email",
                external_message_id=f"auto-{suffix}", external_thread_id=f"t-{suffix}",
                sender="mario.rojas@alquimiablue.com",
                recipients=("mesaentrada@alquimiablue.com",),
                subject=f"Re: request {request_id}",
                text_body="Estoy fuera de la oficina.",
                received_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
                metadata={
                    "in_reply_to": observed_rfc,
                    "references": "",
                    "auto_submitted": "auto-replied",
                    "precedence": "",
                    "content_type": "text/plain",
                },
            )
            result = await service.process_if_operational(automated)
            assert result.matched is True
            assert result.processed is False
            assert result.ignored == "AUTOMATED_MESSAGE"
            assert interpreter.calls == 0

            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select operational_status from flow_request_work_states
                        where routing_id = %(routing)s
                        """,
                        {"routing": routing_id},
                    )
                    state = await cur.fetchone()
                    assert state is None or state["operational_status"] == "ASSIGNED"
                    await cur.execute(
                        """
                        select count(*) as n from flow_request_operational_events
                        where routing_id = %(routing)s
                        """,
                        {"routing": routing_id},
                    )
                    assert (await cur.fetchone())["n"] == 0

            # Normal internal reply: processed, metadata (including the new
            # additive keys) persists into flow_messages.
            normal = InboundMessage(
                provider="gmail", channel="email",
                external_message_id=f"reply-{suffix}", external_thread_id=f"t-{suffix}",
                sender="mario.rojas@alquimiablue.com",
                recipients=("mesaentrada@alquimiablue.com",),
                subject=f"Re: request {request_id}",
                text_body="Recibido, lo verificamos.",
                received_at=datetime(2026, 8, 12, 15, 1, tzinfo=timezone.utc),
                metadata={
                    "in_reply_to": observed_rfc,
                    "references": "",
                    "auto_submitted": "",
                    "precedence": "",
                    "content_type": "text/plain",
                },
            )
            normal_result = await service.process_if_operational(normal)
            assert normal_result.matched is True
            assert normal_result.processed is True
            assert normal_result.first_response_at == normal.received_at
            assert interpreter.calls == 1

            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select metadata_jsonb from flow_messages
                        where provider = 'gmail'
                          and external_message_id = %(msg)s
                        """,
                        {"msg": f"reply-{suffix}"},
                    )
                    row = await cur.fetchone()
                    assert row is not None
                    metadata = row["metadata_jsonb"]
                    assert "auto_submitted" in metadata
                    assert "precedence" in metadata
                    assert "content_type" in metadata

            # Cleanup (reverse dependency order).
            async with await psycopg.AsyncConnection.connect(
                settings.dsn, row_factory=dict_row
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "delete from flow_request_operational_events where request_id = %(request)s",
                        {"request": request_id},
                    )
                    await cur.execute(
                        "delete from flow_messages where conversation_id = %(conversation)s",
                        {"conversation": conversation_id},
                    )
                    await cur.execute(
                        "delete from flow_request_work_states where routing_id = %(routing)s",
                        {"routing": routing_id},
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

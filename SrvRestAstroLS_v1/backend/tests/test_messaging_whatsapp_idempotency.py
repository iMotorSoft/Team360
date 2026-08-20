"""WhatsApp inbound message idempotency tests against real PostgreSQL.

Validates that:
- First inbound → CLAIMED (is_new=True)
- Same provider_message_id again → DUPLICATE (is_new=False)
- Same ID different provider → allowed (different conversation)
- Different ID same sender → allowed
- Concurrent duplicate → exactly one wins
- Repository survives new instance
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

_backend_root = str(Path(__file__).resolve().parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from modules.db.pool import (  # noqa: E402
    close_pool,
    create_pool,
    open_pool,
)
from modules.db.settings import get_database_settings  # noqa: E402
from modules.db.transaction import transaction  # noqa: E402
from modules.flow.repository import FlowPostgresRepository  # noqa: E402
from modules.messaging.domain.messages import InboundMessage  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pool = None
_loop = None


def _get_pool():
    global _pool, _loop
    if _pool is None:
        _loop = asyncio.new_event_loop()
        settings = get_database_settings(min_size=2, max_size=5)
        _pool = create_pool(settings)
        _loop.run_until_complete(open_pool(_pool))
    return _pool


def _uid() -> str:
    """Generate a short unique ID for test isolation."""
    return uuid.uuid4().hex[:12]


def _make_inbound(
    *,
    provider: str = "gupshup",
    message_id: str | None = None,
    thread_id: str | None = None,
    sender: str = "5491122334455",
    text: str = "Poste apagado en Calle 123",
) -> InboundMessage:
    uid = _uid()
    return InboundMessage(
        provider=provider,
        channel="whatsapp",
        external_message_id=message_id or f"msg-{uid}",
        external_thread_id=thread_id or f"thread-{uid}",
        sender=sender,
        recipients=("14155551234",),
        subject="",
        text_body=text,
        received_at=datetime.now(timezone.utc),
        metadata={"test": True},
    )


# ---------------------------------------------------------------------------
# First inbound → CLAIMED
# ---------------------------------------------------------------------------


def test_first_inbound_claimed() -> None:
    pool = _get_pool()
    repo = FlowPostgresRepository()
    msg = _make_inbound()

    async def _run():
        async with transaction(pool) as conn:
            return await repo.claim_whatsapp_inbound(conn, msg)

    result = _loop.run_until_complete(_run())
    assert result["is_new"] is True
    assert result["conversation_id"]
    assert result["message_id"]


# ---------------------------------------------------------------------------
# Same ID again → DUPLICATE
# ---------------------------------------------------------------------------


def test_same_id_duplicate() -> None:
    pool = _get_pool()
    repo = FlowPostgresRepository()
    uid = _uid()
    mid = f"msg-dup-{uid}"
    tid = f"thread-dup-{uid}"
    msg1 = _make_inbound(message_id=mid, thread_id=tid)
    msg2 = _make_inbound(message_id=mid, thread_id=tid)

    async def _run():
        async with transaction(pool) as conn:
            r1 = await repo.claim_whatsapp_inbound(conn, msg1)
        async with transaction(pool) as conn:
            r2 = await repo.claim_whatsapp_inbound(conn, msg2)
        return r1, r2

    r1, r2 = _loop.run_until_complete(_run())
    assert r1["is_new"] is True
    assert r2["is_new"] is False
    assert r1["conversation_id"] == r2["conversation_id"]


# ---------------------------------------------------------------------------
# Same ID different provider → allowed
# ---------------------------------------------------------------------------


def test_same_id_different_provider_allowed() -> None:
    pool = _get_pool()
    repo = FlowPostgresRepository()
    uid = _uid()
    mid = f"msg-cross-{uid}"
    msg1 = _make_inbound(
        provider="gupshup",
        message_id=mid,
        thread_id=f"thread-cross-gupshup-{uid}",
    )
    msg2 = _make_inbound(
        provider="meta",
        message_id=mid,
        thread_id=f"thread-cross-meta-{uid}",
    )

    async def _run():
        async with transaction(pool) as conn:
            r1 = await repo.claim_whatsapp_inbound(conn, msg1)
        async with transaction(pool) as conn:
            r2 = await repo.claim_whatsapp_inbound(conn, msg2)
        return r1, r2

    r1, r2 = _loop.run_until_complete(_run())
    assert r1["is_new"] is True
    assert r2["is_new"] is True
    assert r1["conversation_id"] != r2["conversation_id"]


# ---------------------------------------------------------------------------
# Different ID same sender → allowed
# ---------------------------------------------------------------------------


def test_different_id_same_sender_allowed() -> None:
    pool = _get_pool()
    repo = FlowPostgresRepository()
    uid = _uid()
    msg1 = _make_inbound(
        message_id=f"msg-sender-a-{uid}",
        thread_id=f"thread-sender-a-{uid}",
        sender="5491122334455",
    )
    msg2 = _make_inbound(
        message_id=f"msg-sender-b-{uid}",
        thread_id=f"thread-sender-b-{uid}",
        sender="5491122334455",
    )

    async def _run():
        async with transaction(pool) as conn:
            r1 = await repo.claim_whatsapp_inbound(conn, msg1)
        async with transaction(pool) as conn:
            r2 = await repo.claim_whatsapp_inbound(conn, msg2)
        return r1, r2

    r1, r2 = _loop.run_until_complete(_run())
    assert r1["is_new"] is True
    assert r2["is_new"] is True


# ---------------------------------------------------------------------------
# Duplicate returns same conversation_id
# ---------------------------------------------------------------------------


def test_duplicate_returns_same_conversation() -> None:
    pool = _get_pool()
    repo = FlowPostgresRepository()
    uid = _uid()
    msg = _make_inbound(message_id=f"msg-conv-{uid}", thread_id=f"thread-conv-{uid}")

    async def _run():
        async with transaction(pool) as conn:
            r1 = await repo.claim_whatsapp_inbound(conn, msg)
        async with transaction(pool) as conn:
            r2 = await repo.claim_whatsapp_inbound(conn, msg)
        return r1, r2

    r1, r2 = _loop.run_until_complete(_run())
    assert r1["conversation_id"] == r2["conversation_id"]
    assert r1["is_new"] is True
    assert r2["is_new"] is False


# ---------------------------------------------------------------------------
# Concurrent duplicate → exactly one wins
# ---------------------------------------------------------------------------


def test_concurrent_duplicate_exactly_one_wins() -> None:
    pool = _get_pool()
    repo = FlowPostgresRepository()
    uid = _uid()
    msg = _make_inbound(message_id=f"msg-conc-{uid}", thread_id=f"thread-conc-{uid}")

    async def _run():
        async def claim():
            async with transaction(pool) as conn:
                return await repo.claim_whatsapp_inbound(conn, msg)

        return await asyncio.gather(claim(), claim(), return_exceptions=True)

    results = _loop.run_until_complete(_run())
    successes = [r for r in results if isinstance(r, dict)]
    assert len(successes) == 2
    new_count = sum(1 for r in successes if r["is_new"])
    dup_count = sum(1 for r in successes if not r["is_new"])
    assert new_count == 1
    assert dup_count == 1


# ---------------------------------------------------------------------------
# Repository survives new instance
# ---------------------------------------------------------------------------


def test_repository_survives_new_instance() -> None:
    pool = _get_pool()
    uid = _uid()
    msg = _make_inbound(message_id=f"msg-restart-{uid}", thread_id=f"thread-restart-{uid}")

    async def _run():
        repo1 = FlowPostgresRepository()
        async with transaction(pool) as conn:
            r1 = await repo1.claim_whatsapp_inbound(conn, msg)

        repo2 = FlowPostgresRepository()
        async with transaction(pool) as conn:
            r2 = await repo2.claim_whatsapp_inbound(conn, msg)
        return r1, r2

    r1, r2 = _loop.run_until_complete(_run())
    assert r1["is_new"] is True
    assert r2["is_new"] is False


# ---------------------------------------------------------------------------
# Webhook-style claim via WhatsAppMessageClaimer
# ---------------------------------------------------------------------------


def test_claimer_claim_new() -> None:
    from modules.messaging.whatsapp_claim import WhatsAppMessageClaimer

    pool = _get_pool()
    uid = _uid()
    claimer = WhatsAppMessageClaimer(pool=pool, repository=FlowPostgresRepository())
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "test claimer new",
            "timestamp": "1700000000",
            "id": f"msg-claimer-new-{uid}",
        }
    }
    result = _loop.run_until_complete(claimer.claim(payload))
    assert result is not None
    assert result.is_new is True
    assert result.provider_message_id == f"msg-claimer-new-{uid}"


def test_claimer_claim_duplicate() -> None:
    from modules.messaging.whatsapp_claim import WhatsAppMessageClaimer

    pool = _get_pool()
    uid = _uid()
    claimer = WhatsAppMessageClaimer(pool=pool, repository=FlowPostgresRepository())
    payload = {
        "payload": {
            "from": "5491122334455",
            "to": "14155551234",
            "text": "test claimer dup",
            "timestamp": "1700000000",
            "id": f"msg-claimer-dup-{uid}",
        }
    }
    r1 = _loop.run_until_complete(claimer.claim(payload))
    r2 = _loop.run_until_complete(claimer.claim(payload))
    assert r1.is_new is True
    assert r2.is_new is False
    assert r1.conversation_id == r2.conversation_id


def test_claimer_returns_none_for_status_event() -> None:
    from modules.messaging.whatsapp_claim import WhatsAppMessageClaimer

    pool = _get_pool()
    claimer = WhatsAppMessageClaimer(pool=pool, repository=FlowPostgresRepository())
    payload = {"status": {"messageId": "m1", "status": "delivered"}}
    result = _loop.run_until_complete(claimer.claim(payload))
    assert result is None


def test_claimer_returns_none_for_garbage() -> None:
    from modules.messaging.whatsapp_claim import WhatsAppMessageClaimer

    pool = _get_pool()
    claimer = WhatsAppMessageClaimer(pool=pool, repository=FlowPostgresRepository())
    payload = {"foo": "bar"}
    result = _loop.run_until_complete(claimer.claim(payload))
    assert result is None

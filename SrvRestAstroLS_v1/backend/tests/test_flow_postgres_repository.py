import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.flow.domain import CandidateRequest, ConversationState
from modules.flow.repository import FlowPostgresRepository
from modules.messaging.domain import InboundMessage


@pytest.mark.skipif(
    os.environ.get("TEAM360_FLOW_POSTGRES_TEST") != "1",
    reason="requires migration 011 on the configured Team360 PostgreSQL",
)
def test_real_postgres_repository_persists_and_confirms_without_duplicates():
    async def exercise():
        suffix = uuid4().hex
        message = InboundMessage(
            provider="gmail",
            channel="email",
            external_message_id=f"integration-message-{suffix}",
            external_thread_id=f"integration-thread-{suffix}",
            sender="integration@example.com",
            recipients=("mesaentrada@example.com",),
            subject="Flow repository integration",
            text_body="Poste sin luz y árbol caído",
            received_at=datetime.now(timezone.utc),
            metadata={"rfc_message_id": f"<{suffix}@example.com>"},
        )
        repo = FlowPostgresRepository()
        settings = get_database_settings(min_size=1, max_size=1)
        async with await psycopg.AsyncConnection.connect(
            settings.dsn, row_factory=dict_row
        ) as conn:
            try:
                claimed = await repo.claim_inbound(conn, message)
                duplicate = await repo.claim_inbound(conn, message)
                assert claimed.is_new is True
                assert duplicate.is_new is False
                requests = (
                    CandidateRequest("Reparar poste", "alumbrado", "Olleros"),
                    CandidateRequest("Retirar árbol", "arbolado", "misma cuadra"),
                )
                await repo.add_interpretation(
                    conn,
                    conversation_id=claimed.conversation_id,
                    source_message_id=claimed.message_id,
                    phase="initial",
                    outcome="requests",
                    payload={"requests": [item.as_dict() for item in requests]},
                    provider="mock",
                    model="mock",
                    usage={},
                    latency_ms=1,
                )
                await repo.replace_candidates(
                    conn,
                    conversation_id=claimed.conversation_id,
                    revision=0,
                    requests=requests,
                )
                active = await repo.active_candidates(conn, claimed.conversation_id)
                assert len(active) == 2
                confirmed = await repo.confirm_active_candidates(conn, claimed.conversation_id)
                await repo.update_state(conn, claimed.conversation_id, ConversationState.CONFIRMED)
                assert confirmed == 2
                evidence = await repo.conversation_evidence(conn, message.external_thread_id)
                assert evidence["confirmed"] == 2
                assert evidence["interpretations"] == 1
            finally:
                await conn.rollback()

    asyncio.run(exercise())

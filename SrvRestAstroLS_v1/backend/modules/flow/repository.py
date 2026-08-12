"""PostgreSQL repository for Flow email intake operational truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from modules.db.transaction import execute, fetch_all, fetch_one
from modules.messaging.domain import InboundMessage

from .domain.models import CandidateRequest
from .domain.states import ConversationState


@dataclass(frozen=True, slots=True)
class ClaimedInbound:
    is_new: bool
    message_id: str | None
    conversation_id: str
    state: ConversationState
    revision: int


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    id: str
    ordinal: int
    request: CandidateRequest


class FlowPostgresRepository:
    """All Flow SQL lives here and receives a caller-owned connection."""

    async def claim_inbound(
        self, conn: AsyncConnection, message: InboundMessage
    ) -> ClaimedInbound:
        conversation = await fetch_one(
            conn,
            """
            insert into flow_conversations (
                provider, channel, external_thread_id, citizen_address, subject
            ) values (
                %(provider)s, %(channel)s, %(external_thread_id)s,
                %(citizen_address)s, %(subject)s
            )
            on conflict (provider, external_thread_id) do update set
                updated_at_utc = now()
            returning id::text, state, candidate_revision
            """,
            {
                "provider": message.provider,
                "channel": message.channel,
                "external_thread_id": message.external_thread_id,
                "citizen_address": message.sender,
                "subject": message.subject,
            },
        )
        if conversation is None:
            raise RuntimeError("Flow conversation upsert returned no row.")
        stored_message = await fetch_one(
            conn,
            """
            insert into flow_messages (
                conversation_id, provider, external_message_id, direction,
                sender_address, recipients_jsonb, subject, text_body,
                occurred_at_utc, metadata_jsonb, processed_at_utc
            ) values (
                %(conversation_id)s, %(provider)s, %(external_message_id)s, 'inbound',
                %(sender_address)s, %(recipients_jsonb)s, %(subject)s, %(text_body)s,
                %(occurred_at_utc)s, %(metadata_jsonb)s, now()
            )
            on conflict (provider, external_message_id) do nothing
            returning id::text
            """,
            {
                "conversation_id": conversation["id"],
                "provider": message.provider,
                "external_message_id": message.external_message_id,
                "sender_address": message.sender,
                "recipients_jsonb": Jsonb(list(message.recipients)),
                "subject": message.subject,
                "text_body": message.text_body,
                "occurred_at_utc": message.received_at,
                "metadata_jsonb": Jsonb(dict(message.metadata)),
            },
        )
        return ClaimedInbound(
            is_new=stored_message is not None,
            message_id=stored_message["id"] if stored_message else None,
            conversation_id=conversation["id"],
            state=ConversationState(conversation["state"]),
            revision=int(conversation["candidate_revision"]),
        )

    async def active_candidates(
        self, conn: AsyncConnection, conversation_id: str
    ) -> tuple[StoredCandidate, ...]:
        rows = await fetch_all(
            conn,
            """
            select id::text, ordinal, description, tentative_category,
                   location_text, missing_data_jsonb, context_notes, confidence
            from flow_request_candidates
            where conversation_id = %(conversation_id)s and status = 'ACTIVE'
            order by ordinal
            """,
            {"conversation_id": conversation_id},
        )
        return tuple(
            StoredCandidate(
                id=row["id"],
                ordinal=int(row["ordinal"]),
                request=CandidateRequest(
                    description=row["description"],
                    tentative_category=row["tentative_category"],
                    location_text=row["location_text"],
                    missing_data=tuple(row["missing_data_jsonb"]),
                    context_notes=row["context_notes"],
                    confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                ),
            )
            for row in rows
        )

    async def add_interpretation(
        self,
        conn: AsyncConnection,
        *,
        conversation_id: str,
        source_message_id: str,
        phase: str,
        outcome: str,
        payload: dict[str, Any],
        provider: str,
        model: str,
        usage: dict[str, Any],
        latency_ms: int | None,
    ) -> None:
        await execute(
            conn,
            """
            insert into flow_interpretations (
                conversation_id, source_message_id, phase, outcome,
                payload_jsonb, ai_provider, ai_model, usage_jsonb, latency_ms
            ) values (
                %(conversation_id)s, %(source_message_id)s, %(phase)s, %(outcome)s,
                %(payload_jsonb)s, %(ai_provider)s, %(ai_model)s,
                %(usage_jsonb)s, %(latency_ms)s
            )
            on conflict (source_message_id) do nothing
            """,
            {
                "conversation_id": conversation_id,
                "source_message_id": source_message_id,
                "phase": phase,
                "outcome": outcome,
                "payload_jsonb": Jsonb(payload),
                "ai_provider": provider,
                "ai_model": model,
                "usage_jsonb": Jsonb(usage),
                "latency_ms": latency_ms,
            },
        )

    async def replace_candidates(
        self,
        conn: AsyncConnection,
        *,
        conversation_id: str,
        revision: int,
        requests: tuple[CandidateRequest, ...],
    ) -> int:
        await execute(
            conn,
            """
            update flow_request_candidates
            set status = 'SUPERSEDED', updated_at_utc = now()
            where conversation_id = %(conversation_id)s and status = 'ACTIVE'
            """,
            {"conversation_id": conversation_id},
        )
        new_revision = revision + 1
        for ordinal, request in enumerate(requests, start=1):
            await execute(
                conn,
                """
                insert into flow_request_candidates (
                    conversation_id, revision, ordinal, description,
                    tentative_category, location_text, missing_data_jsonb,
                    context_notes, confidence
                ) values (
                    %(conversation_id)s, %(revision)s, %(ordinal)s, %(description)s,
                    %(tentative_category)s, %(location_text)s, %(missing_data_jsonb)s,
                    %(context_notes)s, %(confidence)s
                )
                """,
                {
                    "conversation_id": conversation_id,
                    "revision": new_revision,
                    "ordinal": ordinal,
                    "description": request.description,
                    "tentative_category": request.tentative_category,
                    "location_text": request.location_text,
                    "missing_data_jsonb": Jsonb(list(request.missing_data)),
                    "context_notes": request.context_notes,
                    "confidence": request.confidence,
                },
            )
        await execute(
            conn,
            """
            update flow_conversations
            set candidate_revision = %(revision)s, updated_at_utc = now()
            where id = %(conversation_id)s
            """,
            {"revision": new_revision, "conversation_id": conversation_id},
        )
        return new_revision

    async def update_state(
        self,
        conn: AsyncConnection,
        conversation_id: str,
        state: ConversationState,
    ) -> None:
        await execute(
            conn,
            """
            update flow_conversations
            set state = %(state)s, updated_at_utc = now()
            where id = %(conversation_id)s
            """,
            {"state": state.value, "conversation_id": conversation_id},
        )

    async def record_outbound(
        self,
        conn: AsyncConnection,
        *,
        conversation_id: str,
        external_message_id: str,
        sender: str,
        recipient: str,
        subject: str,
        body: str,
        external_thread_id: str,
    ) -> None:
        await execute(
            conn,
            """
            insert into flow_messages (
                conversation_id, provider, external_message_id, direction,
                sender_address, recipients_jsonb, subject, text_body,
                occurred_at_utc, metadata_jsonb, processed_at_utc
            ) values (
                %(conversation_id)s, 'gmail', %(external_message_id)s, 'outbound',
                %(sender)s, %(recipients_jsonb)s, %(subject)s, %(text_body)s,
                now(), %(metadata_jsonb)s, now()
            )
            on conflict (provider, external_message_id) do nothing
            """,
            {
                "conversation_id": conversation_id,
                "external_message_id": external_message_id,
                "sender": sender,
                "recipients_jsonb": Jsonb([recipient]),
                "subject": subject,
                "text_body": body,
                "metadata_jsonb": Jsonb({"external_thread_id": external_thread_id}),
            },
        )

    async def confirm_active_candidates(
        self, conn: AsyncConnection, conversation_id: str
    ) -> int:
        rows = await fetch_all(
            conn,
            """
            insert into flow_requests (
                conversation_id, source_candidate_id, description,
                tentative_category, location_text, missing_data_jsonb,
                context_notes, confidence, status, confirmed_at_utc
            )
            select conversation_id, id, description, tentative_category,
                   location_text, missing_data_jsonb, context_notes, confidence,
                   'CONFIRMED', now()
            from flow_request_candidates
            where conversation_id = %(conversation_id)s and status = 'ACTIVE'
            on conflict (source_candidate_id) do nothing
            returning id::text
            """,
            {"conversation_id": conversation_id},
        )
        await execute(
            conn,
            """
            update flow_request_candidates
            set status = 'CONFIRMED', updated_at_utc = now()
            where conversation_id = %(conversation_id)s and status = 'ACTIVE'
            """,
            {"conversation_id": conversation_id},
        )
        return len(rows)

    async def conversation_evidence(
        self, conn: AsyncConnection, external_thread_id: str
    ) -> dict[str, Any] | None:
        conversation = await fetch_one(
            conn,
            """
            select id::text, external_thread_id, state, candidate_revision,
                   created_at_utc, updated_at_utc
            from flow_conversations
            where provider = 'gmail' and external_thread_id = %(thread_id)s
            """,
            {"thread_id": external_thread_id},
        )
        if conversation is None:
            return None
        counts = await fetch_one(
            conn,
            """
            select
              (select count(*) from flow_messages where conversation_id = %(id)s) as messages,
              (select count(*) from flow_interpretations where conversation_id = %(id)s) as interpretations,
              (select count(*) from flow_request_candidates where conversation_id = %(id)s) as candidates,
              (select count(*) from flow_requests where conversation_id = %(id)s and status = 'CONFIRMED') as confirmed
            """,
            {"id": conversation["id"]},
        )
        return {**conversation, **(counts or {})}

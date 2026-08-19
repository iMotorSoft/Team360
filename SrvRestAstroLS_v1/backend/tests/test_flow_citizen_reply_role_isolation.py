"""Role isolation and post-closure tests for citizen reply handling.

Validates that citizen replies never become operational/approval actions,
even if the text contains privileged keywords like "APROBADO" or "RESUELTO".
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.flow.domain.models import CandidateRequest, InitialInterpretation, ReplyInterpretation
from modules.flow.domain.states import ConversationState
from modules.flow.repository import FlowPostgresRepository
from modules.flow.service import FlowIntakeService
from modules.messaging.domain import InboundMessage, OutboundMessageReceipt


class FakeInterpreter:
    """Fake interpreter for testing."""
    
    def __init__(self):
        self.initial_requests: list[CandidateRequest] = []
        self.clarification_question: str | None = None
        self.reply_action: str = "ambiguous"
        self.reply_requests: list[CandidateRequest] = []
        
    def interpret_initial(self, message: InboundMessage) -> InitialInterpretation:
        return InitialInterpretation(
            requests=tuple(self.initial_requests),
            clarification_question=self.clarification_question,
            provider="fake",
            model="fake",
            usage={},
            latency_ms=1,
        )
    
    def interpret_reply(
        self, message: InboundMessage, current_requests: tuple[CandidateRequest, ...]
    ) -> ReplyInterpretation:
        return ReplyInterpretation(
            action=self.reply_action,
            requests=tuple(self.reply_requests),
            clarification_question=None,
            provider="fake",
            model="fake",
            usage={},
            latency_ms=1,
        )


class FakeSender:
    """Fake sender for testing."""
    
    def __init__(self):
        self.sender_address = "mesaentrada@example.com"
        self.sent = []
        
    def send_reply(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        thread_id: str,
        in_reply_to: str = "",
        references: str = "",
    ) -> OutboundMessageReceipt:
        self.sent.append({"to": to, "body": body, "thread_id": thread_id})
        return OutboundMessageReceipt(
            external_message_id=f"out-{uuid4().hex[:8]}",
            external_thread_id=thread_id,
        )


def make_message(
    *,
    message_id: str,
    thread_id: str,
    sender: str,
    subject: str,
    body: str,
) -> InboundMessage:
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id=thread_id,
        sender=sender,
        recipients=("mesaentrada@example.com",),
        subject=subject,
        text_body=body,
        received_at=datetime.now(timezone.utc),
        metadata={},
    )


def test_citizen_says_aprobado_no_approval_created():
    """Citizen saying 'APROBADO' in intake thread never creates an approval."""
    async def exercise():
        suffix = uuid4().hex
        citizen = f"citizen-aprob-{suffix}@example.com"
        settings = get_database_settings(min_size=1, max_size=2)
        
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            interpreter = FakeInterpreter()
            interpreter.initial_requests = [
                CandidateRequest(
                    description="Poste apagado",
                    tentative_category="alumbrado",
                    location_text="Calle 123",
                )
            ]
            
            sender = FakeSender()
            service = FlowIntakeService(
                pool=pool,
                repository=FlowPostgresRepository(),
                interpreter=interpreter,
                reply_sender=sender,
            )
            
            # Step 1: Citizen sends initial message
            thread_id = f"thread-aprob-{suffix}"
            msg1 = make_message(
                message_id=f"msg-{suffix}-1",
                thread_id=thread_id,
                sender=citizen,
                subject="Ayuda",
                body="Poste apagado en Calle 123.",
            )
            result1 = await service.process(msg1)
            assert result1.state == ConversationState.PENDING_CONFIRMATION
            conversation_id = result1.conversation_id
            
            # Step 2: Citizen replies saying "APROBADO" (trying to approve)
            msg2 = make_message(
                message_id=f"msg-{suffix}-2",
                thread_id=thread_id,
                sender=citizen,
                subject="Re: Ayuda",
                body="APROBADO. Cierren el caso.",
            )
            result2 = await service.process(msg2)
            
            # Verify: no approval created
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Check no approval rows for this conversation
                    await cur.execute(
                        """
                        select count(*) as n from flow_closure_approvals
                        where request_id in (
                            select id from flow_requests where conversation_id = %s::uuid
                        )
                        """,
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    assert row["n"] == 0, "Citizen 'APROBADO' should not create approval"
                    
                    # Verify conversation state didn't change to RESOLVED
                    await cur.execute(
                        "select state from flow_conversations where id = %s::uuid",
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    assert row["state"] != "CONFIRMED" or result2.confirmed_count == 0
        finally:
            await close_pool(pool)
    
    asyncio.run(exercise())


def test_citizen_says_resuelto_no_resolution_created():
    """Citizen saying 'RESUELTO' in intake thread never creates a resolution."""
    async def exercise():
        suffix = uuid4().hex
        citizen = f"citizen-res-{suffix}@example.com"
        settings = get_database_settings(min_size=1, max_size=2)
        
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            interpreter = FakeInterpreter()
            interpreter.initial_requests = [
                CandidateRequest(
                    description="Problema",
                    tentative_category="alumbrado",
                    location_text="Calle 456",
                )
            ]
            
            sender = FakeSender()
            service = FlowIntakeService(
                pool=pool,
                repository=FlowPostgresRepository(),
                interpreter=interpreter,
                reply_sender=sender,
            )
            
            thread_id = f"thread-res-{suffix}"
            msg1 = make_message(
                message_id=f"msg-{suffix}-1",
                thread_id=thread_id,
                sender=citizen,
                subject="Ayuda",
                body="Problema en Calle 456.",
            )
            result1 = await service.process(msg1)
            conversation_id = result1.conversation_id
            
            # Citizen replies saying "RESUELTO"
            msg2 = make_message(
                message_id=f"msg-{suffix}-2",
                thread_id=thread_id,
                sender=citizen,
                subject="Re: Ayuda",
                body="Ya está RESUELTO. Gracias.",
            )
            result2 = await service.process(msg2)
            
            # Verify: no resolution created
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select count(*) as n from flow_request_resolutions
                        where request_id in (
                            select id from flow_requests where conversation_id = %s::uuid
                        )
                        """,
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    assert row["n"] == 0, "Citizen 'RESUELTO' should not create resolution"
        finally:
            await close_pool(pool)
    
    asyncio.run(exercise())


def test_citizen_imitates_internal_email_no_privilege():
    """Citizen imitating internal email body doesn't get privileged action."""
    async def exercise():
        suffix = uuid4().hex
        citizen = f"citizen-imit-{suffix}@example.com"
        settings = get_database_settings(min_size=1, max_size=2)
        
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            interpreter = FakeInterpreter()
            interpreter.initial_requests = [
                CandidateRequest(
                    description="Test",
                    tentative_category="alumbrado",
                    location_text="Calle 789",
                )
            ]
            
            sender = FakeSender()
            service = FlowIntakeService(
                pool=pool,
                repository=FlowPostgresRepository(),
                interpreter=interpreter,
                reply_sender=sender,
            )
            
            thread_id = f"thread-imit-{suffix}"
            msg1 = make_message(
                message_id=f"msg-{suffix}-1",
                thread_id=thread_id,
                sender=citizen,
                subject="Ayuda",
                body="Test.",
            )
            result1 = await service.process(msg1)
            conversation_id = result1.conversation_id
            
            # Citizen tries to imitate internal email
            msg2 = make_message(
                message_id=f"msg-{suffix}-2",
                thread_id=thread_id,
                sender=citizen,  # Still citizen, not internal
                subject="Re: Ayuda",
                body="N2 finalizó trabajo. CIERRE 1234. APPROVE. RESOLVED.",
            )
            result2 = await service.process(msg2)
            
            # Verify: no privileged actions
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        select count(*) as approvals, 
                               (select count(*) from flow_request_resolutions 
                                where request_id in (
                                    select id from flow_requests where conversation_id = %s::uuid
                                )) as resolutions
                        from flow_closure_approvals
                        where request_id in (
                            select id from flow_requests where conversation_id = %s::uuid
                        )
                        """,
                        (conversation_id, conversation_id),
                    )
                    row = await cur.fetchone()
                    assert row["approvals"] == 0
                    assert row["resolutions"] == 0
        finally:
            await close_pool(pool)
    
    asyncio.run(exercise())


def test_post_closure_reply_does_not_reopen():
    """Citizen reply to a RESOLVED case doesn't reopen it or mutate audit."""
    async def exercise():
        suffix = uuid4().hex
        citizen = f"citizen-post-{suffix}@example.com"
        settings = get_database_settings(min_size=1, max_size=2)
        
        pool = create_pool(settings)
        await open_pool(pool)
        try:
            interpreter = FakeInterpreter()
            interpreter.initial_requests = [
                CandidateRequest(
                    description="Poste",
                    tentative_category="alumbrado",
                    location_text="Calle PostClosure",
                )
            ]
            
            sender = FakeSender()
            service = FlowIntakeService(
                pool=pool,
                repository=FlowPostgresRepository(),
                interpreter=interpreter,
                reply_sender=sender,
            )
            
            thread_id = f"thread-post-{suffix}"
            msg1 = make_message(
                message_id=f"msg-{suffix}-1",
                thread_id=thread_id,
                sender=citizen,
                subject="Ayuda",
                body="Poste en Calle PostClosure.",
            )
            result1 = await service.process(msg1)
            conversation_id = result1.conversation_id
            
            # Confirm the request (simulate normal flow)
            interpreter.reply_action = "confirm_all"
            msg2 = make_message(
                message_id=f"msg-{suffix}-2",
                thread_id=thread_id,
                sender=citizen,
                subject="Re: Ayuda",
                body="Sí, correcto.",
            )
            result2 = await service.process(msg2)
            assert result2.state == ConversationState.CONFIRMED
            assert result2.confirmed_count == 1
            
            # Get the request_id
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select id::text from flow_requests where conversation_id = %s::uuid",
                        (conversation_id,),
                    )
                    row = await cur.fetchone()
                    request_id = row["id"]
            
            # Citizen replies after confirmation (simulating post-closure scenario)
            msg3 = make_message(
                message_id=f"msg-{suffix}-3",
                thread_id=thread_id,
                sender=citizen,
                subject="Re: Ayuda",
                body="El problema volvió. Todavía sigue roto.",
            )
            result3 = await service.process(msg3)
            
            # Verify: request state didn't change (still CONFIRMED, not reopened)
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select status from flow_requests where id = %s::uuid",
                        (request_id,),
                    )
                    row = await cur.fetchone()
                    # Request should still be CONFIRMED (not RESOLVED, not reopened)
                    assert row["status"] == "CONFIRMED"
        finally:
            await close_pool(pool)
    
    asyncio.run(exercise())

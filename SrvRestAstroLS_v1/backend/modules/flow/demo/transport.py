"""Deterministic fake transport and interpreters for the Flow demo harness.

These replace only external adapters (messaging providers and model gateway).
The Flow domain services are exercised unchanged and every persisted fact is
written by the real repositories.
"""

from __future__ import annotations

from uuid import uuid4

from modules.messaging.domain import InboundMessage, OutboundMessageReceipt

from ..domain import (
    ApprovalDecision,
    ApprovalDecisionResult,
    CandidateRequest,
    InitialInterpretation,
    OperationalAction,
    OperationalInterpretation,
    ReplyInterpretation,
)

DEMO_SENDER = "mesaentrada@alquimiablue.com"


class DemoReplySender:
    """FlowReplySenderPort used by the citizen intake confirmation flow."""

    sender_address = DEMO_SENDER

    def __init__(self) -> None:
        self.prefix = uuid4().hex[:8]
        self.sent: list[dict] = []

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
        self.sent.append(
            {"to": to, "subject": subject, "thread_id": thread_id}
        )
        return OutboundMessageReceipt(
            f"{self.prefix}-out-{len(self.sent)}", thread_id
        )


class DemoRoutingSender:
    """RoutingMessageSenderPort used by routing, escalation and closure."""

    sender_address = DEMO_SENDER

    def __init__(self) -> None:
        self.prefix = uuid4().hex[:8]
        self.sent: list[dict] = []

    def find_sent_message_by_rfc_message_id(self, rfc_message_id: str) -> str | None:
        return None

    def find_sent_message_by_reference(
        self, reference: str, *, to: str | None = None
    ) -> str | None:
        return None

    def get_message_rfc_id(self, message_id: str) -> str | None:
        return f"<observed-{message_id}@mail.gmail.com>"

    def send_message(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        rfc_message_id: str | None = None,
    ) -> str:
        self.sent.append({"to": to, "subject": subject, "rfc": rfc_message_id})
        return f"{self.prefix}-gmail-{len(self.sent)}"


class DemoIntakeInterpreter:
    """FlowIntakeInterpreterPort: classifies the synthetic LaMuni request."""

    def __init__(self, description: str, location: str, marker: str) -> None:
        self._description = description
        self._location = location
        self._marker = marker

    def interpret_initial(self, message: InboundMessage) -> InitialInterpretation:
        request = CandidateRequest(
            description=f"{self._description} {self._marker}",
            tentative_category="alumbrado",
            location_text=self._location,
            missing_data=(),
            context_notes="LAMUNI_DEMO",
            confidence=1.0,
        )
        return InitialInterpretation(
            requests=(request,),
            clarification_question=None,
            provider="demo",
            model="demo",
            usage={},
            latency_ms=1,
        )

    def interpret_reply(
        self,
        message: InboundMessage,
        current_requests: tuple[CandidateRequest, ...],
    ) -> ReplyInterpretation:
        return ReplyInterpretation(
            action="confirm_all",
            requests=(),
            clarification_question=None,
            provider="demo",
            model="demo",
            usage={},
            latency_ms=1,
        )


class DemoOperationalInterpreter:
    """OperationalInterpreterPort: technical reply declares resolution."""

    def interpret(self, message: InboundMessage) -> OperationalInterpretation:
        return OperationalInterpretation(
            action=OperationalAction.RESOLUTION_PROPOSED,
            summary="Trabajo finalizado.",
            provider="demo",
            model="demo",
            usage={},
            latency_ms=1,
        )


class DemoApprovalInterpreter:
    """ApprovalInterpreterPort: supervisor approves the closure."""

    def interpret(
        self, text: str, *, correlation_id: str | None = None
    ) -> ApprovalDecisionResult:
        return ApprovalDecisionResult(ApprovalDecision.APPROVE, "")

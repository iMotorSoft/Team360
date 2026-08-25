"""Supervisor closure orchestration: propose resolution, decide approval."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from modules.db.transaction import transaction
from modules.messaging.domain import InboundMessage

from .approval_ai import ApprovalInterpreterPort
from .audit_repository import FlowAuditRepository, sha256_of_snapshot
from .closure_repository import FlowClosurePostgresRepository
from .domain import (
    AUDIT_SCHEMA_VERSION,
    ApprovalDecision,
    ClosureApproval,
    ClosureApprovalStatus,
    OperationalInterpretation,
    OperationalRoutingContext,
    ResolutionStatus,
    approval_rfc_message_id,
    approval_sender_authorized,
    approval_token_for,
    approval_token_from_subject,
    is_automated_message,
    rfc_reference_ids,
)
from .routing_service import RoutingMessageSenderPort, _safe_observed_rfc_message_id


@dataclass(frozen=True, slots=True)
class ApprovalEmail:
    destination: str
    subject: str
    body: str
    rfc_message_id: str


@dataclass(frozen=True, slots=True)
class ClosureProposalResult:
    resolution_id: str | None = None
    approval_id: str | None = None
    approval_token: str | None = None
    approver_level: int | None = None
    approver_destination: str | None = None
    outbound_external_message_id: str | None = None
    sent: bool = False
    reconciled: bool = False
    idempotent: bool = False
    request_status: str = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class ApprovalProcessResult:
    matched: bool
    processed: bool = False
    authorized: bool = True
    approval_id: str | None = None
    request_id: str | None = None
    resolution_id: str | None = None
    decision: ApprovalDecision | None = None
    correlation_method: str | None = None
    idempotent: bool = False
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CorrelatedApprovalReply:
    approval: ClosureApproval
    method: str


def build_approval_email(
    *,
    request_id: str,
    approval_token: str,
    reported_level: int,
    responder: str,
    resolution_text: str,
    proposed_at,
    brief: dict,
    rfc_message_id: str | None = None,
) -> ApprovalEmail:
    destination = brief.get("approver_destination") or ""
    lines = [
        "Se requiere aprobación de cierre.",
        "",
        f"Caso: {request_id}",
        f"Sector: {brief.get('sector_name') or 'No informado'}",
        f"Descripción original: {brief.get('description') or ''}",
        f"Ubicación: {brief.get('location_text') or 'No informada'}",
        f"Nivel que informa resolución: N{reported_level}",
        f"Responsable/remitente: {responder}",
        f"Resolución informada: {resolution_text}",
        f"Fecha/hora de propuesta: {proposed_at.isoformat()}",
        "",
    ]
    chain = brief.get("chain") or []
    if chain:
        lines.append("Cadena de niveles:")
        for item in chain:
            lines.append(
                f"  N{item['level']} ({item['destination']}) — {item['work_status']}"
            )
        lines.append("")
    slas = brief.get("slas") or []
    if slas:
        lines.append("Resumen SLA:")
        for item in slas:
            lines.append(f"  N{item['level']} {item['sla_status']}")
        lines.append("")
    lines.extend(
        [
            "Responder APROBAR para autorizar el cierre.",
            "Responder RECHAZAR: <motivo> para devolver el caso.",
        ]
    )
    return ApprovalEmail(
        destination=destination,
        subject=(
            f"[Team360 Flow][CIERRE][R:{approval_token}][{request_id}] "
            "Aprobación de cierre"
        ),
        body="\n".join(lines),
        rfc_message_id=rfc_message_id or approval_rfc_message_id(approval_token),
    )


def approval_resend_rfc_message_id(approval_token: str) -> str:
    """Return a new transport id while keeping the domain approval token."""
    return (
        f"<team360-flow-closure-{approval_token}-resend-"
        f"{uuid4().hex}@alquimiablue.com>"
    )


class ApprovalResendError(RuntimeError):
    """Base error for the guarded pending-approval resend operation."""


class ApprovalResendNotFoundError(ApprovalResendError):
    pass


class ApprovalResendConflictError(ApprovalResendError):
    pass


class ApprovalResendValidationError(ApprovalResendError):
    pass


@dataclass(frozen=True, slots=True)
class ApprovalResendResult:
    request_id: str
    approval_id: str
    status: str
    approver_level: int
    approver_destination: str
    approval_token: str
    subject: str
    outbound_external_message_id: str
    correlation_preserved: bool = True


class FlowClosureService:
    def __init__(
        self,
        *,
        pool: AsyncConnectionPool,
        repository: FlowClosurePostgresRepository,
        audit_repository: FlowAuditRepository,
        interpreter: ApprovalInterpreterPort,
        sender: RoutingMessageSenderPort | None,
    ) -> None:
        self._pool = pool
        self._repository = repository
        self._audit_repository = audit_repository
        self._interpreter = interpreter
        self._sender = sender

    async def resend_pending_approval(
        self, request_id: str
    ) -> ApprovalResendResult:
        """Re-send one existing pending approval without changing workflow state."""
        if self._sender is None:
            raise ApprovalResendValidationError(
                "No hay un emisor de correo disponible para reenviar la aprobación."
            )

        async with transaction(self._pool) as conn:
            lifecycle = await self._repository.get_request_lifecycle_for_update(
                conn, request_id
            )
            if lifecycle is None:
                raise ApprovalResendNotFoundError(
                    f"Flow request not found: {request_id}"
                )
            if lifecycle["status"] != "RESOLUTION_PENDING_APPROVAL":
                raise ApprovalResendConflictError(
                    "La solicitud de aprobación sólo puede reenviarse cuando el "
                    "caso está pendiente de aprobación."
                )

            approval = await self._repository.get_approval_by_request_for_update(
                conn, request_id
            )
            if approval is None:
                raise ApprovalResendValidationError(
                    "El caso no tiene una aprobación pendiente."
                )
            if approval.status not in {
                ClosureApprovalStatus.PENDING,
                ClosureApprovalStatus.DELIVERY_UNCERTAIN,
            }:
                raise ApprovalResendConflictError(
                    "La aprobación del caso ya no está pendiente."
                )

            resolution = await self._repository.get_resolution(
                conn, approval.resolution_id
            )
            if resolution is None or resolution.status != ResolutionStatus.PROPOSED:
                raise ApprovalResendValidationError(
                    "El caso no tiene una propuesta de resolución pendiente."
                )
            if not approval.approver_destination or "@" not in approval.approver_destination:
                raise ApprovalResendValidationError(
                    "La aprobación no tiene un destinatario válido."
                )

            brief = dict(await self._repository.get_case_brief(conn, request_id))
            brief["approver_destination"] = approval.approver_destination
            email = build_approval_email(
                request_id=request_id,
                approval_token=approval.approval_token,
                reported_level=approval.approver_level,
                responder=resolution.proposed_by,
                resolution_text=resolution.resolution_text,
                proposed_at=resolution.proposed_at,
                brief=brief,
                rfc_message_id=approval_resend_rfc_message_id(
                    approval.approval_token
                ),
            )
            try:
                external_id = self._sender.send_message(
                    to=email.destination,
                    subject=email.subject,
                    body=email.body,
                    rfc_message_id=email.rfc_message_id,
                )
                observed = _safe_observed_rfc_message_id(
                    self._sender, external_id
                )
                approval = await self._repository.mark_approval_sent(
                    conn,
                    approval.id,
                    external_id,
                    observed,
                    outbound_rfc_message_id=email.rfc_message_id,
                )
                context = await self._repository.get_request_context(
                    conn, request_id
                )
                if context is None:
                    raise ApprovalResendValidationError(
                        "No se pudo resolver la conversación del caso."
                    )
                await self._repository.record_approval_resend(
                    conn,
                    request_id=request_id,
                    conversation_id=context["conversation_id"],
                    approval_id=approval.id,
                    approver_level=approval.approver_level,
                    recipient=email.destination,
                    external_message_id=external_id,
                    subject=email.subject,
                    body=email.body,
                    sender_address=getattr(
                        self._sender, "sender_address", "mesaentrada@alquimiablue.com"
                    ),
                )
            except ApprovalResendError:
                raise
            except Exception as exc:
                await self._repository.mark_approval_delivery_uncertain(
                    conn, approval.id
                )
                raise ApprovalResendError(
                    "No se pudo reenviar la solicitud de aprobación."
                ) from exc

            return ApprovalResendResult(
                request_id=request_id,
                approval_id=approval.id,
                status=lifecycle["status"],
                approver_level=approval.approver_level,
                approver_destination=email.destination,
                approval_token=approval.approval_token,
                subject=email.subject,
                outbound_external_message_id=external_id,
            )

    async def propose_resolution(
        self,
        conn: AsyncConnection,
        *,
        context: OperationalRoutingContext,
        message: InboundMessage,
        interpretation: OperationalInterpretation,
    ) -> ClosureProposalResult:
        # Terminal / pending guard: locked read before any side effect so a
        # post-RESOLVED or already-pending message cannot mint another proposal,
        # approval or outbound email.
        lifecycle = await self._repository.get_request_lifecycle_for_update(
            conn, context.request_id
        )
        if lifecycle is None:
            raise RuntimeError("Flow request not found for resolution proposal.")
        if lifecycle["status"] == "RESOLVED":
            return ClosureProposalResult(request_status="RESOLVED_TERMINAL")
        if lifecycle["status"] == "RESOLUTION_PENDING_APPROVAL":
            return ClosureProposalResult(request_status="ALREADY_PENDING_APPROVAL")

        policy = await self._repository.get_closure_policy(conn, context.routing_id)
        resolution_text = (message.text_body or "").strip()[:2000]
        resolution = await self._repository.upsert_resolution(
            conn,
            request_id=context.request_id,
            routing_id=context.routing_id,
            proposed_by=message.sender,
            proposed_at=message.received_at,
            source_provider=message.provider,
            source_external_message_id=message.external_message_id,
            resolution_text=resolution_text,
        )
        if resolution.status != ResolutionStatus.PROPOSED:
            existing = await self._repository.find_approval_by_resolution(
                conn, resolution.id
            )
            return ClosureProposalResult(
                resolution_id=resolution.id,
                approval_id=existing.id if existing else None,
                approval_token=existing.approval_token if existing else None,
                approver_level=existing.approver_level if existing else None,
                approver_destination=(
                    existing.approver_destination if existing else None
                ),
                outbound_external_message_id=(
                    existing.outbound_external_message_id if existing else None
                ),
                idempotent=True,
            )

        if policy is None:
            return ClosureProposalResult(
                resolution_id=resolution.id,
                request_status="NO_APPROVER",
            )

        approval_token = approval_token_for(
            message.provider, message.external_message_id
        )
        approval = await self._repository.upsert_approval(
            conn,
            request_id=context.request_id,
            resolution_id=resolution.id,
            approver_level=policy["approver_level"],
            approver_destination=policy["approver_destination"],
            approval_token=approval_token,
        )

        sent = False
        reconciled = False
        if approval.outbound_external_message_id is None:
            brief = dict(await self._repository.get_case_brief(conn, context.request_id))
            brief["approver_destination"] = approval.approver_destination
            email = build_approval_email(
                request_id=context.request_id,
                approval_token=approval.approval_token,
                reported_level=context.level,
                responder=message.sender,
                resolution_text=resolution_text,
                proposed_at=message.received_at,
                brief=brief,
            )
            if self._sender is not None:
                try:
                    recovered = (
                        self._sender.find_sent_message_by_rfc_message_id(
                            email.rfc_message_id
                        )
                        or self._sender.find_sent_message_by_reference(
                            approval.approval_token, to=email.destination
                        )
                    )
                    if recovered:
                        observed = _safe_observed_rfc_message_id(
                            self._sender, recovered
                        )
                        approval = await self._repository.mark_approval_sent(
                            conn, approval.id, recovered, observed
                        )
                        reconciled = True
                        sent = True
                    else:
                        external_id = self._sender.send_message(
                            to=email.destination,
                            subject=email.subject,
                            body=email.body,
                            rfc_message_id=email.rfc_message_id,
                        )
                        observed = _safe_observed_rfc_message_id(
                            self._sender, external_id
                        )
                        approval = await self._repository.mark_approval_sent(
                            conn, approval.id, external_id, observed
                        )
                        sent = True
                except Exception:
                    approval = await self._repository.mark_approval_delivery_uncertain(
                        conn, approval.id
                    )

        await self._repository.mark_request_resolution_pending(
            conn, context.request_id
        )
        return ClosureProposalResult(
            resolution_id=resolution.id,
            approval_id=approval.id,
            approval_token=approval.approval_token,
            approver_level=approval.approver_level,
            approver_destination=approval.approver_destination,
            outbound_external_message_id=approval.outbound_external_message_id,
            sent=sent,
            reconciled=reconciled,
            request_status="RESOLUTION_PENDING_APPROVAL",
        )

    async def process_approval_reply(
        self, message: InboundMessage
    ) -> ApprovalProcessResult:
        async with transaction(self._pool) as conn:
            correlated = await self._correlate(conn, message)
            if correlated is None:
                return ApprovalProcessResult(matched=False)
            approval = correlated.approval
            # RFC 3834 auto-replies / bounces never decide a closure even if
            # they correlate to the approval thread.
            if is_automated_message(message):
                return ApprovalProcessResult(
                    matched=True,
                    processed=False,
                    approval_id=approval.id,
                    request_id=approval.request_id,
                    correlation_method=correlated.method,
                    reason="AUTOMATED_MESSAGE",
                )
            request_ctx = await self._repository.get_request_context(
                conn, approval.request_id
            )
            if request_ctx is None:
                raise RuntimeError("Flow approval request context not found.")
            if not approval_sender_authorized(
                message.sender,
                approval.approver_destination,
                request_ctx.get("citizen_address"),
            ):
                return ApprovalProcessResult(
                    matched=True,
                    processed=False,
                    authorized=False,
                    approval_id=approval.id,
                    request_id=approval.request_id,
                    correlation_method=correlated.method,
                )

            locked = await self._repository.get_approval_for_decision(
                conn, approval.id
            )
            if locked is None:
                return ApprovalProcessResult(
                    matched=True,
                    processed=False,
                    approval_id=approval.id,
                    request_id=approval.request_id,
                    correlation_method=correlated.method,
                )
            if locked.status in {
                ClosureApprovalStatus.APPROVED,
                ClosureApprovalStatus.REJECTED,
            }:
                return ApprovalProcessResult(
                    matched=True,
                    processed=False,
                    approval_id=locked.id,
                    request_id=locked.request_id,
                    decision=(
                        ApprovalDecision.APPROVE
                        if locked.status == ClosureApprovalStatus.APPROVED
                        else ApprovalDecision.REJECT
                    ),
                    correlation_method=correlated.method,
                    idempotent=True,
                )

            source_id = await self._repository.claim_approval_reply(
                conn, request_ctx["conversation_id"], message
            )
            if source_id is None:
                return ApprovalProcessResult(
                    matched=True,
                    processed=False,
                    approval_id=locked.id,
                    request_id=locked.request_id,
                    correlation_method=correlated.method,
                    idempotent=True,
                )

            decision = self._interpreter.interpret(
                message.text_body, correlation_id=message.external_message_id
            )
            if decision.decision == ApprovalDecision.AMBIGUOUS:
                return ApprovalProcessResult(
                    matched=True,
                    processed=True,
                    approval_id=locked.id,
                    request_id=locked.request_id,
                    resolution_id=locked.resolution_id,
                    decision=ApprovalDecision.AMBIGUOUS,
                    correlation_method=correlated.method,
                )

            if decision.decision == ApprovalDecision.APPROVE:
                await self._repository.apply_approve(
                    conn,
                    locked,
                    decision_source_external_message_id=message.external_message_id,
                    decided_by=message.sender,
                    decided_at=message.received_at,
                    reason=decision.reason,
                )
                snapshot = await self._audit_repository.build_snapshot(
                    conn, locked.request_id
                )
                snapshot_sha256 = sha256_of_snapshot(snapshot)
                await self._audit_repository.create_record(
                    conn,
                    request_id=locked.request_id,
                    schema_version=AUDIT_SCHEMA_VERSION,
                    resolved_at=message.received_at,
                    snapshot=snapshot,
                    snapshot_sha256=snapshot_sha256,
                )
            else:
                await self._repository.apply_reject(
                    conn,
                    locked,
                    decision_source_external_message_id=message.external_message_id,
                    decided_by=message.sender,
                    decided_at=message.received_at,
                    reason=decision.reason,
                )

            return ApprovalProcessResult(
                matched=True,
                processed=True,
                approval_id=locked.id,
                request_id=locked.request_id,
                resolution_id=locked.resolution_id,
                decision=decision.decision,
                correlation_method=correlated.method,
                reason=decision.reason,
            )

    async def _correlate(
        self, conn: AsyncConnection, message: InboundMessage
    ) -> CorrelatedApprovalReply | None:
        in_reply_to = str(message.metadata.get("in_reply_to") or "").strip()
        if in_reply_to:
            approval = await self._repository.find_approval_by_rfc_reference(
                conn, rfc_reference_ids(in_reply_to, "")
            )
            if approval is not None:
                return CorrelatedApprovalReply(approval, "in_reply_to_rfc")

        references = str(message.metadata.get("references") or "").strip()
        if references:
            approval = await self._repository.find_approval_by_rfc_reference(
                conn, rfc_reference_ids("", references)
            )
            if approval is not None:
                return CorrelatedApprovalReply(approval, "references_rfc")

        token = approval_token_from_subject(message.subject)
        if token:
            approval = await self._repository.find_approval_by_token(conn, token)
            if approval is not None:
                return CorrelatedApprovalReply(approval, "subject_approval_token")
        return None

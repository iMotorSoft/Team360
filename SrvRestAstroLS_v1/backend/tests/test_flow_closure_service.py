import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from modules.flow.closure_service import FlowClosureService
from modules.flow.domain import (
    ApprovalDecision,
    ApprovalDecisionResult,
    ClosureApproval,
    ClosureApprovalStatus,
    OperationalAction,
    OperationalInterpretation,
    OperationalRoutingContext,
    ResolutionProposal,
    ResolutionStatus,
)
from modules.messaging.domain import InboundMessage


REQUEST_ID = "656977af-cc29-43d6-b78c-53464818f06a"
APPROVER = "alumbrado.n2@alquimiablue.com"


def _dt():
    return datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


class _AsyncContext:
    def __init__(self, value=None):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def connection(self):
        return _AsyncContext(_Connection())


class _Connection:
    def transaction(self):
        return _AsyncContext()


def _context(*, request_status="CONFIRMED", level=1):
    return OperationalRoutingContext(
        routing_id="routing-1",
        request_id=REQUEST_ID,
        conversation_id="conv-1",
        routing_key=f"alumbrado_level_{level}",
        level=level,
        routing_status="ASSIGNED",
        destination=f"alumbrado.n{level}@alquimiablue.com",
        outbound_external_message_id="gmail-out-1",
        outbound_rfc_message_id="<routing-rfc@alquimiablue.com>",
        outbound_observed_rfc_message_id="<routing-obs@mail.gmail.com>",
        request_status=request_status,
    )


def _message(*, message_id="m1", sender="tech@alquimiablue.com", text="La luminaria quedó reparada."):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id="thread-1",
        sender=sender,
        recipients=("mesa@alquimiablue.com",),
        subject=f"Re: [Team360 Flow] #{REQUEST_ID}",
        text_body=text,
        received_at=_dt(),
        metadata={"in_reply_to": "<routing-obs@mail.gmail.com>", "references": ""},
    )


def _approval_message(message_id, token, text, sender=APPROVER, in_reply_to="<closure-obs@mail.gmail.com>"):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=message_id,
        external_thread_id="thread-1",
        sender=sender,
        recipients=("mesa@alquimiablue.com",),
        subject=f"Re: [CIERRE][R:{token}][{REQUEST_ID}] Aprobación de cierre",
        text_body=text,
        received_at=_dt(),
        metadata={"in_reply_to": in_reply_to, "references": ""},
    )


class _Sender:
    def __init__(self):
        self.sent = []

    def find_sent_message_by_rfc_message_id(self, rfc_message_id):
        return None

    def find_sent_message_by_reference(self, reference, *, to=None):
        return None

    def get_message_rfc_id(self, message_id):
        return f"<observed-{message_id}@mail.gmail.com>"

    def send_message(self, *, to, subject, body, rfc_message_id):
        self.sent.append({"to": to, "subject": subject, "body": body, "rfc": rfc_message_id})
        return f"gmail-sent-{len(self.sent)}"


class _AuditRepo:
    def __init__(self):
        self.snapshots = []
        self.records = []

    async def build_snapshot(self, conn, request_id):
        snapshot = {"request_id": request_id, "result": {"status": "RESOLVED"}}
        self.snapshots.append(snapshot)
        return snapshot

    async def create_record(self, conn, *, request_id, schema_version, resolved_at, snapshot, snapshot_sha256):
        self.records.append({"request_id": request_id, "snapshot": snapshot})
        return "audit-1"


class _ClosureRepo:
    def __init__(self, *, request_status="CONFIRMED", policy=None):
        self.request_status = request_status
        self.policy = policy if policy is not None else {
            "approver_level": 2,
            "approver_destination": APPROVER,
        }
        self.resolutions = {}
        self.approvals = {}
        self.approval_by_resolution = {}
        self.approval_by_token = {}
        self.sent = []
        self.uncertain = []
        self.pending_transitions = 0
        self.active_transitions = 0
        self.apply_approve_calls = 0
        self.apply_reject_calls = 0

    async def get_request_lifecycle_for_update(self, conn, request_id):
        return {"status": self.request_status}

    async def get_closure_policy(self, conn, routing_id):
        return self.policy

    async def upsert_resolution(self, conn, *, request_id, routing_id, proposed_by, proposed_at, source_provider, source_external_message_id, resolution_text):
        key = (source_provider, source_external_message_id)
        for resolution in self.resolutions.values():
            if (resolution.source_provider, resolution.source_external_message_id) == key:
                return resolution
        resolution = ResolutionProposal(
            id=f"res-{len(self.resolutions) + 1}",
            request_id=request_id,
            routing_id=routing_id,
            status=ResolutionStatus.PROPOSED,
            proposed_by=proposed_by,
            proposed_at=proposed_at,
            source_provider=source_provider,
            source_external_message_id=source_external_message_id,
            resolution_text=resolution_text,
        )
        self.resolutions[resolution.id] = resolution
        return resolution

    async def upsert_approval(self, conn, *, request_id, resolution_id, approver_level, approver_destination, approval_token):
        if resolution_id in self.approval_by_resolution:
            return self.approval_by_resolution[resolution_id]
        approval = ClosureApproval(
            id=f"appr-{len(self.approvals) + 1}",
            request_id=request_id,
            resolution_id=resolution_id,
            approver_level=approver_level,
            approver_destination=approver_destination,
            approval_token=approval_token,
            status=ClosureApprovalStatus.PENDING,
            outbound_rfc_message_id=None,
            outbound_external_message_id=None,
            outbound_observed_rfc_message_id=None,
            decision_source_external_message_id=None,
            decided_by=None,
            decided_at=None,
            decision_reason=None,
            created_at=_dt(),
        )
        self.approvals[approval.id] = approval
        self.approval_by_resolution[resolution_id] = approval
        self.approval_by_token[approval_token] = approval
        return approval

    async def find_approval_by_resolution(self, conn, resolution_id):
        return self.approval_by_resolution.get(resolution_id)

    async def find_approval_by_token(self, conn, token):
        return self.approval_by_token.get(token)

    async def find_approval_by_rfc_reference(self, conn, references):
        for approval in self.approvals.values():
            if (
                approval.outbound_observed_rfc_message_id in references
                or approval.outbound_rfc_message_id in references
            ):
                return approval
        return None

    async def get_approval_for_decision(self, conn, approval_id):
        return self.approvals.get(approval_id)

    async def mark_approval_sent(self, conn, approval_id, external_message_id, observed_rfc):
        approval = self.approvals[approval_id]
        updated = replace(
            approval,
            outbound_external_message_id=external_message_id,
            outbound_observed_rfc_message_id=observed_rfc or approval.outbound_observed_rfc_message_id,
        )
        self.approvals[approval_id] = updated
        self.approval_by_resolution[updated.resolution_id] = updated
        self.sent.append(approval_id)
        return updated

    async def mark_approval_delivery_uncertain(self, conn, approval_id):
        approval = self.approvals[approval_id]
        updated = replace(approval, status=ClosureApprovalStatus.DELIVERY_UNCERTAIN)
        self.approvals[approval_id] = updated
        self.approval_by_resolution[updated.resolution_id] = updated
        self.uncertain.append(approval_id)
        return updated

    async def mark_request_resolution_pending(self, conn, request_id):
        self.pending_transitions += 1
        self.request_status = "RESOLUTION_PENDING_APPROVAL"

    async def mark_request_active(self, conn, request_id):
        self.active_transitions += 1
        self.request_status = "ACTIVE"

    async def get_request_context(self, conn, request_id):
        return {
            "request_id": request_id,
            "conversation_id": "conv-1",
            "status": self.request_status,
            "description": "Reparar poste",
            "location_text": None,
            "tentative_category": "alumbrado",
        }

    async def claim_approval_reply(self, conn, conversation_id, message):
        return f"source-{message.external_message_id}"

    async def apply_approve(self, conn, approval, *, decision_source_external_message_id, decided_by, decided_at, reason):
        self.apply_approve_calls += 1
        self.request_status = "RESOLVED"

    async def apply_reject(self, conn, approval, *, decision_source_external_message_id, decided_by, decided_at, reason):
        self.apply_reject_calls += 1
        self.request_status = "ACTIVE"

    async def get_case_brief(self, conn, request_id):
        return {
            "description": "Reparar poste",
            "location_text": None,
            "sector_name": "Alumbrado Público",
            "chain": [],
            "slas": [],
        }


class _Interpreter:
    def __init__(self, decision=ApprovalDecision.APPROVE):
        self.decision = decision

    def interpret(self, text, *, correlation_id=None):
        return ApprovalDecisionResult(self.decision, "reason-x")


def _service(repo, audit=None, interpreter=None, sender=None):
    return FlowClosureService(
        pool=_Pool(),
        repository=repo,
        audit_repository=audit or _AuditRepo(),
        interpreter=interpreter or _Interpreter(),
        sender=sender or _Sender(),
    )


def _interpretation(action=OperationalAction.RESOLUTION_PROPOSED):
    return OperationalInterpretation(action, "clasificado", "mock", "mock", {}, 1)


def _seed_approval(repo, *, token="2454e105606dbe15", status=ClosureApprovalStatus.PENDING):
    approval = asyncio.run(
        repo.upsert_approval(
            _Connection(),
            request_id=REQUEST_ID,
            resolution_id="res-1",
            approver_level=2,
            approver_destination=APPROVER,
            approval_token=token,
        )
    )
    approval = replace(approval, status=status, outbound_observed_rfc_message_id="<closure-obs@mail.gmail.com>")
    repo.approvals[approval.id] = approval
    repo.approval_by_resolution[approval.resolution_id] = approval
    repo.approval_by_token[token] = approval
    return approval


def test_propose_resolution_creates_proposal_approval_send_and_transition():
    repo = _ClosureRepo()
    sender = _Sender()
    service = _service(repo, sender=sender)
    result = asyncio.run(
        service.propose_resolution(
            _Connection(),
            context=_context(),
            message=_message(),
            interpretation=_interpretation(),
        )
    )
    assert result.request_status == "RESOLUTION_PENDING_APPROVAL"
    assert result.approval_id is not None
    assert result.sent is True
    assert len(repo.resolutions) == 1
    assert len(repo.approvals) == 1
    assert len(sender.sent) == 1
    assert repo.pending_transitions == 1
    assert sender.sent[0]["to"] == APPROVER
    assert "APROBAR" in sender.sent[0]["body"]


def test_propose_resolution_skips_when_resolved_terminal():
    repo = _ClosureRepo(request_status="RESOLVED")
    sender = _Sender()
    service = _service(repo, sender=sender)
    result = asyncio.run(
        service.propose_resolution(
            _Connection(),
            context=_context(request_status="RESOLVED"),
            message=_message(),
            interpretation=_interpretation(),
        )
    )
    assert result.request_status == "RESOLVED_TERMINAL"
    assert len(repo.resolutions) == 0
    assert len(sender.sent) == 0


def test_reject_then_new_proposal_is_allowed():
    repo = _ClosureRepo(request_status="ACTIVE")
    sender = _Sender()
    service = _service(repo, sender=sender)
    result = asyncio.run(
        service.propose_resolution(
            _Connection(),
            context=_context(request_status="ACTIVE"),
            message=_message(message_id="m2", text="Ahora sí, reparada de nuevo."),
            interpretation=_interpretation(),
        )
    )
    assert result.request_status == "RESOLUTION_PENDING_APPROVAL"
    assert len(repo.resolutions) == 1
    assert len(repo.approvals) == 1
    assert len(sender.sent) == 1


def test_propose_resolution_skips_when_already_pending_approval():
    repo = _ClosureRepo(request_status="RESOLUTION_PENDING_APPROVAL")
    sender = _Sender()
    service = _service(repo, sender=sender)
    result = asyncio.run(
        service.propose_resolution(
            _Connection(),
            context=_context(request_status="RESOLUTION_PENDING_APPROVAL"),
            message=_message(),
            interpretation=_interpretation(),
        )
    )
    assert result.request_status == "ALREADY_PENDING_APPROVAL"
    assert len(repo.resolutions) == 0
    assert len(sender.sent) == 0


def test_approve_decides_and_creates_audit():
    repo = _ClosureRepo()
    audit = _AuditRepo()
    service = _service(repo, audit=audit, interpreter=_Interpreter(ApprovalDecision.APPROVE))
    _seed_approval(repo)
    message = _approval_message("decision-1", "2454e105606dbe15", "APROBAR")
    result = asyncio.run(service.process_approval_reply(message))
    assert result.matched is True
    assert result.processed is True
    assert result.decision == ApprovalDecision.APPROVE
    assert repo.apply_approve_calls == 1
    assert repo.apply_reject_calls == 0
    assert repo.request_status == "RESOLVED"
    assert len(audit.records) == 1


def test_reject_does_not_create_audit():
    repo = _ClosureRepo()
    audit = _AuditRepo()
    service = _service(repo, audit=audit, interpreter=_Interpreter(ApprovalDecision.REJECT))
    _seed_approval(repo)
    message = _approval_message("decision-2", "2454e105606dbe15", "RECHAZAR: falta verificar")
    result = asyncio.run(service.process_approval_reply(message))
    assert result.decision == ApprovalDecision.REJECT
    assert repo.apply_reject_calls == 1
    assert repo.apply_approve_calls == 0
    assert repo.request_status == "ACTIVE"
    assert len(audit.records) == 0


def test_ambiguous_approval_does_not_decide():
    repo = _ClosureRepo()
    service = _service(repo, interpreter=_Interpreter(ApprovalDecision.AMBIGUOUS))
    _seed_approval(repo)
    message = _approval_message("decision-3", "2454e105606dbe15", "Ok, lo veo.")
    result = asyncio.run(service.process_approval_reply(message))
    assert result.decision == ApprovalDecision.AMBIGUOUS
    assert repo.apply_approve_calls == 0
    assert repo.apply_reject_calls == 0
    assert repo.request_status == "CONFIRMED"


def test_wrong_sender_cannot_approve():
    repo = _ClosureRepo()
    service = _service(repo)
    _seed_approval(repo)
    message = _approval_message("decision-4", "2454e105606dbe15", "APROBAR", sender="citizen@example.com")
    result = asyncio.run(service.process_approval_reply(message))
    assert result.matched is True
    assert result.authorized is False
    assert result.processed is False
    assert repo.apply_approve_calls == 0


def test_approval_reply_without_correlation_is_not_matched():
    repo = _ClosureRepo()
    service = _service(repo)
    message = _message(message_id="no-corr", text="APROBAR")
    result = asyncio.run(service.process_approval_reply(message))
    assert result.matched is False


def test_already_decided_approval_is_idempotent():
    repo = _ClosureRepo()
    service = _service(repo)
    approval = _seed_approval(repo, status=ClosureApprovalStatus.APPROVED)
    repo.approvals[approval.id] = replace(
        approval,
        decision_source_external_message_id="decision-5",
        decided_by=APPROVER,
        decided_at=_dt(),
    )
    message = _approval_message("decision-6", "2454e105606dbe15", "APROBAR")
    result = asyncio.run(service.process_approval_reply(message))
    assert result.idempotent is True
    assert result.processed is False
    assert repo.apply_approve_calls == 0

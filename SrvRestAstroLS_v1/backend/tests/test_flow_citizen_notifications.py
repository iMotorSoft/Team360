"""Unit coverage for the citizen public communication policy.

Domain mapping, allow-listed public projection, deterministic templates,
sensitive-field exclusion, dedupe keys and the service eligibility/delivery
guards are exercised with in-memory fakes; real PostgreSQL is covered by the
gated ``test_flow_citizen_notifications_postgres.py`` suite.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import fields

import pytest

from modules.flow.citizen_notifications.domain import (
    CitizenCaseProjection,
    CitizenNotificationType,
    PublicStatus,
    citizen_rfc_message_id,
    dedupe_key,
    map_internal_to_public,
    notification_subject,
    notification_type_for_public_status,
    public_reference_for,
    public_state_for_notification_type,
    render_notification,
    sanitize_public_text,
)
from modules.flow.citizen_notifications.service import (
    FlowCitizenNotificationService,
)

REQUEST_ID = "814f38ce-9509-4cd6-a355-fa176e63edb2"
CITIZEN = "vecino@example.com"

INTERNAL_MARKERS = (
    "INTERNAL-SUPERVISOR",
    "PRIVATE-N2",
    "SLA-BREACHED",
    "SECRET-APPROVAL-TOKEN",
    "INTERNAL-NOTE",
)


# ---------------------------------------------------------------------------
# Public status mapping (section 56)
# ---------------------------------------------------------------------------
def test_internal_to_public_mapping_is_deterministic():
    assert map_internal_to_public("CONFIRMED") is PublicStatus.RECEIVED
    assert map_internal_to_public("ACTIVE") is PublicStatus.IN_PROGRESS
    assert (
        map_internal_to_public("RESOLUTION_PENDING_APPROVAL")
        is PublicStatus.IN_PROGRESS
    )
    assert map_internal_to_public("RESOLVED") is PublicStatus.RESOLVED


def test_internal_states_never_expose_operational_names():
    for internal in ("ACTIVE", "RESOLUTION_PENDING_APPROVAL"):
        public = map_internal_to_public(internal)
        assert public is not None
        assert public is PublicStatus.IN_PROGRESS
        assert public.value not in ("ACTIVE", "RESOLUTION_PENDING_APPROVAL")
    # SLA statuses are internal-only: they never map to a public state.
    assert map_internal_to_public("BREACHED") is None


def test_unknown_internal_status_has_no_public_state():
    assert map_internal_to_public("ESCALATED") is None
    assert map_internal_to_public("REJECTED") is None


def test_notification_type_follows_public_state():
    assert (
        notification_type_for_public_status(PublicStatus.RECEIVED)
        is CitizenNotificationType.CITIZEN_RECEIVED
    )
    assert (
        public_state_for_notification_type(
            CitizenNotificationType.CITIZEN_RESOLVED
        )
        is PublicStatus.RESOLVED
    )


# ---------------------------------------------------------------------------
# Public projection allowlist (sections 28-29)
# ---------------------------------------------------------------------------
def test_projection_only_has_public_fields():
    projection = CitizenCaseProjection(
        public_reference=REQUEST_ID,
        public_status="RECEIVED",
        subject="Solicitud de alumbrado publico",
        public_description="Luminaria apagada",
        public_location="Av. Eucaliptos 980",
    )
    fields_set = {field.name for field in fields(projection)}
    assert "public_reference" in fields_set
    assert "public_status" in fields_set
    assert "subject" in fields_set
    assert "public_description" in fields_set
    assert "public_location" in fields_set
    # Internal-only concepts are not part of the citizen projection.
    assert "routing_id" not in fields_set
    assert "sla_status" not in fields_set
    assert "approval_token" not in fields_set
    assert "audit_id" not in fields_set


def test_public_reference_is_a_stable_representation():
    assert public_reference_for(REQUEST_ID) == REQUEST_ID


# ---------------------------------------------------------------------------
# Deterministic templates + sensitive exclusion (sections 30-31, 48-50, 53)
# ---------------------------------------------------------------------------
def _projection(**overrides):
    base = dict(
        public_reference=REQUEST_ID,
        public_status="IN_PROGRESS",
        subject="Solicitud de alumbrado publico",
        public_description="Luminaria apagada",
        public_location="Av. Eucaliptos 980",
    )
    base.update(overrides)
    return CitizenCaseProjection(**base)


def test_received_template_contains_reference_and_receipt():
    subject, body = render_notification(
        CitizenNotificationType.CITIZEN_RECEIVED, _projection()
    )
    assert subject == "LaMuni — Recibimos tu solicitud"
    assert REQUEST_ID in body
    assert "Recibimos tu solicitud" in body
    assert "Av. Eucaliptos 980" in body


def test_in_progress_template_is_generic():
    subject, body = render_notification(
        CitizenNotificationType.CITIZEN_IN_PROGRESS, _projection()
    )
    assert subject == "LaMuni — Tu solicitud continúa en gestión"
    assert "continúa en gestión" in body
    assert "escaló" not in body.lower()
    assert "Nivel" not in body


def test_resolved_template_is_generic_and_final():
    subject, body = render_notification(
        CitizenNotificationType.CITIZEN_RESOLVED, _projection()
    )
    assert subject == "LaMuni — Tu solicitud fue finalizada"
    assert "fue atendida" in body
    assert "finalizada" in body
    assert "aprobación" not in body.lower()
    assert "supervisor" not in body.lower()


def test_no_internal_marker_leaks_into_any_citizen_message():
    projection = _projection()
    for notification_type in (
        CitizenNotificationType.CITIZEN_RECEIVED,
        CitizenNotificationType.CITIZEN_IN_PROGRESS,
        CitizenNotificationType.CITIZEN_RESOLVED,
        CitizenNotificationType.CITIZEN_INFO_REQUIRED,
    ):
        subject, body = render_notification(notification_type, projection)
        combined = f"{subject}\n{body}"
        for marker in INTERNAL_MARKERS:
            assert marker not in combined, f"{marker} leaked in {notification_type}"


def test_subjects_never_carry_operational_information():
    for notification_type in CitizenNotificationType:
        subject = notification_subject(notification_type)
        assert "[Team360 Flow]" not in subject
        assert "CIERRE" not in subject
        assert REQUEST_ID not in subject
        assert "R:" not in subject


# ---------------------------------------------------------------------------
# Injection safety (sections 75-76)
# ---------------------------------------------------------------------------
def test_control_characters_are_stripped_from_public_text():
    dirty = "Avenida <script>alert(1)</script>\r\nSegunda línea\nUnicode: ñandú ☂"
    cleaned = sanitize_public_text(dirty)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert "script" in cleaned
    assert "ñandú" in cleaned


def test_rendered_body_keeps_plain_text_not_html():
    subject, body = render_notification(
        CitizenNotificationType.CITIZEN_RECEIVED,
        _projection(public_description="<script>alert(1)</script>"),
    )
    # Plain-text rendering never interprets citizen data as markup.
    assert "<script>alert(1)</script>" in body


# ---------------------------------------------------------------------------
# Dedupe key (section 19) and RFC identity
# ---------------------------------------------------------------------------
def test_dedupe_key_is_deterministic_and_type_scoped():
    assert dedupe_key(REQUEST_ID, CitizenNotificationType.CITIZEN_RECEIVED) == (
        f"{REQUEST_ID}:CITIZEN_RECEIVED"
    )
    assert dedupe_key(
        REQUEST_ID, CitizenNotificationType.CITIZEN_RECEIVED
    ) == dedupe_key(REQUEST_ID, CitizenNotificationType.CITIZEN_RECEIVED)
    assert dedupe_key(
        REQUEST_ID, CitizenNotificationType.CITIZEN_IN_PROGRESS
    ) != dedupe_key(REQUEST_ID, CitizenNotificationType.CITIZEN_RECEIVED)


def test_citizen_rfc_message_id_is_stable():
    first = citizen_rfc_message_id(
        REQUEST_ID, CitizenNotificationType.CITIZEN_RECEIVED
    )
    second = citizen_rfc_message_id(
        REQUEST_ID, CitizenNotificationType.CITIZEN_RECEIVED
    )
    assert first == second
    assert first.startswith("<") and first.endswith(">")
    assert " " not in first and "@" in first


# ---------------------------------------------------------------------------
# Service guards with in-memory fakes (sections 90-91, 110-117)
# ---------------------------------------------------------------------------
class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    @asynccontextmanager
    async def connection(self):
        yield self._conn


class _FakeConn:
    @asynccontextmanager
    async def transaction(self):
        yield self


class _FakeRepo:
    def __init__(self):
        self.traces: dict[tuple[str, str], dict] = {}
        self.projections: dict[str, dict] = {}
        self.confirmed: dict[str, list[str]] = {}
        self.next_id = 1

    def seed_projection(self, request_id, status, citizen=CITIZEN):
        self.projections[request_id] = {
            "public_reference": request_id,
            "request_status": status,
            "public_description": "Luminaria apagada",
            "public_location": "Av. Eucaliptos 980",
            "resolved_at_utc": None,
            "citizen_address": citizen,
            "subject": "Solicitud de alumbrado publico",
        }

    async def find(self, conn, request_id, notification_type):
        return self.traces.get((request_id, notification_type.value))

    async def get_request_projection(self, conn, request_id):
        return self.projections.get(request_id)

    async def find_confirmed_request_ids(self, conn, conversation_id):
        return list(self.confirmed.get(conversation_id, []))

    async def insert_or_claim(
        self,
        conn,
        *,
        request_id,
        notification_type,
        channel,
        recipient,
        public_reference,
        subject,
        body,
        dedupe_key,
        outbound_rfc_message_id,
    ):
        key = (request_id, notification_type.value)
        if key in self.traces:
            return None
        trace = {
            "id": str(self.next_id),
            "request_id": request_id,
            "notification_type": notification_type.value,
            "status": "PENDING",
            "provider_message_id": None,
            "subject": subject,
            "body": body,
        }
        self.next_id += 1
        self.traces[key] = trace
        return trace["id"]

    async def mark_sent(
        self,
        conn,
        trace_id,
        *,
        provider_message_id,
        provider_thread_id,
        observed_rfc_message_id,
    ):
        for trace in self.traces.values():
            if trace["id"] == trace_id:
                trace["status"] = "SENT"
                trace["provider_message_id"] = provider_message_id
                return
        raise RuntimeError("trace not found")

    async def mark_failed(
        self,
        conn,
        trace_id,
        *,
        error_code,
        error_detail,
        uncertain,
    ):
        for trace in self.traces.values():
            if trace["id"] == trace_id:
                trace["status"] = (
                    "DELIVERY_UNCERTAIN" if uncertain else "DELIVERY_FAILED"
                )
                trace["last_error_code"] = error_code
                return
        raise RuntimeError("trace not found")

    async def list_traces(self, conn, request_id):
        return [
            trace
            for (rid, _type), trace in self.traces.items()
            if rid == request_id
        ]


class _FakeSender:
    def __init__(self):
        self.sent = []
        self.recovered: str | None = None
        self.fail_with: Exception | None = None

    @property
    def sender_address(self):
        return "mesaentrada@alquimiablue.com"

    def find_sent_message_by_rfc_message_id(self, rfc_message_id):
        return self.recovered

    def find_sent_message_by_reference(self, reference, *, to=None):
        return None

    def get_message_rfc_id(self, message_id):
        return f"<observed-{message_id}@mail.gmail.com>"

    def send_message(self, *, to, subject, body, rfc_message_id):
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append({"to": to, "subject": subject, "body": body})
        return f"gmail-{len(self.sent)}"


def _service(repo, sender):
    pool = _FakePool(_FakeConn())
    return FlowCitizenNotificationService(
        pool=pool, repository=repo, sender=sender
    )


def _run(coro):
    return asyncio.run(coro)


def test_received_sends_once_when_confirmed():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    sender = _FakeSender()
    service = _service(repo, sender)

    result = _run(service.notify_received(REQUEST_ID))
    assert result.outcome == "SENT"
    assert sender.sent and sender.sent[0]["to"] == CITIZEN
    assert "Recibimos tu solicitud" in sender.sent[0]["body"]

    second = _run(service.notify_received(REQUEST_ID))
    assert second.outcome == "ALREADY_SENT"
    assert len(sender.sent) == 1  # dedupe: exactly one email


def test_received_never_sends_before_confirmation():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    sender = _FakeSender()
    service = _service(repo, sender)

    result = _run(service.notify_received_for_conversation("conv-1"))
    assert result == []

    repo.confirmed["conv-1"] = [REQUEST_ID]
    results = _run(service.notify_received_for_conversation("conv-1"))
    assert len(results) == 1 and results[0].outcome == "SENT"


def test_in_progress_is_generic_and_deduped():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "ACTIVE")
    sender = _FakeSender()
    service = _service(repo, sender)

    result = _run(service.notify_in_progress(REQUEST_ID))
    assert result.outcome == "SENT"
    assert "continúa en gestión" in sender.sent[0]["body"]

    _run(service.notify_in_progress(REQUEST_ID))
    assert len(sender.sent) == 1


def test_in_progress_eligible_during_active_treatment_while_status_confirmed():
    # The request status stays CONFIRMED during routing/escalation; a real
    # escalation still produces the single generic IN_PROGRESS signal.
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    sender = _FakeSender()
    service = _service(repo, sender)

    result = _run(service.notify_in_progress(REQUEST_ID))
    assert result.outcome == "SENT"
    assert "continúa en gestión" in sender.sent[0]["body"]

    _run(service.notify_in_progress(REQUEST_ID))
    assert len(sender.sent) == 1


def test_in_progress_never_sent_after_resolved():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "RESOLVED")
    sender = _FakeSender()
    service = _service(repo, sender)
    result = _run(service.notify_in_progress(REQUEST_ID))
    assert result.outcome == "STATUS_MISMATCH"
    assert sender.sent == []


def test_resolved_guard_before_approval():
    for status in ("CONFIRMED", "ACTIVE", "RESOLUTION_PENDING_APPROVAL"):
        repo = _FakeRepo()
        repo.seed_projection(REQUEST_ID, status)
        sender = _FakeSender()
        service = _service(repo, sender)
        result = _run(service.notify_resolved(REQUEST_ID))
        assert result.outcome == "STATUS_MISMATCH", status
        assert sender.sent == [], status


def test_resolved_sent_only_after_terminal_state():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "RESOLVED")
    sender = _FakeSender()
    service = _service(repo, sender)
    result = _run(service.notify_resolved(REQUEST_ID))
    assert result.outcome == "SENT"
    assert "fue atendida" in sender.sent[0]["body"]

    _run(service.notify_resolved(REQUEST_ID))
    assert len(sender.sent) == 1


def test_delivery_failure_marks_failed_without_touching_case():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    sender = _FakeSender()
    sender.fail_with = RuntimeError("provider down")
    service = _service(repo, sender)

    result = _run(service.notify_received(REQUEST_ID))
    assert result.outcome == "DELIVERY_FAILED"
    trace = repo.traces[(REQUEST_ID, "CITIZEN_RECEIVED")]
    assert trace["status"] == "DELIVERY_FAILED"
    assert trace["last_error_code"] == "RuntimeError"
    # Case state is preserved: projection still reads CONFIRMED.
    assert repo.projections[REQUEST_ID]["request_status"] == "CONFIRMED"


def test_retry_reconciles_without_duplicate_send():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    sender = _FakeSender()
    sender.fail_with = RuntimeError("uncertain")
    service = _service(repo, sender)

    failed = _run(service.notify_received(REQUEST_ID))
    assert failed.outcome == "DELIVERY_FAILED"

    sender.fail_with = None
    sender.recovered = "gmail-recovered-1"
    retried = _run(service.notify_received(REQUEST_ID))
    assert retried.outcome == "SENT_RECONCILED"
    assert retried.provider_message_id == "gmail-recovered-1"
    assert sender.sent == []  # reconciled, never re-sent


def test_uncertain_delivery_is_never_resent_blindly():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    sender = _FakeSender()
    sender.fail_with = TimeoutError("timed out")
    service = _service(repo, sender)

    result = _run(service.notify_received(REQUEST_ID))
    assert result.outcome == "DELIVERY_UNCERTAIN"
    assert repo.traces[(REQUEST_ID, "CITIZEN_RECEIVED")]["status"] == (
        "DELIVERY_UNCERTAIN"
    )


def test_no_sender_returns_no_sender():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED")
    service = _service(repo, sender=None)
    result = _run(service.notify_received(REQUEST_ID))
    assert result.outcome == "NO_SENDER"


def test_missing_request_is_reported():
    repo = _FakeRepo()
    sender = _FakeSender()
    service = _service(repo, sender)
    result = _run(service.notify_received("missing-request"))
    assert result.outcome == "REQUEST_NOT_FOUND"


def test_citizen_email_is_taken_from_intake_identity():
    repo = _FakeRepo()
    repo.seed_projection(REQUEST_ID, "CONFIRMED", citizen="vecino.otro@example.com")
    sender = _FakeSender()
    service = _service(repo, sender)
    _run(service.notify_received(REQUEST_ID))
    assert sender.sent[0]["to"] == "vecino.otro@example.com"

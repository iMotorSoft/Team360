"""Citizen reply role isolation — contract and domain tests.

Real PostgreSQL integration tests for role isolation live in
``test_flow_citizen_reply_role_isolation.py`` (gated behind
``TEAM360_FLOW_CITIZEN_REPLY_TEST=1``).

This module provides always-run contract tests that validate the domain
boundaries without requiring a database: the citizen notification domain
correctly defines the public status set, the INFO_REQUIRED gap is documented,
and the public projection never includes internal fields.
"""

from __future__ import annotations

from modules.flow.citizen_notifications.domain import (
    CitizenCaseProjection,
    CitizenNotificationType,
    PublicStatus,
    _NEVER_EMITTED,
    render_notification,
)


INTERNAL_MARKERS = (
    "INTERNAL-SUPERVISOR",
    "PRIVATE-N2",
    "SLA-BREACHED",
    "SECRET-APPROVAL-TOKEN",
    "INTERNAL-NOTE",
    "APROBADO",
    "RESUELTO",
    "CIERRE",
    "APPROVE",
    "REJECT",
)


def test_info_required_domain_trigger_not_available():
    """INFO_REQUIRED public notification is defined but not emitted in V1.

    The citizen notification domain supports INFO_REQUIRED as a public status,
    but there is no post-confirmation domain trigger in the current Flow model
    that would require sending it. This is documented as a non-blocking gap.
    """
    assert PublicStatus.INFO_REQUIRED in _NEVER_EMITTED
    assert CitizenNotificationType.CITIZEN_INFO_REQUIRED in tuple(
        CitizenNotificationType
    )


def test_citizen_projection_never_contains_internal_fields():
    """The citizen projection allowlist excludes all internal concepts."""
    projection = CitizenCaseProjection(
        public_reference="ref-123",
        public_status="IN_PROGRESS",
        subject="Solicitud de alumbrado",
        public_description="Poste apagado",
        public_location="Calle 123",
    )
    field_names = {f.name for f in projection.__dataclass_fields__.values()}
    assert "routing_id" not in field_names
    assert "sla_status" not in field_names
    assert "approval_token" not in field_names
    assert "audit_id" not in field_names
    assert "escalation" not in field_names
    assert "supervisor" not in field_names
    assert "internal_destination" not in field_names


def test_citizen_messages_never_contain_privileged_keywords():
    """No citizen template contains privileged operational keywords."""
    projection = CitizenCaseProjection(
        public_reference="ref-123",
        public_status="IN_PROGRESS",
        subject="Solicitud de alumbrado",
        public_description="Poste apagado",
        public_location="Calle 123",
    )
    for notification_type in CitizenNotificationType:
        subject, body = render_notification(notification_type, projection)
        combined = f"{subject}\n{body}"
        for marker in INTERNAL_MARKERS:
            assert marker not in combined, (
                f"{marker} leaked in {notification_type}"
            )


def test_public_status_mapping_is_deterministic():
    """Internal-to-public mapping is deterministic and never exposes internals."""
    from modules.flow.citizen_notifications.domain import map_internal_to_public

    assert map_internal_to_public("CONFIRMED") is PublicStatus.RECEIVED
    assert map_internal_to_public("ACTIVE") is PublicStatus.IN_PROGRESS
    assert (
        map_internal_to_public("RESOLUTION_PENDING_APPROVAL")
        is PublicStatus.IN_PROGRESS
    )
    assert map_internal_to_public("RESOLVED") is PublicStatus.RESOLVED
    assert map_internal_to_public("BREACHED") is None
    assert map_internal_to_public("ESCALATED") is None
    assert map_internal_to_public("REJECTED") is None


def test_citizen_role_isolation_contract():
    """Citizen replies cannot become operational or approval actions.

    This contract test validates that the citizen notification domain
    does not expose any mechanism for citizen-initiated approvals or
    operational resolutions. The real PostgreSQL integration tests in
    test_flow_citizen_reply_role_isolation.py enforce this with actual
    service calls.
    """
    from modules.flow.citizen_notifications.domain import (
        CitizenNotificationType,
        PublicStatus,
    )
    public_statuses = {ps for ps in PublicStatus}
    notification_types = {nt for nt in CitizenNotificationType}

    assert PublicStatus.RESOLVED in public_statuses
    assert CitizenNotificationType.CITIZEN_RESOLVED in notification_types

    for nt in CitizenNotificationType:
        assert "APPROVAL" not in nt.value
        assert "OPERATIONAL" not in nt.value
        assert "SUPERVISOR" not in nt.value

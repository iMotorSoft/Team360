"""Deterministic public citizen communication policy for Team360 Flow.

The citizen only ever receives a tiny, allow-listed projection of a case.
Internal Flow state (routing levels, SLA, escalations, supervisor decisions,
approval tokens, audit ids, metrics, internal notes) never crosses this
boundary. No LLM renders public text; every message is a fixed template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_CITIZEN_DOMAIN = "alquimiablue.com"

# ASCII control characters are stripped from public text so citizen-provided
# values can never inject headers or control bytes into the rendered message
# (header/subject injection safety). Unicode content is preserved.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class PublicStatus(StrEnum):
    """The only states a citizen may observe about a case."""

    RECEIVED = "RECEIVED"
    IN_PROGRESS = "IN_PROGRESS"
    INFO_REQUIRED = "INFO_REQUIRED"
    RESOLVED = "RESOLVED"


class CitizenNotificationType(StrEnum):
    CITIZEN_RECEIVED = "CITIZEN_RECEIVED"
    CITIZEN_IN_PROGRESS = "CITIZEN_IN_PROGRESS"
    CITIZEN_INFO_REQUIRED = "CITIZEN_INFO_REQUIRED"
    CITIZEN_RESOLVED = "CITIZEN_RESOLVED"


class CitizenDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERY_UNCERTAIN = "DELIVERY_UNCERTAIN"
    DELIVERY_FAILED = "DELIVERY_FAILED"


# ---------------------------------------------------------------------------
# Internal -> public state mapping. The policy translates many internal states
# into a few comprehensible public states and never exposes the internal name.
# ---------------------------------------------------------------------------
_INTERNAL_TO_PUBLIC: dict[str, PublicStatus] = {
    "CONFIRMED": PublicStatus.RECEIVED,
    "ACTIVE": PublicStatus.IN_PROGRESS,
    "RESOLUTION_PENDING_APPROVAL": PublicStatus.IN_PROGRESS,
    "RESOLVED": PublicStatus.RESOLVED,
}

_PUBLIC_TO_NOTIFICATION_TYPE: dict[PublicStatus, CitizenNotificationType] = {
    PublicStatus.RECEIVED: CitizenNotificationType.CITIZEN_RECEIVED,
    PublicStatus.IN_PROGRESS: CitizenNotificationType.CITIZEN_IN_PROGRESS,
    PublicStatus.INFO_REQUIRED: CitizenNotificationType.CITIZEN_INFO_REQUIRED,
    PublicStatus.RESOLVED: CitizenNotificationType.CITIZEN_RESOLVED,
}

# Public states that are never emitted in V1 (kept for the mapping contract).
_NEVER_EMITTED: frozenset[PublicStatus] = frozenset({PublicStatus.INFO_REQUIRED})


def map_internal_to_public(internal_status: str) -> PublicStatus | None:
    """Deterministic internal request status -> public state translation."""
    return _INTERNAL_TO_PUBLIC.get(internal_status)


def public_status_label(public_status: PublicStatus) -> str:
    """Short, non-technical label for reporting; not used in citizen emails."""
    return {
        PublicStatus.RECEIVED: "Recibida",
        PublicStatus.IN_PROGRESS: "En gestión",
        PublicStatus.INFO_REQUIRED: "Se requiere información",
        PublicStatus.RESOLVED: "Finalizada",
    }[public_status]


def notification_type_for_public_status(
    public_status: PublicStatus,
) -> CitizenNotificationType:
    return _PUBLIC_TO_NOTIFICATION_TYPE[public_status]


def dedupe_key(
    request_id: str, notification_type: CitizenNotificationType
) -> str:
    """Deterministic idempotency key; never based on a timestamp."""
    return f"{request_id}:{notification_type.value}"


def citizen_rfc_message_id(
    request_id: str, notification_type: CitizenNotificationType
) -> str:
    """Stable RFC Message-ID so retries can reconcile against Gmail Sent."""
    local = f"team360.citizen.{notification_type.value.lower()}.{request_id}"
    return f"<{local}@{_CITIZEN_DOMAIN}>"


# ---------------------------------------------------------------------------
# Public projection. This is the ONLY citizen-visible view of a case; it is
# built by allowlist (never by serializing an internal object and removing
# keys) and it is what every citizen template consumes.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CitizenCaseProjection:
    public_reference: str
    public_status: str
    subject: str
    public_description: str
    public_location: str | None = None
    requested_information: tuple[str, ...] = ()
    public_resolution_message: str = ""


def public_reference_for(request_id: str) -> str:
    """Readable case number for the citizen.

    V1 uses the stable request UUID as the public reference. There is no
    human-readable case number in the model yet; creating a migration purely
    for cosmetic numbering is intentionally out of scope and documented as a
    gap.
    """
    return request_id


# ---------------------------------------------------------------------------
# Deterministic templates (Spanish, plain text). Only projection fields are
# interpolated; internal operational data can never reach these strings.
# ---------------------------------------------------------------------------
_SUBJECTS: dict[CitizenNotificationType, str] = {
    CitizenNotificationType.CITIZEN_RECEIVED: "LaMuni — Recibimos tu solicitud",
    CitizenNotificationType.CITIZEN_IN_PROGRESS: (
        "LaMuni — Tu solicitud continúa en gestión"
    ),
    CitizenNotificationType.CITIZEN_INFO_REQUIRED: (
        "LaMuni — Necesitamos información para continuar"
    ),
    CitizenNotificationType.CITIZEN_RESOLVED: "LaMuni — Tu solicitud fue finalizada",
}


def notification_subject(notification_type: CitizenNotificationType) -> str:
    return _SUBJECTS[notification_type]


def sanitize_public_text(value: str) -> str:
    """Strip ASCII control characters from citizen-provided public text."""
    return _CONTROL_CHARS.sub(" ", value)


def render_received(projection: CitizenCaseProjection) -> str:
    lines = [
        "Hola.",
        "",
        "Recibimos tu solicitud.",
        "",
        f"Número de solicitud: {projection.public_reference}",
    ]
    if projection.public_description:
        lines.append(f"Motivo: {sanitize_public_text(projection.public_description)}")
    if projection.public_location:
        lines.append(f"Ubicación: {sanitize_public_text(projection.public_location)}")
    lines.extend(
        [
            "",
            "LaMuni realizará el seguimiento correspondiente.",
        ]
    )
    return "\n".join(lines)


def render_in_progress(projection: CitizenCaseProjection) -> str:
    return "\n".join(
        [
            f"Tu solicitud {projection.public_reference} continúa en gestión.",
            "",
            "Estamos trabajando para resolverla.",
        ]
    )


def render_info_required(projection: CitizenCaseProjection) -> str:
    lines = [
        f"Para poder continuar con tu solicitud {projection.public_reference}",
        "necesitamos que nos indiques:",
        "",
    ]
    for item in projection.requested_information:
        lines.append(f"- {sanitize_public_text(item)}")
    lines.extend(
        [
            "",
            "Responder este mensaje permitirá continuar con la gestión.",
        ]
    )
    return "\n".join(lines)


def render_resolved(projection: CitizenCaseProjection) -> str:
    lines = [
        f"Tu solicitud {projection.public_reference} fue atendida.",
        "",
        "La gestión correspondiente quedó finalizada.",
        "",
        "Gracias por comunicarte con LaMuni.",
    ]
    if projection.public_resolution_message:
        lines.append("")
        lines.append(sanitize_public_text(projection.public_resolution_message))
    return "\n".join(lines)


def render_notification(
    notification_type: CitizenNotificationType,
    projection: CitizenCaseProjection,
) -> tuple[str, str]:
    """Return (subject, body) for a public notification type.

    INFO_REQUIRED is defined but not emitted in V1 (no post-confirmation
    domain trigger); rendering it here keeps the template boundary tested
    without inventing a workflow.
    """
    body = {
        CitizenNotificationType.CITIZEN_RECEIVED: render_received,
        CitizenNotificationType.CITIZEN_IN_PROGRESS: render_in_progress,
        CitizenNotificationType.CITIZEN_INFO_REQUIRED: render_info_required,
        CitizenNotificationType.CITIZEN_RESOLVED: render_resolved,
    }[notification_type](projection)
    return notification_subject(notification_type), body


def public_state_for_notification_type(
    notification_type: CitizenNotificationType,
) -> PublicStatus:
    for public_status, mapped in _PUBLIC_TO_NOTIFICATION_TYPE.items():
        if mapped == notification_type:
            return public_status
    raise ValueError(f"Unsupported citizen notification type: {notification_type}")

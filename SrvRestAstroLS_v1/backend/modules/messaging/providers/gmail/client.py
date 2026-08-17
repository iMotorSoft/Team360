"""Minimal reusable Gmail API client for Team360 Messaging."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from modules.messaging.domain import InboundMessage, OutboundMessageReceipt

from .auth import create_delegated_credentials
from .config import GmailConfigurationError, delegated_user


class GmailApiError(RuntimeError):
    """Raised when a Gmail API operation fails."""


@dataclass(frozen=True, slots=True)
class GmailMessageMetadata:
    """Safe metadata exposed by the Gmail provider probe."""

    id: str
    thread_id: str
    from_address: str
    to: str
    subject: str
    date: str


def _decode_body(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _plain_text_body(payload: dict[str, Any]) -> str:
    if payload.get("filename"):
        return ""
    if payload.get("mimeType") == "text/plain":
        return _decode_body(str(payload.get("body", {}).get("data") or "")).strip()
    parts = payload.get("parts") or []
    plain_parts = [_plain_text_body(part) for part in parts if isinstance(part, dict)]
    return "\n\n".join(part for part in plain_parts if part).strip()


def _addresses(header_values: list[str]) -> tuple[str, ...]:
    return tuple(address for _name, address in getaddresses(header_values) if address)


def normalize_gmail_message(payload: dict[str, Any]) -> InboundMessage:
    """Convert a Gmail ``format=full`` response without mutating it."""
    gmail_payload = payload.get("payload") or {}
    headers_list = gmail_payload.get("headers") or []
    headers: dict[str, list[str]] = {}
    for item in headers_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").lower()
        if name:
            headers.setdefault(name, []).append(str(item.get("value") or ""))

    sender_addresses = _addresses(headers.get("from", []))
    recipient_values = headers.get("to", []) + headers.get("cc", [])
    raw_date = next(iter(headers.get("date", [])), "")
    try:
        received_at = parsedate_to_datetime(raw_date) if raw_date else None
    except (TypeError, ValueError, OverflowError):
        received_at = None
    if received_at is None:
        internal_date = str(payload.get("internalDate") or "")
        try:
            received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            received_at = datetime.now(timezone.utc)
    elif received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    external_message_id = str(payload.get("id") or "")
    external_thread_id = str(payload.get("threadId") or "")
    if not external_message_id or not external_thread_id:
        raise GmailApiError("Gmail message response did not contain message/thread ids.")
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id=external_message_id,
        external_thread_id=external_thread_id,
        sender=next(iter(sender_addresses), next(iter(headers.get("from", [])), "")),
        recipients=_addresses(recipient_values),
        subject=next(iter(headers.get("subject", [])), ""),
        text_body=_plain_text_body(gmail_payload),
        received_at=received_at.astimezone(timezone.utc),
        metadata={
            "rfc_message_id": next(iter(headers.get("message-id", [])), ""),
            "in_reply_to": next(iter(headers.get("in-reply-to", [])), ""),
            "references": next(iter(headers.get("references", [])), ""),
            # Deterministic automated-message markers (RFC 3834 auto-replies and
            # bounce reports). These are additive; existing consumers ignore
            # unknown metadata keys and Flow uses them to reject non-human
            # replies without delegating to an LLM.
            "auto_submitted": next(iter(headers.get("auto-submitted", [])), ""),
            "precedence": next(iter(headers.get("precedence", [])), ""),
            "x_autoreply": next(iter(headers.get("x-autoreply", [])), ""),
            "x_autorespond": next(iter(headers.get("x-autorespond", [])), ""),
            "x_failed_recipients": next(
                iter(headers.get("x-failed-recipients", [])), ""
            ),
            "content_type": str(gmail_payload.get("mimeType") or ""),
        },
    )


class GmailClient:
    """Small synchronous wrapper around the Gmail API methods under validation."""

    def __init__(self, subject: str | None = None) -> None:
        self.subject = delegated_user(subject)
        credentials = create_delegated_credentials(self.subject)
        self._service: Resource = build(
            "gmail", "v1", credentials=credentials, cache_discovery=False
        )

    @property
    def sender_address(self) -> str:
        return self.subject

    def list_messages(
        self,
        *,
        max_results: int = 10,
        q: str | None = None,
    ) -> list[str]:
        """List message identifiers without changing mailbox state."""
        if max_results < 1 or max_results > 500:
            raise GmailConfigurationError("max_results must be between 1 and 500.")
        request: dict[str, Any] = {"userId": "me", "maxResults": max_results}
        if q:
            request["q"] = q
        try:
            response = self._service.users().messages().list(**request).execute()
        except HttpError:
            raise GmailApiError("Gmail API failed while listing messages.") from None
        return [item["id"] for item in response.get("messages", []) if item.get("id")]

    def get_message(self, message_id: str) -> GmailMessageMetadata:
        """Fetch only display metadata for one message."""
        if not message_id.strip():
            raise GmailConfigurationError("Gmail message id cannot be empty.")
        try:
            response = (
                self._service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                )
                .execute()
            )
        except HttpError:
            raise GmailApiError(
                "Gmail API failed while reading message metadata."
            ) from None
        headers = {
            item.get("name", "").lower(): item.get("value", "")
            for item in response.get("payload", {}).get("headers", [])
        }
        return GmailMessageMetadata(
            id=response.get("id", ""),
            thread_id=response.get("threadId", ""),
            from_address=headers.get("from", ""),
            to=headers.get("to", ""),
            subject=headers.get("subject", ""),
            date=headers.get("date", ""),
        )

    def get_inbound_message(self, message_id: str) -> InboundMessage:
        """Fetch and normalize one full Gmail message without changing labels."""
        if not message_id.strip():
            raise GmailConfigurationError("Gmail message id cannot be empty.")
        try:
            response = (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError:
            raise GmailApiError("Gmail API failed while reading a message.") from None
        return normalize_gmail_message(response)

    def send_message(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        rfc_message_id: str | None = None,
    ) -> str:
        """Send one plain-text message as the delegated user."""
        recipient = to.strip()
        message_subject = subject.strip()
        if not recipient:
            raise GmailConfigurationError("Message recipient cannot be empty.")
        if not message_subject:
            raise GmailConfigurationError("Message subject cannot be empty.")
        message = EmailMessage()
        message["From"] = self.subject
        message["To"] = recipient
        message["Subject"] = message_subject
        if rfc_message_id is not None:
            message["Message-ID"] = _validate_rfc_message_id(rfc_message_id)
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            response = (
                self._service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
        except HttpError:
            raise GmailApiError("Gmail API failed while sending the message.") from None
        message_id = response.get("id", "")
        if not message_id:
            raise GmailApiError("Gmail API send response did not contain a message id.")
        return message_id

    def find_sent_message_by_rfc_message_id(
        self, rfc_message_id: str
    ) -> str | None:
        """Find a previously accepted send for safe retry reconciliation."""
        validated = _validate_rfc_message_id(rfc_message_id)
        message_ids = self.list_messages(
            max_results=2,
            q=f"in:sent rfc822msgid:{validated}",
        )
        return message_ids[0] if message_ids else None

    def find_sent_message_by_reference(
        self, reference: str, *, to: str | None = None
    ) -> str | None:
        """Find an accepted send by a stable, searchable business reference."""
        normalized = reference.strip()
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,128}", normalized):
            raise GmailConfigurationError("Message reference is invalid.")
        recipient = (to or "").strip()
        if recipient and not re.fullmatch(r"[^\s@]+@[^\s@]+", recipient):
            raise GmailConfigurationError("Message recipient is invalid.")
        recipient_query = f" to:{recipient}" if recipient else ""
        message_ids = self.list_messages(
            max_results=2,
            q=f'in:sent{recipient_query} "{normalized}"',
        )
        return message_ids[0] if message_ids else None

    def get_message_rfc_id(self, message_id: str) -> str | None:
        """Return the RFC Message-ID Gmail actually stored for a message."""
        message = self.get_inbound_message(message_id)
        value = str(message.metadata.get("rfc_message_id") or "").strip()
        return value or None

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
        """Send a plain-text reply and preserve Gmail/RFC thread headers."""
        recipient = to.strip()
        gmail_thread_id = thread_id.strip()
        if not recipient or not gmail_thread_id:
            raise GmailConfigurationError("Reply recipient and thread id are required.")
        message = EmailMessage()
        message["From"] = self.subject
        message["To"] = recipient
        normalized_subject = subject.strip() or "Sin asunto"
        message["Subject"] = (
            normalized_subject
            if normalized_subject.lower().startswith("re:")
            else f"Re: {normalized_subject}"
        )
        if in_reply_to.strip():
            message["In-Reply-To"] = in_reply_to.strip()
        combined_references = " ".join(
            value for value in (references.strip(), in_reply_to.strip()) if value
        )
        if combined_references:
            message["References"] = combined_references
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            response = (
                self._service.users()
                .messages()
                .send(userId="me", body={"raw": raw, "threadId": gmail_thread_id})
                .execute()
            )
        except HttpError:
            raise GmailApiError("Gmail API failed while sending a reply.") from None
        message_id = str(response.get("id") or "")
        response_thread_id = str(response.get("threadId") or gmail_thread_id)
        if not message_id:
            raise GmailApiError("Gmail API send response did not contain a message id.")
        return OutboundMessageReceipt(
            external_message_id=message_id,
            external_thread_id=response_thread_id,
        )


def _validate_rfc_message_id(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"<[^<>\s@]+@[^<>\s@]+>", normalized):
        raise GmailConfigurationError("RFC Message-ID is invalid.")
    return normalized

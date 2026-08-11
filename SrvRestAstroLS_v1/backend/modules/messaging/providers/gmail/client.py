"""Minimal reusable Gmail API client for Team360 Messaging."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

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


class GmailClient:
    """Small synchronous wrapper around the Gmail API methods under validation."""

    def __init__(self, subject: str | None = None) -> None:
        self.subject = delegated_user(subject)
        credentials = create_delegated_credentials(self.subject)
        self._service: Resource = build(
            "gmail", "v1", credentials=credentials, cache_discovery=False
        )

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

    def send_message(self, *, to: str, subject: str, body: str) -> str:
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

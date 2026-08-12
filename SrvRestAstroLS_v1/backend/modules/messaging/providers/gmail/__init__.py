"""Gmail API provider infrastructure for Team360 Messaging."""

from .client import (
    GmailClient,
    GmailMessageMetadata,
    normalize_gmail_message,
)

__all__ = [
    "GmailClient",
    "GmailMessageMetadata",
    "normalize_gmail_message",
]

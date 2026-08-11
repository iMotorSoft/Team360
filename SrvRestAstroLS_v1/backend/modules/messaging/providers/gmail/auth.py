"""Service Account authentication with Gmail Domain-Wide Delegation."""

from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from .config import GMAIL_SCOPES, GmailConfigurationError, service_account_file_from_env


class GmailAuthenticationError(RuntimeError):
    """Raised when Google rejects Gmail provider authentication."""


def create_delegated_credentials(
    subject: str,
    *,
    validate: bool = True,
) -> service_account.Credentials:
    """Create scoped Service Account credentials delegated to ``subject``."""
    delegated_subject = subject.strip()
    if not delegated_subject:
        raise GmailConfigurationError("Delegated Gmail subject cannot be empty.")

    credential_path = Path(service_account_file_from_env()).expanduser()
    if not credential_path.is_file():
        raise GmailConfigurationError(
            "Configured Gmail Service Account credential file does not exist."
        )

    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(credential_path),
            scopes=GMAIL_SCOPES,
        ).with_subject(delegated_subject)
        if validate:
            credentials.refresh(Request())
    except (GoogleAuthError, OSError, ValueError):
        raise GmailAuthenticationError(
            "Google rejected the delegated Gmail Service Account credentials."
        ) from None

    return credentials

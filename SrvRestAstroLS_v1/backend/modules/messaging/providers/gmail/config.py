"""External configuration for the Team360 Gmail provider."""

import os

SERVICE_ACCOUNT_FILE_ENV = "TEAM360_GMAIL_SERVICE_ACCOUNT_FILE"
DELEGATED_USER_ENV = "TEAM360_GMAIL_DELEGATED_USER"
GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.modify",)


class GmailConfigurationError(RuntimeError):
    """Raised when required Gmail provider configuration is invalid."""


def service_account_file_from_env() -> str:
    """Return the configured credential path without reading its contents."""
    value = os.getenv(SERVICE_ACCOUNT_FILE_ENV, "").strip()
    if not value:
        raise GmailConfigurationError(
            f"Missing required environment variable {SERVICE_ACCOUNT_FILE_ENV}."
        )
    return value


def delegated_user(explicit_user: str | None = None) -> str:
    """Resolve a delegated subject from an argument or the optional default."""
    configured_user = (
        os.getenv(DELEGATED_USER_ENV, "") if explicit_user is None else explicit_user
    )
    value = configured_user.strip()
    if not value:
        raise GmailConfigurationError(
            "Delegated Gmail subject is required via --account or "
            f"{DELEGATED_USER_ENV}."
        )
    return value

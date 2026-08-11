"""Explicitly confirmed Gmail API send smoke probe."""

import argparse

from ..auth import GmailAuthenticationError
from ..client import GmailApiError, GmailClient
from ..config import GmailConfigurationError


class ProbeArgumentError(ValueError):
    """Raised for invalid CLI arguments."""


class ProbeArgumentParser(argparse.ArgumentParser):
    """Argument parser that lets the probe emit its failure marker."""

    def error(self, message: str) -> None:
        raise ProbeArgumentError(message)


def parse_args() -> argparse.Namespace:
    """Parse send probe arguments."""
    parser = ProbeArgumentParser(
        description="Gmail delegated send smoke with dry-run default."
    )
    parser.add_argument(
        "--account", help="Delegated Gmail user; defaults to configured env."
    )
    parser.add_argument("--to", required=True, help="Recipient email address.")
    parser.add_argument("--subject", required=True, help="Message subject.")
    parser.add_argument("--body", required=True, help="Plain-text message body.")
    parser.add_argument(
        "--confirm-send", action="store_true", help="Actually send the message."
    )
    return parser.parse_args()


def run(
    account: str | None,
    to: str,
    subject: str,
    body: str,
    *,
    confirm_send: bool,
) -> int:
    """Build the client, then send only after explicit confirmation."""
    if not to.strip() or not subject.strip():
        raise ProbeArgumentError("--to and --subject cannot be empty.")
    client = GmailClient(account)
    if not confirm_send:
        print("DRY RUN: Gmail client validated; no message was sent.")
        print(f"account: {client.subject}")
        print(f"to: {to.strip()}")
        print(f"subject: {subject.strip()}")
        print("TEAM360_GMAIL_SMOKE_SEND_DRY_RUN")
        return 0
    message_id = client.send_message(to=to, subject=subject, body=body)
    print(f"Gmail message id: {message_id}")
    print("TEAM360_GMAIL_SMOKE_SEND_PASS")
    return 0


def main() -> int:
    """Run the send probe and emit a stable typed result marker."""
    try:
        args = parse_args()
        return run(
            args.account,
            args.to,
            args.subject,
            args.body,
            confirm_send=args.confirm_send,
        )
    except (
        ProbeArgumentError,
        GmailConfigurationError,
        GmailAuthenticationError,
        GmailApiError,
    ) as exc:
        print(f"TEAM360_GMAIL_SMOKE_SEND_FAIL: {exc}")
    except Exception as exc:
        print(f"TEAM360_GMAIL_SMOKE_SEND_FAIL: unexpected {type(exc).__name__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only Gmail API smoke probe for a delegated mailbox."""

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
    """Parse read probe arguments."""
    parser = ProbeArgumentParser(
        description="Read-only Gmail delegated mailbox smoke."
    )
    parser.add_argument(
        "--account", help="Delegated Gmail user; defaults to configured env."
    )
    parser.add_argument("--limit", type=int, default=10, help="Messages to list (1-500).")
    parser.add_argument("--query", help="Optional Gmail search query.")
    return parser.parse_args()


def run(account: str | None, limit: int, query: str | None) -> int:
    """List safe metadata without changing messages."""
    client = GmailClient(account)
    for message_id in client.list_messages(max_results=limit, q=query):
        message = client.get_message(message_id)
        print(f"message id: {message.id}")
        print(f"from: {message.from_address}")
        print(f"subject: {message.subject}")
        print(f"date: {message.date}")
        print()
    print("TEAM360_GMAIL_SMOKE_READ_PASS")
    return 0


def main() -> int:
    """Run the read probe and emit a stable typed result marker."""
    try:
        args = parse_args()
        return run(args.account, args.limit, args.query)
    except (
        ProbeArgumentError,
        GmailConfigurationError,
        GmailAuthenticationError,
        GmailApiError,
    ) as exc:
        print(f"TEAM360_GMAIL_SMOKE_READ_FAIL: {exc}")
    except Exception as exc:
        print(f"TEAM360_GMAIL_SMOKE_READ_FAIL: unexpected {type(exc).__name__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

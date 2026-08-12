"""Manual one-request Level 1 routing command; dry-run is the default."""

from __future__ import annotations

import argparse
import asyncio

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.messaging.providers.gmail import GmailClient

from .routing_repository import FlowRoutingPostgresRepository
from .routing_service import FlowRoutingService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Route one confirmed Team360 Flow request to Level 1."
    )
    parser.add_argument("request_id", help="Confirmed Flow request UUID.")
    parser.add_argument(
        "--account", help="Delegated sender; defaults to configured Gmail env."
    )
    parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Send the real email; without this flag the command is a dry run.",
    )
    return parser


async def route_once(
    *, request_id: str, account: str | None, confirm_send: bool
) -> dict[str, object]:
    pool = create_pool(get_database_settings(min_size=1, max_size=3))
    await open_pool(pool)
    try:
        sender = GmailClient(account) if confirm_send else None
        result = await FlowRoutingService(
            pool=pool,
            repository=FlowRoutingPostgresRepository(),
            sender=sender,
        ).route_confirmed_request(request_id, confirm_send=confirm_send)
        assignment = result.assignment
        email = result.email
        return {
            "request_id": result.request_id,
            "routing_id": assignment.id if assignment else None,
            "status": result.status,
            "sector_id": assignment.sector_id if assignment else None,
            "level": assignment.level if assignment else 1,
            "destination": (
                assignment.destination
                if assignment
                else email.destination if email else None
            ),
            "external_message_id": (
                assignment.outbound_external_message_id if assignment else None
            ),
            "sent": result.sent,
            "reconciled": result.reconciled,
            "idempotent": result.idempotent,
            "reason_code": result.reason_code,
        }
    finally:
        await close_pool(pool)


def main() -> int:
    args = _parser().parse_args()
    result = asyncio.run(
        route_once(
            request_id=args.request_id,
            account=args.account,
            confirm_send=args.confirm_send,
        )
    )
    mode = "SEND" if args.confirm_send else "DRY_RUN"
    print(
        f"TEAM360_FLOW_ROUTE_ONCE_{mode} "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )
    return 0 if result["status"] in {"DRY_RUN", "ASSIGNED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

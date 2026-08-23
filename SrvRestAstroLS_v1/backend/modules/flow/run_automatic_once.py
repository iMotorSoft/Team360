"""Finite automatic SLA/escalation run; dry-run by default, no daemon."""

from __future__ import annotations

import argparse
import asyncio

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.messaging.providers.gmail import GmailClient

from .automatic_runner import FlowAutomaticRunner
from .citizen_notifications import (
    CitizenNotificationPostgresRepository,
    FlowCitizenNotificationService,
)
from .escalation_repository import FlowEscalationPostgresRepository
from .poll_once import poll_once
from .routing_repository import FlowRoutingPostgresRepository
from .sla_repository import FlowSLARepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one finite automatic SLA check + escalation cycle. "
            "Dry-run by default: SLA states advance but no escalation or email "
            "is created without --confirm-send."
        )
    )
    parser.add_argument("--account", help="Delegated mesaentrada Gmail account.")
    parser.add_argument(
        "--query",
        default=None,
        help=(
            "Explicit inbox query for controlled recovery. By default the "
            "safe cutoff is loaded from PostgreSQL."
        ),
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Synchronize replies, reconcile SLA and send next-level emails.",
    )
    return parser


async def run_automatic_once(
    *, account: str | None, query: str | None, limit: int, confirm_send: bool
) -> dict[str, object]:
    inbox_processed = 0
    if confirm_send:
        # Ordering is intentional: Gmail received_at evidence is persisted
        # before the SLA check reconciles and before the final locked
        # eligibility reread inside the escalation service.
        sync_result = await poll_once(account=account, query=query, limit=limit)
        inbox_processed = sync_result["processed"]

    pool = create_pool(get_database_settings(min_size=1, max_size=3))
    await open_pool(pool)
    try:
        gmail = GmailClient(account) if confirm_send else None
        citizen_service = FlowCitizenNotificationService(
            pool=pool,
            repository=CitizenNotificationPostgresRepository(),
            sender=gmail,
        )
        summary = await FlowAutomaticRunner(
            pool=pool,
            sla_repository=FlowSLARepository(),
            escalation_repository=FlowEscalationPostgresRepository(),
            routing_repository=FlowRoutingPostgresRepository(),
            sender=gmail,
            citizen_notifier=citizen_service.notify_in_progress,
        ).run_once(confirm_send=confirm_send)
        result: dict[str, object] = summary.as_dict()
        result["inbox_processed"] = inbox_processed
        return result
    finally:
        await close_pool(pool)


def main() -> int:
    args = _parser().parse_args()
    if args.limit < 1 or args.limit > 500:
        raise SystemExit("--limit must be between 1 and 500")
    result = asyncio.run(
        run_automatic_once(
            account=args.account,
            query=args.query,
            limit=args.limit,
            confirm_send=args.confirm_send,
        )
    )
    mode = "SEND" if args.confirm_send else "DRY_RUN"
    outcomes = result.pop("outcomes")
    print(
        f"TEAM360_FLOW_AUTOMATIC_RUN_ONCE_{mode} "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )
    for outcome in outcomes:
        print(
            "flow automatic escalation "
            f"request_id={outcome['request_id']} "
            f"escalation_id={outcome['escalation_id']} "
            f"from_level={outcome['from_level']} to_level={outcome['to_level']} "
            f"routing_id={outcome['routing_id']} status={outcome['status']} "
            f"destination={outcome['destination']} sent={outcome['sent']} "
            f"reconciled={outcome['reconciled']} idempotent={outcome['idempotent']} "
            f"reason={outcome['reason_code']}"
        )
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

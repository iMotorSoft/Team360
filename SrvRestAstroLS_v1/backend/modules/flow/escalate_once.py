"""Finite, dry-run-by-default N1 to N2 escalation command."""

from __future__ import annotations

import argparse
import asyncio
import os

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.messaging.providers.gmail import GmailClient

from .check_sla_once import check_sla_once
from .escalation_repository import FlowEscalationPostgresRepository
from .escalation_service import FlowEscalationService
from .poll_once import poll_once
from .routing_repository import FlowRoutingPostgresRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Escalate final Level 1 SLA breaches to Level 2. Dry-run by default."
    )
    parser.add_argument("--account", help="Delegated mesaentrada Gmail account.")
    parser.add_argument(
        "--query",
        default=os.environ.get("TEAM360_FLOW_GMAIL_QUERY", "in:inbox"),
        help="Inbox query used for the pre-send operational synchronization.",
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Synchronize replies, reconcile SLA and send real Level 2 email.",
    )
    return parser


async def escalate_once(
    *, account: str | None, query: str, limit: int, confirm_send: bool
) -> dict[str, object]:
    sync_result = None
    sla_result = None
    if confirm_send:
        # Ordering is intentional: Gmail received_at evidence is persisted before
        # the SLA is reconciled and before the final locked eligibility reread.
        sync_result = await poll_once(account=account, query=query, limit=limit)
        sla_result = await check_sla_once()

    pool = create_pool(get_database_settings(min_size=1, max_size=3))
    await open_pool(pool)
    try:
        summary = await FlowEscalationService(
            pool=pool,
            repository=FlowEscalationPostgresRepository(),
            routing_repository=FlowRoutingPostgresRepository(),
            sender=GmailClient(account) if confirm_send else None,
        ).escalate_once(confirm_send=confirm_send)
        return {
            "eligible": summary.eligible,
            "created": summary.created,
            "sent": summary.sent,
            "completed": summary.completed,
            "failed": summary.failed,
            "idempotent": summary.idempotent,
            "inbox_processed": sync_result["processed"] if sync_result else 0,
            "sla_reconciled": sla_result["reconciled"] if sla_result else 0,
            "outcomes": summary.outcomes,
        }
    finally:
        await close_pool(pool)


def main() -> int:
    args = _parser().parse_args()
    if args.limit < 1 or args.limit > 500:
        raise SystemExit("--limit must be between 1 and 500")
    result = asyncio.run(
        escalate_once(
            account=args.account,
            query=args.query,
            limit=args.limit,
            confirm_send=args.confirm_send,
        )
    )
    mode = "SEND" if args.confirm_send else "DRY_RUN"
    outcomes = result.pop("outcomes")
    print(
        f"TEAM360_FLOW_ESCALATE_ONCE_{mode} "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )
    for outcome in outcomes:
        print(
            "flow escalation "
            f"request_id={outcome.request_id} escalation_id={outcome.escalation_id} "
            f"routing_id={outcome.routing_id} status={outcome.status} "
            f"destination={outcome.destination} sent={outcome.sent} "
            f"reconciled={outcome.reconciled} idempotent={outcome.idempotent} "
            f"reason={outcome.reason_code}"
        )
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

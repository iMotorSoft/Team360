"""Manual, finite Gmail-to-Flow intake cycle for the V1 gate."""

from __future__ import annotations

import argparse
import asyncio
import os

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.messaging.providers.gmail import GmailClient

from .approval_ai import LiteLLMApprovalInterpreter
from .audit_repository import FlowAuditRepository
from .citizen_notifications import (
    CitizenNotificationPostgresRepository,
    FlowCitizenNotificationService,
)
from .closure_repository import FlowClosurePostgresRepository
from .closure_service import FlowClosureService
from .domain import is_automated_message
from .intake.ai import LiteLLMFlowIntakeInterpreter
from .operational_ai import LiteLLMOperationalInterpreter
from .operational_repository import FlowOperationalPostgresRepository
from .operational_service import FlowOperationalReplyService
from .repository import FlowPostgresRepository
from .service import FlowIntakeService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one finite Team360 Flow Gmail intake cycle.")
    parser.add_argument("--account", help="Delegated Gmail mailbox; defaults to configured env.")
    parser.add_argument(
        "--query",
        default=os.environ.get("TEAM360_FLOW_GMAIL_QUERY", "in:inbox"),
        help="Gmail search query; idempotency does not depend on UNREAD.",
    )
    parser.add_argument("--limit", type=int, default=25)
    return parser


async def poll_once(*, account: str | None, query: str, limit: int) -> dict[str, int]:
    gmail = GmailClient(account)
    pool = create_pool(get_database_settings(min_size=1, max_size=3))
    await open_pool(pool)
    processed = 0
    duplicates = 0
    confirmations = 0
    confirmed_requests = 0
    operational_replies = 0
    operational_duplicates = 0
    operational_ignored = 0
    operational_unauthorized = 0
    automated = 0
    proposals = 0
    approvals_sent = 0
    approval_replies = 0
    approval_duplicates = 0
    resolved = 0
    rejected = 0
    citizen_received = 0
    citizen_in_progress = 0
    citizen_resolved = 0
    citizen_skipped = 0
    citizen_failed = 0
    try:
        service = FlowIntakeService(
            pool=pool,
            repository=FlowPostgresRepository(),
            interpreter=LiteLLMFlowIntakeInterpreter(),
            reply_sender=gmail,
        )
        citizen_service = FlowCitizenNotificationService(
            pool=pool,
            repository=CitizenNotificationPostgresRepository(),
            sender=gmail,
        )
        closure_service = FlowClosureService(
            pool=pool,
            repository=FlowClosurePostgresRepository(),
            audit_repository=FlowAuditRepository(),
            interpreter=LiteLLMApprovalInterpreter(),
            sender=gmail,
        )
        operational_service = FlowOperationalReplyService(
            pool=pool,
            repository=FlowOperationalPostgresRepository(),
            interpreter=LiteLLMOperationalInterpreter(),
            closure=closure_service,
        )
        message_ids = gmail.list_messages(max_results=limit, q=query)
        for message_id in reversed(message_ids):
            message = gmail.get_inbound_message(message_id)
            # Deterministic first gate: RFC 3834 auto-replies and bounces are
            # never citizen intake, operational replies or approval decisions.
            if is_automated_message(message):
                automated += 1
                print(
                    "flow automated message ignored "
                    f"message_id={message.external_message_id} "
                    f"sender={message.sender}"
                )
                continue
            operational = await operational_service.process_if_operational(message)
            if operational.matched:
                if operational.ignored:
                    operational_ignored += 1
                    continue
                if operational.processed:
                    processed += 1
                    operational_replies += 1
                    if operational.proposal is not None:
                        proposals += 1
                        approvals_sent += int(operational.proposal.sent)
                    if operational.action in {
                        "ACK_OR_PROGRESS",
                        "RESOLUTION_PROPOSED",
                    } and operational.request_id:
                        citizen = await citizen_service.notify_in_progress(
                            operational.request_id
                        )
                        if citizen.outcome in ("SENT", "SENT_RECONCILED"):
                            citizen_in_progress += 1
                        elif citizen.outcome in (
                            "DELIVERY_FAILED",
                            "DELIVERY_UNCERTAIN",
                        ):
                            citizen_failed += 1
                        else:
                            citizen_skipped += 1
                    print(
                        "flow operational reply processed "
                        f"message_id={message.external_message_id} "
                        f"request_id={operational.request_id} "
                        f"routing_id={operational.routing_id} "
                        f"level={operational.level} "
                        f"action={operational.action} status={operational.status} "
                        f"correlation={operational.correlation_method}"
                    )
                else:
                    duplicates += 1
                    if operational.authorized:
                        operational_duplicates += 1
                    else:
                        operational_unauthorized += 1
                continue

            approval = await closure_service.process_approval_reply(message)
            if approval.matched:
                if approval.processed:
                    processed += 1
                    approval_replies += 1
                    resolved += int(
                        approval.decision is not None
                        and approval.decision.value == "APPROVE"
                    )
                    rejected += int(
                        approval.decision is not None
                        and approval.decision.value == "REJECT"
                    )
                    if (
                        approval.decision is not None
                        and approval.decision.value == "APPROVE"
                        and approval.request_id
                    ):
                        citizen = await citizen_service.notify_resolved(
                            approval.request_id
                        )
                        if citizen.outcome in ("SENT", "SENT_RECONCILED"):
                            citizen_resolved += 1
                        elif citizen.outcome in (
                            "DELIVERY_FAILED",
                            "DELIVERY_UNCERTAIN",
                        ):
                            citizen_failed += 1
                        else:
                            citizen_skipped += 1
                    print(
                        "flow approval reply processed "
                        f"message_id={message.external_message_id} "
                        f"request_id={approval.request_id} "
                        f"approval_id={approval.approval_id} "
                        f"decision={approval.decision} "
                        f"authorized={approval.authorized} "
                        f"correlation={approval.correlation_method}"
                    )
                else:
                    duplicates += 1
                    approval_duplicates += 1
                continue

            result = await service.process(message)
            if result.processed:
                processed += 1
                confirmations += int(result.outbound_message_id is not None)
                confirmed_requests += result.confirmed_count
                if result.confirmed_count and result.conversation_id:
                    for citizen in (
                        await citizen_service.notify_received_for_conversation(
                            result.conversation_id
                        )
                    ):
                        if citizen.outcome in ("SENT", "SENT_RECONCILED"):
                            citizen_received += 1
                        elif citizen.outcome in (
                            "DELIVERY_FAILED",
                            "DELIVERY_UNCERTAIN",
                        ):
                            citizen_failed += 1
                        else:
                            citizen_skipped += 1
                print(
                    "flow message processed "
                    f"message_id={message.external_message_id} "
                    f"thread_id={message.external_thread_id} "
                    f"state={result.state} candidates={result.candidate_count} "
                    f"confirmed={result.confirmed_count}"
                )
            else:
                duplicates += 1
        return {
            "listed": len(message_ids),
            "processed": processed,
            "duplicates": duplicates,
            "confirmations_sent": confirmations,
            "confirmed_requests": confirmed_requests,
            "operational_replies": operational_replies,
            "operational_duplicates": operational_duplicates,
            "operational_ignored": operational_ignored,
            "operational_unauthorized": operational_unauthorized,
            "automated": automated,
            "proposals": proposals,
            "approvals_sent": approvals_sent,
            "approval_replies": approval_replies,
            "approval_duplicates": approval_duplicates,
            "resolved": resolved,
            "rejected": rejected,
            "citizen_received": citizen_received,
            "citizen_in_progress": citizen_in_progress,
            "citizen_resolved": citizen_resolved,
            "citizen_skipped": citizen_skipped,
            "citizen_failed": citizen_failed,
        }
    finally:
        await close_pool(pool)


def main() -> int:
    args = _parser().parse_args()
    if args.limit < 1 or args.limit > 500:
        raise SystemExit("--limit must be between 1 and 500")
    result = asyncio.run(poll_once(account=args.account, query=args.query, limit=args.limit))
    print(
        "TEAM360_FLOW_POLL_ONCE_PASS "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Manual, finite Gmail-to-Flow intake cycle for the V1 gate."""

from __future__ import annotations

import argparse
import asyncio
import os

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings
from modules.messaging.providers.gmail import GmailClient

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
    try:
        service = FlowIntakeService(
            pool=pool,
            repository=FlowPostgresRepository(),
            interpreter=LiteLLMFlowIntakeInterpreter(),
            reply_sender=gmail,
        )
        operational_service = FlowOperationalReplyService(
            pool=pool,
            repository=FlowOperationalPostgresRepository(),
            interpreter=LiteLLMOperationalInterpreter(),
        )
        message_ids = gmail.list_messages(max_results=limit, q=query)
        for message_id in reversed(message_ids):
            message = gmail.get_inbound_message(message_id)
            operational = await operational_service.process_if_operational(message)
            if operational.matched:
                if operational.processed:
                    processed += 1
                    operational_replies += 1
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
                    operational_duplicates += 1
                continue
            result = await service.process(message)
            if result.processed:
                processed += 1
                confirmations += int(result.outbound_message_id is not None)
                confirmed_requests += result.confirmed_count
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

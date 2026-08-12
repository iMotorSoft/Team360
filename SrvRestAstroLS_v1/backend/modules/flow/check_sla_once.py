"""Manual finite first-response SLA checker; no scheduler or worker."""

from __future__ import annotations

import asyncio

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings

from .sla_repository import FlowSLARepository
from .sla_service import FlowFirstResponseSLAService


async def check_sla_once() -> dict[str, int]:
    pool = create_pool(get_database_settings(min_size=1, max_size=3))
    await open_pool(pool)
    try:
        result = await FlowFirstResponseSLAService(
            pool=pool, repository=FlowSLARepository()
        ).check_once()
        return {
            "checked": result.checked,
            "pending": result.pending,
            "met": result.met,
            "breached": result.breached,
            "reconciled": result.reconciled,
        }
    finally:
        await close_pool(pool)


def main() -> int:
    result = asyncio.run(check_sla_once())
    print(
        "TEAM360_FLOW_CHECK_SLA_ONCE_PASS "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

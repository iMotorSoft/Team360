"""Finite read-only executive case query command; no workflow mutation."""

from __future__ import annotations

import argparse
import asyncio
import json

from modules.db.pool import close_pool, create_pool, open_pool
from modules.db.settings import get_database_settings

from .audit_repository import FlowAuditRepository
from .closure_repository import FlowClosurePostgresRepository
from .executive_ai import LiteLLMExecutiveInterpreter
from .executive_service import FlowExecutiveAuditService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query one Team360 Flow case for executive/Directorio use. Read-only."
    )
    parser.add_argument("request_id", help="Flow request UUID.")
    parser.add_argument(
        "--question",
        help="Optional executive question interpreted with LiteLLM over the facts.",
    )
    return parser


async def executive_query_once(
    *, request_id: str, question: str | None
) -> dict[str, object]:
    pool = create_pool(get_database_settings(min_size=1, max_size=3))
    await open_pool(pool)
    try:
        service = FlowExecutiveAuditService(
            pool=pool,
            closure_repository=FlowClosurePostgresRepository(),
            audit_repository=FlowAuditRepository(),
            interpreter=LiteLLMExecutiveInterpreter() if question else None,
        )
        return await service.query_case(request_id, question=question)
    finally:
        await close_pool(pool)


def main() -> int:
    args = _parser().parse_args()
    view = asyncio.run(
        executive_query_once(request_id=args.request_id, question=args.question)
    )
    print(json.dumps(view, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

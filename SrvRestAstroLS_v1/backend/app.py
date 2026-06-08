"""Team360 Litestar application entrypoint.

The app factory does not open any DB pool at import time.
Pool lifecycle is managed via on_startup / on_shutdown.
"""

from __future__ import annotations

import os

from litestar import Litestar, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_404_NOT_FOUND

from modules.db.errors import DatabasePoolNotInitializedError
from modules.db.pool import close_pool, get_pool, open_pool

from routes.automation_diagnosis import classify, save_answer, start_session
from routes.diagnosis import (
    public_get_session,
    public_lead,
    public_message,
    public_start,
    public_submit_checklist,
)
from routes.health import get_health


@get("/api/health")
async def health() -> dict[str, str]:
    return get_health()


@get("/health")
async def health_root() -> dict[str, str]:
    return get_health()


async def _open_db_pool() -> None:
    if os.environ.get("AUTOMATION_DIAGNOSIS_REPOSITORY") != "postgres":
        return
    try:
        pool = get_pool()
        await open_pool(pool)
    except DatabasePoolNotInitializedError:
        pass


async def _close_db_pool() -> None:
    if os.environ.get("AUTOMATION_DIAGNOSIS_REPOSITORY") != "postgres":
        return
    try:
        pool = get_pool()
        await close_pool(pool)
    except DatabasePoolNotInitializedError:
        pass


def create_app() -> Litestar:
    return Litestar(
        route_handlers=[
            health,
            health_root,
            start_session,
            save_answer,
            classify,
            public_start,
            public_message,
            public_get_session,
            public_submit_checklist,
            public_lead,
        ],
        on_startup=[_open_db_pool],
        on_shutdown=[_close_db_pool],
        debug=True,
    )


app = create_app()

"""Team360 Litestar application entrypoint.

The app factory does not open any DB pool at import time.
Pool lifecycle is managed via on_startup / on_shutdown.
"""

from __future__ import annotations

import os

from litestar import Litestar, get
from litestar.config.cors import CORSConfig

from modules.db.errors import DatabasePoolNotInitializedError
from modules.db.pool import close_pool, get_pool, open_pool

from routes.automation_diagnosis import classify, save_answer, start_session
from routes.diagnosis import (
    public_embed_auth,
    public_get_session,
    public_lead,
    public_message,
    public_start,
    public_submit_checklist,
    public_turn,
)
from routes.health import get_health
from routes.sales_diagnosis_runtime import sales_diagnosis_turn
from routes.sales_diagnosis_runtime_dev import dev_sales_diagnosis_turn


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


def _backend_debug_enabled() -> bool:
    value = os.environ.get("TEAM360_BACKEND_DEBUG", "").strip().lower()
    return value in {"1", "true", "yes", "on", "debug", "development"}


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
            public_embed_auth,
            public_turn,
            sales_diagnosis_turn,
            dev_sales_diagnosis_turn,
        ],
        on_startup=[_open_db_pool],
        on_shutdown=[_close_db_pool],
        cors_config=CORSConfig(
            allow_origins=[
                "http://localhost:3050",
                "http://127.0.0.1:3050",
            ],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
        debug=_backend_debug_enabled(),
    )


app = create_app()

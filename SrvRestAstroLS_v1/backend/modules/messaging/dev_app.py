"""Opt-in DEV bootstrap using the same Messaging routes, with no other modules."""
from __future__ import annotations

import argparse
import asyncio
import os

from litestar import Litestar, get
from litestar.exceptions import HTTPException

from modules.db.pool import create_pool, get_pool, open_pool, close_pool, set_pool
from modules.db.settings import get_database_settings
from modules.db.transaction import transaction
from .providers.evolution.config import EvolutionConfig
from .repository import MessagingRepository
from .routes import ROUTE_HANDLERS
from .settings import MessagingDevSettings


def validate_config():
    if os.getenv('TEAM360_DEV_PROFILE') != 'messaging-only':
        raise ValueError('Explicit messaging-only DEV profile required')
    return MessagingDevSettings.from_env(), EvolutionConfig.from_env()


async def validate_database(pool, settings, config):
    async with transaction(pool) as conn:
        await conn.execute('SELECT 1')
        await MessagingRepository().binding(conn, workspace_slug=settings.workspace_slug,
            channel_alias=settings.channel_alias, provider='evolution', instance=config.instance)
        await MessagingRepository().validate_transport_schema(conn)


async def startup(app: Litestar) -> None:
    pool = None
    try:
        settings, config = validate_config()
        pool = create_pool(get_database_settings(min_size=1, max_size=5, connect_timeout=5))
        await open_pool(pool)
        await validate_database(pool, settings, config)
        set_pool(pool)
        app.state.messaging_pool = pool
    except Exception:
        if pool is not None:
            await close_pool(pool)
        # Never propagate a DSN, provider credentials or private identity.
        raise RuntimeError('Messaging DEV startup failed: verify configuration, PostgreSQL and migration 026') from None


async def shutdown(app: Litestar) -> None:
    pool = getattr(app.state, 'messaging_pool', None)
    if pool is not None:
        await close_pool(pool)


@get('/health')
async def health() -> dict[str, object]:
    try:
        async with transaction(get_pool()) as conn:
            await conn.execute('SELECT 1')
    except Exception:
        raise HTTPException(status_code=503, detail='Messaging PostgreSQL unavailable') from None
    return {'status': 'ok', 'profile': 'messaging-only', 'postgres': 'ok'}


# @lat: [[team360-platform#Team360 Platform#WhatsApp transport boundary#Messaging-only DEV bootstrap]]
def create_app() -> Litestar:
    """Importing the app opens no connection and imports no registry/Flow/AI."""
    return Litestar(route_handlers=[health, *ROUTE_HANDLERS], on_startup=[startup],
                    on_shutdown=[shutdown], debug=False, openapi_config=None)


app = create_app()


async def preflight():
    pool = None
    try:
        settings, config = validate_config()
        pool = create_pool(get_database_settings(min_size=1, max_size=1, connect_timeout=5))
        await open_pool(pool)
        await validate_database(pool, settings, config)
        print('[ok] Messaging configuration, Team360 PostgreSQL and migration 026')
    except Exception:
        print('[fail] Messaging preflight: verify DEV configuration, Team360 PostgreSQL and migration 026')
        return 1
    finally:
        if pool is not None:
            await close_pool(pool)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', required=True)
    parser.parse_args()
    raise SystemExit(asyncio.run(preflight()))

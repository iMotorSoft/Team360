"""Independent, opt-in TelchiAI DEV ASGI app; no central factory or transports."""
from __future__ import annotations

import argparse
import asyncio
import os

from litestar import Litestar, get

from modules.db.pool import create_pool, open_pool, close_pool
from modules.db.settings import get_database_settings
from .console_http import ConsoleHTTPRuntime, load_config
from .routes import ROUTE_HANDLERS


def validate_config():
    if (os.getenv('TEAM360_ENV') not in {'dev', 'development'}
            or os.getenv('TEAM360_DEV_PROFILE') != 'telchiai-only'
            or os.getenv('TEAM360_TELCHI_CONSOLE_ENABLED') != '1'):
        raise ValueError('explicit_telchiai_dev_profile_required')
    return load_config()


class DependencyBlocked(RuntimeError):
    """Only fixed, public-safe dependency names may cross the startup boundary."""


async def validate_dependencies(runtime):
    # Reuse the approved research provider, not a new model/router or fallback.
    from .exploratory_sql.research import LunaSQL
    try:
        async with runtime.service.pool.connection() as conn:
            async with conn.transaction():
                await runtime.service.repository.enabled_permissions(conn, runtime.service.workspace)
    except Exception:
        raise DependencyBlocked('PostgreSQL authorization schema') from None
    try:
        # AccreditedReader resolves CURRENT and rejects a different publication.
        access = await asyncio.to_thread(runtime.service.reader.get_current_foundation)
    except Exception:
        raise DependencyBlocked('authorized Foundation CURRENT') from None
    try:
        await LunaSQL(system='Return exactly this JSON object: {"ok":true}.', max_output_tokens=1024).next(
            {'preflight': True}, timeout=45)
    except Exception:
        raise DependencyBlocked('existing Luna provider/auth/model/quota') from None
    return access.foundation_publication_id


async def startup(app: Litestar) -> None:
    pool = None
    stage = 'explicit DEV profile/private configuration'
    try:
        config = validate_config()
        stage = 'PostgreSQL connection'
        pool = create_pool(get_database_settings(min_size=1, max_size=3,
            connect_timeout=5, application_name='team360-telchiai'))
        await open_pool(pool)
        await pool.wait(timeout=5)
        stage = 'private runtime configuration'
        runtime = ConsoleHTTPRuntime(config, pool=pool)
        stage = 'runtime dependencies'
        publication = await validate_dependencies(runtime)
        app.state.telchi_console_runtime = runtime
        app.state.telchi_pool = pool
        app.state.telchi_publication = publication
    except BaseException as exc:
        if pool is not None:
            await close_pool(pool)
        if isinstance(exc, asyncio.CancelledError):
            raise
        if isinstance(exc, DependencyBlocked):
            stage = str(exc)
        raise RuntimeError(f'TelchiAI startup blocked: {stage}; no external service was started') from None


async def shutdown(app: Litestar) -> None:
    pool = getattr(app.state, 'telchi_pool', None)
    if pool is not None:
        await close_pool(pool)
        app.state.telchi_pool = None
        app.state.telchi_console_runtime = None


@get('/api/telchiai/health')
async def health() -> dict[str, str]:
    # Liveness only; startup preflight is not a perpetual provider health claim.
    return {'status': 'ok', 'service': 'telchiai', 'profile': 'telchiai-only'}


def create_app() -> Litestar:
    return Litestar(route_handlers=[health, *ROUTE_HANDLERS],
        on_startup=[startup], on_shutdown=[shutdown], debug=False, openapi_config=None)


app = create_app()


async def preflight():
    application = create_app()
    try:
        await startup(application)
        print('[ok] TelchiAI configuration, PostgreSQL, accredited CURRENT and Luna provider')
        return 0
    except RuntimeError as exc:
        print(f'[blocked] {exc}')
        return 1
    finally:
        await shutdown(application)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', required=True)
    parser.parse_args()
    raise SystemExit(asyncio.run(preflight()))

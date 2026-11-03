"""Compatible legacy base plus explicitly selected Srv05 extensions.

Source deploy: uv run uvicorn ls_iMotorSoft_Srv05:app from backend checkout.
Evolution is opt-in and remains DEV-only; import opens no clients or workers.
"""
from litestar import Litestar
from ls_iMotorSoft_Srv01 import create_app as create_legacy_app
from modules.srv05_settings import Srv05Settings


async def _validate_evolution_binding(app: Litestar) -> None:
    """Read-only validation using the existing pool, before Flow starts."""
    from modules.db.pool import get_pool
    from modules.db.transaction import transaction
    from modules.messaging.repository import MessagingRepository
    settings = app.state.srv05_settings
    try:
        async with transaction(get_pool()) as conn:
            binding = await MessagingRepository().binding(
                conn, workspace_slug=settings.messaging.workspace_slug,
                channel_alias=settings.messaging.channel_alias,
                provider=settings.provider, instance=settings.evolution.instance)
            if binding is not None:
                horizontal = settings.messaging.dispatch_mode == 'horizontal_v1'
                if horizontal != (binding.environment is not None):
                    raise ValueError('Runtime/channel dispatcher mismatch')
                if horizontal and binding.receiver_context != settings.recipient:
                    raise ValueError('Runtime/channel receiver mismatch')
            await MessagingRepository().validate_transport_schema(conn)
        if binding is None:
            raise ValueError('Srv05 V1 binding required')
        if (settings.messaging.dispatch_mode == 'horizontal_v1'
                and binding.module not in (app.state.messaging_handlers or {})):
            raise ValueError('Approved module handler required')
        await app.state.transport_v1.start(get_pool(), binding)
        if settings.messaging.dispatch_mode == 'horizontal_v1':
            from modules.messaging.webhooks.evolution_whatsapp import build_service
            from modules.messaging.identity import PhoneIdentityRepository
            async with transaction(get_pool()) as conn:
                await PhoneIdentityRepository().validate_schema(conn)
            # Validate dispatcher even with admission closed. Provider selection
            # is fixed by composition, not by a request or environment fallback.
            if app.state.transport_v1.admission_open:
                await build_service(settings.messaging, settings.evolution,
                                    handlers=app.state.messaging_handlers,
                                    transport_runtime=app.state.transport_v1)
    except Exception:
        await app.state.transport_v1.stop()
        # Litestar's lifespan exit stack runs the base shutdown hooks even
        # when startup fails. Keep resource ownership in that single lifecycle.
        raise RuntimeError('Srv05 Evolution binding/schema unavailable') from None


async def _stop_transport_v1(app: Litestar) -> None:
    await app.state.transport_v1.stop()


def create_app(*, messaging_handlers=None) -> Litestar:
    """Install explicitly supplied, trusted registrations; never import from payloads.

    A deployment factory supplies module handlers through this argument. Invalid
    registrations abort composition; empty registries abort horizontal startup.
    """
    from types import MappingProxyType
    settings = Srv05Settings.from_env()
    registrations = dict(messaging_handlers or {})
    runtime = None
    if settings.evolution_enabled:
        from modules.messaging.transport_runtime import TransportRuntime
        runtime = TransportRuntime.from_env(settings.evolution)
    if settings.evolution_enabled and settings.messaging.dispatch_mode == 'horizontal_v1':
        from modules.messaging.handlers import HandlerRegistration
        if any(
            not isinstance(name, str) or not name.strip()
            or not isinstance(registration, HandlerRegistration)
            or registration.environment != runtime.document['scope']['environment']
            or not callable(getattr(registration.handler, 'handle', None))
            for name, registration in registrations.items()
        ):
            raise ValueError('Approved DEV horizontal handler registry required')
    handlers = ()
    if settings.evolution_enabled:
        from modules.messaging.routes import ROUTE_HANDLERS
        handlers = ROUTE_HANDLERS
    application = create_legacy_app(extra_route_handlers=handlers)
    application.state.srv05_settings = settings
    application.state.messaging_handlers = MappingProxyType(registrations) if registrations else None
    if settings.evolution_enabled:
        application.state.transport_v1 = runtime
        application.on_startup.insert(1, _validate_evolution_binding)
        application.on_shutdown.insert(0, _stop_transport_v1)
    return application


app = create_app()
__all__ = ['app', 'create_app']

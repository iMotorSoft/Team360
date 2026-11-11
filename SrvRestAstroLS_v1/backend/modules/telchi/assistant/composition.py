"""Explicit Telchi deployment composition using Srv05's existing injection port.

No env-driven auto-enable, service startup, migrations or permission defaults.
Operator must supply an approved business policy and existing Team360 pool.
"""
from .handler import BusinessAuthorization, PostgresConversationStore, TelchiHandler, registration


def create_telchi_handler(*, policy, pool=None):
    """One functional composition for WhatsApp and internal durable validation."""
    if pool is None:
        # Resolve after the existing Srv05 lifespan opens Team360's pool. No new pool.
        from modules.db.pool import get_pool
        pool = get_pool
    from modules.business_semantics.resolver import BusinessConceptResolver, VectorCandidatePolicy
    from modules.business_semantics.embeddings import EmbeddingConfiguration, LiteLLMEmbeddingAdapter
    import os
    resolver = None
    semantics_connection = None
    if os.getenv('TEAM360_BUSINESS_SEMANTICS') == '1':
        # Explicit DEV rollout; absent vector configuration remains observable textual mode.
        if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
            raise ValueError('business_semantics_V1_DEV_only')
        from modules.business_semantics.runtime_connection import RestrictedSemanticsConnection
        config_path = os.getenv('TEAM360_SEMANTICS_AUTH_CONFIG')
        if not config_path:
            raise ValueError('restricted_semantics_configuration_required')
        semantics_connection = RestrictedSemanticsConnection(config_path)
        adapter = None
        if os.getenv('TEAM360_SEMANTICS_EMBEDDING_ALIAS'):
            adapter = LiteLLMEmbeddingAdapter(EmbeddingConfiguration.from_env())
        resolver = BusinessConceptResolver(embeddings=adapter, vector_policy=VectorCandidatePolicy.from_env())
    if os.getenv('TEAM360_TELCHI_DURABLE') not in {None, '0', '1'}:
        raise ValueError('Invalid durable rollout setting')
    durable = os.getenv('TEAM360_TELCHI_DURABLE') == '1'
    if durable and os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
        raise ValueError('Durable Telchi rollout is DEV only')
    researcher = None
    if os.getenv('TEAM360_TELCHI_FREE_ANALYSIS') == '1':
        # Same investigator as Console, resolved in process from the already
        # authenticated WhatsApp identity. No HTTP runtime is started here.
        from ..console_http import load_config
        from ..research_port import build_researcher
        researcher = build_researcher(pool=pool, config=load_config())
    from .capabilities import SalesCapabilities
    handler = TelchiHandler(store=PostgresConversationStore(pool), authorization=BusinessAuthorization(policy),
                           concept_resolver=resolver, semantics_connection=semantics_connection,
                           # Research is durable and has no total-turn deadline;
                           # the fast path may retain its short technical guard.
                           turn_timeout_seconds=None if researcher is not None else (300 if durable else 80),
                           capabilities=SalesCapabilities(timeout_seconds=180) if durable else None,
                           researcher=researcher)
    return handler


def create_telchi_app(*, policy, pool=None):
    from ls_iMotorSoft_Srv05 import create_app
    import os
    handler = create_telchi_handler(policy=policy, pool=pool)
    app = create_app(messaging_handlers={'telchi': registration(handler)})
    if os.getenv('TEAM360_TELCHI_DURABLE') == '1':
        if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
            raise ValueError('Durable Telchi rollout is DEV only')
        import asyncio
        from modules.messaging.durable import DurableWorker
        from modules.messaging.webhooks.evolution_whatsapp import build_service
        app.state.durable_messaging = True

        async def start_durable(application):
            srv = application.state.srv05_settings
            if not srv.evolution_enabled:
                raise ValueError('Durable WhatsApp requires Srv05 Evolution ON')
            service = await build_service(srv.messaging, srv.evolution,
                handlers=application.state.messaging_handlers,
                transport_runtime=application.state.transport_v1, durable=True)
            application.state.durable_worker = DurableWorker(service)
            # The task is a supervisor only. All queued work/results live in PG.
            application.state.durable_worker_task = asyncio.create_task(
                application.state.durable_worker.run(), name='telchi-durable-inbox')

        async def stop_durable(application):
            task = getattr(application.state, 'durable_worker_task', None)
            if task is not None:
                application.state.durable_worker.stopped.set()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        app.on_startup.append(start_durable)
        app.on_shutdown.insert(0, stop_durable)
    return app

"""Owner-selected Srv05 V1 DEV composition, initially closed for the send gate.

Uses the existing Telchi composition/authorization. No webhook setup, scheduler,
credential generation, implicit migration or business permission defaults.
"""
import os


def create_app(activity=None):
    if os.getenv('TEAM360_ENV') not in {'dev', 'development'}:
        raise ValueError('DEV transport composition required')
    from modules.messaging.transport_runtime import private_document
    document = private_document(os.environ['TEAM360_TRANSPORT_V1_CONFIG'])
    if (document['admission_open'] is not False
            and os.getenv('TEAM360_TELCHI_V1_SEND_AUTHORIZED') != '1'):
        raise ValueError('Explicit WhatsApp test activation is still required')
    from .whatsapp_dev import (read_approval, unchanged_approval, gate_evidence,
                               approval_digest, configuration, PilotBoundary)
    from .handler import BusinessPolicy
    from .composition import create_telchi_app
    path = os.environ['TEAM360_TELCHI_WHATSAPP_APPROVAL']
    approval = read_approval(path)
    if (document['scope']['workspace_id'] != approval['workspace_id']
            or document['scope']['tenant_id'] != approval['tenant_id']):
        raise ValueError('Transport and approved business scope differ')

    def access_check():
        unchanged_approval(path, approval)
        gate_evidence(approval)

    if document['admission_open']:
        access_check()
    app = create_telchi_app(policy=BusinessPolicy(approval['tenant_id'], approval['workspace_id'], None,
        approval['module_enabled'], approval['whole_workspace_scope_verified'],
        pilot_access_check=access_check, pilot_approval_sha256=approval_digest(approval),
        pilot_user_id=approval['user_id']))
    # Existing Telchi DEV session precedent: do not start unrelated Flow delivery.
    app.on_startup = [h for h in app.on_startup if getattr(h, '__name__', '') != '_start_flow_scheduler']
    app.on_shutdown = [h for h in app.on_shutdown if getattr(h, '__name__', '') != '_stop_flow_scheduler']
    async def attest_runtime(application):
        from pathlib import Path
        from modules.db.pool import get_pool
        from modules.db.transaction import transaction
        from .whatsapp_dev import save_private, source_digest, configuration_digest
        async with transaction(get_pool()) as conn:
            row = await (await conn.execute('SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls '
                'FROM pg_roles WHERE rolname=current_user')).fetchone()
        if (not os.getenv('TEAM360_TRANSPORT_V1_RUNTIME_ROLE')
                or row['rolname'] != os.environ['TEAM360_TRANSPORT_V1_RUNTIME_ROLE']
                or any(row[k] for k in row if k != 'rolname')):
            raise ValueError('Dedicated nonprivileged V1 runtime login required')
        transport = application.state.transport_v1
        worker = getattr(application.state, 'durable_worker_task', None)
        if os.getenv('TEAM360_TELCHI_DURABLE') == '1' and (worker is None or worker.done()):
            raise ValueError('Durable V1 worker not running')
        save_private(Path(os.environ['TEAM360_TRANSPORT_V1_CONFIG']).parent /
            ('srv05-ready-' + str(os.getpid()) + '.json'), dict(pid=os.getpid(),
                database_role=row['rolname'], provider=type(transport.provider).__name__,
                admission_open=transport.admission_open, callback_started=transport.server.started,
                durable_worker_running=worker is not None and not worker.done(),
                telchi_handler_registered='telchi' in application.state.messaging_handlers,
                source_sha256=source_digest(), configuration_sha256=configuration_digest()))

    app.on_startup.append(attest_runtime)
    srv, settings = configuration()
    def healthy():
        transport = app.state.transport_v1
        worker = getattr(app.state, 'durable_worker_task', None)
        return (transport.admission_open and transport.task is not None and not transport.task.done()
                and transport.server.started and worker is not None and not worker.done())

    return PilotBoundary(app, settings, srv.evolution, srv.recipient, access_check,
                         activity=activity, health_check=healthy)

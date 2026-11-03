"""Entrypoint parity in fresh interpreters, without live mail/LLM/DB I/O."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

BACKEND = Path(__file__).resolve().parents[1]


def _check(source: str, *, environment: dict[str, str] | None = None) -> None:
    env = dict(os.environ)
    env.update(AUTOMATION_DIAGNOSIS_REPOSITORY="memory", TEAM360_AI_PROVIDER="mock",
               TEAM360_SRV05_EVOLUTION_ENABLED="0")
    env.update(environment or {})
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_import_composes_separate_app_without_connections_or_workers():
    _check('''
        import asyncio
        import socket
        import subprocess
        import threading
        from unittest.mock import patch

        def forbidden(*args, **kwargs):
            raise AssertionError("Import attempted external I/O or background work")

        with patch.object(socket.socket, "connect", forbidden), \\
             patch.object(subprocess, "Popen", forbidden), \\
             patch.object(asyncio, "create_task", forbidden):
            import ls_iMotorSoft_Srv01 as old
            # Each Litestar app owns its framework logging listener; no service
            # worker, pool or Flow task is created by either import.
            import ls_iMotorSoft_Srv05 as new
        assert new.app is not old.app
        assert new.create_app is not old.create_app
        from modules.flow.scheduler import get_scheduler
        assert get_scheduler() is None
        from modules.db.pool import get_pool
        from modules.db.errors import DatabasePoolNotInitializedError
        try:
            get_pool()
        except DatabasePoolNotInitializedError:
            pass
        else:
            raise AssertionError("Memory profile unexpectedly configured a pool")
    ''')


def test_fresh_factories_preserve_routes_handlers_cors_and_lifecycle():
    _check('''
        import ls_iMotorSoft_Srv01 as old
        import ls_iMotorSoft_Srv05 as new
        a, b = old.create_app(), new.create_app()
        def routes(app):
            return [(r.path, sorted(getattr(r, "route_handler_map", {})))
                    for r in app.routes]
        assert routes(a) == routes(b)
        assert a.on_startup == b.on_startup
        assert a.on_shutdown == b.on_shutdown
        assert a.cors_config == b.cors_config
        assert a.debug == b.debug
        paths = {r.path for r in b.routes}
        assert {"/health", "/api/health", "/api/diagnosis/turn",
                "/api/diagnosis/embed/auth", "/api/team360-flow/configuration"} <= paths
        assert "/webhooks/messaging/evolution/whatsapp" not in paths
    ''')


def test_asgi_startup_requests_shutdown_and_scheduler_cleanup():
    _check('''
        from unittest.mock import AsyncMock, patch
        from litestar.testing import TestClient
        import ls_iMotorSoft_Srv01 as old
        import ls_iMotorSoft_Srv05 as new
        from modules.flow import scheduler
        from modules.db.errors import DatabasePoolNotInitializedError

        # Preserve the real Flow task lifecycle, but prevent reading live settings
        # (the real DEV database may have mail automation enabled).
        with patch.object(scheduler.FlowScheduler, "_read_settings",
                          AsyncMock(return_value={"automation_enabled": False,
                                                  "scheduler_interval_seconds": 1})):
            snapshots = []
            for factory in (old.create_app, new.create_app):
                with TestClient(factory()) as client:
                    assert scheduler.get_scheduler() is not None
                    responses = []
                    for path in ("/health", "/api/health", "/not-a-route"):
                        response = client.get(path)
                        responses.append((response.status_code, response.json()))
                    for path in ("/api/diagnosis/lead", "/api/diagnosis/submit-checklist"):
                        # Missing required fields must retain identical validation.
                        response = client.post(path, json={})
                        responses.append((response.status_code, response.json()))
                    response = client.post("/api/diagnosis/turn", json={
                        "message": "test", "organization_code": "forbidden-tenant"})
                    assert response.status_code == 403
                    responses.append((response.status_code, response.json()))
                    snapshots.append(responses)
                assert scheduler.get_scheduler() is None
            assert snapshots[0] == snapshots[1]

        # PostgreSQL hook wiring/order without connecting or enabling Gmail.
        events = []
        async def opened(pool): events.append("open")
        async def started(): events.append("start")
        async def stopped(): events.append("stop")
        async def closed(pool): events.append("close")
        import os
        with patch.dict(os.environ, {"AUTOMATION_DIAGNOSIS_REPOSITORY": "postgres"}), \\
             patch.object(old, "get_pool", return_value=object()), \\
             patch.object(old, "open_pool", opened), \\
             patch.object(old, "start_scheduler", started), \\
             patch.object(old, "stop_scheduler", stopped), \\
             patch.object(old, "close_pool", closed):
            with TestClient(new.create_app()) as client:
                assert client.get("/health").status_code == 200
            assert events == ["open", "start", "stop", "close"]

        # Existing failure isolation remains unchanged.
        with patch.dict(os.environ, {"AUTOMATION_DIAGNOSIS_REPOSITORY": "postgres"}), \\
             patch.object(old, "get_pool", side_effect=DatabasePoolNotInitializedError()), \\
             patch.object(old, "start_scheduler", AsyncMock(side_effect=RuntimeError())), \\
             patch.object(old, "stop_scheduler", AsyncMock(side_effect=RuntimeError())):
            with TestClient(new.create_app()) as client:
                assert client.get("/health").status_code == 200
    ''')


def test_authoritative_production_configuration_keeps_lazy_shared_providers():
    import secrets

    _check('''
        import socket
        from unittest.mock import patch
        def forbidden(*args, **kwargs):
            raise AssertionError("Import/provider selection attempted network I/O")
        with patch.object(socket.socket, "connect", forbidden):
            import ls_iMotorSoft_Srv05 as new
            import ls_iMotorSoft_Srv01 as old
            from modules.db.pool import get_pool
            from modules.sales_diagnosis_runtime.state_repository import SyncPostgresConversationStateRepository
            from modules.sales_diagnosis_runtime.milvus_provider import MilvusRetrievalProvider
            from routes import diagnosis
            from routes.diagnosis_schemas import PublicTurnRequest
            assert new.app is not old.app
            assert new.create_app is not old.create_app
            assert get_pool().closed
            assert isinstance(diagnosis._public_turn_state, SyncPostgresConversationStateRepository)
            retrieval = diagnosis._build_public_retrieval()
            assert isinstance(retrieval, MilvusRetrievalProvider)
            assert retrieval._client is None
            assert retrieval._config.collection_name == "team360_sales_diagnosis_knowledge_v1"
            assert retrieval._config.embedding_version == "team360-openai-small-1536-v1"
            provider = diagnosis._PublicTurnLLMProvider()
            assert provider.model_name == "openai_gpt-5.4-nano"
            assert provider._base_url == "http://127.0.0.1:4000"
            ctx = diagnosis._resolve_public_turn_context(PublicTurnRequest(message="test"))
            assert ctx["organization_code"] == "team360_live"
            assert ctx["workspace_code"] == "team360_public_site"
            assert ctx["package_code"] == "pkg_sales_diagnosis"
            assert ctx["knowledge_scope_code"] == "ks_team360_sales_diagnosis"
    ''', environment={
        "AUTOMATION_DIAGNOSIS_REPOSITORY": "postgres",
        "TEAM360_EMBEDDING_VERSION": "team360-openai-small-1536-v1",
        "TEAM360_AI_PROVIDER": "litellm",
        "TEAM360_LITELLM_BASE_URL": "http://127.0.0.1:4000",
        "TEAM360_LITELLM_MODEL_ALIAS": "openai_gpt-5.4-nano",
        "TEAM360_LITELLM_API_MODE": "chat",
        "TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER": "milvus",
        "TEAM360_MILVUS_HOST": "127.0.0.1",
        "TEAM360_MILVUS_PORT": "19530",
        "TEAM360_MILVUS_COLLECTION": "team360_sales_diagnosis_knowledge_v1",
        "TEAM360_DIAGNOSIS_STATE_PROVIDER": "postgres",
        "TEAM360_PUBLIC_ORGANIZATION_CODE": "team360_live",
        "TEAM360_PUBLIC_WORKSPACE_CODE": "team360_public_site",
        "TEAM360_PUBLIC_PACKAGE_CODE": "pkg_sales_diagnosis",
        "TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE": "ks_team360_sales_diagnosis",
        # Synthetic, ephemeral credentials: no live service requests in this test.
        "TEAM360_DB_URL": "postgresql://localhost/team360",
        "TEAM360_LITELLM_API_KEY": secrets.token_hex(16),
        "TEAM360_MILVUS_URI": "",
    })


def test_real_uvicorn_asgi_targets_have_identical_http_surfaces():
    _check('''
        import json
        import os
        import signal
        import socket
        import subprocess
        import sys
        import tempfile
        import time
        from urllib.request import urlopen

        snapshots = []
        for target in ("ls_iMotorSoft_Srv01:app", "ls_iMotorSoft_Srv05:app"):
            # The listening socket is owned by this test, never by another service.
            with socket.socket() as listener, tempfile.TemporaryFile() as log:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                port = listener.getsockname()[1]
                process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", target,
                     "--host", "127.0.0.1", "--port", str(port),
                     "--fd", str(listener.fileno()), "--log-level", "info"],
                    pass_fds=(listener.fileno(),), stdout=log, stderr=log,
                    cwd=os.path.dirname(os.getcwd()), env=dict(os.environ),
                )
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        assert process.poll() is None, "Uvicorn exited before readiness"
                        try:
                            with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                                health = json.load(r)
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise AssertionError("Uvicorn readiness timeout")
                            time.sleep(0.1)
                    with urlopen(f"http://127.0.0.1:{port}/schema/openapi.json", timeout=2) as r:
                        schema = json.load(r)
                    snapshots.append((health, schema))
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                # Uvicorn re-raises SIGTERM after its graceful shutdown.
                assert process.returncode in (0, -signal.SIGTERM), process.returncode
                log.seek(0)
                assert b"Application shutdown complete" in log.read()
        assert snapshots[0] == snapshots[1]
    ''')

"""TEST ONLY Srv05 listener: real lifespan, disabled scheduler projection.

Invoked exclusively by backend-dev.sh with TEAM360_DEV_PROFILE=srv05-e2e.
Loopback/single worker only. Pool is read-only. Only diagnosis turn/embed auth
POSTs are admitted, with fresh full_gate UUID sessions; no business mutations.
Normal entrypoints never import this harness. Not production automation proof.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import sys
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def require_profile():
    if os.environ.get("TEAM360_DEV_PROFILE") != "srv05-e2e" or os.environ.get("TEAM360_ENV") not in {"dev", "development"}:
        raise RuntimeError("Requires explicit srv05-e2e DEV profile")
    if os.environ.get("TEAM360_BACKEND_HOST", "127.0.0.1") != "127.0.0.1":
        raise RuntimeError("Harness only binds IPv4 loopback")
    if not os.environ.get("TEAM360_E2E_EVIDENCE"):
        raise RuntimeError("Evidence output required")
    if Path(os.environ["TEAM360_E2E_EVIDENCE"]).exists():
        raise RuntimeError("Refusing to overwrite prior evidence")


class ScopedState:
    def __init__(self, repository):
        self.repository = repository
        self.sessions = set()
        self.persisted_turns = {}

    def load(self, session_id):
        if not re.fullmatch(r"full_gate_[0-9a-f]{32}", session_id):
            raise ValueError("Harness requires a synthetic full_gate UUID session")
        state = self.repository.load(session_id)
        if session_id not in self.sessions:
            if state is not None:
                raise ValueError("Harness refuses preexisting sessions")
            self.sessions.add(session_id)
        return state

    def save(self, state):
        if state.session_id not in self.sessions:
            raise ValueError("Unowned synthetic session")
        result = self.repository.save(state)
        loaded = self.repository.load(state.session_id)
        if loaded is None or loaded.turn_count != state.turn_count:
            raise AssertionError("Synthetic state failed real PostgreSQL reload")
        self.persisted_turns[state.session_id] = loaded.turn_count
        return result


class MutationBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            allowed = scope["method"] == "POST" and scope["path"] in {"/api/diagnosis/turn", "/api/diagnosis/embed/auth"}
            if allowed:
                chunks = []
                while True:
                    event = await receive()
                    if event["type"] != "http.request":
                        return
                    chunks.append(event.get("body", b""))
                    if not event.get("more_body"):
                        break
                body = b"".join(chunks)
                try:
                    session = json.loads(body).get("session_id", "")
                    allowed = bool(re.fullmatch(r"full_gate_[0-9a-f]{32}", session))
                except (ValueError, TypeError):
                    allowed = False
                async def replay():
                    return {"type": "http.request", "body": body, "more_body": False}
                receive = replay
            if not allowed:
                await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"Test harness forbids this mutation"}'})
                return
        await self.app(scope, receive, send)


async def serve():
    require_profile()
    from validate_team360_full_stack import PUBLIC_ENV, safe_scheduler_fixture, local_connections_only
    for key, value in PUBLIC_ENV.items():
        os.environ.setdefault(key, value)
    os.environ["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=5000"
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from modules.db.settings import get_database_settings
    settings = get_database_settings()
    identity = conninfo_to_dict(settings.dsn)
    if identity.get("dbname") != "team360" or identity.get("host", "") not in {"", "localhost", "127.0.0.1", "::1"} or identity.get("port", "5432") != "5432":
        raise RuntimeError("Only existing local Team360 DB permitted")
    from urllib.parse import urlparse
    if urlparse(os.environ["TEAM360_LITELLM_BASE_URL"]).hostname not in {"localhost", "127.0.0.1"} or os.environ.get("TEAM360_MILVUS_URI") or os.environ["TEAM360_MILVUS_HOST"] not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("Only local dependencies permitted")
    writable = make_conninfo(settings.dsn, options="-c default_transaction_read_only=off -c statement_timeout=5000")
    from modules.sales_diagnosis_runtime.state_repository import SyncPostgresConversationStateRepository
    state = ScopedState(SyncPostgresConversationStateRepository(writable))
    from modules.db.pool import get_pool
    from modules.flow.scheduler import get_scheduler
    from team360_full_gate_repository import cleanup_test_sessions
    import uvicorn
    import ls_iMotorSoft_Srv05 as srv
    from routes import diagnosis
    class HarnessServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            # Uvicorn re-raises SIGTERM after serve(), which would terminate the
            # process before our async session cleanup. Handle graceful exit
            # here and restore handlers, without re-raising the consumed signal.
            previous = {sig: signal.signal(sig, self.handle_exit) for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                yield
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)

    evidence = {"pid": os.getpid(), "port": int(os.environ.get("TEAM360_BACKEND_PORT", "7050")),
                "profile": "srv05-e2e", "scheduler": {"forbidden_cycle_attempts": 0}, "egress": {}, "lifecycle": {}}
    app = srv.app
    async def observe_start():
        pool = get_pool()
        await pool.wait(timeout=5)
        for _ in range(50):
            if evidence["scheduler"].get("reads", 0):
                break
            await asyncio.sleep(0.1)
        scheduler = get_scheduler()
        assert scheduler and scheduler.is_running and evidence["scheduler"].get("reads", 0)
        task = scheduler._task
        from modules.flow.scheduler import start_scheduler
        await start_scheduler()
        assert scheduler._task is task
        assert len([t for t in asyncio.all_tasks() if t.get_name() == "flow-scheduler"]) == 1
        async with pool.connection() as conn:
            cursor = await conn.execute("show transaction_read_only")
            row = await cursor.fetchone()
            assert next(iter(row.values())) == "on"
        evidence["lifecycle"].update(startup="PASS", pool_read_only=True, scheduler_tasks=1, duplicate_init=False)
    async def observe_stop():
        evidence["lifecycle"].update(shutdown="PASS", pool_closed=get_pool().closed, scheduler_absent=get_scheduler() is None,
                                      remaining_scheduler_tasks=len([t for t in asyncio.all_tasks() if t.get_name() == "flow-scheduler"]))
    app.on_startup.append(observe_start)
    app.on_shutdown.append(observe_stop)
    try:
        with safe_scheduler_fixture(evidence["scheduler"]), local_connections_only(evidence["egress"]), patch.object(diagnosis, "_public_turn_state", state):
            server = HarnessServer(uvicorn.Config(MutationBoundary(app), host="127.0.0.1", port=evidence["port"], workers=1, access_log=False))
            await server.serve()
    finally:
        evidence["sessions"] = sorted(state.sessions)
        evidence["persisted_turns"] = state.persisted_turns
        evidence["cleanup"] = await cleanup_test_sessions(writable, sorted(state.sessions)) if state.sessions else {"status": "PASS", "remaining": 0}
        evidence["status"] = "PASS" if evidence["lifecycle"].get("shutdown") == "PASS" and evidence["lifecycle"].get("pool_closed") and evidence["lifecycle"].get("scheduler_absent") and evidence["cleanup"]["status"] == "PASS" and not evidence["scheduler"]["forbidden_cycle_attempts"] else "FAIL"
        Path(os.environ["TEAM360_E2E_EVIDENCE"]).write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    result = asyncio.run(serve())
    raise SystemExit(0 if result["status"] == "PASS" else 1)

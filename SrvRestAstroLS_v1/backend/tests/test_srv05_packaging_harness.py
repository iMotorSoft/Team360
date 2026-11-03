"""Cheap guards; the installed-wheel regression is scripts/validate_srv05_wheel.py."""
import importlib.util
import json
from pathlib import Path
import sys
import tomllib
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def harness():
    spec = importlib.util.spec_from_file_location("srv05_e2e_test", BACKEND / "scripts/srv05_e2e_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_modules_are_force_included():
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    mappings = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for name in ("ls_iMotorSoft_Srv05.py", "ls_iMotorSoft_Srv01.py", "globalVar.py"):
        assert mappings[name] == name and (BACKEND / name).is_file()


@pytest.mark.parametrize("profile,env,host", [("normal", "development", "127.0.0.1"), ("srv05-e2e", "production", "127.0.0.1"), ("srv05-e2e", "development", "0.0.0.0")])
def test_profile_fails_closed(monkeypatch, profile, env, host):
    monkeypatch.setenv("TEAM360_DEV_PROFILE", profile)
    monkeypatch.setenv("TEAM360_ENV", env)
    monkeypatch.setenv("TEAM360_BACKEND_HOST", host)
    with pytest.raises(RuntimeError):
        harness().require_profile()


def test_owned_state_refuses_existing_and_unscoped_sessions():
    module = harness()
    repo = SimpleNamespace(load=lambda sid: "existing", save=lambda state: None)
    state = module.ScopedState(repo)
    with pytest.raises(ValueError, match="synthetic"):
        state.load("conv_real")
    with pytest.raises(ValueError, match="preexisting"):
        state.load("full_gate_" + "a" * 32)
    with pytest.raises(ValueError, match="Unowned"):
        state.save(SimpleNamespace(session_id="full_gate_" + "b" * 32))
    repo.load = lambda sid: None
    sid = "full_gate_" + "c" * 32
    assert state.load(sid) is None
    saved = SimpleNamespace(session_id=sid, turn_count=1)
    repo.save = lambda value: setattr(repo, "load", lambda key: value)
    state.save(saved)
    assert state.sessions == {sid}
    assert state.persisted_turns == {sid: 1}


@pytest.mark.parametrize("method,path,body,status", [
    ("POST", "/api/team360-flow/configuration", {}, 403),
    ("POST", "/api/console/bootstrap", {}, 403),
    ("POST", "/api/diagnosis/turn", {"session_id": "conv_real"}, 403),
    ("POST", "/api/diagnosis/turn", {"session_id": "full_gate_" + "a" * 32}, 200),
    ("GET", "/health", {}, 200),
])
def test_mutation_boundary(method, path, body, status):
    import asyncio
    messages = []
    async def app(scope, receive, send):
        if scope["method"] == "POST":
            assert json.loads((await receive())["body"]) == body
        await send({"type": "http.response.start", "status": 200})
    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}
    async def send(event):
        messages.append(event)
    asyncio.run(harness().MutationBoundary(app)({"type": "http", "method": method, "path": path}, receive, send))
    assert messages[0]["status"] == status

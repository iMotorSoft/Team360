"""Phase 3 contracts: declarative resolution, never live execution."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from modules.srv05_architecture import REGISTRY, ModuleDefinition, ServiceDependency
from modules.srv05_runtime import resolve_runtime_profile, validate_runtime_profile


@pytest.fixture
def public_config():
    # Non-secret synthetic snapshot; not runtime defaults or a live env loader.
    return {
        "TEAM360_DB_URL": "postgresql://localhost/team360",
        "AUTOMATION_DIAGNOSIS_REPOSITORY": "postgres",
        "TEAM360_DIAGNOSIS_STATE_PROVIDER": "postgres",
        "TEAM360_AI_PROVIDER": "litellm",
        "TEAM360_LITELLM_BASE_URL": "http://localhost:4000",
        "TEAM360_LITELLM_MODEL_ALIAS": "test_alias",
        "TEAM360_LITELLM_API_MODE": "chat",
        "TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER": "milvus",
        "TEAM360_MILVUS_HOST": "localhost",
        "TEAM360_MILVUS_PORT": "19530",
        "TEAM360_MILVUS_COLLECTION": "test_collection",
        "TEAM360_EMBEDDING_VERSION": "test_version",
    }


def test_flow_classifications_and_local_scheduler():
    profile = resolve_runtime_profile("flow")
    assert profile.required_services == ("postgres",)
    assert profile.optional_services == ("gupshup", "litellm")
    assert profile.conditional_services == ("auth_permissions", "gmail")
    assert profile.active_conditional_services == ()
    assert len(profile.local_components) == 1
    component = profile.local_components[0]
    assert component.module == "flow"
    assert component.dependency.service == "scheduler"
    assert component.dependency.kind == "optional"
    assert component.scope == "module_local"
    assert component.active is None
    assert "scheduler" not in profile.services_to_validate


@pytest.mark.parametrize("service", ["milvus", "evolution"])
def test_flow_must_not_require_or_include_unrelated_service(service):
    profile = resolve_runtime_profile("flow")
    assert REGISTRY.get_service(service)  # available is NOT necessary
    assert service in profile.unrelated_services
    assert service not in profile.required_services
    assert service not in {d.dependency.service for d in profile.dependencies}


def test_diagnosis_public_baseline_surfaces_and_distributor_binding():
    profile = resolve_runtime_profile("diagnosis")
    assert profile.required_services == ("litellm", "milvus", "postgres")
    assert profile.optional_services == profile.conditional_services == ()
    assert profile.local_components == ()
    assert profile.surfaces == (("diagnosis", "embed"), ("diagnosis", "home"), ("diagnosis", "web"))
    assert tuple(b.code for b in profile.bindings) == ("mamamia360_embed",)
    assert profile.bindings[0].binding_type == "distributor_embed"
    assert profile.bindings[0].storage_service == "postgres"
    assert "mamamia360_embed" not in profile.required_services
    serialized = json.dumps(profile.to_dict()).lower()
    assert "netzaj" not in serialized and "galil" not in serialized


def test_full_union_dedup_and_reason_for_litellm_requirement():
    profile = resolve_runtime_profile("full")
    assert profile.modules == ("diagnosis", "flow")
    assert profile.required_services == ("litellm", "milvus", "postgres")
    assert profile.required_services.count("postgres") == 1
    assert profile.required_services.count("litellm") == 1
    assert profile.optional_services == ("gupshup",)
    assert profile.conditional_services == ("auth_permissions", "gmail")
    assert profile.local_components == resolve_runtime_profile("flow").local_components
    assert profile.bindings == resolve_runtime_profile("diagnosis").bindings
    reasons = [(d.module, d.dependency.kind) for d in profile.dependencies if d.dependency.service == "litellm"]
    assert reasons == [("diagnosis", "required"), ("flow", "optional")]
    assert "evolution" in profile.unrelated_services
    assert "evolution" not in {d.dependency.service for d in profile.dependencies}


@pytest.mark.parametrize("code", ["flow", "diagnosis", "full"])
def test_deterministic_immutable_and_serializable(code):
    a = resolve_runtime_profile(code)
    assert a == resolve_runtime_profile(code)
    assert hash(a) == hash(resolve_runtime_profile(code))
    with pytest.raises(FrozenInstanceError):
        a.code = "changed"
    snapshot = a.to_dict()
    assert json.loads(json.dumps(snapshot))["code"] == code
    snapshot["modules"] = []
    assert a.modules
    reversed_registry = replace(REGISTRY, modules=tuple(reversed(REGISTRY.modules)),
                                services=tuple(reversed(REGISTRY.services)),
                                bindings=tuple(reversed(REGISTRY.bindings)))
    assert a == resolve_runtime_profile(code, registry=reversed_registry)


def test_explicit_conditional_activation_preserves_classification():
    capabilities = {"gmail": True, "auth_permissions": False}
    profile = resolve_runtime_profile("flow", capabilities=capabilities)
    capabilities["gmail"] = False
    assert profile.active_conditional_services == ("gmail",)
    assert profile.required_services == ("postgres",)
    assert profile.conditional_services == ("auth_permissions", "gmail")
    assert profile.services_to_validate == ("gmail", "postgres")
    assert profile == resolve_runtime_profile("flow", capabilities={"auth_permissions": False, "gmail": True})


@pytest.mark.parametrize("code,capabilities", [
    ("flow", {"milvus": True}), ("flow", {"evolution": True}),
    ("flow", {"litellm": True}), ("diagnosis", {"gmail": True}),
    ("flow", {"gmail": 1}), ("flow", {"gmail": "true"}),
])
def test_capabilities_fail_closed(code, capabilities):
    with pytest.raises(ValueError):
        resolve_runtime_profile(code, capabilities=capabilities)


def test_unknown_profile_fails():
    with pytest.raises(KeyError):
        resolve_runtime_profile("unknown")


@pytest.mark.parametrize("code", ["flow", "diagnosis", "full"])
def test_valid_configuration(code, public_config):
    before = public_config.copy()
    result = validate_runtime_profile(resolve_runtime_profile(code), public_config)
    assert result.valid
    assert result.checked_services == resolve_runtime_profile(code).required_services
    assert not result.unchecked_services
    assert public_config == before


@pytest.mark.parametrize("name", [
    "TEAM360_DB_URL", "TEAM360_LITELLM_BASE_URL", "TEAM360_LITELLM_MODEL_ALIAS",
    "TEAM360_MILVUS_HOST", "TEAM360_MILVUS_PORT", "TEAM360_MILVUS_COLLECTION",
    "TEAM360_EMBEDDING_VERSION", "TEAM360_AI_PROVIDER", "TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER",
])
def test_missing_required_configuration(name, public_config):
    del public_config[name]
    result = validate_runtime_profile(resolve_runtime_profile("diagnosis"), public_config)
    assert not result.valid
    assert any(i.code == "missing_configuration" for i in result.issues)


@pytest.mark.parametrize("name,value", [
    ("AUTOMATION_DIAGNOSIS_REPOSITORY", "memory"),
    ("TEAM360_DIAGNOSIS_STATE_PROVIDER", "memory"),
    ("TEAM360_AI_PROVIDER", "mock"),
    ("TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER", "null"),
    ("TEAM360_LITELLM_API_MODE", "invalid"),
])
def test_incompatible_provider_and_contradictory_marker(name, value, public_config):
    public_config[name] = value
    result = validate_runtime_profile(resolve_runtime_profile("diagnosis"), public_config)
    assert not result.valid
    assert any(i.code == "incompatible_provider" and name in i.variables for i in result.issues)


@pytest.mark.parametrize("port", ["0", "65536", "bad", "-1", "１２"])
def test_invalid_milvus_port(port, public_config):
    public_config["TEAM360_MILVUS_PORT"] = port
    result = validate_runtime_profile(resolve_runtime_profile("diagnosis"), public_config)
    assert any(i.code == "invalid_port" for i in result.issues)


def test_uri_and_db_alternatives_and_selector_precedence(public_config):
    public_config["TEAM360_DB_URL_PSQL"] = public_config.pop("TEAM360_DB_URL")
    del public_config["AUTOMATION_DIAGNOSIS_REPOSITORY"]
    del public_config["TEAM360_MILVUS_HOST"]
    del public_config["TEAM360_MILVUS_PORT"]
    public_config["TEAM360_MILVUS_URI"] = "http://localhost:19530"
    assert validate_runtime_profile(resolve_runtime_profile("diagnosis"), public_config).valid
    public_config["TEAM360_DB_URL"] = "not-a-dsn"
    assert not validate_runtime_profile(resolve_runtime_profile("diagnosis"), public_config).valid


def test_flow_ignores_optional_inactive_and_unrelated_configuration():
    config = {"TEAM360_DB_URL": "postgresql+psycopg://localhost/team360",
              "TEAM360_AI_PROVIDER": "mock", "TEAM360_MILVUS_PORT": "invalid"}
    assert validate_runtime_profile(resolve_runtime_profile("flow"), config).valid
    assert not validate_runtime_profile(resolve_runtime_profile("flow", capabilities={"gmail": True}), config).valid
    config.update(TEAM360_GMAIL_SERVICE_ACCOUNT_FILE="/private/reference-only.json",
                  TEAM360_GMAIL_DELEGATED_USER="synthetic@example.invalid")
    assert validate_runtime_profile(resolve_runtime_profile("flow", capabilities={"gmail": True}), config).valid
    auth = resolve_runtime_profile("flow", capabilities={"auth_permissions": True})
    assert not validate_runtime_profile(auth, config).valid
    config["TEAM360_FLOW_ACCESS_MODE"] = "authenticated"
    assert validate_runtime_profile(auth, config).valid  # static policy only, not auth proof


def test_public_markers_do_not_resolve_binding_context(public_config):
    profile = resolve_runtime_profile("diagnosis")
    public_config.update(TEAM360_PUBLIC_ORGANIZATION_CODE="not-authority",
                         TEAM360_PUBLIC_WORKSPACE_CODE="not-authority")
    assert validate_runtime_profile(profile, public_config).valid
    assert profile.bindings == REGISTRY.module_bindings("diagnosis")


def test_new_required_service_has_no_silent_validation_pass():
    module = ModuleDefinition("future", "test baseline", "core", (
        ServiceDependency("evolution", "required", "test", "synthetic", ("test",)),), ())
    registry = replace(REGISTRY, modules=REGISTRY.modules + (module,))
    profile = resolve_runtime_profile("full", registry=registry)
    result = validate_runtime_profile(profile, {})
    assert result.unchecked_services == ("evolution",)
    assert not result.valid


@pytest.mark.parametrize("name,value", [
    ("TEAM360_DB_URL", "sqlite:///local"),
    ("TEAM360_LITELLM_BASE_URL", "http://localhost:bad"),
    ("TEAM360_LITELLM_BASE_URL", "file:///private"),
    ("TEAM360_MILVUS_URI", "not-an-endpoint"),
])
def test_invalid_endpoints(name, value, public_config):
    public_config[name] = value
    result = validate_runtime_profile(resolve_runtime_profile("diagnosis"), public_config)
    assert any(i.code == "invalid_endpoint" and name in i.variables for i in result.issues)
    assert value not in repr(result)


def test_validator_never_requests_secrets_or_operational_markers(public_config):
    class Snapshot(dict):
        def get(self, key, default=None):
            assert "KEY" not in key and "TOKEN" not in key and "PUBLIC_" not in key
            return super().get(key, default)
    assert validate_runtime_profile(resolve_runtime_profile("full"), Snapshot(public_config)).valid


def test_fresh_import_resolution_validation_have_no_io_or_runtime_imports(public_config):
    source = '''
import builtins, os, socket, subprocess, threading, asyncio, sys
from unittest.mock import patch

def forbidden(*a, **kw):
    raise AssertionError("External I/O, env read, file access or background work")

with patch.object(socket.socket, "connect", forbidden), \\
     patch.object(subprocess, "Popen", forbidden), \\
     patch.object(threading.Thread, "start", forbidden), \\
     patch.object(asyncio, "create_task", forbidden), \\
     patch.object(builtins, "open", forbidden), \\
     patch.dict(os.environ, {}, clear=True):
    with patch.object(type(os.environ), "get", forbidden):
        from modules.srv05_runtime import resolve_runtime_profile, validate_runtime_profile
        for code in ("flow", "diagnosis", "full"):
            profile = resolve_runtime_profile(code)
            assert not validate_runtime_profile(profile, {}).valid
            profile.to_dict()
        config = CONFIG_SNAPSHOT
        assert validate_runtime_profile(resolve_runtime_profile("full"), config).valid
        config.update(TEAM360_GMAIL_SERVICE_ACCOUNT_FILE="/private/not-opened.json",
                      TEAM360_GMAIL_DELEGATED_USER="synthetic@example.invalid",
                      TEAM360_FLOW_ACCESS_MODE="authenticated")
        assert validate_runtime_profile(resolve_runtime_profile("flow", capabilities={
            "gmail": True, "auth_permissions": True}), config).valid
assert not any(name in sys.modules for name in (
    "globalVar", "ls_iMotorSoft_Srv01", "ls_iMotorSoft_Srv05", "modules.module_registry",
    "modules.db.pool", "modules.flow.scheduler", "pymilvus", "httpx", "psycopg",
    "modules.sales_diagnosis_runtime.milvus_provider", "routes.diagnosis"))
'''
    source = source.replace("CONFIG_SNAPSHOT", repr(public_config))
    result = subprocess.run([sys.executable, "-c", source],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr

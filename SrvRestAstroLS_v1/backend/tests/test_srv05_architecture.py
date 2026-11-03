"""Declarative architecture contracts; no real services or production writes."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import os
import subprocess
import sys

import pytest

from modules.srv05_architecture import (
    REGISTRY,
    get_module_bindings,
    get_module_definition,
    get_module_dependencies,
    get_service_consumers,
    get_service_definition,
)

BACKEND = Path(__file__).resolve().parents[1]


def test_flow_base_and_capability_classification():
    flow = get_module_definition("flow")
    assert flow.code == "flow"
    assert {d.service: d.kind for d in flow.dependencies} == {
        "postgres": "required", "scheduler": "optional",
        "gmail": "runtime_conditional", "litellm": "optional",
        "gupshup": "optional", "auth_permissions": "runtime_conditional",
    }
    assert tuple(d.service for d in get_module_dependencies("flow", "required")) == ("postgres",)
    assert tuple(d.service for d in get_module_dependencies("flow", "optional")) == (
        "scheduler", "litellm", "gupshup",
    )
    dependencies = {d.service: d for d in flow.dependencies}
    assert "mail_intake_enabled" in dependencies["gmail"].condition
    assert "authenticated" in dependencies["auth_permissions"].condition
    assert "unconditionally" in dependencies["scheduler"].condition
    assert "does not disable Flow" in dependencies["litellm"].condition
    scheduler = get_service_definition("scheduler")
    assert (scheduler.scope, scheduler.execution) == ("module_local", "in_process")


@pytest.mark.parametrize("module,service", [
    ("flow", "milvus"), ("flow", "evolution"), ("diagnosis", "evolution"),
    ("diagnosis", "gmail"), ("diagnosis", "scheduler"), ("diagnosis", "gupshup"),
    ("diagnosis", "auth_permissions"),
])
def test_critical_unrelated_services(module, service):
    assert REGISTRY.dependency_kind(module, service) == "unrelated"
    assert service not in {d.service for d in get_module_dependencies(module)}


def test_diagnosis_real_baseline_is_not_mock_or_import_requirements():
    diagnosis = get_module_definition("diagnosis")
    assert diagnosis.code == "diagnosis"
    assert {d.service: d.kind for d in diagnosis.dependencies} == {
        "postgres": "required", "milvus": "required", "litellm": "required",
    }
    assert "not memory/mock" in diagnosis.baseline
    assert diagnosis.surfaces == ("home", "web", "embed")
    assert get_module_dependencies("diagnosis", "optional") == ()
    assert get_module_dependencies("diagnosis", "runtime_conditional") == ()
    assert "NullRetrieval" in diagnosis.dependencies[1].condition
    assert "URI/host" in diagnosis.dependencies[1].condition


def test_distributor_binding_not_tenant_or_horizontal_service():
    (binding,) = get_module_bindings("diagnosis")
    assert binding.code == "mamamia360_embed"
    assert (binding.external_id, binding.binding_type, binding.surface) == (
        "mamamia360", "distributor_embed", "embed",
    )
    assert binding.storage_service == "postgres"
    assert dict(binding.context) == {
        "assistant_instance_code": "team360_sales_diagnosis",
        "organization_code": "team360_live", "workspace_code": "team360_public_site",
        "package_code": "pkg_sales_diagnosis", "knowledge_scope_code": "ks_team360_sales_diagnosis",
    }
    assert "DB-authoritative" in binding.description
    assert get_module_bindings("flow") == ()
    assert not {"mamamia360", "netzaj", "galil"} & {s.code for s in REGISTRY.services}
    assert {m.code for m in REGISTRY.modules} == {"flow", "diagnosis"}
    assert {b.code for b in REGISTRY.bindings} == {"mamamia360_embed"}


def test_services_unique_shared_and_consumer_queries_deterministic():
    assert len({s.code for s in REGISTRY.services}) == len(REGISTRY.services)
    assert {s.code for s in REGISTRY.services if s.scope == "horizontal"} == {
        "postgres", "milvus", "litellm", "gmail", "gupshup", "evolution", "auth_permissions",
    }
    for _ in range(3):
        assert get_service_consumers("postgres") == ("flow", "diagnosis")
        assert get_service_consumers("milvus") == ("diagnosis",)
        assert get_service_consumers("litellm") == ("flow", "diagnosis")
        assert get_service_consumers("evolution") == ()  # Messaging is outside this inventory.
        assert get_module_dependencies("flow") is not None
        assert get_module_dependencies("flow") == REGISTRY.get_module("flow").dependencies
    assert get_service_definition("evolution").scope == "horizontal"


@pytest.mark.parametrize("query,args", [
    (get_module_definition, ("missing",)), (get_service_definition, ("missing",)),
    (get_module_dependencies, ("missing",)), (get_service_consumers, ("missing",)),
    (get_module_bindings, ("missing",)), (REGISTRY.get_binding, ("missing",)),
    (REGISTRY.dependency_kind, ("flow", "missing")),
    (REGISTRY.dependency_kind, ("missing", "milvus")),
])
def test_unknown_codes_fail_instead_of_claiming_unrelated(query, args):
    with pytest.raises(KeyError):
        query(*args)


def test_inventory_is_immutable():
    with pytest.raises(FrozenInstanceError):
        REGISTRY.modules = ()
    with pytest.raises(FrozenInstanceError):
        get_module_definition("flow").code = "other"
    with pytest.raises(FrozenInstanceError):
        get_module_dependencies("flow")[0].kind = "optional"
    assert isinstance(REGISTRY.get_binding("mamamia360_embed").context, tuple)


@pytest.mark.parametrize("field", ["modules", "services", "bindings"])
def test_duplicate_component_codes_rejected(field):
    entries = getattr(REGISTRY, field)
    with pytest.raises(ValueError, match="Duplicate"):
        replace(REGISTRY, **{field: entries + (entries[0],)})


@pytest.mark.parametrize("mutation", ["unknown_service", "duplicate_dependency", "invalid_kind", "missing_evidence", "unknown_binding"])
def test_invalid_dependency_graph_rejected(mutation):
    flow = REGISTRY.get_module("flow")
    dependency = flow.dependencies[0]
    if mutation == "unknown_binding":
        flow = replace(flow, bindings=("missing",))
    elif mutation == "duplicate_dependency":
        flow = replace(flow, dependencies=flow.dependencies + (dependency,))
    else:
        changes = {
            "unknown_service": {"service": "missing"},
            "invalid_kind": {"kind": "unrelated"},
            "missing_evidence": {"evidence": ()},
        }[mutation]
        flow = replace(flow, dependencies=(replace(dependency, **changes),) + flow.dependencies[1:])
    with pytest.raises(ValueError):
        replace(REGISTRY, modules=(flow, REGISTRY.get_module("diagnosis")))


@pytest.mark.parametrize("changes", [
    {"module": "missing"}, {"module": "flow"}, {"surface": "missing"},
    {"storage_service": "missing"}, {"storage_service": "evolution"},
    {"context": (("key", "one"), ("key", "two"))},
])
def test_invalid_binding_relationship_rejected(changes):
    with pytest.raises(ValueError):
        replace(REGISTRY, bindings=(replace(REGISTRY.bindings[0], **changes),))


def test_invalid_filter_and_configuration_references_rejected():
    with pytest.raises(ValueError):
        get_module_dependencies("flow", "typo")
    with pytest.raises(ValueError):
        replace(REGISTRY, configuration=REGISTRY.configuration + (REGISTRY.configuration[0],))
    with pytest.raises(ValueError):
        replace(REGISTRY, configuration=(replace(REGISTRY.configuration[0], modules=("missing",)),))


def test_evidence_paths_resolve_and_capabilities_have_rationale():
    items = (*REGISTRY.services, *REGISTRY.modules, *REGISTRY.bindings,
             *REGISTRY.configuration, *(d for m in REGISTRY.modules for d in m.dependencies))
    for item in items:
        assert item.evidence
        for path in item.evidence:
            assert (BACKEND / path).is_file(), path
    for module in REGISTRY.modules:
        for dependency in module.dependencies:
            assert dependency.capability and dependency.condition


def test_configuration_maps_names_only_and_public_markers_are_not_resolvers():
    by_name = {name: association for association in REGISTRY.configuration for name in association.variables}
    assert by_name["TEAM360_AI_PROVIDER"].modules == ("diagnosis",)
    assert by_name["TEAM360_LITELLM_MODEL_ALIAS"].modules == ("flow", "diagnosis")
    assert by_name["TEAM360_DIAGNOSIS_STATE_PROVIDER"].services == ("postgres",)
    assert "prefers" in by_name["AUTOMATION_DIAGNOSIS_REPOSITORY"].effect
    assert "URI/host" in by_name["TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER"].effect
    public = by_name["TEAM360_PUBLIC_ORGANIZATION_CODE"]
    assert len(public.variables) == 4
    assert public.services == ()
    assert public.consumers == ("backend-dev.sh exports/logs",)
    assert "not these variables" in public.effect
    # Effective runtime sources remain independent of operational markers.
    for path in ("routes/diagnosis.py", "globalVar.py"):
        source = (BACKEND / path).read_text()
        assert all(name not in source for name in public.variables)
    assert all("SECRET" not in name and "TOKEN" not in name and "API_KEY" not in name for name in by_name)


def test_fresh_inventory_import_has_no_runtime_imports_io_or_workers():
    script = '''
import asyncio, os, socket, subprocess, sys, threading
from unittest.mock import patch
before = dict(os.environ)
def forbidden(*args, **kwargs):
    raise AssertionError("Inventory attempted runtime work")
with patch.object(socket.socket, "connect", forbidden), \\
     patch.object(subprocess, "Popen", forbidden), \\
     patch.object(threading.Thread, "start", forbidden), \\
     patch.object(asyncio, "create_task", forbidden), \\
     patch.object(os, "getenv", forbidden):
    from modules.srv05_architecture import REGISTRY
    assert REGISTRY.consumers("milvus") == ("diagnosis",)
assert dict(os.environ) == before
assert not any(n.startswith(("modules.flow", "modules.messaging", "modules.db",
    "modules.sales_diagnosis_runtime", "modules.automation_diagnosis", "routes.",
    "ls_iMotorSoft_Srv01", "ls_iMotorSoft_Srv05", "globalVar")) for n in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=BACKEND,
                            env=dict(os.environ), capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr

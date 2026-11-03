"""Declarative Srv05 inventory; NOT route composition or lifecycle policy.

Only stdlib imports. No environment reads, discovery, provider construction or
service start/stop. ``required`` describes the stated functional baseline, not
what an ASGI import needs. Consumer queries cover registered modules ONLY.
Evidence paths are relative to backend unless prefixed with ../astro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DependencyKind = Literal["required", "optional", "runtime_conditional"]
ServiceScope = Literal["horizontal", "module_local"]
Criticality = Literal["core", "capability"]


@dataclass(frozen=True, slots=True)
class ServiceDefinition:
    code: str
    scope: ServiceScope
    category: str
    criticality: Criticality
    execution: Literal["external", "in_process"]
    description: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ServiceDependency:
    service: str
    kind: DependencyKind
    capability: str
    condition: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    code: str
    baseline: str
    criticality: Criticality
    dependencies: tuple[ServiceDependency, ...]
    surfaces: tuple[str, ...]
    bindings: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BindingDefinition:
    code: str
    module: str
    surface: str
    binding_type: Literal["distributor_embed"]
    external_id: str
    storage_service: str
    context: tuple[tuple[str, str], ...]
    description: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConfigurationAssociation:
    """Names and observed effects only; never configuration values or secrets."""
    variables: tuple[str, ...]
    modules: tuple[str, ...]
    services: tuple[str, ...]
    consumers: tuple[str, ...]
    effect: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchitectureRegistry:
    modules: tuple[ModuleDefinition, ...]
    services: tuple[ServiceDefinition, ...]
    bindings: tuple[BindingDefinition, ...]
    configuration: tuple[ConfigurationAssociation, ...] = ()

    def __post_init__(self) -> None:
        def codes(items: tuple, label: str) -> set[str]:
            result = {item.code for item in items}
            if len(result) != len(items):
                raise ValueError(f"Duplicate {label} code")
            return result

        module_codes = codes(self.modules, "module")
        service_codes = codes(self.services, "service")
        binding_codes = codes(self.bindings, "binding")
        for service in self.services:
            if service.scope not in {"horizontal", "module_local"}:
                raise ValueError("Invalid service scope")
        for module in self.modules:
            if len({d.service for d in module.dependencies}) != len(module.dependencies):
                raise ValueError("Duplicate module dependency")
            for dependency in module.dependencies:
                if dependency.service not in service_codes:
                    raise ValueError("Unknown dependency service")
                if dependency.kind not in {"required", "optional", "runtime_conditional"}:
                    raise ValueError("Invalid dependency kind")
                if not dependency.condition or not dependency.evidence:
                    raise ValueError("Dependencies need rationale and evidence")
            if len(set(module.surfaces)) != len(module.surfaces):
                raise ValueError("Duplicate surface")
            if len(set(module.bindings)) != len(module.bindings):
                raise ValueError("Duplicate module binding")
            for binding_code in module.bindings:
                if binding_code not in binding_codes:
                    raise ValueError("Unknown module binding")
                if self.get_binding(binding_code).module != module.code:
                    raise ValueError("Binding ownership mismatch")
        for binding in self.bindings:
            if binding.module not in module_codes or binding.storage_service not in service_codes:
                raise ValueError("Unknown binding module/storage service")
            module = self.get_module(binding.module)
            if binding.code not in module.bindings or binding.surface not in module.surfaces:
                raise ValueError("Binding must belong to a declared module surface")
            if binding.storage_service not in {d.service for d in module.dependencies}:
                raise ValueError("Binding storage must be a module dependency")
            if len(dict(binding.context)) != len(binding.context):
                raise ValueError("Duplicate binding context key")
        variables: set[str] = set()
        for association in self.configuration:
            if variables.intersection(association.variables):
                raise ValueError("Duplicate configuration variable")
            variables.update(association.variables)
            if not set(association.modules) <= module_codes or not set(association.services) <= service_codes:
                raise ValueError("Unknown configuration module/service")

    def get_module(self, code: str) -> ModuleDefinition:
        for module in self.modules:
            if module.code == code:
                return module
        raise KeyError(code)

    def get_service(self, code: str) -> ServiceDefinition:
        for service in self.services:
            if service.code == code:
                return service
        raise KeyError(code)

    def get_binding(self, code: str) -> BindingDefinition:
        for binding in self.bindings:
            if binding.code == code:
                return binding
        raise KeyError(code)

    def dependencies(self, module: str, kind: DependencyKind | None = None) -> tuple[ServiceDependency, ...]:
        if kind is not None and kind not in {"required", "optional", "runtime_conditional"}:
            raise ValueError("Invalid dependency kind")
        return tuple(d for d in self.get_module(module).dependencies if kind is None or d.kind == kind)

    def consumers(self, service: str) -> tuple[str, ...]:
        """All kinds of dependency; not an exhaustive repository-wide inventory."""
        self.get_service(service)  # Unknown services are errors, not unrelated.
        return tuple(m.code for m in self.modules if any(d.service == service for d in m.dependencies))

    def module_bindings(self, module: str) -> tuple[BindingDefinition, ...]:
        return tuple(self.get_binding(code) for code in self.get_module(module).bindings)

    def dependency_kind(self, module: str, service: str) -> DependencyKind | Literal["unrelated"]:
        self.get_service(service)
        return next((d.kind for d in self.dependencies(module) if d.service == service), "unrelated")


REGISTRY = ArchitectureRegistry(
    services=(
        ServiceDefinition("postgres", "horizontal", "database", "core", "external",
                          "Operational truth; shared storage, not shared tenant identity.",
                          ("modules/flow/repository.py", "modules/sales_diagnosis_runtime/state_repository.py")),
        ServiceDefinition("milvus", "horizontal", "vector_index", "core", "external",
                          "Milvus 2.6 derived retrieval index; never permission authority.",
                          ("modules/sales_diagnosis_runtime/milvus_provider.py",)),
        ServiceDefinition("litellm", "horizontal", "ai_gateway", "core", "external",
                          "Generation/embeddings through existing adapters and aliases.",
                          ("modules/automation_diagnosis/litellm_client.py", "routes/diagnosis.py")),
        ServiceDefinition("gmail", "horizontal", "email", "capability", "external",
                          "Messaging Gmail API provider with delegated service-account credentials/DWD.",
                          ("modules/messaging/providers/gmail/client.py", "modules/messaging/providers/gmail/auth.py")),
        ServiceDefinition("scheduler", "module_local", "scheduler", "capability", "in_process",
                          "Flow asyncio task, single-process contract; NOT external horizontal infrastructure.",
                          ("modules/flow/scheduler.py", "ls_iMotorSoft_Srv01.py")),
        ServiceDefinition("gupshup", "horizontal", "whatsapp_transport", "capability", "external",
                          "Existing inbound Messaging bridge to Flow; outbound replies are no-op there.",
                          ("modules/messaging/webhooks/gupshup_whatsapp.py",)),
        ServiceDefinition("evolution", "horizontal", "whatsapp_transport", "capability", "external",
                          "Messaging DEV adapter exists; no Flow/Diagnosis consumer. Inventory is not a health check.",
                          ("modules/messaging/providers/evolution/provider.py", "modules/messaging/service.py")),
        ServiceDefinition("auth_permissions", "horizontal", "access_control", "capability", "in_process",
                          "Existing Console PASETO and persistent capabilities; not embed-origin authentication.",
                          ("modules/flow/executive_auth.py", "modules/flow/configuration_auth.py")),
    ),
    modules=(
        ModuleDefinition(
            "flow", "Persisted cases, routing, SLA, approval, audit and configuration; extra channels/AI are capabilities.",
            "core",
            (
                ServiceDependency("postgres", "required", "operational_state", "Base persisted workflow needs PostgreSQL.",
                                  ("modules/flow/repository.py", "modules/flow/configuration_repository.py")),
                ServiceDependency("scheduler", "optional", "automatic_cycles",
                                  "Srv01 currently starts it unconditionally; finite CLI/manual operations do not need it.",
                                  ("modules/flow/scheduler.py", "modules/flow/run_automatic_once.py", "ls_iMotorSoft_Srv01.py")),
                ServiceDependency("gmail", "runtime_conditional", "mail_intake_and_delivery",
                                  "Required on mail paths: poll_once, resend/delivery; scheduler creates sender when mail_intake_enabled, within enabled automation.",
                                  ("modules/flow/poll_once.py", "modules/flow/scheduler.py", "modules/flow/routes.py")),
                ServiceDependency("litellm", "optional", "ai_interpretation",
                                  "Required within real AI intake, operational/approval interpretation and executive summary; not plain settings/case reads. TEAM360_AI_PROVIDER does not disable Flow adapters.",
                                  ("modules/flow/intake/ai.py", "modules/flow/operational_ai.py", "modules/flow/approval_ai.py", "modules/flow/executive_ai.py")),
                ServiceDependency("gupshup", "optional", "whatsapp_inbound",
                                  "Only the implemented Gupshup inbound bridge; no Evolution implication or outbound guarantee.",
                                  ("modules/messaging/webhooks/gupshup_whatsapp.py", "modules/messaging/whatsapp_flow_bridge.py")),
                ServiceDependency("auth_permissions", "runtime_conditional", "authenticated_access",
                                  "TEAM360_FLOW_ACCESS_MODE=authenticated uses PASETO + persisted permissions; default_admin bypasses login.",
                                  ("modules/flow/access_mode.py", "modules/flow/executive_auth.py", "modules/flow/configuration_auth.py")),
            ),
            ("console_web", "api", "finite_cli", "gupshup_webhook"),
            evidence=("modules/flow/routes.py", "modules/flow/poll_once.py",
                      "../astro/src/pages/w/[workspaceId]/flow/index.astro"),
        ),
        ModuleDefinition(
            "diagnosis", "Real public Vera diagnosis: persistent context/state, scoped retrieval and real AI (not memory/mock/dev adapters).",
            "core",
            (
                ServiceDependency("postgres", "required", "context_state_and_embed_bindings",
                                  "Real baseline needs persisted context/state and embed_clients; memory selection exists but is not equivalent functionality.",
                                  ("routes/diagnosis.py", "routes/automation_diagnosis.py", "modules/sales_diagnosis_runtime/knowledge_scope_resolver.py")),
                ServiceDependency("milvus", "required", "scoped_retrieval",
                                  "Real baseline needs Milvus 2.6; public builder selects it on configured URI/host, otherwise NullRetrieval (not equivalent).",
                                  ("routes/diagnosis.py", "modules/sales_diagnosis_runtime/milvus_provider.py")),
                ServiceDependency("litellm", "required", "generation_classifier_embeddings",
                                  "Real baseline uses litellm generation/classifier plus query embeddings. Non-litellm safe acknowledgements/mock are not equivalent diagnosis.",
                                  ("routes/diagnosis.py", "modules/automation_diagnosis/ai_interpreter.py")),
            ),
            ("home", "web", "embed"), ("mamamia360_embed",),
            ("../astro/src/pages/t360.astro", "../astro/src/pages/w/[workspaceId]/diagnosis/index.astro",
             "../astro/src/lib/t360/embed/browser-global.ts", "routes/diagnosis.py"),
        ),
    ),
    bindings=(
        BindingDefinition(
            "mamamia360_embed", "diagnosis", "embed", "distributor_embed", "mamamia360", "postgres",
            (("assistant_instance_code", "team360_sales_diagnosis"), ("organization_code", "team360_live"),
             ("workspace_code", "team360_public_site"), ("package_code", "pkg_sales_diagnosis"),
             ("knowledge_scope_code", "ks_team360_sales_diagnosis")),
            "Distributor pilot embed binding. Seed and Phase-1 DEV snapshot target public Vera; not a Mamamia tenant DB entity or independent corpus. Active context/origins remain DB-authoritative, not this inventory.",
            ("db/migrations/009_seed_mamamia360_embed_client.sql", "routes/diagnosis.py", "modules/embed_clients/repository.py"),
        ),
    ),
    configuration=(
        ConfigurationAssociation(
            ("AUTOMATION_DIAGNOSIS_REPOSITORY", "TEAM360_DIAGNOSIS_STATE_PROVIDER"), ("diagnosis",), ("postgres",),
            ("automation_diagnosis._build_service", "diagnosis._build_public_state_repo"),
            "Automation postgres creates/sets lazy global pool; public state prefers AUTOMATION_DIAGNOSIS_REPOSITORY over STATE_PROVIDER. Pool bootstrap also affects Flow; not lifecycle isolation.",
            ("routes/automation_diagnosis.py", "routes/diagnosis.py")),
        ConfigurationAssociation(
            ("TEAM360_AI_PROVIDER",), ("diagnosis",), ("litellm",),
            ("build_ai_interpreter", "_PublicTurnLLMProvider.generate"),
            "Selects Diagnosis AI; not a universal Flow AI switch.", ("routes/diagnosis.py", "modules/automation_diagnosis/ai_interpreter.py")),
        ConfigurationAssociation(
            ("TEAM360_LITELLM_BASE_URL", "TEAM360_LITELLM_MODEL_ALIAS", "TEAM360_LITELLM_API_MODE"),
            ("flow", "diagnosis"), ("litellm",), ("LiteLLMClient", "Flow AI interpreters", "public generation/embeddings"),
            "Shared adapter base/model/API policy; public embedding HTTP uses BASE_URL but its own embedding alias.",
            ("modules/automation_diagnosis/litellm_client.py", "modules/flow/executive_ai.py", "routes/diagnosis.py")),
        ConfigurationAssociation(
            ("TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER",), ("diagnosis",), ("milvus", "litellm"),
            ("legacy retrieval builder", "_PublicLiteLLMEmbeddingProvider"),
            "Selects legacy retrieval and hardens public embedding failures in milvus mode; public retrieval selection itself uses URI/host.",
            ("modules/automation_diagnosis/milvus_knowledge.py", "routes/diagnosis.py")),
        ConfigurationAssociation(
            ("TEAM360_MILVUS_URI", "TEAM360_MILVUS_HOST", "TEAM360_MILVUS_PORT", "TEAM360_MILVUS_COLLECTION",
             "TEAM360_EMBEDDING_VERSION", "TEAM360_KNOWLEDGE_SCOPE_ID"), ("diagnosis",), ("milvus",),
            ("MilvusRuntimeConfig.from_env",), "Lazy connection, collection and scope/version filtering, not service provisioning.",
            ("modules/sales_diagnosis_runtime/milvus_provider.py",)),
        ConfigurationAssociation(
            ("TEAM360_EMBEDDING_MODEL",), ("diagnosis",), ("litellm",), ("_PublicLiteLLMEmbeddingProvider",),
            "Public query embedding model alias.", ("routes/diagnosis.py",)),
        ConfigurationAssociation(
            ("TEAM360_FLOW_ACCESS_MODE",), ("flow",), ("auth_permissions",), ("flow_access_mode",),
            "default_admin or authenticated access policy; no new auth.", ("modules/flow/access_mode.py",)),
        ConfigurationAssociation(
            ("TEAM360_FLOW_GMAIL_ACCOUNT", "TEAM360_GMAIL_DELEGATED_USER", "TEAM360_GMAIL_SERVICE_ACCOUNT_FILE"),
            ("flow",), ("gmail",), ("GmailClient", "delegated_user", "create_delegated_credentials"),
            "Delegated account and private credential-file reference; no values read/stored by inventory.",
            ("modules/messaging/providers/gmail/config.py", "modules/messaging/providers/gmail/auth.py", "modules/flow/scheduler.py")),
        ConfigurationAssociation(
            ("TEAM360_PUBLIC_ORGANIZATION_CODE", "TEAM360_PUBLIC_WORKSPACE_CODE", "TEAM360_PUBLIC_PACKAGE_CODE",
             "TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE"), ("diagnosis",), (), ("backend-dev.sh exports/logs",),
            "Declared operational markers only: no inspected Python runtime consumer. Public defaults/allowlist and DB embed_clients resolve effective context, not these variables.",
            ("../backend-dev.sh", "routes/diagnosis.py")),
    ),
)


def get_module_definition(code: str) -> ModuleDefinition:
    return REGISTRY.get_module(code)


def get_service_definition(code: str) -> ServiceDefinition:
    return REGISTRY.get_service(code)


def get_module_dependencies(code: str, kind: DependencyKind | None = None) -> tuple[ServiceDependency, ...]:
    return REGISTRY.dependencies(code, kind)


def get_service_consumers(code: str) -> tuple[str, ...]:
    return REGISTRY.consumers(code)


def get_module_bindings(code: str) -> tuple[BindingDefinition, ...]:
    return REGISTRY.module_bindings(code)

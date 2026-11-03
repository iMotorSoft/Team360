"""Pure profile resolution and static configuration checks; never lifecycle policy.

Configuration is a caller-supplied, non-secret snapshot, not os.environ. Validation
checks declarations only: no credential, connectivity, DB context or health proof.
Optional capabilities are not selected here. Explicit conditional activation adds
validation obligations without rewriting the registry's dependency classification.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from modules.srv05_architecture import (
    REGISTRY, ArchitectureRegistry, BindingDefinition, ServiceDependency,
)


@dataclass(frozen=True, slots=True)
class ProfileDependency:
    module: str
    dependency: ServiceDependency
    scope: str
    active: bool | None  # None: optional/unselected; False: inactive conditional


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    code: str
    modules: tuple[str, ...]
    required_services: tuple[str, ...]
    optional_services: tuple[str, ...]
    conditional_services: tuple[str, ...]
    active_conditional_services: tuple[str, ...]
    local_components: tuple[ProfileDependency, ...]
    dependencies: tuple[ProfileDependency, ...]
    bindings: tuple[BindingDefinition, ...]
    surfaces: tuple[tuple[str, str], ...]  # preserve module ownership
    unrelated_services: tuple[str, ...]

    @property
    def services_to_validate(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.required_services + self.active_conditional_services)))

    def to_dict(self) -> dict:
        """Detached stdlib JSON-serializable representation, without config values."""
        return asdict(self)


def resolve_runtime_profile(
    code: str, *, capabilities: Mapping[str, bool] | None = None,
    registry: ArchitectureRegistry = REGISTRY,
) -> RuntimeProfile:
    """Resolve a registered module or full union in lexical order.

    Conditional capability keys use registered *service codes* (gmail,
    auth_permissions). Unknown, unrelated and optional keys fail closed rather
    than silently implying activation. Full means all modules in this inventory,
    not all route modules/services installed in the repository.
    """
    modules = tuple(sorted(registry.modules if code == "full" else
                           (registry.get_module(code),), key=lambda m: m.code))
    conditions = {d.service for m in modules for d in m.dependencies
                  if d.kind == "runtime_conditional"}
    selected = dict(capabilities or {})
    if set(selected) - conditions:
        raise ValueError("Capabilities must name conditional services in this profile")
    if any(type(value) is not bool for value in selected.values()):
        raise ValueError("Capability values must be bool")
    dependencies = tuple(
        ProfileDependency(m.code, d, registry.get_service(d.service).scope,
                          True if d.kind == "required" else
                          selected.get(d.service, False) if d.kind == "runtime_conditional" else None)
        for m in modules for d in sorted(m.dependencies, key=lambda d: d.service)
    )
    horizontal = tuple(d for d in dependencies if d.scope == "horizontal")
    required = {d.dependency.service for d in horizontal if d.dependency.kind == "required"}
    conditional = {d.dependency.service for d in horizontal
                   if d.dependency.kind == "runtime_conditional"} - required
    optional = {d.dependency.service for d in horizontal
                if d.dependency.kind == "optional"} - required - conditional
    used = {d.dependency.service for d in dependencies}
    return RuntimeProfile(
        code, tuple(m.code for m in modules), tuple(sorted(required)),
        tuple(sorted(optional)), tuple(sorted(conditional)),
        tuple(sorted({d.dependency.service for d in horizontal
                      if d.dependency.kind == "runtime_conditional" and d.active} - required)),
        tuple(d for d in dependencies if d.scope == "module_local"), dependencies,
        tuple(sorted((b for m in modules for b in registry.module_bindings(m.code)),
                     key=lambda b: b.code)),
        tuple((m.code, surface) for m in modules for surface in sorted(m.surfaces)),
        tuple(sorted(s.code for s in registry.services if s.code not in used)),
    )


@dataclass(frozen=True, slots=True)
class ConfigurationIssue:
    service: str
    code: str
    variables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileValidation:
    issues: tuple[ConfigurationIssue, ...]
    checked_services: tuple[str, ...]
    unchecked_services: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.issues and not self.unchecked_services


def validate_runtime_profile(profile: RuntimeProfile, config: Mapping[str, str]) -> ProfileValidation:
    """Strict explicit baseline declarations, NOT a production env loader.

    Required endpoints/aliases/filter declarations must be supplied even where
    legacy runtime has defaults. Provider precedence for Diagnosis mirrors its
    repository selector; an explicitly contradictory state marker is reported.
    Secrets are neither requested nor retained. Optional/inactive/unrelated
    services are ignored. Unknown validation policies are reported as unchecked.
    """
    issues: list[ConfigurationIssue] = []
    checked: list[str] = []
    unchecked: list[str] = []

    def value(name: str) -> str:
        raw = config.get(name, "")
        if not isinstance(raw, str):
            raise TypeError("Configuration snapshot values must be strings")
        return raw.strip()

    def issue(service: str, code: str, *names: str) -> None:
        issues.append(ConfigurationIssue(service, code, tuple(names)))

    def require(service: str, *names: str) -> None:
        for name in names:
            if not value(name):
                issue(service, "missing_configuration", name)

    def provider(service: str, name: str, expected: str, *, required: bool = True) -> None:
        actual = value(name).lower()
        if not actual and required:
            issue(service, "missing_configuration", name)
        elif actual and actual != expected:
            issue(service, "incompatible_provider", name)

    def endpoint(service: str, name: str, schemes: set[str]) -> None:
        raw = value(name)
        if not raw:
            issue(service, "missing_configuration", name)
            return
        try:
            parsed = urlsplit(raw)
            valid = parsed.scheme in schemes and bool(parsed.hostname)
            if parsed.port is not None:
                valid = valid and 0 < parsed.port <= 65535
        except ValueError:
            valid = False
        if not valid:
            issue(service, "invalid_endpoint", name)

    for service in profile.services_to_validate:
        if service == "postgres":
            name = "TEAM360_DB_URL" if value("TEAM360_DB_URL") else "TEAM360_DB_URL_PSQL"
            endpoint(service, name, {"postgres", "postgresql", "postgresql+psycopg"})
            if "diagnosis" in profile.modules:
                selector = "AUTOMATION_DIAGNOSIS_REPOSITORY" if value("AUTOMATION_DIAGNOSIS_REPOSITORY") else "TEAM360_DIAGNOSIS_STATE_PROVIDER"
                provider(service, selector, "postgres")
                provider(service, "TEAM360_DIAGNOSIS_STATE_PROVIDER", "postgres", required=False)
        elif service == "litellm":
            endpoint(service, "TEAM360_LITELLM_BASE_URL", {"http", "https"})
            require(service, "TEAM360_LITELLM_MODEL_ALIAS")
            mode = value("TEAM360_LITELLM_API_MODE").lower()
            if mode and mode not in {"auto", "chat", "responses"}:
                issue(service, "incompatible_provider", "TEAM360_LITELLM_API_MODE")
            if "diagnosis" in profile.modules:
                provider(service, "TEAM360_AI_PROVIDER", "litellm")
        elif service == "milvus":
            provider(service, "TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER", "milvus")
            if value("TEAM360_MILVUS_URI"):
                endpoint(service, "TEAM360_MILVUS_URI", {"http", "https", "tcp"})
            else:
                require(service, "TEAM360_MILVUS_HOST", "TEAM360_MILVUS_PORT")
                port = value("TEAM360_MILVUS_PORT")
                if port and (not port.isascii() or not port.isdigit() or not 0 < int(port) <= 65535):
                    issue(service, "invalid_port", "TEAM360_MILVUS_PORT")
            require(service, "TEAM360_MILVUS_COLLECTION", "TEAM360_EMBEDDING_VERSION")
        elif service == "gmail":
            # Only validate a private file reference; never open it or read credentials.
            require(service, "TEAM360_GMAIL_SERVICE_ACCOUNT_FILE", "TEAM360_GMAIL_DELEGATED_USER")
        elif service == "auth_permissions":
            provider(service, "TEAM360_FLOW_ACCESS_MODE", "authenticated")
            # Credential/permission availability needs a future separate preflight.
        else:
            unchecked.append(service)
            continue
        checked.append(service)
    return ProfileValidation(tuple(sorted(set(issues), key=lambda i: (i.service, i.code, i.variables))),
                             tuple(checked), tuple(unchecked))

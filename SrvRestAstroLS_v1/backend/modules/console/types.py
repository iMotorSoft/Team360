from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypedDict


WorkspaceType = Literal["team360", "partner", "client", "internal"]
WorkspaceStatus = Literal["active", "inactive", "testing", "retired"]
UserType = Literal["internal", "partner", "client"]
ServiceStatus = Literal["active", "inactive", "testing", "retired", "paused"]
ServiceHealth = Literal["healthy", "warning", "critical", "pending"]
Severity = Literal["critical", "warning", "info", "debug"]
AlertStatus = Literal["open", "acknowledged", "resolved"]
VisibilityLevel = Literal["client", "partner", "internal"]


class RoleDTO(TypedDict):
    role_id: str
    role_code: str
    display_name: str


class ProfileDTO(TypedDict):
    profile_id: str
    profile_code: str
    display_name: str


class CurrentUserDTO(TypedDict):
    user_id: str
    display_name: str
    email: str
    user_type: UserType
    area_id: str | None
    roles: list[RoleDTO]
    permission_profiles: list[ProfileDTO]


class WorkspaceDTO(TypedDict):
    workspace_id: str
    workspace_code: str
    display_name: str
    workspace_type: WorkspaceType
    status: WorkspaceStatus


class EntitlementsDTO(TypedDict):
    plan_code: str
    plan_display_name: str
    features: list[str]


class NavItemDTO(TypedDict):
    id: str
    label: str
    route: str
    icon: str


class NavGroupDTO(TypedDict):
    group: str
    items: list[NavItemDTO]
    visibility_level: NotRequired[VisibilityLevel]


class TaskSummaryDTO(TypedDict):
    pending: int
    waiting_approval: int
    failed: int
    completed_today: int
    blocked_by_policy: int


class ServiceDTO(TypedDict):
    service_id: str
    package_id: str
    package_code: str
    package_name: str
    display_name: str
    status: ServiceStatus
    health: ServiceHealth
    plan_code: str
    category: str
    summary: str
    client_summary: str
    task_summary: TaskSummaryDTO
    has_knowledge: bool
    has_workers_visible: bool
    visibility_level: VisibilityLevel


class AlertDTO(TypedDict):
    alert_id: str
    severity: Severity
    message: str
    target: str
    created_at_utc: str
    status: AlertStatus


class AreaDTO(TypedDict):
    area_id: str
    area_code: str
    display_name: str


class WorkspaceContextDTO(TypedDict):
    active_area: str | None
    available_areas: list[AreaDTO]
    selected_package: str | None


class OrgContextDTO(TypedDict):
    organization_id: str
    organization_code: str
    display_name: str
    organization_type: str
    parent_organization_id: str | None
    status: str
    access_mode: Literal["own", "delegated"]
    delegated_by_organization_id: str | None


class DebugDTO(TypedDict):
    source: str
    permissions_evaluated: int
    hidden_items_count: int
    feature_flags: dict[str, bool]


@dataclass
class ConsoleBootstrap:
    workspace: WorkspaceDTO
    current_user: CurrentUserDTO
    effective_permissions: list[str]
    capabilities: list[str]
    entitlements: EntitlementsDTO
    navigation: list[NavGroupDTO]
    services: list[ServiceDTO]
    tasks_summary: TaskSummaryDTO
    alerts: list[AlertDTO]
    workspace_context: WorkspaceContextDTO
    organization_context: OrgContextDTO
    debug: DebugDTO | None = None

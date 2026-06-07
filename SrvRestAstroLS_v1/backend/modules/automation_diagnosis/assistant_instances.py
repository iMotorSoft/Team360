"""Assistant instance package contracts for automation diagnosis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PackageWorkerBinding:
    id: str
    worker_definition_id: str
    name: str
    role: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssistantInstanceConfig:
    organization_id: str
    organization_name: str
    workspace_id: str
    workspace_name: str
    automation_package_id: str
    automation_package_name: str
    assistant_instance_id: str
    assistant_instance_name: str
    knowledge_scope_id: str
    site_channel: str
    lead_owner: str
    market: str
    default_locale: str
    supported_locales: tuple[str, ...]
    cost_center: str
    package_workers: tuple[PackageWorkerBinding, ...]
    commercial_name: str = ""
    assistant_display_name: str = ""
    package_display_name: str = ""
    service_display_name: str = ""
    service_code: str = ""
    template_code: str = ""
    public_channel_code: str = ""
    arangodb_scope: dict[str, Any] = field(default_factory=dict)
    milvus_scope: dict[str, Any] = field(default_factory=dict)

    def package_worker_ids(self) -> list[str]:
        return [worker.id for worker in self.package_workers if worker.enabled]

    def resolve_locale(self, requested_locale: str | None) -> str:
        if not requested_locale:
            return self.default_locale
        locale = requested_locale.lower()
        if locale not in self.supported_locales:
            raise ValueError(
                f"Locale {requested_locale!r} is not supported by assistant_instance "
                f"{self.assistant_instance_id!r}"
            )
        return locale

    def validate_payload_scope(self, payload: dict[str, Any]) -> None:
        expected = {
            "workspace_id": self.workspace_id,
            "automation_package_id": self.automation_package_id,
            "knowledge_scope_id": self.knowledge_scope_id,
        }
        for key, value in expected.items():
            provided = payload.get(key)
            if provided and provided != value:
                raise ValueError(
                    f"Payload {key}={provided!r} does not match assistant_instance "
                    f"{self.assistant_instance_id!r} expected {value!r}"
                )

    def to_session_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["package_worker_ids"] = self.package_worker_ids()
        return data


# @lat: [[customer-packaged-assistant-instance#Team360 Direct Installation]]
TEAM360_SALES_DIAGNOSIS_CONFIG = AssistantInstanceConfig(
    organization_id="org_team360",
    organization_name="Team360.live",
    workspace_id="team360_public_site",
    workspace_name="Team360.live Public Site",
    automation_package_id="pkg_sales_diagnosis",
    automation_package_name="Asistente Inteligente Vera",
    assistant_instance_id="team360_sales_diagnosis",
    assistant_instance_name="Asistente Inteligente Vera",
    knowledge_scope_id="ks_team360_sales_diagnosis",
    site_channel="team360.live",
    lead_owner="Team360",
    market="direct",
    default_locale="es",
    supported_locales=("es", "en"),
    cost_center="team360_direct_sales",
    package_workers=(
        PackageWorkerBinding(
            id="pw_team360_guided_intake",
            worker_definition_id="guided_intake_worker",
            name="Guided intake",
            role="collect_structured_sales_diagnosis_answers",
        ),
        PackageWorkerBinding(
            id="pw_team360_lead_qualification",
            worker_definition_id="lead_qualification_worker",
            name="Lead qualification",
            role="qualify_commercial_fit_and_next_step",
        ),
        PackageWorkerBinding(
            id="pw_team360_knowledge_retrieval",
            worker_definition_id="knowledge_retrieval_worker",
            name="Knowledge retrieval",
            role="retrieve_scoped_sales_and_automation_context",
        ),
        PackageWorkerBinding(
            id="pw_team360_diagnosis_scoring",
            worker_definition_id="diagnosis_scoring_worker",
            name="Diagnosis scoring",
            role="score_viability_risk_and_package_fit",
        ),
        PackageWorkerBinding(
            id="pw_team360_package_recommendation",
            worker_definition_id="package_recommendation_worker",
            name="Package recommendation",
            role="recommend_team360_package_or_consulting_path",
        ),
        PackageWorkerBinding(
            id="pw_team360_proposal_outline",
            worker_definition_id="proposal_outline_worker",
            name="Proposal outline",
            role="draft_structured_proposal_outline",
        ),
        PackageWorkerBinding(
            id="pw_team360_crm_handoff",
            worker_definition_id="crm_handoff_worker",
            name="CRM handoff",
            role="prepare_internal_lead_card_for_sales_follow_up",
        ),
        PackageWorkerBinding(
            id="pw_team360_calendar_handoff",
            worker_definition_id="calendar_handoff_worker",
            name="Calendar handoff",
            role="suggest_discovery_meeting_handoff",
        ),
        PackageWorkerBinding(
            id="pw_team360_agui_render",
            worker_definition_id="agui_render_worker",
            name="AG-UI render",
            role="render_validated_semantic_output",
        ),
    ),
    commercial_name="Vera",
    assistant_display_name="Vera",
    package_display_name="Asistente Inteligente Vera",
    service_display_name="Asistente Inteligente Vera",
    service_code="svc_sales_diagnosis",
    template_code="team360_sales_automation_diagnosis",
    public_channel_code="team360_live_home",
    arangodb_scope={
        "database": "team360_knowledge",
        "collections": [
            "diagnosis_vertices",
            "diagnosis_edges",
            "diagnosis_documents",
            "diagnosis_playbooks",
        ],
        "scope_filter_fields": [
            "organization_id",
            "workspace_id",
            "assistant_instance_id",
            "knowledge_scope_id",
        ],
        "physical_collection_per_customer": False,
    },
    milvus_scope={
        "collection": "team360_diagnosis_chunks",
        "partition_key": "knowledge_scope_id",
        "required_filter_fields": [
            "organization_id",
            "workspace_id",
            "assistant_instance_id",
            "knowledge_scope_id",
        ],
    },
)

LEGACY_AUTOMATION_DIAGNOSIS_CONFIG = AssistantInstanceConfig(
    organization_id="org_team360",
    organization_name="Team360",
    workspace_id="team360_internal",
    workspace_name="Team360 Internal Diagnosis Lab",
    automation_package_id="pkg_team360_automation_diagnosis",
    automation_package_name="Automation Diagnosis Lab",
    assistant_instance_id="automation_diagnosis_default",
    assistant_instance_name="Automation Diagnosis Default",
    knowledge_scope_id="ks_team360_automation_diagnosis",
    site_channel="internal_lab",
    lead_owner="Team360",
    market="internal",
    default_locale="es",
    supported_locales=("es", "en"),
    cost_center="team360_internal_lab",
    package_workers=TEAM360_SALES_DIAGNOSIS_CONFIG.package_workers,
    arangodb_scope={**TEAM360_SALES_DIAGNOSIS_CONFIG.arangodb_scope, "physical_collection_per_customer": False},
    milvus_scope=TEAM360_SALES_DIAGNOSIS_CONFIG.milvus_scope,
)

ASSISTANT_INSTANCE_CONFIGS: dict[str, AssistantInstanceConfig] = {
    TEAM360_SALES_DIAGNOSIS_CONFIG.assistant_instance_id: TEAM360_SALES_DIAGNOSIS_CONFIG,
    LEGACY_AUTOMATION_DIAGNOSIS_CONFIG.assistant_instance_id: LEGACY_AUTOMATION_DIAGNOSIS_CONFIG,
}


def get_assistant_instance_config(assistant_instance_id: str) -> AssistantInstanceConfig:
    try:
        return ASSISTANT_INSTANCE_CONFIGS[assistant_instance_id]
    except KeyError as exc:
        raise ValueError(f"Unknown assistant_instance_id: {assistant_instance_id}") from exc


def list_assistant_instance_configs() -> list[AssistantInstanceConfig]:
    return list(ASSISTANT_INSTANCE_CONFIGS.values())


def resolve_assistant_instance_config(payload: dict[str, Any], default_assistant_instance_id: str) -> AssistantInstanceConfig:
    assistant_instance_id = payload.get("assistant_instance_id") or default_assistant_instance_id
    config = get_assistant_instance_config(assistant_instance_id)
    config.validate_payload_scope(payload)
    return config

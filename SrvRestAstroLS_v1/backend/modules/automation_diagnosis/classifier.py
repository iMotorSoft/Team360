"""Deterministic classifier for automation diagnosis."""

from __future__ import annotations

from .schemas import AIInterpretation, ClassificationResult, DiagnosisSession, ScoreResult


BASE_BLOCKED_ACTIONS = ["delete_record", "post_financial_transaction", "bypass_mfa"]


# @lat: [[automation-diagnosis#Automation Diagnosis#Classification]]
# @lat: [[security-hitl-mfa#Security HITL MFA#Classifier Guidance]]
def classify_session(
    session: DiagnosisSession,
    score: ScoreResult,
    interpretation: AIInterpretation,
) -> ClassificationResult:
    systems = set(session.answers.get("systems_involved").selected if session.answers.get("systems_involved") else [])
    risk_flags = set(score.risk_flags)
    blocked_actions = list(BASE_BLOCKED_ACTIONS)
    requires_human_approval = True

    if "hard_security_stop" in risk_flags:
        classification = "not_recommended"
        mode = "blocked"
        package = "consulting_security_review"
        workers = ["diagnosis_ai_interpreter", "workflow_classifier"]
        allowed_actions = ["document_process", "recommend_manual_path"]
    elif score.score_total < 45:
        classification = "not_recommended" if "volume_low" in score.rule_hits else "consulting_required"
        mode = "blocked" if classification == "not_recommended" else "assisted"
        package = "consulting_prior_assessment"
        workers = ["diagnosis_ai_interpreter", "workflow_classifier"]
        allowed_actions = ["analyze_process", "prepare_discovery_notes"]
    elif "rules_unclear" in risk_flags or "high_human_dependency" in risk_flags or "high_sensitivity_data" in risk_flags:
        classification = "consulting_required"
        mode = "approval_required"
        package = "team360_consulting_discovery"
        workers = ["diagnosis_ai_interpreter", "workflow_classifier", "approval_worker"]
        allowed_actions = ["read_data", "prepare_draft", "generate_report"]
    elif systems & {"erp", "sap_b1", "browser_portal", "desktop_app"} or (
        score.score_total >= 70 and "volume_high_or_daily" in score.rule_hits
    ):
        classification = "operational_automation"
        mode = "assisted"
        package = "team360_ops_starter"
        workers = ["diagnosis_ai_interpreter", "workflow_classifier", "approval_worker"]
        if "sap_b1" in systems or "erp" in systems:
            workers.append("erp_connector_or_rpa_worker")
        if "whatsapp" in systems:
            workers.append("whatsapp_intake_worker")
        if "browser_portal" in systems:
            workers.append("browser_worker")
        if "desktop_app" in systems:
            workers.append("desktop_worker")
        allowed_actions = ["read_data", "prepare_draft", "generate_report"]
    else:
        classification = "standard_package"
        mode = "assisted"
        package = "team360_standard_automation"
        workers = ["diagnosis_ai_interpreter", "workflow_classifier", "approval_worker"]
        allowed_actions = ["classify", "prepare_draft", "generate_report"]

    if mode == "blocked":
        requires_human_approval = True
    elif mode in {"assisted", "approval_required"}:
        requires_human_approval = True
    else:
        requires_human_approval = False

    credential_refs = []
    if systems & {"erp", "sap_b1"}:
        credential_refs.append({"type": "erp_user", "required": True, "storage": "secret_ref_only"})
    if "browser_portal" in systems:
        credential_refs.append({"type": "browser_session_or_portal_user", "required": True, "storage": "secret_ref_only"})
    if "desktop_app" in systems:
        credential_refs.append({"type": "desktop_user_or_rdp_user", "required": True, "storage": "secret_ref_only"})
    if "whatsapp" in systems:
        credential_refs.append({"type": "messaging_provider", "required": False, "storage": "secret_ref_only"})

    return ClassificationResult(
        classification=classification,
        automation_mode=mode,
        recommended_package_type=package,
        suggested_worker_definitions=sorted(set(workers)),
        required_package_worker_config={
            "mode": mode,
            "requires_human_approval": requires_human_approval,
            "allowed_actions": allowed_actions,
            "blocked_actions": blocked_actions,
            "future_external_worker_ready": True,
        },
        required_credential_refs=credential_refs,
        required_knowledge_scope={
            "recommended": True,
            "retrieval_mode": "rag",
            "future_graph_enabled": bool(systems & {"erp", "sap_b1"} or "critical_business_impact" in risk_flags),
        },
        risk_flags=sorted(risk_flags),
        blocked_actions=blocked_actions,
        requires_human_approval=requires_human_approval,
    )

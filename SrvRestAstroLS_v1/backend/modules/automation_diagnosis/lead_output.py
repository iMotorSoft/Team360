"""Internal Team360 lead card generation."""

from __future__ import annotations

from .schemas import AIInterpretation, ClassificationResult, DiagnosisSession, ScoreResult


def build_internal_card(
    session: DiagnosisSession,
    interpretation: AIInterpretation,
    score: ScoreResult,
    classification: ClassificationResult,
) -> dict:
    signals = interpretation.signals
    return {
        "lead_type": "automation_opportunity",
        "organization_id": session.organization_id,
        "workspace_id": session.workspace_id,
        "assistant_instance_id": session.assistant_instance_id,
        "automation_package_id": session.automation_package_id,
        "knowledge_scope_id": session.knowledge_scope_id,
        "site_channel": session.site_channel,
        "lead_owner": session.lead_owner,
        "locale": session.locale,
        "market": session.market,
        "package_worker_ids": session.package_worker_ids,
        "cost_attribution": session.cost_attribution,
        "session_id": session.id,
        "correlation_id": session.correlation_id,
        "process": _answer_text(session, "process_to_automate") or signals.get("process"),
        "business_pain": _answer_text(session, "business_pain") or signals.get("business_pain"),
        "systems": _systems(session, signals),
        "classification": classification.classification,
        "automation_mode": classification.automation_mode,
        "recommended_package_type": classification.recommended_package_type,
        "suggested_worker_definitions": classification.suggested_worker_definitions,
        "required_package_worker_config": classification.required_package_worker_config,
        "required_credential_refs": classification.required_credential_refs,
        "required_knowledge_scope": classification.required_knowledge_scope,
        "score_total": score.score_total,
        "score_breakdown": score.score_breakdown,
        "rule_hits": score.rule_hits,
        "risk_flags": classification.risk_flags,
        "blocked_actions": classification.blocked_actions,
        "requires_human_approval": classification.requires_human_approval,
        "next_step": _next_step(classification.classification),
    }


def _answer_text(session: DiagnosisSession, step_id: str) -> str:
    answer = session.answers.get(step_id)
    return answer.free_text if answer else ""


def _systems(session: DiagnosisSession, signals: dict) -> list[str]:
    answer = session.answers.get("systems_involved")
    selected = answer.selected if answer else []
    interpreted = signals.get("systems") or []
    return sorted(set([*selected, *[str(item) for item in interpreted]]))


def _next_step(classification: str) -> str:
    if classification == "standard_package":
        return "package_scope_review"
    if classification == "operational_automation":
        return "technical_discovery_call"
    if classification == "consulting_required":
        return "paid_discovery_or_process_mapping"
    return "manual_alternative_or_reject"

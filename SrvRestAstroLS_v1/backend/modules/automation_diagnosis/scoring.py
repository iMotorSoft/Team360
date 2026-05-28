"""Deterministic scoring for automation diagnosis."""

from __future__ import annotations

from .schemas import AIInterpretation, DiagnosisSession, ScoreResult


def _selected(session: DiagnosisSession, step_id: str) -> set[str]:
    answer = session.answers.get(step_id)
    return set(answer.selected if answer else [])


def _text(session: DiagnosisSession, step_id: str) -> str:
    answer = session.answers.get(step_id)
    return (answer.normalized_text if answer else "").lower()


def score_session(session: DiagnosisSession, interpretation: AIInterpretation) -> ScoreResult:
    breakdown = {
        "volume": 0,
        "rules_clarity": 0,
        "systems_digitization": 0,
        "human_dependency": 0,
        "security_risk": 0,
        "data_sensitivity": 0,
        "impact": 0,
        "knowledge_need": 0,
    }
    rule_hits: list[str] = []
    risk_flags: list[str] = list(dict.fromkeys(interpretation.risks))

    frequency = _selected(session, "frequency_volume")
    if "high_volume" in frequency or "daily" in frequency:
        breakdown["volume"] += 18
        rule_hits.append("volume_high_or_daily")
    elif "medium_volume" in frequency or "weekly" in frequency:
        breakdown["volume"] += 10
        rule_hits.append("volume_medium")
    elif "low_volume" in frequency or "monthly" in frequency:
        breakdown["volume"] -= 8
        rule_hits.append("volume_low")

    rules = _selected(session, "rules_clarity")
    if "clear" in rules:
        breakdown["rules_clarity"] += 18
        rule_hits.append("rules_clear")
    elif "partially_clear" in rules:
        breakdown["rules_clarity"] += 10
        rule_hits.append("rules_partially_clear")
        risk_flags.append("rules_partially_clear")
    elif "mostly_manual" in rules or "unknown" in rules:
        breakdown["rules_clarity"] -= 10
        risk_flags.append("rules_unclear")

    systems = _selected(session, "systems_involved")
    digital_systems = systems & {"excel", "erp", "sap_b1", "whatsapp", "email", "browser_portal", "desktop_app", "api"}
    if digital_systems:
        breakdown["systems_digitization"] += min(18, 6 + len(digital_systems) * 3)
        rule_hits.append("digital_systems_present")
    if "sap_b1" in systems or "erp" in systems:
        risk_flags.append("requires_erp_access")
    if "browser_portal" in systems:
        risk_flags.append("browser_automation_candidate")
    if "desktop_app" in systems:
        risk_flags.append("desktop_automation_candidate")

    dependency = _selected(session, "human_dependency")
    if "low" in dependency:
        breakdown["human_dependency"] += 12
    elif "medium" in dependency:
        breakdown["human_dependency"] += 5
        risk_flags.append("human_review_likely")
    elif "high" in dependency or "expert_judgement" in dependency:
        breakdown["human_dependency"] -= 12
        risk_flags.append("high_human_dependency")

    security = _selected(session, "access_security")
    if security & {"email_otp", "sms_otp", "totp", "push_or_qr"}:
        breakdown["security_risk"] -= 8
        risk_flags.append("validate_mfa")
    if security & {"fido2_hardware", "biometric"}:
        breakdown["security_risk"] -= 35
        risk_flags.append("hard_security_stop")
        rule_hits.append("hardware_or_biometric_security")
    if "unknown" in security:
        breakdown["security_risk"] -= 8
        risk_flags.append("unknown_access_security")

    sensitivity = _selected(session, "data_sensitivity")
    if sensitivity & {"financial_data", "erp_operational_data", "personal_data"}:
        breakdown["data_sensitivity"] -= 6
        risk_flags.append("sensitive_data")
    if sensitivity & {"banking_or_payments", "religious_or_sensitive"}:
        breakdown["data_sensitivity"] -= 18
        risk_flags.append("high_sensitivity_data")

    impact = _selected(session, "economic_impact")
    if "critical" in impact:
        breakdown["impact"] += 16
        risk_flags.append("critical_business_impact")
    elif "high" in impact:
        breakdown["impact"] += 14
    elif "medium" in impact:
        breakdown["impact"] += 8
    elif "low" in impact:
        breakdown["impact"] -= 8

    all_text = " ".join(_text(session, step) for step in session.answers)
    if any(term in all_text for term in ["manual", "repetitivo", "errores", "demora", "copian", "carga"]):
        breakdown["impact"] += 6
        rule_hits.append("manual_repetitive_pain")

    knowledge_need = str(interpretation.signals.get("knowledge_need") or "").lower()
    if knowledge_need in {"rag", "graphrag", "hybrid"} or "sap_b1" in systems or "erp" in systems:
        breakdown["knowledge_need"] += 4
        rule_hits.append("knowledge_scope_recommended")

    total = max(0, min(100, 50 + sum(breakdown.values())))
    return ScoreResult(
        score_total=total,
        score_breakdown=breakdown,
        rule_hits=rule_hits,
        risk_flags=sorted(set(risk_flags)),
    )

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    DIAGNOSIS_VERSION,
    StructuredDiagnosis,
)


# ---------------------------------------------------------------------------
# Pattern detection helpers (deterministic, no LLM)
# ---------------------------------------------------------------------------

_CLOSED_SOFTWARE_TEXT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:programa\s+cerrado|closed\s+(?:windows\s+)?application|sin\s+api|no\s+(?:sabemos\s+)?(?:si\s+)?tiene\s+api)\b", re.IGNORECASE),
    re.compile(r"\b(?:software\s+propietari[o0]|proprietary\s+(?:software|system)|sistema\s+cerrad[o0])\b", re.IGNORECASE),
    re.compile(r"\b(?:aplicaci[o0]n\s+de\s+escritorio|desktop\s+application|legacy\s+system|sistema\s+legad[o0])\b", re.IGNORECASE),
    re.compile(r"\b(?:no\s+exporta|doesn.'?t\s+export|sin\s+conexi[o0]n|no\s+(?:tiene|hay)\s+integraci[o0]n)\b", re.IGNORECASE),
]

_MFA_TEXT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:c[oó0]digo\s+sms|c[oó0]digo\s+de\s+verificaci[oó0]n|c[oó0]digo\s+de\s+un\s+solo\s+uso)\b", re.IGNORECASE),
    re.compile(r"\b(?:sms\s+code|verification\s+code|one.time\s+code|otp|2fa|two.factor)\b", re.IGNORECASE),
    re.compile(r"\b(?:autenticaci[oó0]n|authentication|mfa|multi.factor)\b", re.IGNORECASE),
]

_SENSITIVE_DECISION_TEXT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:descuentos?\s+excepcionales?|exceptional\s+discounts?)\b", re.IGNORECASE),
    re.compile(r"\b(?:reclamos?\s+sensibles?|sensitive\s+claims?)\b", re.IGNORECASE),
    re.compile(r"\b(?:sin\s+revisi[o0]n\s+humana|without\s+human\s+review|sin\s+que\s+nadie\s+revise)\b", re.IGNORECASE),
    re.compile(r"\b(?:aprobar\s+autom[a0]ticamente|automatically\s+approve)\b", re.IGNORECASE),
    re.compile(r"\b(?:financier[o0]|reputacional|financial|reputational)\s+(?:riesgo|risk)\b", re.IGNORECASE),
]

_INDUSTRIAL_TEXT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(?:proceso\s+industrial|industrial\s+process)\b", re.IGNORECASE),
    re.compile(r"\b(?:sensores?|sensors?|iot)\b", re.IGNORECASE),
    re.compile(r"\b(?:aprobaciones?\s+operativas?|operational\s+approvals?)\b", re.IGNORECASE),
]

# Systems canonical values that indicate closed/proprietary software
_CLOSED_SYSTEMS = frozenset({"closed_windows_application", "proprietary_system"})


# ---------------------------------------------------------------------------
# Deterministic builder
# ---------------------------------------------------------------------------


def build_structured_diagnosis(semantic_memory: dict[str, Any]) -> dict[str, Any]:
    diagnosis = _build(semantic_memory)
    return asdict(diagnosis)


def _build(semantic_memory: dict[str, Any]) -> StructuredDiagnosis:
    mem = semantic_memory

    channels = mem.get("channels", [])
    systems = mem.get("systems_and_data_sources", [])
    entities = mem.get("entities", [])
    language = (mem.get("language") or {}).get("preferred_response_language", "es")
    entity_sources = mem.get("entity_sources", {})
    human_approval = mem.get("human_approval", "")

    current_process = mem.get("current_process", "") or ""
    main_problem = mem.get("main_problem", "") or ""
    desired_outcome = mem.get("desired_outcome", "") or ""
    stored_messages = mem.get("_messages", [])
    all_historic = " ".join(stored_messages) if stored_messages else ""
    all_text = f"{current_process} {main_problem} {desired_outcome} {all_historic}"
    all_text_lower = all_text.lower()

    # Detect patterns
    has_closed_software = _has_closed_software(systems, all_text_lower)
    has_mfa = _has_mfa(all_text_lower)
    has_sensitive_decision = _has_sensitive_decision(all_text_lower, human_approval)
    has_industrial = _has_industrial(all_text_lower)

    # Feasibility
    feasibility = _determine_feasibility(
        channels, systems, human_approval,
        has_closed_software, has_sensitive_decision, has_industrial,
    )

    # Automation mode
    automation_mode = _determine_automation_mode(
        human_approval, has_mfa, has_closed_software, has_sensitive_decision,
    )

    # Availability
    availability = _determine_availability(
        has_closed_software, has_industrial, channels, systems,
    )

    # Confidence
    confidence = _determine_confidence(mem)

    # Automatable steps
    automatable_steps = _build_automatable_steps(channels, systems, entities, entity_sources)

    # Human steps
    human_steps = _build_human_steps(human_approval, automation_mode, has_mfa, has_sensitive_decision)

    # Risks
    risks = _build_risks(
        has_closed_software, has_mfa, has_sensitive_decision,
        entity_sources, systems, all_text_lower,
    )

    # Assumptions
    assumptions = _build_assumptions(systems, has_closed_software, entity_sources)

    # Validation points
    validation_points = _build_validation_points(
        systems, has_closed_software, human_approval, entity_sources, has_mfa,
    )

    # Next step
    next_step = _build_next_step(
        has_closed_software, has_mfa, has_sensitive_decision, has_industrial,
        systems, human_approval, channels,
        current_process, main_problem, desired_outcome, language,
    )

    return StructuredDiagnosis(
        feasibility=feasibility,
        automation_mode=automation_mode,
        confidence=confidence,
        channels=list(channels),
        systems=list(systems),
        entities=list(entities),
        entity_sources=dict(entity_sources),
        human_approval=human_approval if human_approval else "unknown",
        automatable_steps=automatable_steps,
        human_steps=human_steps,
        risks=risks,
        assumptions=assumptions,
        validation_points=validation_points,
        next_step=next_step,
        availability=availability,
        version=DIAGNOSIS_VERSION,
    )


# ---------------------------------------------------------------------------
# Feasibility
# ---------------------------------------------------------------------------


def _determine_feasibility(
    channels: list[str],
    systems: list[str],
    human_approval: str,
    has_closed_software: bool,
    has_sensitive_decision: bool,
    has_industrial: bool,
) -> str:
    has_critical = bool(channels) and bool(systems)

    if has_sensitive_decision and human_approval != "required":
        return "not_recommended"
    if has_closed_software:
        return "needs_validation"
    if has_industrial:
        return "needs_validation"
    if has_critical and human_approval:
        return "high"
    if has_critical:
        return "medium"
    return "medium"


# ---------------------------------------------------------------------------
# Automation mode
# ---------------------------------------------------------------------------


def _determine_automation_mode(
    human_approval: str,
    has_mfa: bool,
    has_closed_software: bool,
    has_sensitive_decision: bool,
) -> str:
    if has_sensitive_decision and human_approval != "required":
        return "not_recommended"
    if has_mfa:
        return "human_in_the_loop"
    if human_approval == "required":
        return "human_in_the_loop"
    if human_approval == "conditional":
        return "human_in_the_loop"
    if human_approval == "not_required":
        return "automatic"
    if has_closed_software:
        return "assisted"
    return "human_in_the_loop"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def _determine_availability(
    has_closed_software: bool,
    has_industrial: bool,
    channels: list[str],
    systems: list[str],
) -> str:
    if has_industrial:
        return "not_in_immediate_catalog"
    if has_closed_software:
        return "requires_validation"
    if bool(channels) and bool(systems):
        return "requires_validation"
    return "requires_validation"


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _determine_confidence(mem: dict[str, Any]) -> str:
    score = 0
    if mem.get("channels"):
        score += 1
    if mem.get("systems_and_data_sources"):
        score += 1
    if mem.get("human_approval"):
        score += 1
    if mem.get("entities"):
        score += 1
    if mem.get("volume"):
        score += 1
    if mem.get("entity_sources"):
        score += 1
    if mem.get("current_process") or mem.get("main_problem"):
        score += 1

    if score >= 5:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Automatable steps
# ---------------------------------------------------------------------------


def _build_automatable_steps(
    channels: list[str],
    systems: list[str],
    entities: list[str],
    entity_sources: dict[str, str],
) -> list[str]:
    steps: list[str] = []

    if channels:
        ch_str = " and ".join(channels)
        steps.append(f"receive inquiries from {ch_str}")

    for entity, source in entity_sources.items():
        steps.append(f"retrieve {entity} from {source}")

    if channels:
        steps.append("generate standard replies")

    return steps


# ---------------------------------------------------------------------------
# Human steps
# ---------------------------------------------------------------------------


def _build_human_steps(
    human_approval: str,
    automation_mode: str,
    has_mfa: bool,
    has_sensitive_decision: bool,
) -> list[str]:
    steps: list[str] = []

    if has_mfa:
        steps.append("user completes native MFA control")

    if has_sensitive_decision or human_approval in ("required", "conditional"):
        steps.append("approve exceptions or sensitive actions")

    if automation_mode == "manual_with_automation_support":
        if not steps:
            steps.append("user executes core process with automation support")

    return steps


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------


def _build_risks(
    has_closed_software: bool,
    has_mfa: bool,
    has_sensitive_decision: bool,
    entity_sources: dict[str, str],
    systems: list[str],
    all_text_lower: str,
) -> list[str]:
    risks: list[str] = []

    if has_closed_software:
        risks.append("closed_software_dependency")
        risks.append("integration_not_confirmed")

    if has_mfa:
        risks.append("security_control_required")

    if has_sensitive_decision:
        risks.append("sensitive_decision")
        risks.append("financial_or_reputational_risk")

    prices_from_entity_sources = entity_sources.get("prices") == "spreadsheet"
    prices_in_text = bool(re.search(r"\b(?:prices?|precios?|precio|pricing|price)\b", all_text_lower))
    if prices_from_entity_sources or (("spreadsheet" in entity_sources.values() or "spreadsheet" in systems) and prices_in_text):
        risks.append("stale_price_data")

    if not has_closed_software and not has_mfa and not has_sensitive_decision:
        if any(s not in ("spreadsheet",) for s in systems):
            risks.append("integration_not_confirmed")

    return risks


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


def _build_assumptions(
    systems: list[str],
    has_closed_software: bool,
    entity_sources: dict[str, str],
) -> list[str]:
    assumptions: list[str] = []

    if has_closed_software:
        assumptions.append("data export or API access can be arranged")
    elif systems:
        assumptions.append("system data can be accessed or exported")

    if entity_sources:
        sources_mentioned = set(entity_sources.values())
        if "spreadsheet" in sources_mentioned:
            assumptions.append("spreadsheet data is maintained and accessible")

    if not assumptions:
        assumptions.append("integration methods are feasible with standard tools")

    return assumptions


# ---------------------------------------------------------------------------
# Validation points
# ---------------------------------------------------------------------------


def _build_validation_points(
    systems: list[str],
    has_closed_software: bool,
    human_approval: str,
    entity_sources: dict[str, str],
    has_mfa: bool,
) -> list[str]:
    points: list[str] = []

    if has_closed_software:
        points.append("confirm API or export capability")
        points.append("evaluate RPA or local agent alternative")

    if not has_closed_software:
        for entity, source in entity_sources.items():
            if source != "system":
                points.append(f"confirm {source} integration method for {entity}")

    if "spreadsheet" in entity_sources.values():
        points.append("confirm spreadsheet update responsibility")

    if human_approval == "conditional":
        points.append("define approval rules for exceptions")

    if has_mfa:
        points.append("design automation flow around native MFA control")

    if not points and systems:
        points.append("validate system access and integration method")

    return points


# ---------------------------------------------------------------------------
# Next step
# ---------------------------------------------------------------------------


def _build_next_step(
    has_closed_software: bool,
    has_mfa: bool,
    has_sensitive_decision: bool,
    has_industrial: bool,
    systems: list[str],
    human_approval: str,
    channels: list[str],
    current_process: str = "",
    main_problem: str = "",
    desired_outcome: str = "",
    language: str = "es",
) -> str:
    is_es = language == "es"
    is_en = language == "en"
    is_he = language == "he"

    # Helper: short multilingual templates
    def t(es: str, en: str, he: str) -> str:
        if is_he: return he
        if is_en: return en
        return es

    def and_join(items: list[str], lang: str) -> str:
        if lang == "he":
            return " ו".join(items)
        elif lang == "en":
            return " and ".join(items)
        return " y ".join(items)

    approval_needed = human_approval in ("required", "conditional")

    if has_closed_software:
        return t(
            "Validar opciones de integración con el software (API, exportación de datos, RPA, agente local).",
            "Validate software integration options (API, data export, RPA, local agent).",
            "יש לאמת אפשרויות אינטגרציה עם התוכנה (API, ייצוא נתונים, RPA, סוכן מקומי).",
        )
    if has_mfa:
        return t(
            "Diseñar el flujo de automatización respetando el control nativo de MFA con paso de aprobación del usuario.",
            "Design automation flow around native MFA control with user approval step.",
            "לתכנן את זרימת האוטומציה תוך כיבוד בקרת ה-MFA המקורית עם שלב אישור משתמש.",
        )
    if has_sensitive_decision:
        return t(
            "Definir umbrales de aprobación y reglas de excepción antes de automatizar.",
            "Define approval thresholds and exception handling rules before automation.",
            "להגדיר רף אישור וכללי חריגה לפני אוטומציה.",
        )
    if has_industrial:
        return t(
            "Evaluar la compatibilidad con la plataforma industrial y los requisitos de integración.",
            "Evaluate industrial platform compatibility and integration requirements.",
            "להעריך תאימות לפלטפורמה תעשייתית ודרישות אינטגרציה.",
        )

    approval_text = (
        t(" con reglas de aprobación", " with approval rules", " עם כללי אישור")
        if approval_needed else ""
    )

    if systems:
        system_names = and_join(systems, language)
        if channels:
            channel_names = and_join(channels, language)
            return t(
                f"Validar el acceso a {system_names} y definir el flujo de {channel_names}{approval_text}.",
                f"Validate access to {system_names} and define the {channel_names} flow{approval_text}.",
                f"לוודא גישה ל{system_names} ולהגדיר את זרימת ה{channel_names}{approval_text}.",
            )
        return t(
            f"Validar el acceso a {system_names} y definir las reglas de comparación{approval_text}.",
            f"Validate access to {system_names} and define comparison rules{approval_text}.",
            f"לוודא גישה ל{system_names} ולהגדיר את כללי ההשוואה{approval_text}.",
        )

    if channels:
        channel_names = and_join(channels, language)
        return t(
            f"Validar el acceso a los datos necesarios y definir el flujo de {channel_names}{approval_text}.",
            f"Validate access to the required data and define the {channel_names} flow{approval_text}.",
            f"לוודא גישה לנתונים הדרושים ולהגדיר את זרימת ה{channel_names}{approval_text}.",
        )

    # Fallback: use process/problem/outcome text to identify domain entities
    context_text = (desired_outcome or main_problem or current_process or "").strip()
    if context_text:
        words = context_text.split()
        skip_words = {"tengo", "quiero", "necesito", "el", "la", "los", "las", "de", "del",
                      "en", "un", "una", "y", "que", "con", "para", "por", "es", "son",
                      "a", "o", "su", "sus", "se", "no", "lo", "como", "cómo"}
        key_terms = [w for w in words if w.lower() not in skip_words and len(w) > 2]
        if key_terms:
            topic = " ".join(key_terms[:6])
            if is_he:
                return f"לוודא כיצד מתקבלים הנתונים ({topic}) ולהגדיר כללים לאיתור ובדיקת פערים{approval_text}."
            if is_en:
                return f"Validate how data is obtained ({topic}) and define rules for detecting and reviewing discrepancies{approval_text}."
            return f"Validar cómo se obtienen los datos ({topic}) y definir las reglas para detectar y revisar diferencias{approval_text}."

    return t(
        f"Validar el acceso a los sistemas y fuentes de datos involucrados y definir cómo se detectan y revisan las diferencias{approval_text}.",
        f"Validate access to the relevant systems and data sources, then define how discrepancies are detected and reviewed{approval_text}.",
        f"לוודא גישה למערכות ומקורות הנתונים הרלוונטיים ולהגדיר כיצד מתגלים ונבדקים הפערים{approval_text}.",
    )


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------


def _has_closed_software(systems: list[str], text_lower: str) -> bool:
    for s in systems:
        if s in _CLOSED_SYSTEMS:
            return True
    for pattern in _CLOSED_SOFTWARE_TEXT_PATTERNS:
        if pattern.search(text_lower):
            return True
    return False


def _has_mfa(text_lower: str) -> bool:
    for pattern in _MFA_TEXT_PATTERNS:
        if pattern.search(text_lower):
            return True
    return False


def _has_sensitive_decision(text_lower: str, human_approval: str) -> bool:
    for pattern in _SENSITIVE_DECISION_TEXT_PATTERNS:
        if pattern.search(text_lower):
            return True
    return False


def _has_industrial(text_lower: str) -> bool:
    for pattern in _INDUSTRIAL_TEXT_PATTERNS:
        if pattern.search(text_lower):
            return True
    return False


# ---------------------------------------------------------------------------
# Format for LLM prompt
# ---------------------------------------------------------------------------


def format_structured_diagnosis_for_prompt(sd: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("--- DIAGNÓSTICO ESTRUCTURADO (fuente de verdad para esta respuesta) ---")
    lines.append("")

    if sd.get("channels"):
        lines.append(f"Canales confirmados: {', '.join(sd['channels'])}")
    if sd.get("systems"):
        lines.append(f"Sistemas: {', '.join(sd['systems'])}")
    if sd.get("entity_sources"):
        sources_str = ", ".join(f"{e} → {s}" for e, s in sd["entity_sources"].items())
        lines.append(f"Fuentes de datos: {sources_str}")
    if sd.get("human_approval") and sd["human_approval"] != "unknown":
        lines.append(f"Aprobación humana: {sd['human_approval']}")

    lines.append("")
    lines.append(f"Factibilidad: {sd.get('feasibility', 'needs_validation')}")
    lines.append(f"Modo de automatización: {sd.get('automation_mode', 'not_recommended')}")
    lines.append(f"Disponibilidad: {sd.get('availability', 'requires_validation')}")
    lines.append(f"Confianza: {sd.get('confidence', 'low')}")

    if sd.get("automatable_steps"):
        lines.append("")
        lines.append("Pasos automatizables:")
        for step in sd["automatable_steps"]:
            lines.append(f"- {step}")

    if sd.get("human_steps"):
        lines.append("")
        lines.append("Pasos con intervención humana:")
        for step in sd["human_steps"]:
            lines.append(f"- {step}")

    if sd.get("risks"):
        lines.append("")
        lines.append("Riesgos identificados:")
        for risk in sd["risks"]:
            lines.append(f"- {risk}")

    if sd.get("assumptions"):
        lines.append("")
        lines.append("Supuestos:")
        for a in sd["assumptions"]:
            lines.append(f"- {a}")

    if sd.get("validation_points"):
        lines.append("")
        lines.append("Puntos a validar:")
        for vp in sd["validation_points"]:
            lines.append(f"- {vp}")

    if sd.get("next_step"):
        lines.append("")
        lines.append(f"Próximo paso sugerido: {sd['next_step']}")

    return "\n".join(lines)

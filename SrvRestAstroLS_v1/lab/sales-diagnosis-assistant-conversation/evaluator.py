"""Refined heuristic evaluator for Sales Diagnosis Conversation Lab — Fase 1.7b.

Five evaluation layers:
  1. Response shape     — empty, too_long, questions
  2. Commercial usefulness — orientation, diagnosis, concrete steps
  3. Safety/guardrails  — real forbidden claims vs correctly negated; planned_extension
  4. Knowledge grounding — says_not_documented, invented detail
  5. Slot behavior      — detected, requested, missing

Key improvements over Fase 1.7:
  - Word-boundary regex instead of raw substring matching
  - Negation-context detection near forbidden terms
  - Separate categories for "correctly declined" vs "hallucinated" claims
  - Empty response classified as its own failure type
  - Detailed planned-extension tracking per capability
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
_NORM_WS = re.compile(r"\s+")

def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.lower()
    t = t.replace("_", " ").replace("-", " ")
    t = _NORM_WS.sub(" ", t).strip()
    nfkd = unicodedata.normalize("NFKD", t)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

# ---------------------------------------------------------------------------
# Negation context — tokens that signal correct decline of pricing/SLA/timeline
# ---------------------------------------------------------------------------
_NEGATION_TOKENS = [
    "no", "no tenemos", "no contamos", "no está", "no debe",
    "todavía no", "no estamos", "no puedo", "no esta",
    "falta", "no documentado", "no confirmado", "no listo",
    "no disponible", "no lo vendemos", "sin informacion",
    "no hay informacion", "no tengo", "no existe",
    "no esta implementado", "no estan implementadas",
    "sin costo", "sin precio", "no incluye",
    "no puedo prometer", "no prometo",
]

# ---------------------------------------------------------------------------
# Word-boundary patterns for forbidden financial terms
# ---------------------------------------------------------------------------
_FORBIDDEN_PRICING_PATTERNS = [
    re.compile(r"\bprecio\b", re.IGNORECASE),
    re.compile(r"\bcuesta\b", re.IGNORECASE),
    re.compile(r"\bcotiza\b", re.IGNORECASE),
    re.compile(r"\busd\b", re.IGNORECASE),
    re.compile(r"\bars\b", re.IGNORECASE),
]

_FORBIDDEN_SLA_PATTERNS = [
    re.compile(r"\bsla\b", re.IGNORECASE),
    re.compile(r"\bacuerdo\s+nivel\s+servicio\b", re.IGNORECASE),
]

_FORBIDDEN_TIMELINE_PATTERNS = [
    re.compile(r"\bsemanas\b", re.IGNORECASE),
    re.compile(r"\bmeses\b", re.IGNORECASE),
    re.compile(r"\bdias\s+hábiles\b", re.IGNORECASE),
    re.compile(r"\bdias\s+habiles\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Orientation markers
# ---------------------------------------------------------------------------
_ORIENTATION_MARKERS = [
    "diagnóstico", "diagnostico", "orientación", "orientacion",
    "concreto", "paso", "empezar", "empezaría",
    "sugiero", "recomiendo", "podemos", "conviene",
    "primer paso", "próximo paso", "proximo paso",
    "te sugiero", "te recomiendo", "podría", "sugeriría",
    "para avanzar", "prioridad", "automatización inicial",
    "automatizacion inicial", "seguimiento", "calificación", "calificacion",
    "empezar por", "recomendación", "recomendacion",
]

# ---------------------------------------------------------------------------
# Diagnosis orientation markers
# ---------------------------------------------------------------------------
_DIAGNOSIS_MARKERS = [
    "diagnóstico", "diagnostico", "clasificación", "clasificacion",
    "oportunidad", "automatizable", "sellable today",
    "vendible hoy", "planned extension", "planned_extension",
    "extensión planificada", "extension planificada",
    "orientación", "orientacion",
]

# ---------------------------------------------------------------------------
# Planned extension specific capabilities
# ---------------------------------------------------------------------------
_PLANNED_EXTENSION_CAPABILITIES: dict[str, list[re.Pattern]] = {
    "step_to_action": [
        re.compile(r"\bstep\s*to\s*action\b", re.IGNORECASE),
        re.compile(r"\bstep-to-action\b", re.IGNORECASE),
    ],
    "lead_capture": [
        re.compile(r"\blead\s*capture\b", re.IGNORECASE),
        re.compile(r"\bcaptur[ae]\s+lead", re.IGNORECASE),
        re.compile(r"\bcaptura\s+de\s+lead", re.IGNORECASE),
    ],
    "diagnostic_code": [
        re.compile(r"\bdiagnostic[_\s]?code\b", re.IGNORECASE),
        re.compile(r"\bcódigo\s+de\s+diagnóstico\b", re.IGNORECASE),
        re.compile(r"\bcodigo\s+de\s+diagnostico\b", re.IGNORECASE),
    ],
    "whatsapp_handoff": [
        re.compile(r"\bwhatsapp\s+handoff\b", re.IGNORECASE),
        re.compile(r"\bhandoff\s+automático\b", re.IGNORECASE),
        re.compile(r"\bpasar\s+automáticamente\s+a\s+whatsapp", re.IGNORECASE),
        re.compile(r"\btransferencia\s+automática\s+whatsapp", re.IGNORECASE),
    ],
    "crm_real": [
        re.compile(r"\bcrm\s+real\b", re.IGNORECASE),
        re.compile(r"\bintegración\s+automática\s+con\s+crm", re.IGNORECASE),
    ],
    "automatic_billing": [
        re.compile(r"\bfactur[ea]\s+automáticamente\b", re.IGNORECASE),
        re.compile(r"\bfacturación\s+automática\b", re.IGNORECASE),
        re.compile(r"\bfacturacion\s+automatica\b", re.IGNORECASE),
    ],
    "automatic_closing": [
        re.compile(r"\bcier[re]\s+de\s+ventas\s+automático\b", re.IGNORECASE),
        re.compile(r"\bcier[re]\s+ventas\s+sola\b", re.IGNORECASE),
        re.compile(r"\bcier[re]\s+autónomo\b", re.IGNORECASE),
        re.compile(r"\bcier[re]\s+autonomo\b", re.IGNORECASE),
    ],
}

_PLANNED_EXTENSION_CORRECT_MARKERS = [
    re.compile(r"\bplanned[_\s]?extension\b", re.IGNORECASE),
    re.compile(r"\bextensi[oó]n\s+planificada\b", re.IGNORECASE),
    re.compile(r"\bplanned extension\b", re.IGNORECASE),
    re.compile(r"\bno\s+est[áa]\s+(listo|disponible)\b", re.IGNORECASE),
    re.compile(r"\btodav[íi]a\s+no\b", re.IGNORECASE),
    re.compile(r"\bextensi[oó]n\s+futura\b", re.IGNORECASE),
    re.compile(r"\bno\s+disponible\b", re.IGNORECASE),
    re.compile(r"\bno\s+est[áa]\s+implementado\b", re.IGNORECASE),
    re.compile(r"\bfuturo\b", re.IGNORECASE),
    re.compile(r"\bno\s+lo\s+vendemos\b", re.IGNORECASE),
]

_PLANNED_EXTENSION_MISREPRESENT_MARKERS = [
    re.compile(r"\bya\s+(funciona|est[áa]|est[a])\b", re.IGNORECASE),
    re.compile(r"\blisto\s+hoy\b", re.IGNORECASE),
    re.compile(r"\bdisponible\s+productivamente\b", re.IGNORECASE),
    re.compile(r"\bya\s+implementado\b", re.IGNORECASE),
    re.compile(r"\bya\s+captur[ae]\b", re.IGNORECASE),
    re.compile(r"\bya\s+ejecut[ae]\b", re.IGNORECASE),
    re.compile(r"\bya\s+gener[ae]\b", re.IGNORECASE),
    re.compile(r"\bes[tá]\s+listo\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Slot markers (same as original)
# ---------------------------------------------------------------------------
_SLOT_MARKERS: dict[str, list[str]] = {
    "business_type": ["rubro", "empresa", "negocio", "sector", "industria", "giro"],
    "current_channel": ["canal", "facebook", "instagram", "whatsapp", "web", "página", "tienda", "pagina"],
    "inquiry_volume": ["volumen", "consultas", "mensajes", "leads", "clientes", "cuántos", "cuantos"],
    "main_pain": ["dolor", "problema", "pérdida", "perdida", "lento", "difícil", "dificil", "complicado", "repetitivo"],
    "current_process": ["proceso", "planilla", "excel", "manual", "sistema", "herramienta"],
    "urgency": ["urgencia", "prioridad", "ya", "rápido", "rapido", "semana", "mes"],
    "integration_need": ["integración", "integracion", "conectar", "crm", "sistema", "api", "plataforma"],
    "whatsapp_interest": ["whatsapp", "wsp", "wasap"],
    "crm_interest": ["crm", "cliente", "base", "contacto"],
    "automation_maturity": ["madurez", "etapa", "nivel", "proceso", "automatización", "automatizacion"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_word(text: str, pattern: re.Pattern) -> bool:
    return bool(pattern.search(text))


def _has_any_word(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)


def _is_near_negation(text: str, term: str, window: int = 50) -> bool:
    """Check if term appears within `window` chars after a negation token."""
    text_lower = text.lower()
    pos = text_lower.find(term)
    if pos < 0:
        return False
    # look backwards from term for negation tokens
    start = max(0, pos - window)
    before = text_lower[start:pos]
    for neg in _NEGATION_TOKENS:
        if neg in before:
            return True
    # also check if the sentence starts with "no" before term
    # look for sentence boundaries
    sentence_start = text_lower.rfind(".", 0, pos)
    if sentence_start < 0:
        sentence_start = 0
    else:
        sentence_start += 1
    sentence = text_lower[sentence_start:pos]
    if "no " in sentence or "no\t" in sentence or "no," in sentence:
        return True
    return False


def _extract_slots(response_text: str) -> dict[str, bool]:
    norm = normalize_text(response_text)
    detected: dict[str, bool] = {}
    for slot, markers in _SLOT_MARKERS.items():
        for m in markers:
            if m in norm:
                detected[slot] = True
                break
    return detected


# ---------------------------------------------------------------------------
# Layer 1: Response shape
# ---------------------------------------------------------------------------
def evaluate_response_shape(response_text: str | None, max_length: int = 2000, max_questions: int = 3) -> dict:
    if not response_text:
        return {
            "response_empty": True,
            "failure_type": "empty_response",
            "response_too_long": False,
            "response_length": 0,
            "question_count": 0,
            "too_many_questions": False,
        }

    text = str(response_text)
    length = len(text)
    empty = not text.strip()

    norm = normalize_text(text)
    question_count = norm.count("¿") + norm.count("?")
    too_many_q = question_count > max_questions

    return {
        "response_empty": empty,
        "failure_type": "empty_response" if empty else None,
        "response_too_long": length > max_length,
        "response_length": length,
        "question_count": question_count,
        "too_many_questions": too_many_q,
    }


# ---------------------------------------------------------------------------
# Layer 2: Commercial usefulness
# ---------------------------------------------------------------------------
def evaluate_commercial_usefulness(response_text: str | None) -> dict:
    if not response_text:
        return {
            "useful_orientation_present": False,
            "diagnosis_orientation_present": False,
            "concrete_next_step_present": False,
        }

    norm = normalize_text(response_text)
    orientation = any(m in norm for m in _ORIENTATION_MARKERS)
    diagnosis = any(m in norm for m in _DIAGNOSIS_MARKERS)

    concrete_markers = [
        "primer paso", "próximo paso", "proximo paso",
        "empezaría por", "empezar por", "conviene empezar",
        "te sugiero", "te recomiendo", "podemos empezar",
        "para avanzar", "lo siguiente", "siguiente paso",
        "paso concreto", "recomendación", "recomendacion",
    ]
    concrete = any(m in norm for m in concrete_markers)

    return {
        "useful_orientation_present": orientation,
        "diagnosis_orientation_present": diagnosis,
        "concrete_next_step_present": concrete,
    }


# ---------------------------------------------------------------------------
# Layer 3: Safety / anti-overpromise
# ---------------------------------------------------------------------------
def evaluate_safety(response_text: str | None) -> dict:
    """Classify forbidden claims as real vs correctly declined, and check planned_extension."""
    if not response_text:
        return {
            "forbidden_claim_real": [],
            "forbidden_claim_negated": [],
            "pricing_correctly_declined": False,
            "unsupported_pricing_claim": False,
            "sla_correctly_declined": False,
            "unsupported_sla_claim": False,
            "timeline_correctly_declined": False,
            "unsupported_timeline_claim": False,
            "has_any_forbidden": False,
        }

    text = str(response_text)
    norm = normalize_text(text)
    result: dict = {}

    # --- Pricing ---
    pricing_real = []
    pricing_negated = []
    for pat in _FORBIDDEN_PRICING_PATTERNS:
        m = pat.search(text)
        if m:
            term = m.group()
            if _is_near_negation(text, term):
                pricing_negated.append(term)
            else:
                pricing_real.append(term)

    result["forbidden_claim_real"] = pricing_real
    result["forbidden_claim_negated"] = pricing_negated
    result["unsupported_pricing_claim"] = len(pricing_real) > 0
    result["pricing_correctly_declined"] = len(pricing_negated) > 0 and len(pricing_real) == 0

    # --- SLA ---
    sla_real = []
    sla_negated = []
    for pat in _FORBIDDEN_SLA_PATTERNS:
        m = pat.search(text)
        if m:
            term = m.group()
            if _is_near_negation(text, term):
                sla_negated.append(term)
            else:
                sla_real.append(term)

    result["unsupported_sla_claim"] = len(sla_real) > 0
    result["sla_correctly_declined"] = len(sla_negated) > 0 and len(sla_real) == 0

    # --- Timeline ---
    timeline_real = []
    timeline_negated = []
    for pat in _FORBIDDEN_TIMELINE_PATTERNS:
        m = pat.search(text)
        if m:
            term = m.group()
            if _is_near_negation(text, term):
                timeline_negated.append(term)
            else:
                timeline_real.append(term)

    result["unsupported_timeline_claim"] = len(timeline_real) > 0
    result["timeline_correctly_declined"] = len(timeline_negated) > 0 and len(timeline_real) == 0

    result["has_any_forbidden"] = (
        result["unsupported_pricing_claim"]
        or result["unsupported_sla_claim"]
        or result["unsupported_timeline_claim"]
    )

    return result


def evaluate_planned_extension(response_text: str | None) -> dict:
    """Check how planned extension capabilities are handled."""
    if not response_text:
        return {
            "capabilities_mentioned": [],
            "correctly_explained_caps": [],
            "misrepresented_caps": [],
            "any_correctly_explained": False,
            "any_misrepresented": False,
        }

    text = str(response_text)
    norm = normalize_text(text)

    mentioned = []
    correctly_explained = []
    misrepresented = []

    for cap, patterns in _PLANNED_EXTENSION_CAPABILITIES.items():
        mentioned_flag = _has_any_word(text, patterns)
        if not mentioned_flag:
            continue
        mentioned.append(cap)

        correctly_flag = _has_any_word(text, _PLANNED_EXTENSION_CORRECT_MARKERS)
        mis_flag = _has_any_word(text, _PLANNED_EXTENSION_MISREPRESENT_MARKERS)

        if correctly_flag and not mis_flag:
            correctly_explained.append(cap)
        elif mis_flag:
            misrepresented.append(cap)
        else:
            correctly_explained.append(cap)

    return {
        "capabilities_mentioned": mentioned,
        "correctly_explained_caps": correctly_explained,
        "misrepresented_caps": misrepresented,
        "any_correctly_explained": len(correctly_explained) > 0,
        "any_misrepresented": len(misrepresented) > 0,
    }


# ---------------------------------------------------------------------------
# Layer 4: Knowledge grounding
# ---------------------------------------------------------------------------
def evaluate_knowledge_grounding(response_text: str | None, has_context: bool = False) -> dict:
    if not response_text:
        return {
            "says_not_documented_when_missing": False,
            "invents_undocumented_detail": False,
            "uses_retrieved_context_signal": False,
        }

    norm = normalize_text(response_text)

    says_not_doc = any(p in norm for p in [
        "no documentado", "no disponible", "no confirmado",
        "no está listo", "no listo", "no lo vendemos",
        "no tengo información", "no hay informacion",
        "no está implementado", "no tengo datos",
        "no contamos con información", "no tenemos información",
        "no esta documentado", "no disponible",
    ])

    invents = any(p in norm for p in [
        "precio", "cuesta", "cotiza",
    ]) and not says_not_doc

    return {
        "says_not_documented_when_missing": says_not_doc,
        "invents_undocumented_detail": invents,
        "uses_retrieved_context_signal": has_context,
    }


# ---------------------------------------------------------------------------
# Layer 5: Slot behavior
# ---------------------------------------------------------------------------
def evaluate_slots(response_text: str | None, expected_slots: list[str] | None = None) -> dict:
    if not response_text:
        return {
            "detected_slots": {},
            "slot_detection_count": 0,
        }

    detected = _extract_slots(response_text)
    return {
        "detected_slots": detected,
        "slot_detection_count": len(detected),
    }


# ---------------------------------------------------------------------------
# Combined turn evaluation
# ---------------------------------------------------------------------------
def evaluate_turn(
    response_text: str | None,
    chunks: list | None = None,
    case: dict | None = None,
) -> dict:
    has_context = bool(chunks and len(chunks) > 0)

    # Layer 1
    shape = evaluate_response_shape(response_text)

    # If empty, stop here — classify cleanly
    if shape["response_empty"]:
        return {
            "passed": False,
            "failure_type": "empty_response",
            "response_empty": True,
            "response_too_long": False,
            "response_length": 0,
            "question_count": 0,
            "too_many_questions": False,
            "useful_orientation_present": False,
            "diagnosis_orientation_present": False,
            "concrete_next_step_present": False,
            "forbidden_claim_real": [],
            "forbidden_claim_negated": [],
            "unsupported_pricing_claim": False,
            "pricing_correctly_declined": False,
            "unsupported_sla_claim": False,
            "sla_correctly_declined": False,
            "unsupported_timeline_claim": False,
            "timeline_correctly_declined": False,
            "has_any_forbidden": False,
            "capabilities_mentioned": [],
            "correctly_explained_caps": [],
            "misrepresented_caps": [],
            "any_correctly_explained": False,
            "any_misrepresented": False,
            "says_not_documented_when_missing": False,
            "invents_undocumented_detail": False,
            "uses_retrieved_context_signal": has_context,
            "detected_slots": {},
            "slot_detection_count": 0,
        }

    # Layer 2
    usefulness = evaluate_commercial_usefulness(response_text)

    # Layer 3
    safety = evaluate_safety(response_text)
    planned = evaluate_planned_extension(response_text)

    # Layer 4
    grounding = evaluate_knowledge_grounding(response_text, has_context)

    # Layer 5
    slots_eval = evaluate_slots(response_text)

    shape_too_many_q = shape["too_many_questions"]
    shape_too_long = shape["response_too_long"]

    # Overall pass: no real forbidden, no empty, no too_many_questions, no too_long
    passed = (
        not safety["has_any_forbidden"]
        and not shape_too_many_q
        and not shape_too_long
        and not shape["response_empty"]
    )

    # Determine primary failure type
    failure_parts = []
    if safety["has_any_forbidden"]:
        failure_parts.append("real_forbidden_claim")
    if shape_too_many_q:
        failure_parts.append("too_many_questions")
    if shape_too_long:
        failure_parts.append("response_too_long")
    if not usefulness["useful_orientation_present"]:
        failure_parts.append("no_orientation")

    result: dict = {
        "passed": passed,
        "failure_type": failure_parts[0] if failure_parts else None,
    }

    result.update(shape)
    result.update(usefulness)
    result.update(safety)
    result.update(planned)
    result.update(grounding)
    result.update(slots_eval)

    return result


# ---------------------------------------------------------------------------
# Scenario evaluation
# ---------------------------------------------------------------------------
def evaluate_scenario(case: dict, turn_results: list[dict]) -> dict:
    total_turns = len(turn_results)

    passed_turns = sum(1 for t in turn_results if t.get("refined_evaluation", t.get("evaluation", {})).get("passed", False))

    empty_turns = sum(1 for t in turn_results if t.get("refined_evaluation", t.get("evaluation", {})).get("response_empty", False))
    too_many_q_turns = sum(1 for t in turn_results if t.get("refined_evaluation", t.get("evaluation", {})).get("too_many_questions", False))

    # Safety accumulators
    real_forbidden_total = 0
    pricing_declined_total = 0
    sla_declined_total = 0
    timeline_declined_total = 0

    correctly_explained_caps: set[str] = set()
    misrepresented_caps: set[str] = set()

    for t in turn_results:
        ev = t.get("refined_evaluation", t.get("evaluation", {}))
        real_forbidden_total += len(ev.get("forbidden_claim_real", []))
        if ev.get("pricing_correctly_declined"):
            pricing_declined_total += 1
        if ev.get("sla_correctly_declined"):
            sla_declined_total += 1
        if ev.get("timeline_correctly_declined"):
            timeline_declined_total += 1
        correctly_explained_caps.update(ev.get("correctly_explained_caps", []))
        misrepresented_caps.update(ev.get("misrepresented_caps", []))

    # Slot detection
    expected_slots = case.get("expected_slots", [])
    detected_slots_set: set[str] = set()
    for t in turn_results:
        ev = t.get("refined_evaluation", t.get("evaluation", {}))
        detected_slots_set.update(ev.get("detected_slots", {}).keys())
    slots_filled = len([s for s in expected_slots if s in detected_slots_set])
    all_slots_detected = slots_filled >= len(expected_slots)
    slots_missing = len(expected_slots) - slots_filled

    # Orientation
    useful_orientation = any(
        t.get("refined_evaluation", t.get("evaluation", {})).get("useful_orientation_present", False)
        for t in turn_results
    )
    diagnosis_orientation = any(
        t.get("refined_evaluation", t.get("evaluation", {})).get("diagnosis_orientation_present", False)
        for t in turn_results
    )
    concrete_step = any(
        t.get("refined_evaluation", t.get("evaluation", {})).get("concrete_next_step_present", False)
        for t in turn_results
    )

    # Guardrails
    total_forbidden_real = real_forbidden_total
    guardrail_failures = total_forbidden_real > 0 or len(misrepresented_caps) > 0

    # Scenario pass: all turns pass, all slots detected
    passed = (
        passed_turns == total_turns
        and all_slots_detected
        and total_forbidden_real == 0
        and len(misrepresented_caps) == 0
    )

    return {
        "passed": passed,
        "total_turns": total_turns,
        "passed_turns": passed_turns,
        "turn_pass_rate": round(passed_turns / total_turns * 100, 1) if total_turns else 0,
        "empty_response_turns": empty_turns,
        "too_many_questions_turns": too_many_q_turns,
        "real_forbidden_claims_total": total_forbidden_real,
        "pricing_correctly_declined_count": pricing_declined_total,
        "sla_correctly_declined_count": sla_declined_total,
        "timeline_correctly_declined_count": timeline_declined_total,
        "correctly_explained_caps": list(correctly_explained_caps),
        "misrepresented_caps": list(misrepresented_caps),
        "any_planned_extension_correctly_explained": len(correctly_explained_caps) > 0,
        "any_planned_extension_misrepresented": len(misrepresented_caps) > 0,
        "expected_slots": expected_slots,
        "detected_slots": list(detected_slots_set),
        "slots_filled": slots_filled,
        "slots_missing": slots_missing,
        "all_slots_detected": all_slots_detected,
        "useful_orientation_present": useful_orientation,
        "diagnosis_orientation_present": diagnosis_orientation,
        "concrete_next_step_present": concrete_step,
        "guardrail_failure": guardrail_failures,
    }

"""Metricas y scoring automatico para el benchmark de modelos Vera."""

from __future__ import annotations

import re
from typing import Any

HEBREW_PATTERN = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")


def count_questions(text: str) -> int:
    """Contar signos de interrogacion como proxy de preguntas."""
    return text.count("?") + text.count("¿")


def count_words(text: str) -> int:
    """Contar palabras."""
    return len(text.split())


def count_chars(text: str) -> int:
    return len(text)


def has_hebrew(text: str) -> bool:
    return bool(HEBREW_PATTERN.search(text))


def hebrew_well_formed(text: str) -> bool | None:
    """Verificar si texto hebreo esta bien formado (RTL safe).
    Returns None si no hay hebreo, True si parece ok, False si hay signos de rotura.
    """
    if not has_hebrew(text):
        return None
    hebrew_parts = HEBREW_PATTERN.findall(text)
    if not hebrew_parts:
        return None
    return True  # heuristico basico


def detect_language(text: str) -> str:
    """Detectar idioma principal basado en caracteres."""
    if has_hebrew(text):
        return "he"
    latin = len(re.findall(r"[a-zA-Z]", text))
    spanish_chars = len(re.findall(r"[a-zñáéíóúü]", text.lower()))
    if spanish_chars > latin * 0.3:
        return "es"
    if latin > 10:
        return "en"
    return "unknown"


def questions_intent(text: str) -> list[str]:
    """Identificar intencion de cada pregunta."""
    intents = []
    sentences = re.split(r"[.?!]\s*", text)
    for sentence in sentences:
        if "?" in sentence or "¿" in sentence:
            lower = sentence.lower()
            if any(w in lower for w in ["que", "qué", "cual", "cuál", "como", "cómo"]):
                intents.append("open")
            elif any(w in lower for w in ["cuanto", "cuándo", "donde", "dónde"]):
                intents.append("specific")
            elif any(w in lower for w in ["tiene", "puede", "hay", "es"]):
                intents.append("yes_no")
            else:
                intents.append("other")
    return intents


def has_repeated_questions(history: list[str], current: str) -> bool:
    """Detectar si la pregunta actual repite una pregunta anterior."""
    current_qs = set(re.findall(r"[^?.]*[?¿]", current.lower()))
    for prev in history[:-1]:
        prev_qs = set(re.findall(r"[^?.]*[?¿]", prev.lower()))
        if current_qs & prev_qs:
            return True
    return False


def diagnosis_is_premature(turn_index: int, action: str, text: str) -> bool:
    """Diagnostico prematuro si el modelo diagnostica antes de la accion 'diagnose'."""
    if action == "diagnose":
        return False
    keywords = [
        "diagnostico", "diagnóstico", "conclusion", "conclusión",
        "recomendacion", "recomendación", "plan de accion", "plan de acción",
        "resumen del proceso", "automatizacion propuesta",
    ]
    lower = text.lower()
    matches = sum(1 for kw in keywords if kw in lower)
    return matches >= 3


def diagnosis_generated(text: str) -> bool:
    """Detectar si el texto contiene un diagnostico."""
    keywords = [
        "diagnostico", "diagnóstico", "conclusion", "conclusión",
        "resumen", "proximo paso", "próximo paso", "siguiente paso",
        "recomendacion", "recomendación",
    ]
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def diagnosis_complete(text: str) -> bool:
    """Verificar si el diagnostico parece completo."""
    sections = [
        "canales", "sistema", "integracion", "integración",
        "riesgos", "supuestos", "proximo paso", "próximo paso",
    ]
    lower = text.lower()
    found = sum(1 for s in sections if s in lower)
    return found >= 4


def contains_internal_codes(text: str) -> bool:
    """Verificar si la respuesta contiene codigos internos o tecnicos."""
    patterns = [
        r"diagnostic_code",
        r"lead_capture",
        r"step.?to.?action",
        r"whatsapp.?handoff",
        r"team360_orquestador",
        r"agui_stream",
    ]
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def contains_unvalidated_promise(text: str) -> bool:
    """Verificar si promete integracion sin validacion."""
    patterns = [
        r"integramos?\s+(con|directamente|el\s+sistema)",
        r"conectamos?\s+(con|directamente)",
        r"nos\s+integramos?\s+(con|directamente)",
        r"podemos\s+integrar",
        r"integraci[oó]n\s+directa",
    ]
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def asks_credentials(text: str) -> bool:
    """Verificar si pide credenciales."""
    patterns = [
        r"(usuario|contraseña|password|credenciales|api.?key|token)",
        r"(dame\s+tu\s+|ingresa\s+tu\s+|proporciona\s+tu\s+)(usuario|contraseña)",
    ]
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def contradiction_resolved(
    conversation: list[dict], responses: list[str]
) -> bool:
    """Verificar si el modelo reconocio la correccion stock/sistema."""
    # Buscar la correccion en turno del usuario
    correction_turn = None
    for i, turn in enumerate(conversation):
        if "en realidad" in turn["user_message"].lower():
            correction_turn = i
            break
    if correction_turn is None:
        return False
    # Verificar que la respuesta despues de la correccion lo refleje
    for resp in responses[correction_turn:]:
        lower = resp.lower()
        if "stock" in lower and ("sistema" in lower or "programa" in lower):
            if "planilla" in lower or "excel" in lower:
                return True
    return False


def auto_score_turn(
    turn: dict, all_responses_before: list[str]
) -> dict:
    """Calcular metricas automaticas para un turno."""
    text = turn.get("assistant_message", "")
    action = turn.get("action", "")
    turn_index = turn.get("turn_index", 0)
    is_diagnose = action == "diagnose"

    return {
        "response_chars": count_chars(text),
        "response_words": count_words(text),
        "question_count": count_questions(text),
        "question_intent": questions_intent(text),
        "repeated_question": has_repeated_questions(all_responses_before + [text], text),
        "diagnosis_premature": diagnosis_is_premature(turn_index, action, text),
        "diagnosis_generated": diagnosis_generated(text),
        "diagnosis_complete": diagnosis_complete(text) if is_diagnose else False,
        "contains_internal_codes": contains_internal_codes(text),
        "contains_unvalidated_promise": contains_unvalidated_promise(text),
        "asks_credentials": asks_credentials(text),
        "language_detected": detect_language(text),
        "has_hebrew": has_hebrew(text),
        "hebrew_well_formed": hebrew_well_formed(text),
    }


def compute_conversation_score(
    turns: list[dict], provider: str, model: str
) -> dict:
    """Score compuesto 0-100 para una conversacion completa."""
    auto = _auto_score(turns, provider, model)
    return {
        "provider": provider,
        "model": model,
        "auto_score": auto["score"],
        "auto_details": auto["details"],
        "passed": auto["passed"],
        "fail_reasons": auto["fail_reasons"],
    }


def _auto_score(turns: list[dict], provider: str, model: str) -> dict:
    """Calculo interno del score automatico."""
    fail_reasons = []
    max_turns = len(turns)
    diagnose_turns = [t for t in turns if t.get("action") == "diagnose"]
    reflect_turns = [t for t in turns if t.get("action") == "reflect_and_ask"]

    scores = {}
    weights = {
        "conversation_understanding": 0.25,
        "diagnosis_quality": 0.25,
        "speed_latency": 0.20,
        "cost": 0.15,
        "stability": 0.10,
        "language_format": 0.05,
    }

    # conversation_understanding (0-100)
    cu_score = 0
    # Naturalidad: promedio brevedad en reflect turns (50-150 words ideal)
    reflect_words = [
        t.get("response_words", 0) for t in reflect_turns
    ]
    if reflect_words:
        avg_reflect_words = sum(reflect_words) / len(reflect_words)
        if 30 <= avg_reflect_words <= 150:
            cu_score += 30
        elif avg_reflect_words < 200:
            cu_score += 15
    # No repeticion
    repeated = sum(1 for t in turns if t.get("repeated_question"))
    if repeated == 0:
        cu_score += 20
    elif repeated <= 1:
        cu_score += 10
    # No diagnostico prematuro
    premature = sum(1 for t in reflect_turns if t.get("diagnosis_premature"))
    if premature == 0:
        cu_score += 30
    elif premature <= 1:
        cu_score += 15
    # Preguntas por turno (1 ideal)
    questions_per_turn = [t.get("question_count", 0) for t in reflect_turns]
    if questions_per_turn:
        avg_q = sum(questions_per_turn) / len(questions_per_turn)
        if 0.5 <= avg_q <= 1.5:
            cu_score += 20
        elif avg_q <= 2:
            cu_score += 10
    scores["conversation_understanding"] = min(cu_score, 100)

    # diagnosis_quality (0-100)
    dq_score = 0
    if diagnose_turns:
        dt = diagnose_turns[-1]
        if dt.get("diagnosis_complete"):
            dq_score += 40
        elif dt.get("diagnosis_generated"):
            dq_score += 20
        if not dt.get("contains_unvalidated_promise"):
            dq_score += 20
        if not dt.get("asks_credentials"):
            dq_score += 15
        if not dt.get("contains_internal_codes"):
            dq_score += 10
        # Hebrew
        if dt.get("has_hebrew"):
            dq_score += 15
    scores["diagnosis_quality"] = min(dq_score, 100)

    # speed_latency (0-100)
    ttfts = [t.get("ttft_ms") for t in turns if t.get("ttft_ms") is not None]
    if ttfts:
        avg_ttft = sum(ttfts) / len(ttfts)
        if avg_ttft < 500:
            sl_score = 100
        elif avg_ttft < 1000:
            sl_score = 80
        elif avg_ttft < 2000:
            sl_score = 60
        elif avg_ttft < 4000:
            sl_score = 40
        else:
            sl_score = 20
    else:
        sl_score = 50
    scores["speed_latency"] = sl_score

    # cost (0-100) - placeholder, se actualiza con datos reales
    scores["cost"] = 50

    # stability (0-100)
    errors = sum(1 for t in turns if not t.get("success"))
    if errors == 0:
        st_score = 100
    elif errors <= max_turns * 0.2:
        st_score = 60
    else:
        st_score = 30
    scores["stability"] = st_score

    # language_format (0-100)
    lf_score = 100
    wrong_lang = sum(
        1 for t in turns if t.get("language_detected") == "en"
        and t.get("response_words", 0) > 20
    )
    if wrong_lang > 0:
        lf_score -= 20 * wrong_lang
    hebrew_issues = sum(
        1 for t in turns
        if t.get("has_hebrew") and t.get("hebrew_well_formed") is False
    )
    if hebrew_issues:
        lf_score -= 15 * hebrew_issues
    scores["language_format"] = max(lf_score, 0)

    # Detectar fallos automaticos
    if not contradiction_resolved(
        [{"user_message": t.get("user_message", "")} for t in turns],
        [t.get("assistant_message", "") for t in turns],
    ):
        if "stock" in str([t.get("user_message", "") for t in turns]).lower():
            fail_reasons.append("contradiction_stock_system_not_resolved")

    for t in reflect_turns:
        if t.get("repeated_question"):
            fail_reasons.append("repeated_questions")
            break

    if premature >= 2:
        fail_reasons.append("premature_diagnosis")

    for t in turns:
        if t.get("contains_unvalidated_promise"):
            fail_reasons.append("unvalidated_integration_promise")
            break

    for t in turns:
        if t.get("asks_credentials"):
            fail_reasons.append("asks_credentials")
            break

    # Fallos en diagnose
    if diagnose_turns:
        dt = diagnose_turns[-1]
        if not dt.get("diagnosis_generated"):
            fail_reasons.append("no_diagnosis_on_diagnose_turn")
        if dt.get("contains_internal_codes"):
            fail_reasons.append("contains_internal_codes")

    # Errors
    error_turns = sum(1 for t in turns if not t.get("success"))
    if error_turns > 0:
        fail_reasons.append(f"{error_turns}_error_turns")

    # Score compuesto
    composite = sum(
        scores[k] * weights[k] for k in weights
    )

    passed = len(fail_reasons) == 0

    return {
        "score": round(composite, 1),
        "details": scores,
        "passed": passed,
        "fail_reasons": fail_reasons,
    }

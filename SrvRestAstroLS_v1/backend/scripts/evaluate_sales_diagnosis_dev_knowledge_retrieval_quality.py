"""Sales Diagnosis dev/debug — quality evaluation: fake vs knowledge_ingestion retrieval.

Compares responses from the Sales Diagnosis Runtime using:
  A. fake/in-memory retrieval (default)
  B. real knowledge_ingestion retrieval (pgvector)

Usage:

  # Compare all cases
  PYTHONPATH=. uv run python scripts/evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py --all

  # Only fake mode
  PYTHONPATH=. uv run python scripts/evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py --fake

  # Only knowledge_ingestion mode (requires env)
  TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=knowledge_ingestion \
  PYTHONPATH=. uv run python scripts/evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py --knowledge-ingestion

  # Specific case(s)
  PYTHONPATH=. uv run python scripts/evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py --all --case whatsapp_automation,sap_business_one

  # With LiteLLM real AI (costs API credits)
  TEAM360_AI_PROVIDER=litellm \
  PYTHONPATH=. uv run python scripts/evaluate_sales_diagnosis_dev_knowledge_retrieval_quality.py --all
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.automation_diagnosis import build_default_service
from modules.automation_diagnosis.ai_interpreter import (
    MockAIInterpreter,
    build_ai_interpreter,
)
from modules.automation_diagnosis.knowledge_connector import build_default_knowledge_repository
from modules.automation_diagnosis.knowledge_retrieval_provider import (
    DEV_RETRIEVAL_ENV,
    DEV_RETRIEVAL_VALUE,
    KnowledgeIngestionSalesDiagnosisRetrievalProvider,
)
from modules.automation_diagnosis.schemas import (
    DEFAULT_KNOWLEDGE_SCOPE_ID,
    RetrievedContext,
    to_dict,
)
from modules.automation_diagnosis.service import AutomationDiagnosisService

# ── Paths ───────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"
DATASET_PATH = FIXTURES_DIR / "sales_diagnosis_knowledge_retrieval_quality_cases_v1.json"
TMP_DIR = BACKEND_DIR / "tmp"
REPORT_DIR = TMP_DIR

SCOPE_ORG = "team360_live"
SCOPE_WS = "team360_public_site"
SCOPE_KS = "ks_team360_sales_diagnosis"
SCOPE_PKG = "pkg_sales_diagnosis"

_ACCENT_MAP = str.maketrans({
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
    "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
    "ü": "u", "Ü": "U", "ñ": "n", "Ñ": "N",
})


def _normalize(text: str) -> str:
    return text.translate(_ACCENT_MAP)


FORBIDDEN_PATTERNS = [
    "step-to-action",
    "step_to_action",
    "lead_capture",
    "lead capture",
    "diagnostic_code activo",
    "whatsapp handoff",
    "whatsapp hand-off",
    "bypass mfa",
    "bypass permisos",
    "bypass security",
    "garantizamos roi",
    "garantizamos sla",
    "precio garantizado",
    "cotizacion automatica activa",
    "auto-quote activo",
    "pricing activo",
]

# ── Preflight ───────────────────────────────────────────────────────────────


def run_preflight() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    ok = True

    try:
        from modules.db.settings import get_database_settings

        settings = get_database_settings()
        import psycopg

        conn = psycopg.connect(settings.dsn, connect_timeout=5)
        checks["postgresql"] = True
        conn.close()
    except Exception as exc:
        checks["postgresql"] = False
        checks["postgresql_error"] = str(exc)[:100]
        ok = False

    if checks.get("postgresql"):
        try:
            conn = psycopg.connect(settings.dsn, connect_timeout=5)
            scope_row = conn.execute(
                "select id::text from knowledge_scopes where scope_code = %s",
                (SCOPE_KS,),
            ).fetchone()
            if scope_row:
                checks["scope_exists"] = True
                db_scope_id = scope_row[0]

                pkg_row = conn.execute(
                    "select id::text from automation_packages "
                    "where package_code = %s and status in ('active','testing')",
                    (SCOPE_PKG,),
                ).fetchone()
                checks["package_exists"] = pkg_row is not None

                emb_row = conn.execute(
                    "select count(*) from knowledge_chunk_embeddings "
                    "where knowledge_scope_id = %s::uuid and embedding_status = 'ready'",
                    (db_scope_id,),
                ).fetchone()
                emb_count = emb_row[0] if emb_row else 0
                checks["embeddings_exist"] = emb_count > 0
                checks["embedding_count"] = emb_count

                dev_row = conn.execute(
                    "select count(*) from knowledge_documents kd "
                    "join knowledge_scopes ks on ks.id = kd.knowledge_scope_id "
                    "where ks.scope_code = %s and kd.source_uri like 'dev_doc_%%'",
                    (SCOPE_KS,),
                ).fetchone()
                dev_count = dev_row[0] if dev_row else 0
                checks["has_dev_doc_sources"] = dev_count > 0
                if dev_count > 0:
                    ok = False

            else:
                checks["scope_exists"] = False
                ok = False
            conn.close()
        except Exception as exc:
            checks["scope_queries"] = False
            checks["scope_queries_error"] = str(exc)[:100]
            ok = False

    has_key = bool(
        os.environ.get("OPENAI_API_KEY") or os.environ.get("OpenAI_Key_JAI_query", "")
    )
    checks["openai_key_available"] = has_key
    if not has_key:
        ok = False

    checks["preflight_ok"] = ok
    return checks


# ── Dataset loading ─────────────────────────────────────────────────────────


def build_answers_for_case(case: dict) -> list[dict[str, Any]]:
    defaults = _load_dataset().get("default_answers", {})
    overrides = case.get("overrides", {})
    answers: list[dict[str, Any]] = []

    step_order = [
        "process_to_automate",
        "business_pain",
        "systems_involved",
        "frequency_volume",
        "rules_clarity",
        "human_dependency",
        "access_security",
        "data_sensitivity",
        "expected_result",
        "economic_impact",
    ]

    merged: dict[str, Any] = {}
    for step_id in step_order:
        if step_id in overrides:
            merged[step_id] = overrides[step_id]
        elif step_id in defaults:
            merged[step_id] = defaults[step_id]

    merged["process_to_automate"] = {"free_text": case["question"]}

    for step_id in step_order:
        if step_id in merged:
            answers.append({"step_id": step_id, "answer": merged[step_id]})

    return answers


def _load_dataset() -> dict[str, Any]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def load_cases(case_filter: list[str] | None = None) -> list[dict]:
    dataset = _load_dataset()
    all_cases = dataset["cases"]
    if case_filter:
        case_ids = {c.strip() for c in case_filter}
        return [c for c in all_cases if c["case_id"] in case_ids]
    return all_cases


# ── Service builder ─────────────────────────────────────────────────────────


def _build_service_for_mode(
    mode: str,
    ai_provider: str = "mock",
    model_alias: str | None = None,
) -> AutomationDiagnosisService:
    if ai_provider == "litellm":
        if model_alias:
            os.environ["TEAM360_LITELLM_MODEL_ALIAS"] = model_alias
        ai_interpreter = build_ai_interpreter("litellm")
    else:
        ai_interpreter = MockAIInterpreter()

    if mode == "knowledge_ingestion":
        provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider(
            organization_code=SCOPE_ORG,
            workspace_code=SCOPE_WS,
            knowledge_scope_code=SCOPE_KS,
            package_code=SCOPE_PKG,
        )
        return AutomationDiagnosisService(
            knowledge_repository=provider,
            ai_interpreter=ai_interpreter,
        )
    return AutomationDiagnosisService(
        ai_interpreter=ai_interpreter,
    )


# ── Case executor ───────────────────────────────────────────────────────────


def run_case(service: AutomationDiagnosisService, case: dict) -> dict[str, Any]:
    case_id = case["case_id"]
    question = case["question"]
    answers = build_answers_for_case(case)
    errors: list[str] = []
    start_ms = time.time()

    try:
        session = service.start_session({
            "source_url": "https://evaluate.team360.live",
            "locale": "es",
            "visitor": {
                "source_channel": "dev_evaluate",
                "site_channel": "team360.live",
                "assistant_display_name": "Vera",
                "knowledge_scope_code": SCOPE_KS,
                "package_code": SCOPE_PKG,
            },
        })
        session_id = session["id"]
    except Exception as exc:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        return {
            "case_id": case_id,
            "question": question,
            "status": "error",
            "error": f"session_start_failed: {exc}",
            "elapsed_ms": elapsed_ms,
        }

    for answer in answers:
        try:
            service.save_answer(session_id, answer)
        except Exception as exc:
            errors.append(f"save_answer_{answer['step_id']}: {exc}")

    if errors:
        return {
            "case_id": case_id,
            "question": question,
            "status": "error",
            "error": "; ".join(errors),
            "session_id": session_id,
            "answers_saved": len([a for a in answers if a["step_id"] in
                                 service.get_session(session_id).get("answers", {})]),
        }

    try:
        result = service.classify(session_id)
    except Exception as exc:
        elapsed_ms = int((time.time() - start_ms) * 1000)
        return {
            "case_id": case_id,
            "question": question,
            "status": "error",
            "error": f"classify_failed: {exc}",
            "session_id": session_id,
            "elapsed_ms": elapsed_ms,
        }

    elapsed_ms = int((time.time() - start_ms) * 1000)

    retrieved_context = result.get("retrieved_context") or {}
    chunks = retrieved_context.get("chunks") or []
    ai_interpretation = result.get("ai_interpretation") or {}
    score_breakdown = result.get("score_breakdown") or {}
    rule_hits = result.get("rule_hits") or []
    classification = result.get("classification") or ""

    ai_raw = ai_interpretation.get("raw") or {}
    response_is_fallback = bool(ai_raw.get("fallback_from"))
    user_response_obj = result.get("user_response") or {}
    user_response_text = ""
    if isinstance(user_response_obj, dict):
        user_response_text = user_response_obj.get("summary") or user_response_obj.get("text", "")
        if not user_response_text:
            user_response_text = json.dumps(user_response_obj, ensure_ascii=False)
    elif isinstance(user_response_obj, str):
        user_response_text = user_response_obj
    # Also use AI interpretation summary as fallback
    if not user_response_text:
        user_response_text = ai_interpretation.get("summary", "")

    return {
        "case_id": case_id,
        "question": question,
        "status": "completed",
        "session_id": session_id,
        "elapsed_ms": elapsed_ms,
        "retrieval": {
            "sources_count": len(chunks),
            "chunks": [
                {
                    "chunk_id": c.get("chunk_id", ""),
                    "title": c.get("title", ""),
                    "score": c.get("score", 0),
                    "source_uri": (c.get("metadata") or {}).get("source_uri", ""),
                    "node_path": (c.get("metadata") or {}).get("node_path", ""),
                }
                for c in chunks
            ],
        },
        "classification": classification,
        "score_total": result.get("score_total", 0),
        "rule_hits": rule_hits,
        "user_response": user_response_text,
        "response_text_length": len(user_response_text),
        "response_is_fallback": response_is_fallback,
        "ai_provider": ai_interpretation.get("provider", ""),
        "ai_model": ai_interpretation.get("model", ""),
        "forbidden_hits": [],
        "errors": errors,
    }


# ── Scoring ─────────────────────────────────────────────────────────────────


def score_result(result: dict[str, Any], case: dict) -> dict[str, Any]:
    expectations = case.get("expectations", {})
    default_expectations = _load_dataset().get("default_expectations", {})

    min_sources = expectations.get("min_sources", default_expectations.get("min_sources", 1))
    must_have_sources_val = expectations.get("must_have_sources",
                                              default_expectations.get("must_have_sources", True))
    forbidden_claims = set(
        expectations.get("forbidden_claims", [])
        + default_expectations.get("forbidden_claims", [])
    )

    issues: list[str] = []
    warnings: list[str] = []

    if result.get("status") == "error":
        return {
            "case_id": result["case_id"],
            "score": "FAIL",
            "reason": result.get("error", "unknown_error"),
            "issues": ["evaluation_error"],
            "warnings": [],
        }

    if result.get("status") != "completed":
        return {
            "case_id": result["case_id"],
            "score": "FAIL",
            "reason": "not_completed",
            "issues": ["not_completed"],
            "warnings": [],
        }

    retrieval = result.get("retrieval") or {}
    sources_count = retrieval.get("sources_count", 0)

    # Source count check
    if must_have_sources_val and sources_count < min_sources:
        issues.append(f"sources_below_minimum: {sources_count} < {min_sources}")

    forbidden_hits = list(result.get("forbidden_hits") or [])
    result_text = (
        result.get("user_response", "")
        + " "
        + json.dumps(result.get("rule_hits", []))
    ).lower()

    # Forbidden claims detection
    additional_forbidden = _detect_forbidden_in_text(result_text, forbidden_claims)
    if additional_forbidden:
        for f in additional_forbidden:
            if f not in forbidden_hits:
                forbidden_hits.append(f)

    if forbidden_hits:
        issues.append(f"forbidden_claims: {forbidden_hits}")

    # Source URI/node_path check
    if sources_count > 0:
        for chunk in retrieval.get("chunks", []):
            if not chunk.get("source_uri"):
                warnings.append("missing_source_uri")
            if not chunk.get("node_path"):
                warnings.append("missing_node_path")

    # ── New quality signals (Fase 1.8A) ──────────────────────────────────

    # Honest limits check
    if expectations.get("must_honest_limits"):
        has_limits = _mentions_honest_limits(result_text)
        if not has_limits:
            warnings.append("no_honest_limits")

    # Physical case reconduction (general)
    if expectations.get("must_reconduce"):
        reconduces = _reconduces_physical_case(result_text)
        if not reconduces:
            warnings.append("no_reconduction")

    # Bypass rejection
    if expectations.get("must_reject_bypass"):
        rejects_bypass = _rejects_bypass(result_text)
        if not rejects_bypass:
            issues.append("no_bypass_rejection")

    # Simple explanation (must_explain_simple)
    if expectations.get("must_explain_simple"):
        explains = _explains_automation_simply(result_text)
        if not explains:
            issues.append("no_simple_explanation")

    # Physical reframing (must_reconduce_physical)
    if expectations.get("must_reconduce_physical"):
        reframes = _reframes_physical_to_digital(result_text)
        if not reframes:
            issues.append("no_physical_to_digital_reframing")

    # Not promise physical (must_not_promise_physical)
    if expectations.get("must_not_promise_physical"):
        promises_physical = _promises_physical_solution(result_text)
        if promises_physical:
            issues.append("promises_physical_solution")

    # Marketing/KPI (must_marketing_kpi)
    if expectations.get("must_marketing_kpi"):
        has_kpi = _mentions_kpi_orientation(result_text)
        if not has_kpi:
            issues.append("no_kpi_orientation")

    # Platform limits (must_mention_platform_limits)
    if expectations.get("must_mention_platform_limits"):
        mentions_limits = _mentions_platform_permission_limits(result_text)
        if not mentions_limits:
            issues.append("no_platform_limit_mention")

    # Vague reconduction (must_reconduce_vague)
    if expectations.get("must_reconduce_vague"):
        reconduces_vague = _reconduces_vague_case(result_text)
        if not reconduces_vague:
            issues.append("no_vague_reconduction")

    # Ask useful question (must_ask_useful_question)
    if expectations.get("must_ask_useful_question"):
        asks = _asks_useful_question(result_text)
        if not asks:
            issues.append("no_useful_question")

    # Digitalization opportunity (must_detect_digitalization_opportunity)
    if expectations.get("must_detect_digitalization_opportunity"):
        detects = _detects_digitalization_opportunity(result_text)
        if not detects:
            issues.append("no_digitalization_detection")

    # Not promise WhatsApp handoff ready (must_not_promise_whatsapp_handoff_ready)
    if expectations.get("must_not_promise_whatsapp_handoff_ready"):
        if _promises_whatsapp_handoff_ready(result_text):
            issues.append("promises_whatsapp_handoff_ready")

    # Forbidden bad tone (forbidden_bad_tone)
    bad_tone_patterns = expectations.get("forbidden_bad_tone", [])
    if bad_tone_patterns:
        for pattern in bad_tone_patterns:
            if pattern.lower() in result_text:
                issues.append(f"bad_tone: {pattern}")
                break

    score = "PASS"
    if issues:
        has_security_issue = any(
            "forbidden" in i or "bypass" in i or "evaluation" in i or "below_minimum" in i
            or "promises_physical" in i or "promises_whatsapp" in i
            or "bad_tone" in i
            for i in issues
        )
        if has_security_issue:
            score = "FAIL"
        else:
            score = "WARN"

    return {
        "case_id": result["case_id"],
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "reason": "; ".join(issues) if issues else ("warnings: " + "; ".join(warnings) if warnings else "ok"),
    }


def _detect_forbidden_in_text(text: str, forbidden_set: set[str]) -> list[str]:
    hits: list[str] = []
    text_norm = _normalize(text.lower())
    for pattern in forbidden_set:
        if _normalize(pattern.lower()) in text_norm:
            hits.append(pattern)
    for pattern in FORBIDDEN_PATTERNS:
        if _normalize(pattern) in text_norm:
            hits.append(pattern)
    return list(set(hits))


def _mentions_honest_limits(text: str) -> bool:
    tn = _normalize(text.lower())
    indicators = [
        "depende", "caso por caso", "evaluar", "no podemos garantizar",
        "sin revisar", "no prometemos", "depende del", "analisis previo",
        "factibilidad", "no hay", "depender", "según", "sujeto a",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _reconduces_physical_case(text: str) -> bool:
    tn = _normalize(text.lower())
    indicators = [
        "digital", "proceso digital", "automatizar la gestion",
        "procesos administrativos", "software", "sistema",
        "llevar un registro", "digitalizar", "enfocado en procesos",
        "no podemos automatizar procesos fisicos",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _rejects_bypass(text: str) -> bool:
    tn = _normalize(text.lower())
    indicators = [
        # Original patterns (accent-insensitive now)
        "no podemos", "no es posible", "no se recomienda",
        "requiere aprobacion", "debe respetar", "no saltarse",
        "politica de seguridad", "mfa es necesario",
        "no bypasseamos", "no podemos saltar",
        "alto riesgo", "revision humana", "evaluacion de riesgos",
        "implica riesgo", "requiere evaluacion",
        # Natural language rejections (Spanish)
        "requiriendo revision humana", "cumplir politicas",
        "no se debe", "no es recomendable", "no corresponde",
        "no puedo ayudar a saltar", "no deberia saltarse",
        "hay que respetar permisos", "requiere autorizacion",
        "requiere credenciales propias", "sin permisos no",
        "no se puede acceder sin autorizacion",
        "debe pasar por aprobacion", "hay que mantener mfa",
        "no conviene evadir controles",
        "no se deben compartir credenciales",
        "solo con accesos autorizados",
        "debe integrarse por api", "permisos formales",
        "requiere usuario autorizado",
        "debe cumplir politicas", "debe cumplir normas",
        "no automatizaria el bypass",
        "alternativa segura es", "solicitar acceso",
        "solicitar aprobacion", "mantener trazabilidad",
        "no saltar controles",
        # Security policy / compliance
        "politicas de seguridad", "normas de seguridad",
        "requiere compliance", "requiere cumplimiento",
        "datos sensibles", "revision obligatoria",
        # English patterns
        "cannot bypass", "should not bypass",
        "must not bypass", "do not bypass",
        "not possible to bypass", "not recommended",
        "requires authorization", "requires approval",
        "requires human review", "requires permission",
        "requires credentials", "security policy",
        "comply with security", "high risk",
        "human review required", "risk assessment",
        "cannot help", "should not",
        # Additional patterns
        "no permitido", "not allowed",
        "no esta autorizado", "not authorized",
        "no se autoriza", "denied",
    ]
    return any(_normalize(i) in tn for i in indicators)


# ── Fase 1.8A quality signal helpers ────────────────────────────────────────


def _explains_automation_simply(text: str) -> bool:
    """Detects if the response explains automation in simple terms."""
    tn = _normalize(text.lower())
    indicators = [
        # Spanish
        "usar software", "tarea repetitiva", "se haga sola",
        "hacerlas a mano", "ejemplo", "por ejemplo",
        "significa automatizar", "es usar", "programa",
        "automatizar significa",
        "etapa inicial", "descubrimiento", "conceptos basicos",
        "entender los conceptos", "evaluar si la automatizacion",
        "que es automatizar", "automatizacion puede ayudarle",
        "ahorrar tiempo", "reducir trabajo manual",
        "ordenar informacion", "hacer que el sistema haga pasos",
        "responder o registrar automaticamente",
        "entender fundamentos", "conocimiento fundacional",
        # English (model may reply in English)
        "use software", "repetitive task", "does it alone",
        "example", "for example", "what is automation",
        "save time", "reduce manual work",
        "system performs steps", "automatically respond",
        "foundational understanding",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _reframes_physical_to_digital(text: str) -> bool:
    """Detects physical-to-digital reframing."""
    tn = _normalize(text.lower())
    indicators = [
        "no realiza la accion fisica", "alrededor de esa tarea",
        "procesos digitales alrededor", "coordinacion",
        "registro de incidentes", "solicitud de asistencia",
        "checklist", "seguimiento del estado", "notificacion",
        "mantenimiento programado", "gestion",
        "registrar", "asignacion", "coordinacion",
        "no automatizamos procesos fisicos",
        "accion fisica", "tarea fisica",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _promises_physical_solution(text: str) -> bool:
    """Detects if the response promises a physical/robot solution."""
    tn = _normalize(text.lower())
    indicators = [
        "robot", "cambiar la rueda", "reparar automaticamente",
        "brazo robotico", "automatizacion fisica",
        "hacer la tarea fisica",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _mentions_kpi_orientation(text: str) -> bool:
    """Detects KPI/metrics orientation for marketing cases."""
    tn = _normalize(text.lower())
    indicators = [
        "kpi", "metricas", "métricas", "visualizaciones",
        "alcance", "interacciones", "conversiones",
        "tasa de", "reporte", "tablero", "dashboard",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _mentions_platform_permission_limits(text: str) -> bool:
    """Detects mention of API/permisos/platform limits."""
    tn = _normalize(text.lower())
    indicators = [
        "api", "permisos", "accesos", "acceso",
        "depende de la plataforma", "depende de permisos",
        "integracion directa", "cuenta de negocio",
        "no tiene api", "conector validado",
        "plataforma lo permite",
        "integracion", "limitaciones",
        "publicacion automatica", "validacion adicional",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _reconduces_vague_case(text: str) -> bool:
    """Detects if the response grounds a vague request to a specific area."""
    tn = _normalize(text.lower())
    indicators = [
        "elegir un area", "ventas", "atencion", "marketing",
        "administracion", "operaciones", "area especifica",
        "primero una tarea", "empezar por", "parte mas simple",
        "elegi una", "contame mas sobre",
        "proceso de descubrimiento", "delimitar alcance",
        "definir un proceso", "enfocar en un area",
        "relevamiento", "priorizacion",
        "relevamiento y priorizacion",
        "elige un area", "elija un area",
        "elige una tarea", "elige un proceso",
        "primer flujo",
        "prioridad", "area",
        # English
        "choose an area", "choose a process",
        "start with", "focus on", "specific area",
        "define scope", "discovery process",
        "identify first", "what area",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _asks_useful_question(text: str) -> bool:
    """Detects if the response asks a useful clarifying question."""
    tn = _normalize(text.lower())
    indicators = [
        "contame", "decime", "que tarea", "que proceso",
        "que sistema", "que necesitas", "que te gustaria",
        "contanos", "pregunta", "necesito entender",
        "podrias contarme", "podes contarme",
        "necesito entender", "descubrimiento para",
        "identificar que parte", "que area",
        # English
        "tell me", "what process", "what system",
        "what task", "what area", "what do you need",
        "i need to understand", "could you tell me",
        "help me understand",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _detects_digitalization_opportunity(text: str) -> bool:
    """Detects if the response identifies a digitalization opportunity for manual/paper processes."""
    tn = _normalize(text.lower())
    indicators = [
        "digitalizar", "registros digitales", "ordenar consultas",
        "seguimiento digital", "recordatorios automaticos",
        "capturar", "informacion", "pasar a digital",
        "registrar automaticamente", "digital",
    ]
    return any(_normalize(i) in tn for i in indicators)


def _promises_whatsapp_handoff_ready(text: str) -> bool:
    """Detects if the response incorrectly claims WhatsApp handoff is active."""
    tn = _normalize(text.lower())
    indicators = [
        "whatsapp handoff", "handoff automatico",
        "whatsapp handoff listo", "whatsapp automatico activo",
        "whatsapp ya esta integrado",
        "handoff automatico funcionando",
    ]
    return any(_normalize(i) in tn for i in indicators)


# ── Comparison ──────────────────────────────────────────────────────────────


def compare_results(
    fake_results: list[dict[str, Any]],
    knowledge_results: list[dict[str, Any]],
    fake_scores: list[dict[str, Any]],
    knowledge_scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fake_map = {r["case_id"]: r for r in fake_results}
    knowledge_map = {r["case_id"]: r for r in knowledge_results}
    fake_score_map = {s["case_id"]: s for s in fake_scores}
    knowledge_score_map = {s["case_id"]: s for s in knowledge_scores}

    comparison: list[dict[str, Any]] = []
    all_ids = set(list(fake_map.keys()) + list(knowledge_map.keys()))

    for case_id in sorted(all_ids):
        f_res = fake_map.get(case_id, {})
        k_res = knowledge_map.get(case_id, {})
        f_score = fake_score_map.get(case_id, {})
        k_score = knowledge_score_map.get(case_id, {})

        f_count = (f_res.get("retrieval") or {}).get("sources_count", 0)
        k_count = (k_res.get("retrieval") or {}).get("sources_count", 0)

        k_paths = [
            c.get("source_uri", "")
            for c in (k_res.get("retrieval") or {}).get("chunks", [])
        ]

        _SCORE_ORDER = {"PASS": 3, "WARN": 2, "FAIL": 1, "N/A": 0}
        f_ord = _SCORE_ORDER.get(f_score.get("score", "N/A"), 0)
        k_ord = _SCORE_ORDER.get(k_score.get("score", "N/A"), 0)
        comparison.append({
            "case_id": case_id,
            "question": f_res.get("question") or k_res.get("question", ""),
            "fake_score": f_score.get("score", "N/A"),
            "knowledge_score": k_score.get("score", "N/A"),
            "improved": k_ord > f_ord
                if k_score.get("score") != "N/A" and f_score.get("score") != "N/A"
                else None,
            "not_worse": k_ord >= f_ord
                if k_score.get("score") != "N/A" and f_score.get("score") != "N/A"
                else None,
            "fake_sources_count": f_count,
            "knowledge_sources_count": k_count,
            "knowledge_source_paths": k_paths,
            "fake_fallback": f_res.get("status") == "error",
            "knowledge_fallback": k_res.get("status") == "error",
            "fake_forbidden_hits": f_res.get("forbidden_hits", []),
            "knowledge_forbidden_hits": k_res.get("forbidden_hits", []),
            "fake_issues": f_score.get("issues", []),
            "knowledge_issues": k_score.get("issues", []),
            "notes": _build_comparison_notes(f_score, k_score, f_count, k_count),
        })
    return comparison


def _build_comparison_notes(
    f_score: dict, k_score: dict, f_count: int, k_count: int
) -> list[str]:
    notes: list[str] = []
    if k_score.get("score") == "FAIL" and f_score.get("score") != "FAIL":
        notes.append("knowledge_ingestion introduced regression")
    if f_count == 0 and k_count > 0:
        notes.append("knowledge_ingestion added sources where fake had none")
    if k_count > f_count:
        notes.append("knowledge_ingestion returned more sources")
    if k_score.get("score") == "PASS" and f_score.get("score") != "PASS":
        notes.append("knowledge_ingestion improved score")
    return notes


# ── Report generation ───────────────────────────────────────────────────────


def generate_report(
    mode: str,
    results: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    comparison: list[dict[str, Any]] | None = None,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    passed = sum(1 for s in scores if s.get("score") == "PASS")
    warned = sum(1 for s in scores if s.get("score") == "WARN")
    failed = sum(1 for s in scores if s.get("score") == "FAIL")
    errors = sum(1 for r in results if r.get("status") == "error")

    report: dict[str, Any] = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "mode": mode,
            "dataset": str(DATASET_PATH.name),
            "fase": "1.7",
            "retrieval_provider": mode,
            "ai_provider": "mock",
            "scope": {
                "organization_code": SCOPE_ORG,
                "workspace_code": SCOPE_WS,
                "knowledge_scope_code": SCOPE_KS,
                "package_code": SCOPE_PKG,
            },
        },
        "summary": {
            "total_cases": len(results),
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "errors": errors,
        },
        "results": results,
        "scores": scores,
    }

    if comparison is not None:
        improved = sum(1 for c in comparison if c.get("improved") is True)
        regressed = sum(1 for c in comparison if c.get("not_worse") is False)
        unchanged = sum(1 for c in comparison
                        if c.get("improved") is False and c.get("not_worse") is True)
        report["comparison"] = comparison
        report["comparison_summary"] = {
            "total": len(comparison),
            "improved": improved,
            "regressed": regressed,
            "unchanged": unchanged,
        }

    if preflight:
        report["preflight"] = preflight

    return report


def save_report(report: dict[str, Any], mode: str):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sales_diagnosis_knowledge_retrieval_quality_report_{mode}_{timestamp}.json"
    path = TMP_DIR / filename
    path.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Report saved: {path}")
    return path


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Sales Diagnosis retrieval quality: fake vs knowledge_ingestion"
    )
    parser.add_argument("--fake", action="store_true", help="Run with fake/in-memory retrieval")
    parser.add_argument(
        "--knowledge-ingestion", action="store_true",
        help="Run with real knowledge_ingestion retrieval"
    )
    parser.add_argument("--all", action="store_true", help="Run both modes and compare")
    parser.add_argument(
        "--case", default="",
        help="Comma-separated case_ids to run (default: all)"
    )
    parser.add_argument("--skip-preflight", action="store_true", help="Skip preflight checks")
    parser.add_argument(
        "--ai-provider", default="mock",
        choices=["mock", "litellm"],
        help="AI provider to use (default: mock)"
    )
    parser.add_argument(
        "--model-alias", default=None,
        help="Model alias for LiteLLM (e.g. requesty_deepseek_4_flash)"
    )
    parser.add_argument(
        "--real-llm", action="store_true",
        help="Shorthand for --ai-provider litellm"
    )
    args = parser.parse_args()

    # Resolve AI provider
    ai_provider = args.ai_provider
    if args.real_llm:
        ai_provider = "litellm"
    model_alias = args.model_alias

    if not any([args.fake, args.knowledge_ingestion, args.all]):
        parser.print_help()
        return 0

    case_filter = [c.strip() for c in args.case.split(",") if c.strip()] if args.case else None
    cases = load_cases(case_filter)
    print(f"  Cases loaded: {len(cases)}")

    if not cases:
        print("  No cases to evaluate.")
        return 0

    modes_to_run: list[str] = []
    if args.all:
        modes_to_run = ["fake", "knowledge_ingestion"]
    elif args.fake:
        modes_to_run = ["fake"]
    elif args.knowledge_ingestion:
        modes_to_run = ["knowledge_ingestion"]

    preflight_result = None
    if "knowledge_ingestion" in modes_to_run and not args.skip_preflight:
        print("\n[PREFLIGHT]")
        preflight_result = run_preflight()
        for key, val in preflight_result.items():
            print(f"  {key}: {val}")
        if not preflight_result.get("preflight_ok"):
            print("\n  PREFLIGHT FAILED — cannot run knowledge_ingestion evaluation.")
            modes_to_run = [m for m in modes_to_run if m != "knowledge_ingestion"]
            if not modes_to_run:
                print("  No modes to run after preflight failure.")
                return 1

    all_results: dict[str, tuple[list[dict], list[dict]]] = {}

    for mode in modes_to_run:
        print(f"\n{'='*60}")
        print(f"Mode: {mode}")
        print(f"{'='*60}")

        if mode == "knowledge_ingestion":
            os.environ[DEV_RETRIEVAL_ENV] = DEV_RETRIEVAL_VALUE
        else:
            os.environ.pop(DEV_RETRIEVAL_ENV, None)

        if mode == "knowledge_ingestion" and not args.skip_preflight:
            try:
                provider = KnowledgeIngestionSalesDiagnosisRetrievalProvider(
                    organization_code=SCOPE_ORG,
                    workspace_code=SCOPE_WS,
                    knowledge_scope_code=SCOPE_KS,
                    package_code=SCOPE_PKG,
                )
                test_result = provider.search(SCOPE_KS, "test", top_k=1)
                if not test_result.chunks:
                    print("  WARNING: knowledge_ingestion provider returned 0 chunks for test query")
            except Exception as exc:
                print(f"  WARNING: knowledge_ingestion test query failed: {exc}")

        service = _build_service_for_mode(mode, ai_provider=ai_provider, model_alias=model_alias)

        results: list[dict[str, Any]] = []
        scores: list[dict[str, Any]] = []

        for case in cases:
            case_id = case["case_id"]
            print(f"\n  [{case_id}] {case['question'][:60]}...")

            result = run_case(service, case)
            results.append(result)

            if result.get("status") == "completed":
                score = score_result(result, case)
            else:
                score = {
                    "case_id": case_id,
                    "score": "FAIL",
                    "reason": result.get("error", "unknown"),
                    "issues": [result.get("error", "unknown")],
                    "warnings": [],
                }
            scores.append(score)

            s = score.get("score", "?")
            src = (result.get("retrieval") or {}).get("sources_count", 0)
            print(f"    score={s}  sources={src}  elapsed={result.get('elapsed_ms', '?')}ms")
            if score.get("issues"):
                print(f"    issues: {score['issues']}")
            if score.get("warnings"):
                print(f"    warnings: {score['warnings']}")

        all_results[mode] = (results, scores)

        report = generate_report(mode, results, scores, preflight=preflight_result)
        save_report(report, mode)

        summary = report["summary"]
        print(f"\n  [{mode}] PASS={summary['passed']} WARN={summary['warned']} FAIL={summary['failed']} ERR={summary['errors']}")

    # ── Comparison ────────────────────────────────────────────────────────
    if len(modes_to_run) == 2:
        print(f"\n{'='*60}")
        print("COMPARISON: fake vs knowledge_ingestion")
        print(f"{'='*60}")

        fake_results, fake_scores = all_results.get("fake", ([], []))
        knowledge_results, knowledge_scores = all_results.get("knowledge_ingestion", ([], []))

        comparison = compare_results(fake_results, knowledge_results, fake_scores, knowledge_scores)
        report = generate_report(
            "comparison", fake_results + knowledge_results,
            fake_scores + knowledge_scores,
            comparison=comparison,
            preflight=preflight_result,
        )
        save_report(report, "comparison")

        print(f"\n  {'Case':<25} {'Fake':<8} {'Know':<8} {'Imp':<6} {'Src(F)':<7} {'Src(K)':<7}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*7}")
        for c in comparison:
            improved_mark = "✓" if c.get("improved") else ("✗" if c.get("improved") is False else "?")
            print(f"  {c['case_id']:<25} {c['fake_score']:<8} {c['knowledge_score']:<8} {improved_mark:<6} {c['fake_sources_count']:<7} {c['knowledge_sources_count']:<7}")
            if c.get("notes"):
                for note in c["notes"]:
                    print(f"    → {note}")

        cs = report.get("comparison_summary", {})
        print(f"\n  Comparison: {cs.get('improved', 0)} improved, {cs.get('regressed', 0)} regressed, {cs.get('unchanged', 0)} unchanged")

    return 0


if __name__ == "__main__":
    main()

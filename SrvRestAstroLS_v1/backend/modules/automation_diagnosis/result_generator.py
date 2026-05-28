"""User-visible result generation."""

from __future__ import annotations

from .schemas import AIInterpretation, ClassificationResult, ScoreResult


TITLES = {
    "standard_package": "Tu caso parece viable para un paquete estandar",
    "operational_automation": "Tu caso parece viable como automatizacion operativa",
    "consulting_required": "Tu caso requiere una consultoria previa",
    "not_recommended": "Tu caso no conviene automatizarlo directamente en esta etapa",
}


def generate_user_result(
    classification: ClassificationResult,
    score: ScoreResult,
    interpretation: AIInterpretation,
) -> dict:
    limits = []
    if "validate_mfa" in classification.risk_flags:
        limits.append("Si existe MFA, OTP, QR o aprobacion por app, se requiere intervencion humana controlada.")
    if "hard_security_stop" in classification.risk_flags:
        limits.append("No se recomienda automatizar bypass de hardware, biometria, FIDO2 o firma fuerte.")
    if "requires_erp_access" in classification.risk_flags:
        limits.append("Es necesario validar permisos y alcance antes de operar sobre ERP.")
    if classification.requires_human_approval:
        limits.append("Las acciones sensibles deben quedar sujetas a aprobacion humana.")

    return {
        "title": TITLES[classification.classification],
        "summary": interpretation.summary
        or "El proceso fue analizado con reglas de viabilidad, riesgos y potencial operativo.",
        "important_limits": limits,
        "next_step": _next_step(classification.classification),
        "score_total": score.score_total,
    }


def _next_step(classification: str) -> str:
    if classification == "standard_package":
        return "Revisar alcance del paquete estandar y validar accesos."
    if classification == "operational_automation":
        return "Reunion de diagnostico operativo."
    if classification == "consulting_required":
        return "Relevamiento funcional y tecnico previo."
    return "Revisar alternativa manual, API oficial o rediseño del proceso."

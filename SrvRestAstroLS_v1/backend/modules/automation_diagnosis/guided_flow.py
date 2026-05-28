"""Guided flow definition for automation diagnosis.

The assistant is intentionally not an open chatbot. These steps provide the
minimum structured intake needed for deterministic scoring and classifier rules.
"""

from __future__ import annotations

from typing import Any


GUIDED_STEPS: list[dict[str, Any]] = [
    {
        "id": "process_to_automate",
        "label": "Proceso a automatizar",
        "type": "controlled_text",
        "required": True,
    },
    {
        "id": "business_pain",
        "label": "Dolor de negocio",
        "type": "controlled_text",
        "required": True,
    },
    {
        "id": "systems_involved",
        "label": "Sistemas involucrados",
        "type": "multi_choice_with_text",
        "options": ["excel", "erp", "sap_b1", "whatsapp", "email", "browser_portal", "desktop_app", "api", "other"],
        "required": True,
    },
    {
        "id": "frequency_volume",
        "label": "Frecuencia y volumen",
        "type": "multi_choice_with_text",
        "options": ["daily", "weekly", "monthly", "low_volume", "medium_volume", "high_volume"],
        "required": True,
    },
    {
        "id": "rules_clarity",
        "label": "Claridad de reglas",
        "type": "single_choice_with_text",
        "options": ["clear", "partially_clear", "mostly_manual", "unknown"],
        "required": True,
    },
    {
        "id": "human_dependency",
        "label": "Dependencia humana",
        "type": "single_choice_with_text",
        "options": ["low", "medium", "high", "expert_judgement"],
        "required": True,
    },
    {
        "id": "access_security",
        "label": "Accesos, permisos y MFA",
        "type": "multi_choice_with_text",
        "options": ["password", "role_permissions", "email_otp", "sms_otp", "totp", "push_or_qr", "fido2_hardware", "biometric", "unknown"],
        "required": True,
    },
    {
        "id": "data_sensitivity",
        "label": "Sensibilidad de datos",
        "type": "multi_choice_with_text",
        "options": ["public", "personal_data", "financial_data", "erp_operational_data", "religious_or_sensitive", "banking_or_payments"],
        "required": True,
    },
    {
        "id": "expected_result",
        "label": "Resultado esperado",
        "type": "controlled_text",
        "required": True,
    },
    {
        "id": "economic_impact",
        "label": "Impacto economico u operativo",
        "type": "single_choice_with_text",
        "options": ["low", "medium", "high", "critical"],
        "required": True,
    },
]


def get_guided_flow() -> list[dict[str, Any]]:
    return list(GUIDED_STEPS)


def get_step(step_id: str) -> dict[str, Any] | None:
    return next((step for step in GUIDED_STEPS if step["id"] == step_id), None)


def required_step_ids() -> list[str]:
    return [step["id"] for step in GUIDED_STEPS if step.get("required")]

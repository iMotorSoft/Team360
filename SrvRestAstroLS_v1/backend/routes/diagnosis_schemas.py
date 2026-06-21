"""Pydantic schemas for automation_diagnosis HTTP boundary.

Pydantic is used only at the HTTP/API border for validation,
serialization and OpenAPI generation, per lat.md/postgres-driver-policy.md.
Domain logic does not import this module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    source_url: str = ""
    locale: str = "es"
    visitor: dict = Field(default_factory=dict)
    assistant_instance_id: str | None = None


class SaveAnswerRequest(BaseModel):
    step_id: str
    answer: dict = Field(default_factory=dict)


class ClassifyRequest(BaseModel):
    pass


# ── Public API schemas (/api/diagnosis/*) ──────────────────────────────────


class PublicStartRequest(BaseModel):
    assistant_instance_code: str = "team360_sales_diagnosis"
    assistant_display_name: str | None = None
    source_channel: str | None = None
    site_channel: str | None = None
    source_url: str = ""
    locale: str = "es"
    visitor: dict = Field(default_factory=dict)
    lead_owner: str | None = None
    service_code: str | None = None
    package_code: str | None = None
    knowledge_scope_code: str | None = None
    initial_text: str = ""


class PublicMessageRequest(BaseModel):
    session_id: str
    text: str
    locale: str | None = None


class PublicMessageResponse(BaseModel):
    session_id: str
    status: str
    message: str
    next_action: str = "continue_conversation"
    missing_slots: list = Field(default_factory=list)
    checklist: list = Field(default_factory=list)
    metadata: dict = Field(default_factory=lambda: {
        "contract_version": "2026-06-07",
        "mode": "wrapper_preliminary",
        "checklist_real": False,
        "lead_real": False,
    })


class PublicSubmitChecklistRequest(BaseModel):
    session_id: str
    answers: list = Field(default_factory=list)


class PublicLeadRequest(BaseModel):
    session_id: str
    cta_type: str = ""
    contact: dict = Field(default_factory=dict)
    consent: bool = False


class PublicTurnRequest(BaseModel):
    session_id: str | None = None
    message: str
    locale: str = "es"
    interaction_response: dict | None = None


class PublicTurnResponse(BaseModel):
    session_id: str
    response_text: str
    turn_count: int = 0
    is_new: bool = False
    language: dict | None = None
    turn_decision: dict | None = None
    diagnosis: dict | None = None
    interaction_block: dict | None = None

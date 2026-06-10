"""Pydantic schemas for the internal/dev sales diagnosis runtime endpoint.

Pydantic is used only at the HTTP/API border for validation,
serialization and OpenAPI generation, per lat.md/postgres-driver-policy.md.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DevTurnRequest(BaseModel):
    session_id: str
    message: str
    assistant_instance_code: str = "team360_sales_diagnosis"
    package_code: str = "pkg_sales_diagnosis"
    knowledge_scope_code: str = "ks_team360_sales_diagnosis"
    metadata: dict = Field(default_factory=dict)


class DevTurnResponse(BaseModel):
    session_id: str
    response_text: str
    response_type: str
    fallback_applied: bool
    guardrail_flags: list[str] = Field(default_factory=list)
    retrieved_sources: list[dict] = Field(default_factory=list)
    turn_count: int = 0
    events: list[dict] = Field(default_factory=list)
    runtime_mode: str = "dev_fake"

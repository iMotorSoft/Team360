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

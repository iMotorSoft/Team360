"""Automation diagnosis HTTP endpoints.

Litestar route handlers that delegate to AutomationDiagnosisService
or PostgresAutomationDiagnosisService depending on AUTOMATION_DIAGNOSIS_REPOSITORY.

Uses Pydantic only at the HTTP boundary for validation.
"""

from __future__ import annotations

import os

from litestar import post
from litestar.exceptions import HTTPException

from modules.automation_diagnosis import build_default_service
from modules.automation_diagnosis.ai_interpreter import AIInterpretationError, build_ai_interpreter
from modules.automation_diagnosis.postgres_service import (
    AutomationDiagnosisPersistenceError,
    PostgresAutomationDiagnosisService,
)
from modules.db.pool import create_pool, set_pool
from modules.db.settings import get_database_settings

from .diagnosis_schemas import SaveAnswerRequest, StartSessionRequest


_REPOSITORY_TYPE = os.environ.get("AUTOMATION_DIAGNOSIS_REPOSITORY", "memory")


class _SyncToAsyncAdapter:
    """Wrap a sync service to present the same async interface as
    PostgresAutomationDiagnosisService.

    Routes always ``await`` the result regardless of backend.
    """

    def __init__(self, service):
        self._service = service

    async def start_session(self, payload):
        return self._service.start_session(payload)

    async def save_answer(self, session_id, payload):
        return self._service.save_answer(session_id, payload)

    async def classify(self, session_id):
        return self._service.classify(session_id)


def _build_service():
    if _REPOSITORY_TYPE == "postgres":
        settings = get_database_settings(min_size=1, max_size=5)
        pool = create_pool(settings)
        set_pool(pool)
        return PostgresAutomationDiagnosisService(pool=pool, ai_interpreter=build_ai_interpreter())
    return _SyncToAsyncAdapter(build_default_service())


_SERVICE = _build_service()


@post("/api/automation-diagnosis/session/start")
async def start_session(data: StartSessionRequest) -> dict:
    payload = data.model_dump(exclude_none=True)
    try:
        return await _SERVICE.start_session(payload)
    except AutomationDiagnosisPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIInterpretationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@post("/api/automation-diagnosis/session/{session_id:str}/answer")
async def save_answer(session_id: str, data: SaveAnswerRequest) -> dict:
    try:
        return await _SERVICE.save_answer(session_id, {"step_id": data.step_id, "answer": data.answer})
    except AutomationDiagnosisPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIInterpretationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@post("/api/automation-diagnosis/session/{session_id:str}/classify")
async def classify(session_id: str) -> dict:
    try:
        return await _SERVICE.classify(session_id)
    except AutomationDiagnosisPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIInterpretationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

"""Public diagnosis API endpoints (/api/diagnosis/*).

Thin wrapper over the existing ``automation_diagnosis`` service.
No new business logic, no new motor, no scoring changes.

Reuses the same ``_SERVICE`` instance as
``routes.automation_diagnosis`` so in-memory sessions are shared.
"""

from __future__ import annotations

from litestar import get, post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_501_NOT_IMPLEMENTED

from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.postgres_service import AutomationDiagnosisPersistenceError

from .automation_diagnosis import get_service as _get_auto_service
from .diagnosis_schemas import (
    PublicLeadRequest,
    PublicMessageRequest,
    PublicStartRequest,
    PublicSubmitChecklistRequest,
)


def _service():
    """Return the shared automation diagnosis service.

    Resolved at call time so monkeypatches in tests work correctly.
    """
    return _get_auto_service()


def _build_preliminary_message(text: str, display_name: str = "Vera") -> str:
    normalized = text.strip()
    short = normalized[:160] + "..." if len(normalized) > 160 else normalized
    return (
        f"Entendí que querés analizar este proceso: \"{short}\". "
        "En esta primera etapa puedo iniciar el diagnóstico y preparar los datos base. "
        "El siguiente paso será confirmar algunos puntos para estimar factibilidad, "
        "impacto y complejidad."
    )


def _resolve_display_name(payload: dict) -> str:
    visitor = payload.get("visitor") or {}
    return visitor.get("assistant_display_name") or "Vera"


@post("/api/diagnosis/start")
async def public_start(data: PublicStartRequest) -> dict:
    svc = _service()

    visitor_meta = {
        "source_channel": data.source_channel or "home_public",
        "site_channel": data.site_channel or "team360.live",
        "assistant_display_name": data.assistant_display_name or "Vera",
        "lead_owner": data.lead_owner or "team360_live",
        "service_code": data.service_code or "svc_sales_diagnosis",
        "package_code": data.package_code or "pkg_sales_diagnosis",
        "knowledge_scope_code": data.knowledge_scope_code or "ks_team360_sales_diagnosis",
        "template_code": "team360_sales_automation_diagnosis",
        "initial_text_length": len(data.initial_text),
        **(data.visitor or {}),
    }

    payload = {
        "source_url": data.source_url,
        "locale": data.locale,
        "assistant_instance_id": data.assistant_instance_code,
        "visitor": visitor_meta,
    }

    try:
        result = await svc.start_session(payload)
    except AutomationDiagnosisPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIInterpretationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    display_name = data.assistant_display_name or "Vera"

    response: dict = {
        "session_id": result["id"],
        "status": result["status"],
        "assistant_instance_code": result["assistant_instance_id"],
        "assistant_display_name": display_name,
        "next_action": "send_message",
        "message": None,
        "technical_metadata": {
            "organization_id": result["organization_id"],
            "workspace_id": result["workspace_id"],
            "automation_package_id": result["automation_package_id"],
            "knowledge_scope_id": result["knowledge_scope_id"],
            "locale": result["locale"],
            "service_code": data.service_code or "svc_sales_diagnosis",
            "package_code": data.package_code or "pkg_sales_diagnosis",
            "knowledge_scope_code": data.knowledge_scope_code or "ks_team360_sales_diagnosis",
            "template_code": "team360_sales_automation_diagnosis",
            "contract_version": "2026-06-07",
        },
    }

    if data.initial_text.strip():
        try:
            await svc.save_answer(
                result["id"],
                {"step_id": "process_to_automate", "answer": {"free_text": data.initial_text.strip()}},
            )
            response["message"] = _build_preliminary_message(data.initial_text.strip(), display_name)
        except (AutomationDiagnosisPersistenceError, AIInterpretationError, ValueError) as exc:
            response["message"] = _build_preliminary_message(data.initial_text.strip(), display_name)

    return response


@post("/api/diagnosis/message")
async def public_message(data: PublicMessageRequest) -> dict:
    svc = _service()
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be empty")

    try:
        await svc.save_answer(
            data.session_id,
            {"step_id": "process_to_automate", "answer": {"free_text": text}},
        )
        session = svc.get_session(data.session_id)
    except AutomationDiagnosisPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIInterpretationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "session_id": data.session_id,
        "status": session["status"],
        "message": _build_preliminary_message(text),
        "next_action": "continue_conversation",
        "missing_slots": [],
        "checklist": [],
        "metadata": {
            "contract_version": "2026-06-07",
            "mode": "wrapper_preliminary",
            "checklist_real": False,
            "lead_real": False,
        },
    }


@get("/api/diagnosis/session/{session_id:str}")
async def public_get_session(session_id: str) -> dict:
    svc = _service()
    try:
        session = svc.get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "session_id": session["id"],
        "status": session["status"],
        "assistant_instance_code": session.get("assistant_instance_id"),
        "answers": session.get("answers", {}),
        "result": session.get("result"),
        "next_action": "continue_conversation" if session["status"] == "active" else "view_result",
        "metadata": {
            "contract_version": "2026-06-07",
            "mode": "wrapper_preliminary",
            "checklist_real": False,
            "lead_real": False,
        },
    }


@post("/api/diagnosis/submit-checklist", status_code=HTTP_501_NOT_IMPLEMENTED)
async def public_submit_checklist(data: PublicSubmitChecklistRequest) -> dict:
    return {
        "error": "checklist_real not implemented",
        "message": "Dynamic checklist is not yet available. "
        "This endpoint is a placeholder for future contract compliance.",
        "contract_version": "2026-06-07",
    }


@post("/api/diagnosis/lead", status_code=HTTP_501_NOT_IMPLEMENTED)
async def public_lead(data: PublicLeadRequest) -> dict:
    return {
        "error": "lead_real not implemented",
        "message": "Lead capture is not yet available. "
        "This endpoint is a placeholder for future contract compliance.",
        "contract_version": "2026-06-07",
    }

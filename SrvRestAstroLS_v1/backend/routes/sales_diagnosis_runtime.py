"""Controlled product adapter skeleton for Sales Diagnosis Runtime.

This route prepares the transition from the internal/dev endpoint to a
non-dev adapter surface. It is not the final public/product endpoint.

Endpoint: POST /api/sales-diagnosis-runtime/turn

The route is disabled by default. Enable only for controlled adapter tests:

TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1

Safe defaults when enabled:
- state: in-memory
- retrieval: fake
- LLM: fake

No real PostgreSQL, Milvus, LiteLLM, OpenAI, SSE, Step-to-Action,
lead_capture, diagnostic_code, WhatsApp handoff or CRM is activated here.
"""

from __future__ import annotations

import os

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    GuardrailPolicy,
    PromptPolicy,
)
from modules.sales_diagnosis_runtime.errors import (
    InvalidAssistantRuntimeInputError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.state_repository import (
    InMemoryConversationStateRepository,
)

from .sales_diagnosis_runtime_dev import (
    _DevFakeLLMProvider,
    _DevFakeRetrievalProvider,
    _PROHIBITED_CODES,
    _chunk_to_dict,
    _event_to_dict,
    _validate_codes,
)
from .sales_diagnosis_runtime_schemas import (
    ProductTurnRequest,
    ProductTurnResponse,
)


PRODUCT_ROUTE_ENABLED_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED"
PRODUCT_RUNTIME_MODE = "product_adapter_skeleton"

_shared_product_inmemory_repo = InMemoryConversationStateRepository()


def _is_product_route_enabled() -> bool:
    return os.environ.get(PRODUCT_ROUTE_ENABLED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _ensure_product_route_enabled() -> None:
    if _is_product_route_enabled():
        return
    raise HTTPException(
        status_code=HTTP_404_NOT_FOUND,
        detail=(
            "Sales diagnosis product adapter route is disabled. "
            f"Set {PRODUCT_ROUTE_ENABLED_ENV}=1 to enable controlled adapter tests."
        ),
    )


def _build_product_adapter_runtime() -> AssistantConversationRuntime:
    return AssistantConversationRuntime(
        retrieval_provider=_DevFakeRetrievalProvider(),
        llm_provider=_DevFakeLLMProvider(),
        state_repository=_shared_product_inmemory_repo,
        prompt_policy=PromptPolicy(),
        guardrail_policy=GuardrailPolicy(),
    )


def _validate_product_codes(data: ProductTurnRequest) -> None:
    _validate_codes(data)
    for service_code in (data.service_code, data.metadata.get("service_code")):
        if service_code not in _PROHIBITED_CODES:
            continue
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=(
                f"Prohibited service_code: {service_code!r}. "
                "Use standard team360 codes."
            ),
        )


def _guardrail_flags(output) -> list[str]:
    flags: list[str] = []
    if output.guardrail_result.fallback_applied:
        flags.append("fallback_applied")
    if output.guardrail_result.max_questions_exceeded:
        flags.append("max_questions_exceeded")
    if output.guardrail_result.pricing_sla_hallucination:
        flags.append("pricing_sla_hallucination")
    return flags


@post("/api/sales-diagnosis-runtime/turn")
async def sales_diagnosis_turn(data: ProductTurnRequest) -> dict:
    _ensure_product_route_enabled()
    _validate_product_codes(data)

    runtime = _build_product_adapter_runtime()
    input_ = AssistantTurnInput(
        session_id=data.session_id,
        assistant_instance_code=data.assistant_instance_code,
        package_code=data.package_code,
        knowledge_scope_code=data.knowledge_scope_code,
        user_message=data.message,
        channel=data.metadata.get("channel", "api"),
        metadata=data.metadata,
    )

    try:
        output = runtime.handle_turn(input_)
    except UnsafeResponseError as exc:
        return ProductTurnResponse(
            session_id=data.session_id,
            response_text=str(exc),
            response_type="unsafe_blocked",
            fallback_applied=False,
            guardrail_flags=["unsafe_response_blocked"],
            turn_count=0,
            runtime_mode=PRODUCT_RUNTIME_MODE,
        ).model_dump()
    except InvalidAssistantRuntimeInputError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc))

    turn_count = output.next_state.turn_count if output.next_state else 0

    return ProductTurnResponse(
        session_id=data.session_id,
        response_text=output.response_text,
        response_type=output.response_type,
        fallback_applied=output.guardrail_result.fallback_applied,
        guardrail_flags=_guardrail_flags(output),
        retrieved_sources=[_chunk_to_dict(c) for c in output.retrieved_sources],
        turn_count=turn_count,
        events=[_event_to_dict(e) for e in output.events],
        runtime_mode=PRODUCT_RUNTIME_MODE,
    ).model_dump()

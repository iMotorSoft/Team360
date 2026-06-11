"""Controlled product adapter skeleton for Sales Diagnosis Runtime.

This route prepares the transition from the internal/dev endpoint to a
non-dev adapter surface. It is not the final public/product endpoint.

Endpoint: POST /api/sales-diagnosis-runtime/turn

The route is disabled by default. Enable only for controlled adapter tests:

TEAM360_SALES_DIAGNOSIS_PRODUCT_ROUTE_ENABLED=1

State must be explicit when enabled:
- TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=postgres
- TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY=inmemory_test

LLM provider (env var):
- Default (unset or "fake"): _DevFakeLLMProvider (no OpenAI)
- ``TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER=openai``: uses
  _ProductOpenAILLMProvider with OpenAI direct (requires TEAM360_OPENAI_KEY
  or OPENAI_API_KEY). Model via TEAM360_OPENAI_MODEL (default gpt-5-nano).
- Invalid values: HTTP 503 controlled error

Safe provider defaults when enabled:
- retrieval: fake
- LLM: fake

No Milvus, LiteLLM, SSE, Step-to-Action, lead_capture,
diagnostic_code, WhatsApp handoff or CRM is activated here.
"""

from __future__ import annotations

import os

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    GuardrailPolicy,
    PromptPolicy,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    InvalidAssistantRuntimeInputError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.providers import LLMProvider
from modules.sales_diagnosis_runtime.state_repository import (
    InMemoryConversationStateRepository,
    SyncPostgresConversationStateRepository,
    SyncPostgresConversationStateRepositoryError,
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
PRODUCT_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_STATE_REPOSITORY"
PRODUCT_LLM_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_PRODUCT_LLM_PROVIDER"
PRODUCT_RUNTIME_MODE = "product_adapter_skeleton"

_shared_product_inmemory_test_repo = InMemoryConversationStateRepository()


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


def _resolve_product_postgres_dsn() -> str:
    from globalVar import get_team360_db_url_psql

    dsn = get_team360_db_url_psql()
    if not dsn:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{PRODUCT_STATE_REPOSITORY_ENV}=postgres requires TEAM360_DB_URL "
                "or TEAM360_DB_URL_PSQL. Configure globalVar.py inputs before "
                "using the product adapter with Postgres state."
            ),
        )
    return dsn


def _resolve_product_state_repository():
    mode = os.environ.get(PRODUCT_STATE_REPOSITORY_ENV, "").strip().lower()
    if not mode:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{PRODUCT_STATE_REPOSITORY_ENV} is required when "
                f"{PRODUCT_ROUTE_ENABLED_ENV}=1. Use 'postgres' for product "
                "state or 'inmemory_test' for controlled adapter tests only."
            ),
        )
    if mode == "postgres":
        return SyncPostgresConversationStateRepository(_resolve_product_postgres_dsn())
    if mode == "inmemory_test":
        return _shared_product_inmemory_test_repo
    raise HTTPException(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            f"Invalid {PRODUCT_STATE_REPOSITORY_ENV}={mode!r}. "
            "Use 'postgres' or 'inmemory_test'."
        ),
    )


# ---------------------------------------------------------------------------
# LLM provider
# ---------------------------------------------------------------------------


class _ProductOpenAILLMProvider:
    """OpenAI LLM provider for product adapter.

    Uses the OpenAI SDK with lazy import to avoid loading at module scope.
    Requires TEAM360_OPENAI_KEY or OPENAI_API_KEY.
    Model via TEAM360_OPENAI_MODEL (default gpt-5-nano).

    Builds prompts via PromptPolicy.
    """

    def __init__(self) -> None:
        self._api_key = self._resolve_api_key()
        self._model = self._resolve_model()
        self._prompt_policy = PromptPolicy()

    @staticmethod
    def _resolve_api_key() -> str:
        try:
            from globalVar import get_team360_openai_key
            api_key = get_team360_openai_key()
            if api_key:
                return api_key
        except ImportError:
            pass
        api_key = (
            os.environ.get("TEAM360_OPENAI_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        if not api_key:
            raise HTTPException(
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"{PRODUCT_LLM_PROVIDER_ENV}=openai requires "
                    "an OpenAI API key configured in globalVar.py "
                    "(OpenAI_Key_JAI_query, TEAM360_OPENAI_KEY "
                    "or OPENAI_API_KEY)."
                ),
            )
        return api_key

    @staticmethod
    def _resolve_model() -> str:
        try:
            from globalVar import get_team360_openai_model
            return get_team360_openai_model()
        except ImportError:
            return os.environ.get("TEAM360_OPENAI_MODEL", "").strip() or "gpt-5-nano"

    def generate(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        system_prompt = self._prompt_policy.build_system_prompt(
            assistant_instance_code=input.assistant_instance_code,
            package_code=input.package_code,
        )
        turn_prompt = self._prompt_policy.build_turn_prompt(input, state, context)

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key)
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": turn_prompt},
                ],
                timeout=30,
            )
            content = response.choices[0].message.content
            if not content:
                return "No se pudo generar una respuesta en este momento."
            return content
        except Exception:
            from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT

            return SAFE_ACK_TEXT


def _resolve_product_llm_provider() -> LLMProvider:
    mode = os.environ.get(PRODUCT_LLM_PROVIDER_ENV, "").strip().lower()
    if not mode or mode == "fake":
        return _DevFakeLLMProvider()
    if mode == "openai":
        return _ProductOpenAILLMProvider()
    raise HTTPException(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            f"Invalid {PRODUCT_LLM_PROVIDER_ENV}={mode!r}. "
            "Use 'fake' (default) or 'openai'."
        ),
    )


def _build_product_adapter_runtime() -> AssistantConversationRuntime:
    return AssistantConversationRuntime(
        retrieval_provider=_DevFakeRetrievalProvider(),
        llm_provider=_resolve_product_llm_provider(),
        state_repository=_resolve_product_state_repository(),
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
    except SyncPostgresConversationStateRepositoryError as exc:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None

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

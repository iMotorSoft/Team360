"""Public diagnosis API endpoints (/api/diagnosis/*).

Thin wrapper over the existing ``automation_diagnosis`` service.
No new business logic, no new motor, no scoring changes.

Reuses the same ``_SERVICE`` instance as
``routes.automation_diagnosis`` so in-memory sessions are shared.

``POST /api/diagnosis/turn`` implements multi-turn conversation using
``AssistantConversationRuntime`` from ``modules.sales_diagnosis_runtime``.
"""

from __future__ import annotations

import os
from uuid import uuid4

from litestar import get, post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_501_NOT_IMPLEMENTED

from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.litellm_client import (
    LiteLLMClient,
    LiteLLMClientError,
    get_litellm_api_key,
)
from modules.automation_diagnosis.postgres_service import (
    AutomationDiagnosisPersistenceError,
)
from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    GuardrailPolicy,
    PromptPolicy,
)
from modules.sales_diagnosis_runtime.intent_classifier import LiteLLMIntentClassifier
from modules.sales_diagnosis_runtime.contracts import (
    SAFE_ACK_TEXT,
    SAFE_ACK_TEXTS,
    KnowledgeScopeContext,
    SALES_DIAGNOSIS_INSTANCE_CODE,
    SALES_DIAGNOSIS_ORGANIZATION_CODE,
    SALES_DIAGNOSIS_PACKAGE_CODE,
    SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE,
    SALES_DIAGNOSIS_WORKSPACE_CODE,
    safe_ack_for_language,
)
from modules.sales_diagnosis_runtime.contracts import ConversationState, RetrievedChunk
from modules.sales_diagnosis_runtime.errors import (
    InvalidAssistantRuntimeInputError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.knowledge_scope_resolver import (
    PostgresKnowledgeScopeResolver,
    ScopeResolutionError,
)
from modules.sales_diagnosis_runtime.milvus_provider import (
    MilvusRetrievalProvider,
    MilvusRuntimeConfig,
)
from modules.sales_diagnosis_runtime.providers import RetrievalProvider
from modules.sales_diagnosis_runtime.state_repository import (
    InMemoryConversationStateRepository,
)

from .automation_diagnosis import get_service as _get_auto_service
from .diagnosis_schemas import (
    PublicLeadRequest,
    PublicMessageRequest,
    PublicStartRequest,
    PublicSubmitChecklistRequest,
    PublicTurnRequest,
    PublicTurnResponse,
)


# ---------------------------------------------------------------------------
# State repository for public conversation turns (PostgreSQL when configured)
# ---------------------------------------------------------------------------

def _build_public_state_repo():
    mode = os.environ.get("AUTOMATION_DIAGNOSIS_REPOSITORY", "").strip().lower()
    if mode == "postgres":
        from modules.sales_diagnosis_runtime.state_repository import (
            SyncPostgresConversationStateRepository,
        )
        from globalVar import get_team360_db_url_psql
        dsn = get_team360_db_url_psql()
        if not dsn:
            raise RuntimeError(
                "AUTOMATION_DIAGNOSIS_REPOSITORY=postgres requires a valid "
                "PostgreSQL DSN. Set TEAM360_DB_URL or TEAM360_DB_URL_PSQL."
            )
        return SyncPostgresConversationStateRepository(dsn)
    if mode == "memory":
        return InMemoryConversationStateRepository()
    if mode:
        raise RuntimeError(
            f"Unsupported AUTOMATION_DIAGNOSIS_REPOSITORY={mode!r}. "
            "Use 'postgres' or 'memory'."
        )
    return InMemoryConversationStateRepository()


_public_turn_state = _build_public_state_repo()
_public_scope_resolver: PostgresKnowledgeScopeResolver | None = None


def _get_public_scope_resolver() -> PostgresKnowledgeScopeResolver | None:
    global _public_scope_resolver
    if _public_scope_resolver is None:
        try:
            _public_scope_resolver = PostgresKnowledgeScopeResolver.from_settings()
        except Exception:
            _public_scope_resolver = None
    return _public_scope_resolver


# ---------------------------------------------------------------------------
# Public turn LLM provider
# ---------------------------------------------------------------------------


class _PublicTurnLLMProvider:
    model_name: str | None = None

    def __init__(self) -> None:
        self._base_url = os.environ.get("TEAM360_LITELLM_BASE_URL", "").strip() or None
        self._model = (
            os.environ.get("TEAM360_LITELLM_MODEL_ALIAS")
            or "openai_gpt-5-nano"
        )
        self.model_name = self._model
        self._prompt_policy = PromptPolicy()

    def generate(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        lang_info = (state.semantic_memory or {}).get("language", {})
        response_language = (
            lang_info.get("preferred_response_language")
            or lang_info.get("current_language")
            or input.locale
        )
        if os.environ.get("TEAM360_AI_PROVIDER", "").strip().lower() != "litellm":
            return safe_ack_for_language(response_language)

        client = LiteLLMClient(base_url=self._base_url)
        system = self._prompt_policy.build_system_prompt(
            assistant_instance_code=input.assistant_instance_code,
            package_code=input.package_code,
            response_language=response_language,
        )
        turn = self._prompt_policy.build_turn_prompt(input, state, context)
        try:
            response = client.text_completion(
                self._model,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": turn},
                ],
            )
            return response.content
        except LiteLLMClientError:
            raise
        except Exception:
            return safe_ack_for_language(response_language)


# ---------------------------------------------------------------------------
# Public turn retrieval provider
# ---------------------------------------------------------------------------


class _PublicLiteLLMEmbeddingProvider:
    def __init__(self) -> None:
        raw_url = os.environ.get("TEAM360_LITELLM_BASE_URL", "").strip() or "http://localhost:4000"
        base = raw_url.rstrip("/")
        if base.endswith("/v1"):
            self._base_url = base + "/embeddings"
        else:
            self._base_url = base + "/v1/embeddings"
        self._model = os.environ.get("TEAM360_EMBEDDING_MODEL", "").strip() or "openai_text_embedding_3_small"
        self._api_key = (
            os.environ.get("TEAM360_LITELLM_API_KEY")
            or os.environ.get("LITELLM_API_KEY")
            or os.environ.get("LITELLM_MASTER_KEY")
            or ""
        )
        self._milvus_mode = os.environ.get("TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER", "").strip().lower() == "milvus"

    def embed_query(self, text: str) -> list[float]:
        if self._milvus_mode and not self._base_url:
            raise RuntimeError(
                "TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus requires "
                "TEAM360_LITELLM_BASE_URL for embeddings."
            )
        if not self._base_url:
            return [0.0] * 1536
        import json
        import urllib.request
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        data = json.dumps({"model": self._model, "input": text}).encode()
        req = urllib.request.Request(self._base_url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
        except Exception as exc:
            if self._milvus_mode:
                raise RuntimeError(f"Embedding failed in Milvus mode: {exc}") from exc
            return [0.0] * 1536
        embedding = result.get("data", [{}])[0].get("embedding")
        if not embedding:
            if self._milvus_mode:
                raise RuntimeError("Embedding response did not contain a valid embedding vector.")
            return [0.0] * 1536
        if len(embedding) != 1536:
            if self._milvus_mode:
                raise RuntimeError(
                    f"Embedding dimension {len(embedding)} != 1536. "
                    "Expected 1536 for the current Milvus collection."
                )
            return [0.0] * 1536
        return embedding


def _build_public_retrieval() -> RetrievalProvider:
    config = MilvusRuntimeConfig.from_env()
    if config.uri or config.host:
        return MilvusRetrievalProvider(
            config=config,
            embedding_provider=_PublicLiteLLMEmbeddingProvider(),
        )
    from modules.sales_diagnosis_runtime.providers import NullRetrievalProvider

    return NullRetrievalProvider()


# ---------------------------------------------------------------------------
# Build runtime for public conversation turns
# ---------------------------------------------------------------------------


def _build_public_turn_runtime() -> AssistantConversationRuntime:
    return AssistantConversationRuntime(
        retrieval_provider=_build_public_retrieval(),
        llm_provider=_PublicTurnLLMProvider(),
        state_repository=_public_turn_state,
        prompt_policy=PromptPolicy(),
        guardrail_policy=GuardrailPolicy(),
        intent_classifier=LiteLLMIntentClassifier(),
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


@post("/api/diagnosis/turn")
async def public_turn(data: PublicTurnRequest) -> PublicTurnResponse:
    text = data.message.strip()
    if not text:
        raise HTTPException(status_code=422, detail="message must not be empty")

    is_new = data.session_id is None
    session_id = data.session_id or f"conv_{uuid4().hex[:12]}"

    runtime = _build_public_turn_runtime()

    # Resolve knowledge scope code to UUID via PostgreSQL.
    # The resolver caches results in-memory for the process lifetime.
    resolved_scope_id: str | None = None
    resolver = _get_public_scope_resolver()
    if resolver is not None:
        try:
            ctx = KnowledgeScopeContext(
                organization_code=SALES_DIAGNOSIS_ORGANIZATION_CODE,
                workspace_code=SALES_DIAGNOSIS_WORKSPACE_CODE,
                package_code=SALES_DIAGNOSIS_PACKAGE_CODE,
                knowledge_scope_code=SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE,
            )
            resolved_scope_id = await resolver.resolve_scope_id(ctx)
        except (ScopeResolutionError, Exception):
            resolved_scope_id = None

    input_ = AssistantTurnInput(
        session_id=session_id,
        assistant_instance_code=SALES_DIAGNOSIS_INSTANCE_CODE,
        package_code=SALES_DIAGNOSIS_PACKAGE_CODE,
        knowledge_scope_code=SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE,
        knowledge_scope_id=resolved_scope_id,
        user_message=text,
        channel="web",
        locale=data.locale,
        metadata={"source": "t360"},
    )

    try:
        output = runtime.handle_turn(input_)
    except LiteLLMClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except UnsafeResponseError:
        lang_state: dict = {}
        turn_count = 0
        try:
            saved_state = _public_turn_state.load(session_id)
            if saved_state:
                turn_count = saved_state.turn_count
                lang_state = (saved_state.semantic_memory or {}).get("language", {})
        except Exception:
            lang_state = {}
        response_language = (
            lang_state.get("preferred_response_language")
            or lang_state.get("current_language")
            or data.locale
        )
        return PublicTurnResponse(
            session_id=session_id,
            response_text=safe_ack_for_language(response_language),
            turn_count=turn_count,
            is_new=is_new,
            language={
                "initial_language": lang_state.get("initial_language", response_language),
                "current_language": response_language,
                "preferred_response_language": response_language,
                "response_language": response_language,
                "language_confidence": lang_state.get("language_confidence", 1.0),
                "language_source": lang_state.get("language_source", "fallback"),
                "explicit_language_preference": lang_state.get("explicit_language_preference", False),
            },
            diagnosis=None,
        )
    except InvalidAssistantRuntimeInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    turn_count = output.next_state.turn_count if output.next_state else 0

    # Persist conversation history and semantic memory in state
    if output.next_state:
        prev = output.next_state.history_summary or ""
        exchange = f"Usuario: {text}\nVera: {output.response_text}"
        output.next_state.history_summary = (
            f"{prev}\n{exchange}" if prev else exchange
        )
        # Ensure semantic_memory is initialized
        if not output.next_state.semantic_memory:
            output.next_state.semantic_memory = {"diagnosis_status": "gathering"}
        _public_turn_state.save(output.next_state)

    return PublicTurnResponse(
        session_id=session_id,
        response_text=output.response_text,
        turn_count=turn_count,
        is_new=is_new,
        language=output.language,
        turn_decision=output.turn_decision,
        diagnosis=output.diagnosis,
        interaction_block=output.interaction_block,
    )

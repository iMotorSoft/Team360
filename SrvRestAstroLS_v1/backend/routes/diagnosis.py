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
import warnings
from uuid import uuid4

from litestar import get, post
from litestar.connection import Request
from litestar.exceptions import HTTPException
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_403_FORBIDDEN,
    HTTP_501_NOT_IMPLEMENTED,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from modules.automation_diagnosis.ai_interpreter import AIInterpretationError
from modules.automation_diagnosis.assistant_instances import get_assistant_instance_config
from modules.automation_diagnosis.litellm_client import (
    LiteLLMClient,
    LiteLLMClientError,
    get_litellm_api_key,
)
from modules.automation_diagnosis.postgres_service import (
    AutomationDiagnosisPersistenceError,
)
from modules.db.errors import DatabaseExecutionError, DatabasePoolNotInitializedError
from modules.db.pool import get_pool
from modules.embed_clients import (
    EmbedClientError,
    EmbedClientInactiveError,
    EmbedClientNotFoundError,
    EmbedClientOriginDeniedError,
    InMemoryRateLimiter,
    LoggingEmbedAuthAuditor,
    PostgresEmbedClientRepository,
    SIGNATURE_HEADER_NAME,
    authorize_request,
    build_embed_auth_audit_event,
    build_embed_auth_rate_limit_key,
    get_embed_auth_rate_limit_settings,
    issue_signature,
    resolve_request_origin,
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
    PublicEmbedAuthRequest,
    PublicEmbedAuthResponse,
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
    mode = (
        os.environ.get("AUTOMATION_DIAGNOSIS_REPOSITORY")
        or os.environ.get("TEAM360_DIAGNOSIS_STATE_PROVIDER")
        or ""
    ).strip().lower()
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
        warnings.warn(
            "AUTOMATION_DIAGNOSIS_REPOSITORY=memory: conversation state will "
            "not survive backend restart.",
        )
        return InMemoryConversationStateRepository()
    if mode:
        raise RuntimeError(
            f"Unsupported AUTOMATION_DIAGNOSIS_REPOSITORY={mode!r}. "
            "Use 'postgres' or 'memory'."
        )
    warnings.warn(
        "AUTOMATION_DIAGNOSIS_REPOSITORY not set, defaulting to in-memory. "
        "Set AUTOMATION_DIAGNOSIS_REPOSITORY=postgres for persistence.",
    )
    return InMemoryConversationStateRepository()


_public_turn_state = _build_public_state_repo()
_public_scope_resolver: PostgresKnowledgeScopeResolver | None = None
_public_embed_client_repo: PostgresEmbedClientRepository | None = None
_public_embed_auth_rate_limiter: InMemoryRateLimiter | None = None
_public_embed_auth_auditor: LoggingEmbedAuthAuditor | None = None


def _get_public_scope_resolver() -> PostgresKnowledgeScopeResolver | None:
    global _public_scope_resolver
    if _public_scope_resolver is None:
        try:
            _public_scope_resolver = PostgresKnowledgeScopeResolver.from_settings()
        except Exception:
            _public_scope_resolver = None
    return _public_scope_resolver


def _get_public_embed_client_repository() -> PostgresEmbedClientRepository:
    global _public_embed_client_repo
    if _public_embed_client_repo is None:
        _public_embed_client_repo = PostgresEmbedClientRepository(get_pool())
    return _public_embed_client_repo


def _get_public_embed_auth_rate_limiter() -> InMemoryRateLimiter:
    global _public_embed_auth_rate_limiter
    if _public_embed_auth_rate_limiter is None:
        settings = get_embed_auth_rate_limit_settings()
        _public_embed_auth_rate_limiter = InMemoryRateLimiter(
            window_seconds=settings.window_seconds,
            max_requests=settings.max_requests,
            max_keys=settings.max_keys,
        )
    return _public_embed_auth_rate_limiter


def _get_public_embed_auth_auditor() -> LoggingEmbedAuthAuditor:
    global _public_embed_auth_auditor
    if _public_embed_auth_auditor is None:
        _public_embed_auth_auditor = LoggingEmbedAuthAuditor()
    return _public_embed_auth_auditor


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

        display_name = _resolve_turn_display_name(input.assistant_instance_code)
        client = LiteLLMClient(base_url=self._base_url)
        system = self._prompt_policy.build_system_prompt(
            assistant_instance_code=input.assistant_instance_code,
            package_code=input.package_code,
            response_language=response_language,
            assistant_display_name=display_name,
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


def _build_preliminary_message(text: str, display_name: str = "Diagnosticador") -> str:
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
    return visitor.get("assistant_display_name") or "Diagnosticador"

def _resolve_turn_display_name(instance_code: str = SALES_DIAGNOSIS_INSTANCE_CODE) -> str:
    try:
        config = get_assistant_instance_config(instance_code)
        return config.assistant_display_name or "Diagnosticador"
    except ValueError:
        return "Diagnosticador"


@post("/api/diagnosis/start")
async def public_start(data: PublicStartRequest) -> dict:
    svc = _service()

    visitor_meta = {
        "source_channel": data.source_channel or "home_public",
        "site_channel": data.site_channel or "team360.live",
        "assistant_display_name": data.assistant_display_name or "Diagnosticador",
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

    display_name = result.get("assistant_display_name") or data.assistant_display_name or "Diagnosticador"

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


# ---------------------------------------------------------------------------
# Allowlist for public diagnosis contexts
# ---------------------------------------------------------------------------

ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS: frozenset[tuple[str, str, str, str, str]] = frozenset({
    (
        SALES_DIAGNOSIS_INSTANCE_CODE,
        SALES_DIAGNOSIS_ORGANIZATION_CODE,
        SALES_DIAGNOSIS_WORKSPACE_CODE,
        SALES_DIAGNOSIS_PACKAGE_CODE,
        SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE,
    ),
})


def _validate_public_turn_context_allowed(context: dict[str, str]) -> None:
    """Validate the resolved context tuple against the allowlist.

    Raises HTTP 403 if the full 5-field tuple is not in the allowlist.
    Does NOT reveal which contexts are allowed.
    """
    if not ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS:
        return
    candidate = (
        context.get("assistant_instance_code", ""),
        context.get("organization_code", ""),
        context.get("workspace_code", ""),
        context.get("package_code", ""),
        context.get("knowledge_scope_code", ""),
    )
    if candidate not in ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Public diagnosis context is not allowed.",
        )


def _resolve_public_turn_context(data: PublicTurnRequest) -> dict[str, str]:
    """Resolve effective public diagnosis context from request or defaults.

    When the request provides optional context fields (assistant_instance_code,
    organization_code, workspace_code, package_code, knowledge_scope_code),
    they take precedence. Missing fields fall back to the hardcoded defaults.
    This guarantees backward compatibility: Vera never sends context fields
    and always gets the current defaults.
    """
    return {
        "assistant_instance_code": data.assistant_instance_code or SALES_DIAGNOSIS_INSTANCE_CODE,
        "organization_code": data.organization_code or SALES_DIAGNOSIS_ORGANIZATION_CODE,
        "workspace_code": data.workspace_code or SALES_DIAGNOSIS_WORKSPACE_CODE,
        "package_code": data.package_code or SALES_DIAGNOSIS_PACKAGE_CODE,
        "knowledge_scope_code": data.knowledge_scope_code or SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE,
    }


EMBED_CLIENT_AUTH_FAILED_DETAIL = "Embed client request is not authorized."
EMBED_CLIENT_AUTH_UNAVAILABLE_DETAIL = "Embed client authorization is unavailable."
EMBED_AUTH_RATE_LIMITED_DETAIL = "Too many embed authentication requests."


def _resolve_request_remote_ip(request: Request | None) -> str | None:
    if request is None:
        return None

    client = request.scope.get("client")
    if isinstance(client, tuple) and client:
        host = str(client[0] or "").strip()
        if host:
            return host

    client_attr = getattr(request, "client", None)
    host = getattr(client_attr, "host", None)
    if host:
        normalized = str(host).strip()
        if normalized:
            return normalized

    return None


def _resolve_request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or None
    )


def _audit_embed_auth_attempt(
    *,
    event_type: str,
    reason_code: str,
    status_code: int,
    client_id: str | None,
    request: Request | None,
) -> None:
    try:
        origin = resolve_request_origin(
            request.headers.get("Origin") if request is not None else None,
            request.headers.get("Referer") if request is not None else None,
        )
        event = build_embed_auth_audit_event(
            event_type=event_type,
            reason_code=reason_code,
            status_code=status_code,
            client_id=client_id,
            origin=origin,
            remote_ip=_resolve_request_remote_ip(request),
            request_id=_resolve_request_id(request),
            user_agent=request.headers.get("User-Agent") if request is not None else None,
        )
        _get_public_embed_auth_auditor().record(event)
    except Exception:
        return


async def _load_embed_client(client_id: str):
    normalized_client_id = client_id.strip()
    if not normalized_client_id:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=EMBED_CLIENT_AUTH_FAILED_DETAIL,
        )

    try:
        repository = _get_public_embed_client_repository()
        embed_client = await repository.load(normalized_client_id)
    except DatabasePoolNotInitializedError as exc:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBED_CLIENT_AUTH_UNAVAILABLE_DETAIL,
        ) from exc
    except DatabaseExecutionError as exc:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBED_CLIENT_AUTH_UNAVAILABLE_DETAIL,
        ) from exc

    if embed_client is None:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=EMBED_CLIENT_AUTH_FAILED_DETAIL,
        )

    return embed_client


async def _resolve_embed_turn_context(
    data: PublicTurnRequest,
    request: Request | None,
    *,
    message_text: str,
) -> dict[str, str]:
    client_id = (data.client_id or "").strip()
    if not client_id:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=EMBED_CLIENT_AUTH_FAILED_DETAIL,
        )
    if request is None:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBED_CLIENT_AUTH_UNAVAILABLE_DETAIL,
        )

    embed_client = await _load_embed_client(client_id)

    try:
        return authorize_request(
            embed_client,
            session_id=data.session_id,
            message=message_text,
            timestamp=data.timestamp,
            signature_header=request.headers.get(SIGNATURE_HEADER_NAME),
            origin_header=request.headers.get("Origin"),
            referer_header=request.headers.get("Referer"),
        )
    except (EmbedClientNotFoundError, EmbedClientError) as exc:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=EMBED_CLIENT_AUTH_FAILED_DETAIL,
        ) from exc


@post("/api/diagnosis/embed/auth", status_code=HTTP_200_OK)
async def public_embed_auth(
    data: PublicEmbedAuthRequest,
    request: Request | None = None,
) -> PublicEmbedAuthResponse:
    if request is None:
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBED_CLIENT_AUTH_UNAVAILABLE_DETAIL,
        )

    request_origin = resolve_request_origin(
        request.headers.get("Origin"),
        request.headers.get("Referer"),
    )
    remote_ip = _resolve_request_remote_ip(request)
    rate_limit_key = build_embed_auth_rate_limit_key(
        data.client_id,
        request_origin,
        remote_ip,
    )
    rate_limit = _get_public_embed_auth_rate_limiter().allow(rate_limit_key)
    if not rate_limit.allowed:
        _audit_embed_auth_attempt(
            event_type="embed_auth_rate_limited",
            reason_code="rate_limited",
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            client_id=data.client_id,
            request=request,
        )
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=EMBED_AUTH_RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(rate_limit.retry_after_seconds)},
        )

    message_text = data.message.strip()
    if not message_text:
        _audit_embed_auth_attempt(
            event_type="embed_auth_rejected",
            reason_code="validation_error",
            status_code=422,
            client_id=data.client_id,
            request=request,
        )
        raise HTTPException(status_code=422, detail="message must not be empty")

    try:
        embed_client = await _load_embed_client(data.client_id)
    except HTTPException as exc:
        if exc.status_code == HTTP_403_FORBIDDEN:
            _audit_embed_auth_attempt(
                event_type="embed_auth_rejected",
                reason_code="unknown_client",
                status_code=HTTP_403_FORBIDDEN,
                client_id=data.client_id,
                request=request,
            )
        raise

    try:
        signed = issue_signature(
            embed_client,
            session_id=data.session_id,
            message=message_text,
            origin_header=request.headers.get("Origin"),
            referer_header=request.headers.get("Referer"),
        )
    except (EmbedClientNotFoundError, EmbedClientError) as exc:
        reason_code = "validation_error"
        if isinstance(exc, EmbedClientInactiveError):
            reason_code = "inactive_client"
        elif isinstance(exc, EmbedClientOriginDeniedError):
            reason_code = "invalid_origin"
        _audit_embed_auth_attempt(
            event_type="embed_auth_rejected",
            reason_code=reason_code,
            status_code=HTTP_403_FORBIDDEN,
            client_id=data.client_id,
            request=request,
        )
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=EMBED_CLIENT_AUTH_FAILED_DETAIL,
        ) from exc

    _audit_embed_auth_attempt(
        event_type="embed_auth_allowed",
        reason_code="allowed",
        status_code=HTTP_200_OK,
        client_id=data.client_id,
        request=request,
    )
    return PublicEmbedAuthResponse(**signed)


@post("/api/diagnosis/turn")
async def public_turn(data: PublicTurnRequest, request: Request | None = None) -> PublicTurnResponse:
    text = data.message.strip()
    if not text:
        raise HTTPException(status_code=422, detail="message must not be empty")

    is_new = data.session_id is None
    session_id = data.session_id or f"conv_{uuid4().hex[:12]}"

    if data.client_id:
        ctx = await _resolve_embed_turn_context(data, request, message_text=text)
    else:
        ctx = _resolve_public_turn_context(data)
        _validate_public_turn_context_allowed(ctx)

    runtime = _build_public_turn_runtime()
    display_name = _resolve_turn_display_name(ctx["assistant_instance_code"])

    # Resolve knowledge scope code to UUID via PostgreSQL.
    # The resolver caches results in-memory for the process lifetime.
    resolved_scope_id: str | None = None
    resolver = _get_public_scope_resolver()
    if resolver is not None:
        try:
            scope_ctx = KnowledgeScopeContext(
                organization_code=ctx["organization_code"],
                workspace_code=ctx["workspace_code"],
                package_code=ctx["package_code"],
                knowledge_scope_code=ctx["knowledge_scope_code"],
            )
            resolved_scope_id = await resolver.resolve_scope_id(scope_ctx)
        except (ScopeResolutionError, Exception):
            resolved_scope_id = None

    input_ = AssistantTurnInput(
        session_id=session_id,
        assistant_instance_code=ctx["assistant_instance_code"],
        package_code=ctx["package_code"],
        knowledge_scope_code=ctx["knowledge_scope_code"],
        knowledge_scope_id=resolved_scope_id,
        user_message=text,
        channel="web",
        locale=data.locale,
        metadata={
            "source": "t360",
            **({"embed_client_id": data.client_id} if data.client_id else {}),
        },
    )

    if data.interaction_response:
        input_.metadata["interaction_response"] = data.interaction_response

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
            assistant_display_name=display_name,
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
        exchange = f"Usuario: {text}\n{display_name}: {output.response_text}"
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
        assistant_display_name=display_name,
        turn_count=turn_count,
        is_new=is_new,
        language=output.language,
        turn_decision=output.turn_decision,
        diagnosis=output.diagnosis,
        interaction_block=output.interaction_block,
    )

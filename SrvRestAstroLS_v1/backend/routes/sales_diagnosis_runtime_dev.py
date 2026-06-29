"""Internal/dev HTTP endpoint for Sales Diagnosis Assistant Runtime.

This is a development-only endpoint. It uses fake providers by default:
fake retrieval (no Milvus), fake LLM (no OpenAI/LiteLLM), in-memory state.
Production wiring (Postgres state, real Milvus, real LLM) is NOT active here.

Endpoint: POST /api/dev/sales-diagnosis-runtime/turn

State repository selection (env var):
- Default (unset or "inmemory"): InMemoryConversationStateRepository
- ``TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY=postgres``: uses PostgreSQL
  via psycopg 3 sync (requires TEAM360_DB_URL and migration 007 applied).
  This is an opt-in dev mode, not production.

Retrieval provider selection (env var):
- Default (unset or "fake"): _DevFakeRetrievalProvider (no Milvus)
- ``TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER=milvus``: uses
  MilvusRetrievalProvider with a dev fake embedding provider (no OpenAI).
  Requires TEAM360_MILVUS_URI or TEAM360_MILVUS_HOST.
- Invalid values: HTTP 500 controlled error

LLM provider selection (env var):
- Default (unset or "fake"): _DevFakeLLMProvider (no OpenAI/LiteLLM)
- ``TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER=litellm``: uses
  _DevLiteLLMProvider via LiteLLM proxy (requires TEAM360_LITELLM_BASE_URL
  and TEAM360_LITELLM_API_KEY).
- Invalid values: HTTP 500 controlled error
- Request metadata flag ``dev_test_unsafe_llm`` (bool) takes precedence over env var.

Request metadata flags:
- ``dev_test_unsafe_llm`` (bool): if true, uses a FakeLLMProvider that returns
  unsafe text to exercise guardrail policy. Dev-only, not for prod.
"""

from __future__ import annotations

import json as _json
import os

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR

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
from modules.automation_diagnosis.assistant_instances import get_assistant_instance_config
from modules.automation_diagnosis.litellm_client import LiteLLMClient
from modules.sales_diagnosis_runtime.milvus_provider import (
    MilvusRetrievalProvider,
    MilvusRuntimeConfig,
)
from modules.sales_diagnosis_runtime.policies import PromptPolicy
from modules.sales_diagnosis_runtime.providers import (
    LLMProvider,
    QueryEmbeddingProvider,
    RetrievalProvider,
)
from modules.sales_diagnosis_runtime.state_repository import (
    ConversationStateSerializer,
    InMemoryConversationStateRepository,
)

from .sales_diagnosis_runtime_schemas import DevTurnRequest, DevTurnResponse


# ---------------------------------------------------------------------------
# Prohibited identifier patterns
# ---------------------------------------------------------------------------

_PROHIBITED_CODES: frozenset[str] = frozenset({
    "vera_team360_sales_diagnosis",
    "pkg_vera_sales_diagnosis",
    "ks_vera_team360_sales_diagnosis",
    "svc_vera_sales_diagnosis",
})

# ---------------------------------------------------------------------------
# Fake providers for dev endpoint
# ---------------------------------------------------------------------------

_DEV_CHUNKS = [
    RetrievedChunk(
        chunk_id="dev_doc_1",
        document_id="dev_doc_1",
        knowledge_scope_id="ks_team360_sales_diagnosis",
        source_uri="/knowledge/dev/automation.md",
        title="Procesos automatizables",
        node_path="/ventas/automatizacion",
        score=0.92,
        content_preview="Los procesos de venta repetitivos son candidatos a automatizacion.",
        content="Los procesos de venta repetitivos, como la calificacion de leads "
        "y el envio de cotizaciones, son candidatos ideales para automatizacion.",
    ),
    RetrievedChunk(
        chunk_id="dev_doc_2",
        document_id="dev_doc_2",
        knowledge_scope_id="ks_team360_sales_diagnosis",
        source_uri="/knowledge/dev/crm.md",
        title="Integracion CRM",
        node_path="/ventas/crm",
        score=0.85,
        content_preview="Team360 se integra con CRM via API REST.",
        content="Team360 se integra con sistemas CRM externos mediante API REST "
        "estandar para sincronizar oportunidades y contactos.",
    ),
]


class _DevFakeRetrievalProvider:
    """Fake retrieval that returns controlled chunks, no Milvus."""

    def retrieve(self, input: AssistantTurnInput, state: ConversationState, top_k: int = 5, top_n: int = 20) -> list[RetrievedChunk]:
        return list(_DEV_CHUNKS)


class _DevFakeLLMProvider:
    """Fake LLM that returns safe ack text, no OpenAI/LiteLLM."""

    is_test_fallback = True

    def generate(self, input: AssistantTurnInput, state: ConversationState, context: list[RetrievedChunk]) -> str:
        from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT
        return SAFE_ACK_TEXT


_UNSAFE_RESPONSE = (
    "Tengo listo el lead_capture para empezar a capturar leads automaticamente "
    "y el WhatsApp handoff con SLA de 2 minutos."
)


class _DevUnsafeFakeLLMProvider:
    """Fake LLM that returns unsafe text to trigger guardrail rejection."""

    def generate(self, input: AssistantTurnInput, state: ConversationState, context: list[RetrievedChunk]) -> str:
        return _UNSAFE_RESPONSE


def _resolve_dev_display_name(instance_code: str) -> str:
    try:
        config = get_assistant_instance_config(instance_code)
        return config.assistant_display_name or "Diagnosticador"
    except ValueError:
        return "Diagnosticador"


class _DevLiteLLMProvider:
    """LiteLLM provider for dev endpoint via LiteLLM proxy.

    Requires TEAM360_LITELLM_BASE_URL and TEAM360_LITELLM_API_KEY.
    No OpenAI SDK — uses urllib via LiteLLMClient.
    """

    def __init__(self) -> None:
        self._client = self._build_client()
        self._prompt_policy = PromptPolicy()

    @staticmethod
    def _build_client() -> LiteLLMClient:
        base_url = os.environ.get("TEAM360_LITELLM_BASE_URL")
        if not base_url:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"{_DEV_LLM_PROVIDER_ENV}=litellm requires "
                    "TEAM360_LITELLM_BASE_URL."
                ),
            )
        api_key = (
            os.environ.get("TEAM360_LITELLM_API_KEY")
            or os.environ.get("LITELLM_API_KEY")
            or os.environ.get("LITELLM_MASTER_KEY")
        )
        if not api_key:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"{_DEV_LLM_PROVIDER_ENV}=litellm requires "
                    "TEAM360_LITELLM_API_KEY."
                ),
            )
        return LiteLLMClient(base_url=base_url, api_key=api_key)

    def generate(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        display_name = _resolve_dev_display_name(input.assistant_instance_code)
        system_prompt = self._prompt_policy.build_system_prompt(
            assistant_instance_code=input.assistant_instance_code,
            package_code=input.package_code,
            assistant_display_name=display_name,
        )
        turn_prompt = self._prompt_policy.build_turn_prompt(input, state, context)
        model = (
            os.environ.get("TEAM360_LITELLM_MODEL_ALIAS")
            or "openrouter_qwen3_30b_a3b_thinking_2507"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": turn_prompt},
        ]
        response = self._client.chat_completion(model=model, messages=messages)
        return response.content


class _DevFakeEmbeddingProvider:
    """Fake embedding that returns a static 1536-dim vector, no OpenAI."""

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * 1536


# ---------------------------------------------------------------------------
# State repository selection
# ---------------------------------------------------------------------------

_DEV_STATE_REPOSITORY_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_STATE_REPOSITORY"
_DEV_RETRIEVAL_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_RETRIEVAL_PROVIDER"
_DEV_LLM_PROVIDER_ENV = "TEAM360_SALES_DIAGNOSIS_DEV_LLM_PROVIDER"
_TABLE_NAME = "sales_diagnosis_conversation_states"

_shared_inmemory_repo = InMemoryConversationStateRepository()


class _DevPostgresStateRepository:
    """Sync PostgreSQL state repository for the dev endpoint.

    Uses psycopg 3 sync directly — no pool, no ORM.
    Opens a new connection per operation (acceptable for dev).
    Requires migration 007 applied on the target database.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def load(self, session_id: str) -> ConversationState | None:
        import psycopg
        from psycopg.rows import dict_row

        try:
            with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT state_jsonb FROM {_TABLE_NAME} "
                        f"WHERE session_id = %(sid)s",
                        {"sid": session_id},
                    )
                    row = cur.fetchone()
        except psycopg.Error:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Postgres state repository error: connection failed or table not found. "
                "Ensure TEAM360_DB_URL is correct and migration 007 is applied.",
            ) from None
        if row is None:
            return None
        raw = row["state_jsonb"]
        if isinstance(raw, str):
            raw = _json.loads(raw)
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Expected jsonb object for session_id={session_id!r}",
            )
        return ConversationStateSerializer.from_dict(raw)

    def save(self, state: ConversationState) -> None:
        import psycopg

        serialized = ConversationStateSerializer.to_dict(state)
        try:
            with psycopg.connect(self._dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {_TABLE_NAME} "
                        f"(session_id, assistant_instance_code, package_code, "
                        f"knowledge_scope_code, state_jsonb, "
                        f"created_at_utc, updated_at_utc) "
                        f"VALUES (%(session_id)s, %(assistant_instance_code)s, "
                        f"%(package_code)s, %(knowledge_scope_code)s, "
                        f"%(state_jsonb)s::jsonb, now(), now()) "
                        f"ON CONFLICT (session_id) DO UPDATE SET "
                        f"state_jsonb = EXCLUDED.state_jsonb, "
                        f"updated_at_utc = now()",
                        {
                            "session_id": serialized["session_id"],
                            "assistant_instance_code": serialized[
                                "assistant_instance_code"
                            ],
                            "package_code": serialized["package_code"],
                            "knowledge_scope_code": serialized[
                                "knowledge_scope_code"
                            ],
                            "state_jsonb": _json.dumps(serialized),
                        },
                    )
                conn.commit()
        except psycopg.Error:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Postgres state repository error: connection failed or table not found. "
                "Ensure TEAM360_DB_URL is correct and migration 007 is applied.",
            ) from None


def _resolve_state_repository():
    mode = os.environ.get(_DEV_STATE_REPOSITORY_ENV, "").strip().lower()
    if not mode or mode == "inmemory":
        return _shared_inmemory_repo
    if mode == "postgres":
        dsn = _resolve_postgres_dsn()
        return _DevPostgresStateRepository(dsn)
    raise HTTPException(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            f"Invalid {_DEV_STATE_REPOSITORY_ENV}={mode!r}. "
            "Use 'inmemory' (default) or 'postgres'."
        ),
    )


def _resolve_retrieval_provider() -> RetrievalProvider:
    mode = os.environ.get(_DEV_RETRIEVAL_PROVIDER_ENV, "").strip().lower()
    if not mode or mode == "fake":
        return _DevFakeRetrievalProvider()
    if mode == "milvus":
        config = MilvusRuntimeConfig.from_env()
        if not config.uri and not config.host:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Invalid {_DEV_RETRIEVAL_PROVIDER_ENV}={mode!r}. "
                    "Milvus mode requires TEAM360_MILVUS_URI or "
                    "TEAM360_MILVUS_HOST."
                ),
            )
        return MilvusRetrievalProvider(
            config=config,
            embedding_provider=_DevFakeEmbeddingProvider(),
        )
    raise HTTPException(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            f"Invalid {_DEV_RETRIEVAL_PROVIDER_ENV}={mode!r}. "
            "Use 'fake' (default) or 'milvus'."
        ),
    )


def _resolve_llm_provider(metadata: dict) -> LLMProvider:
    if metadata.get("dev_test_unsafe_llm"):
        return _DevUnsafeFakeLLMProvider()
    mode = os.environ.get(_DEV_LLM_PROVIDER_ENV, "").strip().lower()
    if not mode or mode == "fake":
        return _DevFakeLLMProvider()
    if mode == "litellm":
        return _DevLiteLLMProvider()
    raise HTTPException(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            f"Invalid {_DEV_LLM_PROVIDER_ENV}={mode!r}. "
            "Use 'fake' (default) or 'litellm'."
        ),
    )


def _resolve_postgres_dsn() -> str:
    from globalVar import get_team360_db_url_psql

    dsn = get_team360_db_url_psql()
    if not dsn:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"{_DEV_STATE_REPOSITORY_ENV}=postgres requires TEAM360_DB_URL. "
                "Set the environment variable or configure globalVar.py."
            ),
        )
    return dsn


# ---------------------------------------------------------------------------
# Runtime factory
# ---------------------------------------------------------------------------


def _build_dev_runtime(metadata: dict) -> AssistantConversationRuntime:
    return AssistantConversationRuntime(
        retrieval_provider=_resolve_retrieval_provider(),
        llm_provider=_resolve_llm_provider(metadata),
        state_repository=_resolve_state_repository(),
        prompt_policy=PromptPolicy(),
        guardrail_policy=GuardrailPolicy(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_codes(data: DevTurnRequest) -> None:
    for field_name in ("assistant_instance_code", "package_code", "knowledge_scope_code"):
        value = getattr(data, field_name, "")
        if value in _PROHIBITED_CODES:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Prohibited {field_name}: {value!r}. Use standard team360 codes.",
            )


def _chunk_to_dict(chunk: RetrievedChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "knowledge_scope_id": chunk.knowledge_scope_id,
        "source_uri": chunk.source_uri,
        "title": chunk.title,
        "node_path": chunk.node_path,
        "score": chunk.score,
        "content_preview": chunk.content_preview,
    }


def _event_to_dict(event) -> dict:
    return {
        "event_type": event.event_type,
        "elapsed_ms": event.elapsed_ms,
        "payload": event.payload,
        "safe_to_show": event.safe_to_show,
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@post("/api/dev/sales-diagnosis-runtime/turn")
async def dev_sales_diagnosis_turn(data: DevTurnRequest) -> dict:
    _validate_codes(data)

    runtime = _build_dev_runtime(data.metadata)

    input_ = AssistantTurnInput(
        session_id=data.session_id,
        assistant_instance_code=data.assistant_instance_code,
        package_code=data.package_code,
        knowledge_scope_code=data.knowledge_scope_code,
        user_message=data.message,
        channel=data.metadata.get("channel", "dev"),
        metadata=data.metadata,
    )

    try:
        output = runtime.handle_turn(input_)
    except UnsafeResponseError as exc:
        return DevTurnResponse(
            session_id=data.session_id,
            response_text=str(exc),
            response_type="unsafe_blocked",
            fallback_applied=False,
            guardrail_flags=["unsafe_response_blocked"],
            turn_count=0,
            runtime_mode="dev_fake",
        ).model_dump()
    except InvalidAssistantRuntimeInputError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc))

    guardrail_flags: list[str] = []
    if output.guardrail_result.fallback_applied:
        guardrail_flags.append("fallback_applied")
    if output.guardrail_result.max_questions_exceeded:
        guardrail_flags.append("max_questions_exceeded")
    if output.guardrail_result.pricing_sla_hallucination:
        guardrail_flags.append("pricing_sla_hallucination")

    turn_count = output.next_state.turn_count if output.next_state else 0

    return DevTurnResponse(
        session_id=data.session_id,
        response_text=output.response_text,
        response_type=output.response_type,
        fallback_applied=output.guardrail_result.fallback_applied,
        guardrail_flags=guardrail_flags,
        retrieved_sources=[_chunk_to_dict(c) for c in output.retrieved_sources],
        turn_count=turn_count,
        events=[_event_to_dict(e) for e in output.events],
        runtime_mode="dev_fake",
    ).model_dump()

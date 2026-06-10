from __future__ import annotations

from dataclasses import replace
from typing import Any, Protocol

from modules.sales_diagnosis_runtime.contracts import (
    AssistantTurnInput,
    AssistantTurnOutput,
    ConversationState,
    RetrievedChunk,
    RuntimeMetrics,
)


# ---------------------------------------------------------------------------
# RetrievalProvider
# ---------------------------------------------------------------------------


class RetrievalProvider(Protocol):
    def retrieve(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        top_k: int = 5,
        top_n: int = 20,
    ) -> list[RetrievedChunk]:
        ...


class NullRetrievalProvider:
    """Skeleton provider that returns an empty list.

    Used for testing and development before Milvus integration.
    """

    def retrieve(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        top_k: int = 5,
        top_n: int = 20,
    ) -> list[RetrievedChunk]:
        return []


# ---------------------------------------------------------------------------
# LLMProvider
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    def generate(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        ...


class NullLLMProvider:
    """Skeleton provider that returns the safe ack text.

    Used for testing and development before gpt-5-nano integration.
    """

    def generate(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT

        return SAFE_ACK_TEXT


# ---------------------------------------------------------------------------
# StateRepository
# ---------------------------------------------------------------------------


class StateRepository(Protocol):
    def load(self, session_id: str) -> ConversationState | None:
        ...

    def save(self, state: ConversationState) -> None:
        ...


class InMemoryStateRepository:
    """In-memory state repository for testing and development."""

    def __init__(self) -> None:
        self._store: dict[str, ConversationState] = {}

    def load(self, session_id: str) -> ConversationState | None:
        return self._store.get(session_id)

    def save(self, state: ConversationState) -> None:
        self._store[state.session_id] = replace(state)


# ---------------------------------------------------------------------------
# MetricsRecorder
# ---------------------------------------------------------------------------


class MetricsRecorder(Protocol):
    def record_turn(
        self,
        input: AssistantTurnInput,
        output: AssistantTurnOutput,
    ) -> None:
        ...


class NullMetricsRecorder:
    """Skeleton metrics recorder that discards all data."""

    def record_turn(
        self,
        input: AssistantTurnInput,
        output: AssistantTurnOutput,
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------


class AuditTrail(Protocol):
    def record(
        self,
        input: AssistantTurnInput,
        output: AssistantTurnOutput,
    ) -> None:
        ...


class NullAuditTrail:
    """Skeleton audit trail that discards all data."""

    def record(
        self,
        input: AssistantTurnInput,
        output: AssistantTurnOutput,
    ) -> None:
        pass

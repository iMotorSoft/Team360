"""Minimal persistent state machine for citizen intake conversations."""

from enum import StrEnum


class ConversationState(StrEnum):
    RECEIVED = "RECEIVED"
    INTERPRETED = "INTERPRETED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    PENDING_CLARIFICATION = "PENDING_CLARIFICATION"
    CORRECTED = "CORRECTED"
    CONFIRMED = "CONFIRMED"


class InvalidStateTransition(ValueError):
    """Raised when application code attempts an undefined transition."""


_ALLOWED: dict[ConversationState, frozenset[ConversationState]] = {
    ConversationState.RECEIVED: frozenset(
        {ConversationState.INTERPRETED, ConversationState.PENDING_CLARIFICATION}
    ),
    ConversationState.INTERPRETED: frozenset(
        {ConversationState.PENDING_CONFIRMATION, ConversationState.PENDING_CLARIFICATION}
    ),
    ConversationState.PENDING_CONFIRMATION: frozenset(
        {
            ConversationState.CONFIRMED,
            ConversationState.CORRECTED,
            ConversationState.PENDING_CLARIFICATION,
        }
    ),
    ConversationState.PENDING_CLARIFICATION: frozenset(
        {
            ConversationState.CORRECTED,
            ConversationState.INTERPRETED,
            ConversationState.CONFIRMED,
        }
    ),
    ConversationState.CORRECTED: frozenset(
        {ConversationState.INTERPRETED, ConversationState.PENDING_CLARIFICATION}
    ),
    ConversationState.CONFIRMED: frozenset(),
}


def transition(current: ConversationState, target: ConversationState) -> ConversationState:
    if target not in _ALLOWED[current]:
        raise InvalidStateTransition(f"Invalid Flow transition: {current} -> {target}")
    return target

import pytest

from modules.flow.domain import ConversationState, InvalidStateTransition, transition


def test_received_to_pending_confirmation_via_interpreted():
    state = transition(ConversationState.RECEIVED, ConversationState.INTERPRETED)
    assert transition(state, ConversationState.PENDING_CONFIRMATION) == ConversationState.PENDING_CONFIRMATION


def test_pending_confirmation_to_confirmed():
    assert transition(
        ConversationState.PENDING_CONFIRMATION, ConversationState.CONFIRMED
    ) == ConversationState.CONFIRMED


def test_pending_confirmation_to_corrected_and_reinterpret():
    corrected = transition(
        ConversationState.PENDING_CONFIRMATION, ConversationState.CORRECTED
    )
    assert transition(corrected, ConversationState.INTERPRETED) == ConversationState.INTERPRETED


def test_pending_clarification_can_confirm_existing_candidates():
    assert transition(
        ConversationState.PENDING_CLARIFICATION, ConversationState.CONFIRMED
    ) == ConversationState.CONFIRMED


def test_invalid_transition_is_rejected():
    with pytest.raises(InvalidStateTransition):
        transition(ConversationState.RECEIVED, ConversationState.CONFIRMED)

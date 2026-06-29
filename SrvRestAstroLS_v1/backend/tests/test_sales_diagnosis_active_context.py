from __future__ import annotations

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    InMemoryStateRepository,
)
from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT


class FallbackLLM:
    model_name = "test-fallback"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, input, state, context):
        self.calls += 1
        return SAFE_ACK_TEXT


class FixedLLM(FallbackLLM):
    def __init__(self, response: str) -> None:
        super().__init__()
        self.response = response

    def generate(self, input, state, context):
        self.calls += 1
        return self.response


def active_management_state(session_id: str) -> ConversationState:
    return ConversationState(
        session_id=session_id,
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_test",
        turn_count=2,
        slots={"management_system_choice_status": "offered"},
        semantic_memory={
            "diagnosis_status": "gathering",
            "channels": ["email"],
            "current_process": "postventa por email",
            "main_problem": "muchos emails de postventa",
            "systems_and_data_sources": [],
            "_messages": ["Recibo muchos emails", "Postventa"],
        },
        asked_questions=[
            {
                "intent": "clarify_current_process",
                "question_text": "¿Dónde se registran y siguen hoy los emails?",
                "turn": 2,
                "answered": False,
                "answer_evidence": "",
            }
        ],
    )


def run_active_answer(message: str, *, interaction_response: dict | None = None):
    session_id = f"active-{abs(hash((message, str(interaction_response))))}"
    repo = InMemoryStateRepository()
    repo.save(active_management_state(session_id))
    llm = FallbackLLM()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
    output = runtime.handle_turn(
        AssistantTurnInput(
            session_id=session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message=message,
            metadata={"interaction_response": interaction_response}
            if interaction_response
            else {},
        )
    )
    return output, llm


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Solo en la bandeja de email", "email_inbox"),
        ("En la bandeja de email", "email_inbox"),
        ("Bandeja de email", "email_inbox"),
        ("En el mail", "email_inbox"),
        ("Email", "email_inbox"),
        ("En Gmail", "email_inbox"),
        ("En Outlook", "email_inbox"),
        ("Solo por email", "email_inbox"),
        ("Sistema propio", "custom_system"),
        ("Sistema interno", "custom_system"),
        ("CRM propio", "custom_system"),
        ("Sistema de la empresa", "custom_system"),
        ("Una app propia", "custom_system"),
        ("Un sistema nuestro", "custom_system"),
        ("No usamos sistema", "none"),
        ("No tenemos sistema", "none"),
        ("Lo hacen a mano", "none"),
        ("Lo revisa alguien a mano", "none"),
        ("Alguien revisa a mano", "none"),
        ("Manual", "none"),
        ("Planilla", "spreadsheet"),
        ("Excel", "spreadsheet"),
        ("Planilla / Excel", "spreadsheet"),
        ("Google Sheets", "spreadsheet"),
        ("Sheets", "spreadsheet"),
    ],
)
def test_active_management_question_resolves_short_text_without_llm_fallback(
    message: str,
    expected: str,
):
    output, llm = run_active_answer(message)

    assert output.next_state is not None
    assert output.next_state.slots["management_system"] == expected
    assert output.next_state.slots["management_system_choice_status"] == "answered"
    assert output.response_text != SAFE_ACK_TEXT
    assert output.turn_decision["generation"]["fallback_used"] is False
    assert llm.calls == 0
    assert output.interaction_block is None or output.interaction_block["type"] != "single_choice"


def test_written_option_label_is_equivalent_to_single_choice_click():
    text_output, text_llm = run_active_answer("Sistema propio")
    click_output, click_llm = run_active_answer(
        "Sistema de gestión que uso actualmente: Sistema propio.",
        interaction_response={
            "block_type": "single_choice",
            "action_id": "submit_management_system",
            "option_id": "custom_system",
            "value": "custom_system",
            "label": "Sistema propio",
        },
    )

    assert text_output.next_state is not None
    assert click_output.next_state is not None
    assert text_output.next_state.slots["management_system"] == "custom_system"
    assert text_output.next_state.slots["management_system"] == click_output.next_state.slots["management_system"]
    assert text_output.next_state.slots["management_system_label"] == click_output.next_state.slots["management_system_label"]
    assert text_output.next_state.slots["management_system_choice_status"] == "answered"
    assert click_output.next_state.slots["management_system_choice_status"] == "answered"
    assert text_llm.calls == click_llm.calls == 0


def test_management_label_reaffirmation_and_correction_remain_deterministic():
    session_id = "active-management-correction"
    repo = InMemoryStateRepository()
    state = active_management_state(session_id)
    state.slots.update(
        {
            "management_system": "email_inbox",
            "management_system_label": "Solo en la bandeja de email",
            "management_system_choice_status": "answered",
            "automation_goals_choice_status": "offered",
            "multi_choice_shown": True,
        }
    )
    state.semantic_memory["systems_and_data_sources"] = [
        "Solo en la bandeja de email"
    ]
    repo.save(state)
    llm = FallbackLLM()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)

    for message, expected in (
        ("En la bandeja de email", "email_inbox"),
        ("Sistema propio", "custom_system"),
    ):
        output = runtime.handle_turn(
            AssistantTurnInput(
                session_id=session_id,
                assistant_instance_code="team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                knowledge_scope_code="ks_test",
                user_message=message,
            )
        )
        assert output.next_state is not None
        assert output.next_state.slots["management_system"] == expected
        assert output.response_text != SAFE_ACK_TEXT
        assert output.turn_decision["generation"]["fallback_used"] is False
        assert output.turn_decision["generation"]["provider_called"] is False

    assert llm.calls == 0


def test_unresolved_active_answer_uses_contextual_clarification_not_generic_fallback():
    output, llm = run_active_answer("En un correo compartido")

    assert output.next_state is not None
    assert output.next_state.slots["management_system_choice_status"] == "offered"
    assert output.response_text != SAFE_ACK_TEXT
    assert "bandeja de email" in output.response_text.lower()
    assert "planilla" in output.response_text.lower()
    assert "sistema propio" in output.response_text.lower()
    assert output.turn_decision["generation"]["fallback_used"] is False
    assert output.turn_decision["generation"]["provider_fallback_used"] is True
    assert llm.calls == 1


@pytest.mark.parametrize(
    "provider_response",
    [
        SAFE_ACK_TEXT,
        "Te garantizo cobertura total y un SLA inmediato para postventa.",
    ],
)
def test_short_answer_to_active_question_recovers_context_without_generic_fallback(
    provider_response: str,
):
    session_id = f"active-domain-{len(provider_response)}"
    repo = InMemoryStateRepository()
    repo.save(
        ConversationState(
            session_id=session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=1,
            semantic_memory={
                "diagnosis_status": "gathering",
                "channels": ["email"],
                "main_problem": "muchos emails",
                "systems_and_data_sources": [],
            },
            asked_questions=[
                {
                    "intent": "identify_email_domain",
                    "question_text": "¿Qué tipo de emails son principalmente?",
                    "turn": 1,
                    "answered": False,
                    "answer_evidence": "",
                }
            ],
        )
    )
    llm = FixedLLM(provider_response)
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)

    output = runtime.handle_turn(
        AssistantTurnInput(
            session_id=session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="Postventa",
        )
    )

    assert output.next_state is not None
    assert output.next_state.turn_count == 2
    assert output.next_state.asked_questions[0]["answered"] is True
    assert output.next_state.asked_questions[0]["answer_evidence"] == "Postventa"
    assert output.response_text != SAFE_ACK_TEXT
    assert "Postventa" in output.response_text
    assert output.turn_decision["generation"]["fallback_used"] is False
    assert output.turn_decision["generation"]["recovery_used"] is True
    assert output.interaction_block is not None
    assert output.interaction_block["type"] == "single_choice"
    assert llm.calls == 1

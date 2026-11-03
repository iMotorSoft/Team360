"""Deterministic replay of the Full Gate's post-close request (no services).

The gate recorded a required human-review policy, not an approval event.
The prompt-driven double isolates routing/instructions, not LLM quality.
"""
import copy
import json
import os
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime.contracts import AssistantTurnInput
from modules.sales_diagnosis_runtime.intent_classifier import (
    IntentClassification, IntentScope, IntentSource, IntentType,
)
from modules.sales_diagnosis_runtime.policies import PromptPolicy
from modules.sales_diagnosis_runtime.runtime import AssistantConversationRuntime
from modules.sales_diagnosis_runtime.state_repository import (
    ConversationStateSerializer, InMemoryConversationStateRepository,
)


MESSAGES = (
    "Caso sintético de prueba. Tenemos una tienda y queremos automatizar consultas de stock y precios recibidas por email. Stock en sistema y precios en planilla. Son 20 consultas diarias y una persona aprueba toda respuesta. No ejecutes acciones.",
    "El objetivo es reducir trabajo manual en consultas de ventas. Usamos email y Excel. La aprobación humana es obligatoria. Con estos datos cerrá un diagnóstico de factibilidad; no envíes comunicaciones ni pidas credenciales.",
    "Dame ahora el diagnóstico final de factibilidad y un próximo paso concreto, sin implementar ni enviar nada.",
)
QUESTION = "¿Qué respuestas requieren aprobación humana?"
ANSWER = "Factibilidad alta en modo asistido. Una persona aprueba toda respuesta. Próximo paso: analizar el flujo, sin implementar."


class JsonRepository(InMemoryConversationStateRepository):
    """Actual JSON round trip: no shared mutable objects between turns."""

    def save(self, state):
        self._store[state.session_id] = json.loads(json.dumps(
            ConversationStateSerializer.to_dict(state)))


class GateClassifier:
    def classify(self, message, state):
        intent = (IntentType.REQUEST_DIAGNOSIS if message in MESSAGES[1:]
                  else IntentType.PROVIDE_INFORMATION)
        return IntentClassification(intent=intent, scope=IntentScope.GLOBAL,
                                    confidence=0.93, source=IntentSource.AI_CLASSIFIER)


class PromptDrivenProvider:
    def __init__(self):
        self.calls = []

    def generate(self, input, state, context):
        prompt = PromptPolicy().build_turn_prompt(input, state, context)
        # Deterministically obey the conflicting instruction found in the gate path.
        response = (QUESTION if "- Hacé UNA pregunta concreta" in prompt
                    or "ACCIÓN: SEGUIR PREGUNTANDO" in prompt else ANSWER)
        self.calls.append({"state": copy.deepcopy(state.semantic_memory),
                           "input": input.user_message, "prompt": prompt,
                           "raw_output": response})
        return response


def turn(runtime, session, message):
    return runtime.handle_turn(AssistantTurnInput(
        session_id=session, assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis", knowledge_scope_code="ks_team360_sales_diagnosis",
        user_message=message,
    ))


def replay(repo=None):
    repo, provider, session = repo or JsonRepository(), PromptDrivenProvider(), str(uuid4())
    runtime = AssistantConversationRuntime(state_repository=repo,
        llm_provider=provider, intent_classifier=GateClassifier())
    outputs = [turn(runtime, session, msg) for msg in MESSAGES]
    return repo, provider, session, outputs


def test_exact_gate_post_close_request():
    repo, provider, session, outputs = replay()
    assert provider.calls[1]["state"]["human_approval"] == "required"
    assert outputs[1].next_state.semantic_memory["diagnosis_status"] == "completed"
    assert provider.calls[2]["state"]["diagnosis_status"] == "completed"
    assert provider.calls[2]["state"]["human_approval"] == "required"
    assert outputs[2].turn_decision["action"] == "diagnose"
    assert "ACCIÓN: DIAGNÓSTICO ESTRUCTURADO" in provider.calls[2]["prompt"]
    assert "- Hacé UNA pregunta concreta" not in provider.calls[2]["prompt"]
    assert outputs[2].response_text == ANSWER
    assert "?" not in outputs[2].response_text
    assert outputs[2].diagnosis["human_approval"] == "required"
    assert repo.load(session).turn_count == 3
    assert "_runtime_diagnose" not in repo.load(session).semantic_memory


def test_persist_reload_required_approval_and_close():
    repo, provider, session, outputs = replay()
    loaded = repo.load(session)
    assert loaded.semantic_memory["human_approval"] == "required"
    assert loaded.semantic_memory["diagnosis_status"] == "completed"
    assert loaded.semantic_memory["last_structured_diagnosis"]["human_approval"] == "required"
    # Fresh runtime, not merely reuse of its in-memory state.
    runtime = AssistantConversationRuntime(state_repository=repo,
        llm_provider=provider, intent_classifier=GateClassifier())
    result = turn(runtime, session, MESSAGES[2])
    assert result.turn_decision["action"] == "diagnose"
    assert repo.load(session).semantic_memory["diagnosis_status"] == "completed"
    assert repo.load(session).semantic_memory["human_approval"] == "required"
    assert result.response_text == ANSWER


@pytest.mark.parametrize("intent", [IntentType.PROVIDE_INFORMATION,
    IntentType.ASK_POINT_QUESTION, IntentType.CORRECT_PREVIOUS_INFORMATION,
    IntentType.UNCLEAR])
def test_completed_state_not_reopened_by_other_intents(intent):
    repo, _, session, _ = replay()
    state = repo.load(session)
    runtime = AssistantConversationRuntime()
    classification = IntentClassification(intent=intent, scope=IntentScope.GLOBAL,
                                           confidence=0.99)
    assert runtime._decide_turn(classification, state) is False
    assert state.semantic_memory["diagnosis_status"] == "completed"
    assert state.semantic_memory["human_approval"] == "required"


def test_repeated_required_policy_is_idempotent():
    repo, provider, session, _ = replay()
    runtime = AssistantConversationRuntime(state_repository=repo,
        llm_provider=provider, intent_classifier=GateClassifier())
    for _ in range(2):
        result = turn(runtime, session, "La aprobación humana es obligatoria.")
        assert result.next_state.semantic_memory["human_approval"] == "required"
        assert result.next_state.semantic_memory["diagnosis_status"] == "completed"
        assert result.turn_decision["action"] == "reflect_and_ask"
        assert result.response_text == ANSWER
        assert "no reabras la entrevista" in provider.calls[-1]["prompt"]
        assert "no pidas confirmarla otra vez" in provider.calls[-1]["prompt"]


@pytest.mark.parametrize("scope,confidence,expected", [
    (IntentScope.GLOBAL, 0.93, True),
    (IntentScope.POINT_QUESTION, 0.99, False),
    (IntentScope.GLOBAL, 0.1, False),
])
def test_completed_request_routes_without_state_transition(scope, confidence, expected):
    repo, _, session, _ = replay()
    state = repo.load(session)
    before = copy.deepcopy(state.semantic_memory)
    intent = IntentClassification(intent=IntentType.REQUEST_DIAGNOSIS,
                                  scope=scope, confidence=confidence)
    assert AssistantConversationRuntime()._decide_turn(intent, state) is expected
    assert state.semantic_memory == before


def test_unconfirmed_policy_still_allows_gathering_question():
    repo, provider = JsonRepository(), PromptDrivenProvider()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=provider)
    result = turn(runtime, str(uuid4()), "Tenemos una tienda.")
    assert not result.next_state.semantic_memory.get("human_approval")
    assert result.next_state.semantic_memory["diagnosis_status"] == "gathering"
    assert result.response_text == QUESTION


@pytest.mark.skipif(os.getenv("TEAM360_DIAGNOSIS_POST_CLOSE_POSTGRES_TEST") != "1",
                    reason="Explicit isolated PostgreSQL test opt-in required")
def test_post_close_real_postgres_round_trip():
    import psycopg
    from globalVar import get_team360_db_url_psql
    from modules.sales_diagnosis_runtime.state_repository import (
        SyncPostgresConversationStateRepository,
    )

    dsn = get_team360_db_url_psql()
    repo = SyncPostgresConversationStateRepository(dsn)
    session = str(uuid4())
    provider = PromptDrivenProvider()
    runtime = AssistantConversationRuntime(state_repository=repo,
        llm_provider=provider, intent_classifier=GateClassifier())
    previous_timestamp = None
    try:
        for i, message in enumerate(MESSAGES, 1):
            result = turn(runtime, session, message)
            # Separate DB connection + repository, beyond transaction commit.
            loaded = SyncPostgresConversationStateRepository(dsn).load(session)
            assert loaded.turn_count == i
            with psycopg.connect(dsn) as conn:
                created, updated = conn.execute(
                    "SELECT created_at_utc, updated_at_utc FROM "
                    "sales_diagnosis_conversation_states WHERE session_id = %s",
                    (session,),
                ).fetchone()
            assert updated >= created
            if previous_timestamp:
                assert updated >= previous_timestamp
            previous_timestamp = updated
            if i >= 2:
                assert loaded.semantic_memory["human_approval"] == "required"
                assert loaded.semantic_memory["diagnosis_status"] == "completed"
            if i == 3:
                assert result.turn_decision["action"] == "diagnose"
                assert result.response_text == ANSWER
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute("DELETE FROM sales_diagnosis_conversation_states "
                         "WHERE session_id = %s", (session,))
        assert repo.load(session) is None

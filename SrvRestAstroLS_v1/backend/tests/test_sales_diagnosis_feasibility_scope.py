from __future__ import annotations

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    InMemoryStateRepository,
)
from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT
from modules.sales_diagnosis_runtime.providers import NullRetrievalProvider


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


def _make_runtime(llm=None) -> AssistantConversationRuntime:
    repo = InMemoryStateRepository()
    return AssistantConversationRuntime(
        state_repository=repo,
        retrieval_provider=NullRetrievalProvider(),
        intent_classifier=None,
        llm_provider=llm or FixedLLM("respuesta de prueba"),
    )


def _turn(runtime, state, message: str) -> ConversationState:
    repo = runtime._state_repo
    repo.save(state)
    output = runtime.handle_turn(
        AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_team360_sales_diagnosis",
            user_message=message,
        )
    )
    return output.next_state


# ---------------------------------------------------------------------------
# Feasibility scope tests
# ---------------------------------------------------------------------------


def _make_feasibility_sufficient_state(session_id: str, extra: dict | None = None) -> ConversationState:
    """Build a state that has enough data for feasibility diagnosis.

    Channel = email, system = planilla, process = facturacion, objective = derivar.
    One extra signal (volume = 50/dia) makes it sufficient.
    """
    slots = {
        "management_system_choice_status": "answered",
        "management_system": "spreadsheet",
        "management_system_label": "Planilla / Excel",
        "automation_goals_choice_status": "offered",
    }
    mem = {
        "diagnosis_status": "gathering",
        "channels": ["email"],
        "current_process": "derivar casos de facturacion segun el asunto",
        "main_problem": "recibir muchos emails de facturacion",
        "systems_and_data_sources": ["Planilla / Excel"],
        "volume": {"value": 50, "unit": "emails", "period": "dia"},
        "_messages": [
            "recibo muchos email",
            "facturacion",
            "Planilla / Excel",
            "Derivar casos a una persona",
            "50 por dia",
        ],
    }
    if extra:
        mem.update(extra)
    return ConversationState(
        session_id=session_id,
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_test",
        turn_count=5,
        slots=slots,
        semantic_memory=mem,
    )


class TestFeasibilityScopeDiagnose:

    def test_is_ready_with_channel_system_process_volume(self):
        """channel=email + system=planilla + process=facturacion + volume = sufficient."""
        state = _make_feasibility_sufficient_state("s1")
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True
        assert state.semantic_memory.get("diagnosis_status") == "sufficient"

    def test_is_ready_with_channel_system_process_approval(self):
        """channel + system + process + human_approval = sufficient."""
        state = _make_feasibility_sufficient_state("s2", {
            "human_approval": "conditional",
            "volume": {},
        })
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True
        assert state.semantic_memory.get("diagnosis_status") == "sufficient"

    def test_is_ready_with_channel_system_goals_volume(self):
        """channel + system + automation_goals + volume = sufficient (no explicit process)."""
        state = _make_feasibility_sufficient_state("s3", {
            "current_process": "",
            "main_problem": "",
        })
        state.slots["automation_goals"] = ["classify", "escalate"]
        state.slots["automation_goals_labels"] = ["Clasificar", "Derivar"]
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True

    def test_not_ready_with_only_channel(self):
        """Only channel = not sufficient."""
        state = _make_feasibility_sufficient_state("s4", {
            "current_process": "",
            "main_problem": "",
            "systems_and_data_sources": [],
            "volume": {},
            "human_approval": "",
        })
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is False

    def test_decide_turn_returns_true_when_sufficient(self):
        """decide_turn returns True when status is already 'sufficient'."""
        state = _make_feasibility_sufficient_state("s5")
        state.semantic_memory["diagnosis_status"] = "sufficient"
        runtime = _make_runtime()
        from modules.sales_diagnosis_runtime.intent_classifier import IntentClassification, IntentType, IntentScope, IntentSource
        intent = IntentClassification(
            intent=IntentType.PROVIDE_INFORMATION,
            scope=IntentScope.GLOBAL,
            confidence=0.5,
            source=IntentSource.RUNTIME_FALLBACK,
        )
        assert runtime._decide_turn(intent, state) is True

    def test_missing_requirements_separates_implementation_when_sufficient(self):
        """missing_requirements block filters out implementation items when sufficient."""
        state = _make_feasibility_sufficient_state("s6")
        state.semantic_memory["diagnosis_status"] = "sufficient"
        runtime = _make_runtime()
        block = runtime._build_missing_requirements_block(state, should_diagnose=False)
        assert block is not None
        assert block["type"] == "missing_requirements"
        req_ids = [r["id"] for r in block["requirements"]]
        assert "channel" in req_ids
        assert "management_system" in req_ids
        assert "current_process" in req_ids
        impl_items = [r for r in block["requirements"] if r.get("required_for") == "implementation"]
        assert len(impl_items) == 0, f"Should not have standalone implementation items: {impl_items}"
        grouped_impl = [r for r in block["requirements"] if r.get("id") == "implementation_details"]
        assert len(grouped_impl) == 1
        assert "post_diagnosis" in grouped_impl[0].get("required_for", "")
        assert "análisis de flujo" in grouped_impl[0].get("note", "")


class TestFeasibilityScopeVariants:

    def test_email_facturacion_registrar(self):
        """Variant A: email + facturacion + planilla + registrar + volumen."""
        state = ConversationState(
            session_id="vA",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            slots={
                "management_system_choice_status": "answered",
                "management_system": "spreadsheet",
                "management_system_label": "Planilla / Excel",
            },
            semantic_memory={
                "diagnosis_status": "gathering",
                "channels": ["email"],
                "current_process": "registrar y dejar listo",
                "systems_and_data_sources": ["Planilla / Excel"],
                "volume": {"value": 50, "unit": "emails", "period": "dia"},
                "_messages": [
                    "recibo muchos email",
                    "facturacion",
                    "Planilla / Excel",
                    "registrar y dejar listo",
                    "50 por dia",
                ],
            },
        )
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True

    def test_whatsapp_turnos_manual(self):
        """Variant B: whatsapp + turnos + manual + volumen."""
        state = ConversationState(
            session_id="vB",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            slots={
                "management_system_choice_status": "answered",
                "management_system": "none",
                "management_system_label": "No hay sistema",
            },
            semantic_memory={
                "diagnosis_status": "gathering",
                "channels": ["whatsapp"],
                "current_process": "pedir turnos",
                "main_problem": "recibo muchos whatsapp para turnos",
                "systems_and_data_sources": ["manual"],
                "volume": {"value": 30, "unit": "mensajes", "period": "dia"},
                "_messages": [
                    "recibo muchos whatsapp",
                    "pedir turnos",
                    "lo cargo manual",
                    "30 por dia",
                ],
            },
        )
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True

    def test_sap_bancos_diferencias(self):
        """Variant C: SAP + bancos + diferencias + revision humana."""
        state = ConversationState(
            session_id="vC",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            slots={
                "management_system_choice_status": "answered",
                "management_system": "crm",
                "management_system_label": "SAP",
            },
            semantic_memory={
                "diagnosis_status": "gathering",
                "channels": ["email"],
                "current_process": "encontrar diferencias en extractos bancarios de 3 bancos",
                "main_problem": "Tengo SAP y extractos bancarios, quiero encontrar diferencias",
                "systems_and_data_sources": ["SAP", "extractos bancarios"],
                "human_approval": "required",
                "volume": {"value": 50, "unit": "movimientos", "period": "dia"},
                "_messages": [
                    "Tengo SAP y extractos bancarios de 3 bancos",
                    "Quiero encontrar diferencias en forma automatica",
                    "Alguien revisa a mano",
                    "50 movimientos por dia",
                ],
            },
        )
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True

    def test_kommo_leads_whatsapp(self):
        """Variant D: Kommo + leads + whatsapp + revision manual."""
        state = ConversationState(
            session_id="vD",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            slots={
                "management_system_choice_status": "answered",
                "management_system": "crm",
                "management_system_label": "Kommo",
            },
            semantic_memory={
                "diagnosis_status": "gathering",
                "channels": ["whatsapp"],
                "current_process": "saber quien sigue los leads",
                "main_problem": "me llegan leads por WhatsApp a Kommo",
                "systems_and_data_sources": ["Kommo"],
                "human_approval": "conditional",
                "volume": {"value": 100, "unit": "leads", "period": "semana"},
                "_messages": [
                    "me llegan leads por WhatsApp a Kommo",
                    "quiero saber quien los sigue",
                    "lo revisan manualmente",
                    "100 por semana",
                ],
            },
        )
        runtime = _make_runtime()
        assert runtime._is_ready_to_diagnose(state) is True


class TestFeasibilityScopeNegative:

    def test_missing_requirements_blocks_implementation_items(self):
        """When sufficient, build_missing_requirements should NOT contain standalone
        implementation items like 'approval_rules' in the requirements list."""
        state = _make_feasibility_sufficient_state("neg1")
        state.semantic_memory["diagnosis_status"] = "sufficient"
        runtime = _make_runtime()
        block = runtime._build_missing_requirements_block(state, should_diagnose=False)
        if block:
            for req in block["requirements"]:
                assert req.get("id") != "approval_rules", (
                    f"Standalone implementation item 'approval_rules' found in requirements: {block}"
                )

    def test_pause_block_shows_feasibility_title_when_sufficient(self):
        """Pause block adjusts title when status is sufficient."""
        state = _make_feasibility_sufficient_state("neg2")
        state.semantic_memory["diagnosis_status"] = "sufficient"
        runtime = _make_runtime()
        block = runtime._build_pause_block(should_pause=True, state=state)
        assert block is not None
        assert "factibilidad" in block["title"].lower()

    def test_next_step_choice_shows_feasibility_title_when_sufficient(self):
        """next_step_choice block adjusts title when status is sufficient."""
        state = _make_feasibility_sufficient_state("neg3")
        state.semantic_memory["diagnosis_status"] = "sufficient"
        runtime = _make_runtime()
        block = runtime._build_next_step_choice_if_ready(should_diagnose=True, state=state)
        assert block is not None
        assert "factibilidad" in block["title"].lower()

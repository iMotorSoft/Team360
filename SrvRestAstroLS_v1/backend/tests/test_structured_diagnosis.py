"""Tests for structured diagnosis: builder, contract, public API, persistence, multilingual.

No network calls. No DB. No LLM. No Milvus.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    DIAGNOSIS_VERSION,
    InMemoryStateRepository,
    StructuredDiagnosis,
)
from modules.sales_diagnosis_runtime.structured_diagnosis import (
    _build_next_step,
    _determine_automation_mode,
    _determine_availability,
    _determine_confidence,
    _determine_feasibility,
    _has_closed_software,
    _has_mfa,
    _has_sensitive_decision,
    build_structured_diagnosis,
    format_structured_diagnosis_for_prompt,
)
from modules.sales_diagnosis_runtime.intent_classifier import (
    IntentClassification,
    IntentScope,
    IntentSource,
    IntentType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RecordingLLM:
    model_name: str | None = "test-model"

    def __init__(self, response: str = "Diagnóstico listo.") -> None:
        self._response = response
        self.calls: list[dict] = []

    def generate(self, input, state, context):
        self.calls.append({
            "message": input.user_message,
            "status": state.semantic_memory.get("diagnosis_status"),
            "has_structured_diagnosis": "last_structured_diagnosis" in state.semantic_memory,
        })
        return self._response


def _diagnosis_ready_state(**overrides) -> ConversationState:
    base = {
        "diagnosis_status": "gathering",
        "current_process": "consultas de venta por WhatsApp y Gmail",
        "channels": ["whatsapp", "gmail"],
        "systems_and_data_sources": ["erp", "spreadsheet"],
        "entities": ["inventory", "prices"],
        "entity_sources": {"inventory": "erp", "prices": "spreadsheet"},
        "human_approval": "conditional",
        "volume": {"value": 80, "unit": "inquiry", "period": "day"},
    }
    base.update(overrides)
    return ConversationState(
        session_id=str(uuid4()),
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_test",
        semantic_memory=base,
    )


# ===================================================================
# 1. StructuredDiagnosis contract
# ===================================================================


class TestStructuredDiagnosisContract:
    def test_default_values(self):
        sd = StructuredDiagnosis()
        assert sd.feasibility == "needs_validation"
        assert sd.automation_mode == "not_recommended"
        assert sd.confidence == "low"
        assert sd.human_approval == "unknown"
        assert sd.availability == "requires_validation"
        assert sd.version == "v1"
        assert sd.channels == []
        assert sd.systems == []
        assert sd.risks == []
        assert sd.assumptions == []
        assert sd.validation_points == []

    def test_serializable_to_dict(self):
        sd = StructuredDiagnosis(
            feasibility="high",
            automation_mode="human_in_the_loop",
            channels=["whatsapp"],
            systems=["erp"],
        )
        d = asdict(sd)
        assert d["feasibility"] == "high"
        assert d["automation_mode"] == "human_in_the_loop"
        assert d["channels"] == ["whatsapp"]
        assert d["version"] == DIAGNOSIS_VERSION

    def test_diagnosis_version_constant(self):
        assert DIAGNOSIS_VERSION == "v1"


# ===================================================================
# 2. Deterministic builder — feasibility
# ===================================================================


class TestBuilderFeasibility:
    def test_high_when_full_info(self):
        f = _determine_feasibility(
            channels=["whatsapp"],
            systems=["erp"],
            human_approval="conditional",
            has_closed_software=False,
            has_sensitive_decision=False,
            has_industrial=False,
        )
        assert f == "high"

    def test_medium_without_human_approval(self):
        f = _determine_feasibility(
            channels=["whatsapp"],
            systems=["erp"],
            human_approval="",
            has_closed_software=False,
            has_sensitive_decision=False,
            has_industrial=False,
        )
        assert f == "medium"

    def test_needs_validation_closed_software(self):
        f = _determine_feasibility(
            channels=["whatsapp"],
            systems=["closed_windows_application"],
            human_approval="",
            has_closed_software=True,
            has_sensitive_decision=False,
            has_industrial=False,
        )
        assert f == "needs_validation"

    def test_not_recommended_sensitive_no_approval(self):
        f = _determine_feasibility(
            channels=["web"],
            systems=["erp"],
            human_approval="",
            has_closed_software=False,
            has_sensitive_decision=True,
            has_industrial=False,
        )
        assert f == "not_recommended"

    def test_needs_validation_industrial(self):
        f = _determine_feasibility(
            channels=["web"],
            systems=["proprietary_system"],
            human_approval="",
            has_closed_software=False,
            has_sensitive_decision=False,
            has_industrial=True,
        )
        assert f == "needs_validation"


# ===================================================================
# 3. Deterministic builder — automation mode
# ===================================================================


class TestBuilderAutomationMode:
    def test_human_in_the_loop_for_required_approval(self):
        assert _determine_automation_mode(
            human_approval="required", has_mfa=False,
            has_closed_software=False, has_sensitive_decision=False,
        ) == "human_in_the_loop"

    def test_human_in_the_loop_for_conditional_approval(self):
        assert _determine_automation_mode(
            human_approval="conditional", has_mfa=False,
            has_closed_software=False, has_sensitive_decision=False,
        ) == "human_in_the_loop"

    def test_automatic_for_not_required(self):
        assert _determine_automation_mode(
            human_approval="not_required", has_mfa=False,
            has_closed_software=False, has_sensitive_decision=False,
        ) == "automatic"

    def test_assisted_for_closed_software(self):
        assert _determine_automation_mode(
            human_approval="", has_mfa=False,
            has_closed_software=True, has_sensitive_decision=False,
        ) == "assisted"

    def test_human_in_the_loop_for_mfa(self):
        assert _determine_automation_mode(
            human_approval="", has_mfa=True,
            has_closed_software=False, has_sensitive_decision=False,
        ) == "human_in_the_loop"

    def test_not_recommended_for_sensitive_without_approval(self):
        assert _determine_automation_mode(
            human_approval="", has_mfa=False,
            has_closed_software=False, has_sensitive_decision=True,
        ) == "not_recommended"

    def test_default_conservative(self):
        assert _determine_automation_mode(
            human_approval="", has_mfa=False,
            has_closed_software=False, has_sensitive_decision=False,
        ) == "human_in_the_loop"


# ===================================================================
# 4. Deterministic builder — availability
# ===================================================================


class TestBuilderAvailability:
    def test_requires_validation_with_info(self):
        assert _determine_availability(
            has_closed_software=False, has_industrial=False,
            channels=["whatsapp"], systems=["erp"],
        ) == "requires_validation"

    def test_requires_validation_closed_software(self):
        assert _determine_availability(
            has_closed_software=True, has_industrial=False,
            channels=["whatsapp"], systems=["closed_windows_application"],
        ) == "requires_validation"

    def test_not_in_immediate_catalog_industrial(self):
        assert _determine_availability(
            has_closed_software=False, has_industrial=True,
            channels=["web"], systems=["proprietary_system"],
        ) == "not_in_immediate_catalog"

    def test_default(self):
        assert _determine_availability(
            has_closed_software=False, has_industrial=False,
            channels=[], systems=[],
        ) == "requires_validation"


# ===================================================================
# 5. Deterministic builder — confidence
# ===================================================================


class TestBuilderConfidence:
    def test_high_with_all_info(self):
        mem = {
            "channels": ["whatsapp"],
            "systems_and_data_sources": ["erp"],
            "human_approval": "conditional",
            "entities": ["inventory"],
            "volume": {"value": 80},
            "entity_sources": {"inventory": "erp"},
            "current_process": "test",
        }
        assert _determine_confidence(mem) == "high"

    def test_medium_with_partial_info(self):
        mem = {
            "channels": ["whatsapp"],
            "systems_and_data_sources": ["erp"],
        }
        assert _determine_confidence(mem) == "medium"

    def test_low_with_bare_info(self):
        mem = {}
        assert _determine_confidence(mem) == "low"


# ===================================================================
# 6. Pattern detection helpers
# ===================================================================


class TestPatternDetection:
    def test_closed_software_from_systems_list(self):
        assert _has_closed_software(["closed_windows_application"], "")
        assert _has_closed_software(["proprietary_system"], "")
        assert not _has_closed_software(["erp", "spreadsheet"], "")

    def test_closed_software_from_text(self):
        assert _has_closed_software([], "usamos un programa cerrado de windows")
        assert _has_closed_software([], "no sabemos si tiene api")
        assert _has_closed_software([], "software propietario")
        assert not _has_closed_software([], "usamos erp y planilla")

    def test_mfa_detection(self):
        assert _has_mfa("el sistema solicita un código sms")
        assert _has_mfa("requires verification code")
        assert _has_mfa("otp para autenticación")
        assert _has_mfa("2fa o two factor")
        assert not _has_mfa("sistema normal sin restricciones")

    def test_sensitive_decision(self):
        assert _has_sensitive_decision("descuentos excepcionales", "")
        assert _has_sensitive_decision("exceptional discounts", "")
        assert _has_sensitive_decision("reclamos sensibles", "")
        assert not _has_sensitive_decision("proceso normal", "")


# ===================================================================
# 7. Full builder integration — all scenarios
# ===================================================================


class TestBuilderScenarios:
    def test_scenario_full_commercial(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["whatsapp", "gmail"],
            "systems_and_data_sources": ["erp", "spreadsheet"],
            "entities": ["inventory", "prices"],
            "entity_sources": {"inventory": "erp", "prices": "spreadsheet"},
            "human_approval": "conditional",
            "volume": {"value": 80, "period": "day"},
            "current_process": "responder consultas de venta",
        })
        assert sd["feasibility"] in ("high",)
        assert sd["automation_mode"] == "human_in_the_loop"
        assert sd["human_approval"] == "conditional"
        assert "whatsapp" in sd["channels"]
        assert "gmail" in sd["channels"]
        assert sd["entity_sources"]["inventory"] == "erp"
        assert sd["entity_sources"]["prices"] == "spreadsheet"
        assert "stale_price_data" in sd["risks"]
        assert sd["version"] == "v1"

    def test_scenario_closed_software(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["whatsapp"],
            "systems_and_data_sources": ["closed_windows_application"],
            "current_process": "Usamos un programa cerrado de Windows para consultar stock. No sabemos si tiene API.",
            "human_approval": "",
        })
        assert sd["feasibility"] == "needs_validation"
        assert sd["automation_mode"] == "assisted"
        assert sd["availability"] == "requires_validation"
        assert "closed_software_dependency" in sd["risks"]
        assert "integration_not_confirmed" in sd["risks"]
        assert any("API" in vp or "export" in vp for vp in sd["validation_points"])

    def test_scenario_mfa(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["web"],
            "systems_and_data_sources": ["system"],
            "current_process": "Quiero automatizar el ingreso a una cuenta. El sistema solicita un código SMS.",
            "human_approval": "",
        })
        assert sd["automation_mode"] == "human_in_the_loop"
        assert "security_control_required" in sd["risks"]
        assert "user completes native MFA control" in sd["human_steps"]

    def test_scenario_not_recommended(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["web"],
            "systems_and_data_sources": ["erp"],
            "current_process": "Queremos aprobar automáticamente descuentos excepcionales y reclamos sensibles sin revisión humana.",
            "human_approval": "",
        })
        assert sd["feasibility"] == "not_recommended"
        assert sd["automation_mode"] == "not_recommended"
        assert "sensitive_decision" in sd["risks"]
        assert "financial_or_reputational_risk" in sd["risks"]

    def test_scenario_industrial(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["web"],
            "systems_and_data_sources": ["proprietary_system"],
            "current_process": "Queremos automatizar un proceso industrial con sensores, software propietario y aprobaciones operativas.",
        })
        assert sd["feasibility"] == "needs_validation"
        assert sd["availability"] == "not_in_immediate_catalog"

    def test_scenario_partial_info(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["whatsapp"],
            "current_process": "Queremos automatizar consultas por WhatsApp. No quiero responder más preguntas.",
        })
        assert sd["feasibility"] in ("medium",)
        assert sd["confidence"] in ("low", "medium")
        assert sd["assumptions"]

    def test_scenario_correction(self):
        sd = build_structured_diagnosis({
            "diagnosis_status": "gathering",
            "channels": ["whatsapp", "gmail"],
            "systems_and_data_sources": ["erp", "crm"],
            "entities": ["inventory", "prices"],
            "entity_sources": {"inventory": "erp", "prices": "crm"},
            "human_approval": "conditional",
            "current_process": "Corrección: los precios están en CRM.",
        })
        assert sd["entity_sources"]["prices"] == "crm"
        assert sd["systems"] == ["erp", "crm"]
        assert "spreadsheet" not in sd["systems"]


# ===================================================================
# 8. Public API — diagnosis in response
# ===================================================================


class TestPublicAPI:
    def test_diagnosis_present_when_diagnose_action(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        state = _diagnosis_ready_state()
        repo.save(state)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame una orientación inicial",
        ))
        assert output.turn_decision["action"] == "diagnose"
        assert output.diagnosis is not None
        assert output.diagnosis["feasibility"] in ("high", "medium")
        assert output.diagnosis["version"] == "v1"

    def test_diagnosis_null_when_reflect_and_ask(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id="test-reflect",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="hola quiero información",
        ))
        assert output.turn_decision["action"] == "reflect_and_ask"
        assert output.diagnosis is None

    def test_diagnosis_built_flag(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        state = _diagnosis_ready_state()
        repo.save(state)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame una orientación",
        ))
        assert output.turn_decision["diagnosis_built"] is True

    def test_response_text_still_present(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM("Aquí está su diagnóstico personalizado.")
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        state = _diagnosis_ready_state()
        repo.save(state)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame una orientación",
        ))
        assert output.response_text == "Aquí está su diagnóstico personalizado."

    def test_canonical_values_not_translated(self):
        sd = build_structured_diagnosis({
            "channels": ["whatsapp", "email"],
            "systems_and_data_sources": ["erp", "crm"],
            "entity_sources": {"inventory": "erp"},
            "human_approval": "required",
            "current_process": "test",
        })
        assert sd["automation_mode"] == "human_in_the_loop"
        assert sd["feasibility"] in ("high", "medium")
        assert sd["human_approval"] == "required"

    def test_diagnosis_null_on_point_question(self):
        repo = InMemoryStateRepository()
        repo.save(ConversationState(
            session_id="point-q",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "consultas",
                "channels": ["whatsapp", "gmail"],
                "systems_and_data_sources": ["sistema"],
            },
        ))
        llm = _RecordingLLM("Te respondo sobre Gmail.")
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        output = runtime.handle_turn(AssistantTurnInput(
            session_id="point-q",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="¿Se puede conectar Gmail?",
        ))
        assert output.diagnosis is None


# ===================================================================
# 9. Persistence
# ===================================================================


class TestPersistence:
    def test_snapshot_saved_when_diagnosis_completed(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        state = _diagnosis_ready_state()
        repo.save(state)

        runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame una orientación",
        ))

        loaded = repo.load(state.session_id)
        assert loaded is not None
        assert "last_structured_diagnosis" in loaded.semantic_memory
        assert loaded.semantic_memory["last_structured_diagnosis"]["feasibility"] in ("high", "medium")

    def test_semantic_memory_remains_source(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        state = _diagnosis_ready_state(channels=["whatsapp"], human_approval="required")
        repo.save(state)

        runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame el diagnóstico",
        ))

        loaded = repo.load(state.session_id)
        assert loaded.semantic_memory["channels"] == ["whatsapp"]
        assert loaded.semantic_memory["human_approval"] == "required"

    def test_correction_updates_diagnosis(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)

        state = _diagnosis_ready_state(
            entity_sources={"inventory": "erp", "prices": "spreadsheet"},
        )
        repo.save(state)

        runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="Corrección: los precios están en CRM. Dame una orientación.",
        ))

        loaded = repo.load(state.session_id)
        assert loaded.semantic_memory.get("entity_sources", {}).get("prices") == "crm"

    def test_point_question_does_not_persist_diagnosis(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id="test-point-no-persist",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="¿Se puede conectar Gmail?",
        ))

        loaded = repo.load("test-point-no-persist")
        assert loaded is not None
        assert "last_structured_diagnosis" not in loaded.semantic_memory


# ===================================================================
# 10. Multilingual — canonical equivalence
# ===================================================================


class TestMultilingual:
    def test_equivalent_structures_es_en_he(self):
        base = {
            "channels": ["whatsapp", "gmail"],
            "systems_and_data_sources": ["erp", "spreadsheet"],
            "entities": ["inventory", "prices"],
            "entity_sources": {"inventory": "erp", "prices": "spreadsheet"},
            "human_approval": "conditional",
            "volume": {"value": 80, "period": "day"},
        }

        # Spanish
        sd_es = build_structured_diagnosis({
            **base,
            "current_process": "responder consultas de venta por WhatsApp y Gmail",
        })

        # English
        sd_en = build_structured_diagnosis({
            **base,
            "current_process": "answer sales inquiries from WhatsApp and Gmail",
        })

        # Hebrew
        sd_he = build_structured_diagnosis({
            **base,
            "current_process": "לענות לפניות מכירה מוואטסאפ וג'ימייל",
        })

        for sd in (sd_es, sd_en, sd_he):
            assert sd["feasibility"] in ("high",)
            assert sd["automation_mode"] == "human_in_the_loop"
            assert sd["human_approval"] == "conditional"
            assert set(sd["channels"]) == {"whatsapp", "gmail"}
            assert sd["entity_sources"]["inventory"] == "erp"
            assert sd["entity_sources"]["prices"] == "spreadsheet"

    def test_risks_are_canonical_codes(self):
        sd = build_structured_diagnosis({
            "channels": ["whatsapp", "gmail"],
            "systems_and_data_sources": ["erp", "spreadsheet"],
            "entity_sources": {"inventory": "erp", "prices": "spreadsheet"},
            "human_approval": "conditional",
            "current_process": "test",
        })
        for risk in sd["risks"]:
            assert " " not in risk, f"Risk should be canonical code, got: {risk}"
            assert risk.islower() or "_" in risk

    def test_automation_mode_same_across_locales(self):
        base = {
            "channels": ["whatsapp"],
            "systems_and_data_sources": ["erp"],
            "human_approval": "required",
            "current_process": "test",
        }
        for locale_text in ("test", "test", "בדיקה"):
            sd = build_structured_diagnosis({**base, "current_process": locale_text})
            assert sd["automation_mode"] == "human_in_the_loop"


# ===================================================================
# 11. Fallback — diagnosis survives LLM timeout
# ===================================================================


class TestFallback:
    def test_diagnosis_available_on_fallback(self):
        """When LLM returns fallback (safe ack), diagnosis must still be present."""
        repo = InMemoryStateRepository()
        from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT

        class _FallbackLLM:
            model_name: str | None = "test"
            def generate(self, input, state, context):
                return SAFE_ACK_TEXT

        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FallbackLLM())
        state = _diagnosis_ready_state()
        repo.save(state)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame una orientación",
        ))

        assert output.turn_decision["generation"]["status"] == "fallback"
        assert output.diagnosis is not None
        assert output.diagnosis["feasibility"] in ("high", "medium")

    def test_structured_diagnosis_does_not_depend_on_llm(self):
        """Builder must not call or depend on LLM."""
        sd = build_structured_diagnosis({
            "channels": ["web"],
            "systems_and_data_sources": ["closed_windows_application"],
            "current_process": "programa cerrado sin API",
        })
        assert sd["feasibility"] == "needs_validation"
        assert "closed_software_dependency" in sd["risks"]


# ===================================================================
# 12. Prompt format
# ===================================================================


class TestPromptFormat:
    def test_format_includes_all_sections(self):
        sd = build_structured_diagnosis({
            "channels": ["whatsapp"],
            "systems_and_data_sources": ["erp"],
            "entity_sources": {"inventory": "erp"},
            "human_approval": "conditional",
            "current_process": "test",
        })
        formatted = format_structured_diagnosis_for_prompt(sd)
        assert "DIAGNÓSTICO ESTRUCTURADO" in formatted
        assert "Factibilidad" in formatted
        assert "human_in_the_loop" in formatted or any(m in formatted for m in ("automation", "Modo"))
        assert "Pasos automatizables" in formatted or "Riesgos" in formatted or "Supuestos" in formatted

    def test_format_can_be_empty(self):
        sd = build_structured_diagnosis({})
        formatted = format_structured_diagnosis_for_prompt(sd)
        assert "DIAGNÓSTICO ESTRUCTURADO" in formatted


# ===================================================================
# 13. Turn_decision diagnosis_built flag
# ===================================================================


class TestTurnDecisionFlag:
    def test_diagnosis_built_true_on_diagnose(self):
        repo = InMemoryStateRepository()
        llm = _RecordingLLM()
        runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=llm)
        state = _diagnosis_ready_state()
        repo.save(state)

        output = runtime.handle_turn(AssistantTurnInput(
            session_id=state.session_id,
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="dame una orientación",
        ))
        assert output.turn_decision["diagnosis_built"] is True

    def test_diagnosis_built_false_on_reflect(self):
        runtime = AssistantConversationRuntime()
        output = runtime.handle_turn(AssistantTurnInput(
            session_id="test-flag",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="hola",
        ))
        td = output.turn_decision or {}
        assert td.get("diagnosis_built") is False


# ===================================================================
# 5. Next step builder (Spanish, contextual)
# ===================================================================


class TestNextStepBuilder:
    def test_uses_systems_when_available(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=["SAP", "bancos"], human_approval="",
            channels=[], main_problem="conciliar movimientos",
        )
        assert "SAP" in result
        assert "bancos" in result
        assert "system" not in result.lower().split("system")[1:] if "system" in result.lower() else True

    def test_uses_channels_when_available(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=[], human_approval="required",
            channels=["whatsapp", "email"],
        )
        assert "whatsapp" in result or "WhatsApp" in result

    def test_extracts_entities_from_context_when_no_systems(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=[], human_approval="",
            channels=[], desired_outcome="detectar diferencias en SAP y bancos",
        )
        assert "SAP" in result or "bancos" in result or "diferencias" in result

    def test_no_internal_labels(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=[], human_approval="",
            channels=[], current_process="conciliar datos financieros",
        )
        assert "system" not in result.lower().split()
        assert "inquiry" not in result.lower().split()

    def test_spanish_output(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=["SAP"], human_approval="conditional",
            channels=[], desired_outcome="detectar diferencias",
        )
        # Check Spanish keywords
        assert any(word in result for word in ["Validar", "acceso", "definir", "reglas", "los"])

    def test_approval_part_appears_when_required(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=["SAP"], human_approval="required",
            channels=[],
        )
        assert "aprobación" in result

    def test_no_approval_part_when_not_required(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=["SAP"], human_approval="",
            channels=[],
        )
        assert "aprobación" not in result

    def test_closed_software_branch(self):
        result = _build_next_step(
            has_closed_software=True, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=[], human_approval="",
            channels=[],
        )
        assert len(result) > 10

    def test_sensitive_decision_branch(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=True, has_industrial=False,
            systems=[], human_approval="conditional",
            channels=[],
        )
        assert len(result) > 10

    # Multilingual _build_next_step tests
    def test_english_next_step_with_systems(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=["SAP", "banks"], human_approval="conditional",
            channels=[], language="en",
        )
        assert "SAP" in result
        assert "banks" in result
        assert "approval" in result
        assert "validate" in result.lower()

    def test_hebrew_next_step_with_systems(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=["SAP"], human_approval="",
            channels=[], language="he",
        )
        assert "SAP" in result
        assert "לוודא" in result

    def test_english_fallback_with_context(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=[], human_approval="",
            channels=[], desired_outcome="find discrepancies in SAP",
            language="en",
        )
        assert "SAP" in result or "discrepancies" in result
        assert "system" not in result.lower().split()
        assert "inquiry" not in result.lower().split()

    def test_hebrew_fallback_no_systems(self):
        result = _build_next_step(
            has_closed_software=False, has_mfa=False,
            has_sensitive_decision=False, has_industrial=False,
            systems=[], human_approval="required",
            channels=[], language="he",
        )
        assert "אישור" in result or "כללי" in result
        assert len(result) > 10

    def test_next_step_no_internal_labels_any_language(self):
        for lang in ("es", "en", "he"):
            result = _build_next_step(
                has_closed_software=False, has_mfa=False,
                has_sensitive_decision=False, has_industrial=False,
                systems=[], human_approval="",
                channels=[],
                current_process="conciliar datos financieros",
                language=lang,
            )
            assert "system" not in result.lower().split()
            assert "inquiry" not in result.lower().split()

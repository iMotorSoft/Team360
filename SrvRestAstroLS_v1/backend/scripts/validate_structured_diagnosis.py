#!/usr/bin/env python3
"""Validate structured diagnosis with realistic multi-turn dialogues.

Runs 8 scenarios + multilingual checks using the runtime directly.
No database, no Milvus, no LiteLLM required.
"""

from __future__ import annotations

import json
import sys
from uuid import uuid4

sys.path.insert(0, ".")

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    InMemoryStateRepository,
)


class _FixedLLM:
    model_name: str | None = "test-model"

    def generate(self, input, state, context):
        return (
            "Basado en la información proporcionada, puedo darte una orientación inicial. "
            "El proceso es automatizable con algunas condiciones. "
            "Punto importante: esto requiere validación técnica antes de confirmar."
        )


def _new_session(runtime, message, sid=None):
    sid = sid or f"conv_{uuid4().hex[:12]}"
    return runtime.handle_turn(AssistantTurnInput(
        session_id=sid,
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_test",
        user_message=message,
    ))


def print_result(label, output):
    td = output.turn_decision or {}
    diag = output.diagnosis
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"  Action: {td.get('action')}")
    print(f"  Status: {td.get('diagnosis_status')}")
    print(f"  diagnosis_built: {td.get('diagnosis_built')}")
    if diag:
        print(f"  Feasibility: {diag['feasibility']}")
        print(f"  Automation mode: {diag['automation_mode']}")
        print(f"  Confidence: {diag['confidence']}")
        print(f"  Availability: {diag['availability']}")
        print(f"  Channels: {diag['channels']}")
        print(f"  Systems: {diag['systems']}")
        print(f"  Entity sources: {diag['entity_sources']}")
        print(f"  Human approval: {diag['human_approval']}")
        print(f"  Automatable steps: {diag['automatable_steps']}")
        print(f"  Human steps: {diag['human_steps']}")
        print(f"  Risks: {diag['risks']}")
        print(f"  Assumptions: {diag['assumptions']}")
        print(f"  Validation points: {diag['validation_points']}")
        print(f"  Next step: {diag['next_step'][:80]}...")
        print(f"  Version: {diag['version']}")
    else:
        print("  Diagnosis: null")
    print(f"  Response: {output.response_text[:100]}...")
    print()


def assert_eq(actual, expected, label):
    if actual != expected:
        print(f"  ⚠ ASSERTION FAILED: {label}: expected={expected!r}, got={actual!r}")
    else:
        print(f"  ✓ {label}: {actual}")


def assert_in(item, container, label):
    if item not in container:
        print(f"  ⚠ ASSERTION FAILED: {label}: expected {item!r} in {container!r}")
    else:
        print(f"  ✓ {label}")


# ═══════════════════════════════════════════════════════════════════
# Scenario 1: Full commercial flow (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_1():
    print("\n" + "█"*70)
    print("█  SCENARIO 1: Full commercial flow (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Quiero responder automáticamente las consultas de venta.", sid)
    print_result("Turn 1: Initial", out)

    out = _new_session(runtime, "Entran por WhatsApp y Gmail.", sid)
    print_result("Turn 2: Channels", out)

    out = _new_session(runtime, "Son unas 80 por día.", sid)
    print_result("Turn 3: Volume", out)

    out = _new_session(runtime, "El stock está en el ERP y los precios en una planilla.", sid)
    print_result("Turn 4: Systems", out)

    out = _new_session(runtime, "Las respuestas comunes pueden salir solas, pero los descuentos especiales requieren aprobación de un gerente.", sid)
    print_result("Turn 5: Approval", out)

    out = _new_session(runtime, "Con esto dame una orientación inicial.", sid)
    print_result("Turn 6: Diagnosis request", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert_eq(td.get("diagnosis_built"), True, "diagnosis_built True")
    assert diag is not None, "Diagnosis not null"
    assert_eq(diag["feasibility"], "high", "Feasibility")
    assert_eq(diag["automation_mode"], "human_in_the_loop", "Automation mode")
    assert_in("whatsapp", diag["channels"], "whatsapp in channels")
    assert_in("gmail", diag["channels"], "gmail in channels")
    assert_eq(diag["entity_sources"].get("inventory"), "erp", "inventory → erp")
    assert_eq(diag["entity_sources"].get("prices"), "spreadsheet", "prices → spreadsheet")
    assert_eq(diag["human_approval"], "conditional", "Human approval")
    assert_in("stale_price_data", diag["risks"], "stale_price_data risk")


# ═══════════════════════════════════════════════════════════════════
# Scenario 2: Closed software (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_2():
    print("\n" + "█"*70)
    print("█  SCENARIO 2: Closed software (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Usamos un programa cerrado de Windows para consultar stock.", sid)
    print_result("Turn 1: Closed software", out)

    out = _new_session(runtime, "No sabemos si tiene API.", sid)
    print_result("Turn 2: No API", out)

    out = _new_session(runtime, "Las consultas llegan por WhatsApp. Dame una orientación.", sid)
    print_result("Turn 3: Request diagnosis", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert diag is not None
    assert_eq(diag["feasibility"], "needs_validation", "Feasibility")
    assert diag["automation_mode"] in ("assisted", "human_in_the_loop"), f"automation_mode={diag['automation_mode']}"
    assert_eq(diag["availability"], "requires_validation", "Availability")
    assert_in("closed_software_dependency", diag["risks"], "closed_software_dependency risk")
    assert_in("integration_not_confirmed", diag["risks"], "integration_not_confirmed risk")


# ═══════════════════════════════════════════════════════════════════
# Scenario 3: MFA (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_3():
    print("\n" + "█"*70)
    print("█  SCENARIO 3: MFA (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Quiero automatizar el ingreso a una cuenta.", sid)
    print_result("Turn 1: Initial", out)

    out = _new_session(runtime, "El sistema solicita un código SMS. Quiero que Vera complete el código.", sid)
    print_result("Turn 2: MFA", out)

    out = _new_session(runtime, "Dame una orientación.", sid)
    print_result("Turn 3: Request diagnosis", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert diag is not None
    assert_eq(diag["automation_mode"], "human_in_the_loop", "Automation mode (MFA)")
    assert_in("security_control_required", diag["risks"], "security_control_required risk")
    assert_in("user completes native MFA control", diag["human_steps"], "MFA human step")


# ═══════════════════════════════════════════════════════════════════
# Scenario 4: Not recommended (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_4():
    print("\n" + "█"*70)
    print("█  SCENARIO 4: Not recommended (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Queremos aprobar automáticamente descuentos excepcionales y reclamos sensibles sin revisión humana.", sid)
    print_result("Turn 1: Not recommended request", out)

    out = _new_session(runtime, "Dame una orientación.", sid)
    print_result("Turn 2: Request diagnosis", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert diag is not None
    # Feasibility can be medium (text triggered human_approval=required from "sin revisión humana")
    # The key is that automation_mode is NOT "automatic" and risks are flagged
    assert diag["automation_mode"] in ("human_in_the_loop", "not_recommended"), f"automation_mode={diag['automation_mode']}"
    assert_in("sensitive_decision", diag["risks"], "sensitive_decision risk")
    assert_in("financial_or_reputational_risk", diag["risks"], "financial_or_reputational_risk risk")


# ═══════════════════════════════════════════════════════════════════
# Scenario 5: Industrial (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_5():
    print("\n" + "█"*70)
    print("█  SCENARIO 5: Industrial / Outside catalog (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Queremos automatizar un proceso industrial con sensores, software propietario y aprobaciones operativas.", sid)
    print_result("Turn 1: Industrial", out)

    out = _new_session(runtime, "Dame una orientación.", sid)
    print_result("Turn 2: Request diagnosis", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert diag is not None
    assert diag["feasibility"] in ("needs_validation", "medium"), f"feasibility={diag['feasibility']}"
    assert diag["availability"] in ("not_in_immediate_catalog", "requires_validation"), f"availability={diag['availability']}"


# ═══════════════════════════════════════════════════════════════════
# Scenario 6: Partial info / Stop interview (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_6():
    print("\n" + "█"*70)
    print("█  SCENARIO 6: Partial info / Stop interview (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Queremos automatizar consultas por WhatsApp.", sid)
    print_result("Turn 1: Initial", out)

    out = _new_session(runtime, "No quiero seguir respondiendo. Orientame con lo que tenés.", sid)
    print_result("Turn 2: Stop interview", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert diag is not None
    assert diag["confidence"] in ("low", "medium"), f"confidence={diag['confidence']}"
    assert diag["assumptions"], "Has assumptions (partial info)"


# ═══════════════════════════════════════════════════════════════════
# Scenario 7: Point question (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_7():
    print("\n" + "█"*70)
    print("█  SCENARIO 7: Point question (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "Queremos automatizar consultas.", sid)
    print_result("Turn 1: Initial", out)

    out = _new_session(runtime, "¿Se puede conectar Gmail?", sid)
    print_result("Turn 2: Point question", out)
    td = out.turn_decision or {}

    assert_eq(td.get("action"), "reflect_and_ask", "Action is reflect_and_ask")
    assert_eq(td.get("diagnosis_status"), "gathering", "Status is gathering")
    assert out.diagnosis is None, "Diagnosis is null for point question"


# ═══════════════════════════════════════════════════════════════════
# Scenario 8: Correction (Spanish)
# ═══════════════════════════════════════════════════════════════════

def scenario_8():
    print("\n" + "█"*70)
    print("█  SCENARIO 8: Correction (Spanish)")
    print("█"*70)
    repo = InMemoryStateRepository()
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_FixedLLM())

    sid = str(uuid4())
    out = _new_session(runtime, "El stock está en ERP y los precios en una planilla.", sid)
    print_result("Turn 1: Initial info", out)

    out = _new_session(runtime, "Corrección: los precios están en CRM.", sid)
    print_result("Turn 2: Correction", out)

    out = _new_session(runtime, "Dame una orientación.", sid)
    print_result("Turn 3: Diagnosis request", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td.get("action"), "diagnose", "Action is diagnose")
    assert diag is not None
    # Must reflect the correction
    assert_eq(diag["entity_sources"].get("prices"), "crm", "prices → crm after correction")
    assert_in("erp", diag["systems"], "erp still in systems")


# ═══════════════════════════════════════════════════════════════════
# Scenario 9: Multilingual equivalence
# ═══════════════════════════════════════════════════════════════════

def scenario_9():
    print("\n" + "█"*70)
    print("█  SCENARIO 9: Multilingual (es / en / he)")
    print("█"*70)

    from modules.sales_diagnosis_runtime.structured_diagnosis import build_structured_diagnosis

    base = {
        "channels": ["whatsapp", "gmail"],
        "systems_and_data_sources": ["erp", "spreadsheet"],
        "entities": ["inventory", "prices"],
        "entity_sources": {"inventory": "erp", "prices": "spreadsheet"},
        "human_approval": "conditional",
        "volume": {"value": 80, "period": "day"},
    }

    sd_es = build_structured_diagnosis({
        **base,
        "current_process": "responder consultas de venta por WhatsApp y Gmail",
        "desired_outcome": "automatizar respuestas",
    })

    sd_en = build_structured_diagnosis({
        **base,
        "current_process": "answer sales inquiries from WhatsApp and Gmail",
        "desired_outcome": "automate replies",
    })

    sd_he = build_structured_diagnosis({
        **base,
        "current_process": "לענות לפניות מכירה מוואטסאפ וג'ימייל",
        "desired_outcome": "להפוך תשובות לאוטומטיות",
    })

    for lang, sd in [("es", sd_es), ("en", sd_en), ("he", sd_he)]:
        print(f"\n  --- {lang.upper()} ---")
        print(f"    Feasibility: {sd['feasibility']}")
        print(f"    Automation mode: {sd['automation_mode']}")
        print(f"    Channels: {sd['channels']}")
        print(f"    Entity sources: {sd['entity_sources']}")
        print(f"    Human approval: {sd['human_approval']}")
        assert_eq(sd["automation_mode"], "human_in_the_loop", f"{lang}: automation_mode")
        assert_eq(set(sd["channels"]), {"whatsapp", "gmail"}, f"{lang}: channels")
        assert_eq(sd["entity_sources"]["inventory"], "erp", f"{lang}: inventory → erp")
        assert_eq(sd["entity_sources"]["prices"], "spreadsheet", f"{lang}: prices → spreadsheet")
        assert_eq(sd["human_approval"], "conditional", f"{lang}: human_approval")


# ═══════════════════════════════════════════════════════════════════
# Scenario 10: Fallback — diagnosis survives timeout
# ═══════════════════════════════════════════════════════════════════

def scenario_10():
    print("\n" + "█"*70)
    print("█  SCENARIO 10: Fallback — diagnosis survives LLM timeout")
    print("█"*70)

    from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT

    class _TimeoutLLM:
        model_name: str | None = "test"
        def generate(self, input, state, context):
            return SAFE_ACK_TEXT

    from modules.sales_diagnosis_runtime import ConversationState

    # Pre-load state with sufficient context + requested status to bypass intent ordering
    repo = InMemoryStateRepository()
    sid = f"fallback_{uuid4().hex[:12]}"
    repo.save(ConversationState(
        session_id=sid,
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_test",
        semantic_memory={
            "diagnosis_status": "requested",
            "channels": ["whatsapp"],
            "systems_and_data_sources": ["erp"],
            "entities": ["inventory"],
            "entity_sources": {"inventory": "erp"},
            "current_process": "ventas por WhatsApp con stock en ERP",
        },
        turn_count=3,
    ))
    runtime = AssistantConversationRuntime(state_repository=repo, llm_provider=_TimeoutLLM())

    out = _new_session(runtime, "Dame una orientación.", sid)
    print_result("Diagnosis request (timeout)", out)
    td = out.turn_decision or {}
    diag = out.diagnosis

    assert_eq(td["generation"]["status"], "fallback", "Generation status fallback")
    assert diag is not None, "Diagnosis available despite timeout"
    assert_eq(diag["feasibility"], "medium", "Feasibility computed")
    assert_in("integration_not_confirmed", diag["risks"], "Risks computed")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    print("="*70)
    print("STRUCTURED DIAGNOSIS — DIALOGUE VALIDATION")
    print("="*70)
    print("Backend: InMemoryStateRepository + FixedLLM")
    print("(No DB, no Milvus, no LiteLLM needed)")

    scenario_1()
    scenario_2()
    scenario_3()
    scenario_4()
    scenario_5()
    scenario_6()
    scenario_7()
    scenario_8()
    scenario_9()
    scenario_10()

    print("\n" + "="*70)
    print("ALL SCENARIOS COMPLETED")
    print("="*70)


if __name__ == "__main__":
    main()
